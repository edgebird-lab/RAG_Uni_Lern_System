"""Tests für die Fächer-Archivierung (manifest.archive_subject()/
unarchive_subject()/list_archived_subjects()) - ein "fertiges" Fach soll aus
den Lern-Dropdowns verschwinden (über die bereits etablierte suspended-
Markierung), ohne Karten zu löschen, und sich exakt wieder rückgängig machen
lassen. Isolierte Temp-DB, niemals die echte data/manifest.db."""
from __future__ import annotations

import pytest

from ragapp import manifest


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "manifest_test.db"
    monkeypatch.setattr(manifest, "MANIFEST_DB", db_path)
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)
    return db_path


def _insert_card(conn, *, subject: str, suspended: int = 0) -> str:
    import time
    import uuid
    cid = f"c-{uuid.uuid4().hex[:12]}"
    conn.execute(
        "INSERT INTO review_items (card_id, subject, front, back, suspended, "
        "use_flashcard, created_at) VALUES (?,?,?,?,?,1,?)",
        (cid, subject, "F", "A", suspended, time.time()))
    return cid


def test_archive_subject_pausiert_alle_aktiven_karten(isolated_db):
    with manifest._connect() as conn:
        c1 = _insert_card(conn, subject="mathe")
        c2 = _insert_card(conn, subject="mathe")
        c3 = _insert_card(conn, subject="physik")
    n = manifest.archive_subject("mathe")
    assert n == 2
    assert "mathe" not in manifest.study_subjects()
    assert "physik" in manifest.study_subjects()
    with manifest._connect() as conn:
        rows = {r["card_id"]: r["suspended"] for r in
               conn.execute("SELECT card_id, suspended FROM review_items")}
    assert rows[c1] == 1 and rows[c2] == 1
    assert rows[c3] == 0


def test_archive_subject_erscheint_in_der_archiv_liste(isolated_db):
    with manifest._connect() as conn:
        _insert_card(conn, subject="mathe")
    manifest.archive_subject("mathe")
    assert manifest.list_archived_subjects() == ["mathe"]


def test_unarchive_subject_reaktiviert_genau_diese_karten(isolated_db):
    with manifest._connect() as conn:
        c1 = _insert_card(conn, subject="mathe")
        c2 = _insert_card(conn, subject="mathe")
    manifest.archive_subject("mathe")
    n = manifest.unarchive_subject("mathe")
    assert n == 2
    assert "mathe" in manifest.study_subjects()
    assert manifest.list_archived_subjects() == []
    with manifest._connect() as conn:
        rows = {r["card_id"]: r["suspended"] for r in
               conn.execute("SELECT card_id, suspended FROM review_items")}
    assert rows[c1] == 0 and rows[c2] == 0


def test_unarchive_subject_laesst_vorher_manuell_pausierte_karte_in_ruhe(isolated_db):
    # Regressionstest fuer den eigentlichen Grund, WARUM archivierte Karten-IDs
    # gemerkt werden: eine Karte, die schon VOR dem Archivieren aus einem
    # anderen Grund pausiert war, darf beim Reaktivieren NICHT ploetzlich
    # wieder aktiv werden.
    with manifest._connect() as conn:
        c1 = _insert_card(conn, subject="mathe")               # aktiv
        c2 = _insert_card(conn, subject="mathe", suspended=1)   # schon vorher pausiert
    manifest.archive_subject("mathe")   # merkt sich NUR c1 (war aktiv)
    manifest.unarchive_subject("mathe")
    with manifest._connect() as conn:
        rows = {r["card_id"]: r["suspended"] for r in
               conn.execute("SELECT card_id, suspended FROM review_items")}
    assert rows[c1] == 0   # reaktiviert
    assert rows[c2] == 1   # bleibt pausiert - war nie Teil der Archivierung


def test_archive_subject_ohne_karten_funktioniert_trotzdem(isolated_db):
    n = manifest.archive_subject("leeres_fach")
    assert n == 0
    assert manifest.list_archived_subjects() == ["leeres_fach"]


def test_unarchive_unbekanntes_fach_tut_nichts_und_crasht_nicht(isolated_db):
    assert manifest.unarchive_subject("nie_archiviert") == 0


def test_archive_subject_zweimal_ist_idempotent(isolated_db):
    with manifest._connect() as conn:
        _insert_card(conn, subject="mathe")
    manifest.archive_subject("mathe")
    n2 = manifest.archive_subject("mathe")   # keine aktiven Karten mehr uebrig
    assert n2 == 0
    assert manifest.list_archived_subjects() == ["mathe"]
