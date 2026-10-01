"""Lernplan-Hinweise: veralteter Zeitplan, Zieldatum/Klausur, Aufschlüsselung der Zeitschätzung.
Reine Funktionen aus ``ragapp.study_plan`` - offline, ohne Datenbank."""
from __future__ import annotations

from datetime import date

import pytest

from ragapp import study_plan

TODAY = date(2026, 10, 5)


def sec(sid, est, done=False):
    return {"section_id": sid, "est_minutes": est, "done": done}


def blk(sid, minutes, day="2026-10-06"):
    return {"section_id": sid, "planned_min": minutes, "planned_date": day}


# --------------------------------------------------------------------------- #
# plan_staleness
# --------------------------------------------------------------------------- #
def test_ohne_themen_ist_der_zustand_leer():
    assert study_plan.plan_staleness([], [])["state"] == "empty"


def test_themen_ohne_zeitplan_fehlt_der_plan():
    res = study_plan.plan_staleness([sec("a", 60)], [])
    assert res["state"] == "missing" and "noch nicht berechnet" in res["reasons"][0]


def test_passender_zeitplan_ist_ok_auch_mit_kleiner_abweichung():
    res = study_plan.plan_staleness([sec("a", 60), sec("b", 120)],
                                    [blk("a", 25), blk("a", 25), blk("a", 10), blk("b", 120)])
    assert res == {"state": "ok", "reasons": [], "orphans": 0, "uncovered": 0, "mismatch": 0}
    # 20 % bzw. mindestens 10 Min Toleranz
    assert study_plan.plan_staleness([sec("a", 60)], [blk("a", 52)])["state"] == "ok"


def test_bloecke_zu_verschwundenen_themen_machen_den_plan_veraltet():
    res = study_plan.plan_staleness([sec("a", 60)], [blk("a", 60), blk("alt", 25), {"section_id": None, "planned_min": 5}])
    assert res["state"] == "stale" and res["orphans"] == 2
    assert "nicht mehr gibt" in res["reasons"][0]


def test_neues_thema_ohne_termine_macht_den_plan_veraltet():
    res = study_plan.plan_staleness([sec("a", 60), sec("neu", 90)], [blk("a", 60)])
    assert res["state"] == "stale" and res["uncovered"] == 1


def test_erledigtes_thema_ohne_bloecke_ist_kein_mangel():
    res = study_plan.plan_staleness([sec("a", 60), sec("fertig", 90, done=True)], [blk("a", 60)])
    assert res["state"] == "ok"


def test_geaenderte_minuten_der_gliederung_machen_den_plan_veraltet():
    assert study_plan.plan_staleness([sec("a", 120)], [blk("a", 60)])["mismatch"] == 1     # mehr geschaetzt
    assert study_plan.plan_staleness([sec("a", 30)], [blk("a", 120)])["mismatch"] == 1     # weniger geschaetzt


def test_knappes_zieldatum_darf_bloecke_weglassen_ohne_veraltet_zu_wirken():
    sections = [sec("a", 60), sec("b", 90)]
    blocks = [blk("a", 60), blk("b", 25)]                    # b nur teilweise (Engpass)
    assert study_plan.plan_staleness(sections, blocks)["state"] == "stale"
    assert study_plan.plan_staleness(sections, blocks, allow_shortfall=True)["state"] == "ok"
    # Zu VIEL geplant bleibt auch beim Engpass ein Mangel.
    assert study_plan.plan_staleness([sec("a", 30)], [blk("a", 120)], allow_shortfall=True)["state"] == "stale"


def test_nach_neu_gliedern_mit_alten_bloecken_ist_der_plan_veraltet():
    """Der echte Fall: 14 alte Themen -> 38 neue; die alten Bloecke haengen an wenigen neuen."""
    new = [sec(f"n{i}", 60) for i in range(6)]
    blocks = [blk("n0", 25) for _ in range(20)]               # alles auf ein Thema umgehaengt
    res = study_plan.plan_staleness(new, blocks)
    assert res["state"] == "stale" and res["uncovered"] == 5 and res["mismatch"] == 1


# --------------------------------------------------------------------------- #
# deadline_hints
# --------------------------------------------------------------------------- #
def preview(last="2026-12-05", total=3928, eff=60, shortfall=0, deadline_days=None):
    return {"blocks": [{"planned_date": "2026-10-05"}, {"planned_date": last}],
            "total_minutes": total, "effective_daily_min": eff, "shortfall_minutes": shortfall,
            "deadline_days": deadline_days}


def texts(hints):
    return [h["text"] for h in hints]


def test_ohne_zieldatum_und_ohne_klausur_wird_das_tempo_erklaert():
    hints = study_plan.deadline_hints({"deadline": None}, preview(), exam_iso=None, today=TODAY)
    assert len(hints) == 1 and hints[0]["level"] == "info" and hints[0]["action"] is None
    t = hints[0]["text"]
    assert "Ohne Zieldatum" in t and "3928 Min" in t and "60 Min/Tag" in t
    assert "62 Kalendertage" in t and "05.12.2026" in t


def test_ohne_zieldatum_aber_mit_klausur_wird_uebernahme_angeboten():
    hints = study_plan.deadline_hints({"deadline": None}, preview(last="2026-11-20"),
                                      exam_iso="2026-12-01", today=TODAY)
    exam_hint = [h for h in hints if h["action"] == "use_exam_date"]
    assert len(exam_hint) == 1 and "01.12.2026" in exam_hint[0]["text"] and "in 57 Tagen" in exam_hint[0]["text"]
    assert not [h for h in hints if h["level"] == "warning"]


def test_ohne_zieldatum_warnt_wenn_der_plan_nicht_bis_zur_klausur_reicht():
    hints = study_plan.deadline_hints({"deadline": None}, preview(last="2026-12-05"),
                                      exam_iso="2026-11-20", today=TODAY)
    warn = [h for h in hints if h["level"] == "warning"]
    assert len(warn) == 1 and "reicht der Plan nicht bis zur Klausur" in warn[0]["text"]


def test_vergangene_klausur_wird_nicht_vorgeschlagen():
    hints = study_plan.deadline_hints({"deadline": None}, preview(), exam_iso="2026-09-01", today=TODAY)
    assert not [h for h in hints if h["action"]]


def test_zieldatum_in_der_vergangenheit_wird_gewarnt():
    hints = study_plan.deadline_hints({"deadline": "2026-09-30"}, preview(), exam_iso=None, today=TODAY)
    assert hints[0]["level"] == "warning" and "Vergangenheit" in hints[0]["text"]


def test_zieldatum_nach_der_klausur_warnt_und_bietet_uebernahme():
    hints = study_plan.deadline_hints({"deadline": "2026-12-10"}, preview(), exam_iso="2026-12-01", today=TODAY)
    assert hints[0]["level"] == "warning" and hints[0]["action"] == "use_exam_date"
    assert "nach der Klausur" in hints[0]["text"]


def test_zieldatum_vor_der_klausur_nennt_den_puffer():
    hints = study_plan.deadline_hints({"deadline": "2026-11-24"}, preview(), exam_iso="2026-12-01", today=TODAY)
    assert hints[0]["level"] == "info" and "7 Tage vor der Klausur" in hints[0]["text"]


def test_zieldatum_gleich_klausur_braucht_keinen_hinweis():
    assert study_plan.deadline_hints({"deadline": "2026-12-01"}, preview(), exam_iso="2026-12-01",
                                     today=TODAY) == []


def test_engpass_nennt_das_noetige_tempo_und_die_empfohlene_obergrenze(monkeypatch):
    monkeypatch.setattr(study_plan.settings, "PLAN_MAX_DAILY_FOCUS_MIN", 240)
    hints = study_plan.deadline_hints(
        {"deadline": "2026-10-15"}, preview(total=4000, shortfall=3000, deadline_days=11),
        exam_iso=None, today=TODAY)
    t = texts(hints)[-1]
    assert "mindestens etwa 364 Min" in t and "Obergrenze von 240 Min/Tag" in t
    hints = study_plan.deadline_hints(
        {"deadline": "2026-10-15"}, preview(total=1000, shortfall=200, deadline_days=11),
        exam_iso=None, today=TODAY)
    assert "mindestens etwa 91 Min" in texts(hints)[-1] and "Obergrenze" not in texts(hints)[-1]


def test_ohne_bloecke_und_ohne_zieldatum_kein_absturz():
    hints = study_plan.deadline_hints({"deadline": None}, {"blocks": [], "total_minutes": 0,
                                                            "effective_daily_min": 60},
                                      exam_iso=None, today=TODAY)
    assert hints == []


# --------------------------------------------------------------------------- #
# Zeitschaetzung
# --------------------------------------------------------------------------- #
@pytest.fixture()
def fixed_factor(monkeypatch):
    monkeypatch.setattr(study_plan, "time_factor_info", lambda subject=None: {"factor": 1.5, "source": "default"})
    for k, v in (("PLAN_CHARS_PER_PAGE", 3000), ("PLAN_PAGES_PER_HOUR", 25.0),
                 ("PLAN_CHARS_PER_CONCEPT", 1000), ("PLAN_ITEMS_PER_HOUR", 10.0)):
        monkeypatch.setattr(study_plan.settings, k, v)


def test_time_breakdown_und_estimate_minutes_stimmen_ueberein(fixed_factor):
    b = study_plan.time_breakdown(6000)
    assert b["reading_min"] == pytest.approx(4.8) and b["practice_min"] == pytest.approx(36.0)
    assert b["factor"] == 1.5 and b["source"] == "default"
    assert study_plan.estimate_minutes(6000) == round((4.8 + 36.0) * 1.5) == 61
    assert study_plan.estimate_minutes(6000, content_multiplier=1.4) == round((4.8 + 36.0) * 1.5 * 1.4)
    assert study_plan.estimate_minutes(10) == 5                      # Untergrenze


def test_explain_time_estimate_nennt_annahmen_faktor_und_beispiel(fixed_factor):
    lines = study_plan.explain_time_estimate("LA", example_chars=6000)
    text = "\n".join(lines)
    assert "25 Seiten pro Stunde" in text and "3000 Zeichen" in text
    assert "1000 Zeichen" in text and "10 Konzepte pro Stunde" in text
    assert "1.50×" in text and "Standardwert" in text and "+40 %" in text
    assert "6000 Zeichen" in text and "5 Min" in text and "36 Min" in text and "**61 Min**" in text
    assert "Faustformel" in text
