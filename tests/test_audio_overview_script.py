"""Skript-Generierung (``ragapp.audio_overview.generate_overview_script``):
läuft ABSCHNITTSWEISE (ein LLM-Aufruf je Abschnitt, siehe Moduldoc) statt als
ein einzelner budget-gedeckelter Aufruf - Regressionstest für einen real
gemeldeten Bug: die alte Version erzeugte IMMER ein ähnlich kurzes Skript
(~6000 Zeichen Zielvorgabe), unabhängig von der Dokumentgröße ("egal ob 3
oder 20 Seiten, immer ~6 Minuten Audio").

Isoliert geladen (kein Vollimport von ``ragapp.audio_overview``, das über
``ragapp.study_plan`` schwere Abhängigkeiten wie chromadb zieht sowie
coqui-tts/torch, was für reine Text-Logik-Tests nicht nötig ist)."""
import types

import pytest


def _fake_settings(**overrides):
    base = dict(AUDIO_MAX_SCRIPT_CHARS=40000, LLM_MODEL_AUTHOR="", LLM_MODEL="fallback-model")
    base.update(overrides)
    ns = types.SimpleNamespace(**base)
    ns.author_model = lambda: (ns.LLM_MODEL_AUTHOR or "").strip() or ns.LLM_MODEL
    return ns


class _FakeLLM:
    """Antwortet der Reihe nach mit den Eintraegen aus ``responses`` (ein
    Eintrag je ``generate()``-Aufruf, unabhaengig davon, ob es der Erst- oder
    ein Retry-Versuch ist - so lassen sich Trunkierung/Retry gezielt fuer
    EINEN bestimmten Abschnitt simulieren, ohne alle anderen zu beeinflussen).
    ``responses`` kann auch Exceptions enthalten (werden geworfen statt
    zurueckgegeben) - simuliert einen einzelnen fehlschlagenden Abschnitt."""
    def __init__(self, responses, *, done_reasons=None):
        self._responses = list(responses)
        self._done_reasons = list(done_reasons) if done_reasons else None
        self._call_idx = 0
        self.last_done_reason = "stop"
        self.model = "test-model"

    def generate(self, prompt, system=None, temperature=None, think=None, num_predict=None):
        i = self._call_idx
        self._call_idx += 1
        if self._done_reasons is not None and i < len(self._done_reasons):
            self.last_done_reason = self._done_reasons[i]
        r = self._responses[i] if i < len(self._responses) else ""
        if isinstance(r, Exception):
            raise r
        return r


def _fake_granular_sections_factory(sections):
    """``sections``: Liste (label, title, body) - direkt durchgereicht."""
    def _fake(doc_ids):
        return list(sections)
    return _fake


@pytest.fixture
def generate_script_funcs(load_functions, ragapp_dir):
    def _make(*, llm, settings_obj=None, sections=None):
        settings = settings_obj or _fake_settings()
        sections = sections if sections is not None else [
            ("doc.pdf", "Abschnitt 1", "Inhalt von Abschnitt 1 " * 20),
            ("doc.pdf", "Abschnitt 2", "Inhalt von Abschnitt 2 " * 20),
        ]
        return load_functions(
            ragapp_dir / "audio_overview.py",
            ["generate_overview_script", "_narrate_section", "_looks_truncated"],
            {
                "settings": settings,
                "get_llm": lambda model=None: llm,
                "_granular_sections": _fake_granular_sections_factory(sections),
                "AudioOverviewError": RuntimeError,
                "Optional": None,
            },
            const_names=["_SECTION_SYSTEM", "_SECTION_PROMPT", "_SECTION_CHAR_BUDGET",
                        "_MIN_SECTION_CHARS", "_SECTION_NUM_PREDICT",
                        "_SECTION_NUM_PREDICT_RETRY", "_NO_CONTENT_MARKER"],
        )["generate_overview_script"]
    return _make


def test_skript_waechst_mit_anzahl_der_abschnitte(generate_script_funcs):
    # Der eigentliche Regressionsfall: mehr Abschnitte -> laengeres Skript,
    # nicht immer dieselbe (Ziel-)Laenge unabhaengig von der Dokumentgroesse.
    kurzer_text = "Text für Abschnitt. " * 30
    langes_dok = [("doc.pdf", f"Abschnitt {i}", "Quelltext " * 20) for i in range(10)]

    llm_kurz = _FakeLLM([kurzer_text, kurzer_text])
    f = generate_script_funcs(llm=llm_kurz, sections=[
        ("doc.pdf", "Abschnitt 1", "Quelltext " * 20),
        ("doc.pdf", "Abschnitt 2", "Quelltext " * 20),
    ])
    script_kurz, _ = f(["doc1"], "DSA")

    llm_lang = _FakeLLM([kurzer_text] * 10)
    f2 = generate_script_funcs(llm=llm_lang, sections=langes_dok)
    script_lang, _ = f2(["doc1"], "DSA")

    assert len(script_lang) > len(script_kurz) * 3


def test_generate_script_erfolgsfall_haengt_abschnitte_zusammen(generate_script_funcs):
    llm = _FakeLLM(["Erster Abschnitt Text.", "Zweiter Abschnitt Text."])
    f = generate_script_funcs(llm=llm)
    script, warning = f(["doc1"], "DSA")
    assert warning is None
    assert "Erster Abschnitt Text." in script
    assert "Zweiter Abschnitt Text." in script


def test_generate_script_ruft_on_progress_je_abschnitt_auf_auch_bei_uebersprungenen(
        generate_script_funcs):
    llm = _FakeLLM(["Normaler Abschnitt mit genug Inhalt.", "Guter zweiter Abschnitt hier."])
    calls = []
    f = generate_script_funcs(llm=llm, sections=[
        ("doc.pdf", "Zu kurz", "kurz"),   # unter _MIN_SECTION_CHARS -> uebersprungen
        ("doc.pdf", "Normal 1", "Ausreichend langer Quelltext fuer Abschnitt eins. " * 5),
        ("doc.pdf", "Normal 2", "Ausreichend langer Quelltext fuer Abschnitt zwei. " * 5),
    ])
    script, _ = f(["doc1"], "DSA",
                  on_progress=lambda done, total, label: calls.append((done, total, label)))
    assert calls == [(1, 3, "Zu kurz"), (2, 3, "Normal 1"), (3, 3, "Normal 2")]
    assert "Normaler Abschnitt" in script


def test_generate_script_keine_abschnitte_wirft_error(generate_script_funcs):
    llm = _FakeLLM([])
    f = generate_script_funcs(llm=llm, sections=[])
    with pytest.raises(RuntimeError, match="Keine indexierten Abschnitte"):
        f(["doc1"], "DSA")


def test_generate_script_zu_kurze_abschnitte_werden_uebersprungen(generate_script_funcs):
    llm = _FakeLLM(["Normaler Abschnitt mit genug Inhalt zum Erklären hier."])
    f = generate_script_funcs(llm=llm, sections=[
        ("doc.pdf", "Zu kurz", "kurz"),  # unter _MIN_SECTION_CHARS -> uebersprungen, kein LLM-Aufruf
        ("doc.pdf", "Normal", "Ausreichend langer Quelltext für einen Abschnitt. " * 5),
    ])
    script, warning = f(["doc1"], "DSA")
    assert warning is None
    assert "Normaler Abschnitt" in script


def test_generate_script_abschnitt_ohne_erklaerbaren_inhalt_wird_uebersprungen(
        generate_script_funcs):
    llm = _FakeLLM(["(kein erklärbarer Inhalt)", "Guter Abschnitt mit echtem Inhalt."])
    f = generate_script_funcs(llm=llm)
    script, warning = f(["doc1"], "DSA")
    assert warning is None
    assert "Guter Abschnitt" in script
    assert "kein erklärbarer" not in script.lower()


def test_generate_script_alle_abschnitte_ohne_inhalt_wirft_error(generate_script_funcs):
    llm = _FakeLLM(["(kein erklärbarer Inhalt)", "(kein erklärbarer Inhalt)"])
    f = generate_script_funcs(llm=llm)
    with pytest.raises(RuntimeError, match="kein Skript erzeugen"):
        f(["doc1"], "DSA")


def test_generate_script_ein_fehlschlagender_abschnitt_kippt_nicht_die_anderen(
        generate_script_funcs):
    llm = _FakeLLM([ConnectionError("Ollama weg"), "Zweiter Abschnitt klappt trotzdem."])
    f = generate_script_funcs(llm=llm)
    script, warning = f(["doc1"], "DSA")
    assert "Zweiter Abschnitt klappt trotzdem." in script


def test_generate_script_truncation_in_einem_abschnitt_gibt_warnung(generate_script_funcs):
    # Erster Versuch abgeschnitten (done_reason='length') -> Retry, der Retry
    # ist AUCH abgeschnitten -> Warnung, aber das Skript bleibt nutzbar.
    llm = _FakeLLM(
        ["Satz, der mitten drin abbricht und mit einem Doppelpunkt endet:",
         "Satz, der auch im Retry mitten drin abbricht:"],
        done_reasons=["length", "length"])
    f = generate_script_funcs(llm=llm, sections=[("doc.pdf", "Abschnitt 1", "Quelltext " * 20)])
    script, warning = f(["doc1"], "DSA")
    assert script  # bleibt trotzdem nutzbar, kein Absturz
    assert warning is not None
    assert "Token-Budget" in warning


def test_generate_script_hard_cap_kappt_und_warnt(generate_script_funcs):
    grosser_abschnitt_text = "Ein ganzer Satz mit Inhalt. " * 50   # ~1400 Zeichen/Antwort
    sections = [("doc.pdf", f"Abschnitt {i}", "Quelltext " * 20) for i in range(50)]
    llm = _FakeLLM([grosser_abschnitt_text] * 50)
    settings_obj = _fake_settings(AUDIO_MAX_SCRIPT_CHARS=2000)  # winziger Deckel fuers Testen
    f = generate_script_funcs(llm=llm, settings_obj=settings_obj, sections=sections)
    script, warning = f(["doc1"], "DSA")
    assert len(script) < 50 * len(grosser_abschnitt_text)  # wurde tatsaechlich gekappt
    assert warning is not None
    assert "gekappt" in warning


def test_generate_script_verwendet_autoren_modell_wenn_kein_modell_angegeben(
        generate_script_funcs):
    llm = _FakeLLM(["Text.", "Text2."])
    settings_obj = _fake_settings(LLM_MODEL_AUTHOR="mein-autoren-modell")
    f = generate_script_funcs(llm=llm, settings_obj=settings_obj)
    script, warning = f(["doc1"], "DSA", model=None)
    assert warning is None
    assert "Text." in script
