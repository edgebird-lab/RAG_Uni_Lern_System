"""Tests fuer die pronunciation_fixes-CRUD in ragapp.manifest (isolierte
Temp-DB, niemals die echte data/manifest.db - gleiches Muster wie
test_manifest_audio_overviews.py). Dauerhaft gemerkte Ausspracheregeln
(z. B. "nmap" -> "en map"), vom Nutzer in der Audio-Overview-Seite bestaetigt
(siehe ragapp/audio_overview.py::suggest_pronunciations)."""
from __future__ import annotations

import pytest

from ragapp import manifest


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "manifest_test.db"
    monkeypatch.setattr(manifest, "MANIFEST_DB", db_path)
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)
    return db_path


def test_upsert_and_list_pronunciation_fix(isolated_db):
    manifest.upsert_pronunciation_fix("nmap", "en map")
    assert manifest.list_pronunciation_fixes() == {"nmap": "en map"}


def test_list_pronunciation_fixes_empty_by_default(isolated_db):
    assert manifest.list_pronunciation_fixes() == {}


def test_upsert_same_word_twice_updates_replacement_not_duplicates(isolated_db):
    manifest.upsert_pronunciation_fix("nmap", "en map")
    manifest.upsert_pronunciation_fix("nmap", "korrigierte aussprache")
    assert manifest.list_pronunciation_fixes() == {"nmap": "korrigierte aussprache"}


def test_multiple_words_are_all_listed(isolated_db):
    manifest.upsert_pronunciation_fix("nmap", "en map")
    manifest.upsert_pronunciation_fix("GTFOBins", "gie-ti-eff-o-bins")
    fixes = manifest.list_pronunciation_fixes()
    assert fixes == {"nmap": "en map", "GTFOBins": "gie-ti-eff-o-bins"}


def test_delete_pronunciation_fix_removes_it(isolated_db):
    manifest.upsert_pronunciation_fix("nmap", "en map")
    manifest.upsert_pronunciation_fix("SSH", "es es ha")
    manifest.delete_pronunciation_fix("nmap")
    assert manifest.list_pronunciation_fixes() == {"SSH": "es es ha"}


def test_delete_unknown_word_does_not_raise(isolated_db):
    manifest.delete_pronunciation_fix("existiert-nicht")  # darf nicht crashen
    assert manifest.list_pronunciation_fixes() == {}
