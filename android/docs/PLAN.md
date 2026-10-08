# Android-Plan: RAG-Lernsystem „Lite“ (komplett lokal)

Status: Entwurf, 2026-10-07. Zielgerät für alle Messungen: **Pixel 9 Pro XL** (Tensor G4, 16 GB RAM, Android 17).
iOS folgt erst, wenn Android steht. Die Architektur hält die Tür aber offen (siehe Abschnitt 2).

## 1. Zielumfang (Version 1.0)

Aus der PC-App wird bewusst nur der Kern übernommen:

| Funktion | PC-Vorbild | Android v1 |
|---|---|---|
| Dokumente importieren | `ingestion/loaders.py`, `chunker.py` | PDF, TXT, MD (DOCX/PPTX/OCR später) |
| Chat mit Quellen (RAG) | `graph/rag_graph.py` | Hybrid-Suche, 3–4 Chunks, Quellenangabe, „nicht im Material“ als Standardausgang |
| Karteikarten + Lernsystem | `study.py`, FSRS | Karten erzeugen, FSRS-Wiederholung, Tagesziel |
| Zusammenfassungen | `ingestion/summarize.py` | pro Dokument/Kapitel (Map-Reduce) |
| Pomodoro | neu | Timer, Benachrichtigungen, Lernzeit-Statistik |

**Bewusst nicht in v1:** Audio-Overview/Chatterbox, Vortrag/Talk, Mindmap, Sokratik, Lernplan-Karten, Prüfungsgenerator, Cloudflare-Tunnel, Websuche, Reranker, OCR.

**Grundregeln:** Alles läuft auf dem Gerät. Nach dem einmaligen Modell-Download braucht die App kein Netz. Keine Analytics, keine Cloud-APIs, keine Konten.

## 2. Architekturentscheidungen

1. **Kotlin, Gradle-Multi-Module.** `core` ist reines Kotlin/JVM ohne Android-Imports (Datenmodelle, Chunker, Fusion, Prompts, FSRS). So bleibt der Kern später für Kotlin Multiplatform/iOS übertragbar.
2. **Inferenz hinter Interfaces:** `LlmEngine` und `Embedder`. Zwei Kandidaten werden im Spike gemessen, nicht geraten:
   - **LiteRT-LM** (Google, Kotlin-API, `.litertlm`, nutzt GPU/NPU des Tensor G4)
   - **llama.cpp** (JNI, GGUF, einheitlich für Android und später iOS)
3. **Datenbank:** Room/SQLite mit FTS5 (BM25-Ersatz) plus Vektor-BLOB-Spalte, Brute-Force-Cosinus. Reicht für einige zehntausend Chunks.
4. **UI:** Jetpack Compose, Material 3, ein Activity-Single-Stack.
5. **Hintergrundarbeit:** WorkManager (Import, Embedding, Karten-Erzeugung), Foreground-Service für Pomodoro.
6. **Modelle werden nicht ins APK gepackt**, sondern in der App nachgeladen (Abschnitt 4).

Zielstruktur:

```
android/
  app/            Compose-UI, DI, Navigation
  core/           reines Kotlin: Modelle, Chunker, Fusion, Prompts, FSRS, Pomodoro-Logik
  ai/             LlmEngine, Embedder, Implementierungen, Model-Downloader
  data/           Room-DB, Repositories, Import
  eval/           Gold-Set + Skripte (nur synthetische/eigene Daten, nie ins Repo mit Fremdunterlagen)
  docs/PLAN.md
```

## 3. Modellwahl

- **LLM:** Gemma 4 E2B als Start (Apache 2.0, Weitergabe erlaubt, mit Lizenz- und Hinweistext). E4B als optionale Auswahl für das Pixel 9 Pro XL, falls das Tempo reicht. Die Entscheidung fällt im Spike.
- **Embeddings:** EmbeddingGemma (308M, mehrsprachig, 768 Dim, MRL auf 256/512 kürzbar). Alternative bge-m3 nur, wenn es mobil effizient läuft.
- **Quantisierung:** Erst fertige Q4-Varianten messen (Qualität, Tempo, RAM). Eigene Quantisierung/LoRA nur, wenn das Eval-Ergebnis es rechtfertigt.

## 4. Modell-Verteilung über GitHub (keine dritte Abhängigkeit)

Idee: Eigenes, kleines Repo (z. B. `edgebird-lab/lernsystem-modelle`), die Modelle liegen als **Release-Assets**. Die App lädt von dort, nicht von Hugging Face oder einer API.

Wichtige Fakten und Konsequenzen:
- Ein Release-Asset darf bis zu **2 GiB** groß sein. Größere Modelle werden in Teile (z. B. 500–1000 MB) gesplittet.
- Normale Repo-Dateien (100 MB-Limit) und Git-LFS (Kontingent) sind ungeeignet, nur Releases.
- **`manifest.json`** (im Repo, klein) beschreibt: Modell-ID, Version, Teile, URL(s), Größe, SHA-256, Lizenz, Mindest-RAM, Mindest-App-Version.
- Die App prüft Integrität per SHA-256, lädt **fortsetzbar** (HTTP Range), nur im WLAN als Standard, mit Speicherplatzprüfung.
- Das Manifest listet mehrere URLs (Primär: GitHub-Release, Fallback: Mirror), damit die App nicht von einer Quelle abhängt.
- Wir behalten das Modell in dem Format, das wir getestet haben. Eine Änderung der Quelle (HF, Google) kann so nichts brechen. Preis: Wir pflegen Konvertierung und Release selbst.
- **Lizenz:** Apache 2.0 verlangt Lizenztext und Hinweise. LICENSE und NOTICE liegen im Release und werden in der App angezeigt.
- Offene Prüfung: GitHub-Nutzungsbedingungen zu großen Binär-Downloads in öffentlichen Repos kurz gegenlesen, bevor die App viele Nutzer hat.

## 5. Arbeitsschritte

Jeder Schritt ist klein, einzeln testbar und endet mit einem überprüfbaren Ergebnis. Phasen 0 und 1 sind **Entscheidungstore**.

### Phase 0: Fundament

- [x] 0.1 SDK (Platform 36/37, Build-Tools 37, NDK 29, CMake 3.22), `adb` und Pixel 9 Pro XL (Android 17, API 37, 16 GB RAM) eingerichtet; `adb devices` zeigt das Gerät. Android Studio Rabbit 1 (2026.2.1) liegt unter `~/android-studio`.
- [x] 0.2 Gradle-Projekt `android/` mit leeren Modulen `app`, `core`, `ai`, `data` anlegen; „Hello Compose“ läuft auf dem Pixel.
- [x] 0.3 (Workflow `.github/workflows/android.yml`, noch nicht auf GitHub gelaufen) CI (GitHub Actions): `./gradlew test lint assembleDebug` bei jedem Push.
- [ ] 0.4 Code-Konventionen: ktlint/detekt, JUnit5, Kotlin-Coroutines/Flow.

### Phase 1: Spike „Läuft das Modell gut genug?“ (Tor 1)

- [x] 1.1 Interface `LlmEngine { generate(prompt, params): Flow<String>; cancel(); close() }` und `Embedder`.
- [x] 1.2 Modell manuell per `adb push` aufs Gerät legen (Downloader kommt später).
- [x] 1.3 Implementierung A: LiteRT-LM mit Gemma 4 E2B. Misst: Ladezeit, Tokens/s (Prefill + Decode), RAM-Spitze, Temperatur nach 5 Minuten.
- [ ] 1.4 (zurückgestellt, siehe `SPIKE_ERGEBNIS.md`) Implementierung B: llama.cpp (JNI) mit Gemma 4 E2B Q4_K_M. Gleiche Messungen.
- [x] 1.5 Embedding-Spike: EmbeddingGemma über beide Wege; Durchsatz (Chunks/s) und Vektor-Qualität (Paar-Ähnlichkeit auf deutschen Sätzen).
- [x] 1.6 E4B gegen E2B messen (Pixel hat 16 GB).
- [x] 1.7 **Entscheidung (LiteRT-LM + E2B, GPU, MTP):** Runtime (A oder B), Modellgröße, Mindest-RAM. Ergebnis als `docs/SPIKE_ERGEBNIS.md` mit Zahlen.
  Abbruchkriterium: weniger als ca. 8 Token/s Decode oder instabile Antwortqualität → Plan überdenken (kleinerer Funktionsumfang oder größeres Modell nur optional).

### Phase 2: Eval-Grundlage (vor dem Bauen der Funktionen)

- [x] 2.1 (fertig: 102 geprüfte Fragen in `eval/goldset/goldset.jsonl`, siehe README dort) Gold-Set der PC-App (`data/eval/gold_set.jsonl`, 57 Fragen) als Format-Vorlage verwenden. Die Fragen stammen aus persönlichen Unterlagen und bleiben **lokal**; für das öffentliche Repo ein eigenes, freies Beispiel-Korpus erstellen (z. B. gemeinfreie Lehrtexte).
- [ ] 2.2 Kleines Eval-Tool (Kotlin-JVM oder Python-Skript), das Fragen gegen ein Modell/Index laufen lässt und Treffer@k sowie Antwort-Treue (Quelle enthalten, „nicht im Material“-Quote) ausgibt.
- [ ] 2.3 Baseline festhalten: Basismodell, Q4, kleiner Kontext. Dieses Eval ist die Messlatte für jede spätere Änderung.

### Phase 3: Daten und Import

- [x] 3.1 Room-Schema `Document`, `Chunk`, `Embedding` + FTS5-Tabelle (`Card`, `ReviewLog`, `PomodoroSession`, `Setting` kommen mit Phase 5/7). **Befund: Androids System-SQLite hat kein FTS5**, deshalb `BundledSQLiteDriver` (androidx.sqlite-bundled).
- [x] 3.2 (Paritätstest gegen den Python-Chunker: 133 identische Chunks) Chunker nach Kotlin portieren (Vorlage: `ingestion/chunker.py`, Größe ca. 1100 Zeichen, 180 Überlappung; Parameter für kleineren Kontext neu bewerten). Unit-Tests aus den Python-Tests ableiten.
- [x] 3.3 Text-Normalisierung (Unicode-NFC, Trennstriche, Whitespace) portieren.
- [x] 3.4 (PDFium, `io.legere:pdfiumandroid`; Silbentrennungs-Marker U+FFFE werden entfernt) PDF-Extraktion (Text, Seitenzuordnung) mit einer Android-PDF-Bibliothek; Test mit mehreren echten PDFs.
- [x] 3.5 TXT/MD-Import; Datei-Auswahl über Storage Access Framework.
- [x] 3.6 Dedup per SHA-256 des Volltexts (wie `dedup.py`), „unverändert“/„Duplikat“/„geändert“.
- [x] 3.7 Import-Pipeline als WorkManager-Job mit Fortschritt, Abbruch und Wiederaufnahme.
- [x] 3.8 (Vordergrunddienst, wiederaufnehmbar; pausiert bei Hitze ab THERMAL_MODERATE oder Akku unter 20 % ohne Ladegerät; Schalter „Nur am Ladegerät indexieren“) Embedding der Chunks im Hintergrund (Batching, Drosselung bei Hitze/Akku, bevorzugt am Ladegerät).

### Phase 4: Suche und Chat (RAG)

- [x] 4.1 (Snowball-German-Port mit Paritätstest gegen Python: 9022 Wörter, 3847 Tokens identisch) FTS5-Suche inkl. deutscher Vorverarbeitung (Stemming/Normalisierung, Ersatz für Snowball).
- [x] 4.2 Vektor-Suche (Brute-Force-Cosinus), gemessen bei 5k/10k/50k Abschnitten (siehe `docs/RAG_EVAL.md`: 190 ms bei 10k, 382 ms bei 50k).
- [x] 4.3 Fusion per RRF (Formel aus `ARCHITEKTUR.md` übernehmen), Top-K auf 3–4.
- [x] 4.4 Prompt-Vorlage „nur aus dem Material antworten, Quelle nennen, sonst ‚Nicht im Material gefunden‘“. Prompts aus `graph/prompts.py` als Ausgangsbasis, gekürzt.
- [x] 4.5 Chat-UI: Streaming-Antwort, Abbrechen, klickbare Quellen mit Textstelle und Seite.
- [x] 4.6 Gesprächsverlauf (letzte 2 Runden, Antworten auf 600 Zeichen gekürzt; kurze Rückfragen suchen mit der vorigen Frage) mit knapper Historie (Kontextbudget einhalten).
- [x] 4.7 (Ergebnisse: `docs/RAG_EVAL.md`; 19/19 Verweigerungen, Beleg in den Quellen 95 %, ca. 88 % inhaltlich korrekt) Eval aus Phase 2 laufen lassen, mit der Baseline vergleichen.

### Phase 5: Karteikarten und Lernen

- [x] 5.1 (Parität: 2553 zufällige Bewertungen identisch zu py-fsrs 6.3, auf JVM und auf dem Gerät) FSRS nach Kotlin portieren (Vorlage: Python-`fsrs`, Tests mit festen Referenzwerten).
- [x] 5.2 Karten-Erzeugung aus Chunks: zweistufig wie in der PC-App (Fragen als JSON, dann je Frage eine Musterlösung; Retry bei Mängeln; Cloze-Karten gibt es auch dort nicht) (wie `generate_json` in `llm.py`).
- [x] 5.3 (Parität mit `card_quality.py`: 133 Fragen, 213 Antworten identisch; Dubletten per Embedding, Schwelle 0,89 an EmbeddingGemma geprüft) Qualitätsfilter für Karten (Vorlage: `card_quality.py`), Duplikat-Erkennung.
- [x] 5.4 Lern-UI: Karte zeigen, mit drei Tasten bewerten (Nicht gewusst / Halb / Gewusst wie in der PC-App), Vorschau der nächsten Fälligkeit je Taste.
- [x] 5.5 Tagesziel, Serie, Wochenansicht und Zahl gefestigter Karten.
- [x] 5.6 Karten manuell anlegen/bearbeiten/löschen; Anki-Export (TSV).

### Phase 6: Zusammenfassungen

- [x] 6.1 Map-Reduce: Abschnitt-Zusammenfassungen, dann Kurzfassung (stapelweise Verdichtung); Teilergebnisse werden gespeichert, unterbrochene Läufe setzen fort. Prüfungen auf abgeschnittene Sätze und nicht belegte Zahlen (Vorlage: `ingestion/summarize.py`).
- [x] 6.2 Stil wählbar: Gegliedert, Stichpunkte, Kurzfassung.
- [x] 6.3 Anzeige (Markdown), Teilen, Speicherung pro Dokument und Stil; ersetzt eine neue Fassung das Dokument, werden vorhandene Zusammenfassungen automatisch neu erstellt.

### Phase 7: Pomodoro

- [x] 7.1 Zustandsmaschine in `core` (Fokus/Kurzpause/Langpause, Einstellungen), voll unit-getestet.
- [x] 7.2 Benachrichtigung mit Chronometer-Countdown und Aktionsknöpfen plus genauer Alarm (`setExactAndAllowWhileIdle`) fürs Phasenende, Boot-Wiederherstellung. Bewusst kein Vordergrunddienst: Der Zustand ist zeitstempelbasiert, nichts muss im Hintergrund laufen.
- [x] 7.3 UI: Tab „Fokus“ mit Timer, Start/Pause/Überspringen/Beenden, Zuordnung zu einem Dokument (Fach folgt mit dem Feinschliff-Backlog), Einstellungen.
- [x] 7.4 Lernzeit-Statistik (pro Tag/Woche) und Verknüpfung mit dem Tagesziel.

### Phase 8: Modell-Download in der App

- [ ] 8.1 Modell-Repo auf GitHub anlegen, Konvertierung/Quantisierung reproduzierbar dokumentieren (Skript im Repo).
- [ ] 8.2 `manifest.json`-Schema festlegen (Abschnitt 4), Release `v1` mit Teilen erstellen.
- [ ] 8.3 Downloader: Range-Fortsetzung, SHA-256-Prüfung, Speicherplatz-Check, nur WLAN (einstellbar), Fortschritt und Abbruch.
- [ ] 8.4 Erststart-Assistent: Gerät prüfen (RAM), Modell empfehlen, Download starten, Lizenz anzeigen.
- [ ] 8.5 Fallback-URLs und Fehlerfälle testen (Abbruch, kaputte Datei, volles Gerät).
- [ ] 8.6 Updates: Manifest-Version prüfen, altes Modell erst nach erfolgreichem Download löschen.

### Phase 9: Qualität, Robustheit, Release

- [ ] 9.1 Fehlerbehandlung: Modell nicht geladen, zu wenig RAM, leere Datenbank, Abbruch mitten im Import.
- [ ] 9.2 Performance: Kaltstart, Speicherverbrauch, Akku-Test über 30 Minuten Chat.
- [ ] 9.3 Datenschutz: Datenschutzerklärung (nichts verlässt das Gerät), Backup-Regeln (`allowBackup` bewusst entscheiden), Export/Löschen aller Daten.
- [ ] 9.4 Barrierefreiheit, Dark Mode, deutsch/englisch.
- [ ] 9.5 Geschlossener Test mit wenigen Nutzern (Play Console, interne Testspur).
- [ ] 9.6 Play-Store-Eintrag: Screenshots, Beschreibung, Content-Rating, Data-Safety-Formular, App Bundle signieren.
- [ ] 9.7 Veröffentlichung auf der Produktionsspur.

### Phase 10: iOS (erst danach)

- [ ] 10.1 `core` auf Kotlin Multiplatform umstellen, ggf. Compose Multiplatform prüfen.
- [ ] 10.2 Inferenz auf iOS (llama.cpp mit Metal oder LiteRT-LM Swift), Entitlement für erhöhtes Speicherlimit.
- [ ] 10.3 Modell-Download und Pomodoro-Benachrichtigungen für iOS anpassen; App-Store-Einreichung (Mac + Developer-Konto nötig).

## 5a. Feinschliff-Backlog (nach den Phasen, Reihenfolge offen)

Vom Nutzer nach dem Test über Nacht genannt oder beim Bauen aufgefallen:

- **Fächer und Referenz im RAG:** Fächer anlegen, Dokumente einem Fach zuordnen und den Chat auf ein Fach oder ein einzelnes Dokument einschränken (wie in der PC-App). Betrifft Suche (`HybridRetriever`: Filter nach Dokument-IDs), Datenmodell (`subject`-Tabelle, Dokument-Zuordnung), Import-Dialog und Chat-Kopfzeile. Nach dem Fach lassen sich auch Karten und Zusammenfassungen (Fach-Zusammenfassung wie `write_summary(mode="subject")`) filtern.
- Kartenerzeugung: Dublettenschwelle für EmbeddingGemma feiner abstimmen, Lückentext-Karten, bessere Fragen bei Code-Dokumenten.
- Zusammenfassung eines ganzen Fachs aus den Dokumentzusammenfassungen.
- Dokumente umbenennen; Reihenfolge und Suche in der Dokumentenliste.
- Querformat und Tablets (Layout funktioniert, ist aber nicht optimiert).

## 6. Risiken und Gegenmaßnahmen

| Risiko | Gegenmaßnahme |
|---|---|
| E2B liefert zu schwache deutsche Antworten | Eval früh (Phase 2), kurzer Kontext, JSON-Constrained-Decoding, optional E4B, ggf. LoRA-Finetuning |
| Tempo/Akku/Hitze | Spike-Messungen, Drosselung beim Embedding, Streaming-UI |
| Speicherfehler (OOM) bei großem Modell | Mindest-RAM im Manifest, Geräteprüfung im Erststart, E2B als Standard |
| Android-Regex (ICU) weicht von der JVM ab (Flag `U`, einzelnes `}`): JVM-Tests fanden zwei App-Abstürze nicht | Paritätstests laufen zusätzlich auf dem Gerät (`CoreParityOnDeviceTest`) |
| Lange Prompts scheitern, wenn Embedder und Sprachmodell die GPU teilen (gefunden und behoben, siehe `RAG_EVAL.md`) | Aufwärmlauf mit langem Prompt in `LiteRtLmEngine.load()`; Regressionstest bei jeder LiteRT-LM-Aktualisierung |
| LiteRT-LM-API ändert sich | Interface-Schicht, Modell und Version im eigenen Release eingefroren |
| GitHub-Release nicht erreichbar | Mehrere URLs im Manifest, Wiederaufnahme, Offline nach erstem Download |
| Lizenzpflichten | Apache-2.0-Texte im Release und in der App, NOTICE pflegen |
| Datenschutz in öffentlichen Tests | Gold-Set und Unterlagen nie committen (`.gitignore` für `android/eval/private/`) |

## 7. Nächster Schritt

Phase 8 (Modell-Download über GitHub-Releases), danach Phase 9. Phase 7 (Pomodoro) ist umgesetzt, die Sichtprüfung des Tabs auf dem Pixel steht aus. Vorher/danach: Phase 8 (Modell-Download über GitHub-Releases), dann Qualität und Release (Phase 9) und das Feinschliff-Backlog.
