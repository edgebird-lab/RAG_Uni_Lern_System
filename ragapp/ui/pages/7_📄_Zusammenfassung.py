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

from ragapp import manifest
from ragapp.config import settings, SUBJECT_LABELS
from ragapp.ingestion import summarize

st.set_page_config(page_title="Zusammenfassung", page_icon="📄", layout="wide")

from ragapp.ui._auth import require_pin
require_pin()

st.markdown("<style>.block-container{padding-top:2rem;max-width:900px;}"
            "h1{font-weight:750;letter-spacing:-.5px;}</style>", unsafe_allow_html=True)


def _fach(code: str) -> str:
    return SUBJECT_LABELS.get(code, code)


st.title("📄 Zusammenfassung schreiben")
st.caption("Erzeugt aus einem indexierten Dokument oder einem ganzen Fach eine "
           "strukturierte, klausurtaugliche Zusammenfassung – gegroundet, es wird "
           "nur der Quellinhalt verwendet.")

docs = manifest.list_documents()
if not docs:
    st.info("Noch keine Dokumente indexiert – lege zuerst welche über **📥 Ingestion** an.")
    st.stop()

subjects = sorted({d["subject"] for d in docs if d["subject"]})

quelle = st.radio("Quelle", ["Dokument", "Fach"], horizontal=True)

if quelle == "Dokument":
    opts = {d["doc_id"]: f'{d["filename"]}  ·  {_fach(d["subject"] or "")}' for d in docs}
    target = st.selectbox("Dokument", list(opts), format_func=lambda k: opts[k])
    mode = "document"
else:
    target = st.selectbox("Fach", subjects, format_func=_fach)
    mode = "subject"

model = (getattr(settings, "LLM_MODEL_AUTHOR", "") or settings.LLM_MODEL)
st.caption(f"Autoren-Modell: `{model}`. Das kann je nach Umfang etwas dauern.")

if st.button("📝 Zusammenfassung erzeugen", type="primary", use_container_width=True):
    status = st.empty()

    def _prog(msg: str) -> None:
        status.info(msg)

    try:
        with st.spinner("Erzeuge Zusammenfassung …"):
            path = summarize.write_summary(target, mode=mode, progress=_prog)
    except ValueError as exc:
        status.warning(str(exc))
    except Exception as exc:                      # noqa: BLE001
        status.error(f"Fehler bei der Generierung: {exc}")
    else:
        status.empty()
        content = pathlib.Path(path).read_text("utf-8")
        st.session_state["_zus_md"] = content
        st.session_state["_zus_name"] = pathlib.Path(path).name
        st.success(f"Fertig – gespeichert unter docs/{pathlib.Path(path).name}")

if st.session_state.get("_zus_md"):
    st.download_button("⬇️ Markdown herunterladen", st.session_state["_zus_md"],
                       file_name=st.session_state["_zus_name"], mime="text/markdown",
                       use_container_width=True)
    st.divider()
    st.markdown(st.session_state["_zus_md"])
