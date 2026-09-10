"""FSRS-6-Wiederholungs-Rechnung (``ragapp.study.fsrs_next``), ersetzt das
fruehere SM-2 (``tests/test_study_sm2.py``).

Rein rechnerisch, ohne LLM/Embedding/Ollama/Chroma. ``fsrs_next`` wird isoliert
geladen (wie zuvor ``sm2_next``), weil ein Vollimport von ``ragapp.study`` ueber
den Vektorstore chromadb zieht. Das ``fsrs``-Paket selbst ist leichtgewichtig
(nur ``typing-extensions``) und wird hier direkt importiert.
"""
import time as _time
from datetime import datetime, timezone

import pytest
from fsrs import Card, Rating, Scheduler, State


@pytest.fixture
def fsrs_next(load_functions, ragapp_dir):
    funcs = load_functions(
        ragapp_dir / "study.py",
        ["fsrs_next", "_scheduler", "_to_utc"],
        {
            "time": _time, "datetime": datetime, "timezone": timezone,
            "Card": Card, "Rating": Rating, "Scheduler": Scheduler, "State": State,
            "NICHT": 0, "HALB": 1, "GEWUSST": 2,
            "_FSRS_RATING": {0: Rating.Again, 1: Rating.Hard, 2: Rating.Good},
        },
    )
    return funcs["fsrs_next"]


def _fresh_card() -> dict:
    return {"fsrs_state": None, "fsrs_step": None, "stability": None,
            "difficulty": None, "due": None, "last_review": None,
            "reps": 0, "lapses": 0}


def _reviewed_card(*, reps=4, stability=30.0, difficulty=3.0,
                   last_review=-30 * 86400.0, due=0.0) -> dict:
    return {"fsrs_state": State.Review.value, "fsrs_step": None,
            "stability": stability, "difficulty": difficulty,
            "due": due, "last_review": last_review, "reps": reps, "lapses": 0}


def test_nicht_setzt_reps_zurueck_und_zaehlt_lapse(fsrs_next):
    card = _reviewed_card()
    r = fsrs_next(0, card, now=0.0)
    assert r["reps"] == 0
    assert r["lapses"] == 1
    assert r["stability"] is not None
    assert r["due"] > 0.0    # kurzer Relearn-Schritt, aber in der Zukunft


def test_halb_laesst_reps_lapses_unveraendert(fsrs_next):
    card = _reviewed_card(reps=3)
    r = fsrs_next(1, card, now=0.0)
    assert r["reps"] == 3
    assert r["lapses"] == 0


def test_gewusst_erhoeht_reps_auf_frischer_karte(fsrs_next):
    r = fsrs_next(2, _fresh_card(), now=0.0)
    assert r["reps"] == 1
    assert r["lapses"] == 0
    assert r["due"] > 0.0
    assert r["stability"] is not None
    assert r["difficulty"] is not None
    assert r["fsrs_state"] in (State.Learning.value, State.Review.value)


def test_gewusst_faelligkeit_waechst_ueber_mehrere_runden(fsrs_next):
    """Mit wiederholt 'Gewusst' soll der Abstand bis zur naechsten Faelligkeit
    ueber mehrere Runden hinweg klar zunehmen (Kernversprechen von FSRS: laenger
    gelernte Karten werden seltener abgefragt)."""
    card = _fresh_card()
    now = 0.0
    gaps = []
    for _ in range(5):
        r = fsrs_next(2, card, now=now)
        gaps.append(r["due"] - now)
        card = {**card, "fsrs_state": r["fsrs_state"], "fsrs_step": r["fsrs_step"],
               "stability": r["stability"], "difficulty": r["difficulty"],
               "reps": r["reps"], "lapses": r["lapses"], "last_review": now,
               "due": r["due"]}
        now = r["due"]
    assert gaps[-1] > gaps[0]
    assert all(g > 0 for g in gaps)


def test_klausur_modus_kappt_auf_klausurtag(fsrs_next):
    card = _reviewed_card()
    cap_days = 3
    r = fsrs_next(2, card, now=0.0, max_interval_days=cap_days)
    assert r["due"] == pytest.approx(cap_days * 86400.0)
    assert r["interval"] == pytest.approx(float(cap_days), abs=0.01)


def test_cap_verkuerzt_kurzen_relearn_nicht(fsrs_next):
    # "Nicht gewusst" liegt weit vor dem Klausurtag -> der Deckel greift nicht.
    card = _reviewed_card()
    r = fsrs_next(0, card, now=0.0, max_interval_days=3)
    assert r["due"] < 3 * 86400.0


def test_difficulty_bleibt_im_erwarteten_band(fsrs_next):
    r = fsrs_next(2, _fresh_card(), now=0.0)
    assert 1.0 <= r["difficulty"] <= 10.0
    r2 = fsrs_next(0, _reviewed_card(), now=0.0)
    assert 1.0 <= r2["difficulty"] <= 10.0


def test_seeded_legacy_karte_wird_korrekt_uebernommen(fsrs_next):
    """Backfill-Fall: eine per Migration geseedete Karte (state=Review, stability/
    difficulty aus dem alten ease/interval abgeleitet) muss fsrs_next genauso
    verarbeiten koennen wie eine 'echte' FSRS-Karte."""
    seeded = {"fsrs_state": State.Review.value, "fsrs_step": None,
             "stability": 12.0, "difficulty": 4.2,
             "due": 0.0, "last_review": -12 * 86400.0, "reps": 5, "lapses": 1}
    r = fsrs_next(2, seeded, now=0.0)
    assert r["reps"] == 6
    assert r["due"] > 0.0
