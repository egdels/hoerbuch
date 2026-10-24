from hoerbuch.konfig import MODELLE, waehle_backend


def test_apple_silicon_nutzt_mlx():
    assert waehle_backend("darwin", "arm64", None) == "mlx"


def test_windows_linux_intel_nutzen_torch():
    assert waehle_backend("win32", "AMD64", None) == "torch"
    assert waehle_backend("linux", "x86_64", None) == "torch"
    assert waehle_backend("darwin", "x86_64", None) == "torch"


def test_umgebungsvariable_erzwingt_backend():
    assert waehle_backend("darwin", "arm64", "torch") == "torch"
    assert waehle_backend("win32", "AMD64", " MLX ") == "mlx"


def test_modelle_je_backend_vollstaendig():
    for backend in ("mlx", "torch"):
        assert set(MODELLE[backend]) == {"base", "design", "ki", "stt"}
    assert MODELLE["mlx"]["base"].startswith("mlx-community/")
    assert MODELLE["torch"]["base"].startswith("Qwen/")


def test_stimmentwuerfe_eingebaut_plus_eigene():
    from hoerbuch.konfig import VOICE_DESIGNS, stimmentwuerfe
    d = stimmentwuerfe(["  Eine helle,\n junge Stimme. ", ""])
    assert list(d)[:len(VOICE_DESIGNS)] == list(VOICE_DESIGNS)
    assert d["entwurf_1"] == "Eine helle, junge Stimme."
    assert "entwurf_2" not in d          # leere Beschreibung wird übergangen
    assert stimmentwuerfe(["x"], nur_eigene=True) == {"entwurf_1": "x"}
    assert stimmentwuerfe(None, nur_eigene=True) == {}


def test_eingebaute_entwuerfe_ohne_personennamen():
    from hoerbuch.konfig import VOICE_DESIGNS
    assert "erzaehler_sf" in VOICE_DESIGNS
    for desc in VOICE_DESIGNS.values():
        assert len(desc) > 80 and "Hochdeutsch" in desc
