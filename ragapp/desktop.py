"""
RAG-Lernsystem – Desktop-App-Fenster
====================================
Startet die Streamlit-Oberflaeche und oeffnet sie in einem eigenen,
rahmenlosen App-Fenster (Chromium ``--app``-Modus) statt in einem Browser-Tab.
Kein sichtbarer Browser, keine Adressleiste, keine Tabs – es fuehlt sich wie
ein eigenstaendiges Programm an. Das Fenster-/Taskleisten-Icon ist unser
App-Icon (ueber das Streamlit-Favicon).

Sauberer, mehrstufiger Rueckfall:
  1. Microsoft Edge  --app   (auf Windows 11 praktisch immer vorhanden)
  2. Google Chrome   --app
  3. Standardbrowser (normaler Tab), falls keiner der beiden da ist

Robust:
  * Waehlt automatisch einen freien Port (Standard 8501, sonst OS-vergeben) –
    kollidiert nie mit einem evtl. schon laufenden Streamlit.
  * ``--server.address localhost`` -> nur lokal erreichbar (nicht im Heimnetz).
  * ``--server.headless true``     -> Streamlit oeffnet KEINEN eigenen Tab.
  * Beim Schliessen wird der ganze Prozessbaum sauber beendet.

Aufruf:  python -m ragapp.desktop   (oder ueber Start.bat)
"""
from __future__ import annotations

import os
import sys
import time
import socket
import shutil
import atexit
import pathlib
import subprocess
import webbrowser

HOST = "127.0.0.1"
PREFERRED_PORT = int(os.environ.get("RAG_UI_PORT", "8501"))

ROOT = pathlib.Path(__file__).resolve().parents[1]      # Repo-Wurzel (enthaelt 'ragapp')
HOME = ROOT / "ragapp" / "ui" / "Home.py"
PROFILE_DIR = ROOT / "data" / ".appwindow"              # eigenes Browser-Profil -> isolierte, wartbare Instanz


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """True, wenn auf host:port jemand lauscht."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def _pick_port(preferred: int = PREFERRED_PORT) -> int:
    """Nimmt den bevorzugten Port, wenn frei; sonst einen vom OS vergebenen freien Port."""
    if not _port_open(HOST, preferred):
        return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def _find_browser() -> "tuple[str | None, str]":
    """Findet Edge oder Chrome. Rueckgabe (pfad|None, art) mit art in {'Edge','Chrome',''}."""
    candidates = [
        ("Edge", [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            shutil.which("msedge"),
        ]),
        ("Chrome", [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            shutil.which("chrome"),
        ]),
    ]
    for kind, paths in candidates:
        for p in paths:
            if p and os.path.isfile(p):
                return p, kind
    return None, ""


def _start_streamlit(port: int) -> subprocess.Popen:
    """Startet den Streamlit-Server headless (kein eigener Browser-Tab, nur lokal)."""
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    cmd = [
        sys.executable, "-m", "streamlit", "run", str(HOME),
        "--server.address", "localhost",
        "--server.port", str(port),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]
    return subprocess.Popen(cmd, cwd=str(ROOT), env=env)


def _wait_until_ready(proc: subprocess.Popen, port: int, timeout: float = 90.0) -> bool:
    """Wartet, bis der Port offen ist. False, wenn Streamlit vorher stirbt oder Timeout."""
    start = time.time()
    while time.time() - start < timeout:
        if proc.poll() is not None:
            return False
        if _port_open(HOST, port):
            return True
        time.sleep(0.4)
    return False


def _open_window(browser: str, url: str) -> "subprocess.Popen | None":
    """Oeffnet ein rahmenloses App-Fenster (eigenes Profil -> eine wartbare Instanz)."""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    args = [
        browser,
        f"--app={url}",
        f"--user-data-dir={PROFILE_DIR}",
        "--window-size=1240,860",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    try:
        return subprocess.Popen(args)
    except Exception as exc:  # noqa: BLE001 - Fallback ist wichtiger als der genaue Fehler
        print(f"[!] App-Fenster liess sich nicht oeffnen: {exc}")
        return None


def _kill_tree(proc: subprocess.Popen) -> None:
    """Beendet den Prozess samt Kindprozessen (Streamlit kann Kinder spawnen)."""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            )
            return
        except Exception:  # noqa: BLE001 - dann klassisch weiter unten
            pass
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    if not HOME.is_file():
        print(f"[Fehler] Oberflaeche nicht gefunden: {HOME}")
        return 1

    port = _pick_port()
    url = f"http://localhost:{port}"
    if port != PREFERRED_PORT:
        print(f"[i] Port {PREFERRED_PORT} war belegt – nutze freien Port {port}.")

    print("Starte Oberflaeche (im Hintergrund) ...")
    st_proc = _start_streamlit(port)
    atexit.register(lambda: _kill_tree(st_proc))

    if not _wait_until_ready(st_proc, port):
        print(f"[Fehler] Oberflaeche wurde nicht bereit (Port {port}).")
        _kill_tree(st_proc)
        return 1

    browser, kind = _find_browser()
    if browser:
        print(f"Oeffne App-Fenster ({kind}) – kein Browser-Rahmen.")
        win = _open_window(browser, url)
        if win is not None:
            try:
                win.wait()          # blockiert, bis das App-Fenster geschlossen wird
            except KeyboardInterrupt:
                pass
            print("Fenster geschlossen – beende Oberflaeche.")
            _kill_tree(st_proc)
            return 0
        # sonst: Fenster-Start fehlgeschlagen -> Standardbrowser-Fallback

    print("Kein Edge/Chrome fuer den App-Modus gefunden – oeffne Standardbrowser.")
    print("Zum Beenden dieses schwarze Fenster schliessen.")
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass
    try:
        st_proc.wait()              # blockiert, bis Streamlit/Konsole beendet wird
    except KeyboardInterrupt:
        pass
    _kill_tree(st_proc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
