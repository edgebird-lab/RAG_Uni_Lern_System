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
# Reiner Einzelplatz-Betrieb: Streamlit bindet unten an 127.0.0.1 (nur dieser
# Rechner), daher ist KEIN Token/PIN nötig - die Oberfläche gibt sich direkt frei.
# (Der Handy-/Netzwerk-Zugriff mit PIN ist Windows-spezifisch über ragapp.desktop.)
export RAG_LOCAL_ONLY=1
# Tab-Close-Waechter im Server aktivieren: schliesst du das letzte Browser-Tab,
# schreibt die App data/.shutdown -> der Waechter unten stoppt Streamlit sauber.
export RAG_IDLE_SHUTDOWN=1

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

cleanup() {
    trap - EXIT INT TERM HUP
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
trap cleanup EXIT INT TERM HUP

echo "Starte Weboberflaeche (http://localhost:8501) ..."
# An 127.0.0.1 binden: nur dieser Rechner erreicht die App (passt zu RAG_LOCAL_ONLY).
# KEIN 'exec' mehr: die Shell bleibt als schlanker Aufseher bestehen, damit beim
# Beenden (SIGTERM/HUP beim Abmelden, stop.sh, oder der In-App-Button) cleanup laeuft.
rm -f "$ROOT/data/.shutdown" 2>/dev/null || true
"$PY" -m streamlit run "ragapp/ui/Home.py" --server.address 127.0.0.1 &
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
wait "$STREAMLIT_PID" || true
