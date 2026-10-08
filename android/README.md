# RAG-Lernsystem Android (Lite)

Abgespeckte, komplett lokale Android-Version des RAG-Lernsystems: Dokumente importieren, Chat mit Quellen (RAG), Karteikarten mit FSRS-6. Die KI (Gemma 4 E2B plus EmbeddingGemma 2) läuft auf dem Gerät, es gibt keine Cloud-Abhängigkeit.

**Stand:** Phasen 0 bis 8 des [Plans](docs/PLAN.md) sind umgesetzt (Import, hybride Suche, Chat, Karteikarten, Zusammenfassungen, Fokus-Timer, Fächer, Spracheingabe, sokratische Abfragen; Konzept in [DESIGN.md](docs/DESIGN.md)). Der Store-Release (Phase 9) fehlt noch.

## Bauen und installieren

```bash
cd android
export ANDROID_HOME=$HOME/android-sdk
./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk   # -r behält die App-Daten
```

Tests: `./gradlew :core:test testDebugUnitTest` (JVM) und `./gradlew :data:connectedDebugAndroidTest :ingest:connectedDebugAndroidTest` (Gerät).

## Modelle

Beim ersten Start lädt die App die Modelle selbst aus dem Release von [edgebird-lab/lernsystem-modelle](https://github.com/edgebird-lab/lernsystem-modelle) (Apache 2.0, unverändert von `litert-community`): `gemma-4-E2B-it.litertlm` (2,6 GB, Sprachmodell) und `embeddinggemma-2-text-270m.litertlm` (165 MB, Embeddings). Der Assistent zeigt Gerät, Speicher und Lizenz; geladen wird standardmäßig nur im WLAN, mit Fortsetzen nach Abbruch und SHA-256-Prüfung. Später prüft „KI-Modelle“ im Tab Dokumente auf Updates.

Die Berechtigung `INTERNET` wird **nur** dafür benutzt. Dokumente, Chats und Karten verlassen das Gerät nie.

Zum Testen ohne Download lassen sich die Dateien auch per adb in den App-Ordner `files/models/` legen (die App erkennt sie an Name und Größe):

```bash
adb push gemma-4-E2B-it.litertlm /data/local/tmp/
adb shell "run-as de.edgebird.lernsystem sh -c 'mkdir -p files/models && cp /data/local/tmp/gemma-4-E2B-it.litertlm files/models/'"
```

**Achtung:** „Daten löschen“ in den Android-Einstellungen oder ein Deinstallieren entfernt auch die Modelle (und den GPU-Cache); danach lädt der Assistent sie neu und der erste Start dauert wieder 5 bis 10 Minuten. Zum Zurücksetzen der Inhalte reichen in der App „Löschen“ bei den Dokumenten und Karten.

## Gut zu wissen

- Das Display muss bei langen Hintergrundjobs (Indexieren, Karten erzeugen) an bleiben, sonst bremst die GPU stark.
- Beim ersten Start nach einer Neuinstallation optimiert die App das Sprachmodell für die GPU (5 bis 10 Minuten, einmalig).
- Fokus-Timer: genaue Alarme (Android-Einstellung „Alarme und Erinnerungen“) lassen das Phasenende pünktlich melden; ohne sie kann es einige Minuten dauern. Der Timer läuft zeitstempelbasiert, die App muss dafür nicht offen sein. Gerätetest mit kurzen Dauern: `adb shell am start -W -n de.edgebird.lernsystem/.spike.DebugPomodoroActivity --ei focus 15 --ei short 8` (nur Debug-Build).
- Messergebnisse: [RAG_EVAL](docs/RAG_EVAL.md), [KARTEN_EVAL](docs/KARTEN_EVAL.md), [SPIKE_ERGEBNIS](docs/SPIKE_ERGEBNIS.md).

Persönliche Unterlagen und Eval-Daten gehören nach `eval/private/` (nicht versioniert).
