"""Die fünf Unterbefehle: exportieren, bereinigen, probe, stimme, vertonen."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .audio import build_output, normalize_level, read_wav, trim_silence, write_wav
from .bereinigung import CleanReport, clean_text, read_text
from .epub import EPUB_SKIP_DEFAULT, epub_to_text
from .hilfen import fmt_dur
from .kapitel import parse_book, sample_paragraph
from .ki import ki_refine
from .konfig import DEFAULT_VOICE, REF_SENTENCE, VOICE_DESIGNS, default_voice
from .tts import Voice, synth_checked
from .zahlen import num2words_available

def cmd_exportieren(args) -> Path:
    src = Path(args.datei)
    title, author, text, info = epub_to_text(src, args.ohne if args.ohne is not None else EPUB_SKIP_DEFAULT,
                                             with_intro=not args.ohne_intro)
    if args.ausgabe:
        out = Path(args.ausgabe)
    else:
        stem = re.sub(r"[^\w\-]+", "_", title).strip("_") if title else src.stem
        out = src.with_name(stem + ".txt")
    out.write_text(text, encoding="utf-8")
    print(f"Exportiert: {out}")
    if title or author:
        print(f"  Titel/Autor:  {title} – {author}")
    for line in info:
        print(line)
    print("  Kapitel:")
    for ln in text.splitlines():
        if ln.startswith("# "):
            print(f"    {ln}")
    return out


def cmd_bereinigen(args) -> Path:
    src = Path(args.datei)
    if src.suffix.lower() == ".epub":
        args.datei = str(cmd_exportieren(args))
        src = Path(args.datei)
        print()
    report = CleanReport(ki=bool(getattr(args, "ki", False)), numbers=not args.ziffern_lassen)
    text = read_text(src, report)
    cleaned = clean_text(text, report)
    stem = src.name[:-4] if src.name.lower().endswith(".txt") else src.name
    out = src.with_name(stem + (".neu.txt" if stem.endswith(".bereinigt") else ".bereinigt.txt"))
    log = None
    if report.ki:
        log = Path(args.ki_protokoll or src.with_name(stem + ".ki-protokoll.txt"))
        cleaned = ki_refine(cleaned, args.ki_modell, report, log, verbose=args.verbose,
                            max_blocks=args.ki_bloecke, headings=args.ki_ueberschriften)
    out.write_text(cleaned, encoding="utf-8")

    print(f"Bereinigt: {out}")
    print(f"  Kodierung:            {report.encoding}")
    print(f"  Absatzerkennung:      {report.paragraph_mode}")
    print(f"  Seitenzahlen entfernt:{report.removed_pages:>6}")
    print(f"  Trennungen aufgelöst: {report.dehyphenated:>6}")
    print(f"  Abkürzungen ersetzt:  {report.abbreviations:>6}")
    print(f"  URLs entfernt:        {report.urls:>6}")
    if report.numbers:
        hint = "" if num2words_available() else "  (num2words fehlt: pip install num2words)"
        print(f"  Zahlen ausgeschrieben:{report.numbers_expanded:>6}{hint}")
    if report.removed_headers:
        print("  Kopf-/Fußzeilen entfernt:")
        for s, c in sorted(report.removed_headers.items(), key=lambda x: -x[1])[:10]:
            print(f"    {c:>4}× {s!r}")
    if report.ki:
        print(f"  KI-Ersetzungen:       {report.ki_applied:>6}  ({report.ki_rejected} verworfen, "
              f"{report.ki_headings} Überschriften, {fmt_dur(report.ki_seconds)}) → {log}")
        report.chapters = [ln[2:] for ln in cleaned.splitlines() if ln.startswith("# ")]
    print(f"  Kapitel erkannt:      {len(report.chapters):>6}")
    for h in report.chapters[:40]:
        print(f"    # {h}")
    if len(report.chapters) > 40:
        print(f"    … und {len(report.chapters) - 40} weitere")
    if not report.chapters:
        print("  Hinweis: Keine Kapitel erkannt. Du kannst in der bereinigten Datei")
        print("  selbst Zeilen mit '# Kapitelname' einfügen.")
    print(f"  Zeichen gesamt:       {len(cleaned):>6}  "
          f"(≈ {len(cleaned) / 14 / 3600:.1f} h Hörzeit)")
    return out


def cmd_probe(args):
    src = Path(args.datei)
    text = src.read_text(encoding="utf-8")
    sample = sample_paragraph(text)
    outdir = Path(args.ausgabe or "probe")
    outdir.mkdir(exist_ok=True)
    print(f"Probetext ({len(sample)} Zeichen):\n  {sample}\n")

    if args.nur_ref and not args.ref and not default_voice():
        sys.exit("--nur-ref braucht --ref oder eine eingerichtete Standardstimme (hoerbuch stimme …).")
    # Schritt A: Referenzstimmen per Beschreibung entwerfen
    refs: dict[str, Path] = {}
    if not args.nur_ref:
        designer = Voice(args.modell_design, verbose=args.verbose)
        for name, desc in VOICE_DESIGNS.items():
            path = outdir / f"stimme_{name}.wav"
            if path.exists():
                print(f"  vorhanden: {path}")
            else:
                t0 = time.time()
                audio = normalize_level(trim_silence(designer.synth(REF_SENTENCE, instruct=desc, seed=42),
                                                     designer.sample_rate))
                write_wav(path, audio, designer.sample_rate)
                print(f"  Referenzstimme {path}  ({audio.size / designer.sample_rate:.1f} s, "
                      f"{time.time() - t0:.0f} s Rechenzeit)")
            (outdir / f"stimme_{name}.txt").write_text(REF_SENTENCE, encoding="utf-8")
            refs[name] = path
        designer.close()

    if args.ref:
        refs["eigene"] = Path(args.ref)
    elif default_voice():
        refs["eigene"] = default_voice()
        print(f"  eigene Standardstimme: {refs['eigene']}")

    # Schritt B: Probeabsatz mit jeder Referenzstimme (so klingt später das Buch)
    reader = Voice(args.modell, verbose=args.verbose)
    for name, ref in refs.items():
        ref_text = args.ref_text if name == "eigene" else REF_SENTENCE
        if name == "eigene" and not ref_text:
            txt = ref.with_suffix(".txt")
            ref_text = txt.read_text(encoding="utf-8").strip() if txt.exists() else None
        if not ref_text:
            print(f"  Überspringe {ref}: --ref-text fehlt (Wortlaut der Aufnahme).")
            continue
        t0 = time.time()
        audio, ok = synth_checked(reader, sample, ref_audio=ref, ref_text=ref_text)
        dur = audio.size / reader.sample_rate
        out = outdir / f"probe_{name}.wav"
        write_wav(out, audio, reader.sample_rate)
        took = time.time() - t0
        print(f"  Hörprobe {out}  ({dur:.1f} s Audio in {took:.0f} s"
              f"{'' if ok else ', Länge auffällig – bitte anhören'})")
        if dur > 0:
            speed = len(sample) / took
            print(f"    Tempo: ≈ {speed * 60:,.0f} Zeichen/Minute".replace(",", "."))
    reader.close()

    print("\nFertig. Hör dir die probe_*.wav-Dateien an und starte dann z. B.:")
    first = next(iter(refs.values()), Path("probe/stimme_erzaehler_m.wav"))
    print(f"  hoerbuch vertonen {src} --ref {first}")


def cmd_stimme(args):
    """Aufnahme prüfen, auf Mono/24 kHz/-20 LUFS bringen und als Standardstimme speichern."""
    import numpy as np
    src = Path(args.datei)
    if not src.exists():
        sys.exit(f"Aufnahme nicht gefunden: {src}")
    text = args.text
    if not text:
        txt = src.with_suffix(".txt")
        if not txt.exists():
            sys.exit("Bitte --text \"…\" angeben (genauer Wortlaut der Aufnahme) "
                     f"oder eine Datei {txt} anlegen.")
        text = txt.read_text(encoding="utf-8").strip()
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg fehlt (brew install ffmpeg).")
    dest = Path(args.ziel) if args.ziel else DEFAULT_VOICE
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Mono, 24 kHz; erst Lautheit auf −20 LUFS (Spitze −2 dB), dann Stille an den Enden auf
    # 0,3 s kürzen. Die Reihenfolge ist wichtig: Bei leisen Aufnahmen würde sonst das leise
    # Wortende als Stille gelten und abgeschnitten – das Modell "ergänzt" die fehlenden Wörter
    # dann in jedem Abschnitt. Zum Schluss 0,4 s Stille anhängen, damit kein Wort am Rand endet.
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
                    "-ac", "1", "-ar", "24000",
                    "-af", "loudnorm=I=-20:TP=-2:LRA=7,"
                           "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.3,"
                           "areverse,silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.3,areverse,"
                           "apad=pad_dur=0.4",
                    str(dest)], check=True)
    dest.with_suffix(".txt").write_text(text.strip(), encoding="utf-8")
    audio, sr = read_wav(dest)
    dur = audio.size / sr
    rms = 20 * np.log10(max(float(np.sqrt(np.mean(audio ** 2))), 1e-9))
    peak = 20 * np.log10(max(float(np.abs(audio).max()), 1e-9))
    print(f"Standardstimme gespeichert: {dest}")
    print(f"  Dauer {dur:.1f} s · RMS {rms:.1f} dB · Spitze {peak:.1f} dB · Wortlaut {len(text)} Zeichen")
    if dur < 8:
        print("  Hinweis: Die Aufnahme ist kurz. 10–20 Sekunden geben dem Modell mehr Material.")
    elif dur > 30:
        print("  Hinweis: Die Aufnahme ist lang. 10–20 Sekunden reichen; sehr lange Referenzen bremsen.")
    if dest.resolve() == DEFAULT_VOICE.resolve():
        print("  'probe' und 'vertonen' verwenden diese Stimme jetzt automatisch, wenn kein --ref angegeben ist.")
    else:
        print(f"  Verwenden mit:  --ref {dest}   (Standardstimme bleibt {DEFAULT_VOICE})")


def cmd_vertonen(args):
    import numpy as np
    src = Path(args.datei)
    if args.ref:
        ref = Path(args.ref)
    elif default_voice():
        ref = default_voice()
        print(f"Referenzstimme: eigene Standardstimme {ref}")
    else:
        sys.exit("Bitte --ref angeben oder eine Standardstimme einrichten:  "
                 "hoerbuch stimme aufnahme.wav --text \"…\"")
    if not ref.exists():
        sys.exit(f"Referenzaufnahme nicht gefunden: {ref}")
    ref_text = args.ref_text
    if not ref_text:
        txt = ref.with_suffix(".txt")
        if not txt.exists():
            sys.exit("Bitte --ref-text angeben (genauer Wortlaut der Referenzaufnahme) "
                     f"oder eine Datei {txt} anlegen.")
        ref_text = txt.read_text(encoding="utf-8").strip()

    text = src.read_text(encoding="utf-8")
    if not args.ohne_bereinigung and not re.search(r"^# ", text, re.M):
        print("Hinweis: Keine '# '-Kapitelzeilen gefunden – bereinige den Text vorher automatisch.")
        rep = CleanReport()
        text = clean_text(text, rep)

    title = args.titel or src.name.split(".")[0].replace("_", " ")
    chapters = parse_book(text, args.abschnitt, title)
    total_chars = sum(len(c.text) for ch in chapters for c in ch.chunks)
    n_chunks = sum(len(ch.chunks) for ch in chapters)
    work = Path(args.arbeitsordner or src.with_suffix("").as_posix() + "_audio")
    work.mkdir(exist_ok=True)

    # Wenn sich der Text geändert hat, alte Abschnitte nicht wiederverwenden
    sig = json.dumps([[ch.title, [c.text for c in ch.chunks]] for ch in chapters],
                     ensure_ascii=False)
    meta_path = work / "plan.json"
    old = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else None
    if old and (old.get("sig") != sig or old.get("ref") != str(ref.resolve())):
        print("Text oder Stimme haben sich geändert – bisherige Audioabschnitte werden verworfen.")
        for f in work.glob("k*_*.wav"):
            f.unlink()
    meta_path.write_text(json.dumps({"sig": sig, "ref": str(ref.resolve())}, ensure_ascii=False),
                         encoding="utf-8")

    print(f"{len(chapters)} Kapitel, {n_chunks} Abschnitte, {total_chars:,} Zeichen".replace(",", "."))
    done_chars = sum(len(c.text) for ci, ch in enumerate(chapters) for i, c in enumerate(ch.chunks)
                     if (work / f"k{ci:03d}_{i:04d}.wav").exists())
    if done_chars:
        print(f"Setze fort: {done_chars / total_chars:.0%} bereits erledigt.")

    voice = None
    suspicious = []
    t_start = time.time()
    chars_this_run = 0
    try:
        for ci, ch in enumerate(chapters):
            for i, c in enumerate(ch.chunks):
                path = work / f"k{ci:03d}_{i:04d}.wav"
                if path.exists():
                    continue
                if voice is None:
                    voice = Voice(args.modell, verbose=args.verbose)
                audio, ok = synth_checked(voice, c.text, ref_audio=ref, ref_text=ref_text,
                                          temperature=args.temperatur)
                write_wav(path, audio, voice.sample_rate)
                if not ok:
                    suspicious.append((path.name, c.text))
                chars_this_run += len(c.text)
                done_chars += len(c.text)
                el = time.time() - t_start
                rate = chars_this_run / el if el > 0 else 0
                eta = (total_chars - done_chars) / rate if rate > 0 else 0
                print(f"\r[{done_chars / total_chars:6.1%}] Kapitel {ci + 1}/{len(chapters)} "
                      f"Abschnitt {i + 1}/{len(ch.chunks)} · {rate * 60:,.0f} Z/min · "
                      f"Rest ≈ {fmt_dur(eta)}   ".replace(",", "."), end="", flush=True)
    except KeyboardInterrupt:
        print("\nAbgebrochen. Beim nächsten Aufruf geht es hier weiter.")
        sys.exit(1)
    finally:
        if suspicious:
            log = work / "auffaellig.txt"
            with log.open("a", encoding="utf-8") as f:
                for name, t in suspicious:
                    f.write(f"{name}\t{t}\n")
            print(f"\n{len(suspicious)} Abschnitte mit auffälliger Länge → {log}")
            print("  Zum Neuerzeugen einfach die WAV-Datei löschen und das Skript erneut starten.")
        if voice is not None:
            voice.close()
    print()

    # Kapitel zusammensetzen
    sr = None
    chapter_files = []
    for ci, ch in enumerate(chapters):
        parts = []
        for i, c in enumerate(ch.chunks):
            a, sr = read_wav(work / f"k{ci:03d}_{i:04d}.wav")
            parts.append(a)
            parts.append(np.zeros(int(c.pause_after * sr), dtype=np.float32))
        out = work / f"kapitel_{ci + 1:03d}.wav"
        write_wav(out, np.concatenate(parts), sr)
        chapter_files.append((ch.title, out, sum(p.size for p in parts) / sr))

    build_output(chapter_files, src, title, fmt=args.format, ausgabe=args.ausgabe, cover=args.cover)
