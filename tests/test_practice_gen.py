"""Übungsaufgaben-Generator (``ragapp.practice_gen``): Auto-Erkennung Rechenaufgabe
vs. Anwendungsszenario (``_pick_kind``), Quelltext-Auswahl (``_pick_source_text``)
und JSON-Reparatur der KI-Antwort (``_repair_problem``).

Rein rechnerisch, ohne LLM/Embedding/Chroma - isoliert geladen, weil ein
Vollimport von ``ragapp.practice_gen`` ueber ``ragapp.retrieval.vectorstore``
schwere Abhaengigkeiten (chromadb) zieht. ``_TECHNICAL_MARKER_RE`` wird ebenso
isoliert aus ``study_plan.py`` mitgeladen (keine Duplikation, kein Vollimport).
"""
import re
import types

import pytest


@pytest.fixture(scope="module")
def technical_marker_re(load_functions, ragapp_dir):
    consts = load_functions(ragapp_dir / "study_plan.py", [], {"re": re},
                            const_names=["_TECHNICAL_MARKER_RE"])
    return consts["_TECHNICAL_MARKER_RE"]


def _fake_settings(**overrides):
    base = dict(PRACTICE_NUMERIC_DENSITY_THRESHOLD=1.0, PRACTICE_MAX_HINTS=3)
    base.update(overrides)
    return types.SimpleNamespace(**base)


@pytest.fixture
def gen_funcs(load_functions, ragapp_dir, technical_marker_re):
    def _make(**settings_overrides):
        return load_functions(
            ragapp_dir / "practice_gen.py",
            ["_pick_kind", "_pick_source_text", "_repair_problem"],
            {"settings": _fake_settings(**settings_overrides),
             "_TECHNICAL_MARKER_RE": technical_marker_re},
        )
    return _make


# ---------------------------------------------------------------------------
# _pick_kind
# ---------------------------------------------------------------------------

def test_pick_kind_erkennt_zahlenlastigen_text_als_numeric(gen_funcs):
    f = gen_funcs()["_pick_kind"]
    text = "Gegeben sei f(x) = 3x^2 + 5x - 2, x1 = 0, x2 = 1.5, x3 = -2.3, Summe = 12.7"
    assert f(text) == "numeric"


def test_pick_kind_erkennt_fliesstext_als_scenario(gen_funcs):
    f = gen_funcs()["_pick_kind"]
    text = ("Die Kommunikation zwischen Teams ist ein zentraler Erfolgsfaktor "
            "in agilen Projekten und erfordert klare Absprachen sowie "
            "regelmäßige Rücksprache zwischen den beteiligten Personen.")
    assert f(text) == "scenario"


def test_pick_kind_leerer_text_ist_scenario(gen_funcs):
    f = gen_funcs()["_pick_kind"]
    assert f("") == "scenario"
    assert f(None) == "scenario"


def test_pick_kind_schwelle_ist_konfigurierbar(gen_funcs):
    text = "a=1, b=2, c=3."
    f_high = gen_funcs(PRACTICE_NUMERIC_DENSITY_THRESHOLD=90.0)["_pick_kind"]
    assert f_high(text) == "scenario"
    f_low = gen_funcs(PRACTICE_NUMERIC_DENSITY_THRESHOLD=0.01)["_pick_kind"]
    assert f_low(text) == "numeric"


# ---------------------------------------------------------------------------
# _pick_source_text
# ---------------------------------------------------------------------------

def test_pick_source_text_leer_bei_keinen_abschnitten(gen_funcs):
    f = gen_funcs()["_pick_source_text"]
    assert f([], None, 1000) == ("", [])


def test_pick_source_text_bevorzugt_zum_thema_passende_abschnitte(gen_funcs):
    f = gen_funcs()["_pick_source_text"]
    sections = [
        ("doc.pdf", "Einleitung", "Text A"),
        ("doc.pdf", "Stacks und Queues", "Text B"),
        ("doc.pdf", "Zusammenfassung", "Text C"),
    ]
    source, titles = f(sections, "Stacks", 1000)
    assert titles[0] == "Stacks und Queues"
    assert "Text B" in source


def test_pick_source_text_ohne_thema_behaelt_dokumentreihenfolge(gen_funcs):
    f = gen_funcs()["_pick_source_text"]
    sections = [
        ("doc.pdf", "Kapitel 1", "AAA"),
        ("doc.pdf", "Kapitel 2", "BBB"),
    ]
    source, titles = f(sections, None, 1000)
    assert titles == ["Kapitel 1", "Kapitel 2"]
    assert source == "AAA\n\nBBB"


def test_pick_source_text_haelt_zeichen_budget_ein_ohne_abschnitt_zu_zerschneiden(gen_funcs):
    f = gen_funcs()["_pick_source_text"]
    sections = [
        ("doc.pdf", "A", "x" * 100),
        ("doc.pdf", "B", "y" * 100),
        ("doc.pdf", "C", "z" * 100),
    ]
    source, titles = f(sections, None, 150)
    # nur ganze Abschnitte, nie mitten im Abschnitt abgeschnitten
    assert source in ("x" * 100, "y" * 100, "z" * 100, "x" * 100 + "\n\n" + "y" * 100)
    assert len(source) <= 150 or "\n\n" not in source
    for t in titles:
        assert t in ("A", "B", "C")


# ---------------------------------------------------------------------------
# _repair_problem
# ---------------------------------------------------------------------------

def _valid_data(**overrides):
    base = dict(
        problem_text="Berechne die Fläche eines Rechtecks mit a=4, b=5.",
        given=[{"label": "a", "value": "4"}, {"label": "b", "value": "5"}],
        steps=[{"step_text": "Fläche = a * b"}, {"step_text": "Fläche = 20"}],
        final_answer="20 Flächeneinheiten",
        hints=["Denk an die Formel", "A mal B", "Es ist 20"],
    )
    base.update(overrides)
    return base


def test_repair_problem_gueltige_daten_werden_uebernommen(gen_funcs):
    f = gen_funcs()["_repair_problem"]
    out = f(_valid_data())
    assert out["problem_text"] == "Berechne die Fläche eines Rechtecks mit a=4, b=5."
    assert out["given"] == [{"label": "a", "value": "4"}, {"label": "b", "value": "5"}]
    assert out["steps"] == [{"step_text": "Fläche = a * b"}, {"step_text": "Fläche = 20"}]
    assert out["final_answer"] == "20 Flächeneinheiten"
    assert len(out["hints"]) == 3


def test_repair_problem_verwirft_bei_fehlender_aufgabenstellung(gen_funcs):
    f = gen_funcs()["_repair_problem"]
    assert f(_valid_data(problem_text="")) is None
    assert f(_valid_data(problem_text="   ")) is None


def test_repair_problem_verwirft_bei_fehlenden_loesungsschritten(gen_funcs):
    f = gen_funcs()["_repair_problem"]
    assert f(_valid_data(steps=[])) is None
    assert f(_valid_data(steps=[{"step_text": ""}, {"step_text": "   "}])) is None


def test_repair_problem_verwirft_nicht_dict_eingaben(gen_funcs):
    f = gen_funcs()["_repair_problem"]
    assert f(None) is None
    assert f([1, 2, 3]) is None
    assert f("kein json") is None


def test_repair_problem_akzeptiert_steps_als_reine_strings(gen_funcs):
    f = gen_funcs()["_repair_problem"]
    out = f(_valid_data(steps=["Schritt 1", "Schritt 2"]))
    assert out["steps"] == [{"step_text": "Schritt 1"}, {"step_text": "Schritt 2"}]


def test_repair_problem_verwirft_leere_given_eintraege(gen_funcs):
    f = gen_funcs()["_repair_problem"]
    out = f(_valid_data(given=[{"label": "", "value": ""}, {"label": "a", "value": ""},
                               {"label": "", "value": "5"}]))
    assert out["given"] == [{"label": "a", "value": ""}, {"label": "", "value": "5"}]


def test_repair_problem_kappt_hints_auf_practice_max_hints(gen_funcs):
    f = gen_funcs(PRACTICE_MAX_HINTS=2)["_repair_problem"]
    out = f(_valid_data(hints=["h1", "h2", "h3", "h4"]))
    assert out["hints"] == ["h1", "h2"]


def test_repair_problem_final_answer_optional(gen_funcs):
    f = gen_funcs()["_repair_problem"]
    out = f(_valid_data(final_answer=None))
    assert out["final_answer"] == ""
