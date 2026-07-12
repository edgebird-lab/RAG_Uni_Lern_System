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
