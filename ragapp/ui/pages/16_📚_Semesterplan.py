"""
RAG-Lernsystem: Seite „Semester einrichten"
==================================================
Liest ein hochgeladenes Modulhandbuch, einen Semesterplan oder eine Studien- oder
Prüfungsordnung per LLM aus und schlägt daraus Fächer samt Klausurtermin,
ECTS und Vorlesungszeiten vor - erst nach Durchsicht/Bearbeitung in der
Vorschau-Tabelle werden ausgewählte Zeilen wirklich in Fortschritt
(Klausurtermine) und Kurse & Stundenplan übernommen. Die hochgeladene
Datei selbst wird NICHT indexiert (siehe ragapp/syllabus_import.py) - wer sie
zusätzlich durchsuchbar haben will, lädt sie separat über Ingestion hoch.
"""
from __future__ import annotations

import sys
import pathlib
from datetime import datetime

_p = pathlib.Path(__file__).resolve()
for _anc in _p.parents:
    if (_anc / "ragapp").is_dir():
        sys.path.insert(0, str(_anc))
        break

import streamlit as st

from ragapp.ui._loading import page_boot, skeleton
page_boot("📚 Semester einrichten", page_title="Semester einrichten", icon="📚",
         layout="wide", accent="semesterplan")

from ragapp.ui._style import card

st.markdown("<style>.block-container{padding-top:2rem;max-width:1000px;}"
            "h1{font-weight:750;letter-spacing:-.5px;}</style>", unsafe_allow_html=True)

with skeleton("Modulhandbuch-Import wird geladen …"):
    import pandas as pd
    from ragapp import manifest, syllabus_import
    from ragapp.config import settings, DATA_DIR
    from ragapp.llm import list_installed_models
    from ragapp.ingestion.loaders import load_document
    from ragapp.ui._progress import ProgressReporter

_TMP_DIR = DATA_DIR / "_syllabus_import_tmp"

_flash = st.session_state.pop("_syllabus_flash", None)
if _flash:
    st.success(_flash)

st.caption("Modulhandbuch prüfen und übernehmen: Klausurtermine, ECTS und Vorlesungszeiten.")


def _model_picker(key: str) -> "str | None":
    _author = settings.author_model()
    _fast = settings.LLM_MODEL_FAST
    _installed = list_installed_models() or []
    _options = [f"🎯 Gründlich ({_author})", f"⚡ Schnell ({_fast})"] + sorted(
        m for m in _installed if m not in (_author, _fast))
    _choice = st.selectbox("Modell", _options, key=key,
                           help="Gründlich liest genauer, Schnell antwortet zügiger.")
    if _choice.startswith("🎯 Gründlich"):
        return None
    if _choice.startswith("⚡ Schnell"):
        return _fast
    return _choice


def _fmt_lectures(lectures: list) -> str:
    if not lectures:
        return "–"
    names = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    parts = [f"{names[l.weekday]} {l.start}–{l.end}" + (f" ({l.room})" if l.room else "")
             for l in lectures]
    return ", ".join(parts)


with card("upload"):
    _upload = st.file_uploader(
        "Modulhandbuch / Semesterplan / Prüfungsordnung", type=["pdf", "docx", "txt", "md"],
        key="syllabus_upload")
    _model_choice = _model_picker("syllabus_model")
    _extract = st.button(
        "🔎 Fächer extrahieren", type="primary",
        disabled=_upload is None, key="syllabus_extract",
        help="Zuerst eine Datei hochladen." if _upload is None else None)
    if _extract and _upload is not None:
        _TMP_DIR.mkdir(parents=True, exist_ok=True)
        _tmp_path = _TMP_DIR / f"_tmp_{_upload.name}"
        _tmp_path.write_bytes(_upload.getvalue())
        try:
            _reporter = ProgressReporter()
            try:
                _doc = load_document(_tmp_path, progress=_reporter)
            finally:
                _reporter.clear()
            with st.spinner("KI liest Fächer/Termine/Zeiten aus dem Dokument …"):
                _status = st.empty()

                def _syllabus_progress(i, n):
                    _status.caption(f"KI liest Abschnitt {i} von {n} …")

                _subjects = syllabus_import.remap_extracted_subjects(
                    syllabus_import.extract_syllabus(
                        _doc.text, model=_model_choice, progress=_syllabus_progress))
                _status.empty()
        except (syllabus_import.SyllabusImportError, ValueError) as exc:
            st.error(str(exc))
        except Exception as exc:  # noqa: BLE001
            st.error(f"Extraktion fehlgeschlagen: {exc}")
        else:
            st.session_state["_syllabus_extracted"] = _subjects
            st.success(f"{len(_subjects)} Fach/Fächer erkannt – unten prüfen und übernehmen.")
        finally:
            _tmp_path.unlink(missing_ok=True)

_extracted = st.session_state.get("_syllabus_extracted")
if _extracted:
    with card("vorschau"):
        st.subheader("Vorschau – bitte prüfen, dann übernehmen")
        st.caption(
            "Häkchen raus = dieses Fach wird NICHT übernommen. Importierte Namen "
            "werden mit bestehenden Fächern und Ordnern abgeglichen (Spalte Abgleich). "
            "Klausurdatum/ECTS sind direkt in der Tabelle korrigierbar."
        )
        _by_code = {s.code: s for s in _extracted}
        _df = pd.DataFrame([{
            "✓": True, "Code": s.code, "Fach": s.label,
            "Abgleich": s.match or "–",
            "Klausurdatum": (datetime.strptime(s.exam_date, "%Y-%m-%d").date()
                            if s.exam_date else None),
            "ECTS": s.ects, "Vorlesungszeiten": _fmt_lectures(s.lectures),
        } for s in _extracted])
        # Echter datetime64-Spaltentyp (statt object mit gemischten date/None-
        # Werten) - erst so rendert data_editor ein fehlendes Klausurdatum als
        # leere Zelle statt als woertlichen Text "None".
        _df["Klausurdatum"] = pd.to_datetime(_df["Klausurdatum"])
        _edited = st.data_editor(
            _df, hide_index=True, use_container_width=True, key="syllabus_preview_editor",
            column_config={
                "✓": st.column_config.CheckboxColumn(width="small"),
                "Code": st.column_config.TextColumn(disabled=True),
                "Fach": st.column_config.TextColumn(disabled=True),
                "Abgleich": st.column_config.TextColumn(disabled=True),
                "Klausurdatum": st.column_config.DateColumn(format="DD.MM.YYYY"),
                "ECTS": st.column_config.NumberColumn(min_value=0.0, max_value=60.0, step=1.0),
                "Vorlesungszeiten": st.column_config.TextColumn(disabled=True),
            },
        )

        c1, c2 = st.columns(2)
        if c1.button("✅ Ausgewählte übernehmen", type="primary", use_container_width=True):
            _selected = syllabus_import.subjects_from_preview_rows(
                [row.to_dict() for _, row in _edited.iterrows()], _by_code)
            if not _selected:
                st.warning("Kein Fach ausgewählt – Häkchen setzen, dann erneut versuchen.")
            else:
                result = syllabus_import.apply_extracted_subjects(_selected)
                st.session_state.pop("_syllabus_extracted", None)
                st.session_state.pop("syllabus_preview_editor", None)
                st.session_state.pop("_syllabus_bytes", None)
                st.session_state.pop("_syllabus_name", None)
                st.session_state["_syllabus_flash"] = (
                    f"Übernommen: **{result['subjects']} Fach/Fächer**, "
                    f"{result['exams']} Klausur-Eintrag/Einträge, "
                    f"{result['slots']} Vorlesungszeit(en). "
                    "Klausur/ECTS: **📈 Fortschritt**. Termine: **🗂️ Kurse & Stundenplan**."
                    " Das Modulhandbuch wurde bewusst nicht als Lernstoff indexiert; "
                    "Skripte und Folien ordnest du unter **🗃️ Dokumente** einem Fach zu."
                )
                st.rerun()
        if c2.button("🗑️ Verwerfen", use_container_width=True):
            st.session_state.pop("_syllabus_extracted", None)
            st.session_state.pop("_syllabus_bytes", None)
            st.session_state.pop("_syllabus_name", None)
            st.rerun()


_already = manifest.list_exams()
_slots_n = len(manifest.list_timetable())
if _already or _slots_n:
    with card("bestand"):
        st.subheader("Bereits übernommen")
        st.caption("Das landet nach dem Import hier – nicht bei den Karteikarten.")

        def _exam_fragment(ex: dict) -> bool:
            subj = (ex.get("subject") or "").strip()
            if ex.get("exam_date"):
                return False
            if subj.isdigit():
                return True
            if subj.count("(") != subj.count(")"):
                return True
            return subj.endswith(("(", "-", "–", "/", "&"))

        _ok_exams = [e for e in _already if not _exam_fragment(e)]
        _frag_exams = [e for e in _already if _exam_fragment(e)]

        def _exam_line(ex: dict) -> str:
            title = ex.get("notiz") or ex["subject"]
            extra = ex["subject"] if ex.get("notiz") and ex["notiz"] != ex["subject"] else None
            bits = []
            if extra:
                bits.append(extra)
            bits.append(ex.get("exam_date") or "kein Klausurdatum")
            if ex.get("ects"):
                bits.append(f"{ex['ects']:g} ECTS")
            return "• **" + title + "** · " + " · ".join(bits)

        for _ex in _ok_exams:
            st.write(_exam_line(_ex))
        if _frag_exams:
            with st.expander(
                    f"Unvollständige Importreste ({len(_frag_exams)})", expanded=False):
                st.caption("Kürzel ohne Klausurdatum, oft abgeschnittene Modulnummern. "
                           "Unter Fortschritt löschen oder einen Termin setzen.")
                for _ex in _frag_exams:
                    st.write(_exam_line(_ex))
        if _slots_n:
            st.write(f"• {_slots_n} Vorlesungszeit(en) unter **🗂️ Kurse & Stundenplan**.")
        else:
            st.caption("Keine Vorlesungszeiten erkannt – die trägst du bei Bedarf unter **🗂️ Kurse & Stundenplan** ein.")
