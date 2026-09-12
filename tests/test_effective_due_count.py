"""Tests für manifest.due_breakdown()/effective_due_count() und die davon
abhängenden analytics.overview()/daily_goal_status() - Bugfix: "80 Karten
fällig" wurde vorher auch für brandneue, nie geübte Karten gemeldet, obwohl
das tägliche Neue-Karten-Limit sie absichtlich zurückhält. Isolierte
Temp-DB, niemals die echte data/manifest.db."""
from __future__ import annotations

import time
import uuid

import pytest

from ragapp import analytics, manifest


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "manifest_test.db"
    monkeypatch.setattr(manifest, "MANIFEST_DB", db_path)
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)
    monkeypatch.setattr(analytics, "MANIFEST_DB", db_path)
    manifest.init_db()
    return db_path


def _seed_new_card(subject: str) -> str:
    """Eine brandneue, nie geuebte Karte (reps=0) - genau wie
    upsert_review_items() sie anlegt: due = Erstellungszeitpunkt."""
    cid = uuid.uuid4().hex[:16]
    now = time.time()
    with manifest._connect() as conn:
        conn.execute(
            "INSERT INTO review_items (card_id, subject, front, back, suspended, "
            "use_flashcard, reps, created_at, due) VALUES (?,?,?,?,0,1,0,?,?)",
            (cid, subject, "F", "A", now, now))
    return cid


def _seed_reviewed_card(subject: str) -> str:
    """Eine schon geuebte, echt faellige Karte (reps>0)."""
    cid = uuid.uuid4().hex[:16]
    now = time.time()
    with manifest._connect() as conn:
        conn.execute(
            "INSERT INTO review_items (card_id, subject, front, back, suspended, "
            "use_flashcard, reps, created_at, due) VALUES (?,?,?,?,0,1,3,?,?)",
            (cid, subject, "F", "A", now, now - 3600))
    return cid


def _mark_studied_today(card_id: str, subject: str) -> None:
    with manifest._connect() as conn:
        conn.execute(
            "INSERT INTO review_log (card_id, subject, rating, reviewed_at) "
            "VALUES (?,?,2,?)", (card_id, subject, time.time()))


def _first_n_new_card_ids(subject: str, n: int) -> list[str]:
    with manifest._connect() as conn:
        rows = conn.execute(
            "SELECT card_id FROM review_items WHERE subject=? AND reps=0 LIMIT ?",
            (subject, n)).fetchall()
    return [r["card_id"] for r in rows]


def test_due_breakdown_trennt_neu_und_wiederholung(isolated_db):
    _seed_new_card("mathe")
    _seed_reviewed_card("mathe")
    b = manifest.due_breakdown("mathe")
    assert b == {"due_learning": 0, "due_review": 1, "due_new": 1}


def test_effective_due_count_deckelt_neue_karten_auf_tageslimit(isolated_db):
    for _ in range(100):
        _seed_new_card("mathe")
    # Noch nichts heute gelernt -> genau new_per_day duerfen als "faellig" zaehlen.
    assert manifest.effective_due_count("mathe", new_per_day=20) == 20


def test_effective_due_count_beruecksichtigt_schon_heute_gelernte(isolated_db):
    for _ in range(100):
        _seed_new_card("mathe")
    for cid in _first_n_new_card_ids("mathe", 20):
        _mark_studied_today(cid, "mathe")
    # 20 von 20 erlaubten neuen Karten schon gelernt -> 0 weitere neue "fällig",
    # NICHT 80 (der Bug, den dieser Test verhindern soll).
    assert manifest.effective_due_count("mathe", new_per_day=20) == 0


def test_effective_due_count_zaehlt_echte_wiederholungen_immer_mit(isolated_db):
    for _ in range(100):
        _seed_new_card("mathe")
    _seed_reviewed_card("mathe")  # echte faellige Wiederholung
    # Neue-Karten-Limit komplett ausgeschoepft ...
    for cid in _first_n_new_card_ids("mathe", 20):
        _mark_studied_today(cid, "mathe")
    # ... die echte Wiederholung zaehlt trotzdem weiter als "fällig".
    assert manifest.effective_due_count("mathe", new_per_day=20) == 1


def test_effective_due_count_ohne_limit_ist_unbegrenzt(isolated_db):
    for _ in range(50):
        _seed_new_card("mathe")
    assert manifest.effective_due_count("mathe", new_per_day=0) == 50


def test_effective_due_count_nutzt_settings_default_ohne_explizites_limit(isolated_db, monkeypatch):
    monkeypatch.setattr(analytics.settings, "SRS_NEW_PER_DAY", 5, raising=False)
    for _ in range(50):
        _seed_new_card("mathe")
    assert manifest.effective_due_count("mathe") == 5


def test_overview_due_verwendet_effective_due_count(isolated_db):
    for _ in range(100):
        _seed_new_card("mathe")
    for cid in _first_n_new_card_ids("mathe", 20):
        _mark_studied_today(cid, "mathe")
    ov = analytics.overview("mathe")
    assert ov["due"] == 0, "overview()['due'] soll das Tageslimit respektieren, nicht 80 melden"


def test_daily_goal_status_ampel_ignoriert_gedeckelte_neue_karten(isolated_db, monkeypatch):
    monkeypatch.setattr(analytics.settings, "DAILY_REVIEW_GOAL", 10, raising=False)
    monkeypatch.setattr(analytics.settings, "SRS_NEW_PER_DAY", 20, raising=False)
    for _ in range(100):
        _seed_new_card("mathe")
    for cid in _first_n_new_card_ids("mathe", 20):
        _mark_studied_today(cid, "mathe")
    status = analytics.daily_goal_status("mathe")
    # Tageslimit voll ausgeschoepft -> 0 "fällige" neue Karten -> Ampel gruen,
    # NICHT rot nur wegen 80 uebrig gebliebener, absichtlich zurueckgehaltener
    # neuer Karten.
    assert status["due"] == 0
    assert status["ampel"] == "grün"


def _seed_learning_card(subject: str, *, due_offset: float = -60.0) -> str:
    """Faellige Learning-Karte (fsrs_state=1)."""
    cid = uuid.uuid4().hex[:16]
    now = time.time()
    with manifest._connect() as conn:
        conn.execute(
            "INSERT INTO review_items (card_id, subject, front, back, suspended, "
            "use_flashcard, reps, fsrs_state, created_at, due) "
            "VALUES (?,?,?,?,0,1,1,1,?,?)",
            (cid, subject, "F", "A", now, now + due_offset))
    return cid


def _seed_card_with_flags(subject: str, *, use_flashcard: int = 1,
                          deck: str | None = None) -> str:
    cid = uuid.uuid4().hex[:16]
    now = time.time()
    with manifest._connect() as conn:
        conn.execute(
            "INSERT INTO review_items (card_id, subject, front, back, suspended, "
            "use_flashcard, reps, deck, created_at, due) "
            "VALUES (?,?,?,?,0,?,0,?,?,?)",
            (cid, subject, "F", "A", use_flashcard, deck, now, now))
    return cid


def test_due_breakdown_zaehlt_learning_separat(isolated_db):
    _seed_new_card("mathe")
    _seed_reviewed_card("mathe")
    _seed_learning_card("mathe")
    b = manifest.due_breakdown("mathe")
    assert b["due_learning"] == 1
    assert b["due_review"] == 1
    assert b["due_new"] == 1


def test_gather_study_cards_reihenfolge_lernen_review_neu(isolated_db):
    new_id = _seed_new_card("mathe")
    rev_id = _seed_reviewed_card("mathe")
    learn_id = _seed_learning_card("mathe")
    cards = manifest.gather_study_cards("mathe", new_per_day=20, limit=10)
    ids = [c["card_id"] for c in cards]
    assert ids[0] == learn_id
    assert ids[1] == rev_id
    assert ids[2] == new_id


def test_gather_study_cards_respektiert_tageslimit_neuer(isolated_db, monkeypatch):
    monkeypatch.setattr(
        "ragapp.config.settings.SRS_NEW_PER_DAY", 5, raising=False)
    for _ in range(30):
        _seed_new_card("mathe")
    _seed_reviewed_card("mathe")
    cards = manifest.gather_study_cards("mathe", new_per_day=5, limit=100)
    news = [c for c in cards if int(c.get("reps") or 0) == 0
            and c.get("fsrs_state") not in (1, 3)]
    reviews = [c for c in cards if int(c.get("reps") or 0) > 0
               and c.get("fsrs_state") not in (1, 3)]
    assert len(news) == 5
    assert len(reviews) == 1


def test_gather_study_cards_zweite_sitzung_keine_weiteren_neuen(
        isolated_db, monkeypatch):
    monkeypatch.setattr(
        "ragapp.config.settings.SRS_NEW_PER_DAY", 5, raising=False)
    for _ in range(20):
        _seed_new_card("mathe")
    for cid in _first_n_new_card_ids("mathe", 5):
        _mark_studied_today(cid, "mathe")
        # reps>0 simuliert: Karte wurde heute eingefuehrt und ist nicht mehr "neu"
        with manifest._connect() as conn:
            conn.execute(
                "UPDATE review_items SET reps=1, fsrs_state=2, due=? WHERE card_id=?",
                (time.time() + 86400, cid))
    cards = manifest.gather_study_cards("mathe", new_per_day=5, limit=100)
    news = [c for c in cards if int(c.get("reps") or 0) == 0
            and c.get("fsrs_state") not in (1, 3)]
    assert news == []


def test_gather_study_cards_ohne_use_flashcard(isolated_db):
    active = _seed_card_with_flags("mathe", use_flashcard=1)
    _seed_card_with_flags("mathe", use_flashcard=0)
    cards = manifest.gather_study_cards("mathe", new_per_day=20)
    assert [c["card_id"] for c in cards] == [active]


def test_deck_overview_liefert_queue_spalten(isolated_db):
    _seed_card_with_flags("mathe", deck="Algebra")
    _seed_learning_card("mathe")
    with manifest._connect() as conn:
        conn.execute(
            "UPDATE review_items SET deck=? WHERE fsrs_state=1", ("Algebra",))
    ov = {o["deck"]: o for o in manifest.deck_overview("mathe", only_flashcard=True)}
    assert "Algebra" in ov
    assert ov["Algebra"]["new"] >= 1
    assert ov["Algebra"]["learning"] == 1
    assert "review" in ov["Algebra"]


def test_should_requeue_in_session_learning_kurz():
    from ragapp import study
    now = time.time()
    assert study.should_requeue_in_session(
        {"fsrs_state": 1, "due": now + 60}, now=now) is True
    assert study.should_requeue_in_session(
        {"fsrs_state": 3, "due": now + 300}, now=now) is True
    assert study.should_requeue_in_session(
        {"fsrs_state": 2, "due": now + 60}, now=now) is False
    assert study.should_requeue_in_session(
        {"fsrs_state": 1, "due": now + 3600}, now=now) is False
