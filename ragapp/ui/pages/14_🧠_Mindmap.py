"""
RAG-Lernsystem: Seite „Mindmap" (Themenbaum aus dem Inhaltsverzeichnis)
==========================================================================
Erzeugt aus den bereits indexierten Abschnitten gewählter Dokumente einen
hierarchischen Themenbaum - quellengetreu (nur ordnen/gruppieren, nichts
Erfundenes), gerendert als eigenes SVG-Layout (kein System-Graphviz nötig,
siehe ``ragapp/mindmap_render.py``-Docstring).
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
page_boot("🧠 Mindmap", page_title="Mindmap", icon="🧠", layout="wide", accent="mindmap")

from ragapp.ui._style import card

st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1150px;}
h1 {font-weight: 750; letter-spacing:-0.5px;}
.mm-svg-frame {overflow:auto; max-height:70vh; border:1px solid rgba(100,116,139,.3);
              border-radius:10px; padding:10px; background:rgba(148,163,184,.05);}
</style>
""", unsafe_allow_html=True)

st.caption("Quellengetreuer Themenbaum aus deinen indexierten Dokumenten - ordnet und "
           "gruppiert nur, was im Inhaltsverzeichnis bereits steht, erfindet keine "
           "neuen Themen.")

with st.spinner("Mindmap wird geladen ..."):
    from ragapp import manifest, mindmap, mindmap_render
    from ragapp.config import settings, SUBJECT_LABELS
    from ragapp.ui._colors import subject_color
    from ragapp.llm import list_installed_models


def _model_picker(key: str) -> "str | None":
    """Modellwahl fuer die Mindmap-Generierung: 'Gründlich'/'Schnell' als
    Schnellwahl (wie bei Lernplan/Übungsaufgaben), PLUS alle lokal
    installierten Modelle einzeln waehlbar - manche (Reasoning-)Modelle
    brauchen fuer grosse Themenbaeume deutlich laenger oder brechen sogar ab
    (siehe Warnhinweis nach der Generierung); dann hilft oft nur, ein anderes
    Modell zu probieren. Rueckgabe passt direkt zu generate_mindmap(model=...):
    ``None`` = Autoren-Modell, sonst der exakte Modellname."""
    _author = settings.author_model()
    _fast = settings.LLM_MODEL_FAST
    _installed = list_installed_models() or []
    _options = [f"🎯 Gründlich ({_author})", f"⚡ Schnell ({_fast})"] + sorted(
        m for m in _installed if m not in (_author, _fast))
    _choice = st.selectbox("Modell", _options, key=key,
                           help="Bricht ein Modell bei vielen Abschnitten ab "
                                "(siehe Warnhinweis), hilft oft ein anderes.")
    if _choice.startswith("🎯 Gründlich"):
        return None
    if _choice.startswith("⚡ Schnell"):
        return _fast
    return _choice


def _fach(code: "str | None") -> str:
    return SUBJECT_LABELS.get(code, code) if code else "–"


def _flatten_topics(graph: dict) -> list[tuple[int, dict]]:
    """Depth-First-Liste ``(einrueckung, knoten)`` fuer die Themen-Auswahlliste
    unter dem SVG - unabhaengig vom Rendering-Layout, rein fuer die Anzeige."""
    children: dict = {}
    for n in graph.get("nodes", []):
        children.setdefault(n.get("parent"), []).append(n)
    out: list[tuple[int, dict]] = []

    def visit(pid, depth):
        for n in children.get(pid, []):
            out.append((depth, n))
            visit(n["id"], depth + 1)

    visit(None, 0)
    return out


_all_docs = [dict(d) for d in manifest.list_documents()
            if d["use_rag"] and d["num_chunks"] > 0]
_subjects_with_docs = sorted({d["subject"] for d in _all_docs if d["subject"]})

if not _subjects_with_docs:
    st.info("Noch keine indexierten Dokumente (im RAG) vorhanden. Gehe zu "
            "**📥 Ingestion**, um welche hinzuzufügen.")
    st.stop()

_plan_colors = manifest.subject_colors_map()
_mindmaps = manifest.list_mindmaps()
_mm_by_id = {m["mindmap_id"]: m for m in _mindmaps}

if "_mm_pending_choice" in st.session_state:
    st.session_state["mm_choice"] = st.session_state.pop("_mm_pending_choice")
elif st.session_state.get("mm_choice") not in ([None] + list(_mm_by_id.keys())):
    st.session_state["mm_choice"] = None


def _fmt_mm_option(mid: "str | None") -> str:
    if mid is None:
        return "➕ Neue Mindmap"
    m = _mm_by_id.get(mid)
    return f"{m['title']}  ·  {_fach(m['subject'])}" if m else "(gelöscht)"


st.selectbox("Mindmap wählen", [None] + list(_mm_by_id.keys()),
            format_func=_fmt_mm_option, key="mm_choice")
_active_id = st.session_state.get("mm_choice")

st.divider()

# --------------------------------------------------------------------------- #
# Neue Mindmap
# --------------------------------------------------------------------------- #
if _active_id is None:
    st.markdown("##### Neue Mindmap anlegen")
    nc1, nc2 = st.columns(2)
    with nc1:
        _new_subject = st.selectbox("Fach", _subjects_with_docs, format_func=_fach,
                                    key="mm_new_subject")
    with nc2:
        if st.session_state.get("_mm_title_for_subject") != _new_subject:
            st.session_state["mm_new_title"] = f"Mindmap {_fach(_new_subject)}"
            st.session_state["_mm_title_for_subject"] = _new_subject
        _new_title = st.text_input("Titel", key="mm_new_title")

    _subj_docs = {d["filename"]: d["doc_id"] for d in _all_docs if d["subject"] == _new_subject}
    _new_doc_names = st.multiselect("Dokument(e)", list(_subj_docs.keys()), key="mm_new_docs",
                                    placeholder="Auswählen …")

    _new_model = _model_picker("mm_new_model")

    if st.button("🧠 Mindmap erstellen", type="primary", disabled=not _new_doc_names):
        _doc_ids = [_subj_docs[n] for n in _new_doc_names]
        with st.spinner("KI erstellt die Mindmap … das kann je nach Umfang und "
                        "Hardware einige Zeit dauern."):
            try:
                _new_mid, _new_warning = mindmap.create_and_save_mindmap(
                    _doc_ids, _new_subject, _new_title or f"Mindmap {_fach(_new_subject)}",
                    model=_new_model)
            except mindmap.MindmapError as exc:
                st.error(str(exc))
                st.stop()
        if _new_warning:
            st.session_state["_mm_gen_warning"] = _new_warning
        else:
            st.success("Mindmap erstellt.")
        st.session_state["_mm_pending_choice"] = _new_mid
        st.rerun()
    st.stop()

# --------------------------------------------------------------------------- #
# Bestehende Mindmap anzeigen
# --------------------------------------------------------------------------- #
_active = manifest.get_mindmap(_active_id)
if _active is None:
    st.session_state["_mm_pending_choice"] = None
    st.rerun()

_graph = _active["graph"]
_base_color = subject_color(_active["subject"], _plan_colors, _subjects_with_docs)

with card("viewer"):
    hh1, hh2 = st.columns([3, 1])
    with hh1:
        st.markdown(f"##### {_active['title']}")
        st.caption(_fach(_active["subject"]))
    with hh2:
        st.markdown(f"<div style='text-align:right;padding-top:6px;font-size:.8rem;opacity:.7'>"
                   f"{len(_graph.get('nodes', []))} Themen</div>", unsafe_allow_html=True)

    # key= haelt den Auf/Zu-Zustand fest - ohne key faellt der Expander sonst bei
    # JEDEM Rerun (auch nur durch die Modellwahl DARIN) auf zugeklappt zurueck,
    # bevor der Klick auf "neu generieren" erfolgt.
    with st.expander("⚙️ Neu generieren & Löschen", key=f"mm_regen_expander_{_active_id}"):
        _regen_model = _model_picker(f"mm_regen_model_{_active_id}")
        if st.button("🔄 Mindmap neu generieren", key=f"mm_regen_{_active_id}"):
            with st.spinner("KI erstellt die Mindmap neu … das kann je nach Umfang und "
                            "Hardware einige Zeit dauern."):
                try:
                    _new_graph, _regen_warning = mindmap.generate_mindmap(
                        _active["doc_ids"], _active["subject"], model=_regen_model)
                except mindmap.MindmapError as exc:
                    st.error(str(exc))
                    st.stop()
            manifest.update_mindmap(_active_id, graph=_new_graph,
                                    model=_regen_model or settings.author_model())
            if _regen_warning:
                st.session_state["_mm_gen_warning"] = _regen_warning
            else:
                st.success("Mindmap neu erzeugt.")
            st.rerun()
        if st.button("🗑️ Mindmap löschen", key=f"mm_delete_{_active_id}"):
            manifest.delete_mindmap(_active_id)
            st.session_state["_mm_pending_choice"] = None
            st.success("Mindmap gelöscht.")
            st.rerun()

    _gen_warning = st.session_state.pop("_mm_gen_warning", None)
    if _gen_warning:
        st.warning(_gen_warning)

    if not _graph.get("nodes"):
        st.info("Diese Mindmap hat keine Themen (leerer Graph).")
        st.stop()

    _layout = mindmap_render.layout_tree(_graph)
    _svg = mindmap_render.render_svg(_graph, _layout, base_color=_base_color)
    st.markdown(f'<div class="mm-svg-frame">{_svg}</div>', unsafe_allow_html=True)

    # --------------------------------------------------------------------------- #
    # Themen-Auswahlliste (statische Klickbarkeit v1 - echte Klick-Navigation im
    # SVG selbst braeuchte eine eigene Streamlit-Custom-Component).
    # --------------------------------------------------------------------------- #
    st.markdown("##### Thema auswählen")
    _topics = _flatten_topics(_graph)
    _topic_labels = {n["id"]: ("　" * depth) + n["title"] for depth, n in _topics}
    _sel_topic_id = st.selectbox(
        "Thema", list(_topic_labels.keys()), format_func=lambda tid: _topic_labels.get(tid, tid),
        key=f"mm_topic_pick_{_active_id}")

    if _sel_topic_id:
        _sel_node = next(n for _, n in _topics if n["id"] == _sel_topic_id)
        tc1, tc2 = st.columns(2)
        if tc1.button("🔎 Dazu fragen", key=f"mm_chat_{_active_id}_{_sel_topic_id}",
                     use_container_width=True,
                     help="Stellt die Frage im Chat unten - bleibt auf dieser Seite."):
            st.session_state[f"_mm_chat_pending_{_active_id}"] = (
                f"Erkläre mir das Thema: {_sel_node['title']}")
            st.rerun()
        if tc2.button("🧮 Dazu eine Übungsaufgabe", key=f"mm_practice_{_active_id}_{_sel_topic_id}",
                     use_container_width=True):
            st.session_state["practice_prefill"] = {
                "subject": _active["subject"], "doc_ids": _active["doc_ids"],
                "topic": _sel_node["title"],
            }
            st.switch_page("pages/13_🧮_Übungsaufgaben.py")

    # --------------------------------------------------------------------------- #
    # Eingebetteter Chat - gescoped auf GENAU die Dokumente dieser Mindmap (nicht
    # die ganze Bibliothek), damit man z. B. bei einer Marketing-Mindmap nicht
    # plötzlich Cybersecurity-Inhalte aus anderen Dokumenten bekommt. Bewusst AUF
    # DIESER SEITE (nicht mehr ein Sprung zur globalen Chat-Seite) - man bleibt
    # im Thema, die Mindmap bleibt sichtbar, waehrend man Fragen stellt.
    # --------------------------------------------------------------------------- #
st.divider()
with card("chat"):
    st.markdown("##### 💬 Fragen zu dieser Mindmap")
    st.caption("Antwortet nur aus den " + str(len(_active["doc_ids"])) +
              " Dokument(en) dieser Mindmap - nicht aus dem Rest deiner Bibliothek.")

    _chat_key = f"mm_chat_messages_{_active_id}"
    st.session_state.setdefault(_chat_key, [])

    if st.session_state[_chat_key] and st.button(
            "🗑️ Chat-Verlauf löschen", key=f"mm_chat_clear_{_active_id}"):
        st.session_state[_chat_key] = []
        st.rerun()

    for _msg in st.session_state[_chat_key]:
        with st.chat_message(_msg["role"], avatar="🧑‍🎓" if _msg["role"] == "user" else "🤖"):
            st.markdown(_msg["content"])
            if _msg.get("sources"):
                with st.expander(f"📚 Quellen ({len(_msg['sources'])})"):
                    for s in _msg["sources"]:
                        loc = f" · {s['location']}" if s.get("location") else ""
                        st.caption(f"[{s['rank']}] {s['filename']}{loc}")
                        _snip = s.get("snippet", "")
                        st.caption("„" + _snip[:240] + ("…" if len(_snip) > 240 else "") + "”")

    _mm_prompt = st.chat_input("Frage zu diesen Dokumenten …", key=f"mm_chat_input_{_active_id}")
    if not _mm_prompt:
        _mm_prompt = st.session_state.pop(f"_mm_chat_pending_{_active_id}", None)

    if _mm_prompt:
        st.session_state[_chat_key].append({"role": "user", "content": _mm_prompt})
        with st.chat_message("user", avatar="🧑‍🎓"):
            st.markdown(_mm_prompt)
        with st.chat_message("assistant", avatar="🤖"):
            from ragapp.graph.rag_graph import answer_query_stream
            _history = [{"role": m["role"], "content": m["content"]}
                       for m in st.session_state[_chat_key][:-1]]
            with st.spinner("🧠 Antwort wird erstellt …"):
                try:
                    _mm_stream, _mm_holder = answer_query_stream(
                        _mm_prompt, subject=_active["subject"], doc_ids=_active["doc_ids"],
                        check_faithfulness=False, history=_history, chat_mode="tutor")
                except Exception:  # noqa: BLE001 - Setup-Fehler -> als Antwort anzeigen
                    _mm_stream, _mm_holder = None, {}
                if _mm_stream is not None:
                    try:
                        _mm_answer = st.write_stream(_mm_stream)
                    except Exception as exc:  # noqa: BLE001 - Stream-Fehler nie roh anzeigen
                        _mm_answer = _mm_holder.get("answer") or f"Fehler: {exc}"
                else:
                    _mm_answer = _mm_holder.get("answer") or "Keine Antwort erhalten."
                    st.markdown(_mm_answer)
            _mm_sources = _mm_holder.get("sources", [])
            if _mm_sources:
                with st.expander(f"📚 Quellen ({len(_mm_sources)})"):
                    for s in _mm_sources:
                        loc = f" · {s['location']}" if s.get("location") else ""
                        st.caption(f"[{s['rank']}] {s['filename']}{loc}")
                        _snip = s.get("snippet", "")
                        st.caption("„" + _snip[:240] + ("…" if len(_snip) > 240 else "") + "”")
        st.session_state[_chat_key].append(
            {"role": "assistant", "content": _mm_answer, "sources": _mm_sources})
