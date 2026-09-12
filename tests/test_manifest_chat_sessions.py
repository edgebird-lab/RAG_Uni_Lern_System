"""Tests für die chat_sessions-CRUD in ragapp.manifest (dauerhaft gespeicherter
Chat-Verlauf über App-Neustarts hinweg - vorher nur st.session_state.messages).
Isolierte Temp-DB, niemals die echte data/manifest.db (gleiches Muster wie
test_manifest_audio_overviews.py)."""
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


def test_create_and_get_chat_session(isolated_db):
    msgs = [{"role": "user", "content": "Was ist FSRS?"},
            {"role": "assistant", "content": "Ein Wiederholungsalgorithmus."}]
    sid = manifest.create_chat_session(title="FSRS-Frage", subject="mathe", messages=msgs)
    row = manifest.get_chat_session(sid)
    assert row is not None
    assert row["title"] == "FSRS-Frage"
    assert row["subject"] == "mathe"
    assert row["messages"] == msgs
    assert row["created_at"] is not None


def test_create_chat_session_ohne_messages_startet_leer(isolated_db):
    sid = manifest.create_chat_session(title="Neu")
    assert manifest.get_chat_session(sid)["messages"] == []


def test_get_unknown_session_returns_none(isolated_db):
    assert manifest.get_chat_session("does-not-exist") is None


def test_list_chat_sessions_orders_newest_updated_first(isolated_db, monkeypatch):
    times = iter([100.0, 200.0, 300.0])
    monkeypatch.setattr(time, "time", lambda: next(times))
    id1 = manifest.create_chat_session(title="Erste")
    id2 = manifest.create_chat_session(title="Zweite")
    id3 = manifest.create_chat_session(title="Dritte")
    assert [r["session_id"] for r in manifest.list_chat_sessions()] == [id3, id2, id1]


def test_update_chat_session_messages_bumps_updated_at_order(isolated_db, monkeypatch):
    times = iter([100.0, 200.0, 300.0])
    monkeypatch.setattr(time, "time", lambda: next(times))
    id1 = manifest.create_chat_session(title="Erste")
    id2 = manifest.create_chat_session(title="Zweite")
    # Erste Sitzung bekommt eine neue Nachricht -> muss jetzt zuoberst stehen.
    manifest.update_chat_session(id1, messages=[{"role": "user", "content": "Hallo"}])
    assert [r["session_id"] for r in manifest.list_chat_sessions()] == [id1, id2]
    assert manifest.get_chat_session(id1)["messages"] == [{"role": "user", "content": "Hallo"}]


def test_update_chat_session_title_only_leaves_messages_unangetastet(isolated_db):
    sid = manifest.create_chat_session(title="Alt", messages=[{"role": "user", "content": "x"}])
    manifest.update_chat_session(sid, title="Neuer Titel")
    row = manifest.get_chat_session(sid)
    assert row["title"] == "Neuer Titel"
    assert row["messages"] == [{"role": "user", "content": "x"}]


def test_update_chat_session_ohne_felder_tut_nichts(isolated_db):
    sid = manifest.create_chat_session(title="X", messages=[{"role": "user", "content": "a"}])
    before = manifest.get_chat_session(sid)
    manifest.update_chat_session(sid)
    assert manifest.get_chat_session(sid) == before


def test_delete_chat_session_removes_row(isolated_db):
    sid = manifest.create_chat_session(title="Zu löschen")
    manifest.delete_chat_session(sid)
    assert manifest.get_chat_session(sid) is None
    assert manifest.list_chat_sessions() == []
