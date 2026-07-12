#!/usr/bin/env bash
# ============================================================
#  build_setup.sh - Windows-Installer-EXE unter Linux/macOS bauen
#  Kompiliert setup.iss mit Inno Setup in einem Docker-Container
#  (amake/innosetup) - KEINE lokale Wine-/Inno-Installation noetig.
#  Ergebnis: installer/RAG-Lernsystem-Setup.exe (+ Kopie in ~/Downloads).
#
#  WICHTIG: LANG/LC_ALL=C.UTF-8 muss gesetzt sein, sonst kann Wine die
#  Emoji-Seitennamen (z. B. ragapp/ui/pages/1_📥_Ingestion.py) nicht lesen
#  ("Invalid name"). Auf echtem Windows baut Build_Setup.bat dieselbe EXE.
#
#  Aufruf:  ./build_setup.sh
#  Voraussetzung: laufender Docker-Daemon.
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

IMAGE="amake/innosetup:latest"
EXE="installer/RAG-Lernsystem-Setup.exe"

echo "== Baue $EXE via Docker ($IMAGE) =="
docker run --rm -e LANG=C.UTF-8 -e LC_ALL=C.UTF-8 -v "$PWD":/work "$IMAGE" setup.iss

if [ ! -f "$EXE" ]; then
    echo "[X] EXE wurde nicht erzeugt." >&2
    exit 1
fi
echo "[OK] $EXE  ($(du -h "$EXE" | cut -f1))"

# Fertige EXE zusaetzlich nach ~/Downloads kopieren (zum Weitergeben an den Laptop).
if [ -d "$HOME/Downloads" ]; then
    cp -f "$EXE" "$HOME/Downloads/RAG-Lernsystem-Setup.exe" \
        && echo "[OK] kopiert -> $HOME/Downloads/RAG-Lernsystem-Setup.exe"
fi
