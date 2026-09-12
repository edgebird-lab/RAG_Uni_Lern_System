"""Tests für ragapp.ics_import.parse_ics() - reine String/Parsing-Logik, keine
Datenbank (siehe Modul-Docstring: schreibt bewusst nichts selbst, Organisation.py
committet erst nach einer Vorschau)."""
from __future__ import annotations

from ragapp.ics_import import parse_ics

_HEADER = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Test//DE\r\n"
_FOOTER = "END:VCALENDAR\r\n"


def _ics(*events: str) -> bytes:
    return (_HEADER + "".join(events) + _FOOTER).encode("utf-8")


def _vevent(summary: str, dtstart: str, dtend: str | None = None,
           rrule: str | None = None, location: str | None = None,
           uid: str = "x") -> str:
    lines = [f"BEGIN:VEVENT\r\nUID:{uid}\r\nDTSTART:{dtstart}\r\n"]
    if dtend:
        lines.append(f"DTEND:{dtend}\r\n")
    if rrule:
        lines.append(f"RRULE:{rrule}\r\n")
    if location:
        lines.append(f"LOCATION:{location}\r\n")
    lines.append(f"SUMMARY:{summary}\r\nEND:VEVENT\r\n")
    return "".join(lines)


def test_explizite_rrule_wird_als_stundenplan_erkannt():
    # 2026-09-14 ist ein Montag.
    content = _ics(_vevent("Mathe", "20260914T080000", "20260914T093000",
                           rrule="FREQ=WEEKLY", location="R101"))
    result = parse_ics(content)
    assert len(result["timetable"]) == 1
    row = result["timetable"][0]
    assert row["subject"] == "Mathe"
    assert row["weekday"] == 0  # Montag
    assert row["start_time"] == "08:00"
    assert row["end_time"] == "09:30"
    assert row["room"] == "R101"
    assert result["tasks"] == []


def test_wiederholte_einzeltermine_ohne_rrule_werden_zusammengefasst():
    # WebUntis-Stil: ein Termin PRO Woche, keine RRULE.
    content = _ics(
        _vevent("Physik", "20260914T100000", "20260914T113000", uid="a"),
        _vevent("Physik", "20260921T100000", "20260921T113000", uid="b"),
        _vevent("Physik", "20260928T100000", "20260928T113000", uid="c"),
    )
    result = parse_ics(content)
    assert len(result["timetable"]) == 1
    assert result["timetable"][0]["subject"] == "Physik"
    assert result["tasks"] == []


def test_einzelner_termin_wird_zur_aufgabe():
    content = _ics(_vevent("Hausarbeit abgeben", "20260920T235900", location="Zuhause"))
    result = parse_ics(content)
    assert result["timetable"] == []
    assert len(result["tasks"]) == 1
    assert result["tasks"][0]["title"] == "Hausarbeit abgeben"
    assert result["tasks"][0]["due_date"] == "2026-09-20"
    assert result["tasks"][0]["notiz"] == "Zuhause"


def test_ganztaegiger_termin_wird_zur_aufgabe_mit_datum():
    content = _ics(_vevent("Projektabgabe", "20260925", uid="allday"))
    result = parse_ics(content)
    assert len(result["tasks"]) == 1
    assert result["tasks"][0]["due_date"] == "2026-09-25"


def test_gemischter_kalender_trennt_stundenplan_und_aufgaben():
    content = _ics(
        _vevent("Mathe", "20260914T080000", "20260914T093000", rrule="FREQ=WEEKLY", uid="m1"),
        _vevent("Referat halten", "20261010T090000", uid="t1"),
    )
    result = parse_ics(content)
    assert len(result["timetable"]) == 1
    assert len(result["tasks"]) == 1
    assert result["tasks"][0]["title"] == "Referat halten"


def test_zwei_verschiedene_faecher_am_selben_tag_bleiben_getrennt():
    content = _ics(
        _vevent("Mathe", "20260914T080000", "20260914T093000", rrule="FREQ=WEEKLY", uid="m1"),
        _vevent("Deutsch", "20260914T100000", "20260914T113000", rrule="FREQ=WEEKLY", uid="d1"),
    )
    result = parse_ics(content)
    assert {r["subject"] for r in result["timetable"]} == {"Mathe", "Deutsch"}


def test_leerer_kalender_liefert_leere_listen():
    result = parse_ics(_ics())
    assert result == {"timetable": [], "tasks": []}


def test_stundenplan_ist_nach_wochentag_und_uhrzeit_sortiert():
    content = _ics(
        _vevent("Deutsch", "20260916T080000", "20260916T093000", rrule="FREQ=WEEKLY", uid="d1"),
        _vevent("Mathe", "20260914T080000", "20260914T093000", rrule="FREQ=WEEKLY", uid="m1"),
    )
    result = parse_ics(content)
    subjects = [r["subject"] for r in result["timetable"]]
    assert subjects == ["Mathe", "Deutsch"]  # Montag vor Mittwoch
