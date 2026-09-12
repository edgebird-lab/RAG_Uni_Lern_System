"""
.ics-Import (Stundenplan/Termine)
=================================
Viele Schulverwaltungen (WebUntis, DSB Mobile) und auch Uni-/private Kalender
(Outlook, Google Kalender) exportieren einen Kalender als offene, standardisierte
.ics-Datei (iCalendar, RFC 5545) - im Gegensatz zu z. B. einer OneNote-API
BRAUCHT das kein OAuth/Konto, nur die (einmal heruntergeladene oder abonnierte)
Datei selbst, bleibt also mit dem Offline-Grundsatz der App vereinbar.

Reine PARSE-Funktion, schreibt NICHTS in die Datenbank - der Aufruf (siehe
Organisation.py) zeigt erst eine Vorschau, der Nutzer waehlt aus, ERST DANACH
committet die Seite ausgewaehlte Zeilen ueber die schon vorhandenen
``manifest.upsert_timetable_slot()``/``manifest.upsert_task()``-Funktionen.

Zwei Ziel-Kategorien, bewusst OHNE eine dritte fuer Klausuren:
- ``timetable``: woechentlich wiederkehrende Termine (eine Unterrichtsstunde) -
  passen ins bestehende Stundenplan-Modell (Wochentag + Uhrzeit).
- ``tasks``: alles andere (einmalige Termine/Abgaben/Deadlines).
Klausurtermine (``manifest.exams``) werden bewusst NICHT automatisch befuellt:
dort ist ``subject`` Primary Key (ein Termin PRO Fach) - eine falsch erkannte
"Klausur" wuerde eine schon bestehende stillschweigend ueberschreiben. Der
Nutzer kann eine importierte Aufgabe bei Bedarf manuell zur Klausur befoerdern
(Seite Fortschritt).

Erkennung woechentlicher Wiederholung ZWEIGLEISIG, weil beide Exportstile in
freier Wildbahn vorkommen:
1. Eine echte RRULE mit FREQ=WEEKLY (Outlook/Google-Stil).
2. KEINE RRULE, aber mehrere Einzeltermine mit gleichem Fach/Wochentag/Uhrzeit
   an verschiedenen Tagen (typischer WebUntis-Exportstil: ein Termin PRO
   Semesterwoche statt einer Wiederholungsregel).
"""
from __future__ import annotations

import datetime as _dt
from collections import defaultdict
from typing import Any


def parse_ics(content: bytes) -> dict[str, list[dict[str, Any]]]:
    """Liest eine .ics-Datei und liefert ``{"timetable": [...], "tasks": [...]}``
    fuer eine Vorschau vor dem eigentlichen Import (siehe Modul-Docstring).
    Wirft bei kaputtem/leerem Inhalt eine Exception - der Aufrufer faengt das
    ab und zeigt eine Fehlermeldung (siehe Organisation.py)."""
    from icalendar import Calendar

    cal = Calendar.from_ical(content)

    occurrences: list[dict[str, Any]] = []
    for comp in cal.walk():
        if comp.name != "VEVENT":
            continue
        summary = str(comp.get("summary", "") or "").strip()
        dtstart = comp.get("dtstart")
        if not summary or dtstart is None:
            continue
        dt = dtstart.dt
        location = str(comp.get("location", "") or "").strip() or None

        rrule = comp.get("rrule")
        explicit_weekly = False
        if rrule is not None:
            freqs = [str(f).upper() for f in (rrule.get("FREQ") or [])]
            explicit_weekly = "WEEKLY" in freqs

        if isinstance(dt, _dt.datetime):
            weekday = dt.weekday()
            start_time = dt.strftime("%H:%M")
            dtend = comp.get("dtend")
            end_dt = dtend.dt if dtend is not None else None
            end_time = (end_dt.strftime("%H:%M")
                        if isinstance(end_dt, _dt.datetime) else start_time)
            date_iso = dt.date().isoformat()
        else:  # datetime.date - ganztaegiger Termin, kann keine Unterrichtsstunde sein
            weekday = dt.weekday()
            start_time = None
            end_time = None
            date_iso = dt.isoformat()

        occurrences.append({
            "subject": summary, "weekday": weekday, "start_time": start_time,
            "end_time": end_time, "room": location, "date": date_iso,
            "explicit_weekly": explicit_weekly,
        })

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for o in occurrences:
        if o["start_time"] is None:
            continue
        key = (o["subject"], o["weekday"], o["start_time"], o["end_time"])
        groups[key].append(o)

    timetable_rows: list[dict[str, Any]] = []
    recurring_markers: set[tuple] = set()
    for (subject, weekday, start_time, end_time), occs in groups.items():
        distinct_dates = {o["date"] for o in occs}
        is_recurring = len(distinct_dates) >= 2 or any(o["explicit_weekly"] for o in occs)
        if not is_recurring:
            continue
        timetable_rows.append({
            "subject": subject, "weekday": weekday, "start_time": start_time,
            "end_time": end_time, "room": occs[0]["room"],
        })
        for o in occs:
            recurring_markers.add((o["subject"], o["date"], o["start_time"]))

    task_rows = [
        {"title": o["subject"], "due_date": o["date"], "notiz": o["room"]}
        for o in occurrences
        if (o["subject"], o["date"], o["start_time"]) not in recurring_markers
    ]

    # Stundenplan nach Wochentag/Uhrzeit sortiert, Aufgaben nach Datum - reine
    # Vorschau-Ergonomie (gleiche Sortierung wie manifest.list_timetable()/
    # list_tasks()).
    timetable_rows.sort(key=lambda r: (r["weekday"], r["start_time"]))
    task_rows.sort(key=lambda r: (r["due_date"] is None, r["due_date"], r["title"]))
    return {"timetable": timetable_rows, "tasks": task_rows}
