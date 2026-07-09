#!/usr/bin/env bash
# ============================================================================
#  build_linux.sh  -  Baut das Linux/macOS-Distributionspaket (Quell-Tarball)
# ============================================================================
#  Erzeugt installer/RAG-Lernsystem-Linux.tar.gz NUR aus den von Git getrackten
#  Dateien. Dadurch sind persoenliche Unterlagen (Zusammenfassungen*), die
#  Datenbank (data/), die virtuelle Umgebung (.venv) und die Ollama-Binaries
#  (ipex-ollama/) automatisch NICHT enthalten - sie sind in .gitignore.
#
#  Nutzung (auf Windows in Git-Bash oder auf Linux):
#      bash build_linux.sh
#
#  Der Empfaenger entpackt das Archiv und richtet alles ein:
#      tar xzf RAG-Lernsystem-Linux.tar.gz
#      cd RAG-Lernsystem
#      bash install.sh          # baut .venv, installiert Ollama + Modelle
#      ./start.sh               # startet die Oberflaeche
# ============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if ! command -v git >/dev/null 2>&1; then
    echo "[Fehler] git wird benoetigt." >&2
    exit 1
fi

mkdir -p installer
OUT="installer/RAG-Lernsystem-Linux.tar.gz"

# git archive nimmt ausschliesslich getrackte Dateien des aktuellen HEAD ->
# keine ungetrackten/ignorierten Dateien (data/, .venv, persoenliche Docs).
git archive --format=tar.gz -o "$OUT" --prefix=RAG-Lernsystem/ HEAD

SIZE="$(du -h "$OUT" | cut -f1)"
echo "Linux-Paket erstellt: $OUT  ($SIZE)"
echo "Enthaelt den Quellcode + install.sh/start.sh. Empfaenger: 'bash install.sh'."
