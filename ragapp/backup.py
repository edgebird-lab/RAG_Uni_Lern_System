"""
Lernstand-Snapshots (Datensicherung)
====================================
Das ``review_log`` (jede einzelne Wiederholung) und ``review_items`` (der SM-2-
Fortschritt) sind das wertvollste, unersetzliche Gut der App - Monate verteilten
Uebens. Ein Absturz, ein Fehlklick auf "Karten loeschen" oder eine kaputte
Migration kurz vor der Klausur wuerde den ganzen Vergessenskurven-Plan vernichten.

Dieses Modul zieht WAL-konsistente Kopien der gesamten ``manifest.db`` (via
``sqlite3.Connection.backup()``) nach ``data/backups/`` und rotiert sie
(Grossvater-Vater-Sohn: die letzten N bleiben). Snapshots werden automatisch
gezogen (a) vor destruktiven Aktionen (Karten/Deck loeschen, Neu-Ernte) und
(b) beim Start, wenn der letzte Snapshot aelter als ``BACKUP_MIN_HOURS`` ist.
Reines stdlib, offline, ohne Fremdabhaengigkeit.
"""
from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

from ragapp.config import MANIFEST_DB, DATA_DIR, settings

BACKUP_DIR = DATA_DIR / "backups"
_PREFIX = "manifest-"
_SUFFIX = ".db"


def _safe(reason: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (reason or "snapshot").lower()).strip("-")
    return s[:24] or "snapshot"


def _keep() -> int:
    return int(getattr(settings, "BACKUP_KEEP", 12))


def snapshot(reason: str = "manuell") -> "Path | None":
    """Zieht einen konsistenten Snapshot der manifest.db. Gibt den Pfad zurueck
    (oder None, wenn die DB fehlt / etwas schiefging - nie eine Exception)."""
    if not MANIFEST_DB.exists():
        return None
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
        dest = BACKUP_DIR / f"{_PREFIX}{stamp}-{_safe(reason)}{_SUFFIX}"
        src = sqlite3.connect(str(MANIFEST_DB))
        try:
            dst = sqlite3.connect(str(dest))
            try:
                src.backup(dst)          # WAL-konsistent, atomar
            finally:
                dst.close()
        finally:
            src.close()
    except Exception:  # noqa: BLE001 - Backup darf nie den Betrieb stoeren
        return None
    _rotate()
    return dest


def _rotate() -> None:
    keep = _keep()
    if keep <= 0:
        return
    snaps = list_snapshot_paths()
    for old in snaps[:-keep]:
        try:
            old.unlink()
        except Exception:  # noqa: BLE001
            pass


def list_snapshot_paths() -> list[Path]:
    if not BACKUP_DIR.is_dir():
        return []
    return sorted(BACKUP_DIR.glob(f"{_PREFIX}*{_SUFFIX}"))


def list_snapshots() -> list[dict]:
    """Snapshots, neueste zuerst: {path, name, when (epoch), size_kb}."""
    out = []
    for p in reversed(list_snapshot_paths()):
        try:
            st = p.stat()
            out.append({"path": p, "name": p.name, "when": st.st_mtime,
                        "size_kb": round(st.st_size / 1024)})
        except Exception:  # noqa: BLE001
            pass
    return out


def latest() -> "Path | None":
    snaps = list_snapshot_paths()
    return snaps[-1] if snaps else None


def snapshot_if_stale(reason: str = "autostart", min_hours: "float | None" = None) -> "Path | None":
    """Zieht einen Start-Snapshot nur, wenn der letzte aelter als ``min_hours`` ist
    (Standard aus den Einstellungen). Idempotent genug fuer den App-Start."""
    hours = float(min_hours if min_hours is not None else getattr(settings, "BACKUP_MIN_HOURS", 24.0))
    last = latest()
    if last is not None:
        try:
            if (time.time() - last.stat().st_mtime) < hours * 3600:
                return None
        except Exception:  # noqa: BLE001
            pass
    return snapshot(reason)


def restore(snapshot_path: "str | Path") -> bool:
    """Stellt einen Snapshot wieder her. Sichert vorher den AKTUELLEN Stand
    (reason='vor-wiederherstellung'), damit auch das rueckgaengig gemacht werden
    kann, und schreibt den Snapshot dann via sqlite-backup in die Live-DB
    (verbindungssicher, kein Datei-Ueberschreiben unter offenen Handles)."""
    src_path = Path(snapshot_path)
    if not src_path.is_file():
        return False
    snapshot("vor-wiederherstellung")
    try:
        src = sqlite3.connect(str(src_path))
        try:
            dst = sqlite3.connect(str(MANIFEST_DB))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        return True
    except Exception:  # noqa: BLE001
        return False
