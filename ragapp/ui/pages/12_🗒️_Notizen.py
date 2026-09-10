"""
RAG-Lernsystem: Seite „Notizen" (freie, eigene Gedanken)
==========================================================
Im Unterschied zu JEDEM anderen Inhalt dieser App (Zusammenfassung, Karteikarten,
Gliederung, Übungsaufgaben) ist hier NICHTS KI-generiert - das ist der Ort für
eigene Gedanken, Fragen, Merksätze. Optional an ein Fach, ein Dokument oder ein
Thema geheftet, oder frei in einer "Sammlung".

Bewusst NICHT im RAG-Index: der BM25-Index (siehe ragapp/retrieval/bm25_index.py)
baut ausschließlich aus indexierten Dokument-Chunks (type='chunk'); Notizen dort
einzuspeisen würde drei Retrieval-Hot-Path-Dateien anfassen und unkuratierten,
nicht garantiert korrekten Text in den sorgfältig auf Anti-Halluzination getunten
Chat-Beleg-Pfad mischen - für einen Nutzen, den der Kernwert des Features (freier,
ungefilterter Gedankenraum) nicht braucht. Volltextsuche läuft daher rein in SQLite.
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
page_boot("🗒️ Notizen", page_title="Notizen", icon="🗒️", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1150px;}
h1 {font-weight: 750; letter-spacing:-0.5px;}
.notiz-item {padding:8px 10px; border-radius:8px; margin-bottom:4px; cursor:pointer;}
.notiz-item-title {font-weight:650; font-size:.9rem;}
.notiz-item-meta {font-size:.75rem; opacity:.7;}
</style>
""", unsafe_allow_html=True)

st.caption("Deine eigenen Gedanken, Fragen und Merksätze – im Unterschied zu allem "
           "anderen in dieser App NICHT KI-generiert. Optional an ein Fach, ein "
           "Dokument oder eine Sammlung geheftet.")

with st.spinner("Notizen werden geladen ..."):
    from ragapp import manifest
    from ragapp.config import SUBJECT_LABELS


def _fach(code: "str | None") -> str:
    return SUBJECT_LABELS.get(code, code) if code else "–"


_known_subjects = sorted(
    set(SUBJECT_LABELS.keys())
    | {d["subject"] for d in manifest.list_documents() if d["subject"]})

# --------------------------------------------------------------------------- #
# Prefill aus anderen Seiten (Chat: Antwort als Notiz; Dokumentenmanager: Notiz
# zu einem Dokument) - MUSS vor der Instanziierung der betroffenen Widgets
# gesetzt werden (gleiches Muster wie splan_prefill/pomo_prefill).
# --------------------------------------------------------------------------- #
_prefill = st.session_state.pop("note_prefill", None)
if _prefill:
    st.session_state["_notiz_pending_choice"] = None   # in den "Neue Notiz"-Editor springen
    st.session_state["notiz_new_subject"] = (
        _prefill.get("subject") if _prefill.get("subject") in _known_subjects else None)
    st.session_state["notiz_new_title"] = _prefill.get("title") or ""
    st.session_state["notiz_new_body"] = _prefill.get("body") or ""
    st.session_state["notiz_new_doc_id"] = _prefill.get("doc_id")
    st.session_state["notiz_new_topic"] = _prefill.get("topic")
    st.session_state["notiz_new_preview"] = False
    st.info("📝 Vorbelegt – unten ergänzen und speichern.")

# --------------------------------------------------------------------------- #
# Filter (links) + Auswahl
# --------------------------------------------------------------------------- #
fcol, lcol = st.columns([1, 2])
with fcol:
    _f_subject = st.selectbox("Fach", ["Alle Fächer"] + _known_subjects,
                              format_func=lambda s: s if s == "Alle Fächer" else _fach(s),
                              key="notiz_filter_subject")
with lcol:
    _f_search = st.text_input("🔎 Suche (Titel/Text)", key="notiz_filter_search")

_subj_arg = None if _f_subject == "Alle Fächer" else _f_subject
_notes = manifest.list_notes(subject=_subj_arg, search=_f_search or None)

st.divider()

col_list, col_editor = st.columns([1, 2])

# --------------------------------------------------------------------------- #
# Linke Spalte: Liste
# --------------------------------------------------------------------------- #
with col_list:
    if st.button("➕ Neue Notiz", use_container_width=True, type="primary"):
        st.session_state["_notiz_pending_choice"] = None
        for _k in ("notiz_new_subject", "notiz_new_title", "notiz_new_body",
                  "notiz_new_body_draft", "notiz_new_doc_id", "notiz_new_topic",
                  "notiz_new_collection", "notiz_new_preview"):
            st.session_state.pop(_k, None)
        st.rerun()

    if "_notiz_pending_choice" in st.session_state:
        st.session_state["notiz_choice"] = st.session_state.pop("_notiz_pending_choice")
    # KEIN Reset mehr, wenn die aktive Notiz nur aus der GEFILTERTEN Liste faellt
    # (z. B. Fach-Filter auf ein anderes Fach umgestellt, waehrend man gerade
    # editiert) - das hat faelschlich mitten im Bearbeiten in den "Neue Notiz"-
    # Editor geworfen, nur weil ein reiner Anzeigefilter geaendert wurde. Die
    # Editor-Sektion unten faellt ohnehin sauber auf "Neue Notiz" zurueck, falls
    # die Notiz tatsaechlich geloescht wurde (manifest.get_note liefert dann None).

    if not _notes:
        st.caption("Noch keine Notizen für diese Filterung." if (_subj_arg or _f_search)
                  else "Noch keine Notizen – leg oben die erste an.")
    with st.container(height=480):
        for n in _notes:
            _label = ("📌 " if n["pinned"] else "") + (n["title"] or "(ohne Titel)")
            _meta = _fach(n["subject"]) + (f" · {n['collection']}" if n.get("collection") else "")
            _active = st.session_state.get("notiz_choice") == n["note_id"]
            if st.button(f"{'▶️ ' if _active else ''}{_label}", key=f"notiz_pick_{n['note_id']}",
                        use_container_width=True, help=_meta):
                st.session_state["_notiz_pending_choice"] = n["note_id"]
                st.rerun()

# --------------------------------------------------------------------------- #
# Rechte Spalte: Editor
# --------------------------------------------------------------------------- #
_active_id = st.session_state.get("notiz_choice")
_active_note = manifest.get_note(_active_id) if _active_id else None

# Beim Wechsel der aktiven Notiz die Editor-Widgets der VORHER offenen Notiz
# verwerfen (nicht erst beim naechsten Besuch). Ohne das wuerde Streamlit einen
# ungespeicherten Entwurf beim spaeteren Zurueckkehren zu dieser Notiz faelschlich
# wieder anzeigen, statt des echten (gespeicherten) DB-Stands - die Widgets sind
# je Notiz-ID verschluesselt, ihr session_state bleibt sonst beliebig lang stehen.
_prev_shown = st.session_state.get("_notiz_last_shown_id")
if _prev_shown != _active_id:
    if _prev_shown:
        for _suffix in ("subject", "collection", "title", "body", "body_draft",
                        "pinned", "preview"):
            st.session_state.pop(f"notiz_edit_{_suffix}_{_prev_shown}", None)
    st.session_state["_notiz_last_shown_id"] = _active_id

with col_editor:
    if _active_note is None:
        st.markdown("##### ✏️ Neue Notiz")
        ec1, ec2 = st.columns(2)
        with ec1:
            _e_subject = st.selectbox("Fach (optional)", [None] + _known_subjects,
                                      format_func=lambda s: "–" if s is None else _fach(s),
                                      key="notiz_new_subject")
        with ec2:
            _e_collection = st.text_input(
                "Sammlung (optional)", key="notiz_new_collection",
                help="Freier Name, z. B. 'Klausurvorbereitung' – wie ein Karteikarten-Stapel.")
        _e_title = st.text_input("Titel (optional)", key="notiz_new_title")

        # Streamlit verwirft den internen Zustand eines Widgets, das in einem
        # Durchlauf NICHT instanziiert wird (hier: waehrend die Vorschau steht) -
        # beim Zurueckschalten entsteht ein KOMPLETT NEUES text_area mit dem
        # Ausgangswert, der eingetippte Text waere weg. Deshalb wird der Text
        # zusaetzlich in einem eigenen, IMMER erhaltenen Schluessel gespiegelt
        # (bei jedem Rendern des text_area aktualisiert) und beim Zurueckschalten
        # als expliziter Startwert zurueckgegeben.
        _draft_key = "notiz_new_body_draft"
        _preview = st.toggle("👁️ Vorschau", key="notiz_new_preview")
        if _preview:
            st.markdown(st.session_state.get(_draft_key) or "*(leer)*")
        else:
            st.session_state[_draft_key] = st.text_area(
                "Text (Markdown)", value=st.session_state.get(_draft_key, ""),
                height=280, key="notiz_new_body")

        if st.button("💾 Notiz anlegen", type="primary", disabled=not
                     (st.session_state.get(_draft_key) or "").strip()):
            nid = manifest.create_note(
                subject=_e_subject, doc_id=st.session_state.get("notiz_new_doc_id"),
                topic=st.session_state.get("notiz_new_topic"),
                collection=(_e_collection or "").strip() or None,
                title=_e_title, body=st.session_state[_draft_key])
            st.success("Notiz angelegt.")
            st.session_state["_notiz_pending_choice"] = nid
            st.rerun()
    else:
        st.markdown("##### ✏️ Notiz bearbeiten")
        _nid = _active_note["note_id"]
        mc1, mc2 = st.columns(2)
        with mc1:
            _cur_subj = _active_note.get("subject")
            _subj_opts = [None] + _known_subjects
            _idx = _subj_opts.index(_cur_subj) if _cur_subj in _subj_opts else 0
            _m_subject = st.selectbox("Fach (optional)", _subj_opts, index=_idx,
                                      format_func=lambda s: "–" if s is None else _fach(s),
                                      key=f"notiz_edit_subject_{_nid}")
        with mc2:
            _m_collection = st.text_input("Sammlung (optional)",
                                          value=_active_note.get("collection") or "",
                                          key=f"notiz_edit_collection_{_nid}")
        _m_title = st.text_input("Titel (optional)", value=_active_note.get("title") or "",
                                 key=f"notiz_edit_title_{_nid}")
        if _active_note.get("doc_id") or _active_note.get("topic"):
            st.caption("🔗 Verknüpft mit: " + " · ".join(
                x for x in (_active_note.get("doc_id"), _active_note.get("topic")) if x))

        _prev_key = f"notiz_edit_preview_{_nid}"
        _body_key = f"notiz_edit_body_{_nid}"
        # Wie beim "Neue Notiz"-Editor: das text_area wird beim Umschalten auf
        # Vorschau NICHT gerendert -> Streamlit verwirft seinen internen Zustand.
        # Eigener, immer erhaltener Spiegel-Schluessel verhindert den Textverlust
        # beim Zurueckschalten.
        _draft_key = f"notiz_edit_body_draft_{_nid}"
        _m_preview = st.toggle("👁️ Vorschau", key=_prev_key)
        if _m_preview:
            st.markdown(st.session_state.get(_draft_key, _active_note.get("body") or ""))
        else:
            st.session_state[_draft_key] = st.text_area(
                "Text (Markdown)",
                value=st.session_state.get(_draft_key, _active_note.get("body") or ""),
                height=280, key=_body_key)

        _m_pinned = st.checkbox("📌 Angeheftet (immer oben in der Liste)",
                                value=bool(_active_note.get("pinned")),
                                key=f"notiz_edit_pinned_{_nid}")

        bc1, bc2 = st.columns(2)
        if bc1.button("💾 Speichern", type="primary", use_container_width=True):
            manifest.update_note(
                _nid, subject=_m_subject, collection=(_m_collection or "").strip() or None,
                title=_m_title, body=st.session_state.get(_draft_key, _active_note.get("body")),
                pinned=_m_pinned)
            st.success("Gespeichert.")
            st.rerun()
        if bc2.button("🗑️ Löschen", use_container_width=True):
            manifest.delete_note(_nid)
            st.session_state["_notiz_pending_choice"] = None
            st.success("Notiz gelöscht.")
            st.rerun()
