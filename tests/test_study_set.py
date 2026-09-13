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
