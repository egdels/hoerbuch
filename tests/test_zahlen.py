import pytest

from hoerbuch.zahlen import expand_numbers, num2words_available

pytestmark = pytest.mark.skipif(not num2words_available(), reason="num2words nicht installiert")


@pytest.mark.parametrize("roh, erwartet", [
    ("am 3. Mai 1848", "am dritten Mai achtzehnhundertachtundvierzig"),
    ("am 27. Januar 2020", "am siebenundzwanzigsten Januar zweitausendzwanzig"),
    ("03.05.21", "dritten Mai zweitausendeinundzwanzig"),
    ("der Müller hatte 1.200 Mark bezahlt", "der Müller hatte eintausendzweihundert Mark bezahlt"),
    ("2.267.118 Menschen", "zwei Millionen zweihundertsiebenundsechzigtausendeinhundertachtzehn Menschen"),
    ("fast 30 % seines Vermögens", "fast dreißig Prozent seines Vermögens"),
    ("0,7 Prozent", "null Komma sieben Prozent"),
    ("um 16.30 Uhr", "um sechzehn Uhr dreißig"),
    ("von 22.00 bis 5.00 Uhr", "von zweiundzwanzig Uhr bis fünf Uhr"),
    ("ca. 2,5 km lang", "ca. zwei Komma fünf Kilometer lang"),
    ("3.99 Euro", "drei Komma neunundneunzig Euro"),
    ("€ 5", "fünf Euro"),
    ("nach § 7 der Dorfordnung", "nach Paragraf sieben der Dorfordnung"),
    ("in den 70er Jahren", "in den siebziger Jahren"),
    ("Saison 2020/21", "Saison zweitausendzwanzig einundzwanzig"),
    ("8 – 12-Jährigen", "acht- bis zwölf-Jährigen"),
    ("10 – 15-fach", "zehn- bis fünfzehnfach"),
    ("MI5", "MI fünf"),
    ("Apollo-13", "Apollo-dreizehn"),
    ("im Jahr 1066", "im Jahr eintausendsechsundsechzig"),
    ("Seite 12", "Seite zwölf"),
])
def test_zahlen_ausschreiben(roh, erwartet):
    assert expand_numbers(roh) == erwartet


def test_ordnungszahl_endung_nach_kontext():
    assert expand_numbers("in der 3. Welle") == "in der dritten Welle"   # Dativ
    assert expand_numbers("der 3. Mann") == "der dritte Mann"            # Nominativ


def test_eins_vor_substantiv_mit_genus():
    assert expand_numbers("1 Woche") == "eine Woche"
    assert expand_numbers("1 Jahr") == "ein Jahr"


def test_ohne_ziffern_unveraendert():
    s = "Kein Zahlwort weit und breit."
    assert expand_numbers(s) == s
