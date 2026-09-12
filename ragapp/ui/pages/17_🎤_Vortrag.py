"""
RAG-Lernsystem: Seite „Vortrag“ (Marp + optional SearXNG + Lernvideo)
=====================================================================
Aus gewählten Dokumenten entsteht ein Marp-Markdown-Vortrag und ein
Sprecher-Skript. Optional: wissenschaftliche Treffer über die private
SearXNG-Instanz (Opt-in). Vertonung nutzt dieselbe Chatterbox-Pipeline wie
Audio-Overview. Optional: PNG-Folien + Audio → MP4 (Marp-CLI + ffmpeg).
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
page_boot("🎤 Vortrag", page_title="Vortrag", icon="🎤", layout="wide",
          accent="vortrag")

from ragapp.ui._style import card

st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1000px;}
h1 {font-weight: 750; letter-spacing:-0.5px;}
</style>
""", unsafe_allow_html=True)

st.caption("Erzeugt einen Marp-Vortrag aus deinen Unterlagen, optional mit "
           "wissenschaftlichen Quellen (SearXNG, Opt-in), vertont ihn mit deiner "
           "Stimme und exportiert Markdown / Audio / optional MP4.")

with skeleton("Vortrag wird geladen …"):
    from ragapp import manifest, talk, searx_client, audio_overview
    from ragapp.config import settings, SUBJECT_LABELS, PROJECT_ROOT, TALK_DIR
    from ragapp.llm import list_installed_models
    from ragapp.ui._progress import fmt_dauer as _fmt_dauer, progress_tracker as _progress_tracker
    from ragapp.ui._pronunciation import render_pronunciation_hints as _render_pronunciation_hints

_KEIN_FACH = "— Kein Fach —"


def _fach(code: "str | None") -> str:
    return SUBJECT_LABELS.get(code, code) if code else "–"


def _model_picker(key: str) -> "str | None":
    _author = settings.author_model()
    _fast = settings.LLM_MODEL_FAST
    _installed = list_installed_models() or []
    _options = [f"🎯 Gründlich ({_author})", f"⚡ Schnell ({_fast})"] + sorted(
        m for m in _installed if m not in (_author, _fast))
    _choice = st.selectbox("Modell für Folien & Skript", _options, key=key)
    if _choice.startswith("🎯 Gründlich"):
        return None
    if _choice.startswith("⚡ Schnell"):
        return _fast
    return _choice


_ref_path = PROJECT_ROOT / settings.AUDIO_REFERENCE_WAV
_has_voice = _ref_path.is_file()

_all_docs = [dict(d) for d in manifest.list_documents()
             if d["use_rag"] and d["num_chunks"] > 0]
_subjects_with_docs = sorted({d["subject"] for d in _all_docs if d["subject"]})

_talks = manifest.list_talks()
_talk_by_id = {t["talk_id"]: t for t in _talks}

if "_talk_pending_choice" in st.session_state:
    st.session_state["talk_choice"] = st.session_state.pop("_talk_pending_choice")
elif st.session_state.get("talk_choice") not in ([None] + list(_talk_by_id.keys())):
    st.session_state["talk_choice"] = None


def _fmt_talk_option(tid: "str | None") -> str:
    if tid is None:
        return "➕ Neuer Vortrag"
    t = _talk_by_id.get(tid)
    return f"{t['title']}  ·  {_fach(t['subject'])}" if t else "(gelöscht)"


st.selectbox("Vortrag wählen", [None] + list(_talk_by_id.keys()),
             format_func=_fmt_talk_option, key="talk_choice")
_active_id = st.session_state.get("talk_choice")

# --------------------------------------------------------------------------- #
# Neu anlegen
# --------------------------------------------------------------------------- #
if _active_id is None:
    st.markdown("##### Neuen Vortrag anlegen")
    if not _subjects_with_docs:
        st.info("Noch keine indexierten Dokumente vorhanden. Gehe zu **📥 Import**.")
        st.stop()

    _draft = st.session_state.get("_talk_draft")

    if _draft is None:
        nc1, nc2 = st.columns(2)
        with nc1:
            _new_subject = st.selectbox(
                "Fach (optional)", [None] + _subjects_with_docs,
                format_func=lambda s: _KEIN_FACH if s is None else _fach(s),
                key="talk_new_subject")
        with nc2:
            if st.session_state.get("_talk_title_for_subject") != _new_subject:
                st.session_state["talk_new_title"] = (
                    f"Vortrag {_fach(_new_subject)}" if _new_subject else "Vortrag")
                st.session_state["_talk_title_for_subject"] = _new_subject
            _new_title = st.text_input("Titel", key="talk_new_title")

        _subj_docs = {d["filename"]: d["doc_id"] for d in _all_docs
                      if _new_subject is None or d["subject"] == _new_subject}
        _new_doc_names = st.multiselect("Dokument(e)", list(_subj_docs.keys()),
                                        key="talk_new_docs", placeholder="Auswählen …")
        _new_model = _model_picker("talk_new_model")

        st.markdown("##### Externe Quellen (optional)")
        _ext = st.checkbox(
            "Wissenschaftliche Quellen über SearXNG einbeziehen",
            value=bool(settings.SEARXNG_ENABLED),
            key="talk_use_searx",
            help="Opt-in. Default aus – die App bleibt offline. Braucht VPN/LAN "
                 "zur konfigurierten SearXNG-Instanz.")
        if _ext:
            st.caption(f"Instanz: `{settings.SEARXNG_BASE_URL}` · "
                       "In den Einstellungen URL/Test ändern.")
            if st.button("🔎 Quellen suchen", disabled=not _new_doc_names,
                         key="talk_searx_search"):
                _doc_ids = [_subj_docs[n] for n in _new_doc_names]
                try:
                    with st.spinner("Suchqueries + SearXNG …"):
                        # Temporär enabled für diesen Lauf
                        _prev = settings.SEARXNG_ENABLED
                        settings.SEARXNG_ENABLED = True
                        try:
                            _queries = talk.extract_search_queries(
                                _doc_ids, title=_new_title or "Vortrag",
                                subject=_new_subject, model=_new_model)
                            _hits = searx_client.search_many(_queries) if _queries else []
                        finally:
                            settings.SEARXNG_ENABLED = _prev
                    st.session_state["_talk_searx_hits"] = [h.as_dict() for h in _hits]
                    st.session_state["_talk_searx_queries"] = _queries
                    if not _hits:
                        st.warning("Keine Treffer (Allowlist/VPN?). Pipeline kann lokal weiterlaufen.")
                    else:
                        st.success(f"{len(_hits)} Treffer – unten ankreuzen.")
                except (talk.TalkError, searx_client.SearxError) as exc:
                    st.warning(f"Externe Suche übersprungen: {exc}")
                    st.session_state["_talk_searx_hits"] = []

            _hits = st.session_state.get("_talk_searx_hits") or []
            _selected_sources: list[dict] = []
            if _hits:
                st.caption("Quellen auswählen (0–N):")
                for i, h in enumerate(_hits):
                    _lab = f"{h.get('title', 'Ohne Titel')[:80]}"
                    if st.checkbox(_lab, key=f"talk_src_{i}",
                                   help=(h.get("url") or "")[:200]):
                        st.caption((h.get("content") or "")[:280] or h.get("url", ""))
                        _selected_sources.append(h)
                st.session_state["_talk_selected_sources"] = _selected_sources
            else:
                st.session_state["_talk_selected_sources"] = []
        else:
            st.session_state.pop("_talk_searx_hits", None)
            st.session_state["_talk_selected_sources"] = []

        if st.button("📝 Folien & Skript erzeugen", type="primary",
                     disabled=not _new_doc_names, key="talk_generate"):
            _doc_ids = [_subj_docs[n] for n in _new_doc_names]
            _sources = list(st.session_state.get("_talk_selected_sources") or [])
            _bar = st.progress(0.0)
            _cap = st.empty()
            try:
                _marp, _script, _used, _warn = talk.generate_talk_content(
                    _doc_ids, title=_new_title or "Vortrag",
                    subject=_new_subject, sources=_sources, model=_new_model,
                    on_progress=_progress_tracker(_bar, _cap, "Vortrag"))
                st.session_state["_talk_draft"] = {
                    "marp_md": _marp, "script": _script,
                    "title": _new_title or f"Vortrag {_fach(_new_subject)}",
                    "subject": _new_subject, "doc_ids": _doc_ids,
                    "sources": _sources, "model": _used,
                    "warning": _warn,
                }
                st.rerun()
            except talk.TalkError as exc:
                st.error(str(exc))

    else:
        st.markdown("##### Entwurf prüfen")
        if _draft.get("warning"):
            st.warning(_draft["warning"])
        _marp_key = "talk_draft_marp"
        _script_key = "talk_draft_script"
        st.text_area("Marp-Markdown", value=_draft["marp_md"], height=280, key=_marp_key)
        st.text_area("Sprecher-Skript", value=_draft["script"], height=280, key=_script_key)
        _script_len = len(st.session_state[_script_key])
        st.caption(
            f"{_script_len} Zeichen Skript (~{_script_len / 1000:.0f} Min. grob) · "
            f"{len(_draft.get('sources') or [])} externe Quelle(n)"
        )
        _render_pronunciation_hints(st.session_state[_script_key], key_prefix="talk_draft")

        dc1, dc2, dc3 = st.columns(3)
        if dc1.button("💾 Speichern", type="primary", use_container_width=True,
                      key="talk_draft_save"):
            try:
                _md = talk.validate_marp_markdown(st.session_state[_marp_key])
                _tid = talk.create_talk_record(
                    title=_draft["title"], subject=_draft["subject"],
                    doc_ids=_draft["doc_ids"], marp_md=_md,
                    script_text=st.session_state[_script_key],
                    sources=_draft.get("sources") or [],
                    model=_draft.get("model"),
                )
                st.session_state.pop("_talk_draft", None)
                st.session_state["_talk_pending_choice"] = _tid
                st.rerun()
            except talk.TalkError as exc:
                st.error(str(exc))
        if dc2.button("💾 + 🎙️ Speichern & vertonen", use_container_width=True,
                      key="talk_draft_save_tts", disabled=not _has_voice):
            try:
                _md = talk.validate_marp_markdown(st.session_state[_marp_key])
                _tid = talk.create_talk_record(
                    title=_draft["title"], subject=_draft["subject"],
                    doc_ids=_draft["doc_ids"], marp_md=_md,
                    script_text=st.session_state[_script_key],
                    sources=_draft.get("sources") or [],
                    model=_draft.get("model"),
                )
                _bar = st.progress(0.0)
                _cap = st.empty()
                talk.synthesize_talk_audio(
                    _tid, st.session_state[_script_key],
                    on_progress=_progress_tracker(_bar, _cap, "Vertonung"))
                st.session_state.pop("_talk_draft", None)
                st.session_state["_talk_pending_choice"] = _tid
                st.rerun()
            except (talk.TalkError, audio_overview.AudioOverviewError) as exc:
                st.error(str(exc))
        if dc3.button("🗑️ Verwerfen", use_container_width=True, key="talk_draft_discard"):
            st.session_state.pop("_talk_draft", None)
            st.rerun()
        if not _has_voice:
            st.info("Für Vertonung fehlt die Stimm-Referenz "
                    f"(`{settings.AUDIO_REFERENCE_WAV}`).")
    st.stop()

# --------------------------------------------------------------------------- #
# Bestehenden Vortrag anzeigen
# --------------------------------------------------------------------------- #
_active = manifest.get_talk(_active_id)
if _active is None:
    st.session_state["_talk_pending_choice"] = None
    st.rerun()

with card("talk_head"):
    hh1, hh2 = st.columns([3, 1])
    with hh1:
        st.markdown(f"##### {_active['title']}")
        st.caption(_fach(_active["subject"]))
    with hh2:
        st.markdown(
            f"<div style='text-align:right;padding-top:6px;font-size:.8rem;opacity:.7'>"
            f"{len(_active.get('doc_ids') or [])} Dokument(e)</div>",
            unsafe_allow_html=True)

    _marp_edit = st.text_area("Marp-Markdown", value=_active["marp_md"], height=260,
                              key=f"talk_marp_{_active_id}")
    _script_edit = st.text_area("Sprecher-Skript", value=_active["script_text"], height=240,
                                key=f"talk_script_{_active_id}")
    st.caption(f"{len(_script_edit)} Zeichen Skript (~{len(_script_edit) / 1000:.0f} Min. grob)")
    _render_pronunciation_hints(_script_edit, key_prefix=f"talk_exist_{_active_id}")

    if _active.get("sources"):
        with st.expander(f"🔗 {len(_active['sources'])} externe Quelle(n)"):
            for s in _active["sources"]:
                st.markdown(f"- [{s.get('title') or 'Quelle'}]({s.get('url') or '#'})")

    b1, b2, b3 = st.columns(3)
    if b1.button("💾 Änderungen speichern", key="talk_save_edits"):
        try:
            _md = talk.validate_marp_markdown(_marp_edit)
            talk.save_marp_file(_active_id, _md)
            manifest.update_talk(_active_id, marp_md=_md, script_text=_script_edit)
            st.success("Gespeichert.")
            st.rerun()
        except talk.TalkError as exc:
            st.error(str(exc))

    if b2.button("🎙️ Vertonen", type="primary", key="talk_tts",
                 disabled=not _has_voice):
        _bar = st.progress(0.0)
        _cap = st.empty()
        try:
            talk.synthesize_talk_audio(
                _active_id, _script_edit,
                on_progress=_progress_tracker(_bar, _cap, "Vertonung"))
            st.success("Audio erzeugt.")
            st.rerun()
        except (talk.TalkError, audio_overview.AudioOverviewError) as exc:
            st.error(str(exc))

    if b3.button("🗑️ Löschen", key="talk_delete"):
        manifest.delete_talk(_active_id)
        st.session_state["_talk_pending_choice"] = None
        st.rerun()

# Downloads & Video
st.markdown("##### Export")
_md_bytes = (_active.get("marp_md") or "").encode("utf-8")
st.download_button("⬇️ Marp (.md)", data=_md_bytes,
                   file_name=f"{_active['title'][:40] or 'vortrag'}.md",
                   mime="text/markdown", key="talk_dl_md")

_audio_rel = _active.get("audio_path")
if _audio_rel:
    _ap = TALK_DIR / _audio_rel
    if _ap.is_file():
        st.audio(_ap.read_bytes(), format="audio/wav")
        st.download_button("⬇️ Audio (WAV)", data=_ap.read_bytes(),
                           file_name=f"{_active['title'][:40] or 'vortrag'}.wav",
                           mime="audio/wav", key="talk_dl_wav")

_marp_ok = talk.find_marp_cli() is not None
if not _marp_ok:
    st.info(talk.marp_install_hint())

vc1, vc2 = st.columns(2)
with vc1:
    if st.button("🖼️ HTML per Marp", disabled=not _marp_ok, key="talk_html"):
        try:
            _md_path = talk.save_marp_file(_active_id, _active["marp_md"])
            _html = talk.talk_dir(_active_id) / "talk.html"
            talk.run_marp(_md_path, output=_html, fmt="html")
            st.download_button("⬇️ HTML herunterladen", data=_html.read_bytes(),
                               file_name="talk.html", mime="text/html",
                               key="talk_dl_html")
        except talk.TalkError as exc:
            st.error(str(exc))
with vc2:
    _can_video = bool(_audio_rel and _marp_ok)
    if st.button("🎬 Video (MP4) erzeugen", disabled=not _can_video, key="talk_video",
                 type="primary" if _can_video else "secondary"):
        try:
            with st.spinner("Marp → PNG → ffmpeg …"):
                _vrel = talk.render_talk_video(_active_id)
            st.success("Video fertig.")
            st.rerun()
        except talk.TalkError as exc:
            st.error(str(exc))
    if not _audio_rel:
        st.caption("Video braucht zuerst eine Vertonung.")

_video_rel = _active.get("video_path")
if _video_rel:
    _vp = TALK_DIR / _video_rel
    if _vp.is_file():
        st.video(str(_vp))
        st.download_button("⬇️ Video (MP4)", data=_vp.read_bytes(),
                           file_name=f"{_active['title'][:40] or 'vortrag'}.mp4",
                           mime="video/mp4", key="talk_dl_mp4")
