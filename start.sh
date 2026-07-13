#!/usr/bin/env bash
# ============================================================
#  RAG-Lernsystem - Kombi-Starter (Linux / macOS)
#  - Intel-Variante (ipex-ollama/ollama vorhanden):
#      startet den IPEX-GPU-Server im Hintergrund, wartet auf
#      Port 11434, dann die Weboberflaeche.
#  - Sonst (NVIDIA/AMD/Apple/CPU): nimmt an, dass der Ollama-
#      Dienst laeuft, und startet nur die Weboberflaeche.
#  Nutzt $(dirname "$0") -> voll portabel (kein fester Pfad).
# ============================================================
set -euo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
    DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
    SOURCE="$(readlink "$SOURCE")"
    [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
ROOT="$(cd -P "$(dirname "$SOURCE")" && pwd)"
cd "$ROOT"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
# Bei einem NATIVEN Absturz (Segfault in torch/chromadb o. ae.) druckt Python dank
# faulthandler noch einen Traceback ins Log, statt still zu sterben. So ist ein
# "Server antwortet nicht" nach dem Absturz nachvollziehbar.
export PYTHONFAULTHANDLER=1
# pyarrow den SYSTEM-Allocator nutzen lassen statt des gebuendelten jemalloc:
# jemalloc kollidiert mit torch (Reranker) im selben Prozess und liess den
# Streamlit-Server beim Rendern von Tabellen (st.dataframe -> pyarrow) nativ
# abstuerzen ("Server antwortet nicht", schon beim Reiter-Wechseln). config.py
# setzt das zusaetzlich per os.environ.setdefault; hier doppelt abgesichert, damit
# es garantiert VOR dem ersten pyarrow-Import steht (auch bei anderen Startwegen).
export ARROW_DEFAULT_MEMORY_POOL=system
# Reiner Einzelplatz-Betrieb: Streamlit bindet unten an 127.0.0.1 (nur dieser
# Rechner), daher ist KEIN Token/PIN nötig - die Oberfläche gibt sich direkt frei.
# (Der Handy-/Netzwerk-Zugriff mit PIN ist Windows-spezifisch über ragapp.desktop.)
export RAG_LOCAL_ONLY=1
# Tab-Close-Waechter (Auto-Beenden, wenn keine Browser-Verbindung mehr besteht) ist
# standardmaessig AUS: er beendete die App faelschlich schon, wenn der Browser den
# Tab nur kurz trennte/verwarf (z. B. Memory-Saver bei parallelen Apps) -> "Server
# antwortet nicht". Manuelles Beenden (In-App-Button "App beenden" oder stop.sh)
# raeumt weiterhin sauber auf (Modell entladen). Bewusst aktivieren: RAG_IDLE_SHUTDOWN=1 ./start.sh
export RAG_IDLE_SHUTDOWN="${RAG_IDLE_SHUTDOWN:-0}"

PY="$ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
    echo "[Fehler] Virtuelle Umgebung nicht gefunden: $PY" >&2
    echo "Bitte zuerst 'bash install.sh' ausfuehren." >&2
    exit 1
fi

# --- Doppelstart verhindern ------------------------------------------------- #
# Laeuft die Oberflaeche schon (Port 8501 antwortet), KEINE zweite Instanz
# starten - das wuerde nur an der Port-Bindung scheitern und beim Aufraeumen die
# bereits laufende Sitzung stoeren. Stattdessen das vorhandene Fenster oeffnen.
UI_PORT="${RAG_UI_PORT:-8501}"
if curl -fsS "http://127.0.0.1:${UI_PORT}/_stcore/health" >/dev/null 2>&1; then
    echo "[Hinweis] Die Oberflaeche laeuft bereits (Port ${UI_PORT}) - oeffne sie im Browser."
    command -v xdg-open >/dev/null 2>&1 && xdg-open "http://localhost:${UI_PORT}" >/dev/null 2>&1 || true
    exit 0
fi

if [ -x "$ROOT/ipex-ollama/ollama" ]; then
    echo "[Intel-GPU erkannt] IPEX-Ollama-Server wird verwendet."
    if curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
        echo "GPU-Server laeuft bereits."
    else
        echo "Starte IPEX-Ollama-Server im Hintergrund ..."
        OLLAMA_NUM_GPU=999 ZES_ENABLE_SYSMAN=1 ONEAPI_DEVICE_SELECTOR=level_zero:0 \
        OLLAMA_HOST=127.0.0.1:11434 OLLAMA_KEEP_ALIVE=30m OLLAMA_MAX_LOADED_MODELS=2 \
        "$ROOT/ipex-ollama/ollama" serve >"$ROOT/ipex-ollama-serve.log" 2>&1 &
        IPEX_OLLAMA_PID=$!
        echo "Warte, bis der GPU-Server bereit ist (Port 11434) ..."
        t=0
        while [ "$t" -lt 90 ]; do
            if curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
                echo "   -> GPU-Server bereit."; break
            fi
            sleep 1; t=$((t + 1))
        done
        if [ "$t" -ge 90 ]; then
            echo "[!] GPU-Server nicht erreichbar geworden - starte Oberflaeche trotzdem."
            echo "    Antworten laufen dann ggf. auf der CPU (siehe ipex-ollama-serve.log)."
        fi
    fi
else
    echo "[Standard-Ollama] Es wird angenommen, dass der Ollama-Dienst laeuft."
fi

# ============================================================
#  Sauberes Beenden: beim Schliessen der App wird die Weboberflaeche
#  gestoppt UND das in Ollama geladene Modell entladen (RAM/VRAM frei).
#  Der per systemd verwaltete Ollama-Dienst selbst bleibt unberuehrt
#  (Stoppen braeuchte Root; andere Nutzer wie local-agent bleiben heil).
# ============================================================
STREAMLIT_PID=""
WATCHER_PID=""

CLEANUP_TRIGGER=""
cleanup() {
    trap - EXIT INT TERM
    # Ausloeser merken (wird unten in die zuverlaessige [Ende]-Zeile geschrieben):
    # TERM = Abmelden/Session-Ende, INT = Strg+C, EXIT = Streamlit war schon weg.
    CLEANUP_TRIGGER="${1:-EXIT}"
    # 1) Weboberflaeche (Streamlit) beenden.
    if [ -n "$STREAMLIT_PID" ] && kill -0 "$STREAMLIT_PID" 2>/dev/null; then
        kill "$STREAMLIT_PID" 2>/dev/null || true
        for _ in 1 2 3 4 5; do
            kill -0 "$STREAMLIT_PID" 2>/dev/null || break
            sleep 0.3
        done
        kill -9 "$STREAMLIT_PID" 2>/dev/null || true
    fi
    # 2) Nur den vom App-Starter selbst gestarteten IPEX-Ollama-Server stoppen
    #    (Intel-Pfad). Der Standard-/systemd-Ollama-Dienst wird NICHT angefasst.
    if [ -n "${IPEX_OLLAMA_PID:-}" ] && kill -0 "$IPEX_OLLAMA_PID" 2>/dev/null; then
        kill "$IPEX_OLLAMA_PID" 2>/dev/null || true
    fi
    # 3) In Ollama geladenes Modell sofort entladen (keep_alive=0) -> RAM/VRAM frei.
    "$PY" "$ROOT/ragapp/scripts/stop_ollama_standby.py" >/dev/null 2>&1 || true
    # 4) Hintergrund-Waechter und Beenden-Signal aufraeumen.
    if [ -n "$WATCHER_PID" ]; then kill "$WATCHER_PID" 2>/dev/null || true; fi
    rm -f "$ROOT/data/.shutdown" 2>/dev/null || true
}
# HUP wird BEWUSST ignoriert: ein geschlossenes oder verwaistes Terminal (z. B. beim
# Start uebers Desktop-Icon, wo gnome-terminal sich sofort abkoppelt) schickte sonst
# SIGHUP -> cleanup -> die App beendete sich "von selbst" ("Server antwortet nicht").
# Sauberes Beenden laeuft weiterhin ueber den In-App-Button (data/.shutdown), stop.sh
# und das echte Session-Ende (SIGTERM beim Abmelden).
trap '' HUP
trap 'cleanup INT'  INT
trap 'cleanup TERM' TERM
trap 'cleanup EXIT' EXIT

echo "Starte Weboberflaeche (http://localhost:8501) ..."
# --- Dauerhafte Logmitschrift -------------------------------------------------
# Weil das Icon die App ohne sichtbares Terminal startet (Terminal-Ausgabe geht
# verloren), wird ALLES zusaetzlich in eine Datei geschrieben. Stuerzt die App bei
# einer Aktion ab ("Server antwortet nicht"), steht der Grund (Traceback/Signal)
# hier drin. Das Log vom vorigen Lauf wird als .prev gesichert (geht beim Neustart
# also NICHT verloren).
LOGDIR="$ROOT/data/logs"
mkdir -p "$LOGDIR" 2>/dev/null || true
LOGFILE="$LOGDIR/streamlit.log"
[ -f "$LOGFILE" ] && mv -f "$LOGFILE" "$LOGFILE.prev" 2>/dev/null || true
echo "[Log] Diese Sitzung wird protokolliert in: $LOGFILE"
# An 127.0.0.1 binden: nur dieser Rechner erreicht die App (passt zu RAG_LOCAL_ONLY).
# KEIN 'exec' mehr: die Shell bleibt als schlanker Aufseher bestehen, damit beim
# Beenden (SIGTERM/HUP beim Abmelden, stop.sh, oder der In-App-Button) cleanup laeuft.
# -u (ungepuffert) + Prozess-Substitution mit tee: Ausgabe landet SOFORT im Log
# UND (falls doch ein Terminal sichtbar ist) auf dem Bildschirm. $! bleibt der
# Python-/Streamlit-Prozess (nicht tee), damit cleanup/wait weiter korrekt greifen.
rm -f "$ROOT/data/.shutdown" 2>/dev/null || true
"$PY" -u -m streamlit run "ragapp/ui/💬_Chat.py" --server.address 127.0.0.1 \
    > >(tee "$LOGFILE") 2>&1 &
STREAMLIT_PID=$!

# In-App-Button "App beenden" auf Linux wirksam machen: er schreibt data/.shutdown;
# dieser Waechter sieht das Signal und beendet Streamlit -> danach greift cleanup().
(
    while :; do
        if [ -f "$ROOT/data/.shutdown" ]; then
            kill "$STREAMLIT_PID" 2>/dev/null || true
            break
        fi
        sleep 1
    done
) &
WATCHER_PID=$!

# Auf die Oberflaeche warten. Endet sie (Button/Absturz/Kill), laeuft cleanup().
# '|| RC=$?' faengt den Endcode ab, OHNE dass 'set -e' hier vorzeitig abbricht.
RC=0
wait "$STREAMLIT_PID" || RC=$?
# Endcode ins Log schreiben - das verraet die Absturzart:
#   0   = normal beendet (Button/stop.sh)
#   139 = Segfault (128+11, nativer Crash z. B. in torch/chromadb)
#   137 = hart abgeschossen (128+9, meist OOM-Killer / kill -9)
#   134 = Abort (128+6)
{ echo "[Ende] Streamlit-Prozess beendet mit Code $RC${CLEANUP_TRIGGER:+ (Aufraeumen ausgeloest durch $CLEANUP_TRIGGER)} ($(date '+%Y-%m-%d %H:%M:%S'))."; } >>"$LOGFILE" 2>/dev/null || true
