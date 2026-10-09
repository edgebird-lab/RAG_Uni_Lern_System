#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
# SPDX-License-Identifier: GPL-3.0-or-later
# Holt die Sprachdaten für die Texterkennung (Tesseract, tessdata_best, Apache-2.0) nach ingest/src/main/assets/tessdata.
# Die Dateien (24 MB) liegen nicht im Repo; der Gradle-Task `fetchTessdata` ruft dieses Skript bei Bedarf auf. Quelle: https://github.com/tesseract-ocr/tessdata_best
set -euo pipefail
cd "$(dirname "$0")/.."
DEST="ingest/src/main/assets/tessdata"
REV="4.1.0"   # Tag des Repos tessdata_best
DEU_SHA="8407331d6aa0229dc927685c01a7938fc5a641d1a9524f74838cdac599f0d06e"
ENG_SHA="8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba"
check() { [ -f "$DEST/$1.traineddata" ] && [ "$(sha256sum "$DEST/$1.traineddata" | cut -d' ' -f1)" = "$2" ]; }
if check deu "$DEU_SHA" && check eng "$ENG_SHA"; then exit 0; fi
mkdir -p "$DEST"
for pair in "deu:$DEU_SHA" "eng:$ENG_SHA"; do
  lang="${pair%%:*}"; sha="${pair##*:}"
  echo "Lade $lang.traineddata …"
  curl -fL --retry 3 -o "$DEST/$lang.traineddata" "https://github.com/tesseract-ocr/tessdata_best/raw/$REV/$lang.traineddata"
  check "$lang" "$sha" || { echo "Prüfsumme von $lang.traineddata stimmt nicht" >&2; rm -f "$DEST/$lang.traineddata"; exit 1; }
done
