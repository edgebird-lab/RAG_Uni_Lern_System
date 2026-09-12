"""Tests für die Probeklausur-Ergebnis-Historie (manifest.log_exam_attempt()/
list_exam_attempts()/best_exam_pct()) - vorher lebte das Ergebnis nur in
st.session_state und war nach Verlassen der Seite komplett weg. Isolierte
Temp-DB, niemals die echte data/manifest.db."""
from __future__ import annotations

import time

import pytest

from ragapp import manifest


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "manifest_test.db"
    monkeypatch.setattr(manifest, "MANIFEST_DB", db_path)
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)
    return db_path


def test_log_and_list_exam_attempt(isolated_db):
    manifest.log_exam_attempt(82, 10)
    attempts = manifest.list_exam_attempts()
    assert len(attempts) == 1
    assert attempts[0]["total_pct"] == 82
    assert attempts[0]["num_items"] == 10
    assert attempts[0]["taken_at"] is not None


def test_list_exam_attempts_newest_first(isolated_db, monkeypatch):
    times = iter([100.0, 200.0, 300.0])
    monkeypatch.setattr(time, "time", lambda: next(times))
    manifest.log_exam_attempt(50, 5)
    manifest.log_exam_attempt(60, 5)
    manifest.log_exam_attempt(70, 5)
    pcts = [a["total_pct"] for a in manifest.list_exam_attempts()]
    assert pcts == [70, 60, 50]


def test_list_exam_attempts_respektiert_limit(isolated_db):
    for i in range(5):
        manifest.log_exam_attempt(i * 10, 5)
    assert len(manifest.list_exam_attempts(limit=2)) == 2


def test_best_exam_pct_ohne_versuche_ist_none(isolated_db):
    assert manifest.best_exam_pct() is None


def test_best_exam_pct_liefert_hoechsten_wert(isolated_db):
    manifest.log_exam_attempt(60, 5)
    manifest.log_exam_attempt(90, 5)
    manifest.log_exam_attempt(75, 5)
    assert manifest.best_exam_pct() == 90
