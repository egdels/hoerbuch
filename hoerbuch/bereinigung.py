"""Regelbasierte Textbereinigung: Kodierung, Seitenzahlen, Kopfzeilen, Silbentrennung,
Absätze, Abkürzungen, Kapitelüberschriften."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .zahlen import expand_numbers

LIGATURES = {
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st",
}
INVISIBLE = dict.fromkeys(map(ord, "­​‌‍⁠﻿"), None)
SPACES = dict.fromkeys(map(ord, "       \t"), " ")
SUPERSCRIPTS = "⁰¹²³⁴⁵⁶⁷⁸⁹"

# Abkürzungen → ausgeschrieben (Reihenfolge: längere zuerst)
ABBREVIATIONS = [
    (r"\bz\.\s?B\.", "zum Beispiel"),
    (r"\bZ\.\s?B\.", "Zum Beispiel"),
    (r"\bn\.\s?e\.\s?V\.", "nicht eingetragener Verein"),
    (r"\be\.\s?V\.", "eingetragener Verein"),
    (r"\bbe?zgl\.", "bezüglich"),
    (r"\bAbs\.(?=\s*\d)", "Absatz"),
    (r"\bJan\.", "Januar"), (r"\bFeb\.", "Februar"), (r"\bMär\.", "März"), (r"\bApr\.", "April"),
    (r"\bAug\.", "August"), (r"\bSept?\.", "September"), (r"\bOkt\.", "Oktober"),
    (r"\bNov\.", "November"), (r"\bDez\.", "Dezember"),
    (r"\bArt\.(?=\s*\d)", "Artikel"),
    (r"\bmax\.", "maximal"),
    (r"\bmin\.(?=\s+[a-zäöü])", "mindestens"),
    (r"\bet al\.", "und andere"),
    (r"\bCa\.", "Circa"),
    (r"\bAbb\.(?=\s*\d)", "Abbildung"),
    (r"\bTab\.(?=\s*\d)", "Tabelle"),
    (r"\bJh\.", "Jahrhundert"),
    (r"\bd\.\s?h\.", "das heißt"),
    (r"\bu\.\s?a\.", "unter anderem"),
    (r"\bu\.\s?U\.", "unter Umständen"),
    (r"\bo\.\s?ä\.", "oder ähnlich"),
    (r"\bu\.\s?Ä\.", "und Ähnliches"),
    (r"\bs\.\s?o\.", "siehe oben"),
    (r"\bs\.\s?u\.", "siehe unten"),
    (r"\bz\.\s?T\.", "zum Teil"),
    (r"\bi\.\s?d\.\s?R\.", "in der Regel"),
    (r"\bu\.\s?s\.\s?w\.", "und so weiter"),
    (r"\busw\.", "und so weiter"),
    (r"\betc\.", "et cetera"),
    (r"\bbzw\.", "beziehungsweise"),
    (r"\bca\.", "circa"),
    (r"\bevtl\.", "eventuell"),
    (r"\bggf\.", "gegebenenfalls"),
    (r"\binkl\.", "inklusive"),
    (r"\bvgl\.", "vergleiche"),
    (r"\bsog\.", "sogenannte"),
    (r"\bDr\.", "Doktor"),
    (r"\bProf\.", "Professor"),
    (r"\bHr\.", "Herr"),
    (r"\bFr\.(?=\s+[A-ZÄÖÜ])", "Frau"),
    (r"\bNr\.(?=\s*\d)", "Nummer"),
    (r"\bS\.(?=\s*\d)", "Seite"),
    (r"\bMio\.", "Millionen"),
    (r"\bMrd\.", "Milliarden"),
    (r"\bJhd\.", "Jahrhundert"),
    (r"\bv\.\s?Chr\.", "vor Christus"),
    (r"\bn\.\s?Chr\.", "nach Christus"),
]
# Diese Abkürzungen sind ohne Kontext mehrdeutig. Mit --ki entscheidet das Sprachmodell.
AMBIGUOUS_ABBREVIATIONS = {r"\bFr\.(?=\s+[A-ZÄÖÜ])", r"\bS\.(?=\s*\d)"}

CHAPTER_RE = re.compile(
    r"^\s*("
    r"(kapitel|teil|buch|abschnitt|prolog|epilog|nachwort|vorwort|einleitung|anhang)\b.*"
    r"|chapter\s+\w+.*"
    r"|[IVXLC]{1,7}\.?"                      # nur römische Zahl
    r"|\d{1,3}\.?"                           # nur Zahl ("7" oder "7.")
    r"|\d{1,3}\.?\s+[A-ZÄÖÜ][^.!?]{0,60}"    # "7. Die Rückkehr"
    r")\s*$",
    re.IGNORECASE,
)
KEYWORD_RE = re.compile(
    r"^\s*(kapitel|prolog|epilog|nachwort|vorwort|einleitung|anhang|chapter)\b", re.IGNORECASE)
HEAD_MARK = "\x00H"
SCENE_RE = re.compile(r"^\s*([*#~=_\-–—•·]\s*){3,}$|^\s*[*#~•·]\s*$")
URL_RE = re.compile(r"(https?://\S+|www\.\S+)", re.IGNORECASE)
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF☀-➿️]")


ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def roman_to_int(s: str) -> int | None:
    s = s.upper()
    if not s or any(c not in ROMAN for c in s):
        return None
    total = 0
    for i, c in enumerate(s):
        v = ROMAN[c]
        total += -v if i + 1 < len(s) and ROMAN[s[i + 1]] > v else v
    return total


@dataclass
class CleanReport:
    encoding: str = ""
    removed_pages: int = 0
    removed_headers: dict = field(default_factory=dict)
    dehyphenated: int = 0
    abbreviations: int = 0
    urls: int = 0
    chapters: list = field(default_factory=list)
    paragraph_mode: str = ""
    ki: bool = False                 # Sprachmodell-Stufe aktiv → mehrdeutige Abkürzungen offen lassen
    numbers: bool = True             # Ziffern als Zahlwörter ausschreiben
    numbers_expanded: int = 0
    ki_applied: int = 0
    ki_rejected: int = 0
    ki_headings: int = 0
    ki_seconds: float = 0.0


MOJIBAKE = "[\u00c2\u00c3\u00e2][\u0080-\u00bf\u0152\u0153\u0160\u0161\u0178\u017d\u017e\u0192\u02c6\u02dc\u2013-\u203a\u20ac\u2122]{1,2}"


def _fix_mojibake_seq(m: re.Match) -> str:
    seq = m.group(0)
    for enc in ("cp1252", "latin-1"):
        for k in (len(seq), 2):
            try:
                return seq[:k].encode(enc).decode("utf-8") + seq[k:]
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
    return seq


def read_text(path: Path, report: CleanReport) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            report.encoding = enc
            break
        except UnicodeDecodeError:
            continue
    # kaputte Umlaute ("Ã¤" statt "ä") reparieren
    if re.search(MOJIBAKE, text):
        try:
            import ftfy  # type: ignore
            text = ftfy.fix_text(text)
            report.encoding += " (Umlaute repariert mit ftfy)"
        except ImportError:
            text = re.sub(MOJIBAKE, _fix_mojibake_seq, text)
            report.encoding += " (Umlaute repariert)"
    return text


def normalize_chars(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("»", "„").replace("«", "“").replace("›", "‚").replace("‹", "‘")
    for k, v in LIGATURES.items():
        text = text.replace(k, v)
    text = text.translate(INVISIBLE).translate(SPACES)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n\n")
    return text


def is_heading(line: str) -> bool:
    s = line.strip()
    return bool(s) and len(s) <= 80 and bool(CHAPTER_RE.match(s))


def clean_text(text: str, report: CleanReport) -> str:
    text = normalize_chars(text)
    lines = text.split("\n")

    # 1. Seitenzahlen entfernen
    #    "- 12 -" und "Seite 12" sind immer Seitenzahlen. Reine Zahlen ("12") nur dann,
    #    wenn sie oft und in kurzen Abständen vorkommen (sonst sind es Kapitelnummern).
    always = re.compile(r"^\s*([-–—]\s*\d{1,4}\s*[-–—]|seite\s+\d{1,4}(\s*(/|von)\s*\d{1,4})?|\d{1,4}\s*/\s*\d{1,4})\s*$",
                        re.IGNORECASE)
    bare = [(i, int(ln)) for i, ln in enumerate(lines) if re.fullmatch(r"\s*\d{1,4}\s*", ln)]
    # Seitenzahlen bilden eine lange Kette n, n+1, n+2 … in kurzen, regelmäßigen
    # Abständen (eine Seite = ca. 15–120 Zeilen). Kapitelnummern liegen weiter auseinander.
    # Kapitelanfangsseiten tragen oft keine Seitenzahl, daher sind Lücken von bis zu
    # zwei Seiten erlaubt. Gibt es mindestens eine Kette aus 5 Seitenzahlen, gelten
    # auch alle weiteren Ketten ab 3 Gliedern als Seitenzahlen.
    chains: list[list[int]] = []
    used: set[int] = set()
    for k, (i0, v0) in enumerate(bare):
        if i0 in used or v0 < 2:   # "1" ist eher Kapitel 1 als Seite 1
            continue
        chain, last_i, last_v = [i0], i0, v0
        for i, v in bare[k + 1:]:
            if i in used:
                continue
            # Ab drei Gliedern darf die Seite kurz sein (letzte Seite eines Kapitels/Buchs).
            min_gap = 15 if len(chain) < 3 else 3
            if last_v < v <= last_v + 3 and min_gap <= i - last_i <= 360:
                chain.append(i)
                last_i, last_v = i, v
            elif i - last_i > 360:
                break
        used.update(chain)
        chains.append(chain)
    best = max(chains, key=len, default=[])
    page_lines: set[int] = set()
    if len(best) >= 5:
        for chain in chains:
            if len(chain) >= 3:
                page_lines.update(chain)
    bare_set = page_lines
    kept = []
    for i, ln in enumerate(lines):
        if always.match(ln) or i in bare_set:
            report.removed_pages += 1
            continue
        kept.append(ln)
    lines = kept

    # 2. Wiederkehrende Kopf-/Fußzeilen (kurze Zeilen, die oft identisch vorkommen)
    counts = Counter(ln.strip() for ln in lines if 0 < len(ln.strip()) <= 70)
    threshold = max(5, len(lines) // 400)
    headers = {s for s, c in counts.items()
               if c >= threshold and not is_heading(s) and not SCENE_RE.match(s)
               and not s.startswith("#")
               and not re.search(r"[.!?…\"“”»«]$", s)}
    if headers:
        report.removed_headers = {s: counts[s] for s in headers}
        lines = [ln for ln in lines if ln.strip() not in headers]

    text = "\n".join(lines)

    # 3. Silbentrennung am Zeilenende auflösen
    def _dehyph(m: re.Match) -> str:
        report.dehyphenated += 1
        a, b = m.group(1), m.group(2)
        # Großbuchstabe danach → echter Bindestrich (Ost-West, E-Mail-Adresse)
        return f"{a}-{b}" if b[0].isupper() else f"{a}{b}"
    text = re.sub(r"(\w)[-¬]\n[ \t]*(\w+)", _dehyph, text)

    # 4. Absätze rekonstruieren
    raw_lines = text.split("\n")
    nonempty = [ln for ln in raw_lines if ln.strip()]
    blank_ratio = (len(raw_lines) - len(nonempty)) / max(1, len(raw_lines))
    avg_len = sum(len(ln) for ln in nonempty) / max(1, len(nonempty))
    one_par_per_line = blank_ratio < 0.05 and avg_len > 150
    report.paragraph_mode = ("eine Zeile = ein Absatz" if one_par_per_line
                             else "Absätze durch Leerzeilen, Zeilen werden zusammengeführt")

    paragraphs: list[str] = []
    buf: list[str] = []

    def flush():
        if buf:
            paragraphs.append(" ".join(s.strip() for s in buf))
            buf.clear()

    def blank(i: int) -> bool:
        return i < 0 or i >= len(raw_lines) or not raw_lines[i].strip()

    def heading_at(i: int) -> bool:
        s = raw_lines[i].strip()
        if re.match(r"^#{1,2} \S", s):      # bereits markierte Überschrift (z. B. aus EPUB-Export)
            return True
        if not is_heading(s):
            return False
        if one_par_per_line:
            return len(s) <= 60 and not re.search(r"[!?…,;:\"“”»«]$", s)
        return blank(i - 1) and (blank(i + 1) or bool(KEYWORD_RE.match(s)))

    i = 0
    while i < len(raw_lines):
        s = raw_lines[i].strip()
        if not s:
            flush()
            i += 1
            continue
        if SCENE_RE.match(s) and (one_par_per_line or blank(i - 1) or blank(i + 1)):
            flush()
            paragraphs.append("***")
            i += 1
            continue
        if heading_at(i):
            flush()
            if s.startswith("#"):
                paragraphs.append(HEAD_MARK + s)
                i += 1
                continue
            # Untertitel darunter, direkt oder nach einer Leerzeile ("Kapitel 1" / "Der Anfang"):
            # kurze Zeile ohne Satzschluss, danach Leerzeile, selbst keine Überschrift
            j = i + 1 if not blank(i + 1) else (i + 2 if not blank(i + 2) else None)
            if j is not None and not one_par_per_line and blank(j + 1):
                sub = raw_lines[j].strip()
                if (len(sub) <= 60 and not re.search(r"[.!?…,;:\"“”»«]$", sub)
                        and not sub.startswith("#") and not is_heading(sub) and not SCENE_RE.match(sub)):
                    paragraphs.append(HEAD_MARK + s + ": " + sub)
                    i = j + 1
                    continue
            paragraphs.append(HEAD_MARK + s)
            i += 1
            continue
        if one_par_per_line:
            paragraphs.append(s)
        else:
            buf.append(s)
        i += 1
    flush()

    # 5. Pro Absatz: Überschriften, Szenenwechsel, Zeichen säubern
    out: list[str] = []
    for p in paragraphs:
        if p == "***":
            if out and out[-1] != "***":
                out.append("***")
            continue
        if p.startswith(HEAD_MARK):
            h = re.sub(r"\s+", " ", p[len(HEAD_MARK):]).strip()
            m = re.match(r"^(#{1,2}) (.*)$", h)
            if m:                          # bereits markiert: Text säubern, Markierung behalten
                h = clean_sentence_text(m.group(2), report, numbers=False)
                out.append(m.group(1) + " " + h)
                if m.group(1) == "#":
                    report.chapters.append(h)
                continue
            # römische Zahlen → arabisch ("Kapitel IV" → "Kapitel 4")
            h = re.sub(r"\b([IVXLC]{1,7})\b(\.?)",
                       lambda m: str(roman_to_int(m.group(1))) if roman_to_int(m.group(1)) else m.group(0),
                       h)
            if re.fullmatch(r"\d{1,3}\.?", h):
                h = "Kapitel " + h.rstrip(".")
            out.append("# " + h)
            report.chapters.append(h)
            continue
        out.append(clean_sentence_text(p, report))

    text = "\n\n".join(x for x in out if x.strip())
    return text.strip() + "\n"


def clean_sentence_text(p: str, report: CleanReport, numbers: bool = True) -> str:
    n_urls = len(URL_RE.findall(p))
    report.urls += n_urls
    p = URL_RE.sub("", p)
    p = EMOJI_RE.sub("", p)
    # Gendersternchen: "Freund*innen" → "Freund-innen", "seine*ihre" → "seine oder ihre", Rest-Sterne weg
    p = re.sub(r"(\w)\*(innen|in)\b", r"\1-\2", p)
    p = re.sub(r"([a-zäöüß])\*([a-zäöüß])", r"\1 oder \2", p)
    p = p.replace("*", " ")
    # fehlendes Leerzeichen nach Satzzeichen ("Fisch.Wir" → "Fisch. Wir")
    p = re.sub(r"([a-zäöüß]{2})([.!?])([A-ZÄÖÜ][a-zäöü])", r"\1\2 \3", p)
    # Fußnotenzeichen
    p = re.sub(f"[{SUPERSCRIPTS}]+", "", p)
    p = re.sub(r"\[\d{1,3}\]", "", p)
    p = re.sub(r"(?<=[a-zäöüß])\d{1,2}(?=[\s.,;:!?]|$)", "", p)            # "Wort12 " → "Wort "
    p = re.sub(r"(?<=[a-zäöüß][.,;:!?\"“”»«])\d{1,2}(?=\s|$)", "", p)      # "Wort.12 " → "Wort. "
    # Abkürzungen
    for pat, rep in ABBREVIATIONS:
        if report.ki and pat in AMBIGUOUS_ABBREVIATIONS:
            continue
        p, n = re.subn(pat, rep, p)
        report.abbreviations += n
    if numbers and report.numbers:
        before = p
        p = expand_numbers(p)
        if p != before:
            report.numbers_expanded += len(re.findall(r"\d+", before)) - len(re.findall(r"\d+", p))
    # Zeichen, die TTS/SSML stören
    p = p.replace("&", " und ")
    p = re.sub(r"[<>{}\[\]|\\^~`_]", " ", p)
    p = re.sub(r"\.{3,}|…", "…", p)
    p = re.sub(r"([!?])[!?]+", r"\1", p)
    p = re.sub(r"\s*[–—]\s*", " – ", p)
    p = re.sub(r"\s+([,.;:!?…])", r"\1", p)
    p = re.sub(r"\s{2,}", " ", p)
    return p.strip()


def is_text_par(p: str) -> bool:
    """Fließtextabsatz, keine Überschrift (# / ##) und kein Szenenwechsel (***)."""
    return bool(p) and not re.match(r"^#{1,2} ", p) and p != "***"
