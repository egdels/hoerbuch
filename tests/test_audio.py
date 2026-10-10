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
