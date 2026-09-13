"""Tests fuer das In-App-Beenden (ragapp.ui._shutdown_watchdog)."""
from __future__ import annotations

import inspect
import time

from ragapp.ui import _shutdown_watchdog as watchdog
from ragapp.ui._auth import _quit_button


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
    src = inspect.getsource(_quit_button)
    assert "request_quit" in src
    assert "arm_shutdown_on_tab_close" not in src
