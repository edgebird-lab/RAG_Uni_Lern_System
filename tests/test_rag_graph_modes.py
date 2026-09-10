"""Chat-Modus-Logik (``ragapp.graph.rag_graph``): _chat_mode/_relaxed_mode sowie die
budget-bewusste Verlaufs-Kompaktierung (_history_turns_raw/_history_char_budget/
_summarize_history/_history_for_chat/_log_token_sample) fuer Tutor- und Sokratischen
Dialog.

Rein rechnerisch, ohne echtes LLM/Embedding/Chroma/LangGraph - ``manifest``/``get_llm``
werden gefaked. Isoliert geladen, weil ein Vollimport von ``ragapp.graph.rag_graph``
ueber ``langgraph``/chromadb schwere Abhaengigkeiten zieht.
"""
import logging
import types
from typing import Optional

import pytest

from ragapp.config import settings as S


@pytest.fixture
def mode_funcs(load_functions, ragapp_dir):
    return load_functions(
        ragapp_dir / "graph" / "rag_graph.py",
        ["_chat_mode", "_relaxed_mode"],
        {"settings": S, "_CHAT_MODES": ("strict", "tutor", "sokratisch"),
         "Optional": Optional},
    )


def test_chat_mode_erkennt_alle_drei_werte(mode_funcs):
    f = mode_funcs["_chat_mode"]
    assert f({"chat_mode": "strict"}) == "strict"
    assert f({"chat_mode": "tutor"}) == "tutor"
    assert f({"chat_mode": "sokratisch"}) == "sokratisch"


def test_chat_mode_faellt_bei_fehlendem_ungueltigem_wert_auf_strict_zurueck(mode_funcs):
    f = mode_funcs["_chat_mode"]
    assert f({}) == "strict"
    assert f({"chat_mode": None}) == "strict"
    assert f({"chat_mode": "irgendwas"}) == "strict"


def test_relaxed_mode_gilt_fuer_tutor_und_sokratisch_nicht_fuer_strict(mode_funcs):
    f = mode_funcs["_relaxed_mode"]
    assert f({"chat_mode": "tutor"}) is True
    assert f({"chat_mode": "sokratisch"}) is True
    assert f({"chat_mode": "strict"}) is False
    assert f({}) is False


# ---------------------------------------------------------------------------
# Verlaufs-Kompaktierung: _history_turns_raw / _history_char_budget /
# _summarize_history / _history_for_chat / _log_token_sample
# ---------------------------------------------------------------------------

def _fake_settings(**overrides):
    base = dict(
        LLM_NUM_CTX=8192,
        LLM_NUM_PREDICT=700,
        CHAT_SYSTEM_PROMPT_RESERVE_CHARS=2500,
        MAX_CONTEXT_CHARS=7000,
        CHAT_QUESTION_RESERVE_CHARS=500,
        CHAT_HISTORY_BUDGET_SAFETY=0.75,
        DEFAULT_CHARS_PER_TOKEN=3.2,
        LLM_MODEL="test-model",
        LLM_MODEL_FAST="test-model-fast",
        CHAT_HISTORY_KEEP_RECENT_TURNS=2,
    )
    base.update(overrides)
    return types.SimpleNamespace(**base)


class _FakeManifest:
    def __init__(self, ratio=None, raise_on_log=False):
        self._ratio = ratio
        self._raise_on_log = raise_on_log
        self.samples: list[tuple] = []

    def chars_per_token(self, model, min_samples=5, limit=40):
        return self._ratio

    def log_token_sample(self, model, chars, tokens):
        if self._raise_on_log:
            raise RuntimeError("DB weg")
        self.samples.append((model, chars, tokens))


class _FakeLLM:
    def __init__(self, summary="Zusammenfassung.", fail=False,
                 last_prompt_tokens=None, model="fake-model"):
        self._summary = summary
        self._fail = fail
        self.calls = 0
        self.last_prompt_tokens = last_prompt_tokens
        self.model = model

    def generate(self, prompt, system=None):
        self.calls += 1
        if self._fail:
            raise RuntimeError("LLM nicht erreichbar")
        return self._summary


@pytest.fixture
def history_funcs(load_functions, ragapp_dir):
    def _make(*, ratio=None, summary="Zusammenfassung.", fail_llm=False,
               settings_obj=None, raise_on_log=False):
        fake_manifest = _FakeManifest(ratio=ratio, raise_on_log=raise_on_log)
        fake_llm = _FakeLLM(summary=summary, fail=fail_llm)
        funcs = load_functions(
            ragapp_dir / "graph" / "rag_graph.py",
            ["_history_turns_raw", "_history_char_budget", "_summarize_history",
             "_history_for_chat", "_log_token_sample"],
            {"settings": settings_obj or _fake_settings(),
             "manifest": fake_manifest,
             "get_llm": lambda *a, **kw: fake_llm,
             "COMPACT_SYSTEM": "SYS", "COMPACT_PROMPT": "{verlauf}",
             "_log": logging.getLogger("test_rag_graph_modes"),
             "Optional": Optional},
        )
        return funcs, fake_manifest, fake_llm
    return _make


def test_history_turns_raw_filtert_rollen_und_leere_beitraege(history_funcs):
    funcs, _, _ = history_funcs()
    history = [
        {"role": "user", "content": "Frage 1"},
        {"role": "assistant", "content": "Antwort 1", "meta": {"x": 1}},
        {"role": "system", "content": "sollte rausfallen"},
        {"role": "user", "content": "   "},  # leer nach strip -> raus
        {"role": "user", "content": "Frage 2"},
    ]
    out = funcs["_history_turns_raw"](history)
    assert out == [
        {"role": "user", "content": "Frage 1"},
        {"role": "assistant", "content": "Antwort 1"},
        {"role": "user", "content": "Frage 2"},
    ]


def test_history_turns_raw_leer_bei_none_oder_leerer_liste(history_funcs):
    funcs, _, _ = history_funcs()
    assert funcs["_history_turns_raw"](None) == []
    assert funcs["_history_turns_raw"]([]) == []


def test_history_char_budget_verwendet_kalibrierten_ratio(history_funcs):
    funcs, _, _ = history_funcs(ratio=4.0)
    # total=8192*4.0=32768; reserved=700*4.0+2500+7000+500=12800;
    # (32768-12800)*0.75 = 14976.0
    assert funcs["_history_char_budget"]() == 14976


def test_history_char_budget_faellt_auf_default_ratio_zurueck_ohne_messwerte(history_funcs):
    funcs, _, _ = history_funcs(ratio=None)
    # ratio faellt auf DEFAULT_CHARS_PER_TOKEN=3.2 zurueck:
    # total=8192*3.2=26214.4; reserved=700*3.2+2500+7000+500=12240;
    # (26214.4-12240)*0.75 = 10480.8 -> int() = 10480
    assert funcs["_history_char_budget"]() == 10480


def test_history_char_budget_hat_untergrenze_500(history_funcs):
    tiny = _fake_settings(LLM_NUM_CTX=100)
    funcs, _, _ = history_funcs(ratio=3.2, settings_obj=tiny)
    assert funcs["_history_char_budget"]() == 500


def test_history_for_chat_leer_bei_none_oder_leerer_liste(history_funcs):
    funcs, _, fake_llm = history_funcs()
    assert funcs["_history_for_chat"](None) == []
    assert funcs["_history_for_chat"]([]) == []
    assert fake_llm.calls == 0


def test_history_for_chat_bleibt_roh_wenn_im_budget(history_funcs):
    # grosszuegiges Budget (ratio=None -> 10480), Historie winzig -> keine Kompaktierung.
    funcs, _, fake_llm = history_funcs(ratio=None)
    history = [
        {"role": "user", "content": "Kurze Frage"},
        {"role": "assistant", "content": "Kurze Antwort"},
    ]
    out = funcs["_history_for_chat"](history)
    assert out == [
        {"role": "user", "content": "Kurze Frage"},
        {"role": "assistant", "content": "Kurze Antwort"},
    ]
    assert fake_llm.calls == 0


def test_history_for_chat_zu_wenig_turns_zum_aufteilen_bleibt_roh(history_funcs):
    # Budget winzig (500), aber nur genau keep_n=2 Turns vorhanden -> nichts
    # "Aelteres" zum Zusammenfassen, roh durchreichen trotz Ueberschreitung.
    tiny = _fake_settings(LLM_NUM_CTX=100, CHAT_HISTORY_KEEP_RECENT_TURNS=2)
    funcs, _, fake_llm = history_funcs(ratio=3.2, settings_obj=tiny)
    history = [
        {"role": "user", "content": "x" * 1000},
        {"role": "assistant", "content": "y" * 1000},
    ]
    out = funcs["_history_for_chat"](history)
    assert out == [
        {"role": "user", "content": "x" * 1000},
        {"role": "assistant", "content": "y" * 1000},
    ]
    assert fake_llm.calls == 0


def test_history_for_chat_komprimiert_aeltere_turns_bei_budget_ueberschreitung(history_funcs):
    tiny = _fake_settings(LLM_NUM_CTX=100, CHAT_HISTORY_KEEP_RECENT_TURNS=2)
    funcs, _, fake_llm = history_funcs(
        ratio=3.2, settings_obj=tiny, summary="Kurzfassung des Verlaufs.")
    history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"Turn {i}" * 50}
               for i in range(5)]
    out = funcs["_history_for_chat"](history)
    assert fake_llm.calls == 1
    # letzte 2 rohe Turns bleiben unveraendert erhalten, davor EIN Kontext-Turn.
    assert len(out) == 3
    assert out[1:] == [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"Turn {i}" * 50}
        for i in (3, 4)
    ]
    assert out[0]["role"] == "user"
    assert "Kurzfassung des Verlaufs." in out[0]["content"]
    assert out[0]["content"].startswith("[Kontext:")


def test_history_for_chat_faellt_bei_fehlgeschlagener_zusammenfassung_auf_juengste_turns_zurueck(
        history_funcs):
    tiny = _fake_settings(LLM_NUM_CTX=100, CHAT_HISTORY_KEEP_RECENT_TURNS=2)
    funcs, _, fake_llm = history_funcs(ratio=3.2, settings_obj=tiny, fail_llm=True)
    history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"Turn {i}" * 50}
               for i in range(5)]
    out = funcs["_history_for_chat"](history)
    assert fake_llm.calls == 1
    assert out == [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"Turn {i}" * 50}
        for i in (3, 4)
    ]


def test_log_token_sample_speichert_zeichen_und_tokenzahl(history_funcs):
    funcs, fake_manifest, _ = history_funcs()
    llm_obj = types.SimpleNamespace(last_prompt_tokens=42, model="m1")
    messages = [{"role": "system", "content": "abc"}, {"role": "user", "content": "defgh"}]
    funcs["_log_token_sample"](llm_obj, messages)
    assert fake_manifest.samples == [("m1", 8, 42)]


def test_log_token_sample_ignoriert_fehlende_tokenzahl(history_funcs):
    funcs, fake_manifest, _ = history_funcs()
    llm_obj = types.SimpleNamespace(last_prompt_tokens=None, model="m1")
    funcs["_log_token_sample"](llm_obj, [{"role": "user", "content": "abc"}])
    assert fake_manifest.samples == []


def test_log_token_sample_schluckt_fehler_beim_speichern(history_funcs):
    funcs, _, _ = history_funcs(raise_on_log=True)
    llm_obj = types.SimpleNamespace(last_prompt_tokens=42, model="m1")
    # darf NICHT werfen - best effort, darf den Antwortpfad nie stoeren.
    funcs["_log_token_sample"](llm_obj, [{"role": "user", "content": "abc"}])


# ---------------------------------------------------------------------------
# Sokratischer Dialog: erzwungene Aufloesung statt endlosem Rueckfragen-Loop
# (_looks_like_giving_up / _is_open_question / _consecutive_open_questions /
# _sokratisch_force_resolve). Regressionstest fuer einen real beobachteten
# Dialog, in dem eine fast identische Rueckfrage 4x in Folge gestellt wurde,
# sogar nach explizitem "Ich weiß es nicht".
# ---------------------------------------------------------------------------

@pytest.fixture
def sokratisch_funcs(load_functions, ragapp_dir):
    def _make(resolve_after_questions=3):
        settings_obj = types.SimpleNamespace(
            SOKRATISCH_RESOLVE_AFTER_QUESTIONS=resolve_after_questions)
        return load_functions(
            ragapp_dir / "graph" / "rag_graph.py",
            ["_looks_like_giving_up", "_is_open_question",
             "_consecutive_open_questions", "_sokratisch_force_resolve"],
            {"settings": settings_obj, "Optional": Optional,
             "re": __import__("re")},
            const_names=["_GIVE_UP_MARKERS", "_TRAILING_SOURCE_TAGS_RE"],
        )
    return _make


def test_looks_like_giving_up_erkennt_typische_aufgeben_phrasen(sokratisch_funcs):
    f = sokratisch_funcs()["_looks_like_giving_up"]
    assert f("Ich weiß es nicht")
    assert f("ich weiss es nicht")
    assert f("Sag mir einfach die Antwort")
    assert f("Ich komme nicht weiter")
    assert not f("Ressourcen, Prozesse, Daten und Nutzer")
    assert not f("Kannst du mir noch andere Fragen stellen?")
    assert not f("")


def test_is_open_question_erkennt_fragezeichen_auch_vor_quellenangaben(sokratisch_funcs):
    f = sokratisch_funcs()["_is_open_question"]
    assert f("Welche Schutzziele werden genannt? [Quelle 6]")
    assert f("Welche Punkte ergänzen das? [Quelle 1, 2, 4]")
    assert f("Was denkst du dazu?")
    assert not f("Die Antwort ist X, Y und Z laut [Quelle 1].")
    assert not f("")
    assert not f(None)


def _turn(role, content):
    return {"role": role, "content": content}


def test_consecutive_open_questions_zaehlt_regressionsdialog_korrekt(sokratisch_funcs):
    f = sokratisch_funcs()["_consecutive_open_questions"]
    # Nachgestellter, real gemeldeter Dialog: 4 fast identische Rueckfragen in
    # Folge zum selben Thema (Schutzziele/Bezugsobjekte), ohne Aufloesung.
    history = [
        _turn("user", "Wie funktioniert IT Sicherheit"),
        _turn("assistant", "Welche Schutzziele der IT-Sicherheit werden in der "
              "Zusammenfassung genannt? [Quelle 6]"),
        _turn("user", "Ich denke mal Ressourcen, Prozesse, Daten und Nutzer"),
        _turn("assistant", "Welche vier Elemente nennt deine Zusammenfassung als "
              "Bezugsobjekte? [Quelle 1]"),
        _turn("user", "Ressourcen, Prozesse, Daten und Nutzer"),
        _turn("assistant", "Welche Schutzziele gelten für diese vier "
              "Bezugsobjekte? [Quelle 1]"),
        _turn("user", "Ressourcen, Prozesse, Daten und Nutzer"),
        _turn("assistant", "Welche Schutzziele gelten für die vier Bezugsobjekte "
              "Ressourcen, Prozesse, Daten und Nutzer? [Quelle 1]"),
    ]
    assert f(history) == 4
    assert f(history[:4]) == 2
    assert f(None) == 0
    assert f([]) == 0


def test_consecutive_open_questions_bricht_kette_bei_aufloesung(sokratisch_funcs):
    f = sokratisch_funcs()["_consecutive_open_questions"]
    history = [
        _turn("user", "x"),
        _turn("assistant", "Frage 1?"),
        _turn("user", "y"),
        _turn("assistant", "Die Antwort ist X laut [Quelle 1]."),
        _turn("user", "z"),
        _turn("assistant", "Frage 2?"),
    ]
    assert f(history) == 1  # nur die juengste Frage zaehlt, Aufloesung bricht die Kette


def test_force_resolve_bei_expliziter_aufgeben_phrase(sokratisch_funcs):
    f = sokratisch_funcs()["_sokratisch_force_resolve"]
    history = [_turn("user", "x"), _turn("assistant", "Frage 1?")]
    assert f("Ich weiß es nicht", history) is True


def test_force_resolve_unterhalb_der_schwelle_bleibt_aus(sokratisch_funcs):
    f = sokratisch_funcs(resolve_after_questions=3)["_sokratisch_force_resolve"]
    history = [
        _turn("user", "x"), _turn("assistant", "Frage 1?"),
        _turn("user", "y"), _turn("assistant", "Frage 2?"),
    ]
    assert f("Verfügbarkeit", history) is False


def test_force_resolve_bei_erreichen_der_schwelle_auch_ohne_aufgeben_phrase(sokratisch_funcs):
    f = sokratisch_funcs(resolve_after_questions=3)["_sokratisch_force_resolve"]
    history = [
        _turn("user", "x"), _turn("assistant", "Frage 1?"),
        _turn("user", "y"), _turn("assistant", "Frage 2?"),
        _turn("user", "z"), _turn("assistant", "Frage 3?"),
    ]
    assert f("Verfügbarkeit", history) is True


def test_force_resolve_schwelle_ist_konfigurierbar(sokratisch_funcs):
    f = sokratisch_funcs(resolve_after_questions=1)["_sokratisch_force_resolve"]
    history = [_turn("user", "x"), _turn("assistant", "Frage 1?")]
    assert f("Verfügbarkeit", history) is True
