"""Tests für die Probeklausur-Ergebnis-Historie (manifest.log_exam_attempt()/
list_exam_attempts()/best_exam_pct()) - vorher lebte das Ergebnis nur in
st.session_state und war nach Verlassen der Seite komplett weg. Isolierte
Temp-DB, niemals die echte data/manifest.db."""
from __future__ import annotations

import time

import pytest

from ragapp import manifest, oral_exam


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "manifest_test.db"
    monkeypatch.setattr(manifest, "MANIFEST_DB", db_path)
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)
    return db_path


def test_log_and_list_exam_attempt(isolated_db):
    manifest.log_exam_attempt(82, 10)
    attempts = manifest.list_exam_attempts()
    assert len(attempts) == 1
    assert attempts[0]["total_pct"] == 82
    assert attempts[0]["num_items"] == 10
    assert attempts[0]["taken_at"] is not None


def test_list_exam_attempts_newest_first(isolated_db, monkeypatch):
    times = iter([100.0, 200.0, 300.0])
    monkeypatch.setattr(time, "time", lambda: next(times))
    manifest.log_exam_attempt(50, 5)
    manifest.log_exam_attempt(60, 5)
    manifest.log_exam_attempt(70, 5)
    pcts = [a["total_pct"] for a in manifest.list_exam_attempts()]
    assert pcts == [70, 60, 50]


def test_list_exam_attempts_respektiert_limit(isolated_db):
    for i in range(5):
        manifest.log_exam_attempt(i * 10, 5)
    assert len(manifest.list_exam_attempts(limit=2)) == 2


def test_best_exam_pct_ohne_versuche_ist_none(isolated_db):
    assert manifest.best_exam_pct() is None


def test_best_exam_pct_liefert_hoechsten_wert(isolated_db):
    manifest.log_exam_attempt(60, 5)
    manifest.log_exam_attempt(90, 5)
    manifest.log_exam_attempt(75, 5)
    assert manifest.best_exam_pct() == 90


def test_oral_exam_session_speichert_verlauf_als_json(isolated_db):
    session = oral_exam.create_session(
        "BWL", [{"question": "Was ist der Deckungsbeitrag?",
                 "reference": "Erlös minus variable Kosten."}])
    assert session["status"] == "active"
    assert session["questions"][0]["transcript"] is None
    saved = oral_exam.record_answer(
        session["session_id"], 0, "Der Erlös abzüglich variabler Kosten.",
        followup="Warum ist er entscheidungsrelevant?", partial_points=80)
    item = saved["questions"][0]
    assert item["partial_points"] == 80
    assert item["followups"][0]["question"].startswith("Warum")
    done = oral_exam.finish_session(session["session_id"])
    assert done["status"] == "done"
    assert done["total_pct"] == 80


def test_oral_exam_beruehrt_schriftliche_attempts_nicht(isolated_db):
    manifest.log_exam_attempt(75, 4)
    before = manifest.list_exam_attempts()
    oral_exam.create_session("BWL", [{"question": "Erkläre X."}])
    assert manifest.list_exam_attempts() == before
    assert len(oral_exam.list_sessions("BWL")) == 1


def test_oral_exam_session_from_cards_zeigt_eine_frage_nach_der_anderen(
        isolated_db):
    from ragapp.student_flow import card_from_text
    card_from_text("Erkläre X.", "X ist Y.", subject="BWL", source="note")
    session = oral_exam.session_from_cards("BWL", limit=1)
    assert session["status"] == "active"
    assert len(session["questions"]) == 1
    assert session["questions"][0]["question"] == "Erkläre X."


def test_oral_transcribe_audio_klarer_abbruch_ohne_stt(monkeypatch):
    monkeypatch.setattr(
        "ragapp.speech_to_text.is_available", lambda: False)
    out = oral_exam.transcribe_answer(b"audio")
    assert out["status"] == "no_stt"
    assert out["transcript"] == ""
    assert out["message"]


def test_oral_followup_klarer_abbruch_ohne_modell(monkeypatch):
    monkeypatch.setattr(
        "ragapp.llm.list_installed_models", lambda: [])
    out = oral_exam.generate_followup("Frage?", "Antwort", model="nicht-da")
    assert out["status"] == "no_model"
    assert out["followup"] is None
    assert "nicht installiert" in out["message"]
