"""
Lern-Analytik (liest das ``review_log`` aus)
============================================
Das ``review_log`` wird bei jeder Wiederholung geschrieben, aber bislang nie
gelesen. Dieses Modul verwandelt es (zusammen mit dem FSRS-6-Zustand in
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


def weekly_recap(subject: Optional[str] = None) -> dict:
    """Vergleicht die letzten 7 Tage mit den 7 Tagen DAVOR: Wiederholungen,
    Trefferquote, investierte Lernzeit. Reine Sparklines/Zahlen werden mit der
    Zeit leicht übersehen - der explizite Wochenvergleich soll Fortschritt
    bewusst SPÜRBAR machen (Grundlage des "Wochenrückblick" auf Fortschritt)."""
    now = time.time()
    this_start = _day_start(now) - 6 * 86400
    prev_start = this_start - 7 * 86400
    sc, sa = _subj_clause(subject)
    with _conn() as c:
        this_row = c.execute(
            "SELECT COUNT(*) AS r, SUM(CASE WHEN rating>=? THEN 1 ELSE 0 END) AS g "
            "FROM review_log WHERE reviewed_at>=?" + sc, [_GEWUSST, this_start] + sa
        ).fetchone()
        prev_row = c.execute(
            "SELECT COUNT(*) AS r, SUM(CASE WHEN rating>=? THEN 1 ELSE 0 END) AS g "
            "FROM review_log WHERE reviewed_at>=? AND reviewed_at<?" + sc,
            [_GEWUSST, prev_start, this_start] + sa
        ).fetchone()

    def _study_minutes(since: float, until: "float | None") -> int:
        from ragapp import manifest
        by_subj = manifest.study_time_by_subject(since=since, until=until)
        return round((by_subj.get(subject, 0) if subject else sum(by_subj.values())) / 60)

    def _pack(row, minutes: int) -> dict:
        rev = row["r"] or 0
        acc = round(100 * (row["g"] or 0) / rev) if rev else None
        return {"reviews": rev, "accuracy_pct": acc, "minutes": minutes}

    return {
        "this_week": _pack(this_row, _study_minutes(this_start, None)),
        "prev_week": _pack(prev_row, _study_minutes(prev_start, this_start)),
    }


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
            "SELECT card_id, subject, topic, interval, reps, last_review, due, "
            "fsrs_state, stability, difficulty "
            "FROM review_items WHERE suspended=0 AND use_flashcard=1" + sc, sa)]


# --------------------------------------------------------------------------- #
# Vergessenskurve / Klausur-Bereitschaft
# --------------------------------------------------------------------------- #
# Nutzt seit der FSRS-6-Umstellung (siehe ragapp/study.py) das ECHTE, aus 700+ Mio.
# Wiederholungen trainierte Vergessens-Modell statt einer handgestrickten Formel -
# card["stability"]/card["fsrs_state"] kommen direkt aus review_items. Eigener,
# leichtgewichtiger Scheduler-Aufbau (statt ragapp.study zu importieren): study.py
# zieht ueber get_vectorstore() transitiv chromadb, was analytics.py bewusst
# vermeidet (reine Leseoperationen, offline, ohne schwere Abhaengigkeiten).
_MIN_STABILITY_DAYS = 1.0  # Untergrenze, damit eine frisch gelernte Karte nicht
                           # sofort als "vergessen" zaehlt (analog zur alten Formel)


def _fsrs_scheduler():
    from fsrs import Scheduler
    # enable_fuzzing wirkt nur auf review_card()/Intervall-Berechnung, nicht auf
    # get_card_retrievability() - hier egal, aber konsistent mit study.py gesetzt.
    return Scheduler(desired_retention=float(settings.FSRS_DESIRED_RETENTION),
                     maximum_interval=int(settings.FSRS_MAX_INTERVAL_DAYS),
                     enable_fuzzing=False)


def card_retrievability(card: dict, at_time: Optional[float] = None) -> float:
    """Abrufwahrscheinlichkeit einer Karte zu einem Zeitpunkt (0..1), direkt aus dem
    echten FSRS-Modell (``scheduler.get_card_retrievability``). Nie geuebte Karten
    (kein ``stability``) -> 0.0 (Abdeckung noch offen, wie zuvor)."""
    from datetime import datetime, timezone
    from fsrs import Card, State
    reps = int(card.get("reps") or 0)
    last = card.get("last_review")
    stability = card.get("stability")
    if reps <= 0 or not last or stability is None:
        return 0.0
    now = at_time if at_time is not None else time.time()
    fsrs_card = Card(
        state=State(int(card.get("fsrs_state") or State.Review.value)),
        stability=max(_MIN_STABILITY_DAYS, float(stability)),
        difficulty=card.get("difficulty"),
        due=datetime.fromtimestamp(float(card.get("due") or now), tz=timezone.utc),
        last_review=datetime.fromtimestamp(float(last), tz=timezone.utc),
    )
    return _fsrs_scheduler().get_card_retrievability(
        fsrs_card, datetime.fromtimestamp(now, tz=timezone.utc))


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


_SNAPSHOT_ALL = "_all_"   # Fach-Platzhalter fuer die Auswahl "Alle Faecher"


def record_progress_snapshot(subject: Optional[str] = None) -> None:
    """Schreibt/aktualisiert den heutigen Schnappschuss von Klausur-Bereitschaft
    + 'Sitzt'-Anteil fuer ``subject`` (oder 'Alle Faecher') - siehe
    manifest.progress_snapshots-Kommentar. Ueberschreibt bei mehrfachem Aufruf
    am selben Tag denselben Eintrag (kein Anwachsen bei jedem Seitenaufruf)."""
    from ragapp import manifest
    ov = overview(subject)
    ready = subject_readiness(subject)["readiness_pct"]
    manifest.upsert_progress_snapshot(
        _day_key(time.time()), subject or _SNAPSHOT_ALL, ready, ov["mastery_pct"])


def progress_snapshot_trend(subject: Optional[str] = None, days: int = 14) -> list[dict]:
    """Die letzten ``days`` taeglichen Schnappschuesse (siehe
    record_progress_snapshot) - leer, solange noch keine Schnappschuesse fuer
    dieses Fach vorliegen (baut sich erst ab dem ersten Aufruf auf)."""
    from ragapp import manifest
    return manifest.list_progress_snapshots(subject or _SNAPSHOT_ALL, days)


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


def max_lapses(subject: Optional[str] = None) -> int:
    """Hoechste Patzer-Zahl unter den (nicht pausierten) Karten - nur fuer die
    Anzeige, WARUM (noch) keine Dauerpatzer da sind (0, wenn keine Karten da sind)."""
    sc, sa = _subj_clause(subject)
    with _conn() as c:
        row = c.execute(
            "SELECT MAX(lapses) AS m FROM review_items WHERE suspended=0" + sc, sa
        ).fetchone()
    return int(row["m"] or 0)
