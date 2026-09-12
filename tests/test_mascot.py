"""Tests fuer ragapp.ui._mascot (reines SVG/HTML, keine Streamlit-Abhaengigkeit)."""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from ragapp.ui._mascot import mascot_svg, pose_for, home_mood, POSES, _MOUTHS, _PROPS


def _inner_svg(html: str) -> str:
    start = html.index("<svg")
    end = html.index("</svg>") + len("</svg>")
    return html[start:end]


@pytest.mark.parametrize("pose", list(_MOUTHS.keys()))
@pytest.mark.parametrize("animation", ["float", "wave", "run", "shake"])
@pytest.mark.parametrize("prop", list(_PROPS.keys()))
def test_mascot_svg_ist_fuer_jede_kombination_gueltiges_xml(pose, animation, prop):
    html = mascot_svg("#FF8FA3", pose=pose, animation=animation, prop=prop)
    ET.fromstring(_inner_svg(html))


def test_mascot_svg_enthaelt_gewaehlte_animationsklasse():
    html = mascot_svg("#FF8FA3", animation="wave")
    assert "rag-mascot-wave" in html


def test_mascot_svg_extra_class_wird_uebernommen():
    html = mascot_svg("#FF8FA3", extra_class="rag-mascot-corner")
    assert "rag-mascot-corner" in html


def test_pose_for_liefert_tuple_fuer_jede_registrierte_seite():
    for key in POSES:
        pose, animation, prop = pose_for(key)
        assert pose in _MOUTHS
        assert animation in ("float", "wave", "run", "shake")
        assert prop is None or prop in _PROPS


def test_pose_for_unbekannte_seite_faellt_auf_idle_zurueck():
    assert pose_for("irgendwas_neues_unbekanntes") == ("idle", "float", None)


def test_sleepy_pose_haelt_beide_augen_statisch_halb_geschlossen():
    html = mascot_svg("#FF8FA3", pose="sleepy")
    assert "ragm-sleepy" in html
    assert "ragm-wink-loop" not in html


def test_idle_und_cheer_posen_zwinkern_nur_links_nicht_rechts():
    for pose in ("idle", "cheer"):
        html = mascot_svg("#FF8FA3", pose=pose)
        assert 'class="ragm-eye-l ragm-wink-loop"' in html
        assert 'class="ragm-eye-r ragm-blink"' in html


def test_home_mood_feiert_bei_neuer_errungenschaft_vor_allem_anderen():
    assert home_mood({"streak_at_risk": True, "leeches": 20}, celebrate=True) == \
        ("cheer", "wave", "star")


def test_home_mood_ist_besorgt_bei_reissendem_streak():
    assert home_mood({"streak_at_risk": True, "leeches": 0}) == ("worried", "shake", None)


def test_home_mood_ist_besorgt_bei_vielen_problemkarten():
    assert home_mood({"streak_at_risk": False, "leeches": 5}) == ("worried", "shake", None)


def test_home_mood_ignoriert_wenige_problemkarten():
    assert home_mood({"streak_at_risk": False, "leeches": 4, "due_cards": 0}) == \
        ("idle", "float", None)


def test_home_mood_faellige_karten_sind_fokussiert():
    assert home_mood({"due_cards": 3, "leeches": 0}) == ("focused", "float", "book")


def test_home_mood_harvest_braucht_birne():
    assert home_mood({"due_cards": 0}, needs_harvest=True) == ("focused", "float", "bulb")


def test_home_mood_ohne_snapshot_ist_neutral_froehlich():
    assert home_mood(None) == ("cheer", "wave", None)


def test_home_mood_line_nennt_faellige_karten():
    from ragapp.ui._mascot import home_mood_line
    icon, text = home_mood_line({"due_cards": 3})
    assert icon == "🎴"
    assert "3" in text


def test_mascot_svg_prop_hat_ragm_prop_klasse():
    html = mascot_svg("#FF8FA3", prop="book")
    assert 'class="ragm-prop"' in html
    assert "ragm-body" in html
