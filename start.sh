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

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
# Reiner Einzelplatz-Betrieb: Streamlit bindet unten an 127.0.0.1 (nur dieser
# Rechner), daher ist KEIN Token/PIN nötig - die Oberfläche gibt sich direkt frei.
# (Der Handy-/Netzwerk-Zugriff mit PIN ist Windows-spezifisch über ragapp.desktop.)
export RAG_LOCAL_ONLY=1

PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

if [ -x "$ROOT/ipex-ollama/ollama" ]; then
    echo "[Intel-GPU erkannt] IPEX-Ollama-Server wird verwendet."
    if curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
        echo "GPU-Server laeuft bereits."
    else
        echo "Starte IPEX-Ollama-Server im Hintergrund ..."
        ( cd "$ROOT/ipex-ollama" && \
          OLLAMA_NUM_GPU=999 ZES_ENABLE_SYSMAN=1 ONEAPI_DEVICE_SELECTOR=level_zero:0 \
          OLLAMA_HOST=127.0.0.1:11434 OLLAMA_KEEP_ALIVE=30m OLLAMA_MAX_LOADED_MODELS=2 \
          ./ollama serve >"$ROOT/ipex-ollama-serve.log" 2>&1 & )
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

echo "Starte Weboberflaeche (http://localhost:8501) ..."
# An 127.0.0.1 binden: nur dieser Rechner erreicht die App (passt zu RAG_LOCAL_ONLY).
exec "$PY" -m streamlit run "ragapp/ui/Home.py" --server.address 127.0.0.1
