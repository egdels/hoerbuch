"""Bereinigten Text in Kapitel und sprechbare Abschnitte zerlegen."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .bereinigung import is_text_par
from .konfig import MAX_CHUNK_CHARS, PAUSE_CHAPTER, PAUSE_PARAGRAPH, PAUSE_SCENE, PAUSE_SENTENCE
from .zahlen import expand_numbers

@dataclass
class Chunk:
    text: str
    pause_after: float


@dataclass
class Chapter:
    title: str
    chunks: list


SENT_END = re.compile(r"(?<![0-9])([.!?…][\"“”»«'’)]*)\s+(?=[\"„“»«'‚(]?[A-ZÄÖÜ0-9])")


def split_long(sentence: str, limit: int) -> list[str]:
    """Teilt einen überlangen Satz an Satzzeichen (; : , –), notfalls an Leerzeichen."""
    if len(sentence) <= limit:
        return [sentence]
    for sep in ("; ", ": ", " – ", ", "):
        parts = sentence.split(sep)
        if len(parts) > 1:
            out, cur = [], ""
            for i, part in enumerate(parts):
                piece = part + (sep.rstrip() if i < len(parts) - 1 else "")
                if cur and len(cur) + 1 + len(piece) > limit:
                    out.append(cur)
                    cur = piece
                else:
                    cur = f"{cur} {piece}".strip()
            if cur:
                out.append(cur)
            if all(len(o) <= limit for o in out):
                return out
            return [x for o in out for x in split_long(o, limit)]
    words, out, cur = sentence.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > limit:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        out.append(cur)
    return out


def mit_satzzeichen(s: str) -> str:
    """Hängt einen Punkt an, wenn der Abschnitt ohne Satzschluss endet. Ohne Satzzeichen bricht
    das Modell kurze Texte gelegentlich mitten im letzten Laut ab."""
    s = s.rstrip()
    if not s or re.search(r"[.!?…][\"“”»«'’)]*$", s):
        return s
    if s[-1] in ",;:–-":
        s = s[:-1].rstrip()
    return s + "."


def paragraph_chunks(par: str, limit: int) -> list[str]:
    sentences = [s.strip() for s in SENT_END.sub(r"\1\n", par).split("\n") if s.strip()]
    pieces = [x for s in sentences for x in split_long(s, limit)]
    chunks, cur = [], ""
    for s in pieces:
        if cur and len(cur) + 1 + len(s) > limit:
            chunks.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        chunks.append(cur)
    return chunks


def parse_book(text: str, limit: int, default_title: str) -> list[Chapter]:
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    chapters: list[Chapter] = []
    current = Chapter(default_title, [])
    for b in blocks:
        if b.startswith("# "):
            if current.chunks:
                chapters.append(current)
            title = b[2:].strip()
            current = Chapter(title, [Chunk(expand_numbers(title) + ".", PAUSE_CHAPTER)])
            continue
        if b == "***":
            if current.chunks:
                current.chunks[-1].pause_after = PAUSE_SCENE
            continue
        if b.startswith("## "):
            if current.chunks:
                current.chunks[-1].pause_after = PAUSE_SCENE
            current.chunks.append(Chunk(expand_numbers(b[3:].strip()) + ".", PAUSE_CHAPTER))
            continue
        b = " ".join(b.split())
        cs = paragraph_chunks(b, limit)
        for i, c in enumerate(cs):
            last = i == len(cs) - 1
            current.chunks.append(Chunk(mit_satzzeichen(c) if last else c,
                                        PAUSE_PARAGRAPH if last else PAUSE_SENTENCE))
    if current.chunks:
        chapters.append(current)
    return chapters


def sample_paragraph(text: str) -> str:
    """Wählt einen Fließtextabsatz als Hörprobe (keine Überschrift, kein Szenenwechsel)."""
    paras = [" ".join(b.split()) for b in re.split(r"\n\s*\n", text)]
    paras = [b for b in paras if is_text_par(b)]
    for b in paras:
        if len(b) >= 250:
            return paragraph_chunks(b, MAX_CHUNK_CHARS)[0]
    if paras:   # kurze Absätze: den längsten nehmen
        return paragraph_chunks(max(paras, key=len), MAX_CHUNK_CHARS)[0]
    return " ".join(text.split())[:MAX_CHUNK_CHARS]
