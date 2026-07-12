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
import pathlib

_p = pathlib.Path(__file__).resolve()
for _anc in _p.parents:
    if (_anc / "ragapp").is_dir():
        sys.path.insert(0, str(_anc))
        break

import streamlit as st

from ragapp import manifest, study, planner
from ragapp.config import settings, SUBJECT_LABELS

st.set_page_config(page_title="Probeklausur", page_icon="📝", layout="wide")

from ragapp.ui._auth import require_pin
require_pin()

st.markdown("<style>.block-container{padding-top:2rem;max-width:900px;}"
            "h1{font-weight:750;letter-spacing:-.5px;}</style>", unsafe_allow_html=True)


def _fach(code: str) -> str:
    return SUBJECT_LABELS.get(code, code)


st.title("📝 Probeklausur")
st.caption("Getimte Simulation unter echten Bedingungen – ohne Zwischenfeedback. Am Ende "
           "benotet die KI alle Antworten und plant schwache Themen sofort neu ein.")

EXAM = "_exam"        # aktive Probeklausur (dict: cards, answers, start, limit)

subjects = manifest.study_subjects()
if not subjects:
    st.info("Noch keine Karteikarten vorhanden – erstelle sie zuerst auf **🎓 Lernen**.")
    st.stop()

# --------------------------------------------------------------------------- #
# Aufbau
# --------------------------------------------------------------------------- #
if EXAM not in st.session_state:
    st.subheader("Probeklausur zusammenstellen")
    c1, c2, c3 = st.columns(3)
    _fs = c1.multiselect("Fächer (leer = alle)", subjects, format_func=_fach)
    n = c2.number_input("Aufgaben", min_value=3, max_value=40, value=10, step=1)
    minutes = c3.number_input("Zeitlimit (Min.)", min_value=5, max_value=240, value=30, step=5)
    st.caption("Die Aufgaben werden aus deinen fälligen und – falls nötig – den schwächsten "
               "Karten gemischt (fächerübergreifend, wenn kein Fach gewählt ist).")

    if st.button("▶️ Probeklausur starten", type="primary", use_container_width=True):
        if _fs:
            cards = []
            for s in _fs:
                cards += manifest.get_due_cards(s, limit=int(n), cram=True)
            # gleichmäßig kürzen + mischen
            cards = cards[:int(n)]
        else:
            cards = planner.phase_round(limit=int(n), cram=True)
        if not cards:
            st.warning("Keine Karten für diese Auswahl gefunden.")
        else:
            st.session_state[EXAM] = {
                "cards": cards, "answers": {}, "start": time.time(),
                "limit": int(minutes) * 60, "done": False,
            }
            st.rerun()
    st.stop()

exam = st.session_state[EXAM]

# --------------------------------------------------------------------------- #
# Auswertung (nach Abgabe / Zeitablauf)
# --------------------------------------------------------------------------- #
if exam.get("done"):
    res = exam["result"]
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
                         f"{_fach(it.get('subject') or '')}"):
            st.markdown(f"**Frage:** {it['front']}")
            st.markdown(f"**Deine Antwort:** {it.get('typed') or '_(leer)_'}")
            if it.get("feedback"):
                st.info(it["feedback"])
            if it.get("fehlt"):
                st.caption("Fehlt: " + " · ".join(it["fehlt"]))
            with st.popover("Musterlösung"):
                st.markdown(it.get("reference") or "—")
    if st.button("🔁 Neue Probeklausur", use_container_width=True):
        del st.session_state[EXAM]
        st.rerun()
    st.stop()

# --------------------------------------------------------------------------- #
# Laufende Klausur
# --------------------------------------------------------------------------- #
elapsed = time.time() - exam["start"]
remaining = max(0, exam["limit"] - elapsed)
time_up = remaining <= 0

hc1, hc2 = st.columns([3, 1])
mm, ss = divmod(int(remaining), 60)
hc1.subheader(f"⏱️ {mm:02d}:{ss:02d} verbleibend" if not time_up else "⏱️ Zeit abgelaufen")
hc1.caption(f"{len(exam['cards'])} Aufgaben · schreibe deine Antworten, dann unten abgeben. "
            "Die Zeit aktualisiert sich bei jeder Eingabe.")
if hc2.button("🔄 Zeit aktualisieren", use_container_width=True):
    st.rerun()

for i, card in enumerate(exam["cards"]):
    st.markdown(f"**Aufgabe {i + 1}** · _{_fach(card.get('subject') or '')}_")
    st.markdown(card.get("front") or "")
    exam["answers"][card["card_id"]] = st.text_area(
        f"Antwort {i + 1}", value=exam["answers"].get(card["card_id"], ""),
        key=f"exam_ans_{i}", label_visibility="collapsed", height=110,
        disabled=time_up)
    st.divider()


def _rating_from_score(score):
    if score is None:
        return study.HALB
    return study.GEWUSST if score >= 75 else (study.HALB if score >= 40 else study.NICHT)


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
        items.append({"front": card.get("front"), "subject": card.get("subject"),
                      "typed": typed, "reference": ref, "score": g.get("score"),
                      "feedback": g.get("feedback"), "fehlt": g.get("fehlt")})
        if g.get("score") is not None:
            scored.append(g["score"])
        prog.progress(j / len(exam["cards"]), text=f"Benotet {j}/{len(exam['cards'])} …")
    total = round(sum(scored) / len(scored)) if scored else 0
    exam["result"] = {"items": items, "total_pct": total,
                      "used_min": round((time.time() - exam["start"]) / 60)}
    exam["done"] = True


if time_up:
    st.warning("Die Zeit ist abgelaufen. Gib die Klausur zur Auswertung ab.")
if st.button("✅ Abgeben & auswerten", type="primary", use_container_width=True):
    with st.spinner("Werte aus …"):
        _auswerten()
    st.rerun()
