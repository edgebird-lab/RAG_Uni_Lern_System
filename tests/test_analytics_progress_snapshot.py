"""Tests fuer die taeglichen Fortschritts-Schnappschuesse (Grundlage der
Trend-Sparklines "Klausur-Bereitschaft"/"Sitzt"-Anteil auf der Seite
Fortschritt) - sowohl die manifest-CRUD als auch analytics.record_progress_
snapshot()/progress_snapshot_trend(). Isolierte Temp-DB, niemals die echte
data/manifest.db (gleiches Muster wie test_manifest_audio_overviews.py)."""
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
    # analytics.py haelt eine EIGENE MANIFEST_DB-Referenz (eigener Import,
    # kein Zugriff ueber das manifest-Modul) - muss separat umgebogen werden,
    # sonst schreibt/liest record_progress_snapshot() an der echten DB vorbei.
    monkeypatch.setattr(analytics, "MANIFEST_DB", db_path)
    return db_path


def _insert_card(conn, *, subject: str, reps: int, stability=None, difficulty=None,
                 last_review=None, due=None, fsrs_state=2) -> None:
    conn.execute(
        "INSERT INTO review_items (card_id, subject, topic, front, back, "
        "suspended, use_flashcard, reps, stability, difficulty, last_review, "
        "due, fsrs_state, created_at) VALUES (?,?,?,?,?,0,1,?,?,?,?,?,?,?)",
        (f"c-{uuid.uuid4().hex[:12]}", subject, None, "F", "A", reps, stability,
         difficulty, last_review, due, fsrs_state, time.time()))


# --------------------------------------------------------------------------- #
# manifest.py: reine CRUD
# --------------------------------------------------------------------------- #
def test_upsert_progress_snapshot_liest_sich_zurueck(isolated_db):
    manifest.upsert_progress_snapshot("2026-09-10", "mathe", readiness_pct=60, mastery_pct=40)
    rows = manifest.list_progress_snapshots("mathe", days=14)
    assert len(rows) == 1
    assert rows[0] == {"day": "2026-09-10", "readiness_pct": 60, "mastery_pct": 40}


def test_upsert_am_selben_tag_ueberschreibt_statt_neue_zeile(isolated_db):
    manifest.upsert_progress_snapshot("2026-09-10", "mathe", readiness_pct=60, mastery_pct=40)
    manifest.upsert_progress_snapshot("2026-09-10", "mathe", readiness_pct=70, mastery_pct=50)
    rows = manifest.list_progress_snapshots("mathe", days=14)
    assert len(rows) == 1
    assert rows[0]["readiness_pct"] == 70
    assert rows[0]["mastery_pct"] == 50


def test_list_progress_snapshots_aelteste_zuerst_und_pro_fach_getrennt(isolated_db):
    manifest.upsert_progress_snapshot("2026-09-08", "mathe", readiness_pct=50, mastery_pct=30)
    manifest.upsert_progress_snapshot("2026-09-09", "mathe", readiness_pct=55, mastery_pct=35)
    manifest.upsert_progress_snapshot("2026-09-09", "physik", readiness_pct=90, mastery_pct=80)
    rows = manifest.list_progress_snapshots("mathe", days=14)
    assert [r["day"] for r in rows] == ["2026-09-08", "2026-09-09"]
    assert manifest.list_progress_snapshots("physik", days=14)[0]["readiness_pct"] == 90


def test_list_progress_snapshots_unbekanntes_fach_ist_leer(isolated_db):
    assert manifest.list_progress_snapshots("nichtvorhanden", days=14) == []


# --------------------------------------------------------------------------- #
# analytics.py: record_progress_snapshot()/progress_snapshot_trend()
# --------------------------------------------------------------------------- #
def test_record_progress_snapshot_schreibt_heutigen_eintrag(isolated_db):
    with manifest._connect() as conn:
        _insert_card(conn, subject="mathe", reps=5)
        _insert_card(conn, subject="mathe", reps=0)

    analytics.record_progress_snapshot("mathe")
    trend = analytics.progress_snapshot_trend("mathe", days=14)
    assert len(trend) == 1
    assert trend[0]["day"] == time.strftime("%Y-%m-%d", time.localtime())
    assert trend[0]["mastery_pct"] == 50   # 1 von 2 Karten "sitzt" (reps>=Ziel)


def test_record_progress_snapshot_mehrfach_am_tag_bleibt_ein_eintrag(isolated_db):
    with manifest._connect() as conn:
        _insert_card(conn, subject="mathe", reps=1)
    analytics.record_progress_snapshot("mathe")
    analytics.record_progress_snapshot("mathe")
    analytics.record_progress_snapshot("mathe")
    assert len(analytics.progress_snapshot_trend("mathe", days=14)) == 1


def test_record_progress_snapshot_ohne_fach_nutzt_platzhalter_all(isolated_db):
    with manifest._connect() as conn:
        _insert_card(conn, subject="mathe", reps=1)
    analytics.record_progress_snapshot(None)
    assert len(analytics.progress_snapshot_trend(None, days=14)) == 1
    # Unter dem echten Fachnamen darf dabei NICHTS gelandet sein.
    assert analytics.progress_snapshot_trend("mathe", days=14) == []


def test_progress_snapshot_trend_ohne_historie_ist_leer(isolated_db):
    assert analytics.progress_snapshot_trend("mathe", days=14) == []
