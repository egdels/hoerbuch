"""Einstellungen: Backend, Modelle, Pausen, Pegel, Standardstimme."""
from __future__ import annotations

import os
import platform
import sys
from pathlib import Path


def waehle_backend(plattform: str = sys.platform, maschine: str = platform.machine(),
                   umgebung: str | None = os.environ.get("HOERBUCH_BACKEND")) -> str:
    """Rechen-Backend: "mlx" (Apple Silicon, mlx-audio/mlx-lm) oder "torch" (qwen-tts/transformers,
    alles andere: Windows, Linux, Intel-Mac). Mit HOERBUCH_BACKEND=mlx|torch erzwingbar."""
    if umgebung:
        u = umgebung.strip().lower()
        if u not in ("mlx", "torch"):
            sys.exit(f"HOERBUCH_BACKEND={umgebung!r} unbekannt, erlaubt sind mlx oder torch.")
        return u
    if plattform == "darwin" and maschine.lower() in ("arm64", "aarch64"):
        return "mlx"
    return "torch"


BACKEND = waehle_backend()

# Modelle je Backend: MLX nutzt die quantisierten Umsetzungen der mlx-community,
# PyTorch die Originale von Qwen (bf16) bzw. ein Sprachmodell aus dem Transformers-Format.
MODELLE = {
    "mlx": {
        "base": "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit",
        "design": "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit",
        "ki": "mlx-community/Qwen3.5-9B-MLX-4bit",
        "stt": "mlx-community/whisper-large-v3-turbo-asr-fp16",
    },
    "torch": {
        "base": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        "design": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
        "ki": "Qwen/Qwen3-8B",
        "stt": "openai/whisper-large-v3-turbo",
    },
}
MODEL_BASE = MODELLE[BACKEND]["base"]
MODEL_DESIGN = MODELLE[BACKEND]["design"]
MODEL_KI = MODELLE[BACKEND]["ki"]        # Sprachmodell für "bereinigen --ki"
MODEL_STT = MODELLE[BACKEND]["stt"]      # Spracherkennung für den Wortlaut der Referenz

def torch_geraet_und_typ():
    """(Gerät, dtype, Beschreibung) für das PyTorch-Backend: CUDA mit bfloat16 ab NVIDIA Ampere
    (RTX 30er), float16 auf älteren Karten (dort wird bfloat16 nur langsam emuliert), sonst CPU
    mit float32. Mit HOERBUCH_DTYPE=bf16|fp16|fp32 erzwingbar."""
    import torch
    wunsch = (os.environ.get("HOERBUCH_DTYPE") or "").strip().lower()
    typen = {"bf16": torch.bfloat16, "fp16": torch.float16, "fp32": torch.float32}
    if wunsch and wunsch not in typen:
        sys.exit(f"HOERBUCH_DTYPE={wunsch!r} unbekannt, erlaubt sind bf16, fp16 oder fp32.")
    if torch.cuda.is_available():
        name = torch.cuda.get_device_name(0)
        if wunsch:
            dtype = typen[wunsch]
        elif torch.cuda.is_bf16_supported():
            dtype = torch.bfloat16
        else:
            dtype = torch.float16
            print(f"Hinweis: {name} rechnet bfloat16 nicht nativ – verwende float16.")
        return "cuda:0", dtype, name
    return "cpu", typen.get(wunsch, torch.float32), "CPU"


# Installationshinweis für ffmpeg je Plattform (nur für Fehlermeldungen).
if sys.platform == "darwin":
    FFMPEG_HINT = "brew install ffmpeg"
elif sys.platform == "win32":
    FFMPEG_HINT = "winget install ffmpeg  (oder von https://ffmpeg.org laden und in den PATH legen)"
else:
    FFMPEG_HINT = "z. B. apt install ffmpeg"
KI_BLOCK_CHARS = 1200        # Textmenge pro Modellanfrage in der KI-Bereinigung
LANGUAGE = "german"

MAX_CHUNK_CHARS = 350        # kürzere Abschnitte = weniger Aussetzer/Wiederholungen
PAUSE_SENTENCE = 0.25        # Sekunden zwischen Abschnitten im selben Absatz
PAUSE_PARAGRAPH = 0.7        # Sekunden zwischen Absätzen
PAUSE_SCENE = 1.6            # Sekunden bei Szenenwechsel (***)
PAUSE_CHAPTER = 2.0          # Sekunden nach einer Kapitelüberschrift

# Plausibilitätsprüfung: deutsche Erzählstimme spricht etwa 12–17 Zeichen/s.
# Liegt ein Abschnitt weit außerhalb, wird er neu erzeugt.
MIN_CHARS_PER_SEC = 5.0      # langsamer → vermutlich Wiederholung/Gestammel
MAX_CHARS_PER_SEC = 32.0     # schneller → vermutlich Text verschluckt
MAX_TRIES = 3

# Stimmdrift: Jeder Abschnitt wird über den Sprecher-Encoder von Qwen3-TTS mit der Referenz
# verglichen (Kosinus-Ähnlichkeit). Gemessen an vier Referenzstimmen: saubere Abschnitte ≥ 0,967
# (meist ≈ 0,99), in eine andere Stimme gekippte 0,93–0,95, fremde Sprecher 0,91–0,94.
# Unter 3 Sekunden streut das Maß zu stark und wird nicht geprüft.
MIN_SPEAKER_SIMILARITY = 0.96
SPEAKER_MIN_SECONDS = 3.0

# Pegel: jeder erzeugte Abschnitt wird auf denselben Effektivpegel gebracht, damit die
# Lautstärke über das Buch nicht driftet (Hörbuch-Richtwert: RMS −18 bis −23 dBFS, Spitze ≤ −3 dB).
TARGET_RMS_DB = -20.0
MAX_PEAK_DB = -2.0

# Eigene Standardstimme (wird mit "hoerbuch stimme aufnahme.wav" eingerichtet).
# Liegt sie vor, verwenden "probe" und "vertonen" sie automatisch, wenn kein --ref angegeben ist.
DEFAULT_VOICE = Path(os.environ.get("HOERBUCH_STIMME", Path.home() / ".hoerbuch" / "stimme.wav"))

# Referenztext für die Stimmen im Probelauf (ca. 12–15 Sekunden gesprochen).
REF_SENTENCE = (
    "Es war ein stiller Abend, und über dem kleinen Dorf lag ein feiner Nebel. "
    "Niemand ahnte, dass sich in dieser Nacht alles verändern würde."
)

# Stimmbeschreibungen für den Probelauf (VoiceDesign).
VOICE_DESIGNS = {
    "erzaehler_m": "Ein ruhiger, warmer männlicher Hörbuchsprecher mittleren Alters "
                   "mit tiefer, angenehmer Stimme. Spricht klares Hochdeutsch, "
                   "gelassen und ausdrucksvoll, in gemächlichem Tempo.",
    "erzaehlerin_w": "Eine warme, klare weibliche Hörbuchsprecherin um die vierzig. "
                     "Spricht akzentfreies Hochdeutsch, ruhig, freundlich und "
                     "lebendig betont, in gemächlichem Tempo.",
    "erzaehler_alt": "Ein älterer männlicher Erzähler mit sonorer, leicht rauer Stimme. "
                     "Spricht bedächtig und atmosphärisch in klarem Hochdeutsch, "
                     "wie ein Märchenerzähler am Kaminfeuer.",
    "erzaehler_sf": "Ein markanter männlicher Sprecher mittleren Alters mit tiefer, fester "
                    "Stimme und sehr klarer Artikulation, wie ein erfahrener Synchronsprecher. "
                    "Spricht sachlich und konzentriert, mit unterschwelliger Spannung und "
                    "leichtem Nachdruck auf wichtigen Wörtern, in zügigem, aber ruhigem Tempo. "
                    "Hochdeutsch, ohne Pathos.",
}
DESIGN_SEED = 42             # Seed für den Stimmentwurf; andere Werte ergeben andere Varianten


def stimmentwuerfe(eigene: list[str] | None, nur_eigene: bool = False) -> dict[str, str]:
    """Name → Beschreibung für den Probelauf: die eingebauten Stimmen plus eigene Beschreibungen
    (--design, benannt entwurf_1, entwurf_2 …). Mit nur_eigene nur die eigenen."""
    designs = {} if nur_eigene else dict(VOICE_DESIGNS)
    for n, desc in enumerate(eigene or [], 1):
        desc = " ".join(desc.split())
        if desc:
            designs[f"entwurf_{n}"] = desc
    return designs


def default_voice() -> Path | None:
    """Pfad der eingerichteten Standardstimme, falls vorhanden (WAV + gleichnamige TXT)."""
    if DEFAULT_VOICE.exists() and DEFAULT_VOICE.with_suffix(".txt").exists():
        return DEFAULT_VOICE
    return None
