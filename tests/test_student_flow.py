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


def test_is_hard_gap_nur_unter_40_oder_nicht_gewusst():
    assert student_flow.is_hard_gap(score=0)
    assert student_flow.is_hard_gap(score=39)
    assert not student_flow.is_hard_gap(score=40)
    assert not student_flow.is_hard_gap(score=74)
    assert not student_flow.is_hard_gap(score=75)
    assert student_flow.is_hard_gap(rating=study.NICHT)
    assert not student_flow.is_hard_gap(rating=study.HALB)
    assert not student_flow.is_hard_gap(rating=study.GEWUSST)


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
    manifest.update_study_plan(pid, status="active")
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


def test_course_snapshot_ohne_index_empfiehlt_unterlagen_nicht_lernplan(isolated_db):
    manifest.upsert_document(
        doc_id="d-raw", content_hash="h", source_path="/raw.md",
        filename="raw.md", subject="BWL", filetype="md",
        num_chunks=0, num_questions=0, char_count=10, status="ok", use_rag=False)
    snap = student_flow.course_snapshot("BWL")
    assert snap["doc_count"] == 1
    assert snap["next_action"] == "Unterlagen"


def test_inbox_ist_kein_kurs_im_cockpit():
    assert student_flow.is_placeholder_subject("31")
    assert student_flow.is_placeholder_subject("inbox")
    assert student_flow.is_placeholder_subject("Modul 4 (Fortsetzung")
    assert student_flow.is_placeholder_subject("BWL-")
    assert student_flow.is_placeholder_subject("IT-Recht und IT-Comp")
    assert student_flow.looks_truncated_subject("IT-Recht und IT-Comp")
    assert not student_flow.looks_truncated_subject("IT-Sicherheit")
    assert not student_flow.looks_truncated_subject("Unternehmensführung")
    assert not student_flow.is_placeholder_subject("Livetest")
    assert not student_flow.is_placeholder_subject("IT-Sicherheit")
    assert student_flow.is_fixture_subject("Livetest")
    assert student_flow.is_fixture_subject("Livetest-Leer")
    assert not student_flow.is_fixture_subject("IT-Sicherheit")
    assert student_flow.is_exam_fragment({"subject": "31", "exam_date": None})
    assert student_flow.is_exam_fragment({"subject": "IT-Recht und IT-Comp", "exam_date": None})
    assert not student_flow.is_exam_fragment({"subject": "31", "exam_date": "2026-07-01"})
    assert not student_flow.is_exam_fragment({"subject": "Livetest", "exam_date": None})
    assert not student_flow.is_exam_fragment(
        {"subject": "Unternehmensführung", "exam_date": None})
    skip = student_flow.course_cockpit_bucket(
        {"subject": "inbox", "due_cards": 0, "doc_count": 2, "days_to_exam": None},
        has_cards=False)
    assert skip == "skip"
    assert student_flow.course_cockpit_bucket(
        {"subject": "Livetest", "due_cards": 3, "doc_count": 1, "days_to_exam": 21},
        has_cards=True) == "skip"
    assert student_flow.course_cockpit_bucket(
        {"subject": "IT-Recht und IT-Comp", "due_cards": 0, "doc_count": 0,
         "days_to_exam": None}, has_cards=False) == "skip"
    assert student_flow.is_exam_fragment({"subject": "31", "exam_date": None})
    assert not student_flow.is_exam_fragment({"subject": "31", "exam_date": "2026-07-01"})
    assert not student_flow.is_exam_fragment({"subject": "Livetest", "exam_date": None})
    skip = student_flow.course_cockpit_bucket(
        {"subject": "inbox", "due_cards": 0, "doc_count": 2, "days_to_exam": None},
        has_cards=False)
    assert skip == "skip"
    assert student_flow.course_cockpit_bucket(
        {"subject": "BWL", "due_cards": 3, "doc_count": 1, "days_to_exam": 21},
        has_cards=True) == "active"
    assert student_flow.course_cockpit_bucket(
        {"subject": "Analysis", "due_cards": 0, "doc_count": 1, "days_to_exam": None},
        has_cards=False) == "stoff"
    assert student_flow.course_cockpit_bucket(
        {"subject": "Leer", "due_cards": 0, "doc_count": 0, "days_to_exam": 45},
        has_cards=False) == "import"
    assert student_flow.course_cockpit_bucket(
        {"subject": "Klausur-bald", "due_cards": 0, "doc_count": 0, "days_to_exam": 10},
        has_cards=False) == "active"


def test_purge_import_remnant_exams_laesst_echte_faecher(isolated_db):
    manifest.upsert_exam("31", exam_date=None)
    manifest.upsert_exam("IT-Recht und IT-Comp", exam_date=None)
    manifest.upsert_exam("Unternehmensführung", exam_date=None)
    manifest.upsert_exam("Livetest", exam_date=None)
    manifest.upsert_exam("BWL", exam_date="2026-07-15")
    n = student_flow.purge_import_remnant_exams()
    assert n == 2
    subjects = {e["subject"] for e in manifest.list_exams()}
    assert "31" not in subjects
    assert "IT-Recht und IT-Comp" not in subjects
    assert "Livetest" in subjects
    assert "Unternehmensführung" in subjects
    assert "BWL" in subjects


def test_course_snapshot_empfiehlt_unterlagen_ohne_docs(isolated_db):
    snap = student_flow.course_snapshot("Mathe")
    assert snap["doc_count"] == 0
    assert snap["next_action"] == "Unterlagen"


def test_default_plan_deadline_ohne_termin_ist_none(isolated_db):
    assert student_flow.default_plan_deadline("BWL") is None
    assert student_flow.default_plan_deadline() is None


def test_default_plan_deadline_nimmt_nur_das_eigene_fach(isolated_db):
    future = (date.today() + timedelta(days=12)).isoformat()
    other = (date.today() + timedelta(days=4)).isoformat()
    manifest.upsert_exam("BWL", exam_date=future)
    manifest.upsert_exam("Livetest", exam_date=other)
    assert student_flow.default_plan_deadline("BWL") == future
    assert student_flow.default_plan_deadline("Mathe") is None
    assert student_flow.default_plan_deadline() == future


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


def test_add_course_photo_erscheint_auch_ohne_ocr_als_unterlage(
        isolated_db, tmp_path, monkeypatch):
    src = tmp_path / "quellen"
    monkeypatch.setattr("ragapp.config.SOURCE_DIR", src)
    monkeypatch.setattr("ragapp.config.PROJECT_ROOT", tmp_path)
    out = student_flow.add_course_material(
        "BWL", image_bytes=b"\xff\xd8fake-jpeg")
    docs = [dict(d) for d in manifest.list_documents()]
    assert out["doc_id"]
    assert len(docs) == 1
    assert docs[0]["subject"] == "BWL"
    assert docs[0]["filetype"] == "jpg"
    assert student_flow.course_snapshot("BWL")["doc_count"] == 1


def test_add_course_material_bleibt_bei_ingestion_fehler_sichtbar(
        isolated_db, tmp_path, monkeypatch):
    src = tmp_path / "quellen"
    monkeypatch.setattr("ragapp.config.SOURCE_DIR", src)
    monkeypatch.setattr("ragapp.config.PROJECT_ROOT", tmp_path)

    def _boom(*args, **kwargs):
        raise RuntimeError("Index aus")

    monkeypatch.setattr("ragapp.ingestion.pipeline.ingest_file", _boom)
    out = student_flow.add_course_material(
        "BWL", file_bytes=b"# Stoff", filename="stoff.md")
    assert out["status"] == "error"
    assert student_flow.course_snapshot("BWL")["doc_count"] == 1
    doc = manifest.list_documents()[0]
    assert doc["status"] == "error"
    assert doc["use_rag"] == 1
    assert len(manifest.list_index_retry_jobs()) == 1


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


def test_scan_inbox_fehlerdatei_bleibt_im_kurs_sichtbar(
        isolated_db, tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    src = tmp_path / "quellen"
    inbox.mkdir()
    (inbox / "kaputt.md").write_text("# Stoff", encoding="utf-8")
    monkeypatch.setattr("ragapp.config.INBOX_DIR", inbox)
    monkeypatch.setattr("ragapp.config.SOURCE_DIR", src)
    monkeypatch.setattr("ragapp.config.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        "ragapp.ingestion.pipeline.ingest_file",
        lambda path, **kw: {"status": "error"})
    result = student_flow.scan_inbox_once(subject="Mathe")
    assert result["errors"]
    assert student_flow.course_snapshot("Mathe")["doc_count"] == 1
    assert manifest.list_documents()[0]["status"] == "error"
    assert len(manifest.list_index_retry_jobs()) == 1


def test_backfill_failed_index_jobs_liest_sqlite_rows(isolated_db):
    """Live-Test: Dokumente-Seite rief .get() auf sqlite3.Row und stürzte ab."""
    manifest.upsert_document(
        doc_id="err-1", content_hash="h", source_path="quellen/BWL/alt.md",
        filename="alt.md", subject="BWL", filetype="md",
        num_chunks=0, num_questions=0, char_count=12, status="error",
        use_rag=True)
    manifest.upsert_document(
        doc_id="ok-1", content_hash="h2", source_path="quellen/BWL/ok.md",
        filename="ok.md", subject="BWL", filetype="md",
        num_chunks=3, num_questions=0, char_count=40, status="ok",
        use_rag=True)
    assert student_flow.backfill_failed_index_jobs() == 1
    jobs = manifest.list_index_retry_jobs()
    assert len(jobs) == 1
    assert jobs[0]["source_path"] == "quellen/BWL/alt.md"
    assert student_flow.backfill_failed_index_jobs() == 0


def test_index_retry_queue_ist_idempotent_und_wird_erfolgreich_abgebaut(
        isolated_db, tmp_path, monkeypatch):
    source = tmp_path / "skript.txt"
    source.write_text("Lernstoff", encoding="utf-8")
    first = student_flow.enqueue_index_retry(source, "BWL", error="Modell aus")
    second = student_flow.enqueue_index_retry(source, "BWL", error="Noch aus")
    assert first == second
    assert len(manifest.list_index_retry_jobs()) == 1

    monkeypatch.setattr(
        "ragapp.ingestion.pipeline.ingest_file",
        lambda *args, **kwargs: {"status": "ok"})
    result = student_flow.retry_index_queue(force=True)
    assert result == {"processed": 1, "ok": 1, "failed": 0, "errors": []}
    assert manifest.list_index_retry_jobs() == []
    done = manifest.list_index_retry_jobs(include_done=True)
    assert done[0]["status"] == "done"
    assert done[0]["attempts"] == 1


def test_index_retry_queue_behaelt_fehler_mit_backoff(
        isolated_db, tmp_path, monkeypatch):
    source = tmp_path / "folie.txt"
    source.write_text("Lernstoff", encoding="utf-8")
    student_flow.enqueue_index_retry(source, "BWL", error="Erster Fehler")
    monkeypatch.setattr(
        "ragapp.ingestion.pipeline.ingest_file",
        lambda *args, **kwargs: {"status": "error", "error": "VRAM voll"})
    result = student_flow.retry_index_queue(force=True)
    assert result["failed"] == 1
    job = manifest.list_index_retry_jobs()[0]
    assert job["status"] == "failed"
    assert job["attempts"] == 1
    assert job["next_attempt_at"] > 0
    assert "VRAM voll" in job["last_error"]


def test_ocr_luecke_wird_automatisch_job(isolated_db, tmp_path, monkeypatch):
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF fake")
    monkeypatch.setattr("ragapp.config.PROJECT_ROOT", tmp_path)
    manifest.upsert_document(
        doc_id="scan-1", content_hash="h", source_path="scan.pdf",
        filename="scan.pdf", subject="BWL", filetype="pdf",
        num_chunks=0, num_questions=0, char_count=0, status="ocr_needed",
        use_rag=True)
    assert student_flow.enqueue_ocr_jobs() == 1
    job = manifest.list_index_retry_jobs()[0]
    assert job["job_type"] == "ocr"
    assert job["doc_id"] == "scan-1"
    assert student_flow.enqueue_ocr_jobs() == 0


def test_ocr_worker_respektiert_archivierte_dokumente(
        isolated_db, tmp_path, monkeypatch):
    source = tmp_path / "archiv.pdf"
    source.write_bytes(b"%PDF fake")
    monkeypatch.setattr("ragapp.config.PROJECT_ROOT", tmp_path)
    manifest.upsert_document(
        doc_id="archiv-1", content_hash="h", source_path="archiv.pdf",
        filename="archiv.pdf", subject="BWL", filetype="pdf",
        num_chunks=0, num_questions=0, char_count=0, status="ocr_needed",
        use_rag=False)
    assert student_flow.enqueue_ocr_jobs() == 0
    assert manifest.list_index_retry_jobs() == []


def test_reconcile_erkennt_chroma_drift_und_baut_bm25_neu(
        isolated_db, tmp_path, monkeypatch):
    import sys
    import types
    source = tmp_path / "skript.pdf"
    source.write_bytes(b"%PDF fake")
    monkeypatch.setattr("ragapp.config.PROJECT_ROOT", tmp_path)
    manifest.upsert_document(
        doc_id="doc-1", content_hash="h", source_path="skript.pdf",
        filename="skript.pdf", subject="BWL", filetype="pdf",
        num_chunks=2, num_questions=0, char_count=100, status="ok",
        use_rag=True)

    class _Store:
        def get_all_chunks(self):
            return [{"id": "c1", "document": "x", "meta": {"doc_id": "doc-1"}}]

    rebuilt = []
    monkeypatch.setitem(
        sys.modules, "ragapp.retrieval.vectorstore",
        types.SimpleNamespace(get_vectorstore=lambda: _Store()))
    monkeypatch.setitem(
        sys.modules, "ragapp.retrieval.bm25_index",
        types.SimpleNamespace(
            get_bm25=lambda: types.SimpleNamespace(metas=[]),
            rebuild_bm25_from_store=lambda: rebuilt.append(True)))
    result = student_flow.reconcile_indexes()
    assert result["mismatches"][0]["chroma"] == 1
    assert result["queued"] == 1
    assert result["bm25_rebuilt"] is True
    assert rebuilt == [True]


def test_recovery_worker_startet_nur_einmal(monkeypatch):
    calls = []
    monkeypatch.setenv("RAG_AUTO_RECOVERY", "1")
    monkeypatch.setenv("RAG_RECOVERY_ONCE", "1")
    monkeypatch.setattr(student_flow, "_RECOVERY_STARTED", False)
    monkeypatch.setattr(
        student_flow, "backfill_failed_index_jobs",
        lambda: calls.append("backfill"))
    monkeypatch.setattr(
        student_flow, "enqueue_ocr_jobs", lambda: calls.append("ocr"))
    monkeypatch.setattr(
        student_flow, "reconcile_indexes",
        lambda **kwargs: calls.append("reconcile"))
    monkeypatch.setattr(
        student_flow, "retry_index_queue",
        lambda **kwargs: calls.append("retry"))
    assert student_flow.start_recovery_worker() is True
    student_flow._RECOVERY_THREAD.join(timeout=2)
    assert calls == ["backfill", "ocr", "reconcile", "retry"]
    assert student_flow.start_recovery_worker() is False


def test_cards_for_prefill_prefers_card_ids(isolated_db):
    a = student_flow.card_from_text("A?", "aa", subject="BWL", doc_id="d1")
    b = student_flow.card_from_text("B?", "bb", subject="BWL", doc_id="d2")
    cards = student_flow.cards_for_prefill({
        "card_ids": [b], "doc_ids": ["d1"], "limit": 10,
    })
    assert [c["card_id"] for c in cards] == [b]
    assert a not in [c["card_id"] for c in cards]


def test_cards_for_prefill_uses_doc_ids(isolated_db):
    a = student_flow.card_from_text("A?", "aa", subject="BWL", doc_id="d1")
    student_flow.card_from_text("B?", "bb", subject="BWL", doc_id="d2")
    cards = student_flow.cards_for_prefill({"doc_ids": ["d1"], "limit": 10})
    assert [c["card_id"] for c in cards] == [a]


def test_prefill_from_plan_block_carries_section_docs(isolated_db):
    pid = manifest.create_study_plan(
        title="P", subject="BWL", doc_ids=["fallback"],
        deadline=None, daily_minutes=45)
    sid = manifest.append_plan_section(
        pid, title="Kosten", summary="", est_minutes=25,
        source_refs=[{"doc_id": "d1", "filename": "a.pdf", "section": "1.1"}])
    manifest.append_plan_block(
        pid, section_id=sid, planned_date=date.today().isoformat(),
        planned_min=25)
    bid = manifest.list_plan_blocks(pid)[0]["block_id"]
    pre = student_flow.prefill_from_plan_block(bid, limit=8)
    assert pre["subject"] == "BWL"
    assert pre["doc_ids"] == ["d1"]
    assert pre["topics"] == ["Kosten"]
    assert pre["block_id"] == bid
    assert pre["limit"] == 8
    student_flow.mark_plan_block_done(bid, via="manual")
    assert manifest.get_plan_block(bid)["done"] == 1


def test_formelsammlung_note_upsert(isolated_db):
    nid = student_flow.upsert_formelsammlung("BWL", "DB = E - Kv")
    assert student_flow.formelsammlung_text("BWL") == "DB = E - Kv"
    nid2 = student_flow.upsert_formelsammlung("BWL", "neu")
    assert nid2 == nid
    assert student_flow.formelsammlung_text("BWL") == "neu"
    notes = manifest.list_notes(subject="BWL", collection="Formelsammlung")
    assert len(notes) == 1
    assert notes[0]["pinned"]


def test_resolve_error_lowers_open_count(isolated_db):
    cid = student_flow.card_from_text("Q", "A", source="chat", subject="X")
    eid = student_flow.record_error(
        source="card", card_id=cid, front="Q", subject="X")
    assert manifest.count_open_errors() == 1
    manifest.resolve_error(eid)
    assert manifest.count_open_errors() == 0


def test_apply_oral_score_rates_card_and_errors(isolated_db):
    cid = student_flow.card_from_text("Was ist X?", "X ist Y.", subject="BWL")
    student_flow.apply_oral_score(cid, 80, subject="BWL", front="Was ist X?")
    row = manifest.get_cards_by_ids([cid])[0]
    assert int(row.get("reps") or 0) >= 1
    student_flow.apply_oral_score(cid, 10, subject="BWL", front="Was ist X?")
    errors = manifest.list_errors(subject="BWL")
    assert any(e.get("source") == "oral" for e in errors)


def test_normalize_exam_prefill_defaults_and_caps():
    assert student_flow.normalize_exam_prefill({})["mode"] == "written"
    assert student_flow.normalize_exam_prefill({"mode": "oral", "limit": "7"}) == {
        "mode": "oral", "subject": None, "limit": 7,
    }
    assert student_flow.normalize_exam_prefill({"mode": "nope"})["mode"] == "written"
    assert student_flow.normalize_exam_prefill({"limit": 0})["limit"] is None


def test_exam_hub_history_mixes_written_and_oral(isolated_db):
    from ragapp import oral_exam
    manifest.log_exam_attempt(50, 5)
    session = oral_exam.create_session("BWL", [{"question": "X?"}])
    oral_exam.finish_session(session["session_id"], total_pct=80)
    rows = student_flow.exam_hub_history()
    kinds = {r["kind"] for r in rows}
    assert kinds == {"written", "oral"}
    oral_row = next(r for r in rows if r["kind"] == "oral")
    assert oral_row["total_pct"] == 80
    assert oral_row["subject"] == "BWL"


def test_exam_hub_history_skips_aborted_oral(isolated_db):
    from ragapp import oral_exam
    session = oral_exam.create_session("BWL", [{"question": "X?"}])
    oral_exam.abort_session(session["session_id"])
    assert student_flow.exam_hub_history() == []


def test_oral_weak_card_ids_skips_passed_and_missing():
    ids = student_flow.oral_weak_card_ids({
        "questions": [
            {"card_id": "a", "partial_points": 80},
            {"card_id": "b", "partial_points": 40},
            {"card_id": "c", "partial_points": None},
            {"question": "ohne id", "partial_points": 0},
            {"card_id": "b", "partial_points": 10},
        ]
    })
    assert ids == ["b"]


def test_plain_study_snippet_strips_math_and_markdown():
    snip = student_flow.plain_study_snippet("Ableitung von $x^2$ und **fertig**")
    assert "$" not in snip
    assert "**" not in snip
    assert "Ableitung von" in snip
    assert "fertig" in snip
    block = student_flow.plain_study_snippet(r"Start $$\int_0^1 x\,dx$$ Ende")
    assert "Start" in block and "Ende" in block
    assert "int" not in block
    assert student_flow.plain_study_snippet("") == ""
    long = student_flow.plain_study_snippet("a" * 80, limit=42)
    assert long.endswith("…")
    assert len(long) == 43


def test_pick_verstehen_topic_ueberspringt_livetest(isolated_db):
    student_flow.card_from_text(
        "Was ist der Testing-Effekt?",
        "Wiederholen verbessert das Behalten stärker als nur nochmal lesen.",
        subject="Livetest", topic="Testing-Effekt")
    assert student_flow.pick_verstehen_topic() is None


def test_pick_verstehen_topic_nimmt_echtes_fach(isolated_db):
    student_flow.card_from_text(
        "Was ist der Testing-Effekt?",
        "Wiederholen verbessert das Behalten stärker als nur nochmal lesen.",
        subject="Livetest", topic="Testing-Effekt")
    student_flow.card_from_text(
        "Was ist der Deckungsbeitrag?",
        "Erlös minus variable Kosten in der Kosten- und Leistungsrechnung.",
        subject="BWL", topic="Deckungsbeitrag")
    got = student_flow.pick_verstehen_topic()
    assert got is not None
    assert got["subject"] == "BWL"
    assert got["topic"] == "Deckungsbeitrag"
    assert got["minutes"] == 20
    assert "Livetest" not in (got["subject"] or "")


def test_pick_verstehen_topic_nimmt_kartenfrage_statt_seite(isolated_db):
    student_flow.card_from_text(
        "Was ist ein Incident-Report?",
        "Ein Bericht nach einem Sicherheitsvorfall mit Zeitlinie und Maßnahmen.",
        subject="Cybersecurity", topic="Seite 7")
    manifest.upsert_document(
        doc_id="d-cs", content_hash="h", source_path="cs.pdf", filename="cs.pdf",
        subject="Cybersecurity", filetype="pdf", num_chunks=1, num_questions=0,
        char_count=10, status="ok")
    got = student_flow.pick_verstehen_topic()
    assert got is not None
    assert got["subject"] == "Cybersecurity"
    assert got["topic"]
    assert "Seite" not in got["topic"]
    assert got["topic"].lower() not in {"(ohne thema)", "ohne thema"}


def test_verstehen_pairs_erklaeren_und_aufloesen():
    messages = [
        {"role": "user", "content": "Lass uns über Schutzziele sprechen."},
        {"role": "assistant", "content": "Was sind die drei Schutzziele?\nBleib bei diesem Punkt."},
        {"role": "user", "content": (
            "Vertraulichkeit, Integrität und Verfügbarkeit sind die klassischen "
            "Schutzziele der Informationssicherheit.")},
        {"role": "assistant", "content": "Welches Ziel schützt vor unbefugtem Lesen?"},
        {"role": "user", "content": "Löse es auf."},
        {"role": "assistant", "content": "Vertraulichkeit schützt vor unbefugtem Lesen."},
    ]
    pairs = student_flow.verstehen_pairs(messages, "Schutzziele")
    assert len(pairs) == 2
    assert "drei Schutzziele" in pairs[0][0]
    assert "Vertraulichkeit, Integrität" in pairs[0][1]
    assert "unbefugtem Lesen" in pairs[1][0]
    assert "Vertraulichkeit schützt" in pairs[1][1]


def test_finish_verstehen_session_schreibt_notiz_und_karten(isolated_db):
    messages = [
        {"role": "user", "content": "Lass uns über Schutzziele sprechen."},
        {"role": "assistant", "content": "Was sind die drei Schutzziele?"},
        {"role": "user", "content": (
            "Vertraulichkeit, Integrität und Verfügbarkeit sind die klassischen "
            "Schutzziele der Informationssicherheit.")},
        {"role": "assistant", "content": "Welches Ziel schützt vor unbefugtem Lesen?"},
        {"role": "user", "content": "Löse es auf."},
        {"role": "assistant", "content": "Vertraulichkeit schützt vor unbefugtem Lesen."},
    ]
    out = student_flow.finish_verstehen_session(
        messages, topic="Schutzziele", subject="IT-Sicherheit",
        started_at=1000.0, minutes=20)
    assert out["note_id"]
    note = manifest.get_note(out["note_id"])
    assert note["collection"] == "Verstehen"
    assert "Schutzziele" in note["title"]
    assert "Vertraulichkeit" in note["body"]
    assert out["card_ids"]
    cards = manifest.get_cards_by_ids(out["card_ids"])
    assert any(c.get("source") == "chat" for c in cards)
    sessions = manifest.list_study_sessions(subject="IT-Sicherheit")
    assert any(s.get("mode") == "verstehen" for s in sessions)


def test_finish_verstehen_leerer_dialog_legt_trotzdem_notiz_an(isolated_db):
    out = student_flow.finish_verstehen_session(
        [], topic="Schutzziele", subject="IT-Sicherheit")
    assert out["note_id"]
    assert out["card_ids"] == []
    note = manifest.get_note(out["note_id"])
    assert "Noch keine Dialogzeilen" in note["body"]
    assert note["collection"] == "Verstehen"


def _write_skript_md(tmp_path, name="skript.md"):
    path = tmp_path / name
    path.write_text(
        "# Schutzziele\n\n"
        "Vertraulichkeit schützt Daten vor unbefugtem Lesen in der Praxis.\n\n"
        "Integrität verhindert unbemerkte Änderungen an Informationen.\n",
        encoding="utf-8")
    return path


def test_passages_on_page_nimmt_markdown_absatz(tmp_path):
    from ragapp.ui import _docviewer
    path = _write_skript_md(tmp_path)
    rows = _docviewer.passages_on_page(path, heading="Schutzziele")
    assert len(rows) >= 2
    assert any("Vertraulichkeit" in r["text"] for r in rows)


def test_passages_on_page_nimmt_pdf_bloecke(tmp_path):
    import fitz
    from ragapp.ui import _docviewer
    path = tmp_path / "stoff.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Deckungsbeitrag ist Erloes minus variable Kosten in der Rechnung.")
    page.insert_text((72, 140), "Break-even ist die Menge, bei der der Gewinn genau null ist.")
    doc.save(path)
    doc.close()
    rows = _docviewer.passages_on_page(path, 1)
    joined = " ".join(r["text"] for r in rows)
    assert "Deckungsbeitrag" in joined
    assert "Break-even" in joined


def test_pick_skript_spot_ueberspringt_livetest(isolated_db, tmp_path):
    path = _write_skript_md(tmp_path, "live.md")
    manifest.upsert_document(
        doc_id="liv", content_hash="h", source_path=str(path),
        filename="live.md", subject="Livetest", filetype="md",
        num_chunks=1, num_questions=0, char_count=20, status="ok")
    student_flow.card_from_text(
        "Was ist Grounding?", "Antwort nur aus den Unterlagen.",
        subject="Livetest", topic="Grounding")
    assert student_flow.pick_skript_spot() is None


def test_pick_skript_spot_nimmt_echtes_dokument(isolated_db, tmp_path):
    path = _write_skript_md(tmp_path)
    manifest.upsert_document(
        doc_id="d-cs", content_hash="h", source_path=str(path),
        filename="skript.md", subject="Cybersecurity", filetype="md",
        num_chunks=1, num_questions=0, char_count=80, status="ok")
    student_flow.card_from_text(
        "Was sind Schutzziele?", "Vertraulichkeit, Integritaet, Verfuegbarkeit.",
        subject="Cybersecurity", topic="Schutzziele")
    got = student_flow.pick_skript_spot()
    assert got is not None
    assert got["subject"] == "Cybersecurity"
    assert got["doc_id"] == "d-cs"
    assert got["minutes"] == 20
    assert "Livetest" not in (got["subject"] or "")
    assert got["heading"]


def test_pick_skript_spot_nimmt_heutigen_planblock(isolated_db, tmp_path):
    path = _write_skript_md(tmp_path)
    manifest.upsert_document(
        doc_id="d-plan", content_hash="h", source_path=str(path),
        filename="skript.md", subject="BWL", filetype="md",
        num_chunks=1, num_questions=0, char_count=80, status="ok")
    student_flow.card_from_text("Q", "A ist lang genug fuer eine Karte.", subject="BWL")
    pid = manifest.create_study_plan(
        title="BWL", subject="BWL", doc_ids=["d-plan"], deadline=None, daily_minutes=45)
    manifest.update_study_plan(pid, status="active")
    sid = manifest.append_plan_section(
        pid, title="Deckungsbeitrag", est_minutes=20,
        source_refs=[{"doc_id": "d-plan", "filename": "skript.md"}])
    manifest.append_plan_block(
        pid, section_id=sid, planned_date=date.today().isoformat(), planned_min=20)
    got = student_flow.pick_skript_spot()
    assert got is not None
    assert got["subject"] == "BWL"
    assert got["doc_id"] == "d-plan"
    assert got["block_id"]
    assert "Deckungsbeitrag" in (got["heading"] or "")


def test_hydrate_skript_spot_nimmt_prefill_dokument(isolated_db, tmp_path):
    path = _write_skript_md(tmp_path)
    manifest.upsert_document(
        doc_id="d-hy", content_hash="h", source_path=str(path),
        filename="skript.md", subject="Cybersecurity", filetype="md",
        num_chunks=1, num_questions=0, char_count=80, status="ok")
    got = student_flow.hydrate_skript_spot({
        "doc_id": "d-hy", "subject": "Cybersecurity",
        "heading": "Schutzziele", "minutes": 20,
    })
    assert got is not None
    assert got["doc_id"] == "d-hy"
    assert got["heading"] == "Schutzziele"
    assert got["minutes"] == 20


def test_skript_cursor_merkt_letzte_seite(tmp_path, monkeypatch):
    monkeypatch.setattr(
        student_flow, "_skript_cursor_file", lambda: tmp_path / "cursors.json")
    student_flow.save_skript_cursor("doc-a", 7, "Rechte")
    got = student_flow.load_skript_cursor("doc-a")
    assert got == {"page": 7, "heading": "Rechte"}
    assert student_flow.load_skript_cursor("missing") is None
    student_flow.save_skript_cursor("", 3)
    assert student_flow.load_skript_cursor("") is None


def test_pick_skript_spot_nimmt_gespeicherte_seite(isolated_db, tmp_path, monkeypatch):
    monkeypatch.setattr(
        student_flow, "_skript_cursor_file", lambda: tmp_path / "cursors.json")
    path = _write_skript_md(tmp_path)
    manifest.upsert_document(
        doc_id="d-cur", content_hash="h", source_path=str(path),
        filename="skript.md", subject="Cybersecurity", filetype="md",
        num_chunks=1, num_questions=0, char_count=80, status="ok")
    student_flow.save_skript_cursor("d-cur", 4, "Navigation")
    got = student_flow.pick_skript_spot()
    assert got is not None
    assert got["doc_id"] == "d-cur"
    assert got["page"] == 4
    assert got["heading"] == "Navigation"


def test_hydrate_skript_nutzt_cursor_ohne_seite(isolated_db, tmp_path, monkeypatch):
    monkeypatch.setattr(
        student_flow, "_skript_cursor_file", lambda: tmp_path / "cursors.json")
    path = _write_skript_md(tmp_path)
    manifest.upsert_document(
        doc_id="d-hy2", content_hash="h", source_path=str(path),
        filename="skript.md", subject="BWL", filetype="md",
        num_chunks=1, num_questions=0, char_count=80, status="ok")
    student_flow.save_skript_cursor("d-hy2", 9, "Break-even")
    got = student_flow.hydrate_skript_spot({"doc_id": "d-hy2", "subject": "BWL"})
    assert got["page"] == 9
    assert got["heading"] == "Break-even"


def test_page_text_len_leere_pdf_seite(tmp_path):
    import fitz
    from ragapp.ui import _docviewer
    path = tmp_path / "scan.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(path)
    doc.close()
    assert _docviewer.page_text_len(path, 1) == 0


def test_finish_skript_session_schreibt_notiz_und_karte(isolated_db):
    marks = [{
        "text": "Vertraulichkeit schuetzt vor unbefugtem Lesen in Informationssystemen.",
        "heading": "Schutzziele", "page": 2,
    }]
    out = student_flow.finish_skript_session(
        marks, heading="Schutzziele", subject="IT-Sicherheit",
        filename="skript.pdf", started_at=1000.0)
    assert out["note_id"]
    note = manifest.get_note(out["note_id"])
    assert note["collection"] == "Skript"
    assert "Vertraulichkeit" in note["body"]
    assert out["card_ids"]
    cards = manifest.get_cards_by_ids(out["card_ids"])
    assert any(c.get("source") == "skript" for c in cards)


def test_finish_skript_leere_markierung_legt_trotzdem_notiz_an(isolated_db):
    out = student_flow.finish_skript_session(
        [], heading="Schutzziele", subject="IT-Sicherheit", filename="a.md")
    assert out["note_id"]
    assert out["card_ids"] == []
    note = manifest.get_note(out["note_id"])
    assert "Noch keine Markierungen" in note["body"]
    assert note["collection"] == "Skript"
