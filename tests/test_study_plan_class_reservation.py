"""Tests für study_plan._class_minutes_by_weekday()/build_schedule() - der
Lernplan reserviert jetzt taeglich Zeit fuer bereits im Stundenplan
eingetragene Vorlesungen/Kurse (siehe manifest.timetable), analog zur schon
vorhandenen Wiederholungs-Reservierung. Isolierte Temp-DB, niemals die echte
data/manifest.db."""
from __future__ import annotations

from datetime import date, timedelta

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


def _overdue_plan(*, daily_minutes=60, blocks=(30, 30, 30)):
    pid = manifest.create_study_plan(
        title="Plan", subject="Mathe", doc_ids=[], deadline=None,
        daily_minutes=daily_minutes)
    manifest.update_study_plan(pid, status="active")
    sid = manifest.append_plan_section(
        pid, title="Rückstand", est_minutes=sum(blocks))
    old = (date.today() - timedelta(days=2)).isoformat()
    for minutes in blocks:
        manifest.append_plan_block(
            pid, section_id=sid, planned_date=old, planned_min=minutes)
    return pid


def test_repair_overdue_blocks_verteilt_statt_auf_heute_zu_kippen(
        isolated_db, monkeypatch):
    monkeypatch.setattr(
        study_plan.settings, "PLAN_MAX_DAILY_FOCUS_MIN", 60, raising=False)
    pid = _overdue_plan(daily_minutes=60, blocks=(30, 30, 30))
    preview = study_plan.repair_overdue_blocks(pid, apply=False)
    days = [m["to_date"] for m in preview["moves"]]
    assert len(set(days)) >= 2
    assert preview["moved_minutes"] == 90
    # Vorschau mutiert noch nicht.
    assert len(manifest.list_overdue_plan_blocks(date.today().isoformat(), pid)) == 3
    applied = study_plan.repair_overdue_blocks(pid, apply=True)
    assert applied["applied"] is True
    assert manifest.list_overdue_plan_blocks(date.today().isoformat(), pid) == []


def test_repair_overdue_blocks_zeigt_shortfall_ehrlich(
        isolated_db, monkeypatch):
    monkeypatch.setattr(
        study_plan.settings, "PLAN_MAX_DAILY_FOCUS_MIN", 20, raising=False)
    pid = _overdue_plan(daily_minutes=20, blocks=(30,))
    out = study_plan.repair_overdue_blocks(pid, apply=False)
    assert out["moves"] == []
    assert out["shortfall_minutes"] == 30


def test_repair_reserviert_vorlesungszeit(isolated_db, monkeypatch):
    monkeypatch.setattr(
        study_plan.settings, "PLAN_MAX_DAILY_FOCUS_MIN", 60, raising=False)
    monkeypatch.setattr(
        study_plan.settings, "PLAN_CLASS_MAX_SHARE", 1.0, raising=False)
    start = date(2026, 9, 14)  # Montag
    manifest.upsert_timetable_slot(
        subject="Uni", weekday=0, start_time="08:00", end_time="09:00")
    pid = manifest.create_study_plan(
        title="Plan", subject=None, doc_ids=[], deadline=None, daily_minutes=60)
    manifest.update_study_plan(pid, status="active")
    sid = manifest.append_plan_section(pid, title="Thema", est_minutes=30)
    manifest.append_plan_block(
        pid, section_id=sid,
        planned_date=(start - timedelta(days=1)).isoformat(), planned_min=30)
    out = study_plan.repair_overdue_blocks(pid, start=start)
    assert out["moves"][0]["to_date"] == "2026-09-15"


def test_repair_zaehlt_bloecke_anderer_aktiver_plaene_zur_tageslast(
        isolated_db, monkeypatch):
    monkeypatch.setattr(
        study_plan.settings, "PLAN_MAX_DAILY_FOCUS_MIN", 60, raising=False)
    start = date(2026, 9, 14)
    busy = manifest.create_study_plan(
        title="Anderer Plan", subject=None, doc_ids=[], deadline=None,
        daily_minutes=60)
    manifest.update_study_plan(busy, status="active")
    busy_sid = manifest.append_plan_section(busy, title="Belegt", est_minutes=60)
    manifest.append_plan_block(
        busy, section_id=busy_sid, planned_date=start.isoformat(),
        planned_min=60)

    pid = manifest.create_study_plan(
        title="Zu reparieren", subject=None, doc_ids=[], deadline=None,
        daily_minutes=60)
    manifest.update_study_plan(pid, status="active")
    sid = manifest.append_plan_section(pid, title="Alt", est_minutes=30)
    manifest.append_plan_block(
        pid, section_id=sid,
        planned_date=(start - timedelta(days=1)).isoformat(), planned_min=30)
    out = study_plan.repair_overdue_blocks(pid, start=start)
    assert out["moves"][0]["to_date"] == "2026-09-15"


def test_build_schedule_respektiert_ruhetage(isolated_db):
    start = date(2026, 9, 14)  # Montag
    out = study_plan.build_schedule(
        [{"section_id": "s1", "est_minutes": 90}],
        daily_minutes=60, deadline=None, start=start, subject=None,
        rest_weekdays={0})
    assert all(b["planned_date"] != "2026-09-14" for b in out["blocks"])
    assert out["blocks"][0]["planned_date"] == "2026-09-15"


def test_repair_respektiert_ruhetage(isolated_db, monkeypatch):
    monkeypatch.setattr(
        study_plan.settings, "PLAN_MAX_DAILY_FOCUS_MIN", 60, raising=False)
    pid = _overdue_plan(daily_minutes=60, blocks=(30,))
    start = date.today()
    out = study_plan.repair_overdue_blocks(
        pid, start=start, rest_weekdays={start.weekday()})
    assert out["moves"][0]["to_date"] != start.isoformat()


def test_repair_verschiebt_zukuenftigen_block_vom_neuen_ruhetag(
        isolated_db, monkeypatch):
    monkeypatch.setattr(
        study_plan.settings, "PLAN_MAX_DAILY_FOCUS_MIN", 60, raising=False)
    start = date(2026, 9, 14)  # Montag
    pid = manifest.create_study_plan(
        title="Plan", subject=None, doc_ids=[], deadline=None, daily_minutes=60)
    manifest.update_study_plan(pid, status="active")
    sid = manifest.append_plan_section(pid, title="Thema", est_minutes=30)
    manifest.append_plan_block(
        pid, section_id=sid, planned_date=start.isoformat(), planned_min=30)
    preview = study_plan.repair_overdue_blocks(
        pid, start=start, rest_weekdays={0})
    assert preview["moves"][0]["to_date"] == "2026-09-15"
    study_plan.repair_overdue_blocks(
        pid, start=start, rest_weekdays={0}, apply=True)
    assert manifest.list_plan_blocks(pid)[0]["planned_date"] == "2026-09-15"


def test_alle_tage_ruhe_liefert_shortfall_statt_endlosschleife(isolated_db):
    out = study_plan.build_schedule(
        [{"section_id": "s1", "est_minutes": 90}],
        daily_minutes=60, deadline=None, start=date.today(),
        rest_weekdays=set(range(7)))
    assert out["blocks"] == []
    assert out["shortfall_minutes"] == 90
