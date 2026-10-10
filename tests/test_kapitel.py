from hoerbuch.kapitel import paragraph_chunks, parse_book, sample_paragraph, split_long
from hoerbuch.konfig import PAUSE_CHAPTER, PAUSE_PARAGRAPH, PAUSE_SCENE, PAUSE_SENTENCE

TEXT = ("# Kapitel 1: Start\n\nErster Absatz. Zweiter Satz!\n\n***\n\nNach dem Wechsel.\n\n"
        "## Zwischen 2\n\nNoch ein Absatz.\n\n# Kapitel 2\n\nEnde.")


def test_parse_book():
    chapters = parse_book(TEXT, 350, "Buch")
    assert [c.title for c in chapters] == ["Kapitel 1: Start", "Kapitel 2"]
    k1 = [(c.text, c.pause_after) for c in chapters[0].chunks]
    assert k1 == [
        ("Kapitel eins: Start.", PAUSE_CHAPTER),         # Überschrift wird gesprochen, Ziffern ausgeschrieben
        ("Erster Absatz. Zweiter Satz!", PAUSE_SCENE),   # *** verlängert die Pause des Vorgängers
        ("Nach dem Wechsel.", PAUSE_SCENE),              # vor einer Zwischenüberschrift ebenso
        ("Zwischen zwei.", PAUSE_CHAPTER),
        ("Noch ein Absatz.", PAUSE_PARAGRAPH),
    ]
    assert [(c.text, c.pause_after) for c in chapters[1].chunks] == [
        ("Kapitel zwei.", PAUSE_CHAPTER), ("Ende.", PAUSE_PARAGRAPH)]


def test_parse_book_ohne_kapitelzeile_nutzt_standardtitel():
    chapters = parse_book("Nur Text.\n\nZweiter Absatz.", 350, "Mein Buch")
    assert len(chapters) == 1 and chapters[0].title == "Mein Buch"
    assert [c.pause_after for c in chapters[0].chunks] == [PAUSE_PARAGRAPH, PAUSE_PARAGRAPH]


def test_paragraph_chunks_haelt_limit_und_satzgrenzen():
    par = "Satz eins ist hier. Satz zwei ist auch da. Satz drei kommt noch."
    assert paragraph_chunks(par, 40) == ["Satz eins ist hier.", "Satz zwei ist auch da.", "Satz drei kommt noch."]
    assert paragraph_chunks(par, 100) == [par]
    for limit in (40, 60, 100):
        assert all(len(c) <= limit for c in paragraph_chunks(par, limit))


def test_paragraph_chunks_trennt_nicht_an_dezimalpunkt():
    assert paragraph_chunks("Es kostet 3.5 Euro. Danach kommt mehr.", 30) == ["Es kostet 3.5 Euro.", "Danach kommt mehr."]


def test_split_long():
    assert split_long("kurz", 10) == ["kurz"]
    assert split_long("a, b, c, d, e, f", 6) == ["a, b,", "c, d,", "e, f"]
    worte = split_long("ein zwei drei vier fünf", 9)
    assert worte == ["ein zwei", "drei vier", "fünf"]


def test_sample_paragraph_ueberspringt_ueberschriften():
    lang = "Ein langer Fließtextabsatz. " * 12
    text = f"# Kapitel 1\n\nKurz.\n\n***\n\n{lang.strip()}\n"
    probe = sample_paragraph(text)
    assert probe.startswith("Ein langer Fließtextabsatz.")
    assert not probe.startswith("#")
