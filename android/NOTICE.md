# Drittkomponenten der Android-App

| Komponente | Zweck | Lizenz |
|---|---|---|
| LiteRT-LM (Google), Gemma 4 E2B, EmbeddingGemma 2 | Sprach- und Embedding-Modell | Apache-2.0 |
| sherpa-onnx (k2-fsa), ONNX Runtime | Offline-Sprachausgabe (Native Bibliotheken, `Tts.kt`) | Apache-2.0 / MIT |
| **espeak-ng** (in sherpa-onnx enthalten) und `espeak-ng-data` im Stimmenpaket | Aussprache (Phonemisierung) für die Stimme | **GPL-3.0 oder später** |
| Piper-Modell „Thorsten (de_DE, medium)“, Datensatz Thorsten-Voice | Stimme | MIT (Piper), CC0 (Daten) |
| PDFium (pdfium-android) | PDF-Text | BSD-3 / Apache-2.0 |
| ML Kit Text Recognition (Latein, gebündelt) | Texterkennung für Fotos und Scans | Google ML Kit Terms |
| AndroidX, Jetpack Compose, Room, WorkManager | Grundgerüst | Apache-2.0 |

**Hinweis zur GPL:** `libsherpa-onnx-jni.so` enthält espeak-ng. Wer die App als Binärdatei weitergibt, muss für diesen Teil die Bedingungen der GPL-3.0-oder-später einhalten (insbesondere das Angebot des Quelltextes von sherpa-onnx und espeak-ng: https://github.com/k2-fsa/sherpa-onnx, https://github.com/espeak-ng/espeak-ng). Der eigene Quelltext dieses Repos steht unter der MIT-Lizenz; die MIT-Lizenz ist mit der GPL-3.0 verträglich, die weitergegebene Gesamtdatei (App-Binärdatei) unterliegt aber den Bedingungen der GPL. **Stand der Entscheidung:** Die Stimmen (Modelle und `espeak-ng-data`) sind ein **Zusatzpaket**, das man beim Download der KI-Modelle auswählt oder später unter „KI-Modelle“ lädt; der Standard ist „aus“. Die Bibliothek `libsherpa-onnx-jni.so` mit espeak-ng liegt aber weiterhin in der APK, weil Android keine nachgeladenen nativen Bibliotheken ausführen lässt. Für eine vollständige Trennung müsste die Bibliothek in ein Play-Feature-Modul (on demand) ausgelagert werden; das gibt es nur über den Play Store (AAB), nicht für eine direkt installierte APK. Bis dahin gilt für die Weitergabe der APK die GPL-Regel für diesen Teil (Quelltext-Angebot, siehe oben).
