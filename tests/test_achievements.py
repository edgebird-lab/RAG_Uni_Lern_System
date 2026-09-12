"""Tests für ragapp/achievements.py (Katalog + Freischalt-Logik). Isolierte
Temp-DB, niemals die echte data/manifest.db. analytics.py hat eine eigene
_conn()/MANIFEST_DB, deshalb wird auch dort gepatcht (Lehre aus
test_analytics_total_reviews.py)."""
from __future__ import annotations

import time
import uuid

import pytest

from ragapp import achievements, analytics, manifest


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "manifest_test.db"
    monkeypatch.setattr(manifest, "MANIFEST_DB", db_path)
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)
    monkeypatch.setattr(analytics, "MANIFEST_DB", db_path)
    manifest.init_db()
    return db_path


def _log_review(subject: str, reviewed_at: float, rating: int = 2) -> None:
    with manifest._connect() as conn:
        cid = f"c-{uuid.uuid4().hex[:12]}"
        conn.execute(
            "INSERT INTO review_items (card_id, subject, front, back, suspended, "
            "use_flashcard, created_at, reps, due) VALUES (?,?,?,?,0,1,?,1,?)",
            (cid, subject, "F", "A", time.time(), time.time() + 86400))
        conn.execute(
            "INSERT INTO review_log (card_id, subject, rating, reviewed_at) "
            "VALUES (?,?,?,?)", (cid, subject, rating, reviewed_at))


def test_catalog_ist_nicht_leer(isolated_db):
    cat = achievements.catalog()
    assert len(cat) >= 5
    ids = [a.id for a in cat]
    assert len(ids) == len(set(ids))


def test_check_and_unlock_ohne_daten_schaltet_nichts_frei(isolated_db):
    assert achievements.check_and_unlock() == []
    assert manifest.list_unlocked_achievements() == {}


def test_check_and_unlock_schaltet_wiederholungs_meilenstein_frei(isolated_db):
    now = time.time()
    for _ in range(100):
        _log_review("mathe", now)
    newly = achievements.check_and_unlock()
    ids = [a.id for a in newly]
    assert "cards_100" in ids
    assert "cards_1000" not in ids


def test_check_and_unlock_meldet_bereits_freigeschaltetes_nicht_erneut(isolated_db):
    now = time.time()
    for _ in range(100):
        _log_review("mathe", now)
    first = achievements.check_and_unlock()
    assert any(a.id == "cards_100" for a in first)
    second = achievements.check_and_unlock()
    assert not any(a.id == "cards_100" for a in second)


def test_check_and_unlock_probeklausur(isolated_db):
    manifest.log_exam_attempt(80, 10)
    newly = achievements.check_and_unlock()
    assert any(a.id == "exam_passed" for a in newly)


def test_check_and_unlock_probeklausur_unter_schwelle_schaltet_nicht_frei(isolated_db):
    manifest.log_exam_attempt(50, 10)
    newly = achievements.check_and_unlock()
    assert not any(a.id == "exam_passed" for a in newly)


def test_check_and_unlock_lernplan_abgeschlossen(isolated_db):
    pid = manifest.create_study_plan(title="Klausurplan", subject="mathe", doc_ids=[],
                                     deadline=None, daily_minutes=30)
    manifest.update_study_plan(pid, status="done")
    newly = achievements.check_and_unlock()
    assert any(a.id == "plan_done" for a in newly)


def test_check_and_unlock_erste_notiz(isolated_db):
    manifest.create_note(title="Test", subject="mathe", body="Inhalt")
    newly = achievements.check_and_unlock()
    assert any(a.id == "first_note" for a in newly)


def test_night_owl_ist_als_versteckt_markiert(isolated_db):
    night_owl = next(a for a in achievements.catalog() if a.id == "night_owl")
    assert night_owl.hidden is True


def test_cards_100_hat_ehrlichen_fortschritt(isolated_db):
    now = time.time()
    for _ in range(37):
        _log_review("mathe", now)
    cards_100 = next(a for a in achievements.catalog() if a.id == "cards_100")
    cur, tgt = cards_100.progress()
    assert (cur, tgt) == (37, 100)


def test_achievements_ohne_progress_liefern_none():
    plan_done = next(a for a in achievements.catalog() if a.id == "plan_done")
    assert plan_done.progress is None


def test_perfect_round_schaltet_nur_mit_passendem_kontext_frei(isolated_db):
    ohne_kontext = achievements.check_and_unlock()
    assert not any(a.id == "perfect_round" for a in ohne_kontext)
    mit_kontext = achievements.check_and_unlock(
        context={"round_total": 10, "round_gewusst": 10})
    assert any(a.id == "perfect_round" for a in mit_kontext)


def test_perfect_round_schaltet_nicht_frei_wenn_nicht_alles_gewusst(isolated_db):
    newly = achievements.check_and_unlock(
        context={"round_total": 10, "round_gewusst": 9})
    assert not any(a.id == "perfect_round" for a in newly)


def test_perfect_round_schaltet_nicht_frei_unter_10_karten(isolated_db):
    newly = achievements.check_and_unlock(
        context={"round_total": 5, "round_gewusst": 5})
    assert not any(a.id == "perfect_round" for a in newly)


def test_leech_buster_schaltet_frei_ab_fuenf_bereinigten_dauerpatzern(isolated_db):
    newly = achievements.check_and_unlock(context={"leech_cleared": 5})
    assert any(a.id == "leech_buster" for a in newly)


def test_leech_buster_schaltet_nicht_frei_unter_fuenf(isolated_db):
    newly = achievements.check_and_unlock(context={"leech_cleared": 4})
    assert not any(a.id == "leech_buster" for a in newly)


def test_nearest_locked_ist_leer_ohne_fortschritt(isolated_db):
    assert achievements.nearest_locked() is None


def test_nearest_locked_findet_naechstliegende_ueber_schwelle(isolated_db):
    now = time.time()
    for _ in range(80):
        _log_review("mathe", now)
    nudge = achievements.nearest_locked(min_pct=70.0)
    assert nudge is not None
    assert nudge["id"] == "cards_100"
    assert nudge["current"] == 80
    assert nudge["target"] == 100


def test_nearest_locked_ignoriert_bereits_freigeschaltete(isolated_db):
    now = time.time()
    for _ in range(100):
        _log_review("mathe", now)
    achievements.check_and_unlock()  # schaltet cards_100 frei
    nudge = achievements.nearest_locked(min_pct=0.0)
    assert nudge is None or nudge["id"] != "cards_100"


def test_nearest_locked_ignoriert_versteckte_errungenschaften(isolated_db):
    # night_owl hat kein progress() -> kann per Definition nie als nudge
    # auftauchen, unabhaengig vom hidden-Flag; dieser Test dokumentiert das.
    night_owl = next(a for a in achievements.catalog() if a.id == "night_owl")
    assert night_owl.progress is None
