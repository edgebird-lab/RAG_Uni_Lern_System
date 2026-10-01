"""Prüfskript für die Lernplan-Seite - läuft als EIGENER Prozess (siehe test_lernplan_page.py).

Warum ein Subprozess: Streamlits AppTest kann abstürzen, wenn im selben Prozess torch/chromadb
geladen sind und mehrere AppTests laufen (CONTRIBUTING.md). So bleibt ein Absturz auf diesen
einen Test begrenzt.

Alles offline: eine temporäre Datenbank, erzeugt/gefüllt wird nichts echtes (die Füll-Funktionen
sind durch Attrappen ersetzt); geprüft wird, was die Seite anzeigt und was sie übergibt.
Aufruf: python tests/_lernplan_page_probe.py <Ordner für die Test-Datenbank>"""
from __future__ import annotations

import os
import sys
import threading
import time
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["ARROW_DEFAULT_MEMORY_POOL"] = "system"
os.environ["RAG_LOCAL_ONLY"] = "1"
os.environ["RAG_DISABLE_PREWARM"] = "1"
os.environ["RAG_IDLE_SHUTDOWN"] = "0"

from ragapp import jobs, manifest, plan_cards          # noqa: E402

_work = Path(sys.argv[1])
manifest.MANIFEST_DB = _work / "manifest_probe.db"                 # NIE die echte Datenbank
manifest._initialized = False
# Dieser Prozess erbt die Test-Isolation aus conftest.py NICHT - hier dasselbe noch einmal:
# keine Sicherungen der echten Datenbank, nicht die echte Tagesziel-Datei.
from ragapp import analytics, backup                                # noqa: E402
backup.BACKUP_DIR = _work / "backups"
backup.MANIFEST_DB = _work / "keine-echte-manifest.db"
analytics._DAILY_GOAL_FILE = _work / "daily_goal.json"

today = date.today().isoformat()
later = (date.today() + timedelta(days=5)).isoformat()

for did, fn in (("dA", "1 Vektorrechnung.pdf"), ("dB", "4 Matrizen.pdf")):
    manifest.upsert_document(doc_id=did, content_hash="h", source_path=f"x/{fn}", filename=fn,
                             subject="LAT", filetype="pdf", num_chunks=6, num_questions=0,
                             char_count=6000, status="ok")
pid = manifest.create_study_plan(title="Plan LAT", subject="LAT", doc_ids=["dA", "dB"],
                                 deadline=None, daily_minutes=60)


def refs(doc, fn, *pages):
    return [{"doc_id": doc, "filename": fn, "section": f"Seite {p}"} for p in pages]


VEK, MAT = "1 Vektorrechnung.pdf", "4 Matrizen.pdf"
manifest.replace_plan_sections(pid, [
    {"title": "Vektoren", "summary": "", "est_chars": 1500, "est_minutes": 25, "source_refs": refs("dA", VEK, 1, 2)},
    {"title": "Skalarprodukt", "summary": "", "est_chars": 1500, "est_minutes": 25, "source_refs": refs("dA", VEK, 3)},
    {"title": "Matrizen", "summary": "", "est_chars": 1500, "est_minutes": 25, "source_refs": refs("dB", MAT, 1)},
    {"title": "Gemischt", "summary": "", "est_chars": 1500, "est_minutes": 25,
     "source_refs": refs("dA", VEK, 5) + refs("dB", MAT, 4)},
])
vek, skal, mat, gem = manifest.list_plan_sections(pid)
manifest.replace_plan_blocks(pid, [
    {"section_id": vek["section_id"], "planned_date": today, "planned_min": 25},
    {"section_id": skal["section_id"], "planned_date": today, "planned_min": 25},
    {"section_id": mat["section_id"], "planned_date": later, "planned_min": 25},
])
manifest.update_study_plan(pid, status="active")


def card(cid, doc, page, answer="Eine brauchbare Antwort mit Inhalt.", front=None):
    return {"card_id": cid, "source": "question", "chroma_id": cid, "subject": "LAT",
            "topic": f"Seite {page}", "front": front or f"Was ist Begriff {cid}?", "back": "Beleg",
            "answer": answer, "doc_id": doc}


manifest.upsert_review_items([
    card("v1", "dA", 1), card("v2", "dA", 2),
    card("s1", "dA", 3, front="Wie lautet die Definition von OD im Abschnitt?"),     # mangelhaft
    card("m1", "dB", 1), card("m2", "dB", 1)])
now = time.time()
with manifest._connect() as conn:
    conn.execute("UPDATE review_items SET reps=3, due=? WHERE card_id='v1'", (now - 100,))     # geübt + fällig
    conn.execute("UPDATE review_items SET reps=2, due=? WHERE card_id='v2'", (now + 86400,))   # geübt, nicht fällig
    conn.execute("UPDATE review_items SET reps=4, due=? WHERE card_id='m1'", (now - 50,))      # Matrizen: schon geübt
manifest.create_practice_problem(subject="LAT", doc_id="dB", topic="Matrizen",
                                 problem_text="Matrix-Aufgabe", steps=["s"])

from streamlit.testing.v1 import AppTest      # noqa: E402

PAGE = str(ROOT / "ragapp" / "ui" / "pages" / "11_📋_Lernplan.py")
calls = {"fill": [], "repair": []}
gate = threading.Event()


def fake_fill(sections, **kw):
    calls["fill"].append(([s["title"] for s in sections], kw.get("with_practice"), kw.get("subject")))
    kw["progress"]("Thema 1/2 · Vektoren – Fragen erzeugen …")
    kw["on_step"](1, 2)
    gate.wait(10)
    if kw["should_cancel"]():
        return {"status": "cancelled", "topics": 2, "topics_done": 1, "topics_empty": 0, "questions": 2,
                "cards_new": 2, "answers": 2, "rejected": 1, "duplicates": 0, "problems_new": 0,
                "problems_failed": 0, "error_msg": None}
    return {"status": "ok", "topics": 2, "topics_done": 2, "topics_empty": 0, "questions": 4,
            "cards_new": 4, "answers": 4, "rejected": 2, "duplicates": 1, "problems_new": 2,
            "problems_failed": 0, "error_msg": None}


def fake_repair(plan, sections, **kw):
    calls["repair"].append([s["title"] for s in sections])
    return {"status": "ok", "topics": 1, "topics_done": 1, "topics_empty": 0, "questions": 1,
            "cards_new": 1, "answers": 1, "rejected": 0, "duplicates": 0, "problems_new": 0,
            "problems_failed": 0, "error_msg": None, "repair": {"deleted": 1, "protected": 0}}


for p in (mock.patch("ragapp.plan_cards.fill_plan_cards", fake_fill),
          mock.patch("ragapp.plan_cards.repair_and_fill", fake_repair),
          mock.patch("ragapp.retrieval.embeddings.get_embedder",
                     lambda: type("E", (), {"embed_texts": staticmethod(lambda t: [[1.0]] * len(t))})())):
    p.start()


def page():
    at = AppTest.from_file(PAGE, default_timeout=90)
    at.session_state["splan_choice"] = pid
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def alltext(at):
    return " ".join([m.value for m in at.markdown] + [c.value for c in at.caption]
                    + [s.value for s in at.success] + [w.value for w in at.warning]
                    + [e.value for e in at.error] + [i.value for i in at.info])


def wait_job(timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        j = jobs.get(plan_cards.job_key(pid))
        if j is None or j.status != jobs.RUNNING:
            return j
        time.sleep(0.02)
    raise AssertionError("Auftrag wurde nicht fertig")


# 1) Schrittleiste
at = page()
t = alltext(at)
assert "class='splan-steps'" in t and t.count("<b>als Nächstes</b>") == 1, t[:300]
assert "aus mehreren Dokumenten" in t
print("OK 1 Schrittleiste: vier Schritte, genau ein 'als Nächstes', Warnung bei gemischtem Thema")

# 2) Termine auf den Kacheln
assert "📅 heute" in t and "kommt später" in t and "noch nicht eingeplant" in t
assert f"ab {plan_cards.fmt_day(later)}" in t and "in 5 Tagen" in t
print("OK 2 Kacheln: heute / kommt später / noch nicht eingeplant")

# 3) Lernstand + Wiederholen je Thema
assert "🧠 1 von 2 sitzen · 1 fällig" in t and "splan-statebar" in t
assert at.button(key=f"splan_review_{vek['section_id']}").label == "🔁 Wiederholen · 1 fällig"
assert not [b for b in at.button if b.key == f"splan_review_{skal['section_id']}"]
at.button(key=f"splan_review_{vek['section_id']}").click().run()
pf = at.session_state["study_prefill"]
assert pf["card_ids"] == ["v1"] and pf["source"] == "plan" and pf["scope"].startswith("Wiederholung: Thema „Vektoren“"), pf
print("OK 3 Lernstand je Thema; 'Wiederholen' nur mit fälligen Karten dieses Themas")

# 4) Wiederholen im Heute-Panel: nur Fälliges aus angefangenen Themen
at = page()
btn = at.button(key=f"splan_dayreview_{today}")
assert btn.label == "🔁 Wiederholen · 2 fällig", btn.label
btn.click().run()
pf = at.session_state["study_prefill"]
assert sorted(pf["card_ids"]) == ["m1", "v1"] and "s1" not in pf["card_ids"], pf["card_ids"]
print("OK 4 Heute-Panel: 'Wiederholen' nimmt nur Fälliges aus bisherigen Themen")

# 5) Kartenqualität: Tabelle, Bestätigung, Reparatur-Auftrag über alle Themen
at = page()
assert any("1 Karte(n) mit Mängeln" in e.label for e in at.expander), [e.label for e in at.expander]
lines = [m.value for m in at.markdown if "Definition von OD im Abschnitt" in m.value]
assert len(lines) == 1, [m.value[:80] for m in at.markdown][-6:]
assert "verweist auf die Quelle" in lines[0] and "wird ersetzt" in lines[0] and "**Skalarprodukt**" in lines[0], lines[0]
at.button(key=f"splan_quality_ask_{pid}").click().run()
assert any("Wirklich beheben?" in w.value for w in at.warning)
at.button(key=f"splan_quality_go_{pid}").click().run()
j = wait_job()
assert j.status == jobs.DONE and calls["repair"] and len(calls["repair"][-1]) == 4, (j, calls)
at = page()
assert "1 fehlerhafte Karte(n) entfernt" in alltext(at)
at.button(key=f"splan_job_ok_{j.job_id}").click().run()
assert jobs.get(plan_cards.job_key(pid)) is None
print("OK 5 Kartenqualität: Tabelle, Bestätigung, Reparatur-Auftrag, Ergebnis + OK")

# 6) Hintergrundauftrag: starten, Leiste, Knöpfe gesperrt, Abbrechen, Teilergebnis
gate.clear()
at = page()
at.button(key=f"splan_fill_{pid}").click().run()
j = jobs.get(plan_cards.job_key(pid))
assert j is not None and j.status == jobs.RUNNING
at = page()
assert "⏳ Alle Lerneinheiten werden gefüllt" in alltext(at)
prog = [(pr.value, pr.text) for pr in at.get("progress")]
assert any("Thema 1/2" in (txt or "") for _, txt in prog) and any(abs(v - 50) < 1 for v, _ in prog), prog
assert at.button(key=f"splan_fill_{pid}").disabled
assert at.button(key=f"splan_unit_{gem['section_id']}").disabled
assert at.button(key=f"splan_regen_{pid}").disabled
at.button(key=f"splan_job_cancel_{j.job_id}").click().run()
assert jobs.get(plan_cards.job_key(pid)).cancel_requested
gate.set()
j = wait_job()
assert j.status == jobs.CANCELLED, j
at = page()
t = alltext(at)
assert "Abgebrochen – bis dahin: 2 neue Karten" in t and "macht dort weiter" in t
at.button(key=f"splan_job_ok_{j.job_id}").click().run()
assert jobs.get(plan_cards.job_key(pid)) is None and not at.button(key=f"splan_fill_{pid}").disabled
print("OK 6 Hintergrundauftrag: Leiste, Fortschritt, Knöpfe gesperrt, Abbrechen, Teilergebnis")

# 7) Einheit füllen (Kachel) startet einen Auftrag nur für dieses Thema
gate.set()
calls["fill"].clear()
at = page()
at.button(key=f"splan_unit_{skal['section_id']}").click().run()
wait_job()
assert calls["fill"][-1] == (["Skalarprodukt"], True, "LAT"), calls["fill"]
jobs.dismiss(plan_cards.job_key(pid))
print("OK 7 'Einheit füllen' startet einen Auftrag nur für dieses Thema")

# 8) Zieldatum / Klausur
at = page()
assert "Ohne Zieldatum verteilt die App den Stoff ab heute" in alltext(at)
exam_day = (date.today() + timedelta(days=30)).isoformat()
manifest.upsert_exam("LAT", exam_date=exam_day)
at = page()
assert "der Plan kennt sie aber nicht" in alltext(at)
adopt = [b for b in at.button if b.label == "📅 Klausurdatum als Zieldatum übernehmen"]
assert adopt
adopt[0].click().run()
assert manifest.get_study_plan(pid)["deadline"] == exam_day
print("OK 8 Zieldatum-Hinweis und 'Klausurdatum übernehmen'")

# 9) Zeitschätzung erklärt
at = page()
assert any("Wie kommt die Zeitschätzung zustande?" in e.label for e in at.expander)
assert "Korrekturfaktor:" in alltext(at)
print("OK 9 Zeitschätzung wird erklärt")

# 10) Veralteter Zeitplan: neues Thema ohne Termine
manifest.append_plan_section(pid, title="Neues Thema", est_minutes=40, source_refs=refs("dB", MAT, 2))
at = page()
t = alltext(at)
assert "Der Zeitplan ist veraltet" in t and "veraltet – neu berechnen" in t
print("OK 10 Veralteter Zeitplan erkannt")
print("ALLE CHECKS OK")
