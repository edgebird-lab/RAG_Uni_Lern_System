"""
Struktur-bewusstes Chunking (Slicing)
=====================================

Ziel: Chunks, die *thematisch geschlossen* sind, das ist der wichtigste Hebel
für die Trefferquote. Zwei Strategien:

* **Markdown** wird an den Überschriften (``#``, ``##``, ``###`` …) geschnitten.
  Jeder Chunk trägt seinen Überschriften-Pfad als Kontext mit (z. B.
  "TEIL I › Kostenartenrechnung › Kostenspaltung"). Zu große Abschnitte werden
  rekursiv weiter zerlegt, kleine benachbarte Abschnitte zusammengefasst.

* **PDF/DOCX/PPTX** werden pro Seite/Folie rekursiv an natürlichen Grenzen
  (Absätze › Zeilen › Sätze › Wörter) mit Überlappung geschnitten. Jeder Chunk
  behält seine Seitennummer für exakte Quellenangaben.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ragapp.config import settings
from ragapp.ingestion.loaders import LoadedDoc


@dataclass
class Chunk:
    text: str
    meta: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Rekursiver Zeichen-Splitter (mit Überlappung)
# --------------------------------------------------------------------------- #
_SEPARATORS = ["\n\n", "\n", ". ", "; ", ", ", " ", ""]


def _split_recursive(text: str, size: int, overlap: int) -> list[str]:
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []

    # kleinste passende Trenn-Ebene finden
    for sep in _SEPARATORS:
        if sep == "":
            # harte Zeichen-Grenze; Schrittweite gegen 0/negativ absichern
            step = max(1, size - overlap)
            pieces = [text[i:i + size] for i in range(0, len(text), step)]
            return [p for p in pieces if p.strip()]
        parts = text.split(sep)
        if len(parts) == 1:
            continue
        # Teile zu Chunks nahe der Zielgröße zusammenbauen
        chunks: list[str] = []
        current = ""
        for part in parts:
            candidate = part if not current else current + sep + part
            if len(candidate) <= size:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                # Teil selbst zu groß? rekursiv weiter zerlegen
                if len(part) > size:
                    chunks.extend(_split_recursive(part, size, overlap))
                    current = ""
                else:
                    current = part
        if current:
            chunks.append(current)
        # Überlappung zwischen aufeinanderfolgenden Chunks herstellen
        return _apply_overlap(chunks, overlap)
    return [text]


def _apply_overlap(chunks: list[str], overlap: int) -> list[str]:
    if overlap <= 0 or len(chunks) <= 1:
        return chunks
    out = [chunks[0]]
    for i in range(1, len(chunks)):
        prev_tail = chunks[i - 1][-overlap:]
        out.append((prev_tail + " " + chunks[i]).strip())
    return out


# --------------------------------------------------------------------------- #
# Markdown-Header-Splitting
# --------------------------------------------------------------------------- #
_HEADER_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def _split_markdown_sections(text: str) -> list[tuple[str, str]]:
    """Zerlegt Markdown in (header_pfad, abschnittstext)."""
    lines = text.split("\n")
    sections: list[tuple[str, str]] = []
    header_stack: list[tuple[int, str]] = []  # (level, title)
    buffer: list[str] = []

    def header_path() -> str:
        return " › ".join(title for _, title in header_stack)

    def flush():
        body = "\n".join(buffer).strip()
        if body:
            sections.append((header_path(), body))

    for line in lines:
        m = _HEADER_RE.match(line.strip())
        if m:
            flush()
            buffer = []
            level = len(m.group(1))
            title = m.group(2).strip()
            # Stack auf passendes Level zurücksetzen
            header_stack = [(lvl, t) for lvl, t in header_stack if lvl < level]
            header_stack.append((level, title))
        else:
            buffer.append(line)
    flush()
    return sections if sections else [("", text.strip())]


# --------------------------------------------------------------------------- #
# Öffentliche Chunking-Funktion
# --------------------------------------------------------------------------- #
def chunk_document(loaded: LoadedDoc, base_meta: dict) -> list[Chunk]:
    size = settings.CHUNK_SIZE
    overlap = settings.CHUNK_OVERLAP
    min_chars = settings.MIN_CHUNK_CHARS
    chunks: list[Chunk] = []

    if loaded.is_markdown and settings.RESPECT_MARKDOWN_HEADERS:
        for header_path, body in _split_markdown_sections(loaded.text):
            # Header-Pfad dem Chunk-Text voranstellen -> besserer semantischer Anker
            prefix = f"[{header_path}]\n" if header_path else ""
            for piece in _split_recursive(body, size, overlap):
                text = (prefix + piece).strip()
                meta = dict(base_meta)
                meta["header_path"] = header_path
                meta["location"] = header_path or "Dokument"
                chunks.append(Chunk(text=text, meta=meta))
    else:
        # Seiten-/Blockweise (PDF, DOCX, PPTX, TXT)
        for block in loaded.blocks:
            for piece in _split_recursive(block.text, size, overlap):
                meta = dict(base_meta)
                if block.page is not None:
                    label = "Folie" if block.kind == "slide" else "Seite"
                    meta["page"] = block.page
                    meta["location"] = f"{label} {block.page}"
                else:
                    meta["location"] = "Dokument"
                chunks.append(Chunk(text=piece, meta=meta))

    # Zu kleine Chunks mit dem vorherigen zusammenführen (Rauschen reduzieren)
    merged = _merge_small(chunks, min_chars)

    # Chunk-Index vergeben
    for i, ch in enumerate(merged):
        ch.meta["chunk_index"] = i
    return merged


def _merge_small(chunks: list[Chunk], min_chars: int) -> list[Chunk]:
    if not chunks:
        return chunks
    out: list[Chunk] = []
    for ch in chunks:
        if out and len(ch.text) < min_chars and ch.meta.get("location") == out[-1].meta.get("location"):
            out[-1].text = (out[-1].text + "\n" + ch.text).strip()
        else:
            out.append(ch)
    return out
