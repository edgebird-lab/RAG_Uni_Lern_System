"""
RAG-Lernsystem: Seite „Lernen" (Karteikarten + Spaced Repetition)
=================================================================
Aktives Ueben statt nur Nachschlagen: Die App erntet aus dem schon indexierten
Fragenmaterial (Klausur-Katalog + generierte Fragen) Karteikarten und plant sie
mit SM-2 (verteiltes Wiederholen). Alles offline, ohne LLM zur Laufzeit.
"""
from __future__ import annotations

import sys
import pathlib

# Projektwurzel auffindbar machen (damit 'ragapp' importierbar ist)
_p = pathlib.Path(__file__).resolve()
for _anc in _p.parents:
    if (_anc / "ragapp").is_dir():
        sys.path.insert(0, str(_anc))
        break

import streamlit as st

from ragapp import manifest, study
from ragapp.config import SUBJECT_LABELS

st.set_page_config(page_title="Lernen", page_icon="🎓", layout="wide")

from ragapp.ui._auth import require_pin
require_pin()

st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 900px;}
.karte {border:1px solid #e2e8f4; border-radius:16px; padding:26px 30px;
    background:linear-gradient(135deg,#f8fafc 0%,#eef2fb 100%); font-size:1.15rem;
    line-height:1.55; min-height:120px;}
.karte-frage {font-weight:650; color:#1f3a63;}
@media (prefers-color-scheme: dark){
  .karte{background:linear-gradient(135deg,#1e293b 0%,#0f172a 100%);border-color:#334155;}
  .karte-frage{color:#cbd5e1;}
}
h1 {font-weight:750; letter-spacing:-0.5px;}
</style>
""", unsafe_allow_html=True)


def _fach_label(code: str) -> str:
    return SUBJECT_LABELS.get(code, code)


st.title("🎓 Lernen")
st.caption("Karteikarten aus deinen eigenen Unterlagen – aktives Abfragen mit "
           "automatischer Wiederholungs-Planung (Spaced Repetition). Das ist der "
           "wirksamste Klausur-Hebel.")

# --------------------------------------------------------------------------- #
# Karten-Bestand
# --------------------------------------------------------------------------- #
_counts = manifest.review_counts()

if _counts["total"] == 0:
    st.info("📇 Noch keine Karteikarten vorhanden. Sie entstehen aus deinen "
            "**generierten Fragen** und dem **Klausur-Lernkatalog**.")
    with st.spinner("Suche vorhandenes Fragenmaterial …"):
        pass
    if st.button("📇 Karten aus meinen Unterlagen erstellen", type="primary"):
        with st.status("Erstelle Karteikarten …", expanded=True) as s:
            res = study.harvest_cards(progress=lambda m: s.update(label=m))
            s.update(label=f"Fertig: {res['neu']} Karten erstellt", state="complete")
        if res["gefunden"] == 0:
            st.warning("Es wurde **kein** Fragenmaterial gefunden. Erzeuge zuerst Fragen: "
                       "Seite **📥 Import** → Fragen generieren bzw. Klausur-Lernkatalog "
                       "erstellen. Danach hier erneut Karten erstellen.")
        else:
            st.rerun()
    st.stop()

# Kopfzeile mit Zahlen
c1, c2, c3, c4 = st.columns(4)
c1.metric("Karten gesamt", _counts["total"])
c2.metric("Jetzt fällig", _counts["due"])
c3.metric("Neu", _counts["neu"])
c4.metric("Schon geübt", _counts["gelernt"])

with st.expander("⚙️ Karten verwalten"):
    cc1, cc2 = st.columns(2)
    with cc1:
        if st.button("🔄 Karten aktualisieren (neue Fragen aufnehmen)"):
            with st.status("Aktualisiere …", expanded=True) as s:
                res = study.harvest_cards(progress=lambda m: s.update(label=m))
                s.update(label=f"{res['neu']} neue Karten hinzugefügt", state="complete")
            st.rerun()
    with cc2:
        st.caption("Karten kommen aus dem generierten Fragenmaterial – neue Fragen/"
                   "Katalog-Einträge werden per Aktualisieren übernommen.")

st.divider()

# --------------------------------------------------------------------------- #
# Lernrunde
# --------------------------------------------------------------------------- #
Q = "_study_queue"
ACTIVE = "_study_active"
REVEAL = "_study_reveal"
TALLY = "_study_tally"
ROUND = "_study_round"

if not st.session_state.get(ACTIVE):
    _faecher = manifest.study_subjects()
    fopts = ["Alle Fächer"] + _faecher
    fchoice = st.selectbox("Fach", fopts, format_func=lambda c: c if c == "Alle Fächer"
                           else _fach_label(c))
    subj = None if fchoice == "Alle Fächer" else fchoice

    _fc = manifest.review_counts(subj)
    faellig = _fc["due"]
    if faellig == 0:
        st.success("✅ Für diese Auswahl ist gerade **nichts fällig** – gut gemacht! "
                   "Komm später wieder oder wähle ein anderes Fach.")
    else:
        maxr = min(faellig, 50)
        anzahl = st.slider("Karten in dieser Runde", min_value=1,
                           max_value=int(max(1, maxr)),
                           value=int(min(20, maxr)))
        if st.button(f"▶️ Lernrunde starten ({anzahl} von {faellig} fällig)",
                     type="primary", use_container_width=True):
            karten = manifest.get_due_cards(subj, limit=int(anzahl))
            st.session_state[Q] = karten
            st.session_state[ACTIVE] = True
            st.session_state[REVEAL] = False
            st.session_state[TALLY] = {"gewusst": 0, "halb": 0, "nicht": 0}
            st.session_state[ROUND] = len(karten)
            st.rerun()

else:
    queue = st.session_state.get(Q) or []
    tally = st.session_state.get(TALLY, {"gewusst": 0, "halb": 0, "nicht": 0})

    if not queue:
        # Runde fertig
        beantwortet = sum(tally.values())
        st.success(f"🎉 Runde geschafft! **{beantwortet}** Karten geübt.")
        m1, m2, m3 = st.columns(3)
        m1.metric("✅ Gewusst", tally["gewusst"])
        m2.metric("🟡 Halb", tally["halb"])
        m3.metric("❌ Nicht", tally["nicht"])
        b1, b2 = st.columns(2)
        if b1.button("🔁 Neue Runde", use_container_width=True):
            for k in (Q, ACTIVE, REVEAL, TALLY, ROUND):
                st.session_state.pop(k, None)
            st.rerun()
        if b2.button("Beenden", use_container_width=True):
            for k in (Q, ACTIVE, REVEAL, TALLY, ROUND):
                st.session_state.pop(k, None)
            st.rerun()
        st.stop()

    karte = queue[0]
    gesamt = st.session_state.get(ROUND, len(queue))
    erledigt = sum(tally.values())
    st.progress(min(1.0, erledigt / max(1, gesamt)),
                text=f"Karte {erledigt + 1} · noch {len(queue)} in der Runde")
    _tt = _fach_label(karte.get("subject") or "")
    _topic = karte.get("topic")
    st.caption(f"📚 {_tt}" + (f" · {_topic}" if _topic else ""))

    # Vorderseite
    st.markdown(f"<div class='karte karte-frage'>{karte['front']}</div>",
                unsafe_allow_html=True)
    st.write("")

    if not st.session_state.get(REVEAL):
        st.caption("Überlege (oder tippe für dich) die Antwort – dann aufdecken.")
        if st.button("👁️ Antwort zeigen", type="primary", use_container_width=True):
            st.session_state[REVEAL] = True
            st.rerun()
    else:
        # Rueckseite (LaTeX-faehig via Markdown)
        st.markdown(karte["back"])
        st.write("")
        st.caption("Wie gut wusstest du es?")
        r1, r2, r3 = st.columns(3)

        def _bewerten(rating: int) -> None:
            nxt = study.rate_card(karte, rating)
            t = st.session_state[TALLY]
            t["gewusst" if rating == study.GEWUSST else
              "halb" if rating == study.HALB else "nicht"] += 1
            q = st.session_state[Q]
            q.pop(0)
            if rating == study.NICHT:
                # In derselben Runde erneut ueben (mit zurueckgesetztem Zustand).
                q.append({**karte, **nxt})
            st.session_state[REVEAL] = False
            st.rerun()

        if r1.button("❌ Nicht gewusst", use_container_width=True):
            _bewerten(study.NICHT)
        if r2.button("🟡 Halb", use_container_width=True):
            _bewerten(study.HALB)
        if r3.button("✅ Gewusst", use_container_width=True):
            _bewerten(study.GEWUSST)
