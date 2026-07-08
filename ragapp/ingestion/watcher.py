"""
Ordnerwächter (automatische Ingestion-Pipeline)
===============================================

Überwacht den Quell- und den Inbox-Ordner. Sobald eine unterstützte Datei
hineingelegt oder geändert wird, wird sie automatisch geladen, geslicet,
dedupliziert, mit Fragen angereichert und in die Vektordatenbank geschrieben.

"Datei rein → fertig aufbereitet im Index" – ohne manuelles Zutun.

Debounce: Nach einem Ereignis wird gewartet, bis die Datei einige Sekunden
unverändert (stabil) ist, damit kein halb geschriebenes PDF gelesen wird.
"""
from __future__ import annotations

import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from ragapp.config import SOURCE_DIR, INBOX_DIR
from ragapp.ingestion.loaders import SUPPORTED_EXTENSIONS
from ragapp.ingestion.pipeline import ingest_file


class _Handler(FileSystemEventHandler):
    def __init__(self, debounce: float = 3.0):
        self.debounce = debounce
        self._pending: dict[str, float] = {}

    def on_created(self, event):
        self._maybe_queue(event)

    def on_modified(self, event):
        self._maybe_queue(event)

    def _maybe_queue(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            self._pending[str(path)] = time.time()

    def process_ready(self):
        now = time.time()
        ready = [p for p, t in self._pending.items() if now - t >= self.debounce]
        for p in ready:
            self._pending.pop(p, None)
            path = Path(p)
            if not path.exists():
                continue
            try:
                print(f"[watcher] Verarbeite: {path.name}")
                res = ingest_file(path)
                print(f"[watcher]   -> {res['status']} "
                      f"(Chunks: {res.get('chunks', 0)}, Fragen: {res.get('questions', 0)})")
            except Exception as exc:  # pragma: no cover
                print(f"[watcher]   FEHLER bei {path.name}: {exc}")


def watch(paths: list[Path] | None = None, poll_interval: float = 2.0) -> None:
    paths = paths or [SOURCE_DIR, INBOX_DIR]
    handler = _Handler()
    observer = Observer()
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)
        observer.schedule(handler, str(p), recursive=True)
    observer.start()
    print(f"[watcher] Überwache: {', '.join(str(p) for p in paths)}")
    print("[watcher] Lege PDFs/MD/DOCX/PPTX hinein – sie werden automatisch indexiert.")
    print("[watcher] Beenden mit Strg+C.")
    try:
        while True:
            time.sleep(poll_interval)
            handler.process_ready()
    except KeyboardInterrupt:
        observer.stop()
        print("\n[watcher] gestoppt.")
    observer.join()
