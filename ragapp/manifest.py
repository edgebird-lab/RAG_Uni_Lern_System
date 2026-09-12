"""
Manifest / Dokument-Registry (SQLite)
=====================================

Zentrale Buchführung über alle ingestierten Dokumente und Chunks. Erfüllt zwei
Aufgaben, die für ein gutes RAG-System essenziell sind:

1. **Deduplizierung auf Dokumentebene**: Jede Datei wird über einen SHA-256-Hash
   ihres *Inhalts* identifiziert. Wird dieselbe Datei (auch unter anderem Namen)
   erneut eingespielt, erkennt das System das und überspringt sie. Ändert sich
   der Inhalt, werden die alten Chunks gelöscht und neu erzeugt.

2. **Deduplizierung auf Chunk-Ebene (exakt)**: Der Hash jedes Chunk-Textes wird
   gespeichert. Exakt gleiche Textstücke (z. B. wiederkehrende Kopfzeilen,
   Formelsammlungen) werden nur einmal indexiert.

Die Tabelle ``documents`` dient zusätzlich als Anzeige-Registry für die UI
(welche Dokumente sind drin, wie viele Chunks, wann ingestiert).
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

from ragapp.config import MANIFEST_DB, DATA_DIR
from ragapp.logging_setup import get_logger


_log = get_logger(__name__)

_DEVICE_ID_FILE = DATA_DIR / ".device_id"

# Schema wird beim ERSTEN DB-Zugriff angelegt/migriert (nicht mehr als
# Import-Nebenwirkung). _ensure_initialized() ist idempotent und wird von
# _connect() aufgerufen.
_initialized = False


def _device_id() -> str:
    """Stabile, einmalig erzeugte Geraete-ID (fuer die Multi-Device-Sync)."""
    try:
        if _DEVICE_ID_FILE.exists():
            v = _DEVICE_ID_FILE.read_text("utf-8").strip()
            if v:
                return v
        v = uuid.uuid4().hex[:12]
        _DEVICE_ID_FILE.write_text(v, "utf-8")
        return v
    except Exception:  # noqa: BLE001
        return "unknown"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id         TEXT PRIMARY KEY,   -- stabile ID (Hash des Quellpfads)
    content_hash   TEXT NOT NULL,      -- SHA-256 des normalisierten Inhalts
    source_path    TEXT NOT NULL,
    filename       TEXT NOT NULL,
    subject        TEXT,               -- Fach (aus Ordnerstruktur)
    filetype       TEXT,
    num_chunks     INTEGER DEFAULT 0,
    num_questions  INTEGER DEFAULT 0,
    char_count     INTEGER DEFAULT 0,
    status         TEXT DEFAULT 'ok',
    ocr_partial_pages INTEGER DEFAULT 0,   -- F2: unvollstaendig gelesene OCR-Seiten
    use_rag        INTEGER DEFAULT 1,      -- 0 = nur archiviert (kein Chunking/Embedding, nicht im Chat zitierbar)
    tags           TEXT,                   -- frei vergebene Kategorien, kommagetrennt
    ingested_at    REAL,
    updated_at     REAL
);

CREATE TABLE IF NOT EXISTS chunk_hashes (
    chunk_hash  TEXT PRIMARY KEY,      -- SHA-256 des Chunk-Textes
    doc_id      TEXT NOT NULL,
    chunk_id    TEXT NOT NULL,
    created_at  REAL
);

CREATE INDEX IF NOT EXISTS idx_chunk_doc ON chunk_hashes(doc_id);
CREATE INDEX IF NOT EXISTS idx_doc_contenthash ON documents(content_hash);

-- Lern-Layer: Karteikarten + Spaced Repetition (FSRS-6, siehe ragapp/study.py). Rein
-- additiv - die Karten werden aus dem schon indexierten Fragenmaterial (kind='exam_qa' /
-- type='question') geerntet; hier wird nur der LERNFORTSCHRITT gefuehrt.
CREATE TABLE IF NOT EXISTS review_items (
    card_id     TEXT PRIMARY KEY,   -- stabile ID (= Chroma-ID der Quelle)
    source      TEXT,               -- 'exam_qa' | 'question'
    chroma_id   TEXT,
    subject     TEXT,
    topic       TEXT,               -- Abschnitt/Thema (location/header_path)
    front       TEXT NOT NULL,      -- Frage (Vorderseite)
    back        TEXT NOT NULL,      -- Antwort/Erklaerung (Rueckseite)
    doc_id      TEXT,
    -- Legacy-SM-2-Feld: wird seit der FSRS-6-Umstellung NICHT mehr fortgeschrieben,
    -- bleibt aber unangetastet stehen (keine destruktive Spalten-Migration fuer echte
    -- Nutzerdaten ohne funktionalen Grund).
    ease        REAL    DEFAULT 2.5,
    interval    INTEGER DEFAULT 0,  -- Tage bis zur naechsten Faelligkeit (FSRS-gepflegt)
    reps        INTEGER DEFAULT 0,  -- Anzahl korrekter Wiederholungen in Folge (eigene Buchfuehrung, FSRS kennt das nicht)
    lapses      INTEGER DEFAULT 0,  -- Anzahl 'Nicht gewusst' (eigene Buchfuehrung)
    due         REAL,               -- naechster Faelligkeits-Zeitpunkt (epoch)
    last_review REAL,
    created_at  REAL,
    suspended   INTEGER DEFAULT 0,
    deck        TEXT,               -- optionaler Stapel/Themenstapel (frei benannt)
    answer      TEXT,               -- KI-generierte Antwort (statt rohem Chunk); leer = Chunk zeigen
    use_flashcard INTEGER DEFAULT 1,-- Karte fuer die Abfrage (Lernrunde) nutzen?
    use_embedding INTEGER DEFAULT 1,-- zugehoerige Frage im Vektorindex (Suche) halten?
    edited        INTEGER DEFAULT 0,-- 1 = manuell bearbeitet -> Ernte ueberschreibt nicht mehr
    -- FSRS-6-Zustand (siehe ragapp/study.py:fsrs_next). fsrs_state: 1=Learning,
    -- 2=Review, 3=Relearning (Werte des fsrs.State-Enums). stability/difficulty NULL =
    -- noch nie geuebt (frische Karte, Standard-Initialwerte kommen beim ersten Review).
    fsrs_state  INTEGER,
    fsrs_step   INTEGER,
    stability   REAL,
    difficulty  REAL
);
CREATE INDEX IF NOT EXISTS idx_review_due ON review_items(due);
CREATE INDEX IF NOT EXISTS idx_review_subject ON review_items(subject);

CREATE TABLE IF NOT EXISTS review_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id        TEXT NOT NULL,
    subject        TEXT,
    topic          TEXT,
    rating         INTEGER,         -- 0=nicht gewusst, 1=halb, 2=gewusst
    reviewed_at    REAL,
    interval_after INTEGER,
    ease_after     REAL,            -- Legacy (SM-2), seit FSRS-6 nicht mehr befuellt
    confidence     TEXT,            -- 'sicher'|'mittel'|'unsicher' (JOL vor dem Aufdecken)
    device_id      TEXT,            -- Geraet, das die Wiederholung erzeugt hat (Sync)
    event_uid      TEXT,            -- global eindeutige Ereignis-ID (idempotenter Import)
    due_after      REAL,            -- absolute Faelligkeit nach dieser Wiederholung (exakter Replay)
    -- FSRS-6-Zustand NACH dieser Wiederholung - noetig, damit sync.rebuild_state()
    -- den echten FSRS-Zustand (nicht nur ease/interval) exakt replizieren kann.
    fsrs_state_after  INTEGER,
    fsrs_step_after   INTEGER,
    stability_after   REAL,
    difficulty_after  REAL
);
-- Der UNIQUE-Index auf event_uid wird in init_db() NACH der Spalten-Migration
-- angelegt (sonst schlaegt er bei einer bestehenden DB ohne die Spalte fehl).
CREATE INDEX IF NOT EXISTS idx_reviewlog_card ON review_log(card_id);
CREATE INDEX IF NOT EXISTS idx_reviewlog_subject ON review_log(subject);

-- Klausurtermine: pro Fach ein Termin (Datum, Gewicht/ECTS). Fundament fuer
-- Bereitschafts-Score, Countdown, Cram-Modus und die Prioritaets-Planung.
CREATE TABLE IF NOT EXISTS exams (
    subject     TEXT PRIMARY KEY,   -- Fach (= review_items.subject)
    exam_date   TEXT,               -- ISO 'YYYY-MM-DD'
    ects        REAL,               -- Umfang (optional, fuer Gewichtung)
    gewicht     REAL DEFAULT 1.0,   -- manuelles Gewicht (Prioritaet)
    notiz       TEXT,
    note        REAL,               -- tatsaechlich erhaltene Note (Noten-Tracking, NACH
                                     -- der Klausur eingetragen) - siehe planner.gpa_summary()
    note_updated_at REAL,
    created_at  REAL,
    updated_at  REAL
);

-- Verwaltungsbereich (Organisation): Aufgaben/Hausaufgaben + Stundenplan. Rein
-- organisatorisch, unabhaengig von RAG/Lern-Layer - kein LLM, kein Embedding.
CREATE TABLE IF NOT EXISTS tasks (
    task_id     TEXT PRIMARY KEY,
    subject     TEXT,
    title       TEXT NOT NULL,
    notiz       TEXT,
    due_date    TEXT,               -- ISO 'YYYY-MM-DD' (optional, ohne Termin = NULL)
    done        INTEGER DEFAULT 0,
    created_at  REAL,
    updated_at  REAL
);
CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_subject ON tasks(subject);

CREATE TABLE IF NOT EXISTS timetable (
    slot_id     TEXT PRIMARY KEY,
    subject     TEXT NOT NULL,
    weekday     INTEGER NOT NULL,   -- 0=Montag .. 6=Sonntag (wie date.weekday())
    start_time  TEXT NOT NULL,      -- 'HH:MM'
    end_time    TEXT NOT NULL,      -- 'HH:MM'
    room        TEXT,
    notiz       TEXT,
    created_at  REAL,
    updated_at  REAL
);
CREATE INDEX IF NOT EXISTS idx_timetable_weekday ON timetable(weekday);

-- Frei waehlbare Fach-Farben (Stundenplan-Kacheln). Fehlt ein Eintrag, weist die
-- Oberflaeche automatisch eine Palettenfarbe zu (deterministisch, ohne DB-Eintrag).
CREATE TABLE IF NOT EXISTS subject_colors (
    subject     TEXT PRIMARY KEY,
    color       TEXT NOT NULL    -- Hex, z. B. '#4A45C4'
);

-- Lernzeit-Tracker (Pomodoro + freier Timer): EIN Eintrag pro abgeschlossenem
-- Lernblock (Arbeitsphase). Wird erst beim Beenden des Blocks geschrieben, nicht
-- waehrend er laeuft - ein Browser-Reload waehrenddessen verliert daher hoechstens
-- den aktuell laufenden Block, nie fertige.
CREATE TABLE IF NOT EXISTS study_sessions (
    session_id    TEXT PRIMARY KEY,
    subject       TEXT,
    mode          TEXT,             -- 'pomodoro' | 'frei'
    started_at    REAL NOT NULL,
    ended_at      REAL NOT NULL,
    duration_sec  INTEGER NOT NULL,
    notiz         TEXT
);
CREATE INDEX IF NOT EXISTS idx_study_sessions_subject ON study_sessions(subject);
CREATE INDEX IF NOT EXISTS idx_study_sessions_started ON study_sessions(started_at);

-- Lernplan: KI-Gliederung eines/mehrerer Dokumente -> realistischer, auf Tage
-- verteilter Zeitplan (siehe ragapp/study_plan.py, docs/LERNPLAN_FORSCHUNG.md).
CREATE TABLE IF NOT EXISTS study_plans (
    plan_id       TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    subject       TEXT,
    doc_ids       TEXT,             -- JSON-Liste gewaehlter Dokument-IDs
    deadline      TEXT,             -- ISO-Datum oder NULL ("so schnell wie moeglich")
    daily_minutes INTEGER NOT NULL, -- vom Nutzer angegebenes Zeitbudget/Tag
    status        TEXT DEFAULT 'draft',  -- draft (Gliederung wird bearbeitet) | active | done
    created_at    REAL,
    updated_at    REAL
);

CREATE TABLE IF NOT EXISTS study_plan_sections (
    section_id    TEXT PRIMARY KEY,
    plan_id       TEXT NOT NULL,
    order_index   INTEGER NOT NULL,
    title         TEXT NOT NULL,
    summary       TEXT,
    est_chars     INTEGER DEFAULT 0,
    est_minutes   INTEGER DEFAULT 0,
    done          INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_plan_sections_plan ON study_plan_sections(plan_id);

CREATE TABLE IF NOT EXISTS study_plan_blocks (
    block_id      TEXT PRIMARY KEY,
    plan_id       TEXT NOT NULL,
    section_id    TEXT,
    planned_date  TEXT NOT NULL,    -- ISO-Datum
    planned_min   INTEGER NOT NULL,
    done          INTEGER DEFAULT 0,
    done_via      TEXT,             -- 'pomodoro' (echte Zeit erfasst) | 'manual' | NULL
    actual_min    INTEGER           -- ECHTE, per Pomodoro gemessene Minuten (NULL = keine
                                     -- Messung, z. B. manuell abgehakt) - Grundlage der
                                     -- selbstlernenden Zeitkalibrierung (time_calibration)
);
CREATE INDEX IF NOT EXISTS idx_plan_blocks_plan ON study_plan_blocks(plan_id);
CREATE INDEX IF NOT EXISTS idx_plan_blocks_date ON study_plan_blocks(planned_date);

-- Echte gemessene Gliederungs-Dauern (pro Modell) - kalibriert die grobe ETA-
-- Formel in der Oberflaeche mit der Zeit selbstlernend nach (siehe study_plan.py).
CREATE TABLE IF NOT EXISTS plan_eta_samples (
    sample_id   TEXT PRIMARY KEY,
    model       TEXT,
    chars       INTEGER,
    seconds     REAL,
    created_at  REAL
);
CREATE INDEX IF NOT EXISTS idx_eta_samples_model ON plan_eta_samples(model);

-- Freie Notizen: EIGENE Gedanken des Nutzers, im Unterschied zu allen anderen
-- Inhalten der App (Zusammenfassung/Karten/Gliederung sind KI-generiert). Bewusst
-- NICHT im RAG-Index (siehe ragapp/ui/pages/12_notizen.py-Docstring) - reine
-- SQLite-Volltextsuche statt Vektor-/BM25-Suche.
CREATE TABLE IF NOT EXISTS notes (
    note_id     TEXT PRIMARY KEY,
    subject     TEXT,
    doc_id      TEXT,             -- optional: an ein bestimmtes Dokument geheftet
    topic       TEXT,             -- optional: an ein Thema/Abschnitt geheftet
    collection  TEXT,             -- freie "Sammlung" (wie 'deck' bei Karten)
    title       TEXT,
    body        TEXT NOT NULL,    -- Markdown
    pinned      INTEGER DEFAULT 0,
    created_at  REAL,
    updated_at  REAL
);
CREATE INDEX IF NOT EXISTS idx_notes_subject ON notes(subject);
CREATE INDEX IF NOT EXISTS idx_notes_doc ON notes(doc_id);
CREATE INDEX IF NOT EXISTS idx_notes_collection ON notes(collection);

-- Echte Zeichen/Token-Messwerte pro Modell (aus Ollamas prompt_eval_count) -
-- kalibriert das Zeichen-Budget der Chat-Verlaufs-Kompaktierung selbstlernend
-- auf das tatsaechlich konfigurierte Modell, statt eine feste Schaetzung zu
-- raten (siehe ragapp/graph/rag_graph.py).
CREATE TABLE IF NOT EXISTS llm_token_samples (
    sample_id   TEXT PRIMARY KEY,
    model       TEXT,
    chars       INTEGER,
    tokens      INTEGER,
    created_at  REAL
);
CREATE INDEX IF NOT EXISTS idx_token_samples_model ON llm_token_samples(model);

-- Uebungsaufgaben: mehrschrittige Rechen-/Anwendungsaufgaben mit Musterloesung.
-- BEWUSST GETRENNT von review_items/review_log: SM-2/FSRS modellieren
-- Vergessens-Zerfall fuer ATOMARE Fakten, bei denen ein Wiederabfragen "faellig
-- in X Tagen" sinnvoll ist - eine mehrabsatzige Rechenaufgabe mit bekannten
-- Zahlen erneut "in 2 Minuten" vorzulegen waere unehrlich. Eine Aufgabe wird
-- daher nie "faellig", sie bleibt einfach dauerhaft in der Liste zum Ueben.
CREATE TABLE IF NOT EXISTS practice_problems (
    problem_id      TEXT PRIMARY KEY,
    subject         TEXT,
    doc_id          TEXT,
    topic           TEXT,
    kind            TEXT,               -- 'numeric' | 'scenario'
    problem_text    TEXT NOT NULL,
    given_json      TEXT,               -- [{"label":..., "value":...}]
    steps_json      TEXT NOT NULL,      -- [{"step_text":...}]
    final_answer    TEXT,
    hints_json      TEXT,               -- [hinweis, ...] progressiv
    source_excerpt  TEXT,
    model           TEXT,
    created_at      REAL
);
CREATE INDEX IF NOT EXISTS idx_practice_problems_subject ON practice_problems(subject);
CREATE INDEX IF NOT EXISTS idx_practice_problems_doc ON practice_problems(doc_id);
CREATE INDEX IF NOT EXISTS idx_practice_problems_topic ON practice_problems(topic);

-- Append-only Log der Selbsteinschaetzungen (Stil wie review_log, aber OHNE
-- SM-2/FSRS-Zustand - siehe Kommentar oben).
CREATE TABLE IF NOT EXISTS practice_attempts (
    attempt_id   TEXT PRIMARY KEY,
    problem_id   TEXT NOT NULL,
    attempted_at REAL,
    self_rating  INTEGER,   -- 0=falsch, 1=teilweise, 2=richtig (wie review_log.rating)
    notiz        TEXT
);
CREATE INDEX IF NOT EXISTS idx_practice_attempts_problem ON practice_attempts(problem_id);

-- Mindmaps: hierarchischer Themenbaum aus dem Inhaltsverzeichnis gewaehlter
-- Dokumente (wie study_plans/study_plan_sections, aber als EIN JSON-Graph statt
-- Zeilen-Tabelle - eine Mindmap-Struktur mit Eltern/Kind- UND Querverbindungen
-- passt nicht sinnvoll in eine flache Tabelle). LLM-Generierung ist zu teuer
-- fuer "bei jedem Aufruf neu" - mehrere parallele Mindmaps bleiben wie bei
-- Lernplaenen wählbar.
CREATE TABLE IF NOT EXISTS mindmaps (
    mindmap_id  TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    subject     TEXT,
    doc_ids     TEXT,             -- JSON-Liste gewaehlter Dokument-IDs
    graph_json  TEXT NOT NULL,    -- {"root":..., "nodes":[...], "links":[...]}
    model       TEXT,
    created_at  REAL,
    updated_at  REAL
);
CREATE INDEX IF NOT EXISTS idx_mindmaps_subject ON mindmaps(subject);

-- Audio-Overviews: gesprochenes Erklaer-Skript (LLM) + damit synthetisierte
-- WAV-Datei (Chatterbox Multilingual, geklonte Nutzerstimme - siehe ragapp/audio_overview.py).
-- Skript-TEXT liegt in der DB (klein, durchsuchbar); die Audio-Datei selbst
-- liegt unter data/audio_overviews/ - nur der Pfad wird referenziert (wie
-- source_path bei documents), Audiodaten gehoeren nicht in SQLite-TEXT/BLOB.
CREATE TABLE IF NOT EXISTS audio_overviews (
    overview_id TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    subject     TEXT,
    doc_ids     TEXT,             -- JSON-Liste gewaehlter Dokument-IDs
    script_text TEXT NOT NULL,
    audio_path  TEXT NOT NULL,    -- relativ zu AUDIO_DIR
    model       TEXT,
    created_at  REAL,
    updated_at  REAL
);
CREATE INDEX IF NOT EXISTS idx_audio_overviews_subject ON audio_overviews(subject);

-- Dauerhaft gemerkte Ausspracheregeln fuers Vorlesen (siehe
-- ragapp/audio_overview.py: _apply_pronunciation_fixes/suggest_pronunciations).
-- Ergaenzt die fest im Code hinterlegte _PRONUNCIATION_FIXES-Liste um vom
-- Nutzer BESTAETIGTE, vom LLM vorgeschlagene Korrekturen (z. B. "nmap" ->
-- "en map") - einmal bestaetigt, gilt die Korrektur automatisch fuer ALLE
-- kuenftigen Audio-Overviews, nicht nur fuer das eine Skript, in dem sie
-- entdeckt wurde.
CREATE TABLE IF NOT EXISTS pronunciation_fixes (
    word        TEXT PRIMARY KEY,   -- Original-Schreibweise, wie erkannt
    replacement TEXT NOT NULL,      -- gesprochene/phonetische Ersetzung
    created_at  REAL,
    updated_at  REAL
);

-- Taegliche Momentaufnahme von "Klausur-Bereitschaft" und "Sitzt"-Anteil (siehe
-- analytics.subject_readiness()/overview()) - beide werden sonst IMMER LIVE aus
-- dem aktuellen FSRS-Zustand berechnet, es existiert also von Haus aus keine
-- Historie dafuer (anders als retention_trend(), das aus den zeitgestempelten
-- review_log-Eintraegen echte Vergangenheitswerte ableiten kann). Ein Eintrag
-- pro (Tag, Fach) - "_all_" steht fuer die Fach-Auswahl "Alle Faecher" -, beim
-- erneuten Schreiben AM SELBEN TAG ueberschrieben (PRIMARY KEY), damit
-- mehrfaches Oeffnen der Seite an einem Tag nicht mehrere Zeilen erzeugt.
-- Baut erst AB dem Tag der Einfuehrung eine echte Kurve auf - fuer Tage davor
-- gibt es bewusst KEINE rueckwirkend rekonstruierten Werte (waere aus dem
-- heutigen FSRS-Zustand nicht verlaesslich moeglich, siehe analytics.py).
CREATE TABLE IF NOT EXISTS progress_snapshots (
    day             TEXT NOT NULL,
    subject         TEXT NOT NULL,
    readiness_pct   INTEGER,
    mastery_pct     INTEGER,
    created_at      REAL,
    PRIMARY KEY (day, subject)
);
CREATE INDEX IF NOT EXISTS idx_progress_snapshots_subject ON progress_snapshots(subject);
"""


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    _ensure_initialized()
    conn = sqlite3.connect(str(MANIFEST_DB))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        # Additive Migrationen fuer bestehende Karten-DBs: neue Spalten nachziehen.
        try:
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(review_items)")}
            _adds = [
                ("deck", "ALTER TABLE review_items ADD COLUMN deck TEXT"),
                ("answer", "ALTER TABLE review_items ADD COLUMN answer TEXT"),
                ("use_flashcard", "ALTER TABLE review_items ADD COLUMN use_flashcard INTEGER DEFAULT 1"),
                ("use_embedding", "ALTER TABLE review_items ADD COLUMN use_embedding INTEGER DEFAULT 1"),
                ("edited", "ALTER TABLE review_items ADD COLUMN edited INTEGER DEFAULT 0"),
                ("fsrs_state", "ALTER TABLE review_items ADD COLUMN fsrs_state INTEGER"),
                ("fsrs_step", "ALTER TABLE review_items ADD COLUMN fsrs_step INTEGER"),
                ("stability", "ALTER TABLE review_items ADD COLUMN stability REAL"),
                ("difficulty", "ALTER TABLE review_items ADD COLUMN difficulty REAL"),
            ]
            for name, ddl in _adds:
                if name not in cols:
                    conn.execute(ddl)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_review_deck ON review_items(deck)")
        except Exception:  # noqa: BLE001
            # Additive, idempotente Migration -> nicht fatal, aber sichtbar loggen
            # (nicht mehr still verschlucken).
            _log.warning("Additive Migration review_items uebersprungen", exc_info=True)
        # Additive Migration fuer review_log: Konfidenz (JOL) + Sync-Felder nachziehen.
        try:
            rlcols = {r["name"] for r in conn.execute("PRAGMA table_info(review_log)")}
            for _c, _ddl in (("confidence", "ALTER TABLE review_log ADD COLUMN confidence TEXT"),
                             ("device_id", "ALTER TABLE review_log ADD COLUMN device_id TEXT"),
                             ("event_uid", "ALTER TABLE review_log ADD COLUMN event_uid TEXT"),
                             ("due_after", "ALTER TABLE review_log ADD COLUMN due_after REAL"),
                             ("fsrs_state_after", "ALTER TABLE review_log ADD COLUMN fsrs_state_after INTEGER"),
                             ("fsrs_step_after", "ALTER TABLE review_log ADD COLUMN fsrs_step_after INTEGER"),
                             ("stability_after", "ALTER TABLE review_log ADD COLUMN stability_after REAL"),
                             ("difficulty_after", "ALTER TABLE review_log ADD COLUMN difficulty_after REAL")):
                if _c not in rlcols:
                    conn.execute(_ddl)
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_reviewlog_uid ON review_log(event_uid)")
        except Exception:  # noqa: BLE001
            _log.warning("Additive Migration review_log uebersprungen", exc_info=True)
        # Einmaliger FSRS-6-Backfill: bereits geuebte Karten (reps>0) OHNE FSRS-Zustand
        # bekommen ein grobes Seeding aus dem alten SM-2-Zustand (stability ~ Intervall
        # in Tagen, difficulty aus ease abgeleitet) - kein Forschungswert, nur ein
        # Startpunkt; FSRS korrigiert sich mit der naechsten echten Wiederholung selbst.
        # Idempotent (WHERE stability IS NULL), nie geuebte Karten bleiben unangetastet
        # (starten frisch beim ersten echten Review). Additiv, aber echte Nutzerdaten
        # -> vorher sichern.
        try:
            _to_seed = conn.execute(
                "SELECT card_id, ease, interval FROM review_items "
                "WHERE reps>0 AND stability IS NULL").fetchall()
            if _to_seed:
                _pre_destructive_snapshot("vor-fsrs-backfill")
                for _r in _to_seed:
                    _stability = max(1.0, float(_r["interval"] or 1))
                    _difficulty = max(1.0, min(10.0, 11.0 - 3.0 * float(_r["ease"] or 2.5)))
                    conn.execute(
                        "UPDATE review_items SET fsrs_state=2, stability=?, difficulty=? "
                        "WHERE card_id=?", (_stability, _difficulty, _r["card_id"]))
                _log.info("FSRS-6-Backfill: %d Karte(n) mit Legacy-Zustand geseedet",
                         len(_to_seed))
        except Exception:  # noqa: BLE001
            _log.warning("FSRS-6-Backfill uebersprungen", exc_info=True)
        # Additive Migration fuer documents: OCR-Zaehler (F2) + RAG-Auswahl (Dokument
        # verwalten/archivieren, ohne es zu chunken/einzubetten).
        try:
            dcols = {r["name"] for r in conn.execute("PRAGMA table_info(documents)")}
            if "ocr_partial_pages" not in dcols:
                conn.execute("ALTER TABLE documents ADD COLUMN ocr_partial_pages INTEGER DEFAULT 0")
            if "use_rag" not in dcols:
                conn.execute("ALTER TABLE documents ADD COLUMN use_rag INTEGER DEFAULT 1")
            if "tags" not in dcols:
                conn.execute("ALTER TABLE documents ADD COLUMN tags TEXT")
        except Exception:  # noqa: BLE001
            _log.warning("Additive Migration documents uebersprungen", exc_info=True)
        # Additive Migration fuer study_plan_blocks: ehrlich unterscheiden, ob ein
        # Block ueber eine echte Pomodoro-Zeitmessung oder manuell abgehakt wurde.
        try:
            bcols = {r["name"] for r in conn.execute("PRAGMA table_info(study_plan_blocks)")}
            if "done_via" not in bcols:
                conn.execute("ALTER TABLE study_plan_blocks ADD COLUMN done_via TEXT")
            if "actual_min" not in bcols:
                conn.execute("ALTER TABLE study_plan_blocks ADD COLUMN actual_min INTEGER")
        except Exception:  # noqa: BLE001
            _log.warning("Additive Migration study_plan_blocks uebersprungen", exc_info=True)
        # Additive Migration fuer exams: tatsaechlich erhaltene Note (Noten-
        # Tracking/GPA, siehe upsert_exam()/planner.gpa_summary()) - kommt zeitlich
        # NACH dem Anlegen des Klausurtermins, daher separate Migration.
        try:
            ecols = {r["name"] for r in conn.execute("PRAGMA table_info(exams)")}
            if "note" not in ecols:
                conn.execute("ALTER TABLE exams ADD COLUMN note REAL")
            if "note_updated_at" not in ecols:
                conn.execute("ALTER TABLE exams ADD COLUMN note_updated_at REAL")
        except Exception:  # noqa: BLE001
            _log.warning("Additive Migration exams uebersprungen", exc_info=True)


def _ensure_initialized() -> None:
    """Legt Schema an und zieht additive Migrationen nach - genau EINMAL, beim
    ersten DB-Zugriff (frueher lief das als Import-Nebenwirkung, siehe Ro7).

    Idempotent und exception-sichtbar: schlaegt die Initialisierung fehl, wird das
    Flag zurueckgesetzt (naechster Zugriff versucht es erneut), der Fehler geloggt
    und weitergereicht - statt still verschluckt."""
    global _initialized
    if _initialized:
        return
    # Flag VOR init_db() setzen: init_db() nutzt _connect(), das wiederum
    # _ensure_initialized() aufruft - so wird eine Endlos-Rekursion vermieden.
    _initialized = True
    try:
        init_db()
    except Exception:
        _initialized = False
        _log.exception("Manifest-Initialisierung fehlgeschlagen")
        raise


def _pre_destructive_snapshot(reason: str) -> None:
    """Zieht vor destruktiven Aktionen (Karten/Deck loeschen, Neu-Ernte) einen
    Lernstand-Snapshot. Lazy-Import gegen Zyklen; darf nie den Betrieb stoeren."""
    try:
        from ragapp import backup
        backup.snapshot(reason)
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- #
# Dokument-Ebene
# --------------------------------------------------------------------------- #
def find_document_by_content(content_hash: str) -> Optional[sqlite3.Row]:
    """Gibt ein bereits vorhandenes Dokument mit identischem Inhalt zurück."""
    with _connect() as conn:
        cur = conn.execute(
            "SELECT * FROM documents WHERE content_hash = ? LIMIT 1", (content_hash,)
        )
        return cur.fetchone()


def get_document(doc_id: str) -> Optional[sqlite3.Row]:
    with _connect() as conn:
        cur = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,))
        return cur.fetchone()


def upsert_document(
    *,
    doc_id: str,
    content_hash: str,
    source_path: str,
    filename: str,
    subject: str,
    filetype: str,
    num_chunks: int,
    num_questions: int,
    char_count: int,
    status: str = "ok",
    ocr_partial_pages: int = 0,
    use_rag: Optional[bool] = None,
) -> None:
    """``use_rag=None`` laesst einen bereits vorhandenen Wert unveraendert (Default
    fuer neue Dokumente: an) - so ueberschreibt ein routinemaessiger Re-Scan (Watcher,
    Ordner-Import) NIE die bewusste Entscheidung 'nur archivieren' eines Nutzers,
    solange der Aufrufer sie nicht ausdruecklich (True/False) setzen will."""
    now = time.time()
    with _connect() as conn:
        exists = conn.execute(
            "SELECT ingested_at, use_rag FROM documents WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        ingested_at = exists["ingested_at"] if exists else now
        if use_rag is None:
            use_rag_val = int(exists["use_rag"]) if exists and exists["use_rag"] is not None else 1
        else:
            use_rag_val = 1 if use_rag else 0
        conn.execute(
            """
            INSERT INTO documents
                (doc_id, content_hash, source_path, filename, subject, filetype,
                 num_chunks, num_questions, char_count, status, ocr_partial_pages,
                 use_rag, ingested_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(doc_id) DO UPDATE SET
                content_hash=excluded.content_hash,
                source_path=excluded.source_path,
                filename=excluded.filename,
                subject=excluded.subject,
                filetype=excluded.filetype,
                num_chunks=excluded.num_chunks,
                num_questions=excluded.num_questions,
                char_count=excluded.char_count,
                status=excluded.status,
                ocr_partial_pages=excluded.ocr_partial_pages,
                use_rag=excluded.use_rag,
                updated_at=excluded.updated_at
            """,
            (doc_id, content_hash, source_path, filename, subject, filetype,
             num_chunks, num_questions, char_count, status, int(ocr_partial_pages or 0),
             use_rag_val, ingested_at, now),
        )


def delete_document(doc_id: str) -> None:
    """Entfernt Dokument + zugehörige Chunk-Hashes aus dem Manifest."""
    with _connect() as conn:
        conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
        conn.execute("DELETE FROM chunk_hashes WHERE doc_id = ?", (doc_id,))


def set_document_tags(doc_id: str, tags: "str | None") -> None:
    """Setzt die frei vergebenen Kategorien (kommagetrennt) eines Dokuments."""
    dedup = list(dict.fromkeys(t.strip() for t in (tags or "").split(",") if t.strip()))
    norm = ", ".join(dedup) or None
    with _connect() as conn:
        conn.execute("UPDATE documents SET tags=?, updated_at=? WHERE doc_id=?",
                     (norm, time.time(), doc_id))


def all_document_tags() -> list[str]:
    """Alle im Bestand vorkommenden Kategorien (sortiert, ohne Duplikate) - fuer
    Filter/Vorschlaege in der Oberflaeche."""
    seen: set[str] = set()
    with _connect() as conn:
        for r in conn.execute("SELECT DISTINCT tags FROM documents WHERE tags IS NOT NULL"):
            for t in (r["tags"] or "").split(","):
                t = t.strip()
                if t:
                    seen.add(t)
    return sorted(seen)


def set_num_questions(doc_id: str, n: int) -> None:
    """Setzt die Fragen-Anzahl eines Dokuments (z. B. nach dem Löschen von Fragen)."""
    with _connect() as conn:
        conn.execute("UPDATE documents SET num_questions = ?, updated_at = ? WHERE doc_id = ?",
                     (n, time.time(), doc_id))


def clear_questions(subject: Optional[str] = None) -> None:
    """Setzt num_questions auf 0 - fuer alle Dokumente oder nur ein Fach."""
    with _connect() as conn:
        if subject:
            conn.execute("UPDATE documents SET num_questions = 0 WHERE subject = ?", (subject,))
        else:
            conn.execute("UPDATE documents SET num_questions = 0")


def list_documents() -> list[sqlite3.Row]:
    with _connect() as conn:
        cur = conn.execute("SELECT * FROM documents ORDER BY subject, filename")
        return cur.fetchall()


def documents_needing_ocr() -> list[dict]:
    """Dokumente, deren Textextraktion vermutlich verunglueckt ist - Kandidaten fuer
    OCR/Neu-Import. Je Zeile ein Feld ``reason``:
      * 'empty'   -> status='ocr_needed' (gar kein/unbrauchbarer Text extrahiert),
      * 'partial' -> ocr_partial_pages>0 (einzelne Scan-Seiten unvollstaendig gelesen,
                     der Rest des Dokuments ist brauchbar)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM documents "
            "WHERE status='ocr_needed' OR COALESCE(ocr_partial_pages,0) > 0 "
            "ORDER BY subject, filename"
        ).fetchall()
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        # 'empty' (ganzes Dok betroffen) hat Vorrang vor 'partial'.
        d["reason"] = "empty" if d.get("status") == "ocr_needed" else "partial"
        out.append(d)
    return out


# --------------------------------------------------------------------------- #
# Chunk-Ebene (exakte Deduplizierung)
# --------------------------------------------------------------------------- #
def chunk_hash_exists(chunk_hash: str) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "SELECT 1 FROM chunk_hashes WHERE chunk_hash = ? LIMIT 1", (chunk_hash,)
        )
        return cur.fetchone() is not None


def register_chunk_hash(chunk_hash: str, doc_id: str, chunk_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO chunk_hashes (chunk_hash, doc_id, chunk_id, created_at)"
            " VALUES (?,?,?,?)",
            (chunk_hash, doc_id, chunk_id, time.time()),
        )


def clear_chunk_hashes(doc_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM chunk_hashes WHERE doc_id = ?", (doc_id,))


def chunk_ids_for_doc(doc_id: str) -> list[str]:
    """Alle bisher registrierten Chunk-IDs eines Dokuments (aus der Hash-Registry).
    Wird beim Aktualisieren gebraucht, um nach dem Schreiben der NEUEN Chunks die
    verwaisten ALTEN gezielt zu entfernen (write-new-then-delete-old, Ro3)."""
    with _connect() as conn:
        return [r["chunk_id"] for r in conn.execute(
            "SELECT chunk_id FROM chunk_hashes WHERE doc_id = ?", (doc_id,))]


def stats() -> dict:
    with _connect() as conn:
        docs = conn.execute("SELECT COUNT(*) AS c FROM documents").fetchone()["c"]
        chunks = conn.execute("SELECT COALESCE(SUM(num_chunks),0) AS c FROM documents").fetchone()["c"]
        questions = conn.execute("SELECT COALESCE(SUM(num_questions),0) AS c FROM documents").fetchone()["c"]
        subjects = conn.execute("SELECT COUNT(DISTINCT subject) AS c FROM documents").fetchone()["c"]
    return {"documents": docs, "chunks": chunks, "questions": questions, "subjects": subjects}


# --------------------------------------------------------------------------- #
# Lern-Layer: Karteikarten + Spaced Repetition
# --------------------------------------------------------------------------- #
def upsert_review_items(cards: list[dict]) -> int:
    """Legt neue Karteikarten an (bewahrt bei bereits vorhandenen den Lernfortschritt;
    aktualisiert nur Inhalt/Metadaten). Gibt die Anzahl NEUER Karten zurueck."""
    if not cards:
        return 0
    now = time.time()
    with _connect() as conn:
        existing = {r["card_id"]: r["edited"]
                    for r in conn.execute("SELECT card_id, edited FROM review_items")}
        neu = 0
        for c in cards:
            cid = c["card_id"]
            ans = (c.get("answer") or "").strip() or None
            if cid in existing:
                if existing[cid]:
                    # Manuell bearbeitet -> Frage/Antwort NICHT ueberschreiben, nur Metadaten.
                    conn.execute(
                        "UPDATE review_items SET source=?, chroma_id=?, subject=?, topic=?, "
                        "doc_id=? WHERE card_id=?",
                        (c.get("source"), c.get("chroma_id"), c.get("subject"),
                         c.get("topic"), c.get("doc_id"), cid),
                    )
                else:
                    # answer nur setzen, wenn die Ernte eine liefert (sonst bestehende behalten).
                    if ans is not None:
                        conn.execute(
                            "UPDATE review_items SET source=?, chroma_id=?, subject=?, topic=?, "
                            "front=?, back=?, answer=?, doc_id=? WHERE card_id=?",
                            (c.get("source"), c.get("chroma_id"), c.get("subject"), c.get("topic"),
                             c["front"], c["back"], ans, c.get("doc_id"), cid),
                        )
                    else:
                        conn.execute(
                            "UPDATE review_items SET source=?, chroma_id=?, subject=?, topic=?, "
                            "front=?, back=?, doc_id=? WHERE card_id=?",
                            (c.get("source"), c.get("chroma_id"), c.get("subject"), c.get("topic"),
                             c["front"], c["back"], c.get("doc_id"), cid),
                        )
            else:
                conn.execute(
                    "INSERT INTO review_items (card_id, source, chroma_id, subject, topic, "
                    "front, back, answer, doc_id, ease, interval, reps, lapses, due, created_at, "
                    "suspended, use_flashcard, use_embedding, edited) "
                    "VALUES (?,?,?,?,?,?,?,?,?,2.5,0,0,0,?,?,0,1,1,0)",
                    (cid, c.get("source"), c.get("chroma_id"), c.get("subject"), c.get("topic"),
                     c["front"], c["back"], ans, c.get("doc_id"), now, now),
                )
                neu += 1
        return neu


def _filter(subject: Optional[str], deck: Optional[str]) -> tuple[str, list]:
    """Baut die WHERE-Zusaetze fuer Fach/Stapel. deck='__none__' = ohne Stapel."""
    sql, args = "", []
    if subject:
        sql += " AND subject=?"
        args.append(subject)
    if deck is not None:
        if deck == "__none__":
            sql += " AND deck IS NULL"
        else:
            sql += " AND deck=?"
            args.append(deck)
    return sql, args


def _scope(subject: Optional[str], deck: Optional[str],
           decks: Optional[list[str]]) -> tuple[str, list]:
    """Wie _filter, unterstuetzt zusaetzlich eine LISTE von Stapeln (Mehrfachauswahl).
    '__none__' in der Liste = auch Karten ohne Stapel. Leere Liste -> nichts."""
    if decks is None:
        return _filter(subject, deck)
    sql, args = "", []
    if subject:
        sql += " AND subject=?"; args.append(subject)
    named = [d for d in decks if d != "__none__"]
    parts = []
    if named:
        parts.append(f"deck IN ({','.join('?' * len(named))})"); args += named
    if "__none__" in decks:
        parts.append("deck IS NULL")
    sql += " AND (" + " OR ".join(parts) + ")" if parts else " AND 1=0"
    return sql, args


def review_counts(subject: Optional[str] = None, deck: Optional[str] = None,
                  decks: Optional[list[str]] = None) -> dict:
    """Zaehlt Karten: gesamt / faellig / neu (nie geuebt) / gelernt (schon geuebt)."""
    now = time.time()
    fsql, fargs = _scope(subject, deck, decks)
    where = "WHERE suspended=0 AND use_flashcard=1" + fsql
    with _connect() as conn:
        def one(extra, a):
            return conn.execute(f"SELECT COUNT(*) AS c FROM review_items {where}{extra}",
                                fargs + a).fetchone()["c"]
        return {
            "total": one("", []),
            "due": one(" AND due<=?", [now]),
            "neu": one(" AND reps=0", []),
            "gelernt": one(" AND reps>0", []),
        }


def _interleave_by_topic(cards: list[dict]) -> list[dict]:
    """Mischt Karten verschraenkt: reihum je ein Thema (Fallback: Fach), sodass
    moeglichst nie zwei gleiche Themen aufeinanderfolgen. Innerhalb eines Themas
    bleibt die urspruengliche Reihenfolge (Faelligkeit) erhalten."""
    from collections import OrderedDict, deque
    groups: "OrderedDict[str, deque]" = OrderedDict()
    for c in cards:
        key = str(c.get("topic") or c.get("subject") or "?")
        groups.setdefault(key, deque()).append(c)
    queues = list(groups.values())
    out: list[dict] = []
    while queues:
        for q in list(queues):
            if q:
                out.append(q.popleft())
            if not q:
                queues.remove(q)
    return out


def get_due_cards(subject: Optional[str] = None, limit: int = 20,
                  now: Optional[float] = None, deck: Optional[str] = None,
                  decks: Optional[list[str]] = None,
                  new_limit: Optional[int] = None, order: str = "due",
                  cram: bool = False) -> list[dict]:
    """Faellige Karten (Wiederholungen zuerst, dann neue), aufsteigend nach Faelligkeit.
    ``decks`` erlaubt Mehrfachauswahl von Stapeln; ``new_limit`` deckelt die Zahl NEUER
    (nie geuebter) Karten in dieser Auswahl (Tages-/Runden-Limit). ``order='interleave'``
    mischt die ausgewaehlten Karten verschraenkt nach Thema (bessere Unterscheidung).
    ``cram=True`` (Klausur-Modus): fuellt die Runde bei zu wenig Faelligen mit den
    SCHWAECHSTEN noch-nicht-faelligen Karten auf (wenige reps / niedrige Ease)."""
    now = now if now is not None else time.time()
    ssql, sargs = _scope(subject, deck, decks)
    q = ("SELECT * FROM review_items WHERE suspended=0 AND use_flashcard=1 AND due<=?" + ssql
         + " ORDER BY CASE WHEN reps>0 THEN 0 ELSE 1 END, due ASC")
    with _connect() as conn:
        rows = [dict(r) for r in conn.execute(q, [now] + sargs).fetchall()]
    out, new_count = [], 0
    for r in rows:
        if r.get("reps", 0) == 0:
            if new_limit is not None and new_count >= int(new_limit):
                continue
            new_count += 1
        out.append(r)
        if len(out) >= int(limit):
            break
    if cram and len(out) < int(limit):
        have = {c["card_id"] for c in out}
        eq = ("SELECT * FROM review_items WHERE suspended=0 AND use_flashcard=1 AND due>?"
              + ssql + " ORDER BY reps ASC, ease ASC, due ASC LIMIT ?")
        with _connect() as conn:
            extra = [dict(r) for r in conn.execute(eq, [now] + sargs + [int(limit)]).fetchall()]
        for r in extra:
            if r["card_id"] in have:
                continue
            out.append(r)
            if len(out) >= int(limit):
                break
    if order == "interleave" and len(out) > 2:
        out = _interleave_by_topic(out)
    return out


def _local_day_start(now: Optional[float] = None) -> float:
    """Lokaler Tagesbeginn (Mitternacht) als epoch-Sekunde."""
    lt = time.localtime(now if now is not None else time.time())
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))


def count_new_today(subject: Optional[str] = None, deck: Optional[str] = None,
                    decks: Optional[list[str]] = None,
                    day_start: Optional[float] = None) -> int:
    """Anzahl heute ERSTMALS geuebter (neuer) Karten in der Auswahl - fuer das
    Tages-Limit neuer Karten."""
    if day_start is None:
        day_start = _local_day_start()
    ssql, sargs = _scope(subject, deck, decks)
    # 'subject' existiert in BEIDEN JOIN-Tabellen -> qualifizieren (sonst 'ambiguous
    # column name'). deck gibt es nur in review_items, ist also eindeutig.
    ssql = ssql.replace(" subject=?", " ri.subject=?")
    q = ("SELECT COUNT(*) AS c FROM (SELECT rl.card_id, MIN(rl.reviewed_at) AS first "
         "FROM review_log rl JOIN review_items ri ON ri.card_id=rl.card_id "
         "WHERE ri.suspended=0 AND ri.use_flashcard=1" + ssql + " GROUP BY rl.card_id) t "
         "WHERE t.first >= ?")
    with _connect() as conn:
        return conn.execute(q, sargs + [day_start]).fetchone()["c"]


def record_review(card_id: str, rating: int, *, fsrs_state: int, fsrs_step: Optional[int],
                  stability: Optional[float], difficulty: Optional[float], interval: float,
                  reps: int, lapses: int, due: float, subject: Optional[str] = None,
                  topic: Optional[str] = None, confidence: Optional[str] = None) -> None:
    """Schreibt den neuen FSRS-6-Zustand einer Karte + einen Eintrag ins Lern-Log
    (inkl. optionaler Konfidenz/JOL vor dem Aufdecken). Das Legacy-Feld ``ease`` wird
    NICHT mehr fortgeschrieben (siehe Schema-Kommentar in _SCHEMA)."""
    now = time.time()
    with _connect() as conn:
        conn.execute(
            "UPDATE review_items SET fsrs_state=?, fsrs_step=?, stability=?, difficulty=?, "
            "interval=?, reps=?, lapses=?, due=?, last_review=? WHERE card_id=?",
            (fsrs_state, fsrs_step, stability, difficulty, interval, reps, lapses, due,
             now, card_id),
        )
        conn.execute(
            "INSERT INTO review_log (card_id, subject, topic, rating, reviewed_at, "
            "interval_after, fsrs_state_after, fsrs_step_after, stability_after, "
            "difficulty_after, confidence, device_id, event_uid, due_after) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (card_id, subject, topic, rating, now, interval, fsrs_state, fsrs_step,
             stability, difficulty, confidence, _device_id(), uuid.uuid4().hex, due),
        )


def study_subjects() -> list[str]:
    """Faecher, zu denen es Karten gibt."""
    with _connect() as conn:
        return [r["subject"] for r in conn.execute(
            "SELECT DISTINCT subject FROM review_items WHERE subject IS NOT NULL "
            "AND suspended=0 ORDER BY subject")]


def delete_cards(subject: Optional[str] = None) -> None:
    """Karten (+ deren Log) loeschen - alle oder nur ein Fach."""
    _pre_destructive_snapshot("vor-loeschen-" + (subject or "alle"))
    with _connect() as conn:
        if subject:
            conn.execute("DELETE FROM review_items WHERE subject=?", (subject,))
            conn.execute("DELETE FROM review_log WHERE subject=?", (subject,))
        else:
            conn.execute("DELETE FROM review_items")
            conn.execute("DELETE FROM review_log")


def list_cards(subject: Optional[str] = None, deck: Optional[str] = None,
               source: Optional[str] = None, only_unanswered: bool = False,
               limit: Optional[int] = None, offset: int = 0) -> list[dict]:
    """Karten fuer die Verwaltung/Katalog-Liste (mit Frage, Antwort, Nutzung, Stapel)."""
    fsql, fargs = _filter(subject, deck)
    sql = "SELECT * FROM review_items WHERE 1=1" + fsql
    args = list(fargs)
    if source:
        sql += " AND source=?"; args.append(source)
    if only_unanswered:
        sql += " AND source='question' AND (answer IS NULL OR answer='')"
    sql += " ORDER BY subject, deck, front"
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"; args += [int(limit), int(offset)]
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


def count_cards(subject: Optional[str] = None, deck: Optional[str] = None,
                source: Optional[str] = None, only_unanswered: bool = False) -> int:
    fsql, fargs = _filter(subject, deck)
    sql = "SELECT COUNT(*) AS c FROM review_items WHERE 1=1" + fsql
    args = list(fargs)
    if source:
        sql += " AND source=?"; args.append(source)
    if only_unanswered:
        sql += " AND source='question' AND (answer IS NULL OR answer='')"
    with _connect() as conn:
        return conn.execute(sql, args).fetchone()["c"]


def get_cards_by_ids(card_ids: list[str]) -> list[dict]:
    if not card_ids:
        return []
    ph = ",".join("?" * len(card_ids))
    with _connect() as conn:
        return [dict(r) for r in conn.execute(
            f"SELECT * FROM review_items WHERE card_id IN ({ph})", list(card_ids)).fetchall()]


def delete_card_ids(card_ids: list[str]) -> list[str]:
    """Loescht einzelne Karten (+ deren Log). Gibt die zugehoerigen Chroma-IDs zurueck,
    damit der Aufrufer die Frage bei Bedarf auch aus dem Vektorindex entfernen kann."""
    if not card_ids:
        return []
    _pre_destructive_snapshot("vor-karten-loeschen")
    ph = ",".join("?" * len(card_ids))
    with _connect() as conn:
        chroma = [r["chroma_id"] for r in conn.execute(
            f"SELECT chroma_id FROM review_items WHERE card_id IN ({ph})", list(card_ids))
            if r["chroma_id"]]
        conn.execute(f"DELETE FROM review_items WHERE card_id IN ({ph})", list(card_ids))
        conn.execute(f"DELETE FROM review_log WHERE card_id IN ({ph})", list(card_ids))
    return chroma


def delete_deck(deck: str) -> list[str]:
    """Loescht ALLE Karten eines Stapels (+ Log). Gibt deren Chroma-IDs zurueck."""
    _pre_destructive_snapshot("vor-deck-loeschen")
    with _connect() as conn:
        rows = conn.execute(
            "SELECT card_id, chroma_id FROM review_items WHERE deck=?", (deck,)).fetchall()
        ids = [r["card_id"] for r in rows]
        chroma = [r["chroma_id"] for r in rows if r["chroma_id"]]
        if ids:
            ph = ",".join("?" * len(ids))
            conn.execute(f"DELETE FROM review_items WHERE card_id IN ({ph})", ids)
            conn.execute(f"DELETE FROM review_log WHERE card_id IN ({ph})", ids)
    return chroma


def set_card_usage(card_ids: list[str], *, use_flashcard: Optional[bool] = None,
                   use_embedding: Optional[bool] = None) -> int:
    """Setzt fuer Karten, ob sie zum Abfragen (Lernrunde) und/oder fuers Embedding
    (Suche) genutzt werden. Gibt die Anzahl geaenderter Karten zurueck."""
    sets, args = [], []
    if use_flashcard is not None:
        sets.append("use_flashcard=?"); args.append(1 if use_flashcard else 0)
    if use_embedding is not None:
        sets.append("use_embedding=?"); args.append(1 if use_embedding else 0)
    if not sets or not card_ids:
        return 0
    ph = ",".join("?" * len(card_ids))
    with _connect() as conn:
        cur = conn.execute(
            f"UPDATE review_items SET {','.join(sets)} WHERE card_id IN ({ph})",
            args + list(card_ids))
        return cur.rowcount


def set_suspended(card_ids: list[str], suspended: bool = True) -> int:
    """Pausiert oder reaktiviert Karten (suspended=1 erscheint nicht in Lernrunden)."""
    if not card_ids:
        return 0
    ph = ",".join("?" * len(card_ids))
    with _connect() as conn:
        cur = conn.execute(
            f"UPDATE review_items SET suspended=? WHERE card_id IN ({ph})",
            [1 if suspended else 0] + list(card_ids))
        return cur.rowcount


def update_card(card_id: str, *, front: Optional[str] = None,
                answer: Optional[str] = None) -> None:
    """Bearbeitet Frage und/oder Antwort einer Karte und markiert sie als bearbeitet
    (die Ernte ueberschreibt bearbeitete Karten danach nicht mehr)."""
    sets, args = ["edited=1"], []
    if front is not None:
        sets.append("front=?"); args.append(front)
    if answer is not None:
        sets.append("answer=?"); args.append(answer)
    with _connect() as conn:
        conn.execute(f"UPDATE review_items SET {','.join(sets)} WHERE card_id=?",
                     args + [card_id])


def set_answer(card_id: str, answer: str) -> None:
    """Setzt die (KI-)Antwort einer Karte, ohne sie als 'bearbeitet' zu markieren."""
    with _connect() as conn:
        conn.execute("UPDATE review_items SET answer=? WHERE card_id=?", (answer, card_id))


def cards_needing_answer(subject: Optional[str] = None, deck: Optional[str] = None,
                         limit: Optional[int] = None) -> list[dict]:
    """Karten aus generierten Fragen, die noch KEINE eigene Antwort haben (zeigen bisher
    den rohen Chunk). Kandidaten fuer die Antwort-Generierung."""
    return list_cards(subject=subject, deck=deck, source="question",
                      only_unanswered=True, limit=limit)


# --------------------------------------------------------------------------- #
# Stapel (Decks): hierarchisch nach Fach, flexibel nach Doc/Thema/Karte
# --------------------------------------------------------------------------- #
def find_cards(
    *,
    subject: Optional[str] = None,
    doc_ids: Optional[list[str]] = None,
    topics: Optional[list[str]] = None,
    deck: Optional[str] = None,
    search: Optional[str] = None,
    only_unassigned: bool = False,
    exclude_suspended: bool = True,
    card_ids: Optional[list[str]] = None,
    limit: int = 500,
    offset: int = 0,
) -> list[dict]:
    """Karten nach Fach / Dokument / Thema (TOC) / Stapel / Textsuche filtern.

    Filter werden mit AND kombiniert (innerhalb von Listen: OR). Ideal fuer die
    Stapel-Vorschau vor dem Zuordnen."""
    sql = "SELECT * FROM review_items WHERE 1=1"
    args: list = []
    if exclude_suspended:
        sql += " AND suspended=0"
    if subject:
        sql += " AND subject=?"; args.append(subject)
    if doc_ids:
        sql += f" AND doc_id IN ({','.join('?' * len(doc_ids))})"; args += list(doc_ids)
    if topics:
        # Leeres Thema als '__none__'
        named = [t for t in topics if t != "__none__"]
        parts = []
        if named:
            parts.append(f"topic IN ({','.join('?' * len(named))})")
            args += named
        if "__none__" in topics:
            parts.append("(topic IS NULL OR topic='')")
        if parts:
            sql += " AND (" + " OR ".join(parts) + ")"
    if deck is not None:
        if deck == "__none__":
            sql += " AND (deck IS NULL OR deck='')"
        else:
            sql += " AND deck=?"; args.append(deck)
    if only_unassigned:
        sql += " AND (deck IS NULL OR deck='')"
    if card_ids:
        sql += f" AND card_id IN ({','.join('?' * len(card_ids))})"; args += list(card_ids)
    if search and search.strip():
        q = f"%{search.strip()}%"
        sql += " AND (front LIKE ? OR IFNULL(answer,'') LIKE ? OR IFNULL(back,'') LIKE ?)"
        args += [q, q, q]
    sql += " ORDER BY subject, IFNULL(topic,''), front LIMIT ? OFFSET ?"
    args += [int(limit), int(offset)]
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


def count_find_cards(**kwargs) -> int:
    """Wie find_cards, aber nur die Anzahl (ohne LIMIT)."""
    kw = dict(kwargs)
    kw.pop("limit", None)
    kw.pop("offset", None)
    # grosse Grenze, wir zaehlen in SQL effizienter:
    sql = "SELECT COUNT(*) AS c FROM review_items WHERE 1=1"
    args: list = []
    if kw.get("exclude_suspended", True):
        sql += " AND suspended=0"
    if kw.get("subject"):
        sql += " AND subject=?"; args.append(kw["subject"])
    if kw.get("doc_ids"):
        ids = list(kw["doc_ids"])
        sql += f" AND doc_id IN ({','.join('?' * len(ids))})"; args += ids
    if kw.get("topics"):
        topics = list(kw["topics"])
        named = [t for t in topics if t != "__none__"]
        parts = []
        if named:
            parts.append(f"topic IN ({','.join('?' * len(named))})")
            args += named
        if "__none__" in topics:
            parts.append("(topic IS NULL OR topic='')")
        if parts:
            sql += " AND (" + " OR ".join(parts) + ")"
    deck = kw.get("deck", None)
    if "deck" in kwargs and deck is not None:
        if deck == "__none__":
            sql += " AND (deck IS NULL OR deck='')"
        else:
            sql += " AND deck=?"; args.append(deck)
    if kw.get("only_unassigned"):
        sql += " AND (deck IS NULL OR deck='')"
    if kw.get("card_ids"):
        ids = list(kw["card_ids"])
        sql += f" AND card_id IN ({','.join('?' * len(ids))})"; args += ids
    if kw.get("search") and str(kw["search"]).strip():
        q = f"%{str(kw['search']).strip()}%"
        sql += " AND (front LIKE ? OR IFNULL(answer,'') LIKE ? OR IFNULL(back,'') LIKE ?)"
        args += [q, q, q]
    with _connect() as conn:
        return int(conn.execute(sql, args).fetchone()["c"])


def list_topics(subject: Optional[str] = None,
                doc_ids: Optional[list[str]] = None) -> list[str]:
    """Distincte Themen/Abschnitte (TOC aus location/header_path) der Karten."""
    sql = ("SELECT DISTINCT topic FROM review_items WHERE suspended=0 "
           "AND topic IS NOT NULL AND topic<>''")
    args: list = []
    if subject:
        sql += " AND subject=?"; args.append(subject)
    if doc_ids:
        sql += f" AND doc_id IN ({','.join('?' * len(doc_ids))})"; args += list(doc_ids)
    sql += " ORDER BY topic"
    with _connect() as conn:
        return [r["topic"] for r in conn.execute(sql, args).fetchall()]


def list_docs_with_cards(subject: Optional[str] = None) -> list[dict]:
    """Dokumente, zu denen es Karteikarten gibt (doc_id, filename, n_cards, subject)."""
    sql = (
        "SELECT ri.doc_id AS doc_id, ri.subject AS subject, COUNT(*) AS n_cards, "
        "COALESCE(d.filename, ri.doc_id) AS filename "
        "FROM review_items ri "
        "LEFT JOIN documents d ON d.doc_id = ri.doc_id "
        "WHERE ri.suspended=0 AND ri.doc_id IS NOT NULL AND ri.doc_id<>''"
    )
    args: list = []
    if subject:
        sql += " AND ri.subject=?"; args.append(subject)
    sql += " GROUP BY ri.doc_id ORDER BY filename"
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


def assign_deck(deck: Optional[str], *, doc_ids: Optional[list[str]] = None,
                subjects: Optional[list[str]] = None, card_ids: Optional[list[str]] = None,
                topics: Optional[list[str]] = None,
                only_unassigned: bool = False) -> int:
    """Ordnet Karten einem Stapel zu (deck=None hebt die Zuordnung auf).

    Auswahl-Filter werden mit **AND** kombiniert (Listen intern OR). Wenn
    ``card_ids`` gesetzt ist, werden genau diese Karten aktualisiert (andere
    Filter dienen dann nur der Einschraenkung, falls zusaetzlich gesetzt).
    Gibt die Anzahl geaenderter Karten zurueck."""
    conds, args = [], []
    # Explizite Karten-IDs: primaere Auswahl
    if card_ids:
        conds.append(f"card_id IN ({','.join('?' * len(card_ids))})")
        args += list(card_ids)
    else:
        # Ohne card_ids: Fach/Dokument/Thema muessen AND-verknuepft sein
        if subjects:
            conds.append(f"subject IN ({','.join('?' * len(subjects))})")
            args += list(subjects)
        if doc_ids:
            conds.append(f"doc_id IN ({','.join('?' * len(doc_ids))})")
            args += list(doc_ids)
        if topics:
            named = [t for t in topics if t != "__none__"]
            tparts = []
            if named:
                tparts.append(f"topic IN ({','.join('?' * len(named))})")
                args += named
            if "__none__" in topics:
                tparts.append("(topic IS NULL OR topic='')")
            if tparts:
                conds.append("(" + " OR ".join(tparts) + ")")
    if not conds:
        return 0
    where = " AND ".join(conds)
    if only_unassigned:
        where += " AND (deck IS NULL OR deck='')"
    with _connect() as conn:
        cur = conn.execute(
            f"UPDATE review_items SET deck=? WHERE {where}", [deck] + args)
        return cur.rowcount


def list_decks(subject: Optional[str] = None) -> list[str]:
    """Alle vorhandenen Stapelnamen (optional nur eines Fachs)."""
    with _connect() as conn:
        if subject:
            return [r["deck"] for r in conn.execute(
                "SELECT DISTINCT deck FROM review_items WHERE deck IS NOT NULL AND deck<>'' "
                "AND subject=? ORDER BY deck", (subject,))]
        return [r["deck"] for r in conn.execute(
            "SELECT DISTINCT deck FROM review_items WHERE deck IS NOT NULL AND deck<>'' "
            "ORDER BY deck")]


def dissolve_deck(deck: str) -> int:
    """Hebt die Zuordnung aller Karten eines Stapels auf (deck -> NULL)."""
    with _connect() as conn:
        cur = conn.execute("UPDATE review_items SET deck=NULL WHERE deck=?", (deck,))
        return cur.rowcount


def rename_deck(old_name: str, new_name: str) -> int:
    """Benennt einen Stapel um. Gibt die Anzahl umbenannter Karten zurueck."""
    old_name = (old_name or "").strip()
    new_name = (new_name or "").strip()
    if not old_name or not new_name or old_name == new_name:
        return 0
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE review_items SET deck=? WHERE deck=?", (new_name, old_name))
        return cur.rowcount


def deck_overview(subject: Optional[str] = None) -> list[dict]:
    """Pro Stapel: Kartenzahl, faellig, betroffene Faecher (fuer hierarchische UI)."""
    now = time.time()
    sql = (
        "SELECT COALESCE(deck,'') AS deck, "
        "COUNT(*) AS total, "
        "SUM(CASE WHEN due<=? THEN 1 ELSE 0 END) AS due, "
        "GROUP_CONCAT(DISTINCT subject) AS subjects "
        "FROM review_items WHERE suspended=0"
    )
    args: list = [now]
    if subject:
        sql += " AND subject=?"; args.append(subject)
    sql += " GROUP BY COALESCE(deck,'') ORDER BY deck"
    with _connect() as conn:
        rows = conn.execute(sql, args).fetchall()
        out = []
        for r in rows:
            subjs = [s for s in (r["subjects"] or "").split(",") if s]
            out.append({
                "deck": r["deck"] or None,
                "total": r["total"],
                "due": r["due"],
                "subjects": sorted(set(subjs)),
            })
        return out


# --------------------------------------------------------------------------- #
# Klausurtermine (pro Fach ein Termin)
# --------------------------------------------------------------------------- #
def upsert_exam(subject: str, *, exam_date: Optional[str] = None,
                ects: Optional[float] = None, gewicht: float = 1.0,
                notiz: Optional[str] = None, note: Optional[float] = None) -> None:
    """Legt einen Klausurtermin fuer ein Fach an oder aktualisiert ihn.
    ``exam_date`` ist ISO 'YYYY-MM-DD' (oder None/'' = kein Termin gesetzt).
    ``note`` ist die tatsaechlich erhaltene Note (meist erst lange NACH dem
    Anlegen des Termins eingetragen, siehe planner.gpa_summary())."""
    if not subject:
        return
    now = time.time()
    exam_date = (exam_date or "").strip() or None
    note_updated_at = now if note is not None else None
    with _connect() as conn:
        exists = conn.execute(
            "SELECT created_at FROM exams WHERE subject=?", (subject,)).fetchone()
        created = exists["created_at"] if exists else now
        conn.execute(
            "INSERT INTO exams (subject, exam_date, ects, gewicht, notiz, note, "
            "note_updated_at, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(subject) DO UPDATE SET exam_date=excluded.exam_date, "
            "ects=excluded.ects, gewicht=excluded.gewicht, notiz=excluded.notiz, "
            "note=excluded.note, note_updated_at=excluded.note_updated_at, "
            "updated_at=excluded.updated_at",
            (subject, exam_date, ects, float(gewicht or 1.0), notiz, note,
             note_updated_at, created, now),
        )


def get_exam(subject: str) -> Optional[dict]:
    with _connect() as conn:
        r = conn.execute("SELECT * FROM exams WHERE subject=?", (subject,)).fetchone()
        return dict(r) if r else None


def list_exams() -> list[dict]:
    """Alle Klausurtermine (mit gesetztem Datum zuerst, dann nach Datum)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM exams ORDER BY (exam_date IS NULL), exam_date, subject").fetchall()
        return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# Verwaltungsbereich: Aufgaben/Hausaufgaben
# --------------------------------------------------------------------------- #
def upsert_task(*, task_id: Optional[str] = None, subject: Optional[str] = None,
                title: str, notiz: Optional[str] = None,
                due_date: Optional[str] = None, done: bool = False) -> str:
    """Legt eine Aufgabe an (``task_id=None``) oder aktualisiert sie. Gibt die
    (ggf. neu erzeugte) ``task_id`` zurueck."""
    now = time.time()
    tid = task_id or uuid.uuid4().hex[:16]
    due_date = (due_date or "").strip() or None
    with _connect() as conn:
        exists = conn.execute("SELECT created_at FROM tasks WHERE task_id=?", (tid,)).fetchone()
        created = exists["created_at"] if exists else now
        conn.execute(
            "INSERT INTO tasks (task_id, subject, title, notiz, due_date, done, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(task_id) DO UPDATE SET subject=excluded.subject, "
            "title=excluded.title, notiz=excluded.notiz, due_date=excluded.due_date, "
            "done=excluded.done, updated_at=excluded.updated_at",
            (tid, subject, (title or "").strip(), notiz, due_date,
             1 if done else 0, created, now),
        )
    return tid


def list_tasks(subject: Optional[str] = None, include_done: bool = True) -> list[dict]:
    sql = "SELECT * FROM tasks WHERE 1=1"
    args: list = []
    if subject:
        sql += " AND subject=?"
        args.append(subject)
    if not include_done:
        sql += " AND done=0"
    sql += " ORDER BY (due_date IS NULL), due_date, title"
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


def set_task_done(task_id: str, done: bool) -> None:
    with _connect() as conn:
        conn.execute("UPDATE tasks SET done=?, updated_at=? WHERE task_id=?",
                     (1 if done else 0, time.time(), task_id))


def delete_task(task_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM tasks WHERE task_id=?", (task_id,))


# --------------------------------------------------------------------------- #
# Verwaltungsbereich: Stundenplan
# --------------------------------------------------------------------------- #
def upsert_timetable_slot(*, slot_id: Optional[str] = None, subject: str,
                          weekday: int, start_time: str, end_time: str,
                          room: Optional[str] = None, notiz: Optional[str] = None) -> str:
    now = time.time()
    sid = slot_id or uuid.uuid4().hex[:16]
    with _connect() as conn:
        exists = conn.execute(
            "SELECT created_at FROM timetable WHERE slot_id=?", (sid,)).fetchone()
        created = exists["created_at"] if exists else now
        conn.execute(
            "INSERT INTO timetable (slot_id, subject, weekday, start_time, end_time, "
            "room, notiz, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(slot_id) DO UPDATE SET subject=excluded.subject, "
            "weekday=excluded.weekday, start_time=excluded.start_time, "
            "end_time=excluded.end_time, room=excluded.room, notiz=excluded.notiz, "
            "updated_at=excluded.updated_at",
            (sid, subject, int(weekday), start_time, end_time, room, notiz, created, now),
        )
    return sid


def list_timetable(subject: Optional[str] = None) -> list[dict]:
    sql = "SELECT * FROM timetable WHERE 1=1"
    args: list = []
    if subject:
        sql += " AND subject=?"
        args.append(subject)
    sql += " ORDER BY weekday, start_time"
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


def delete_timetable_slot(slot_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM timetable WHERE slot_id=?", (slot_id,))


# --------------------------------------------------------------------------- #
# Verwaltungsbereich: Fach-Farben (Stundenplan-Kacheln)
# --------------------------------------------------------------------------- #
def set_subject_color(subject: str, color: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO subject_colors (subject, color) VALUES (?,?) "
            "ON CONFLICT(subject) DO UPDATE SET color=excluded.color",
            (subject, color),
        )


def subject_colors_map() -> dict:
    with _connect() as conn:
        return {r["subject"]: r["color"]
               for r in conn.execute("SELECT subject, color FROM subject_colors")}


# --------------------------------------------------------------------------- #
# Lernzeit-Tracker (Pomodoro + freier Timer)
# --------------------------------------------------------------------------- #
def log_study_session(*, subject: Optional[str], mode: str, started_at: float,
                      ended_at: float, duration_sec: int,
                      notiz: Optional[str] = None) -> str:
    """Speichert einen ABGESCHLOSSENEN Lernblock. Wird erst beim Beenden
    aufgerufen (siehe Modul-Docstring der Tabelle) - ein laufender Block steht nur
    in st.session_state, nicht in der DB."""
    sid = uuid.uuid4().hex[:16]
    with _connect() as conn:
        conn.execute(
            "INSERT INTO study_sessions (session_id, subject, mode, started_at, "
            "ended_at, duration_sec, notiz) VALUES (?,?,?,?,?,?,?)",
            (sid, subject, mode, started_at, ended_at, int(duration_sec), notiz),
        )
    return sid


def list_study_sessions(subject: Optional[str] = None,
                        since: Optional[float] = None) -> list[dict]:
    sql = "SELECT * FROM study_sessions WHERE 1=1"
    args: list = []
    if subject:
        sql += " AND subject=?"
        args.append(subject)
    if since is not None:
        sql += " AND started_at>=?"
        args.append(since)
    sql += " ORDER BY started_at DESC"
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


def delete_study_session(session_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM study_sessions WHERE session_id=?", (session_id,))


def study_time_by_subject(since: Optional[float] = None) -> dict:
    """Fach -> Summe Lernzeit (Sekunden) seit ``since`` (None = gesamter Verlauf)."""
    sql = "SELECT subject, SUM(duration_sec) AS s FROM study_sessions WHERE 1=1"
    args: list = []
    if since is not None:
        sql += " AND started_at>=?"
        args.append(since)
    sql += " GROUP BY subject"
    with _connect() as conn:
        return {(r["subject"] or "Ohne Fach"): (r["s"] or 0)
               for r in conn.execute(sql, args)}


def study_time_total(since: Optional[float] = None) -> int:
    return sum(study_time_by_subject(since).values())


# --------------------------------------------------------------------------- #
# Lernplan (KI-Gliederung -> realistischer, tagesverteilter Zeitplan)
# --------------------------------------------------------------------------- #
def create_study_plan(*, title: str, subject: Optional[str], doc_ids: list[str],
                      deadline: Optional[str], daily_minutes: int) -> str:
    now = time.time()
    pid = uuid.uuid4().hex[:16]
    with _connect() as conn:
        conn.execute(
            "INSERT INTO study_plans (plan_id, title, subject, doc_ids, deadline, "
            "daily_minutes, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (pid, title.strip(), subject, json.dumps(doc_ids), (deadline or "").strip() or None,
             int(daily_minutes), "draft", now, now),
        )
    return pid


def get_study_plan(plan_id: str) -> Optional[dict]:
    with _connect() as conn:
        r = conn.execute("SELECT * FROM study_plans WHERE plan_id=?", (plan_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    try:
        d["doc_ids"] = json.loads(d.get("doc_ids") or "[]")
    except Exception:  # noqa: BLE001
        d["doc_ids"] = []
    return d


def list_study_plans() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM study_plans ORDER BY created_at DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["doc_ids"] = json.loads(d.get("doc_ids") or "[]")
        except Exception:  # noqa: BLE001
            d["doc_ids"] = []
        out.append(d)
    return out


def update_study_plan(plan_id: str, **fields: Any) -> None:
    """Aktualisiert einzelne Felder (z. B. status, deadline, daily_minutes)."""
    valid = {"title", "subject", "deadline", "daily_minutes", "status"}
    sets = [f"{k}=?" for k in fields if k in valid]
    if not sets:
        return
    args = [fields[k] for k in fields if k in valid] + [time.time(), plan_id]
    with _connect() as conn:
        conn.execute(f"UPDATE study_plans SET {','.join(sets)}, updated_at=? WHERE plan_id=?", args)


def delete_study_plan(plan_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM study_plans WHERE plan_id=?", (plan_id,))
        conn.execute("DELETE FROM study_plan_sections WHERE plan_id=?", (plan_id,))
        conn.execute("DELETE FROM study_plan_blocks WHERE plan_id=?", (plan_id,))


def replace_plan_sections(plan_id: str, sections: list[dict]) -> None:
    """Ersetzt die komplette Gliederung eines Plans (KI-Erstellung oder Bearbeitung
    speichern beides ueber diesen Weg - einfacher als Zeile-fuer-Zeile-Diffing).
    ``sections``: Liste von {title, summary, est_chars, est_minutes, done?}."""
    with _connect() as conn:
        conn.execute("DELETE FROM study_plan_sections WHERE plan_id=?", (plan_id,))
        for i, s in enumerate(sections):
            conn.execute(
                "INSERT INTO study_plan_sections (section_id, plan_id, order_index, "
                "title, summary, est_chars, est_minutes, done) VALUES (?,?,?,?,?,?,?,?)",
                (s.get("section_id") or uuid.uuid4().hex[:16], plan_id, i,
                 (s.get("title") or "").strip(), s.get("summary"),
                 int(s.get("est_chars") or 0), int(s.get("est_minutes") or 0),
                 1 if s.get("done") else 0),
            )
        conn.execute("UPDATE study_plans SET updated_at=? WHERE plan_id=?", (time.time(), plan_id))


def list_plan_sections(plan_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM study_plan_sections WHERE plan_id=? ORDER BY order_index",
            (plan_id,)).fetchall()
        return [dict(r) for r in rows]


def set_section_done(section_id: str, done: bool) -> None:
    with _connect() as conn:
        conn.execute("UPDATE study_plan_sections SET done=? WHERE section_id=?",
                     (1 if done else 0, section_id))


def replace_plan_blocks(plan_id: str, blocks: list[dict]) -> None:
    """Ersetzt den kompletten Tages-Zeitplan eines Plans (Neuberechnung).
    ``blocks``: Liste von {section_id, planned_date, planned_min}."""
    with _connect() as conn:
        conn.execute("DELETE FROM study_plan_blocks WHERE plan_id=?", (plan_id,))
        for b in blocks:
            conn.execute(
                "INSERT INTO study_plan_blocks (block_id, plan_id, section_id, "
                "planned_date, planned_min, done) VALUES (?,?,?,?,?,0)",
                (uuid.uuid4().hex[:16], plan_id, b.get("section_id"),
                 b["planned_date"], int(b["planned_min"])),
            )
        conn.execute("UPDATE study_plans SET updated_at=? WHERE plan_id=?", (time.time(), plan_id))


def list_plan_blocks(plan_id: Optional[str] = None, date: Optional[str] = None) -> list[dict]:
    sql = "SELECT * FROM study_plan_blocks WHERE 1=1"
    args: list = []
    if plan_id:
        sql += " AND plan_id=?"
        args.append(plan_id)
    if date:
        sql += " AND planned_date=?"
        args.append(date)
    sql += " ORDER BY planned_date"
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


def set_block_done(block_id: str, done: bool, via: Optional[str] = None) -> None:
    """``via``: 'pomodoro' (aus einer echten, abgeschlossenen Zeitmessung) oder
    'manual' (Haekchen ohne Zeittracking - z. B. Programmieraufgaben, die sich
    nicht sinnvoll per Pomodoro tracken lassen). None beim Zuruecksetzen."""
    with _connect() as conn:
        conn.execute("UPDATE study_plan_blocks SET done=?, done_via=? WHERE block_id=?",
                     (1 if done else 0, via if done else None, block_id))


def get_plan_block(block_id: str) -> Optional[dict]:
    with _connect() as conn:
        r = conn.execute("SELECT * FROM study_plan_blocks WHERE block_id=?", (block_id,)).fetchone()
        return dict(r) if r else None


def add_block_actual_min(block_id: str, minutes: int) -> None:
    """Addiert ECHTE (per Pomodoro gemessene) Minuten auf einen Lernplan-Block -
    unabhaengig davon, ob der Block dadurch schon fertig ist (siehe Lernzeit-Seite:
    ein Block kann mehrere Arbeitsphasen brauchen, auch abgebrochene zaehlen die
    tatsaechlich investierte Zeit). Grundlage von ``time_calibration``."""
    minutes = int(minutes)
    if minutes <= 0:
        return
    with _connect() as conn:
        conn.execute(
            "UPDATE study_plan_blocks SET actual_min = COALESCE(actual_min,0) + ? "
            "WHERE block_id=?", (minutes, block_id))


def time_calibration(subject: Optional[str] = None, min_samples: int = 5) -> Optional[float]:
    """Faktor 'echte Minuten / geplante Minuten' aus ECHTEN Pomodoro-Messungen an
    ERLEDIGTEN Lernplan-Bloecken. ``None``, wenn (noch) zu wenige brauchbare
    Messungen vorliegen - dann greift der statische PLAN_TIME_FACTOR aus
    config.py (siehe study_plan.py:time_factor_info). Einzelne Ausreisser (z. B.
    ein vergessener, weiterlaufender Timer) werden verworfen; das Ergebnis bleibt
    auf ein plausibles Band [0.4, 4.0] begrenzt, damit ein einzelner kaputter
    Messwert die Schaetzung nicht verzerrt. Nur ERLEDIGTE Bloecke (``done=1``)
    zaehlen - ein noch offener Block (z. B. nach einer abgebrochenen ersten
    Pomodoro-Runde) hat erst EINEN TEIL seiner Zeit gemeldet; ihn schon jetzt
    einzurechnen wuerde die tatsaechliche Dauer systematisch unterschaetzen."""
    sql = ("SELECT b.planned_min AS planned, b.actual_min AS actual "
           "FROM study_plan_blocks b JOIN study_plans p ON p.plan_id=b.plan_id "
           "WHERE b.done=1 AND b.actual_min IS NOT NULL AND b.planned_min>0")
    args: list = []
    if subject:
        sql += " AND p.subject=?"
        args.append(subject)
    with _connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    usable = [(r["planned"], r["actual"]) for r in rows
             if r["actual"] and 0 < r["actual"] <= r["planned"] * 8]
    if len(usable) < max(1, min_samples):
        return None
    planned_sum = sum(p for p, _ in usable)
    actual_sum = sum(a for _, a in usable)
    if planned_sum <= 0:
        return None
    return max(0.4, min(4.0, actual_sum / planned_sum))


def plan_time_totals(subject: Optional[str] = None) -> dict:
    """Aggregiert ERLEDIGTE Lernplan-Bloecke: geplante vs. tatsaechlich (per
    Pomodoro) gemessene Minuten - Grundlage der Anzeige 'Plan vs. Realitaet'
    (Seite Fortschritt). Getrennt nach Bloecken MIT echter Zeitmessung (fliessen
    in ``time_calibration`` ein) und ohne (manuell abgehakt, z. B. Programmier-
    aufgaben ohne Timer)."""
    sql = ("SELECT b.planned_min AS planned, b.actual_min AS actual "
           "FROM study_plan_blocks b JOIN study_plans p ON p.plan_id=b.plan_id "
           "WHERE b.done=1")
    args: list = []
    if subject:
        sql += " AND p.subject=?"
        args.append(subject)
    with _connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    measured = [r for r in rows if r["actual"] is not None]
    return {
        "planned_total": sum(r["planned"] for r in rows),
        "measured_blocks": len(measured),
        "manual_blocks": len(rows) - len(measured),
        "planned_for_measured": sum(r["planned"] for r in measured),
        "actual_for_measured": sum(r["actual"] for r in measured),
    }


def list_plan_blocks_detailed(plan_id: Optional[str] = None,
                              date: Optional[str] = None) -> list[dict]:
    """Wie ``list_plan_blocks``, aber mit Plan-Titel/-Fach und Abschnitts-Titel
    angereichert (JOIN) - fuer Uebersichten ueber MEHRERE Plaene hinweg (z. B. das
    Wochen-Dashboard "heute faellige Lernplan-Bloecke", planübergreifend)."""
    sql = (
        "SELECT b.*, p.title AS plan_title, p.subject AS plan_subject, "
        "p.status AS plan_status, s.title AS section_title "
        "FROM study_plan_blocks b "
        "JOIN study_plans p ON p.plan_id = b.plan_id "
        "LEFT JOIN study_plan_sections s ON s.section_id = b.section_id "
        "WHERE 1=1"
    )
    args: list = []
    if plan_id:
        sql += " AND b.plan_id=?"
        args.append(plan_id)
    if date:
        sql += " AND b.planned_date=?"
        args.append(date)
    sql += " ORDER BY b.planned_date"
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


def sync_plan_status(plan_id: str) -> str:
    """Nach JEDER Block-Status-Aenderung aufrufen: setzt einen Plan automatisch auf
    'done', sobald ALLE seine Bloecke erledigt sind, bzw. zurueck auf 'active',
    wenn nicht mehr alle erledigt sind (z. B. nach Zuruecksetzen eines Hakens).
    Ein Plan im Entwurf ('draft', noch keine Bloecke berechnet) oder ganz ohne
    Bloecke bleibt unangetastet. Gibt den (ggf. neuen) Status zurueck."""
    plan = get_study_plan(plan_id)
    if not plan or plan["status"] == "draft":
        return plan["status"] if plan else ""
    blocks = list_plan_blocks(plan_id)
    if not blocks:
        return plan["status"]
    new_status = "done" if all(b["done"] for b in blocks) else "active"
    if new_status != plan["status"]:
        update_study_plan(plan_id, status=new_status)
    return new_status


# --------------------------------------------------------------------------- #
# Lernplan: selbstlernende Wartezeit-Schaetzung (echte Messwerte je Modell)
# --------------------------------------------------------------------------- #
def log_eta_sample(model: str, chars: int, seconds: float) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO plan_eta_samples (sample_id, model, chars, seconds, created_at) "
            "VALUES (?,?,?,?,?)",
            (uuid.uuid4().hex[:16], model, int(chars), float(seconds), time.time()))


def eta_calibration(model: str, min_samples: int = 3, limit: int = 20) -> Optional[float]:
    """Durchschnittliche Sekunden PRO 1000 Zeichen aus den letzten ``limit``
    echten Messungen fuer ``model``. ``None``, wenn (noch) zu wenige Messwerte da
    sind (dann greift in der UI die statische Formel aus config.py)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT chars, seconds FROM plan_eta_samples WHERE model=? "
            "ORDER BY created_at DESC LIMIT ?", (model, int(limit))).fetchall()
    usable = [(r["chars"], r["seconds"]) for r in rows if r["chars"] and r["chars"] > 0]
    if len(usable) < max(1, min_samples):
        return None
    rates = [sec / chars * 1000.0 for chars, sec in usable]
    return sum(rates) / len(rates)


def log_token_sample(model: str, chars: int, tokens: int) -> None:
    """Speichert einen echten Zeichen/Token-Messwert (aus Ollamas
    ``prompt_eval_count``) fuer ein Modell - Grundlage der selbstlernenden
    Zeichen-Budget-Kalibrierung (siehe ``chars_per_token``)."""
    if not tokens or tokens <= 0 or not chars or chars <= 0:
        return
    with _connect() as conn:
        conn.execute(
            "INSERT INTO llm_token_samples (sample_id, model, chars, tokens, created_at) "
            "VALUES (?,?,?,?,?)",
            (uuid.uuid4().hex[:16], model, int(chars), int(tokens), time.time()))


def chars_per_token(model: str, min_samples: int = 5, limit: int = 40) -> Optional[float]:
    """Durchschnittliches Zeichen/Token-Verhaeltnis aus den letzten ``limit``
    echten Messungen fuer ``model``. ``None``, wenn (noch) zu wenige Messwerte
    vorliegen (dann greift eine statische Schaetzung, siehe config.py)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT chars, tokens FROM llm_token_samples WHERE model=? "
            "ORDER BY created_at DESC LIMIT ?", (model, int(limit))).fetchall()
    usable = [(r["chars"], r["tokens"]) for r in rows if r["tokens"] and r["tokens"] > 0]
    if len(usable) < max(1, min_samples):
        return None
    ratios = [chars / tokens for chars, tokens in usable]
    return sum(ratios) / len(ratios)


# --------------------------------------------------------------------------- #
# Fortschritt: taeglicher Schnappschuss fuer die Trend-Sparklines auf der
# Seite "Fortschritt" (siehe analytics.py-Kommentar oben bei progress_snapshots)
# --------------------------------------------------------------------------- #
def upsert_progress_snapshot(day: str, subject: str, readiness_pct: int, mastery_pct: int) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO progress_snapshots (day, subject, readiness_pct, mastery_pct, created_at) "
            "VALUES (?,?,?,?,?) "
            "ON CONFLICT(day, subject) DO UPDATE SET "
            "readiness_pct=excluded.readiness_pct, mastery_pct=excluded.mastery_pct, "
            "created_at=excluded.created_at",
            (day, subject, int(readiness_pct), int(mastery_pct), time.time()))


def list_progress_snapshots(subject: str, days: int = 14) -> list[dict]:
    """Die letzten ``days`` Tages-Schnappschuesse fuer ein Fach (oder '_all_'),
    aeltester zuerst (passend fuer eine Sparkline/einen Verlaufs-Chart)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT day, readiness_pct, mastery_pct FROM progress_snapshots "
            "WHERE subject=? ORDER BY day DESC LIMIT ?",
            (subject, int(days))).fetchall()
    return [dict(r) for r in rows][::-1]


def exam_map() -> dict:
    """Fach -> exam-Datensatz (dict), fuer schnelle Nachschlage in Planer/Analytik."""
    return {e["subject"]: e for e in list_exams()}


def delete_exam(subject: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM exams WHERE subject=?", (subject,))


# --------------------------------------------------------------------------- #
# Freie Notizen (eigene Gedanken - im Unterschied zu allen KI-generierten
# Inhalten der App bewusst NICHT im RAG-Index, siehe Schema-Kommentar)
# --------------------------------------------------------------------------- #
def create_note(*, subject: Optional[str] = None, doc_id: Optional[str] = None,
                topic: Optional[str] = None, collection: Optional[str] = None,
                title: str = "", body: str, pinned: bool = False) -> str:
    now = time.time()
    nid = uuid.uuid4().hex[:16]
    with _connect() as conn:
        conn.execute(
            "INSERT INTO notes (note_id, subject, doc_id, topic, collection, title, "
            "body, pinned, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (nid, subject, doc_id, topic, collection, (title or "").strip(),
             body, 1 if pinned else 0, now, now),
        )
    return nid


def update_note(note_id: str, **fields: Any) -> None:
    """Aktualisiert nur die uebergebenen Felder (z. B. nur ``body`` beim Speichern
    im Editor, oder nur ``pinned`` beim Anheften) - wie ``update_study_plan``."""
    valid = {"subject", "doc_id", "topic", "collection", "title", "body", "pinned"}
    sets = [f"{k}=?" for k in fields if k in valid]
    if not sets:
        return
    args = [(1 if fields[k] else 0) if k == "pinned" else fields[k]
           for k in fields if k in valid]
    args += [time.time(), note_id]
    with _connect() as conn:
        conn.execute(f"UPDATE notes SET {','.join(sets)}, updated_at=? WHERE note_id=?", args)


def get_note(note_id: str) -> Optional[dict]:
    with _connect() as conn:
        r = conn.execute("SELECT * FROM notes WHERE note_id=?", (note_id,)).fetchone()
        return dict(r) if r else None


def list_notes(subject: Optional[str] = None, doc_id: Optional[str] = None,
               topic: Optional[str] = None, collection: Optional[str] = None,
               search: Optional[str] = None, pinned_only: bool = False,
               limit: Optional[int] = None, offset: int = 0) -> list[dict]:
    sql = "SELECT * FROM notes WHERE 1=1"
    args: list = []
    if subject:
        sql += " AND subject=?"; args.append(subject)
    if doc_id:
        sql += " AND doc_id=?"; args.append(doc_id)
    if topic:
        sql += " AND topic=?"; args.append(topic)
    if collection is not None:
        if collection == "__none__":
            sql += " AND (collection IS NULL OR collection='')"
        else:
            sql += " AND collection=?"; args.append(collection)
    if pinned_only:
        sql += " AND pinned=1"
    if search and search.strip():
        q = f"%{search.strip()}%"
        sql += " AND (title LIKE ? OR body LIKE ?)"
        args += [q, q]
    sql += " ORDER BY pinned DESC, updated_at DESC"
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"; args += [int(limit), int(offset)]
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


def count_notes(subject: Optional[str] = None, collection: Optional[str] = None,
               search: Optional[str] = None) -> int:
    sql = "SELECT COUNT(*) AS c FROM notes WHERE 1=1"
    args: list = []
    if subject:
        sql += " AND subject=?"; args.append(subject)
    if collection is not None:
        if collection == "__none__":
            sql += " AND (collection IS NULL OR collection='')"
        else:
            sql += " AND collection=?"; args.append(collection)
    if search and search.strip():
        q = f"%{search.strip()}%"
        sql += " AND (title LIKE ? OR body LIKE ?)"
        args += [q, q]
    with _connect() as conn:
        return int(conn.execute(sql, args).fetchone()["c"])


def delete_note(note_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM notes WHERE note_id=?", (note_id,))


def list_collections(subject: Optional[str] = None) -> list[str]:
    """Alle vorhandenen Sammlungs-Namen (optional nur eines Fachs) - wie ``list_decks``."""
    sql = "SELECT DISTINCT collection FROM notes WHERE collection IS NOT NULL AND collection<>''"
    args: list = []
    if subject:
        sql += " AND subject=?"; args.append(subject)
    sql += " ORDER BY collection"
    with _connect() as conn:
        return [r["collection"] for r in conn.execute(sql, args)]


# --------------------------------------------------------------------------- #
# Uebungsaufgaben (siehe _SCHEMA-Kommentar oben zur Abgrenzung von review_items)
# --------------------------------------------------------------------------- #

def _decode_practice_problem(row: dict) -> dict:
    d = dict(row)
    for col, key in (("given_json", "given"), ("steps_json", "steps"),
                     ("hints_json", "hints")):
        try:
            d[key] = json.loads(d.get(col) or "[]")
        except Exception:  # noqa: BLE001
            d[key] = []
    return d


def create_practice_problem(*, subject: Optional[str] = None, doc_id: Optional[str] = None,
                            topic: Optional[str] = None, kind: str = "scenario",
                            problem_text: str, given: Optional[list] = None,
                            steps: list, final_answer: Optional[str] = None,
                            hints: Optional[list] = None,
                            source_excerpt: Optional[str] = None,
                            model: Optional[str] = None) -> str:
    now = time.time()
    pid = uuid.uuid4().hex[:16]
    with _connect() as conn:
        conn.execute(
            "INSERT INTO practice_problems (problem_id, subject, doc_id, topic, kind, "
            "problem_text, given_json, steps_json, final_answer, hints_json, "
            "source_excerpt, model, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, subject, doc_id, topic, kind, problem_text.strip(),
             json.dumps(given or []), json.dumps(steps),
             (final_answer or "").strip() or None, json.dumps(hints or []),
             source_excerpt, model, now),
        )
    return pid


def get_practice_problem(problem_id: str) -> Optional[dict]:
    with _connect() as conn:
        r = conn.execute(
            "SELECT * FROM practice_problems WHERE problem_id=?", (problem_id,)).fetchone()
    return _decode_practice_problem(r) if r else None


def list_practice_problems(subject: Optional[str] = None, doc_id: Optional[str] = None,
                           topic: Optional[str] = None, kind: Optional[str] = None,
                           limit: Optional[int] = None, offset: int = 0) -> list[dict]:
    sql = "SELECT * FROM practice_problems WHERE 1=1"
    args: list = []
    if subject:
        sql += " AND subject=?"; args.append(subject)
    if doc_id:
        sql += " AND doc_id=?"; args.append(doc_id)
    if topic:
        sql += " AND topic=?"; args.append(topic)
    if kind:
        sql += " AND kind=?"; args.append(kind)
    sql += " ORDER BY created_at DESC"
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"; args += [int(limit), int(offset)]
    with _connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [_decode_practice_problem(r) for r in rows]


def count_practice_problems(subject: Optional[str] = None, doc_id: Optional[str] = None,
                            topic: Optional[str] = None, kind: Optional[str] = None) -> int:
    sql = "SELECT COUNT(*) AS n FROM practice_problems WHERE 1=1"
    args: list = []
    if subject:
        sql += " AND subject=?"; args.append(subject)
    if doc_id:
        sql += " AND doc_id=?"; args.append(doc_id)
    if topic:
        sql += " AND topic=?"; args.append(topic)
    if kind:
        sql += " AND kind=?"; args.append(kind)
    with _connect() as conn:
        return int(conn.execute(sql, args).fetchone()["n"])


def delete_practice_problem(problem_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM practice_problems WHERE problem_id=?", (problem_id,))
        conn.execute("DELETE FROM practice_attempts WHERE problem_id=?", (problem_id,))


def log_practice_attempt(problem_id: str, *, self_rating: int,
                         notiz: Optional[str] = None) -> str:
    aid = uuid.uuid4().hex[:16]
    with _connect() as conn:
        conn.execute(
            "INSERT INTO practice_attempts (attempt_id, problem_id, attempted_at, "
            "self_rating, notiz) VALUES (?,?,?,?,?)",
            (aid, problem_id, time.time(), int(self_rating), notiz),
        )
    return aid


def list_practice_attempts(problem_id: Optional[str] = None,
                           limit: Optional[int] = None, offset: int = 0) -> list[dict]:
    sql = "SELECT * FROM practice_attempts WHERE 1=1"
    args: list = []
    if problem_id:
        sql += " AND problem_id=?"; args.append(problem_id)
    sql += " ORDER BY attempted_at DESC"
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"; args += [int(limit), int(offset)]
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


# --------------------------------------------------------------------------- #
# Mindmaps (siehe _SCHEMA-Kommentar oben)
# --------------------------------------------------------------------------- #

def create_mindmap(*, title: str, subject: Optional[str], doc_ids: list[str],
                   graph: dict, model: Optional[str] = None) -> str:
    now = time.time()
    mid = uuid.uuid4().hex[:16]
    with _connect() as conn:
        conn.execute(
            "INSERT INTO mindmaps (mindmap_id, title, subject, doc_ids, graph_json, "
            "model, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (mid, title.strip(), subject, json.dumps(doc_ids), json.dumps(graph),
             model, now, now),
        )
    return mid


def _decode_mindmap(row: dict) -> dict:
    d = dict(row)
    try:
        d["doc_ids"] = json.loads(d.get("doc_ids") or "[]")
    except Exception:  # noqa: BLE001
        d["doc_ids"] = []
    try:
        d["graph"] = json.loads(d.get("graph_json") or "{}")
    except Exception:  # noqa: BLE001
        d["graph"] = {}
    return d


def get_mindmap(mindmap_id: str) -> Optional[dict]:
    with _connect() as conn:
        r = conn.execute(
            "SELECT * FROM mindmaps WHERE mindmap_id=?", (mindmap_id,)).fetchone()
    return _decode_mindmap(r) if r else None


def list_mindmaps(subject: Optional[str] = None) -> list[dict]:
    sql = "SELECT * FROM mindmaps WHERE 1=1"
    args: list = []
    if subject:
        sql += " AND subject=?"; args.append(subject)
    sql += " ORDER BY created_at DESC"
    with _connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [_decode_mindmap(r) for r in rows]


def update_mindmap(mindmap_id: str, **fields: Any) -> None:
    """Aktualisiert einzelne Felder (z. B. ``title`` oder eine neu erzeugte
    ``graph``/``model`` nach 'Neu generieren')."""
    valid = {"title", "graph", "model"}
    sets = []
    args = []
    for k in fields:
        if k not in valid:
            continue
        sets.append(f"{'graph_json' if k == 'graph' else k}=?")
        args.append(json.dumps(fields[k]) if k == "graph" else fields[k])
    if not sets:
        return
    args += [time.time(), mindmap_id]
    with _connect() as conn:
        conn.execute(f"UPDATE mindmaps SET {','.join(sets)}, updated_at=? WHERE mindmap_id=?", args)


def delete_mindmap(mindmap_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM mindmaps WHERE mindmap_id=?", (mindmap_id,))


# --------------------------------------------------------------------------- #
# Audio-Overviews (siehe _SCHEMA-Kommentar oben) - gleiches Muster wie Mindmaps,
# zusaetzlich mit einer Datei auf der Platte (Audio gehoert nicht in SQLite).
# --------------------------------------------------------------------------- #

def create_audio_overview(*, title: str, subject: Optional[str], doc_ids: list[str],
                          script_text: str, audio_path: str,
                          model: Optional[str] = None, overview_id: Optional[str] = None) -> str:
    """``overview_id`` optional vorgeben, damit die WAV-Datei VOR dem DB-Insert
    schon unter der endgueltigen ID abgelegt werden kann (audio_overview.py -
    sonst muesste die Datei nach dem Insert umbenannt werden, um zum
    autogenerierten Schluessel zu passen)."""
    now = time.time()
    oid = overview_id or uuid.uuid4().hex[:16]
    with _connect() as conn:
        conn.execute(
            "INSERT INTO audio_overviews (overview_id, title, subject, doc_ids, "
            "script_text, audio_path, model, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (oid, title.strip(), subject, json.dumps(doc_ids), script_text,
             audio_path, model, now, now),
        )
    return oid


def _decode_audio_overview(row: dict) -> dict:
    d = dict(row)
    try:
        d["doc_ids"] = json.loads(d.get("doc_ids") or "[]")
    except Exception:  # noqa: BLE001
        d["doc_ids"] = []
    return d


def get_audio_overview(overview_id: str) -> Optional[dict]:
    with _connect() as conn:
        r = conn.execute(
            "SELECT * FROM audio_overviews WHERE overview_id=?", (overview_id,)).fetchone()
    return _decode_audio_overview(r) if r else None


def update_audio_overview(overview_id: str, **fields: Any) -> None:
    """Aktualisiert einzelne Felder (z. B. ``script_text``/``model`` nach
    'Neu generieren') - gleiches Muster wie ``update_mindmap``. Bewusst KEIN
    ``create_audio_overview`` mit vorhandener ``overview_id`` fuer diesen
    Zweck: das waere ein reines ``INSERT`` und wuerde an der PRIMARY-KEY-
    Kollision scheitern statt die Zeile zu aktualisieren."""
    valid = {"title", "subject", "doc_ids", "script_text", "audio_path", "model"}
    sets = []
    args = []
    for k in fields:
        if k not in valid:
            continue
        sets.append(f"{k}=?")
        args.append(json.dumps(fields[k]) if k == "doc_ids" else fields[k])
    if not sets:
        return
    args += [time.time(), overview_id]
    with _connect() as conn:
        conn.execute(f"UPDATE audio_overviews SET {','.join(sets)}, updated_at=? "
                    "WHERE overview_id=?", args)


def list_audio_overviews(subject: Optional[str] = None) -> list[dict]:
    sql = "SELECT * FROM audio_overviews WHERE 1=1"
    args: list = []
    if subject:
        sql += " AND subject=?"; args.append(subject)
    sql += " ORDER BY created_at DESC"
    with _connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [_decode_audio_overview(r) for r in rows]


def delete_audio_overview(overview_id: str) -> None:
    """Loescht den DB-Eintrag UND die zugehoerige WAV-Datei (anders als bei
    Mindmaps, wo alles in der DB liegt - Audio ist eine echte Datei unter
    AUDIO_DIR, die sonst verwaist zurueckbliebe)."""
    row = get_audio_overview(overview_id)
    with _connect() as conn:
        conn.execute("DELETE FROM audio_overviews WHERE overview_id=?", (overview_id,))
    if row and row.get("audio_path"):
        from ragapp.config import AUDIO_DIR
        p = AUDIO_DIR / row["audio_path"]
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass


# --------------------------------------------------------------------------- #
# Dauerhaft gemerkte Ausspracheregeln (siehe _SCHEMA-Kommentar oben) - einfache
# Wort-fuer-Wort-Tabelle statt eines eigenen ID-Schemas wie bei Mindmaps/Audio-
# Overviews, weil ``word`` selbst der natuerliche, eindeutige Schluessel ist.
# --------------------------------------------------------------------------- #

def upsert_pronunciation_fix(word: str, replacement: str) -> None:
    """Legt eine Ausspracheregel an oder aktualisiert sie (gleiches Wort ->
    neue Ersetzung ueberschreibt die alte, kein Duplikat)."""
    now = time.time()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO pronunciation_fixes (word, replacement, created_at, updated_at) "
            "VALUES (?,?,?,?) "
            "ON CONFLICT(word) DO UPDATE SET replacement=excluded.replacement, "
            "updated_at=excluded.updated_at",
            (word, replacement, now, now),
        )


def list_pronunciation_fixes() -> dict[str, str]:
    """``{original_wort: ausgesprochene_ersetzung}`` - fuer den schnellen
    Nachschlage-Zugriff aus ``audio_overview._apply_pronunciation_fixes``."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT word, replacement FROM pronunciation_fixes ORDER BY word").fetchall()
    return {r["word"]: r["replacement"] for r in rows}


def delete_pronunciation_fix(word: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM pronunciation_fixes WHERE word=?", (word,))


# Ro7: KEINE Initialisierung mehr als Import-Nebenwirkung. Schema/Migrationen
# laufen ueber _ensure_initialized() beim ersten DB-Zugriff (idempotent, mit
# Logging). init_db() bleibt oeffentlich (z. B. fuer explizite CLI-Nutzung).
