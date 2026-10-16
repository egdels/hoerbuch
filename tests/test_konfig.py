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
        assert set(MODELLE[backend]) == {"base", "design", "ki"}
    assert MODELLE["mlx"]["base"].startswith("mlx-community/")
    assert MODELLE["torch"]["base"].startswith("Qwen/")
