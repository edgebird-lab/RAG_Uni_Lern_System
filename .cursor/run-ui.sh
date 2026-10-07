#!/usr/bin/env bash
# ============================================================================
#  .cursor/run-ui.sh  -  Startet die Streamlit-Weboberflaeche (als Terminal)
# ----------------------------------------------------------------------------
#  Wartet zuerst, bis der Ollama-Server (eigenes Terminal "Ollama") auf Port
#  11434 antwortet, damit das Vorwaermen von Embedding/Reranker beim Start nicht
#  ins Leere laeuft. Danach wird die App ueber das mitgelieferte start.sh
#  gestartet (bindet an 127.0.0.1:8501, RAG_LOCAL_ONLY=1). Headless-Modus
#  unterbindet den Streamlit-E-Mail-Prompt in der Cloud-Umgebung.
# ============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "[ui] Warte auf den Ollama-Server (Port 11434) ..."
for _ in $(seq 1 120); do
    if curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
        echo "[ui] Ollama erreichbar - starte die Weboberflaeche."
        break
    fi
    sleep 1
done

exec env STREAMLIT_SERVER_HEADLESS=true ./start.sh
