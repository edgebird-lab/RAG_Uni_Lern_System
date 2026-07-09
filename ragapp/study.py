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


def harvest_cards(subject: "str | None" = None, max_per_chunk: "int | None" = None,
                  progress=None) -> dict:
    """Erntet Karten aus dem Vektorstore und legt neue in manifest.db an.
    Vorhandene Karten behalten ihren Lernfortschritt. Optional nur ein ``subject`` und
    hoechstens ``max_per_chunk`` Fragen je Eltern-Chunk (verhindert zu viele aehnliche
    Karten). Gibt {gefunden, neu} zurueck."""
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
                # Bei Klausur-Q&A ist die Erklaerung die echte Antwort -> als 'answer'
                # setzen (die Anzeige nutzt bevorzugt 'answer').
                "front": frage, "back": antwort, "answer": antwort,
                "doc_id": meta.get("doc_id"),
            })

    # 2) Generierte Fragen -> Rueckseite = Eltern-Chunk (Beleg); Antwort ggf. aus dem
    #    Enrichment (Metadaten-Feld 'answer'), sonst spaeter per KI nachziehbar.
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
    per_parent: dict = {}
    for i, cid in enumerate(resq.get("ids", [])):
        frage = (resq["documents"][i] or "").strip()
        meta = resq["metadatas"][i] or {}
        pid = meta.get("parent_id")
        if max_per_chunk:
            used = per_parent.get(pid, 0)
            if used >= max_per_chunk:
                continue
        back = (parents.get(pid, {}).get("document", "") or "").strip()
        if frage and back:
            per_parent[pid] = per_parent.get(pid, 0) + 1
            cards.append({
                "card_id": cid, "source": "question", "chroma_id": cid,
                "subject": meta.get("subject"), "topic": _topic(meta),
                "front": frage, "back": back,
                "answer": (meta.get("answer") or "").strip() or None,
                "doc_id": meta.get("doc_id"),
            })

    if progress:
        progress(f"Speichere {len(cards)} Karten …")
    neu = manifest.upsert_review_items(cards)
    return {"gefunden": len(cards), "neu": neu}


def generate_answers(subject: "str | None" = None, deck: "str | None" = None,
                     limit: "int | None" = None, card_ids: "list[str] | None" = None,
                     progress=None) -> dict:
    """Erzeugt fuer Karten aus generierten Fragen, die bisher nur den Chunk zeigen, eine
    echte KI-Musterloesung und speichert sie. Mit ``card_ids`` gezielt fuer eine Auswahl.
    Ehrliches Ergebnis (status/filled/errors)."""
    from ragapp.config import settings
    from ragapp.hardware import probe_model
    from ragapp.ingestion.question_gen import generate_answer, QuestionGenError

    if card_ids:
        todo = [c for c in manifest.get_cards_by_ids(card_ids)
                if c.get("source") == "question" and not (c.get("answer") or "").strip()]
        if limit:
            todo = todo[:limit]
    else:
        todo = manifest.cards_needing_answer(subject=subject, deck=deck, limit=limit)
    if not todo:
        return {"status": "nothing_to_do", "processed": 0, "filled": 0,
                "errors": 0, "error_msg": None}

    ok, msg = probe_model(settings.LLM_MODEL_FAST)
    if not ok:
        return {"status": "llm_error", "processed": 0, "filled": 0, "errors": 0,
                "error_msg": f"Modell '{settings.LLM_MODEL_FAST}' laeuft nicht: {msg}"}

    filled = errors = 0
    error_msg = None
    for i, card in enumerate(todo, 1):
        if progress:
            progress(f"Antwort {i}/{len(todo)} · {(card.get('front') or '')[:50]} …")
        try:
            ans = generate_answer(card.get("back") or "", card.get("front") or "")
        except QuestionGenError as exc:
            errors += 1
            if error_msg is None:
                error_msg = str(exc)
            if errors >= 3 and filled == 0:      # Fail-fast statt endlos ins Leere
                return {"status": "llm_error", "processed": i, "filled": filled,
                        "errors": errors, "error_msg": error_msg}
            continue
        if ans:
            manifest.set_answer(card["card_id"], ans)
            filled += 1

    status = "ok" if filled > 0 else ("llm_error" if errors else "empty")
    return {"status": status, "processed": len(todo), "filled": filled,
            "errors": errors, "error_msg": error_msg}


def apply_embedding_flags(card_ids: "list[str]", progress=None) -> dict:
    """Gleicht den Vektorindex an die Karten-Einstellung ``use_embedding`` an:
    ausgeschaltet -> die zugehoerige Frage aus dem Index entfernen; eingeschaltet ->
    (falls fehlt) neu einbetten. Gibt {removed, added} zurueck."""
    if not card_ids:
        return {"removed": 0, "added": 0}
    store = get_vectorstore()
    cards = manifest.get_cards_by_ids(card_ids)
    present = store.get_by_ids([c["chroma_id"] for c in cards if c.get("chroma_id")])
    removed = added = 0
    embedder = None
    for c in cards:
        cid = c.get("chroma_id")
        if not cid:
            continue
        want = bool(c.get("use_embedding", 1))
        exists = cid in present
        if not want and exists:
            store.delete_by_ids([cid]); removed += 1
        elif want and not exists:
            if embedder is None:
                from ragapp.retrieval.embeddings import get_embedder
                embedder = get_embedder()
            if c.get("source") == "question":
                text = c.get("front") or ""
                parent = cid.rsplit("::", 1)[0]
                meta = {"type": "question", "parent_id": parent,
                        "subject": c.get("subject"), "doc_id": c.get("doc_id")}
                if c.get("answer"):
                    meta["answer"] = c["answer"]
            else:  # exam_qa: Frage + Erklaerung wiederherstellen
                text = f"FRAGE: {c.get('front','')}\nERKLÄRUNG (Vorgehen): {c.get('answer') or c.get('back','')}"
                meta = {"kind": "exam_qa", "subject": c.get("subject"), "doc_id": c.get("doc_id")}
            if text.strip():
                try:
                    emb = embedder.embed_texts([text])[0]
                    store.add([cid], [emb], [text], [meta]); added += 1
                except Exception:  # noqa: BLE001
                    pass
    return {"removed": removed, "added": added}


def sm2_next(rating: int, ease: float, interval: int, reps: int,
             lapses: int, now: "float | None" = None) -> dict:
    """Konfigurierbarer Wiederholungs-Planer (SM-2/Anki-Stil). Intervalle, Ease-Schritte
    und die GEWUSST-Leiter kommen aus den Einstellungen (SRS_*), damit der Nutzer die
    Abstaende frei tunen kann. ``interval`` ist die Zahl der TAGE (0 = noch in kurzen
    Minuten-Schritten); ``due`` ist der naechste Faelligkeits-Zeitpunkt.
    rating: 0=nicht gewusst, 1=halb, 2=gewusst."""
    from ragapp.config import settings as S
    now = now if now is not None else time.time()
    ease = ease if ease else S.SRS_EASE_START
    steps = [float(m) for m in (S.SRS_GOOD_STEPS_MIN or (1440,)) if float(m) > 0] or [1440.0]
    emin, emax = S.SRS_EASE_MIN, S.SRS_EASE_MAX

    if rating <= NICHT:
        # Zurueck auf Anfang; kurzer Relearn-Schritt (Standard 2 min).
        return {"ease": round(max(emin, ease + S.SRS_EASE_AGAIN), 3), "interval": 0,
                "reps": 0, "lapses": lapses + 1, "due": now + S.SRS_AGAIN_MINUTES * 60}
    if rating == HALB:
        # Kurzer Relearn (Standard 10 min); Stufe und Reps bleiben erhalten.
        return {"ease": round(max(emin, ease + S.SRS_EASE_HALF), 3), "interval": interval,
                "reps": reps, "lapses": lapses, "due": now + S.SRS_HALF_MINUTES * 60}
    # GEWUSST: eine Stufe hoch auf der Leiter; jenseits der Leiter x Ease.
    ease = min(emax, ease + S.SRS_EASE_GOOD)
    reps += 1
    if reps <= len(steps):
        minutes = steps[reps - 1]
    else:
        # Wachstum aus dem ZULETZT tatsaechlich gesetzten Abstand (in Minuten),
        # NICHT aus dem auf ganze Tage gerundeten interval - sonst frieren kurze
        # Leitern (letzte Stufe < ~1 Tag) fuer immer ein.
        base = max(float(interval) * 1440.0, steps[-1])
        minutes = base * ease * max(0.1, S.SRS_INTERVAL_FACTOR)
    # interval als echte Tage (auch < 1) speichern -> das Wachstum jenseits der Leiter
    # kann sich aufbauen, selbst wenn eine Stufe unter einem Tag liegt.
    interval_days = round(minutes / 1440.0, 4)
    return {"ease": round(ease, 3), "interval": interval_days, "reps": reps,
            "lapses": lapses, "due": now + minutes * 60}


def humanize_due(due: float, now: "float | None" = None) -> str:
    """Menschliche Beschreibung des Abstands bis zur naechsten Faelligkeit."""
    now = now if now is not None else time.time()
    sec = max(0.0, float(due) - now)
    if sec < 90:
        return "in ~1 Minute"
    if sec < 3600:
        return f"in {round(sec / 60)} Minuten"
    if sec < 2 * 86400:
        h = sec / 3600
        return "morgen" if h >= 20 else f"in {round(h)} Stunden"
    d = sec / 86400
    if d < 30:
        return f"in {round(d)} Tagen"
    if d < 365:
        return f"in {round(d / 30)} Monaten"
    return f"in {round(d / 365, 1)} Jahren"


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
