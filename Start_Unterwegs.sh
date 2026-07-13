#!/usr/bin/env bash
# ============================================================
#  RAG-Lernsystem - Start MIT Zugriff von UNTERWEGS (Cloudflare)
#  Baut einen sicheren Cloudflare-Tunnel auf: die App bekommt eine
#  oeffentliche https-Adresse. Adresse + QR-Code stehen dann in der
#  App unter Einstellungen -> Handy-Zugriff. Die PIN-Sperre ist aktiv
#  (das Handy braucht den PIN; dieser PC nicht - dank lokalem Token).
#
#  Laeuft ueber ragapp.desktop (NICHT start.sh): nur dieser Starter bindet
#  sicher, verwaltet Token/PIN und baut den Tunnel. cloudflared muss
#  installiert sein (install.sh erledigt das, legt es nach ~/.local/bin).
#  (Hinweis: Die trycloudflare-Adresse aendert sich pro Start.)
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
# pyarrow-Allocator auf system (verhindert jemalloc/torch-Segfault, s. config.py/start.sh)
export ARROW_DEFAULT_MEMORY_POOL=system
# cloudflared liegt nach install.sh unter ~/.local/bin - sicherstellen, dass es auf PATH ist.
export PATH="$HOME/.local/bin:$PATH"

PY="$ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
    echo "[Fehler] Virtuelle Umgebung nicht gefunden: $PY" >&2
    echo "Bitte zuerst 'bash install.sh' ausfuehren." >&2
    exit 1
fi

if ! command -v cloudflared >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/cloudflared" ]; then
    echo "[Hinweis] 'cloudflared' ist nicht installiert - der Tunnel kann nicht aufgebaut werden."
    echo "          Fuehre 'bash install.sh' aus (installiert cloudflared automatisch) oder lade es:"
    echo "          https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
fi

echo "============================================================"
echo "  RAG-Lernsystem - Zugriff von UNTERWEGS (Cloudflare) AKTIV"
echo "  Oeffentliche Adresse + QR-Code:  in der App unter"
echo "  Einstellungen  ->  Handy-Zugriff"
echo "  (PIN vorher setzen! Die Adresse aendert sich pro Start.)"
echo "============================================================"

# ragapp.desktop startet Streamlit (an 0.0.0.0), setzt das lokale Token, baut den
# Cloudflare-Tunnel und schreibt die Adresse nach data/tunnel_url.txt -> die App
# zeigt dann automatisch QR-Code + Adresse an.
export RAG_NETWORK=1
export RAG_TUNNEL=1
exec "$PY" -m ragapp.desktop
