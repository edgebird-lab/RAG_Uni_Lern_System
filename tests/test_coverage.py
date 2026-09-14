"""Abdeckung Lernziele gegen Mini-Manifest – ohne LLM."""
from __future__ import annotations

import pytest

from ragapp import analytics, coverage, manifest, student_flow


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "manifest_test.db"
    monkeypatch.setattr(manifest, "MANIFEST_DB", db_path)
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)
    monkeypatch.setattr(analytics, "MANIFEST_DB", db_path)
    return db_path


def test_coverage_ohne_ziele_bleibt_leer(isolated_db):
    assert coverage.coverage_for_subject("BWL") == []


def test_coverage_fehlend_ohne_stoff(isolated_db):
    manifest.add_learning_goals(
        "BWL", ["Die Studierenden können den Deckungsbeitrag je Stück berechnen."])
    rows = coverage.coverage_for_subject("BWL")
    assert len(rows) == 1
    assert rows[0]["status"] == "fehlend"


def test_coverage_leiter_dokument_karte_uebung_sitzt(isolated_db, monkeypatch):
    monkeypatch.setattr(analytics, "_target_reps", lambda: 2)
    goal = "Die Studierenden können den Deckungsbeitrag je Stück berechnen."
    manifest.add_learning_goals("BWL", [goal])

    manifest.upsert_document(
        doc_id="d1", content_hash="h", source_path="BWL/deckungsbeitrag.pdf",
        filename="deckungsbeitrag.pdf", subject="BWL", filetype="pdf",
        num_chunks=1, num_questions=0, char_count=10, status="ok")
    assert coverage.coverage_for_subject("BWL")[0]["status"] == "Dokument"

    cid = student_flow.card_from_text(
        "Was ist der Deckungsbeitrag je Stück?", "Erlös minus variable Kosten.",
        source="note", subject="BWL", topic="Deckungsbeitrag")
    assert coverage.coverage_for_subject("BWL")[0]["status"] == "Karte"

    manifest.create_practice_problem(
        subject="BWL", topic="Deckungsbeitrag", kind="numeric",
        problem_text="Berechne den Deckungsbeitrag je Stück.",
        steps=[{"step_text": "Erlös minus variable Kosten"}])
    assert coverage.coverage_for_subject("BWL")[0]["status"] == "Übung"

    import sqlite3
    with sqlite3.connect(isolated_db) as conn:
        conn.execute("UPDATE review_items SET reps=2 WHERE card_id=?", (cid,))
        conn.commit()
    row = coverage.coverage_for_subject("BWL")[0]
    assert row["status"] == "sitzt"
    assert cid in row["card_ids"]


def test_coverage_start_action_fuer_luecken():
    assert coverage.coverage_start_action({"status": "fehlend"})["kind"] == "dokument"
    assert coverage.coverage_start_action({"status": "Dokument"})["kind"] == "lernset"
    assert coverage.coverage_start_action({"status": "Karte"})["kind"] == "uebung"
    assert coverage.coverage_start_action({"status": "sitzt"})["kind"] is None


def test_coverage_ignoriert_suspendierte_karte(isolated_db):
    manifest.add_learning_goals(
        "BWL", ["Die Studierenden können den Deckungsbeitrag berechnen."])
    cid = student_flow.card_from_text(
        "Wie berechnet man den Deckungsbeitrag?", "Erlös minus Kosten",
        subject="BWL", topic="Deckungsbeitrag")
    with manifest._connect() as conn:
        conn.execute(
            "UPDATE review_items SET suspended=1 WHERE card_id=?", (cid,))
    assert coverage.coverage_for_subject("BWL")[0]["status"] == "fehlend"


def test_klausurbereitschaft_kombiniert_behalten_und_lernzielabdeckung(
        isolated_db, monkeypatch):
    manifest.add_learning_goals(
        "BWL", ["Die Studierenden können den Deckungsbeitrag berechnen."])
    manifest.upsert_document(
        doc_id="d1", content_hash="h", source_path="BWL/deckungsbeitrag.pdf",
        filename="deckungsbeitrag.pdf", subject="BWL", filetype="pdf",
        num_chunks=1, num_questions=0, char_count=10, status="ok")
    student_flow.card_from_text(
        "Was ist Marktforschung?", "Datenerhebung", subject="BWL",
        topic="Marktforschung")
    monkeypatch.setattr(analytics, "card_retrievability", lambda card, at=None: 1.0)
    ready = analytics.subject_readiness("BWL")
    assert ready["retention_pct"] == 100
    assert ready["coverage_pct"] == 25
    assert ready["readiness_pct"] == 74


def test_bestandene_getippte_uebung_schliesst_lernziel(isolated_db):
    goal = "Die Studierenden können den Deckungsbeitrag berechnen."
    manifest.add_learning_goals("BWL", [goal])
    pid = manifest.create_practice_problem(
        subject="BWL", topic="Deckungsbeitrag", kind="numeric",
        problem_text="Berechne den Deckungsbeitrag.",
        steps=[{"step_text": "Erlös minus variable Kosten"}])
    manifest.log_practice_attempt(
        pid, self_rating=2, typed_answer="100-60=40", score=85)
    assert coverage.coverage_for_subject("BWL")[0]["status"] == "sitzt"
