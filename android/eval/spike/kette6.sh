#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
# SPDX-License-Identifier: GPL-3.0-or-later
# Prompt-/Top-k-Experimente fuer die RAG-Auswertung (Phase 4, offene Punkte)
set -u
cd "$(dirname "$0")"
export PATH="$HOME/android-sdk/platform-tools:$PATH"
adb shell input keyevent KEYCODE_WAKEUP
adb install -r ../../app/build/outputs/apk/debug/app-debug.apk >/dev/null
run() { # tag topk style
  adb shell am force-stop de.edgebird.lernsystem; adb shell am start -n de.edgebird.lernsystem/.MainActivity >/dev/null; sleep 3
  adb logcat -c
  adb shell am start -n de.edgebird.lernsystem/.spike.SpikeRagEvalActivity --es tag "$1" --ei n 102 --ei topk "$2" --es style "$3" >/dev/null
  for i in $(seq 1 120); do adb logcat -d -s SPIKE:I | grep -q "FERTIG $1" && break; sleep 10; done
  adb exec-out run-as de.edgebird.lernsystem cat "files/spike/$1.json" > "$1.json"
}
run rag-lenient-k4 4 lenient
run rag-strict-k6 6 strict
run rag-lenient-k6 6 lenient
echo KETTE-FERTIG
