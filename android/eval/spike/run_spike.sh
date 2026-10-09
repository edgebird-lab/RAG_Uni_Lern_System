#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
# SPDX-License-Identifier: GPL-3.0-or-later
# Startet einen Spike-Lauf auf dem Pixel und holt das Ergebnis.
# Aufruf: run_spike.sh <tag> <modell-datei> <cpu|gpu> <mtp true|false> <n> [timeout_s]
set -euo pipefail
export PATH="$HOME/android-sdk/platform-tools:$PATH"
tag=$1 model=$2 backend=$3 mtp=$4 n=$5 timeout=${6:-1500}
adb logcat -c
adb shell am force-stop de.edgebird.lernsystem
adb shell am start -n de.edgebird.lernsystem/.spike.SpikeActivity --es model "$model" --es backend "$backend" --ez mtp "$mtp" --ei n "$n" --es tag "$tag" >/dev/null
end=$((SECONDS + timeout))
until adb logcat -d -s SPIKE:I | grep -q "FERTIG $tag"; do
  if (( SECONDS > end )); then echo "TIMEOUT $tag"; exit 1; fi
  sleep 5
done
adb exec-out run-as de.edgebird.lernsystem cat "files/spike/$tag.json" > "$(dirname "$0")/$tag.json"
adb logcat -d -s SPIKE:I | grep -E "geladen|FEHLER|FERTIG" | sed 's/^.*SPIKE *: //'
