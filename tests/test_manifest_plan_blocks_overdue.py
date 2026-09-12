"""Tests für den Lernplan-Rückstand (manifest.list_overdue_plan_blocks()/
reschedule_overdue_blocks()) - ein verpasster Block sollte sichtbar bleiben
und sich gesammelt auf ein neues Datum verschieben lassen, statt im
Lernplan-Verlauf unbemerkt zurückzubleiben. Isolierte Temp-DB, niemals die
echte data/manifest.db (gleiches Muster wie test_manifest_audio_overviews.py)."""
from __future__ import annotations

import pytest

from ragapp import manifest


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "manifest_test.db"
    monkeypatch.setattr(manifest, "MANIFEST_DB", db_path)
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)
    return db_path


def _make_plan_with_blocks(blocks: list[dict]) -> str:
    pid = manifest.create_study_plan(
        title="Testplan", subject="mathe", doc_ids=["d1"], deadline=None, daily_minutes=60)
    manifest.replace_plan_blocks(pid, blocks)
    return pid


def test_list_overdue_plan_blocks_findet_nur_unerledigte_vergangene(isolated_db):
    pid = _make_plan_with_blocks([
        {"section_id": None, "planned_date": "2026-09-01", "planned_min": 25},
        {"section_id": None, "planned_date": "2026-09-05", "planned_min": 25},
        {"section_id": None, "planned_date": "2026-09-10", "planned_min": 25},  # heute/zukuenftig
    ])
    blocks = manifest.list_plan_blocks(pid)
    # Den Block vom 2026-09-05 schon erledigt markieren - darf NICHT als
    # rueckstaendig auftauchen, obwohl das Datum in der Vergangenheit liegt.
    _done_block = next(b for b in blocks if b["planned_date"] == "2026-09-05")
    manifest.set_block_done(_done_block["block_id"], True, via="manual")

    overdue = manifest.list_overdue_plan_blocks("2026-09-10")
    assert [b["planned_date"] for b in overdue] == ["2026-09-01"]
    assert overdue[0]["plan_title"] == "Testplan"
    assert overdue[0]["plan_subject"] == "mathe"


def test_list_overdue_plan_blocks_zukuenftige_bleiben_aussen_vor(isolated_db):
    _make_plan_with_blocks([
        {"section_id": None, "planned_date": "2026-09-15", "planned_min": 25},
    ])
    assert manifest.list_overdue_plan_blocks("2026-09-10") == []


def test_list_overdue_plan_blocks_kann_auf_einen_plan_gefiltert_werden(isolated_db):
    pid1 = _make_plan_with_blocks([
        {"section_id": None, "planned_date": "2026-09-01", "planned_min": 25}])
    pid2 = _make_plan_with_blocks([
        {"section_id": None, "planned_date": "2026-09-02", "planned_min": 25}])
    assert len(manifest.list_overdue_plan_blocks("2026-09-10")) == 2
    only_1 = manifest.list_overdue_plan_blocks("2026-09-10", plan_id=pid1)
    assert len(only_1) == 1
    assert only_1[0]["plan_id"] == pid1
    assert pid2  # nur zur Klarheit referenziert


def test_reschedule_overdue_blocks_verschiebt_nur_dieses_plans_rueckstand(isolated_db):
    pid1 = _make_plan_with_blocks([
        {"section_id": None, "planned_date": "2026-09-01", "planned_min": 25},
        {"section_id": None, "planned_date": "2026-09-02", "planned_min": 25},
    ])
    pid2 = _make_plan_with_blocks([
        {"section_id": None, "planned_date": "2026-09-01", "planned_min": 30},
    ])
    n = manifest.reschedule_overdue_blocks(pid1, "2026-09-10", "2026-09-10")
    assert n == 2
    assert {b["planned_date"] for b in manifest.list_plan_blocks(pid1)} == {"2026-09-10"}
    # Anderer Plan bleibt unangetastet.
    assert manifest.list_plan_blocks(pid2)[0]["planned_date"] == "2026-09-01"


def test_reschedule_overdue_blocks_laesst_bereits_erledigte_in_ruhe(isolated_db):
    pid = _make_plan_with_blocks([
        {"section_id": None, "planned_date": "2026-09-01", "planned_min": 25},
    ])
    block = manifest.list_plan_blocks(pid)[0]
    manifest.set_block_done(block["block_id"], True, via="manual")
    n = manifest.reschedule_overdue_blocks(pid, "2026-09-10", "2026-09-10")
    assert n == 0
    assert manifest.list_plan_blocks(pid)[0]["planned_date"] == "2026-09-01"


def test_reschedule_overdue_blocks_gibt_null_zurueck_wenn_nichts_rueckstaendig(isolated_db):
    pid = _make_plan_with_blocks([
        {"section_id": None, "planned_date": "2026-09-15", "planned_min": 25},
    ])
    assert manifest.reschedule_overdue_blocks(pid, "2026-09-10", "2026-09-10") == 0
