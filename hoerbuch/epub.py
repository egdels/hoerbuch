"""EPUB → Text mit Kapitelmarken.

Liest die Kapitel in Spine-Reihenfolge, macht aus Überschriften "# "-Zeilen
(Kapitelmarken) bzw. "## "-Zeilen (gesprochene Zwischenüberschriften ohne
Kapitelmarke), lässt Cover, Titelei, Impressum und Inhaltsverzeichnis weg und
entfernt Fußnotenziffern."""
from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

from .bereinigung import INVISIBLE

EPUB_SKIP_DEFAULT = (r"cover|titel|title|impressum|copyright|inhalt|contents|^toc|^nav|"
                     r"weitere bücher|werbung|anzeige|advertis|bookwire|leseprobe|scan|qr-?code")
BLOCK_TAGS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
              "tr", "table", "ul", "ol", "section", "article", "header", "footer",
              "figure", "figcaption", "dd", "dt", "pre", "aside", "nav"}
HEADING_CLASS_RE = re.compile(r"^h([1-6])[a-z]?$", re.IGNORECASE)


class _EpubHTML(HTMLParser):
    """Wandelt ein XHTML-Kapitel in Blöcke (text, level) um. level 0 = Absatz."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, int]] = []
        self._buf: list[str] = []
        self._level = 0
        self._skip = 0          # in <head>, <script>, <style>, Fußnoten-Asides
        self._sup = 0
        self._sup_buf: list[str] = []
        self._in_table = 0
        self._row: list[str] = []
        self._cell: list[str] | None = None
        self.tables = 0

    def _flush(self):
        txt = "".join(self._buf).translate(INVISIBLE)
        txt = " ".join(txt.split())
        txt = re.sub(r"^[•·\-–—*▪■●]\s*", "", txt)       # Aufzählungszeichen
        if txt:
            self.blocks.append((txt, self._level))
        self._buf = []
        self._level = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        etype = (a.get("epub:type") or "").lower()
        if tag in ("head", "script", "style", "title") or "footnote" in etype or "endnote" in etype:
            self._skip += 1
            return
        if self._skip:
            return
        if tag == "sup":
            self._sup += 1
            self._sup_buf = []
            return
        if tag == "br":
            self._buf.append(" ")
            return
        if tag == "table":
            self._flush()
            self._in_table += 1
            self.tables += 1
            return
        if self._in_table:
            if tag == "tr":
                self._row = []
            elif tag in ("td", "th"):
                self._cell = []
            return
        if tag in BLOCK_TAGS:
            self._flush()
            m = re.fullmatch(r"h([1-6])", tag)
            if m:
                self._level = int(m.group(1))
            else:
                for cls in (a.get("class") or "").split():
                    m = HEADING_CLASS_RE.match(cls)
                    if m:
                        self._level = int(m.group(1))
                        break

    def handle_endtag(self, tag):
        if tag in ("head", "script", "style", "title", "aside"):
            if self._skip:
                self._skip -= 1
            return
        if self._skip:
            return
        if tag == "sup":
            self._sup = max(0, self._sup - 1)
            s = "".join(self._sup_buf).strip()
            # Fußnotenziffern/Sternchen verschwinden, echte Hochzahlen (m²) bleiben
            if s and not re.fullmatch(r"[\d*†‡§)\]\[(,\s]+", s):
                (self._cell if self._cell is not None else self._buf).append(s)
            return
        if self._in_table:
            if tag in ("td", "th") and self._cell is not None:
                c = " ".join("".join(self._cell).split())
                if c:
                    self._row.append(c)
                self._cell = None
            elif tag == "tr":
                if self._row:
                    self.blocks.append((", ".join(self._row) + ".", 0))
                self._row = []
            elif tag == "table":
                self._in_table -= 1
            return
        if tag in BLOCK_TAGS:
            self._flush()

    def handle_data(self, data):
        if self._skip:
            return
        if self._sup:
            self._sup_buf.append(data)
        elif self._cell is not None:
            self._cell.append(data)
        elif self._in_table:
            return
        else:
            self._buf.append(data)

    def close(self):
        super().close()
        self._flush()


def epub_to_text(path: Path, skip_pattern: str = EPUB_SKIP_DEFAULT, with_intro: bool = True):
    """Gibt (titel, autor, text, bericht) zurück."""
    import zipfile
    import xml.etree.ElementTree as ET
    from urllib.parse import unquote
    import posixpath

    skip_re = re.compile(skip_pattern, re.IGNORECASE) if skip_pattern else None
    z = zipfile.ZipFile(path)
    names = set(z.namelist())

    def read(name: str) -> str:
        return z.read(name).decode("utf-8", errors="replace")

    # Paketdatei finden
    opf_path = None
    if "META-INF/container.xml" in names:
        root = ET.fromstring(read("META-INF/container.xml"))
        for rf in root.iter():
            if rf.tag.endswith("rootfile") and rf.get("full-path"):
                opf_path = rf.get("full-path")
                break
    if not opf_path:
        opf_path = next((n for n in names if n.lower().endswith(".opf")), None)
    if not opf_path:
        sys.exit("Keine content.opf im EPUB gefunden.")
    opf_dir = posixpath.dirname(opf_path)
    opf = ET.fromstring(read(opf_path))

    def tagname(el) -> str:
        return el.tag.split("}")[-1]

    title = author = ""
    manifest: dict[str, tuple[str, str, str]] = {}   # id → (href, media-type, properties)
    spine: list[str] = []
    for el in opf.iter():
        t = tagname(el)
        if t == "title" and not title:
            title = (el.text or "").strip()
        elif t == "creator" and not author:
            author = (el.text or "").strip()
        elif t == "item":
            manifest[el.get("id")] = (el.get("href", ""), el.get("media-type", ""),
                                      el.get("properties", ""))
        elif t == "itemref":
            spine.append(el.get("idref"))
    if re.match(r"^[^,]+,\s*[^,]+$", author):           # "Muster, Erika" → "Erika Muster"
        last, first = [x.strip() for x in author.split(",", 1)]
        author = f"{first} {last}"

    # Navigationslabels (toc.ncx bzw. nav.xhtml) → Kapitelnamen als Rückfall
    labels: dict[str, str] = {}
    for mid, (href, mt, props) in manifest.items():
        full = posixpath.normpath(posixpath.join(opf_dir, unquote(href)))
        if full not in names:
            continue
        if mt == "application/x-dtbncx+xml":
            ncx = ET.fromstring(read(full))
            for np_ in ncx.iter():
                if tagname(np_) != "navPoint":
                    continue
                text = src = None
                for sub in np_.iter():
                    if tagname(sub) == "text" and text is None:
                        text = (sub.text or "").strip()
                    elif tagname(sub) == "content":
                        src = sub.get("src", "")
                if text and src:
                    doc = posixpath.normpath(posixpath.join(posixpath.dirname(full), unquote(src.split("#")[0])))
                    labels.setdefault(doc, text)
        elif "nav" in props.split():
            labels.setdefault(full, "")

    docs: list[dict] = []
    report: list[str] = []
    tables = 0
    seen = set()
    for idref in spine:
        if idref not in manifest:
            continue
        href, mt, props = manifest[idref]
        full = posixpath.normpath(posixpath.join(opf_dir, unquote(href)))
        if full in seen:
            continue
        seen.add(full)
        if full not in names:
            report.append(f"  fehlt im EPUB: {href}")
            continue
        if "nav" in props.split():
            report.append(f"  übersprungen (Navigation): {href}")
            continue
        parser = _EpubHTML()
        parser.feed(read(full))
        parser.close()
        blocks = parser.blocks
        tables += parser.tables
        label = labels.get(full, "")
        basename = posixpath.basename(full)
        total = sum(len(t) for t, _ in blocks)
        if total < 20:
            report.append(f"  übersprungen (kein Text): {basename}")
            continue
        probe = f"{basename} {label}"
        if skip_re and skip_re.search(probe):
            report.append(f"  übersprungen ({label or basename}, {total} Zeichen)")
            continue
        docs.append({"blocks": blocks, "label": label, "name": basename, "chars": total})

    # Blöcke → Text. Aufeinanderfolgende Überschriften werden zu einer zusammengefasst.
    out: list[str] = []
    chapters: list[str] = []
    if with_intro and (title or author):
        intro = title or Path(path).stem
        out.append("# " + intro)
        if author:
            out.append(f"{intro}. Von {author}.")
        chapters.append(intro)
    for d in docs:
        first_heading_done = False
        pending: list[tuple[str, int]] = []

        def emit_heading():
            nonlocal first_heading_done
            if not pending:
                return
            parts = [t for t, _ in pending]
            text = parts[0]
            for p in parts[1:]:
                text += (" – " if ":" in text else ": ") + p
            m_num = re.match(r"^(\d{1,3})\.?(?:\s+|:\s*)(\S.*)$", text)   # "1 Titel", "1. Titel", "1: Titel"
            if m_num:
                text = f"Kapitel {m_num.group(1)}: {m_num.group(2)}"
            level = min(l for _, l in pending)
            if not first_heading_done or level <= 2:
                out.append("# " + text)
                chapters.append(text)
            else:
                out.append("## " + text)
            first_heading_done = True
            pending.clear()

        has_heading = any(l for _, l in d["blocks"])
        if not has_heading:
            label = d["label"]
            if not label or re.fullmatch(r"(textbeginn|text|start|beginn|body|anfang|haupttext|section\s*\d*)", label, re.I):
                label = re.sub(r"[_\-]+", " ", Path(d["name"]).stem)
            name = label
            out.append("# " + name)
            chapters.append(name)
            first_heading_done = True
        for text, level in d["blocks"]:
            if level:
                pending.append((text, level))
            else:
                emit_heading()
                out.append(text)
        emit_heading()

    info = []
    info.append(f"{len(docs)} Dokumente übernommen, {len(chapters)} Kapitel, "
                f"{sum(d['chars'] for d in docs):,} Zeichen".replace(",", "."))
    if tables:
        info.append(f"  {tables} Tabellen zeilenweise übernommen (bitte prüfen, ob sie vorgelesen werden sollen)")
    info.extend(report)
    return title, author, "\n\n".join(out) + "\n", info
