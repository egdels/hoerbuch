"""WAV lesen/schreiben, Pegel normalisieren, Stille kürzen, M4B/MP3 mit ffmpeg bauen."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import wave
from pathlib import Path

from .hilfen import fmt_dur
from .konfig import FFMPEG_HINT, MAX_PEAK_DB, TARGET_RMS_DB

def normalize_level(audio, target_rms_db: float = TARGET_RMS_DB, max_peak_db: float = MAX_PEAK_DB):
    """Statische Verstärkung auf Ziel-RMS, begrenzt durch den maximalen Spitzenpegel."""
    import numpy as np
    if audio.size == 0:
        return audio
    rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    peak = float(np.max(np.abs(audio)))
    if rms < 1e-6 or peak < 1e-6:
        return audio
    gain = 10 ** (target_rms_db / 20) / rms
    gain = min(gain, 10 ** (max_peak_db / 20) / peak)
    return (audio * gain).astype(np.float32)


def trim_silence(audio, sr: int, thresh: float = 0.01, keep: float = 0.05):
    import numpy as np
    if audio.size == 0:
        return audio
    idx = np.where(np.abs(audio) > thresh)[0]
    if idx.size == 0:
        return audio[:0]
    pad = int(keep * sr)
    return audio[max(0, idx[0] - pad): min(audio.size, idx[-1] + pad)]


def write_wav(path: Path, audio, sr: int):
    import numpy as np
    a = np.clip(audio, -1.0, 1.0)
    pcm = (a * 32767).astype("<i2")
    tmp = path.with_suffix(".tmp.wav")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    os.replace(tmp, path)


def read_wav(path: Path):
    import numpy as np
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    return data.astype(np.float32) / 32767, sr


def build_output(chapter_files, src: Path, title: str, *, fmt: str = "m4b",
                 ausgabe: str | None = None, cover: str | None = None):
    """Setzt die Kapitel-WAVs zu einer M4B-Datei mit Kapitelmarken oder zu MP3s zusammen."""
    if not shutil.which("ffmpeg"):
        print(f"ffmpeg fehlt ({FFMPEG_HINT}). Die Kapitel liegen als WAV im Arbeitsordner.")
        return
    work = chapter_files[0][1].parent

    if fmt == "mp3":
        outdir = Path(ausgabe or src.with_suffix("").as_posix() + "_mp3")
        outdir.mkdir(exist_ok=True)
        for n, (t, wav, _) in enumerate(chapter_files, 1):
            # Nur unbedenkliche Zeichen; unter Windows dürfen Namen nicht mit Punkt oder Leerzeichen enden
            safe = re.sub(r"[^\w äöüÄÖÜß.-]", "", t)[:60].strip(" .") or f"Kapitel {n}"
            mp3 = outdir / f"{n:03d} - {safe}.mp3"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav),
                            "-codec:a", "libmp3lame", "-q:a", "4",
                            "-metadata", f"title={t}", "-metadata", f"album={title}",
                            "-metadata", f"track={n}/{len(chapter_files)}", str(mp3)],
                           check=True)
        print(f"Fertig: {outdir}/ ({len(chapter_files)} MP3-Dateien)")
        return

    listfile = work / "liste.txt"
    # Pfade mit Schrägstrichen: so versteht sie ffmpeg auf allen Plattformen, auch unter Windows
    listfile.write_text("".join(f"file '{w.resolve().as_posix()}'\n" for _, w, _ in chapter_files),
                        encoding="utf-8")
    meta = [";FFMETADATA1", f"title={title}", "genre=Hörbuch"]
    pos = 0
    total = 0.0
    for t, _, dur in chapter_files:
        start = pos
        total += dur
        pos = int(round(total * 1000))
        meta += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={start}", f"END={pos}",
                 "title=" + re.sub(r"([=;#\\])", r"\\\1", t)]
    metafile = work / "kapitel.ffmeta"
    metafile.write_text("\n".join(meta) + "\n", encoding="utf-8")

    out = Path(ausgabe or src.with_suffix(".m4b"))
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "concat", "-safe", "0", "-i", str(listfile),
           "-i", str(metafile)]
    if cover:
        cmd += ["-i", str(cover)]
    cmd += ["-map_metadata", "1", "-map_chapters", "1", "-map", "0:a"]
    if cover:
        cmd += ["-map", "2:v", "-c:v", "mjpeg", "-disposition:v", "attached_pic"]
    cmd += ["-c:a", "aac", "-b:a", "64k", "-ac", "1", "-movflags", "+faststart", "-f", "mp4"]
    subprocess.run(cmd + [str(out)], check=True)
    print(f"Fertig: {out}  ({fmt_dur(total)}, {len(chapter_files)} Kapitel)")
