#!/usr/bin/env bash
# ============================================================================
#  .cursor/start.sh  -  Pro-Boot-Start der Laufzeitdienste
# ----------------------------------------------------------------------------
#  Startet den Ollama-Server (LLM/Embedding-Backend) im Hintergrund, weil in der
#  Cloud-Umgebung kein systemd laeuft. Idempotent: laeuft der Server schon,
#  passiert nichts. Die Weboberflaeche (Streamlit) laeuft separat als Terminal
#  (siehe .cursor/environment.json -> "terminals"), damit ihre Logs sichtbar
#  bleiben und sie neu gestartet werden kann.
# ============================================================================
set -euo pipefail

if curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
    echo "[start] Ollama laeuft bereits (Port 11434)."
    exit 0
fi

echo "[start] Starte Ollama-Server im Hintergrund ..."
nohup ollama serve >/tmp/ollama-serve.log 2>&1 &

for _ in $(seq 1 60); do
    if curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
        echo "[start] Ollama bereit (Port 11434)."
        exit 0
    fi
    sleep 1
done

echo "[start] [!] Ollama wurde nicht rechtzeitig erreichbar (siehe /tmp/ollama-serve.log)." >&2
exit 1
