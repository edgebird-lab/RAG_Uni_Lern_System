"""Tests für analytics.weekly_recap() (Wochenrückblick: diese Woche vs. die
Woche davor - Wiederholungen, Trefferquote, Lernzeit). Isolierte Temp-DB,
niemals die echte data/manifest.db (gleiches Muster wie
test_analytics_progress_snapshot.py)."""
from __future__ import annotations

import time
import uuid

import pytest

from ragapp import analytics, manifest


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "manifest_test.db"
    monkeypatch.setattr(manifest, "MANIFEST_DB", db_path)
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)
    monkeypatch.setattr(analytics, "MANIFEST_DB", db_path)
    # analytics._conn() legt (anders als manifest._connect()) das Schema NICHT
    # selbst an - fuer einen Test ganz OHNE vorherigen manifest-Aufruf (z. B.
    # "keine Daten") muss die Temp-DB daher hier einmalig initialisiert werden.
    manifest.init_db()
    return db_path


def _log_review(subject: str, reviewed_at: float, rating: int) -> None:
    with manifest._connect() as conn:
        cid = f"c-{uuid.uuid4().hex[:12]}"
        conn.execute(
            "INSERT INTO review_items (card_id, subject, front, back, suspended, "
            "use_flashcard, reps, created_at) VALUES (?,?,?,?,0,1,1,?)",
            (cid, subject, "F", "A", time.time()))
        conn.execute(
            "INSERT INTO review_log (card_id, subject, rating, reviewed_at) "
            "VALUES (?,?,?,?)", (cid, subject, rating, reviewed_at))


def _log_study(subject: str, started_at: float, duration_sec: int) -> None:
    with manifest._connect() as conn:
        conn.execute(
            "INSERT INTO study_sessions (session_id, subject, mode, started_at, "
            "ended_at, duration_sec) VALUES (?,?,?,?,?,?)",
            (uuid.uuid4().hex[:16], subject, "frei", started_at,
             started_at + duration_sec, duration_sec))


def test_weekly_recap_ohne_daten_ist_leer(isolated_db):
    recap = analytics.weekly_recap()
    assert recap["this_week"] == {"reviews": 0, "accuracy_pct": None, "minutes": 0}
    assert recap["prev_week"] == {"reviews": 0, "accuracy_pct": None, "minutes": 0}


def test_weekly_recap_trennt_diese_und_letzte_woche(isolated_db):
    now = time.time()
    _log_review("mathe", now - 1 * 86400, rating=2)      # diese Woche, gewusst
    _log_review("mathe", now - 2 * 86400, rating=0)      # diese Woche, nicht gewusst
    _log_review("mathe", now - 10 * 86400, rating=2)      # letzte Woche
    recap = analytics.weekly_recap()
    assert recap["this_week"]["reviews"] == 2
    assert recap["this_week"]["accuracy_pct"] == 50
    assert recap["prev_week"]["reviews"] == 1
    assert recap["prev_week"]["accuracy_pct"] == 100


def test_weekly_recap_ignoriert_aeltere_daten_als_zwei_wochen(isolated_db):
    now = time.time()
    _log_review("mathe", now - 25 * 86400, rating=2)
    recap = analytics.weekly_recap()
    assert recap["this_week"]["reviews"] == 0
    assert recap["prev_week"]["reviews"] == 0


def test_weekly_recap_filtert_nach_fach(isolated_db):
    now = time.time()
    _log_review("mathe", now - 1 * 86400, rating=2)
    _log_review("physik", now - 1 * 86400, rating=2)
    recap = analytics.weekly_recap(subject="mathe")
    assert recap["this_week"]["reviews"] == 1


def test_weekly_recap_zaehlt_lernzeit_pro_zeitraum(isolated_db):
    now = time.time()
    _log_study("mathe", now - 1 * 86400, 1500)     # 25 Min, diese Woche
    _log_study("mathe", now - 10 * 86400, 3000)    # 50 Min, letzte Woche
    recap = analytics.weekly_recap()
    assert recap["this_week"]["minutes"] == 25
    assert recap["prev_week"]["minutes"] == 50


def test_weekly_recap_lernzeit_ohne_fach_filter_summiert_alle_faecher(isolated_db):
    now = time.time()
    _log_study("mathe", now - 1 * 86400, 600)
    _log_study("physik", now - 1 * 86400, 600)
    recap = analytics.weekly_recap()
    assert recap["this_week"]["minutes"] == 20
