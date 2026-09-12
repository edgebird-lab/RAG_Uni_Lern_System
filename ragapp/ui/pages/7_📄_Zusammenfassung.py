"""
RAG-Lernsystem: Seite „Zusammenfassung schreiben"
=================================================
Erzeugt aus einem indexierten Dokument oder allen Inhalten eines Fachs eine
strukturierte, klausurtaugliche Markdown-Zusammenfassung (gegroundet, grosses
Autoren-Modell). Anzeige + Download; schreibt zusaetzlich nach docs/.
"""
from __future__ import annotations

import sys
import pathlib

_p = pathlib.Path(__file__).resolve()
for _anc in _p.parents:
    if (_anc / "ragapp").is_dir():
        sys.path.insert(0, str(_anc))
        break

import streamlit as st

from ragapp.ui._loading import page_boot, skeleton
page_boot("📄 Zusammenfassung schreiben", page_title="Zusammenfassung",
          icon="📄", layout="wide", accent="zusammenfassung")

from ragapp.ui._style import card

st.markdown("<style>.block-container{padding-top:2rem;max-width:900px;}"
            "h1{font-weight:750;letter-spacing:-.5px;}</style>", unsafe_allow_html=True)

with skeleton("Zusammenfassung wird geladen …"):
    from ragapp import manifest
    from ragapp.config import settings, SUBJECT_LABELS
    from ragapp.ingestion import summarize
    from ragapp.ingestion.summarize import SummaryStats
    from ragapp.ui._progress import progress_tracker


def _fach(code: str) -> str:
    return SUBJECT_LABELS.get(code, code)


st.caption("Erzeugt aus einem indexierten Dokument oder einem ganzen Fach eine "
           "strukturierte, klausurtaugliche Zusammenfassung – gegroundet, es wird "
           "nur der Quellinhalt verwendet.")

docs = manifest.list_documents()
if not docs:
    st.info("Noch keine Dokumente indexiert – lege zuerst welche über **📥 Import** an.")
    st.stop()

subjects = sorted({d["subject"] for d in docs if d["subject"]})

with card("quelle"):
    quelle = st.radio("Quelle", ["Dokument", "Fach"], horizontal=True)

    if quelle == "Dokument":
        opts = {d["doc_id"]: f'{d["filename"]}  ·  {_fach(d["subject"] or "")}' for d in docs}
        target = st.selectbox("Dokument", list(opts), format_func=lambda k: opts[k])
        mode = "document"
    else:
        target = st.selectbox("Fach", subjects, format_func=_fach)
        mode = "subject"
        st.warning("Fach-Modus fasst **alle** Chunks des Fachs abschnittsweise zusammen. "
                   "Bei vielen Dokumenten kann das längere Zeit dauern.")

    model = (getattr(settings, "LLM_MODEL_AUTHOR", "") or settings.LLM_MODEL)
    st.caption(f"Autoren-Modell: `{model}`. Das kann je nach Umfang etwas dauern.")

    if st.button("📝 Zusammenfassung erzeugen", type="primary", use_container_width=True):
        _zus_bar = st.progress(0.0)
        _zus_cap = st.empty()
        status = st.empty()
        stats = SummaryStats()
        _tracker = progress_tracker(_zus_bar, _zus_cap, "Zusammenfassung")

        def _prog(msg: str) -> None:
            status.caption(msg)
            # write_summary() ruft progress() jetzt fuer JEDEN Abschnitt auf -
            # auch uebersprungene/fehlgeschlagene (siehe Kommentar dort) - daher
            # ergibt die Summe der Zaehler in `stats` (die write_summary schon
            # live mitfuehrt) den echten, monoton wachsenden Fortschritt, ohne
            # den Aufruftext selbst parsen zu muessen.
            _done = stats.written + stats.failed + stats.skipped_short + stats.skipped_empty
            _tracker(_done, stats.total_sections or 1, msg[:40])

        try:
            path = summarize.write_summary(
                target, mode=mode, progress=_prog, stats_out=stats,
            )
        except ValueError as exc:
            status.warning(str(exc))
        except Exception as exc:                      # noqa: BLE001
            status.error(f"Fehler bei der Generierung: {exc}")
        else:
            status.empty()
            content = pathlib.Path(path).read_text("utf-8")
            st.session_state["_zus_md"] = content
            st.session_state["_zus_name"] = pathlib.Path(path).name
            st.session_state["_zus_stats"] = {
                "written": stats.written,
                "failed": stats.failed,
                "skipped_short": stats.skipped_short,
                "skipped_empty": stats.skipped_empty,
                "total_sections": stats.total_sections,
                "errors": list(stats.errors),
            }
            st.success(
                f"Fertig – {stats.written} Abschnitte geschrieben "
                f"(von {stats.total_sections}). Gespeichert unter docs/{pathlib.Path(path).name}"
            )
            if stats.failed:
                st.warning(
                    f"{stats.failed} Abschnitte fehlgeschlagen"
                    + (f": {stats.errors[0]}" if stats.errors else ".")
                )

if st.session_state.get("_zus_md"):
    with card("ergebnis"):
        _zs = st.session_state.get("_zus_stats") or {}
        if _zs:
            st.caption(
                f"Abschnitte: {_zs.get('written', '?')} geschrieben · "
                f"{_zs.get('failed', 0)} Fehler · "
                f"{_zs.get('skipped_empty', 0)} ohne Prüfungsstoff · "
                f"{_zs.get('skipped_short', 0)} zu kurz"
            )
        st.download_button("⬇️ Markdown herunterladen", st.session_state["_zus_md"],
                           file_name=st.session_state["_zus_name"], mime="text/markdown",
                           use_container_width=True)
        st.divider()
        st.markdown(st.session_state["_zus_md"])
