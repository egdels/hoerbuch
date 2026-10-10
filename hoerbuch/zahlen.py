"""Zahlen deterministisch als deutsche Zahlwörter ausschreiben (num2words).

Sprachmodelle vertun sich bei deutschen Zahlwörtern regelmäßig (Zehner/Einer
vertauscht, Jahreszahlen falsch). Darum übernimmt das der Code. Nur die
grammatische Endung von Ordnungszahlen wird aus dem Kontext geschätzt."""
from __future__ import annotations

import re

MONTHS = ("Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember|"
          "Jänner|Jan\\.|Feb\\.|Mär\\.|Apr\\.|Aug\\.|Sept\\.|Sep\\.|Okt\\.|Nov\\.|Dez\\.")
# Wörter, nach denen "3." eine Ordnungszahl im Dativ/Akkusativ/Genitiv ist → Endung "-n"
ORD_PREV_N = {"am", "im", "vom", "zum", "zur", "beim", "seit", "ab", "nach", "vor", "mit", "bis",
              "dem", "den", "des", "einem", "einer", "eines", "jeden", "jedem", "jeder", "dieser",
              "diesen", "diesem", "seiner", "seinem", "seinen", "ihrer", "ihrem", "ihren",
              "unserer", "unserem", "unseren", "zwischen", "um", "auf", "an", "in", "über", "unter"}
# Wörter, nach denen die Endung "-e" ist (Nominativ/Akkusativ Neutrum/Femininum)
ORD_PREV_E = {"der", "die", "das", "eine", "jede", "jedes", "diese", "dieses", "welche", "welches"}
# Substantive, vor denen "3." praktisch immer eine Ordnungszahl ist
ORD_NOUNS = re.compile(
    r"^(Kalenderwoche|Welle|Platz|Stelle|Jahrhundert|Jahrtausend|Mal|Klasse|Auflage|Lebensjahr|Tag|Woche|"
    r"Monat|Quartal|Halbjahr|Jahrgang|Geburtstag|Stock|Etage|Kapitel|Teil|Band|Satz|Absatz|Artikel|"
    r"Weltkrieg|Reich|Liga|Runde|Spieltag|Sitzung|Lesung|Fassung|Version|Dosis|Impfung|Zeile|Seite|"
    r"Ausgabe|Generation|Staffel|Folge|Akt|Szene|Strophe|Semester|Schuljahr|Legislaturperiode|Amtszeit|"
    r"Wahlgang|Durchgang|Versuch|Anlauf|Bundesliga|Division|Armee|Infanterie|Jahrestag|Todestag|Advent|"
    r"Sonntag|Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Stunde|Minute|Sekunde|Reihe|Spalte|"
    r"Position|Rang|Stufe|Ebene|Phase|Stadium|Grad|Ordnung|Dimension|Person|Singular|Plural|Fall|Kind|Sohn|Tochter)"
    r"(e|en|es|er|n|s)?$")
_N2W = None


def _n2w():
    global _N2W
    if _N2W is None:
        try:
            from num2words import num2words
            _N2W = num2words
        except ImportError:
            _N2W = False
    return _N2W


def _card(s: str) -> str:
    """Kardinalzahl aus Ziffernfolge (ohne Tausenderpunkte)."""
    n2w = _n2w()
    n = int(s)
    return n2w(n, lang="de")


def _year_or_card(s: str) -> str:
    n2w = _n2w()
    n = int(s)
    if 1100 <= n <= 2099:
        return n2w(n, lang="de", to="year")
    return n2w(n, lang="de")


def _ordinal(s: str, prev: str, nxt: str) -> str:
    """prev = bis zu zwei Wörter davor ("in der"), nxt = Wort danach."""
    n2w = _n2w()
    base = n2w(int(s), lang="de", to="ordinal")      # "dritte"
    words = prev.lower().split()
    last = words[-1] if words else ""
    before = words[-2] if len(words) > 1 else ""
    if last in ORD_PREV_E:
        # "in der dritten Welle" (Dativ) vs. "der dritte Mann" (Nominativ)
        if last == "der" and before in {"in", "an", "auf", "bei", "mit", "nach", "seit", "von", "zu", "aus",
                                        "während", "wegen", "trotz", "innerhalb", "außerhalb", "ende", "anfang",
                                        "mitte", "beginn", "aus", "ab", "vor", "über", "unter", "zwischen"}:
            return base + "n"
        return base
    if last in ORD_PREV_N:
        return base + "n"
    return base + "n"


def _decimal(ip: str, dp: str) -> str:
    n2w = _n2w()
    head = n2w(int(ip), lang="de")
    if dp.startswith("0") or len(dp) > 3:
        tail = " ".join(n2w(int(d), lang="de") for d in dp)
    else:
        tail = n2w(int(dp), lang="de")
    return f"{head} Komma {tail}"


def _one_before_noun(word: str) -> str:
    """'1 Woche' → 'eine Woche', '1 Jahr' → 'ein Jahr' (grobe Schätzung des Genus)."""
    if re.search(r"(e|ung|heit|keit|schaft|ion|tät|ik|ur|in|ei|enz|anz|ie)$", word):
        return "eine"
    return "ein"


def expand_numbers(p: str) -> str:
    """Schreibt Ziffern in einem Absatz als Zahlwörter aus."""
    if not _n2w():
        return p
    D = r"\d{1,3}(?:\.\d{3})+|\d+"          # Ganzzahl mit oder ohne Tausenderpunkte

    def plain(s: str) -> str:
        return s.replace(".", "")

    # Uhrzeiten: "16.30 Uhr", "von 22.00 bis 5.00 Uhr", "um 5 Uhr"
    def _time(m):
        h, mi = int(m.group(1)), m.group(2)
        out = _card(str(h)) + " Uhr"
        if mi and int(mi):
            out += " " + _card(mi)
        return out
    p = re.sub(r"\b(\d{1,2})[.:](\d{2})(?=\s*(?:bis|und|–|-|/)\s*\d{1,2}[.:]\d{2}\s*Uhr\b)", _time, p)
    p = re.sub(r"\b(\d{1,2})(?:[.:](\d{2}))?\s*Uhr\b", _time, p)

    # Einheiten direkt nach Zahlen
    UNITS = {"km": "Kilometer", "cm": "Zentimeter", "mm": "Millimeter", "kg": "Kilogramm", "mg": "Milligramm",
             "ml": "Milliliter", "km/h": "Kilometer pro Stunde", "°C": "Grad Celsius", "€": "Euro", "$": "Dollar",
             "qm": "Quadratmeter", "m²": "Quadratmeter", "ha": "Hektar", "kWh": "Kilowattstunden", "MHz": "Megahertz",
             "GB": "Gigabyte", "MB": "Megabyte", "l": "Liter", "sek": "Sekunden", "Sek.": "Sekunden", "Min.": "Minuten",
             "Std.": "Stunden", "Mrd.": "Milliarden", "Mio.": "Millionen", "Tsd.": "Tausend"}
    p = re.sub(r"(\d)\s?(km/h|°C|m²|km|cm|mm|kg|mg|ml|qm|ha|kWh|MHz|GB|MB|Sek\.|Min\.|Std\.|Mrd\.|Mio\.|Tsd\.|€|\$)(?![\w/])",
               lambda m: m.group(1) + " " + UNITS[m.group(2)], p)
    p = re.sub(r"(€|\$)\s?(\d)", lambda m: m.group(2) + " " + UNITS[m.group(1)] + "@@", p)   # "€ 5" → "5 Euro"

    # Datum: "27. Januar 2020", "am 3. Mai", "3.5.2021", "03.05.21"
    def _date_long(m):
        prev = m.group(1) or ""
        day = _ordinal(m.group(2), prev, m.group(3))
        out = f"{prev}{day} {m.group(3)}"
        if m.group(4):
            out += " " + _year_or_card(m.group(4))
        return out
    p = re.sub(rf"((?:\b\w+\s+){{0,2}})\b(\d{{1,2}})\.\s?({MONTHS})\b(?:\s+(\d{{4}})\b)?", _date_long, p)
    MONTH_NAMES = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
                   "September", "Oktober", "November", "Dezember"]

    def _date_num(m):
        prev = m.group(1) or ""
        d, mo, y = int(m.group(2)), int(m.group(3)), m.group(4)
        if not (1 <= d <= 31 and 1 <= mo <= 12):
            return m.group(0)
        out = f"{prev}{_ordinal(str(d), prev, 'Januar')} {MONTH_NAMES[mo - 1]}"
        if y:
            yy = int(y) if len(y) == 4 else 2000 + int(y) if int(y) < 50 else 1900 + int(y)
            out += " " + _year_or_card(str(yy))
        return out
    p = re.sub(r"((?:\b\w+\s+){0,2})\b(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4}|\d{2})\b", _date_num, p)

    # Jahresangaben mit Schrägstrich: "2020/21", "2020/2021", "20/21"
    def _slash(m):
        a, b = m.group(1), m.group(2)
        if len(b) == 2:
            b_full = a[:2] + b
        else:
            b_full = b
        return _year_or_card(a) + " " + (_card(b) if len(b) == 2 else _year_or_card(b_full))
    p = re.sub(r"\b((?:19|20)\d{2})/(\d{2}|\d{4})\b", _slash, p)
    p = re.sub(r"\b(\d{2})/(\d{2})\b", lambda m: _card(m.group(1)) + " " + _card(m.group(2)), p)

    # Prozent
    p = re.sub(rf"\b({D}(?:,\d+)?)\s?%", lambda m: m.group(1) + " Prozent", p)
    # Paragraf
    p = re.sub(r"§§?\s*", "Paragraf ", p)

    # Bereiche: "8 – 12-Jährigen" → "acht- bis zwölf-Jährigen", "10 – 15-fach" → "zehn- bis fünfzehnfach",
    # "28 bis 60 Tagen" bleibt (Zahlen einzeln), "400.000 – 600.000" → "… bis …"
    p = re.sub(rf"\b({D})\s*[–-]\s*({D})-(\w)", lambda m: f"{m.group(1)}- bis {m.group(2)}-{m.group(3)}", p)
    p = re.sub(rf"\b({D})\s*[–-]\s*({D})\b", r"\1 bis \2", p)

    # Dezimalzahlen "2,5", "1,50", "0,0013"; englische Schreibung bei Preisen "3.99 Euro"
    p = re.sub(r"\b(\d+)\.(\d{1,2})(?=\s?(?:Euro|Dollar|Pfund|Franken|Mark|Prozent|Meter|Kilometer|Liter|Kilo|Gramm|Sekunden|Minuten)\b)",
               lambda m: _decimal(m.group(1), m.group(2)), p)
    p = re.sub(rf"\b({D}),(\d+)\b", lambda m: _decimal(plain(m.group(1)), m.group(2)), p)

    # Ordnungszahlen vor Substantiv oder nach Präposition/Artikel: "3. Welle", "am 3.", "der 20. bis 23. Kalenderwochen"
    def _ord(m):
        prev, num, nxt = m.group(1) or "", m.group(2), m.group(3) or ""
        pl = prev.strip().lower().split()[-1:] or [""]
        if pl[0] in ORD_PREV_N or pl[0] in ORD_PREV_E or ORD_NOUNS.match(nxt) or nxt == "bis":
            return f"{prev}{_ordinal(num, prev.strip(), nxt)} {nxt}".rstrip()
        return m.group(0)
    p = re.sub(r"((?:\b\w+\s+){0,2})\b(\d{1,2})\.\s+(\w+)", _ord, p)

    # Jahrzehnte: "70er Jahre", "in den 1970ern", "50er-Jahre-Bau"
    p = re.sub(r"\b(\d{2}|\d{4})er(n?)\b", lambda m: _year_or_card(m.group(1)) + "er" + m.group(2), p)
    # Rest: Ganzzahlen (Jahreszahlen 1100–2099 als Jahr), auch in Bindestrichwörtern (Apollo-13)
    def _int(m):
        s = plain(m.group(0))
        if len(s) > 15:
            return m.group(0)
        word = _card(s) if "." in m.group(0) else _year_or_card(s)
        # "MI5" → "MI fünf", "H5N1" → "H fünf N eins"
        if m.start() > 0 and p[m.start() - 1].isalpha():
            word = " " + word
        if m.end() < len(p) and p[m.end()].isalpha():
            word = word + " "
        return word
    p = re.sub(rf"(?<![\d.,])({D})(?!\d)(?![.,]\d)", _int, p)

    # "eins Jahr" → "ein Jahr", "eins Woche" → "eine Woche"
    p = re.sub(r"\beins(-| )([A-ZÄÖÜ]\w*)", lambda m: m.group(0) if m.group(2) in ("Komma", "Prozent", "Uhr")
               else _one_before_noun(m.group(2)) + m.group(1) + m.group(2), p)
    p = re.sub(r"\beins (Prozent|Uhr)\b", r"ein \1", p)
    # "fünfzehn-fach" → "fünfzehnfach"
    p = re.sub(r"(\w)-(fach|mal|jährig\w*|köpfig\w*|prozentig\w*|stündig\w*|tägig\w*|wöchig\w*|monatig\w*|"
               r"teilig\w*|stellig\w*|facher|fache|faches|fachen)\b", r"\1\2", p)
    p = p.replace("@@", "")
    return p


def num2words_available() -> bool:
    return bool(_n2w())
