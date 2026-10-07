# RAG-Lernsystem Android (Lite)

Abgespeckte, komplett lokale Android-Version des RAG-Lernsystems: Dokumente importieren, Chat mit Quellen (RAG), Karteikarten mit FSRS-6. Die KI (Gemma 4 E2B plus EmbeddingGemma 2) läuft auf dem Gerät, es gibt keine Cloud-Abhängigkeit.

**Stand:** Phasen 0 bis 5 des [Plans](docs/PLAN.md) sind umgesetzt (Import, hybride Suche, Chat, Karteikarten). Zusammenfassungen (Phase 6), Pomodoro (7), Modell-Download in der App (8) und der Store-Release (9) fehlen noch.

## Bauen und installieren

```bash
cd android
export ANDROID_HOME=$HOME/android-sdk
./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk   # -r behält die App-Daten
```

Tests: `./gradlew :core:test testDebugUnitTest` (JVM) und `./gradlew :data:connectedDebugAndroidTest :ingest:connectedDebugAndroidTest` (Gerät).

## Modelle (bis zum Download in Phase 8 manuell)

Die App erwartet die Modelle im privaten App-Ordner `files/models/`. Quelle: Hugging Face `litert-community` (Apache 2.0).

| Datei | Größe | Zweck |
|---|---|---|
| `gemma-4-E2B-it.litertlm` | 2,6 GB | Sprachmodell |
| `embeddinggemma-2-text-270m.litertlm` | 165 MB | Embeddings |

```bash
adb push gemma-4-E2B-it.litertlm /data/local/tmp/
adb shell "run-as de.edgebird.lernsystem sh -c 'mkdir -p files/models && cp /data/local/tmp/gemma-4-E2B-it.litertlm files/models/'"
```

**Achtung:** „Daten löschen“ in den Android-Einstellungen oder ein Deinstallieren entfernt auch die Modelle (und den GPU-Cache); danach müssen sie erneut per adb aufgespielt werden und der erste Start dauert wieder 5 bis 10 Minuten. Zum Zurücksetzen der Inhalte reichen in der App „Löschen“ bei den Dokumenten und Karten.

## Gut zu wissen

- Das Display muss bei langen Hintergrundjobs (Indexieren, Karten erzeugen) an bleiben, sonst bremst die GPU stark.
- Beim ersten Start nach einer Neuinstallation optimiert die App das Sprachmodell für die GPU (5 bis 10 Minuten, einmalig).
- Messergebnisse: [RAG_EVAL](docs/RAG_EVAL.md), [KARTEN_EVAL](docs/KARTEN_EVAL.md), [SPIKE_ERGEBNIS](docs/SPIKE_ERGEBNIS.md).

Persönliche Unterlagen und Eval-Daten gehören nach `eval/private/` (nicht versioniert).
