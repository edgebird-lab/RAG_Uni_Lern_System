# RAG-Auswertung auf dem Gerät (Phase 4, Stand 2026-10-07)

Gerät: Pixel 9 Pro XL. Korpus: Grundgesetz, BGB, HGB, 8 Wikipedia-Artikel = **5462 Chunks** (Chunker 1000/150 Zeichen).
Goldset: 102 Fragen (`eval/goldset/goldset.jsonl`). Rohdaten: `eval/spike/retr-1.json`, `rag-1.json`. Auswertung: `auswerten_rag.py`.
Pipeline: hybride Suche (FTS5/BM25 mit Snowball-Stemming + EmbeddingGemma 2, RRF) → Top 4 → Gemma 4 E2B (GPU, MTP) mit Quellenprompt.

## Suche (nur Retrieval, 83 beantwortbare Fragen, Beleg in den Top-k)

| Verfahren | @1 | @4 | @10 | Zeit je Anfrage |
|---|---|---|---|---|
| Stichwort (FTS5/BM25) | 0,66 | 0,86 | 0,88 | 21 ms |
| Vektor (EmbeddingGemma 2) | 0,59 | 0,93 | 0,98 | 200 ms |
| **Hybrid (RRF 1:1)** | **0,69** | **0,94** | **0,98** | 210 ms |

Als Beleg zählt ein Abschnitt, in dem mindestens 80 % der Wortstämme des Beleg-Zitats vorkommen (der Chunker teilt anders als beim Goldset-Bau).
Die Gerätewerte decken sich mit der Offline-Schätzung aus dem Spike (Hybrid @4 0,94).

## Ganze Pipeline (102 Fragen, Antwort vom Sprachmodell)

| Messgröße | Ergebnis |
|---|---|
| Beleg steht in den 4 Quellen | 79 von 83 (95 %) |
| **Unbeantwortbare Fragen korrekt verweigert** | **19 von 19** |
| Direkte Fragen: Beleg in den Quellen / falsch verweigert | 52 von 52 / 0 |
| Umformulierte Fragen: Beleg in den Quellen / falsch verweigert | 18 von 21 / 3 |
| Mehrstufige Fragen: Beleg in den Quellen / falsch verweigert | 9 von 10 / 1 |
| Zeit bis zum ersten Token (Median) | 1,4 s |
| Gesamtzeit je Antwort (Median / Maximum) | 3,1 s / 10,8 s |

**Von Hand gelesene Qualität der beantwortbaren Fragen** (die 20 Antworten, die der grobe Wortabgleich nicht bestätigte, einzeln gelesen; die übrigen 63 nur per Wortabgleich geprüft):
- ca. **73 von 83 inhaltlich korrekt** (63 über den Wortabgleich bestätigt + 10 weitere Antworten, die korrekt umformuliert waren),
- 3 falsche Verweigerungen, obwohl die Quelle im Kontext stand (`gg-umfo-45`, `wiki_inflation-umfo-01`, `bgb-mehr-02`),
- 1 Antwort aus der falschen Quelle (`bgb-umfo-01`: beantwortet eine andere Vorschrift, statt zu verweigern),
- 3 teilweise unvollständige oder vermischte Antworten (`gg-dire-09` ohne die Ausnahmen, `gg-umfo-03`, `wiki_zelle_biologie-mehr-02`),
- 3 weitere, bei denen die Suche den Beleg verfehlte (davon verweigerte das Modell 1 korrekt, 2 antworteten plausibel aus Nachbarabschnitten).

Fazit: Für Chat mit Quellen taugt E2B. Die wichtigste Schutzfunktion, „Nicht im Material gefunden“ bei fehlender Antwort, hat auf allen 19 Testfällen funktioniert. Die Schwächen liegen bei umformulierten Fragen mit juristischen Fachwörtern (falsche Verweigerung). Hebel: Rückfrage an den Nutzer statt Verweigerung, Top-6 statt Top-4 bei kurzem Kontext, Prompt-Feinschliff.

## Experimente gegen falsche Verweigerungen (alle 102 Fragen, Pixel 9 Pro XL)

| Konfiguration | Beleg in den Quellen | falsch verweigert | Unbeantwortbare korrekt verweigert | Antwort deckt erwartete Begriffe* |
|---|---|---|---|---|
| **streng, 4 Quellen (Standard)** | 79/83 | 3 | **19/19** | 63/76 |
| tolerant, 4 Quellen | 79/83 | 1 | 16/19 | 63/78 |
| streng, 6 Quellen | 80/83 | 2 | 18/19 | 59/78 |
| tolerant, 6 Quellen | 80/83 | 0 | 17/19 | 64/80 |

\* grober Wortabgleich mit der erwarteten Antwort, nur Orientierung.

Der „tolerante“ Prompt erlaubt Umschreibungen; 6 statt 4 Quellen liefern mehr Kontext. Beides senkt die falschen Verweigerungen, **erhöht aber die erfundenen Antworten auf unbeantwortbare Fragen** (bis zu 3 von 19). Mehr Quellen verschlechtern bei E2B außerdem die Treffsicherheit des Wortabgleichs (59 statt 63), vermutlich weil das kleine Modell durch mehr Text abgelenkt wird.

**Entscheidung:** Strenger Standard mit 4 Quellen bleibt. Eine erfundene Antwort schadet in einer Lern-App mehr als eine Verweigerung. Als Ausgleich bietet der Chat nach „Nicht im Material gefunden“ den Knopf **„Mit mehr Quellen erneut versuchen“** (6 Quellen, toleranter Prompt, Antwort mit Hinweis „bitte Quellen prüfen“). So entscheidet die Nutzerin, wann sie das Risiko eingeht.

## Vektorsuche bei großen Bibliotheken (Plan 4.2)

| Abschnitte | Erste Suche inkl. Laden aus der Datenbank | Folgesuchen (Median) | Heap |
|---|---|---|---|
| 10.000 | 2,0 s | 190 ms | ca. 63 MB |
| 50.000 | 23,9 s | 382 ms | ca. 159 MB |

Bis ca. 20.000 Abschnitte (ca. 60–100 Bücher) ist das unproblematisch. Darüber lohnen sich Int8-Quantisierung (4-mal weniger Speicher, schnelleres Laden) oder ein Vektor-Cache als Datei. Nicht vorab optimiert.

## Befunde aus der Integration (wichtig für die weitere Arbeit)

1. **Lange Prompts scheitern nach dem Laden des Embedders** ("Failed to invoke the compiled model", OpenCL, `cl_arguments.cc`), wenn das Sprachmodell vorher noch nie mit einem langen Prompt gelaufen ist. Die GPU-Kerne für lange Eingaben entstehen erst beim ersten passenden Aufruf. Prompts bis ca. 1300 Zeichen liefen, ab ca. 1800 Zeichen scheiterten sie. **Abhilfe:** `LiteRtLmEngine.load()` macht direkt nach dem Laden einen Aufwärmlauf mit ca. 4500 Zeichen. Danach laufen Sprachmodell und Embedder im selben Prozess in beliebiger Reihenfolge.
2. **Display muss an bleiben** (siehe `SPIKE_ERGEBNIS.md`): Der Vordergrunddienst mit Wakelock für das Embedding ist deshalb Pflicht.
3. **Android-System-SQLite hat kein FTS5** → eigene SQLite (`sqlite-bundled`).
4. **Debug-Aktivitäten** werden vom System nach einer Neuinstallation wiederhergestellt und liefen dann doppelt; sie starten jetzt nur noch bei einem frischen Start.
5. Der Snowball-Stemmer behandelt „wählt“ und „gewählt“ als verschiedene Stämme (`wahlt` / `gewahlt`). Das ist Eigenschaft des Algorithmus; die Vektorsuche gleicht das aus.
