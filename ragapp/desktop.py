"""
RAG-Lernsystem: Desktop-Starter (Ollama + Oberflaeche in einem)
===============================================================
Dieser Starter ist der EINZIGE Besitzer der Sitzung. Er

  1. startet das lokale KI-Modell (Ollama) - Intel-Arc-iGPU ueber IPEX-LLM,
     sonst Standard-Ollama - als getrackten Kindprozess,
  2. startet die Streamlit-Oberflaeche headless (standardmaessig NUR lokal),
  3. oeffnet sie in einem eigenen, rahmenlosen App-Fenster (Edge/Chrome
     ``--app``, sonst Standardbrowser),
  4. ueberwacht Fenster, Oberflaeche und Signale aus der App und
  5. stoppt beim Schliessen des Fensters ODER ueber den "Beenden"-Button in der
     App WIRKLICH ALLES (Oberflaeche + Ollama + evtl. Tunnel). Danach laeuft
     nichts mehr im Hintergrund.

Netzwerk-/Handy-Zugriff:
  * Standard = nur dieser PC (localhost).
  * Der Button "Mit Smartphone verbinden" in der App legt UI_RESTART_FILE mit
    "network" an -> dieser Starter startet Streamlit kurz im Netzwerkmodus
    (0.0.0.0) neu (gleicher Port, das Fenster verbindet sich automatisch neu).
    "Verbindung trennen" schaltet analog zurueck auf "local".
  * RAG_NETWORK=1 / RAG_TUNNEL=1 (Start_Handy-Zugriff.bat / Start_Unterwegs.bat)
    starten direkt im Netzwerk- bzw. Tunnelmodus.

Aufruf:  python -m ragapp.desktop   (bzw. ueber Start.bat)
"""
from __future__ import annotations

import os
import re
import sys
import time
import shutil
import socket
import atexit
import secrets
import pathlib
import threading
import subprocess
import webbrowser

HOST = "127.0.0.1"
PREFERRED_PORT = int(os.environ.get("RAG_UI_PORT", "8501"))

ROOT = pathlib.Path(__file__).resolve().parents[1]      # Repo-Wurzel (enthaelt 'ragapp')
HOME = ROOT / "ragapp" / "ui" / "Home.py"
PROFILE_DIR = ROOT / "data" / ".appwindow"              # eigenes Browser-Profil -> isolierte, wartbare Instanz
SHUTDOWN_SENTINEL = ROOT / "data" / ".shutdown"         # "Beenden"-Button legt diese Datei an
UI_RESTART_FILE = ROOT / "data" / ".restart_ui"         # Modus-Wechsel aus der App ("local"/"network"/"tunnel")
UI_MODE_FILE = ROOT / "data" / ".mode"                  # aktueller Modus (fuer die Anzeige in der App)
IPEX_EXE = ROOT / "ipex-ollama" / "ollama.exe"          # vorhanden = Intel-GPU-Variante
OLLAMA_PORT = 11434
TUNNEL_URL_FILE = ROOT / "data" / "tunnel_url.txt"      # Cloudflare-Adresse (liest die App)
TUNNEL_MODE = os.environ.get("RAG_TUNNEL") == "1"       # Cloudflare-Tunnel gewuenscht? (Start_Unterwegs.bat)


def _no_window_flag() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _rm(path: pathlib.Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _write_mode(m: str) -> None:
    try:
        UI_MODE_FILE.write_text(m, encoding="utf-8")
    except OSError:
        pass


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def _pick_port(preferred: int = PREFERRED_PORT) -> int:
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


def _wait_port_free(port: int, timeout: float = 12.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        if not _port_open(HOST, port):
            return True
        time.sleep(0.3)
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
    getrackten Kindprozess (ohne eigenes Fenster)."""
    intel = IPEX_EXE.is_file()
    if _port_open(HOST, OLLAMA_PORT):
        if intel:
            _taskkill_image("ollama.exe")
            _taskkill_image("ollama app.exe")
            time.sleep(1.0)
        else:
            return None  # laeuft schon ein (Standard-)Ollama -> nutzen
    if intel:
        print("Starte lokales KI-Modell auf der Intel-GPU (IPEX-LLM) ...")
        env = dict(os.environ)
        env.update({
            "OLLAMA_NUM_GPU": "999", "ZES_ENABLE_SYSMAN": "1",
            "ONEAPI_DEVICE_SELECTOR": "level_zero:0", "OLLAMA_HOST": "127.0.0.1:11434",
            "OLLAMA_KEEP_ALIVE": "30m", "OLLAMA_NUM_PARALLEL": "1",
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
    _kill_tree(proc)
    _taskkill_image("ollama.exe")
    _taskkill_image("ollama app.exe")
    # Intel-IPEX spawnt den eigentlichen Server als ollama-lib.exe (haelt Port
    # 11434) - der muss mit, sonst laeuft er nach dem Beenden weiter.
    _taskkill_image("ollama-lib.exe")


# --------------------------------------------------------------------------- #
# Cloudflare-Tunnel (Zugriff von unterwegs) - optional
# --------------------------------------------------------------------------- #
def _resolve_cloudflared() -> "str | None":
    exe = shutil.which("cloudflared")
    if exe:
        return exe
    for c in (os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\cloudflared.exe"),
              r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
              r"C:\Program Files\cloudflared\cloudflared.exe"):
        if os.path.isfile(c):
            return c
    return None


def _ensure_cloudflared() -> "str | None":
    """cloudflared finden; auf Windows bei Bedarf via winget installieren."""
    exe = _resolve_cloudflared()
    if exe:
        return exe
    if os.name == "nt" and shutil.which("winget"):
        print("Installiere cloudflared (einmalig, via winget) - kann 1-2 Minuten dauern ...")
        try:
            subprocess.run(
                ["winget", "install", "--id", "Cloudflare.cloudflared", "-e", "--silent",
                 "--accept-source-agreements", "--accept-package-agreements"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=360)
        except Exception:  # noqa: BLE001
            pass
        return _resolve_cloudflared()
    return None


_TUNNEL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def _start_tunnel(port: int) -> "subprocess.Popen | None":
    """Cloudflare-Quick-Tunnel auf localhost:port; schreibt die oeffentliche
    Adresse nach data/tunnel_url.txt, sobald sie steht."""
    _rm(TUNNEL_URL_FILE)
    exe = _ensure_cloudflared()
    if not exe:
        print("[i] cloudflared nicht gefunden/installierbar - Tunnel uebersprungen.")
        return None
    print("Starte Cloudflare-Tunnel (Zugriff von unterwegs) ...")
    try:
        proc = subprocess.Popen(
            # --protocol http2: QUIC (UDP 7844) wird von vielen Netzen blockiert
            # (Fehler 1033). HTTP/2 laeuft ueber TCP 443 und kommt fast immer durch.
            [exe, "tunnel", "--url", f"http://localhost:{port}",
             "--protocol", "http2", "--no-autoupdate"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", creationflags=_no_window_flag())
    except Exception as exc:  # noqa: BLE001
        print(f"[!] Cloudflare-Tunnel liess sich nicht starten: {exc}")
        return None

    def _reader() -> None:
        found = False
        try:
            for line in proc.stdout:  # type: ignore[union-attr]
                if not found:
                    m = _TUNNEL_RE.search(line or "")
                    if m:
                        found = True
                        try:
                            TUNNEL_URL_FILE.write_text(m.group(0), encoding="utf-8")
                            print(f"Cloudflare-Adresse: {m.group(0)}")
                        except Exception:  # noqa: BLE001
                            pass
                # weiterlesen, damit die Pipe nicht volllaeuft und cloudflared blockiert
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=_reader, daemon=True).start()
    return proc


# --------------------------------------------------------------------------- #
# Streamlit + App-Fenster
# --------------------------------------------------------------------------- #
def _start_streamlit(port: int, network: bool = True) -> subprocess.Popen:
    """Startet Streamlit - IMMER an 0.0.0.0 gebunden. Dadurch braucht ein
    Moduswechsel (lokal/WLAN/Cloudflare) KEINEN Neustart und kein Neuladen (kein
    Verbindungsabbruch). Der Zugriff wird stattdessen ueber den Modus (data/.mode)
    und PIN/Token in der App geregelt - nicht ueber die Bind-Adresse."""
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    cmd = [
        sys.executable, "-m", "streamlit", "run", str(HOME),
        "--server.address", "0.0.0.0",
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
        browser, f"--app={url}", f"--user-data-dir={PROFILE_DIR}",
        "--window-size=1240,860", "--no-first-run", "--no-default-browser-check",
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

    _rm(SHUTDOWN_SENTINEL)
    _rm(UI_RESTART_FILE)

    ollama_proc = _start_ollama()

    port = _pick_port()
    # Geheimes Token nur fuer das lokale App-Fenster: damit am PC KEIN PIN noetig
    # ist (nur das Handy, das dieses Token nicht kennt, muss den PIN eingeben).
    os.environ["RAG_LOCAL_TOKEN"] = secrets.token_urlsafe(16)
    url = f"http://localhost:{port}/?k={os.environ['RAG_LOCAL_TOKEN']}"
    if port != PREFERRED_PORT:
        print(f"[i] Port {PREFERRED_PORT} war belegt, nutze freien Port {port}.")

    def _mode_from_env() -> str:
        if os.environ.get("RAG_TUNNEL") == "1":
            return "tunnel"
        if os.environ.get("RAG_NETWORK") == "1":
            return "network"
        return "local"

    def _is_net(m: str) -> bool:
        return m in ("network", "tunnel")

    mode = _mode_from_env()
    _write_mode(mode)
    print("Starte Oberflaeche%s ..." % ("" if mode == "local" else " (%s)" % mode))
    st = {"proc": _start_streamlit(port, _is_net(mode))}
    tunnel = {"proc": _start_tunnel(port) if mode == "tunnel" else None}

    def _cleanup() -> None:
        _kill_tree(st["proc"])
        _stop_ollama_fully(ollama_proc)
        _kill_tree(tunnel["proc"])
        _taskkill_image("cloudflared.exe")
        _rm(TUNNEL_URL_FILE)
        _rm(SHUTDOWN_SENTINEL)
        _rm(UI_RESTART_FILE)
        _rm(UI_MODE_FILE)
    atexit.register(_cleanup)

    if not _wait_until_ready(st["proc"], port):
        print(f"[Fehler] Oberflaeche wurde nicht bereit (Port {port}).")
        _cleanup()
        return 1

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

    print("Laeuft. Fenster schliessen oder in der App 'Beenden' druecken zum Stoppen.")
    try:
        while True:
            if win is not None and win.poll() is not None:
                break                                   # Fenster geschlossen
            if st["proc"].poll() is not None:
                break                                   # Oberflaeche beendet
            if SHUTDOWN_SENTINEL.exists():
                break                                   # Beenden-Button

            # Modus-Wechsel aus der App (lokal / WLAN / Cloudflare)?
            if UI_RESTART_FILE.exists():
                try:
                    desired = UI_RESTART_FILE.read_text(encoding="utf-8").strip()
                except Exception:  # noqa: BLE001
                    desired = ""
                _rm(UI_RESTART_FILE)
                if desired in ("local", "network", "tunnel") and desired != mode:
                    print("Wechsle auf '%s' ..." % desired)
                    mode = desired
                    _write_mode(mode)
                    # KEIN Streamlit-Neustart (Bind ist immer 0.0.0.0) -> kein
                    # Neuladen. Nur den Cloudflare-Tunnel starten bzw. stoppen.
                    if desired == "tunnel" and tunnel["proc"] is None:
                        # nicht-blockierend: cloudflared-Installation kann dauern.
                        threading.Thread(
                            target=lambda: tunnel.__setitem__("proc", _start_tunnel(port)),
                            daemon=True).start()
                    elif desired != "tunnel" and tunnel["proc"] is not None:
                        _kill_tree(tunnel["proc"])
                        tunnel["proc"] = None
                        _taskkill_image("cloudflared.exe")
                        _rm(TUNNEL_URL_FILE)
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass

    print("Beende - Oberflaeche und lokales KI-Modell werden gestoppt ...")
    _rm(SHUTDOWN_SENTINEL)
    _rm(UI_RESTART_FILE)
    if win is not None:
        _kill_tree(win)
    _kill_tree(st["proc"])
    _stop_ollama_fully(ollama_proc)
    _kill_tree(tunnel["proc"])
    _taskkill_image("cloudflared.exe")
    _rm(TUNNEL_URL_FILE)
    print("Fertig. Es laeuft nichts mehr im Hintergrund.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
