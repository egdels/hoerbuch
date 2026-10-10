from pathlib import Path

import pytest

BEISPIEL = Path(__file__).resolve().parent.parent / "beispiel"


@pytest.fixture(scope="session")
def testbuch_text() -> str:
    return (BEISPIEL / "testbuch.txt").read_text(encoding="utf-8")
