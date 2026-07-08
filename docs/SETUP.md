# Installation & Einrichtung

Diese Anleitung beschreibt die Installation von Grund auf – für einen
Windows-11-Rechner **ohne NVIDIA-GPU** (CPU-Inferenz). Alle Kommandos sind für
die **Windows PowerShell** gedacht.

---

## 1. Voraussetzungen

| Komponente | Version / Hinweis |
| ---------- | ----------------- |
| Betriebssystem | Windows 11 |
| Python     | **3.13** |
| Ollama     | aktuelle Version, installiert und laufend (Dienst/Tray-Icon) |
| Festplatte | Platz für Modelle (mehrere GB) + `data/`-Index |
| GPU        | keine erforderlich – das System ist auf CPU ausgelegt |

Prüfe, dass Python und Ollama verfügbar sind:

```powershell
python --version        # sollte 3.13.x zeigen
ollama --version
```

---

## 2. Ollama-Modelle bereitstellen

Das System nutzt drei lokale Modelle über Ollama. Das **Haupt-LLM `gemma4:e4b`**
und das **Hilfsmodell `gemma4:e2b`** sind auf diesem Rechner bereits vorhanden.
Neu gezogen werden muss lediglich das **Embedding-Modell**:

```powershell
ollama pull bge-m3
```

Falls die Gemma-Modelle auf einem anderen Rechner noch fehlen:

```powershell
ollama pull gemma4:e4b
ollama pull gemma4:e2b
```

Vorhandene Modelle auflisten:

```powershell
ollama list
```

> Ollama muss beim Betrieb des Systems **laufen** und unter
> `http://localhost:11434` erreichbar sein (Standard). Dieser Wert steht in
> `ragapp/config.py` als `OLLAMA_BASE_URL`.

Der **Reranker** (`BAAI/bge-reranker-v2-m3`) läuft **nicht** über Ollama, sondern
über `sentence-transformers`. Er wird beim ersten Retrieval automatisch aus dem
Hugging-Face-Hub geladen (einmaliger Download) und danach lokal aus dem Cache
ausgeführt.

---

## 3. Virtuelle Umgebung erstellen & aktivieren

Die virtuelle Umgebung liegt im Projekt unter `d:\RAG\.venv`.

```powershell
cd d:\RAG

# Falls noch nicht vorhanden: venv anlegen
python -m venv .venv

# Aktivieren (Windows PowerShell)
.\.venv\Scripts\Activate.ps1
```

Sollte das Aktivieren an der PowerShell-Ausführungsrichtlinie scheitern, hilft
für die aktuelle Sitzung:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Alternativ (funktioniert immer, auch ohne Aktivierung) lassen sich alle Kommandos
direkt über den venv-Interpreter aufrufen – genau das tun auch die mitgelieferten
`.bat`-Dateien:

```powershell
.\.venv\Scripts\python.exe -m ragapp.scripts.cli stats
```

---

## 4. Abhängigkeiten installieren

**Wichtig – Reihenfolge beachten:** Zuerst wird `torch` als **CPU-Build**
installiert (ohne CUDA), erst danach der Rest. So wird nicht versehentlich eine
große GPU-Variante gezogen.

```powershell
# 1) PyTorch als CPU-Build
pip install torch --index-url https://download.pytorch.org/whl/cpu

# 2) Restliche Abhängigkeiten
pip install -r requirements.txt
```

`requirements.txt` enthält u. a.: `langgraph`, `langchain(-core/-community/-ollama)`,
`ollama`, `chromadb`, `pymupdf`/`pypdf`, `python-docx`, `python-pptx`,
`python-frontmatter`, `rank-bm25`, `snowballstemmer`, `sentence-transformers`,
`streamlit`, `plotly`, `pandas`, `numpy`, `watchdog`, `tqdm`.

`torch` wird bewusst **nicht** in `requirements.txt` gepinnt, damit die CPU-Wheel-
Quelle genutzt werden kann.

---

## 5. Verifikation

```powershell
# a) Kann das Paket importiert werden und ist der Index initialisiert?
python -m ragapp.scripts.cli stats
#    -> zeigt Dokumente/Chunks/Fragen/Fächer (anfangs 0) und Chroma-Einträge.

# b) Dokumente einlesen (Quellordner "Zusammenfassungen SoSE26")
python -m ragapp.scripts.cli ingest

# c) Eine Testfrage stellen (nach dem Import)
python -m ragapp.scripts.cli ask "Was ist ein Deckungsbeitrag?"

# d) Weboberfläche starten
streamlit run ragapp/ui/Home.py
```

Erscheint bei `ask` eine belegte Antwort mit Quellen (oder ein ehrlicher
Fallback mit Fundstellen), funktioniert die gesamte Kette: Ollama, Embeddings,
Chroma, BM25, Reranker und der LangGraph-Ablauf.

---

## 6. Troubleshooting

### Ollama nicht erreichbar

Symptome: Fehler wie „connection refused", `Embedding fehlgeschlagen`,
`LLM-Aufruf fehlgeschlagen`, oder lange Hänger.

- Prüfe, ob Ollama läuft: `ollama list` muss ohne Fehler eine Modellliste zeigen.
- Prüfe die Adresse: Standard ist `http://localhost:11434`
  (`OLLAMA_BASE_URL` in `config.py`).
- Sind die Modelle da? Ggf. `ollama pull bge-m3` / `ollama pull gemma4:e4b`.
- Der Embedder wiederholt fehlgeschlagene Aufrufe automatisch (3 Versuche mit
  Wartezeit); der LLM-Client ebenfalls (Retry). Bleibt es rot, liegt es fast
  immer an einem gestoppten Ollama-Dienst oder einem fehlenden Modell.

### torch / Reranker lädt nicht → automatischer Fallback

- Lässt sich der Cross-Encoder nicht laden (z. B. `torch`-Problem oder kein
  Internet beim ersten Download), gibt der Reranker eine **Warnung** aus und das
  System fällt automatisch auf die **RRF-Fusions-Reihenfolge** zurück. Es bleibt
  funktionsfähig – nur die Feinsortierung fehlt (etwas niedrigere Trefferquote).
- Reparatur: `torch` sauber als CPU-Build neu installieren (siehe §4), dann
  `sentence-transformers` erneut installieren. Beim ersten erfolgreichen
  Retrieval wird das Reranker-Modell heruntergeladen.
- Zum bewussten Deaktivieren kann `USE_RERANKER` auf `false` gesetzt werden
  (Einstellungen/`data/config.json`), siehe [TUNING.md](TUNING.md).

### <a id="performance-cpu"></a>Langsame CPU-Inferenz (normal!)

Ohne GPU ist die Inferenz langsam – das ist erwartbar, kein Fehler. Grobe
Richtwerte auf diesem System:

| Vorgang | grober Richtwert |
| ------- | ---------------- |
| Eine LLM-Antwort (inkl. Faithfulness-Check) | **~20–40 s** |
| Embedding | **~1–2 Chunks/s** |
| Fragen-Generierung pro Chunk (`enrich`/Question-Indexing) | **~20 s/Chunk** |

Konsequenzen und Gegenmaßnahmen:
- Der **Bulk-Import** ist dank abgeschalteter Fragen-Generierung
  (`ENABLE_QUESTION_INDEXING=False`) vergleichsweise flott; Fragen werden nur
  gezielt via `enrich` nachgezogen.
- Mit dem **Fach-Filter** in der UI wird die Suche kleiner und schneller.
- Der `LLM_TIMEOUT` in `config.py` (Standard 600 s) ist bewusst großzügig, damit
  lange CPU-Läufe nicht abbrechen.

### Speicher / Platz

- Modelle (Ollama) und der `sentence-transformers`-Cache belegen mehrere GB im
  Benutzerprofil.
- Der lokale Index liegt unter `data/` (`chroma/`, `bm25/`, `manifest.db`). Er
  lässt sich jederzeit mit `python -m ragapp.scripts.cli reset --yes` komplett
  leeren und per `ingest` neu aufbauen.
- Bei sehr großem Korpus die Batch-Größe im Blick behalten; Embeddings werden in
  Blöcken zu 32 verarbeitet.

### „Nicht unterstütztes Format"

Unterstützt werden `.pdf`, `.md`, `.markdown`, `.txt`, `.docx`, `.pptx`. Andere
Dateien werden beim Import übersprungen (Status `skipped`).

---

## 7. Start im Alltag

Nach der Einrichtung genügen im Regelfall die Doppelklick-Starthilfen im
Projektordner:

- `Start_Oberflaeche.bat` → Chat-Oberfläche im Browser.
- `Dokumente_importieren.bat` → alle Quelldokumente (neu) einlesen.
- `Auto_Ueberwachung.bat` → Ordnerwächter für automatischen Import.

Die tägliche Nutzung ist in [BEDIENUNG.md](BEDIENUNG.md) beschrieben.
