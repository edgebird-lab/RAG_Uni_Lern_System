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
import random
import shutil
import socket
import atexit
import base64
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
TUNNEL_ERROR_FILE = ROOT / "data" / ".tunnel_error"    # Tunnelaufbau fehlgeschlagen (liest die App)
TUNNEL_MODE = os.environ.get("RAG_TUNNEL") == "1"       # Cloudflare-Tunnel gewuenscht? (Start_Unterwegs.bat)
SPLASH_FILE = ROOT / "data" / ".splash.html"           # schoener Ladebildschirm im App-Fenster
ICON_PNG = ROOT / "assets" / "icon.png"


def _no_window_flag() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _rm(path: pathlib.Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _write_mode(m: str) -> None:
    # Atomar schreiben (Temp + os.replace), damit die App nie einen halb/leer
    # geschriebenen Modus liest und faelschlich auf 'local' zurueckfaellt.
    try:
        tmp = UI_MODE_FILE.parent / (UI_MODE_FILE.name + ".tmp")
        tmp.write_text(m, encoding="utf-8")
        os.replace(tmp, UI_MODE_FILE)
    except OSError:
        pass


def _write_tunnel_error() -> None:
    try:
        TUNNEL_ERROR_FILE.write_text("1", encoding="utf-8")
    except OSError:
        pass


# Generation der Tunnel-Versuche: jeder neue Start UND jedes Wegschalten erhoeht sie.
# reader/watchdog eines Versuchs schreiben Tunnel-Dateien nur, solange ihre Generation
# noch die aktuelle ist - so kann ein alter/abgebrochener Versuch keine stale Datei
# hinterlassen (bzw. einen spaeteren, legitim aufbauenden Versuch nicht faelschlich als
# Fehler markieren).
_tunnel_lock = threading.Lock()
_tunnel_gen = 0


def _bump_tunnel_gen() -> int:
    global _tunnel_gen
    with _tunnel_lock:
        _tunnel_gen += 1
        return _tunnel_gen


def _tunnel_gen_current() -> int:
    with _tunnel_lock:
        return _tunnel_gen


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


def _kill_stray_streamlit() -> None:
    """Beendet VERWAISTE Streamlit-Server frueherer Laeufe (App abgestuerzt, hart
    beendet oder z. B. durch Ruhezustand getrennt). Erkennung ueber die Kommandozeile
    UND darueber, dass der Elternprozess (ragapp.desktop) nicht mehr laeuft - so wird
    garantiert KEIN fremdes Python und keine zweite, LAUFENDE Instanz getroffen.
    Verhindert, dass sich im Hintergrund Server ansammeln (L/RAM/Port)."""
    if os.name != "nt":
        return
    ps = (
        "$a=Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" | "
        "Where-Object {$_.CommandLine -match 'ragapp.desktop'} | "
        "Select-Object -ExpandProperty ProcessId; "
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" | "
        "Where-Object {$_.CommandLine -match 'streamlit run' -and $_.CommandLine -match 'ragapp' "
        "-and ($a -notcontains $_.ParentProcessId)} | "
        "ForEach-Object {Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue}"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=20, creationflags=_no_window_flag())
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
    Adresse nach data/tunnel_url.txt, sobald sie steht. Scheitert der Aufbau, wird
    data/.tunnel_error gesetzt, damit die App nicht ewig auf 'wird aufgebaut' haengt,
    sondern einen Hinweis + 'Erneut versuchen' zeigen kann."""
    gen = _bump_tunnel_gen()   # diese Generation; aeltere Versuche verstummen dadurch
    _rm(TUNNEL_URL_FILE)
    _rm(TUNNEL_ERROR_FILE)
    exe = _ensure_cloudflared()
    if not exe:
        print("[i] cloudflared nicht gefunden/installierbar - Tunnel uebersprungen.")
        if gen == _tunnel_gen_current():
            _write_tunnel_error()
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
        if gen == _tunnel_gen_current():
            _write_tunnel_error()
        return None

    def _reader() -> None:
        found = False
        try:
            for line in proc.stdout:  # type: ignore[union-attr]
                if not found:
                    m = _TUNNEL_RE.search(line or "")
                    if m:
                        found = True
                        if gen == _tunnel_gen_current():
                            try:
                                TUNNEL_URL_FILE.write_text(m.group(0), encoding="utf-8")
                                _rm(TUNNEL_ERROR_FILE)
                                print(f"Cloudflare-Adresse: {m.group(0)}")
                            except Exception:  # noqa: BLE001
                                pass
                # weiterlesen, damit die Pipe nicht volllaeuft und cloudflared blockiert
        except Exception:  # noqa: BLE001
            pass
        if not found and gen == _tunnel_gen_current() and not TUNNEL_URL_FILE.exists():
            # cloudflared endete, ohne je eine Adresse zu liefern.
            _write_tunnel_error()

    def _watchdog() -> None:
        # Laeuft DIESER Prozess nach 90s noch, ohne je eine Adresse geliefert zu haben
        # (z. B. Netz blockiert QUIC UND HTTP/2): hart beenden + Fehler signalisieren.
        # Bindung an 'proc' (poll) + Generation verhindert, dass ein alter Watchdog einen
        # spaeteren, noch legitim aufbauenden Versuch faelschlich als Fehler markiert. Das
        # Beenden sorgt zugleich dafuer, dass ein 'Erneut versuchen' danach wieder greift.
        if (proc.poll() is None and gen == _tunnel_gen_current()
                and not TUNNEL_URL_FILE.exists()):
            _kill_tree(proc)
            _write_tunnel_error()

    threading.Thread(target=_reader, daemon=True).start()
    _wd = threading.Timer(90.0, _watchdog)
    _wd.daemon = True
    _wd.start()
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
    return subprocess.Popen(cmd, cwd=str(ROOT), env=env,
                            creationflags=_no_window_flag())


def _wait_until_ready(proc: subprocess.Popen, port: int, timeout: float = 90.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        if proc.poll() is not None:
            return False
        if _port_open(HOST, port):
            return True
        time.sleep(0.4)
    return False


_SPLASH_QUOTES = [
    "Jeder Experte war einmal ein Anfänger.",
    "Erfolg ist die Summe kleiner Anstrengungen – Tag für Tag.",
    "Lernen ist wie Rudern gegen den Strom: Hörst du auf, treibt es dich zurück.",
    "Der beste Zeitpunkt zu lernen war gestern. Der zweitbeste ist jetzt.",
    "Ein Kapitel nach dem anderen – so wird aus Stoff Verständnis.",
    "Nicht für die Klausur, für dich lernst du.",
    "Wissen wächst, wenn man es teilt.",
    "Konzentration schlägt Zeitdruck.",
    "Kleine Schritte bringen dich weiter als kein Schritt.",
    "Du hast schon schwierigere Dinge geschafft.",
]

_SPLASH_TEMPLATE = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RAG-Lernsystem wird gestartet …</title>
<style>
  *{box-sizing:border-box}html,body{height:100%;margin:0}
  body{font-family:"Segoe UI",system-ui,-apple-system,sans-serif;display:flex;
    align-items:center;justify-content:center;
    background:radial-gradient(1200px 800px at 50% -10%,#1e293b 0%,#0f172a 55%,#0b1120 100%);
    color:#e5e7eb;overflow:hidden}
  .card{text-align:center;padding:40px 44px;max-width:480px;animation:fadeIn .6s ease both}
  .logo{width:84px;height:84px;border-radius:20px;margin:0 auto 22px;display:flex;
    align-items:center;justify-content:center;background:rgba(255,255,255,.06);
    box-shadow:0 10px 40px rgba(0,0,0,.45),inset 0 0 0 1px rgba(255,255,255,.08);
    animation:float 3s ease-in-out infinite}
  .logo img{width:60px;height:60px}
  h1{font-size:25px;font-weight:650;margin:0 0 8px;letter-spacing:.2px}
  .quote{font-size:15px;font-style:italic;color:#94a3b8;line-height:1.5;margin:0 0 30px}
  .spinner{width:42px;height:42px;margin:0 auto 18px;border-radius:50%;
    border:3px solid rgba(255,255,255,.12);border-top-color:#6366f1;
    animation:spin .9s linear infinite}
  .status{font-size:13.5px;color:#cbd5e1;min-height:20px;transition:opacity .3s}
  .hint{font-size:12px;color:#64748b;margin-top:14px;min-height:16px}
  @keyframes spin{to{transform:rotate(360deg)}}
  @keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-7px)}}
  @keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
  @media (prefers-color-scheme:light){
    body{background:radial-gradient(1200px 800px at 50% -10%,#eef2ff 0%,#f1f5f9 55%,#e2e8f0 100%);color:#1e293b}
    .logo{background:#fff;box-shadow:0 10px 40px rgba(2,6,23,.12),inset 0 0 0 1px rgba(2,6,23,.06)}
    .quote{color:#64748b}.status{color:#334155}.hint{color:#94a3b8}
    .spinner{border-color:rgba(2,6,23,.10);border-top-color:#6366f1}
  }
</style>
</head>
<body>
  <div class="card">
    <div class="logo"><img src="%%ICON%%" alt=""></div>
    <h1>RAG-Lernsystem</h1>
    <p class="quote">%%QUOTE%%</p>
    <div class="spinner"></div>
    <div class="status" id="s">Wird gestartet …</div>
    <div class="hint" id="h"></div>
  </div>
<script>
  var APP="%%APP_URL%%",HEALTH="%%HEALTH_URL%%";
  var msgs=["Starte lokales KI-Modell …","Lade Oberfläche …","Bereite die Suche vor …","Fast fertig …"];
  var i=0,s=document.getElementById("s"),h=document.getElementById("h"),done=false,t0=Date.now();
  setInterval(function(){if(!done){i=(i+1)%msgs.length;s.style.opacity=0;
    setTimeout(function(){s.textContent=msgs[i];s.style.opacity=1;},300);}},2600);
  function go(){if(done)return;done=true;window.location.replace(APP);}
  function ping(){
    if(done)return;
    fetch(HEALTH,{mode:"no-cors",cache:"no-store"}).then(go).catch(function(){
      if(Date.now()-t0>90000){h.innerHTML='Das dauert länger als sonst. <a href="'+APP+'" style="color:#818cf8;text-decoration:none">Jetzt öffnen ›</a>';}
      setTimeout(ping,700);
    });
  }
  ping();
</script>
</body>
</html>
"""


def _write_splash(app_url: str, health_url: str) -> "str | None":
    """Schreibt einen schoenen Ladebildschirm (self-contained HTML) und gibt seine
    file://-Adresse zurueck. Der Splash zeigt sich sofort im App-Fenster und leitet
    per JS selbst auf die App weiter, sobald Streamlit antwortet."""
    try:
        icon = ""
        if ICON_PNG.is_file():
            icon = "data:image/png;base64," + base64.b64encode(
                ICON_PNG.read_bytes()).decode("ascii")
        html = (_SPLASH_TEMPLATE
                .replace("%%APP_URL%%", app_url)
                .replace("%%HEALTH_URL%%", health_url)
                .replace("%%ICON%%", icon)
                .replace("%%QUOTE%%", random.choice(_SPLASH_QUOTES)))
        SPLASH_FILE.parent.mkdir(parents=True, exist_ok=True)
        SPLASH_FILE.write_text(html, encoding="utf-8")
        return SPLASH_FILE.as_uri()
    except Exception as exc:  # noqa: BLE001
        print(f"[i] Ladebildschirm konnte nicht erstellt werden: {exc}")
        return None


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
        # Vollbild -> die Windows-Taskleiste ist ausgeblendet und verdeckt nichts
        # mehr (z. B. das Fach-Dropdown). Mit F11 laesst sich Vollbild umschalten.
        "--start-fullscreen",
        "--window-size=1240,860", "--no-first-run", "--no-default-browser-check",
    ]
    try:
        return subprocess.Popen(args)
    except Exception as exc:  # noqa: BLE001
        print(f"[!] App-Fenster liess sich nicht oeffnen: {exc}")
        return None


# --------------------------------------------------------------------------- #
# Fensterloser Start (pythonw.exe): Ausgabe nach data/app.log umleiten
# --------------------------------------------------------------------------- #
def _redirect_output_if_windowless() -> None:
    """Wird die App ueber ``pythonw.exe`` (Desktop-Icon, KEIN Konsolenfenster)
    gestartet, sind ``sys.stdout``/``sys.stderr`` = ``None`` - jeder ``print()``
    wuerde dann mit ``AttributeError`` abstuerzen. In diesem Fall die Ausgabe nach
    ``data/app.log`` umleiten (Diagnose bleibt erhalten). Beim Start ueber
    ``python.exe`` (Konsole, Start.bat) sind stdout/err vorhanden -> nichts tun.

    Hintergrund: Der fensterlose Start ersetzt das fruehere ``Start.vbs`` (wscript
    mit verstecktem Fenster), das von Virenscannern haeufig als Fehlalarm markiert
    wurde. ``pythonw.exe`` erreicht dieselbe Unsichtbarkeit ohne verdaechtiges
    Skript-Muster."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        (ROOT / "data").mkdir(parents=True, exist_ok=True)
        log = open(ROOT / "data" / "app.log", "a", encoding="utf-8",
                   errors="replace", buffering=1)
        if sys.stdout is None:
            sys.stdout = log
        if sys.stderr is None:
            sys.stderr = log
    except OSError:
        # Zur Not stumme Ersatz-Streams, damit print() den Start niemals killt.
        class _Null:
            def write(self, *_a: object) -> int:
                return 0

            def flush(self) -> None:
                pass

        if sys.stdout is None:
            sys.stdout = _Null()   # type: ignore[assignment]
        if sys.stderr is None:
            sys.stderr = _Null()   # type: ignore[assignment]


# --------------------------------------------------------------------------- #
# Hauptablauf
# --------------------------------------------------------------------------- #
def main() -> int:
    if not HOME.is_file():
        print(f"[Fehler] Oberflaeche nicht gefunden: {HOME}")
        return 1

    _rm(SHUTDOWN_SENTINEL)
    _rm(UI_RESTART_FILE)
    _rm(TUNNEL_URL_FILE)      # Altlasten eines frueheren (evtl. hart beendeten) Laufs
    _rm(TUNNEL_ERROR_FILE)
    _rm(SPLASH_FILE)
    # Verwaiste Server frueherer (hart beendeter) Laeufe aufraeumen, damit sich im
    # Hintergrund nichts ansammelt (Streamlit + evtl. offener Cloudflare-Tunnel).
    _kill_stray_streamlit()
    _taskkill_image("cloudflared.exe")

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
    tunnel = {"proc": None, "starting": False, "cancel": False}
    if mode == "tunnel":
        tunnel["proc"] = _start_tunnel(port)

    def _cleanup() -> None:
        _kill_tree(st["proc"])
        _stop_ollama_fully(ollama_proc)
        _kill_tree(tunnel["proc"])
        _taskkill_image("cloudflared.exe")
        _rm(TUNNEL_URL_FILE)
        _rm(TUNNEL_ERROR_FILE)
        _rm(SPLASH_FILE)
        _rm(SHUTDOWN_SENTINEL)
        _rm(UI_RESTART_FILE)
        _rm(UI_MODE_FILE)
    atexit.register(_cleanup)

    # Ladebildschirm SOFORT im App-Fenster zeigen, waehrend Ollama/Streamlit hochfahren.
    # Der Splash leitet per JS selbst auf die App weiter, sobald sie bereit ist.
    health_url = f"http://localhost:{port}/_stcore/health"
    splash_uri = _write_splash(url, health_url)
    browser, kind = _find_browser()

    win = None
    opened = False
    if splash_uri:
        if browser:
            print(f"Oeffne App-Fenster ({kind}) ...")
            win = _open_window(browser, splash_uri)
        if win is not None:
            opened = True
        else:
            try:
                webbrowser.open(splash_uri)
                opened = True
            except Exception:  # noqa: BLE001
                opened = False

    # Auf die fertige Oberflaeche warten (fuer sauberes Cleanup bei Fehlstart).
    if not _wait_until_ready(st["proc"], port):
        print(f"[Fehler] Oberflaeche wurde nicht bereit (Port {port}).")
        _kill_tree(win)   # auch das (Splash-)Fenster schliessen
        _cleanup()
        return 1

    if not opened:
        # Kein Splash sichtbar -> jetzt (bereit) direkt die App oeffnen.
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
                if desired in ("local", "network", "tunnel"):
                    if desired != mode:
                        print("Wechsle auf '%s' ..." % desired)
                        mode = desired
                        _write_mode(mode)
                    # KEIN Streamlit-Neustart (Bind ist immer 0.0.0.0) -> kein Neuladen.
                    # Nur den Cloudflare-Tunnel starten bzw. stoppen.
                    if desired == "tunnel":
                        tunnel["cancel"] = False   # aktuelle Absicht: Tunnel gewuenscht
                        proc = tunnel["proc"]
                        # (Neu-)Start, wenn keiner laeuft ODER noch keine Adresse steht
                        # (deckt "Erneut versuchen" bei haengendem cloudflared ab).
                        _need = (proc is None or proc.poll() is not None
                                 or not TUNNEL_URL_FILE.exists())
                        if not tunnel["starting"] and _need:
                            # evtl. noch lebenden, aber haengenden Tunnel hart beenden.
                            if proc is not None and proc.poll() is None:
                                _kill_tree(proc)
                            tunnel["starting"] = True
                            tunnel["proc"] = None
                            _taskkill_image("cloudflared.exe")

                            def _go() -> None:
                                # nicht-blockierend: cloudflared-Installation kann dauern.
                                try:
                                    p = _start_tunnel(port)
                                    if tunnel["cancel"]:
                                        # Nutzer hat waehrenddessen weggeschaltet -> den
                                        # frisch gestarteten Tunnel sofort wieder beenden,
                                        # damit die App NICHT ungewollt exponiert bleibt.
                                        _kill_tree(p)
                                        _taskkill_image("cloudflared.exe")
                                        _rm(TUNNEL_URL_FILE)
                                        _rm(TUNNEL_ERROR_FILE)
                                        tunnel["proc"] = None
                                    else:
                                        tunnel["proc"] = p
                                finally:
                                    tunnel["starting"] = False

                            threading.Thread(target=_go, daemon=True).start()
                    else:
                        tunnel["cancel"] = True   # laufenden Startvorgang abbrechen
                        _bump_tunnel_gen()        # in-flight reader/watchdog verstummen
                        if tunnel["proc"] is not None:
                            _kill_tree(tunnel["proc"])
                            tunnel["proc"] = None
                        _taskkill_image("cloudflared.exe")
                        _rm(TUNNEL_URL_FILE)
                        _rm(TUNNEL_ERROR_FILE)
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
    _rm(TUNNEL_ERROR_FILE)
    print("Fertig. Es laeuft nichts mehr im Hintergrund.")
    return 0


if __name__ == "__main__":
    _redirect_output_if_windowless()
    raise SystemExit(main())
