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

from ragapp.ui._loading import page_boot
page_boot("📝 Probeklausur", page_title="Probeklausur", icon="📝", layout="wide")

st.markdown("<style>.block-container{padding-top:2rem;max-width:900px;}"
            "h1{font-weight:750;letter-spacing:-.5px;}</style>", unsafe_allow_html=True)

with st.spinner("Probeklausur wird geladen ..."):
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
