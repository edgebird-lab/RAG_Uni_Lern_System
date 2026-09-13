"""
Alltags-Hilfen für Studenten (ohne extra LLM-Zwang)
===================================================
Heute-Session, Vorlesung einfangen, Fehlerheft, Karten aus Text, Klausur-
Countdown. Rein deterministisch, damit Tests und Offline-Alltag greifen.
"""
from __future__ import annotations

import hashlib
import re
import time
from datetime import date, timedelta
from typing import Optional

from ragapp import manifest, planner
from ragapp.manifest import FEHLERHEFT_DECK

# Formel-Sprint: Karten, die wirklich nach Formel/Rechnung aussehen – nicht
# jede kurze Vorderseite. LaTeX und Rechenzeichen zaehlen staerker als Laenge.
_LATEX_RE = re.compile(
    r"\$[^$]+\$|\\\(|\\\[|\\begin\{|\\frac|\\sum|\\int|\\lim|\\vec|"
    r"\\mathbb|\\mathrm|\\partial|\\cdot")
_FORMULA_SYM_RE = re.compile(r"[=∑∫√±≤≥≈∞∂∇]|\\[a-zA-Z]+")
_FORMULA_WORD_RE = re.compile(
    r"(?i)\b(formel|gleichung|ableitung|integral|matrix|determinante|"
    r"eigenwert|eigenvektor|vektorraum|stetig|limes|konvergenz|"
    r"differential|gradient)\b")

_HEADING_RE = re.compile(r"^#{1,3}\s+(.+)$", re.M)
_DEF_RE = re.compile(
    r"^\s*(?:\*\*|__)?([^*_\n:]{2,80})(?:\*\*|__)?\s*[:–—-]\s+(.+)$", re.M)
_SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]?")


def evenings_until_exam(exam_date: Optional[str], *, minutes_per_evening: int = 45
                        ) -> Optional[dict]:
    """Tage und grobe Abend-Anzahl bis zur nächsten Klausur."""
    days = planner.days_to_exam(exam_date)
    if days is None:
        return None
    if days < 0:
        return {"days": days, "evenings": 0, "minutes_per_evening": minutes_per_evening}
    evenings = max(0, days)
    return {
        "days": days,
        "evenings": evenings,
        "minutes_per_evening": minutes_per_evening,
        "total_minutes": evenings * minutes_per_evening,
    }


def snapshot_extras(snap: Optional[dict] = None) -> dict:
    """Ergänzt today_snapshot um Countdown und Fehlerheft-Zähler."""
    snap = dict(snap or planner.today_snapshot())
    exam = snap.get("next_exam")
    snap["evenings"] = evenings_until_exam((exam or {}).get("exam_date"))
    snap["open_errors"] = manifest.count_open_errors()
    return snap


def today_session_cards(*, subject: Optional[str] = None, limit: int = 15,
                        cram: bool = False, deck: Optional[str] = None,
                        decks: Optional[list] = None,
                        sprint: bool = False, prefer: str = "auto") -> list[dict]:
    """Karten für den einen Home-Button ‚Heute starten‘."""
    limit = max(1, min(int(limit), 40))
    if sprint:
        return sprint_cards(subject=subject, decks=decks, deck=deck,
                            limit=limit, prefer=prefer)
    subj = subject
    if not subj:
        snap = planner.today_snapshot()
        top = snap.get("top_priority") or {}
        subj = top.get("subject")
        if snap.get("cram_active") and (snap.get("next_exam") or {}).get("subject"):
            subj = snap["next_exam"]["subject"]
            cram = True
    cards: list[dict] = []
    if decks:
        cards = manifest.gather_study_cards(subject=subj, decks=decks, limit=limit)
    if not cards and deck:
        cards = manifest.gather_study_cards(deck=deck, limit=limit)
    if not cards and subj:
        cards = manifest.gather_study_cards(subject=subj, limit=limit)
    if not cards:
        cards = planner.phase_round(limit=limit, cram=cram)
    return cards[:limit]


def card_looks_like_formula(card: dict) -> bool:
    """True, wenn Vorder- oder Rückseite nach einer echten Formel aussieht."""
    front = (card.get("front") or "").strip()
    back = (card.get("back") or card.get("answer") or "").strip()
    blob = f"{front}\n{back}"
    if not blob.strip():
        return False
    if _LATEX_RE.search(blob) or _FORMULA_WORD_RE.search(blob):
        return True
    if _FORMULA_SYM_RE.search(front) and len(front) <= 180:
        return True
    if any(ch in front for ch in "=∑∫√±^") and any(ch.isdigit() for ch in front):
        return True
    return False


def card_looks_like_definition(card: dict) -> bool:
    """Kurze Merk-Vorderseite, aber keine Formel (Definition / Begriff)."""
    if card_looks_like_formula(card):
        return False
    front = (card.get("front") or "").strip()
    return 8 <= len(front) <= 140


def sprint_inventory(*, subject: Optional[str] = None,
                     decks: Optional[list] = None,
                     deck: Optional[str] = None,
                     limit_scan: int = 400) -> dict:
    """Zählt Formel- und Definitions-Karten in der Auswahl (ohne zu lernen)."""
    raw: list[dict] = []
    if decks:
        for d in decks:
            raw.extend(manifest.list_cards(subject=subject, deck=d, limit=limit_scan))
    else:
        raw = manifest.list_cards(subject=subject, deck=deck, limit=limit_scan)
    seen: set[str] = set()
    cards: list[dict] = []
    for c in raw:
        cid = str(c.get("card_id") or "")
        if not cid or cid in seen:
            continue
        if c.get("suspended"):
            continue
        if c.get("use_flashcard") == 0:
            continue
        seen.add(cid)
        cards.append(c)
    formula = [c for c in cards if card_looks_like_formula(c)]
    definition = [c for c in cards if card_looks_like_definition(c)]
    return {
        "formula": formula,
        "definition": definition,
        "formula_n": len(formula),
        "definition_n": len(definition),
        "subjects": sorted({c.get("subject") for c in cards if c.get("subject")}),
    }


def sprint_cards(*, subject: Optional[str] = None, limit: int = 12,
                 decks: Optional[list] = None, deck: Optional[str] = None,
                 prefer: str = "auto") -> list[dict]:
    """Kurz-Sprint: Formeln und/oder Definitionen der gewählten Auswahl.

    ``prefer``: ``formula`` nur Formeln (leer, wenn keine da sind),
    ``definition`` nur kurze Definitionen, ``auto`` Formeln falls vorhanden
    sonst Definitionen. Fällige Karten stehen vorn, der Rest folgt – der
    Sprint ist eine bewusste Auswahl, kein stilles Fallback auf beliebige
    lange Karten."""
    limit = max(1, min(int(limit), 40))
    want = (prefer or "auto").strip().lower()
    inv = sprint_inventory(subject=subject, decks=decks, deck=deck)
    if want == "formula":
        pool = list(inv["formula"])
    elif want == "definition":
        pool = list(inv["definition"])
    else:
        pool = list(inv["formula"] or inv["definition"])
    now = time.time()

    def _due(card: dict) -> float:
        try:
            return float(card.get("due") or 0)
        except (TypeError, ValueError):
            return 0.0

    due = [c for c in pool if _due(c) <= now]
    later = [c for c in pool if _due(c) > now]
    due.sort(key=_due)
    later.sort(key=_due)
    return (due + later)[:limit]


def card_from_text(front: str, back: str, *, source: str = "text",
                   subject: Optional[str] = None, topic: Optional[str] = None,
                   doc_id: Optional[str] = None, deck: Optional[str] = None
                   ) -> Optional[str]:
    """Eine Karte aus beliebigem Text (Chat, Notiz, Zusammenfassung, Vorlesung)."""
    q = (front or "").strip()
    a = (back or "").strip()
    if not q or not a:
        return None
    digest = hashlib.sha1(f"{source}|{subject}|{q}|{a}".encode("utf-8")).hexdigest()[:16]
    cid = f"{source}::{digest}"
    manifest.upsert_review_items([{
        "card_id": cid, "source": source, "chroma_id": None,
        "subject": subject, "topic": topic,
        "front": q[:400], "back": a[:4000], "answer": a[:4000], "doc_id": doc_id,
    }])
    if deck:
        manifest.assign_deck(deck, card_ids=[cid])
    return cid


def cards_from_markdown(md: str, *, subject: Optional[str] = None,
                        source: str = "summary", max_cards: int = 8,
                        doc_id: Optional[str] = None) -> list[str]:
    """Zieht Karten aus Überschriften und ‚Begriff: Erklärung‘-Zeilen."""
    text = (md or "").strip()
    if not text:
        return []
    pairs: list[tuple[str, str]] = []
    for m in _DEF_RE.finditer(text):
        pairs.append((m.group(1).strip(" *"), m.group(2).strip()))
    headings = list(_HEADING_RE.finditer(text))
    for i, m in enumerate(headings):
        title = m.group(1).strip()
        start = m.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        body = text[start:end].strip()
        body = re.sub(r"^#{1,6}\s+.*$", "", body, flags=re.M).strip()
        if title and body and len(body) >= 20:
            pairs.append((title, body[:800]))
    if not pairs:
        paras = [p.strip() for p in re.split(r"\n\s*\n", text) if len(p.strip()) >= 40]
        for p in paras[:max_cards]:
            sent = (_SENTENCE_RE.findall(p) or [p[:80]])[0].strip()
            rest = p[len(sent):].strip() or p
            pairs.append((sent[:120], rest[:800]))
    seen: set[str] = set()
    ids: list[str] = []
    for front, back in pairs:
        if front.lower() in seen:
            continue
        seen.add(front.lower())
        cid = card_from_text(front, back, source=source, subject=subject, doc_id=doc_id)
        if cid:
            ids.append(cid)
        if len(ids) >= max_cards:
            break
    return ids


def capture_lecture(text: str, *, subject: Optional[str] = None,
                    title: Optional[str] = None, doc_id: Optional[str] = None
                    ) -> dict:
    """Nach der Vorlesung: Notiz + Lernziele + Karten + Abend-Block."""
    body = (text or "").strip()
    if not body:
        return {"note_id": None, "card_ids": [], "goals": [], "block_id": None}
    first_line = body.splitlines()[0].strip()
    note_title = (title or first_line)[:80] or "Vorlesung"
    note_id = manifest.create_note(
        subject=subject, doc_id=doc_id, topic="Vorlesung",
        collection="Vorlesung", title=note_title, body=body)
    goals = _learning_goals(body)
    card_ids = cards_from_markdown(
        body, subject=subject, source="lecture", max_cards=8, doc_id=doc_id)
    if goals and not card_ids:
        for g in goals[:4]:
            cid = card_from_text(g, body[:600], source="lecture", subject=subject)
            if cid:
                card_ids.append(cid)
    block_id = _tonight_block(subject, note_title)
    return {"note_id": note_id, "card_ids": card_ids, "goals": goals,
            "block_id": block_id}


def _learning_goals(text: str, n: int = 5) -> list[str]:
    sentences = [s.strip() for s in _SENTENCE_RE.findall(text) if len(s.strip()) >= 24]
    out: list[str] = []
    for s in sentences:
        clean = re.sub(r"\s+", " ", s).strip(" -–")
        if clean and clean.lower() not in {x.lower() for x in out}:
            out.append(clean[:160])
        if len(out) >= n:
            break
    return out


def _tonight_block(subject: Optional[str], title: str) -> Optional[str]:
    today = date.today().isoformat()
    plans = [p for p in manifest.list_study_plans()
             if p.get("status") == "active"
             and (not subject or p.get("subject") == subject)]
    if not plans:
        return None
    plan = plans[0]
    label = f"Vorlesung sichern: {title[:50]}"
    for sec in manifest.list_plan_sections(plan["plan_id"]):
        if (sec.get("title") or "") == label:
            return None
    sid = manifest.append_plan_section(
        plan["plan_id"], title=label,
        summary="Direkt nach der Vorlesung Stoff sichern.", est_minutes=15)
    return manifest.append_plan_block(
        plan["plan_id"], section_id=sid, planned_date=today, planned_min=15)


def record_error(*, source: str, source_id: Optional[str] = None,
                 card: Optional[dict] = None, card_id: Optional[str] = None,
                 subject: Optional[str] = None, topic: Optional[str] = None,
                 front: Optional[str] = None, detail: Optional[str] = None) -> str:
    card = card or {}
    cid = card_id or card.get("card_id")
    eid = manifest.upsert_error(
        source=source, source_id=source_id or cid,
        card_id=cid,
        subject=subject or card.get("subject"),
        topic=topic or card.get("topic"),
        front=front or card.get("front"),
        detail=detail,
    )
    if cid:
        manifest.assign_deck(FEHLERHEFT_DECK, card_ids=[cid])
    return eid


def record_rating_outcome(card: dict, rating: int) -> None:
    """Hängt Falsch/Richtig an das Fehlerheft (FSRS bleibt in study.rate_card)."""
    from ragapp.study import GEWUSST, NICHT
    cid = card.get("card_id")
    if rating <= NICHT:
        record_error(source="card", card=card, detail="Beim Wiederholen nicht gewusst")
    elif rating >= GEWUSST and cid:
        manifest.resolve_errors_for_card(cid)


def fehlerheft_cards(limit: int = 20, subject: Optional[str] = None) -> list[dict]:
    errors = manifest.list_errors(subject=subject, limit=limit * 2)
    ids = [e["card_id"] for e in errors if e.get("card_id")]
    if ids:
        found = manifest.find_cards(card_ids=ids, exclude_suspended=True, limit=limit)
        if found:
            return found[:limit]
    return manifest.gather_study_cards(deck=FEHLERHEFT_DECK, limit=limit)


def reschedule_all_overdue_today() -> int:
    """Schiebt alle überfälligen Planblöcke auf heute (ein Klick / Autostart)."""
    today = date.today().isoformat()
    overdue = manifest.list_overdue_plan_blocks(today)
    moved = 0
    seen: set[str] = set()
    for b in overdue:
        pid = b.get("plan_id")
        if not pid or pid in seen:
            continue
        seen.add(pid)
        moved += manifest.reschedule_overdue_blocks(pid, today, today)
    return moved


def default_plan_deadline(subject: Optional[str] = None) -> Optional[str]:
    if subject:
        exam = manifest.get_exam(subject)
        if exam and exam.get("exam_date"):
            return exam["exam_date"]
    exams = [e for e in manifest.list_exams() if e.get("exam_date")]
    exams.sort(key=lambda e: e["exam_date"])
    return exams[0]["exam_date"] if exams else (date.today() + timedelta(days=21)).isoformat()


def notes_context(subject: Optional[str] = None, query: Optional[str] = None,
                  limit: int = 4) -> str:
    """Kurzer Extra-Kontext aus eigenen Notizen (nicht als [Quelle N])."""
    notes = manifest.list_notes(subject=subject, search=query, limit=limit)
    if not notes and query:
        notes = manifest.list_notes(subject=subject, limit=limit)
    parts = []
    for n in notes:
        title = (n.get("title") or "Notiz").strip()
        body = (n.get("body") or "").strip()
        if not body:
            continue
        parts.append(f"Eigene Notiz „{title}“:\n{body[:900]}")
    if not parts:
        return ""
    return ("Eigene Mitschriften der Nutzerin/des Nutzers "
            "(nicht als nummerierte Quelle verwenden):\n\n" + "\n\n".join(parts))


def weak_subject() -> Optional[str]:
    prios = planner.all_priorities()
    if not prios:
        return None
    return prios[0].get("subject")


def save_voice_reference(audio_bytes: bytes) -> str:
    """Speichert eine in der App aufgenommene Referenzstimme."""
    from pathlib import Path
    from ragapp.config import PROJECT_ROOT, settings
    raw = bytes(audio_bytes or b"")
    if not raw:
        raise ValueError("Keine Audiodaten.")
    dest = Path(PROJECT_ROOT) / settings.AUDIO_REFERENCE_WAV
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    return str(dest)


def keep_filter_option(current: Optional[str], available: list[str],
                       *, all_label: str = "Alle") -> list[str]:
    """Hält den gewählten Filter, auch wenn nach dem Löschen keine Karten mehr da sind.

    Sonst springt ein Selectbox auf „Alle“ und der nächste Klick löscht fremde Karten.
    """
    opts = [all_label]
    for s in available:
        if s and s not in opts:
            opts.append(s)
    if current and current not in opts and current != all_label:
        opts.insert(1, current)
    return opts


def card_wipe_message(*, deleted: int, remaining: int, subject: Optional[str] = None,
                      subject_label: Optional[str] = None,
                      document: Optional[str] = None) -> str:
    """Meldung nach dem Löschen – besonders wenn ein Fach/Dokument jetzt leer ist."""
    scope: list[str] = []
    if subject:
        scope.append(f"Fach „{subject_label or subject}“")
    if document:
        scope.append(f"Dokument „{document}“")
    where = " und ".join(scope) if scope else "dieser Auswahl"
    if deleted <= 0:
        return "Keine Karten gelöscht."
    if remaining <= 0:
        if scope:
            return f"Alle {deleted} Karteikarten von {where} wurden gelöscht."
        return f"Alle {deleted} Karteikarten wurden gelöscht."
    return f"{deleted} Karteikarte(n) von {where} gelöscht. Es bleiben {remaining}."


def scan_inbox_once(progress=None) -> dict:
    """Liest neue Dateien aus dem Inbox-Ordner einmalig ein."""
    from pathlib import Path
    from ragapp.config import INBOX_DIR
    from ragapp.ingestion.pipeline import ingest_file
    inbox = Path(INBOX_DIR)
    if not inbox.is_dir():
        return {"scanned": 0, "ok": 0, "errors": []}
    files = [p for p in inbox.iterdir()
             if p.is_file() and p.suffix.lower() in
             {".pdf", ".md", ".txt", ".docx", ".pptx"}]
    ok = 0
    errors = []
    for i, path in enumerate(files, 1):
        if progress:
            progress(f"Lese {path.name} ({i}/{len(files)})")
        try:
            res = ingest_file(path)
            if res.get("status") in ("ok", "skipped", "duplicate"):
                ok += 1
            else:
                errors.append(f"{path.name}: {res.get('status')}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{path.name}: {exc}")
    return {"scanned": len(files), "ok": ok, "errors": errors}
