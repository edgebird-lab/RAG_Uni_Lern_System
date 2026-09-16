#!/usr/bin/env bash
# ============================================================================
#  .cursor/install.sh  -  Cloud-Agent-Setup fuer das RAG-Lernsystem
# ----------------------------------------------------------------------------
#  Idempotenter Bootstrap fuer die Cursor-Cloud-Umgebung (Linux, CPU-only):
#    1. System-Pakete (python venv, Build-Tools, zstd fuer Ollama, ffmpeg)
#    2. .venv + PyTorch (CPU) + chatterbox-tts (--no-deps) + requirements.txt
#    3. Ollama installieren, Server kurz starten und Modelle ziehen
#       (bge-m3 Embedding + gemma3:4b LLM = config.py-Standardwerte)
#    4. Cross-Encoder-Reranker (BAAI/bge-reranker-v2-m3) vorab in den
#       HF-Cache laden, damit die erste echte Frage keinen Download zahlt.
#
#  Laeuft einmalig beim Erstellen des Environment-Builds (Snapshot). Alles,
#  was hier auf Platte landet (.venv, ~/.ollama Modelle, ~/.cache/huggingface),
#  bleibt im Snapshot erhalten. Laufzeit-Dienste startet ".cursor/start.sh".
# ============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VENV_PY="$ROOT/.venv/bin/python"

log() { printf '\n==> %s\n' "$1"; }

# ---- 1) System-Pakete ------------------------------------------------------ #
log "System-Pakete installieren (venv, Build-Tools, zstd, ffmpeg)"
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3-venv python3-dev build-essential \
    zstd ffmpeg curl ca-certificates

# ---- 2) Virtuelle Umgebung + Python-Abhaengigkeiten ------------------------ #
log "Virtuelle Umgebung (.venv) einrichten"
if [ ! -x "$VENV_PY" ]; then
    python3 -m venv .venv
fi
"$VENV_PY" -m pip install --upgrade pip setuptools wheel

log "PyTorch (CPU-Build) installieren"
if ! "$VENV_PY" -c "import torch, torchvision, torchaudio" >/dev/null 2>&1; then
    "$VENV_PY" -m pip install "torch>=2.6,<3" "torchvision<1" "torchaudio>=2.6,<3" \
        --index-url https://download.pytorch.org/whl/cpu
fi

log "chatterbox-tts (--no-deps, Audio-Overview-TTS) installieren"
"$VENV_PY" -m pip install "chatterbox-tts==0.1.7" --no-deps
# resemble-perth importiert pkg_resources -> setuptools unter 81 halten.
"$VENV_PY" -m pip install "setuptools<81" -q

log "Restliche Abhaengigkeiten (requirements.txt) installieren"
"$VENV_PY" -m pip install -r requirements.txt

# ---- 3) Ollama installieren + Modelle ziehen ------------------------------- #
log "Ollama einrichten"
if ! command -v ollama >/dev/null 2>&1; then
    curl -fsSL https://ollama.com/install.sh | sh
fi

# Ollama-Server nur fuer die Modell-Downloads temporaer starten (systemd laeuft
# in der Cloud-Umgebung nicht; der Dauerbetrieb wird von start.sh uebernommen).
OLLAMA_PID=""
if ! curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
    ollama serve >/tmp/ollama-install.log 2>&1 &
    OLLAMA_PID=$!
    for _ in $(seq 1 60); do
        curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1 && break
        sleep 1
    done
fi

log "Modelle ziehen (bge-m3 Embedding, gemma3:4b LLM)"
ollama pull bge-m3
ollama pull gemma3:4b

if [ -n "$OLLAMA_PID" ]; then
    # Nur den hier gestarteten temporaeren Server beenden (per PID, nicht per
    # Name) - start.sh startet ihn pro Boot ohnehin neu.
    kill "$OLLAMA_PID" 2>/dev/null || true
fi

# ---- 4) Reranker vorab in den HF-Cache laden ------------------------------- #
log "Cross-Encoder-Reranker vorab herunterladen (HF-Cache)"
"$VENV_PY" - <<'PY' || echo "    [!] Reranker-Prefetch uebersprungen (wird sonst beim ersten Retrieval geladen)."
from sentence_transformers import CrossEncoder
CrossEncoder("BAAI/bge-reranker-v2-m3")
print("    Reranker im Cache.")
PY

log "Setup abgeschlossen."
