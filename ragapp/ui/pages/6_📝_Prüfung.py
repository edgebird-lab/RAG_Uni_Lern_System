"""
RAG-Lernsystem: Seite „Probeklausur" (getimte Simulation + Batch-Benotung)
=========================================================================
Reproduziert echte Klausurbedingungen: ein gemischtes Set aus deinen Karten,
ein Zeitlimit, KEIN Zwischenfeedback – am Ende benotet die KI alle Antworten auf
einmal (Teilpunkte + was fehlt) und schreibt das Ergebnis in die
Wiederholungs-Planung zurück (schwache Karten kommen sofort wieder dran).
Getimtes Üben unter Prüfungsbedingungen ist einer der stärksten Leistungsprädiktoren.
"""
from __future__ import annotations

import sys
import time
import random
import pathlib

_p = pathlib.Path(__file__).resolve()
for _anc in _p.parents:
    if (_anc / "ragapp").is_dir():
        sys.path.insert(0, str(_anc))
        break

import streamlit as st

from ragapp.ui._loading import page_boot, skeleton
page_boot("📝 Probeklausur", page_title="Probeklausur", icon="📝", layout="wide",
         accent="pruefung")

from ragapp.ui._style import card

st.markdown("<style>.block-container{max-width:900px;}</style>",
            unsafe_allow_html=True)

with skeleton("Probeklausur wird geladen …"):
    from ragapp import manifest, study, planner
    from ragapp.config import settings, SUBJECT_LABELS


def _fach(code: str) -> str:
    return SUBJECT_LABELS.get(code, code)


def _fair_exam_selection(per_subject, n: int, seed: int = 0) -> list[dict]:
    """Wählt bis zu ``n`` Karten fair über die gewählten Fächer aus: Round-Robin (je
    Runde eine Karte pro Fach) bis ``n`` erreicht ist, sodass jedes Fach so gleichmäßig
    wie möglich vertreten ist – nicht nur die zuerst geladenen. Danach wird die Auswahl
    deterministisch gemischt (Klausur-Reihenfolge), ohne die faire Verteilung zu
    verändern. ``per_subject`` ist eine geordnete Liste ``[(fach, [karten]), …]``.
    Reine, testbare Hilfsfunktion."""
    from collections import deque
    n = max(0, int(n))
    queues = [deque(cards) for _, cards in per_subject if cards]
    picked: list[dict] = []
    while len(picked) < n and any(queues):
        for q in queues:
            if len(picked) >= n:
                break
            if q:
                picked.append(q.popleft())
    random.Random(seed).shuffle(picked)
    return picked


st.caption("Wie in der Klausur: Zeitlimit, keine Zwischentipps, Bewertung erst am Ende.")

EXAM = "_exam"        # aktive Probeklausur (dict: cards, answers, start, limit)


def _clear_exam_answer_widgets() -> None:
    """Alte Streamlit-Textfelder dürfen nicht in die nächste Klausur lecken."""
    for _key in list(st.session_state):
        if str(_key).startswith("exam_ans_"):
            st.session_state.pop(_key, None)


subjects = manifest.study_subjects()

# F2: schlanke Sprechschleife, noch ohne das spätere Prüfungszentrum (F4).
with st.expander("🎙️ Mündliche Prüfung", expanded=False):
    from ragapp import oral_exam
    if not subjects:
        st.caption("Für mündliche Fragen zuerst Karteikarten anlegen.")
    elif not st.session_state.get("_oral_session_id"):
        _oral_subject = st.selectbox(
            "Fach", subjects, format_func=_fach, key="oral_subject")
        _oral_n = st.number_input(
            "Fragen", 1, 10, 5, key="oral_count")
        if st.button("Mündliche Prüfung starten", type="primary", key="oral_start"):
            _started = oral_exam.session_from_cards(
                _oral_subject, limit=int(_oral_n))
            if _started.get("session_id"):
                st.session_state["_oral_session_id"] = _started["session_id"]
                st.rerun()
            else:
                st.warning("Keine geeigneten Fragen in diesem Fach.")
    else:
        _oral_sid = st.session_state["_oral_session_id"]
        _oral = oral_exam.get_session(_oral_sid)
        if not _oral or _oral.get("status") != "active":
            st.session_state.pop("_oral_session_id", None)
            st.rerun()
        _idx = int(_oral.get("current_index") or 0)
        _questions = _oral.get("questions") or []
        _last_idx = st.session_state.get("_oral_last_index")
        if (_last_idx is None and _idx < len(_questions)
                and _questions[_idx].get("transcript")):
            # Nach Reload kommt der offene Rückfrage-Schritt aus SQLite zurück.
            _last_idx = _idx
        # Solange Transkript/Rückfrage offen ist, wird noch NICHT die nächste
        # Hauptfrage gezeigt. So bleibt die Schleife wirklich bei einer Frage.
        if _last_idx is None and _idx >= len(_questions):
            st.success("Alle mündlichen Fragen beantwortet.")
            if st.button("Sitzung abschließen", key="oral_finish"):
                oral_exam.finish_session(_oral_sid)
                st.session_state.pop("_oral_session_id", None)
                st.session_state.pop("_oral_last_index", None)
                st.rerun()
        elif _last_idx is None:
            _item = _questions[_idx]
            st.caption(f"Frage {_idx + 1} von {len(_questions)}")
            st.markdown(f"### {_item['question']}")
            _audio = st.audio_input(
                "Antwort aufnehmen", key=f"oral_audio_{_oral_sid}_{_idx}")
            if st.button(
                    "Aufnahme transkribieren", type="primary",
                    disabled=_audio is None,
                    key=f"oral_transcribe_{_oral_sid}_{_idx}"):
                _tr = oral_exam.transcribe_answer(
                    _audio.getvalue() if _audio else b"")
                if _tr["status"] != "ok":
                    st.error(_tr.get("message") or "Keine Transkription möglich.")
                else:
                    oral_exam.record_answer(
                        _oral_sid, _idx, _tr["transcript"])
                    st.session_state["_oral_last_index"] = _idx
                    st.rerun()

        if _last_idx is not None and int(_last_idx) < len(_questions):
            _last = _questions[int(_last_idx)]
            if _last.get("transcript"):
                st.markdown("**Transkript**")
                st.write(_last["transcript"])
                _oral_points = st.segmented_control(
                    "Selbsteinschätzung",
                    options=[0, 50, 100],
                    format_func=lambda p: {
                        0: "Nicht beantwortet",
                        50: "Teilweise",
                        100: "Sicher",
                    }[p],
                    default=(_last.get("partial_points")
                             if _last.get("partial_points") is not None else 50),
                    key=f"oral_points_{_oral_sid}_{_last_idx}",
                )
                if not _last.get("followups"):
                    if st.button(
                            "Optionale Rückfrage stellen",
                            key=f"oral_followup_{_oral_sid}_{_last_idx}"):
                        _fu = oral_exam.generate_followup(
                            _last["question"], _last["transcript"],
                            _last.get("reference") or "")
                        if _fu["status"] != "ok":
                            st.error(_fu.get("message") or
                                     "Rückfrage ohne Modell nicht möglich.")
                        else:
                            oral_exam.record_answer(
                                _oral_sid, int(_last_idx), _last["transcript"],
                                followup=_fu["followup"])
                            st.rerun()
                else:
                    _fu_item = _last["followups"][-1]
                    st.markdown(f"**Rückfrage:** {_fu_item['question']}")
                    _fu_audio = st.audio_input(
                        "Rückfrage beantworten",
                        key=f"oral_fu_audio_{_oral_sid}_{_last_idx}")
                    if st.button(
                            "Rückfrage transkribieren",
                            disabled=_fu_audio is None,
                            key=f"oral_fu_transcribe_{_oral_sid}_{_last_idx}"):
                        _fu_tr = oral_exam.transcribe_answer(
                            _fu_audio.getvalue() if _fu_audio else b"")
                        if _fu_tr["status"] != "ok":
                            st.error(_fu_tr.get("message") or
                                     "Keine Transkription möglich.")
                        else:
                            oral_exam.record_answer(
                                _oral_sid, int(_last_idx),
                                _last["transcript"],
                                partial_points=int(_oral_points))
                            oral_exam.record_followup_answer(
                                _oral_sid, int(_last_idx),
                                len(_last["followups"]) - 1,
                                _fu_tr["transcript"])
                            oral_exam.advance_session(
                                _oral_sid, int(_last_idx))
                            st.session_state.pop("_oral_last_index", None)
                            st.rerun()
            if st.button(
                    "Ohne Rückfrage weiter", key=f"oral_next_{_oral_sid}_{_last_idx}"):
                oral_exam.record_answer(
                    _oral_sid, int(_last_idx), _last.get("transcript") or "",
                    partial_points=int(_oral_points))
                oral_exam.advance_session(_oral_sid, int(_last_idx))
                st.session_state.pop("_oral_last_index", None)
                st.rerun()

        if st.button("Mündliche Sitzung abbrechen", key="oral_abort"):
            oral_exam.abort_session(_oral_sid)
            st.session_state.pop("_oral_session_id", None)
            st.session_state.pop("_oral_last_index", None)
            st.rerun()

if not subjects:
    from ragapp.ui._style import empty_state, page_title as _pt
    empty_state(
        "Noch keine Karteikarten – erstelle sie zuerst unter Karteikarten.",
        cta_label=f"Zu {_pt('lernen')}",
        page_key="lernen",
        icon="🎓",
        key="pruefung_empty_lernen",
    )
    st.stop()

# --------------------------------------------------------------------------- #
# Aufbau
# --------------------------------------------------------------------------- #
if EXAM not in st.session_state:
    with card("aufbau"):
        st.subheader("Probeklausur zusammenstellen")
        c1, c2, c3 = st.columns(3)
        _fs = c1.multiselect("Fächer (leer = alle)", subjects, format_func=_fach,
                            placeholder="Alle")
        n = c2.number_input("Aufgaben", min_value=3, max_value=40, value=10, step=1)
        minutes = c3.number_input("Zeitlimit (Min.)", min_value=5, max_value=240, value=30, step=5)
        st.caption("Die Aufgaben werden aus deinen fälligen und – falls nötig – den schwächsten "
                   "Karten gemischt (fächerübergreifend, wenn kein Fach gewählt ist).")

        if st.button("▶️ Probeklausur starten", type="primary", use_container_width=True):
            if _fs:
                # Pro Fach die (fälligen/schwächsten) Karten holen und daraus gleichmäßig
                # per Round-Robin bis n auswählen, dann deterministisch mischen – so ist
                # jedes gewählte Fach fair vertreten (nicht nur die zuerst geladenen).
                per_subject = [(s, manifest.get_due_cards(s, limit=int(n), cram=True))
                               for s in _fs]
                cards = _fair_exam_selection(per_subject, int(n))
            else:
                cards = planner.phase_round(limit=int(n), cram=True)
            if not cards:
                st.warning("Keine Karten für diese Auswahl gefunden.")
            else:
                _clear_exam_answer_widgets()
                st.session_state[EXAM] = {
                    "cards": cards, "answers": {}, "start": time.time(),
                    "limit": int(minutes) * 60, "done": False,
                }
                st.rerun()

        _hist = manifest.list_exam_attempts(limit=5)
        if _hist:
            with st.expander("Letzte Probeklausuren", expanded=False):
                for _a in _hist:
                    _when = time.strftime("%d.%m. %H:%M", time.localtime(_a["taken_at"]))
                    st.markdown(f"**{_a['total_pct']} %** · {_a['num_items']} Aufgaben · {_when}")
                    _aits = manifest.list_exam_attempt_items(_a["attempt_id"])
                    if _aits:
                        for _j, _it in enumerate(_aits, 1):
                            st.caption(f"{_j}. {(_it.get('front') or '')[:80]} · "
                                       f"{_it.get('score') if _it.get('score') is not None else '—'} %")
    st.stop()

exam = st.session_state[EXAM]

# --------------------------------------------------------------------------- #
# Auswertung (nach Abgabe / Zeitablauf)
# --------------------------------------------------------------------------- #
if exam.get("done"):
    res = exam["result"]
    with card("ergebnis"):
        st.subheader("📊 Ergebnis")
        m1, m2, m3 = st.columns(3)
        m1.metric("Gesamt", f'{res["total_pct"]} %')
        m2.metric("Aufgaben", len(res["items"]))
        m3.metric("Zeit", f'{res["used_min"]} Min.')
        st.progress(min(1.0, res["total_pct"] / 100))
    st.divider()
    for i, it in enumerate(res["items"], 1):
        _sc = it.get("score")
        _icon = "✅" if (_sc or 0) >= 75 else ("🟡" if (_sc or 0) >= 40 else "❌")
        with st.expander(f"{_icon} Aufgabe {i} · {_sc if _sc is not None else '—'} % · "
                         f"{_fach(it.get('subject') or '')}", key=f"pruefung_item_{i}"):
            st.markdown(f"**Frage:** {it['front']}")
            st.markdown(f"**Deine Antwort:** {it.get('typed') or '_(leer)_'}")
            if it.get("feedback"):
                st.info(it["feedback"])
            if it.get("fehlt"):
                st.caption("Fehlt: " + " · ".join(it["fehlt"]))
            with st.popover("Musterlösung"):
                st.markdown(it.get("reference") or "—")
            # Bei einer schwachen Antwort direkt eine klaerende Notiz anlegen
            # koennen - gleiches Prefill-Muster wie beim Chat ("Als Notiz
            # speichern") - hier zusaetzlich mit Fach/Dokument/Thema vorbelegt,
            # weil eine Klausur-Karte diese Zuordnung (anders als eine freie
            # Chat-Antwort) bereits kennt.
            if (_sc or 0) < 75 and st.button("📝 Notiz schreiben", key=f"pruefung_note_{i}",
                                             help="Öffnet die Notizen-Seite mit dieser "
                                                  "Aufgabe als Ausgangstext."):
                _note_body = (
                    f"**Frage:** {it['front']}\n\n"
                    f"**Meine Antwort:** {it.get('typed') or '(leer)'}\n\n"
                    + (f"**Feedback:** {it['feedback']}\n\n" if it.get("feedback") else "")
                    + f"**Musterlösung:** {it.get('reference') or '—'}"
                )
                st.session_state["note_prefill"] = {
                    "subject": it.get("subject"), "doc_id": it.get("doc_id"),
                    "topic": it.get("topic"), "title": it["front"][:80],
                    "body": _note_body,
                }
                st.switch_page("pages/12_🗒️_Notizen.py")
    _w1, _w2 = st.columns(2)
    if _w1.button("🔁 Neue Probeklausur", use_container_width=True):
        _clear_exam_answer_widgets()
        del st.session_state[EXAM]
        st.rerun()
    _wrong_ids = [it.get("card_id") for it in res["items"]
                  if it.get("card_id") and (it.get("score") or 0) < 75]
    if _w2.button("🎯 Nur Fehler wiederholen", use_container_width=True,
                  disabled=not _wrong_ids):
        _wrong_cards = [c for c in exam["cards"] if c.get("card_id") in set(_wrong_ids)]
        _clear_exam_answer_widgets()
        del st.session_state[EXAM]
        if _wrong_cards:
            st.session_state[EXAM] = {
                "cards": _wrong_cards, "answers": {}, "start": time.time(),
                "limit": max(5, len(_wrong_cards) * 2) * 60, "done": False,
            }
        st.rerun()
    st.stop()

# --------------------------------------------------------------------------- #
# Benotung (auch für die automatische Abgabe bei Zeitablauf)
# --------------------------------------------------------------------------- #
def _rating_from_score(score):
    if score is None:
        return study.HALB
    return study.GEWUSST if score >= 75 else (study.HALB if score >= 40 else study.NICHT)


def _sync_answers() -> None:
    """Übernimmt die aktuell im Browser getippten Antworten aus dem Widget-Zustand in
    ``exam['answers']``. Nötig für die Auto-Abgabe bei Zeitablauf, weil der Countdown
    die Seite neu lädt, bevor die Textfelder in diesem Lauf gerendert wurden."""
    for i, card in enumerate(exam["cards"]):
        val = st.session_state.get(f"exam_ans_{i}")
        if val is not None:
            exam["answers"][card["card_id"]] = val


def _auswerten():
    items = []
    scored = []
    prog = st.progress(0.0, text="Die KI benotet deine Antworten …")
    from ragapp import grading
    for j, card in enumerate(exam["cards"], 1):
        typed = exam["answers"].get(card["card_id"], "")
        ref = (card.get("answer") or card.get("back") or "")
        g = grading.grade_typed_answer(card.get("front", ""), ref, typed)
        rating = _rating_from_score(g.get("score"))
        study.rate_card(card, rating)   # Ergebnis fließt in die Wiederholungs-Planung
        items.append({"card_id": card.get("card_id"),
                      "front": card.get("front"), "subject": card.get("subject"),
                      "typed": typed, "reference": ref, "score": g.get("score"),
                      "feedback": g.get("feedback"), "fehlt": g.get("fehlt"),
                      "doc_id": card.get("doc_id"), "topic": card.get("topic")})
        if (g.get("score") or 0) < 40:
            from ragapp.student_flow import record_error
            record_error(source="exam", source_id=card.get("card_id"),
                         card=card, front=card.get("front"),
                         detail=f"Probeklausur {g.get('score')} %")
        if g.get("score") is not None:
            scored.append(g["score"])
        prog.progress(j / len(exam["cards"]), text=f"Benotet {j}/{len(exam['cards'])} …")
    total = round(sum(scored) / len(scored)) if scored else 0
    exam["result"] = {"items": items, "total_pct": total,
                      "used_min": round((time.time() - exam["start"]) / 60)}
    exam["done"] = True
    # Ergebnis dauerhaft festhalten (vorher nur in st.session_state, nach
    # Verlassen der Seite komplett weg) - Grundlage der Errungenschaft
    # "erste bestandene Probeklausur" (siehe ragapp/achievements.py).
    manifest.log_exam_attempt(total, len(exam["cards"]), items=items)


# --------------------------------------------------------------------------- #
# Laufende Klausur
# --------------------------------------------------------------------------- #
def _remaining() -> float:
    """Serverseitig gemessene Restzeit in Sekunden. Weil die Startzeit in
    st.session_state liegt und die Zeit hier – nicht im Browser – gemessen wird, umgeht
    ein simpler Reload das Zeitlimit nicht."""
    return max(0.0, float(exam["limit"]) - (time.time() - exam["start"]))


# Serverseitige Zeitkontrolle: ist die Zeit abgelaufen, wird die Klausur automatisch
# abgegeben und ausgewertet – noch bevor die Eingabefelder in diesem Lauf gerendert
# werden. Das erzwingt das Limit auch dann, wenn nur die Seite neu geladen wird.
if _remaining() <= 0 and not exam.get("done"):
    _sync_answers()
    with st.spinner("Zeit abgelaufen – die Klausur wird automatisch abgegeben und "
                    "ausgewertet …"):
        _auswerten()
    st.rerun()


@st.fragment(run_every=1)
def _countdown() -> None:
    """Sichtbarer Live-Countdown: aktualisiert sich jede Sekunde SERVERSEITIG (per
    Fragment-Polling, ohne die bereits getippten Antworten zu stören). Läuft die Zeit
    ab, wird die ganze Seite neu gerendert, sodass oben die Auto-Abgabe greift."""
    rem = _remaining()
    if rem <= 0:
        st.rerun()   # ganze Seite neu -> serverseitige Auto-Abgabe greift
        return
    knapp = rem <= 60
    farbe = "#dc2626" if knapp else "inherit"
    st.markdown(
        f"<div style='font-size:1.7rem;font-weight:750;letter-spacing:-.5px;"
        f"color:{farbe}'>⏱️ {int(rem) // 60:02d}:{int(rem) % 60:02d} verbleibend</div>",
        unsafe_allow_html=True)
    if knapp:
        st.caption("Weniger als eine Minute – bei Ablauf wird automatisch abgegeben.")


_countdown()
st.caption(f"{len(exam['cards'])} Aufgaben · schreibe deine Antworten, dann unten abgeben. "
           "Der Countdown läuft automatisch weiter; bei Ablauf wird die Klausur "
           "selbsttätig abgegeben und ausgewertet.")

for i, card in enumerate(exam["cards"]):
    st.markdown(f"**Aufgabe {i + 1}** · _{_fach(card.get('subject') or '')}_")
    st.markdown(card.get("front") or "")
    exam["answers"][card["card_id"]] = st.text_area(
        f"Antwort {i + 1}", value=exam["answers"].get(card["card_id"], ""),
        key=f"exam_ans_{i}", label_visibility="collapsed", height=110)
    st.divider()

if st.button("✅ Abgeben & auswerten", type="primary", use_container_width=True):
    with st.spinner("Werte aus …"):
        _auswerten()
    st.rerun()
