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
    monkeypatch.setattr(llm, "_VRAM_SETTLE_SECONDS", 0)
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


def test_require_vram_wartet_kurz_auf_verzoegert_freigegebenen_speicher(monkeypatch):
    """Zwei Aufgaben direkt nacheinander: Das gerade entladene Modell haelt den VRAM noch
    einen Moment - die zweite Messung sah faelschlich "nur 3.8 GB frei"."""
    monkeypatch.setattr(llm, "_VRAM_SETTLE_SECONDS", 5.0)
    monkeypatch.setattr(llm, "_model_resident", lambda model=None: False)
    monkeypatch.setattr(llm, "release_llm", lambda: 0)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    answers = iter([{"status": "low", "free_gb": 3.8, "need_gb": 8.4, "model": "x"},
                    {"status": "low", "free_gb": 3.8, "need_gb": 8.4, "model": "x"},
                    {"status": "ok", "free_gb": 20.0, "need_gb": 8.4, "model": "x"}])
    calls = []
    monkeypatch.setattr(llm, "vram_preflight", lambda model=None: calls.append(1) or next(answers))
    assert llm.require_vram("x")["status"] == "ok"
    assert len(calls) == 3


def test_require_vram_meldet_nach_der_wartezeit_trotzdem_wenn_wirklich_belegt(monkeypatch):
    monkeypatch.setattr(llm, "_VRAM_SETTLE_SECONDS", 0.02)
    monkeypatch.setattr(llm, "_model_resident", lambda model=None: False)
    monkeypatch.setattr(llm, "release_llm", lambda: 0)
    real_sleep = llm.time.sleep          # llm.time IS das time-Modul: vor dem Patchen merken
    monkeypatch.setattr(llm.time, "sleep", lambda s: real_sleep(0.01))
    monkeypatch.setattr(llm, "vram_preflight", lambda model=None: {
        "status": "low", "free_gb": 2.0, "need_gb": 18.0, "model": "x"})
    with pytest.raises(llm.VramLowError):
        llm.require_vram("x")


# --------------------------------------------------------------------------- #
# Mehrere Threads: Hintergrundauftrag (Lernplan -> Karten) neben dem Chat
# --------------------------------------------------------------------------- #
@pytest.fixture()
def fresh_counter(monkeypatch):
    monkeypatch.setattr(llm, "_active_tasks", 0)
    yield
    assert llm.llm_tasks_active() == 0, "Zaehler muss nach jedem Test wieder bei 0 sein"


def _in_thread(fn):
    import threading
    t = threading.Thread(target=fn, daemon=True)
    t.start()
    return t


def test_zwei_threads_nur_der_letzte_llm_task_entlaedt(monkeypatch, fresh_counter):
    """Der Hintergrundauftrag haelt das Modell; ein Chat, der waehrenddessen fertig wird,
    darf es nicht entladen. Erst wenn der LETZTE aeussere Block endet, wird entladen."""
    import threading
    calls: list[str] = []
    monkeypatch.setattr(llm, "require_vram", lambda model=None: {})
    monkeypatch.setattr(llm, "release_llm", lambda: calls.append("rel") or 0)
    inside, leave = threading.Event(), threading.Event()

    def background_job():
        with llm.llm_task("x"):
            inside.set()
            leave.wait(5)

    t = _in_thread(background_job)
    assert inside.wait(5)
    assert llm.llm_tasks_active() == 1
    with llm.llm_task("x"):             # der "Chat" im Hauptthread
        assert llm.llm_tasks_active() == 2
    assert calls == []                   # Hintergrundauftrag laeuft noch -> NICHT entladen
    leave.set()
    t.join(5)
    assert calls == ["rel"]              # der letzte macht das Licht aus
    assert llm.llm_tasks_active() == 0


def test_release_unless_in_task_ueberspringt_wenn_ein_anderer_thread_laeuft(monkeypatch, fresh_counter):
    import threading
    calls: list[str] = []
    monkeypatch.setattr(llm, "require_vram", lambda model=None: {})
    monkeypatch.setattr(llm, "release_llm", lambda: calls.append("rel") or 1)
    inside, leave = threading.Event(), threading.Event()

    def background_job():
        with llm.llm_task("x"):
            inside.set()
            leave.wait(5)

    t = _in_thread(background_job)
    assert inside.wait(5)
    assert llm.release_llm_unless_in_task() == 0      # fremder Auftrag aktiv
    assert calls == []
    leave.set()
    t.join(5)
    calls.clear()
    assert llm.release_llm_unless_in_task() == 1      # nichts mehr aktiv -> wie frueher
    assert calls == ["rel"]


def test_require_vram_entlaedt_nicht_unter_einem_laufenden_task(monkeypatch, fresh_counter):
    """Das Zielmodell ist nicht resident (anderes Modell) - trotzdem darf require_vram nicht
    die Modelle eines laufenden Hintergrundauftrags entladen; der Preflight meldet ehrlich."""
    import threading
    released: list[int] = []
    monkeypatch.setattr(llm, "_VRAM_SETTLE_SECONDS", 0)
    monkeypatch.setattr(llm, "_model_resident", lambda model=None: False)
    monkeypatch.setattr(llm, "release_llm", lambda: released.append(1) or 0)
    monkeypatch.setattr(llm, "vram_preflight", lambda model=None: {
        "status": "low", "free_gb": 3.0, "need_gb": 8.0, "model": "x"})
    monkeypatch.setattr(llm, "_unload_tts_for_llm", lambda: None)
    inside, leave = threading.Event(), threading.Event()
    real_require = llm.require_vram

    def background_job():
        monkeypatch.setattr(llm, "require_vram", lambda model=None: {})
        with llm.llm_task("x"):
            monkeypatch.setattr(llm, "require_vram", real_require)
            inside.set()
            leave.wait(5)

    t = _in_thread(background_job)
    assert inside.wait(5)
    released.clear()
    with pytest.raises(llm.VramLowError):
        llm.require_vram("anderes-modell")
    assert released == []
    leave.set()
    t.join(5)


def test_zaehler_bleibt_stimmig_wenn_require_vram_scheitert(monkeypatch, fresh_counter):
    def boom(model=None):
        raise llm.VramLowError("zu wenig")
    monkeypatch.setattr(llm, "require_vram", boom)
    with pytest.raises(llm.VramLowError):
        with llm.llm_task("x"):
            pytest.fail("Block darf nicht laufen")
    assert llm.llm_tasks_active() == 0


def test_zaehler_zaehlt_verschachtelte_bloecke_im_selben_thread_nur_einmal(monkeypatch, fresh_counter):
    monkeypatch.setattr(llm, "require_vram", lambda model=None: {})
    monkeypatch.setattr(llm, "release_llm", lambda: 0)
    with llm.llm_task("x"):
        with llm.llm_task("x"):
            assert llm.llm_tasks_active() == 1
        assert llm.llm_tasks_active() == 1
    assert llm.llm_tasks_active() == 0
