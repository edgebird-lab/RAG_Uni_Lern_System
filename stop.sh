#!/usr/bin/env bash
# RAG-Lernsystem sauber beenden (Weboberflaeche auf Port 8501)
set -euo pipefail

PORT="${RAG_UI_PORT:-8501}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

stopped=0

if command -v fuser >/dev/null 2>&1; then
    if fuser "${PORT}/tcp" >/dev/null 2>&1; then
        echo "Beende Streamlit auf Port ${PORT} ..."
        fuser -k "${PORT}/tcp" >/dev/null 2>&1 || true
        stopped=1
    fi
fi

if pgrep -f "streamlit run.*ragapp/ui/Home.py" >/dev/null 2>&1; then
    echo "Beende verbleibende Streamlit-Prozesse ..."
    pkill -f "streamlit run.*ragapp/ui/Home.py" 2>/dev/null || true
    stopped=1
fi

rm -f "$ROOT/data/.shutdown" 2>/dev/null || true

# In Ollama geladenes Modell entladen (RAM/VRAM freigeben). Der Ollama-Dienst
# selbst bleibt laufen (per systemd verwaltet; Stoppen braeuchte Root) - andere
# lokale Ollama-Nutzer/-Tools werden dadurch NICHT gestoert.
PY="$ROOT/.venv/bin/python"
if [ -x "$PY" ] && [ -f "$ROOT/ragapp/scripts/stop_ollama_standby.py" ]; then
    "$PY" "$ROOT/ragapp/scripts/stop_ollama_standby.py" 2>/dev/null || true
fi

if [ "$stopped" = 1 ]; then
    sleep 1
    echo "RAG-Lernsystem (Weboberflaeche) wurde beendet."
else
    echo "RAG-Lernsystem laeuft nicht (Port ${PORT} frei)."
fi

echo ""
echo "Hinweis: Das lokale KI-Modell wurde aus dem Speicher entladen (RAM/VRAM frei)."
echo "         Der Ollama-Dienst selbst laeuft als systemd-Systemdienst weiter."
echo "         Vollstaendig abschalten (optional, braucht Root):"
echo "             sudo systemctl disable --now ollama"
