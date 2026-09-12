"""Tests für ragapp.syllabus_import (Semesterplan/Studienordnung -> Fächer/
Klausurtermine/Vorlesungszeiten extrahieren). Reine Parsing-Logik + eine
gefakte LLM (keine echte Ollama-Abhängigkeit) + isolierte Temp-DB für
apply_extracted_subjects() (niemals die echte data/manifest.db)."""
from __future__ import annotations

import pandas as pd
import pytest

from ragapp import manifest, syllabus_import as si


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "manifest_test.db"
    monkeypatch.setattr(manifest, "MANIFEST_DB", db_path)
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)
    return db_path


class _FakeLLM:
    def __init__(self, *, result=None, raise_exc=None):
        self._result = result
        self._raise_exc = raise_exc
        self.last_done_reason = "stop"

    def generate_json(self, prompt, system=None, temperature=None):
        self.last_prompt = prompt
        if self._raise_exc:
            raise self._raise_exc
        return self._result


# --------------------------------------------------------------------------- #
# Reine Parsing-Helfer
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("v,expected", [
    ("09:15", "09:15"), ("9:5", "09:05"), ("23:59", "23:59"),
    ("24:00", None), ("9-15", None), (None, None), (930, None),
])
def test_clean_hhmm(v, expected):
    assert si._clean_hhmm(v) == expected


@pytest.mark.parametrize("v,expected", [
    ("2026-07-15", "2026-07-15"), ("2026-02-30", None), ("15.07.2026", None),
    ("", None), (None, None),
])
def test_clean_date(v, expected):
    assert si._clean_date(v) == expected


def test_parse_lectures_gueltige_eintraege():
    raw = [{"weekday": 0, "start": "10:00", "end": "12:00", "room": "H1"},
           {"weekday": 2, "start": "14:15", "end": "15:45", "room": None}]
    out = si._parse_lectures(raw)
    assert len(out) == 2
    assert out[0].weekday == 0 and out[0].room == "H1"
    assert out[1].room is None


def test_parse_lectures_ungueltige_eintraege_werden_uebersprungen():
    raw = [{"weekday": 9, "start": "10:00", "end": "12:00"},   # Wochentag ausserhalb 0-6
           {"weekday": 1, "start": "kaputt", "end": "12:00"},   # Uhrzeit unlesbar
           "nicht-mal-ein-dict",
           {"weekday": 1, "start": "10:00", "end": "12:00"}]    # dieser bleibt gueltig
    out = si._parse_lectures(raw)
    assert len(out) == 1


def test_parse_lectures_kein_list_input_gibt_leere_liste():
    assert si._parse_lectures(None) == []
    assert si._parse_lectures({"weekday": 0}) == []


def test_parse_subjects_normalfall():
    data = [{"code": "DSA", "label": "Algorithmen & Datenstrukturen",
             "exam_date": "2026-07-20", "ects": 6,
             "lectures": [{"weekday": 1, "start": "10:00", "end": "12:00"}]}]
    subjects = si._parse_subjects(data)
    assert len(subjects) == 1
    s = subjects[0]
    assert s.code == "DSA" and s.label == "Algorithmen & Datenstrukturen"
    assert s.exam_date == "2026-07-20" and s.ects == 6.0
    assert len(s.lectures) == 1


def test_parse_subjects_ohne_code_wird_uebersprungen():
    data = [{"label": "Kein Code hier"}, {"code": "OK", "label": "Gueltig"}]
    subjects = si._parse_subjects(data)
    assert len(subjects) == 1 and subjects[0].code == "OK"


def test_parse_subjects_dedupliziert_gleichen_code():
    data = [{"code": "DSA", "label": "Vorlesung"}, {"code": "DSA", "label": "Uebung"}]
    subjects = si._parse_subjects(data)
    assert len(subjects) == 1
    assert subjects[0].label == "Vorlesung"   # zuerst gesehener Eintrag gewinnt


def test_parse_subjects_fehlendes_label_faellt_auf_code_zurueck():
    subjects = si._parse_subjects([{"code": "XY"}])
    assert subjects[0].label == "XY"


def test_parse_subjects_kaputtes_ects_wird_none():
    subjects = si._parse_subjects([{"code": "X", "ects": "sechs"}])
    assert subjects[0].ects is None


def test_parse_subjects_kein_list_input_gibt_leere_liste():
    assert si._parse_subjects({"code": "X"}) == []
    assert si._parse_subjects(None) == []


# --------------------------------------------------------------------------- #
# extract_syllabus()
# --------------------------------------------------------------------------- #
def test_extract_syllabus_ohne_text_wirft_fehler(monkeypatch):
    with pytest.raises(si.SyllabusImportError):
        si.extract_syllabus("   ")


def test_extract_syllabus_llm_fehler_wird_zu_syllabus_error(monkeypatch):
    monkeypatch.setattr(si, "get_llm", lambda model=None: _FakeLLM(raise_exc=RuntimeError("boom")))
    with pytest.raises(si.SyllabusImportError):
        si.extract_syllabus("Irgendein Semesterplan-Text.")


def test_extract_syllabus_keine_faecher_erkannt_wirft_fehler(monkeypatch):
    monkeypatch.setattr(si, "get_llm", lambda model=None: _FakeLLM(result=[]))
    with pytest.raises(si.SyllabusImportError):
        si.extract_syllabus("Text ohne erkennbare Faecher.")


def test_extract_syllabus_erfolgsfall(monkeypatch):
    data = [{"code": "DSA", "label": "Algorithmen", "exam_date": "2026-07-20",
             "ects": 6, "lectures": []}]
    monkeypatch.setattr(si, "get_llm", lambda model=None: _FakeLLM(result=data))
    subjects = si.extract_syllabus("Modulhandbuch Text ...")
    assert len(subjects) == 1
    assert subjects[0].code == "DSA"


def test_extract_syllabus_kappt_text_am_zeichenbudget(monkeypatch):
    fake = _FakeLLM(result=[{"code": "X", "label": "X"}])
    monkeypatch.setattr(si, "get_llm", lambda model=None: fake)
    monkeypatch.setattr(si.settings, "SYLLABUS_IMPORT_MAX_CHARS", 20)
    si.extract_syllabus("A" * 500)
    assert "A" * 500 not in fake.last_prompt
    assert "A" * 20 in fake.last_prompt


# --------------------------------------------------------------------------- #
# apply_extracted_subjects(): schreibt in exams + timetable
# --------------------------------------------------------------------------- #
def test_apply_extracted_subjects_schreibt_exam_und_slots(isolated_db):
    subjects = [si.ExtractedSubject(
        code="DSA", label="Algorithmen", exam_date="2026-07-20", ects=6.0,
        lectures=[si.ExtractedLecture(weekday=1, start="10:00", end="12:00", room="H3")])]
    result = si.apply_extracted_subjects(subjects)
    assert result == {"subjects": 1, "exams": 1, "slots": 1}
    exam = manifest.get_exam("DSA")
    assert exam["exam_date"] == "2026-07-20" and exam["ects"] == 6.0
    slots = manifest.list_timetable("DSA")
    assert len(slots) == 1 and slots[0]["room"] == "H3"


def test_apply_extracted_subjects_ohne_termin_und_ects_legt_keinen_exam_an(isolated_db):
    subjects = [si.ExtractedSubject(code="X", label="X", lectures=[
        si.ExtractedLecture(weekday=0, start="08:00", end="10:00")])]
    result = si.apply_extracted_subjects(subjects)
    assert result["exams"] == 0 and result["slots"] == 1
    assert manifest.get_exam("X") is None


# --------------------------------------------------------------------------- #
# subjects_from_preview_rows(): baut ExtractedSubject aus den (ggf. vom Nutzer
# bearbeiteten) st.data_editor-Zeilen - Regressionstest für einen real
# gefundenen Bug: pandas.Timestamp.isoformat() liefert einen vollen Datum-UND-
# Zeit-String statt 'YYYY-MM-DD', und pd.NaT.isoformat() liefert faelschlich
# den String 'NaT' statt kein Datum.
# --------------------------------------------------------------------------- #
def test_subjects_from_preview_rows_timestamp_wird_auf_datum_gekuerzt():
    orig = {"DSA": si.ExtractedSubject(code="DSA", label="Algorithmen")}
    rows = [{"✓": True, "Code": "DSA", "Klausurdatum": pd.Timestamp("2027-02-12"), "ECTS": 6.0}]
    out = si.subjects_from_preview_rows(rows, orig)
    assert len(out) == 1
    assert out[0].exam_date == "2027-02-12"


def test_subjects_from_preview_rows_nat_wird_zu_none_nicht_zum_string_nat():
    orig = {"WA": si.ExtractedSubject(code="WA", label="Wiss. Arbeiten")}
    rows = [{"✓": True, "Code": "WA", "Klausurdatum": pd.NaT, "ECTS": None}]
    out = si.subjects_from_preview_rows(rows, orig)
    assert out[0].exam_date is None
    assert out[0].ects is None


def test_subjects_from_preview_rows_abgewaehlte_zeile_wird_uebersprungen():
    orig = {"DSA": si.ExtractedSubject(code="DSA", label="Algorithmen")}
    rows = [{"✓": False, "Code": "DSA", "Klausurdatum": pd.NaT, "ECTS": None}]
    assert si.subjects_from_preview_rows(rows, orig) == []


def test_subjects_from_preview_rows_unbekannter_code_wird_uebersprungen():
    rows = [{"✓": True, "Code": "UNBEKANNT", "Klausurdatum": pd.NaT, "ECTS": None}]
    assert si.subjects_from_preview_rows(rows, {}) == []


def test_subjects_from_preview_rows_behaelt_vorlesungszeiten_vom_original():
    lec = si.ExtractedLecture(weekday=0, start="10:00", end="12:00", room="H3")
    orig = {"DSA": si.ExtractedSubject(code="DSA", label="Algorithmen", lectures=[lec])}
    rows = [{"✓": True, "Code": "DSA", "Klausurdatum": pd.NaT, "ECTS": None}]
    out = si.subjects_from_preview_rows(rows, orig)
    assert out[0].lectures == [lec]


def test_apply_extracted_subjects_ueberschreibt_bestehende_note_nicht(isolated_db):
    # Nutzer hat fuer "DSA" schon eine Note eingetragen (vom letzten Semester) -
    # ein (erneuter) Import mit neuem Termin darf diese Note NICHT loeschen.
    manifest.upsert_exam("DSA", exam_date="2025-07-20", ects=6.0, note=1.7)
    subjects = [si.ExtractedSubject(code="DSA", label="Algorithmen",
                                    exam_date="2026-07-20", ects=6.0)]
    si.apply_extracted_subjects(subjects)
    exam = manifest.get_exam("DSA")
    assert exam["exam_date"] == "2026-07-20"   # neuer Termin uebernommen
    assert exam["note"] == 1.7                  # alte Note erhalten
