"""Mindmap-Generierung (``ragapp.mindmap.generate_mindmap``): Fehlerfälle,
Fallback-Verhalten und die Trunkierungs-Warnung.

Regressionstest für einen real beobachteten Bug: bei einem Reasoning-Modell,
das trotz ``think=False`` intern weiterdenkt und dabei das komplette
Token-Budget verbraucht (``done_reason == 'length'``, leerer Antwort-Kanal),
fiel die Mindmap-Generierung STILL auf den 1:1-Fallback zurück, ohne dass die
Nutzerin/der Nutzer erfuhr, warum. Jetzt trägt der Fallback in diesem Fall
eine erklärende Warnung.

Isoliert geladen (kein Vollimport von ``ragapp.mindmap``, das über
``ragapp.study_plan`` schwere Abhängigkeiten wie chromadb zieht) - alle
externen Aufrufe (LLM, Abschnitts-Ermittlung) werden gefaked.
"""
import types

import pytest


def _fake_settings(**overrides):
    base = dict(
        PLAN_MAX_TOC_CHARS=10000, MINDMAP_PROMPT_BUDGET_CHARS=9000,
        MINDMAP_EXCERPT_MIN_CHARS=40, MINDMAP_EXCERPT_MAX_CHARS=150,
        MINDMAP_MAX_NODES=40, MINDMAP_MAX_TOPICS=8, MINDMAP_MAX_SUBTOPICS=6,
        MINDMAP_MAX_LINKS=8, LLM_MODEL_AUTHOR="", LLM_MODEL="fallback-model",
    )
    base.update(overrides)
    ns = types.SimpleNamespace(**base)
    ns.author_model = lambda: (ns.LLM_MODEL_AUTHOR or "").strip() or ns.LLM_MODEL
    return ns


class _FakeLLM:
    def __init__(self, *, result=None, raise_exc=None, done_reason="stop",
                completion_tokens=500, model="test-model"):
        self._result = result
        self._raise_exc = raise_exc
        self.last_done_reason = done_reason
        self.last_completion_tokens = completion_tokens
        self.model = model

    def generate_json(self, prompt, system=None, temperature=None):
        if self._raise_exc:
            raise self._raise_exc
        return self._result


def _fake_granular_sections_factory(n=5):
    def _fake(doc_ids):
        return [("doc.pdf", f"Seite {i}", f"Inhalt von Seite {i} " * 10) for i in range(n)]
    return _fake


def _identity_cap(granular, max_chars):
    return granular


@pytest.fixture
def generate_mindmap_funcs(load_functions, ragapp_dir):
    def _make(*, llm, settings_obj=None, n_sections=5):
        return load_functions(
            ragapp_dir / "mindmap.py",
            ["generate_mindmap", "_author_model", "_repair_mindmap", "_toc_with_excerpts"],
            {
                "settings": settings_obj or _fake_settings(),
                "get_llm": lambda model=None: llm,
                "_granular_sections": _fake_granular_sections_factory(n_sections),
                "_cap_granular_for_prompt": _identity_cap,
                "MindmapError": RuntimeError,
                "Optional": None,
            },
            const_names=["_MINDMAP_SYSTEM", "_MINDMAP_PROMPT"],
        )["generate_mindmap"]
    return _make


def test_generate_mindmap_erfolgsfall_gibt_repariertes_ergebnis_ohne_warnung(
        generate_mindmap_funcs):
    good_data = {"root": "Test", "nodes": [
        {"id": "n1", "title": "Thema A", "parent": None, "indices": [0, 1]}], "links": []}
    llm = _FakeLLM(result=good_data)
    f = generate_mindmap_funcs(llm=llm)
    graph, warning = f(["doc1"], "DSA")
    assert warning is None
    assert graph["nodes"][0]["title"] == "Thema A"


def test_generate_mindmap_keine_abschnitte_wirft_mindmap_error(generate_mindmap_funcs):
    llm = _FakeLLM(result={"root": "x", "nodes": [], "links": []})
    f = generate_mindmap_funcs(llm=llm, n_sections=0)
    with pytest.raises(RuntimeError):
        f(["doc1"], "DSA")


def test_generate_mindmap_llm_exception_wirft_mindmap_error(generate_mindmap_funcs):
    llm = _FakeLLM(raise_exc=ConnectionError("Ollama nicht erreichbar"))
    f = generate_mindmap_funcs(llm=llm)
    with pytest.raises(RuntimeError, match="fehlgeschlagen"):
        f(["doc1"], "DSA")


def test_generate_mindmap_truncation_faellt_zurueck_MIT_warnung(generate_mindmap_funcs):
    # Genau der real beobachtete Fall: generate_json() liefert None (Parsen
    # gescheitert) UND done_reason=='length' (Token-Budget aufgebraucht).
    llm = _FakeLLM(result=None, done_reason="length", completion_tokens=1024,
                   model="gpt-oss:20b")
    settings_obj = _fake_settings(LLM_MODEL_AUTHOR="gpt-oss:20b")
    f = generate_mindmap_funcs(llm=llm, settings_obj=settings_obj, n_sections=5)
    graph, warning = f(["doc1"], "DSA")
    # Fallback (1 Knoten je Abschnitt) greift trotzdem - nie ganz scheitern.
    assert len(graph["nodes"]) == 5
    assert all(not n["indices"] or n["indices"] == [i] for i, n in enumerate(graph["nodes"]))
    # Aber diesmal MIT erklärender Warnung statt stillem Fallback.
    assert warning is not None
    assert "gpt-oss:20b" in warning
    assert "1024" in warning


def test_generate_mindmap_andere_reparatur_fehlschlaege_bleiben_ohne_warnung(
        generate_mindmap_funcs):
    # generate_json() liefert etwas Geparstes, das aber KEIN brauchbarer
    # Mindmap-Graph ist (z. B. leere Knotenliste) - kein Trunkierungsfall,
    # also auch keine (irrefuehrende) Trunkierungs-Warnung.
    llm = _FakeLLM(result={"root": "x", "nodes": []}, done_reason="stop")
    f = generate_mindmap_funcs(llm=llm, n_sections=3)
    graph, warning = f(["doc1"], "DSA")
    assert len(graph["nodes"]) == 3
    assert warning is None


def test_generate_mindmap_verwendet_autoren_modell_wenn_kein_modell_angegeben(
        generate_mindmap_funcs):
    good_data = {"root": "Test", "nodes": [
        {"id": "n1", "title": "Thema A", "parent": None, "indices": [0]}], "links": []}
    llm = _FakeLLM(result=good_data)
    settings_obj = _fake_settings(LLM_MODEL_AUTHOR="mein-autoren-modell")
    f = generate_mindmap_funcs(llm=llm, settings_obj=settings_obj)
    graph, warning = f(["doc1"], "DSA", model=None)
    assert warning is None
    assert graph["nodes"][0]["title"] == "Thema A"
