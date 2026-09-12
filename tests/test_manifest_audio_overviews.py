"""Tests fuer die audio_overviews-CRUD in ragapp.manifest (isolierte Temp-DB,
niemals die echte data/manifest.db - gleiches Muster wie fuer Mindmaps noetig,
hier aber erstmals direkt fuer die DB-Schicht statt nur fuer LLM-Logik)."""
from __future__ import annotations

import pathlib

import pytest

from ragapp import manifest


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "manifest_test.db"
    monkeypatch.setattr(manifest, "MANIFEST_DB", db_path)
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)
    return db_path


def test_create_and_get_audio_overview(isolated_db):
    oid = manifest.create_audio_overview(
        title="Testübersicht", subject="mathe", doc_ids=["d1", "d2"],
        script_text="Hallo, das ist ein Test.", audio_path="x.wav",
        model="xtts_v2",
    )
    row = manifest.get_audio_overview(oid)
    assert row is not None
    assert row["title"] == "Testübersicht"
    assert row["subject"] == "mathe"
    assert row["doc_ids"] == ["d1", "d2"]
    assert row["script_text"] == "Hallo, das ist ein Test."
    assert row["audio_path"] == "x.wav"
    assert row["model"] == "xtts_v2"
    assert row["created_at"] is not None


def test_get_unknown_id_returns_none(isolated_db):
    assert manifest.get_audio_overview("does-not-exist") is None


def test_create_with_explicit_overview_id_for_matching_filename(isolated_db):
    # audio_overview.py braucht die ID VOR dem Insert, um die WAV-Datei direkt
    # unter dem endgueltigen Namen abzulegen (keine Umbenennung hinterher noetig).
    oid = manifest.create_audio_overview(
        title="Fest vergebene ID", subject=None, doc_ids=[],
        script_text="x", audio_path="vorgegeben123.wav", overview_id="vorgegeben123",
    )
    assert oid == "vorgegeben123"
    row = manifest.get_audio_overview("vorgegeben123")
    assert row is not None
    assert row["audio_path"] == "vorgegeben123.wav"


def test_list_audio_overviews_orders_newest_first(isolated_db, monkeypatch):
    import time
    times = iter([100.0, 200.0, 300.0])
    monkeypatch.setattr(time, "time", lambda: next(times))
    id1 = manifest.create_audio_overview(title="Erste", subject="s1", doc_ids=[],
                                          script_text="a", audio_path="1.wav")
    id2 = manifest.create_audio_overview(title="Zweite", subject="s1", doc_ids=[],
                                          script_text="b", audio_path="2.wav")
    id3 = manifest.create_audio_overview(title="Dritte", subject="s2", doc_ids=[],
                                          script_text="c", audio_path="3.wav")
    all_rows = manifest.list_audio_overviews()
    assert [r["overview_id"] for r in all_rows] == [id3, id2, id1]

    filtered = manifest.list_audio_overviews(subject="s1")
    assert [r["overview_id"] for r in filtered] == [id2, id1]


def test_update_audio_overview_changes_only_given_fields(isolated_db):
    oid = manifest.create_audio_overview(
        title="Original", subject="mathe", doc_ids=["d1"],
        script_text="alter Text", audio_path="a.wav", model="alt-modell")
    manifest.update_audio_overview(oid, script_text="neuer Text", model="neues-modell")
    row = manifest.get_audio_overview(oid)
    assert row["script_text"] == "neuer Text"
    assert row["model"] == "neues-modell"
    # Unveraendert gebliebene Felder:
    assert row["title"] == "Original"
    assert row["subject"] == "mathe"
    assert row["audio_path"] == "a.wav"


def test_update_audio_overview_kann_titel_umbenennen(isolated_db):
    # Grundlage der "✏️ Umbenennen"-Aktion auf der Audio-Overview-Seite.
    oid = manifest.create_audio_overview(
        title="Alter Titel", subject="mathe", doc_ids=[], script_text="x", audio_path="a.wav")
    manifest.update_audio_overview(oid, title="Neuer Titel")
    row = manifest.get_audio_overview(oid)
    assert row["title"] == "Neuer Titel"
    # Andere Felder bleiben dabei unangetastet.
    assert row["subject"] == "mathe"
    assert row["audio_path"] == "a.wav"


def test_update_audio_overview_reused_id_would_have_crashed_via_create(isolated_db):
    # Regression: die "Neu generieren"-Seite rief zuerst faelschlich
    # create_audio_overview() mit einer bereits existierenden ID auf - das ist
    # ein reines INSERT und waere an der PRIMARY-KEY-Kollision gescheitert.
    oid = manifest.create_audio_overview(
        title="X", subject=None, doc_ids=[], script_text="a", audio_path="a.wav")
    with pytest.raises(Exception):
        manifest.create_audio_overview(
            title="X", subject=None, doc_ids=[], script_text="b", audio_path="a.wav",
            overview_id=oid)
    # update_audio_overview ist der richtige Weg und darf NICHT crashen:
    manifest.update_audio_overview(oid, script_text="b")
    assert manifest.get_audio_overview(oid)["script_text"] == "b"


def test_delete_audio_overview_removes_row_and_file(isolated_db, monkeypatch, tmp_path):
    audio_dir = tmp_path / "audio_overviews"
    audio_dir.mkdir()
    monkeypatch.setattr("ragapp.config.AUDIO_DIR", audio_dir)
    wav_file = audio_dir / "clip.wav"
    wav_file.write_bytes(b"RIFF....WAVEfmt ")

    oid = manifest.create_audio_overview(title="Zu löschen", subject=None, doc_ids=[],
                                          script_text="x", audio_path="clip.wav")
    assert manifest.get_audio_overview(oid) is not None
    assert wav_file.is_file()

    manifest.delete_audio_overview(oid)

    assert manifest.get_audio_overview(oid) is None
    assert not wav_file.is_file()


def test_delete_audio_overview_missing_file_does_not_raise(isolated_db, monkeypatch, tmp_path):
    audio_dir = tmp_path / "audio_overviews"
    audio_dir.mkdir()
    monkeypatch.setattr("ragapp.config.AUDIO_DIR", audio_dir)

    oid = manifest.create_audio_overview(title="Ohne Datei", subject=None, doc_ids=[],
                                          script_text="x", audio_path="fehlt.wav")
    manifest.delete_audio_overview(oid)  # darf nicht crashen, obwohl fehlt.wav nie existierte
    assert manifest.get_audio_overview(oid) is None
