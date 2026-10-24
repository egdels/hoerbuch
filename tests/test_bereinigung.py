import re

from hoerbuch.bereinigung import (CleanReport, clean_sentence_text, clean_text, is_heading,
                                  is_text_par, normalize_chars, read_text, roman_to_int)


def test_roman_to_int():
    assert roman_to_int("IV") == 4
    assert roman_to_int("xiv") == 14
    assert roman_to_int("ABC") is None
    assert roman_to_int("") is None


def test_is_heading():
    for s in ("Kapitel 3", "7. Die Rückkehr", "III", "Prolog", "Epilog", "12"):
        assert is_heading(s), s
    for s in ("Der alte Bahnhof", "Es war ein stiller Abend.", ""):
        assert not is_heading(s), s


def test_is_text_par():
    assert is_text_par("Ein Absatz.")
    assert not is_text_par("# Kapitel 1")
    assert not is_text_par("## Zwischentitel")
    assert not is_text_par("***")
    assert not is_text_par("")


def test_normalize_chars():
    assert normalize_chars("»Hallo« ﬁnden\r\nx") == "„Hallo“ finden\nx"


def test_read_text_repariert_kaputte_umlaute(tmp_path):
    kaputt = "Käse und Brötchen".encode("utf-8").decode("latin-1").encode("utf-8")
    f = tmp_path / "k.txt"
    f.write_bytes(kaputt)
    report = CleanReport()
    assert read_text(f, report) == "Käse und Brötchen"
    assert "repariert" in report.encoding


def test_clean_sentence_text():
    r = CleanReport()
    assert clean_sentence_text("Dr. Konrad Weber kam ca. um 8 Uhr, d. h. spät.", r) == \
        "Doktor Konrad Weber kam circa um acht Uhr, das heißt spät."
    assert clean_sentence_text("Freund*innen und seine*ihre Sachen", r) == "Freund-innen und seine oder ihre Sachen"
    assert clean_sentence_text("Fisch.Wir essen.", r) == "Fisch. Wir essen."
    assert clean_sentence_text("Siehe www.example.org hier.", r) == "Siehe hier."
    assert clean_sentence_text("Hallo & Tschüss!!! Wirklich?!", r) == "Hallo und Tschüss! Wirklich?"
    assert clean_sentence_text("Wort12 steht hier.", r) == "Wort steht hier."   # Fußnotenziffer
    assert r.urls == 1
    assert r.abbreviations == 3


def test_mehrdeutige_abkuerzungen_bleiben_fuer_ki():
    r = CleanReport(ki=True)
    assert clean_sentence_text("Fr. Berger las S. 12.", r) == "Fr. Berger las S. zwölf."
    r = CleanReport(ki=False)
    assert clean_sentence_text("Fr. Berger las S. 12.", r) == "Frau Berger las Seite zwölf."


def test_testbuch(testbuch_text):
    report = CleanReport()
    out = clean_text(testbuch_text, report)

    # Seitenzahlen, Kopfzeilen, Silbentrennung
    assert report.removed_pages == 6
    assert report.removed_headers == {"Der Nebel über Lindenbach": 7}
    assert report.dehyphenated == 4
    assert "Lindenbach erreichte" in out and "Linden-" not in out
    assert "Absender" in out and "Handschrift" in out

    # Kapitel als "# "-Zeilen, Szenenwechsel als eigener Absatz
    assert report.chapters == ["Kapitel 1: Der alte Bahnhof", "Kapitel 2: Die Nachricht"]
    assert "\n# Kapitel 1: Der alte Bahnhof\n" in "\n" + out
    assert "\n\n***\n\n" in out

    # Abkürzungen und Zahlen
    assert "Doktor Konrad Weber" in out
    assert "circa zwei Stunden" in out
    assert "das heißt eine Folge" in out
    assert "am dritten Mai achtzehnhundertachtundvierzig" in out
    assert "eintausendzweihundert Mark" in out
    assert "fast dreißig Prozent" in out
    assert "auf Seite zwölf" in out
    assert "Paragraf sieben" in out
    assert "sechzehn Uhr dreißig" in out
    assert "zwei Komma fünf Kilometer" in out
    fliesstext = [ln for ln in out.splitlines() if not ln.startswith("#")]
    assert not re.search(r"\d", "\n".join(fliesstext)), "im Fließtext dürfen keine Ziffern übrig bleiben"
    assert "# Kapitel 1" in out                 # Kapitelmarken behalten ihre Ziffern

    # Römische Zahlen im Fließtext und OCR-Fehler bleiben der KI-Stufe überlassen
    assert "Kaiser Wilhelms II." in out
    assert "Hirnrnel" in out

    # Absätze sind zusammengeführt (keine harten Umbrüche innerhalb eines Absatzes)
    paras = [p for p in out.strip().split("\n\n") if p.strip()]
    assert all("\n" not in p for p in paras)


def test_bereits_markierte_ueberschriften_bleiben():
    text = "# Erstes Kapitel\n\nText mit 3 Äpfeln.\n\n## Zwischentitel 2\n\nMehr Text.\n"
    report = CleanReport()
    out = clean_text(text, report)
    assert out.startswith("# Erstes Kapitel\n")
    assert "## Zwischentitel 2\n" in out          # Überschriften behalten ihre Ziffern
    assert "drei Äpfeln" in out
    assert report.chapters == ["Erstes Kapitel"]


def test_roemische_kapitelnummer_wird_arabisch():
    text = "Text davor.\n\nIV\n\nEin Absatz.\n"
    report = CleanReport()
    out = clean_text(text, report)
    assert "# Kapitel 4\n" in out


def test_untertitel_nach_leerzeile_wird_angehaengt():
    out = clean_text("Kapitel 1\n\nDer alte Bahnhof\n\nEs war still. Niemand kam.\n\n"
                     "Kapitel 2\nDie Nachricht\n\nEin Brief lag da.\n\n"
                     "Kapitel 3\n\nKapitel 4\n\nText im vierten Kapitel.\n", CleanReport())
    assert "# Kapitel 1: Der alte Bahnhof\n" in out        # mit Leerzeile dazwischen
    assert "# Kapitel 2: Die Nachricht\n" in out           # direkt darunter
    assert "# Kapitel 3\n" in out and "# Kapitel 4\n" in out   # Überschrift ist kein Untertitel
    assert "Es war still. Niemand kam." in out
