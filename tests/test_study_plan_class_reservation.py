"""Tests für study_plan._class_minutes_by_weekday()/build_schedule() - der
Lernplan reserviert jetzt taeglich Zeit fuer bereits im Stundenplan
eingetragene Vorlesungen/Kurse (siehe manifest.timetable), analog zur schon
vorhandenen Wiederholungs-Reservierung. Isolierte Temp-DB, niemals die echte
data/manifest.db."""
from __future__ import annotations

from datetime import date

import pytest

from ragapp import manifest, study_plan


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "manifest_test.db"
    monkeypatch.setattr(manifest, "MANIFEST_DB", db_path)
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)
    manifest.init_db()
    return db_path


def test_class_minutes_by_weekday_ohne_stundenplan_ist_leer(isolated_db):
    assert study_plan._class_minutes_by_weekday() == {}


def test_class_minutes_by_weekday_summiert_mehrere_stunden_am_selben_tag(isolated_db):
    manifest.upsert_timetable_slot(subject="Mathe", weekday=0,
                                   start_time="08:00", end_time="09:30")
    manifest.upsert_timetable_slot(subject="Deutsch", weekday=0,
                                   start_time="10:00", end_time="11:30")
    out = study_plan._class_minutes_by_weekday()
    assert out == {0: 180}  # 90 + 90 Minuten


def test_class_minutes_by_weekday_trennt_wochentage(isolated_db):
    manifest.upsert_timetable_slot(subject="Mathe", weekday=0,
                                   start_time="08:00", end_time="09:30")
    manifest.upsert_timetable_slot(subject="Physik", weekday=2,
                                   start_time="08:00", end_time="09:00")
    out = study_plan._class_minutes_by_weekday()
    assert out == {0: 90, 2: 60}


def test_build_schedule_reduziert_tagesbudget_an_unterrichtstagen(isolated_db, monkeypatch):
    # Montag (weekday=0) hat 4 Stunden Unterricht -> weniger Lernzeit an dem Tag.
    manifest.upsert_timetable_slot(subject="Uni", weekday=0,
                                   start_time="08:00", end_time="12:00")
    monkeypatch.setattr(study_plan.settings, "PLAN_CLASS_MAX_SHARE", 0.7, raising=False)
    monkeypatch.setattr(study_plan.settings, "PLAN_MAX_DAILY_FOCUS_MIN", 240, raising=False)
    _start = date(2026, 9, 14)  # Montag
    result = study_plan.build_schedule(
        [{"section_id": "s1", "est_minutes": 1000}], daily_minutes=120,
        deadline=None, start=_start, subject=None)
    assert result["class_minutes_reserved"] > 0
    # Erwarteter Montags-Anteil des Plans: gedeckelt auf 120*0.7=84 Minuten
    # Unterricht -> hoechstens 120-84=36 Minuten fuer den ersten Tag geplant.
    monday_blocks = [b for b in result["blocks"] if b["planned_date"] == "2026-09-14"]
    assert sum(b["planned_min"] for b in monday_blocks) <= 36


def test_build_schedule_ohne_stundenplan_unveraendert(isolated_db):
    result = study_plan.build_schedule(
        [{"section_id": "s1", "est_minutes": 100}], daily_minutes=60,
        deadline=None, start=date(2026, 9, 14), subject=None)
    assert result["class_minutes_reserved"] == 0
    first_day_blocks = [b for b in result["blocks"] if b["planned_date"] == "2026-09-14"]
    assert sum(b["planned_min"] for b in first_day_blocks) == 60


def test_build_schedule_klausurtag_ohne_unterricht_bleibt_voll_nutzbar(isolated_db):
    # Stundenplan existiert, aber NICHT am betrachteten Wochentag (Dienstag=1).
    manifest.upsert_timetable_slot(subject="Uni", weekday=0,
                                   start_time="08:00", end_time="12:00")
    result = study_plan.build_schedule(
        [{"section_id": "s1", "est_minutes": 100}], daily_minutes=60,
        deadline=None, start=date(2026, 9, 15), subject=None)  # Dienstag
    assert result["class_minutes_reserved"] == 0
    first_day_blocks = [b for b in result["blocks"] if b["planned_date"] == "2026-09-15"]
    assert sum(b["planned_min"] for b in first_day_blocks) == 60


def test_degenerierte_konfiguration_liefert_class_minutes_reserved_null(isolated_db):
    result = study_plan.build_schedule(
        [{"section_id": "s1", "est_minutes": 100}], daily_minutes=0,
        deadline=None, start=date(2026, 9, 14), subject=None)
    assert result["class_minutes_reserved"] == 0
