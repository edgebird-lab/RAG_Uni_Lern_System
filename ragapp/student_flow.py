"""
Alltags-Hilfen für Studenten (ohne extra LLM-Zwang)
===================================================
Heute-Session, Vorlesung einfangen, Fehlerheft, Karten aus Text, Klausur-
Countdown. Rein deterministisch, damit Tests und Offline-Alltag greifen.
"""
from __future__ import annotations

import hashlib
import re
import threading
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from ragapp import manifest, planner
from ragapp.manifest import FEHLERHEFT_DECK

# Formel-Sprint: Karten, die wirklich nach Formel/Rechnung aussehen – nicht
# jede kurze Vorderseite. LaTeX und Rechenzeichen zaehlen staerker als Laenge.
_LATEX_RE = re.compile(
    r"\$[^$]+\$|\\\(|\\\[|\\begin\{|\\frac|\\sum|\\int|\\lim|\\vec|"
    r"\\mathbb|\\mathrm|\\partial|\\cdot")
_LATEX_CMD_RE = re.compile(
    r"\\(?:frac|sum|int|lim|sqrt|cdot|mathbb|mathrm|partial|vec|"
    r"infty|alpha|beta|gamma|delta|varepsilon|epsilon|theta|lambda|"
    r"mu|pi|sigma|omega|to|rightarrow|leq|geq|neq|times|in|subset|"
    r"cup|cap|left|right|overline|hat|bar|text|sin|cos|tan|log|ln|"
    r"exp|begin|end|mathbf|mathcal)\b")
_FORMULA_SYM_RE = re.compile(r"[=∑∫√±≤≥≈∞∂∇]|\\[a-zA-Z]+")
_FORMULA_WORD_RE = re.compile(
    r"(?i)\b(formel|gleichung|ableitung|integral|matrix|determinante|"
    r"eigenwert|eigenvektor|vektorraum|stetig|limes|konvergenz|"
    r"differential|gradient)\b")

_HEADING_RE = re.compile(r"^#{1,3}\s+(.+)$", re.M)
# Fehlerheft nur für harte Lücken – gleiche Schwelle wie Probeklausur/mündlich.
HARD_GAP_SCORE = 40
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
                        sprint: bool = False, prefer: str = "auto",
                        preferred_card_ids: Optional[list[str]] = None) -> list[dict]:
    """Karten für den einen Home-Button ‚Heute starten‘."""
    limit = max(1, min(int(limit), 40))
    if sprint:
        return sprint_cards(subject=subject, decks=decks, deck=deck,
                            limit=limit, prefer=prefer)
    if preferred_card_ids:
        preferred = manifest.find_cards(
            card_ids=preferred_card_ids, exclude_suspended=True, limit=limit)
        if preferred:
            # Bevorzugen, aber die als „N fällige Karten“ angekündigte Mission
            # mit regulären fälligen Karten auffüllen statt sie zu ersetzen.
            regular = manifest.gather_study_cards(subject=subject, limit=limit)
            seen = {c["card_id"] for c in preferred}
            return (preferred + [
                c for c in regular if c.get("card_id") not in seen
            ])[:limit]
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


def cards_for_prefill(prefill: dict) -> list[dict]:
    """Karten aus ``study_prefill``: card_ids vor doc_ids, danach Heute-Session."""
    prefill = prefill or {}
    limit = max(1, min(int(prefill.get("limit") or 16), 40))
    subject = prefill.get("subject")
    if prefill.get("source") == "fehlerheft" or prefill.get("deck") == "Fehlerheft":
        return fehlerheft_cards(limit=limit, subject=subject)
    if prefill.get("sprint") or prefill.get("mode") == "sprint":
        return sprint_cards(
            subject=subject, limit=limit,
            decks=prefill.get("decks"), deck=prefill.get("deck"),
            prefer=prefill.get("prefer") or "auto")
    card_ids = [c for c in (prefill.get("card_ids") or []) if c]
    if card_ids:
        found = manifest.find_cards(
            card_ids=card_ids, exclude_suspended=True, limit=limit)
        by_id = {c["card_id"]: c for c in found}
        ordered = [by_id[i] for i in card_ids if i in by_id]
        if ordered:
            return ordered[:limit]
    doc_ids = [d for d in (prefill.get("doc_ids") or []) if d]
    topics = [t for t in (prefill.get("topics") or []) if t]
    if doc_ids or topics:
        cards = manifest.find_cards(
            subject=subject, doc_ids=doc_ids or None,
            topics=topics or None, limit=limit)
        if not cards and topics and doc_ids:
            cards = manifest.find_cards(
                subject=subject, doc_ids=doc_ids, limit=limit)
        if cards:
            return cards[:limit]
    return today_session_cards(
        subject=subject, limit=limit,
        cram=bool(prefill.get("cram")), deck=prefill.get("deck"),
        sprint=bool(prefill.get("sprint")),
        preferred_card_ids=card_ids or None)


def prefill_from_plan_block(block_id: str, **extra) -> dict:
    """study_prefill / practice_prefill aus einem Lernplan-Block."""
    out = {"source": "plan", "mode": "reveal", "limit": 12, "block_id": block_id}
    out.update(extra)
    block = manifest.get_plan_block(block_id) if block_id else None
    if not block:
        return out
    plan = manifest.get_study_plan(block["plan_id"]) or {}
    section: dict = {}
    if block.get("section_id"):
        for sec in manifest.list_plan_sections(block["plan_id"]):
            if sec.get("section_id") == block["section_id"]:
                section = sec
                break
    doc_ids = [
        ref.get("doc_id") for ref in (section.get("source_refs") or [])
        if ref.get("doc_id")
    ]
    if not doc_ids:
        doc_ids = list(plan.get("doc_ids") or [])
    topics = [section["title"]] if section.get("title") else []
    out.setdefault("subject", plan.get("subject"))
    out.setdefault("doc_ids", doc_ids)
    out.setdefault("topics", topics)
    return out


def pick_existing_practice(*, subject: Optional[str] = None,
                           topic: Optional[str] = None,
                           doc_ids: Optional[list] = None) -> Optional[str]:
    """Vorhandene Übung zum Abschnitt, sonst None – kein Generator-Zwang."""
    rows = manifest.list_practice_problems(subject=subject, limit=80)
    if not rows:
        return None
    topic_n = (topic or "").strip().lower()
    wanted = {d for d in (doc_ids or []) if d}

    def _topic(row: dict) -> str:
        return (row.get("topic") or "").strip().lower()

    if topic_n:
        for row in rows:
            if _topic(row) == topic_n:
                return row.get("problem_id")
        for row in rows:
            t = _topic(row)
            if t and (topic_n in t or t in topic_n):
                return row.get("problem_id")
    if wanted:
        for row in rows:
            if row.get("doc_id") in wanted:
                return row.get("problem_id")
    return None


def mark_plan_block_done(block_id: str, via: str = "manual") -> None:
    """Block abhaken und Planstatus nachziehen."""
    if not block_id:
        return
    manifest.set_block_done(block_id, True, via=via)
    block = manifest.get_plan_block(block_id)
    if block:
        manifest.sync_plan_status(block["plan_id"])


def upsert_formelsammlung(subject: str, text: str) -> str:
    """Eine Formelsammlung pro Fach als angeheftete Notiz."""
    body = (text or "").strip()
    title = f"Formelsammlung {subject}".strip()
    existing = manifest.list_notes(
        subject=subject, collection="Formelsammlung", limit=1)
    if existing:
        manifest.update_note(
            existing[0]["note_id"], body=body, title=title, pinned=True)
        return existing[0]["note_id"]
    return manifest.create_note(
        subject=subject, collection="Formelsammlung", topic="Formel",
        title=title, body=body, pinned=True)


def formelsammlung_text(subject: str) -> Optional[str]:
    notes = manifest.list_notes(
        subject=subject, collection="Formelsammlung", limit=1)
    if notes:
        return notes[0].get("body") or ""
    return None


def overconfidence_card_ids(*, subject: Optional[str] = None,
                            limit: int = 20) -> list[str]:
    """Karten aus dem Fehlerheft, die als sicher-und-falsch markiert sind."""
    ids: list[str] = []
    seen: set[str] = set()
    for err in manifest.list_errors(subject=subject, limit=max(limit * 2, 20)):
        cid = err.get("card_id")
        if not cid or cid in seen:
            continue
        if not (err.get("detail") or "").startswith("Sicher eingeschätzt"):
            continue
        seen.add(cid)
        ids.append(cid)
        if len(ids) >= limit:
            break
    return ids


def apply_oral_score(card_id: Optional[str], partial_points: int, *,
                     subject: Optional[str] = None,
                     front: Optional[str] = None) -> None:
    """Mündliche Teilpunkte auf FSRS und Fehlerheft abbilden."""
    from ragapp.study import GEWUSST, HALB, NICHT, rate_card

    if not card_id:
        return
    cards = manifest.get_cards_by_ids([card_id])
    if not cards:
        return
    pts = max(0, min(100, int(partial_points)))
    if pts >= 75:
        rating = GEWUSST
    elif pts >= 40:
        rating = HALB
    else:
        rating = NICHT
    rate_card(cards[0], rating)
    if is_hard_gap(rating=rating):
        record_error(
            source="oral", card=cards[0], card_id=card_id,
            subject=subject or cards[0].get("subject"),
            front=front or cards[0].get("front"),
            detail=f"Mündlich {pts} %")


def normalize_exam_prefill(prefill: dict) -> dict:
    """exam_prefill: mode written|oral, Fach, optionales Limit – ohne Auto-Start."""
    prefill = prefill or {}
    mode = prefill.get("mode") or "written"
    if mode not in ("written", "oral"):
        mode = "written"
    limit = prefill.get("limit")
    try:
        limit_n = int(limit) if limit is not None else None
    except (TypeError, ValueError):
        limit_n = None
    return {
        "mode": mode,
        "subject": prefill.get("subject") or None,
        "limit": limit_n if limit_n and limit_n > 0 else None,
    }


def exam_hub_history(*, limit: int = 8) -> list[dict]:
    """Gemischte letzte Ergebnisse: schriftliche Versuche und abgeschlossene Mündliche."""
    from ragapp import oral_exam

    limit = max(1, min(int(limit), 20))
    rows: list[dict] = []
    for attempt in manifest.list_exam_attempts(limit=limit):
        rows.append({
            "kind": "written",
            "id": attempt.get("attempt_id"),
            "when": float(attempt.get("taken_at") or 0),
            "total_pct": attempt.get("total_pct"),
            "count": attempt.get("num_items"),
            "subject": None,
            "status": "done",
        })
    for session in oral_exam.list_sessions(limit=limit):
        if session.get("status") != "done":
            continue
        questions = session.get("questions") or []
        rows.append({
            "kind": "oral",
            "id": session.get("session_id"),
            "when": float(session.get("updated_at") or session.get("created_at") or 0),
            "total_pct": session.get("total_pct"),
            "count": len(questions),
            "subject": session.get("subject"),
            "status": session.get("status"),
        })
    rows.sort(key=lambda r: r["when"], reverse=True)
    return rows[:limit]


def oral_weak_card_ids(session: dict, *, threshold: int = 75) -> list[str]:
    """Karten einer mündlichen Sitzung unter der Bestehensschwelle."""
    ids: list[str] = []
    seen: set[str] = set()
    for item in (session or {}).get("questions") or []:
        cid = item.get("card_id")
        pts = item.get("partial_points")
        if not cid or cid in seen or pts is None:
            continue
        if int(pts) < int(threshold):
            seen.add(cid)
            ids.append(cid)
    return ids


def clip_preserving_math(text: Optional[str], limit: int) -> str:
    """Kürzt Text, ohne ein geöffnetes ``$...$`` in der Mitte abzuschneiden."""
    raw = text or ""
    if limit <= 0 or len(raw) <= limit:
        return raw
    cut = raw[:limit]
    if cut.count("$") % 2 == 0:
        return cut
    rest = raw[limit:]
    nxt = rest.find("$")
    if nxt < 0:
        return cut
    return raw[:limit + nxt + 1]


def _latex_span_end(s: str, i: int) -> int:
    """Ende eines LaTeX-Befehls inkl. ``{...}``-Argumenten und ``^``/``_``."""
    n = len(s)
    if i >= n or s[i] != "\\":
        return min(i + 1, n)
    j = i + 1
    while j < n and s[j].isalpha():
        j += 1
    while True:
        k = j
        while k < n and s[k].isspace():
            k += 1
        if k < n and s[k] == "{":
            j = k
            depth = 0
            while j < n:
                if s[j] == "{":
                    depth += 1
                elif s[j] == "}":
                    depth -= 1
                    j += 1
                    if depth == 0:
                        break
                    continue
                j += 1
            continue
        if k < n and s[k] in "^_":
            j = k + 1
            if j < n and s[j] == "{":
                continue
            if j < n:
                j += 1
            continue
        break
    return j


def normalize_card_latex(text: Optional[str]) -> str:
    """Macht Karten-LaTeX display-tauglich: ``\\(`` → ``$``, nackte ``\\frac`` wrappen.

    Ändert nicht die gespeicherte Karte – nur die Anzeige und den Anki-Export.
    """
    s = text or ""
    if not s.strip():
        return s
    s = re.sub(
        r"\\\\(frac|sum|int|lim|sqrt|cdot|mathbb|mathrm|partial|vec)\b",
        r"\\\1", s)
    s = s.replace("\\[", "$$").replace("\\]", "$$")
    s = s.replace("\\(", "$").replace("\\)", "$")
    out: list[str] = []
    i = 0
    n = len(s)
    in_math = False
    while i < n:
        if s.startswith("$$", i):
            in_math = not in_math
            out.append("$$")
            i += 2
            continue
        if s[i] == "$":
            in_math = not in_math
            out.append("$")
            i += 1
            continue
        if not in_math and _LATEX_CMD_RE.match(s, i):
            j = _latex_span_end(s, i)
            out.append("$" + s[i:j] + "$")
            i = j
            continue
        out.append(s[i])
        i += 1
    return "".join(out)


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
        "front": clip_preserving_math(q, 400),
        "back": clip_preserving_math(a, 4000),
        "answer": clip_preserving_math(a, 4000), "doc_id": doc_id,
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


_VERSTEHEN_CTRL = frozenset({
    "Gib mir einen Hinweis, ohne die Antwort zu verraten.",
    "Ich weiß es teilweise.",
    "Löse es auf.",
    "Nächster Aspekt desselben Themas.",
})
_SKIP_TOPICS = frozenset({"(ohne thema)", "ohne thema", "ohne Thema", ""})


def pick_verstehen_topic() -> Optional[dict]:
    """Ein Fach und ein Thema für die nächste Verstehen-Sitzung – ohne Klausurdatum."""
    from ragapp import analytics
    from ragapp.graph.socratic import collect_socratic_topic_suggestions, is_usable_topic

    snap = planner.today_snapshot()
    subject = (snap.get("top_priority") or {}).get("subject")
    if not subject or is_fixture_subject(subject) or is_placeholder_subject(subject):
        subject = None
        for s in manifest.study_subjects():
            if not is_fixture_subject(s) and not is_placeholder_subject(s):
                subject = s
                break
        if not subject:
            return None
    topic = None
    mastery = None
    for row in analytics.mastery_by_topic(subject, limit=8):
        cand = (row.get("topic") or "").strip()
        if cand.lower() in {x.lower() for x in _SKIP_TOPICS}:
            continue
        if not is_usable_topic(cand, subject=subject):
            continue
        topic = cand
        mastery = row.get("mastery_pct")
        break
    if not topic:
        cards = [dict(c) for c in manifest.list_cards(subject=subject, limit=40)]
        docs = [dict(d) for d in manifest.list_documents()]
        docs = [d for d in docs if d.get("subject") == subject]
        sugg = collect_socratic_topic_suggestions(
            cards=cards, documents=docs, subject=subject, limit=5)
        topic = sugg[0] if sugg else None
    if not topic:
        return None
    return {
        "subject": subject,
        "topic": topic,
        "minutes": 20,
        "mastery_pct": mastery,
    }


def verstehen_pairs(messages: list, topic: str) -> list[tuple[str, str]]:
    """Frage/Antwort-Paare aus einem sokratischen Verlauf – ohne extra LLM."""
    pairs: list[tuple[str, str]] = []
    prev_asst = (topic or "").strip() or "Thema"
    prev_user = ""
    seen: set[str] = set()
    for msg in messages or []:
        text = (msg.get("content") or "").strip()
        role = msg.get("role")
        if not text:
            continue
        if role == "user":
            prev_user = text
            if (text.startswith("Lass uns über ")
                    or text in _VERSTEHEN_CTRL or len(text) < 40):
                continue
            front = prev_asst[:200]
            key = front.lower()
            if key not in seen:
                seen.add(key)
                pairs.append((front, text[:1500]))
        elif role == "assistant":
            if prev_user == "Löse es auf.":
                front = prev_asst[:200]
                key = front.lower()
                if key not in seen:
                    seen.add(key)
                    pairs.append((front, text[:1500]))
            prev_asst = (text.split("\n")[0] or prev_asst)[:180]
            prev_user = ""
        if len(pairs) >= 4:
            break
    return pairs


def finish_verstehen_session(
    messages: list, *, topic: str, subject: Optional[str] = None,
    started_at: Optional[float] = None, minutes: int = 20,
) -> dict:
    """Notiz + Karten aus der Sitzung. Kein LLM, kein Harvest."""
    topic = (topic or "").strip() or "Thema"
    lines: list[str] = [f"Thema: {topic}"]
    for msg in messages or []:
        text = (msg.get("content") or "").strip()
        if not text:
            continue
        role = msg.get("role")
        if role == "user":
            if text.startswith("Lass uns über "):
                continue
            label = "Steuerung" if text in _VERSTEHEN_CTRL else "Du"
            lines.append(f"**{label}:** {text[:600]}")
        elif role == "assistant":
            lines.append(text[:500])
    body = "\n\n".join(lines).strip()
    if body == f"Thema: {topic}":
        body += "\n\nNoch keine Dialogzeilen."
    note_id = manifest.create_note(
        subject=subject, topic=topic, collection="Verstehen",
        title=f"Verstehen: {topic}"[:80], body=body)
    card_ids: list[str] = []
    for front, back in verstehen_pairs(messages, topic):
        cid = card_from_text(
            front, back, source="chat", subject=subject, topic=topic)
        if cid:
            card_ids.append(cid)
    ended = time.time()
    started = float(started_at or ended)
    duration = max(1, int(ended - started))
    try:
        manifest.log_study_session(
            subject=subject, mode="verstehen",
            started_at=started, ended_at=ended, duration_sec=duration,
            notiz=topic)
    except Exception:  # noqa: BLE001
        pass
    return {
        "note_id": note_id,
        "card_ids": card_ids,
        "topic": topic,
        "subject": subject,
        "minutes": minutes,
    }


def _first_study_subject(preferred: Optional[str] = None) -> Optional[str]:
    if preferred and not is_fixture_subject(preferred) and not is_placeholder_subject(preferred):
        return preferred
    for s in manifest.study_subjects():
        if not is_fixture_subject(s) and not is_placeholder_subject(s):
            return s
    return None


def _real_documents(subject: Optional[str] = None) -> list[dict]:
    from ragapp.config import PROJECT_ROOT
    out: list[dict] = []
    for raw in manifest.list_documents():
        d = dict(raw)
        subj = (d.get("subject") or "").strip()
        if subject and subj != subject:
            continue
        if is_fixture_subject(subj) or is_placeholder_subject(subj) or is_inbox_subject(subj):
            continue
        sp = d.get("source_path") or ""
        path = Path(sp) if Path(sp).is_absolute() else PROJECT_ROOT / sp
        if not path.is_file():
            continue
        d["_path"] = path
        out.append(d)
    return out


def _heading_for_doc(path: Path, subject: Optional[str], fallback: str) -> tuple[str, int]:
    from ragapp.graph.socratic import is_usable_topic, pdf_toc_titles, topics_from_markdown
    from ragapp.ui import _docviewer

    heading = (fallback or "").strip()
    page = 1
    if path.suffix.lower() == ".pdf":
        toc = pdf_toc_titles(str(path), root=path.parent)
        for cand in toc:
            if is_usable_topic(cand, subject=subject):
                heading = cand
                break
        if heading:
            page = _docviewer.toc_page_for_heading(path, heading)
    else:
        text = _docviewer.load_full_text(path) or ""
        for cand in topics_from_markdown(text, subject=subject, limit=5):
            if is_usable_topic(cand, subject=subject):
                heading = cand
                break
    heading = heading or path.stem.replace("_", " ").strip() or "Skript"
    return heading, max(1, int(page or 1))


def _skript_cursor_file() -> Path:
    from ragapp.config import PROJECT_ROOT
    path = PROJECT_ROOT / "data" / "skript_cursors.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_skript_cursor(doc_id: Optional[str]) -> Optional[dict]:
    """Zuletzt gelesene Seite einer Unterlage (1-basiert)."""
    if not doc_id:
        return None
    try:
        import json
        raw = json.loads(_skript_cursor_file().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    row = raw.get(str(doc_id)) if isinstance(raw, dict) else None
    if not isinstance(row, dict):
        return None
    try:
        page = int(row.get("page") or 0)
    except (TypeError, ValueError):
        return None
    if page < 1:
        return None
    heading = (row.get("heading") or "").strip() or None
    return {"page": page, "heading": heading}


def save_skript_cursor(doc_id: Optional[str], page: int,
                       heading: Optional[str] = None) -> None:
    """Merkt die letzte Skript-Seite, damit die nächste Sitzung dort weiterliest."""
    if not doc_id:
        return
    try:
        page = int(page or 0)
    except (TypeError, ValueError):
        return
    if page < 1:
        return
    import json
    path = _skript_cursor_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except Exception:  # noqa: BLE001
        data = {}
    data[str(doc_id)] = {
        "page": page,
        "heading": (heading or "").strip(),
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=0),
                    encoding="utf-8")


def pick_skript_spot() -> Optional[dict]:
    """Datei + Stelle für die nächste Skript-Sitzung – ohne Klausurdatum."""
    snap = planner.today_snapshot()
    for block in snap.get("plan_blocks_today") or []:
        if block.get("done"):
            continue
        subject = block.get("plan_subject") or block.get("subject")
        if not subject or is_fixture_subject(subject) or is_placeholder_subject(subject):
            continue
        heading = (block.get("section_title") or "").strip()
        plan_id = block.get("plan_id")
        section_id = block.get("section_id")
        doc_ids: list[str] = []
        if plan_id and section_id:
            for sec in manifest.list_plan_sections(plan_id):
                if sec.get("section_id") != section_id:
                    continue
                doc_ids = [
                    r.get("doc_id") for r in (sec.get("source_refs") or [])
                    if r.get("doc_id")
                ]
                break
        docs = _real_documents(subject)
        chosen = None
        if doc_ids:
            by_id = {d["doc_id"]: d for d in docs}
            for did in doc_ids:
                if did in by_id:
                    chosen = by_id[did]
                    break
        if chosen is None and docs:
            chosen = docs[0]
        if not chosen:
            continue
        path = chosen["_path"]
        from ragapp.graph.socratic import is_usable_topic
        from ragapp.ui import _docviewer as _dv
        if heading and is_usable_topic(heading, subject=subject):
            title = heading
            page = _dv.toc_page_for_heading(path, heading)
        else:
            title, page = _heading_for_doc(path, subject, heading)
        return {
            "subject": subject,
            "doc_id": chosen.get("doc_id"),
            "filename": chosen.get("filename") or path.name,
            "source_path": str(chosen.get("source_path") or path),
            "page": page,
            "heading": title,
            "minutes": 20,
            "block_id": block.get("block_id"),
        }

    preferred = (snap.get("top_priority") or {}).get("subject")
    subject = _first_study_subject(preferred)
    if not subject:
        docs = _real_documents()
        if not docs:
            return None
        subject = docs[0].get("subject")
    docs = _real_documents(subject)
    if not docs:
        docs = _real_documents()
    if not docs:
        return None
    chosen = docs[0]
    path = chosen["_path"]
    heading, page = _heading_for_doc(path, subject, "")
    cur = load_skript_cursor(chosen.get("doc_id"))
    if cur:
        page = cur["page"]
        if cur.get("heading"):
            heading = cur["heading"]
    return {
        "subject": subject,
        "doc_id": chosen.get("doc_id"),
        "filename": chosen.get("filename") or path.name,
        "source_path": str(chosen.get("source_path") or path),
        "page": page,
        "heading": heading,
        "minutes": 20,
        "block_id": None,
    }


def hydrate_skript_spot(raw: Optional[dict] = None) -> Optional[dict]:
    """Vervollständigt ein Prefill (doc_id/Fach) zu einem Sitzungs-Spot."""
    from ragapp.config import PROJECT_ROOT
    from ragapp.graph.socratic import is_usable_topic
    from ragapp.ui import _docviewer as _dv

    raw = dict(raw or {})
    doc = None
    if raw.get("doc_id"):
        row = manifest.get_document(str(raw["doc_id"]))
        if row:
            d = dict(row)
            sp = d.get("source_path") or ""
            path = Path(sp) if Path(sp).is_absolute() else PROJECT_ROOT / sp
            if path.is_file():
                d["_path"] = path
                doc = d
    if doc is None and raw.get("subject"):
        docs = _real_documents(str(raw["subject"]))
        doc = docs[0] if docs else None
    if doc is None:
        return pick_skript_spot()
    path = doc["_path"]
    subject = raw.get("subject") or doc.get("subject")
    heading = (raw.get("heading") or "").strip()
    page = int(raw.get("page") or 0)
    if heading and is_usable_topic(heading, subject=subject):
        if page < 1:
            page = _dv.toc_page_for_heading(path, heading)
    else:
        if page < 1:
            cur = load_skript_cursor(doc.get("doc_id"))
            if cur:
                page = cur["page"]
                heading = cur.get("heading") or heading
        if page < 1:
            heading, page = _heading_for_doc(path, subject, heading)
    return {
        "subject": subject,
        "doc_id": doc.get("doc_id"),
        "filename": raw.get("filename") or doc.get("filename") or path.name,
        "source_path": str(doc.get("source_path") or path),
        "page": max(1, int(page or 1)),
        "heading": heading,
        "minutes": int(raw.get("minutes") or 20),
        "block_id": raw.get("block_id"),
    }


def finish_skript_session(
    marks: list, *, heading: str, subject: Optional[str] = None,
    doc_id: Optional[str] = None, filename: Optional[str] = None,
    started_at: Optional[float] = None, minutes: int = 20,
    block_id: Optional[str] = None,
) -> dict:
    """Notiz + Karten aus Markierungen. Kein LLM, kein Harvest."""
    heading = (heading or "").strip() or "Skript"
    lines: list[str] = [f"Stelle: {heading}"]
    if filename:
        lines.append(f"Datei: {filename}")
    card_ids: list[str] = []
    seen: set[str] = set()
    for mark in marks or []:
        text = (mark.get("text") if isinstance(mark, dict) else str(mark or "")).strip()
        if not text:
            continue
        loc = (mark.get("heading") if isinstance(mark, dict) else None) or heading
        page = mark.get("page") if isinstance(mark, dict) else None
        label = f"**{loc}**" + (f" · S. {page}" if page else "")
        lines.append(f"{label}\n{text[:800]}")
        key = text[:80].lower()
        if key in seen or len(card_ids) >= 4:
            continue
        seen.add(key)
        front = (loc if loc != heading else "") or (_SENTENCE_RE.findall(text) or [text[:80]])[0]
        front = (front or heading).strip()[:120]
        cid = card_from_text(
            front, text[:1500], source="skript", subject=subject,
            topic=heading, doc_id=doc_id)
        if cid:
            card_ids.append(cid)
    body = "\n\n".join(lines).strip()
    if body in {f"Stelle: {heading}", f"Stelle: {heading}\n\nDatei: {filename}"}:
        body += "\n\nNoch keine Markierungen."
    note_id = manifest.create_note(
        subject=subject, doc_id=doc_id, topic=heading, collection="Skript",
        title=f"Skript: {heading}"[:80], body=body)
    ended = time.time()
    started = float(started_at or ended)
    duration = max(1, int(ended - started))
    try:
        manifest.log_study_session(
            subject=subject, mode="skript",
            started_at=started, ended_at=ended, duration_sec=duration,
            notiz=heading)
    except Exception:  # noqa: BLE001
        pass
    if block_id:
        try:
            mark_plan_block_done(block_id, via="manual")
        except Exception:  # noqa: BLE001
            pass
    return {
        "note_id": note_id,
        "card_ids": card_ids,
        "heading": heading,
        "subject": subject,
        "minutes": minutes,
    }


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


def is_hard_gap(*, score: Optional[int] = None, rating: Optional[int] = None) -> bool:
    """Fehlerheft nur für harte Lücken: unter 40 % oder 'Nicht gewusst'.

    Teilweise gelöste Übungen (40–74 %) und 'Teilweise'-Selbsteinschätzung
    bleiben im normalen FSRS, ohne das Heft zu füllen.
    """
    if score is not None:
        try:
            return int(score) < HARD_GAP_SCORE
        except (TypeError, ValueError):
            return False
    if rating is not None:
        try:
            return int(rating) <= 0
        except (TypeError, ValueError):
            return False
    return False


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


def record_rating_outcome(card: dict, rating: int,
                          confidence: Optional[str] = None) -> None:
    """Hängt Falsch/Richtig an das Fehlerheft (FSRS bleibt in study.rate_card)."""
    from ragapp.study import GEWUSST, NICHT
    cid = card.get("card_id")
    if rating <= NICHT:
        detail = ("Sicher eingeschätzt, aber nicht gewusst"
                  if confidence == "sicher"
                  else "Beim Wiederholen nicht gewusst")
        record_error(source="card", card=card, detail=detail)
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


def repair_all_overdue_plans(*, apply: bool = False) -> dict:
    """Vorschau/Anwendung der fairen Reparatur für alle betroffenen Pläne."""
    from ragapp.study_plan import repair_overdue_blocks
    today = date.today().isoformat()
    overdue = manifest.list_overdue_plan_blocks(today)
    plan_ids = list(dict.fromkeys(
        b.get("plan_id") for b in overdue if b.get("plan_id")))
    results = [
        repair_overdue_blocks(pid, apply=apply) for pid in plan_ids
    ]
    return {
        "plans": results,
        "moves": [m for result in results for m in result["moves"]],
        "moved_blocks": sum(r["moved_blocks"] for r in results),
        "moved_minutes": sum(r["moved_minutes"] for r in results),
        "shortfall_minutes": sum(r["shortfall_minutes"] for r in results),
        "applied": bool(apply),
    }


def reschedule_all_overdue_today() -> int:
    """Kompatibilitätswrapper: repariert verteilt, nie mehr alles auf heute."""
    return repair_all_overdue_plans(apply=True)["moved_blocks"]


def default_plan_deadline(subject: Optional[str] = None) -> Optional[str]:
    """Echtes Klausurdatum des Fachs, sonst None – kein erfundenes +21-Tage-Ziel."""
    if subject:
        exam = manifest.get_exam(subject)
        if exam and exam.get("exam_date"):
            return exam["exam_date"]
        return None
    exams = [
        e for e in manifest.list_exams()
        if e.get("exam_date")
        and not is_placeholder_subject(e.get("subject"))
        and not is_fixture_subject(e.get("subject"))
    ]
    exams.sort(key=lambda e: e["exam_date"])
    return exams[0]["exam_date"] if exams else None


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


def daily_missions() -> list[dict]:
    """Maximal drei Tagesmissionen: fällige Karten, schwaches Thema, Planblock.

    Wenn Plätze frei sind (nichts fällig, kein Plan), füllen Skript und
    Verstehen auf. Fällige Karten werden nicht verdrängt. Der Planblock
    wird auf PLAN_MAX_DAILY_FOCUS_MIN gedeckelt.
    """
    from ragapp import analytics
    from ragapp.config import settings
    cap = max(5, int(settings.PLAN_MAX_DAILY_FOCUS_MIN))
    snap = planner.today_snapshot()
    missions: list[dict] = []

    overconfident = [
        e for e in manifest.list_errors(limit=20)
        if (e.get("detail") or "").startswith("Sicher eingeschätzt")
        and e.get("card_id")
    ]
    due = int(snap.get("due_cards") or 0)
    if due > 0:
        preferred_subject = (
            overconfident[0].get("subject") if overconfident
            else (snap.get("top_priority") or {}).get("subject")
        )
        missions.append({
            "id": "reviews",
            "kind": "reviews",
            "title": f"{due} fällige Karten",
            "minutes": max(8, min(due, cap)),
            "reason": (
                "Sicher-und-falsch-Karten zuerst: Diese Lücken werden leicht überschätzt."
                if overconfident else
                "Fällige Wiederholungen zuerst, sonst wächst der Stau."
            ),
            "subject": preferred_subject,
            "count": due,
            "prefer_overconfidence": bool(overconfident),
            "card_ids": [e["card_id"] for e in overconfident],
        })

    subj = weak_subject()
    weak = analytics.mastery_by_topic(subj, limit=1) if subj else []
    if weak and int(weak[0].get("mastery_pct") or 0) < 80:
        w = weak[0]
        weak_cards = manifest.find_cards(
            subject=subj, topics=[w.get("topic") or "__none__"], limit=20)
        missions.append({
            "id": "weak",
            "kind": "weak_topic",
            "title": f"Schwäche: {w.get('topic') or 'ohne Thema'}",
            "minutes": min(20, cap),
            "reason": f"Nur {w.get('mastery_pct', 0)} % sitzt – dort lohnt die nächste Runde.",
            "subject": subj,
            "topic": w.get("topic"),
            "card_ids": [c["card_id"] for c in weak_cards],
        })

    open_today = [b for b in (snap.get("plan_blocks_today") or []) if not b.get("done")]
    overdue = [b for b in (snap.get("overdue_plan_blocks") or []) if not b.get("done")]
    blocks = open_today or overdue
    if blocks:
        raw = sum(int(b.get("planned_min") or 0) for b in blocks)
        b0 = blocks[0]
        plan_title = (
            (b0.get("section_title") or b0.get("plan_title") or "Planblock")
            if len(blocks) == 1
            else f"{len(blocks)} Planblöcke"
        )
        missions.append({
            "id": "plan",
            "kind": "plan",
            "title": plan_title,
            "minutes": max(5, min(raw, cap)),
            "reason": ("Im Lernplan für heute vorgesehen." if open_today
                       else "Verpasster Planblock, auf die Lastgrenze gekappt."),
            "subject": b0.get("plan_subject"),
            "plan_id": b0.get("plan_id"),
            "block_ids": [b.get("block_id") for b in blocks if b.get("block_id")],
        })
    if len(missions) < 3:
        sk = pick_skript_spot()
        if sk:
            heading = (sk.get("heading") or sk.get("filename") or "Skript").strip()
            missions.append({
                "id": "skript",
                "kind": "skript",
                "title": f"Skript: {plain_study_snippet(heading, limit=36)}",
                "minutes": max(5, int(sk.get("minutes") or 20)),
                "reason": "Unterlage lesen und markieren – danach sitzt der Stoff besser.",
                "subject": sk.get("subject"),
                "doc_id": sk.get("doc_id"),
                "heading": sk.get("heading"),
                "prefill": sk,
            })
    if len(missions) < 3:
        vs = pick_verstehen_topic()
        if vs:
            topic = (vs.get("topic") or "Thema").strip()
            missions.append({
                "id": "verstehen",
                "kind": "verstehen",
                "title": f"Verstehen: {plain_study_snippet(topic, limit=36)}",
                "minutes": max(5, int(vs.get("minutes") or 20)),
                "reason": "Ein Thema im Dialog klären, ohne auf fällige Karten zu warten.",
                "subject": vs.get("subject"),
                "topic": vs.get("topic"),
                "prefill": vs,
            })
    return missions[:3]


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


def ensure_course_folder(subject: str):
    """Fach-Ordner unter dem Quellenverzeichnis, damit Unterlagen dem Kurs gehören."""
    from pathlib import Path
    from ragapp.config import SOURCE_DIR
    code = (subject or "").strip()
    if not code:
        raise ValueError("Fach fehlt.")
    folder = Path(SOURCE_DIR) / code
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _unique_course_path(folder, name: str):
    from pathlib import Path
    dest = Path(folder) / Path(name).name
    if not dest.exists():
        return dest
    return dest.with_name(f"{dest.stem}_{int(time.time())}{dest.suffix}")


def _register_course_file(path, subject: str, *, status: str = "archived",
                          use_rag: bool = False) -> str:
    """Macht auch nicht indexierbare/Fallback-Dateien im Kurs-Cockpit sichtbar."""
    from ragapp.config import PROJECT_ROOT
    from ragapp.ingestion.dedup import doc_id_for
    try:
        rel = str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except Exception:  # noqa: BLE001
        rel = str(path)
    doc_id = doc_id_for(rel)
    if doc_id not in {d["doc_id"] for d in manifest.list_documents()}:
        raw = path.read_bytes()
        manifest.upsert_document(
            doc_id=doc_id, content_hash=hashlib.sha256(raw).hexdigest(),
            source_path=rel, filename=path.name, subject=subject,
            filetype=path.suffix.lstrip(".").lower() or "bin",
            num_chunks=0, num_questions=0, char_count=len(raw),
            status=status, use_rag=use_rag)
    return doc_id


def enqueue_index_retry(path, subject: Optional[str], *, error: str = "",
                        doc_id: Optional[str] = None) -> str:
    """Merkt fehlgeschlagene Indexierung persistent und idempotent."""
    from pathlib import Path
    from ragapp.config import PROJECT_ROOT
    source = Path(path)
    try:
        source_path = str(source.resolve().relative_to(PROJECT_ROOT.resolve()))
    except Exception:  # noqa: BLE001
        source_path = str(source.resolve())
    return manifest.enqueue_index_retry(
        source_path=source_path, subject=(subject or "").strip() or None,
        doc_id=doc_id, use_rag=True, error=(error or "")[:2000] or None)


def backfill_failed_index_jobs() -> int:
    """Übernimmt Fehler aus älteren App-Versionen einmalig in die Warteschlange."""
    existing = {
        (j["source_path"], j.get("subject") or "")
        for j in manifest.list_index_retry_jobs(include_done=True, limit=5000)
    }
    added = 0
    # list_documents() liefert sqlite3.Row – die haben kein .get().
    for raw in manifest.list_documents():
        doc = dict(raw)
        if doc.get("status") != "error" or not doc.get("use_rag"):
            continue
        key = (doc.get("source_path"), doc.get("subject") or "")
        if key in existing or not key[0]:
            continue
        manifest.enqueue_index_retry(
            source_path=key[0], subject=key[1], doc_id=doc.get("doc_id"),
            error="Frühere fehlgeschlagene Indexierung")
        added += 1
    return added


def enqueue_ocr_jobs() -> int:
    """Macht leere/partielle Scan-PDFs automatisch zu verarbeitbaren Jobs."""
    from pathlib import Path
    from ragapp.config import PROJECT_ROOT
    existing = {
        (j["source_path"], j.get("subject") or "")
        for j in manifest.list_index_retry_jobs(include_done=False, limit=5000)
    }
    added = 0
    for doc in manifest.documents_needing_ocr():
        if not doc.get("use_rag"):
            continue
        source_path = doc.get("source_path") or ""
        key = (source_path, doc.get("subject") or "")
        path = Path(source_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if not source_path or not path.is_file() or key in existing:
            continue
        manifest.enqueue_index_retry(
            source_path=source_path, subject=doc.get("subject"),
            doc_id=doc.get("doc_id"), use_rag=True, job_type="ocr",
            error=(
                f"OCR ausstehend: {int(doc.get('ocr_partial_pages') or 0)} "
                "unvollständige Seite(n)"
                if doc.get("reason") == "partial"
                else "OCR ausstehend: kein verwertbarer Text"
            ))
        added += 1
    return added


def reconcile_indexes(*, rebuild_bm25: bool = True,
                      enqueue_repairs: bool = True,
                      remove_orphans: bool = True) -> dict:
    """Gleicht Manifest, Chroma und BM25 dokumentweise ab."""
    from collections import Counter
    from pathlib import Path
    from ragapp.config import PROJECT_ROOT
    from ragapp.retrieval.vectorstore import get_vectorstore
    from ragapp.retrieval.bm25_index import get_bm25, rebuild_bm25_from_store

    store = get_vectorstore()
    chunks = store.get_all_chunks()
    vector_counts = Counter(
        (c.get("meta") or {}).get("doc_id") for c in chunks
        if (c.get("meta") or {}).get("doc_id")
    )
    bm25 = get_bm25()
    bm25_counts = Counter(
        (meta or {}).get("doc_id") for meta in (bm25.metas or [])
        if (meta or {}).get("doc_id")
    )
    documents = [dict(d) for d in manifest.list_documents()]
    known = {d["doc_id"] for d in documents}
    mismatches = []
    queued = 0
    bm25_dirty = False
    for doc in documents:
        if not doc.get("use_rag"):
            continue
        expected = int(doc.get("num_chunks") or 0)
        vector_n = int(vector_counts.get(doc["doc_id"], 0))
        bm25_n = int(bm25_counts.get(doc["doc_id"], 0))
        if vector_n != expected:
            mismatches.append({
                "doc_id": doc["doc_id"], "filename": doc["filename"],
                "manifest": expected, "chroma": vector_n, "bm25": bm25_n,
            })
            if enqueue_repairs:
                path = Path(doc.get("source_path") or "")
                if not path.is_absolute():
                    path = PROJECT_ROOT / path
                if path.is_file():
                    enqueue_index_retry(
                        path, doc.get("subject"),
                        error=(
                            f"Index-Abgleich: Manifest {expected}, "
                            f"Chroma {vector_n} Chunks"),
                        doc_id=doc["doc_id"])
                    queued += 1
        if bm25_n != vector_n:
            bm25_dirty = True
    orphan_ids = [
        c["id"] for c in chunks
        if (c.get("meta") or {}).get("doc_id")
        and (c.get("meta") or {}).get("doc_id") not in known
    ]
    orphan_chunks = len(orphan_ids)
    if remove_orphans and orphan_ids:
        store.delete_by_ids(orphan_ids)
        bm25_dirty = True
    if rebuild_bm25 and bm25_dirty:
        rebuild_bm25_from_store()
    return {
        "documents": len(documents), "mismatches": mismatches,
        "queued": queued, "bm25_rebuilt": bool(rebuild_bm25 and bm25_dirty),
        "orphan_chunks": orphan_chunks,
        "orphan_chunks_removed": orphan_chunks if remove_orphans else 0,
    }


def retry_index_queue(*, job_ids: Optional[list[str]] = None,
                      force: bool = False, limit: int = 5,
                      progress=None) -> dict:
    """Verarbeitet fällige Index-Jobs mit exponentiellem Backoff."""
    from pathlib import Path
    from ragapp.config import PROJECT_ROOT
    from ragapp.ingestion.pipeline import ingest_file

    now = time.time()
    jobs = manifest.list_index_retry_jobs(
        due_before=None if force else now, limit=max(limit, 100 if job_ids else limit))
    wanted = set(job_ids or [])
    if wanted:
        jobs = [j for j in jobs if j["job_id"] in wanted]
    jobs = jobs[:max(1, int(limit))]
    result = {"processed": 0, "ok": 0, "failed": 0, "errors": []}
    for i, job in enumerate(jobs, 1):
        if not manifest.claim_index_retry_job(job["job_id"], force=force):
            continue
        result["processed"] += 1
        attempts = int(job.get("attempts") or 0) + 1
        lease_stop = threading.Event()

        def _heartbeat(job_id=job["job_id"]) -> None:
            while not lease_stop.wait(60):
                if not manifest.heartbeat_index_retry_job(job_id):
                    return

        lease_thread = threading.Thread(
            target=_heartbeat, name=f"index-lease-{job['job_id']}",
            daemon=True)
        lease_thread.start()
        source = Path(job["source_path"])
        if not source.is_absolute():
            source = PROJECT_ROOT / source
        if progress:
            progress(f"Indexiere {source.name} erneut ({i}/{len(jobs)})")
        try:
            if not source.is_file():
                raise FileNotFoundError(f"Datei fehlt: {source}")
            ingest = ingest_file(
                source, subject=job.get("subject"), force=True,
                use_rag=bool(job.get("use_rag", 1)))
            status = ingest.get("status")
            good = {"ok", "unchanged", "duplicate", "duplicate_chunks"}
            if job.get("job_type") == "ocr":
                good = {"ok", "unchanged"}
            if status not in good:
                raise RuntimeError(ingest.get("error") or f"Status: {status}")
        except Exception as exc:  # noqa: BLE001
            delay = min(24 * 3600, 60 * (2 ** min(attempts - 1, 10)))
            manifest.update_index_retry_job(
                job["job_id"], status="failed", attempts=attempts,
                next_attempt_at=now + delay, last_error=str(exc)[:2000])
            result["failed"] += 1
            result["errors"].append(f"{source.name}: {exc}")
        else:
            if status in {"duplicate", "duplicate_chunks"} and job.get("doc_id"):
                manifest.set_document_index_state(
                    job["doc_id"], status="duplicate", use_rag=False)
            manifest.update_index_retry_job(
                job["job_id"], status="done", attempts=attempts,
                next_attempt_at=0, last_error=None)
            result["ok"] += 1
        finally:
            lease_stop.set()
            lease_thread.join(timeout=1)
    return result


_RECOVERY_THREAD = None
_RECOVERY_STARTED = False
_RECOVERY_LOCK = threading.Lock()


def start_recovery_worker() -> bool:
    """Startet einmalig einen schonenden Hintergrundlauf für Index/OCR-Reparatur."""
    global _RECOVERY_THREAD, _RECOVERY_STARTED
    import os
    if os.environ.get("RAG_AUTO_RECOVERY", "1") != "1":
        return False

    def _run() -> None:
        cycle = 0
        once = os.environ.get("RAG_RECOVERY_ONCE") == "1"
        while True:
            try:
                backfill_failed_index_jobs()
                enqueue_ocr_jobs()
                # Vollabgleich beim Start und danach alle 15 Minuten. Fällige
                # Retry-Jobs werden jede Minute in kleinen Batches abgearbeitet.
                if cycle % 15 == 0:
                    reconcile_indexes(
                        rebuild_bm25=True, enqueue_repairs=True)
                retry_index_queue(limit=3)
            except Exception:  # noqa: BLE001
                # Selbstheilung darf den normalen App-Betrieb niemals verhindern.
                pass
            if once:
                return
            cycle += 1
            time.sleep(60)

    with _RECOVERY_LOCK:
        if _RECOVERY_STARTED:
            return False
        _RECOVERY_THREAD = threading.Thread(
            target=_run, name="rag-index-recovery", daemon=True)
        _RECOVERY_STARTED = True
        _RECOVERY_THREAD.start()
    return True


def add_course_material(subject: str, *, text: Optional[str] = None,
                        title: Optional[str] = None,
                        file_bytes: Optional[bytes] = None,
                        filename: Optional[str] = None,
                        image_bytes: Optional[bytes] = None) -> dict:
    """Datei, Foto oder Notiz in den Fach-Ordner legen und als Unterlage sichtbar machen.

    Kein Umweg über die Ingestion-Experten-UI: Datei landet unter SOURCE_DIR/Fach
    und wird dort eingelesen, sodass das Kurs-Cockpit die neue Unterlage zählt.
    """
    from ragapp.ingestion.loaders import SUPPORTED_EXTENSIONS
    from ragapp.ingestion.pipeline import ingest_file

    code = (subject or "").strip()
    if not code:
        return {"status": "no_subject", "path": None, "doc_id": None, "capture": None}
    folder = ensure_course_folder(code)
    body = (text or "").strip()
    saved: list = []
    if file_bytes and filename:
        dest = _unique_course_path(folder, filename)
        dest.write_bytes(file_bytes)
        saved.append(dest)
    if image_bytes:
        dest = _unique_course_path(folder, "tafel.jpg")
        dest.write_bytes(image_bytes)
        saved.append(dest)
    if body:
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_",
                      (title or body.splitlines()[0] or "notiz")[:40]).strip("_")
        dest = _unique_course_path(folder, f"{slug or 'notiz'}.md")
        heading = (title or slug or "Notiz").strip()
        dest.write_text(f"# {heading}\n\n{body}\n", encoding="utf-8")
        saved.append(dest)
    if not saved:
        return {"status": "empty", "path": None, "doc_id": None, "capture": None}

    ingest = {"status": "ok"}
    doc_id = None
    primary = saved[-1]
    for path in saved:
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            doc_id = _register_course_file(path, code)
            continue
        try:
            ingest = ingest_file(path, subject=code)
        except Exception as exc:  # noqa: BLE001
            ingest = {"status": "error", "error": str(exc), "file": path.name}
        # ingest_file registriert Erfolgsfälle selbst. Bei Modell-/Indexfehlern
        # bleibt die Originaldatei trotzdem als ehrliche archivierte Unterlage.
        doc_id = _register_course_file(
            path, code,
            status="error" if ingest.get("status") == "error" else "archived",
            use_rag=ingest.get("status") == "error")
        if ingest.get("status") == "error":
            enqueue_index_retry(
                path, code, error=ingest.get("error") or "Indexierung fehlgeschlagen",
                doc_id=doc_id)
    capture = capture_lecture(body, subject=code, title=title) if body else None
    return {
        "status": ingest.get("status") or "ok",
        "path": str(primary),
        "doc_id": doc_id,
        "ingest": ingest,
        "capture": capture,
    }


def scan_inbox_once(progress=None, *, subject: Optional[str] = None) -> dict:
    """Liest neue Dateien aus dem Inbox-Ordner einmalig ein.

    Mit ``subject`` wandern die Dateien zuerst in den Fach-Ordner, damit sie
    im Kurs-Cockpit als Unterlagen dieses Fachs erscheinen.
    """
    import shutil
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
    dest_dir = ensure_course_folder(subject) if subject else None
    for i, path in enumerate(files, 1):
        if progress:
            progress(f"Lese {path.name} ({i}/{len(files)})")
        work = path
        if dest_dir is not None:
            dest = _unique_course_path(dest_dir, path.name)
            shutil.move(str(path), str(dest))
            work = dest
        try:
            res = ingest_file(work, subject=subject)
            if res.get("status") in ("ok", "skipped", "duplicate"):
                ok += 1
                if subject and res.get("status") == "duplicate":
                    # Physische Kopie im Kursordner bleibt dort sichtbar, auch wenn
                    # ihr Inhalt bereits unter einem anderen Fach indexiert ist.
                    _register_course_file(work, subject)
            else:
                if subject:
                    retryable = res.get("status") == "error"
                    doc_id = _register_course_file(
                        work, subject, status=str(res.get("status") or "error"),
                        use_rag=retryable)
                    if retryable:
                        enqueue_index_retry(
                            work, subject,
                            error=str(res.get("error") or res.get("status")),
                            doc_id=doc_id)
                errors.append(f"{path.name}: {res.get('status')}")
        except Exception as exc:  # noqa: BLE001
            if subject:
                doc_id = _register_course_file(
                    work, subject, status="error", use_rag=True)
                enqueue_index_retry(work, subject, error=str(exc), doc_id=doc_id)
            errors.append(f"{path.name}: {exc}")
    return {"scanned": len(files), "ok": ok, "errors": errors}


def _next_lecture(slots: list[dict], *, today: Optional[date] = None) -> Optional[dict]:
    """Nächster Vorlesungstermin ab heute (Wochentag + Uhrzeit)."""
    if not slots:
        return None
    today = today or date.today()
    wd = today.weekday()
    now_hm = time.strftime("%H:%M")
    ranked: list[tuple[int, dict]] = []
    for s in slots:
        slot_wd = int(s["weekday"])
        delta = (slot_wd - wd) % 7
        if delta == 0 and str(s.get("start_time") or "") <= now_hm:
            delta = 7
        ranked.append((delta, s))
    ranked.sort(key=lambda x: (x[0], x[1].get("start_time") or ""))
    delta, slot = ranked[0]
    when = today + timedelta(days=delta)
    return {**slot, "date": when.isoformat(), "days_ahead": delta}


def recommend_course_action(*, due_cards: int, doc_count: int,
                            exam_days: Optional[int],
                            has_plan: bool) -> str:
    """Nächste Kursaktion: lernen | planen | Unterlagen | Prüfung."""
    if due_cards > 0:
        return "lernen"
    if doc_count <= 0:
        return "Unterlagen"
    if exam_days is not None and 0 <= exam_days <= 14:
        return "Prüfung"
    if not has_plan:
        return "planen"
    return "lernen"


def course_snapshot(subject: str) -> dict:
    """Ein Blick pro Fach: Termin, Stoff, Lernstand, nächste Aktion."""
    from ragapp import analytics

    exam = manifest.get_exam(subject) or {}
    exam_date = exam.get("exam_date")
    days = planner.days_to_exam(exam_date) if exam_date else None
    evenings = evenings_until_exam(exam_date)
    due = manifest.due_breakdown(subject=subject)
    due_cards = int(due["due_learning"]) + int(due["due_review"]) + int(due["due_new"])
    ready = analytics.subject_readiness(subject)
    weak = analytics.mastery_by_topic(subject, limit=3)
    docs = [dict(d) for d in manifest.list_documents() if d["subject"] == subject]
    indexed = [
        d for d in docs
        if d.get("use_rag") and int(d.get("num_chunks") or 0) > 0
    ]
    slots = manifest.list_timetable(subject=subject)
    next_lec = _next_lecture(slots)
    plans = [p for p in manifest.list_study_plans()
             if p.get("subject") == subject and p.get("status") == "active"]
    action = recommend_course_action(
        due_cards=due_cards, doc_count=len(indexed),
        exam_days=days, has_plan=bool(plans))
    return {
        "subject": subject,
        "exam_date": exam_date,
        "days_to_exam": days,
        "evenings": (evenings or {}).get("evenings"),
        "due_cards": due_cards,
        "readiness_pct": ready.get("readiness_pct", 0),
        "retention_pct": ready.get("retention_pct", 0),
        "coverage_pct": ready.get("coverage_pct"),
        "weak_topics": [
            {"topic": w.get("topic"), "mastery_pct": w.get("mastery_pct")}
            for w in weak
        ],
        "doc_count": len(docs),
        "next_lecture": next_lec,
        "next_action": action,
    }


def is_inbox_subject(subject: Optional[str]) -> bool:
    """Inbox ist Ablage, kein Kurs."""
    return (subject or "").strip().lower() == "inbox"


def is_fixture_subject(subject: Optional[str]) -> bool:
    """QA-Fixture (Livetest), kein Semesterkurs – im Cockpit ausblenden, nicht löschen."""
    s = (subject or "").strip().lower()
    return s == "livetest" or s.startswith("livetest-") or s.startswith("livetest_")


# Kurze Endstücke, die in echten Kürzeln vorkommen – nicht als Import-Abbruch werten.
_SUBJECT_TAIL_OK = {
    "ai", "bio", "bwl", "chem", "db", "ds", "dsa", "ects", "hr", "inf", "it",
    "ki", "mathe", "ml", "nlp", "ocr", "or", "os", "pdf", "phys", "pm", "pr",
    "rag", "se", "sose", "sql", "ui", "ux", "vwl", "wifi", "wise", "wiwi",
}


def looks_truncated_subject(subject: Optional[str]) -> bool:
    """Abgeschnittener Importname, z. B. ``IT-Recht und IT-Comp`` statt Compliance."""
    s = (subject or "").strip()
    if len(s) < 12:
        return False
    if not re.search(r"\b(?:und|oder|/)\s+\S+$", s):
        return False
    last = re.split(r"[\s/]+", s)[-1]
    tail = last.split("-")[-1]
    if not tail.isalpha() or len(tail) > 4:
        return False
    return tail.lower() not in _SUBJECT_TAIL_OK


def is_placeholder_subject(subject: Optional[str]) -> bool:
    """Kein echter Kurs: Inbox, reine Modulnummer, abgeschnittener Importcode."""
    s = (subject or "").strip()
    if not s or is_inbox_subject(s):
        return True
    if s.isdigit():
        return True
    if s.count("(") != s.count(")"):
        return True
    if s.endswith(("(", "-", "–", "/", "&")):
        return True
    if looks_truncated_subject(s):
        return True
    return False


def is_exam_fragment(exam: dict) -> bool:
    """Importrest: Platzhalter-Kürzel ohne Klausurdatum."""
    if exam.get("exam_date"):
        return False
    return is_placeholder_subject(exam.get("subject"))


def list_import_remnant_exams() -> list[dict]:
    """Klausur-Einträge, die vom Semesterimport als unvollständige Reste übrig sind."""
    from ragapp import manifest
    return [e for e in manifest.list_exams() if is_exam_fragment(e)]


def purge_import_remnant_exams() -> int:
    """Löscht nur Importreste (kein Datum, Platzhaltername). Echte Kurse bleiben."""
    from ragapp import manifest
    rows = list_import_remnant_exams()
    for e in rows:
        subj = (e.get("subject") or "").strip()
        if subj:
            manifest.delete_exam(subj)
    return len(rows)


def course_cockpit_bucket(snapshot: dict, *, has_cards: bool) -> str:
    """Kurskarte auf Organisation: ``active``, ``stoff``, ``import`` oder ``skip``.

    Active = Karten, fällige Karten oder Klausur in den nächsten 14 Tagen.
    Stoff = Unterlagen ohne Karten. Import = nur Name/Termin aus dem Semesterimport.
    Inbox-Dokumente gehören nicht ins Kurs-Cockpit.
    """
    if is_inbox_subject(snapshot.get("subject")):
        return "skip"
    if is_fixture_subject(snapshot.get("subject")):
        return "skip"
    if is_placeholder_subject(snapshot.get("subject")):
        return "skip"
    days = snapshot.get("days_to_exam")
    exam_soon = days is not None and 0 <= int(days) <= 14
    if has_cards or int(snapshot.get("due_cards") or 0) > 0 or exam_soon:
        return "active"
    if int(snapshot.get("doc_count") or 0) > 0:
        return "stoff"
    return "import"


def subjects_needing_lernset() -> list[str]:
    """Fächer mit Unterlagen, aber ohne Karten – kein Fixture, Inbox oder Importrest."""
    study = set(manifest.study_subjects())
    seen: list[str] = []
    for raw in manifest.list_documents():
        subj = (dict(raw).get("subject") or "").strip()
        if not subj or subj in study or subj in seen:
            continue
        if is_fixture_subject(subj) or is_placeholder_subject(subj) or is_inbox_subject(subj):
            continue
        seen.append(subj)
    return seen


def plain_study_snippet(text: Optional[str], *, limit: int = 42) -> str:
    """Kürzt Aufgabentext für Buttons: kein KaTeX, kein Umbruch mitten in $...$."""
    raw = (text or "").strip()
    if not raw:
        return ""
    raw = re.sub(r"\$\$[\s\S]*?\$\$", " ", raw)
    raw = re.sub(r"\$[^$]*\$", " ", raw)
    raw = re.sub(r"\\\[[\s\S]*?\\\]", " ", raw)
    raw = re.sub(r"\\\([\s\S]*?\\\)", " ", raw)
    raw = re.sub(r"[_*]{1,2}", "", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    if len(raw) > limit:
        return raw[:limit].rstrip() + "…"
    return raw

