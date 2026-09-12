"""
Einheitliche Suche über Notizen, Chat-Verläufe und Zusammenfassungen
=======================================================================
Bisher durchsuchte jede Seite nur ihren eigenen Bereich getrennt (Notizen-
Volltextsuche, Chat-BM25 gegen die Dokumente, ...) - "wo hab ich das nochmal
gesehen" blieb eine Ratefrage zwischen Notiz/Chat/Zusammenfassung. Bewusst
simple Substring-Suche (kein neuer Suchindex nötig) - Notizen und Chats sind
Nutzerinhalte in überschaubarer Menge, ein Scan reicht; Zusammenfassungen
liegen ohnehin nur als einzelne Markdown-Dateien unter docs/.
"""
from __future__ import annotations

from ragapp import manifest
from ragapp.config import PROJECT_ROOT

_MIN_QUERY_LEN = 2


def _snippet(text: str, query: str, radius: int = 60) -> str:
    """Kurzer Ausschnitt UM die erste Fundstelle herum - ein von vorne
    abgeschnittener Text wäre beim Überfliegen der Ergebnisse oft nutzlos
    (die Fundstelle könnte weit hinten im Dokument liegen)."""
    text = text or ""
    low = text.lower()
    idx = low.find(query.lower())
    if idx == -1:
        snippet = text[:radius * 2].strip()
        return snippet + ("…" if len(text) > radius * 2 else "")
    start = max(0, idx - radius)
    end = min(len(text), idx + len(query) + radius)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return prefix + " ".join(text[start:end].split()) + suffix


def search_notes(query: str, limit: int = 5) -> list[dict]:
    rows = manifest.list_notes(search=query, limit=limit)
    return [{
        "source": "notiz", "id": r["note_id"], "title": r.get("title") or "(ohne Titel)",
        "subject": r.get("subject"), "snippet": _snippet(r.get("body") or "", query),
    } for r in rows]


def search_chat_sessions(query: str, limit: int = 5) -> list[dict]:
    ql = query.lower()
    out: list[dict] = []
    for s in manifest.list_chat_sessions():
        hay = s["title"] + "\n" + "\n".join(
            str(m.get("content", "")) for m in (s.get("messages") or []))
        if ql in hay.lower():
            out.append({
                "source": "chat", "id": s["session_id"], "title": s["title"],
                "subject": None, "snippet": _snippet(hay, query),
            })
            if len(out) >= limit:
                break
    return out


def search_zusammenfassungen(query: str, limit: int = 5) -> list[dict]:
    ql = query.lower()
    out: list[dict] = []
    docs_dir = PROJECT_ROOT / "docs"
    if not docs_dir.is_dir():
        return out
    for path in sorted(docs_dir.glob("Zusammenfassung_*.md")):
        try:
            text = path.read_text("utf-8", errors="ignore")
        except OSError:
            continue
        if ql in text.lower() or ql in path.stem.lower():
            out.append({
                "source": "zusammenfassung", "id": path.name,
                "title": path.stem.replace("Zusammenfassung_", "").replace("_", " "),
                "subject": None, "snippet": _snippet(text, query),
            })
            if len(out) >= limit:
                break
    return out


def search_everything(query: str, limit_per_source: int = 5) -> dict[str, list[dict]]:
    """Sucht in Notizen, Chat-Verläufen und Zusammenfassungen gleichzeitig.
    Zu kurze Suchbegriffe (< 2 Zeichen) liefern bewusst nichts - sonst würde
    z. B. ein einzelner Buchstabe in fast jeder Notiz/jedem Chat "treffen"."""
    query = (query or "").strip()
    if len(query) < _MIN_QUERY_LEN:
        return {"notiz": [], "chat": [], "zusammenfassung": []}
    return {
        "notiz": search_notes(query, limit_per_source),
        "chat": search_chat_sessions(query, limit_per_source),
        "zusammenfassung": search_zusammenfassungen(query, limit_per_source),
    }
