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
import streamlit.components.v1 as components

from ragapp.ui._loading import page_boot, skeleton
page_boot("🧠 Mindmap", page_title="Mindmap", icon="🧠", layout="wide", accent="mindmap")

from ragapp.ui._style import card, delete_button

st.markdown("""
<style>
div[class*="st-key-mm_hit_"],
div.stElementContainer[class*="st-key-mm_hit_"] {
  display:none !important;
}
</style>
""", unsafe_allow_html=True)

st.caption("Themen aus deinen Unterlagen als Baum – nur vorhandener Stoff, keine erfundenen Äste.")

with skeleton("Mindmap wird geladen …"):
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
    """Depth-First-Liste ``(einrueckung, knoten)`` fuer die Themenliste."""
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


def _load_sections(doc_ids: list) -> list:
    """TOC-Abschnitte der Mindmap-Dokumente (gleiche Nummerierung wie beim Erzeugen)."""
    key = "_mm_sec::" + ",".join(str(d) for d in doc_ids)
    if key not in st.session_state:
        try:
            st.session_state[key] = mindmap.sections_for_docs(list(doc_ids))
        except Exception:  # noqa: BLE001 - Detailpanel bleibt ohne Auszuege nutzbar
            st.session_state[key] = []
    return st.session_state[key]


def _labels_for(graph: dict, sections: list) -> dict:
    return {str(n["id"]): mindmap.node_label(n, sections) for n in graph.get("nodes") or []}


def _sel_key(mindmap_id: str) -> str:
    return f"mm_sel_{mindmap_id}"


def _render_clickable_svg(svg: str, height: float) -> None:
    """SVG in einem Iframe (kein Markdown-Sanitizer) + Klicks an Hidden-Buttons."""
    iframe_h = max(220, min(int(height) + 28, 640))
    components.html(
        f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  html,body {{ margin:0; padding:0; background:transparent; }}
  .mm-svg-frame {{ overflow:auto; max-height:{iframe_h}px;
    border:1px solid rgba(100,116,139,.35); border-radius:10px;
    padding:8px; background:rgba(148,163,184,.06); }}
  svg {{ display:block; }}
</style></head><body>
<div class="mm-svg-frame">{svg}</div>
<script>
(function() {{
  function cssEscape(s) {{
    if (window.CSS && CSS.escape) return CSS.escape(s);
    return String(s).replace(/[^a-zA-Z0-9_-]/g, '\\\\$&');
  }}
  function clickHit(nid) {{
    var doc = window.parent.document;
    var btn = doc.querySelector('.st-key-mm_hit_' + cssEscape(nid) + ' button');
    if (btn) btn.click();
  }}
  var root = document.querySelector('.mm-svg-frame');
  if (!root) return;
  root.addEventListener('click', function(e) {{
    var g = e.target.closest ? e.target.closest('[data-mm-id]') : null;
    if (!g) return;
    var nid = g.getAttribute('data-mm-id');
    if (nid) clickHit(nid);
  }});
}})();
</script>
</body></html>""",
        height=iframe_h + 18,
        scrolling=True,
    )


_all_docs = [dict(d) for d in manifest.list_documents()
            if d["use_rag"] and d["num_chunks"] > 0]
_subjects_with_docs = sorted({d["subject"] for d in _all_docs if d["subject"]})

if not _subjects_with_docs:
    from ragapp.ui._style import empty_state, page_title as _pt
    empty_state(
        "Noch keine indexierten Dokumente. Lade Dateien unter Dokumente hoch.",
        cta_label=f"Zu {_pt('dokumente')}",
        page_key="dokumente",
        icon="📥",
        key="mm_empty_dokumente",
    )
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
        from ragapp.ui._progress import LlmWait
        _doc_ids = [_subj_docs[n] for n in _new_doc_names]
        with LlmWait("Suche Themen in den Unterlagen …") as wait:
            wait.set("Formuliere die Mindmap …")
            try:
                _new_mid, _new_warning = mindmap.create_and_save_mindmap(
                    _doc_ids, _new_subject, _new_title or f"Mindmap {_fach(_new_subject)}",
                    model=_new_model)
            except mindmap.MindmapError as exc:
                wait.done("Nicht geklappt", ok=False)
                st.error(str(exc))
                st.stop()
            wait.done()
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
        st.markdown(
            f"<p style='text-align:right;padding-top:6px;font-size:.8rem;opacity:.7;"
            f"white-space:nowrap'>{len(_graph.get('nodes', []))} Themen</p>",
            unsafe_allow_html=True)

    # key= haelt den Auf/Zu-Zustand fest - ohne key faellt der Expander sonst bei
    # JEDEM Rerun (auch nur durch die Modellwahl DARIN) auf zugeklappt zurueck,
    # bevor der Klick auf "neu generieren" erfolgt.
    _pending_key = f"_mm_pending_regen_{_active_id}"
    with st.expander("⚙️ Neu generieren & Löschen", key=f"mm_regen_expander_{_active_id}"):
        _regen_model = _model_picker(f"mm_regen_model_{_active_id}")
        if st.button("🔄 Mindmap neu generieren", key=f"mm_regen_{_active_id}"):
            from ragapp.ui._progress import LlmWait
            with LlmWait("Suche Themen in den Unterlagen …") as wait:
                wait.set("Formuliere die Mindmap …")
                try:
                    _new_graph, _regen_warning = mindmap.generate_mindmap(
                        _active["doc_ids"], _active["subject"], model=_regen_model)
                except mindmap.MindmapError as exc:
                    wait.done("Nicht geklappt", ok=False)
                    st.error(str(exc))
                    st.stop()
                wait.done()
            # NICHT sofort überschreiben - erst zur Vorschau anbieten (siehe
            # _pending_key unten). Ein misslungener/schlechterer Vorschlag
            # (z. B. bei einer Quelle ohne erkennbare Kapitelstruktur) darf
            # die bestehende Mindmap nicht kommentarlos ersetzen.
            st.session_state[_pending_key] = {
                "graph": _new_graph, "warning": _regen_warning, "model": _regen_model}
            st.rerun()
        if delete_button("🗑️ Mindmap löschen", token=f"mm:{_active_id}",
                         body=f"Mindmap **{_active.get('title') or 'ohne Titel'}** wirklich löschen?",
                         key=f"mm_delete_{_active_id}"):
            manifest.delete_mindmap(_active_id)
            st.session_state["_mm_pending_choice"] = None
            st.success("Mindmap gelöscht.")
            st.rerun()

    _pending_regen = st.session_state.get(_pending_key)
    if _pending_regen:
        _new_nodes = _pending_regen["graph"].get("nodes", [])
        _new_top = [n.get("title") for n in _new_nodes if not n.get("parent")]
        with card("regen_preview"):
            st.markdown("##### 🔄 Neu generierter Vorschlag – übernehmen oder verwerfen?")
            st.caption(f"Bisher: {len(_graph.get('nodes', []))} Themen  ·  "
                      f"Neu: {len(_new_nodes)} Themen")
            if _new_top:
                st.markdown("**Neue Hauptthemen:** " + ", ".join(_new_top[:10])
                            + (" …" if len(_new_top) > 10 else ""))
            if _pending_regen["warning"]:
                st.warning(_pending_regen["warning"])
            _pc1, _pc2 = st.columns(2)
            if _pc1.button("✅ Übernehmen", key=f"mm_regen_apply_{_active_id}", type="primary",
                           use_container_width=True):
                manifest.update_mindmap(
                    _active_id, graph=_pending_regen["graph"],
                    model=_pending_regen["model"] or settings.author_model())
                st.session_state.pop(_pending_key, None)
                st.session_state.pop(_sel_key(_active_id), None)
                st.success("Mindmap aktualisiert.")
                st.rerun()
            if _pc2.button("❌ Verwerfen", key=f"mm_regen_discard_{_active_id}",
                           use_container_width=True):
                st.session_state.pop(_pending_key, None)
                st.info("Verworfen – die bisherige Mindmap bleibt erhalten.")
                st.rerun()
            st.caption("Die aktuell gespeicherte Mindmap (unten) bleibt bis zur "
                      "Entscheidung unverändert sichtbar.")

    _gen_warning = st.session_state.pop("_mm_gen_warning", None)
    if _gen_warning:
        st.warning(_gen_warning)

    if not _graph.get("nodes"):
        st.info("Diese Mindmap hat keine Themen (leerer Graph).")
        st.stop()

    _sections = _load_sections(_active.get("doc_ids") or [])
    _labels = _labels_for(_graph, _sections)
    _topics = _flatten_topics(_graph)
    _by_id = {str(n["id"]): n for n in _graph.get("nodes") or []}
    _children: dict[str, list] = {}
    for _n in _graph.get("nodes") or []:
        if _n.get("parent"):
            _children.setdefault(str(_n["parent"]), []).append(_n)

    _sk = _sel_key(_active_id)
    st.session_state.setdefault(_sk, [])

    # Hidden-Buttons zuerst: ein Klick im SVG triggert denselben Toggle wie
    # die sichtbare Themenliste. Zustand liegt in mm_sel_<id>, nicht in
    # pills/selectbox (die die Karte durch eine flache "Seite N"-Liste ersetzten).
    _toggles: list[str] = []
    for _n in _graph.get("nodes") or []:
        _nid = str(_n["id"])
        if st.button("\u200b", key=f"mm_hit_{_nid}"):
            _toggles.append(_nid)
    if _toggles:
        _cur = [str(x) for x in (st.session_state.get(_sk) or [])]
        for _nid in _toggles:
            if _nid in _cur:
                _cur = [x for x in _cur if x != _nid]
            else:
                _cur.append(_nid)
        st.session_state[_sk] = _cur
        st.rerun()

    _selected = [s for s in st.session_state.get(_sk) or [] if s in _by_id]
    if _selected != list(st.session_state.get(_sk) or []):
        st.session_state[_sk] = _selected

    _layout = mindmap_render.layout_tree(_graph, labels=_labels)
    _svg = mindmap_render.render_svg(
        _graph, _layout, base_color=_base_color,
        selected_ids=set(_selected), labels=_labels)
    st.caption("Knoten antippen, um Stoff dazu zu sehen – mehrere Themen nacheinander "
               "wählen geht. Die Karte bleibt stehen.")
    _render_clickable_svg(_svg, _layout["height"])

    _lc, _rc = st.columns([3, 2])
    with _lc:
        if _selected:
            _names = [_labels.get(s, _by_id[s].get("title") or s) for s in _selected]
            st.markdown("Gewählt: **" + "**, **".join(_names) + "**")
        else:
            st.caption("Noch kein Thema gewählt.")
    with _rc:
        if st.button("Auswahl leeren", key=f"mm_clear_{_active_id}",
                     disabled=not _selected, use_container_width=True):
            st.session_state[_sk] = []
            st.rerun()

    with st.expander("Themenliste (Mehrfachauswahl)", expanded=not _selected):
        for _depth, _n in _topics:
            _nid = str(_n["id"])
            _on = _nid in _selected
            _mark = "☑" if _on else "☐"
            _lab = ("　" * _depth) + f"{_mark} {_labels.get(_nid, _n.get('title') or _nid)}"
            if st.button(_lab, key=f"mm_pick_{_nid}", use_container_width=True):
                _cur = [str(x) for x in (st.session_state.get(_sk) or [])]
                if _nid in _cur:
                    _cur = [x for x in _cur if x != _nid]
                else:
                    _cur.append(_nid)
                st.session_state[_sk] = _cur
                st.rerun()

    _include_kids = st.checkbox(
        "Unterthemen einbeziehen", value=True, key=f"mm_kids_{_active_id}",
        help="Stoff der Unterknoten mit dazu nehmen, nicht nur den angeklickten Kasten.")

    _idxs = mindmap.topic_indices(_graph, _selected, include_children=_include_kids)
    _excerpts = mindmap.excerpts_for_indices(_sections, _idxs, max_chars=1800) if _selected else ""
    _title_join = ", ".join(
        _labels.get(s, _by_id[s].get("title") or s) for s in _selected)

    if not _selected:
        st.info("Tippe in der Karte (oder der Liste) ein oder mehrere Themen an – "
                "dann erscheinen hier nur die Quellen zu genau diesem Stoff, "
                "und du kannst dazu fragen, üben oder eine Kurzfassung erzeugen.")
    else:
        st.markdown("##### Stoff zu " + _title_join)
        _sub_bits: list[str] = []
        for _sid in _selected:
            for _ch in _children.get(_sid, []):
                _sub_bits.append(_labels.get(str(_ch["id"]), _ch.get("title") or ""))
        if _sub_bits:
            st.caption("Unterthemen: " + ", ".join(t for t in _sub_bits if t))

        if _excerpts:
            st.markdown(_excerpts)
        else:
            st.caption("Zu diesen Knoten sind keine Textauszüge hinterlegt "
                       "(Indizes zeigen ins Inhaltsverzeichnis der Quelle).")

        ac1, ac2, ac3, ac4 = st.columns(4)
        if ac1.button("🔎 Dazu fragen", key=f"mm_chat_{_active_id}",
                      use_container_width=True,
                      help="Stellt die Frage im Chat unten – bleibt auf dieser Seite."):
            _q = f"Erkläre mir das Thema: {_title_join}. Gehe nur auf diesen Stoff ein."
            if _excerpts:
                _q += "\n\nQuellenauszug:\n" + _excerpts[:1600]
            st.session_state[f"_mm_chat_pending_{_active_id}"] = _q
            st.rerun()
        if ac2.button("🧮 Übung", key=f"mm_practice_{_active_id}",
                      use_container_width=True):
            st.session_state["practice_prefill"] = {
                "subject": _active["subject"], "doc_ids": _active["doc_ids"],
                "topic": _title_join,
            }
            st.switch_page("pages/13_🧮_Übungsaufgaben.py")
        if ac3.button("🎴 Karten aus dem Thema", key=f"mm_cards_{_active_id}",
                      use_container_width=True,
                      help="Legt Karteikarten aus den Quellen dieses Themas an "
                           "(springt nicht auf eine leere Lernen-Seite)."):
            if not _excerpts:
                st.warning("Kein Text zu diesem Thema – Karten brauchen einen Quellenauszug.")
            else:
                from ragapp.student_flow import cards_from_markdown
                _ids = cards_from_markdown(
                    _excerpts, subject=_active.get("subject"), source="mindmap")
                if _ids:
                    st.success(f"{len(_ids)} Karte(n) angelegt. Lernen startet sie über den Stapel.")
                else:
                    st.info("Aus diesem Auszug liessen sich keine Karten ableiten.")
        if ac4.button("📄 Kurzfassung", key=f"mm_sum_{_active_id}",
                      use_container_width=True,
                      help="Fasst nur die gewählten Themen zusammen – bleibt hier, "
                           "statt auf die leere Zusammenfassungs-Seite zu springen."):
            _q = ("Schreibe eine klausurtaugliche Kurzfassung NUR zu diesem Thema: "
                  f"{_title_join}. Nutze ausschliesslich den Quellenauszug, erfinde nichts.\n\n"
                  f"{_excerpts[:2000] if _excerpts else '(kein Auszug vorhanden)'}")
            st.session_state[f"_mm_chat_pending_{_active_id}"] = _q
            st.rerun()

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
    if _selected:
        st.caption("Antwortet zu **" + _title_join + "** aus den "
                   + str(len(_active["doc_ids"])) +
                   " Dokument(en) dieser Mindmap – nicht aus dem Rest der Bibliothek.")
        _chat_placeholder = f"Frage zu {_title_join} …"
    else:
        st.caption("Antwortet nur aus den " + str(len(_active["doc_ids"])) +
                  " Dokument(en) dieser Mindmap - nicht aus dem Rest deiner Bibliothek. "
                  "Wähle ein Thema, damit die Frage darauf eingegrenzt wird.")
        _chat_placeholder = "Frage zu diesen Dokumenten …"

    _chat_key = f"mm_chat_messages_{_active_id}"
    st.session_state.setdefault(_chat_key, [])

    if st.session_state[_chat_key] and delete_button(
            "🗑️ Chat-Verlauf löschen", token=f"mmchat:{_active_id}",
            body="Den Chat-Verlauf dieser Mindmap wirklich leeren?",
            key=f"mm_chat_clear_{_active_id}"):
        st.session_state[_chat_key] = []
        st.rerun()

    for _mi, _msg in enumerate(st.session_state[_chat_key]):
        with st.chat_message(_msg["role"], avatar="🧑‍🎓" if _msg["role"] == "user" else "🤖"):
            st.markdown(_msg["content"])
            if _msg.get("sources"):
                with st.expander(f"📚 Quellen ({len(_msg['sources'])})"):
                    for s in _msg["sources"]:
                        loc = f" · {s['location']}" if s.get("location") else ""
                        st.caption(f"[{s['rank']}] {s['filename']}{loc}")
                        _snip = s.get("snippet", "")
                        st.caption("„" + _snip[:240] + ("…" if len(_snip) > 240 else "") + "”")
            if _msg["role"] == "assistant" and (_msg.get("content") or "").strip():
                _prev = st.session_state[_chat_key][_mi - 1] if _mi > 0 else {}
                _q = _prev.get("content") if _prev.get("role") == "user" else None
                if _q and st.button(
                        "➕ Als Karte speichern",
                        key=f"mm_save_card_{_active_id}_{_mi}"):
                    from ragapp import study as _mm_study
                    _cid = _mm_study.card_from_chat(
                        _q, _msg["content"],
                        subject=_active.get("subject"),
                        sources=_msg.get("sources"))
                    st.toast("📇 Als Karte gespeichert – üben auf 🎓 Karteikarten!"
                             if _cid else "Konnte keine Karte anlegen.")

    _mm_prompt = st.chat_input(_chat_placeholder, key=f"mm_chat_input_{_active_id}")
    if not _mm_prompt:
        _mm_prompt = st.session_state.pop(f"_mm_chat_pending_{_active_id}", None)

    if _mm_prompt:
        _rag_prompt = _mm_prompt
        if _selected and "Quellenauszug:" not in _mm_prompt:
            _rag_prompt = (
                f"Die Frage bezieht sich NUR auf: {_title_join}.\n{_mm_prompt}")
            if _excerpts:
                _rag_prompt += "\n\nQuellenauszug:\n" + _excerpts[:1200]
        st.session_state[_chat_key].append({"role": "user", "content": _mm_prompt})
        with st.chat_message("user", avatar="🧑‍🎓"):
            st.markdown(_mm_prompt)
        with st.chat_message("assistant", avatar="🤖"):
            from ragapp.graph.rag_graph import answer_query_stream
            from ragapp.ui._progress import LlmWait
            _history = [{"role": m["role"], "content": m["content"]}
                       for m in st.session_state[_chat_key][:-1]]
            with LlmWait("Suche in den Unterlagen …") as wait:
                def _on_stage(name: str) -> None:
                    if name == "generate":
                        wait.set("Formuliere Antwort …")
                    else:
                        wait.set("Suche in den Unterlagen …")
                try:
                    _mm_stream, _mm_holder = answer_query_stream(
                        _rag_prompt, subject=_active["subject"], doc_ids=_active["doc_ids"],
                        check_faithfulness=False, history=_history, chat_mode="tutor",
                        on_stage=_on_stage)
                except Exception:  # noqa: BLE001 - Setup-Fehler -> als Antwort anzeigen
                    _mm_stream, _mm_holder = None, {}
                if _mm_stream is not None:
                    try:
                        wait.set("Formuliere Antwort …")
                        _mm_answer = st.write_stream(_mm_stream)
                    except Exception as exc:  # noqa: BLE001 - Stream-Fehler nie roh anzeigen
                        _mm_answer = _mm_holder.get("answer") or f"Fehler: {exc}"
                else:
                    _mm_answer = _mm_holder.get("answer") or "Keine Antwort erhalten."
                    st.markdown(_mm_answer)
                wait.done()
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
