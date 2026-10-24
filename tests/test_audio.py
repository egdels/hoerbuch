import numpy as np
import pytest

from hoerbuch.audio import normalize_level, read_wav, trim_silence, write_wav
from hoerbuch.tts import plausible


def sinus(sekunden=1.0, sr=24000, amp=0.05):
    t = np.arange(int(sekunden * sr)) / sr
    return (amp * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


def test_normalize_level_trifft_ziel_rms():
    out = normalize_level(sinus(), target_rms_db=-20.0, max_peak_db=-2.0)
    rms_db = 20 * np.log10(np.sqrt(np.mean(out.astype(np.float64) ** 2)))
    assert rms_db == pytest.approx(-20.0, abs=0.1)


def test_normalize_level_begrenzt_spitze():
    # Sinus: Spitze liegt 3 dB über RMS → bei Ziel -3 dB RMS würde die Spitze 0 dB erreichen
    out = normalize_level(sinus(), target_rms_db=-3.0, max_peak_db=-6.0)
    peak_db = 20 * np.log10(np.max(np.abs(out)))
    assert peak_db == pytest.approx(-6.0, abs=0.1)


def test_normalize_level_laesst_stille_in_ruhe():
    still = np.zeros(1000, dtype=np.float32)
    assert np.array_equal(normalize_level(still), still)
    assert normalize_level(np.zeros(0, dtype=np.float32)).size == 0


def test_trim_silence():
    sr = 1000
    audio = np.concatenate([np.zeros(500), np.full(200, 0.5), np.zeros(500)]).astype(np.float32)
    out = trim_silence(audio, sr, thresh=0.01, keep=0.05)
    assert 200 + 2 * 50 - 1 <= out.size <= 200 + 2 * 50
    assert trim_silence(np.zeros(100, dtype=np.float32), sr).size == 0


def test_wav_roundtrip(tmp_path):
    audio = sinus(0.1, amp=0.5)
    p = tmp_path / "a.wav"
    write_wav(p, audio, 24000)
    back, sr = read_wav(p)
    assert sr == 24000
    assert back.shape == audio.shape
    assert np.max(np.abs(back - audio)) < 1e-4
    assert not p.with_suffix(".tmp.wav").exists()


def test_plausible():
    text = "x" * 140                      # 140 Zeichen ≈ 10 s bei 14 Zeichen/s
    assert plausible(text, 10.0)
    assert not plausible(text, 60.0)      # viel zu langsam → Gestammel
    assert not plausible(text, 2.0)       # viel zu schnell → Text verschluckt
    assert plausible("Ja.", 1.0)          # sehr kurze Texte werden nicht geprüft
    assert not plausible("Ja.", 0.1)


# ---- Export-Formate -------------------------------------------------------

import shutil
import subprocess
from pathlib import Path

from hoerbuch.audio import BITRATE_STANDARD, FORMATE, build_output, ffmetadata, sicherer_name


def test_sicherer_name():
    assert sicherer_name("Kapitel 3: Die Rückkehr?", 3) == "Kapitel 3 Die Rückkehr"
    assert sicherer_name("Ende...", 7) == "Ende"            # kein Punkt am Ende (Windows)
    assert sicherer_name("***", 2) == "Kapitel 2"
    assert len(sicherer_name("x" * 100, 1)) == 60


def test_ffmetadata_kapitel_und_maskierung(tmp_path):
    files = [("Kapitel 1", tmp_path / "a.wav", 1.5), ("Teil 2; a=b #c", tmp_path / "b.wav", 2.25)]
    meta = ffmetadata(files, "Titel=Test", autor="Erika Muster")
    assert meta.startswith(";FFMETADATA1\ntitle=Titel\\=Test\n")
    assert "artist=Erika Muster\n" in meta and "album=Titel\\=Test\n" in meta
    assert meta.count("[CHAPTER]") == 2
    assert "START=0\nEND=1500\ntitle=Kapitel 1\n" in meta
    assert "START=1500\nEND=3750\ntitle=Teil 2\; a\\=b \\#c\n" in meta
    assert "artist" not in ffmetadata(files, "T")


def test_formate_und_bitraten_konsistent():
    assert set(BITRATE_STANDARD) == set(FORMATE) - {"wav"}


def _kapitel_wavs(tmp_path):
    sr = 24000
    files = []
    for n, (titel, sek) in enumerate([("Kapitel 1", 0.6), ("Kapitel 2: Ende.", 0.4)], 1):
        p = tmp_path / f"kapitel_{n:03d}.wav"
        write_wav(p, sinus(sek, sr), sr)
        files.append((titel, p, sek))
    return files


def _kapitel_in_datei(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_chapters", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return [ln for ln in out.splitlines() if ln.strip()]


def test_build_output_wav_ohne_ffmpeg(tmp_path):
    files = _kapitel_wavs(tmp_path)
    build_output(files, tmp_path / "buch.txt", "Buch", fmt="wav")
    out = sorted((tmp_path / "buch_wav").glob("*.wav"))
    assert [p.name for p in out] == ["001 - Kapitel 1.wav", "002 - Kapitel 2 Ende.wav"]


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg fehlt")
@pytest.mark.parametrize("fmt,endung", [("m4b", ".m4b"), ("mp3-buch", ".mp3"), ("opus", ".opus")])
def test_build_output_eine_datei_mit_kapiteln(tmp_path, fmt, endung):
    files = _kapitel_wavs(tmp_path)
    build_output(files, tmp_path / "buch.txt", "Buch", fmt=fmt, autor="Erika Muster")
    out = tmp_path / ("buch" + endung)
    assert out.exists() and out.stat().st_size > 1000
    assert len(_kapitel_in_datei(out)) == 2


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg fehlt")
def test_build_output_mp3_je_kapitel_mit_cover(tmp_path):
    files = _kapitel_wavs(tmp_path)
    cover = tmp_path / "cover.png"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=1",
                    "-frames:v", "1", str(cover)], check=True)
    build_output(files, tmp_path / "buch.txt", "Buch", fmt="mp3", cover=str(cover), bitrate="48k")
    out = sorted((tmp_path / "buch_mp3").glob("*.mp3"))
    assert [p.name for p in out] == ["001 - Kapitel 1.mp3", "002 - Kapitel 2 Ende.mp3"]
    streams = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0",
                              str(out[0])], capture_output=True, text=True).stdout
    assert "video" in streams        # eingebettetes Cover



# ---- Abbrucherkennung -----------------------------------------------------

def _sprache(sekunden, sr=24000):
    t = np.arange(int(sekunden * sr)) / sr
    return (0.1 * np.sin(2 * np.pi * 220 * t) * (1 + 0.5 * np.sin(2 * np.pi * 4 * t))).astype(np.float32)


def test_abrupt_ending_erkennt_harten_schnitt():
    from hoerbuch.tts import abrupt_ending
    sr = 24000
    hart = _sprache(1.2, sr)                                  # endet bei vollem Pegel
    assert abrupt_ending(hart, sr)
    weich = _sprache(1.2, sr).copy()                          # klingt über 200 ms exponentiell aus
    n = int(0.2 * sr)
    weich[-n:] *= np.exp(-np.linspace(0, 6, n)).astype(np.float32)
    assert not abrupt_ending(weich, sr)
    assert not abrupt_ending(np.zeros(sr, dtype=np.float32), sr)
    assert not abrupt_ending(_sprache(0.2, sr), sr)          # zu kurz für eine Aussage
