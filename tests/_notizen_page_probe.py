"""Prüfskript für die Notizen-Seite - läuft als EIGENER Prozess (siehe test_notizen_page.py).

Geprüft wird, dass ein Klick auf eine gespeicherte Notiz sie im Editor öffnet, dass man zwischen
Notizen wechseln kann und dass nur ein bestätigtes Löschen die Notiz entfernt. Bis 0.2 lief nach
dem Öffnen sofort der Rest des Lösch-Zweigs (falsch eingerückt): "Notiz gelöscht." und zurück in
den "Neue Notiz"-Editor, ohne dass etwas gelöscht wurde.

Alles offline in einer temporären Datenbank.
Aufruf: python tests/_notizen_page_probe.py <Ordner für die Test-Datenbank>"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["ARROW_DEFAULT_MEMORY_POOL"] = "system"
os.environ["RAG_LOCAL_ONLY"] = "1"
os.environ["RAG_DISABLE_PREWARM"] = "1"
os.environ["RAG_IDLE_SHUTDOWN"] = "0"

from ragapp import manifest          # noqa: E402

_work = Path(sys.argv[1])
manifest.MANIFEST_DB = _work / "manifest_probe.db"                 # NIE die echte Datenbank
manifest._initialized = False
from ragapp import analytics, backup                                # noqa: E402
backup.BACKUP_DIR = _work / "backups"
backup.MANIFEST_DB = _work / "keine-echte-manifest.db"
analytics._DAILY_GOAL_FILE = _work / "daily_goal.json"

id_a = manifest.create_note(title="Lagemaße", body="Mittelwert, Median, Modus")
id_b = manifest.create_note(title="Streuung", body="Varianz und Standardabweichung")

from streamlit.testing.v1 import AppTest      # noqa: E402

PAGE = str(ROOT / "ragapp" / "ui" / "pages" / "12_🗒️_Notizen.py")


def check(at):
    assert not at.exception, [e.value for e in at.exception]


def editor_title(at):
    vals = [t.value for t in at.text_input if (t.key or "").startswith("notiz_edit_title_")]
    return vals[0] if vals else None


def headings(at):
    return [m.value for m in at.markdown if (m.value or "").startswith("##### ")]


def pick(at, nid):
    [b for b in at.button if b.key == f"notiz_pick_{nid}"][0].click().run()
    check(at)


at = AppTest.from_file(PAGE, default_timeout=90)
at.run()
check(at)
assert "##### ✏️ Neue Notiz" in headings(at), headings(at)
print("OK 1 Start: Editor für eine neue Notiz")

pick(at, id_a)
assert "##### ✏️ Notiz bearbeiten" in headings(at), headings(at)
assert editor_title(at) == "Lagemaße", editor_title(at)
assert at.session_state["notiz_choice"] == id_a
assert not [s.value for s in at.success if "gelöscht" in s.value]
print("OK 2 Klick auf eine gespeicherte Notiz öffnet sie im Editor")

at.run()                                    # weiterer Lauf (z. B. Tippen) - bleibt offen
check(at)
assert editor_title(at) == "Lagemaße", editor_title(at)
print("OK 3 Die Notiz bleibt über weitere Läufe offen")

pick(at, id_b)
assert editor_title(at) == "Streuung", editor_title(at)
print("OK 4 Wechsel zu einer anderen Notiz")

assert {n["note_id"] for n in manifest.list_notes()} == {id_a, id_b}
print("OK 5 Öffnen löscht nichts")

at.session_state["_rag_delete_confirmed"] = f"note:{id_b}"   # Dialog "Jetzt löschen" bestätigt
at.run()
check(at)
assert {n["note_id"] for n in manifest.list_notes()} == {id_a}
assert "##### ✏️ Neue Notiz" in headings(at), headings(at)
print("OK 6 Bestätigtes Löschen entfernt die Notiz und öffnet den leeren Editor")
print("ALLE CHECKS OK")
