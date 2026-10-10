"""Einstellungen: Modelle, Pausen, Pegel, Standardstimme."""
from __future__ import annotations

import os
from pathlib import Path

MODEL_BASE = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit"
MODEL_DESIGN = "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit"
MODEL_KI = "mlx-community/Qwen3.5-9B-MLX-4bit"   # Sprachmodell für "bereinigen --ki"
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
}


def default_voice() -> Path | None:
    """Pfad der eingerichteten Standardstimme, falls vorhanden (WAV + gleichnamige TXT)."""
    if DEFAULT_VOICE.exists() and DEFAULT_VOICE.with_suffix(".txt").exists():
        return DEFAULT_VOICE
    return None
