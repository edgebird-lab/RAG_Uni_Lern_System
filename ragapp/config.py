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
    FUSION_TOP_K: int = 20                 # Kandidaten nach Fusion (gehen ins Rerank)

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
