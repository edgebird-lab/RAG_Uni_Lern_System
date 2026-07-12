"""
Konfliktfreie Multi-Device-Sync (deterministischer review_log-Replay)
=====================================================================
Weil der Wiederholungs-Zustand (SM-2) eine reine Funktion der Bewertungs-Historie
ist, laesst sich ``review_log`` als append-only, kommutativer Ereignis-Stream
behandeln (CRDT-artig). Handy und PC, die dieselbe Karte wiederholen, loesen sich
dadurch OHNE manuelles Mergen auf - und JEDE einzelne Wiederholung bleibt erhalten
(kein "letzte Datei gewinnt", das ganze Sitzungen zerstoert).

  * ``export_events``  - alle (oder neue) Ereignisse als JSONL exportieren.
  * ``import_events``  - Ereignisse idempotent uebernehmen (INSERT OR IGNORE auf
    der global eindeutigen event_uid), danach den Zustand neu berechnen.
  * ``rebuild_state``  - den SM-2-Zustand jeder Karte aus ihrer gesamten Historie
    exakt rekonstruieren: ease/interval aus dem zuletzt geloggten ease_after/
    interval_after (enthaelt bereits Cram-Kappung & Hypercorrection), reps/lapses
    aus der Rating-Folge (dieselbe Logik wie sm2_next). Deterministisch -> alle
    Geraete kommen zum selben Ergebnis.
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from typing import Iterator, Optional

from ragapp.config import MANIFEST_DB

_FIELDS = ("card_id", "subject", "topic", "rating", "reviewed_at",
           "interval_after", "ease_after", "confidence", "device_id", "event_uid",
           "due_after")


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(str(MANIFEST_DB))
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def export_events(since: Optional[float] = None) -> str:
    """Alle review_log-Ereignisse als JSONL (append-only Stream). ``since`` = nur
    Ereignisse ab diesem Zeitpunkt (fuer inkrementellen Export)."""
    q = f"SELECT {','.join(_FIELDS)} FROM review_log"
    args: list = []
    if since is not None:
        q += " WHERE reviewed_at >= ?"
        args.append(since)
    q += " ORDER BY reviewed_at, id"
    with _conn() as c:
        rows = c.execute(q, args).fetchall()
    return "\n".join(json.dumps(dict(r), ensure_ascii=False) for r in rows)


def import_events(jsonl: str) -> dict:
    """Uebernimmt Ereignisse aus einem anderen Geraet idempotent (Duplikate anhand
    event_uid werden ignoriert) und rechnet danach den Zustand neu. Ereignisse ohne
    event_uid (Altbestand) werden uebersprungen. Gibt {imported, skipped, updated}."""
    imported = skipped = 0
    ph = ",".join("?" * len(_FIELDS))
    with _conn() as c:
        for line in (jsonl or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if not e.get("event_uid"):
                continue
            cur = c.execute(
                f"INSERT OR IGNORE INTO review_log ({','.join(_FIELDS)}) VALUES ({ph})",
                tuple(e.get(k) for k in _FIELDS))
            if cur.rowcount:
                imported += 1
            else:
                skipped += 1
    updated = rebuild_state()
    return {"imported": imported, "skipped": skipped, "updated": updated}


def rebuild_state() -> int:
    """Rekonstruiert den SM-2-Zustand jeder Karte exakt aus ihrer gesamten
    Bewertungs-Historie. Deterministisch. Gibt die Zahl aktualisierter Karten zurueck.
    (Karten ohne review_items-Eintrag werden uebersprungen.)"""
    updated = 0
    with _conn() as c:
        card_ids = [r["card_id"] for r in c.execute("SELECT DISTINCT card_id FROM review_log")]
        for cid in card_ids:
            evs = c.execute(
                "SELECT rating, reviewed_at, interval_after, ease_after, due_after FROM review_log "
                "WHERE card_id=? ORDER BY reviewed_at, id", (cid,)).fetchall()
            if not evs:
                continue
            reps = lapses = 0
            for e in evs:                       # reps/lapses wie in sm2_next
                r = int(e["rating"] or 0)
                if r <= 0:                       # NICHT: zurueck auf Anfang, Patzer++
                    reps = 0
                    lapses += 1
                elif r >= 2:                     # GEWUSST: eine Stufe hoch
                    reps += 1
                # HALB: reps/lapses unveraendert
            last = evs[-1]
            ease = float(last["ease_after"] if last["ease_after"] is not None else 2.5)
            interval = float(last["interval_after"] or 0)
            reviewed = last["reviewed_at"] or time.time()
            # Exakte absolute Faelligkeit aus dem Log (faellt bei Altbestand ohne
            # due_after auf reviewed_at + interval*Tage zurueck).
            due = last["due_after"] if last["due_after"] is not None else reviewed + interval * 86400.0
            cur = c.execute(
                "UPDATE review_items SET ease=?, interval=?, reps=?, lapses=?, due=?, "
                "last_review=? WHERE card_id=?",
                (ease, interval, reps, lapses, due, reviewed, cid))
            if cur.rowcount:
                updated += 1
    return updated
