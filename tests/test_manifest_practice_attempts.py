"""Tests für manifest.practice_attempt_summary() - Grundlage der "was ist
dran"-Sortierung/Badges auf der Übungsaufgaben-Seite (nie geübt oder zuletzt
schlecht bewertet zuerst). Isolierte Temp-DB, niemals die echte
data/manifest.db (gleiches Muster wie test_manifest_audio_overviews.py)."""
from __future__ import annotations

import time

import pytest

from ragapp import manifest


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "manifest_test.db"
    monkeypatch.setattr(manifest, "MANIFEST_DB", db_path)
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)
    return db_path


def _make_problem() -> str:
    return manifest.create_practice_problem(
        subject="mathe", problem_text="1+1?", steps=[{"step_text": "..."}],
        final_answer="2")


def test_summary_leer_ohne_versuche(isolated_db):
    pid = _make_problem()
    assert manifest.practice_attempt_summary([pid]) == {}


def test_summary_zeigt_letzte_bewertung_und_anzahl(isolated_db, monkeypatch):
    pid = _make_problem()
    times = iter([100.0, 200.0, 300.0])
    monkeypatch.setattr(time, "time", lambda: next(times))
    manifest.log_practice_attempt(pid, self_rating=0)
    manifest.log_practice_attempt(pid, self_rating=1)
    manifest.log_practice_attempt(pid, self_rating=2)   # neuester Versuch
    summary = manifest.practice_attempt_summary([pid])
    assert summary[pid]["last_rating"] == 2
    assert summary[pid]["last_attempted_at"] == 300.0
    assert summary[pid]["attempts"] == 3


def test_summary_haelt_mehrere_aufgaben_auseinander(isolated_db):
    pid1, pid2 = _make_problem(), _make_problem()
    manifest.log_practice_attempt(pid1, self_rating=0)
    manifest.log_practice_attempt(pid2, self_rating=2)
    summary = manifest.practice_attempt_summary([pid1, pid2])
    assert summary[pid1]["last_rating"] == 0
    assert summary[pid2]["last_rating"] == 2


def test_summary_mit_leerer_id_liste_ist_leer_nicht_ungefiltert(isolated_db):
    # Regression: eine explizit LEERE Auswahl (z. B. eine leer gefilterte
    # Uebungsaufgaben-Liste) darf NICHT versehentlich als "kein Filter"
    # behandelt werden und dann doch alle Aufgaben zurueckgeben.
    pid = _make_problem()
    manifest.log_practice_attempt(pid, self_rating=0)
    assert manifest.practice_attempt_summary([]) == {}


def test_summary_ohne_id_filter_liefert_alle(isolated_db):
    pid1, pid2 = _make_problem(), _make_problem()
    manifest.log_practice_attempt(pid1, self_rating=0)
    assert set(manifest.practice_attempt_summary().keys()) == {pid1}
    manifest.log_practice_attempt(pid2, self_rating=1)
    assert set(manifest.practice_attempt_summary().keys()) == {pid1, pid2}


def test_attempt_speichert_rechenweg_teilpunkte_und_feedback(isolated_db):
    pid = _make_problem()
    manifest.log_practice_attempt(
        pid, self_rating=1, typed_answer="100 - 60 = 40", score=65,
        feedback="Ansatz stimmt.", fehlt="Einheit")
    attempt = manifest.list_practice_attempts(pid)[0]
    assert attempt["typed_answer"] == "100 - 60 = 40"
    assert attempt["score"] == 65
    assert attempt["feedback"] == "Ansatz stimmt."
    assert attempt["fehlt"] == "Einheit"


def test_attempt_serialisiert_fehlt_liste(isolated_db):
    pid = _make_problem()
    manifest.log_practice_attempt(
        pid, self_rating=1, score=40, fehlt=["Einheit", "Grenzen"])
    attempt = manifest.list_practice_attempts(pid)[0]
    assert attempt["fehlt"] == "Einheit · Grenzen"


def test_best_score_bleibt_trotz_spaeterer_manueller_bewertung(isolated_db):
    pid = _make_problem()
    manifest.log_practice_attempt(pid, self_rating=2, score=85)
    manifest.log_practice_attempt(pid, self_rating=1)
    summary = manifest.practice_attempt_summary([pid])[pid]
    assert summary["last_score"] is None
    assert summary["best_score"] == 85
