"""Chat-Modus-Logik (``ragapp.graph.rag_graph``): _chat_mode/_relaxed_mode/
_history_messages fuer den Sokratischen Dialog.

Rein rechnerisch, ohne LLM/Embedding/Chroma/LangGraph. Isoliert geladen, weil
ein Vollimport von ``ragapp.graph.rag_graph`` ueber ``langgraph``/chromadb
schwere Abhaengigkeiten zieht.
"""
import pytest

from ragapp.config import settings as S


@pytest.fixture
def mode_funcs(load_functions, ragapp_dir):
    return load_functions(
        ragapp_dir / "graph" / "rag_graph.py",
        ["_chat_mode", "_relaxed_mode", "_history_messages"],
        {"settings": S, "_CHAT_MODES": ("strict", "tutor", "sokratisch"),
         "Optional": __import__("typing").Optional},
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


def test_history_messages_filtert_rollen_und_leere_beitraege(mode_funcs):
    f = mode_funcs["_history_messages"]
    history = [
        {"role": "user", "content": "Frage 1"},
        {"role": "assistant", "content": "Antwort 1", "meta": {"x": 1}},
        {"role": "system", "content": "sollte rausfallen"},
        {"role": "user", "content": "   "},  # leer nach strip -> raus
        {"role": "user", "content": "Frage 2"},
    ]
    out = f(history)
    assert out == [
        {"role": "user", "content": "Frage 1"},
        {"role": "assistant", "content": "Antwort 1"},
        {"role": "user", "content": "Frage 2"},
    ]


def test_history_messages_leer_bei_none_oder_leerer_liste(mode_funcs):
    f = mode_funcs["_history_messages"]
    assert f(None) == []
    assert f([]) == []


def test_history_messages_begrenzt_auf_die_letzten_n_turns(mode_funcs):
    f = mode_funcs["_history_messages"]
    history = [{"role": "user", "content": f"Turn {i}"} for i in range(20)]
    _orig = S.SOKRATISCH_MAX_HISTORY_TURNS
    try:
        S.SOKRATISCH_MAX_HISTORY_TURNS = 3
        out = f(history)
        assert len(out) == 3
        assert out[-1]["content"] == "Turn 19"
        assert out[0]["content"] == "Turn 17"
    finally:
        S.SOKRATISCH_MAX_HISTORY_TURNS = _orig
