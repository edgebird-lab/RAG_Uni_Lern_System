"""Headless smoke test for the real Streamlit multipage application.

Kein pytest-Test: CI startet ihn in einem separaten Job mit Chromium. So bleibt
die schnelle Offline-Unit-Suite browserfrei.
"""
from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright


def _has_streamlit_traceback(text: str) -> bool:
    """Streamlit zeigt Exceptions als 'Traceback:\\nFile \"...', nicht als CPython-Header."""
    if "Traceback (most recent call last)" in text:
        return True
    return "Traceback:" in text and 'File "' in text


ROOT = Path(__file__).resolve().parents[1]
PORT = int(os.environ.get("RAG_SMOKE_PORT", "8511"))
BASE = f"http://127.0.0.1:{PORT}"
PAGES = [
    ("/", "Heute"),
    ("/Chat", "Chat"),
    ("/Lernen", "Karteikarten"),
    ("/Organisation", "Kurse"),
    ("/Dokumentenmanager", "Kurs-Inbox"),
    ("/Semesterplan", "Semester einrichten"),
    ("/Fortschritt", "Lernstand"),
    ("/Lernplan", "Lernplan"),
    ("/Übungsaufgaben", "Übungsaufgaben"),
    ("/Prüfung", "Prüfung"),
]


def _wait_for_server(proc: subprocess.Popen, timeout: float = 45.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("Streamlit wurde vor dem Start beendet.")
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=0.5):
                return
        except OSError:
            time.sleep(0.25)
    raise TimeoutError(f"Streamlit antwortet nicht auf Port {PORT}.")


def main() -> int:
    env = {
        **os.environ,
        "RAG_LOCAL_ONLY": "1",
        "RAG_LOCAL_TOKEN": "ci-live-smoke",
        "RAG_DISABLE_PREWARM": "1",
        "RAG_IDLE_SHUTDOWN": "0",
        "RAG_AUTO_RECOVERY": "0",
    }
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run",
            "ragapp/ui/🏠_Home.py",
            "--server.address", "127.0.0.1",
            "--server.port", str(PORT),
            "--server.headless", "true",
        ],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True,
    )
    errors: list[str] = []
    screenshot_dir = os.environ.get("RAG_SMOKE_SCREENSHOT_DIR")
    if screenshot_dir:
        Path(screenshot_dir).mkdir(parents=True, exist_ok=True)
    try:
        _wait_for_server(proc)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on(
                "console",
                lambda msg: errors.append(f"console:{msg.type}:{msg.text}")
                if msg.type == "error" else None,
            )
            page.on("pageerror", lambda exc: errors.append(f"pageerror:{exc}"))
            for path, expected in PAGES:
                page.goto(
                    f"{BASE}{path}?k=ci-live-smoke",
                    wait_until="domcontentloaded",
                )
                page.locator('[data-testid="stApp"]').wait_for(timeout=30_000)
                page.get_by_text(expected, exact=False).first.wait_for(
                    state="visible", timeout=30_000)
                body = page.locator("body").inner_text()
                if _has_streamlit_traceback(body):
                    raise AssertionError(f"Streamlit-Traceback auf {path}")
                if path == "/Lernen" and "Prüfungsphase" in body:
                    raise AssertionError(
                        "Lernen zeigt noch Prüfungsphase – die Simulation liegt unter Prüfung.")
                if screenshot_dir:
                    skel = page.locator(".rag-skel")
                    if skel.count() > 0:
                        skel.first.wait_for(state="detached", timeout=30_000)
                    page.wait_for_timeout(700)
                    name = path.strip("/").replace("/", "_") or "Home"
                    page.screenshot(
                        path=str(Path(screenshot_dir) / f"desktop-{name}.png"),
                        full_page=True)
                print(f"OK {path} -> {expected}", flush=True)
            if screenshot_dir:
                mobile = browser.new_page(
                    viewport={"width": 390, "height": 844},
                    device_scale_factor=1)
                mobile.goto(
                    f"{BASE}/?k=ci-live-smoke",
                    wait_until="domcontentloaded")
                mobile.locator('[data-testid="stApp"]').wait_for(timeout=30_000)
                skel = mobile.locator(".rag-skel")
                if skel.count() > 0:
                    skel.first.wait_for(state="detached", timeout=30_000)
                mobile.wait_for_timeout(700)
                mobile.screenshot(
                    path=str(Path(screenshot_dir) / "mobile-Home.png"),
                    full_page=True)
                mobile.close()
            browser.close()
        fatal = [
            error for error in errors
            if "favicon" not in error.lower()
            and "failed to load resource" not in error.lower()
        ]
        if fatal:
            raise AssertionError("\n".join(fatal))
        return 0
    except Exception:
        if proc.stdout:
            print("\n--- Streamlit log ---", file=sys.stderr)
            proc.terminate()
            try:
                output, _ = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                output, _ = proc.communicate()
            print(output[-12_000:], file=sys.stderr)
        raise
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


if __name__ == "__main__":
    raise SystemExit(main())
