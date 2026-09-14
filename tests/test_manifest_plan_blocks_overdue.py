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


def test_neuberechnung_erhaelt_erledigte_bloecke_und_zieht_sie_ab(isolated_db):
    pid = _make_plan_with_blocks([
        {"section_id": "sec-a", "planned_date": "2026-09-01", "planned_min": 25},
        {"section_id": "sec-a", "planned_date": "2026-09-02", "planned_min": 25},
    ])
    first = manifest.list_plan_blocks(pid)[0]
    manifest.add_block_actual_min(first["block_id"], 22)
    manifest.set_block_done(first["block_id"], True, via="pomodoro")
    manifest.replace_plan_blocks(pid, [
        {"section_id": "sec-a", "planned_date": "2026-09-10", "planned_min": 30},
        {"section_id": "sec-a", "planned_date": "2026-09-11", "planned_min": 20},
    ])
    rows = manifest.list_plan_blocks(pid)
    done = [b for b in rows if b["done"]]
    open_blocks = [b for b in rows if not b["done"]]
    assert len(done) == 1
    assert done[0]["block_id"] == first["block_id"]
    assert done[0]["done_via"] == "pomodoro"
    assert done[0]["actual_min"] == 22
    assert sum(b["planned_min"] for b in open_blocks) == 25


def test_neue_gliederung_verknuepft_erledigten_block_ueber_quelle(isolated_db):
    pid = manifest.create_study_plan(
        title="Plan", subject="BWL", doc_ids=["d1"], deadline=None,
        daily_minutes=30)
    refs = [{"doc_id": "d1", "filename": "x.pdf", "section": "Kapitel 1"}]
    manifest.replace_plan_sections(pid, [{
        "title": "Alter Titel", "est_minutes": 30, "source_refs": refs}])
    old_sid = manifest.list_plan_sections(pid)[0]["section_id"]
    manifest.replace_plan_blocks(pid, [{
        "section_id": old_sid, "planned_date": "2026-09-01",
        "planned_min": 30}])
    block = manifest.list_plan_blocks(pid)[0]
    manifest.set_block_done(block["block_id"], True, via="manual")

    manifest.replace_plan_sections(pid, [{
        "title": "Völlig neu formulierter Titel", "est_minutes": 30,
        "source_refs": refs}])
    new_sid = manifest.list_plan_sections(pid)[0]["section_id"]
    assert manifest.list_plan_blocks(pid)[0]["section_id"] == new_sid
    manifest.replace_plan_blocks(pid, [{
        "section_id": new_sid, "planned_date": "2026-09-10",
        "planned_min": 30}])
    rows = manifest.list_plan_blocks(pid)
    assert len(rows) == 1
    assert rows[0]["done"] == 1
