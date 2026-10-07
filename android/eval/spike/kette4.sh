#!/usr/bin/env bash
set -u
cd "$(dirname "$0")"
export PATH="$HOME/android-sdk/platform-tools:$PATH"
until grep -q "KETTE-FERTIG" kette3.log; do sleep 5; done
adb install -r ../../app/build/outputs/apk/debug/app-debug.apk
DUMP=true ./run_embed.sh emb-dump-768-raw gpu 768 false 512 16 3012 2400
echo KETTE-FERTIG
