"""
Dokument-Loader
===============

Extrahiert reinen Text (inkl. Struktur-Metadaten) aus verschiedenen Formaten:

    .pdf          -> PyMuPDF (fitz), Fallback pypdf; Text pro Seite
    .md / .txt    -> direkt (Markdown behält Überschriften-Struktur)
    .docx         -> python-docx
    .pptx         -> python-pptx (Text pro Folie)

Rückgabe: ``LoadedDoc`` mit
    * text   : vollständiger, normalisierter Text
    * blocks : Liste von Textblöcken mit Metadaten (Seite/Folie), damit der
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
    """Vereinheitlicht Whitespace/Unicode, wichtig für stabile Hashes & Dedup."""
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
_EASYOCR_READER = None
_EASYOCR_TRIED = False


def _get_easyocr():
    """Gibt einen (gecachten) easyocr-Reader (dt.+engl.) zurueck oder None. Bevorzugt
    die GPU (ROCm/CUDA), faellt auf CPU zurueck. Modelle werden beim ersten Mal geladen."""
    global _EASYOCR_READER, _EASYOCR_TRIED
    if _EASYOCR_TRIED:
        return _EASYOCR_READER
    _EASYOCR_TRIED = True
    try:
        import easyocr
        try:
            _EASYOCR_READER = easyocr.Reader(["de", "en"], gpu=True)
        except Exception:  # noqa: BLE001 - GPU evtl. nicht nutzbar -> CPU
            _EASYOCR_READER = easyocr.Reader(["de", "en"], gpu=False)
    except Exception:  # noqa: BLE001 - easyocr nicht installiert
        _EASYOCR_READER = None
    return _EASYOCR_READER


def _ocr_page(page) -> str:
    """OCR einer text-losen PDF-Seite (Scan/Bild). Nutzt easyocr (GPU, dt.+engl.);
    faellt auf pytesseract/Tesseract zurueck. '' wenn kein OCR verfuegbar ist."""
    try:
        png = page.get_pixmap(dpi=200).tobytes("png")
    except Exception:  # noqa: BLE001
        return ""
    reader = _get_easyocr()
    if reader is not None:
        try:
            import io
            import numpy as np
            from PIL import Image
            arr = np.array(Image.open(io.BytesIO(png)).convert("RGB"))
            lines = reader.readtext(arr, detail=0, paragraph=True)
            return "\n".join(str(x) for x in lines)
        except Exception:  # noqa: BLE001
            pass
    try:  # Fallback: pytesseract (falls jemand Tesseract installiert hat)
        import io
        import pytesseract
        from PIL import Image
        img = Image.open(io.BytesIO(png))
        try:
            return pytesseract.image_to_string(img, lang="deu") or ""
        except Exception:  # noqa: BLE001
            return pytesseract.image_to_string(img) or ""
    except Exception:  # noqa: BLE001
        return ""


def _load_pdf(path: Path) -> LoadedDoc:
    blocks: list[Block] = []
    text_parts: list[str] = []
    try:
        import fitz  # PyMuPDF

        with fitz.open(str(path)) as doc:
            for i, page in enumerate(doc, start=1):
                raw = page.get_text("text") or ""
                norm = normalize_text(raw)
                if not norm:
                    # Keine Textebene -> vermutlich Scan/Bild -> OCR versuchen.
                    norm = normalize_text(_ocr_page(page))
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


def _table_to_md(rows: list) -> str:
    """Wandelt eine Tabelle (Liste von Zeilen mit Zellen) in eine Markdown-Tabelle -
    so bleiben Zeilen/Spalten-Beziehungen (Pro/Contra, Klassifikationen, Kennzahlen)
    erhalten, statt zu Zeichenbrei zu kollabieren."""
    clean = [[str(c).replace("\n", " ").replace("|", "/").strip() for c in r]
             for r in rows if any(str(c).strip() for c in r)]
    if not clean:
        return ""
    ncol = max(len(r) for r in clean)
    clean = [r + [""] * (ncol - len(r)) for r in clean]
    out = ["| " + " | ".join(clean[0]) + " |",
           "| " + " | ".join(["---"] * ncol) + " |"]
    for r in clean[1:]:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def _load_docx(path: Path) -> LoadedDoc:
    from docx import Document

    doc = Document(str(path))
    paras = [p.text for p in doc.paragraphs if p.text.strip()]
    # Tabellen als Markdown erfassen (Struktur bleibt erhalten)
    for table in doc.tables:
        md = _table_to_md([[c.text for c in row.cells] for row in table.rows])
        if md:
            paras.append(md)
    norm = normalize_text("\n".join(paras))
    return LoadedDoc(
        text=norm, blocks=[Block(text=norm, kind="text")], filetype="docx"
    )


def _iter_pptx_shapes(shapes):
    """Iteriert Folien-Shapes rekursiv - auch in Gruppen/SmartArt (die sonst
    komplett verloren gingen)."""
    for shape in shapes:
        yield shape
        if hasattr(shape, "shapes"):          # GroupShape
            try:
                yield from _iter_pptx_shapes(shape.shapes)
            except Exception:  # noqa: BLE001
                pass


def _load_pptx(path: Path) -> LoadedDoc:
    from pptx import Presentation

    prs = Presentation(str(path))
    blocks: list[Block] = []
    parts: list[str] = []
    for i, slide in enumerate(prs.slides, start=1):
        texts: list[str] = []
        for shape in _iter_pptx_shapes(slide.shapes):
            if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    line = "".join(run.text for run in para.runs)
                    if line.strip():
                        texts.append(line)
            if getattr(shape, "has_table", False) and shape.has_table:
                md = _table_to_md([[c.text for c in row.cells] for row in shape.table.rows])
                if md:
                    texts.append(md)
        # Sprechernotizen: oft die AUSFORMULIERTE Erklaerung, die die knappe Folie
        # nur andeutet - bisher komplett verworfen.
        try:
            if slide.has_notes_slide:
                notes = (slide.notes_slide.notes_text_frame.text or "").strip()
                if notes:
                    texts.append("Notizen: " + notes)
        except Exception:  # noqa: BLE001
            pass
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
