"""Alltags-Hilfen: Fehlerheft, Vorlesung, Karten aus Text, Timer, Klausur-Items."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from ragapp import analytics, manifest, planner, student_flow, study


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "manifest_test.db"
    monkeypatch.setattr(manifest, "MANIFEST_DB", db_path)
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)
    monkeypatch.setattr(analytics, "MANIFEST_DB", db_path)
    return db_path


def test_cards_from_markdown_headings_and_defs(isolated_db):
    md = """# Titel

Deckungsbeitrag: Erlös minus variable Kosten.

## Break-even

Der Break-even ist die Menge, bei der der Gewinn null ist.
"""
    ids = student_flow.cards_from_markdown(md, subject="BWL", source="summary")
    assert len(ids) >= 2
    cards = manifest.list_cards(subject="BWL")
    fronts = {c["front"] for c in cards}
    assert any("Deckungsbeitrag" in f for f in fronts)
    assert any("Break-even" in f for f in fronts)


def test_card_from_text_roundtrip(isolated_db):
    cid = student_flow.card_from_text("Was ist X?", "X ist Y.", source="note", subject="Mathe")
    assert cid and cid.startswith("note::")
    row = manifest.list_cards(subject="Mathe")[0]
    assert row["front"] == "Was ist X?"
    assert row["answer"] == "X ist Y."


def test_capture_lecture_creates_note_and_cards(isolated_db):
    text = (
        "Kostenrechnung in der Vorlesung.\n\n"
        "Fixkosten: Kosten, die unabhängig von der Menge anfallen.\n\n"
        "Variable Kosten steigen mit der Ausbringungsmenge. "
        "Das ist zentral für die Preisuntergrenze."
    )
    out = student_flow.capture_lecture(text, subject="BWL", title="VL Kosten")
    assert out["note_id"]
    note = manifest.get_note(out["note_id"])
    assert "Fixkosten" in note["body"]
    assert out["goals"]
    assert out["card_ids"]


def test_capture_lecture_appends_plan_block(isolated_db):
    pid = manifest.create_study_plan(
        title="BWL", subject="BWL", doc_ids=[], deadline=None, daily_minutes=45)
    manifest.update_study_plan(pid, status="active")
    out = student_flow.capture_lecture(
        "Thema A ist wichtig genug für eine Karte und ein Lernziel heute Abend.",
        subject="BWL", title="VL A")
    assert out["block_id"]
    secs = manifest.list_plan_sections(pid)
    assert any("Vorlesung sichern" in (s["title"] or "") for s in secs)
    # Zweiter Capture mit gleichem Titel darf den Plan nicht verdoppeln
    out2 = student_flow.capture_lecture("Noch mehr Text zum gleichen Titel.",
                                       subject="BWL", title="VL A")
    assert out2["block_id"] is None
    assert len(manifest.list_plan_sections(pid)) == 1


def test_fehlerheft_open_and_resolve(isolated_db):
    cid = student_flow.card_from_text("Q", "A", source="chat", subject="X")
    student_flow.record_error(source="card", card_id=cid, front="Q", subject="X")
    assert manifest.count_open_errors() == 1
    cards = student_flow.fehlerheft_cards()
    assert any(c["card_id"] == cid for c in cards)
    study.rate_card(cards[0], study.GEWUSST)
    assert manifest.count_open_errors() == 0


def test_exam_attempt_items_persist(isolated_db):
    aid = manifest.log_exam_attempt(70, 2, items=[
        {"card_id": "c1", "front": "F1", "typed": "x", "score": 20, "subject": "A"},
        {"card_id": "c2", "front": "F2", "typed": "y", "score": 90, "subject": "A"},
    ])
    items = manifest.list_exam_attempt_items(aid)
    assert len(items) == 2
    assert items[0]["score"] == 20


def test_timer_state_roundtrip(isolated_db):
    assert manifest.load_timer_state() is None
    manifest.save_timer_state({"pomo_running": True, "pomo_subject": "BWL"})
    loaded = manifest.load_timer_state()
    assert loaded["pomo_subject"] == "BWL"
    manifest.clear_timer_state()
    assert manifest.load_timer_state() is None


def test_evenings_until_exam_positive():
    future = (date.today() + timedelta(days=10)).isoformat()
    info = student_flow.evenings_until_exam(future)
    assert info["days"] == 10
    assert info["evenings"] == 10
    assert info["total_minutes"] == 450


def test_today_snapshot_has_evenings_and_errors(isolated_db):
    future = (date.today() + timedelta(days=4)).isoformat()
    manifest.upsert_exam("BWL", exam_date=future)
    snap = planner.today_snapshot()
    assert snap["evenings"]["days"] == 4
    assert snap["open_errors"] == 0


def test_reschedule_all_overdue(isolated_db):
    pid = manifest.create_study_plan(
        title="P", subject="BWL", doc_ids=[], deadline=None, daily_minutes=45)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    manifest.replace_plan_blocks(pid, [
        {"section_id": None, "planned_date": yesterday, "planned_min": 25},
    ])
    n = student_flow.reschedule_all_overdue_today()
    assert n == 1
    blocks = manifest.list_plan_blocks(pid)
    assert blocks[0]["planned_date"] == date.today().isoformat()


def test_notes_context_lists_body(isolated_db):
    manifest.create_note(subject="BWL", title="Merksatz", body="Deckungsbeitrag merken.")
    ctx = student_flow.notes_context("BWL", "Deckungsbeitrag")
    assert "Deckungsbeitrag" in ctx
    assert "Eigene Notiz" in ctx


def test_set_document_subject(isolated_db):
    manifest.upsert_document(
        doc_id="d1", content_hash="h", source_path="x.pdf", filename="x.pdf",
        subject="Alt", filetype="pdf", num_chunks=0, num_questions=0,
        char_count=0, status="ok")
    manifest.set_document_subject("d1", "Neu")
    docs = [dict(r) for r in manifest.list_documents()]
    assert docs[0]["subject"] == "Neu"
