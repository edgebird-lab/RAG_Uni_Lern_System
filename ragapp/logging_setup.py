"""
Zentrales Logging-Setup
=======================
Einheitliche Logger fuer die gesamte App. Bisher wurde verstreut mit ``print()``
protokolliert; dieses Modul buendelt Format und Level an einer Stelle.

Nutzung::

    from ragapp.logging_setup import get_logger
    log = get_logger(__name__)
    log.info("...")

Das Log-Level wird ueber die Umgebungsvariable ``RAG_LOG_LEVEL`` gesteuert
(z. B. ``DEBUG``, ``INFO``, ``WARNING``); Default ist ``INFO``.

Bewusst ohne schwere Importe (kein torch/streamlit/...), damit das Modul frueh
und ueberall gefahrlos importiert werden kann.
"""
from __future__ import annotations

import logging
import os

# Einheitliches Format fuer alle Handler dieses Setups.
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Merkt sich, welche Logger dieses Modul schon konfiguriert hat, damit bei
# wiederholtem get_logger()-Aufruf nicht mehrfach Handler angehaengt werden
# (das wuerde doppelte Zeilen erzeugen).
_configured: set[str] = set()


def _resolve_level() -> int:
    """Log-Level aus RAG_LOG_LEVEL ableiten (Default INFO, robust bei Unsinn)."""
    raw = os.environ.get("RAG_LOG_LEVEL", "").strip().upper()
    if not raw:
        return logging.INFO
    # Sowohl Namen ("DEBUG") als auch Zahlen ("10") zulassen.
    if raw.isdigit():
        return int(raw)
    return getattr(logging, raw, logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Liefert einen konfigurierten Logger.

    Idempotent: Ein zweiter Aufruf mit demselben Namen haengt keinen weiteren
    Handler an und dupliziert damit keine Ausgaben. Level wird bei jedem Aufruf
    aus RAG_LOG_LEVEL aktualisiert, sodass eine spaet gesetzte Env-Variable noch
    greift.
    """
    logger = logging.getLogger(name)
    level = _resolve_level()
    logger.setLevel(level)

    if name not in _configured:
        # Nur, wenn dieses Setup noch keinen eigenen Handler angehaengt hat.
        # (Bereits vorhandene Fremd-Handler respektieren wir und lassen sie.)
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
            logger.addHandler(handler)
            # Nicht zusaetzlich an den Root-Logger weiterreichen -> keine Dopplung.
            logger.propagate = False
        _configured.add(name)

    return logger


def rotate_file(path: str, max_bytes: int = 5 * 1024 * 1024) -> bool:
    """Groessenbasierte Rotation fuer eine Logdatei.

    Ist ``path`` groesser als ``max_bytes``, wird die Datei nach ``path + '.1'``
    verschoben (eine bestehende ``.1`` wird ueberschrieben). Reine Dateioperation,
    ohne Handler-Verwaltung. Gibt True zurueck, wenn rotiert wurde.

    Exception-safe: Bei Fehlern (Rechte, Race) wird False zurueckgegeben, ohne
    zu werfen.
    """
    try:
        if max_bytes <= 0:
            return False
        if not os.path.isfile(path):
            return False
        if os.path.getsize(path) < max_bytes:
            return False
        backup = path + ".1"
        if os.path.exists(backup):
            os.remove(backup)
        os.replace(path, backup)
        return True
    except OSError:
        return False
