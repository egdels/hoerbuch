import json
from types import SimpleNamespace

import pytest

from hoerbuch import befehle
from hoerbuch.befehle import abschnitte_abgleichen, referenztext


def _kapitel(*texte):
    return [SimpleNamespace(title="K", chunks=[SimpleNamespace(text=t) for t in texte])]


def _lege_an(work, namen):
    for n in namen:
        (work / f"{n}.wav").write_bytes(b"RIFF" + n.encode())


def test_abgleich_behaelt_unveraenderte_und_verschobene_abschnitte(tmp_path):
    work = tmp_path
    assert abschnitte_abgleichen(work, _kapitel("A", "B", "C"), "ref1") == (0, 0)
    _lege_an(work, ["k000_0000", "k000_0001", "k000_0002"])
    # Unverändert: alles bleibt
    assert abschnitte_abgleichen(work, _kapitel("A", "B", "C"), "ref1") == (3, 0)
    # Absatz vorn eingefügt: A, B, C rutschen eine Stelle weiter und werden umbenannt
    assert abschnitte_abgleichen(work, _kapitel("Neu", "A", "B", "C"), "ref1") == (3, 0)
    assert not (work / "k000_0000.wav").exists()
    assert (work / "k000_0001.wav").read_bytes().endswith(b"k000_0000")   # das alte A
    assert (work / "k000_0003.wav").read_bytes().endswith(b"k000_0002")   # das alte C
    # B geändert: nur B wird verworfen
    assert abschnitte_abgleichen(work, _kapitel("Neu", "A", "B2", "C"), "ref1") == (2, 1)
    assert not (work / "k000_0002.wav").exists() and (work / "k000_0003.wav").exists()
    # Andere Stimme: alles weg
    assert abschnitte_abgleichen(work, _kapitel("Neu", "A", "B2", "C"), "ref2") == (0, 2)
    assert not list(work.glob("k*.wav")) and not list(work.glob("h_*.wav"))


def test_abgleich_uebernimmt_alten_plan_mit_gesamtsignatur(tmp_path):
    work = tmp_path
    kap = _kapitel("A", "B")
    sig = json.dumps([["K", ["A", "B"]]], ensure_ascii=False)
    (work / "plan.json").write_text(json.dumps({"sig": sig, "ref": "ref1"}), encoding="utf-8")
    _lege_an(work, ["k000_0000", "k000_0001"])
    assert abschnitte_abgleichen(work, kap, "ref1") == (2, 0)
    plan = json.loads((work / "plan.json").read_text(encoding="utf-8"))
    assert set(plan["abschnitte"]) == {"k000_0000", "k000_0001"} and plan["ref"] == "ref1"
    # Alter Plan, ein Abschnitt geändert: der andere bleibt
    (work / "plan.json").write_text(json.dumps({"sig": json.dumps([["K", ["A", "Balt"]]]), "ref": "ref1"}),
                                    encoding="utf-8")
    assert abschnitte_abgleichen(work, kap, "ref1") == (1, 1)
    assert (work / "k000_0000.wav").exists() and not (work / "k000_0001.wav").exists()
    # Alter Plan unlesbar: nichts ist verlässlich
    _lege_an(work, ["k000_0001"])
    (work / "plan.json").write_text(json.dumps({"sig": "kaputt", "ref": "ref1"}), encoding="utf-8")
    assert abschnitte_abgleichen(work, kap, "ref1") == (0, 2)


@pytest.fixture
def whisper(monkeypatch):
    """Ersetzt die Spracherkennung und merkt sich die Aufrufe."""
    aufrufe = []

    def fake(pfad, model_id):
        aufrufe.append(pfad)
        return "Erkannter Wortlaut."
    monkeypatch.setattr(befehle, "transkribieren", fake)
    return aufrufe


def test_referenztext_angegeben_hat_vorrang(tmp_path, whisper):
    ref = tmp_path / "stimme.wav"
    (tmp_path / "stimme.txt").write_text("Aus der Datei.", encoding="utf-8")
    assert referenztext(ref, "  Von Hand.  ") == "Von Hand."
    assert whisper == []


def test_referenztext_aus_txt(tmp_path, whisper):
    ref = tmp_path / "stimme.wav"
    (tmp_path / "stimme.txt").write_text("Aus der Datei.\n", encoding="utf-8")
    assert referenztext(ref, None) == "Aus der Datei."
    assert whisper == []


def test_referenztext_ohne_txt_wird_mitgeschrieben_und_gespeichert(tmp_path, whisper):
    ref = tmp_path / "stimme.wav"
    (tmp_path / "stimme.txt").write_text("  \n", encoding="utf-8")      # leere Datei zählt nicht
    assert referenztext(ref, None) == "Erkannter Wortlaut."
    assert whisper == [ref]
    assert (tmp_path / "stimme.txt").read_text(encoding="utf-8") == "Erkannter Wortlaut."
    # Beim nächsten Mal kommt der Text aus der .txt, ohne erneute Erkennung
    assert referenztext(ref, None) == "Erkannter Wortlaut."
    assert whisper == [ref]


def test_referenztext_nichts_erkannt_bricht_ab(tmp_path, monkeypatch):
    monkeypatch.setattr(befehle, "transkribieren", lambda pfad, model_id: "")
    with pytest.raises(SystemExit):
        referenztext(tmp_path / "stille.wav", None)
    assert not (tmp_path / "stille.txt").exists()
