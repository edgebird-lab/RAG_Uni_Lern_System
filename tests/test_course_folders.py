"""Fächer als Ordner anlegen, umbenennen und entfernen (student_flow/manifest).
Isolierte Temp-DB und Temp-Quellordner, niemals echte Nutzerdaten."""
from __future__ import annotations

import pytest

from ragapp import manifest, student_flow as sf


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "MANIFEST_DB", tmp_path / "m.db")
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)
    src = tmp_path / "src"
    src.mkdir()
    monkeypatch.setattr("ragapp.config.SOURCE_DIR", src)
    # Such-Index nie anfassen
    monkeypatch.setattr("ragapp.retrieval.vectorstore.get_vectorstore",
                        lambda: (_ for _ in ()).throw(RuntimeError("kein Index im Test")))
    return src


def _doc(subject, name="a.pdf"):
    manifest.upsert_document(
        doc_id=f"id-{subject}-{name}", content_hash="h", source_path=f"x/{subject}/{name}",
        filename=name, subject=subject, filetype="pdf", num_chunks=0, num_questions=0,
        char_count=1, status="ok", use_rag=False)


def test_create_legt_echten_ordner_an(env):
    assert sf.create_course_folder("  BWL  ") == "BWL"
    assert (env / "BWL").is_dir()


@pytest.mark.parametrize("bad", ["", "  ", "a/b", "a\\b", ".versteckt", "_x", "x" * 81])
def test_ungueltige_namen_werden_abgelehnt(env, bad):
    with pytest.raises(ValueError):
        sf.create_course_folder(bad)


def test_rename_zieht_dokumente_klausur_und_leeren_ordner_nach(env):
    sf.create_course_folder("Alt")
    _doc("Alt")
    manifest.upsert_exam("Alt", exam_date="2030-01-01")
    sf.rename_course("Alt", "Neu")
    assert [d["subject"] for d in manifest.list_documents()] == ["Neu"]
    assert (env / "Neu").is_dir() and not (env / "Alt").exists()
    assert [e["subject"] for e in manifest.list_exams()] == ["Neu"]


def test_rename_laesst_ordner_mit_dateien_stehen(env):
    sf.create_course_folder("Alt")
    (env / "Alt" / "a.pdf").write_bytes(b"x")
    sf.rename_course("Alt", "Neu")
    assert (env / "Alt" / "a.pdf").exists()
    assert (env / "Neu").is_dir()


def test_rename_auf_vorhandenes_fach_scheitert(env):
    sf.create_course_folder("A")
    sf.create_course_folder("B")
    with pytest.raises(ValueError):
        sf.rename_course("A", "B")
    with pytest.raises(ValueError):
        sf.rename_course("A", "b")  # Gross-/Kleinschreibung zählt als vorhanden


def test_delete_blockiert_bei_dokumenten(env):
    sf.create_course_folder("Voll")
    _doc("Voll")
    with pytest.raises(ValueError):
        sf.delete_course_folder("Voll")
    assert (env / "Voll").is_dir()


def test_delete_entfernt_leeren_ordner_und_plan(env):
    sf.create_course_folder("Leer")
    manifest.upsert_timetable_slot(subject="Leer", weekday=1, start_time="08:00",
                                   end_time="09:00")
    sf.delete_course_folder("Leer", drop_plan=True)
    assert not (env / "Leer").exists()
    assert manifest.list_timetable("Leer") == []


def test_delete_behaelt_plan_ohne_haken(env):
    sf.create_course_folder("Leer")
    manifest.upsert_timetable_slot(subject="Leer", weekday=1, start_time="08:00",
                                   end_time="09:00")
    sf.delete_course_folder("Leer")
    assert len(manifest.list_timetable("Leer")) == 1
