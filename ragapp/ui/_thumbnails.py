"""
Vorschaubilder fuer den Dokumentenmanager
==========================================
Kleine Kachel-Vorschau je Dokument: bei PDFs ein echtes Thumbnail (erste Seite,
niedrige Aufloesung); alle anderen Dateitypen bekommen in der Oberflaeche ein
generisches Icon (bewusst kein neuer Renderer/Abhaengigkeit fuer docx/pptx/md/txt).
Auf Platte zwischengespeichert (``data/thumbnails/``), damit 100+ Dokumente nicht
bei jedem Seitenaufruf neu gerendert werden.
"""
from __future__ import annotations

from ragapp.config import DATA_DIR, PROJECT_ROOT
from ragapp.ui import _docviewer

THUMB_DIR = DATA_DIR / "thumbnails"
THUMB_DPI = 45  # klein genug fuer eine Kachel, schnell zu rendern


def get_thumbnail(doc: dict) -> "bytes | None":
    """PNG-Vorschau (erste Seite) fuer ein Dokument aus ``manifest.list_documents()``.
    Nur fuer PDFs; sonst ``None`` (die UI zeigt dann ein generisches Icon). Wird
    einmalig gerendert und auf Platte zwischengespeichert; ein neuerer
    ``updated_at`` (Re-Ingest mit geaendertem Inhalt) erzwingt eine frische Vorschau."""
    if (doc.get("filetype") or "").lower() != "pdf":
        return None
    doc_id = doc.get("doc_id")
    if not doc_id:
        return None
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    thumb_path = THUMB_DIR / f"{doc_id}.png"
    try:
        if thumb_path.is_file():
            if thumb_path.stat().st_mtime >= float(doc.get("updated_at") or 0):
                return thumb_path.read_bytes()
    except OSError:
        pass

    path = PROJECT_ROOT / (doc.get("source_path") or "")
    png = _docviewer.render_pdf_page(path, 1, dpi=THUMB_DPI)
    if png:
        try:
            thumb_path.write_bytes(png)
        except OSError:
            pass
    return png


def get_text_preview(doc: dict, max_chars: int = 260) -> "str | None":
    """Kurzer Text-Ausschnitt fuer die Kachel-Vorschau bei Markdown/Text-Dokumenten
    (fuer PDFs gibt es stattdessen ein echtes Thumbnail, siehe ``get_thumbnail``).
    Bei ``.md`` bewusst UNGEKUERZTES Markdown zurueckgeben, damit die Oberflaeche es
    echt gerendert zeigen kann (Ueberschriften/Fett bleiben sichtbar) - kein neuer
    Renderer noetig, Streamlit kann das schon."""
    if (doc.get("filetype") or "").lower() not in ("md", "txt"):
        return None
    path = PROJECT_ROOT / (doc.get("source_path") or "")
    full = _docviewer.load_full_text(path)
    if not full:
        return None
    text = full.strip()
    return text[:max_chars] + ("…" if len(text) > max_chars else "")
