# Qualitätssicherung – Mehrstufiger Code-Review & Fixes

Dieses Dokument protokolliert die Qualitätssicherung des RAG-Systems. Nach der
Implementierung wurde das **gesamte System** durch einen mehrstufigen,
adversarisch verifizierten Code-Review geprüft (19 KI-Review-Agenten über 6
Bereiche + Verifikation + Abschlusskritiker). Es wurden **13 echte Defekte**
bestätigt und **alle behoben**. Ein zusätzlicher Verdacht wurde in der
Verifikation korrekt als **Falsch-Positiv** verworfen.

Der Review war rein statisch (kein Code ausgeführt), damit er parallel zum
laufenden Erstimport gefahren werden konnte.

## Ablauf des Reviews

1. **Review (6 parallele Prüfer)** je Modulgruppe: Ingestion, Retrieval,
   Graph/LLM, Eval/Config, UI/CLI, Doku-gegen-Code.
2. **Verifikation (adversarisch)**: Jede Finding wurde von einem unabhängigen,
   skeptischen Prüfer gegen den echten Code gegengeprüft (CONFIRMED / REJECTED).
   Grundhaltung „im Zweifel REJECTED", um Falsch-Positive zu vermeiden.
3. **Abschlusskritiker**: Suche nach übersehenen Defektklassen an den riskantesten
   Integrationsstellen.

## Behobene Defekte

| # | Schwere | Datei | Problem | Fix |
|---|---------|-------|---------|-----|
| 1 | **hoch** | `retrieval/reranker.py` | sentence-transformers 5.x wendet für den Reranker (num_labels=1) standardmäßig **Sigmoid** an → `rerank_score` lag in (0,1) statt als Logit. Dadurch griff die Anti-Halluzinations-Schwelle `RELEVANCE_MIN_SCORE=-2.0` **nie**. | Rohe Logits erzwungen (`activation_fn=Identity`), Schwelle auf Logit-Skala kalibriert (`-4.0`). Empirisch bestätigt: relevant **+7.57**, irrelevant **−11.04**. |
| 2 | **hoch** | `ingestion/pipeline.py` | **Globale** exakte Chunk-Dedup: ein geteilter Chunk wurde nur beim ersten Dokument gespeichert. Beim Löschen/Aktualisieren dieses Dokuments verschwand der Inhalt aus dem Index, obwohl ihn ein anderes Dokument noch enthielt. | Dedup auf **Dokument-Ebene** umgestellt (lokales Hash-Set). Doppelte Infos über Dokumentgrenzen werden zur Query-Zeit (Jaccard) entfernt. |
| 3 | mittel | `ingestion/chunker.py` | Bei `CHUNK_OVERLAP ≥ CHUNK_SIZE` Schrittweite 0 → **Crash** (`ValueError`) bzw. negativ → **stiller Datenverlust**. | Schrittweite `max(1, size − overlap)` abgesichert. |
| 4 | mittel | `graph/rag_graph.py` | Faithfulness-Gate **fail-open**: `bool("false") == True` und `None → True` ließen ungeprüfte Antworten durch. | **Fail-closed**: nur explizites „ja/true" gilt als belegt, sonst Fallback. |
| 5 | mittel | `ui/…/Einstellungen.py` | „Auf Standard zurücksetzen" löschte nur `config.json`, das laufende `settings`-Objekt blieb mutiert. | `Settings.reset()` ergänzt und aufgerufen. |
| 6 | mittel | `eval/run_eval.py` | Leeres `EVAL_K_VALUES` (Config-Override) → `max()` **Crash** vor jeder Ausgabe. | Leere/kaputte Werte abgefangen (Default `(1,3,5,10)`), zusätzlich `Settings._sanitize()`. |
| 7 | niedrig | `ingestion/loaders.py` | PDF-Fallback (pypdf) hängte an bereits teilbefüllte fitz-Ergebnisse an → **doppelte Seiten**, falscher Hash. | Listen im Fallback zurückgesetzt. |
| 8 | niedrig | `ingestion/pipeline.py` | Im „alle Chunks Duplikat"-Update-Pfad übersprang der frühe `return` den BM25-Neuaufbau → verwaiste BM25-IDs. | BM25-Rebuild vor dem frühen `return` ergänzt. |
| 9 | niedrig | `llm.py` | Konfiguriertes `LLM_TIMEOUT` wurde nie an den Ollama-Client übergeben → möglicher unendlicher Hang. | `timeout` an `ollama.Client` durchgereicht (LLM + Embeddings). |
| 10 | niedrig | `eval/gold_set.py` | Eine defekte JSONL-Zeile brach das Laden des ganzen Gold-Sets ab. | `json.loads` je Zeile in `try/except` (defekte Zeilen überspringen). |
| 11 | niedrig | `ingestion/pipeline.py` | Exakt gleiche Chunks **innerhalb** eines Dokuments wurden nicht dedupliziert (Registrierung erst nach der Schleife). | Durch das lokale Hash-Set (Fix 2) mit erledigt. |
| 12 | niedrig | `scripts/verify.py` | `print("▶ …")` crasht bei umgeleiteter Windows-stdout (cp1252). | ASCII-Marker + `stdout.reconfigure(utf-8)`. |
| 13 | niedrig | `ingestion/pipeline.py` | `progress()`-Aufruf mit Umlaut-Dateinamen außerhalb `try/except` → ein `UnicodeEncodeError` brach den **gesamten** Batch-Import ab. | `progress`-Aufruf gekapselt; CLI stellt stdout auf UTF-8. |

## Korrekt verworfenes Falsch-Positiv

- **BM25 enthielte Frage-Einträge**: Verdacht, dass generierte Fragen den
  Keyword-Index verfälschen. In der Verifikation **widerlegt** – `get_all_chunks()`
  filtert hart auf `type="chunk"`, Frage-Einträge gelangen nie in BM25.

## Fazit

Die Kernversprechen des Systems – **hohe Trefferquote** (Hybrid + funktionierender
Reranker) und **keine Halluzination** (jetzt wirksames Relevanz-Gate +
fail-closed Faithfulness-Check + ehrlicher Dokument-Fallback) – sind nach den
Fixes belegbar wirksam. Alle geänderten Module kompilieren fehlerfrei; die
kritischen Fixes wurden funktional getestet.
