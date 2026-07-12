"""
Tab-Close-Waechter: beendet die App sauber, wenn kein Browser mehr verbunden ist.
============================================================================

Auf Linux/macOS startet die App ueber start.sh -> `streamlit run`, ohne eigenes
Fenster. Streamlit beendet sich NICHT von selbst, wenn das letzte Browser-Tab
geschlossen wird - der Server-Prozess liefe sonst verwaist auf Port 8501 weiter
(genau der "bleibt im Hintergrund"-Effekt).

Erkennung "kein Tab mehr offen":
Jedes offene Browser-Tab haelt eine dauerhafte WebSocket-Verbindung zum UI-Port
(8501). Der Waechter zaehlt daher direkt die bestehenden (ESTABLISHED) TCP-
Verbindungen zu diesem Port aus /proc/net/tcp - unabhaengig von Streamlits
interner Session-Buchhaltung (die getrennte Sessions eine Weile als "aktiv"
behaelt und darum unzuverlaessig ist). Ein offenes Tab ist so IMMER sichtbar
(kein verfruehtes Beenden), und beim Schliessen faellt die Verbindung sofort weg.

Ablauf: Sobald
  * ueberhaupt schon einmal ein Client verbunden war   UND
  * fuer GRACE Sekunden keine Verbindung mehr besteht (alle Tabs zu),
schreibt der Waechter das Beenden-Signal data/.shutdown. Der Waechter in start.sh
sieht das Signal, stoppt Streamlit und entlaedt anschliessend das Ollama-Modell
(RAM/VRAM frei). Als Absicherung - falls die App OHNE start.sh gestartet wurde -
beendet der Waechter den Prozess nach kurzer Frist zusaetzlich selbst.

Aktiv nur, wenn RAG_IDLE_SHUTDOWN gesetzt ist (das setzt start.sh im lokalen
Einzelplatz-Betrieb). Bei blossem `streamlit run` oder im Netzwerk-/Handy-Modus
bleibt der Waechter aus. Abschaltbar mit RAG_NO_AUTO_SHUTDOWN=1; Karenzzeit ueber
RAG_IDLE_SHUTDOWN_SECONDS (Standard 25) einstellbar.
"""
from __future__ import annotations

import os
import threading
import time

_POLL_SECONDS = 3.0          # Wie oft geprueft wird.
_DEFAULT_GRACE = 25.0        # Wartezeit "kein Tab offen" -> Beenden (gegen Reload/Blip).
_SELF_EXIT_DELAY = 6.0       # Absicherung ohne start.sh: danach selbst beenden.
_TCP_ESTABLISHED = "01"      # Zustandscode fuer ESTABLISHED in /proc/net/tcp.

_started = False
_start_lock = threading.Lock()


def _env_flag(name: str) -> bool:
    """Wahr nur bei explizit aktivierenden Werten. Wichtig: ein nicht-leerer String
    wie "0"/"false" ist in Python truthy - deshalb hier bewusst parsen, damit
    RAG_IDLE_SHUTDOWN=0 den Waechter TATSAECHLICH ausschaltet."""
    return (os.environ.get(name, "") or "").strip().lower() in ("1", "true", "yes", "on")


def _ui_port() -> int:
    try:
        return int(os.environ.get("RAG_UI_PORT", "") or 8501)
    except (TypeError, ValueError):
        return 8501


def _connected_client_count(port: int) -> "int | None":
    """Zahl bestehender TCP-Verbindungen zum UI-Port = offene Browser-Tabs (deren
    dauerhafte WebSocket-Verbindung). None nur bei komplettem Lesefehler."""
    target = f":{port:04X}".upper()          # z. B. Port 8501 -> ":2135"
    total = 0
    any_read = False
    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()[1:]    # Kopfzeile ueberspringen
        except FileNotFoundError:
            continue
        except Exception:  # noqa: BLE001
            return None
        any_read = True
        for line in lines:
            parts = line.split()
            if len(parts) < 4:
                continue
            local_addr, state = parts[1], parts[3]      # "0100007F:2135", "01"
            if state == _TCP_ESTABLISHED and local_addr.upper().endswith(target):
                total += 1
    return total if any_read else None


def _trigger_shutdown() -> None:
    """Beenden-Signal schreiben; als Absicherung danach den Prozess selbst beenden."""
    try:
        from ragapp.config import SHUTDOWN_SENTINEL
        SHUTDOWN_SENTINEL.parent.mkdir(parents=True, exist_ok=True)
        SHUTDOWN_SENTINEL.write_text("1", encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    # Falls kein externer Starter (start.sh-Waechter) mitliest: selbst beenden,
    # damit der Server nicht verwaist weiterlaeuft. start.sh raeumt via Trap den
    # Rest auf (Modell entladen). os._exit umgeht Streamlits Signal-Handler.
    time.sleep(_SELF_EXIT_DELAY)
    os._exit(0)


def _watch_loop(grace: float) -> None:
    port = _ui_port()
    seen_client = False
    idle_since: "float | None" = None
    while True:
        n = _connected_client_count(port)
        if n is None:
            return  # Verbindungszahl nicht lesbar -> Waechter beendet sich.
        if n > 0:
            seen_client = True
            idle_since = None
        elif seen_client:
            now = time.monotonic()
            if idle_since is None:
                idle_since = now
            elif now - idle_since >= grace:
                _trigger_shutdown()
                return
        time.sleep(_POLL_SECONDS)


def ensure_shutdown_watchdog() -> None:
    """Startet den Tab-Close-Waechter genau einmal pro Server-Prozess (idempotent).

    No-op, wenn RAG_IDLE_SHUTDOWN nicht gesetzt ist (nur der start.sh-Starter setzt
    es) oder RAG_NO_AUTO_SHUTDOWN=1 gesetzt wurde."""
    global _started
    if not _env_flag("RAG_IDLE_SHUTDOWN"):     # Standard AUS (auch bei "0"/leer)
        return
    if _env_flag("RAG_NO_AUTO_SHUTDOWN"):      # harter Aus-Schalter (Vorrang)
        return
    with _start_lock:
        if _started:
            return
        _started = True
        try:
            grace = float(os.environ.get("RAG_IDLE_SHUTDOWN_SECONDS", "") or _DEFAULT_GRACE)
        except (TypeError, ValueError):
            grace = _DEFAULT_GRACE
        threading.Thread(
            target=_watch_loop, args=(grace,),
            name="rag-idle-shutdown", daemon=True,
        ).start()
