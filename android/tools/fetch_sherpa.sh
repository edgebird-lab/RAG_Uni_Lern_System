#!/usr/bin/env bash
# Holt die nativen Bibliotheken von sherpa-onnx (Apache-2.0, k2-fsa) für die Offline-Sprachausgabe nach ai/src/main/jniLibs/arm64-v8a.
# Sie liegen nicht im Repo (27 MB); der Gradle-Task `fetchSherpa` ruft dieses Skript bei Bedarf auf.
set -euo pipefail
cd "$(dirname "$0")/.."
VER="v1.13.8"
DEST="ai/src/main/jniLibs/arm64-v8a"
ORT_SHA="33847ad43bffe204699fd4a27f7f3603452a8cdaf2f9a44983a0bc31ffcf2da1"
JNI_SHA="3c6492ea91ea68fd3b72b9495efdde6dd913f6b58c387e3b07389cf335f4d26f"
ok() { [ -f "$DEST/libonnxruntime.so" ] && [ -f "$DEST/libsherpa-onnx-jni.so" ] && \
  [ "$(sha256sum "$DEST/libonnxruntime.so" | cut -d' ' -f1)" = "$ORT_SHA" ] && [ "$(sha256sum "$DEST/libsherpa-onnx-jni.so" | cut -d' ' -f1)" = "$JNI_SHA" ]; }
if ok; then exit 0; fi
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/$VER/sherpa-onnx-$VER-android.tar.bz2"
echo "Lade sherpa-onnx $VER …"
curl -fL --retry 3 -o "$TMP/s.tar.bz2" "$URL"
mkdir -p "$DEST"
tar -xjf "$TMP/s.tar.bz2" -C "$TMP" ./jniLibs/arm64-v8a/libonnxruntime.so ./jniLibs/arm64-v8a/libsherpa-onnx-jni.so
cp "$TMP/jniLibs/arm64-v8a/libonnxruntime.so" "$TMP/jniLibs/arm64-v8a/libsherpa-onnx-jni.so" "$DEST/"
ok || { echo "Prüfsumme der sherpa-onnx-Bibliotheken stimmt nicht" >&2; rm -f "$DEST"/*.so; exit 1; }
