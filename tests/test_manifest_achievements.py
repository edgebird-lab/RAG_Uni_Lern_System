"""Tests für die Errungenschaften-Persistenz (manifest.unlock_achievement()/
list_unlocked_achievements()) - der Katalog selbst lebt in
ragapp/achievements.py, hier wird nur "welche ID ist schon frei" geprüft.
Isolierte Temp-DB, niemals die echte data/manifest.db."""
from __future__ import annotations

import pytest

from ragapp import manifest


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "manifest_test.db"
    monkeypatch.setattr(manifest, "MANIFEST_DB", db_path)
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)
    return db_path


def test_unlock_achievement_gibt_true_beim_ersten_mal(isolated_db):
    assert manifest.unlock_achievement("streak_7") is True
    assert "streak_7" in manifest.list_unlocked_achievements()


def test_unlock_achievement_gibt_false_wenn_schon_frei(isolated_db):
    manifest.unlock_achievement("streak_7")
    assert manifest.unlock_achievement("streak_7") is False


def test_unlock_achievement_ist_idempotent_bezueglich_des_zeitpunkts(isolated_db, monkeypatch):
    import time
    times = iter([100.0, 200.0])
    monkeypatch.setattr(time, "time", lambda: next(times))
    manifest.unlock_achievement("streak_7")
    manifest.unlock_achievement("streak_7")   # zweiter Aufruf darf den Zeitpunkt NICHT ueberschreiben
    assert manifest.list_unlocked_achievements()["streak_7"] == 100.0


def test_list_unlocked_achievements_mehrere(isolated_db):
    manifest.unlock_achievement("streak_7")
    manifest.unlock_achievement("cards_100")
    unlocked = manifest.list_unlocked_achievements()
    assert set(unlocked.keys()) == {"streak_7", "cards_100"}


def test_list_unlocked_achievements_leer_ohne_freischaltungen(isolated_db):
    assert manifest.list_unlocked_achievements() == {}
