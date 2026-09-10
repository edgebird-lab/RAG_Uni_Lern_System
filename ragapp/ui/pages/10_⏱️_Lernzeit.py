"""
RAG-Lernsystem: Seite „Lernzeit" (Pomodoro + freier Timer)
=============================================================
Trackt echte investierte Lernzeit je Fach - die Grundlage für einen ehrlichen
Lernstand (siehe auch Fortschritt/Organisation) und Baustein Nr. 1 des geplanten
Lernplan-Systems. Pomodoro-Defaults (25 Min Arbeit / 5 Min Pause, lange Pause nach
4 Blöcken) sind bewusst nicht frei erfunden: Aufmerksamkeit lässt bei den meisten
Menschen nach ca. 25–30 Minuten fokussierter Arbeit spürbar nach (ultradiane
Rhythmik), und Studien zur Pomodoro-Technik zeigen positive Effekte auf Fokus und
Lernleistung bei genau diesem Rhythmus. Alles läuft serverseitig (st.fragment),
ein Reload verliert höchstens den laufenden Block, nie einen bereits fertigen.
"""
from __future__ import annotations

import sys
import time
import pathlib
from datetime import date, timedelta

_p = pathlib.Path(__file__).resolve()
for _anc in _p.parents:
    if (_anc / "ragapp").is_dir():
        sys.path.insert(0, str(_anc))
        break

import streamlit as st

from ragapp.ui._loading import page_boot
page_boot("⏱️ Lernzeit", page_title="Lernzeit", icon="⏱️", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 950px;}
h1 {font-weight: 750; letter-spacing:-0.5px;}
</style>
""", unsafe_allow_html=True)

st.caption("Pomodoro-Timer und freier Zeittracker – zeichnet echte Lernzeit je Fach auf. "
           "Komplett offline, kein Modell nötig.")

with st.spinner("Lernzeit wird geladen ..."):
    import pandas as pd
    from ragapp import manifest
    from ragapp.config import SUBJECT_LABELS


def _fach(code: "str | None") -> str:
    return SUBJECT_LABELS.get(code, code) if code else "Ohne Fach"


def _fmt_hms(sec: float) -> str:
    sec = max(0, int(sec))
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _fmt_dauer(sec: float) -> str:
    sec = max(0, int(sec))
    h, r = divmod(sec, 3600)
    m = r // 60
    if h:
        return f"{h} Std {m} Min"
    return f"{m} Min"


_known_subjects = sorted(
    set(SUBJECT_LABELS.keys())
    | {d["subject"] for d in manifest.list_documents() if d["subject"]})

# --------------------------------------------------------------------------- #
# Timer (Pomodoro oder frei) - nur EIN Timer gleichzeitig
# --------------------------------------------------------------------------- #
st.subheader("⏱️ Timer")

_running = bool(st.session_state.get("pomo_running") or st.session_state.get("free_running"))

# Vorbelegung aus dem Lernplan (Block "🍅 Pomodoro" verlinkt hierher). Fach/Modus
# sind eigene Widgets mit 'key' -> MUESSEN vor deren Instanziierung gesetzt werden
# (danach waere es eine StreamlitAPIException); daher hier, ganz am Anfang. Die
# Zuordnung zum Block muss dagegen bis zum "Starten"-Klick (ein SPAETERER Skript-
# Durchlauf) ueberleben - eine normale lokale Variable wuerde bei jedem Rerun
# verloren gehen, deshalb bleibt sie unter einem EIGENEN (nicht widget-gebundenen)
# session_state-Schluessel, bis sie tatsaechlich verbraucht wird.
_prefill = st.session_state.pop("pomo_prefill", None)
if _prefill and not _running:
    if _prefill.get("subject") in _known_subjects:
        st.session_state["timer_subject"] = _prefill["subject"]
    st.session_state["timer_mode"] = "🍅 Pomodoro"
    st.session_state["_pomo_pending_block_id"] = _prefill.get("block_id")
    st.session_state["_pomo_pending_work_min"] = int(_prefill.get("minutes") or 25)
    st.info(f"📋 Vorbelegt aus dem Lernplan: {_fach(_prefill.get('subject'))}, "
           f"{int(_prefill.get('minutes') or 25)} Min. Der Block gilt nach diesem "
           "Arbeitsblock als erledigt (echte Zeit erfasst).")
_prefill_work_min = st.session_state.get("_pomo_pending_work_min", 25)

if not _running:
    _mode = st.radio("Modus", ["🍅 Pomodoro", "⏱️ Freier Timer"], horizontal=True, key="timer_mode")
    _t_subj = st.selectbox("Fach", _known_subjects + ["(kein Fach)"], key="timer_subject")
    _t_subj = None if _t_subj == "(kein Fach)" else _t_subj

    if _mode == "🍅 Pomodoro":
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            _work_min = st.number_input("Arbeitsblock (Min)", min_value=5, max_value=90,
                                        value=_prefill_work_min, step=5)
        with c2:
            _break_min = st.number_input("Kurze Pause (Min)", min_value=1, max_value=30,
                                         value=5, step=1)
        with c3:
            _long_break_min = st.number_input("Lange Pause (Min)", min_value=5, max_value=60,
                                              value=15, step=5)
        with c4:
            _long_every = st.number_input("Lange Pause nach", min_value=2, max_value=8,
                                          value=4, step=1, help="... Arbeitsblöcken")
        st.caption("Vorbelegt nach Aufmerksamkeitsforschung: Fokus lässt nach "
                   "~25–30 Min spürbar nach – daher der Standard-Pomodoro-Rhythmus.")
        if st.button("🍅 Pomodoro starten", type="primary"):
            st.session_state.update(
                pomo_running=True, pomo_phase="work", pomo_phase_start=time.time(),
                pomo_phase_len=_work_min * 60, pomo_subject=_t_subj, pomo_cycle=0,
                pomo_logged=False, pomo_work_min=int(_work_min),
                pomo_break_min=int(_break_min), pomo_long_break_min=int(_long_break_min),
                pomo_long_every=int(_long_every),
                pomo_plan_block_id=st.session_state.pop("_pomo_pending_block_id", None))
            st.session_state.pop("_pomo_pending_work_min", None)
            st.rerun()
    else:
        if st.button("▶️ Timer starten", type="primary"):
            st.session_state.update(free_running=True, free_start=time.time(),
                                    free_subject=_t_subj)
            st.rerun()

elif st.session_state.get("pomo_running"):
    def _log_work_block(end_ts: float, completed: bool) -> None:
        """``completed=True``: die Arbeitsphase ist normal abgelaufen (voller
        Countdown) - nur DANN gilt ein verlinkter Lernplan-Block als erledigt.
        Ein Abbruch (``completed=False``) protokolliert die echte investierte
        Zeit trotzdem (sie zaehlt fuer Lernzeit-Statistik + Kalibrierung), markiert
        den Block aber NICHT als fertig - sonst wuerde schon eine 2-Minuten-
        Anlern-Sitzung einen 25-Minuten-Block als erledigt zeigen (Logik-Luecke:
        vor dieser Korrektur wurde JEDER Abbruch faelschlich als 'fertig'
        gewertet)."""
        start = st.session_state["pomo_phase_start"]
        dur = end_ts - start
        if dur >= 5:   # winzige Fehlstarts nicht loggen
            manifest.log_study_session(
                subject=st.session_state.get("pomo_subject"), mode="pomodoro",
                started_at=start, ended_at=end_ts, duration_sec=round(dur))
            # Aus einem Lernplan-Block gestartet? -> die echte Zeit immer auf den
            # Block buchen (Grundlage der Zeitkalibrierung), aber nur bei einer
            # NATUERLICH abgelaufenen Arbeitsphase auch als erledigt markieren.
            _block_id = st.session_state.get("pomo_plan_block_id")
            if _block_id:
                manifest.add_block_actual_min(_block_id, round(dur / 60))
                if completed:
                    manifest.set_block_done(_block_id, True, via="pomodoro")
                    _linked_block = manifest.get_plan_block(_block_id)
                    if _linked_block:
                        manifest.sync_plan_status(_linked_block["plan_id"])

    def _pomo_reset() -> None:
        for k in list(st.session_state.keys()):
            if k.startswith("pomo_"):
                del st.session_state[k]

    @st.fragment(run_every=1)
    def _pomo_box() -> None:
        now = time.time()
        remaining = st.session_state["pomo_phase_len"] - (now - st.session_state["pomo_phase_start"])
        phase = st.session_state["pomo_phase"]
        _subj_txt = _fach(st.session_state.get("pomo_subject"))

        if remaining > 0:
            frac = 1 - remaining / st.session_state["pomo_phase_len"]
            st.progress(min(1.0, max(0.0, frac)))
            farbe = "#dc2626" if phase == "work" else "#16a34a"
            label = "🍅 Arbeitsblock" if phase == "work" else "☕ Pause"
            st.markdown(
                f"<div style='font-size:2.2rem;font-weight:750;letter-spacing:-.5px;"
                f"color:{farbe}'>{label}: {_fmt_hms(remaining)}</div>",
                unsafe_allow_html=True)
            st.caption(f"Fach: {_subj_txt} · Block {st.session_state['pomo_cycle'] + 1}")
            if st.button("⏹️ Abbrechen", key="pomo_cancel"):
                if phase == "work":
                    _log_work_block(now, completed=False)
                _pomo_reset()
                st.rerun()
            return

        # Phase abgelaufen -> genau EINMAL loggen, dann auf Bestätigung warten
        if phase == "work":
            if not st.session_state.get("pomo_logged"):
                _log_work_block(st.session_state["pomo_phase_start"]
                               + st.session_state["pomo_phase_len"], completed=True)
                st.session_state["pomo_logged"] = True
                st.session_state["pomo_cycle"] += 1
            st.success(f"✅ Arbeitsblock fertig! {st.session_state['pomo_work_min']} Min "
                      f"für {_subj_txt} gespeichert.")
            is_long = st.session_state["pomo_cycle"] % st.session_state["pomo_long_every"] == 0
            break_min = (st.session_state["pomo_long_break_min"] if is_long
                        else st.session_state["pomo_break_min"])
            c1, c2 = st.columns(2)
            if c1.button(f"☕ {'Lange ' if is_long else ''}Pause ({break_min} Min)",
                        use_container_width=True):
                st.session_state.update(pomo_phase="break", pomo_phase_start=time.time(),
                                        pomo_phase_len=break_min * 60, pomo_logged=False)
                st.rerun()
            if c2.button("⏹️ Beenden", use_container_width=True):
                _pomo_reset()
                st.rerun()
        else:
            st.info(f"☕ Pause vorbei. {st.session_state['pomo_cycle']} Block(e) heute geschafft.")
            c1, c2 = st.columns(2)
            if c1.button("▶️ Nächster Arbeitsblock", use_container_width=True):
                st.session_state.update(
                    pomo_phase="work", pomo_phase_start=time.time(),
                    pomo_phase_len=st.session_state["pomo_work_min"] * 60, pomo_logged=False)
                st.rerun()
            if c2.button("⏹️ Beenden", use_container_width=True):
                _pomo_reset()
                st.rerun()

    _pomo_box()

else:  # freier Timer läuft
    def _free_reset() -> None:
        for k in ("free_running", "free_start", "free_subject"):
            st.session_state.pop(k, None)

    @st.fragment(run_every=1)
    def _free_box() -> None:
        now = time.time()
        elapsed = now - st.session_state["free_start"]
        st.markdown(
            f"<div style='font-size:2.2rem;font-weight:750;letter-spacing:-.5px;'>"
            f"⏱️ {_fmt_hms(elapsed)}</div>", unsafe_allow_html=True)
        st.caption(f"Fach: {_fach(st.session_state.get('free_subject'))}")
        if st.button("⏹️ Stoppen & speichern", type="primary", key="free_stop"):
            if elapsed >= 5:
                manifest.log_study_session(
                    subject=st.session_state.get("free_subject"), mode="frei",
                    started_at=st.session_state["free_start"], ended_at=now,
                    duration_sec=round(elapsed))
                st.toast(f"{_fmt_dauer(elapsed)} gespeichert.")
            _free_reset()
            st.rerun()

    _free_box()

st.divider()

# --------------------------------------------------------------------------- #
# Heute & Verlauf
# --------------------------------------------------------------------------- #
st.subheader("📊 Lernzeit")

_today_start = time.mktime(date.today().timetuple())
_week_start = _today_start - 6 * 86400

_today_by_subj = manifest.study_time_by_subject(since=_today_start)
_week_by_subj = manifest.study_time_by_subject(since=_week_start)

m1, m2, m3 = st.columns(3)
m1.metric("Heute", _fmt_dauer(sum(_today_by_subj.values())))
m2.metric("Letzte 7 Tage", _fmt_dauer(sum(_week_by_subj.values())))
m3.metric("Insgesamt", _fmt_dauer(manifest.study_time_total()))

if _week_by_subj:
    _df_week = pd.DataFrame([
        {"Fach": _fach(s if s != "Ohne Fach" else None), "Minuten": round(sec / 60, 1)}
        for s, sec in _week_by_subj.items()
    ]).set_index("Fach")
    st.bar_chart(_df_week["Minuten"], height=200, color="#4A45C4")
    st.caption("Lernzeit (Minuten) je Fach, letzte 7 Tage.")
else:
    st.caption("Noch keine Lernzeit erfasst – starte oben einen Timer.")

st.markdown("##### Verlauf")
_sessions = manifest.list_study_sessions()[:100]
if not _sessions:
    st.caption("Noch keine Einträge.")
else:
    _sess_df = pd.DataFrame([{
        "🗑️": False,
        "Datum": time.strftime("%d.%m.%Y %H:%M", time.localtime(s["started_at"])),
        "Fach": _fach(s.get("subject")),
        "Modus": "🍅 Pomodoro" if s["mode"] == "pomodoro" else "⏱️ Frei",
        "Dauer": _fmt_dauer(s["duration_sec"]),
        "_id": s["session_id"],
    } for s in _sessions])
    _sess_edited = st.data_editor(
        _sess_df, hide_index=True, use_container_width=True, key="study_sessions_editor",
        column_config={
            "🗑️": st.column_config.CheckboxColumn(width="small"),
            "Datum": st.column_config.TextColumn(disabled=True),
            "Fach": st.column_config.TextColumn(disabled=True),
            "Modus": st.column_config.TextColumn(disabled=True),
            "Dauer": st.column_config.TextColumn(disabled=True),
            "_id": None,
        },
    )
    _del_ids = [row["_id"] for _, row in _sess_edited.iterrows() if row["🗑️"]]
    if st.button(f"🗑️ Ausgewählte löschen ({len(_del_ids)})", disabled=not _del_ids):
        for sid in _del_ids:
            manifest.delete_study_session(sid)
        st.success(f"{len(_del_ids)} Eintrag/Einträge gelöscht.")
        st.rerun()
