#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
# SPDX-License-Identifier: GPL-3.0-or-later
set -u
cd "$(dirname "$0")"
export PATH="$HOME/android-sdk/platform-tools:$PATH"
adb shell am force-stop de.edgebird.lernsystem
adb push ~/lernsystem-modelle/e4b/gemma-4-E4B-it.litertlm /data/local/tmp/
adb shell "run-as de.edgebird.lernsystem sh -c 'cp /data/local/tmp/gemma-4-E4B-it.litertlm files/models/'" && adb shell rm /data/local/tmp/gemma-4-E4B-it.litertlm
./run_spike.sh e4b-gpu-mtp gemma-4-E4B-it.litertlm gpu true 21 4200
echo KETTE-FERTIG
