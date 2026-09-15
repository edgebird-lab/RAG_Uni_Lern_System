"""Lueckentext-Pruefung ``ragapp.grading.check_cloze`` - deterministisch, ohne LLM.

Isoliert geladen (mit dem Helfer ``_norm``), weil ``ragapp.grading`` oben
``ragapp.llm`` (-> ollama) importiert. ``check_cloze``/``_norm`` selbst brauchen
nur ``re``.

Semantik (STRENG): es zaehlt nur eine EXAKTE Uebereinstimmung der Normalform
(Gross/Klein, Umlaute ae/oe/ue/ss, Satzzeichen egal). Teil-/Oberbegriffe werden
bewusst NICHT als korrekt gewertet.
"""
import re as _re

import pytest


@pytest.fixture
def check_cloze(load_functions, ragapp_dir):
    funcs = load_functions(ragapp_dir / "grading.py",
                           ["_norm", "check_cloze"], {"re": _re})
    return funcs["check_cloze"]


def test_exakt_korrekt(check_cloze):
    assert check_cloze("Deckungsbeitrag", ["Deckungsbeitrag"]) is True


def test_gross_klein_und_satzzeichen_egal(check_cloze):
    assert check_cloze("  deckungsbeitrag!  ", ["Deckungsbeitrag"]) is True


def test_umlaut_faltung(check_cloze):
    # 'Größe' == 'Groesse' nach Normalform (ö->oe, ß->ss).
    assert check_cloze("Größe", ["Groesse"]) is True


def test_vager_oberbegriff_wird_abgelehnt(check_cloze):
    # Teilbegriff "Deckung" ist NICHT die exakte Loesung -> abgelehnt.
    assert check_cloze("Deckung", ["Deckungsbeitrag"]) is False


def test_ueberbegriff_superstring_wird_abgelehnt(check_cloze):
    # Auch ein laengerer, umschliessender Begriff zaehlt nicht (keine Teilstring-Logik).
    assert check_cloze("Deckungsbeitragsrechnung", ["Deckungsbeitrag"]) is False


def test_voellig_falscher_begriff(check_cloze):
    assert check_cloze("Zahl", ["Deckungsbeitrag"]) is False


def test_mehrere_luecken_alle_richtig(check_cloze):
    assert check_cloze("variabel; fix", ["variabel", "fix"]) is True


def test_mehrere_luecken_eine_falsch(check_cloze):
    assert check_cloze("variabel; sonstiges", ["variabel", "fix"]) is False


def test_kurzer_exakter_treffer(check_cloze):
    # Exakte Gleichheit der Normalform (Ziffern gehoeren zu \\w).
    assert check_cloze("h2o", ["H2O"]) is True


def test_leere_loesungsliste_ist_false(check_cloze):
    assert check_cloze("irgendwas", []) is False


def test_bzw_als_trenner(check_cloze):
    assert check_cloze("variabel bzw. fix", ["fix"]) is True


def test_make_cloze_ueberspringt_latex_tokens(load_functions, ragapp_dir):
    import re as _re
    fns = load_functions(
        ragapp_dir / "grading.py",
        ["make_cloze"],
        {"re": _re},
        const_names=["_CLOZE_STOP"],
    )
    make_cloze = fns["make_cloze"]
    only_tex = make_cloze(r"Die Ableitung ist $\frac{d}{dx} x^2$ also 2x hier.")
    # Entweder kein Cloze, oder die Lücke ist nicht \frac
    if only_tex is not None:
        blanked, sols = only_tex
        assert all(not s.startswith("\\") and "$" not in s for s in sols)
    defi = make_cloze(
        "Der Deckungsbeitrag ist Erlös minus variable Kosten in der Rechnung.")
    assert defi is not None
    assert "Deckungsbeitrag" in defi[1] or "variable" in defi[1] or "Kosten" in defi[1]
