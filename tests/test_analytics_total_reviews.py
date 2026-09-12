"""Tests für analytics.total_reviews_count() (Wiederholungen INSGESAMT, nicht
nur ein Zeitfenster wie overview()/retention_trend()) - Grundlage der
Errungenschaften "100/1000 Wiederholungen" (ragapp/achievements.py).
Isolierte Temp-DB, niemals die echte data/manifest.db."""
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
    manifest.init_db()
    return db_path


def _log_review(subject: str, reviewed_at: float) -> None:
    with manifest._connect() as conn:
        cid = f"c-{uuid.uuid4().hex[:12]}"
        conn.execute(
            "INSERT INTO review_items (card_id, subject, front, back, suspended, "
            "use_flashcard, created_at) VALUES (?,?,?,?,0,1,?)",
            (cid, subject, "F", "A", time.time()))
        conn.execute(
            "INSERT INTO review_log (card_id, subject, rating, reviewed_at) "
            "VALUES (?,?,2,?)", (cid, subject, reviewed_at))


def test_total_reviews_count_ohne_daten_ist_null(isolated_db):
    assert analytics.total_reviews_count() == 0


def test_total_reviews_count_zaehlt_alte_und_neue_zusammen(isolated_db):
    now = time.time()
    _log_review("mathe", now - 200 * 86400)   # sehr alt - retention_trend()/overview() sehen das nicht mehr
    _log_review("mathe", now - 1 * 86400)
    assert analytics.total_reviews_count() == 2


def test_total_reviews_count_filtert_nach_fach(isolated_db):
    now = time.time()
    _log_review("mathe", now)
    _log_review("physik", now)
    assert analytics.total_reviews_count("mathe") == 1
