# Mitwirken am RAG-Lernsystem

Danke für dein Interesse! Bug-Reports, Ideen und Pull Requests sind willkommen.
Dieses Projekt ist ein **vollständig lokaler** RAG-Lernassistent (Streamlit + Ollama
+ ChromaDB) – Details siehe [README.md](README.md).

## 🐛 Fehler melden

Erstelle ein [Issue](https://github.com/edgebird-lab/RAG_Uni_Lern_System/issues/new/choose)
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
git clone https://github.com/edgebird-lab/RAG_Uni_Lern_System.git
cd RAG_Uni_Lern_System
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

### Tests (pytest)

```bash
pip install -r requirements-dev.txt   # schlanker Stack wie in der CI: kein torch, keine GPU, kein Ollama-Server
pytest -q
```

Die Suite läuft **offline**: Ollama, Vektorindex und Modelle werden durch Attrappen ersetzt;
getestet wird die Logik. Was dabei wichtig ist:

- **Echte Nutzerdaten sind tabu.** `conftest.py` biegt für jeden Test die Sicherungen
  (`backup.BACKUP_DIR`/`MANIFEST_DB`) und die Tagesziel-Datei (`daily_goal.json`) auf Wegwerf-Pfade um –
  früher rotierten Tests, die Karten löschen, die **echten** Snapshots in `data/backups/`
  weg. Wer die Datenbank in einem Test umbiegt (`manifest.MANIFEST_DB`), muss das nicht
  extra für Backups tun. **Nie `data/config.json` schreiben:** `settings.save()` (z. B. über
  `study.mark_needs_card_harvest`) im Test patchen.
- **Optionale Pakete** überspringen sich selbst: Tests mit `torch`/`torchaudio` per
  `pytest.importorskip`, Browser-Tests (`tests/test_talk_presenter.py`), wenn kein Chromium
  startbar ist. Auf einem Rechner mit vorhandenem Chromium hilft
  `RAG_CHROMIUM_PATH=/pfad/zu/chrome pytest tests/test_talk_presenter.py` (oder
  `python -m playwright install chromium`).
- **CI lokal nachstellen** (zwei Jobs, Python 3.11): `python3.11 -m venv v && v/bin/pip install -r requirements-dev.txt && v/bin/python -m pytest -q`
  – am besten in einer **Kopie** des Repos. Der UI-Smoke (`python tests/live_smoke.py`, Port
  `RAG_SMOKE_PORT`, Standard 8511) startet eine **eigene** Streamlit-Instanz; richte ihn nie
  auf deine laufende App (Port 8501) – der Tab-Close-Wächter würde sie beenden.
- Neue Datei mit einem **schweren Import** (`torch`, `chromadb` …)? In `requirements-dev.txt` steht,
  was die CI installiert; alles andere per `importorskip` absichern.

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
