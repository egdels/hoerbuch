import zipfile

from hoerbuch.epub import EPUB_SKIP_DEFAULT, epub_to_text

CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""

OPF = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/" version="3.0">
  <metadata><dc:title>Der Nebel</dc:title><dc:creator>Muster, Erika</dc:creator></metadata>
  <manifest>
    <item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="k1" href="kap1.xhtml" media-type="application/xhtml+xml"/>
    <item id="k2" href="kap2.xhtml" media-type="application/xhtml+xml"/>
    <item id="imp" href="AUD_02_epub_001.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="cover"/><itemref idref="imp"/><itemref idref="nav"/><itemref idref="k1"/><itemref idref="k2"/></spine>
</package>"""

COVER = "<html><body><p>Umschlagbild mit etwas Text, damit die Datei nicht leer ist.</p></body></html>"
NAV = "<html><body><nav><ol><li><a href='kap1.xhtml'>Eins</a></li></ol></nav></body></html>"
KAP1 = """<html><head><title>Kap 1</title></head><body>
<h1>1</h1><h2>Der alte Bahnhof</h2>
<p>Es war ein stiller Abend.<sup>1</sup> Der Zug war weg.</p>
<p class="h3">Die Mühle</p>
<p>Am Bach entlang, bis der Weg aufhört. Fläche: 3 m<sup>²</sup>.</p>
<aside epub:type="footnote"><p>1 Eine Fußnote, die nicht vorgelesen wird.</p></aside>
<table><tr><td>Jahr</td><td>Wert</td></tr><tr><td>1848</td><td>zwölf</td></tr></table>
</body></html>"""
KAP2 = "<html><body><h1>Die Nachricht</h1><p>Am nächsten Morgen lag ein Brief vor seiner Tür.</p></body></html>"
IMPRESSUM = ("<html><body><p>Mehr über unsere Bücher: www.beispielverlag.example</p>"
             "<p>© Beispielverlag GmbH, Musterstadt 2024</p><p>Covergestaltung: Büro Muster</p>"
             "<p>ISBN 978-3-00-000000-0</p></body></html>")


def make_epub(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", CONTAINER)
        z.writestr("OEBPS/content.opf", OPF)
        z.writestr("OEBPS/cover.xhtml", COVER)
        z.writestr("OEBPS/nav.xhtml", NAV)
        z.writestr("OEBPS/kap1.xhtml", KAP1)
        z.writestr("OEBPS/kap2.xhtml", KAP2)
        z.writestr("OEBPS/AUD_02_epub_001.xhtml", IMPRESSUM)


def test_epub_to_text(tmp_path):
    epub = tmp_path / "buch.epub"
    make_epub(epub)
    title, author, text, info = epub_to_text(epub, EPUB_SKIP_DEFAULT, with_intro=True)

    assert title == "Der Nebel"
    assert author == "Erika Muster"                         # "Nachname, Vorname" wird umgestellt
    lines = text.splitlines()
    assert lines[0] == "# Der Nebel"                        # Intro mit Titel und Autor
    assert "Der Nebel. Von Erika Muster." in text
    assert "# Kapitel 1: Der alte Bahnhof" in lines         # nackte Nummer + Untertitel zusammengefasst
    assert "## Die Mühle" in lines                          # class="h3" → Zwischenüberschrift
    assert "# Die Nachricht" in lines
    assert "Es war ein stiller Abend. Der Zug war weg." in lines   # Fußnotenziffer entfernt
    assert "Fläche: 3 m²." in text                          # echte Hochzahl bleibt, nur Ziffern-Sup gelten als Fußnote
    assert "nicht vorgelesen" not in text                   # Fußnoten-Aside ausgelassen
    assert "Umschlagbild" not in text                       # Cover übersprungen
    assert "Jahr, Wert." in lines and "1848, zwölf." in lines     # Tabellen zeilenweise
    assert any("Tabellen" in i for i in info)
    assert any("übersprungen" in i for i in info)
    # Impressum mit nichtssagendem Dateinamen wird am Inhalt erkannt
    assert any("Impressum erkannt: AUD_02_epub_001.xhtml" in i for i in info)
    assert "Beispielverlag" not in text and "AUD 02" not in text


def test_epub_ohne_intro_und_ohne_auslassen(tmp_path):
    epub = tmp_path / "buch.epub"
    make_epub(epub)
    _, _, text, _ = epub_to_text(epub, "", with_intro=False)
    assert not text.startswith("# Der Nebel")
    assert "Umschlagbild" in text
