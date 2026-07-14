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
    LLM_NUM_CTX: int = 8192                # Kontextfenster für Generierung
    LLM_NUM_PREDICT: int = 1024            # max. Antwortlänge (Tokens), begrenzt CPU-Zeit
    LLM_TIMEOUT: int = 600                 # Sekunden (CPU-Inferenz kann dauern)

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
    # Wiederholungs-Abstaende, angelehnt an SM-2/Anki (Forschung: kurze Lernschritte
    # von 1-10 min, danach multiplikatives Wachstum; Ease nie unter 1.3, da niedrigere
    # Werte laut SuperMemo-Forschung zu haeufigem, nervigem Wiedervorlegen fuehren).
    #   NICHT gewusst -> kurzer Relearn-Schritt (Minuten), Fortschritt zurueck auf Anfang
    #   HALB          -> kurzer Relearn-Schritt (Minuten), Stufe bleibt
    #   GEWUSST       -> klettert die Leiter hoch (Minuten); jenseits der Leiter x Ease
    SRS_AGAIN_MINUTES: float = 2.0         # "Nicht gewusst" -> in 2 Minuten erneut
    SRS_HALF_MINUTES: float = 10.0         # "Halb gewusst"  -> in 10 Minuten erneut
    # GEWUSST-Leiter in Minuten: 2 h, 8 h, 1 Tag, 3 Tage, 8 Tage, 21 Tage (danach x Ease)
    SRS_GOOD_STEPS_MIN: tuple = (120, 480, 1440, 4320, 11520, 30240)
    SRS_EASE_START: float = 2.5            # Start-Leichtigkeit (250 %)
    SRS_EASE_MIN: float = 1.3              # Untergrenze (SuperMemo-Forschung)
    SRS_EASE_MAX: float = 2.8              # Obergrenze
    SRS_EASE_GOOD: float = 0.05            # GEWUSST: Ease +
    SRS_EASE_HALF: float = -0.15           # HALB:    Ease -
    SRS_EASE_AGAIN: float = -0.20          # NICHT:   Ease -
    SRS_INTERVAL_FACTOR: float = 1.0       # globaler Faktor auf lange Intervalle (1.0 = 100 %)
    # Tages-/Runden-Limits
    SRS_NEW_PER_DAY: int = 20              # neue Karten pro Tag (0 = unbegrenzt)
    SRS_MAX_PER_SESSION: int = 100         # Obergrenze fuer eine Lernrunde

    # ------------------------------------------------------------------ #
    # Lernplanung, Analytik & Datensicherung (Fortschritt / Klausurtermin)
    # ------------------------------------------------------------------ #
    MASTERY_TARGET_REPS: int = 4          # Wiederholungen in Folge, ab denen eine Karte als "sitzt" gilt
    PLANNER_URGENCY_DAYS: int = 30        # Horizont fuer die Termin-Dringlichkeit (Tage bis Klausur)
    DAILY_REVIEW_GOAL: int = 40           # Tagesziel Wiederholungen (fuer Streak/Fortschritt)
    LEECH_LAPSES_THRESHOLD: int = 4       # ab so vielen Patzern gilt eine Karte als "Dauerpatzer" (Leech)
    BACKUP_KEEP: int = 12                 # Anzahl aufbewahrter Lernstand-Snapshots
    BACKUP_MIN_HOURS: float = 24.0        # automatischer Start-Snapshot nur, wenn letzter aelter als dies

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
