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

from ragapp.ui._loading import page_boot, skeleton
page_boot("🧮 Übungsaufgaben", page_title="Übungsaufgaben", icon="🧮", layout="wide",
         accent="uebungsaufgaben")

from ragapp.ui._style import block_done_banner, card, delete_button, sticky_expander

st.markdown("""
<style>
.pa-item-title {font-weight:650; font-size:.9rem;}
.pa-item-meta {font-size:.75rem;}
</style>
""", unsafe_allow_html=True)

st.caption("Rechenweg eintippen, Teilpunkte erhalten, fehlende Schritte nachlesen.")

with skeleton("Übungsaufgaben werden geladen …"):
    from ragapp import manifest, practice_gen, student_flow
    from ragapp.config import settings, SUBJECT_LABELS

_KIND_LABEL = {
    "numeric": "🧮 Rechenaufgabe",
    "proof": "📐 Begründung / Beweis",
    "scenario": "📖 Anwendungsszenario",
}
_RATING_LABEL = {0: "❌ nicht gewusst", 1: "🟡 teilweise", 2: "✅ gewusst"}


def _fach(code: "str | None") -> str:
    return SUBJECT_LABELS.get(code, code) if code else "–"


_all_docs = [dict(d) for d in manifest.list_documents()
            if d["use_rag"] and d["num_chunks"] > 0]
_subjects_with_docs = sorted({d["subject"] for d in _all_docs if d["subject"]})

if not _subjects_with_docs:
    from ragapp.ui._style import empty_state, page_title as _pt
    empty_state(
        "Noch keine indexierten Dokumente vorhanden.",
        cta_label=f"Zu {_pt('dokumente')}",
        page_key="dokumente",
        icon="📥",
        key="uebung_empty_dokumente",
    )
    st.stop()

# --------------------------------------------------------------------------- #
# Prefill aus Kurs/Lernplan ("Übung starten" / Plan-Block) - MUSS vor der
# Instanziierung der betroffenen Widgets gesetzt werden.
# --------------------------------------------------------------------------- #
_prefill = st.session_state.pop("practice_prefill", None)
if _prefill:
    _psubj = _prefill.get("subject")
    if _psubj in _subjects_with_docs:
        st.session_state["practice_gen_subject"] = _psubj
        st.session_state["practice_filter_subject"] = _psubj
        st.session_state["_practice_prefill_doc_ids"] = _prefill.get("doc_ids") or []
        st.session_state["_practice_prefill_all_docs"] = not (_prefill.get("doc_ids") or [])
        st.session_state["practice_gen_topic"] = _prefill.get("topic") or ""
        st.session_state["practice_gen_expander"] = True
        _pids = [p for p in (_prefill.get("problem_ids") or []) if p]
        if _pids:
            st.session_state["practice_choice"] = _pids[0]
        if _prefill.get("block_id"):
            st.session_state["_practice_from_block_id"] = _prefill["block_id"]
        _src = _prefill.get("source") or ""
        if _src == "coverage":
            st.info("🧮 Vorbelegt aus der Lernziel-Lücke – Thema und Fach stehen "
                    "im Generator; vorhandene Aufgaben siehst du in der Liste.")
        elif _src == "plan":
            st.info("🧮 Vorbelegt aus dem Lernplan – unten Art/Modell wählen und generieren.")
        else:
            st.info("🧮 Fach und Thema sind vorbelegt – unten Art/Modell wählen und generieren.")
    elif _psubj:
        st.warning(f"Keine indexierten Unterlagen für {_fach(_psubj)} – "
                   "zuerst ein Dokument anlegen, dann die Übung starten.")

if st.session_state.get("_practice_session_done"):
    block_done_banner(state_key="_practice_from_block_id", key_prefix="practice")
    if not st.session_state.get("_practice_from_block_id"):
        st.session_state.pop("_practice_session_done", None)

# --------------------------------------------------------------------------- #
# Neue Aufgabe generieren
# --------------------------------------------------------------------------- #
_existing_count = manifest.count_practice_problems()
with sticky_expander("➕ Neue Übungsaufgabe generieren",
                     key="practice_gen_expander",
                     expanded=not _existing_count):
    gc1, gc2 = st.columns(2)
    with gc1:
        _g_subject = st.selectbox("Fach", _subjects_with_docs, format_func=_fach,
                                  key="practice_gen_subject")
    _subj_docs = {d["filename"]: d["doc_id"] for d in _all_docs if d["subject"] == _g_subject}
    _prefill_doc_ids = set(st.session_state.pop("_practice_prefill_doc_ids", []))
    _prefill_all_docs = st.session_state.pop("_practice_prefill_all_docs", False)
    if _prefill_doc_ids:
        st.session_state["practice_gen_docs"] = [n for n, did in _subj_docs.items()
                                                  if did in _prefill_doc_ids]
    elif _prefill_all_docs:
        st.session_state["practice_gen_docs"] = list(_subj_docs.keys())
    with gc2:
        _g_doc_names = st.multiselect("Dokument(e)", list(_subj_docs.keys()),
                                      key="practice_gen_docs", placeholder="Auswählen …")
    _g_topic = st.text_input("Thema (optional, engt den Stoff ein)", key="practice_gen_topic")

    gc3, gc4 = st.columns(2)
    with gc3:
        _g_kind_choice = st.radio(
            "Art",
            ["🤖 Automatisch", "🧮 Rechenaufgabe", "📐 Begründung / Beweis",
             "📖 Anwendungsszenario"],
            horizontal=True, key="practice_gen_kind",
            help="Automatisch erkennt Rechnen, Beweisaufgaben (höhere Mathe) "
                 "und Fallbeispiele für nicht-mathelastige Fächer.")
    with gc4:
        _g_model_choice = st.radio(
            "Modell", ["🎯 Gründlich (langsamer)", "⚡ Schnell (gröber)"],
            horizontal=True, key="practice_gen_model")

    if st.button("🧮 Aufgabe generieren", type="primary", disabled=not _g_doc_names):
        _kind_arg = {"🧮 Rechenaufgabe": "numeric",
                    "📐 Begründung / Beweis": "proof",
                    "📖 Anwendungsszenario": "scenario"}.get(_g_kind_choice)
        _model_arg = settings.LLM_MODEL_FAST if "Schnell" in _g_model_choice else None
        _doc_ids = [_subj_docs[n] for n in _g_doc_names]
        with st.spinner("KI erstellt die Aufgabe aus den gewählten Unterlagen … "
                        "das kann je nach Umfang einige Minuten dauern."):
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
        "Art",
        ["Alle Arten", "🧮 Rechenaufgabe", "📐 Begründung / Beweis",
         "📖 Anwendungsszenario"],
        key="practice_filter_kind")

_subj_arg = None if _f_subject == "Alle Fächer" else _f_subject
_kind_arg = {"🧮 Rechenaufgabe": "numeric",
            "📐 Begründung / Beweis": "proof",
            "📖 Anwendungsszenario": "scenario"}.get(_f_kind_choice)
_problems = manifest.list_practice_problems(subject=_subj_arg, kind=_kind_arg)

# --------------------------------------------------------------------------- #
# "Was lohnt sich zu wiederholen?" - bewusst NICHT als "fällig" formuliert
# (siehe Modul-Docstring: Aufgaben werden hier absichtlich NIE fällig wie
# Karteikarten) - nur eine sanfte Empfehlung, welche Aufgabe am ehesten noch
# einmal dran ist: nie geübt oder zuletzt "nicht gewusst" zuerst, danach am
# laengsten nicht mehr angefasst. Rein additive Sortierung/Badge, aendert
# nichts an den Aufgaben selbst.
# --------------------------------------------------------------------------- #
_attempt_summary = manifest.practice_attempt_summary([p["problem_id"] for p in _problems])


def _practice_priority(p: dict) -> tuple:
    info = _attempt_summary.get(p["problem_id"])
    if info is None:
        return (0, 0.0)                          # nie geuebt -> zuerst
    best = info.get("best_score")
    if best is not None and best >= 75:
        return (3, info["last_attempted_at"] or 0.0)  # sitzt
    _rank = {0: 1, 1: 2, 2: 3}.get(info["last_rating"], 1)
    return (_rank, info["last_attempted_at"] or 0.0)


_problems = sorted(_problems, key=_practice_priority)


def _practice_badge(p: dict) -> str:
    info = _attempt_summary.get(p["problem_id"])
    if info is None:
        return "🔴 "
    best = info.get("best_score")
    if best is not None and best >= 75:
        return "✅ "
    return {0: "🔴 ", 1: "🟡 "}.get(info["last_rating"], "")

if "_practice_pending_choice" in st.session_state:
    st.session_state["practice_choice"] = st.session_state.pop("_practice_pending_choice")
# KEIN Reset, wenn die aktive Aufgabe nur aus der GEFILTERTEN Liste faellt (z. B.
# Fach-Filter umgestellt) - derselbe Grund wie bei den Notizen: ein reiner
# Anzeigefilter soll nicht die gerade geuebte Aufgabe wegreissen.

col_list, col_practice = st.columns([1, 2])

with col_list:
    with card("liste"):
        if _problems:
            st.caption("🔴 empfohlen (nie/schlecht geübt) · 🟡 teilweise · "
                      "✅ sitzt (Bestwert ≥ 75 %).")
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
                    _snip = (student_flow.plain_study_snippet(p.get("topic"))
                             or student_flow.plain_study_snippet(p.get("problem_text")))
                    _kind = _KIND_LABEL.get(p["kind"], p["kind"])
                    _label = _kind + (f" · {_snip}" if _snip else "")
                    _meta = _fach(p["subject"])
                    _active = st.session_state.get("practice_choice") == p["problem_id"]
                    _prefix = "▶️ " if _active else _practice_badge(p)
                    if st.button(f"{_prefix}{_label}",
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
            _answer_key = f"practice_typed_{pid}"
            _grade_key = f"practice_grade_{pid}"
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

            _typed_answer = st.text_area(
                "Dein Rechenweg / deine Antwort",
                key=_answer_key, height=150,
                placeholder="Rechenschritte, Begründung und Ergebnis …",
            )
            if st.button(
                    "Antwort mit Teilpunkten prüfen", type="primary",
                    key=f"practice_grade_btn_{pid}",
                    disabled=(
                        not (_typed_answer or "").strip()
                        or bool(st.session_state.get(_grade_key)))):
                from ragapp import grading
                _reference = "\n".join(
                    [s.get("step_text", "") for s in _active.get("steps", [])]
                    + [_active.get("final_answer") or ""]
                ).strip()
                with st.spinner("Prüfe Rechenweg und Ergebnis …"):
                    _graded = grading.grade_typed_answer(
                        _active.get("problem_text") or "",
                        _reference, _typed_answer)
                _score = _graded.get("score")
                if _score is None:
                    st.warning(
                        _graded.get("feedback")
                        or "Die Antwort konnte gerade nicht bewertet werden.")
                else:
                    _score = int(_score)
                    _rating = 2 if _score >= 75 else (1 if _score >= 40 else 0)
                    _fehlt = _graded.get("fehlt")
                    if isinstance(_fehlt, (list, tuple)):
                        _fehlt_txt = " · ".join(
                            str(x).strip() for x in _fehlt if str(x).strip())
                    else:
                        _fehlt_txt = str(_fehlt or "").strip()
                    manifest.log_practice_attempt(
                        pid, self_rating=_rating, typed_answer=_typed_answer,
                        score=_score, feedback=_graded.get("feedback"),
                        fehlt=_fehlt_txt or None)
                    st.session_state[_grade_key] = {
                        **_graded, "score": _score,
                    }
                    st.session_state["_practice_session_done"] = True
                    if _score < 75:
                        from ragapp.student_flow import record_error, card_from_text
                        _cid = card_from_text(
                            (_active.get("problem_text") or "")[:200],
                            (_reference or "Siehe Lösungsweg.")[:800],
                            source="practice", subject=_active.get("subject"),
                            topic=_active.get("topic"))
                        record_error(
                            source="practice", source_id=pid, card_id=_cid,
                            subject=_active.get("subject"),
                            front=(_active.get("problem_text") or "")[:200],
                            detail=(
                                f"Übung { _score } %"
                                + (f" · {_fehlt_txt}" if _fehlt_txt else "")
                            ))

            _grade = st.session_state.get(_grade_key)
            if _grade:
                st.metric("Teilpunkte", f"{_grade['score']} %")
                if _grade.get("feedback"):
                    st.info(_grade["feedback"])
                if _grade.get("fehlt"):
                    _fehlt_show = _grade["fehlt"]
                    if isinstance(_fehlt_show, (list, tuple)):
                        _fehlt_show = " · ".join(str(x) for x in _fehlt_show if str(x).strip())
                    st.warning(f"Fehlt noch: {_fehlt_show}")

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
                manifest.log_practice_attempt(
                    pid, self_rating=rating,
                    typed_answer=st.session_state.get(_answer_key) or None)
                if rating <= 1:
                    from ragapp.student_flow import record_error, card_from_text
                    cid = card_from_text(
                        (_active.get("problem_text") or "")[:200],
                        (_active.get("final_answer") or "Siehe Lösungsweg.")[:800],
                        source="practice", subject=_active.get("subject"),
                        topic=_active.get("topic"))
                    record_error(
                        source="practice", source_id=pid, card_id=cid,
                        subject=_active.get("subject"),
                        front=(_active.get("problem_text") or "")[:200],
                        detail="Übung nicht vollständig gelöst")
                else:
                    from ragapp.student_flow import card_from_text
                    card_from_text(
                        (_active.get("problem_text") or "")[:200],
                        (_active.get("final_answer") or "Siehe Lösungsweg.")[:800],
                        source="practice", subject=_active.get("subject"),
                        topic=_active.get("topic"))
                for k in (_hint_key, _step_key):
                    st.session_state[k] = 0
                st.session_state.pop(_answer_key, None)
                st.session_state.pop(_grade_key, None)
                st.session_state[_resolved_key] = False
                st.session_state["_practice_session_done"] = True
                st.rerun()

            if r1.button(
                    "❌ Nicht gewusst", key=f"practice_rate0_{pid}",
                    use_container_width=True, disabled=bool(_grade)):
                _bewerten(0)
            if r2.button(
                    "🟡 Teilweise", key=f"practice_rate1_{pid}",
                    use_container_width=True, disabled=bool(_grade)):
                _bewerten(1)
            if r3.button(
                    "✅ Gewusst", key=f"practice_rate2_{pid}",
                    use_container_width=True, disabled=bool(_grade)):
                _bewerten(2)

            _attempts = manifest.list_practice_attempts(pid, limit=5)
            if _attempts:
                _hist = " · ".join(
                    (f"{a['score']} %" if a.get("score") is not None
                     else _RATING_LABEL.get(a["self_rating"], "?"))
                    for a in _attempts)
                st.caption(f"Bisher {len(_attempts)}x geübt (neueste zuerst): {_hist}")

            if delete_button("🗑️ Aufgabe löschen", token=f"practice:{pid}",
                             body="Diese Übungsaufgabe wirklich löschen?",
                             key=f"practice_delete_{pid}"):
                manifest.delete_practice_problem(pid)
                st.session_state["_practice_pending_choice"] = None
                st.success("Aufgabe gelöscht.")
                st.rerun()

# --------------------------------------------------------------------------- #
# Formelsammlung: fasst alle bisherigen Übungsaufgaben EINES Fachs zu einer
# wachsenden Formel-/Methodensammlung zusammen - ein Nebenprodukt der
# normalen Nutzung (keine zusätzliche Erstellungsarbeit), das mit jeder neuen
# Aufgabe reichhaltiger wird. Nur sinnvoll bei einem konkret gewählten Fach
# (nicht "Alle Fächer" - eine fachübergreifende Formelsammlung wäre beliebig).
# --------------------------------------------------------------------------- #
if _subj_arg:
    with card("formelsammlung"):
        st.subheader("📎 Formel- und Methodensammlung")
        st.caption(f"Fasst alle bisherigen Übungsaufgaben aus {_fach(_subj_arg)} zusammen – "
                  "Formeln, Methoden oder Merksätze, je nach Fach. Ohne die konkreten "
                  "Zahlenwerte einzelner Aufgaben.")
        if st.button("📎 Sammlung erstellen/aktualisieren", key="formelsammlung_gen"):
            with st.spinner("KI fasst die bisherigen Aufgaben zusammen …"):
                try:
                    _fs_text = practice_gen.generate_formelsammlung(_subj_arg)
                except practice_gen.PracticeGenError as exc:
                    st.error(str(exc))
                else:
                    from ragapp.student_flow import upsert_formelsammlung
                    upsert_formelsammlung(_subj_arg, _fs_text)
                    st.session_state[f"_formelsammlung_{_subj_arg}"] = _fs_text
        from ragapp.student_flow import formelsammlung_text as _fs_load
        _fs_cached = (
            st.session_state.get(f"_formelsammlung_{_subj_arg}")
            or _fs_load(_subj_arg)
        )
        if _fs_cached:
            st.markdown(_fs_cached)
            st.download_button(
                "⬇️ Als Markdown herunterladen", _fs_cached,
                file_name=f"formelsammlung_{_subj_arg}.md", mime="text/markdown",
                key="formelsammlung_download")
