"""Robuster JSON-Parser ``ragapp.llm._safe_json``.

Isoliert geladen: ``ragapp.llm`` importiert oben ``ollama`` - das soll die CI
NICHT brauchen. ``_safe_json`` selbst ist rein (nur ``json`` + ``re``).
"""
import json as _json
import re as _re

import pytest


@pytest.fixture
def safe_json(load_functions, ragapp_dir):
    funcs = load_functions(ragapp_dir / "llm.py", ["_safe_json"],
                           {"json": _json, "re": _re})
    return funcs["_safe_json"]


def test_none_und_leer_ergeben_none(safe_json):
    assert safe_json(None) is None
    assert safe_json("") is None
    assert safe_json("   \n\t ") is None


def test_reines_objekt(safe_json):
    assert safe_json('{"a": 1, "b": [2, 3]}') == {"a": 1, "b": [2, 3]}


def test_reines_array_mit_prosa_drumherum(safe_json):
    assert safe_json("Ergebnis: [1, 2, 3].") == [1, 2, 3]


def test_codefence_mit_json_tag(safe_json):
    assert safe_json('```json\n{"x": 5}\n```') == {"x": 5}


def test_codefence_ohne_tag_liefert_array(safe_json):
    assert safe_json("```\n[10, 20]\n```") == [10, 20]


def test_objekt_mit_prosa_danach(safe_json):
    assert safe_json('{"ok": true}\n\nErklaerung folgt spaeter.') == {"ok": True}


def test_einzelne_klammern_im_reasoning_sprengen_nicht(safe_json):
    # Verstreute '}' bei depth 0 muessen ignoriert werden (Kern des balancierten Scans).
    raw = 'Denke nach }}} und dann {"score": 90, "note": "ok"}'
    assert safe_json(raw) == {"score": 90, "note": "ok"}


def test_nimmt_erstes_balanciertes_objekt(safe_json):
    assert safe_json('Zuerst {"x": 1} danach {"y": 2}') == {"x": 1}


def test_geschweifte_klammern_im_string_bleiben_erhalten(safe_json):
    assert safe_json('{"text": "nutze { und } im Satz"}') == {"text": "nutze { und } im Satz"}


def test_muell_ohne_klammern_ergibt_none(safe_json):
    assert safe_json("kein json hier, nur text ohne klammern") is None


def test_unbalanciertes_objekt_ergibt_none(safe_json):
    assert safe_json('{"broken": ') is None
