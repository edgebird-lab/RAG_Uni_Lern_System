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


def test_sicher_und_falsch_markiert_overconfidence_im_fehlerheft(isolated_db):
    cid = student_flow.card_from_text(
        "Was ist X?", "X ist Y.", source="note", subject="BWL")
    card = manifest.get_cards_by_ids([cid])[0]
    study.rate_card(card, study.NICHT, confidence="sicher")
    errors = manifest.list_errors(subject="BWL")
    assert len(errors) == 1
    assert errors[0]["card_id"] == cid
    assert errors[0]["detail"].startswith("Sicher eingeschätzt")
    assert manifest.get_cards_by_ids([cid])[0]["deck"] == manifest.FEHLERHEFT_DECK
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


def test_keep_filter_option_haelt_leeres_fach():
    assert student_flow.keep_filter_option("BWL", []) == ["Alle", "BWL"]
    assert student_flow.keep_filter_option("Alle", ["Mathe"]) == ["Alle", "Mathe"]
    assert student_flow.keep_filter_option("BWL", ["BWL", "Mathe"]) == ["Alle", "BWL", "Mathe"]
    assert student_flow.keep_filter_option(None, ["Mathe"]) == ["Alle", "Mathe"]


def test_card_wipe_message_alle_weg():
    msg = student_flow.card_wipe_message(
        deleted=12, remaining=0, subject="BWL", subject_label="Betriebswirtschaft")
    assert "Alle 12" in msg
    assert "Betriebswirtschaft" in msg
    rest = student_flow.card_wipe_message(
        deleted=3, remaining=7, subject="BWL", document="Skript.pdf")
    assert "Es bleiben 7" in rest
    assert "Skript.pdf" in rest
    alle = student_flow.card_wipe_message(deleted=5, remaining=0)
    assert "Alle 5 Karteikarten wurden gelöscht." == alle


def test_delete_cards_matching_nur_ein_fach(isolated_db):
    student_flow.card_from_text("Q1", "A", subject="BWL")
    student_flow.card_from_text("Q2", "A", subject="BWL")
    student_flow.card_from_text("Q3", "A", subject="Mathe")
    manifest.delete_cards_matching(subject="BWL")
    assert manifest.count_cards(subject="BWL") == 0
    assert manifest.count_cards(subject="Mathe") == 1
    assert student_flow.keep_filter_option("BWL", manifest.study_subjects())[1] == "BWL"


def test_delete_cards_matching_nur_ein_dokument(isolated_db):
    student_flow.card_from_text("Q1", "A", subject="BWL", doc_id="docA")
    student_flow.card_from_text("Q2", "A", subject="BWL", doc_id="docB")
    student_flow.card_from_text("Q3", "A", subject="BWL", doc_id="docA")
    ids = manifest.list_card_ids_matching(subject="BWL", doc_ids=["docA"])
    assert len(ids) == 2
    manifest.delete_cards_matching(subject="BWL", doc_ids=["docA"])
    left = manifest.list_cards(subject="BWL")
    assert len(left) == 1
    assert left[0]["doc_id"] == "docB"


def test_purge_document_bibliothek_ohne_karten(isolated_db):
    from ragapp.ingestion import pipeline
    manifest.upsert_document(
        doc_id="d1", content_hash="h", source_path="x.pdf", filename="x.pdf",
        subject="BWL", filetype="pdf", num_chunks=0, num_questions=0,
        char_count=0, status="ok")
    student_flow.card_from_text("Q", "A", subject="BWL", doc_id="d1")
    out = pipeline.purge_document("d1", library=True, index=False, cards=False)
    assert out["library"] is True
    assert out["cards"] == 0
    assert manifest.get_document("d1") is None
    assert manifest.count_cards(subject="BWL") == 1


def test_purge_document_nur_karten(isolated_db):
    from ragapp.ingestion import pipeline
    manifest.upsert_document(
        doc_id="d1", content_hash="h", source_path="x.pdf", filename="x.pdf",
        subject="BWL", filetype="pdf", num_chunks=0, num_questions=0,
        char_count=0, status="ok")
    student_flow.card_from_text("Q1", "A", subject="BWL", doc_id="d1")
    student_flow.card_from_text("Q2", "A", subject="BWL", doc_id="d2")
    out = pipeline.purge_document("d1", library=False, index=False, cards=True)
    assert out["cards"] == 1
    assert manifest.get_document("d1") is not None
    assert manifest.count_cards(subject="BWL") == 1


def test_list_card_ids_matching_leere_doc_liste_ist_nichts(isolated_db):
    student_flow.card_from_text("Q", "A", subject="BWL")
    assert manifest.list_card_ids_matching(doc_ids=[]) == []
    assert manifest.count_cards(subject="BWL") == 1


def test_purge_via_existing_nur_karten(isolated_db):
    from ragapp.ui import _ingest_ui
    manifest.upsert_document(
        doc_id="d1", content_hash="h", source_path="x.pdf", filename="x.pdf",
        subject="BWL", filetype="pdf", num_chunks=0, num_questions=0,
        char_count=0, status="ok")
    student_flow.card_from_text("Q1", "A", subject="BWL", doc_id="d1")
    student_flow.card_from_text("Q2", "A", subject="BWL", doc_id="d2")
    res = _ingest_ui._purge_via_existing(["d1"], library=False, index=False, cards=True)
    assert res["cards"] == 1
    assert manifest.get_document("d1") is not None
    assert manifest.count_cards(subject="BWL") == 1
    from ragapp.ingestion.pipeline import purge_summary
    msg = purge_summary({"library": 1, "index": 1, "cards": 4, "errors": []})
    assert "Bibliothek" in msg
    assert "Suchindex" in msg
    assert "4 Karteikarte" in msg


def test_set_document_subject(isolated_db):
    manifest.upsert_document(
        doc_id="d1", content_hash="h", source_path="x.pdf", filename="x.pdf",
        subject="Alt", filetype="pdf", num_chunks=0, num_questions=0,
        char_count=0, status="ok")
    manifest.set_document_subject("d1", "Neu")
    docs = [dict(r) for r in manifest.list_documents()]
    assert docs[0]["subject"] == "Neu"


def test_card_looks_like_formula_erkennt_latex_und_gleichung():
    assert student_flow.card_looks_like_formula({
        "front": r"$\int_0^1 x^2 dx$", "back": "1/3"})
    assert student_flow.card_looks_like_formula({
        "front": "f(x)=3x+2", "back": "Gerade"})
    assert not student_flow.card_looks_like_formula({
        "front": "Was ist ein Deckungsbeitrag?", "back": "Erlös minus variable Kosten."})


def test_sprint_inventory_und_prefer_formula_vs_definition(isolated_db):
    student_flow.card_from_text(
        r"Ableitung von $x^2$", "2x", subject="Analysis", source="note")
    student_flow.card_from_text(
        "Was ist der Deckungsbeitrag?", "Erlös minus variable Kosten.",
        subject="BWL", source="note")
    student_flow.card_from_text(
        "Eine sehr lange Frage, die bewusst keine kurze Merkliste ist und "
        "auch keinen Rechenausdruck enthält, sondern einen ganzen Absatz.",
        "Lange Antwort " * 20, subject="BWL", source="note")

    inv_all = student_flow.sprint_inventory()
    assert inv_all["formula_n"] == 1
    assert inv_all["definition_n"] >= 1

    inv_ana = student_flow.sprint_inventory(subject="Analysis")
    assert inv_ana["formula_n"] == 1
    assert inv_ana["definition_n"] == 0

    only_f = student_flow.sprint_cards(subject="BWL", prefer="formula")
    assert only_f == []
    defs = student_flow.sprint_cards(subject="BWL", prefer="definition")
    assert defs and all(not student_flow.card_looks_like_formula(c) for c in defs)

    auto_ana = student_flow.sprint_cards(subject="Analysis", prefer="auto")
    assert len(auto_ana) == 1
    assert student_flow.card_looks_like_formula(auto_ana[0])


def test_course_snapshot_aggregiert_fach(isolated_db):
    future = (date.today() + timedelta(days=10)).isoformat()
    manifest.upsert_exam("BWL", exam_date=future)
    manifest.upsert_document(
        doc_id="d-bwl", content_hash="h", source_path="/bwl.pdf",
        filename="bwl.pdf", subject="BWL", filetype="pdf",
        num_chunks=2, num_questions=0, char_count=100, status="ok")
    manifest.upsert_timetable_slot(
        subject="BWL", weekday=date.today().weekday(),
        start_time="23:59", end_time="24:00", room="H1")
    snap = student_flow.course_snapshot("BWL")
    assert snap["subject"] == "BWL"
    assert snap["exam_date"] == future
    assert snap["days_to_exam"] == 10
    assert snap["evenings"] == 10
    assert snap["doc_count"] == 1
    assert snap["due_cards"] == 0
    assert snap["readiness_pct"] == 0
    assert snap["weak_topics"] == []
    assert snap["next_lecture"]["room"] == "H1"
    assert snap["next_action"] in ("lernen", "planen", "Unterlagen", "Prüfung")
    assert snap["next_action"] == "Prüfung"


def test_course_snapshot_empfiehlt_unterlagen_ohne_docs(isolated_db):
    snap = student_flow.course_snapshot("Mathe")
    assert snap["doc_count"] == 0
    assert snap["next_action"] == "Unterlagen"


def test_add_course_material_schreibt_in_fachordner(isolated_db, tmp_path, monkeypatch):
    src = tmp_path / "quellen"
    monkeypatch.setattr("ragapp.config.SOURCE_DIR", src)
    monkeypatch.setattr(
        "ragapp.ingestion.pipeline.ingest_file",
        lambda path, **kw: {"status": "ok", "file": str(path)})
    out = student_flow.add_course_material(
        "BWL", text="Fixkosten sind unabhängig von der Menge.", title="VL Kosten")
    folder = src / "BWL"
    assert folder.is_dir()
    mds = list(folder.glob("*.md"))
    assert mds
    assert "Fixkosten" in mds[0].read_text(encoding="utf-8")
    docs = [d for d in manifest.list_documents() if d["subject"] == "BWL"]
    assert docs
    assert out["status"] == "ok"
    snap = student_flow.course_snapshot("BWL")
    assert snap["doc_count"] >= 1


def test_add_course_material_ohne_fach_bricht_ehrlich_ab(isolated_db):
    out = student_flow.add_course_material("", text="irgendwas")
    assert out["status"] == "no_subject"
    assert out["path"] is None


def test_scan_inbox_once_verschiebt_in_fachordner(isolated_db, tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    src = tmp_path / "quellen"
    inbox.mkdir()
    (inbox / "folie.md").write_text("# Folie\n\nInhalt.", encoding="utf-8")
    monkeypatch.setattr("ragapp.config.INBOX_DIR", inbox)
    monkeypatch.setattr("ragapp.config.SOURCE_DIR", src)
    monkeypatch.setattr(
        "ragapp.ingestion.pipeline.ingest_file",
        lambda path, **kw: {"status": "ok", "file": str(path)})
    res = student_flow.scan_inbox_once(subject="Mathe")
    assert res["scanned"] == 1
    assert res["ok"] == 1
    assert not (inbox / "folie.md").exists()
    assert (src / "Mathe" / "folie.md").is_file()
