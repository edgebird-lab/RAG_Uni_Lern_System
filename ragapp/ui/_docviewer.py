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
import re


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


_PARA_SPLIT = re.compile(r"\n\s*\n")
_HEADING_LINE = re.compile(r"^#{1,3}\s+(.+)$", re.M)


def page_text_len(path: "str | Path", page_num: int = 1) -> int:
    """Sichtbarer Text auf einer PDF-Seite (0 wenn kein PDF/Fehler)."""
    path = Path(path)
    if not path.is_file() or path.suffix.lower() != ".pdf":
        return 0
    try:
        import fitz
        doc = fitz.open(str(path))
        if page_num < 1 or page_num > doc.page_count:
            return 0
        text = (doc.load_page(page_num - 1).get_text("text") or "").strip()
        return len(text)
    except Exception:  # noqa: BLE001
        return 0


def toc_page_for_heading(path: "str | Path", heading: str) -> int:
    """1-basierte PDF-Seite zum Inhaltsverzeichnis-Titel, sonst 1."""
    needle = (heading or "").strip().lower()
    if not needle:
        return 1
    path = Path(path)
    if not path.is_file() or path.suffix.lower() != ".pdf":
        return 1
    try:
        import fitz
        doc = fitz.open(str(path))
        toc = doc.get_toc() or []
        doc.close()
    except Exception:  # noqa: BLE001
        return 1
    for _level, title, page in toc:
        name = (title or "").strip().lower()
        if not name:
            continue
        if needle in name or name in needle:
            return max(1, int(page or 1))
    return 1


def passages_on_page(path: "str | Path", page_num: int = 1, *,
                     heading: "str | None" = None, limit: int = 12,
                     min_chars: int = 24) -> list[dict]:
    """Tippbare Absätze einer Seite/eines Abschnitts – ohne LLM.

    PDF: Textblöcke der gerenderten Seite. Markdown/TXT: Absätze des
    aktuellen Überschriften-Abschnitts (sonst die ganze Datei).
    """
    path = Path(path)
    if not path.is_file():
        return []
    limit = max(1, min(int(limit), 20))
    min_chars = max(8, int(min_chars))
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _pdf_passages(path, page_num, limit=limit, min_chars=min_chars)
    text = load_full_text(path) or ""
    return _text_passages(text, heading=heading, limit=limit, min_chars=min_chars)


def _pdf_passages(path: Path, page_num: int, *, limit: int, min_chars: int) -> list[dict]:
    try:
        import fitz
        doc = fitz.open(str(path))
        if page_num < 1 or page_num > doc.page_count:
            return []
        blocks = doc.load_page(page_num - 1).get_text("blocks") or []
    except Exception:  # noqa: BLE001
        return []
    rows: list[tuple[float, str]] = []
    for blk in blocks:
        if not isinstance(blk, (list, tuple)) or len(blk) < 5:
            continue
        if len(blk) > 6 and int(blk[6] or 0) != 0:
            continue
        text = " ".join(str(blk[4] or "").split()).strip()
        if len(text) < min_chars:
            continue
        y0 = float(blk[1] or 0)
        rows.append((y0, text[:400]))
    rows.sort(key=lambda r: r[0])
    out: list[dict] = []
    seen: set[str] = set()
    for i, (_y, text) in enumerate(rows):
        key = text[:80].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"id": f"p{i}", "text": text, "page": int(page_num)})
        if len(out) >= limit:
            break
    return out


def _text_passages(text: str, *, heading: "str | None", limit: int,
                   min_chars: int) -> list[dict]:
    body = (text or "").strip()
    if not body:
        return []
    want = (heading or "").strip().lower()
    if want:
        matches = list(_HEADING_LINE.finditer(body))
        start = 0
        end = len(body)
        for i, m in enumerate(matches):
            title = (m.group(1) or "").strip().lower()
            if want in title or title in want:
                start = m.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
                break
        body = body[start:end].strip() or body
    paras = [p.strip() for p in _PARA_SPLIT.split(body) if len(p.strip()) >= min_chars]
    if not paras and len(body) >= min_chars:
        paras = [body[:400]]
    out: list[dict] = []
    for i, p in enumerate(paras[:limit]):
        out.append({"id": f"t{i}", "text": " ".join(p.split())[:400], "page": 1})
    return out
