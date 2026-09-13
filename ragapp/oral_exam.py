"""Lokales Sitzungsmodell für mündliche Prüfungen.

Schriftliche ``exam_attempts`` bleiben unberührt. Fragen, Nachfragen,
Transkripte und Teilpunkte liegen als JSON-Blob in SQLite.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Optional

from ragapp import manifest


def _decode(row) -> Optional[dict]:
    if not row:
        return None
    data = dict(row)
    try:
        payload = json.loads(data.pop("payload_json") or "{}")
    except Exception:  # noqa: BLE001
        payload = {}
    return {**data, **payload}


def create_session(subject: Optional[str] = None,
                   questions: Optional[list[dict]] = None) -> dict:
    sid = uuid.uuid4().hex[:16]
    now = time.time()
    payload = {
        "questions": [
            {
                "question": str(q.get("question") or "").strip(),
                "reference": str(q.get("reference") or "").strip(),
                "followups": list(q.get("followups") or []),
                "transcript": q.get("transcript"),
                "partial_points": q.get("partial_points"),
            }
            for q in (questions or []) if str(q.get("question") or "").strip()
        ],
        "current_index": 0,
    }
    with manifest._connect() as conn:
        conn.execute(
            "INSERT INTO oral_exam_sessions "
            "(session_id, subject, status, payload_json, total_pct, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (sid, subject, "active", json.dumps(payload, ensure_ascii=False),
             None, now, now))
    return get_session(sid)


def get_session(session_id: str) -> Optional[dict]:
    with manifest._connect() as conn:
        row = conn.execute(
            "SELECT * FROM oral_exam_sessions WHERE session_id=?",
            (session_id,)).fetchone()
    return _decode(row)


def list_sessions(subject: Optional[str] = None,
                  limit: int = 20) -> list[dict]:
    sql = "SELECT * FROM oral_exam_sessions"
    args: list = []
    if subject:
        sql += " WHERE subject=?"
        args.append(subject)
    sql += " ORDER BY updated_at DESC LIMIT ?"
    args.append(max(1, int(limit)))
    with manifest._connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [_decode(row) for row in rows]


def _save(session: dict) -> dict:
    payload = {
        "questions": session.get("questions") or [],
        "current_index": int(session.get("current_index") or 0),
    }
    with manifest._connect() as conn:
        conn.execute(
            "UPDATE oral_exam_sessions SET status=?, payload_json=?, total_pct=?, "
            "updated_at=? WHERE session_id=?",
            (session.get("status") or "active",
             json.dumps(payload, ensure_ascii=False),
             session.get("total_pct"), time.time(), session["session_id"]))
    return get_session(session["session_id"])


def add_question(session_id: str, question: str, *,
                 reference: str = "") -> dict:
    session = get_session(session_id)
    if not session:
        raise KeyError(session_id)
    text = (question or "").strip()
    if not text:
        return session
    session["questions"].append({
        "question": text, "reference": (reference or "").strip(),
        "followups": [], "transcript": None, "partial_points": None,
    })
    return _save(session)


def record_answer(session_id: str, index: int, transcript: str, *,
                  followup: Optional[str] = None,
                  partial_points: Optional[int] = None) -> dict:
    session = get_session(session_id)
    if not session:
        raise KeyError(session_id)
    item = session["questions"][int(index)]
    item["transcript"] = (transcript or "").strip()
    if followup:
        item.setdefault("followups", []).append({
            "question": followup.strip(), "transcript": None,
            "partial_points": None,
        })
    if partial_points is not None:
        item["partial_points"] = max(0, min(100, int(partial_points)))
    session["current_index"] = min(int(index) + 1, len(session["questions"]))
    return _save(session)


def finish_session(session_id: str, total_pct: Optional[int] = None) -> dict:
    session = get_session(session_id)
    if not session:
        raise KeyError(session_id)
    session["status"] = "done"
    if total_pct is None:
        points = [
            q["partial_points"] for q in session["questions"]
            if q.get("partial_points") is not None
        ]
        total_pct = round(sum(points) / len(points)) if points else None
    session["total_pct"] = (
        max(0, min(100, int(total_pct))) if total_pct is not None else None)
    return _save(session)
