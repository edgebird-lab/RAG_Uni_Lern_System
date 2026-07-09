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

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from ragapp.config import MANIFEST_DB

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

-- Lern-Layer: Karteikarten + Spaced Repetition (SM-2). Rein additiv - die Karten
-- werden aus dem schon indexierten Fragenmaterial (kind='exam_qa' / type='question')
-- geerntet; hier wird nur der LERNFORTSCHRITT gefuehrt.
CREATE TABLE IF NOT EXISTS review_items (
    card_id     TEXT PRIMARY KEY,   -- stabile ID (= Chroma-ID der Quelle)
    source      TEXT,               -- 'exam_qa' | 'question'
    chroma_id   TEXT,
    subject     TEXT,
    topic       TEXT,               -- Abschnitt/Thema (location/header_path)
    front       TEXT NOT NULL,      -- Frage (Vorderseite)
    back        TEXT NOT NULL,      -- Antwort/Erklaerung (Rueckseite)
    doc_id      TEXT,
    -- SM-2-Zustand
    ease        REAL    DEFAULT 2.5,
    interval    INTEGER DEFAULT 0,  -- Tage bis zur naechsten Faelligkeit
    reps        INTEGER DEFAULT 0,  -- Anzahl korrekter Wiederholungen in Folge
    lapses      INTEGER DEFAULT 0,
    due         REAL,               -- naechster Faelligkeits-Zeitpunkt (epoch)
    last_review REAL,
    created_at  REAL,
    suspended   INTEGER DEFAULT 0
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
    ease_after     REAL
);
CREATE INDEX IF NOT EXISTS idx_reviewlog_card ON review_log(card_id);
CREATE INDEX IF NOT EXISTS idx_reviewlog_subject ON review_log(subject);
"""


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
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
) -> None:
    now = time.time()
    with _connect() as conn:
        exists = conn.execute(
            "SELECT ingested_at FROM documents WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        ingested_at = exists["ingested_at"] if exists else now
        conn.execute(
            """
            INSERT INTO documents
                (doc_id, content_hash, source_path, filename, subject, filetype,
                 num_chunks, num_questions, char_count, status, ingested_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
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
                updated_at=excluded.updated_at
            """,
            (doc_id, content_hash, source_path, filename, subject, filetype,
             num_chunks, num_questions, char_count, status, ingested_at, now),
        )


def delete_document(doc_id: str) -> None:
    """Entfernt Dokument + zugehörige Chunk-Hashes aus dem Manifest."""
    with _connect() as conn:
        conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
        conn.execute("DELETE FROM chunk_hashes WHERE doc_id = ?", (doc_id,))


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
    """Legt neue Karteikarten an (bewahrt bei bereits vorhandenen den SM-2-Fortschritt;
    aktualisiert nur Inhalt/Metadaten). Gibt die Anzahl NEUER Karten zurueck."""
    if not cards:
        return 0
    now = time.time()
    with _connect() as conn:
        existing = {r["card_id"] for r in conn.execute("SELECT card_id FROM review_items")}
        neu = 0
        for c in cards:
            cid = c["card_id"]
            if cid in existing:
                conn.execute(
                    "UPDATE review_items SET source=?, chroma_id=?, subject=?, topic=?, "
                    "front=?, back=?, doc_id=? WHERE card_id=?",
                    (c.get("source"), c.get("chroma_id"), c.get("subject"), c.get("topic"),
                     c["front"], c["back"], c.get("doc_id"), cid),
                )
            else:
                conn.execute(
                    "INSERT INTO review_items (card_id, source, chroma_id, subject, topic, "
                    "front, back, doc_id, ease, interval, reps, lapses, due, created_at, "
                    "suspended) VALUES (?,?,?,?,?,?,?,?,2.5,0,0,0,?,?,0)",
                    (cid, c.get("source"), c.get("chroma_id"), c.get("subject"), c.get("topic"),
                     c["front"], c["back"], c.get("doc_id"), now, now),
                )
                neu += 1
        return neu


def review_counts(subject: Optional[str] = None) -> dict:
    """Zaehlt Karten: gesamt / faellig / neu (nie geuebt) / gelernt (schon geuebt)."""
    now = time.time()
    where = "WHERE suspended=0" + (" AND subject=?" if subject else "")
    args = [subject] if subject else []
    with _connect() as conn:
        def one(extra, a):
            return conn.execute(f"SELECT COUNT(*) AS c FROM review_items {where}{extra}",
                                args + a).fetchone()["c"]
        return {
            "total": one("", []),
            "due": one(" AND due<=?", [now]),
            "neu": one(" AND reps=0", []),
            "gelernt": one(" AND reps>0", []),
        }


def get_due_cards(subject: Optional[str] = None, limit: int = 20,
                  now: Optional[float] = None) -> list[dict]:
    """Faellige Karten (Wiederholungen zuerst, dann neue), aufsteigend nach Faelligkeit."""
    now = now if now is not None else time.time()
    q = "SELECT * FROM review_items WHERE suspended=0 AND due<=? "
    args: list = [now]
    if subject:
        q += "AND subject=? "
        args.append(subject)
    q += "ORDER BY CASE WHEN reps>0 THEN 0 ELSE 1 END, due ASC LIMIT ?"
    args.append(int(limit))
    with _connect() as conn:
        return [dict(r) for r in conn.execute(q, args).fetchall()]


def record_review(card_id: str, rating: int, *, ease: float, interval: int, reps: int,
                  lapses: int, due: float, subject: Optional[str] = None,
                  topic: Optional[str] = None) -> None:
    """Schreibt den neuen SM-2-Zustand einer Karte + einen Eintrag ins Lern-Log."""
    now = time.time()
    with _connect() as conn:
        conn.execute(
            "UPDATE review_items SET ease=?, interval=?, reps=?, lapses=?, due=?, "
            "last_review=? WHERE card_id=?",
            (ease, interval, reps, lapses, due, now, card_id),
        )
        conn.execute(
            "INSERT INTO review_log (card_id, subject, topic, rating, reviewed_at, "
            "interval_after, ease_after) VALUES (?,?,?,?,?,?,?)",
            (card_id, subject, topic, rating, now, interval, ease),
        )


def study_subjects() -> list[str]:
    """Faecher, zu denen es Karten gibt."""
    with _connect() as conn:
        return [r["subject"] for r in conn.execute(
            "SELECT DISTINCT subject FROM review_items WHERE subject IS NOT NULL "
            "AND suspended=0 ORDER BY subject")]


def delete_cards(subject: Optional[str] = None) -> None:
    """Karten (+ deren Log) loeschen - alle oder nur ein Fach."""
    with _connect() as conn:
        if subject:
            conn.execute("DELETE FROM review_items WHERE subject=?", (subject,))
            conn.execute("DELETE FROM review_log WHERE subject=?", (subject,))
        else:
            conn.execute("DELETE FROM review_items")
            conn.execute("DELETE FROM review_log")


# Initialisierung beim Import
init_db()
