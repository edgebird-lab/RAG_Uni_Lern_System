"""Inhaltsverzeichnis-mit-Ausschnitten (``ragapp.study_plan._toc_with_excerpts``):
gemeinsam genutzt von der Lernplan-Gliederung UND der Mindmap.

Anders als eine reine Titel-Liste bekommt jede Zeile zusätzlich einen kurzen
Inhalts-Ausschnitt - notwendig, weil generische Titel (z. B. "Seite N" bei
Foliensätzen ohne erkennbare Kapitelstruktur) dem Modell sonst kein Signal
geben, um sinnvolle Themennamen zu vergeben oder überhaupt zu wissen, worum es
in einem Abschnitt geht (siehe study_plan.py-Modul-Kommentar bei
PLAN_PROMPT_BUDGET_CHARS).

Rein rechnerisch, isoliert geladen, weil ein Vollimport von
``ragapp.study_plan`` über ``ragapp.retrieval.vectorstore`` schwere
Abhängigkeiten (chromadb) zieht.
"""
import types

import pytest


def _fake_settings(**overrides):
    base = dict(TOC_EXCERPT_MIN_CHARS=40, TOC_EXCERPT_MAX_CHARS=150)
    base.update(overrides)
    return types.SimpleNamespace(**base)


@pytest.fixture
def toc_with_excerpts(load_functions, ragapp_dir):
    def _make(**settings_overrides):
        funcs = load_functions(
            ragapp_dir / "study_plan.py", ["_toc_with_excerpts"],
            {"settings": _fake_settings(**settings_overrides)},
        )
        return funcs["_toc_with_excerpts"]
    return _make


def test_toc_with_excerpts_enthaelt_titel_zeichenzahl_und_ausschnitt(toc_with_excerpts):
    f = toc_with_excerpts()
    capped = [("doc.pdf", "Seite 7", "Verfügbarkeit bedeutet, dass Systeme erreichbar sind.")]
    out = f(capped, 9000)
    assert out.startswith("0. Seite 7")
    assert "(~53 Zeichen)" in out
    assert "Verfügbarkeit bedeutet" in out


def test_toc_with_excerpts_glaettet_mehrfache_leerzeichen_und_zeilenumbrueche(toc_with_excerpts):
    f = toc_with_excerpts()
    capped = [("doc.pdf", "X", "Zeile 1\n\n   Zeile 2  mit   vielen Leerzeichen")]
    out = f(capped, 9000)
    assert "\n\n" not in out.split(":", 1)[1]
    assert "  " not in out.split('"', 1)[1]


def test_toc_with_excerpts_ausschnitt_schrumpft_bei_vielen_abschnitten(toc_with_excerpts):
    f = toc_with_excerpts()
    long_body = "x" * 1000
    capped_few = [("doc.pdf", f"S{i}", long_body) for i in range(3)]
    capped_many = [("doc.pdf", f"S{i}", long_body) for i in range(300)]
    out_few = f(capped_few, 9000)
    out_many = f(capped_many, 9000)
    # bei wenigen Abschnitten volle MAX-Laenge, bei vielen Abschnitten kuerzer
    first_excerpt_few = out_few.split('"')[1]
    first_excerpt_many = out_many.split('"')[1]
    assert len(first_excerpt_few) > len(first_excerpt_many)


def test_toc_with_excerpts_haelt_untergrenze_ein(toc_with_excerpts):
    f = toc_with_excerpts(TOC_EXCERPT_MIN_CHARS=40)
    long_body = "x" * 1000
    capped = [("doc.pdf", f"S{i}", long_body) for i in range(1000)]
    out = f(capped, 9000)
    first_excerpt = out.split('"')[1]
    assert len(first_excerpt) >= 40 - 1  # -1 wegen moeglichem .strip() am Rand


def test_toc_with_excerpts_eine_zeile_je_abschnitt(toc_with_excerpts):
    f = toc_with_excerpts()
    capped = [("doc.pdf", f"S{i}", "Inhalt " * 20) for i in range(5)]
    out = f(capped, 9000)
    assert len(out.splitlines()) == 5
    for i in range(5):
        assert out.splitlines()[i].startswith(f"{i}. S{i}")
