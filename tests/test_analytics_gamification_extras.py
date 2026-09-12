"""Tests für analytics.has_night_owl_review()/has_full_weekend_study() -
Grundlage der Errungenschaften "night_owl"/"weekend_study"
(ragapp/achievements.py). Isolierte Temp-DB, niemals die echte
data/manifest.db (gleiches Muster wie test_analytics_weekly_recap.py)."""
from __future__ import annotations

import calendar
import datetime
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
    manifest.init_db()
    return db_path


def _log_review(subject: str, reviewed_at: float) -> None:
    with manifest._connect() as conn:
        cid = f"c-{uuid.uuid4().hex[:12]}"
        conn.execute(
            "INSERT INTO review_items (card_id, subject, front, back, suspended, "
            "use_flashcard, reps, created_at) VALUES (?,?,?,?,0,1,1,?)",
            (cid, subject, "F", "A", time.time()))
        conn.execute(
            "INSERT INTO review_log (card_id, subject, rating, reviewed_at) "
            "VALUES (?,?,2,?)", (cid, subject, reviewed_at))


def _ts_at_local_hour(date: datetime.date, hour: int) -> float:
    dt = datetime.datetime(date.year, date.month, date.day, hour, 0, 0)
    return time.mktime(dt.timetuple())


def _last_saturday() -> datetime.date:
    today = datetime.date.today()
    return today - datetime.timedelta(days=(today.weekday() - calendar.SATURDAY) % 7 + 7)


def test_has_night_owl_review_ohne_daten_ist_false(isolated_db):
    assert analytics.has_night_owl_review() is False


def test_has_night_owl_review_erkennt_wiederholung_um_2_uhr(isolated_db):
    sat = _last_saturday()
    _log_review("mathe", _ts_at_local_hour(sat, 2))
    assert analytics.has_night_owl_review() is True


def test_has_night_owl_review_ignoriert_tagsueber(isolated_db):
    sat = _last_saturday()
    _log_review("mathe", _ts_at_local_hour(sat, 14))
    assert analytics.has_night_owl_review() is False


def test_has_full_weekend_study_ohne_daten_ist_false(isolated_db):
    assert analytics.has_full_weekend_study() is False


def test_has_full_weekend_study_erkennt_samstag_und_sonntag(isolated_db):
    sat = _last_saturday()
    sun = sat + datetime.timedelta(days=1)
    _log_review("mathe", _ts_at_local_hour(sat, 10))
    _log_review("mathe", _ts_at_local_hour(sun, 10))
    assert analytics.has_full_weekend_study() is True


def test_has_full_weekend_study_nur_samstag_reicht_nicht(isolated_db):
    sat = _last_saturday()
    _log_review("mathe", _ts_at_local_hour(sat, 10))
    assert analytics.has_full_weekend_study() is False


def test_has_full_weekend_study_nur_sonntag_reicht_nicht(isolated_db):
    sat = _last_saturday()
    sun = sat + datetime.timedelta(days=1)
    _log_review("mathe", _ts_at_local_hour(sun, 10))
    assert analytics.has_full_weekend_study() is False
