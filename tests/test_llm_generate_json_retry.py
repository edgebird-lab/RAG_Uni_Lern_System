"""LLM.generate_json: think=False-Standard + Trunkierungs-Sicherheitsnetz
(``ragapp.llm``).

Regressionstest für einen real beobachteten Bug: ein Reasoning-Modell (26B)
verbrauchte bei ``think="low"`` das komplette num_predict-Budget fürs
"Nachdenken", der Antwort-Kanal blieb leer (``done_reason='length'``) -
Ergebnis war eine Mindmap aus 53 bedeutungslosen "Seite N"-Knoten statt
echter Themen. Ein anderes Reasoning-Modell (gpt-oss:20b) ignoriert sogar
``think=False`` und denkt trotzdem, teils >8000 Tokens nicht-deterministisch -
dafür der Retry mit deutlich größerem Kontextfenster+Budget.

Echter Import (nicht isoliert): ``generate_json`` ist eine gebundene Methode
der ``LLM``-Klasse und lässt sich nicht sinnvoll herauslösen. Der Import von
``ragapp.llm`` zieht nur ``ollama`` zusätzlich (leichtgewichtiger HTTP-Client,
ohnehin Kernabhängigkeit der App) - der eigentliche Ollama-Client wird
gemockt, kein echter Server nötig.
"""
from unittest.mock import patch

from ragapp.llm import LLM, settings as llm_settings


def _resp(content="", thinking="", done_reason="stop", eval_count=10, prompt_eval_count=100):
    return {
        "message": {"content": content, "thinking": thinking},
        "done_reason": done_reason,
        "eval_count": eval_count,
        "prompt_eval_count": prompt_eval_count,
    }


def test_generate_json_erfolgsfall_ohne_retry_und_think_ist_standardmaessig_aus():
    llm = LLM(model="test-model")
    with patch.object(llm._client, "chat", return_value=_resp(content='{"a": 1}')) as m:
        data = llm.generate_json("prompt")
    assert data == {"a": 1}
    assert m.call_count == 1
    assert m.call_args.kwargs["think"] is False


def test_generate_json_retried_bei_trunkierung_und_erfolgreichem_zweiten_versuch():
    llm = LLM(model="test-model")
    responses = [
        _resp(content="", thinking="denk denk denk", done_reason="length", eval_count=1024),
        _resp(content='{"a": 2}', done_reason="stop", eval_count=500),
    ]
    with patch.object(llm._client, "chat", side_effect=responses) as m:
        data = llm.generate_json("prompt")
    assert data == {"a": 2}
    assert m.call_count == 2
    first_options = m.call_args_list[0].kwargs["options"]
    retry_options = m.call_args_list[1].kwargs["options"]
    assert retry_options["num_ctx"] > first_options["num_ctx"]
    assert retry_options["num_predict"] > first_options["num_predict"]


def test_generate_json_gibt_none_zurueck_wenn_auch_retry_trunkiert_wird():
    llm = LLM(model="test-model")
    with patch.object(llm._client, "chat", return_value=_resp(
            content="", thinking="denk denk", done_reason="length", eval_count=1024)) as m:
        data = llm.generate_json("prompt")
    assert data is None
    assert m.call_count == 2   # genau EIN Retry, dann aufgeben (kein Endlos-Loop)


def test_generate_json_kein_retry_wenn_parsing_ohne_trunkierung_fehlschlaegt():
    # done_reason='stop' (kein Abbruch), aber trotzdem kein gueltiges JSON ->
    # KEIN Retry (die Annahme "zu wenig Platz" trifft hier nicht zu, ein
    # Retry wuerde am eigentlichen Problem - falsches Format - nichts aendern).
    llm = LLM(model="test-model")
    with patch.object(llm._client, "chat", return_value=_resp(
            content="Das ist kein JSON.", done_reason="stop", eval_count=10)) as m:
        data = llm.generate_json("prompt")
    assert data is None
    assert m.call_count == 1


def test_generate_json_retry_num_ctx_gedeckelt_bei_32768():
    llm = LLM(model="test-model")
    with patch.object(llm_settings, "LLM_NUM_CTX", 20000):
        with patch.object(llm._client, "chat", return_value=_resp(
                content="", thinking="x", done_reason="length", eval_count=1024)) as m:
            llm.generate_json("prompt")
    retry_options = m.call_args_list[1].kwargs["options"]
    assert retry_options["num_ctx"] == 32768   # 20000*2=40000, gedeckelt auf 32768


def test_generate_json_aufrufer_kann_think_explizit_erzwingen():
    llm = LLM(model="test-model")
    with patch.object(llm._client, "chat", return_value=_resp(content='{"a": 1}')) as m:
        llm.generate_json("prompt", think="low")
    assert m.call_args.kwargs["think"] == "low"


def test_generate_json_thinking_fallback_rettet_leeren_content_kanal():
    # Kein Trunkierungsfall (done_reason='stop'), aber Content leer und das
    # JSON steckt stattdessen im Denk-Kanal - _thinking_fallback=True (Default
    # von generate_json) soll das trotzdem herausparsen.
    llm = LLM(model="test-model")
    with patch.object(llm._client, "chat", return_value=_resp(
            content="", thinking='{"a": 3}', done_reason="stop", eval_count=10)):
        data = llm.generate_json("prompt")
    assert data == {"a": 3}
