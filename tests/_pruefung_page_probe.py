"""Prüfskript für die Probeklausur (Prüfungsseite) - läuft als EIGENER Prozess
(siehe test_pruefung_page.py).

Geprüft wird der Ablauf laufende Klausur -> Abgeben -> Ergebnis: Countdown und Antwortfelder,
Benotung (Attrappe statt Modell), Ergebnis-Karte mit Kennzahlen, kein Countdown mehr, und dass
der Ergebnis-Lauf NORMAL endet (ohne st.stop()), damit Streamlit das Countdown-Fragment abräumt.
Sonst lief ein verspäteter Countdown-Tick nach dem Ergebnis-Lauf und legte seinen Container über
die Ergebnis-Karte.

Alles offline in einer temporären Datenbank.
Aufruf: python tests/_pruefung_page_probe.py <Ordner für die Test-Datenbank>"""
from __future__ import annotations

import contextlib
import os
import sys
import time
from pathlib import Path
from unittest import mock

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


def _card(cid):
    return {"card_id": cid, "source": "question", "chroma_id": cid, "subject": "ANA",
            "topic": "Seite 1", "front": f"Was ist {cid}?", "back": "Beleg",
            "answer": f"Die Antwort zu {cid}.", "doc_id": "d1"}


manifest.upsert_review_items([_card("k1"), _card("k2"), _card("k3")])
cards = [dict(r) for r in manifest.get_due_cards("ANA", limit=3, cram=True)]
assert len(cards) == 3, cards

graded = []


def fake_grade(question, reference, student, model=None):
    graded.append(student)
    return {"score": 80, "fehlt": [], "feedback": "Gut.", "suggested_rating": 3, "ok": True}


for p in (mock.patch("ragapp.grading.grade_typed_answer", fake_grade),
          mock.patch("ragapp.llm.llm_task", lambda *a, **k: contextlib.nullcontext())):
    p.start()

from streamlit.testing.v1 import AppTest      # noqa: E402

PAGE = str(ROOT / "ragapp" / "ui" / "pages" / "6_📝_Prüfung.py")


def check(at):
    assert not at.exception, [e.value for e in at.exception]


def texts(at):
    return " ".join(str(m.value) for m in at.markdown)


at = AppTest.from_file(PAGE, default_timeout=90)
at.session_state["_exam"] = {"cards": cards, "answers": {}, "start": time.time(),
                             "limit": 600, "done": False}
at.run()
check(at)
assert "verbleibend" in texts(at), texts(at)[:400]
assert len(at.text_area) == 3
print("OK 1 Laufende Klausur: Countdown und drei Antwortfelder")

for i, ta in enumerate(at.text_area):
    ta.input(f"Antwort {i + 1}")
[b for b in at.button if "Abgeben" in b.label][0].click()
at.run()
check(at)
assert graded == ["Antwort 1", "Antwort 2", "Antwort 3"], graded
assert at.session_state["_exam"]["done"] is True
print("OK 2 Abgeben benotet alle drei Antworten")

assert any("Ergebnis" in h.value for h in at.subheader), [h.value for h in at.subheader]
metrics = {m.label: m.value for m in at.metric}
assert metrics.get("Gesamt") == "80 %" and metrics.get("Aufgaben") == "3", metrics
assert "verbleibend" not in texts(at)
assert len(at.text_area) == 0
print("OK 3 Ergebnis-Karte mit Kennzahlen, kein Countdown mehr")

# Der Ergebnis-Lauf muss normal enden: dann räumt Streamlit das Countdown-Fragment ab.
stops = []
real_stop = __import__("streamlit").stop


def spy_stop():
    stops.append(1)
    real_stop()


with mock.patch("streamlit.stop", spy_stop):
    at.run()
check(at)
assert not stops, "Ergebnis-Lauf endet mit st.stop()"
assert dict((m.label, m.value) for m in at.metric).get("Gesamt") == "80 %"
print("OK 4 Ergebnis-Lauf endet ohne st.stop()")

[b for b in at.button if "Neue Prüfung" in b.label][0].click()
at.run()
check(at)
assert "_exam" not in at.session_state
assert any("Probeklausur zusammenstellen" in h.value for h in at.subheader)
print("OK 5 'Neue Prüfung' führt zurück zum Aufbau")
print("ALLE CHECKS OK")
