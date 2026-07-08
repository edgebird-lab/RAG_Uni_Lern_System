# Bedienung im Alltag

Diese Anleitung zeigt, wie du mit dem System für Klausuren lernst: Oberfläche
starten, gute Fragen stellen, Antworten richtig deuten, neue Dokumente
hinzufügen – plus eine Referenz aller CLI-Kommandos.

---

## 1. Die Oberfläche starten

**Einfachste Variante:** Doppelklick auf `Start_Oberflaeche.bat` im Projektordner.
Der Browser öffnet sich unter `http://localhost:8501`.

**Manuell (PowerShell):**

```powershell
cd d:\RAG
.\.venv\Scripts\Activate.ps1
streamlit run ragapp/ui/Home.py
```

Die Startseite ist der **Chat** („Frag deine Zusammenfassungen"). In der linken
Seitenleiste findest du:

- **Modell-/Statusanzeige** (verwendetes LLM und Embedding).
- **Kennzahlen**: Anzahl Dokumente, Chunks, Fragen, Fächer.
- **Fach filtern** – schränkt die Suche auf ein Fach ein (schneller & präziser).
- **Quellen anzeigen** (Schalter) – blendet die Quellenkarten ein/aus.
- **Verlauf löschen** – leert die aktuelle Chat-Sitzung.
- Hinweis auf die weiteren Seiten **Ingestion**, **Evaluation**, **Einstellungen**
  (linke Navigation).

Ist noch nichts indexiert, weist die Oberfläche darauf hin, zuerst Dokumente zu
importieren.

---

## 2. Gute Fragen stellen

Das System beantwortet Fragen **ausschließlich aus deinen Unterlagen**. Ein paar
Faustregeln für hohe Trefferquote:

- **Konkret statt vage.** „Wie berechnet man den Deckungsbeitrag je Stück?" ist
  besser als „Erklär mir alles zu Kosten".
- **Fachbegriffe nennen.** Der BM25-Teil der Suche belohnt exakte Begriffe,
  Abkürzungen und Formelnamen (z. B. „Herfindahl-Index", „Cournot-Nash").
- **Fach-Filter nutzen**, wenn du weißt, aus welchem Fach die Frage stammt – das
  reduziert Verwechslungen zwischen Fächern und beschleunigt die Antwort.
- **Eine Frage pro Eingabe.** Mehrere Themen in einem Satz verwässern die Suche.
- **Umformulieren hilft.** Findet das System nichts, frag mit anderen Worten oder
  einem anderen Kernbegriff.

Rechne auf CPU-Hardware mit **~20–40 Sekunden** pro Antwort – der Spinner
(„Suche in deinen Unterlagen und denke nach…") zeigt an, dass gearbeitet wird.

---

## 3. Antworten deuten: Badge & Quellenkarten

Unter jeder Antwort steht ein **Badge**, das den Modus kennzeichnet:

| Badge | Bedeutung |
| ----- | --------- |
| 🟢 **belegte Antwort** (`answer`) | Die Antwort stützt sich auf gefundene Stellen und hat die Faithfulness-Prüfung bestanden. Zentrale Aussagen sind mit `[Quelle N]` belegt. |
| 🟠 **Fallback: passende Dokumente** (`fallback`) | Das System war sich **nicht sicher genug** und hat bewusst **nicht** frei geantwortet. Statt zu raten, nennt es die am besten passenden Dokumente/Stellen zum Nachschlagen. |

Ein Fallback tritt auf, wenn (a) schon die Suche zu schwach war (Relevanz-Gate),
(b) das Modell selbst signalisiert hat, dass die Info fehlt
(`KEINE_AUSREICHENDE_INFORMATION`), oder (c) die Faithfulness-Prüfung die Antwort
nicht als gedeckt bestätigt hat. Das ist gewollt – es schützt dich vor erfundenen
Fakten beim Lernen.

**Quellenkarten** (wenn „Quellen anzeigen" aktiv) zeigen pro Treffer:

- **[Rang] Dateiname** und **Fundstelle** (z. B. „Seite 4", „Folie 7" oder den
  Markdown-Überschriften-Pfad).
- **Fach**, **Score** (Reranker- bzw. Fusionswert) und **Retriever**
  (`dense`, `bm25` oder beides) – woher der Treffer stammt.
- Über „Textstelle ansehen" lässt sich der Originalausschnitt aufklappen.

Nutze die Quellenkarten, um die Antwort gegen dein Skript zu prüfen – das ist
beim Lernen mindestens so wertvoll wie die Antwort selbst.

---

## 4. Neue Dokumente hinzufügen (3 Wege)

Unterstützte Formate: `.pdf`, `.md`, `.markdown`, `.txt`, `.docx`, `.pptx`.
Das **Fach** ergibt sich aus dem **ersten Unterordner** unter
`Zusammenfassungen SoSE26` (z. B. `…\KuLR\skript.pdf` → Fach `KuLR`).

### Weg A – Datei in den Ordner legen + Import/Wächter

1. Datei nach `Zusammenfassungen SoSE26\<Fach>\` (oder nach `data\inbox\`) kopieren.
2. Entweder einmalig importieren …

   ```powershell
   python -m ragapp.scripts.cli ingest
   ```

   … oder den **Ordnerwächter** laufen lassen, der neue/geänderte Dateien
   **automatisch** indexiert (Doppelklick `Auto_Ueberwachung.bat` oder):

   ```powershell
   python -m ragapp.scripts.cli watch
   ```

Der Import ist **resumierbar**: Bereits vorhandene, unveränderte Dateien werden
übersprungen; geänderte werden aktualisiert (alte Chunks entfernt, neu erzeugt).

### Weg B – Einzelne Datei per CLI

```powershell
python -m ragapp.scripts.cli ingest-file "C:\Pfad\zu\meiner\Zusammenfassung.pdf"
```

### Weg C – Über die Weboberfläche

Die Oberfläche hat links drei Unterseiten:

- **📥 Ingestion** – Dateien hochladen (mit Fach-Zuordnung) und indexieren,
  den kompletten Quellordner importieren, die **Fragen-Anreicherung** starten,
  alle indexierten Dokumente als Tabelle sehen und einzelne löschen.
- **📊 Evaluation** – Gold-Set erzeugen, Trefferquote (Hit@k / MRR) messen und
  den Verlauf über die Zeit vergleichen (zum Nachjustieren).
- **⚙️ Einstellungen** – alle Tuning-Parameter ändern und in `data/config.json`
  speichern; auf Standard zurücksetzen.

Die Ingestion-Seite nutzt dieselbe Pipeline wie die CLI (`ingest_directory` /
`ingest_file`) – Datei auswählen bzw. Import anstoßen, der Rest (Laden → Dedup →
Chunking → Embeddings → Speichern) läuft automatisch.

> **Datei-Auswahl:** Anki-/Karteikarten-Dateien (`*anki*`, `*karteikart*`) und
> `.md`/`.txt`, zu denen es eine gleichnamige PDF gibt, werden **automatisch
> ausgeschlossen** (sie duplizieren die PDF-Inhalte). Einzigartige
> `.md`-Zusammenfassungen ohne PDF-Gegenstück (z. B. die ausführliche
> `KuLR_Klausur_Zusammenfassung.md`) bleiben erhalten. Einstellbar über
> `INGEST_EXCLUDE_NAME_SUBSTRINGS` und `INGEST_SKIP_PDF_DUPLICATE_MD` in `config.py`.

> **Nach Fach suchen:** Jedes Dokument ist seinem Fach zugeordnet (aus dem
> Ordnernamen). Wähle links im Interface unter **„Fach filtern"** z. B. `KuLR`,
> dann durchsucht das System ausschließlich KuLR – Fächer wie Analysis oder DSA
> werden gar nicht betrachtet (schneller und präziser).

> Hinweis: Der Erstimport eines großen Korpus dauert auf CPU sehr lange und
> blockiert die Weboberfläche. Für den **Erstimport** ist das CLI
> (`python -m ragapp.scripts.cli ingest`) oder der Ordnerwächter besser geeignet;
> beide laufen im Hintergrund und sind unterbrechbar/fortsetzbar.

> Egal welcher Weg: Doppelte Dokumente werden über den Inhalts-Hash erkannt und
> nicht doppelt indexiert. Nach dem Import wird der BM25-Index automatisch
> aktualisiert.

---

## 5. CLI-Referenz

Aufruf immer als Modul (aus dem aktivierten venv):
`python -m ragapp.scripts.cli <kommando> [optionen]`

| Kommando      | Optionen | Wirkung | Beispiel |
| ------------- | -------- | ------- | -------- |
| `ingest`      | `--dir <ordner>`, `--force` | Ganzen Ordner einlesen (Standard: Quellordner). `--force` importiert auch Unverändertes neu. | `... ingest` |
| `ingest-file` | `<pfad>` (Pflicht), `--force` | Einzelne Datei einlesen. | `... ingest-file skript.pdf` |
| `watch`       | – | Quell- + Inbox-Ordner überwachen und neue/geänderte Dateien automatisch importieren (Strg+C beendet). | `... watch` |
| `gold`        | `--sample <n>` | Held-out-Gold-Set für die Evaluation erzeugen (Standard-Stichprobe aus `EVAL_SAMPLE_SIZE`). | `... gold --sample 60` |
| `enrich`      | `--limit <n>` (Std. 200), `--subject <Fach>` | Hypothetische Fragen für die wichtigsten Chunks erzeugen und indexieren (opt-in, resumierbar). | `... enrich --limit 100 --subject KuLR` |
| `eval`        | – | Trefferquote gegen das Gold-Set messen (Hit@k, MRR) und Ergebnisse speichern. | `... eval` |
| `ask`         | `<frage>` (Pflicht), `--subject <Fach>` | Eine Frage direkt im Terminal beantworten (mit Modus, Belegtheit, Quellen). | `... ask "Was ist ein Deckungsbeitrag?"` |
| `stats`       | – | Statusübersicht: Dokumente, Chunks, Fragen, Fächer, Chroma-Einträge, Dokumentliste. | `... stats` |
| `reset`       | `--yes` (Pflicht zur Ausführung) | Index **und** Manifest komplett leeren. Ohne `--yes` nur Sicherheitshinweis. | `... reset --yes` |

Typischer Ablauf beim ersten Einrichten:

```powershell
python -m ragapp.scripts.cli ingest          # Dokumente einlesen
python -m ragapp.scripts.cli stats           # prüfen, was drin ist
python -m ragapp.scripts.cli enrich --limit 200   # optional: Trefferquote steigern
python -m ragapp.scripts.cli gold --sample 60     # Testfragen erzeugen
python -m ragapp.scripts.cli eval            # Trefferquote messen
```

---

## 6. Wenn eine Antwort falsch oder leer ist

| Situation | Was tun |
| --------- | ------- |
| **Fallback, obwohl das Thema in den Unterlagen steht** | Frage konkreter/mit dem exakten Fachbegriff umformulieren. Fach-Filter setzen. Prüfen, ob das Dokument wirklich importiert ist (`stats`). Ggf. `enrich` für das Fach laufen lassen (Fragen-Indexierung erhöht die Trefferquote). |
| **Gar keine Treffer / „keine passende Stelle"** | Dokument evtl. nicht indexiert oder Format nicht unterstützt. `stats` prüfen, ggf. neu importieren. Bei PDFs ohne Textebene (reine Scans) wird kein Text extrahiert. |
| **Antwort wirkt unvollständig** | Der Kontext ist auf `MAX_CONTEXT_CHARS`/`FINAL_TOP_K` begrenzt. Frage enger stellen oder in Teilfragen zerlegen; die Quellenkarten zeigen weitere Fundstellen. |
| **Antwort wirkt falsch** | Immer gegen die Quellenkarte prüfen. Ist die richtige Quelle gar nicht unter den Treffern, ist es ein **Retrieval**-Problem → siehe [TUNING.md](TUNING.md) und [EVALUATION.md](EVALUATION.md). |
| **Alles zu langsam** | Normal auf CPU. Fach-Filter nutzen; ggf. `USE_RERANKER`/`ENABLE_FAITHFULNESS_CHECK` in den Einstellungen abwägen (weniger Genauigkeit gegen mehr Tempo). |

Alle Anfragen werden in `data/logs/queries.jsonl` protokolliert (Frage, Modus,
Belegtheit, Top-Quellen, Zeiten) – nützlich, um Muster bei schwachen Antworten zu
erkennen und gezielt nachzujustieren.
