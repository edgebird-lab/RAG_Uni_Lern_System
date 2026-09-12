"""
Zentrale Konfiguration des RAG-Lernsystems
==========================================

Alle einstellbaren Parameter des Systems sind hier gebündelt. Die Standardwerte
sind auf **maximale Trefferquote** für deutschsprachige Klausur-Zusammenfassungen
optimiert.

Laufzeit-Overrides:
    Werte in ``data/config.json`` überschreiben die Standardwerte. So kann die
    Weboberfläche (Seite "Einstellungen") Parameter ändern und persistent
    speichern, ohne den Code anzufassen. Genau dieser Mechanismus erlaubt das
    "Nachjustieren" nach einer Evaluation.

Nutzung:
    from ragapp.config import settings
    print(settings.LLM_MODEL)
"""
from __future__ import annotations

import os
# --------------------------------------------------------------------------- #
# pyarrow-Speicher-Allocator auf "system" zwingen (verhindert nativen Absturz)
# --------------------------------------------------------------------------- #
# pyarrow bringt standardmaessig den jemalloc-Allocator mit. Ist im selben Prozess
# auch torch geladen (Reranker/sentence-transformers), kollidieren jemalloc und
# torchs eigener Allocator -> Segmentation fault, sobald pyarrow arbeitet. In der
# Weboberflaeche passiert das genau beim Rendern einer Tabelle (st.dataframe/
# st.data_editor serialisiert ueber pyarrow): jede Seite mit Tabelle (Ingestion/
# Lernen/Fortschritt ...) kann den GANZEN Streamlit-Server abschiessen -> im
# Browser "Streamlit server is not responding", schon beim blossen Reiter-Wechseln
# kurz nach dem Start (sobald der Reranker warm ist). Mit dem System-Allocator
# entfaellt der jemalloc-Konflikt. MUSS vor dem ersten ``import pyarrow`` gesetzt
# werden - config.py wird praktisch ueberall als Erstes importiert, daher hier.
# ``setdefault`` respektiert eine bewusst gesetzte Umgebungsvariable.
os.environ.setdefault("ARROW_DEFAULT_MEMORY_POOL", "system")

import json
from dataclasses import dataclass, asdict, field, fields
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Pfade
# --------------------------------------------------------------------------- #
# Projektwurzel = d:\RAG  (zwei Ebenen über dieser Datei: ragapp/config.py)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Quell-Dokumente: nimmt den ersten existierenden Kandidaten (portabel).
# Auf diesem Rechner "Zusammenfassungen SoSE26"; bei einer frischen Installation
# der generische Ordner "Zusammenfassungen". Kann per Umgebungsvariable
# RAG_SOURCE_DIR überschrieben werden.
import os as _os
_SOURCE_CANDIDATES = ["Zusammenfassungen SoSE26", "Zusammenfassungen"]
if _os.environ.get("RAG_SOURCE_DIR"):
    SOURCE_DIR = Path(_os.environ["RAG_SOURCE_DIR"])
else:
    SOURCE_DIR = next(
        (PROJECT_ROOT / c for c in _SOURCE_CANDIDATES if (PROJECT_ROOT / c).is_dir()),
        PROJECT_ROOT / "Zusammenfassungen",
    )
INBOX_DIR = PROJECT_ROOT / "data" / "inbox"             # Ablage für neue Dateien
DATA_DIR = PROJECT_ROOT / "data"
CHROMA_DIR = DATA_DIR / "chroma"                        # Vektordatenbank
BM25_DIR = DATA_DIR / "bm25"                            # BM25-Index (pickle)
EVAL_DIR = DATA_DIR / "eval"                            # Evaluationsergebnisse
LOG_DIR = DATA_DIR / "logs"                             # Query-/Ingestion-Logs
MANIFEST_DB = DATA_DIR / "manifest.db"                  # SQLite: Dedup + Registry
RUNTIME_CONFIG_FILE = DATA_DIR / "config.json"          # Laufzeit-Overrides
SHUTDOWN_SENTINEL = DATA_DIR / ".shutdown"              # Signal zum sauberen Beenden (Beenden-Button -> Starter)
OPEN_WINDOW_FILE = DATA_DIR / ".open_window"            # Signal: zweites App-Fenster oeffnen (Button -> Starter)
UI_RESTART_FILE = DATA_DIR / ".restart_ui"             # Modus-Wechsel aus der App (Inhalt: "local"/"network"/"tunnel")
UI_MODE_FILE = DATA_DIR / ".mode"                      # aktueller Zugriffsmodus (der Starter schreibt ihn)
VOICE_DIR = DATA_DIR / "voice"                          # eigene Stimm-Referenzaufnahme (Audio-Overview)
AUDIO_DIR = DATA_DIR / "audio_overviews"                # erzeugte Audio-Overview-WAVs
AUDIOBOOK_DIR = DATA_DIR / "audiobooks"                 # exportierte Hörbuch-ZIPs (siehe ragapp/audiobook.py)

for _p in (DATA_DIR, CHROMA_DIR, BM25_DIR, EVAL_DIR, LOG_DIR, INBOX_DIR):
    _p.mkdir(parents=True, exist_ok=True)


@dataclass
class Settings:
    """Alle tunebaren Parameter. Änderbar über data/config.json."""

    # ------------------------------------------------------------------ #
    # Modelle (Ollama, lokal)
    # ------------------------------------------------------------------ #
    OLLAMA_BASE_URL: str = "http://localhost:11434"   # Ollama-Server für das LLM (Antworten)
    # Separater Ollama-Server für Embeddings. Leer -> nutzt OLLAMA_BASE_URL.
    # Für die Intel-iGPU (IPEX-LLM) z. B. "http://127.0.0.1:11435" -> ~8x schnellere Embeddings.
    EMBED_OLLAMA_URL: str = ""
    # Sicherer Standard, der auf JEDEM Backend laedt (auch altes Intel-IPEX/SYCL) und
    # gutes Deutsch liefert. Auf staerkerer Hardware wird ueber die Einstellungen
    # (Hardware-Empfehlung) auf ein groesseres Modell hochgestuft. Gemma 4 z. B. laedt
    # auf dem alten IPEX-Backend NICHT - daher nicht als globaler Default.
    LLM_MODEL: str = "gemma3:4b"           # Haupt-LLM (Antwortgenerierung)
    LLM_MODEL_FAST: str = "gemma3:4b"      # Modell fuer Hilfsaufgaben (Fragen, Checks)
    # Grosses, kluges Modell NUR fuer Batch-Content-Erzeugung (z. B. Klausur-
    # Lernkatalog). Leer = Fallback auf LLM_MODEL (kein zweites Modell laden).
    # Bewusst NICHT im interaktiven Chat-Pfad verwendet, damit dort kein
    # Ollama-Swap entsteht. Aufloesung ueber settings.author_model().
    LLM_MODEL_AUTHOR: str = ""             # "" -> author_model() faellt auf LLM_MODEL zurueck
    EMBED_MODEL: str = "bge-m3"            # multilinguales Embedding (1024-dim)
    EMBED_DIM: int = 1024
    # Parallele Embedding-Anfragen an Ollama. HINWEIS (empirisch gemessen):
    # Bei langen, echten Chunks bringt Parallelität auf dieser CPU praktisch nichts
    # (speicherbandbreiten-limitiert). concurrency=2 war im A/B-Test minimal am
    # besten; der eigentliche Speed-Hebel ist die GPU, nicht mehr CPU-Threads.
    EMBED_CONCURRENCY: int = 2
    EMBED_BATCH_SIZE: int = 24             # Texte pro Anfrage

    # LLM-Generierung
    LLM_TEMPERATURE: float = 0.1           # niedrig = faktentreu, wenig Halluzination
    # Grosszuegig bemessen (nicht das technische Minimum): manche lokale
    # Reasoning-Modelle (z. B. gpt-oss) denken auch bei einfachen JSON-Aufgaben
    # ausfuehrlich weiter und verbrauchen dabei mehrere Tausend Tokens, BEVOR
    # ueberhaupt Antwort-Text entsteht - ein knappes Budget schneidet dann
    # mitten im Denken ab (done_reason='length', leerer Antwort-Kanal). Bei
    # 24+ GB VRAM ist der Puffer den Speicher-Mehrverbrauch wert (getestet:
    # ein 17-GB-Modell braucht bei num_ctx=32768 ca. 21 GB VRAM - auf einer
    # 24-GB-Karte bewusst in Kauf genommen, auf kleineren Karten ggf. senken).
    LLM_NUM_CTX: int = 32768               # Kontextfenster für Generierung
    LLM_NUM_PREDICT: int = 16384           # max. Antwortlänge (Tokens)
    LLM_TIMEOUT: int = 600                 # Sekunden (CPU-Inferenz kann dauern)

    # ------------------------------------------------------------------ #
    # Modell-Ladeverhalten (Ressourcen-Kontrolle fuer den Uni-Alltag)
    # ------------------------------------------------------------------ #
    # Embedding + Reranker beim Oeffnen der Startseite automatisch im Hintergrund
    # vorladen (dann ist die erste echte Frage sofort schnell). AUS -> es laedt
    # NICHTS, bevor man wirklich etwas fragt/einreicht - z. B. wenn man die Sitzung
    # nur zum Karteikarten-Lernen (kein LLM noetig) oeffnet.
    PREWARM_ON_START: bool = True
    # Wie lange bleibt ein ueber Ollama geladenes Modell (Antwort-LLM, Embedding)
    # nach der letzten Nutzung im Speicher (RAM/VRAM)? 0 = sofort nach jeder Antwort
    # entladen (schont Speicher, kostet bei der naechsten Frage den Kaltstart wieder),
    # -1 = fuer immer geladen lassen, sonst Minuten (Ollama-Standard: 5). Wirkt NICHT
    # auf den lokal geladenen Reranker (eigener Prozessspeicher, kein Ollama-Modell).
    OLLAMA_KEEP_ALIVE_MINUTES: float = 5.0

    # ------------------------------------------------------------------ #
    # OCR (Scan-/Bild-PDFs, inkl. Handschrift)
    # ------------------------------------------------------------------ #
    # Engine fuer text-lose PDF-Seiten:
    #   "auto"    -> Vision-LLM (Ollama), falls ein vision-faehiges Modell
    #                installiert ist; sonst easyocr. Bei Vision-Fehler/Loop ->
    #                Fallback auf easyocr.
    #   "vision"  -> Vision-LLM bevorzugt (easyocr nur als Fehler-Fallback)
    #   "easyocr" -> bisheriges Verhalten (easyocr/pytesseract), kein Vision-LLM
    OCR_ENGINE: str = "auto"
    # Vision-Modell fuer OCR. "" = automatisch ein kleines installiertes
    # Vision-Modell waehlen (bevorzugt gemma3:4b / gemma4:e4b, sonst das kleinste).
    OCR_VISION_MODEL: str = ""
    OCR_RENDER_DPI: int = 170          # Render-Aufloesung der Seite vor dem Verkleinern
    OCR_VISION_MAX_SIDE: int = 1400    # lange Bildkante in px (VRAM-schonend; >1500 -> mehr Wiederholungs-Loops)
    OCR_VISION_NUM_PREDICT: int = 700  # Token-Deckel je Seite (begrenzt Endlos-Loops)
    OCR_VISION_TIMEOUT: int = 180      # Sekunden je Seite
    # Vor der OCR werden andere eigene Ollama-Modelle entladen, damit NUR das
    # OCR-Modell im VRAM liegt (auch ein grosses, z. B. 18 GB auf 24 GB, ist so
    # nutzbar). Ein freier-VRAM-Gate laesst Vision-OCR aber nur zu, wenn das Modell
    # + dieser Puffer (GB) WIRKLICH in den freien VRAM passt (fremde GPU-App / der
    # Reranker belegen ihn mit) - sonst CPU-Fallback statt GPU-Hang/System-Freeze.
    OCR_VISION_VRAM_HEADROOM_GB: float = 2.0
    # F2: OCR-Seite mit weniger als so vielen Zeichen gilt als "unvollstaendig
    # gelesen" (Vision degeneriert/verworfen oder easyocr leer). ~40 = eine kurze
    # Textzeile; darunter wurde die Seite faktisch nicht transkribiert. Liegt
    # bewusst ueber GIBBERISH_MIN_CHARS (25) und unter dem Dok-Gate (n<200).
    OCR_MIN_PAGE_CHARS: int = 40

    # ------------------------------------------------------------------ #
    # Sprache-zu-Text (Sprachnotizen, siehe ragapp/speech_to_text.py + Notizen.py)
    # ------------------------------------------------------------------ #
    # Laeuft LOKAL ueber transformers (Whisper), KEIN Ollama/Internet noetig.
    # "small" ist ein guter Kompromiss aus Geschwindigkeit/deutscher Genauigkeit
    # fuer kurze Sprachnotizen (Sekunden bis wenige Minuten); "base" ist
    # schneller, aber merklich fehleranfaelliger bei Deutsch.
    STT_MODEL: str = "openai/whisper-small"
    STT_LANGUAGE: str = "de"
    # Bewusst CPU als Standard (wie easyocr, siehe dort): Whisper laeuft ueber
    # dieselbe torch/ROCm-Umgebung wie Ollama - eine GPU-Allokation unter
    # VRAM-Druck kann den amdgpu-Treiber haengen lassen. Fuer eine kurze
    # Sprachnotiz ist CPU schnell genug; bewusst aktivieren mit RAG_STT_GPU=1.
    STT_MAX_SECONDS: int = 300             # Sicherheitsdeckel gegen versehentliche Stunden-Aufnahmen

    # ------------------------------------------------------------------ #
    # Chunking (Slicing)
    # ------------------------------------------------------------------ #
    CHUNK_SIZE: int = 1100                 # Zielgröße pro Chunk (Zeichen)
    CHUNK_OVERLAP: int = 180               # Überlappung für Kontexterhalt
    MIN_CHUNK_CHARS: int = 120             # kleinere Fragmente werden verworfen/gemerged
    RESPECT_MARKDOWN_HEADERS: bool = True  # Markdown an Überschriften schneiden

    # ------------------------------------------------------------------ #
    # Datei-Auswahl beim Import (welche Dateien in die Wissensbasis kommen)
    # ------------------------------------------------------------------ #
    # Dateien, deren Name eines dieser Kürzel enthält, werden NICHT importiert.
    # Anki-Karten/Karteikarten duplizieren die Inhalte der PDFs/Zusammenfassungen.
    INGEST_EXCLUDE_NAME_SUBSTRINGS: tuple = ("anki", "karteikart")
    # Markdown wird gegenüber einer gleichnamigen PDF BEVORZUGT: In .md bleiben
    # Formeln als sauberes LaTeX erhalten ($\sum$, $\frac{}{}$ …), während die
    # PDF-Textextraktion Mathe zerstört (wichtig für Analysis/Statistik/FTdP).
    # Bei Namensgleichheit wird daher die PDF übersprungen und die .md indexiert.
    INGEST_PREFER_MARKDOWN: bool = True

    # ------------------------------------------------------------------ #
    # Deduplizierung
    # ------------------------------------------------------------------ #
    DEDUP_NEAR_DUPLICATE_THRESHOLD: float = 0.965  # Cosine-Schwelle für Chunk-Near-Dups

    # ------------------------------------------------------------------ #
    # Kauderwelsch-Gate (kein unlesbarer Handschrift-/Scan-Text im Index)
    # ------------------------------------------------------------------ #
    # Garantie: Zeichenmüll (OCR über Handschrift) wird NIE als Chunk gespeichert.
    # Das Gate filtert nur (schreibt nichts um) -> native Dokumente bleiben
    # wortgetreu. Alle Schwellen über data/config.json / Einstellungen justierbar.
    GIBBERISH_FILTER: bool = True                  # Gate an/aus (sicherer Default: an)
    # Chunk gilt als Kauderwelsch, wenn die "Bedeutungshaltigkeit" (0..1) < Schwelle.
    # Bedeutungshaltigkeit = Echtwort-Anteil laut Wörterbuch (de+en, pyspellchecker).
    # Kalibriert: OCR-Kauderwelsch liegt bei ~10–35 %, echter (auch knapper) Text ≥ ~50 %.
    GIBBERISH_MAX_MEANINGFULNESS: float = 0.40     # pro Chunk
    # Ganzes Dokument früh verwerfen (vor Chunking/Embedding), wenn der GESAMTE
    # Text schon darunter liegt. Bewusst STRENGER als pro Chunk, damit gemischte
    # Dokumente (teils lesbar) nicht komplett verloren gehen.
    GIBBERISH_DOC_MAX_MEANINGFULNESS: float = 0.35
    # Anteil verworfener Chunks, ab dem das ganze Dokument als unlesbar gilt.
    GIBBERISH_DOC_DROP_RATIO: float = 0.80
    # Schutz-Guards: darunter wird NICHT beurteilt (im Zweifel behalten).
    GIBBERISH_MIN_CHARS: int = 25                  # kürzerer Text -> behalten
    GIBBERISH_MIN_ALPHA_RATIO: float = 0.30        # wenig Buchstaben -> Formel/Tabelle -> behalten
    GIBBERISH_MIN_TOKENS: int = 4                  # zu wenige Tokens -> behalten

    # ------------------------------------------------------------------ #
    # Fragen-Generierung (Hypothetical Questions -> Trefferquote ↑)
    # ------------------------------------------------------------------ #
    # HINWEIS: Auf CPU-Hardware kostet die Fragen-Generierung ~20 s pro Chunk.
    # Für große Korpora (hier ~9.000 Chunks) ist das beim Bulk-Import unpraktisch,
    # daher standardmäßig AUS. Stattdessen gibt es die gezielte, gedeckelte
    # Anreicherung (``ragapp.ingestion.enrich``) für die wichtigsten Dokumente.
    ENABLE_QUESTION_INDEXING: bool = False
    NUM_INDEX_QUESTIONS: int = 3           # generierte Fragen pro Chunk (indexiert)

    # ------------------------------------------------------------------ #
    # Lern-Algorithmus (Karteikarten / Spaced Repetition)
    # ------------------------------------------------------------------ #
    # Wiederholungs-Algorithmus: FSRS-6 (Free Spaced Repetition Scheduler) - loest
    # das bisherige handgestrickte SM-2 ab. FSRS lernt aus 700+ Mio. echten
    # Wiederholungen ein Vergessens-Modell statt fixer 1980er-Formeln; im Anki-
    # Benchmark (9.999 Sammlungen, ~350 Mio. Reviews) sagt es fuer 99,5 % der
    # Nutzer die Abrufwahrscheinlichkeit genauer voraus und braucht 20-30 %
    # weniger Wiederholungen fuer denselben Lernerfolg (siehe ragapp/study.py).
    FSRS_DESIRED_RETENTION: float = 0.9    # Zielwahrscheinlichkeit, eine Karte am
                                            # Faelligkeitstag noch zu wissen (0.7-0.97)
    FSRS_MAX_INTERVAL_DAYS: int = 365      # Obergrenze fuer den Abstand zwischen zwei
                                            # Wiederholungen (auch bei sehr leichten Karten)
    # Tages-/Sitzungs-Limits (algorithmus-unabhaengig)
    SRS_NEW_PER_DAY: int = 20              # Tageskontingent brandneuer Karten (0 = unbegrenzt);
                                            # faellige Wiederholungen kommen zusaetzlich
    SRS_MAX_PER_SESSION: int = 100         # Sicherheitsdeckel pro Sitzung (nicht Runden-UI)
    # Interner UX-Hinweis (nicht in Einstellungen-UI): Fragen indexiert, aber
    # noch nicht als Karteikarten geerntet - ueberlebt Session-Neustarts.
    NEEDS_CARD_HARVEST: bool = False

    # ------------------------------------------------------------------ #
    # Lernplanung, Analytik & Datensicherung (Fortschritt / Klausurtermin)
    # ------------------------------------------------------------------ #
    MASTERY_TARGET_REPS: int = 4          # Wiederholungen in Folge, ab denen eine Karte als "sitzt" gilt
    PLANNER_URGENCY_DAYS: int = 30        # Horizont fuer die Termin-Dringlichkeit (Tage bis Klausur)
    DAILY_REVIEW_GOAL: int = 40           # Tagesziel Wiederholungen (fuer Streak/Fortschritt)
    LEECH_LAPSES_THRESHOLD: int = 4       # ab so vielen Patzern gilt eine Karte als "Dauerpatzer" (Leech)
    BACKUP_KEEP: int = 12                 # Anzahl aufbewahrter Lernstand-Snapshots
    BACKUP_MIN_HOURS: float = 24.0        # automatischer Start-Snapshot nur, wenn letzter aelter als dies
    # Ab dieser Uhrzeit (24h, lokale Zeit) gilt der Streak als "gefaehrdet", wenn
    # heute noch nichts geuebt wurde - Grundlage sowohl fuer den Warnhinweis auf
    # der Startseite als auch fuer die native Desktop-Erinnerung (siehe unten).
    STREAK_RISK_HOUR: int = 17
    # Ab wie vielen Tagen vor dem naechsten Klausurtermin schaltet die Startseite
    # in einen fokussierteren "Cram"-Modus (siehe planner.today_snapshot()).
    CRAM_MODE_DAYS: int = 3
    # Native Betriebssystem-Erinnerung aus dem Desktop-Starter (ragapp/desktop.py),
    # wenn ab STREAK_RISK_HOUR noch faellige Karten warten - bewusst KEIN Smartphone-
    # Push (Rechner laeuft ja bereits waehrend der Sitzung), hoechstens einmal pro
    # Tag. Nur wirksam im Desktop-Start (start.sh/Start.bat), nicht im reinen
    # Browser-Betrieb.
    DESKTOP_REMINDERS_ENABLED: bool = True

    # ------------------------------------------------------------------ #
    # Lernplan (KI-Gliederung -> realistischer Zeitplan)
    # ------------------------------------------------------------------ #
    # Alle Werte sind an Forschung zu Lesegeschwindigkeit, Vokabel-/Fakten-
    # Lernrate und nachhaltiger taeglicher Fokuszeit angelehnt (Herleitung +
    # Quellen: docs/LERNPLAN_FORSCHUNG.md) - bewusst NICHT frei erfunden, damit
    # "3 Stunden Zeit" nie zu einem unrealistischen Plan fuehrt.
    PLAN_CHARS_PER_PAGE: int = 3000        # grobe Umrechnung Zeichen -> Buchseite
    PLAN_PAGES_PER_HOUR: float = 25.0      # verstehendes Lesen dichten/technischen Stoffs (Forschung: 20-30 S/h)
    PLAN_CHARS_PER_CONCEPT: int = 1000     # ~1 lernbares Konzept/Fakt je ... Zeichen (grobe Heuristik)
    PLAN_ITEMS_PER_HOUR: float = 10.0      # neue Konzepte/Vokabeln pro Stunde aktiver Uebung (Forschungswert)
    # Erfahrungskorrektur: PLAN_ITEMS_PER_HOUR stammt aus Vokabel-/Fakten-Lernen
    # (atomare, isolierte Items). Ein "Konzept" in technischem/prozeduralem Stoff
    # (Algorithmen, Rechenverfahren, Modelle) ist damit nicht vergleichbar - dort
    # kostet WIRKLICHES Verstehen+Ueben (Aufgaben rechnen, Fehlversuche, spaeteres
    # Wiederholen bis zur Klausurreife) deutlich mehr Zeit als reines Abfragen.
    # Ohne Korrektur faellt der Plan spuerbar zu optimistisch aus. Multiplikator
    # auf die GESAMTE Formel-Schaetzung (Lese- + Uebungszeit). 1.5 ist der
    # STATISCHE Startwert (kein Forschungswert) - sobald genug echte Pomodoro-
    # Messungen an erledigten Lernplan-Bloecken vorliegen, ersetzt der
    # selbstlernende Faktor aus manifest.time_calibration() diesen Wert
    # automatisch (siehe study_plan.py:time_factor_info). In Einstellungen ->
    # Lernplan trotzdem manuell nachjustierbar (siehe docs/LERNPLAN_FORSCHUNG.md).
    PLAN_TIME_FACTOR: float = 1.5
    # Grobe Dauer EINER Karteikarten-Wiederholung (Sekunden) - Erfahrungswert
    # (Lesen der Frage, Erinnern, Aufdecken, Bewerten), keine eigene Studie.
    # Reserviert im Lernplan taeglich Zeit fuer faellige Karteikarten-Wiederholungen,
    # BEVOR neuer Stoff eingeplant wird (siehe study_plan.py:build_schedule) -
    # sonst waere der Tagesplan zu optimistisch, weil er die parallel laufende
    # Wiederholungslast ignoriert.
    PLAN_REVIEW_SEC_PER_CARD: float = 25.0
    # Deckel: faellige Wiederholungen duerfen hoechstens diesen Anteil des
    # Tagesbudgets belegen - ein Wiederholungs-Stau soll den Neustoff-Teil des
    # Plans nicht komplett verdraengen (dann lieber ehrlich weniger Puffer als
    # tagelang NULL Fortschritt beim neuen Stoff).
    PLAN_REVIEW_MAX_SHARE: float = 0.5
    # Reserviert im Lernplan taeglich Zeit fuer bereits im Stundenplan
    # eingetragene Vorlesungen/Kurse (siehe manifest.timetable) - ein Tag mit
    # 6 Stunden Uni hat real weniger freie Zeit als ein vorlesungsfreier Tag
    # (siehe study_plan.py:build_schedule). Deckel wie bei PLAN_REVIEW_MAX_SHARE,
    # nur grosszuegiger: tatsaechliche Anwesenheitspflicht ist eine haertere
    # Grenze als eine (flexible) Wiederholungs-Schaetzung.
    PLAN_CLASS_MAX_SHARE: float = 0.7
    PLAN_MAX_DAILY_FOCUS_MIN: int = 240    # nachhaltige Tagesobergrenze hochfokussierten Lernens (Forschung: 3-4h optimal, Qualitaet faellt ab ~4-5h)
    PLAN_BLOCK_MIN: int = 25               # Groesse eines Lernblocks (= 1 Pomodoro-Arbeitsblock)
    PLAN_MAX_OUTLINE_SECTIONS: int = 15    # Obergrenze fuer die KI-Gliederung (Uebersichtlichkeit)
    PLAN_MIN_GRANULAR_CHARS: int = 400     # kleinere Original-Abschnitte werden VOR der KI-Anfrage mit dem naechsten zusammengelegt (weniger Uebersegmentierung + kuerzerer Prompt)
    PLAN_MAX_TOC_CHARS: int = 10000        # Obergrenze fuer das Inhaltsverzeichnis im Gliederungs-Prompt: bei SEHR grossen/vielen Dokumenten wuerde die TOC sonst das Kontextfenster sprengen - das Modell sieht dann nur einen abgeschnittenen Rest und erfindet frei (beobachtet: Marketing-PDF -> Gliederung ueber Deutsch-Grammatik). Weit unter LLM_NUM_CTX, damit auch Systemprompt+Anweisung+Antwort sicher reinpassen.
    # Anders als eine reine Titel-Liste (bei der die Reihenfolge das einzige
    # ist, was zaehlt) muss die Gliederung Abschnitte teils auch thematisch
    # ZUSAMMENFASSEN - bei Quellen ohne erkennbare Kapitelstruktur (Folien-
    # saetze: Abschnittstitel nur "Seite N") ist der Titel allein dafuer kein
    # Signal (beobachtet: identischer Fallback-Bug wie bei der Mindmap, siehe
    # dort). Jede TOC-Zeile bekommt daher zusaetzlich einen kurzen Inhalts-
    # Ausschnitt (study_plan._toc_with_excerpts, auch von mindmap.py genutzt) -
    # die Ausschnittlaenge schrumpft automatisch mit der Abschnittszahl, damit
    # der Gesamt-Prompt PLAN_PROMPT_BUDGET_CHARS nicht sprengt.
    PLAN_PROMPT_BUDGET_CHARS: int = 9000
    # Gemeinsame Ausschnitt-Laengengrenzen fuer _toc_with_excerpts (Lernplan-
    # Gliederung UND Mindmap).
    TOC_EXCERPT_MIN_CHARS: int = 40
    TOC_EXCERPT_MAX_CHARS: int = 150
    # Grobe Wartezeit-Schaetzung fuer die UI (Sekunden) - KEINE Forschung, nur aus
    # eigenen Messwerten kalibriert; haengt stark von der Hardware ab, daher immer
    # als Richtwert kommunizieren, nie als Zusage.
    PLAN_ETA_BASE_SEC: float = 30.0
    PLAN_ETA_SEC_PER_1000_CHARS: float = 8.0

    # Semesterplan-Import (siehe ragapp/syllabus_import.py): Obergrenze fuer den
    # Dokumenttext im Extraktions-Prompt - gleiches Prinzip wie PLAN_MAX_TOC_CHARS
    # (ohne Deckel wuerde ein sehr grosses Modulhandbuch das Kontextfenster
    # sprengen, das Modell saehe nur einen abgeschnittenen Rest).
    SYLLABUS_IMPORT_MAX_CHARS: int = 12000

    # ------------------------------------------------------------------ #
    # Retrieval-Deduplizierung (gegen doppelte Informationen in der Antwort)
    # ------------------------------------------------------------------ #
    RETRIEVAL_DEDUP: bool = True
    RETRIEVAL_DEDUP_JACCARD: float = 0.82  # Token-Jaccard-Schwelle für Near-Dups

    # ------------------------------------------------------------------ #
    # Retrieval (Hybrid: dense + BM25 -> RRF -> Rerank)
    # ------------------------------------------------------------------ #
    DENSE_TOP_K: int = 25                  # Kandidaten aus Vektorsuche
    BM25_TOP_K: int = 25                   # Kandidaten aus Keyword-Suche
    RRF_K: int = 60                        # Reciprocal-Rank-Fusion-Konstante
    # Kandidaten nach Fusion (gehen ins Rerank). Auf 30 angehoben (war 20), damit der
    # Cross-Encoder mehr als nur die Haelfte der ~50 Fusionskandidaten sieht -> bessere
    # finale Rangfolge, ohne die Vektorsuche zu vergroessern.
    FUSION_TOP_K: int = 30

    USE_RERANKER: bool = True
    RERANKER_MODEL: str = "BAAI/bge-reranker-v2-m3"  # multilingualer Cross-Encoder
    # Reranker-Kontextfenster: Chunks sind ~300 Token, daher reichen 384
    # (spart Padding-Rechenzeit auf der CPU, ohne Kandidaten zu verlieren).
    RERANKER_MAX_LENGTH: int = 384
    FINAL_TOP_K: int = 6                   # finale Chunks, die ins LLM gehen

    # Gewichtung, falls Rerank aus ist (reine RRF-Fusion)
    DENSE_WEIGHT: float = 1.0
    BM25_WEIGHT: float = 1.0

    # ------------------------------------------------------------------ #
    # Anti-Halluzination / Antwort-Politik
    # ------------------------------------------------------------------ #
    # Minimaler Rerank-Score (roher Cross-Encoder-Logit von bge-reranker-v2-m3),
    # ab dem ein Chunk als "relevant genug" gilt. Liegt der beste Treffer
    # darunter, antwortet das System NICHT frei, sondern gibt das/die
    # passendste(n) Dokument(e) aus. Skala: guter Treffer > 0, schwach ~ -1..-4,
    # klar irrelevant < -5. Wert bewusst permissiv (Faithfulness-Check fängt
    # Rest ab); über die Evaluation nachjustierbar.
    RELEVANCE_MIN_SCORE: float = -4.0
    # Schnell-Modus (Reranker AUS): dort gibt es keinen Cross-Encoder-Logit. Der
    # RRF-Fusionswert ist RANGBASIERT und misst KEINE Relevanz (der Top-Treffer hat
    # praktisch immer ~denselben Wert) – ein Fusions-Schwellwert kann relevant vs.
    # irrelevant also gar nicht trennen. Deshalb gatet der Schnell-Modus auf die
    # DENSE-Kosinus-Ähnlichkeit (bge-m3) des Top-Treffers – ein echtes Relevanzsignal.
    # Empirisch (Marketing-Korpus): relevante Top-Treffer >=~0.59, off-topic <=~0.43;
    # 0.45 trennt sauber. Über die Einstellungen nachjustierbar.
    DENSE_RELEVANCE_MIN_SCORE: float = 0.45
    # Nur noch als Rückfall, wenn der Top-Treffer ausschließlich aus BM25 stammt
    # (kein Dense-Score vorhanden): dann bleibt der RRF-Fusionswert die einzige Quelle.
    RELEVANCE_MIN_FUSION_SCORE: float = 0.008
    # LLM prüft zusätzlich, ob die Antwort durch den Kontext belegt ist (3. Anti-
    # Halluzinations-Schicht neben Relevanz-Gate + striktem Prompt). Nutzt das
    # schnelle Modell. Auf CPU kostet die Prüfung spürbar Zeit -> in den
    # Einstellungen abschaltbar, falls Tempo wichtiger ist.
    ENABLE_FAITHFULNESS_CHECK: bool = True
    MAX_CONTEXT_CHARS: int = 7000           # Obergrenze Kontext an das LLM
    # Tutor-Gespräch & Sokratischer Dialog: echte Mehrturn-Historie statt nur
    # der aktuellen Frage (siehe rag_graph.py:_history_for_chat), damit sich das
    # Modell an bereits Gesagtes erinnert - Strikt bleibt bewusst zustandslos
    # (jede Antwort direkt+ausschliesslich aus dem RAG, kein Gespraechs-Drift).
    # Waechst die rohe Historie ueber das Zeichen-Budget, werden die AELTEREN
    # Turns per schnellem Modell zu einer knappen Zusammenfassung verdichtet
    # (nur was TATSAECHLICH gesagt wurde, keine neuen Fakten) - die juengsten
    # Turns bleiben fuer unmittelbaren Anschluss roh erhalten.
    CHAT_HISTORY_KEEP_RECENT_TURNS: int = 6   # bei Kompaktierung roh erhaltene juengste Turns
    # Zeichen-Reserve fuer System-Prompt (Tutor/Sokratisch sind laenger als
    # Strict) bzw. die aktuelle Frage - beides zieht vom Kontextfenster ab,
    # BEVOR die Historie ihr Budget bekommt (siehe _history_char_budget()).
    CHAT_SYSTEM_PROMPT_RESERVE_CHARS: int = 2500
    CHAT_QUESTION_RESERVE_CHARS: int = 500
    # Fallback-Schaetzung Zeichen/Token (Deutsch), bis genug echte Messwerte aus
    # Ollamas prompt_eval_count vorliegen (siehe manifest.chars_per_token).
    DEFAULT_CHARS_PER_TOKEN: float = 3.2
    # Sicherheitsabschlag auf das errechnete Zeichen-Budget der Historie (Puffer
    # gegen Tokenizer-Abweichungen vom geschaetzten/kalibrierten Verhaeltnis).
    CHAT_HISTORY_BUDGET_SAFETY: float = 0.75
    # Sokratischer Dialog: nach so vielen eigenen Rueckfragen IN FOLGE (ohne
    # Aufloesung) wird die naechste Antwort erzwungen aufgeloest, statt sich
    # allein auf die Selbsteinschaetzung des (oft kleinen, lokalen) LLM zu
    # verlassen - das hat sich als unzuverlaessig gezeigt (beobachtet: eine
    # fast identische Rueckfrage 4x in Folge, sogar nach "Ich weiß es nicht").
    SOKRATISCH_RESOLVE_AFTER_QUESTIONS: int = 3

    # ------------------------------------------------------------------ #
    # Uebungsaufgaben-Generator (mehrschrittige Rechen-/Anwendungsaufgaben,
    # bewusst GETRENNT von SM-2/FSRS-Karten - siehe manifest.py-Schema-Kommentar)
    # ------------------------------------------------------------------ #
    # Zahlen-/Formeldichte ab der eine Rechenaufgabe statt eines Anwendungs-
    # szenarios generiert wird (dieselbe Heuristik wie der Lernplan-Zeitfaktor,
    # siehe study_plan._TECHNICAL_MARKER_RE - Marker je 100 Zeichen).
    PRACTICE_NUMERIC_DENSITY_THRESHOLD: float = 1.0
    PRACTICE_MAX_HINTS: int = 3
    # Obergrenze fuer den Quelltext im Generierungs-Prompt (Zeichen) - dieselbe
    # Absicherung wie PLAN_MAX_TOC_CHARS: ohne Deckel wuerde ein sehr grosses
    # Thema den Kontext sprengen und das Modell frei erfinden lassen.
    PRACTICE_MAX_SOURCE_CHARS: int = 6000
    # Obergrenze fuer die "Formelsammlung" (siehe practice_gen.generate_
    # formelsammlung) - fasst ALLE bisherigen Aufgaben eines Fachs zusammen,
    # deshalb grosszuegiger als das Einzel-Aufgaben-Budget oben.
    FORMELSAMMLUNG_MAX_CHARS: int = 12000

    # ------------------------------------------------------------------ #
    # Mindmap (Themenbaum aus dem Inhaltsverzeichnis, wie die Lernplan-
    # Gliederung - eigenes SVG-Layout statt System-Graphviz, siehe mindmap.py)
    # ------------------------------------------------------------------ #
    MINDMAP_MAX_TOPICS: int = 8        # max. Hauptthemen (Uebersichtlichkeit)
    MINDMAP_MAX_SUBTOPICS: int = 6     # max. Unterthemen je Hauptthema
    MINDMAP_MAX_LINKS: int = 8         # max. Querverbindungen zwischen Themen
    # Harte Obergrenze aller Knoten zusammen - schuetzt vor einer unlesbaren
    # SVG-Flaeche UND vor einem ausufernden Prompt bei der naechsten Anfrage.
    MINDMAP_MAX_NODES: int = 40
    # Braucht wie die Lernplan-Gliederung Inhalts-Ausschnitte statt nur Titel
    # (siehe study_plan._toc_with_excerpts, PLAN_PROMPT_BUDGET_CHARS-Kommentar
    # fuer die Begruendung) - eigenes Zeichen-Budget, da Mindmap-Prompts durch
    # die Baum-/Link-Struktur laenger als reine Gliederungs-Prompts sind.
    MINDMAP_PROMPT_BUDGET_CHARS: int = 9000

    # ------------------------------------------------------------------ #
    # Audio-Overview (Vertonung mit der eigenen, geklonten Stimme)
    # ------------------------------------------------------------------ #
    # Chatterbox Multilingual (Resemble AI, MIT-Lizenz) - deckt Deutsch nativ
    # und mit guter Qualitaet ab, braucht ~6-8 GB VRAM, klont ab wenigen
    # Sekunden Referenzaudio. Siehe docs/STIMME_AUFNEHMEN.md fuer die
    # Aufnahme-Anleitung.
    #
    # War urspruenglich XTTS-v2 (Coqui) - ausgetauscht, weil XTTS-v2
    # autoregressiv Token fuer Token generiert und dabei selbst entscheiden
    # muss, wann ein Satz fertig ist. Genau bei dieser Stopp-Entscheidung
    # "verlief" es sich gelegentlich (Rauschen/Gebrabbel an Satzgrenzen) - ein
    # in der coqui-tts-Community seit Jahren bekanntes, nie geloestes Problem
    # (u. a. coqui-ai/TTS#3236/#3254/#3407). Mehrere Tuning-/Nachbearbeitungs-
    # Versuche (Temperatur/Pausenlaenge, dann eine Silero-VAD-basierte
    # Saeuberung) haben das Symptom bestenfalls verschoben, nicht behoben -
    # die VAD-Nachbearbeitung hat sogar echte Sprache mit-zerschnitten
    # ("abgehackt" laut Nutzer-Test) und wurde wieder rueckgaengig gemacht.
    # Chatterbox hat eine eingebaute Absicherung (AlignmentStreamAnalyzer),
    # die genau solche Aussetzer WAEHREND der Generierung erkennt und sauber
    # abbricht, statt sie hoerbar werden zu lassen - in echten Testlaeufen mit
    # der eigenen Referenzstimme mehrfach live beobachtet (Log-Zeilen wie
    # "Detected 2x repetition..."/"forcing EOS token...").
    AUDIO_LANGUAGE: str = "de"
    # Fester Pfad, IMMER frisch eingelesen (kein Zwischenspeichern der Stimme) -
    # der Nutzer kann die Datei jederzeit durch eine neue Aufnahme ersetzen,
    # die naechste Generierung nutzt automatisch die neue Version.
    AUDIO_REFERENCE_WAV: str = "data/voice/reference.wav"
    # Wie viel Puffer (GB) zusaetzlich zum geschaetzten Modellbedarf frei sein
    # muss, bevor XTTS-v2 geladen wird (gleiche Vorsicht wie beim Vision-OCR-
    # Gate, siehe ragapp/ingestion/loaders.py::_vision_ocr_prepare).
    AUDIO_VRAM_HEADROOM_GB: float = 2.0
    # Sicherheitsnetz, NICHT die normale Ziel-Laenge: das Skript entsteht
    # ABSCHNITTSWEISE (ein LLM-Aufruf je Abschnitt, siehe audio_overview.py)
    # und waechst dadurch natuerlich mit der Dokumentgroesse - dieser Deckel
    # greift nur, wenn SEHR viele/lange Dokumente auf einmal gewaehlt werden,
    # und verhindert eine Laufzeit-Explosion (40000 Zeichen ~ 40 Min Audio bei
    # durchschnittlichem Sprechtempo).
    AUDIO_MAX_SCRIPT_CHARS: int = 40000
    # Chatterbox wird SATZWEISE aufgerufen (siehe audio_overview.py) - in
    # echten Testlaeufen deutlich sauberer als ein Aufruf mit dem kompletten
    # Skript auf einmal (unnatuerlich schnelles/gehetztes Ergebnis; Chatterbox
    # ist wie die meisten TTS-Modelle fuer einzelne Saetze/Abschnitte optimiert,
    # nicht fuer sehr lange Texte am Stueck). WIR fuegen die Pause zwischen den
    # Saetzen selbst ein (echte Stille, feste Laenge) statt uns auf das Modell
    # zu verlassen - robuster als XTTS' Ansatz, der eine private Konstante im
    # Paket ueberschreiben musste.
    AUDIO_TTS_PAUSE_MS: int = 250
    # Chatterbox-eigene Erzeugungsparameter (Bibliotheks-Standardwerte
    # uebernommen, siehe ChatterboxMultilingualTTS.generate) - in echten
    # Testlaeufen mit der eigenen Referenzstimme verifiziert, bewusst NICHT
    # blind "verbessert" wie beim vorherigen XTTS-Tuning. exaggeration/
    # cfg_weight steuern die Ausdrucksstaerke (Werte >1.5 laut Community
    # anfaelliger fuer Artefakte); repetition_penalty unterdrueckt
    # Wiederholungsschleifen; temperature/min_p/top_p steuern die
    # Sampling-Variation.
    AUDIO_TTS_EXAGGERATION: float = 0.5
    AUDIO_TTS_CFG_WEIGHT: float = 0.5
    AUDIO_TTS_TEMPERATURE: float = 0.8
    AUDIO_TTS_REPETITION_PENALTY: float = 2.0
    AUDIO_TTS_MIN_P: float = 0.05
    AUDIO_TTS_TOP_P: float = 1.0

    # ------------------------------------------------------------------ #
    # Evaluation
    # ------------------------------------------------------------------ #
    EVAL_QUESTIONS_PER_CHUNK: int = 1      # Held-out-Fragen pro gesampeltem Chunk
    EVAL_SAMPLE_SIZE: int = 60             # Anzahl gesampelter Chunks fürs Gold-Set
    EVAL_K_VALUES: tuple = (1, 3, 5, 10)   # k-Werte für Recall@k / Hit@k

    # ------------------------------------------------------------------ #
    # Chroma-Collections
    # ------------------------------------------------------------------ #
    COLLECTION_NAME: str = "zusammenfassungen"

    # ------------------------------------------------------------------ #
    # Handy-/Netzwerk-Zugriff (App vom Smartphone/Tablet nutzen)
    # ------------------------------------------------------------------ #
    # PIN, der beim Zugriff über das Netzwerk (Start_Handy-Zugriff.bat)
    # abgefragt wird. Leer = kein PIN gesetzt -> der Netzwerkmodus verweigert
    # den Zugriff, bis in den Einstellungen ein PIN gesetzt wurde. Im normalen
    # lokalen Betrieb (Start.bat) spielt der Wert keine Rolle.
    UI_ACCESS_PIN: str = ""

    # ------------------------------------------------------------------ #
    # Laden / Speichern von Laufzeit-Overrides
    # ------------------------------------------------------------------ #
    @classmethod
    def load(cls) -> "Settings":
        base = cls()
        if RUNTIME_CONFIG_FILE.exists():
            try:
                overrides = json.loads(RUNTIME_CONFIG_FILE.read_text("utf-8"))
                valid = {f.name for f in fields(cls)}
                for k, v in overrides.items():
                    if k in valid:
                        setattr(base, k, v)
            except Exception as exc:  # pragma: no cover - defensiv
                print(f"[config] Warnung: config.json konnte nicht gelesen werden: {exc}")
        base._sanitize()
        return base

    def _sanitize(self) -> None:
        """Fängt kaputte Overrides ab (z. B. leeres EVAL_K_VALUES)."""
        try:
            kv = list(self.EVAL_K_VALUES)
            kv = [int(x) for x in kv if int(x) > 0]
        except Exception:
            kv = []
        self.EVAL_K_VALUES = tuple(kv) if kv else (1, 3, 5, 10)

    def reset(self) -> None:
        """Setzt alle Werte auf die Standardwerte zurück (In-Memory)."""
        for f in fields(self):
            setattr(self, f.name, getattr(Settings(), f.name))

    def save(self) -> None:
        RUNTIME_CONFIG_FILE.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False), "utf-8"
        )

    def update(self, **kwargs: Any) -> None:
        valid = {f.name for f in fields(self)}
        for k, v in kwargs.items():
            if k in valid:
                setattr(self, k, v)

    def author_model(self) -> str:
        """Modell fuer die Batch-Content-Erzeugung (Autoren-Aufgaben). Faellt auf
        LLM_MODEL zurueck, wenn LLM_MODEL_AUTHOR leer ist (dann kein zweites Modell
        noetig)."""
        return (self.LLM_MODEL_AUTHOR or "").strip() or self.LLM_MODEL

    def keep_alive_seconds(self) -> float:
        """OLLAMA_KEEP_ALIVE_MINUTES in Ollamas ``keep_alive``-Einheit (Sekunden;
        -1 = fuer immer)."""
        m = self.OLLAMA_KEEP_ALIVE_MINUTES
        return -1.0 if m < 0 else m * 60.0


# Globale Instanz, überall importierbar.
settings = Settings.load()


# Fächer-Kürzel -> Klartext (für hübsche Anzeige in der UI)
SUBJECT_LABELS = {
    "Analysis": "Analysis (Mathematik)",
    "DSA": "Algorithmen & Datenstrukturen",
    "FTdP": "Formale Techniken der Programmierung",
    "GrMa": "Grundlagen Marketing",
    "IE": "Internationale Ökonomie / Industrieökonomik",
    "IT-Sich Datenschutz": "IT-Sicherheit & Datenschutz",
    "KuLR": "Kosten- und Leistungsrechnung",
    "MF": "Marktforschung",
    "Statistik": "Statistik",
}
