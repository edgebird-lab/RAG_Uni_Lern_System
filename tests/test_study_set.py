"""create_study_set: ein Aufruf verdrahtet Enrich, Harvest und Antworten."""
from __future__ import annotations

import pytest

from ragapp import manifest, study


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "manifest_test.db"
    monkeypatch.setattr(manifest, "MANIFEST_DB", db_path)
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)
    return db_path


def _doc(isolated_db, doc_id="d1"):
    manifest.upsert_document(
        doc_id=doc_id, content_hash="h", source_path=f"/{doc_id}.pdf",
        filename=f"{doc_id}.pdf", subject="BWL", filetype="pdf",
        num_chunks=3, num_questions=0, char_count=1000, status="ready")
    return doc_id


def test_create_study_set_leere_docs_bricht_ehrlich_ab():
    out = study.create_study_set([])
    assert out["status"] == "empty"
    assert out["cards_new"] == 0
    assert "Dokumente" in (out["error_msg"] or "")


def test_create_study_set_unbekannte_docs(isolated_db):
    out = study.create_study_set(["gibt-es-nicht"])
    assert out["status"] == "empty"
    assert out["questions"] == 0


def test_create_study_set_kein_modell(isolated_db, monkeypatch):
    _doc(isolated_db)

    def _enrich(**kwargs):
        return {"status": "llm_error", "questions": 0,
                "error_msg": "Modell 'x' laeuft nicht: not found"}

    monkeypatch.setattr("ragapp.ingestion.enrich.enrich_questions", _enrich)
    out = study.create_study_set(["d1"])
    assert out["status"] == "no_model"
    assert out["cards_new"] == 0
    assert out["error_msg"]


def test_create_study_set_vram(isolated_db, monkeypatch):
    _doc(isolated_db)

    def _enrich(**kwargs):
        return {"status": "llm_error", "questions": 0,
                "error_msg": "Zu wenig freier Grafikspeicher (VRAM)."}

    monkeypatch.setattr("ragapp.ingestion.enrich.enrich_questions", _enrich)
    out = study.create_study_set(["d1"])
    assert out["status"] == "vram"


def test_create_study_set_erzeugt_fragen_karten_antworten(isolated_db, monkeypatch):
    _doc(isolated_db)
    calls = []

    def _enrich(**kwargs):
        calls.append("enrich")
        assert kwargs["doc_ids"] == ["d1"]
        return {"status": "ok", "questions": 4, "error_msg": None}

    def _harvest(**kwargs):
        calls.append("harvest")
        assert kwargs.get("doc_ids") == ["d1"]
        return {"gefunden": 4, "neu": 3}

    def _answers(**kwargs):
        calls.append("answers")
        assert kwargs.get("card_ids") is not None
        return {"status": "ok", "filled": 3, "error_msg": None}

    monkeypatch.setattr("ragapp.ingestion.enrich.enrich_questions", _enrich)
    monkeypatch.setattr(study, "harvest_cards", _harvest)
    monkeypatch.setattr(study, "generate_answers", _answers)
    notes = []
    out = study.create_study_set(["d1"], progress=notes.append)
    assert out["status"] == "ok"
    assert out["questions"] == 4
    assert out["cards_new"] == 3
    assert out["answers"] == 3
    assert calls == ["enrich", "harvest", "answers"]
    assert notes  # Fortschritt wurde gemeldet


def test_create_study_set_expertenparameter_optional(isolated_db, monkeypatch):
    _doc(isolated_db)

    def _enrich(**kwargs):
        assert kwargs["n_per_chunk"] == 2
        return {"status": "ok", "questions": 1}

    def _harvest(**kwargs):
        assert kwargs["max_per_chunk"] == 5
        return {"gefunden": 1, "neu": 1}

    monkeypatch.setattr("ragapp.ingestion.enrich.enrich_questions", _enrich)
    monkeypatch.setattr(study, "harvest_cards", _harvest)
    monkeypatch.setattr(study, "generate_answers",
                        lambda **k: {"status": "nothing_to_do", "filled": 0})
    out = study.create_study_set(["d1"], n_per_chunk=2, max_per_chunk=5)
    assert out["status"] == "ok"
    assert out["cards_new"] == 1
    assert "preview" in out


def test_study_set_preview_mit_fixture_karten(isolated_db):
    manifest.upsert_review_items([
        {"card_id": "c1", "source": "question", "chroma_id": "c1",
         "subject": "BWL", "topic": "Kosten", "front": "Was sind Fixkosten?",
         "back": "unabhängig von der Menge", "answer": "", "doc_id": "d1"},
        {"card_id": "c2", "source": "question", "chroma_id": "c2",
         "subject": "BWL", "topic": "Kosten", "front": "Was sind variable Kosten?",
         "back": "steigen mit der Menge", "answer": "steigen mit der Menge",
         "doc_id": "d1"},
        {"card_id": "c3", "source": "exam_qa", "chroma_id": "c3",
         "subject": "BWL", "topic": "Preis", "front": "Was ist die Preisuntergrenze?",
         "back": "variable Kosten", "answer": "variable Kosten", "doc_id": "d1"},
        {"card_id": "c4", "source": "question", "chroma_id": "c4",
         "subject": "BWL", "topic": "Anderes", "front": "Andere Datei",
         "back": "x", "answer": "x", "doc_id": "d2"},
    ])
    prev = study.study_set_preview(doc_ids=["d1"])
    assert prev["cards"] == 3
    assert prev["unanswered"] == 1
    assert set(prev["topics"]) == {"Kosten", "Preis"}
    assert len(prev["examples"]) == 3
    assert prev["examples"][0]["front"]
    other = study.study_set_preview(doc_ids=["d2"])
    assert other["cards"] == 1
    assert other["topics"] == ["Anderes"]


def test_study_set_preview_filtert_heading_echo(isolated_db):
    manifest.upsert_review_items([
        {"card_id": "echo", "source": "question", "chroma_id": "echo",
         "subject": "BWL", "topic": "DB",
         "front": "Was ist Deckungsbeitrag?",
         "back": "# Deckungsbeitrag\n\nErlös minus variable Kosten.",
         "answer": "", "doc_id": "d1"},
        {"card_id": "ok", "source": "question", "chroma_id": "ok",
         "subject": "BWL", "topic": "DB",
         "front": "Wie unterscheidet sich der Deckungsbeitrag vom Gewinn?",
         "back": "# Deckungsbeitrag\n\nErlös minus variable Kosten.",
         "answer": "DB ignoriert Fixkosten.", "doc_id": "d1"},
        {"card_id": "qa", "source": "exam_qa", "chroma_id": "qa",
         "subject": "BWL", "topic": "DB",
         "front": "Was ist Deckungsbeitrag?",
         "back": "Erlös minus variable Kosten.",
         "answer": "Erlös minus variable Kosten.", "doc_id": "d1"},
    ])
    prev = study.study_set_preview(doc_ids=["d1"])
    assert prev["cards"] == 2
    assert set(prev["card_ids"]) == {"ok", "qa"}
    assert "echo" not in prev["card_ids"]


def test_enrich_bindet_question_gen():
    """Live-Test: Lernset-Erstellen stürzte mit NameError auf generate_questions ab."""
    from ragapp.ingestion import enrich
    assert callable(enrich.generate_questions)
    assert callable(enrich.generate_answer)
    assert issubclass(enrich.QuestionGenError, Exception)


def test_generate_answers_leere_card_ids_ist_nichts(isolated_db):
    manifest.upsert_review_items([{
        "card_id": "q-open", "source": "question", "chroma_id": None,
        "subject": "BWL", "topic": None,
        "front": "Was ist X?", "back": "Chunk", "answer": "", "doc_id": "d1",
    }])
    out = study.generate_answers(card_ids=[])
    assert out["status"] == "nothing_to_do"
    assert out["filled"] == 0


def test_needs_card_harvest_nur_ueber_flag(isolated_db, monkeypatch):
    from ragapp.config import settings
    monkeypatch.setattr(settings, "NEEDS_CARD_HARVEST", False, raising=False)
    manifest.upsert_document(
        doc_id="d1", content_hash="h", source_path="/d1.pdf",
        filename="d1.pdf", subject="BWL", filetype="pdf",
        num_chunks=3, num_questions=9, char_count=1000, status="ok")
    assert study.needs_card_harvest() is False
    monkeypatch.setattr(settings, "NEEDS_CARD_HARVEST", True, raising=False)
    assert study.needs_card_harvest() is True


def test_upsert_behaelt_ocr_partial_pages(isolated_db):
    manifest.upsert_document(
        doc_id="d1", content_hash="h", source_path="/d1.pdf",
        filename="d1.pdf", subject="BWL", filetype="pdf",
        num_chunks=3, num_questions=0, char_count=1000, status="ok",
        ocr_partial_pages=4)
    d = dict(manifest.get_document("d1"))
    assert d["ocr_partial_pages"] == 4
    manifest.upsert_document(
        doc_id="d1", content_hash=d["content_hash"], source_path=d["source_path"],
        filename=d["filename"], subject=d["subject"], filetype=d["filetype"],
        num_chunks=d["num_chunks"], num_questions=(d["num_questions"] or 0) + 2,
        char_count=d["char_count"], status=d["status"],
        ocr_partial_pages=int(d.get("ocr_partial_pages") or 0),
    )
    assert dict(manifest.get_document("d1"))["ocr_partial_pages"] == 4
    assert dict(manifest.get_document("d1"))["num_questions"] == 2

