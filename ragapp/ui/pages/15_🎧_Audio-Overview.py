"""
RAG-Lernsystem: Seite „Audio-Overview" (Vorlesen mit der eigenen Stimme)
==========================================================================
Erzeugt aus den gewählten Dokumenten ein gesprochen klingendes Erklär-Skript
und vertont es mit der eigenen, geklonten Stimme (XTTS-v2, siehe
``ragapp/audio_overview.py`` und docs/STIMME_AUFNEHMEN.md) - bewusst KEINE
generische KI-Stimme.
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

from ragapp.ui._loading import page_boot
page_boot("🎧 Audio-Overview", page_title="Audio-Overview", icon="🎧", layout="wide",
         accent="audio")

from ragapp.ui._style import card

st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1000px;}
h1 {font-weight: 750; letter-spacing:-0.5px;}
</style>
""", unsafe_allow_html=True)

st.caption("Lässt deine Dokumente als gesprochenes Erklär-Skript zusammenfassen und vertont "
           "es mit deiner eigenen (geklonten) Stimme - keine generische KI-Stimme.")

with st.spinner("Audio-Overview wird geladen ..."):
    from ragapp import manifest, audio_overview
    from ragapp.config import settings, SUBJECT_LABELS, PROJECT_ROOT, AUDIO_DIR
    from ragapp.llm import list_installed_models


def _fach(code: "str | None") -> str:
    return SUBJECT_LABELS.get(code, code) if code else "–"


def _model_picker(key: str) -> "str | None":
    """Modellwahl fürs Sprech-Skript (nicht die Sprachsynthese selbst - dort
    gibt es nur XTTS-v2) - gleiches Gründlich/Schnell-Muster wie bei
    Mindmap/Lernplan/Übungsaufgaben."""
    _author = settings.author_model()
    _fast = settings.LLM_MODEL_FAST
    _installed = list_installed_models() or []
    _options = [f"🎯 Gründlich ({_author})", f"⚡ Schnell ({_fast})"] + sorted(
        m for m in _installed if m not in (_author, _fast))
    _choice = st.selectbox("Modell fürs Skript", _options, key=key,
                           help="Nur für den Text - die Stimme kommt immer aus XTTS-v2.")
    if _choice.startswith("🎯 Gründlich"):
        return None
    if _choice.startswith("⚡ Schnell"):
        return _fast
    return _choice


_ref_path = PROJECT_ROOT / settings.AUDIO_REFERENCE_WAV
if not _ref_path.is_file():
    with card("keine_stimme"):
        st.markdown("##### 🎙️ Noch keine Stimm-Referenz vorhanden")
        st.write(
            "Bevor Audio-Overviews erzeugt werden können, braucht die App eine kurze "
            "Aufnahme deiner Stimme (mehrere Minuten, einmalig - kann später jederzeit "
            "durch eine neue Aufnahme ersetzt werden)."
        )
        st.markdown(
            "**So geht's:** Anleitung + fertiger Vorlesetext stehen in "
            "`docs/STIMME_AUFNEHMEN.md`. Die Aufnahme danach unter "
            f"`{settings.AUDIO_REFERENCE_WAV}` ablegen."
        )
        st.caption("Alternativ hier direkt hochladen (WAV, ein paar Minuten sprechen):")
        _uploaded = st.file_uploader("Stimm-Aufnahme (WAV)", type=["wav"], key="voice_upload")
        if _uploaded is not None and st.button("💾 Als Referenz speichern", type="primary"):
            _ref_path.parent.mkdir(parents=True, exist_ok=True)
            _ref_path.write_bytes(_uploaded.getvalue())
            st.success("Gespeichert. Die Seite lädt jetzt neu.")
            st.rerun()
    st.stop()

_all_docs = [dict(d) for d in manifest.list_documents()
            if d["use_rag"] and d["num_chunks"] > 0]
_subjects_with_docs = sorted({d["subject"] for d in _all_docs if d["subject"]})

if not _subjects_with_docs:
    st.info("Noch keine indexierten Dokumente (im RAG) vorhanden. Gehe zu "
            "**📥 Ingestion**, um welche hinzuzufügen.")
    st.stop()

_overviews = manifest.list_audio_overviews()
_ov_by_id = {o["overview_id"]: o for o in _overviews}

if "_audio_pending_choice" in st.session_state:
    st.session_state["audio_choice"] = st.session_state.pop("_audio_pending_choice")
elif st.session_state.get("audio_choice") not in ([None] + list(_ov_by_id.keys())):
    st.session_state["audio_choice"] = None


def _fmt_ov_option(oid: "str | None") -> str:
    if oid is None:
        return "➕ Neues Audio-Overview"
    o = _ov_by_id.get(oid)
    return f"{o['title']}  ·  {_fach(o['subject'])}" if o else "(gelöscht)"


st.selectbox("Audio-Overview wählen", [None] + list(_ov_by_id.keys()),
            format_func=_fmt_ov_option, key="audio_choice")
_active_id = st.session_state.get("audio_choice")

st.divider()

# --------------------------------------------------------------------------- #
# Neues Audio-Overview
# --------------------------------------------------------------------------- #
if _active_id is None:
    st.markdown("##### Neues Audio-Overview anlegen")
    nc1, nc2 = st.columns(2)
    with nc1:
        _new_subject = st.selectbox("Fach", _subjects_with_docs, format_func=_fach,
                                    key="audio_new_subject")
    with nc2:
        if st.session_state.get("_audio_title_for_subject") != _new_subject:
            st.session_state["audio_new_title"] = f"Audio-Overview {_fach(_new_subject)}"
            st.session_state["_audio_title_for_subject"] = _new_subject
        _new_title = st.text_input("Titel", key="audio_new_title")

    _subj_docs = {d["filename"]: d["doc_id"] for d in _all_docs if d["subject"] == _new_subject}
    _new_doc_names = st.multiselect("Dokument(e)", list(_subj_docs.keys()), key="audio_new_docs")

    _new_model = _model_picker("audio_new_model")

    if st.button("🎧 Audio-Overview erstellen", type="primary", disabled=not _new_doc_names):
        _doc_ids = [_subj_docs[n] for n in _new_doc_names]
        with st.spinner("KI schreibt das Skript und vertont es mit deiner Stimme … "
                        "das kann je nach Umfang und Hardware einige Minuten dauern."):
            try:
                _new_oid, _new_warning = audio_overview.create_and_save_audio_overview(
                    _doc_ids, _new_subject,
                    _new_title or f"Audio-Overview {_fach(_new_subject)}", model=_new_model)
            except audio_overview.AudioOverviewError as exc:
                st.error(str(exc))
                st.stop()
        if _new_warning:
            st.session_state["_audio_gen_warning"] = _new_warning
        else:
            st.success("Audio-Overview erstellt.")
        st.session_state["_audio_pending_choice"] = _new_oid
        st.rerun()
    st.stop()

# --------------------------------------------------------------------------- #
# Bestehendes Audio-Overview anzeigen
# --------------------------------------------------------------------------- #
_active = manifest.get_audio_overview(_active_id)
if _active is None:
    st.session_state["_audio_pending_choice"] = None
    st.rerun()

_audio_path = AUDIO_DIR / _active["audio_path"]

with card("player"):
    hh1, hh2 = st.columns([3, 1])
    with hh1:
        st.markdown(f"##### {_active['title']}")
        st.caption(_fach(_active["subject"]))
    with hh2:
        st.markdown(f"<div style='text-align:right;padding-top:6px;font-size:.8rem;opacity:.7'>"
                   f"{len(_active['doc_ids'])} Dokument(e)</div>", unsafe_allow_html=True)

    _gen_warning = st.session_state.pop("_audio_gen_warning", None)
    if _gen_warning:
        st.warning(_gen_warning)

    if not _audio_path.is_file():
        st.error("Die Audiodatei fehlt (evtl. manuell gelöscht) - bitte neu erzeugen.")
    else:
        _audio_bytes = _audio_path.read_bytes()
        st.audio(_audio_bytes, format="audio/wav")
        st.download_button("⬇️ Herunterladen", data=_audio_bytes,
                           file_name=f"{_active['title']}.wav", mime="audio/wav",
                           use_container_width=True)

    with st.expander("📝 Sprech-Skript (Text)"):
        st.write(_active["script_text"])

    with st.expander("⚙️ Neu generieren & Löschen"):
        _regen_model = _model_picker(f"audio_regen_model_{_active_id}")
        if st.button("🔄 Neu erzeugen (Skript + Stimme)", key=f"audio_regen_{_active_id}"):
            with st.spinner("KI schreibt das Skript neu und vertont es … das kann je nach "
                            "Umfang und Hardware einige Minuten dauern."):
                try:
                    _script, _regen_warning = audio_overview.generate_overview_script(
                        _active["doc_ids"], _active["subject"], model=_regen_model)
                    audio_overview.synthesize_speech(_script, _ref_path, _audio_path)
                except audio_overview.AudioOverviewError as exc:
                    st.error(str(exc))
                    st.stop()
                finally:
                    audio_overview.unload_tts_model()
            manifest.update_audio_overview(
                _active_id, script_text=_script,
                model=_regen_model or settings.author_model())
            if _regen_warning:
                st.session_state["_audio_gen_warning"] = _regen_warning
            else:
                st.success("Neu erzeugt.")
            st.rerun()
        if st.button("🗑️ Audio-Overview löschen", key=f"audio_delete_{_active_id}"):
            manifest.delete_audio_overview(_active_id)
            st.session_state["_audio_pending_choice"] = None
            st.success("Gelöscht.")
            st.rerun()
