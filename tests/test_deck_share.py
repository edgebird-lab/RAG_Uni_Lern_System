"""Tests für ragapp.deck_share (Lerndeck-Export/-Import für Lerngruppen).
Isolierte Temp-DB, niemals die echte data/manifest.db."""
from __future__ import annotations

import json
import time
import uuid

import pytest

from ragapp import deck_share, manifest


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "manifest_test.db"
    monkeypatch.setattr(manifest, "MANIFEST_DB", db_path)
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)
    manifest.init_db()
    return db_path


def _seed_card(subject: str, front: str, answer: str, topic: str | None = None,
               deck: str | None = None) -> str:
    cid = uuid.uuid4().hex[:16]
    with manifest._connect() as conn:
        conn.execute(
            "INSERT INTO review_items (card_id, subject, topic, front, back, answer, "
            "deck, suspended, use_flashcard, created_at, due) "
            "VALUES (?,?,?,?,?,?,?,0,1,?,?)",
            (cid, subject, topic, front, answer, answer, deck, time.time(), time.time()))
    return cid


def test_build_deck_export_enthaelt_nur_karten_mit_antwort(isolated_db):
    _seed_card("mathe", "Frage A", "Antwort A")
    _seed_card("mathe", "Frage ohne Antwort", "")
    data, n = deck_share.build_deck_export(subject="mathe")
    assert n == 1
    payload = json.loads(data)
    assert len(payload["cards"]) == 1
    assert payload["cards"][0]["front"] == "Frage A"


def test_build_deck_export_hat_erwartetes_format_und_feld(isolated_db):
    _seed_card("mathe", "F", "A", topic="Integrale", deck="Klausur 1")
    data, _ = deck_share.build_deck_export(subject="mathe")
    payload = json.loads(data)
    assert payload["format"] == "rag-lernsystem-deck-v1"
    card = payload["cards"][0]
    assert card == {"front": "F", "answer": "A", "topic": "Integrale", "deck": "Klausur 1"}


def test_parse_deck_import_liest_gueltige_datei(isolated_db):
    _seed_card("mathe", "F1", "A1")
    data, _ = deck_share.build_deck_export(subject="mathe")
    result = deck_share.parse_deck_import(data)
    assert len(result["cards"]) == 1
    assert result["cards"][0]["front"] == "F1"


def test_parse_deck_import_verwirft_falsches_format(isolated_db):
    bad = json.dumps({"format": "irgendwas-anderes", "cards": []}).encode("utf-8")
    with pytest.raises(ValueError):
        deck_share.parse_deck_import(bad)


def test_parse_deck_import_verwirft_kaputtes_json(isolated_db):
    with pytest.raises(ValueError):
        deck_share.parse_deck_import(b"das ist kein json {{{")


def test_parse_deck_import_ueberspringt_karten_ohne_antwort():
    data = json.dumps({
        "format": "rag-lernsystem-deck-v1",
        "cards": [{"front": "F1", "answer": "A1"}, {"front": "F2", "answer": ""}],
    }).encode("utf-8")
    result = deck_share.parse_deck_import(data)
    assert len(result["cards"]) == 1


def test_import_deck_cards_legt_neue_karten_im_gewaehlten_fach_an(isolated_db):
    n = deck_share.import_deck_cards(
        [{"front": "F1", "answer": "A1", "topic": None, "deck": None}], subject="physik")
    assert n == 1
    rows = manifest.list_cards(subject="physik")
    assert len(rows) == 1
    assert rows[0]["front"] == "F1"
    assert rows[0]["answer"] == "A1"
    assert rows[0]["subject"] == "physik"


def test_import_deck_cards_ordnet_stapel_zu(isolated_db):
    deck_share.import_deck_cards(
        [{"front": "F1", "answer": "A1", "topic": None, "deck": "Klausur 1"}],
        subject="physik")
    rows = manifest.list_cards(subject="physik")
    assert rows[0]["deck"] == "Klausur 1"


def test_import_deck_cards_vergibt_immer_frische_ids(isolated_db):
    cid_own = _seed_card("physik", "Eigene Karte", "Eigene Antwort")
    deck_share.import_deck_cards(
        [{"front": "Importierte Karte", "answer": "X", "topic": None, "deck": None}],
        subject="physik")
    rows = manifest.list_cards(subject="physik")
    ids = {r["card_id"] for r in rows}
    assert cid_own in ids
    assert len(ids) == 2


def test_export_import_roundtrip(isolated_db):
    _seed_card("mathe", "Roundtrip-Frage", "Roundtrip-Antwort", topic="T", deck="D")
    data, n_exported = deck_share.build_deck_export(subject="mathe")
    parsed = deck_share.parse_deck_import(data)
    n_imported = deck_share.import_deck_cards(parsed["cards"], subject="mathe_kopie")
    assert n_exported == n_imported == 1
    imported_rows = manifest.list_cards(subject="mathe_kopie")
    assert imported_rows[0]["front"] == "Roundtrip-Frage"
    assert imported_rows[0]["deck"] == "D"
