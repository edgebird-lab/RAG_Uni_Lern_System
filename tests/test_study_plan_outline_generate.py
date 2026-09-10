"""Lernplan-Gliederung (``ragapp.study_plan.generate_outline``): Fehlerfälle,
Fallback-Verhalten und die Trunkierungs-Warnung.

Regressionstest für dieselbe Ursache, die zuerst bei der Mindmap behoben
wurde (siehe ``tests/test_mindmap_generate.py``): ein Reasoning-Modell kann
sein Token-Budget komplett fürs interne "Nachdenken" verbrauchen, bevor der
Antwort-Kanal etwas enthält (``done_reason == 'length'``, ``generate_json()``
liefert ``None``) - der 1:1-Fallback greift dann OHNE dass die Nutzerin/der
Nutzer erfährt, warum. ``generate_outline`` trägt diesen Fall jetzt als
erklärende Warnung statt eines stillen Fallbacks.

Isoliert geladen (kein Vollimport von ``ragapp.study_plan``, das über
``ragapp.retrieval.vectorstore`` schwere Abhängigkeiten wie chromadb zieht) -
alle externen Aufrufe (LLM, Abschnitts-Ermittlung, Zeitschätzung, DB) werden
gefaked; ``_repair_outline``/``_toc_with_excerpts``/``_author_model`` werden
echt geladen (rein rechnerisch, keine DB-Abhängigkeit).
"""
import types

import pytest


def _fake_settings(**overrides):
    base = dict(
        PLAN_MAX_TOC_CHARS=10000, PLAN_PROMPT_BUDGET_CHARS=9000,
        TOC_EXCERPT_MIN_CHARS=40, TOC_EXCERPT_MAX_CHARS=150,
        PLAN_MAX_OUTLINE_SECTIONS=15, LLM_MODEL_AUTHOR="", LLM_MODEL="fallback-model",
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


class _FakeManifest:
    def log_eta_sample(self, *a, **kw):
        pass


def _fake_granular_sections_factory(n=5):
    def _fake(doc_ids):
        return [("doc.pdf", f"Seite {i}", f"Inhalt von Seite {i} " * 10) for i in range(n)]
    return _fake


def _identity_cap(granular, max_chars):
    return granular


@pytest.fixture
def generate_outline_funcs(load_functions, ragapp_dir):
    def _make(*, llm, settings_obj=None, n_sections=5):
        settings = settings_obj or _fake_settings()
        return load_functions(
            ragapp_dir / "study_plan.py",
            ["generate_outline", "_author_model", "_repair_outline", "_toc_with_excerpts"],
            {
                "settings": settings,
                "get_llm": lambda model=None: llm,
                "manifest": _FakeManifest(),
                "_granular_sections": _fake_granular_sections_factory(n_sections),
                "_cap_granular_for_prompt": _identity_cap,
                "_content_multiplier": lambda text: 1.0,
                "estimate_minutes": lambda chars, subject=None, content_multiplier=1.0: 10,
                "OutlineError": RuntimeError,
                "Optional": None,
                "time": __import__("time"),
            },
            const_names=["_OUTLINE_SYSTEM", "_OUTLINE_PROMPT"],
        )["generate_outline"]
    return _make


def test_generate_outline_erfolgsfall_gibt_repariertes_ergebnis_ohne_warnung(
        generate_outline_funcs):
    good_data = [{"title": "Thema A", "summary": "worum es geht", "indices": [0, 1]}]
    llm = _FakeLLM(result=good_data)
    f = generate_outline_funcs(llm=llm)
    sections, warning = f(["doc1"], "DSA")
    assert warning is None
    assert sections[0]["title"] == "Thema A"


def test_generate_outline_keine_abschnitte_wirft_outline_error(generate_outline_funcs):
    llm = _FakeLLM(result=[])
    f = generate_outline_funcs(llm=llm, n_sections=0)
    with pytest.raises(RuntimeError):
        f(["doc1"], "DSA")


def test_generate_outline_llm_exception_wirft_outline_error(generate_outline_funcs):
    llm = _FakeLLM(raise_exc=ConnectionError("Ollama nicht erreichbar"))
    f = generate_outline_funcs(llm=llm)
    with pytest.raises(RuntimeError, match="fehlgeschlagen"):
        f(["doc1"], "DSA")


def test_generate_outline_truncation_faellt_zurueck_MIT_warnung(generate_outline_funcs):
    # Genau der real beobachtete Fall: generate_json() liefert None (Parsen
    # gescheitert) UND done_reason=='length' (Token-Budget aufgebraucht).
    llm = _FakeLLM(result=None, done_reason="length", completion_tokens=1024,
                   model="gpt-oss:20b")
    settings_obj = _fake_settings(LLM_MODEL_AUTHOR="gpt-oss:20b")
    f = generate_outline_funcs(llm=llm, settings_obj=settings_obj, n_sections=5)
    sections, warning = f(["doc1"], "DSA")
    # Fallback (1 Abschnitt je Original-Abschnitt) greift trotzdem.
    assert len(sections) == 5
    assert warning is not None
    assert "gpt-oss:20b" in warning
    assert "1024" in warning


def test_generate_outline_andere_reparatur_fehlschlaege_bleiben_ohne_warnung(
        generate_outline_funcs):
    # generate_json() liefert etwas Geparstes, das aber KEIN brauchbares
    # Gliederungs-Ergebnis ist (leere Liste) - kein Trunkierungsfall, also
    # auch keine (irrefuehrende) Trunkierungs-Warnung.
    llm = _FakeLLM(result=[], done_reason="stop")
    f = generate_outline_funcs(llm=llm, n_sections=3)
    sections, warning = f(["doc1"], "DSA")
    assert len(sections) == 3
    assert warning is None


def test_generate_outline_verwendet_autoren_modell_wenn_kein_modell_angegeben(
        generate_outline_funcs):
    good_data = [{"title": "Thema A", "summary": "", "indices": [0]}]
    llm = _FakeLLM(result=good_data)
    settings_obj = _fake_settings(LLM_MODEL_AUTHOR="mein-autoren-modell")
    f = generate_outline_funcs(llm=llm, settings_obj=settings_obj)
    sections, warning = f(["doc1"], "DSA", model=None)
    assert warning is None
    assert sections[0]["title"] == "Thema A"
