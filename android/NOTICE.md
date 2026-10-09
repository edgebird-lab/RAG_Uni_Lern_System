# Lizenz und Drittkomponenten der Android-App „Local Study AI“

**Local Study AI** (Android, Paket `de.edgebird.lernsystem`) steht unter der **GNU General Public License, Version 3 oder (nach Wahl) jeder späteren Version** (`GPL-3.0-or-later`), siehe [LICENSE](LICENSE).
Copyright © 2026 Robin Olbricht – Olbricht Digital (edgebird-lab). Kontakt: kontakt@olbricht-digital.de.

Der **Quelltext** dieser Fassung liegt öffentlich unter https://github.com/edgebird-lab/RAG_Uni_Lern_System (Ordner `android/`). Jede veröffentlichte Version hat dort ein Tag
(`android-v<Versionsname>`, z. B. `android-v0.1.0`) mit genau dem Quelltext, aus dem die Version gebaut wurde. Bauanleitung: [README.md](README.md).

Die Lizenz gilt für den Quelltext der App. Die **Daten und Modelle**, die die App zur Laufzeit lädt oder mitbringt (KI-Modelle, Stimmen, Sprachdaten der Texterkennung), haben die unten genannten eigenen Lizenzen.
Die Texte in `eval/korpus/` (Gesetze gemeinfrei, Wikipedia-Artikel CC BY-SA 4.0) sind **keine** Bestandteile der App und stehen unter ihren eigenen Bedingungen (siehe `eval/korpus/QUELLEN.md`).

## Bestandteile der App

| Komponente | Zweck | Lizenz |
|---|---|---|
| Kotlin, Kotlin Coroutines, AndroidX (Activity, Lifecycle, Room, SQLite, WorkManager), Jetpack Compose, Material 3 | Grundgerüst | Apache-2.0 |
| Gson | JSON | Apache-2.0 |
| SQLite (gebündelt über `androidx.sqlite:sqlite-bundled`) | Datenbank, Volltextsuche (FTS5) | gemeinfrei |
| LiteRT-LM (Google AI Edge) | Ausführung der Sprach- und Embedding-Modelle auf dem Gerät | Apache-2.0 |
| PDFium (über `io.legere:pdfiumandroid`) | PDF-Text lesen | BSD-3-Clause und Apache-2.0 (PDFium bringt weitere freie Bibliotheken mit, u. a. FreeType (FTL), zlib, libjpeg-turbo, ICU) |
| Tesseract OCR, Leptonica, libjpeg-turbo, libpng über Tesseract4Android (adaptech-cz) | Texterkennung für Fotos und Scans | Apache-2.0 (Tesseract4Android, Tesseract), Leptonica-Lizenz (BSD-artig), IJG/BSD-3 (libjpeg-turbo), libpng-Lizenz |
| ONNX Runtime | Ausführung der Sprachsynthese-Modelle | MIT |
| sherpa-onnx (k2-fsa), Datei `Tts.kt` | Offline-Sprachausgabe (JNI-Bibliothek und Kotlin-Anbindung) | Apache-2.0 |
| **eSpeak NG** (in `libsherpa-onnx-jni.so` enthalten) und `espeak-ng-data` in den Stimmenpaketen | Aussprache (Phonemisierung) | **GPL-3.0 oder später** |
| Snowball-Stemmer (Deutsch, Englisch/Porter2), Port in `GermanStemmer.kt` und `EnglishStemmer.kt` | Wortstämme für die Stichwortsuche | BSD-3-Clause (Dr Martin Porter, Richard Boulton, Olly Betts u. a.) |
| FSRS-Algorithmus, Port von `py-fsrs` in `Fsrs.kt` | Planung der Karteikarten | MIT (Open Spaced Repetition) |

## Modelle und Daten (nicht im Quelltext, werden mitgeliefert oder nachgeladen)

| Daten | Lizenz |
|---|---|
| Gemma 4 E2B und EmbeddingGemma 2 (Google), unverändert als `.litertlm` aus `edgebird-lab/lernsystem-modelle` | Apache-2.0 |
| Sprachdaten der Texterkennung `deu.traineddata`, `eng.traineddata` (Tesseract `tessdata_best`) | Apache-2.0 |
| Stimmenpakete (optional): Piper-VITS-Modelle im Format von sherpa-onnx | Piper: MIT; Stimme „Thorsten“ (Thorsten-Voice): CC0 1.0; Stimme „LJSpeech“: gemeinfrei |
| `espeak-ng-data` in den Stimmenpaketen | GPL-3.0 oder später |

Die Lizenztexte stehen in der App unter „Über die App und Lizenz“ und im Ordner `app/src/main/assets/licenses/` (GPL-3.0, Apache-2.0, Hinweise zu MIT und BSD).

## Zur GPL und zum Quelltext der GPL-Bestandteile

Weil die App die Bibliothek eSpeak NG (GPL-3.0-or-later) in `libsherpa-onnx-jni.so` mitliefert, wird die App als Ganzes unter der GPL-3.0-or-later angeboten. Alle anderen mitgelieferten Bibliotheken stehen unter Lizenzen, die mit der GPL-3.0 verträglich sind (Apache-2.0, MIT, BSD, gemeinfrei); proprietäre Bibliotheken (z. B. Google ML Kit, Google Play Services) sind **nicht** enthalten.

Den vollständigen Quelltext (Corresponding Source) der mitgelieferten GPL-Bestandteile erhältst du so:

- **Diese App:** https://github.com/edgebird-lab/RAG_Uni_Lern_System, Tag `android-v<Version>`, Ordner `android/`.
- **sherpa-onnx** (die gebündelte `libsherpa-onnx-jni.so` und `libonnxruntime.so` stammen unverändert aus dem Release `v1.13.8`): https://github.com/k2-fsa/sherpa-onnx/tree/v1.13.8
- **eSpeak NG** (von sherpa-onnx verwendete Fassung, Fork `csukuangfj/espeak-ng`, Commit `ed530aa113046142eb5115cf2fc9157854d0ffe1`): https://github.com/csukuangfj/espeak-ng/tree/ed530aa113046142eb5115cf2fc9157854d0ffe1; Originalprojekt: https://github.com/espeak-ng/espeak-ng
- **Stimmenpakete** (Daten von eSpeak NG darin) und ihre Bauskripte: https://github.com/edgebird-lab/lernsystem-modelle

Auf Wunsch schicken wir den Quelltext auch auf einem Datenträger oder per E-Mail zu (kontakt@olbricht-digital.de). Du darfst die App unter den Bedingungen der GPL ändern und weitergeben.

## Hinweis für spätere Veröffentlichungen

Die GPL-3.0 verträgt sich nicht mit den Nutzungsbedingungen des Apple App Store. Eine iOS-Fassung (Plan, Phase 10) bräuchte eine andere Lösung (z. B. eine Sprachausgabe ohne eSpeak NG und die Zustimmung aller Rechteinhaber zu einer Ausnahme).
