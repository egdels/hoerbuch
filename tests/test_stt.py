from hoerbuch.stt import referenztext_aufbereiten


def test_aufbereiten_glaettet_leerraum():
    assert referenztext_aufbereiten("  Es war ein\n stiller   Abend. ") == "Es war ein stiller Abend."


def test_aufbereiten_schreibt_zahlen_aus():
    assert referenztext_aufbereiten("Um 12 Uhr kamen 3 Gäste.") == "Um zwölf Uhr kamen drei Gäste."


def test_aufbereiten_entfernt_untertitel_halluzination():
    for anhang in ("Untertitel im Auftrag des ZDF, 2021", "Untertitel der Amara.org-Community",
                   "Untertitelung im Auftrag des ZDF für funk, 2017."):
        assert referenztext_aufbereiten(f"Es war ein stiller Abend. {anhang}") == "Es war ein stiller Abend."


def test_aufbereiten_laesst_echte_untertitel_stehen():
    text = "Sie las die Untertitel laut vor."
    assert referenztext_aufbereiten(text) == text
