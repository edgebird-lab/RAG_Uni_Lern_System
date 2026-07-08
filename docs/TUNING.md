# Tuning – Trefferquote verbessern & nachjustieren

Alle Stellschrauben stecken in der `Settings`-Dataclass in `ragapp/config.py`.
Standardwerte sind auf **maximale Trefferquote für deutschsprachige
Klausur-Zusammenfassungen** ausgelegt. Änderungen wirken über
**Laufzeit-Overrides**: Werte in `data/config.json` überschreiben die
Standardwerte – genau das speichert die **Einstellungen-Seite** der UI, ohne den
Code anzufassen (`Settings.save()`). Der Reiz: nach einer Evaluation gezielt
**einen** Parameter ändern und erneut messen.

> **Wichtig:** Parameter, die den **Index** betreffen (Chunking, Embedding-Modell,
> Fragen-Indexierung), wirken erst nach **Neu-Ingestion** bzw. Anreicherung.
> Parameter, die nur die **Suche** betreffen (Top-K, RRF, Reranker, Relevanz,
> Retrieval-Dedup), wirken **sofort** bei der nächsten Frage – ideal zum schnellen
> Experimentieren.

---

## 1. Parameter-Referenz (aus `config.py`)

### Modelle (Ollama, lokal)

| Parameter | Standard | Wirkung |
| --------- | -------- | ------- |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Adresse des lokalen Ollama-Servers. |
| `LLM_MODEL` | `gemma4:e4b` | Haupt-LLM für die Antwortgenerierung und den Faithfulness-Check. |
| `LLM_MODEL_FAST` | `gemma4:e2b` | Schnelleres Hilfsmodell für Fragen-Generierung und Gold-Set. |
| `EMBED_MODEL` | `bge-m3` | Multilinguales Embedding-Modell (dense Retrieval). **Index-relevant.** |
| `EMBED_DIM` | `1024` | Vektor-Dimension von `bge-m3` (nur informativ). |
| `LLM_TEMPERATURE` | `0.1` | Kreativität des LLM. Niedrig = faktentreu, wenig Halluzination. |
| `LLM_NUM_CTX` | `8192` | Kontextfenster des LLM (Token). |
| `LLM_TIMEOUT` | `600` | Zeitbudget (s) für LLM-Läufe auf langsamer CPU. |

### Chunking (Slicing) — **Index-relevant, Neu-Ingestion nötig**

| Parameter | Standard | Wirkung |
| --------- | -------- | ------- |
| `CHUNK_SIZE` | `1100` | Zielgröße pro Chunk (Zeichen). Kleiner = präzisere Treffer, aber mehr Fragmentierung; größer = mehr Kontext, aber unschärfere Treffer. |
| `CHUNK_OVERLAP` | `180` | Überlappung benachbarter Chunks (Zeichen). Erhält Kontext an Schnittkanten; zu hoch = Redundanz. |
| `MIN_CHUNK_CHARS` | `120` | Kleinere Fragmente werden mit dem vorherigen Chunk zusammengeführt (Rauschen raus). |
| `RESPECT_MARKDOWN_HEADERS` | `True` | Markdown an Überschriften schneiden und den Überschriften-Pfad als semantischen Anker voranstellen. |

### Deduplizierung

| Parameter | Standard | Wirkung |
| --------- | -------- | ------- |
| `DEDUP_NEAR_DUPLICATE_THRESHOLD` | `0.965` | Kosinus-Schwelle für Near-Duplicate-Chunks **innerhalb eines Dokuments** (Ingestion). Höher = strenger (nur sehr Ähnliches gilt als Dublette). **Index-relevant.** |

### Fragen-Generierung (Hypothetical Questions)

| Parameter | Standard | Wirkung |
| --------- | -------- | ------- |
| `ENABLE_QUESTION_INDEXING` | `False` | Fragen pro Chunk beim Import mitindexieren. Steigert die Trefferquote, kostet aber auf CPU **~20 s/Chunk** → beim Bulk-Import bewusst AUS. **Index-relevant.** |
| `NUM_INDEX_QUESTIONS` | `3` | Anzahl generierter Fragen pro Chunk (bei aktiver Indexierung/Anreicherung). |

### Retrieval-Deduplizierung (gegen doppelte Infos in der Antwort)

| Parameter | Standard | Wirkung |
| --------- | -------- | ------- |
| `RETRIEVAL_DEDUP` | `True` | Near-Duplicate-Filter zur Query-Zeit an/aus. |
| `RETRIEVAL_DEDUP_JACCARD` | `0.82` | Token-Jaccard-Schwelle. Kandidaten mit Ähnlichkeit ≥ Wert gelten als Dublette; der niedriger platzierte fliegt raus. Niedriger = aggressiver entdoppeln. **Sofort wirksam.** |

### Retrieval (Hybrid: dense + BM25 → RRF → Rerank) — **sofort wirksam**

| Parameter | Standard | Wirkung |
| --------- | -------- | ------- |
| `DENSE_TOP_K` | `25` | Kandidaten aus der Vektorsuche. Mehr = höhere Chance, die richtige Stelle einzufangen (Recall ↑), aber mehr Rechenaufwand. |
| `BM25_TOP_K` | `25` | Kandidaten aus der Keyword-Suche. Wichtig für exakte Begriffe/Zahlen. |
| `RRF_K` | `60` | Konstante der Reciprocal Rank Fusion. Größer = flachere Gewichtung (Rangunterschiede zählen weniger); kleiner = Top-Ränge dominieren stärker. |
| `FUSION_TOP_K` | `20` | Anzahl Kandidaten nach der Fusion, die in Dedup + Rerank gehen. Mehr Kandidaten = mehr Chancen für den Reranker, aber langsamer. |
| `USE_RERANKER` | `True` | Cross-Encoder-Reranking an/aus. **Einer der stärksten Hebel** für die Trefferquote. Aus → schneller, aber ungenauer. |
| `RERANKER_MODEL` | `BAAI/bge-reranker-v2-m3` | Multilingualer Cross-Encoder (via `sentence-transformers`). |
| `FINAL_TOP_K` | `6` | Finale Chunks, die als Kontext ins LLM gehen. Mehr = mehr Kontext (evtl. vollständiger), aber Verwässerungsgefahr und mehr Tokens. |
| `DENSE_WEIGHT` | `1.0` | Gewicht der Dense-Liste in der RRF (greift v. a., wenn Rerank aus ist). |
| `BM25_WEIGHT` | `1.0` | Gewicht der BM25-Liste in der RRF. Höher = Keyword-Treffer bevorzugen. |

### Anti-Halluzination / Antwort-Politik

| Parameter | Standard | Wirkung |
| --------- | -------- | ------- |
| `RELEVANCE_MIN_SCORE` | `-2.0` | Mindest-Reranker-Score des besten Treffers, damit überhaupt frei geantwortet wird. Liegt der beste darunter → Fallback (Dokumente nennen). Höher = strenger (mehr Fallbacks, weniger Risiko); niedriger = großzügiger. |
| `ENABLE_FAITHFULNESS_CHECK` | `True` | Zusätzliche LLM-Prüfung, ob die Antwort durch den Kontext gedeckt ist. Aus → schneller, aber weniger Halluzinationsschutz. |
| `MAX_CONTEXT_CHARS` | `7000` | Obergrenze des an das LLM übergebenen Kontexts (Zeichen). |

### Evaluation

| Parameter | Standard | Wirkung |
| --------- | -------- | ------- |
| `EVAL_QUESTIONS_PER_CHUNK` | `1` | Held-out-Testfragen pro gesampeltem Chunk. |
| `EVAL_SAMPLE_SIZE` | `60` | Anzahl gesampelter Chunks fürs Gold-Set. Größer = robustere, aber langsamere Messung. |
| `EVAL_K_VALUES` | `(1, 3, 5, 10)` | k-Werte für Hit@k / Recall@k. Das größte k bestimmt, wie tief die Pipeline für die Messung sucht. |

### Sonstiges

| Parameter | Standard | Wirkung |
| --------- | -------- | ------- |
| `COLLECTION_NAME` | `zusammenfassungen` | Name der Chroma-Collection. |

---

## 2. Welche Stellschraube beeinflusst die Trefferquote – und wie?

- **`CHUNK_SIZE` / `CHUNK_OVERLAP`** (Index): der grundlegendste Hebel. Zu große
  Chunks vermischen mehrere Themen (unscharfe Treffer), zu kleine zerreißen
  Zusammenhänge. Für dichte Zusammenfassungen sind mittlere Chunks (~1000–1200
  Zeichen) mit moderatem Overlap ein guter Startpunkt. **Neu-Ingestion nötig.**
- **`DENSE_TOP_K` / `BM25_TOP_K`** (Recall): mehr Kandidaten = höhere Chance, die
  richtige Stelle überhaupt einzufangen. Kostet Tempo, aber die richtige Quelle
  kann nur gefunden werden, wenn sie in der Kandidatenmenge ist.
- **`FUSION_TOP_K`** (Übergabe an Rerank): begrenzt, wie viele Kandidaten der
  Reranker sieht. Zu klein = gute Treffer werden vor dem Rerank abgeschnitten.
- **`USE_RERANKER`** (Precision): sortiert die richtige Quelle nach oben →
  verbessert vor allem MRR und Hit@1..3 deutlich. Der wohl wirksamste einzelne
  Schalter.
- **`FINAL_TOP_K`** (Kontextbreite): wie viele Chunks das LLM sieht. Mehr kann
  Vollständigkeit erhöhen, aber auch verwässern und die Antwort verlangsamen.
- **`DENSE_WEIGHT` / `BM25_WEIGHT` / `RRF_K`**: feine Balance zwischen
  semantischer und lexikalischer Suche. Bei viel Fachvokabular/Zahlen `BM25_WEIGHT`
  leicht erhöhen; bei umschreibenden Fragen die Dense-Seite betonen.
- **`RELEVANCE_MIN_SCORE`**: verschiebt die Grenze zwischen „belegter Antwort" und
  „Fallback". Höher = vorsichtiger (mehr Fallbacks), niedriger = mehr freie
  Antworten (mehr Risiko). Beeinflusst nicht das Retrieval selbst, aber das
  gefühlte Verhalten.
- **`ENABLE_QUESTION_INDEXING` bzw. `enrich`**: zusätzliche indexierte Fragen
  bringen Nutzerfragen näher an den richtigen Chunk (Multi-Representation) →
  spürbar bessere Trefferquote, besonders bei Verständnisfragen. Auf CPU gezielt
  via `enrich` statt global.
- **Dedup-Schwellen** (`DEDUP_NEAR_DUPLICATE_THRESHOLD`,
  `RETRIEVAL_DEDUP_JACCARD`): zu aggressiv → nützliche, leicht abweichende Stellen
  verschwinden (Recall ↓); zu lasch → doppelte Infos im Kontext. Im Zweifel eher
  konservativ (hohe Schwelle) lassen.

---

## 3. Empfohlener Tuning-Workflow

Immer **datenbasiert** und **eine Änderung nach der anderen** – sonst weißt du
nicht, was gewirkt hat:

1. **Gold-Set erzeugen** (einmalig bzw. nach größeren Index-Änderungen):

   ```powershell
   python -m ragapp.scripts.cli gold --sample 60
   ```

2. **Basiswert messen:**

   ```powershell
   python -m ragapp.scripts.cli eval
   ```

   → notiert Hit@1/3/5/10 und MRR, speichert Report + `history.jsonl`.

3. **Genau einen Parameter ändern** – am bequemsten auf der **Einstellungen-Seite**
   (schreibt nach `data/config.json`) oder direkt in dieser Datei. Beispiel:
   `FUSION_TOP_K` von 20 auf 30, oder `USE_RERANKER` testweise aus.

4. **Erneut messen** (`eval`). Betrifft die Änderung nur die Suche, genügt das.
   Bei **Index-Parametern** (Chunking, Embedding, Fragen) vorher
   **neu ingestieren** bzw. `enrich`/`reset`+`ingest`, und danach ein **frisches
   Gold-Set** ziehen (die Chunk-IDs ändern sich!).

5. **Verlauf vergleichen:** In `data/eval/history.jsonl` (und im Evaluation-
   Dashboard) stehen alle Läufe mit ihrer Konfiguration nebeneinander. Behalte die
   Änderung, wenn Hit@k/MRR steigen; sonst zurücknehmen.

> Merke: Nach jeder Neu-Ingestion mit anderem Chunking/Embedding **muss** das
> Gold-Set neu erzeugt werden, weil es auf konkrete `chunk_id`s verweist. Sonst
> misst du gegen nicht mehr existierende IDs.

---

## 4. Weitergehende Finetuning-Optionen

- **Mehr Fragen-Anreicherung:** `enrich --limit` schrittweise erhöhen (ggf. pro
  Fach mit `--subject`). Ideal für die wichtigsten Zusammenfassungen. Danach
  messen – der Effekt ist bei Verständnisfragen am größten.
- **Anderes Embedding-Modell:** `EMBED_MODEL` austauschen (muss über Ollama
  verfügbar sein). Achtung: erfordert **komplette Neu-Ingestion**, da alle Vektoren
  neu berechnet werden, und ändert ggf. `EMBED_DIM`.
- **Anderer Reranker:** `RERANKER_MODEL` auf ein anderes `sentence-transformers`-
  Cross-Encoder-Modell setzen. Wirkt sofort (kein Neu-Index), lädt beim ersten
  Aufruf das Modell.
- **Chunk-Strategie:** `RESPECT_MARKDOWN_HEADERS` und `CHUNK_SIZE`/`OVERLAP`
  gemeinsam betrachten. Für gut strukturierte Markdown-Skripte ist Header-Splitting
  meist überlegen; für fließende PDFs zählt eher die Chunk-Größe.
- **Balance Tempo/Genauigkeit:** Auf sehr langsamer CPU kann man `USE_RERANKER`
  oder `ENABLE_FAITHFULNESS_CHECK` abwägen. Beide erhöhen Qualität bzw.
  Halluzinationsschutz, kosten aber Zeit.

---

## 5. Symptom → Stellschraube

| Symptom | Wahrscheinliche Ursache | Stellschraube(n) |
| ------- | ----------------------- | ---------------- |
| Richtige Quelle taucht gar nicht unter den Treffern auf | zu wenig Kandidaten (Recall) | `DENSE_TOP_K` ↑, `BM25_TOP_K` ↑, `FUSION_TOP_K` ↑ |
| Richtige Quelle ist dabei, aber weit hinten (niedriger MRR) | schwache Feinsortierung | `USE_RERANKER = True`, `FINAL_TOP_K` moderat ↑ |
| Exakte Fachbegriffe/Zahlen werden verfehlt | Dense dominiert | `BM25_WEIGHT` ↑, `BM25_TOP_K` ↑ |
| Umschreibende/Verständnisfragen treffen schlecht | reine Textrepräsentation | Fragen-Anreicherung (`enrich`) / `ENABLE_QUESTION_INDEXING` |
| Zu viele Fallbacks, obwohl Inhalt vorhanden | Relevanzschwelle zu streng | `RELEVANCE_MIN_SCORE` ↓ |
| Halluzinationen / unbelegte Aussagen | Antwort-Politik zu locker | `ENABLE_FAITHFULNESS_CHECK = True`, `RELEVANCE_MIN_SCORE` ↑, `LLM_TEMPERATURE` ↓ |
| Antwort enthält dieselbe Info doppelt | Retrieval-Dedup zu lasch | `RETRIEVAL_DEDUP = True`, `RETRIEVAL_DEDUP_JACCARD` ↓ |
| Treffer vermischen mehrere Themen | Chunks zu groß | `CHUNK_SIZE` ↓ (Neu-Ingestion) |
| Zusammenhänge zerrissen, Kontext fehlt | Chunks zu klein / kein Overlap | `CHUNK_SIZE` ↑, `CHUNK_OVERLAP` ↑ (Neu-Ingestion) |
| Verwechslung zwischen Fächern | fachübergreifende Suche | Fach-Filter in der UI (bzw. `ask --subject`) |
| Alles sehr langsam | CPU-Last durch Rerank/Faithfulness | `FUSION_TOP_K` ↓, ggf. `USE_RERANKER`/`ENABLE_FAITHFULNESS_CHECK` abwägen |
| Nützliche, leicht abweichende Stellen fehlen | Dedup zu aggressiv | `RETRIEVAL_DEDUP_JACCARD` ↑, `DEDUP_NEAR_DUPLICATE_THRESHOLD` ↑ |

Wie du diese Effekte belastbar misst, steht in [EVALUATION.md](EVALUATION.md).
