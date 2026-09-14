"""Idempotente Livetest-Fixtures (Fach „Livetest“).

Legt Unterlagen, Karten, Übung, Notiz, Termin, Stundenplan, Aufgabe,
Fehlerheft und eine Mini-Chat-Session an – getrennt vom echten Semester.
Kein LLM, kein Wipe. Mehrfach aufrufbar.

    .venv/bin/python -m ragapp.scripts.seed_livetest
"""
from __future__ import annotations

import time
from datetime import date, timedelta
from pathlib import Path

from ragapp.config import PROJECT_ROOT
from ragapp import manifest
from ragapp.ingestion.pipeline import ingest_file

SUBJECT = "Livetest"
EMPTY_SUBJECT = "Livetest-Leer"
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "livetest"
INGEST_FILES = (
    "Livetest_Definitionen.md",
    "Livetest_Formeln.md",
)


def _already_ingested(filename: str) -> bool:
    return any(
        dict(d).get("filename") == filename and dict(d).get("subject") == SUBJECT
        for d in manifest.list_documents()
    )


def _seed_docs() -> list[str]:
    ids = []
    for name in INGEST_FILES:
        path = FIXTURE_DIR / name
        if not path.is_file():
            print("fehlt", path)
            continue
        if _already_ingested(name):
            doc = next(
                dict(d) for d in manifest.list_documents()
                if dict(d).get("filename") == name)
            ids.append(doc["doc_id"])
            print("dokument da", name, doc["doc_id"])
            continue
        res = ingest_file(path, subject=SUBJECT, progress=lambda m, **k: print(" ", m))
        print("ingest", name, res.get("status"), res)
        doc = next(
            (dict(d) for d in manifest.list_documents()
             if dict(d).get("filename") == name),
            None)
        if doc:
            ids.append(doc["doc_id"])
    return ids


def _seed_cards(doc_ids: list[str]) -> list[str]:
    def_id = doc_ids[0] if doc_ids else None
    form_id = doc_ids[1] if len(doc_ids) > 1 else def_id
    specs = [
        ("livetest::def-testing", "Was ist der Testing-Effekt?",
         "Aktives Abrufen behält Stoff länger als bloßes Nachlesen.",
         "text", def_id, "Testing-Effekt"),
        ("livetest::def-srs", "Was ist Spaced Repetition?",
         "Wiederholungen mit wachsenden Abständen; Fälliges zuerst.",
         "text", def_id, "Spaced Repetition"),
        ("livetest::def-ground", "Was bedeutet Grounding in diesem System?",
         "Die Antwort muss durch die Unterlage gedeckt sein.",
         "text", def_id, "Grounding"),
        ("livetest::f-ableitung", r"Ableitung von $f(x)=x^2$?",
         r"$f'(x)=2x$", "text", form_id, "Ableitung"),
        ("livetest::f-schnitt", r"Schnittmenge von $A=[-5;4)$ und $B=[0;9]$?",
         r"$A \cap B = [0;4)$", "text", form_id, "Mengen"),
        ("livetest::q-open", "Welche drei Schritte hat die Analysis-Anleitung?",
         "", "question", def_id, "Anleitung"),
    ]
    payload = []
    for cid, front, back, source, doc_id, topic in specs:
        payload.append({
            "card_id": cid, "source": source, "chroma_id": None,
            "subject": SUBJECT, "topic": topic, "doc_id": doc_id,
            "front": front, "back": back or "Siehe Unterlage.",
            "answer": back or "",
        })
    neu = manifest.upsert_review_items(payload)
    print("karten neu", neu)
    ids = [c["card_id"] for c in payload]
    manifest.assign_deck("Livetest-Grundlagen", card_ids=ids[:3])
    manifest.assign_deck("Livetest-Formeln", card_ids=ids[3:5])
    manifest.upsert_error(
        source="livetest", source_id="seed-testing",
        card_id="livetest::def-testing", subject=SUBJECT,
        front="Was ist der Testing-Effekt?",
        detail="Sicher eingeschätzt, aber falsch – Livetest-Fehlerheft.")
    return ids


def _seed_practice() -> None:
    existing = manifest.list_practice_problems(subject=SUBJECT)
    if existing:
        print("übung da", existing[0]["problem_id"])
        return
    pid = manifest.create_practice_problem(
        subject=SUBJECT, topic="Mengen", kind="numeric",
        problem_text=(
            "Gegeben sind die Mengen $A = [-5; 4)$ und $B = [0; 9]$. "
            "Bestimme $A \\cap B$ und nenne Minimum und Maximum der Schnittmenge."
        ),
        given=[{"label": "A", "value": "[-5; 4)"}, {"label": "B", "value": "[0; 9]"}],
        steps=[
            {"step_text": "Schnitt: beide Bedingungen gleichzeitig."},
            {"step_text": "Untere Grenze 0 (abgeschlossen), obere 4 (offen)."},
        ],
        final_answer="[0; 4); Min 0, Max existiert nicht (4 nicht enthalten).",
        hints=["Zeichne beide Intervalle auf eine Zahlengerade."],
        source_excerpt="Livetest_Formeln.md – Schnittmenge",
        model="seed",
    )
    print("übung", pid)


def _seed_note() -> None:
    notes = manifest.list_notes(subject=SUBJECT, search="Livetest-Notiz")
    if notes:
        print("notiz da", notes[0]["note_id"])
        return
    nid = manifest.create_note(
        subject=SUBJECT, title="Livetest-Notiz: Grounding",
        body="Nur schreiben, was in der Unterlage steht. Das ist die Livetest-Notiz "
             "für Suche, Export und Karten-aus-Notiz.",
        pinned=True)
    print("notiz", nid)


def _seed_org() -> None:
    exam_day = (date.today() + timedelta(days=21)).isoformat()
    manifest.upsert_exam(SUBJECT, exam_date=exam_day, ects=5, notiz="Livetest-Klausur")
    manifest.upsert_exam(EMPTY_SUBJECT, exam_date=(date.today() + timedelta(days=45)).isoformat(),
                         ects=3, notiz="ohne Unterlagen")
    manifest.upsert_timetable_slot(
        slot_id="livetest-slot-mo", subject=SUBJECT,
        weekday=0, start_time="14:00", end_time="15:30", room="LT1",
        notiz="Livetest-Vorlesung")
    manifest.upsert_task(
        task_id="livetest-task-heute", subject=SUBJECT,
        title="Livetest: Kartenrunde machen", due_date=date.today().isoformat())
    manifest.add_learning_goals(
        SUBJECT,
        ["Testing-Effekt erklären können",
         "Schnittmenge zweier Intervalle bestimmen"],
        source="livetest")
    print("organisation", exam_day)


def _seed_chat() -> None:
    for s in manifest.list_chat_sessions():
        if (s.get("title") or "").startswith("Livetest"):
            print("chat da", s["session_id"])
            return
    sid = manifest.create_chat_session(
        title="Livetest-Chat", subject=SUBJECT,
        messages=[
            {"role": "user", "content": "Was ist der Testing-Effekt?"},
            {"role": "assistant",
             "content": "Aktives Abrufen behält Stoff länger als Nachlesen. [Quelle 1]"},
        ])
    print("chat", sid)


def _seed_sessions() -> None:
    now = time.time()
    existing = manifest.list_study_sessions(subject=SUBJECT)
    if existing:
        print("lernzeit da", len(existing))
        return
    manifest.log_study_session(
        subject=SUBJECT, mode="pomo",
        started_at=now - 1500, ended_at=now - 600, duration_sec=900,
        notiz="Livetest-Pomodoro")
    print("lernzeit session")


def _seed_exam_history() -> None:
    for a in manifest.list_exam_attempts(limit=20):
        items = manifest.list_exam_attempt_items(a["attempt_id"])
        if any((it.get("front") or "").startswith("Livetest") for it in items):
            print("klausur-historie da")
            return
    items = [{
        "card_id": "livetest::def-testing",
        "front": "Livetest: Was ist der Testing-Effekt?",
        "typed": "Abrufen statt nur lesen.",
        "reference": "Aktives Abrufen behält Stoff länger.",
        "score": 80, "feedback": "Kern getroffen.", "fehlt": [],
        "subject": SUBJECT, "topic": "Testing-Effekt",
    }]
    aid = manifest.log_exam_attempt(80, 1, items=items)
    print("klausur-historie", aid)


def main() -> int:
    print("seed Livetest …")
    doc_ids = _seed_docs()
    _seed_cards(doc_ids)
    _seed_practice()
    _seed_note()
    _seed_org()
    _seed_chat()
    _seed_sessions()
    _seed_exam_history()
    print("fertig. Fachfilter in der App: Livetest")
    print("Modulhandbuch-Upload:", FIXTURE_DIR / "Livetest_Modulhandbuch.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
