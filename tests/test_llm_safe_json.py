"""Robuster JSON-Parser ``ragapp.llm._safe_json``.

Isoliert geladen: ``ragapp.llm`` importiert oben ``ollama`` - das soll die CI
NICHT brauchen. ``_safe_json`` selbst ist rein (nur ``json`` + ``re``).
"""
import json as _json
import re as _re

import pytest


@pytest.fixture
def safe_json(load_functions, ragapp_dir):
    funcs = load_functions(
        ragapp_dir / "llm.py",
        ["_safe_json", "_loads_lenient", "_fix_invalid_json_escapes"],
        {"json": _json, "re": _re}, const_names=["_JSON_VALID_ESCAPES"])
    return funcs["_safe_json"]


@pytest.fixture
def fix_invalid_escapes(load_functions, ragapp_dir):
    funcs = load_functions(
        ragapp_dir / "llm.py", ["_fix_invalid_json_escapes"],
        {"json": _json, "re": _re}, const_names=["_JSON_VALID_ESCAPES"])
    return funcs["_fix_invalid_json_escapes"]


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


# --------------------------------------------------------------------------- #
# LaTeX-Notation in KI-Antworten (\cap, \in, \leq, ...) - regulaeres JSON kennt
# diese Escapes nicht ("Invalid \escape"), obwohl der Rest der Antwort
# voellig brauchbar ist. Regressionstest fuer einen real beobachteten Bug:
# die Uebungsaufgaben-Generierung fuer "Analysis" scheiterte daran, dass eine
# inhaltlich einwandfreie KI-Antwort ein "$A \cap B$" im Aufgabentext enthielt.
# --------------------------------------------------------------------------- #
def test_latex_escape_in_string_wird_geheilt(safe_json):
    raw = r'{"problem_text": "Bestimme $A \cap B$ und $A \cup B$."}'
    assert safe_json(raw) == {"problem_text": "Bestimme $A \\cap B$ und $A \\cup B$."}


def test_latex_escape_in_codefence_wird_geheilt(safe_json):
    raw = '```json\n{"steps": [{"step_text": "Nutze \\\\in und \\\\leq hier"}]}\n```'
    # Hinweis: obiger raw-String enthaelt bereits GUELTIGE Escapes (\\\\ -> ein
    # Backslash) - der eigentliche Bug-Fall (rohe KI-Ausgabe mit einem
    # einzelnen Backslash vor einem Buchstaben) wird unten separat getestet.
    assert safe_json(raw) is not None


def test_echte_ki_antwort_mit_cap_cup_wird_geparst(safe_json):
    # 1:1 die reale, live beobachtete Antwort, an der die Generierung scheiterte.
    raw = ('```json\n{\n  "problem_text": "Gegeben sind die Mengen $A = [-5; 4)$ '
          'und $B = [0; 9]$. Bestimme die Schnittmenge $A \\cap B$ sowie die '
          'Vereinigungsmenge $A \\cup B$.",\n  "given": [],\n  "steps": '
          '[{"step_text": "Ergebnis: $A \\cap B = [0; 4)$."}],\n  '
          '"final_answer": "x",\n  "hints": []\n}\n```')
    data = safe_json(raw)
    assert data is not None
    assert r"\cap" in data["problem_text"]


def test_gueltige_escapes_bleiben_unveraendert(safe_json):
    raw = '{"a": "Zeile1\\nZeile2", "b": "Tab\\there", "c": "Pfad\\\\Datei", "d": "\\u00e4"}'
    assert safe_json(raw) == {"a": "Zeile1\nZeile2", "b": "Tab\there",
                              "c": "Pfad\\Datei", "d": "ä"}


def test_fix_invalid_json_escapes_verdoppelt_nur_ungueltige_backslashes(fix_invalid_escapes):
    assert fix_invalid_escapes(r"\cap") == r"\\cap"
    assert fix_invalid_escapes(r"\n") == r"\n"          # gueltig -> unveraendert
    assert fix_invalid_escapes(r"ä") == r"ä"  # gueltiges Unicode-Escape
    assert fix_invalid_escapes(r"\uZZZZ") == r"\\uZZZZ"  # kein echtes Hex -> ungueltig
