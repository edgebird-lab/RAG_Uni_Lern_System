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
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

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
    suspended   INTEGER DEFAULT 0,
    deck        TEXT,               -- optionaler Stapel/Themenstapel (frei benannt)
    answer      TEXT,               -- KI-generierte Antwort (statt rohem Chunk); leer = Chunk zeigen
    use_flashcard INTEGER DEFAULT 1,-- Karte fuer die Abfrage (Lernrunde) nutzen?
    use_embedding INTEGER DEFAULT 1,-- zugehoerige Frage im Vektorindex (Suche) halten?
    edited        INTEGER DEFAULT 0 -- 1 = manuell bearbeitet -> Ernte ueberschreibt nicht mehr
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
    ease_after     REAL,
    confidence     TEXT,            -- 'sicher'|'mittel'|'unsicher' (JOL vor dem Aufdecken)
    device_id      TEXT,            -- Geraet, das die Wiederholung erzeugt hat (Sync)
    event_uid      TEXT,            -- global eindeutige Ereignis-ID (idempotenter Import)
    due_after      REAL             -- absolute Faelligkeit nach dieser Wiederholung (exakter Replay)
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
    created_at  REAL,
    updated_at  REAL
);
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
                             ("due_after", "ALTER TABLE review_log ADD COLUMN due_after REAL")):
                if _c not in rlcols:
                    conn.execute(_ddl)
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_reviewlog_uid ON review_log(event_uid)")
        except Exception:  # noqa: BLE001
            _log.warning("Additive Migration review_log uebersprungen", exc_info=True)
        # Additive Migration fuer documents: Zaehler unvollstaendig gelesener OCR-Seiten (F2).
        try:
            dcols = {r["name"] for r in conn.execute("PRAGMA table_info(documents)")}
            if "ocr_partial_pages" not in dcols:
                conn.execute("ALTER TABLE documents ADD COLUMN ocr_partial_pages INTEGER DEFAULT 0")
        except Exception:  # noqa: BLE001
            _log.warning("Additive Migration documents uebersprungen", exc_info=True)


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
                 num_chunks, num_questions, char_count, status, ocr_partial_pages,
                 ingested_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                updated_at=excluded.updated_at
            """,
            (doc_id, content_hash, source_path, filename, subject, filetype,
             num_chunks, num_questions, char_count, status, int(ocr_partial_pages or 0),
             ingested_at, now),
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
    """Legt neue Karteikarten an (bewahrt bei bereits vorhandenen den SM-2-Fortschritt;
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


def record_review(card_id: str, rating: int, *, ease: float, interval: int, reps: int,
                  lapses: int, due: float, subject: Optional[str] = None,
                  topic: Optional[str] = None, confidence: Optional[str] = None) -> None:
    """Schreibt den neuen SM-2-Zustand einer Karte + einen Eintrag ins Lern-Log
    (inkl. optionaler Konfidenz/JOL vor dem Aufdecken)."""
    now = time.time()
    with _connect() as conn:
        conn.execute(
            "UPDATE review_items SET ease=?, interval=?, reps=?, lapses=?, due=?, "
            "last_review=? WHERE card_id=?",
            (ease, interval, reps, lapses, due, now, card_id),
        )
        conn.execute(
            "INSERT INTO review_log (card_id, subject, topic, rating, reviewed_at, "
            "interval_after, ease_after, confidence, device_id, event_uid, due_after) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (card_id, subject, topic, rating, now, interval, ease, confidence,
             _device_id(), uuid.uuid4().hex, due),
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
# Stapel (Decks): Karten frei benannten Themenstapeln zuordnen
# --------------------------------------------------------------------------- #
def assign_deck(deck: Optional[str], *, doc_ids: Optional[list[str]] = None,
                subjects: Optional[list[str]] = None, card_ids: Optional[list[str]] = None) -> int:
    """Ordnet Karten einem Stapel zu (deck=None hebt die Zuordnung auf). Auswahl ueber
    Dokumente, Faecher und/oder einzelne Karten. Gibt die Anzahl geaenderter Karten zurueck."""
    conds, args = [], []
    if doc_ids:
        conds.append(f"doc_id IN ({','.join('?' * len(doc_ids))})"); args += list(doc_ids)
    if subjects:
        conds.append(f"subject IN ({','.join('?' * len(subjects))})"); args += list(subjects)
    if card_ids:
        conds.append(f"card_id IN ({','.join('?' * len(card_ids))})"); args += list(card_ids)
    if not conds:
        return 0
    with _connect() as conn:
        cur = conn.execute(
            f"UPDATE review_items SET deck=? WHERE ({' OR '.join(conds)})", [deck] + args)
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


def deck_overview() -> list[dict]:
    """Pro Stapel: Kartenzahl + faellig (fuer die Verwaltung/Anzeige)."""
    now = time.time()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT COALESCE(deck,'') AS deck, COUNT(*) AS total, "
            "SUM(CASE WHEN due<=? THEN 1 ELSE 0 END) AS due "
            "FROM review_items WHERE suspended=0 GROUP BY COALESCE(deck,'') ORDER BY deck",
            (now,)).fetchall()
        return [{"deck": r["deck"] or None, "total": r["total"], "due": r["due"]} for r in rows]


# --------------------------------------------------------------------------- #
# Klausurtermine (pro Fach ein Termin)
# --------------------------------------------------------------------------- #
def upsert_exam(subject: str, *, exam_date: Optional[str] = None,
                ects: Optional[float] = None, gewicht: float = 1.0,
                notiz: Optional[str] = None) -> None:
    """Legt einen Klausurtermin fuer ein Fach an oder aktualisiert ihn.
    ``exam_date`` ist ISO 'YYYY-MM-DD' (oder None/'' = kein Termin gesetzt)."""
    if not subject:
        return
    now = time.time()
    exam_date = (exam_date or "").strip() or None
    with _connect() as conn:
        exists = conn.execute(
            "SELECT created_at FROM exams WHERE subject=?", (subject,)).fetchone()
        created = exists["created_at"] if exists else now
        conn.execute(
            "INSERT INTO exams (subject, exam_date, ects, gewicht, notiz, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(subject) DO UPDATE SET exam_date=excluded.exam_date, "
            "ects=excluded.ects, gewicht=excluded.gewicht, notiz=excluded.notiz, "
            "updated_at=excluded.updated_at",
            (subject, exam_date, ects, float(gewicht or 1.0), notiz, created, now),
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


def exam_map() -> dict:
    """Fach -> exam-Datensatz (dict), fuer schnelle Nachschlage in Planer/Analytik."""
    return {e["subject"]: e for e in list_exams()}


def delete_exam(subject: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM exams WHERE subject=?", (subject,))


# Ro7: KEINE Initialisierung mehr als Import-Nebenwirkung. Schema/Migrationen
# laufen ueber _ensure_initialized() beim ersten DB-Zugriff (idempotent, mit
# Logging). init_db() bleibt oeffentlich (z. B. fuer explizite CLI-Nutzung).
