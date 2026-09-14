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
