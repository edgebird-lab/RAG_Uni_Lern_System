# Architektur

Diese Datei beschreibt den technischen Aufbau des RAG-Lernsystems im Detail:
den Ingestion-Pfad und den Query-Pfad, jede Komponente mit Modulpfad, die
Retrieval-Pipeline Schritt für Schritt (inkl. RRF-Formel), den LangGraph-Ablauf,
die Anti-Halluzinations-Mechanismen und das Datenmodell.

---

## 1. Gesamtüberblick

Das System besteht aus zwei klar getrennten Pfaden, die sich nur über die
persistenten Speicher (ChromaDB, BM25-Index, Manifest) treffen:

- **Ingestion-Pfad** (offline, resumierbar): bringt Dokumente in den Index.
- **Query-Pfad** (online): beantwortet Fragen aus dem Index.

Alle Modelle laufen lokal über **Ollama** (`gemma4:e4b`, `gemma4:e2b`, `bge-m3`).
Der Reranker (`BAAI/bge-reranker-v2-m3`) läuft über `sentence-transformers`.

---

## 2. Ingestion-Pfad (Datenfluss)

```
   Datei (PDF / MD / TXT / DOCX / PPTX)
        │
        ▼
 ┌──────────────────┐   loaders.py
 │ 1. Laden         │   PyMuPDF (fitz) → Fallback pypdf; python-docx; python-pptx
 │  + Normalisieren │   Unicode-NFC, Whitespace, Trennstriche zusammenfügen
 └──────────────────┘
        │  LoadedDoc(text, blocks[Seite/Folie], filetype)
        ▼
 ┌──────────────────┐   dedup.py + manifest.py
 │ 2. Dedup         │   content_hash = SHA-256(normalisierter Volltext)
 │  (Dokument)      │   • identischer Inhalt vorhanden?  → SKIP (duplicate)
 │                  │   • gleiche Datei, unverändert?    → SKIP (unchanged)
 │                  │   • Inhalt geändert / --force?     → alte Chunks löschen
 └──────────────────┘
        │
        ▼
 ┌──────────────────┐   chunker.py
 │ 3. Chunking      │   Markdown → an Überschriften (#, ##, …), Header-Pfad als
 │  (struktur-      │            Präfix; zu große Abschnitte rekursiv geteilt
 │   bewusst)       │   PDF/DOCX/PPTX/TXT → pro Seite/Folie rekursiv an
 │                  │            \n\n › \n › ". " › "; " › ", " › " " mit Overlap
 │                  │   zu kleine Chunks (< MIN_CHUNK_CHARS) werden gemerged
 └──────────────────┘
        │  Chunks mit meta (subject, filename, location, chunk_index …)
        ▼
 ┌──────────────────┐   dedup.py + manifest.py
 │ 4. Dedup         │   chunk_hash = SHA-256(lower+whitespace-normalisiert)
 │  (Chunk, exakt)  │   global über das Manifest → exakte Wiederholungen raus
 └──────────────────┘
        │
        ▼
 ┌──────────────────┐   embeddings.py (Ollama bge-m3)
 │ 5. Embeddings    │   batchweise (32), jeder Vektor L2-normalisiert (1024-dim)
 └──────────────────┘
        │
        ▼
 ┌──────────────────┐   dedup.filter_near_duplicates
 │ 6. Dedup         │   greedy: Kosinus (= Skalarprodukt, da normalisiert)
 │  (Chunk,near-dup)│   ≥ DEDUP_NEAR_DUPLICATE_THRESHOLD → verwerfen
 │                  │   (nur innerhalb desselben Dokuments)
 └──────────────────┘
        │
        ▼
 ┌──────────────────┐   question_gen.py  (nur wenn ENABLE_QUESTION_INDEXING=True)
 │ 7. Fragen        │   LLM erzeugt NUM_INDEX_QUESTIONS Fragen je Chunk;
 │  (optional)      │   Fragen werden ebenfalls eingebettet (type="question",
 │                  │   parent_id → Chunk).  Standardmäßig AUS (CPU-Kosten, s. §6)
 └──────────────────┘
        │
        ▼
 ┌──────────────────┐   vectorstore.py (ChromaDB)  +  bm25_index.py  +  manifest.py
 │ 8. Speichern     │   • Chroma-Upsert (Chunks + ggf. Fragen)
 │                  │   • Manifest-Eintrag (Dokument + Chunk-Hashes)
 │                  │   • BM25-Index-Neuaufbau aus allen Chunks
 └──────────────────┘
```

**Resumierbarkeit & Automatik:**
- `ingestion/pipeline.py` → `ingest_file()` / `ingest_directory()`. Beim
  Ordner-Import wird der BM25-Index aus Effizienzgründen **einmal am Ende** neu
  gebaut (nicht pro Datei).
- Reihenfolge beim Ordner-Import ist priorisiert: Dateien mit Namensbestandteilen
  wie *zusammenfassung/kompakt/spickzettel/klausur* zuerst, dann kleinere vor
  größeren, so ist früh viel wichtiges Material verfügbar.
- `ingestion/watcher.py` (via `cli watch`) überwacht Quell- und Inbox-Ordner mit
  `watchdog` und einem Debounce von 3 s (damit kein halb geschriebenes PDF
  gelesen wird).
- Jeder Schritt wird nach `data/logs/ingestion.jsonl` protokolliert.

---

## 3. Query-Pfad (Datenfluss)

```
   Frage (+ optional Fach-Filter)
        │
        ▼
 ┌───────────────────────────── retrieval/hybrid.py ─────────────────────────────┐
 │                                                                                 │
 │  A) Dense-Suche (embeddings.py + vectorstore.py)                                │
 │     bge-m3 → Chroma-Query über Chunks UND Fragen (DENSE_TOP_K=25).              │
 │     Frage-Treffer werden über parent_id auf ihren Eltern-Chunk zurückgeführt.   │
 │                                                                                 │
 │  B) BM25-Suche (bm25_index.py)                                                  │
 │     deutsche Tokenisierung → Stoppwörter raus → Snowball-Stemming (BM25_TOP_K). │
 │                                                                                 │
 │  C) Reciprocal Rank Fusion (RRF)  ── vereint A) und B) (RRF_K=60)               │
 │        → Top FUSION_TOP_K=20 Kandidaten, Chunk-Texte aus Chroma auflösen        │
 │                                                                                 │
 │  D) Near-Duplicate-Filter (Token-Jaccard ≥ RETRIEVAL_DEDUP_JACCARD=0.82)        │
 │        → entfernt fast identische Kandidaten (keine doppelten Infos)            │
 │                                                                                 │
 │  E) Cross-Encoder-Rerank (reranker.py, bge-reranker-v2-m3)                       │
 │        → bewertet (Frage, Chunk)-Paare, sortiert neu, Top FINAL_TOP_K=6         │
 └─────────────────────────────────────────────────────────────────────────────────┘
        │  finale Kandidaten mit rerank_score
        ▼
 ┌───────────────────────── graph/rag_graph.py (LangGraph) ───────────────────────┐
 │  retrieve → [Relevanz-Gate] → generate → faithfulness → END                     │
 │                   └────────── zu schwach / "weiß nicht" / nicht belegt ─▶ fallback
 └─────────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
   Antwort  +  Quellenkarten  +  Badge ("belegte Antwort" / "Fallback")
```

> **Hinweis zur Reihenfolge:** Der Near-Duplicate-Filter (D) läuft im Code
> **vor** dem Reranker (E). Er arbeitet günstig auf den ~20 fusionierten
> Kandidaten, nicht auf dem ganzen Index. Der Reranker sortiert anschließend die
> bereinigte Kandidatenliste final.

---

## 4. Komponenten im Detail

| Komponente          | Modul                            | Aufgabe |
| ------------------- | -------------------------------- | ------- |
| Konfiguration       | `ragapp/config.py`               | Alle Parameter als `Settings`-Dataclass; Laufzeit-Overrides aus `data/config.json`. Globale Instanz `settings`. |
| LLM-Client          | `ragapp/llm.py`                  | Wrapper um Ollama-Chat (`gemma4:e4b`/`e2b`). Niedrige Temperatur, `think=False`, optionaler JSON-Modus mit robustem Parser (`_safe_json`). |
| Dokument-Loader     | `ragapp/ingestion/loaders.py`    | Text + Struktur-Blöcke (Seite/Folie) aus PDF/MD/TXT/DOCX/PPTX; Normalisierung. |
| Chunker             | `ragapp/ingestion/chunker.py`    | Markdown-Header-Splitting bzw. rekursives Splitting pro Seite/Folie mit Overlap; Merge kleiner Chunks. |
| Deduplizierung      | `ragapp/ingestion/dedup.py`      | `content_hash`, `doc_id_for`, `chunk_hash`, `filter_near_duplicates` (Kosinus). |
| Fragen-Generierung  | `ragapp/ingestion/question_gen.py` | Hypothetische Prüfungsfragen pro Chunk (JSON-Modus, `gemma4:e2b`). |
| Anreicherung        | `ragapp/ingestion/enrich.py`     | Gezielte, gedeckelte, resumierbare Fragen-Erzeugung für vorhandene Chunks. |
| Pipeline            | `ragapp/ingestion/pipeline.py`   | Orchestriert die gesamte Ingestion; `ingest_file`, `ingest_directory`, `remove_document`. |
| Ordnerwächter       | `ragapp/ingestion/watcher.py`    | `watchdog`-Observer mit Debounce; ruft `ingest_file` automatisch. |
| Embeddings          | `ragapp/retrieval/embeddings.py` | `bge-m3` über Ollama; L2-Normalisierung; Batch + Retry. |
| Vektor-DB           | `ragapp/retrieval/vectorstore.py`| ChromaDB (persistent, `hnsw:space=cosine`); eine Collection `zusammenfassungen`. |
| BM25-Index          | `ragapp/retrieval/bm25_index.py` | `rank_bm25.BM25Okapi`; deutsche Tokenisierung, Stoppwörter, Snowball-Stemmer; Pickle-Persistenz. |
| Reranker            | `ragapp/retrieval/reranker.py`   | `sentence-transformers.CrossEncoder`; Fallback auf Fusions-Reihenfolge bei Ladefehler. |
| Hybrid-Retrieval    | `ragapp/retrieval/hybrid.py`     | Dense + BM25 → RRF → Dedup → Rerank; `retrieve()`. |
| Prompts             | `ragapp/graph/prompts.py`        | Deutsche, faktentreue Vorlagen; Sentinel `NO_ANSWER_TOKEN`. |
| Orchestrierung      | `ragapp/graph/rag_graph.py`      | LangGraph-Graph + öffentliche `answer_query()`; Query-Logging. |
| Manifest            | `ragapp/manifest.py`             | SQLite-Registry: Tabellen `documents` und `chunk_hashes`; Dedup + Statistik. |
| Gold-Set            | `ragapp/eval/gold_set.py`        | Held-out-Testfragen aus gesampelten Chunks. |
| Metriken            | `ragapp/eval/metrics.py`         | Hit@k / Recall@k / MRR + Aufschlüsselung nach Fach. |
| Evaluation          | `ragapp/eval/run_eval.py`        | Gold-Set gegen die echte Pipeline; JSON/CSV/history. |
| CLI                 | `ragapp/scripts/cli.py`          | `ingest`, `ingest-file`, `watch`, `gold`, `enrich`, `eval`, `ask`, `stats`, `reset`. |
| Weboberfläche       | `ragapp/ui/💬_Chat.py`           | Streamlit-Chat mit Fach-Filter, Quellenkarten, Badges. |

---

## 5. Retrieval-Pipeline Schritt für Schritt

Warum überhaupt hybrid + rerank? Weil sich die Fehlerquellen der Verfahren
gegenseitig ausgleichen und die Trefferquote so maximiert wird:

1. **Dense-Suche (semantisch, `bge-m3`).** Findet sinngemäße Treffer, auch wenn
   andere Wörter benutzt werden ("Deckungsbeitrag" ↔ "DB je Stück"). Schwäche:
   exakte Fachbegriffe, Abkürzungen, Formelnamen, Zahlen. Es wird über **Chunks
   und generierte Fragen** gesucht; Frage-Treffer werden über `parent_id` auf
   den zugehörigen Chunk zurückgeführt (Multi-Representation-Indexing).
   Kandidaten: `DENSE_TOP_K` (Standard 25).

2. **BM25-Suche (lexikalisch, deutsch).** Fängt genau die exakten Begriffe,
   Abkürzungen und Zahlen ab, bei denen die semantische Suche schwächelt.
   Deutsch-spezifisch: unicode-bewusste Tokenisierung (Umlaute/ß bleiben
   erhalten), Entfernen deutscher Stoppwörter, **Snowball-Stemming**
   ("Kosten"/"Kostens"/"kostet" → gleicher Stamm). Kandidaten: `BM25_TOP_K`
   (Standard 25). BM25 indexiert nur Chunks (keine Fragen).

3. **Reciprocal Rank Fusion (RRF).** Vereint beide Ranglisten **rangbasiert**,
   nicht scorebasiert. Dadurch entfallen Skalierungsprobleme zwischen
   Kosinus-Ähnlichkeit und BM25-Scores. Formel:

   ```
                       ┌                    1                    ┐
   score_RRF(d) =  Σ   │  w_i · ─────────────────────────────    │
                   i   └          k  +  rang_i(d)                 ┘

     • i        = Rangliste (dense, bm25)
     • rang_i(d)= 1-basierte Position von Dokument d in Liste i (bestes = 1)
     • k        = RRF_K   (Standard 60; dämpft den Einfluss von Ausreißern)
     • w_i      = DENSE_WEIGHT / BM25_WEIGHT (Standard je 1.0)
   ```

   Anschließend werden die besten `FUSION_TOP_K` (Standard 20) Kandidaten
   behalten und ihre Chunk-Texte aus Chroma aufgelöst.

4. **Near-Duplicate-Filter (Token-Jaccard).** Auf den ~20 fusionierten
   Kandidaten wird paarweise die Jaccard-Ähnlichkeit der Wortmengen berechnet;
   liegt sie ≥ `RETRIEVAL_DEDUP_JACCARD` (0.82), wird der niedriger platzierte
   Kandidat verworfen. Ergebnis: keine doppelten Informationen im Kontext des LLM.

5. **Cross-Encoder-Rerank (`bge-reranker-v2-m3`).** Bewertet jedes
   (Frage, Chunk)-Paar **gemeinsam** in einem Modelldurchlauf, deutlich feiner
   als reine Vektordistanz. Das ist einer der stärksten Hebel für die
   Trefferquote. Ergebnis: die Top `FINAL_TOP_K` (Standard 6) Chunks gehen in die
   Antwortgenerierung. Kann das Modell nicht geladen werden, fällt das System auf
   die Fusions-Reihenfolge zurück (Score = `fusion_score`).

---

## 6. Fragen-Indexierung: die CPU-Designentscheidung (ehrlich)

Die Idee (Hypothetical Questions / Multi-Representation-Indexing): Nutzer stellen
**Fragen**, doch im Index liegt **Lehrtext**. Im Embedding-Raum liegt eine
Nutzerfrage oft näher an einer *anderen Frage* als am reinen Fließtext. Wenn also
zu jedem Chunk ein paar plausible Prüfungsfragen mitindexiert werden, steigt die
Trefferquote spürbar.

**Warum es standardmäßig AUS ist:** Auf reiner **CPU-Hardware ohne GPU** kostet
die LLM-gestützte Fragen-Generierung rund **~20 Sekunden pro Chunk**. Bei einem
Korpus in der Größenordnung mehrerer tausend Chunks wäre das beim Bulk-Import
unpraktikabel (Stunden bis Tage). Deshalb:

- `ENABLE_QUESTION_INDEXING = False` → beim normalen Import werden **keine** Fragen
  erzeugt (schneller Import).
- Stattdessen gibt es die **gezielte, gedeckelte Anreicherung**
  (`ingestion/enrich.py`, CLI `enrich`): Sie erzeugt Fragen nur für die
  wichtigsten Dokumente (Zusammenfassungen/Kompakt/Spickzettel zuerst, dann
  längere Chunks), in kontrollierter Menge (`--limit`), und ist **resumierbar**
  (bereits angereicherte Chunks werden übersprungen).

So bleibt der Trefferquoten-Vorteil nutzbar, ohne den Import unbrauchbar langsam
zu machen. Details zum Abwägen siehe [TUNING.md](TUNING.md).

---

## 7. LangGraph-Ablauf

```
                         ┌──────────┐
                START ──▶│ retrieve │
                         └────┬─────┘
                              │ route_after_retrieve
              relevance_ok ?  │
              ┌───── nein ────┴──── ja ──────┐
              ▼                               ▼
        ┌──────────┐                    ┌──────────┐
        │ fallback │◀───────────────────│ generate │
        └────┬─────┘   route_after_     └────┬─────┘
             │         generate:             │ route_after_generate
             │         Antwort == Sentinel   │  Antwort ok?
             │         oder leer ────────────┘  (Sentinel/leer → fallback)
             │                               │ ja
             │                               ▼
             │                        ┌──────────────┐
             │  route_after_          │ faithfulness │
             │  faithfulness:         └──────┬───────┘
             │  grounded == false            │ grounded?
             └───────────────◀───────────────┤
                                             │ ja
                                             ▼
                                            END
```

**Knoten (`rag_graph.py`):**

- **`retrieve_node`**: ruft die Hybrid-Pipeline auf. Berechnet `relevance_ok`:
  wahr, wenn Kandidaten vorhanden sind **und** der beste `rerank_score` ≥
  `RELEVANCE_MIN_SCORE` (Standard −2.0) ist. Andernfalls Routing zum Fallback
  (Relevanz-Gate).
- **`generate_node`**: baut aus den Kandidaten den nummerierten Kontext (bis
  `MAX_CONTEXT_CHARS`, Standard 7000 Zeichen) und lässt `gemma4:e4b` mit
  `ANSWER_SYSTEM`/`ANSWER_PROMPT` **nur aus dem Kontext** antworten.
- **`faithfulness_node`**: lässt das LLM prüfen, ob die Antwort vollständig durch
  den Kontext gedeckt ist (`FAITHFULNESS_PROMPT`, JSON `{"grounded": …}`). Ist
  `ENABLE_FAITHFULNESS_CHECK=False`, wird der Check übersprungen (immer grounded).
- **`fallback_node`**, der ehrliche Ausweg: keine erfundene Antwort, sondern ein
  Hinweis + Liste der am besten passenden Dokumente/Stellen (bzw. die Info, dass
  gar nichts Passendes gefunden wurde).

**Routing-Kanten:**

| Kante                  | Bedingung                                                  | Ziel |
| ---------------------- | --------------------------------------------------------- | ---- |
| `route_after_retrieve` | `relevance_ok == True`                                    | `generate` |
| `route_after_retrieve` | sonst                                                     | `fallback` |
| `route_after_generate` | Antwort enthält `KEINE_AUSREICHENDE_INFORMATION` oder leer | `fallback` |
| `route_after_generate` | sonst                                                     | `faithfulness` |
| `route_after_faithfulness` | `grounded == True`                                    | `END` |
| `route_after_faithfulness` | sonst                                                 | `fallback` |

Öffentliche Schnittstelle: `answer_query(question, subject=None)` gibt ein Dict
mit `answer`, `mode` (`answer`/`fallback`), `grounded`, `sources`, `timings` und
`total_time` zurück und schreibt einen Eintrag nach `data/logs/queries.jsonl`.

---

## 8. Anti-Halluzinations-Mechanismen (zusammengefasst)

Mehrere Sicherungen greifen ineinander:

1. **Niedrige Temperatur** (`LLM_TEMPERATURE = 0.1`) und `think=False` →
   faktentreue, deterministische Ausgaben.
2. **Strikte Prompts** (`prompts.py`): Das Modell darf ausschließlich den
   Kontext verwenden und muss Quellen als `[Quelle N]` belegen.
3. **Sentinel** `KEINE_AUSREICHENDE_INFORMATION`: Fehlt die Information, gibt das
   Modell genau diese Zeichenkette aus → sofortiges Routing in den Fallback.
4. **Relevanz-Gate** vor der Generierung: Ist schon der beste Treffer zu schwach
   (`< RELEVANCE_MIN_SCORE`), wird gar nicht erst frei generiert.
5. **Faithfulness-Prüfung** nach der Generierung: Ein zweiter LLM-Durchlauf prüft,
   ob die Antwort durch den Kontext gedeckt ist; wenn nein → Fallback.
6. **Ehrlicher Fallback** statt Halluzination: nennt die passendsten Fundstellen.

> Hinweis: `prompts.py` enthält zusätzlich einen `GRADE_PROMPT` (LLM-basierte
> Relevanzbewertung als Backup). Er ist als Baustein vorhanden, wird im aktuellen
> Graphen aber **nicht** aktiv aufgerufen. Das Relevanz-Gate arbeitet
> score-basiert über `RELEVANCE_MIN_SCORE`.

---

## 9. Datenmodell

### ChromaDB (`data/chroma`, Collection `zusammenfassungen`, Kosinus)

Eine Collection speichert **zwei Eintragstypen**, unterschieden über das
Metadatenfeld `type`:

| Feld           | `type = "chunk"`                          | `type = "question"`                     |
| -------------- | ----------------------------------------- | --------------------------------------- |
| `id`           | `<doc_id>::c<index>`                       | `<chunk_id>::q<n>` bzw. `::eq<n>` (enrich) |
| `document`     | Chunk-Text                                | generierte Frage                         |
| Embedding      | L2-normalisiert, 1024-dim (`bge-m3`)      | L2-normalisiert, 1024-dim                |
| `parent_id`    | entfällt                                         | ID des zugehörigen Chunks                |
| weitere Meta   | `doc_id`, `subject`, `filename`, `source_path`, `filetype`, `location`, `header_path`/`page`, `chunk_index` | erbt Chunk-Metadaten + `type`, `parent_id` |

Bei der Suche werden Frage-Treffer über `parent_id` auf ihren Chunk
zurückgeführt, damit dem LLM immer der **volle Chunk-Kontext** vorliegt. Chroma
erlaubt nur `str/int/float/bool` in den Metadaten; `None`/Listen werden vor dem
Speichern konvertiert (`_sanitize_meta`).

### Manifest (`data/manifest.db`, SQLite)

**Tabelle `documents`** (Registry + Dokument-Dedup):

`doc_id` (PK, Hash des relativen Pfads), `content_hash` (SHA-256 des Volltexts),
`source_path`, `filename`, `subject`, `filetype`, `num_chunks`, `num_questions`,
`char_count`, `status`, `ingested_at`, `updated_at`.

**Tabelle `chunk_hashes`** (exakte Chunk-Dedup):

`chunk_hash` (PK, SHA-256 des normalisierten Chunk-Texts), `doc_id`, `chunk_id`,
`created_at`. Index auf `doc_id`.

### Weitere Speicher

- **BM25-Index** (`data/bm25/bm25.pkl`): `ids`, `documents`, `metas`, das
  `BM25Okapi`-Objekt; aus allen Chunks der Vektor-DB neu aufgebaut.
- **Evaluation** (`data/eval/`): `gold_set.jsonl`, `eval_<ts>.json`,
  `per_query_<ts>.csv`, `history.jsonl` (siehe [EVALUATION.md](EVALUATION.md)).
- **Logs** (`data/logs/`): `ingestion.jsonl`, `queries.jsonl`.
- **Laufzeit-Config** (`data/config.json`): überschreibt Standardwerte aus
  `config.py` (siehe [TUNING.md](TUNING.md)).
