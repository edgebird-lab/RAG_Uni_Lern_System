"""VRAM-Schutzschicht: vor einer KI-Aufgabe Restmodelle entladen und bei zu
wenig freiem Grafikspeicher NICHT laden; nach der Aufgabe immer entladen.

Ohne echten Ollama-/GPU-Aufruf – ``vram_preflight`` und ``release_llm`` werden
gefakt, getestet wird die Orchestrierung in ``require_vram`` / ``llm_task``."""
from __future__ import annotations

import pytest

from ragapp import llm


def test_vram_low_message_nennt_freie_und_benoetigte_gb():
    msg = llm.vram_low_message({"free_gb": 3.2, "need_gb": 17.0, "model": "test-llm"})
    assert "3.2" in msg and "17" in msg and "test-llm" in msg


def test_require_vram_wirft_wenn_preflight_low_ist(monkeypatch):
    released = []
    monkeypatch.setattr(llm, "_model_resident", lambda model=None: False)
    monkeypatch.setattr(llm, "release_llm", lambda: released.append(1) or 0)
    monkeypatch.setattr(llm, "vram_preflight", lambda model=None: {
        "status": "low", "free_gb": 2.0, "need_gb": 18.0, "model": "grosses-modell"})
    with pytest.raises(llm.VramLowError) as ei:
        llm.require_vram("grosses-modell")
    assert released == [1]
    assert "2.0" in str(ei.value) and "18" in str(ei.value)


def test_require_vram_ok_wenn_genug_frei(monkeypatch):
    monkeypatch.setattr(llm, "_model_resident", lambda model=None: False)
    monkeypatch.setattr(llm, "release_llm", lambda: 0)
    monkeypatch.setattr(llm, "vram_preflight", lambda model=None: {
        "status": "ok", "free_gb": 20.0, "need_gb": 8.0, "model": "x"})
    pf = llm.require_vram("x")
    assert pf["status"] == "ok"


def test_require_vram_entlaedt_nicht_wenn_zielmodell_schon_resident(monkeypatch):
    released: list[int] = []
    monkeypatch.setattr(llm, "_model_resident", lambda model=None: True)
    monkeypatch.setattr(llm, "release_llm", lambda: released.append(1) or 0)
    monkeypatch.setattr(llm, "vram_preflight", lambda model=None: {
        "status": "ok", "resident": True, "model": "x"})
    pf = llm.require_vram("x")
    assert released == []
    assert pf["status"] == "ok"


def test_llm_task_entlaedt_auch_bei_fehler(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(llm, "require_vram", lambda model=None: calls.append("req") or {})
    monkeypatch.setattr(llm, "release_llm", lambda: calls.append("rel") or 0)
    with pytest.raises(RuntimeError):
        with llm.llm_task("x"):
            raise RuntimeError("boom")
    assert calls == ["req", "rel"]


def test_llm_task_entlaedt_nach_erfolg(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(llm, "require_vram", lambda model=None: calls.append("req") or {})
    monkeypatch.setattr(llm, "release_llm", lambda: calls.append("rel") or 0)
    with llm.llm_task("x"):
        calls.append("work")
    assert calls == ["req", "work", "rel"]


def test_llm_task_verschachtelt_entlaedt_nur_aussen(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(llm, "require_vram", lambda model=None: calls.append("req") or {})
    monkeypatch.setattr(llm, "release_llm", lambda: calls.append("rel") or 0)
    with llm.llm_task("x"):
        calls.append("outer")
        with llm.llm_task("x"):
            calls.append("inner")
        calls.append("after-inner")
    assert calls == ["req", "outer", "inner", "after-inner", "rel"]


def test_diagnose_error_reicht_vram_low_unverändert_durch():
    err = llm.VramLowError("nur 2 GB frei")
    assert llm.diagnose_error(err) == "nur 2 GB frei"
