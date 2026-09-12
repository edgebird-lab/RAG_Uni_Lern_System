"""Tests fuer das Noten-Tracking (Klausurnote nachtraeglich eintragen + ECTS-
gewichteter Notenschnitt): manifest.upsert_exam()s neues ``note``-Feld und
planner.gpa_summary(). Isolierte Temp-DB, niemals die echte data/manifest.db
(gleiches Muster wie test_manifest_audio_overviews.py)."""
from __future__ import annotations

import pytest

from ragapp import manifest, planner


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "manifest_test.db"
    monkeypatch.setattr(manifest, "MANIFEST_DB", db_path)
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)
    return db_path


# --------------------------------------------------------------------------- #
# manifest.upsert_exam(): Note als optionales, spaeter nachgetragenes Feld
# --------------------------------------------------------------------------- #
def test_upsert_exam_ohne_note_bleibt_note_leer(isolated_db):
    manifest.upsert_exam("mathe", exam_date="2026-07-15", ects=6.0)
    exam = manifest.get_exam("mathe")
    assert exam["note"] is None
    assert exam["note_updated_at"] is None


def test_upsert_exam_mit_note_speichert_und_stempelt_zeit(isolated_db):
    manifest.upsert_exam("mathe", exam_date="2026-07-15", ects=6.0, note=1.7)
    exam = manifest.get_exam("mathe")
    assert exam["note"] == 1.7
    assert exam["note_updated_at"] is not None


def test_upsert_exam_note_kann_nachtraeglich_auf_bestehenden_termin_ergaenzt_werden(isolated_db):
    manifest.upsert_exam("mathe", exam_date="2026-07-15", ects=6.0)
    manifest.upsert_exam("mathe", exam_date="2026-07-15", ects=6.0, note=2.3)
    assert manifest.get_exam("mathe")["note"] == 2.3


def test_upsert_exam_note_kann_wieder_auf_none_gesetzt_werden(isolated_db):
    manifest.upsert_exam("mathe", note=1.0)
    manifest.upsert_exam("mathe", note=None)
    exam = manifest.get_exam("mathe")
    assert exam["note"] is None
    assert exam["note_updated_at"] is None


# --------------------------------------------------------------------------- #
# planner.gpa_summary(): ECTS-gewichteter Notenschnitt
# --------------------------------------------------------------------------- #
def test_gpa_summary_ohne_benotete_klausuren_ist_leer(isolated_db):
    manifest.upsert_exam("mathe", exam_date="2026-07-15", ects=6.0)
    summary = planner.gpa_summary()
    assert summary == {"count": 0, "gpa": None, "total_ects": 0.0, "exams": []}


def test_gpa_summary_gewichtet_nach_ects(isolated_db):
    # 1,0 mit 10 ECTS, 4,0 mit 5 ECTS -> (1,0*10 + 4,0*5) / 15 = 2,0
    manifest.upsert_exam("mathe", ects=10.0, note=1.0)
    manifest.upsert_exam("physik", ects=5.0, note=4.0)
    summary = planner.gpa_summary()
    assert summary["count"] == 2
    assert summary["gpa"] == 2.0
    assert summary["total_ects"] == 15.0


def test_gpa_summary_ohne_ects_zaehlt_mit_gewicht_1(isolated_db):
    # Kein ECTS eingetragen -> zaehlt trotzdem mit (Gewicht 1,0), wird nicht
    # einfach aus dem Schnitt geworfen.
    manifest.upsert_exam("mathe", note=2.0)
    manifest.upsert_exam("physik", note=4.0)
    summary = planner.gpa_summary()
    assert summary["gpa"] == 3.0
    assert summary["total_ects"] == 0.0


def test_gpa_summary_ignoriert_unbenotete_klausuren(isolated_db):
    manifest.upsert_exam("mathe", ects=6.0, note=1.3)
    manifest.upsert_exam("physik", ects=6.0)   # keine Note
    summary = planner.gpa_summary()
    assert summary["count"] == 1
    assert summary["gpa"] == 1.3
