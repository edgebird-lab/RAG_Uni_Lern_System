"""Tests fuer das In-App-Beenden (ragapp.ui._shutdown_watchdog)."""
from __future__ import annotations

import inspect
import time

from ragapp.ui import _shutdown_watchdog as watchdog
from ragapp.ui._auth import _quit_button, render_session_controls


def test_write_shutdown_sentinel_legt_datei_an(tmp_path, monkeypatch):
    sentinel = tmp_path / ".shutdown"
    monkeypatch.setattr("ragapp.config.SHUTDOWN_SENTINEL", sentinel)
    watchdog.write_shutdown_sentinel()
    assert sentinel.read_text(encoding="utf-8") == "1"


def test_request_quit_schreibt_sentinel_ohne_auf_tcp_zu_warten(tmp_path, monkeypatch):
    sentinel = tmp_path / ".shutdown"
    monkeypatch.setattr("ragapp.config.SHUTDOWN_SENTINEL", sentinel)
    exits: list[int] = []

    class _FakeOs:
        @staticmethod
        def _exit(code: int) -> None:
            exits.append(code)

    monkeypatch.setattr(watchdog, "os", _FakeOs)
    monkeypatch.setattr(watchdog.time, "sleep", lambda _s: None)
    watchdog._armed_on_close = False

    watchdog.request_quit(delay_sec=0)

    assert sentinel.read_text(encoding="utf-8") == "1"
    deadline = time.monotonic() + 1.0
    while not exits and time.monotonic() < deadline:
        time.sleep(0.01)
    assert exits == [0]


def test_quit_button_beendet_ueber_request_quit_nicht_tab_close():
    src = inspect.getsource(render_session_controls)
    assert "request_quit" in src
    assert "arm_shutdown_on_tab_close" not in src
    wrapper = inspect.getsource(_quit_button)
    assert "render_session_controls" in wrapper


# --------------------------------------------------------------------------- #
# Hintergrundauftrag haelt den Tab-Close-Waechter auf
# --------------------------------------------------------------------------- #
def test_idle_step_beendet_erst_nach_der_karenzzeit_wenn_kein_tab_mehr_offen_ist():
    seen, idle, quit_ = watchdog._idle_step(0, True, None, 100.0, 25.0, busy=False)
    assert (seen, idle, quit_) == (True, 100.0, False)          # Karenzzeit beginnt
    seen, idle, quit_ = watchdog._idle_step(0, True, 100.0, 120.0, 25.0, busy=False)
    assert quit_ is False                                       # noch nicht lange genug
    seen, idle, quit_ = watchdog._idle_step(0, True, 100.0, 126.0, 25.0, busy=False)
    assert quit_ is True


def test_idle_step_offenes_tab_setzt_zurueck():
    seen, idle, quit_ = watchdog._idle_step(1, False, None, 5.0, 25.0, busy=False)
    assert (seen, idle, quit_) == (True, None, False)
    seen, idle, quit_ = watchdog._idle_step(2, True, 50.0, 500.0, 25.0, busy=False)
    assert (seen, idle, quit_) == (True, None, False)


def test_idle_step_beendet_nie_bevor_ein_client_da_war():
    assert watchdog._idle_step(0, False, None, 1e9, 25.0, busy=False) == (False, None, False)


def test_idle_step_laufender_auftrag_haelt_den_waechter_auf_und_startet_die_karenz_neu():
    # Tab zu seit langem, aber ein Auftrag laeuft -> NICHT beenden, Zaehler laeuft mit.
    seen, idle, quit_ = watchdog._idle_step(0, True, 100.0, 5000.0, 25.0, busy=True)
    assert quit_ is False and idle == 5000.0
    # Auftrag fertig: die Karenzzeit beginnt ab dem Ende des Auftrags, nicht ab dem Tab-Schliessen.
    seen, idle, quit_ = watchdog._idle_step(0, True, idle, 5010.0, 25.0, busy=False)
    assert quit_ is False
    seen, idle, quit_ = watchdog._idle_step(0, True, idle, 5026.0, 25.0, busy=False)
    assert quit_ is True


def test_background_job_running_folgt_dem_job_register():
    import threading
    from ragapp import jobs
    jobs.reset_for_tests()
    try:
        assert watchdog._background_job_running() is False
        gate = threading.Event()
        jobs.start("plan:x", "x", lambda ctx: gate.wait(5))
        assert watchdog._background_job_running() is True
        gate.set()
        end = time.time() + 5
        while watchdog._background_job_running() and time.time() < end:
            time.sleep(0.005)
        assert watchdog._background_job_running() is False
    finally:
        jobs.reset_for_tests()


def test_watch_loop_beendet_nicht_solange_ein_auftrag_laeuft(monkeypatch):
    """Die Schleife selbst: kein Tab, aber ein Auftrag -> kein Beenden, auch nach "ewiger" Zeit."""
    clock = {"t": 0.0}
    triggered: list[int] = []
    monkeypatch.setattr(watchdog.time, "monotonic", lambda: clock["t"])
    steps = {"n": 0}
    counts = iter([1, 0, 0, 0, 0, 0, 0, None])       # Tab offen, dann zu, am Ende Abbruch

    def fake_count(port):
        return next(counts)

    def fake_sleep(_s):
        clock["t"] += 1000.0
        steps["n"] += 1

    monkeypatch.setattr(watchdog, "_connected_client_count", fake_count)
    monkeypatch.setattr(watchdog.time, "sleep", fake_sleep)
    monkeypatch.setattr(watchdog, "_background_job_running", lambda: True)
    monkeypatch.setattr(watchdog, "_trigger_shutdown", lambda: triggered.append(1))
    watchdog._watch_loop(25.0)
    assert triggered == []
    assert steps["n"] >= 6


def test_watch_loop_beendet_wieder_normal_ohne_auftrag(monkeypatch):
    clock = {"t": 0.0}
    triggered: list[int] = []
    monkeypatch.setattr(watchdog.time, "monotonic", lambda: clock["t"])
    counts = iter([1, 0, 0, 0, 0, 0])

    def fake_sleep(_s):
        clock["t"] += 20.0

    monkeypatch.setattr(watchdog, "_connected_client_count", lambda port: next(counts))
    monkeypatch.setattr(watchdog.time, "sleep", fake_sleep)
    monkeypatch.setattr(watchdog, "_background_job_running", lambda: False)
    monkeypatch.setattr(watchdog, "_trigger_shutdown", lambda: triggered.append(1))
    watchdog._watch_loop(25.0)
    assert triggered == [1]
