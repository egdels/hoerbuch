"""Sprachsynthese mit Qwen3-TTS, mit Längenprüfung und Wiederholung.

Zwei Backends hinter derselben Schnittstelle:
- "mlx":   mlx-audio auf Apple Silicon (quantisierte Modelle der mlx-community)
- "torch": offizielles Paket qwen-tts (PyTorch) für Windows, Linux und Intel-Macs,
           mit CUDA-GPU oder notfalls auf der CPU."""
from __future__ import annotations

import re
import sys

from .audio import normalize_level, trim_silence
from .konfig import (BACKEND, LANGUAGE, MAX_CHARS_PER_SEC, MAX_TRIES, MIN_CHARS_PER_SEC,
                     torch_geraet_und_typ)


class _VoiceMLX:
    """mlx-audio: Modell + Stimme. Hält nur ein Modell gleichzeitig im Speicher."""

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


class _VoiceTorch:
    """qwen-tts (PyTorch): dieselbe Schnittstelle wie _VoiceMLX."""

    def __init__(self, model_id: str, verbose: bool = False):
        try:
            import torch
            from qwen_tts import Qwen3TTSModel
        except ImportError:
            sys.exit("qwen-tts fehlt. Installieren mit:  pip install -U qwen-tts\n"
                     "(PyTorch mit CUDA vorher passend zur Grafikkarte installieren, siehe README.)")
        self.device, dtype, geraet = torch_geraet_und_typ()
        print(f"Lade Modell {model_id} auf {geraet} ({str(dtype).replace('torch.', '')}) … "
              "(beim ersten Mal wird es heruntergeladen)")
        if self.device == "cpu":
            print("Hinweis: Ohne CUDA-Grafikkarte dauert das Vertonen um ein Vielfaches länger.")
        self.model = Qwen3TTSModel.from_pretrained(model_id, device_map=self.device, dtype=dtype)
        self.model_id = model_id
        self.verbose = verbose
        self.lang = LANGUAGE.capitalize()          # qwen-tts erwartet "German", "English", …
        try:
            langs = [str(l).lower() for l in (self.model.get_supported_languages() or [])]
            if langs and LANGUAGE not in langs:
                print(f"Warnung: '{LANGUAGE}' nicht in {langs} – verwende 'Auto'.")
                self.lang = "Auto"
        except Exception:
            pass
        self.sample_rate = 24000                   # Qwen3-TTS liefert 24 kHz; wird nach dem ersten Lauf übernommen
        self._clone_prompt = None                  # (ref_audio, ref_text) → vorberechnete Referenzmerkmale

    def _prompt_for(self, ref_audio, ref_text):
        key = (str(ref_audio), ref_text)
        if self._clone_prompt is None or self._clone_prompt[0] != key:
            prompt = self.model.create_voice_clone_prompt(ref_audio=str(ref_audio), ref_text=ref_text)
            self._clone_prompt = (key, prompt)
        return self._clone_prompt[1]

    def synth(self, text: str, *, ref_audio=None, ref_text=None, instruct=None,
              temperature=0.8, seed=None):
        import numpy as np
        import torch
        if seed is not None:
            torch.manual_seed(seed)
        gen = {}
        if temperature is not None:
            gen.update(do_sample=temperature > 0, temperature=max(temperature, 1e-3))
        if instruct:
            wavs, sr = self.model.generate_voice_design(text=text, language=self.lang,
                                                        instruct=instruct, **gen)
        elif ref_audio:
            wavs, sr = self.model.generate_voice_clone(text=text, language=self.lang,
                                                       voice_clone_prompt=self._prompt_for(ref_audio, ref_text),
                                                       **gen)
        else:
            sys.exit("Für die Sprachausgabe wird eine Referenzaufnahme (--ref) oder eine Stimmbeschreibung gebraucht.")
        self.sample_rate = int(sr)
        if not wavs:
            return np.zeros(0, dtype=np.float32)
        w = wavs[0]
        if hasattr(w, "detach"):
            w = w.detach().float().cpu().numpy()
        return np.asarray(w, dtype=np.float32).reshape(-1)

    def close(self):
        import gc
        self._clone_prompt = None
        del self.model
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass


Voice = _VoiceMLX if BACKEND == "mlx" else _VoiceTorch


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
