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

    def generate_json(self, prompt, system=None, temperature=None, **kwargs):
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


def test_chunk_syllabus_text_ueberlappt_und_deckt_das_ende():
    text = "".join(chr(65 + (i % 26)) for i in range(20000))
    chunks = si._chunk_syllabus_text(text, 8000, 700)
    assert len(chunks) >= 3
    assert chunks[0] == text[:8000]
    assert chunks[-1].endswith(text[-20:])
    for a, b in zip(chunks, chunks[1:]):
        assert a[-700:] == b[:700]


def test_chunk_syllabus_text_bevorzugt_seitengrenzen():
    pages = [f"Seite{i} " + ("x" * 80) for i in range(6)]
    text = "\f".join(pages)
    chunks = si._chunk_syllabus_text(text, size=250, overlap=40)
    joined = "\n".join(chunks)
    for i in range(6):
        assert f"Seite{i}" in joined


def test_merge_subject_lists_fuellt_luecken_und_vorlesungen():
    a = [si.ExtractedSubject(
        code="DSA", label="DSA", exam_date=None, ects=None,
        lectures=[si.ExtractedLecture(1, "10:00", "12:00", "H1")])]
    b = [si.ExtractedSubject(
        code="DSA", label="Algorithmen", exam_date="2026-07-20", ects=6.0,
        lectures=[si.ExtractedLecture(3, "14:00", "16:00", None)])]
    out = si._merge_subject_lists([a, b])
    assert len(out) == 1
    s = out[0]
    assert s.label == "Algorithmen"
    assert s.exam_date == "2026-07-20" and s.ects == 6.0
    assert len(s.lectures) == 2


@pytest.fixture(autouse=True)
def _skip_vram_guard(monkeypatch):
    """extract_syllabus() nutzt llm_task (VRAM-Check + Entladen) – in Unit-Tests
    ohne echten Ollama-Aufruf ueberspringen."""
    from contextlib import nullcontext
    monkeypatch.setattr(si, "llm_task", lambda model=None: nullcontext())


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


def test_extract_syllabus_liest_langen_text_in_mehreren_chunks(monkeypatch):
    """70-Seiten-PDFs passen nicht in einen Prompt: jeder Chunk wird gelesen,
    Faecher aus allen Abschnitten werden zusammengefuehrt."""
    calls: list[str] = []

    class _ChunkLLM:
        last_done_reason = "stop"

        def generate_json(self, prompt, system=None, temperature=None, **kwargs):
            calls.append(prompt)
            if "FachAlpha" in prompt:
                return [{"code": "A", "label": "FachAlpha"}]
            return [{"code": "B", "label": "FachBeta", "exam_date": "2026-07-20", "ects": 5}]

    monkeypatch.setattr(si, "get_llm", lambda model=None: _ChunkLLM())
    monkeypatch.setattr(si.settings, "SYLLABUS_IMPORT_MAX_CHARS", 800)
    monkeypatch.setattr(si.settings, "SYLLABUS_CHUNK_OVERLAP", 80)
    text = ("FachAlpha Modulbeschreibung " * 80) + ("FachBeta Klausur 20.07. " * 80)
    subjects = si.extract_syllabus(text)
    assert len(calls) >= 2
    assert {s.code for s in subjects} == {"A", "B"}
    beta = next(s for s in subjects if s.code == "B")
    assert beta.exam_date == "2026-07-20" and beta.ects == 5.0


# --------------------------------------------------------------------------- #
# apply_extracted_subjects(): schreibt in exams + timetable
# --------------------------------------------------------------------------- #
def test_apply_extracted_subjects_schreibt_exam_und_slots(isolated_db):
    subjects = [si.ExtractedSubject(
        code="DSA", label="Algorithmen", exam_date="2026-07-20", ects=6.0,
        lectures=[si.ExtractedLecture(weekday=1, start="10:00", end="12:00", room="H3")])]
    result = si.apply_extracted_subjects(subjects)
    assert result["subjects"] == 1 and result["exams"] == 1 and result["slots"] == 1
    exam = manifest.get_exam("DSA")
    assert exam["exam_date"] == "2026-07-20" and exam["ects"] == 6.0
    slots = manifest.list_timetable("DSA")
    assert len(slots) == 1 and slots[0]["room"] == "H3"


def test_apply_extracted_subjects_ohne_termin_und_ects_legt_trotzdem_ein_fach_an(isolated_db):
    subjects = [si.ExtractedSubject(code="X", label="X", lectures=[
        si.ExtractedLecture(weekday=0, start="08:00", end="10:00")])]
    result = si.apply_extracted_subjects(subjects)
    assert result["exams"] == 1 and result["slots"] == 1
    exam = manifest.get_exam("X")
    assert exam is not None
    assert exam["exam_date"] is None and exam["ects"] is None


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


def test_apply_extracted_subjects_legt_label_als_notiz_ab(isolated_db):
    subjects = [si.ExtractedSubject(code="M31", label="Unternehmensführung", ects=5.0)]
    si.apply_extracted_subjects(subjects)
    exam = manifest.get_exam("M31")
    assert exam["notiz"] == "Unternehmensführung"
    assert exam["ects"] == 5.0


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


def test_resolve_subject_code_gleicht_label_ab():
    info = si.resolve_subject_code("ALG", "Algorithmen & Datenstrukturen",
                                   known={"DSA", "KuLR"})
    assert info["code"] == "DSA"
    assert info["via"] == "label"
    assert info["new"] is False


def test_resolve_subject_code_neuer_kurs_bleibt_eigener_code():
    info = si.resolve_subject_code("NEU", "Neues Wahlfach", known={"DSA"})
    assert info["code"] == "NEU"
    assert info["new"] is True


def test_remap_extracted_subjects_vermeidet_dublette(isolated_db, tmp_path, monkeypatch):
    src = tmp_path / "quellen"
    (src / "KuLR").mkdir(parents=True)
    monkeypatch.setattr("ragapp.config.SOURCE_DIR", src)
    subjects = [
        si.ExtractedSubject(code="ALG", label="Algorithmen & Datenstrukturen"),
        si.ExtractedSubject(code="kulr", label="Kosten"),
    ]
    out = si.remap_extracted_subjects(subjects)
    assert out[0].code == "DSA"
    assert "bestehendes Fach" in (out[0].match or "")
    assert out[1].code == "KuLR"


def test_apply_extracted_subjects_legt_fachordner_an(isolated_db, tmp_path, monkeypatch):
    src = tmp_path / "quellen"
    monkeypatch.setattr("ragapp.config.SOURCE_DIR", src)
    subjects = [si.ExtractedSubject(code="WahlA", label="Wahlmodul A", ects=5.0)]
    result = si.apply_extracted_subjects(subjects)
    assert (src / "WahlA").is_dir()
    assert result["folders"] == 1
