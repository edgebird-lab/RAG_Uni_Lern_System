"""
RAG-Lernsystem: Seite „Fortschritt" (Lern-Analytik & Klausurplanung)
====================================================================
Liest endlich das ``review_log`` aus: objektiver Lernstand statt Bauchgefuehl.
Zeigt Kennzahlen, Klausurtermine + Prioritaet, Treffer-Trend, Themen-Mastery,
die Faelligkeits-Prognose (Stau-Warnung) und Dauerpatzer - plus Datensicherung.
Alles offline, ohne LLM.
"""
from __future__ import annotations

import sys
import time
import pathlib
from datetime import date

# Projektwurzel auffindbar machen (damit 'ragapp' importierbar ist)
_p = pathlib.Path(__file__).resolve()
for _anc in _p.parents:
    if (_anc / "ragapp").is_dir():
        sys.path.insert(0, str(_anc))
        break

import streamlit as st

from ragapp.ui._loading import page_boot
page_boot("📈 Fortschritt", page_title="Fortschritt", icon="📈", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1050px;}
h1 {font-weight: 750; letter-spacing:-0.5px;}
</style>
""", unsafe_allow_html=True)

with st.spinner("Fortschritt wird geladen ..."):
    import pandas as pd
    from ragapp import analytics, planner, manifest, backup, sync as _sync
    from ragapp.config import settings, SUBJECT_LABELS


def _fach(code: str) -> str:
    return SUBJECT_LABELS.get(code, code)


st.caption("Dein objektiver Lernstand aus den echten Wiederholungen – damit du "
           "knappe Zeit auf die schwachen, klausurrelevanten Themen lenkst.")

# --------------------------------------------------------------------------- #
# Fach-Filter
# --------------------------------------------------------------------------- #
subjects = manifest.study_subjects()
if not subjects:
    st.info("Noch keine Karteikarten vorhanden. Erzeuge zuerst auf der Seite "
            "**🎓 Lernen** Karten aus deinen Unterlagen – dann erscheint hier dein Fortschritt.")
    st.stop()

col_f, _ = st.columns([1, 2])
with col_f:
    fach = st.selectbox("Fach", ["Alle Fächer"] + subjects,
                        format_func=lambda s: s if s == "Alle Fächer" else _fach(s))
subject = None if fach == "Alle Fächer" else fach

# --------------------------------------------------------------------------- #
# Kernkennzahlen
# --------------------------------------------------------------------------- #
ov = analytics.overview(subject)
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Karten", ov["total"], help="Aktive Abfrage-Karten in der Auswahl.")
c2.metric("Sitzt", f'{ov["mastery_pct"]} %',
          help=f'Anteil Karten mit ≥ {settings.MASTERY_TARGET_REPS} Wiederholungen in Folge.')
c3.metric("Fällig", ov["due"], help="Jetzt zur Wiederholung anstehend.")
c4.metric("Streak", f'{ov["streak"]} 🔥', help="Zusammenhängende Lerntage.")
acc = "–" if ov["accuracy_7d"] is None else f'{ov["accuracy_7d"]} %'
c5.metric("Treffer (7 T.)", acc,
          help=f'Anteil „gewusst" der letzten 7 Tage · {ov["reviews_7d"]} Wiederholungen.')
if ov["leeches"]:
    st.caption(f'⚠️ {ov["leeches"]} Dauerpatzer (Leech-Karten) in der Auswahl – siehe unten.')

# Klausur-Bereitschaft + Tagesziel-Ampel
_ready = analytics.subject_readiness(subject)["readiness_pct"]
_goal = analytics.daily_goal_status(subject)
_ampel = {"grün": "🟢", "gelb": "🟡", "rot": "🔴"}.get(_goal["ampel"], "🟢")
gc1, gc2 = st.columns(2)
gc1.metric("Klausur-Bereitschaft (Schätzung)", f"{_ready} %",
           help="Geschätzte mittlere Abrufwahrscheinlichkeit über alle Karten "
                "(Vergessenskurve aus SM-2). Eine Schätzung, keine Garantie.")
gc2.metric("Heute-Ziel", f'{_goal["done_today"]} / {_goal["goal"]}',
           delta=f'{_ampel} {_goal["due"]} fällig', delta_color="off",
           help="Heute geübte Wiederholungen vs. Tagesziel · Ampel = Backlog "
                "(🟢 im Griff, 🟡 viel, 🔴 sehr viel fällig).")

st.divider()

# --------------------------------------------------------------------------- #
# Klausurtermine + Prioritaet
# --------------------------------------------------------------------------- #
st.subheader("🗓️ Klausurtermine & Priorität")
st.caption("Setze die Termine, dann priorisiert das System nach Klausurnähe × Wissenslücke × Gewicht.")

with st.expander("Klausurtermin setzen / ändern", expanded=not manifest.list_exams()):
    with st.form("exam_form", clear_on_submit=False):
        ecol1, ecol2, ecol3 = st.columns([2, 2, 1])
        with ecol1:
            ex_subject = st.selectbox("Fach", subjects, format_func=_fach, key="ex_subj")
        existing = manifest.get_exam(ex_subject) or {}
        _cur_date = None
        if existing.get("exam_date"):
            try:
                _y, _m, _d = (int(x) for x in existing["exam_date"].split("-")[:3])
                _cur_date = date(_y, _m, _d)
            except Exception:  # noqa: BLE001
                _cur_date = None
        with ecol2:
            ex_date = st.date_input("Klausurdatum", value=_cur_date, format="DD.MM.YYYY")
        with ecol3:
            ex_weight = st.number_input("Gewicht", min_value=0.1, max_value=10.0,
                                        value=float(existing.get("gewicht") or 1.0), step=0.5,
                                        help="Wie wichtig ist dieses Fach relativ? (ECTS-artig)")
        ex_ects = st.number_input("ECTS (optional)", min_value=0.0, max_value=60.0,
                                  value=float(existing.get("ects") or 0.0), step=1.0)
        s1, s2 = st.columns(2)
        save = s1.form_submit_button("💾 Termin speichern", use_container_width=True)
        clear = s2.form_submit_button("🗑️ Termin entfernen", use_container_width=True)
        if save:
            manifest.upsert_exam(ex_subject, exam_date=ex_date.isoformat() if ex_date else None,
                                 ects=ex_ects or None, gewicht=ex_weight)
            st.success(f"Termin für {_fach(ex_subject)} gespeichert.")
            st.rerun()
        if clear:
            manifest.delete_exam(ex_subject)
            st.info(f"Termin für {_fach(ex_subject)} entfernt.")
            st.rerun()

prios = planner.all_priorities()
if prios:
    dfp = pd.DataFrame([{
        "Fach": _fach(p["subject"]),
        "Klausur": planner.humanize_days(p["days_to_exam"]),
        "Datum": p["exam_date"] or "–",
        "Mastery %": p["mastery_pct"],
        "Gewicht": p["weight"],
        "Priorität": p["priority"],
    } for p in prios])
    st.dataframe(dfp, use_container_width=True, hide_index=True,
                 column_config={"Priorität": st.column_config.ProgressColumn(
                     "Priorität", min_value=0.0,
                     max_value=max(1.0, float(dfp["Priorität"].max())), format="%.2f")})

_ics = planner.exams_to_ics()
if _ics:
    st.download_button("📅 Klausurtermine als Kalender (.ics)", data=_ics,
                       file_name="klausurtermine.ics", mime="text/calendar",
                       help="In Google/Apple/Outlook-Kalender importieren.")

st.divider()

# --------------------------------------------------------------------------- #
# Treffer-Trend & Fälligkeits-Prognose
# --------------------------------------------------------------------------- #
tcol1, tcol2 = st.columns(2)
with tcol1:
    st.subheader("📉 Treffer-Verlauf (30 Tage)")
    tr = analytics.retention_trend(30, subject)
    dft = pd.DataFrame(tr).set_index("tag")
    st.line_chart(dft["treffer_pct"], height=220, color="#4A45C4")
    st.bar_chart(dft["wiederholungen"], height=140, color="#9BA3C9")
with tcol2:
    st.subheader("📅 Fälligkeits-Prognose (14 Tage)")
    st.caption("Warnt vor Wiederholungs-Stau kurz vor der Klausur.")
    fc = analytics.due_forecast(14, subject)
    dff = pd.DataFrame(fc).set_index("tag")
    st.bar_chart(dff["faellig"], height=360, color="#C08A2E")

st.divider()

# --------------------------------------------------------------------------- #
# Mastery je Fach / Thema
# --------------------------------------------------------------------------- #
st.subheader("🎯 Mastery")
mcol1, mcol2 = st.columns([1, 1])
with mcol1:
    st.caption("Anteil sitzender Karten je Fach")
    ms = analytics.mastery_by_subject()
    if ms:
        dfm = pd.DataFrame([{"Fach": _fach(m["subject"]), "Mastery %": m["mastery_pct"]}
                            for m in ms]).set_index("Fach")
        st.bar_chart(dfm["Mastery %"], height=max(160, 40 * len(dfm)), horizontal=True,
                     color="#3E9B6C")
with mcol2:
    topic_subject = subject or (subjects[0] if subjects else None)
    st.caption(f"Schwächste Themen · {_fach(topic_subject)}")
    tp = analytics.mastery_by_topic(topic_subject, limit=12) if topic_subject else []
    if tp:
        dftp = pd.DataFrame([{"Thema": (t["topic"] or "")[:48], "Mastery %": t["mastery_pct"],
                              "Karten": t["cards"], "Patzer": t["lapses"]} for t in tp])
        st.dataframe(dftp, use_container_width=True, hide_index=True,
                     column_config={"Mastery %": st.column_config.ProgressColumn(
                         "Mastery %", min_value=0, max_value=100, format="%d %%")})
    else:
        st.caption("Noch keine Themendaten.")

st.divider()

# --------------------------------------------------------------------------- #
# Vergessenskurve (projizierte Bereitschaft zum Klausurtermin)
# --------------------------------------------------------------------------- #
st.subheader("📈 Klausur-Bereitschaft im Zeitverlauf")
_curve_subj = subject or (subjects[0] if subjects else None)
if _curve_subj:
    _ex = manifest.get_exam(_curve_subj)
    _dte = planner.days_to_exam(_ex["exam_date"]) if _ex and _ex.get("exam_date") else None
    _ahead = min(max(_dte, 7), 90) if _dte and _dte > 0 else 30
    _curve = analytics.forgetting_curve(_curve_subj, days_ahead=_ahead)
    if _curve:
        _cap_txt = f"Ohne weiteres Üben · {_fach(_curve_subj)}"
        if _dte and _dte > 0:
            _cap_txt += f" · Klausur in {_dte} Tagen (rechter Rand)"
        st.caption(_cap_txt + " – übe weiter, damit die Kurve oben bleibt.")
        _dfcurve = pd.DataFrame(_curve).set_index("tag")
        st.area_chart(_dfcurve["bereitschaft_pct"], height=240, color="#C08A2E")

st.divider()

# --------------------------------------------------------------------------- #
# Dauerpatzer (Leeches)
# --------------------------------------------------------------------------- #
st.subheader("🩹 Dauerpatzer")
leeches = analytics.leeches(subject, limit=40)
if leeches:
    st.caption(f"{len(leeches)} Karten mit ≥ {settings.LEECH_LAPSES_THRESHOLD} Patzern – "
               "hier lohnt Umformulieren/Aufteilen statt stumpfem Wiederholen.")
    dfl = pd.DataFrame([{"Frage": (c.get("front") or "")[:80], "Fach": _fach(c.get("subject") or ""),
                         "Patzer": c.get("lapses"), "Ease": round(c.get("ease") or 0, 2)}
                        for c in leeches])
    st.dataframe(dfl, use_container_width=True, hide_index=True)
    if st.button(f'➡️ Diese {len(leeches)} Karten als Stapel „Schwachstellen" sammeln'):
        n = manifest.assign_deck("Schwachstellen",
                                 card_ids=[c["card_id"] for c in leeches])
        st.success(f'{n} Karten dem Stapel „Schwachstellen" zugeordnet – jetzt gezielt '
                   "auf 🎓 Lernen üben.")
        st.rerun()
else:
    st.caption("Keine Dauerpatzer – gut! 🎉")

st.divider()

# --------------------------------------------------------------------------- #
# Datensicherung
# --------------------------------------------------------------------------- #
st.subheader("💾 Datensicherung")
st.caption("Dein Lernfortschritt (jede Wiederholung) ist unersetzlich. Snapshots werden "
           "automatisch vor dem Löschen von Karten und beim Start gezogen.")
bcol1, bcol2 = st.columns([1, 2])
with bcol1:
    if st.button("Jetzt sichern", use_container_width=True):
        p = backup.snapshot("manuell")
        st.success(f"Gesichert: {p.name}" if p else "Sicherung fehlgeschlagen.")
        st.rerun()
snaps = backup.list_snapshots()
with bcol2:
    if snaps:
        chosen = st.selectbox("Snapshot", snaps, format_func=lambda s: (
            f'{s["name"]} · {time.strftime("%d.%m.%Y %H:%M", time.localtime(s["when"]))} · {s["size_kb"]} KB'))
        confirm = st.checkbox("Ich will diesen Stand wiederherstellen (der aktuelle wird vorher gesichert).")
        if st.button("Wiederherstellen", disabled=not confirm, use_container_width=True):
            ok = backup.restore(chosen["path"])
            st.success("Wiederhergestellt. Bitte Seite neu laden.") if ok else st.error("Fehlgeschlagen.")
            st.rerun()
    else:
        st.caption("Noch keine Snapshots vorhanden.")

st.divider()

# --------------------------------------------------------------------------- #
# Multi-Device-Sync (Handy ↔ PC)
# --------------------------------------------------------------------------- #
st.subheader("📱 Handy ↔ PC synchronisieren")
st.caption("Exportiere deinen Lernverlauf und importiere ihn auf dem anderen Gerät. "
           "Konflikte lösen sich automatisch – jede einzelne Wiederholung bleibt erhalten "
           "(kein Überschreiben ganzer Sitzungen). Der Import ist wiederholbar "
           "(Duplikate werden erkannt).")
sc1, sc2 = st.columns(2)
sc1.download_button("⬇️ Lernverlauf exportieren", data=_sync.export_events(),
                    file_name="lernverlauf.jsonl", mime="application/json",
                    use_container_width=True)
_up = sc2.file_uploader("Verlauf importieren (.jsonl)", type=["jsonl", "json", "txt"])
if _up is not None:
    _sr = _sync.import_events(_up.getvalue().decode("utf-8", "replace"))
    st.success(f'{_sr["imported"]} neue Wiederholungen übernommen, {_sr["skipped"]} bereits '
               f'vorhanden · Zustand von {_sr["updated"]} Karten neu berechnet.')
    st.rerun()
