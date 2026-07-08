"""
RAG-Lernsystem: Desktop-Starter (Ollama + Oberflaeche in einem)
===============================================================
Dieser Starter ist der EINZIGE Besitzer der Sitzung. Er

  1. startet das lokale KI-Modell (Ollama) - Intel-Arc-iGPU ueber IPEX-LLM,
     sonst Standard-Ollama - als getrackten Kindprozess,
  2. startet die Streamlit-Oberflaeche headless,
  3. oeffnet sie in einem eigenen, rahmenlosen App-Fenster (Edge/Chrome
     ``--app``, sonst Standardbrowser),
  4. ueberwacht Fenster, Oberflaeche und das Beenden-Signal und
  5. stoppt beim Schliessen des Fensters ODER ueber den "Beenden"-Button in
     der App WIRKLICH ALLES wieder - Oberflaeche UND Ollama. Danach laeuft
     nichts mehr im Hintergrund und belastet das System.

Netzwerk-/Handy-Zugriff wird ueber Umgebungsvariablen gesteuert
(Start_Handy-Zugriff.bat): RAG_BIND_HOST=0.0.0.0 und RAG_NETWORK=1.

Aufruf:  python -m ragapp.desktop   (bzw. ueber Start.bat)
"""
from __future__ import annotations

import os
import sys
import time
import shutil
import socket
import atexit
import pathlib
import subprocess
import webbrowser

HOST = "127.0.0.1"
PREFERRED_PORT = int(os.environ.get("RAG_UI_PORT", "8501"))
# Bind-Adresse: 'localhost' = nur dieser PC (Standard). '0.0.0.0' = auch im
# Netzwerk erreichbar (Handy-/Tablet-Zugriff) - setzt Start_Handy-Zugriff.bat.
BIND_HOST = os.environ.get("RAG_BIND_HOST", "localhost")

ROOT = pathlib.Path(__file__).resolve().parents[1]      # Repo-Wurzel (enthaelt 'ragapp')
HOME = ROOT / "ragapp" / "ui" / "Home.py"
PROFILE_DIR = ROOT / "data" / ".appwindow"              # eigenes Browser-Profil -> isolierte, wartbare Instanz
SHUTDOWN_SENTINEL = ROOT / "data" / ".shutdown"         # der Beenden-Button legt diese Datei an
IPEX_EXE = ROOT / "ipex-ollama" / "ollama.exe"          # vorhanden = Intel-GPU-Variante
OLLAMA_PORT = 11434


def _no_window_flag() -> int:
    """Kindprozesse ohne eigenes Konsolenfenster starten (Windows)."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def _pick_port(preferred: int = PREFERRED_PORT) -> int:
    """Bevorzugten Port nehmen, wenn frei; sonst einen freien vom OS."""
    if not _port_open(HOST, preferred):
        return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def _wait_port(port: int, timeout: float = 90.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        if _port_open(HOST, port):
            return True
        time.sleep(0.6)
    return False


def _taskkill_image(name: str) -> None:
    if os.name != "nt":
        return
    try:
        subprocess.run(["taskkill", "/IM", name, "/F", "/T"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    except Exception:  # noqa: BLE001
        pass


def _kill_tree(proc: "subprocess.Popen | None") -> None:
    """Prozess samt Kindprozessen beenden."""
    if proc is None or proc.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            return
        except Exception:  # noqa: BLE001
            pass
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- #
# Ollama (lokales KI-Modell) starten / stoppen
# --------------------------------------------------------------------------- #
def _resolve_standard_ollama() -> "str | None":
    exe = shutil.which("ollama")
    if exe:
        return exe
    for c in (os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
              r"C:\Program Files\Ollama\ollama.exe"):
        if os.path.isfile(c):
            return c
    return None


def _start_ollama() -> "subprocess.Popen | None":
    """Sorgt dafuer, dass ein Ollama-Server laeuft; startet ihn bei Bedarf als
    getrackten Kindprozess (ohne eigenes Fenster). Rueckgabe: der gestartete
    Prozess oder None (wenn schon einer lief oder keiner gefunden wurde)."""
    intel = IPEX_EXE.is_file()

    if _port_open(HOST, OLLAMA_PORT):
        if intel:
            # Auf der Intel-Variante soll garantiert der GPU-Server laufen -
            # ein evtl. laufender CPU-Ollama weicht.
            _taskkill_image("ollama.exe")
            _taskkill_image("ollama app.exe")
            time.sleep(1.0)
        else:
            return None  # es laeuft schon ein (Standard-)Ollama -> nutzen

    if intel:
        print("Starte lokales KI-Modell auf der Intel-GPU (IPEX-LLM) ...")
        env = dict(os.environ)
        env.update({
            "OLLAMA_NUM_GPU": "999",
            "ZES_ENABLE_SYSMAN": "1",
            "ONEAPI_DEVICE_SELECTOR": "level_zero:0",
            "OLLAMA_HOST": "127.0.0.1:11434",
            "OLLAMA_KEEP_ALIVE": "30m",
            "OLLAMA_NUM_PARALLEL": "1",
            "OLLAMA_MAX_LOADED_MODELS": "2",
        })
        try:
            return subprocess.Popen([str(IPEX_EXE), "serve"], cwd=str(IPEX_EXE.parent),
                                    env=env, creationflags=_no_window_flag())
        except Exception as exc:  # noqa: BLE001
            print(f"[!] IPEX-Ollama-Server liess sich nicht starten: {exc}")
            return None

    exe = _resolve_standard_ollama()
    if not exe:
        print("[i] Ollama nicht gefunden - bitte sicherstellen, dass Ollama laeuft.")
        return None
    print("Starte lokales KI-Modell (Ollama) ...")
    try:
        return subprocess.Popen([exe, "serve"], creationflags=_no_window_flag())
    except Exception as exc:  # noqa: BLE001
        print(f"[!] Ollama-Server liess sich nicht starten: {exc}")
        return None


def _stop_ollama_fully(proc: "subprocess.Popen | None") -> None:
    """Ollama WIRKLICH beenden - den getrackten Prozess und alle ollama-Prozesse,
    damit nach dem Beenden nichts mehr im Hintergrund laeuft."""
    _kill_tree(proc)
    _taskkill_image("ollama.exe")
    _taskkill_image("ollama app.exe")


# --------------------------------------------------------------------------- #
# Streamlit + App-Fenster
# --------------------------------------------------------------------------- #
def _start_streamlit(port: int) -> subprocess.Popen:
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    cmd = [
        sys.executable, "-m", "streamlit", "run", str(HOME),
        "--server.address", BIND_HOST,
        "--server.port", str(port),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]
    return subprocess.Popen(cmd, cwd=str(ROOT), env=env)


def _wait_until_ready(proc: subprocess.Popen, port: int, timeout: float = 90.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        if proc.poll() is not None:
            return False
        if _port_open(HOST, port):
            return True
        time.sleep(0.4)
    return False


def _find_browser() -> "tuple[str | None, str]":
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


def _open_window(browser: str, url: str) -> "subprocess.Popen | None":
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
    except Exception as exc:  # noqa: BLE001
        print(f"[!] App-Fenster liess sich nicht oeffnen: {exc}")
        return None


# --------------------------------------------------------------------------- #
# Hauptablauf
# --------------------------------------------------------------------------- #
def main() -> int:
    if not HOME.is_file():
        print(f"[Fehler] Oberflaeche nicht gefunden: {HOME}")
        return 1

    # evtl. altes Beenden-Signal von einer frueheren Sitzung entfernen
    try:
        SHUTDOWN_SENTINEL.unlink()
    except OSError:
        pass

    # 1) Lokales KI-Modell (Ollama) starten - waermt im Hintergrund, waehrend
    #    die Oberflaeche hochfaehrt (nicht blockieren -> schnelleres Fenster).
    ollama_proc = _start_ollama()

    # 2) Oberflaeche starten
    port = _pick_port()
    url = f"http://localhost:{port}"
    if port != PREFERRED_PORT:
        print(f"[i] Port {PREFERRED_PORT} war belegt, nutze freien Port {port}.")
    print("Starte Oberflaeche ...")
    st_proc = _start_streamlit(port)

    def _cleanup() -> None:
        _kill_tree(st_proc)
        _stop_ollama_fully(ollama_proc)
    atexit.register(_cleanup)

    if not _wait_until_ready(st_proc, port):
        print(f"[Fehler] Oberflaeche wurde nicht bereit (Port {port}).")
        _cleanup()
        return 1

    # 3) App-Fenster oeffnen (Fallback: Standardbrowser)
    browser, kind = _find_browser()
    win = None
    if browser:
        print(f"Oeffne App-Fenster ({kind}) ...")
        win = _open_window(browser, url)
    if win is None:
        print("Kein App-Modus verfuegbar - oeffne Standardbrowser.")
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass

    # 4) Ueberwachen: bis das Fenster geschlossen wird ODER die Oberflaeche
    #    endet ODER der "Beenden"-Button das Signal legt.
    print("Laeuft. Fenster schliessen oder in der App 'Beenden' druecken zum Stoppen.")
    try:
        while True:
            if win is not None and win.poll() is not None:
                break                                   # Fenster geschlossen
            if st_proc.poll() is not None:
                break                                   # Oberflaeche beendet
            if SHUTDOWN_SENTINEL.exists():
                break                                   # Beenden-Button
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass

    # 5) Sauber runterfahren: Fenster schliessen, Oberflaeche + Ollama stoppen.
    print("Beende - Oberflaeche und lokales KI-Modell werden gestoppt ...")
    try:
        SHUTDOWN_SENTINEL.unlink()
    except OSError:
        pass
    if win is not None:
        _kill_tree(win)
    _kill_tree(st_proc)
    _stop_ollama_fully(ollama_proc)
    print("Fertig. Es laeuft nichts mehr im Hintergrund.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
