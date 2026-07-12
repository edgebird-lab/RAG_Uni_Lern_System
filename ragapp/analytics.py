"""
Lern-Analytik (liest das ``review_log`` aus)
============================================
Das ``review_log`` wird bei jeder Wiederholung geschrieben, aber bislang nie
gelesen. Dieses Modul verwandelt es (zusammen mit dem SM-2-Zustand in
``review_items``) in die Kennzahlen, die fuer die Klausurvorbereitung zaehlen:
Themen-Mastery, Retention/Trefferquote-Trend, Streak, Faelligkeits-Prognose und
"Dauerpatzer" (Leeches). Reine Leseoperationen, offline, ohne LLM.

Alle Funktionen sind gegen ein leeres/frisches Log robust (geben 0/leer zurueck).
"""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from typing import Iterator, Optional

from ragapp.config import MANIFEST_DB, settings

# Ratings (Spiegel von study.py, hier ohne Import gegen Zyklen)
_GEWUSST = 2


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(str(MANIFEST_DB))
    c.row_factory = sqlite3.Row
    try:
        yield c
    finally:
        c.close()


def _target_reps() -> int:
    return max(1, int(getattr(settings, "MASTERY_TARGET_REPS", 4)))


def _leech_threshold() -> int:
    return max(1, int(getattr(settings, "LEECH_LAPSES_THRESHOLD", 4)))


def _day_start(now: Optional[float] = None) -> float:
    lt = time.localtime(now if now is not None else time.time())
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))


def _day_key(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def _subj_clause(subject: Optional[str], col: str = "subject") -> tuple[str, list]:
    return (f" AND {col}=?", [subject]) if subject else ("", [])


# --------------------------------------------------------------------------- #
# Ueberblick
# --------------------------------------------------------------------------- #
def overview(subject: Optional[str] = None) -> dict:
    """Kernkennzahlen: Karten gesamt/faellig/neu/gelernt/sitzt, heute geuebt,
    Treffer 7 Tage, Streak, Leeches."""
    now = time.time()
    tgt = _target_reps()
    lt = _leech_threshold()
    sc, sa = _subj_clause(subject)
    base = "FROM review_items WHERE suspended=0 AND use_flashcard=1" + sc
    with _conn() as c:
        def n(extra: str, a: list = []) -> int:
            return c.execute(f"SELECT COUNT(*) AS x {base}{extra}", sa + a).fetchone()["x"]
        total = n("")
        due = n(" AND due<=?", [now])
        neu = n(" AND reps=0")
        gelernt = n(" AND reps>0")
        sitzt = n(" AND reps>=?", [tgt])
        leeches = n(" AND lapses>=?", [lt])

        wk = _day_start(now) - 6 * 86400
        lc, la = _subj_clause(subject)
        row = c.execute(
            "SELECT COUNT(*) AS r, SUM(CASE WHEN rating>=? THEN 1 ELSE 0 END) AS g "
            "FROM review_log WHERE reviewed_at>=?" + lc, [_GEWUSST, wk] + la).fetchone()
        rev_7d = row["r"] or 0
        acc_7d = round(100 * (row["g"] or 0) / rev_7d) if rev_7d else None
        today = c.execute(
            "SELECT COUNT(*) AS r FROM review_log WHERE reviewed_at>=?" + lc,
            [_day_start(now)] + la).fetchone()["r"] or 0
    return {
        "total": total, "due": due, "neu": neu, "gelernt": gelernt, "sitzt": sitzt,
        "mastery_pct": round(100 * sitzt / total) if total else 0,
        "leeches": leeches, "reviews_today": today, "reviews_7d": rev_7d,
        "accuracy_7d": acc_7d, "streak": streak(subject),
    }


def streak(subject: Optional[str] = None) -> int:
    """Zusammenhaengende Tage (bis heute oder gestern) mit mindestens einer
    Wiederholung."""
    sc, sa = _subj_clause(subject)
    with _conn() as c:
        rows = c.execute(
            "SELECT DISTINCT reviewed_at FROM review_log WHERE 1=1" + sc, sa).fetchall()
    days = {_day_key(r["reviewed_at"]) for r in rows if r["reviewed_at"]}
    if not days:
        return 0
    n = 0
    cur = _day_start()
    # Startet die Zaehlung heute (falls heute geuebt) sonst gestern.
    if _day_key(cur) not in days:
        cur -= 86400
        if _day_key(cur) not in days:
            return 0
    while _day_key(cur) in days:
        n += 1
        cur -= 86400
    return n


# --------------------------------------------------------------------------- #
# Trend / Mastery / Prognose
# --------------------------------------------------------------------------- #
def retention_trend(days: int = 30, subject: Optional[str] = None) -> list[dict]:
    """Pro Tag der letzten ``days``: Anzahl Wiederholungen + Treffer-% (Anteil
    'gewusst'). Tage ohne Uebung erscheinen mit 0 Wiederholungen."""
    now = time.time()
    start = _day_start(now) - (days - 1) * 86400
    sc, sa = _subj_clause(subject)
    with _conn() as c:
        rows = c.execute(
            "SELECT reviewed_at, rating FROM review_log WHERE reviewed_at>=?" + sc,
            [start] + sa).fetchall()
    agg: dict[str, list[int]] = {}
    for r in rows:
        k = _day_key(r["reviewed_at"])
        a = agg.setdefault(k, [0, 0])
        a[0] += 1
        if (r["rating"] or 0) >= _GEWUSST:
            a[1] += 1
    out = []
    for i in range(days):
        d = _day_key(start + i * 86400)
        rev, good = agg.get(d, [0, 0])
        out.append({"tag": d, "wiederholungen": rev,
                    "treffer_pct": round(100 * good / rev) if rev else None})
    return out


def mastery_by_subject() -> list[dict]:
    """Pro Fach: Karten, 'sitzt'-Anteil (Mastery %), faellig, Ø-Leichtigkeit."""
    now = time.time()
    tgt = _target_reps()
    with _conn() as c:
        rows = c.execute(
            "SELECT subject, COUNT(*) AS cards, "
            "SUM(CASE WHEN reps>=? THEN 1 ELSE 0 END) AS sitzt, "
            "SUM(CASE WHEN due<=? THEN 1 ELSE 0 END) AS due, "
            "AVG(ease) AS avg_ease, SUM(lapses) AS lapses "
            "FROM review_items WHERE suspended=0 AND use_flashcard=1 AND subject IS NOT NULL "
            "GROUP BY subject ORDER BY subject", [tgt, now]).fetchall()
    out = []
    for r in rows:
        cards = r["cards"] or 0
        out.append({
            "subject": r["subject"], "cards": cards, "sitzt": r["sitzt"] or 0,
            "due": r["due"] or 0, "lapses": r["lapses"] or 0,
            "avg_ease": round(r["avg_ease"] or 0, 2),
            "mastery_pct": round(100 * (r["sitzt"] or 0) / cards) if cards else 0,
        })
    return out


def subject_mastery(subject: str) -> float:
    """Mastery eines Fachs als 0..1 (Anteil Karten mit reps>=Ziel). Fuer den Planer."""
    tgt = _target_reps()
    with _conn() as c:
        r = c.execute(
            "SELECT COUNT(*) AS cards, SUM(CASE WHEN reps>=? THEN 1 ELSE 0 END) AS sitzt "
            "FROM review_items WHERE suspended=0 AND use_flashcard=1 AND subject=?",
            [tgt, subject]).fetchone()
    cards = r["cards"] or 0
    return (r["sitzt"] or 0) / cards if cards else 0.0


def mastery_by_topic(subject: str, limit: int = 40) -> list[dict]:
    """Pro Thema eines Fachs: Karten, Mastery %, Patzer - fuer die Themen-Heatmap."""
    tgt = _target_reps()
    with _conn() as c:
        rows = c.execute(
            "SELECT COALESCE(topic,'(ohne Thema)') AS topic, COUNT(*) AS cards, "
            "SUM(CASE WHEN reps>=? THEN 1 ELSE 0 END) AS sitzt, SUM(lapses) AS lapses "
            "FROM review_items WHERE suspended=0 AND use_flashcard=1 AND subject=? "
            "GROUP BY COALESCE(topic,'(ohne Thema)') ORDER BY sitzt*1.0/COUNT(*) ASC, cards DESC "
            "LIMIT ?", [tgt, subject, int(limit)]).fetchall()
    return [{"topic": r["topic"], "cards": r["cards"], "lapses": r["lapses"] or 0,
             "mastery_pct": round(100 * (r["sitzt"] or 0) / r["cards"]) if r["cards"] else 0}
            for r in rows]


def due_forecast(days: int = 14, subject: Optional[str] = None) -> list[dict]:
    """Faelligkeits-Prognose: wie viele Karten werden an jedem der naechsten ``days``
    Tage faellig (Ueberfaellige zaehlen zu 'heute'). Warnt vor Stau vor der Klausur."""
    now = time.time()
    today = _day_start(now)
    sc, sa = _subj_clause(subject)
    with _conn() as c:
        rows = c.execute(
            "SELECT due FROM review_items WHERE suspended=0 AND use_flashcard=1 "
            "AND due IS NOT NULL" + sc, sa).fetchall()
    buckets = [0] * days
    for r in rows:
        due = r["due"]
        if due is None:
            continue
        idx = int((due - today) // 86400)
        if idx < 0:
            idx = 0
        if 0 <= idx < days:
            buckets[idx] += 1
    return [{"tag": _day_key(today + i * 86400), "faellig": buckets[i]} for i in range(days)]


def _active_cards(subject: Optional[str] = None) -> list[dict]:
    sc, sa = _subj_clause(subject)
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT card_id, subject, topic, ease, interval, reps, last_review, due "
            "FROM review_items WHERE suspended=0 AND use_flashcard=1" + sc, sa)]


def card_retrievability(card: dict, at_time: Optional[float] = None) -> float:
    """Abrufwahrscheinlichkeit einer Karte zu einem Zeitpunkt (0..1), als
    Vergessenskurve R = exp(-t/S). Stabilitaet S ~ interval*ease (grobe FSRS-artige
    Naeherung). Nie geuebte Karten -> 0 (noch nicht abrufbar)."""
    import math
    reps = int(card.get("reps") or 0)
    last = card.get("last_review")
    if reps <= 0 or not last:
        return 0.0
    now = at_time if at_time is not None else time.time()
    interval_days = float(card.get("interval") or 0.0)
    ease = float(card.get("ease") or 2.5)
    S = max(0.5, interval_days * ease)
    days = max(0.0, (now - float(last)) / 86400.0)
    return math.exp(-days / S)


def subject_readiness(subject: str, at_time: Optional[float] = None,
                      cards: Optional[list] = None) -> dict:
    """Klausur-Bereitschaft eines Fachs: mittlere Abrufwahrscheinlichkeit ueber alle
    Karten (nie geuebte zaehlen als 0 -> deckt Abdeckung UND Behalten ab)."""
    cards = cards if cards is not None else _active_cards(subject)
    if not cards:
        return {"cards": 0, "readiness_pct": 0}
    rs = [card_retrievability(c, at_time) for c in cards]
    return {"cards": len(cards), "readiness_pct": round(100 * sum(rs) / len(rs))}


def forgetting_curve(subject: str, days_ahead: int = 30,
                     at_start: Optional[float] = None) -> list[dict]:
    """Projizierte Bereitschaft je Tag der naechsten ``days_ahead`` Tage (ohne weiteres
    Ueben) - macht das Vergessen bis zur Klausur sichtbar."""
    now = at_start if at_start is not None else time.time()
    cards = _active_cards(subject)
    out = []
    for d in range(0, int(days_ahead) + 1):
        t = now + d * 86400
        rs = [card_retrievability(c, t) for c in cards]
        out.append({"tag": _day_key(t),
                    "bereitschaft_pct": round(100 * sum(rs) / len(rs)) if rs else 0})
    return out


def daily_goal_status(subject: Optional[str] = None) -> dict:
    """Heutiges Tagesziel + Backlog-Ampel: heute geuebt vs. Ziel, faellige Karten."""
    goal = max(1, int(getattr(settings, "DAILY_REVIEW_GOAL", 40)))
    now = time.time()
    sc, sa = _subj_clause(subject)
    with _conn() as c:
        today = c.execute(
            "SELECT COUNT(*) AS r FROM review_log WHERE reviewed_at>=?" + sc,
            [_day_start(now)] + sa).fetchone()["r"] or 0
        due = c.execute(
            "SELECT COUNT(*) AS d FROM review_items WHERE suspended=0 AND use_flashcard=1 "
            "AND due<=?" + sc, [now] + sa).fetchone()["d"] or 0
    ampel = "grün" if due <= goal else ("gelb" if due <= 2 * goal else "rot")
    return {"goal": goal, "done_today": today, "due": due,
            "goal_reached": today >= goal, "ampel": ampel}


def leeches(subject: Optional[str] = None, limit: int = 60) -> list[dict]:
    """Karten mit vielen Patzern ('Dauerpatzer'), die meiste Klausurzeit fressen -
    aufsteigend nach Mastery, absteigend nach Patzern."""
    lt = _leech_threshold()
    sc, sa = _subj_clause(subject)
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM review_items WHERE suspended=0 AND lapses>=?" + sc +
            " ORDER BY lapses DESC, ease ASC LIMIT ?", [lt] + sa + [int(limit)]).fetchall()
    return [dict(r) for r in rows]
