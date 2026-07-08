"""
Dokument-Loader
===============

Extrahiert reinen Text (inkl. Struktur-Metadaten) aus verschiedenen Formaten:

    .pdf          -> PyMuPDF (fitz), Fallback pypdf; Text pro Seite
    .md / .txt    -> direkt (Markdown behält Überschriften-Struktur)
    .docx         -> python-docx
    .pptx         -> python-pptx (Text pro Folie)

Rückgabe: ``LoadedDoc`` mit
    * text   – vollständiger, normalisierter Text
    * blocks – Liste von Textblöcken mit Metadaten (Seite/Folie), damit der
               Chunker Quellenangaben wie "Seite 4" anhängen kann.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

SUPPORTED_EXTENSIONS = {".pdf", ".md", ".txt", ".markdown", ".docx", ".pptx"}


@dataclass
class Block:
    text: str
    page: int | None = None      # Seiten-/Foliennummer, falls vorhanden
    kind: str = "text"


@dataclass
class LoadedDoc:
    text: str
    blocks: list[Block]
    filetype: str
    is_markdown: bool = False
    meta: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Normalisierung
# --------------------------------------------------------------------------- #
def normalize_text(text: str) -> str:
    """Vereinheitlicht Whitespace/Unicode – wichtig für stabile Hashes & Dedup."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # häufige PDF-Artefakte: harte Trennstriche am Zeilenende zusammenfügen
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    # überzählige Leerzeichen
    text = re.sub(r"[ \t]+", " ", text)
    # mehr als 2 Leerzeilen -> 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# --------------------------------------------------------------------------- #
# Format-spezifische Loader
# --------------------------------------------------------------------------- #
def _load_pdf(path: Path) -> LoadedDoc:
    blocks: list[Block] = []
    text_parts: list[str] = []
    try:
        import fitz  # PyMuPDF

        with fitz.open(str(path)) as doc:
            for i, page in enumerate(doc, start=1):
                raw = page.get_text("text") or ""
                norm = normalize_text(raw)
                if norm:
                    blocks.append(Block(text=norm, page=i, kind="page"))
                    text_parts.append(norm)
    except Exception as exc:  # Fallback auf pypdf
        # evtl. schon teilbefüllte fitz-Ergebnisse verwerfen -> keine Seiten-Duplikate
        blocks, text_parts = [], []
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            for i, page in enumerate(reader.pages, start=1):
                norm = normalize_text(page.extract_text() or "")
                if norm:
                    blocks.append(Block(text=norm, page=i, kind="page"))
                    text_parts.append(norm)
        except Exception as exc2:
            raise RuntimeError(f"PDF konnte nicht gelesen werden: {exc} / {exc2}")
    return LoadedDoc(
        text="\n\n".join(text_parts),
        blocks=blocks,
        filetype="pdf",
        is_markdown=False,
        meta={"pages": len(blocks)},
    )


def _load_markdown(path: Path) -> LoadedDoc:
    raw = path.read_text(encoding="utf-8", errors="replace")
    # optionales YAML-Frontmatter entfernen (Metadaten)
    fm_meta: dict = {}
    try:
        import frontmatter

        post = frontmatter.loads(raw)
        fm_meta = dict(post.metadata)
        raw = post.content
    except Exception:
        pass
    norm = normalize_text(raw)
    return LoadedDoc(
        text=norm,
        blocks=[Block(text=norm, page=None, kind="markdown")],
        filetype="md",
        is_markdown=True,
        meta=fm_meta,
    )


def _load_txt(path: Path) -> LoadedDoc:
    norm = normalize_text(path.read_text(encoding="utf-8", errors="replace"))
    return LoadedDoc(
        text=norm, blocks=[Block(text=norm, kind="text")], filetype="txt"
    )


def _load_docx(path: Path) -> LoadedDoc:
    from docx import Document

    doc = Document(str(path))
    paras = [p.text for p in doc.paragraphs if p.text.strip()]
    # Tabellen ebenfalls erfassen
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                paras.append(" | ".join(cells))
    norm = normalize_text("\n".join(paras))
    return LoadedDoc(
        text=norm, blocks=[Block(text=norm, kind="text")], filetype="docx"
    )


def _load_pptx(path: Path) -> LoadedDoc:
    from pptx import Presentation

    prs = Presentation(str(path))
    blocks: list[Block] = []
    parts: list[str] = []
    for i, slide in enumerate(prs.slides, start=1):
        texts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    line = "".join(run.text for run in para.runs)
                    if line.strip():
                        texts.append(line)
        norm = normalize_text("\n".join(texts))
        if norm:
            blocks.append(Block(text=norm, page=i, kind="slide"))
            parts.append(norm)
    return LoadedDoc(
        text="\n\n".join(parts), blocks=blocks, filetype="pptx",
        meta={"slides": len(blocks)},
    )


_LOADERS = {
    ".pdf": _load_pdf,
    ".md": _load_markdown,
    ".markdown": _load_markdown,
    ".txt": _load_txt,
    ".docx": _load_docx,
    ".pptx": _load_pptx,
}


def load_document(path: str | Path) -> LoadedDoc:
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in _LOADERS:
        raise ValueError(f"Nicht unterstütztes Format: {ext} ({path.name})")
    return _LOADERS[ext](path)
