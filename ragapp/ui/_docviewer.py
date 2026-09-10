"""
Dokument-Viewer (geteilte Bausteine)
=====================================
Gemeinsame Grundlage fuer die Quellenanzeige im Chat (Beleg-Highlight) und den
Dokumentenmanager (einfaches Ansehen/Blaettern/Vorschau). PDF-Seiten werden als
Bild gerendert (Layout/Formeln/Diagramme bleiben lesbar), alles Weitere als
Volltext. CPU-only, offline (fitz/PyMuPDF, bereits Abhaengigkeit der Loader).
"""
from __future__ import annotations

from pathlib import Path


def load_full_text(path: "str | Path") -> "str | None":
    """Volltext einer Originaldatei laden (ueber die bestehenden Loader)."""
    path = Path(path)
    if not path.is_file():
        return None
    try:
        from ragapp.ingestion.loaders import load_document
        return load_document(path).text
    except Exception:  # noqa: BLE001
        return None


def locate(full: str, needle: str) -> "tuple[int, int]":
    """Textstelle im Volltext finden - robust auch bei Markdown (ein Chunk hat dort
    einen Breadcrumb-Praefix, der so nicht im Original steht). (-1, -1), wenn nichts
    gefunden wurde."""
    if needle:
        i = full.find(needle[:200])
        if i >= 0:
            return i, min(i + len(needle), len(full))
    cands = sorted((ln.strip() for ln in (needle or "").split("\n") if len(ln.strip()) >= 20),
                   key=len, reverse=True)
    for c in cands[:10]:
        i = full.find(c)
        if i >= 0:
            return i, min(i + len(needle), len(full))
    return -1, -1


def pdf_page_count(path: "str | Path") -> int:
    """Seitenzahl eines PDFs (0 bei Fehler/kein lesbares PDF)."""
    path = Path(path)
    if not path.is_file():
        return 0
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(path))
        return doc.page_count
    except Exception:  # noqa: BLE001
        return 0


def render_pdf_page(path: "str | Path", page_num: int,
                    highlight_text: "str | None" = None, dpi: int = 140) -> "bytes | None":
    """Rendert eine PDF-Seite als PNG-Bild. ``highlight_text`` markiert optional dessen
    laengste Zeilen darin (Beleg-Highlight im Chat); ohne Angabe ein unmarkiertes Bild
    (Dokumentenmanager-Vorschau). Gibt ``None`` bei Fehler/ungueltiger Seite zurueck."""
    path = Path(path)
    if not path.is_file():
        return None
    try:
        import fitz  # PyMuPDF (bereits Abhaengigkeit der Loader)
        doc = fitz.open(str(path))
        if page_num < 1 or page_num > doc.page_count:
            return None
        page = doc.load_page(page_num - 1)
        if highlight_text:
            anchors = sorted((ln.strip() for ln in highlight_text.split("\n")
                              if len(ln.strip()) >= 15), key=len, reverse=True)[:6]
            for a in anchors:
                try:
                    for rect in page.search_for(a[:90]):
                        page.add_highlight_annot(rect)
                except Exception:  # noqa: BLE001
                    pass
        return page.get_pixmap(dpi=dpi).tobytes("png")
    except Exception:  # noqa: BLE001
        return None
