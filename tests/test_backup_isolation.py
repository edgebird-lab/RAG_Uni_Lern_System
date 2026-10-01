"""Schutz der echten Sicherungen: kein Test darf ``data/backups`` anfassen.

Regression: ``manifest.delete_card_ids`` zieht vor dem Löschen einen Snapshot - über die Pfade
des ``backup``-Moduls, nicht über die vom Test umgebogene Test-Datenbank. Jeder Testlauf legte
so Kopien der ECHTEN Datenbank an und rotierte ältere echte Sicherungen weg (conftest.py)."""
from __future__ import annotations

from ragapp import backup, config, manifest


def test_backup_zeigt_in_tests_nie_auf_die_echten_sicherungen():
    assert backup.BACKUP_DIR != config.DATA_DIR / "backups"
    assert not backup.MANIFEST_DB.exists()
    assert backup.snapshot("test") is None


def test_kartenloeschen_in_einer_testdatenbank_legt_keine_echte_sicherung_an(tmp_path, monkeypatch):
    real_dir = config.DATA_DIR / "backups"
    before = sorted(p.name for p in real_dir.glob("*")) if real_dir.exists() else []
    monkeypatch.setattr(manifest, "MANIFEST_DB", tmp_path / "manifest_test.db")
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)
    manifest.upsert_review_items([{
        "card_id": "c1", "source": "question", "chroma_id": "c1", "subject": "X", "topic": "Seite 1",
        "front": "Frage?", "back": "Beleg", "answer": "A", "doc_id": "d"}])
    assert manifest.delete_card_ids(["c1"]) == ["c1"]
    after = sorted(p.name for p in real_dir.glob("*")) if real_dir.exists() else []
    assert after == before
