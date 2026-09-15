"""TTS bleibt nach einer Vertonung geladen (Hörproben), Idle/LLM entladen es."""
from __future__ import annotations

import types

from ragapp import llm


def test_maybe_unload_idle_entlaedt_nach_timeout(load_functions, ragapp_dir):
    fake_time = types.SimpleNamespace(monotonic=lambda: 1000.0)
    ns = load_functions(
        ragapp_dir / "audio_overview.py",
        ["maybe_unload_idle_tts", "unload_tts_model", "tts_is_loaded"],
        {
            "time": fake_time,
            "settings": types.SimpleNamespace(AUDIO_TTS_KEEP_ALIVE_MINUTES=1),
            "_tts_singleton": object(),
            "_tts_last_used": 0.0,
        },
    )
    assert ns["tts_is_loaded"]() is True
    assert ns["maybe_unload_idle_tts"]() is True
    assert ns["tts_is_loaded"]() is False


def test_maybe_unload_idle_behaelt_frisches_modell(load_functions, ragapp_dir):
    fake_time = types.SimpleNamespace(monotonic=lambda: 30.0)
    ns = load_functions(
        ragapp_dir / "audio_overview.py",
        ["maybe_unload_idle_tts", "tts_is_loaded"],
        {
            "time": fake_time,
            "settings": types.SimpleNamespace(AUDIO_TTS_KEEP_ALIVE_MINUTES=10),
            "_tts_singleton": object(),
            "_tts_last_used": 0.0,
        },
    )
    assert ns["maybe_unload_idle_tts"]() is False
    assert ns["tts_is_loaded"]() is True


def test_maybe_unload_idle_bei_keep_alive_null_nicht(load_functions, ragapp_dir):
    ns = load_functions(
        ragapp_dir / "audio_overview.py",
        ["maybe_unload_idle_tts", "tts_is_loaded"],
        {
            "time": types.SimpleNamespace(monotonic=lambda: 10_000.0),
            "settings": types.SimpleNamespace(AUDIO_TTS_KEEP_ALIVE_MINUTES=0),
            "_tts_singleton": object(),
            "_tts_last_used": 0.0,
        },
    )
    assert ns["maybe_unload_idle_tts"]() is False
    assert ns["tts_is_loaded"]() is True


def test_llm_task_entlaedt_tts_vor_dem_llm(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(llm, "require_vram", lambda model=None: None)
    monkeypatch.setattr(llm, "release_llm", lambda: None)
    monkeypatch.setattr(llm, "_unload_tts_for_llm", lambda: calls.append("tts"))
    with llm.llm_task("x"):
        pass
    assert calls == ["tts"]


def test_audio_seite_hat_tts_entladen_button():
    from pathlib import Path
    src = Path("ragapp/ui/pages/15_🎧_Audio-Overview.py").read_text(encoding="utf-8")
    assert "Sprachmodell entladen" in src
    assert "tts_is_loaded" in src
    talk = Path("ragapp/ui/pages/17_🎤_Vortrag.py").read_text(encoding="utf-8")
    assert "Sprachmodell entladen" in talk
