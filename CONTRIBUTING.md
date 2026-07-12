# Mitwirken am RAG-Lernsystem

Danke für dein Interesse! Bug-Reports, Ideen und Pull Requests sind willkommen.
Dieses Projekt ist ein **vollständig lokaler** RAG-Lernassistent (Streamlit + Ollama
+ ChromaDB) – Details siehe [README.md](README.md).

## 🐛 Fehler melden

Erstelle ein [Issue](https://github.com/edgebird-lab/RAG_System/issues/new/choose)
über die Vorlage **„Fehler melden"**. Am hilfreichsten sind:

- **Was erwartet** vs. **was passiert** ist (gern mit Screenshot),
- **System:** Betriebssystem (Windows / Linux / macOS) und **GPU-Hersteller**
  (NVIDIA / AMD / Apple / Intel / nur CPU),
- **Modell:** welches Antwort-Modell aktiv ist (Einstellungen bzw.
  `python -m ragapp.scripts.cli recommend`),
- **Logs:** relevante Zeilen aus `data/logs/` bzw. `streamlit.log`.

> ⚠️ **Keine persönlichen Dokumente / keine Datenbank** ins Issue hochladen –
> das Projekt ist bewusst lokal. Ein kurzer, anonymisierter Ausschnitt genügt.

## 💡 Funktion vorschlagen

Über die Vorlage **„Funktion vorschlagen"**. Beschreibe **das Problem/den
Anwendungsfall**, nicht nur die Lösung – das hilft, die beste Umsetzung zu finden.

## 🔧 Entwicklungs-Setup

```bash
git clone https://github.com/edgebird-lab/RAG_System.git
cd RAG_System
bash install.sh        # Linux/macOS: venv + Ollama + passendes Modell (erkennt die Hardware)
#   Windows: Installieren.bat
./start.sh             # bzw. Start.bat  ->  http://localhost:8501
```

Manuelle Einrichtung von Grund auf: [docs/SETUP.md](docs/SETUP.md).
Architektur & Datenflüsse: [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md).

### Schnelle Prüfungen vor einem PR

```bash
# Syntax/Import aller Module
python -m compileall ragapp

# End-to-End-Selbsttest der RAG-Pipeline (braucht indexierte Dokumente + Ollama)
python -m ragapp.scripts.verify

# Retrieval-Qualität messen (Gold-Set)
python -m ragapp.scripts.cli eval
```

**Gut zu wissen (nicht offensichtlich):** Streamlits `AppTest` **segfaultet**, wenn im
selben Prozess `torch` (ROCm) oder `chromadb` geladen ist und **mehrere** AppTests
laufen. Teste UI-Seiten daher mit **genau einem AppTest pro Subprozess**; Backend-Logik
lieber direkt (ohne `rag_graph`-Import, der `torch` zieht).

## 📦 Pull Requests

1. Branch von `main` erstellen.
2. Kleine, fokussierte Änderungen; **deutsche** Kommentare/Docstrings wie im Bestand.
3. Keine persönlichen Daten, keine `data/`- oder `.venv`-Inhalte committen
   (per `.gitignore` ausgeschlossen).
4. Kurz beschreiben **was & warum**; bei UI-Änderungen gern einen Screenshot.

## 🤝 Verhaltenskodex

Sei freundlich und respektvoll. Wir wollen einen einladenden, hilfsbereiten Umgang –
konstruktives Feedback, keine persönlichen Angriffe.

## 📄 Lizenz

Mit deinem Beitrag stimmst du zu, dass er unter der **MIT-Lizenz** des Projekts
([LICENSE](LICENSE)) veröffentlicht wird.
