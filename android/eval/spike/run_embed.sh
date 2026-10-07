#!/usr/bin/env bash
# Aufruf: run_embed.sh <tag> <cpu|gpu> <dim> <prefix true|false> <maxlen> <batch> <limit> [timeout_s]
set -euo pipefail
export PATH="$HOME/android-sdk/platform-tools:$PATH"
tag=$1 backend=$2 dim=$3 prefix=$4 maxlen=$5 batch=$6 limit=$7 timeout=${8:-1200}
adb logcat -c
adb shell am force-stop de.edgebird.lernsystem
adb shell am start -n de.edgebird.lernsystem/.spike.SpikeEmbedActivity --es model embeddinggemma-2-text-270m.litertlm --es backend "$backend" --ei dim "$dim" --ez prefix "$prefix" --ei maxlen "$maxlen" --ei batch "$batch" --ei limit "$limit" --es tag "$tag" --ez dump "${DUMP:-false}" >/dev/null
end=$((SECONDS + timeout))
until adb logcat -d -s SPIKE:I | grep -q "FERTIG $tag"; do
  if (( SECONDS > end )); then echo "TIMEOUT $tag"; adb logcat -d -s SPIKE:I | tail -3; exit 1; fi
  sleep 4
done
adb exec-out run-as de.edgebird.lernsystem cat "files/spike/$tag.json" > "$(dirname "$0")/$tag.json"
[ "${DUMP:-false}" = true ] && adb exec-out run-as de.edgebird.lernsystem cat "files/spike/$tag.vec" > "$(dirname "$0")/$tag.vec" || true
adb logcat -d -s SPIKE:I | grep -E "geladen|FEHLER|Dokumente|FERTIG" | sed 's/^.*SPIKE *: //'
