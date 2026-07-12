"""SM-2 / Spaced-Repetition-Rechnung (``ragapp.study.sm2_next``).

Rein rechnerisch, ohne LLM/Embedding/Ollama. ``sm2_next`` wird isoliert geladen,
weil ``ragapp.study`` beim Vollimport ``chromadb`` (ueber den Vektorstore) zieht.
Die Funktion liest ihre Parameter (SRS_*) aus der echten Config - deshalb werden
die Erwartungswerte gegen ``settings`` gebildet und driften nicht.
"""
import time as _time

import pytest

from ragapp.config import settings as S


@pytest.fixture
def sm2(load_functions, ragapp_dir):
    funcs = load_functions(
        ragapp_dir / "study.py",
        ["sm2_next"],
        {"time": _time, "NICHT": 0, "HALB": 1, "GEWUSST": 2},
    )
    return funcs["sm2_next"]


def test_nicht_setzt_zurueck_und_zaehlt_lapse(sm2):
    r = sm2(0, ease=2.5, interval=5, reps=3, lapses=1, now=0.0)
    assert r["interval"] == 0           # zurueck auf Anfang
    assert r["reps"] == 0
    assert r["lapses"] == 2             # Lapse hochgezaehlt
    # kurzer Relearn-Schritt in MINUTEN (nicht Tagen)
    assert r["due"] == pytest.approx(S.SRS_AGAIN_MINUTES * 60)
    assert r["ease"] == round(max(S.SRS_EASE_MIN, 2.5 + S.SRS_EASE_AGAIN), 3)


def test_halb_haelt_stufe_und_intervall(sm2):
    r = sm2(1, ease=2.5, interval=5, reps=3, lapses=1, now=0.0)
    assert r["interval"] == 5           # Stufe/Intervall bleiben
    assert r["reps"] == 3
    assert r["lapses"] == 1             # kein Lapse bei "halb"
    assert r["due"] == pytest.approx(S.SRS_HALF_MINUTES * 60)
    assert r["ease"] == round(max(S.SRS_EASE_MIN, 2.5 + S.SRS_EASE_HALF), 3)


def test_gewusst_erste_stufe_der_leiter(sm2):
    r = sm2(2, ease=2.5, interval=0, reps=0, lapses=0, now=0.0)
    assert r["reps"] == 1
    assert r["lapses"] == 0
    assert r["ease"] == round(min(S.SRS_EASE_MAX, 2.5 + S.SRS_EASE_GOOD), 3)
    step0 = float(S.SRS_GOOD_STEPS_MIN[0])
    assert r["due"] == pytest.approx(step0 * 60)
    assert r["interval"] == pytest.approx(round(step0 / 1440.0, 4))


def test_gewusst_leiter_waechst_streng_monoton(sm2):
    ease, interval, reps, lapses = 2.5, 0, 0, 0
    prev_due = -1.0
    for _ in range(len(S.SRS_GOOD_STEPS_MIN)):
        r = sm2(2, ease=ease, interval=interval, reps=reps, lapses=lapses, now=0.0)
        assert r["due"] > prev_due      # jede Stufe legt die Faelligkeit weiter nach hinten
        prev_due = r["due"]
        ease, interval, reps, lapses = r["ease"], r["interval"], r["reps"], r["lapses"]
    assert reps == len(S.SRS_GOOD_STEPS_MIN)


def test_gewusst_jenseits_der_leiter_waechst_mit_ease(sm2):
    n = len(S.SRS_GOOD_STEPS_MIN)
    r = sm2(2, ease=2.5, interval=21, reps=n, lapses=0, now=0.0)
    assert r["reps"] == n + 1
    base = max(21 * 1440.0, float(S.SRS_GOOD_STEPS_MIN[-1]))
    ease_new = min(S.SRS_EASE_MAX, 2.5 + S.SRS_EASE_GOOD)
    minutes = base * ease_new * max(0.1, S.SRS_INTERVAL_FACTOR)
    assert r["due"] == pytest.approx(minutes * 60)
    assert r["interval"] == pytest.approx(round(minutes / 1440.0, 4))


def test_klausur_modus_kappt_auf_klausurtag(sm2):
    n = len(S.SRS_GOOD_STEPS_MIN)
    cap_days = 3
    r = sm2(2, ease=2.5, interval=21, reps=n, lapses=0, now=0.0, max_interval_days=cap_days)
    assert r["due"] == pytest.approx(cap_days * 86400.0)   # nie hinter den Klausurtag
    assert r["interval"] == round(float(cap_days), 4)


def test_cap_verkuerzt_kurzen_relearn_nicht(sm2):
    # "Nicht gewusst" liegt weit vor dem Klausurtag -> der Deckel greift nicht.
    r = sm2(0, ease=2.5, interval=5, reps=3, lapses=0, now=0.0, max_interval_days=3)
    assert r["due"] == pytest.approx(S.SRS_AGAIN_MINUTES * 60)
    assert r["interval"] == 0


def test_ease_bleibt_in_den_grenzen(sm2):
    # Obergrenze: GEWUSST treibt die Ease nie ueber das Maximum.
    hoch = sm2(2, ease=S.SRS_EASE_MAX, interval=1, reps=0, lapses=0, now=0.0)
    assert hoch["ease"] <= S.SRS_EASE_MAX
    # Untergrenze: NICHT drueckt die Ease nie unter das Minimum.
    tief = sm2(0, ease=S.SRS_EASE_MIN, interval=1, reps=1, lapses=0, now=0.0)
    assert tief["ease"] >= S.SRS_EASE_MIN
