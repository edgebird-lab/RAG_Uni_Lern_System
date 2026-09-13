"""
RAG-Lernsystem: Seite „Semesterplan importieren"
==================================================
Liest einen hochgeladenen Semesterplan/ein Modulhandbuch/eine Studien- oder
Prüfungsordnung per LLM aus und schlägt daraus Fächer samt Klausurtermin,
ECTS und Vorlesungszeiten vor - erst nach Durchsicht/Bearbeitung in der
Vorschau-Tabelle werden ausgewählte Zeilen wirklich in Fortschritt
(Klausurtermine) und Organisation (Stundenplan) übernommen. Die hochgeladene
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
page_boot("📚 Semesterplan importieren", page_title="Semesterplan", icon="📚",
         layout="wide", accent="semesterplan")

from ragapp.ui._style import card

st.markdown("<style>.block-container{padding-top:2rem;max-width:1000px;}"
            "h1{font-weight:750;letter-spacing:-.5px;}</style>", unsafe_allow_html=True)

with skeleton("Semesterplan-Import wird geladen …"):
    import pandas as pd
    from ragapp import manifest, syllabus_import
    from ragapp.config import settings, DATA_DIR
    from ragapp.llm import list_installed_models
    from ragapp.ingestion.loaders import load_document
    from ragapp.ui._progress import ProgressReporter

_TMP_DIR = DATA_DIR / "_syllabus_import_tmp"

st.caption(
    "Lade einen Semesterplan, ein Modulhandbuch oder deine Studien-/Prüfungsordnung "
    "hoch (PDF, Word, Text oder Markdown) - die KI schlägt daraus Fächer mit "
    "Klausurtermin, ECTS und Vorlesungszeiten vor. Du siehst und bearbeitest den "
    "Vorschlag, BEVOR irgendetwas gespeichert wird."
)


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
        "Semesterplan/Modulhandbuch/Prüfungsordnung", type=["pdf", "docx", "txt", "md"],
        key="syllabus_upload")
    _model_choice = _model_picker("syllabus_model")

    if _upload is not None and st.button("🔎 Fächer extrahieren", type="primary"):
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
                _subjects = syllabus_import.extract_syllabus(_doc.text, model=_model_choice)
        except (syllabus_import.SyllabusImportError, ValueError) as exc:
            st.error(str(exc))
        except Exception as exc:  # noqa: BLE001
            st.error(f"Extraktion fehlgeschlagen: {exc}")
        else:
            st.session_state["_syllabus_extracted"] = _subjects
            st.session_state["_syllabus_bytes"] = _upload.getvalue()
            st.session_state["_syllabus_name"] = _upload.name
            st.success(f"{len(_subjects)} Fach/Fächer erkannt – unten prüfen und übernehmen.")
        finally:
            _tmp_path.unlink(missing_ok=True)

_extracted = st.session_state.get("_syllabus_extracted")
if _extracted:
    with card("vorschau"):
        st.subheader("Vorschau – bitte prüfen, dann übernehmen")
        st.caption(
            "Häkchen raus = dieses Fach wird NICHT übernommen. Klausurdatum/ECTS "
            "sind direkt in der Tabelle korrigierbar. Vorlesungszeiten werden "
            "unverändert wie erkannt übernommen (bei Bedarf danach auf "
            "**🗂️ Organisation** anpassen)."
        )
        _by_code = {s.code: s for s in _extracted}
        _df = pd.DataFrame([{
            "✓": True, "Code": s.code, "Fach": s.label,
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
                _raw = st.session_state.pop("_syllabus_bytes", None)
                _name = st.session_state.pop("_syllabus_name", "semesterplan.pdf")
                if _raw:
                    from ragapp.config import INBOX_DIR
                    from ragapp.ingestion.pipeline import ingest_file
                    _dest = INBOX_DIR / _name
                    _dest.write_bytes(_raw)
                    try:
                        ingest_file(_dest, use_rag=True)
                        st.info("Das Dokument wurde zusätzlich indexiert (Chat/Karten).")
                    except Exception as _iexc:  # noqa: BLE001
                        st.warning(f"Indexieren übersprungen: {_iexc}")
                _first = getattr(_selected[0], "code", None) if _selected else None
                st.success(
                    f"Übernommen: {result['subjects']} Fach/Fächer, "
                    f"{result['exams']} Klausurtermin(e), {result['slots']} Vorlesungszeit(en). "
                    "Zu finden auf **📈 Fortschritt** (Klausurtermine) und "
                    "**🗂️ Organisation** (Stundenplan)."
                )
                if _first:
                    st.session_state["study_prefill"] = {"subject": _first, "limit": 12}
                    st.caption(f"Nächster Schritt: Karten für **{_first}** auf 🎓 Karteikarten.")
                st.rerun()
        if c2.button("🗑️ Verwerfen", use_container_width=True):
            st.session_state.pop("_syllabus_extracted", None)
            st.rerun()
