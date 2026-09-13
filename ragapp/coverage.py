"""
Prüfungsstoff-Abdeckung: Lernziele gegen Unterlagen, Karten, Übungen, Mastery.
==============================================================================
Rein deterministisch (Token-Überlappung), ohne LLM zur Laufzeit. Status-Leiter
je Ziel: fehlend → Dokument → Karte → Übung → sitzt.
"""
from __future__ import annotations

import re
from typing import Optional

from ragapp import analytics, manifest

STATUSES = ("fehlend", "Dokument", "Karte", "Übung", "sitzt")

_STOP = {
    "die", "der", "das", "und", "oder", "ein", "eine", "einen", "einem", "einer",
    "von", "im", "in", "zu", "den", "des", "dem", "mit", "auf", "fuer", "für",
    "ist", "sind", "kann", "koennen", "können", "studierende", "studierenden",
    "lernziel", "thema", "themen", "sowie", "auch", "nach", "bei", "aus",
    "sich", "werden", "wird", "dass", "als", "am", "an", "ohne", "nicht",
}

_TOKEN_RE = re.compile(r"[a-zA-ZäöüÄÖÜß0-9]{3,}")


def _tokens(text: str) -> set[str]:
    words = {w.lower() for w in _TOKEN_RE.findall(text or "")}
    return {w for w in words if w not in _STOP}


def _matches(goal_tokens: set[str], haystack: str) -> bool:
    other = _tokens(haystack)
    if not goal_tokens or not other:
        return False
    inter = goal_tokens & other
    if any(len(t) >= 8 for t in inter):
        return True
    return len(inter) >= 2


def _haystack_doc(doc: dict) -> str:
    return " ".join(str(doc.get(k) or "") for k in ("filename", "subject", "tags", "source_path"))


def _haystack_card(card: dict) -> str:
    return " ".join(str(card.get(k) or "") for k in ("front", "topic", "answer", "deck"))


def _haystack_problem(prob: dict) -> str:
    return " ".join(str(prob.get(k) or "") for k in
                    ("topic", "problem_text", "final_answer", "source_excerpt", "kind"))


def _sitzt(card: dict, target_reps: int) -> bool:
    return int(card.get("reps") or 0) >= target_reps and not card.get("suspended")


def coverage_for_subject(subject: str) -> list[dict]:
    """Je persistiertem Lernziel den höchsten Abdeckungsstatus.

    Ohne gespeicherte Ziele: leere Liste (keine halluzinierten Themen).
    """
    subject = (subject or "").strip()
    if not subject:
        return []
    goals = manifest.list_learning_goals(subject)
    if not goals:
        return []
    docs = [dict(d) for d in manifest.list_documents() if d["subject"] == subject]
    cards = manifest.list_cards(subject=subject)
    problems = manifest.list_practice_problems(subject=subject)
    target = analytics._target_reps()
    out: list[dict] = []
    for g in goals:
        tokens = _tokens(g["text"])
        hit_docs = [d for d in docs if _matches(tokens, _haystack_doc(d))]
        hit_cards = [c for c in cards if _matches(tokens, _haystack_card(c))]
        hit_probs = [p for p in problems if _matches(tokens, _haystack_problem(p))]
        sitzt_cards = [c for c in hit_cards if _sitzt(c, target)]
        if sitzt_cards:
            status = "sitzt"
        elif hit_probs:
            status = "Übung"
        elif hit_cards:
            status = "Karte"
        elif hit_docs:
            status = "Dokument"
        else:
            status = "fehlend"
        out.append({
            "goal_id": g["goal_id"],
            "subject": subject,
            "text": g["text"],
            "status": status,
            "doc_ids": [d["doc_id"] for d in hit_docs],
            "card_ids": [c["card_id"] for c in hit_cards],
            "problem_ids": [p["problem_id"] for p in hit_probs],
        })
    return out


def coverage_start_action(row: dict) -> dict:
    """Klickziel für eine Lücke: Dokument, Lernset oder Übung."""
    status = row.get("status")
    if status == "sitzt":
        return {"kind": None, "label": None}
    if status == "fehlend":
        return {"kind": "dokument", "label": "Unterlage holen"}
    if status == "Dokument":
        return {"kind": "lernset", "label": "Lernset starten"}
    if status == "Karte":
        return {"kind": "uebung", "label": "Übung starten"}
    return {"kind": "lernen", "label": "Lücke üben"}


def coverage_gaps(subject: str, *, statuses: Optional[tuple[str, ...]] = None) -> list[dict]:
    """Lücken: standardmäßig alles unter sitzt."""
    want = set(statuses or ("fehlend", "Dokument", "Karte", "Übung"))
    return [row for row in coverage_for_subject(subject) if row["status"] in want]
