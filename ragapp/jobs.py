"""Hintergrundaufträge für lange KI-Läufe (z. B. Lernplan -> Karten für alle Themen).

Ein Auftrag läuft in einem eigenen Thread. Die Seite bleibt bedienbar, der Fortschritt ist
sichtbar, und der Lauf lässt sich abbrechen - auch nachdem man die Seite gewechselt oder neu
geladen hat: das Register hängt am Server-Prozess, nicht an der Browser-Sitzung.

Bewusst ohne Streamlit-Import: Auftragscode darf keine ``st.*``-Aufrufe machen (kein
Skript-Kontext im Thread) und meldet Fortschritt nur über ``JobContext.progress``. Die
Oberfläche fragt den Stand regelmäßig ab (siehe Lernplan-Seite, ``st.fragment(run_every=…)``).

Abbrechen ist kooperativ: ``cancel`` setzt ein Flag, der Auftrag prüft es an sicheren Stellen
(zwischen Themen/Abschnitten/Karten) und beendet sich dann. Was bis dahin fertig ist, bleibt
gespeichert - die Läufe sind wiederholbar und machen beim nächsten Klick dort weiter.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

try:  # zentrales Logging, sonst Standard-Logging
    from ragapp.logging_setup import get_logger
    _log = get_logger(__name__)
except Exception:  # noqa: BLE001
    import logging
    _log = logging.getLogger(__name__)

# Ein haengender Auftrag soll das Beenden der App (Tab-Close-Waechter) nicht ewig aufhalten.
MAX_BUSY_SECONDS = 3 * 3600
_KEEP_FINISHED = 20           # so viele beendete Auftraege merkt sich das Register hoechstens

RUNNING, DONE, CANCELLED, ERROR = "running", "done", "cancelled", "error"


class JobCancelled(Exception):
    """Darf der Auftrag selbst werfen (``JobContext.check``), um sauber auszusteigen."""


@dataclass
class Job:
    key: str
    title: str
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started: float = field(default_factory=time.time)
    finished: Optional[float] = None
    status: str = RUNNING
    message: str = ""
    step: int = 0                       # erledigte Schritte (z. B. Themen)
    total: int = 0                      # Gesamtzahl der Schritte, 0 = unbekannt
    result: Any = None
    error: Optional[str] = None
    cancel_requested: bool = False
    saw_cancel: bool = False            # der Auftrag hat die Abbruch-Bitte bemerkt


class JobContext:
    """Was ein Auftrag von seiner Umgebung sieht: Fortschritt melden, Abbruch erkennen."""

    def __init__(self, job: Job, lock: threading.RLock):
        self._job = job
        self._lock = lock

    def progress(self, message: str, *, step: Optional[int] = None,
                 total: Optional[int] = None) -> None:
        with self._lock:
            self._job.message = message
            if step is not None:
                self._job.step = int(step)
            if total is not None:
                self._job.total = int(total)

    def steps(self, step: int, total: int) -> None:
        """Nur den Zähler setzen (z. B. „3 von 38 Themen“), ohne die Meldung zu ändern."""
        with self._lock:
            self._job.step = int(step)
            self._job.total = int(total)

    def cancelled(self) -> bool:
        """True, sobald Abbrechen verlangt wurde. Der Auftrag soll dann an der nächsten
        sicheren Stelle aufhören und zurückgeben, was er bis dahin geschafft hat."""
        with self._lock:
            if self._job.cancel_requested:
                self._job.saw_cancel = True
                return True
            return False

    def check(self) -> None:
        """Wirft ``JobCancelled``, wenn abgebrochen wurde (Kurzform für tiefe Aufrufer)."""
        if self.cancelled():
            raise JobCancelled()


_lock = threading.RLock()
_jobs: dict[str, Job] = {}


def _prune() -> None:
    finished = sorted((j for j in _jobs.values() if j.status != RUNNING),
                      key=lambda j: j.finished or 0)
    for old in finished[:max(0, len(finished) - _KEEP_FINISHED)]:
        _jobs.pop(old.key, None)


def start(key: str, title: str, func: Callable[[JobContext], Any]) -> tuple[Job, bool]:
    """Startet ``func(ctx)`` im Hintergrund. Läuft unter ``key`` schon ein Auftrag, wird KEIN
    zweiter gestartet. Rückgabe ``(Auftrag, neu_gestartet)``."""
    with _lock:
        existing = _jobs.get(key)
        if existing is not None and existing.status == RUNNING:
            return existing, False
        job = Job(key=key, title=title)
        _jobs[key] = job
        _prune()
    ctx = JobContext(job, _lock)

    def _worker() -> None:
        try:
            result = func(ctx)
            status, error = (CANCELLED if job.saw_cancel else DONE), None
        except JobCancelled:
            result, status, error = None, CANCELLED, None
        except Exception as exc:  # noqa: BLE001 - jeder Fehler wird gemeldet, nie verschluckt
            _log.exception("Hintergrundauftrag %s abgebrochen", key)
            result, status, error = None, ERROR, str(exc) or exc.__class__.__name__
        with _lock:
            job.result = result
            job.error = error
            job.status = status
            job.finished = time.time()

    threading.Thread(target=_worker, name=f"rag-job-{key}", daemon=True).start()
    return job, True


def get(key: str) -> Optional[Job]:
    """Momentaufnahme des Auftrags (Kopie, gefahrlos zu lesen) oder None."""
    with _lock:
        job = _jobs.get(key)
        return Job(**vars(job)) if job is not None else None


def cancel(key: str) -> bool:
    """Bittet einen laufenden Auftrag aufzuhören. True, wenn einer lief."""
    with _lock:
        job = _jobs.get(key)
        if job is None or job.status != RUNNING:
            return False
        job.cancel_requested = True
        return True


def dismiss(key: str) -> None:
    """Vergisst einen BEENDETEN Auftrag (Meldung weggeklickt). Laufende bleiben."""
    with _lock:
        job = _jobs.get(key)
        if job is not None and job.status != RUNNING:
            _jobs.pop(key, None)


def any_running() -> bool:
    """Läuft gerade ein Auftrag? (Der Tab-Close-Wächter beendet die App dann nicht mitten im
    Lauf; ein Auftrag, der länger als ``MAX_BUSY_SECONDS`` läuft, hält ihn nicht auf.)"""
    now = time.time()
    with _lock:
        return any(j.status == RUNNING and now - j.started < MAX_BUSY_SECONDS
                   for j in _jobs.values())


def reset_for_tests() -> None:
    """Nur für Tests: Register leeren."""
    with _lock:
        _jobs.clear()
