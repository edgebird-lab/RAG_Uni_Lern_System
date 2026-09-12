"""Tests für ragapp.search (einheitliche Suche über Notizen, Chat-Verläufe
und Zusammenfassungen). Isolierte Temp-DB für Notizen/Chats (niemals die
echte data/manifest.db), isoliertes Temp-Verzeichnis für die
Zusammenfassungs-Dateien (niemals das echte docs/)."""
from __future__ import annotations

import pytest

from ragapp import manifest, search


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "manifest_test.db"
    monkeypatch.setattr(manifest, "MANIFEST_DB", db_path)
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)
    return db_path


@pytest.fixture()
def isolated_docs(tmp_path, monkeypatch):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    monkeypatch.setattr(search, "PROJECT_ROOT", tmp_path)
    return docs_dir


# --------------------------------------------------------------------------- #
# search_notes()
# --------------------------------------------------------------------------- #
def test_search_notes_findet_treffer_in_titel_oder_text(isolated_db):
    manifest.create_note(subject="mathe", body="Etwas über FSRS-Wiederholungen.",
                         title="Karteikarten-Algorithmus")
    manifest.create_note(subject="physik", body="Nichts Relevantes hier.")
    results = search.search_notes("FSRS")
    assert len(results) == 1
    assert results[0]["source"] == "notiz"
    assert "FSRS" in results[0]["snippet"]


def test_search_notes_keine_treffer_ist_leere_liste(isolated_db):
    manifest.create_note(subject="mathe", body="Ganz anderer Inhalt.")
    assert search.search_notes("nichtvorhanden") == []


# --------------------------------------------------------------------------- #
# search_chat_sessions()
# --------------------------------------------------------------------------- #
def test_search_chat_sessions_findet_treffer_im_nachrichtentext(isolated_db):
    manifest.create_chat_session(
        title="Frage zu Docker", subject=None,
        messages=[{"role": "user", "content": "Wie funktioniert ein Docker-Container?"}])
    results = search.search_chat_sessions("docker")
    assert len(results) == 1
    assert results[0]["source"] == "chat"


def test_search_chat_sessions_findet_treffer_im_titel(isolated_db):
    manifest.create_chat_session(title="Alles über Kubernetes", messages=[])
    results = search.search_chat_sessions("kubernetes")
    assert len(results) == 1


def test_search_chat_sessions_respektiert_limit(isolated_db):
    for i in range(10):
        manifest.create_chat_session(title=f"Docker Frage {i}", messages=[])
    results = search.search_chat_sessions("docker", limit=3)
    assert len(results) == 3


# --------------------------------------------------------------------------- #
# search_zusammenfassungen()
# --------------------------------------------------------------------------- #
def test_search_zusammenfassungen_findet_treffer_im_dateiinhalt(isolated_docs):
    (isolated_docs / "Zusammenfassung_Analysis.md").write_text(
        "# Analysis\n\nSchnittmengen von Intervallen ...", encoding="utf-8")
    (isolated_docs / "Zusammenfassung_Marketing.md").write_text(
        "# Marketing\n\nZielgruppenanalyse ...", encoding="utf-8")
    results = search.search_zusammenfassungen("Schnittmengen")
    assert len(results) == 1
    assert results[0]["title"] == "Analysis"


def test_search_zusammenfassungen_findet_treffer_im_dateinamen(isolated_docs):
    (isolated_docs / "Zusammenfassung_Cybersecurity.md").write_text(
        "Beliebiger Inhalt ohne den Suchbegriff.", encoding="utf-8")
    results = search.search_zusammenfassungen("cybersecurity")
    assert len(results) == 1


def test_search_zusammenfassungen_ohne_docs_ordner_ist_leer(tmp_path, monkeypatch):
    monkeypatch.setattr(search, "PROJECT_ROOT", tmp_path)  # kein docs/-Unterordner angelegt
    assert search.search_zusammenfassungen("irgendwas") == []


# --------------------------------------------------------------------------- #
# search_everything()
# --------------------------------------------------------------------------- #
def test_search_everything_kombiniert_alle_drei_quellen(isolated_db, isolated_docs):
    manifest.create_note(subject="mathe", body="FSRS ist toll.")
    manifest.create_chat_session(title="FSRS Frage", messages=[
        {"role": "user", "content": "Was ist FSRS?"}])
    (isolated_docs / "Zusammenfassung_Lernen.md").write_text(
        "FSRS-Algorithmus erklärt.", encoding="utf-8")
    results = search.search_everything("FSRS")
    assert len(results["notiz"]) == 1
    assert len(results["chat"]) == 1
    assert len(results["zusammenfassung"]) == 1


def test_search_everything_zu_kurze_anfrage_liefert_nichts(isolated_db, isolated_docs):
    manifest.create_note(subject="mathe", body="F")
    assert search.search_everything("F") == {"notiz": [], "chat": [], "zusammenfassung": []}


def test_search_everything_leere_anfrage_liefert_nichts(isolated_db, isolated_docs):
    assert search.search_everything("") == {"notiz": [], "chat": [], "zusammenfassung": []}
