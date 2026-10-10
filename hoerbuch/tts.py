"""Sprachsynthese mit Qwen3-TTS über mlx-audio, mit Längenprüfung und Wiederholung."""
from __future__ import annotations

import re
import sys

from .audio import normalize_level, trim_silence
from .konfig import LANGUAGE, MAX_CHARS_PER_SEC, MAX_TRIES, MIN_CHARS_PER_SEC

class Voice:
    """Kapselt Modell + Stimme. Hält nur ein Modell gleichzeitig im Speicher."""

    def __init__(self, model_id: str, verbose: bool = False):
        try:
            import mlx.core as mx  # noqa: F401
            from mlx_audio.tts.utils import load_model
        except ImportError:
            sys.exit("mlx-audio fehlt. Installieren mit:  pip install -U mlx-audio")
        print(f"Lade Modell {model_id} … (beim ersten Mal wird es heruntergeladen)")
        self.model = load_model(model_id)
        self.model_id = model_id
        self.verbose = verbose
        langs = [l.lower() for l in getattr(self.model, "supported_languages", [])]
        if langs and LANGUAGE not in langs:
            print(f"Warnung: '{LANGUAGE}' nicht in {langs} – verwende 'auto'.")
            self.lang = "auto"
        else:
            self.lang = LANGUAGE
        self.sample_rate = int(self.model.sample_rate)

    def synth(self, text: str, *, ref_audio=None, ref_text=None, instruct=None,
              temperature=0.8, seed=None):
        import mlx.core as mx
        import numpy as np
        if seed is not None:
            mx.random.seed(seed)
        kwargs = dict(text=text, lang_code=self.lang, temperature=temperature,
                      split_pattern="", verbose=self.verbose)
        if ref_audio:
            kwargs.update(ref_audio=str(ref_audio), ref_text=ref_text)
        if instruct:
            kwargs.update(instruct=instruct)
        parts = [np.array(r.audio, dtype=np.float32).reshape(-1)
                 for r in self.model.generate(**kwargs)]
        audio = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
        return audio

    def close(self):
        import gc
        del self.model
        gc.collect()
        try:
            import mlx.core as mx
            mx.clear_cache()
        except Exception:
            pass


def plausible(text: str, seconds: float) -> bool:
    n = len(re.sub(r"\s", "", text))
    if seconds <= 0.2:
        return False
    if n < 15:
        return True
    cps = n / seconds
    return MIN_CHARS_PER_SEC <= cps <= MAX_CHARS_PER_SEC


def synth_checked(voice: Voice, text: str, **kw):
    """Erzeugt Audio, prüft die Länge und versucht es bei Auffälligkeiten erneut."""
    best = None
    for attempt in range(MAX_TRIES):
        audio = trim_silence(voice.synth(text, seed=1000 + attempt * 7919, **kw), voice.sample_rate)
        audio = normalize_level(audio)
        secs = audio.size / voice.sample_rate
        if plausible(text, secs):
            return audio, True
        # Behalte den Versuch, der am nächsten an ~14 Zeichen/s liegt
        n = len(re.sub(r"\s", "", text))
        score = abs((n / secs if secs > 0 else 999) - 14)
        if best is None or score < best[0]:
            best = (score, audio)
    return best[1], False
