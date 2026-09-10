"""
Lernplaner (Prioritaet nach Klausurnaehe & Wissensluecke)
=========================================================
Die App hat einen einzigen Zweck: das Lernen fuer eine bestimmte Klausur. Dieser
Planer macht die Klausurnaehe nutzbar. Fuer jedes Fach berechnet er einen
Prioritaets-Score:

    prio = Dringlichkeit(Tage bis Klausur) x (0.3 + Wissensluecke) x Gewicht

- Dringlichkeit steigt, je naeher der Termin ist (ohne Termin: Grundwert).
- Wissensluecke = 1 - Mastery (Anteil sitzender Karten, aus analytics).
- Gewicht kommt aus dem Klausurtermin (ECTS/manuell).

Rein rechnerisch, offline. Grundlage fuer die Fortschritt-Seite (Phase 0) und
spaeter fuer die faecheruebergreifende Pruefungsphasen-Runde (Phase 4).
"""
from __future__ import annotations

import time
from datetime import date
from typing import Optional

from ragapp import analytics, manifest
from ragapp.config import settings


def days_to_exam(exam_date: Optional[str], now: Optional[float] = None) -> Optional[int]:
    """Tage bis zum Klausurdatum (ISO 'YYYY-MM-DD'). Negativ = vorbei, None = kein Termin."""
    if not exam_date:
        return None
    try:
        y, m, d = (int(x) for x in str(exam_date).split("-")[:3])
        target = date(y, m, d)
    except Exception:  # noqa: BLE001
        return None
    today = date.fromtimestamp(now if now is not None else time.time())
    return (target - today).days


def urgency(days: Optional[int], horizon: Optional[int] = None) -> float:
    """Dringlichkeit 0.05..1.0. Ohne Termin -> Grundwert 0.3; heute/vorbei -> 1.0."""
    H = float(horizon if horizon is not None else getattr(settings, "PLANNER_URGENCY_DAYS", 30)) or 30.0
    if days is None:
        return 0.3
    if days <= 0:
        return 1.0
    return max(0.05, min(1.0, 1.0 - days / H))


def subject_priority(subject: str, exam: Optional[dict] = None) -> dict:
    """Prioritaets-Datensatz fuer ein Fach (mit Zwischenwerten fuer die Anzeige)."""
    exam = exam if exam is not None else manifest.get_exam(subject)
    exam_date = (exam or {}).get("exam_date")
    dte = days_to_exam(exam_date)
    mastery = analytics.subject_mastery(subject)      # 0..1
    gap = 1.0 - mastery
    weight = float((exam or {}).get("gewicht") or 1.0)
    prio = urgency(dte) * (0.3 + gap) * weight
    return {
        "subject": subject, "exam_date": exam_date, "days_to_exam": dte,
        "mastery_pct": round(100 * mastery), "weight": weight,
        "priority": round(prio, 3),
    }


def all_priorities() -> list[dict]:
    """Alle Faecher (mit Karten oder mit Termin), nach Prioritaet absteigend."""
    subjects = set(manifest.study_subjects())
    exams = manifest.exam_map()
    subjects |= set(exams.keys())
    out = [subject_priority(s, exams.get(s)) for s in sorted(subjects)]
    out.sort(key=lambda x: x["priority"], reverse=True)
    return out


def phase_round(limit: int = 20, cram: bool = False,
                per_subject_cap: Optional[int] = None) -> list[dict]:
    """Faecheruebergreifende Pruefungsphasen-Runde: zieht faellige Karten je Fach und
    mischt sie im gewichteten Round-Robin (nach Prioritaet) - nie zwei gleiche Faecher
    hintereinander. Interleaving UEBER Faecher hinweg verbessert nachweislich die
    Unterscheidung (Rohrer & Taylor; Kornell & Bjork). ``cram`` fuellt bei Bedarf mit
    schwachen, noch nicht faelligen Karten auf."""
    from collections import deque
    from ragapp import manifest
    prios = all_priorities()
    order, queues = [], {}
    for p in prios:
        s = p["subject"]
        cards = manifest.get_due_cards(s, limit=int(per_subject_cap or limit), cram=cram)
        if cards:
            order.append(s)
            queues[s] = deque(cards)
    if not queues:
        return []
    out: list[dict] = []
    last = None
    while len(out) < int(limit) and any(queues.values()):
        picked = next((s for s in order if queues[s] and s != last), None)
        if picked is None:  # nur noch das zuletzt genutzte Fach hat Karten
            picked = next((s for s in order if queues[s]), None)
        if picked is None:
            break
        out.append(queues[picked].popleft())
        last = picked
    return out


def exams_to_ics() -> str:
    """Alle Klausurtermine als iCalendar (.ics) – Ganztags-Termine, importierbar in
    Google/Apple/Outlook-Kalender. Leer, wenn kein Termin ein Datum hat."""
    from datetime import date, timedelta
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0",
             "PRODID:-//RAG-Lernsystem//Klausurtermine//DE", "CALSCALE:GREGORIAN"]
    n = 0
    for e in manifest.list_exams():
        ed = e.get("exam_date")
        if not ed:
            continue
        start = ed.replace("-", "")
        try:
            y, m, d = (int(x) for x in ed.split("-")[:3])
            end = (date(y, m, d) + timedelta(days=1)).strftime("%Y%m%d")
        except Exception:  # noqa: BLE001
            end = start
        subj = e["subject"]
        lines += ["BEGIN:VEVENT", f"UID:klausur-{subj}@rag-lernsystem",
                  f"DTSTART;VALUE=DATE:{start}", f"DTEND;VALUE=DATE:{end}",
                  f"SUMMARY:Klausur {subj}", "END:VEVENT"]
        n += 1
    lines.append("END:VCALENDAR")
    return ("\r\n".join(lines) + "\r\n") if n else ""


def organizer_to_ics() -> str:
    """Kombinierter Kalender-Export der Seite 'Organisation': Klausurtermine +
    Aufgaben-Fristen (Einzeltermine) + Stundenplan (woechentlich wiederkehrend via
    RRULE). Importierbar in Google/Apple/Outlook-Kalender."""
    from datetime import date, timedelta
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0",
             "PRODID:-//RAG-Lernsystem//Organisation//DE", "CALSCALE:GREGORIAN"]
    n = 0
    for e in manifest.list_exams():
        ed = e.get("exam_date")
        if not ed:
            continue
        start = ed.replace("-", "")
        try:
            y, m, d = (int(x) for x in ed.split("-")[:3])
            end = (date(y, m, d) + timedelta(days=1)).strftime("%Y%m%d")
        except Exception:  # noqa: BLE001
            end = start
        lines += ["BEGIN:VEVENT", f"UID:klausur-{e['subject']}@rag-lernsystem",
                  f"DTSTART;VALUE=DATE:{start}", f"DTEND;VALUE=DATE:{end}",
                  f"SUMMARY:Klausur {e['subject']}", "END:VEVENT"]
        n += 1

    for t in manifest.list_tasks(include_done=False):
        ed = t.get("due_date")
        if not ed:
            continue
        start = ed.replace("-", "")
        try:
            y, m, d = (int(x) for x in ed.split("-")[:3])
            end = (date(y, m, d) + timedelta(days=1)).strftime("%Y%m%d")
        except Exception:  # noqa: BLE001
            end = start
        summary = f"Frist: {t['title']}" + (f" ({t['subject']})" if t.get("subject") else "")
        lines += ["BEGIN:VEVENT", f"UID:aufgabe-{t['task_id']}@rag-lernsystem",
                  f"DTSTART;VALUE=DATE:{start}", f"DTEND;VALUE=DATE:{end}",
                  f"SUMMARY:{summary}", "END:VEVENT"]
        n += 1

    _WD_ICS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
    _today = date.today()
    for slot in manifest.list_timetable():
        try:
            wd = int(slot["weekday"]) % 7
            sh, sm = (int(x) for x in slot["start_time"].split(":")[:2])
            eh, em = (int(x) for x in slot["end_time"].split(":")[:2])
        except Exception:  # noqa: BLE001
            continue
        # Erste zukuenftige Instanz dieses Wochentags als DTSTART; RRULE laesst den
        # Termin danach woechentlich wiederkehren.
        first = _today + timedelta(days=(wd - _today.weekday()) % 7)
        dtstart = f"{first.strftime('%Y%m%d')}T{sh:02d}{sm:02d}00"
        dtend = f"{first.strftime('%Y%m%d')}T{eh:02d}{em:02d}00"
        summary = slot["subject"] + (f" ({slot['room']})" if slot.get("room") else "")
        lines += ["BEGIN:VEVENT", f"UID:stunde-{slot['slot_id']}@rag-lernsystem",
                  f"DTSTART:{dtstart}", f"DTEND:{dtend}",
                  f"RRULE:FREQ=WEEKLY;BYDAY={_WD_ICS[wd]}",
                  f"SUMMARY:{summary}", "END:VEVENT"]
        n += 1

    # Lernplan-Bloecke: pro Plan+Tag zu EINEM Ganztags-Termin gebuendelt (sonst
    # waeren es bei 25-Min-Bloecken schnell viele Mini-Termine). Nur offene
    # Bloecke - erledigte (siehe sync_plan_status) sind kein Planungsgegenstand mehr.
    _by_plan_day: dict[tuple[str, str], list[dict]] = {}
    for b in manifest.list_plan_blocks_detailed():
        if b["done"]:
            continue
        _by_plan_day.setdefault((b["plan_id"], b["planned_date"]), []).append(b)
    for (plan_id, day), day_blocks in _by_plan_day.items():
        try:
            y, m, d = (int(x) for x in day.split("-")[:3])
            end = (date(y, m, d) + timedelta(days=1)).strftime("%Y%m%d")
        except Exception:  # noqa: BLE001
            end = day.replace("-", "")
        total_min = sum(bl["planned_min"] for bl in day_blocks)
        summary = f"Lernplan: {day_blocks[0]['plan_title']} ({total_min} Min)"
        lines += ["BEGIN:VEVENT", f"UID:lernplan-{plan_id}-{day}@rag-lernsystem",
                  f"DTSTART;VALUE=DATE:{day.replace('-', '')}",
                  f"DTEND;VALUE=DATE:{end}", f"SUMMARY:{summary}", "END:VEVENT"]
        n += 1

    lines.append("END:VCALENDAR")
    return ("\r\n".join(lines) + "\r\n") if n else ""


def humanize_days(days: Optional[int]) -> str:
    """Menschliche Beschreibung des Abstands zur Klausur."""
    if days is None:
        return "kein Termin"
    if days < 0:
        return f"vor {abs(days)} Tagen"
    if days == 0:
        return "heute!"
    if days == 1:
        return "morgen"
    if days < 14:
        return f"in {days} Tagen"
    if days < 70:
        return f"in {round(days / 7)} Wochen"
    return f"in {round(days / 30)} Monaten"
