import numpy as np

from hoerbuch import tts
from hoerbuch.tts import _Sprecherpruefung, befund, synth_checked

SR = 24000
TEXT = "Es war ein stiller Abend, und über dem kleinen Dorf lag ein feiner Nebel."   # ≈ 60 Zeichen


def _sprache(sekunden: float, f: float = 180.0):
    """Ausklingender Ton als Ersatz für einen gesprochenen Abschnitt."""
    t = np.arange(int(sekunden * SR)) / SR
    return (0.3 * np.sin(2 * np.pi * f * t) * np.linspace(1, 0, t.size) ** 2).astype(np.float32)


class _Attrappe(_Sprecherpruefung):
    """Voice-Ersatz: liefert nacheinander vorgegebene Audios; das 'Embedding' ist die Tonhöhe."""
    sample_rate = SR
    verbose = False

    def __init__(self, folge):
        self.folge = list(folge)
        self.aufrufe = 0

    def synth(self, text, **kw):
        self.aufrufe += 1
        return self.folge.pop(0)

    def _embedding(self, audio):
        f = np.argmax(np.abs(np.fft.rfft(audio))) / audio.size * SR
        return np.array([1.0, 0.0]) if f < 150 else np.array([0.0, 1.0])    # tief vs. hoch


def test_befund_unauffaellig_und_gruende():
    a = _sprache(4.5)
    assert befund(TEXT, a, SR, 0.99) == ""
    assert befund(TEXT, a, SR, None) == ""                       # nicht messbar → keine Beanstandung
    assert befund(TEXT, a, SR, 0.94) == "Stimme weicht ab (0,940)"
    assert befund(TEXT, _sprache(40), SR, 0.94) == "Länge, Stimme weicht ab (0,940)"


def test_synth_checked_wiederholt_bei_fremder_stimme(monkeypatch, tmp_path):
    ref = tmp_path / "ref.wav"
    monkeypatch.setattr(tts, "lade_mono", lambda pfad, rate: _sprache(5, 180))
    v = _Attrappe([_sprache(4.5, 110), _sprache(4.5, 180)])      # erst "männlich", dann wie die Referenz
    audio, b = synth_checked(v, TEXT, ref_audio=ref, ref_text="x")
    assert b == "" and v.aufrufe == 2


def test_synth_checked_behaelt_richtige_stimme_wenn_nichts_passt(monkeypatch, tmp_path):
    ref = tmp_path / "ref.wav"
    monkeypatch.setattr(tts, "lade_mono", lambda pfad, rate: _sprache(5, 180))
    richtig_aber_lang = _sprache(15.0, 180)                      # Stimme passt, Länge auffällig
    v = _Attrappe([_sprache(4.5, 110), richtig_aber_lang, _sprache(4.5, 110)])
    audio, b = synth_checked(v, TEXT, ref_audio=ref, ref_text="x")
    assert v.aufrufe == 3 and b == "Länge"
    assert audio.size == tts.trim_silence(richtig_aber_lang, SR).size


def test_kurze_abschnitte_werden_nicht_verglichen(monkeypatch, tmp_path):
    monkeypatch.setattr(tts, "lade_mono", lambda pfad, rate: _sprache(5, 180))
    v = _Attrappe([])
    assert v.aehnlichkeit(_sprache(2.0, 110), tmp_path / "ref.wav") is None
    assert v.aehnlichkeit(_sprache(4.0, 180), tmp_path / "ref.wav") > 0.999
