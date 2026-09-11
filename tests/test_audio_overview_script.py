"""Skript-Generierung (``ragapp.audio_overview.generate_overview_script``):
Fehlerfälle und die Trunkierungs-Warnung.

Isoliert geladen (kein Vollimport von ``ragapp.audio_overview``, das über
``ragapp.study_plan`` schwere Abhängigkeiten wie chromadb zieht sowie beim
Import von coqui-tts/torch eine schwere, optionale Abhängigkeit ziehen würde,
die für reine Text-Logik-Tests nicht nötig ist) - alle externen Aufrufe (LLM,
Abschnitts-Ermittlung) werden gefaked, exakt wie bei den Mindmap-Tests
(siehe test_mindmap_generate.py)."""
import types

import pytest


def _fake_settings(**overrides):
    base = dict(
        PLAN_MAX_TOC_CHARS=10000, AUDIO_PROMPT_BUDGET_CHARS=9000,
        TOC_EXCERPT_MIN_CHARS=40, TOC_EXCERPT_MAX_CHARS=150,
        AUDIO_MAX_SCRIPT_CHARS=6000, LLM_MODEL_AUTHOR="", LLM_MODEL="fallback-model",
    )
    base.update(overrides)
    ns = types.SimpleNamespace(**base)
    ns.author_model = lambda: (ns.LLM_MODEL_AUTHOR or "").strip() or ns.LLM_MODEL
    return ns


class _FakeLLM:
    def __init__(self, *, result="", raise_exc=None, done_reason="stop", model="test-model"):
        self._result = result
        self._raise_exc = raise_exc
        self.last_done_reason = done_reason
        self.model = model

    def generate(self, prompt, system=None, temperature=None, think=None, num_predict=None):
        if self._raise_exc:
            raise self._raise_exc
        return self._result


def _fake_granular_sections_factory(n=5):
    def _fake(doc_ids):
        return [("doc.pdf", f"Abschnitt {i}", f"Inhalt von Abschnitt {i} " * 10) for i in range(n)]
    return _fake


def _identity_cap(granular, max_chars):
    return granular


@pytest.fixture
def generate_script_funcs(load_functions, ragapp_dir):
    def _make(*, llm, settings_obj=None, n_sections=5):
        settings = settings_obj or _fake_settings()
        toc_funcs = load_functions(
            ragapp_dir / "study_plan.py", ["_toc_with_excerpts"], {"settings": settings})
        return load_functions(
            ragapp_dir / "audio_overview.py",
            ["generate_overview_script", "_looks_truncated"],
            {
                "settings": settings,
                "get_llm": lambda model=None: llm,
                "_granular_sections": _fake_granular_sections_factory(n_sections),
                "_cap_granular_for_prompt": _identity_cap,
                "_toc_with_excerpts": toc_funcs["_toc_with_excerpts"],
                "AudioOverviewError": RuntimeError,
                "Optional": None,
            },
            const_names=["_SCRIPT_SYSTEM", "_SCRIPT_PROMPT",
                        "_SCRIPT_NUM_PREDICT", "_SCRIPT_NUM_PREDICT_RETRY"],
        )["generate_overview_script"]
    return _make


def test_generate_script_erfolgsfall_gibt_text_ohne_warnung(generate_script_funcs):
    llm = _FakeLLM(result="Fangen wir an mit dem ersten Thema. Es geht darum, dass ...")
    f = generate_script_funcs(llm=llm)
    script, warning = f(["doc1"], "DSA")
    assert warning is None
    assert script.startswith("Fangen wir an")


def test_generate_script_keine_abschnitte_wirft_error(generate_script_funcs):
    llm = _FakeLLM(result="irrelevant")
    f = generate_script_funcs(llm=llm, n_sections=0)
    with pytest.raises(RuntimeError, match="Keine indexierten Abschnitte"):
        f(["doc1"], "DSA")


def test_generate_script_llm_exception_wirft_error(generate_script_funcs):
    llm = _FakeLLM(raise_exc=ConnectionError("Ollama nicht erreichbar"))
    f = generate_script_funcs(llm=llm)
    with pytest.raises(RuntimeError, match="fehlgeschlagen"):
        f(["doc1"], "DSA")


def test_generate_script_leere_erste_antwort_versucht_retry_dann_fehler(generate_script_funcs):
    # Beide Versuche liefern leer -> ehrlicher Fehler statt stiller leerer Audio-Datei.
    llm = _FakeLLM(result="", done_reason="length")
    f = generate_script_funcs(llm=llm)
    with pytest.raises(RuntimeError, match="kein Skript erzeugt"):
        f(["doc1"], "DSA")


def test_generate_script_truncation_gibt_warnung(generate_script_funcs):
    llm = _FakeLLM(result="Ein Satz, der mitten drin abbricht und mit einem Doppelpunkt endet:",
                   done_reason="length")
    f = generate_script_funcs(llm=llm)
    script, warning = f(["doc1"], "DSA")
    assert script  # Text bleibt trotzdem nutzbar (kein Absturz)
    assert warning is not None
    assert "Token-Budget" in warning


def test_generate_script_normale_antwort_ohne_kuerzung_bleibt_ohne_warnung(generate_script_funcs):
    llm = _FakeLLM(result="Ein ganz normaler, vollständiger Satz zum Thema.", done_reason="stop")
    f = generate_script_funcs(llm=llm)
    script, warning = f(["doc1"], "DSA")
    assert warning is None
    assert script == "Ein ganz normaler, vollständiger Satz zum Thema."


def test_generate_script_kappt_hart_am_zeichen_deckel(generate_script_funcs):
    lang_text = ("Dies ist ein Satz. " * 500) + "Letzter Satz."
    llm = _FakeLLM(result=lang_text, done_reason="stop")
    settings_obj = _fake_settings(AUDIO_MAX_SCRIPT_CHARS=200)
    f = generate_script_funcs(llm=llm, settings_obj=settings_obj)
    script, warning = f(["doc1"], "DSA")
    assert len(script) <= 200
    assert script.endswith(".")


def test_generate_script_verwendet_autoren_modell_wenn_kein_modell_angegeben(
        generate_script_funcs):
    llm = _FakeLLM(result="Text.")
    settings_obj = _fake_settings(LLM_MODEL_AUTHOR="mein-autoren-modell")
    f = generate_script_funcs(llm=llm, settings_obj=settings_obj)
    script, warning = f(["doc1"], "DSA", model=None)
    assert warning is None
    assert script == "Text."
