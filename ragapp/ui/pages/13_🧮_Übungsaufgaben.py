"""
RAG-Lernsystem: Seite „Übungsaufgaben" (mehrschrittige Rechen-/Anwendungsaufgaben)
====================================================================================
Im Unterschied zu den Karteikarten (SM-2/FSRS, Seite „Lernen") wird hier NICHTS
„fällig" - eine mehrabsatzige Rechenaufgabe mit bekannten Zahlen erneut „in 2
Minuten" abzufragen wäre unehrlich. Aufgaben bleiben dauerhaft in der Liste zum
erneuten Üben, mit progressiven Hinweisen und Schritt-für-Schritt-Musterlösung.
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
page_boot("🧮 Übungsaufgaben", page_title="Übungsaufgaben", icon="🧮", layout="wide",
         accent="uebungsaufgaben")

from ragapp.ui._style import card

st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1150px;}
h1 {font-weight: 750; letter-spacing:-0.5px;}
.pa-item-title {font-weight:650; font-size:.9rem;}
.pa-item-meta {font-size:.75rem; opacity:.7;}
</style>
""", unsafe_allow_html=True)

st.caption("Mehrschrittige Rechenaufgaben und Anwendungsszenarien mit Musterlösung "
           "aus deinen indexierten Dokumenten - mit progressiven Hinweisen statt "
           "sofortiger Lösung.")

with st.spinner("Übungsaufgaben werden geladen ..."):
    from ragapp import manifest, practice_gen
    from ragapp.config import settings, SUBJECT_LABELS

_KIND_LABEL = {"numeric": "🧮 Rechenaufgabe", "scenario": "📖 Anwendungsszenario"}
_RATING_LABEL = {0: "❌ nicht gewusst", 1: "🟡 teilweise", 2: "✅ gewusst"}


def _fach(code: "str | None") -> str:
    return SUBJECT_LABELS.get(code, code) if code else "–"


_all_docs = [dict(d) for d in manifest.list_documents()
            if d["use_rag"] and d["num_chunks"] > 0]
_subjects_with_docs = sorted({d["subject"] for d in _all_docs if d["subject"]})

if not _subjects_with_docs:
    st.info("Noch keine indexierten Dokumente (im RAG) vorhanden. Gehe zu "
            "**📥 Ingestion**, um welche hinzuzufügen.")
    st.stop()

# --------------------------------------------------------------------------- #
# Prefill aus dem Lernplan ("🧮 Übungsaufgabe zu diesem Thema") - MUSS vor der
# Instanziierung der betroffenen Widgets gesetzt werden (gleiches Muster wie
# note_prefill/pomo_prefill).
# --------------------------------------------------------------------------- #
_prefill = st.session_state.pop("practice_prefill", None)
if _prefill and _prefill.get("subject") in _subjects_with_docs:
    st.session_state["practice_gen_subject"] = _prefill["subject"]
    st.session_state["_practice_prefill_doc_ids"] = _prefill.get("doc_ids") or []
    st.session_state["practice_gen_topic"] = _prefill.get("topic") or ""
    st.session_state["_practice_gen_expanded"] = True
    st.info("🧮 Vorbelegt aus dem Lernplan – unten Art/Modell wählen und generieren.")

# --------------------------------------------------------------------------- #
# Neue Aufgabe generieren
# --------------------------------------------------------------------------- #
_existing_count = manifest.count_practice_problems()
# key= haelt den Auf/Zu-Zustand fest - ohne key faellt der Expander sonst bei
# JEDEM Rerun (auch nur durch die "Fach"-Auswahl DARIN) auf zugeklappt zurueck.
# Das erzwungene Aufklappen beim Prefill aus dem Lernplan (siehe oben) muss
# dafuer jetzt DIREKT in den Widget-Schluessel schreiben (gleiches "pending"-
# Muster wie an anderen Stellen der App), statt nur den `expanded`-Parameter zu
# setzen - der wird bei einem bereits belegten Schluessel sonst ignoriert.
if st.session_state.pop("_practice_gen_expanded", False):
    st.session_state["practice_gen_expander"] = True
with st.expander("➕ Neue Übungsaufgabe generieren",
                 expanded=not _existing_count, key="practice_gen_expander"):
    gc1, gc2 = st.columns(2)
    with gc1:
        _g_subject = st.selectbox("Fach", _subjects_with_docs, format_func=_fach,
                                  key="practice_gen_subject")
    _subj_docs = {d["filename"]: d["doc_id"] for d in _all_docs if d["subject"] == _g_subject}
    _prefill_doc_ids = set(st.session_state.pop("_practice_prefill_doc_ids", []))
    if _prefill_doc_ids:
        st.session_state["practice_gen_docs"] = [n for n, did in _subj_docs.items()
                                                  if did in _prefill_doc_ids]
    with gc2:
        _g_doc_names = st.multiselect("Dokument(e)", list(_subj_docs.keys()),
                                      key="practice_gen_docs", placeholder="Auswählen …")
    _g_topic = st.text_input("Thema (optional, engt den Stoff ein)", key="practice_gen_topic")

    gc3, gc4 = st.columns(2)
    with gc3:
        _g_kind_choice = st.radio(
            "Art", ["🤖 Automatisch", "🧮 Rechenaufgabe", "📖 Anwendungsszenario"],
            horizontal=True, key="practice_gen_kind")
    with gc4:
        _g_model_choice = st.radio(
            "Modell", ["🎯 Gründlich (langsamer)", "⚡ Schnell (gröber)"],
            horizontal=True, key="practice_gen_model")

    if st.button("🧮 Aufgabe generieren", type="primary", disabled=not _g_doc_names):
        _kind_arg = {"🧮 Rechenaufgabe": "numeric",
                    "📖 Anwendungsszenario": "scenario"}.get(_g_kind_choice)
        _model_arg = settings.LLM_MODEL_FAST if "Schnell" in _g_model_choice else None
        _doc_ids = [_subj_docs[n] for n in _g_doc_names]
        with st.spinner("KI erstellt die Aufgabe … das kann je nach Umfang und "
                        "Hardware einige Zeit dauern."):
            try:
                _new_pid = practice_gen.generate_practice_problem(
                    subject=_g_subject, doc_ids=_doc_ids, topic=_g_topic or None,
                    kind=_kind_arg, model=_model_arg)
            except practice_gen.PracticeGenError as exc:
                st.error(str(exc))
                st.stop()
        st.success("Aufgabe erstellt.")
        st.session_state["_practice_pending_choice"] = _new_pid
        st.rerun()

st.divider()

# --------------------------------------------------------------------------- #
# Filter + Liste
# --------------------------------------------------------------------------- #
fc1, fc2 = st.columns(2)
with fc1:
    _f_subject = st.selectbox("Fach", ["Alle Fächer"] + _subjects_with_docs,
                              format_func=lambda s: s if s == "Alle Fächer" else _fach(s),
                              key="practice_filter_subject")
with fc2:
    _f_kind_choice = st.selectbox(
        "Art", ["Alle Arten", "🧮 Rechenaufgabe", "📖 Anwendungsszenario"],
        key="practice_filter_kind")

_subj_arg = None if _f_subject == "Alle Fächer" else _f_subject
_kind_arg = {"🧮 Rechenaufgabe": "numeric",
            "📖 Anwendungsszenario": "scenario"}.get(_f_kind_choice)
_problems = manifest.list_practice_problems(subject=_subj_arg, kind=_kind_arg)

if "_practice_pending_choice" in st.session_state:
    st.session_state["practice_choice"] = st.session_state.pop("_practice_pending_choice")
# KEIN Reset, wenn die aktive Aufgabe nur aus der GEFILTERTEN Liste faellt (z. B.
# Fach-Filter umgestellt) - derselbe Grund wie bei den Notizen: ein reiner
# Anzeigefilter soll nicht die gerade geuebte Aufgabe wegreissen.

col_list, col_practice = st.columns([1, 2])

with col_list:
    with card("liste"):
        if not _problems:
            # KEIN leerer st.container(height=480) mehr, wenn es nichts zu
            # zeigen gibt - wirkte sonst wie ein verwaistes, kaputtes Element
            # (grosse leere Flaeche unter dem Hinweistext, siehe gleicher Fix
            # bei Notizen).
            st.caption("Noch keine Übungsaufgaben für diese Filterung." if (_subj_arg or _kind_arg)
                      else "Noch keine Übungsaufgaben – oben die erste generieren.")
        else:
            with st.container(height=480):
                for p in _problems:
                    _label = _KIND_LABEL.get(p["kind"], p["kind"]) + " · " + (
                        p["topic"] or (p["problem_text"][:40] + "…"
                                      if len(p["problem_text"]) > 40 else p["problem_text"]))
                    _meta = _fach(p["subject"])
                    _active = st.session_state.get("practice_choice") == p["problem_id"]
                    if st.button(f"{'▶️ ' if _active else ''}{_label}",
                                key=f"practice_pick_{p['problem_id']}",
                                use_container_width=True, help=_meta):
                        st.session_state["_practice_pending_choice"] = p["problem_id"]
                        st.rerun()

# --------------------------------------------------------------------------- #
# Übungsfluss
# --------------------------------------------------------------------------- #
_active_id = st.session_state.get("practice_choice")
_active = manifest.get_practice_problem(_active_id) if _active_id else None

with col_practice:
    with card("aufgabe"):
        if _active is None:
            st.caption("← Wähle links eine Aufgabe oder generiere oben eine neue.")
        else:
            pid = _active["problem_id"]
            _hint_key = f"practice_hints_{pid}"
            _step_key = f"practice_steps_{pid}"
            _resolved_key = f"practice_resolved_{pid}"
            st.session_state.setdefault(_hint_key, 0)
            st.session_state.setdefault(_step_key, 0)
            st.session_state.setdefault(_resolved_key, False)

            st.markdown(f"##### {_KIND_LABEL.get(_active['kind'], _active['kind'])}")
            if _active.get("topic"):
                st.caption(f"Thema: {_active['topic']}")
            st.markdown(_active["problem_text"])

            if _active["given"]:
                st.markdown("**Gegeben:**")
                for g in _active["given"]:
                    st.markdown(f"- {g.get('label', '')}: {g.get('value', '')}"
                               if g.get("label") else f"- {g.get('value', '')}")

            hcol, scol, rcol = st.columns(3)
            _n_hints = len(_active["hints"])
            if hcol.button(f"💡 Hinweis ({st.session_state[_hint_key]}/{_n_hints})",
                          key=f"practice_hint_btn_{pid}", use_container_width=True,
                          disabled=st.session_state[_hint_key] >= _n_hints):
                st.session_state[_hint_key] += 1
                st.rerun()
            _n_steps = len(_active["steps"])
            if scol.button(f"▶️ Nächster Schritt ({st.session_state[_step_key]}/{_n_steps})",
                          key=f"practice_step_btn_{pid}", use_container_width=True,
                          disabled=st.session_state[_step_key] >= _n_steps):
                st.session_state[_step_key] += 1
                st.rerun()
            if rcol.button("🏁 Lösung anzeigen", key=f"practice_resolve_btn_{pid}",
                           use_container_width=True,
                           disabled=st.session_state[_resolved_key]):
                st.session_state[_resolved_key] = True
                st.rerun()

            if st.session_state[_hint_key] > 0:
                for h in _active["hints"][:st.session_state[_hint_key]]:
                    st.info(f"💡 {h}")

            if st.session_state[_step_key] > 0:
                st.markdown("**Lösungsweg bisher:**")
                for i, s in enumerate(_active["steps"][:st.session_state[_step_key]], 1):
                    st.markdown(f"{i}. {s.get('step_text', '')}")

            if st.session_state[_resolved_key] or st.session_state[_step_key] >= _n_steps:
                if _active.get("final_answer"):
                    st.success(f"**Endergebnis:** {_active['final_answer']}")

            if _active.get("source_excerpt"):
                with st.expander("📚 Beleg (Textgrundlage)"):
                    st.caption(_active["source_excerpt"])

            st.markdown("**Wie lief's?**")
            r1, r2, r3 = st.columns(3)

            def _bewerten(rating: int) -> None:
                manifest.log_practice_attempt(pid, self_rating=rating)
                for k in (_hint_key, _step_key):
                    st.session_state[k] = 0
                st.session_state[_resolved_key] = False
                st.rerun()

            if r1.button("❌ Nicht gewusst", key=f"practice_rate0_{pid}", use_container_width=True):
                _bewerten(0)
            if r2.button("🟡 Teilweise", key=f"practice_rate1_{pid}", use_container_width=True):
                _bewerten(1)
            if r3.button("✅ Gewusst", key=f"practice_rate2_{pid}", use_container_width=True):
                _bewerten(2)

            _attempts = manifest.list_practice_attempts(pid, limit=5)
            if _attempts:
                _hist = " · ".join(_RATING_LABEL.get(a["self_rating"], "?") for a in _attempts)
                st.caption(f"Bisher {len(_attempts)}x geübt (neueste zuerst): {_hist}")

            if st.button("🗑️ Aufgabe löschen", key=f"practice_delete_{pid}"):
                manifest.delete_practice_problem(pid)
                st.session_state["_practice_pending_choice"] = None
                st.success("Aufgabe gelöscht.")
                st.rerun()
