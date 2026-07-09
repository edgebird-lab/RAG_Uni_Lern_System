"""
Lern-Layer: Karteikarten + Spaced Repetition (SM-2-lite)
========================================================
Verwandelt das ohnehin schon indexierte Fragenmaterial in echtes Klausurtraining
(Testing-Effekt + verteiltes Wiederholen), OHNE zur Laufzeit ein LLM/Embedding zu
brauchen - laeuft also sofort und offline auch auf schwacher Hardware.

Kartenquellen (aus ChromaDB geerntet):
  * ``kind='exam_qa'`` (Klausur-Lernkatalog): Frage + Schritt-fuer-Schritt-Antwort
    stecken bereits im Text (``FRAGE: … ERKLAERUNG (Vorgehen): …``) -> ideale Karten.
  * ``type='question'`` (generierte Fragen): Vorderseite = die Frage, Rueckseite =
    der zugehoerige Eltern-Chunk (``parent_id``).

Der Lernfortschritt (Faelligkeit, Leichtigkeit, Wiederholungen) liegt in
``manifest.db`` (Tabellen review_items/review_log). Die Planung macht ein
schlankes SM-2: gut -> laengeres Intervall, halb -> kuerzer, nicht gewusst ->
zurueck auf Anfang (kommt in derselben Sitzung erneut).
"""
from __future__ import annotations

import time

from ragapp import manifest
from ragapp.retrieval.vectorstore import get_vectorstore

# Bewertungen
NICHT, HALB, GEWUSST = 0, 1, 2

_ANSWER_MARKERS = ("ERKLÄRUNG (Vorgehen):", "ERKLÄRUNG:", "ERKLAERUNG (Vorgehen):",
                   "ERKLAERUNG:", "ANTWORT:")


def _parse_exam_qa(doc: str) -> tuple[str, str]:
    """Zerlegt einen exam_qa-Text in (Frage, Antwort). Leere Rueckseite -> ('','')."""
    if not doc or "FRAGE:" not in doc:
        return "", ""
    after = doc.split("FRAGE:", 1)[1]
    for marker in _ANSWER_MARKERS:
        if marker in after:
            frage, antwort = after.split(marker, 1)
            return frage.strip(), antwort.strip()
    return "", ""


def _topic(meta: dict) -> "str | None":
    t = meta.get("location") or meta.get("header_path")
    return str(t) if t else None


def harvest_cards(subject: "str | None" = None, progress=None) -> dict:
    """Erntet Karten aus dem Vektorstore und legt neue in manifest.db an.
    Vorhandene Karten behalten ihren Lernfortschritt. Gibt {gefunden, neu} zurueck."""
    store = get_vectorstore()
    col = store._col
    cards: list[dict] = []

    def _where(base: dict) -> dict:
        if subject:
            return {"$and": [base, {"subject": subject}]}
        return base

    # 1) Klausur-Q&A (beste Karten: Frage + Erklaerung schon vorhanden)
    if progress:
        progress("Suche Klausur-Q&A …")
    try:
        res = col.get(where=_where({"kind": "exam_qa"}), include=["documents", "metadatas"])
    except Exception:
        res = {"ids": [], "documents": [], "metadatas": []}
    for i, cid in enumerate(res.get("ids", [])):
        doc = res["documents"][i] or ""
        meta = res["metadatas"][i] or {}
        frage, antwort = _parse_exam_qa(doc)
        if frage and antwort:
            cards.append({
                "card_id": cid, "source": "exam_qa", "chroma_id": cid,
                "subject": meta.get("subject"), "topic": _topic(meta),
                "front": frage, "back": antwort, "doc_id": meta.get("doc_id"),
            })

    # 2) Generierte Fragen -> Rueckseite = Eltern-Chunk
    if progress:
        progress("Suche generierte Fragen …")
    try:
        resq = col.get(where=_where({"type": "question"}), include=["documents", "metadatas"])
    except Exception:
        resq = {"ids": [], "documents": [], "metadatas": []}
    parent_ids = sorted({(resq["metadatas"][i] or {}).get("parent_id")
                         for i in range(len(resq.get("ids", [])))
                         if (resq["metadatas"][i] or {}).get("parent_id")})
    parents = store.get_by_ids(parent_ids) if parent_ids else {}
    for i, cid in enumerate(resq.get("ids", [])):
        frage = (resq["documents"][i] or "").strip()
        meta = resq["metadatas"][i] or {}
        pid = meta.get("parent_id")
        back = (parents.get(pid, {}).get("document", "") or "").strip()
        if frage and back:
            cards.append({
                "card_id": cid, "source": "question", "chroma_id": cid,
                "subject": meta.get("subject"), "topic": _topic(meta),
                "front": frage, "back": back, "doc_id": meta.get("doc_id"),
            })

    if progress:
        progress(f"Speichere {len(cards)} Karten …")
    neu = manifest.upsert_review_items(cards)
    return {"gefunden": len(cards), "neu": neu}


def sm2_next(rating: int, ease: float, interval: int, reps: int,
             lapses: int, now: "float | None" = None) -> dict:
    """Schlankes SM-2: berechnet den naechsten Zustand aus der Bewertung.
    rating: 0=nicht gewusst, 1=halb, 2=gewusst."""
    now = now if now is not None else time.time()
    ease = ease if ease else 2.5
    if rating <= NICHT:
        # Zurueck auf Anfang; kommt in ~1 Min in derselben Sitzung erneut.
        return {"ease": max(1.3, ease - 0.20), "interval": 0, "reps": 0,
                "lapses": lapses + 1, "due": now + 60}
    if rating == HALB:
        ease = max(1.3, ease - 0.15)
    else:  # GEWUSST
        ease = min(2.8, ease + 0.05)
    reps += 1
    if reps == 1:
        interval = 1
    elif reps == 2:
        interval = 3 if rating >= GEWUSST else 2
    else:
        factor = ease * (0.6 if rating == HALB else 1.0)
        interval = max(1, round(interval * factor))
    return {"ease": round(ease, 3), "interval": int(interval), "reps": reps,
            "lapses": lapses, "due": now + interval * 86400}


def rate_card(card: dict, rating: int) -> dict:
    """Wendet SM-2 auf eine Karte an, persistiert den neuen Zustand + Log-Eintrag.
    Gibt den neuen Zustand zurueck (fuer evtl. Wiedervorlage in der Sitzung)."""
    nxt = sm2_next(rating, card.get("ease", 2.5), card.get("interval", 0),
                   card.get("reps", 0), card.get("lapses", 0))
    manifest.record_review(
        card["card_id"], rating, ease=nxt["ease"], interval=nxt["interval"],
        reps=nxt["reps"], lapses=nxt["lapses"], due=nxt["due"],
        subject=card.get("subject"), topic=card.get("topic"),
    )
    return nxt


def humanize_interval(days: int) -> str:
    if days <= 0:
        return "gleich nochmal"
    if days == 1:
        return "morgen"
    if days < 30:
        return f"in {days} Tagen"
    if days < 365:
        return f"in {round(days / 30)} Monaten"
    return f"in {round(days / 365, 1)} Jahren"
