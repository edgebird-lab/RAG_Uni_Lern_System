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
page_boot("📈 Fortschritt", page_title="Fortschritt", icon="📈", layout="wide",
         accent="fortschritt")

from ragapp.ui._style import card, theme_for
from ragapp.ui import _charts
_theme = theme_for("fortschritt")

st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1050px;}
h1 {font-weight: 750; letter-spacing:-0.5px;}
</style>
""", unsafe_allow_html=True)

with st.spinner("Fortschritt wird geladen ..."):
    import pandas as pd
    from ragapp import analytics, planner, manifest, backup, study_plan, sync as _sync
    from ragapp import achievements as _achievements
    from ragapp.config import settings, SUBJECT_LABELS


def _fach(code: str) -> str:
    return SUBJECT_LABELS.get(code, code)


def _fmt_min(m: int) -> str:
    m = int(m)
    if m < 60:
        return f"{m} Min"
    h, r = divmod(m, 60)
    return f"{h} Std {r} Min" if r else f"{h} Std"


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
with card("kennzahlen"):
    ov = analytics.overview(subject)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Karten", ov["total"], help="Aktive Abfrage-Karten in der Auswahl.")
    c2.metric("Sitzt", f'{ov["mastery_pct"]} %',
              help=f'Anteil Karten mit ≥ {settings.MASTERY_TARGET_REPS} Wiederholungen in Folge.')
    # Gauge-Balken UNTER der nackten Prozentzahl - anders als die Sparkline
    # weiter unten (Verlauf ueber Zeit, erst ab 2 Tagen Historie) zeigt das
    # sofort "wie voll ist das GERADE JETZT", ohne auf Historie zu warten.
    c2.markdown(_charts.progress_bar(ov["mastery_pct"], color=_theme["accent"]),
               unsafe_allow_html=True)
    c3.metric("Fällig", ov["due"], help="Jetzt zur Wiederholung anstehend.")
    c4.metric("Streak", f'{ov["streak"]} 🔥', help="Zusammenhängende Lerntage.")
    # Kleine Sparkline direkt unter der nackten Streak-Zahl: zeigt auf einen
    # Blick, WIE die Zahl zustande kam (an welchen der letzten 7 Tage
    # tatsächlich geübt wurde), statt nur ein isoliertes "2 🔥" hinzuwerfen.
    _last7 = analytics.retention_trend(7, subject)
    c4.markdown(_charts.sparkline([d["wiederholungen"] for d in _last7],
                                  color=_theme["accent"], height=28),
               unsafe_allow_html=True)
    acc = "–" if ov["accuracy_7d"] is None else f'{ov["accuracy_7d"]} %'
    c5.metric("Treffer (7 T.)", acc,
              help=f'Anteil „gewusst" der letzten 7 Tage · {ov["reviews_7d"]} Wiederholungen.')
    # Heutigen Stand als Schnappschuss festhalten (ueberschreibt sich am selben
    # Tag) - Grundlage der beiden Verlaufs-Sparklines direkt unten, siehe
    # analytics.record_progress_snapshot()-Docstring.
    analytics.record_progress_snapshot(subject)
    _snap_trend = analytics.progress_snapshot_trend(subject, days=14)
    # Sparkline unter "Sitzt" nur zusaetzlich, wenn schon mind. 2 Tage Historie
    # vorliegen (bei genau 1 Punkt wirkt ein Balken irrefuehrend "voll").
    if len(_snap_trend) >= 2:
        c2.markdown(_charts.sparkline([d["mastery_pct"] for d in _snap_trend],
                                      color=_theme["accent"], height=24),
                   unsafe_allow_html=True)
    if ov["leeches"]:
        st.caption(f'⚠️ {ov["leeches"]} Dauerpatzer (Leech-Karten) in der Auswahl – siehe unten.')

    # Klausur-Bereitschaft + Tagesziel-Ampel
    _ready = analytics.subject_readiness(subject)["readiness_pct"]
    _goal = analytics.daily_goal_status(subject)
    _ampel = {"grün": "🟢", "gelb": "🟡", "rot": "🔴"}.get(_goal["ampel"], "🟢")
    gc1, gc2 = st.columns(2)
    gc1.metric("Klausur-Bereitschaft (Schätzung)", f"{_ready} %",
               help="Geschätzte mittlere Abrufwahrscheinlichkeit über alle Karten "
                    "(Vergessenskurve aus FSRS-6). Eine Schätzung, keine Garantie.")
    gc1.markdown(_charts.progress_bar(_ready, color="#C08A2E"), unsafe_allow_html=True)
    if len(_snap_trend) >= 2:
        gc1.markdown(_charts.sparkline([d["readiness_pct"] for d in _snap_trend],
                                       color="#C08A2E", height=24),
                   unsafe_allow_html=True)
    else:
        gc1.caption("📈 Verlauf sammelt sich – ab morgen siehst du hier den Trend.")
    gc2.metric("Heute-Ziel", f'{_goal["done_today"]} / {_goal["goal"]}',
               delta=f'{_ampel} {_goal["due"]} fällig', delta_color="off",
               help="Heute geübte Wiederholungen vs. Tagesziel · Ampel = Backlog "
                    "(🟢 im Griff, 🟡 viel, 🔴 sehr viel fällig).")
    if ov["reviews_7d"] == 0:
        st.caption("💡 Noch keine Wiederholung in den letzten 7 Tagen – die Zahlen oben "
                   "sind noch nicht aussagekräftig. Starte auf **🎓 Lernen** deine erste "
                   "Lernrunde, dann füllen sie sich mit echten Werten.")

# --------------------------------------------------------------------------- #
# Errungenschaften: Katalog lebt in ragapp/achievements.py, hier nur Anzeige +
# das "Freischalten fühlt sich an wie etwas" (Balloons + Maskottchen-Jubel) -
# check_and_unlock() ist idempotent, ein Aufruf pro Seitenaufruf reicht.
# --------------------------------------------------------------------------- #
with card("errungenschaften"):
    st.subheader("🏆 Errungenschaften")
    _newly_unlocked = _achievements.check_and_unlock()
    if _newly_unlocked:
        st.balloons()
        from ragapp.ui._mascot import render_mascot_corner as _render_mascot_corner
        _render_mascot_corner(_theme["accent"], pose="cheer", animation="wave", prop="star")
        for _na in _newly_unlocked:
            st.success(f"**Neu freigeschaltet:** {_na.icon} {_na.title} – {_na.description}")
    _unlocked_map = manifest.list_unlocked_achievements()
    _catalog = _achievements.catalog()
    _ach_cols = st.columns(4)
    for _i, _ach in enumerate(_catalog):
        _col = _ach_cols[_i % 4]
        if _ach.id in _unlocked_map:
            _when = time.strftime("%d.%m.%Y", time.localtime(_unlocked_map[_ach.id]))
            _col.markdown(f"**{_ach.icon} {_ach.title}**")
            _col.caption(f"{_ach.description}\n\nFreigeschaltet am {_when}.")
        elif _ach.hidden:
            # Ueberraschungs-Errungenschaft: Titel/Beschreibung bleiben bis
            # zum Freischalten bewusst verborgen (siehe achievements.py).
            _col.markdown("**❓ Geheime Errungenschaft**")
            _col.caption("Wird erst beim Freischalten verraten.")
        else:
            _col.markdown(f"**🔒 {_ach.title}**")
            _col.caption(_ach.description)
            if _ach.progress is not None:
                try:
                    _cur, _tgt = _ach.progress()
                    _pct = min(100.0, 100.0 * _cur / _tgt) if _tgt else 0.0
                    _col.markdown(_charts.progress_bar(_pct, color=_theme["accent"]),
                                 unsafe_allow_html=True)
                    _col.caption(f"{_cur:g} / {_tgt:g}")
                except Exception:  # noqa: BLE001 - Fortschrittsanzeige ist ein Bonus
                    pass
    _n_done = len(_unlocked_map)
    st.caption(f"{_n_done} / {len(_catalog)} freigeschaltet.")

# --------------------------------------------------------------------------- #
# Wochenrückblick: diese Woche vs. die Woche davor - macht Fortschritt bewusst
# SPÜRBAR statt nur verfügbar (reine Sparklines werden mit der Zeit leicht
# übersehen, siehe analytics.weekly_recap()-Docstring).
# --------------------------------------------------------------------------- #
with card("wochenrueckblick"):
    st.subheader("📅 Wochenrückblick")
    _recap = analytics.weekly_recap(subject)
    _tw, _pw = _recap["this_week"], _recap["prev_week"]
    if _tw["reviews"] == 0 and _pw["reviews"] == 0 and _tw["minutes"] == 0 and _pw["minutes"] == 0:
        st.caption("Noch keine zwei Wochen Verlauf für einen Vergleich – komm bald wieder.")
    else:
        wc1, wc2, wc3 = st.columns(3)
        wc1.metric("Wiederholungen", _tw["reviews"],
                  delta=(_tw["reviews"] - _pw["reviews"]) or None,
                  help="Diese Woche vs. die 7 Tage davor.")
        _acc_delta = (None if _tw["accuracy_pct"] is None or _pw["accuracy_pct"] is None
                     else _tw["accuracy_pct"] - _pw["accuracy_pct"])
        wc2.metric("Trefferquote",
                  f'{_tw["accuracy_pct"]} %' if _tw["accuracy_pct"] is not None else "–",
                  delta=(f"{_acc_delta:+d} %-Punkte" if _acc_delta else None),
                  help='Anteil „gewusst" diese Woche vs. die 7 Tage davor.')
        wc3.metric("Lernzeit (Min)", _tw["minutes"] if _tw["minutes"] else "–",
                  delta=(_tw["minutes"] - _pw["minutes"]) or None,
                  help="Minuten diese Woche vs. die 7 Tage davor.")

# --------------------------------------------------------------------------- #
# Klausurtermine + Prioritaet
# --------------------------------------------------------------------------- #
with card("klausur"):
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
            ex_note = st.number_input(
                "Note (nach der Klausur eintragen)", min_value=0.0, max_value=6.0,
                value=float(existing.get("note") or 0.0), step=0.1,
                help="0,0 = noch keine Note eingetragen. Fließt ECTS-gewichtet in "
                     "den Notenschnitt unten ein.")
            s1, s2 = st.columns(2)
            save = s1.form_submit_button("💾 Termin speichern", use_container_width=True)
            clear = s2.form_submit_button("🗑️ Termin entfernen", use_container_width=True)
            if save:
                manifest.upsert_exam(ex_subject, exam_date=ex_date.isoformat() if ex_date else None,
                                     ects=ex_ects or None, gewicht=ex_weight, note=ex_note or None)
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

    _gpa = planner.gpa_summary()
    if _gpa["count"]:
        st.divider()
        st.subheader("🎓 Notenschnitt")
        ngc1, ngc2 = st.columns(2)
        ngc1.metric("Ø-Note (ECTS-gewichtet)", f'{_gpa["gpa"]:.2f}',
                    help="Gewichteter Durchschnitt aller eingetragenen Noten – Fächer ohne "
                         "ECTS-Angabe zählen mit Gewicht 1,0.")
        ngc2.metric("Bewertete Klausuren", _gpa["count"])
        dfg = pd.DataFrame([{
            "Fach": _fach(e["subject"]), "Note": e["note"],
            "ECTS": e["ects"] if e.get("ects") else "–",
        } for e in sorted(_gpa["exams"], key=lambda e: e["subject"])])
        st.dataframe(dfg, use_container_width=True, hide_index=True)

# --------------------------------------------------------------------------- #
# Fach-Archivierung: ein "fertiges" Fach (Klausur vorbei, Note eingetragen)
# raeumt sich damit selbst aus den Lern-Dropdowns/Faelligkeits-Zaehlern - ohne
# dass irgendetwas geloescht wird (siehe manifest.archive_subject()). Noten/
# Klausurtermine oben bleiben davon unberuehrt, die sollen ja gerade dauerhaft
# sichtbar bleiben.
# --------------------------------------------------------------------------- #
with card("archiv"):
    st.subheader("📦 Fächer archivieren")
    st.caption('Ein archiviertes Fach verschwindet aus den Lern-/Fortschritt-Auswahlen '
              '(Karten bleiben erhalten, tauchen nur nicht mehr als „fällig" auf) - '
              'praktisch, wenn Klausur und Note schon durch sind.')
    _archived = manifest.list_archived_subjects()
    _ac1, _ac2 = st.columns(2)
    with _ac1:
        if subjects:
            _to_archive = st.selectbox("Fach archivieren", subjects, format_func=_fach,
                                       key="archive_pick")
            if st.button("📦 Archivieren", key="archive_go", use_container_width=True):
                _n_arch = manifest.archive_subject(_to_archive)
                st.success(f"{_fach(_to_archive)} archiviert ({_n_arch} Karte(n) pausiert).")
                st.rerun()
        else:
            st.caption("Keine aktiven Fächer zum Archivieren.")
    with _ac2:
        if _archived:
            st.caption("Archivierte Fächer:")
            for _a_subj in _archived:
                _rc1, _rc2 = st.columns([3, 1])
                _rc1.markdown(f"📦 {_fach(_a_subj)}")
                if _rc2.button("↩️", key=f"unarchive_{_a_subj}", help="Reaktivieren"):
                    _n_un = manifest.unarchive_subject(_a_subj)
                    st.success(f"{_fach(_a_subj)} reaktiviert ({_n_un} Karte(n)).")
                    st.rerun()
        else:
            st.caption("Noch keine Fächer archiviert.")

# --------------------------------------------------------------------------- #
# Treffer-Trend & Fälligkeits-Prognose
# --------------------------------------------------------------------------- #
with card("trend"):
    tcol1, tcol2 = st.columns(2)
    with tcol1:
        st.subheader("📉 Treffer-Verlauf (30 Tage)")
        tr = analytics.retention_trend(30, subject)
        _tage = [t["tag"] for t in tr]
        st.markdown(_charts.line_chart(_tage, [t["treffer_pct"] for t in tr],
                                        color=_theme["accent"], height=200, value_suffix=" %"),
                    unsafe_allow_html=True)
        st.markdown(_charts.bar_chart(_tage, [t["wiederholungen"] for t in tr],
                                       color="#9BA3C9", height=110),
                    unsafe_allow_html=True)
    with tcol2:
        st.subheader("📅 Fälligkeits-Prognose (14 Tage)")
        st.caption("Warnt vor Wiederholungs-Stau kurz vor der Klausur.")
        fc = analytics.due_forecast(14, subject)
        st.markdown(_charts.bar_chart([f["tag"] for f in fc], [f["faellig"] for f in fc],
                                       color="#C08A2E", height=340),
                    unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
# Mastery je Fach / Thema
# --------------------------------------------------------------------------- #
with card("mastery"):
    st.subheader("🎯 Mastery")
    mcol1, mcol2 = st.columns([1, 1])
    with mcol1:
        st.caption("Anteil sitzender Karten je Fach")
        ms = analytics.mastery_by_subject()
        if ms:
            st.markdown(_charts.bar_chart(
                [_fach(m["subject"]) for m in ms], [m["mastery_pct"] for m in ms],
                color="#3E9B6C", height=max(150, 34 * len(ms)), horizontal=True, value_suffix=" %"),
                unsafe_allow_html=True)
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

# --------------------------------------------------------------------------- #
# Plan vs. Realität (selbstlernender Zeit-Korrekturfaktor des Lernplans)
# --------------------------------------------------------------------------- #
with card("planzeit"):
    st.subheader("⏱️ Plan vs. Realität")
    st.caption("Vergleicht die vom Lernplan geschätzte Zeit mit der tatsächlich per "
               "Pomodoro-Timer erfassten Zeit – Grundlage des selbstlernenden "
               "Zeit-Korrekturfaktors (siehe Seite 📋 Lernplan).")
    _pt = manifest.plan_time_totals(subject)
    _tf = study_plan.time_factor_info(subject)
    _tf_src = {"subject": f"kalibriert für {_fach(subject)}" if subject else "kalibriert",
              "global": "kalibriert, alle Fächer",
              "default": "Standardwert"}.get(_tf["source"], "Standardwert")
    pfc1, pfc2, pfc3 = st.columns(3)
    pfc1.metric("Zeit-Korrekturfaktor", f'{_tf["factor"]:.2f}×', help=(
        f"Quelle: {_tf_src}. 1.0× = reine Formel ohne Aufschlag. Wird automatisch "
        "genauer, je mehr erledigte Lernplan-Blöcke mit echter Pomodoro-Zeit "
        "vorliegen. Manuell einstellbar unter ⚙️ Einstellungen → 📋 Lernplan."))
    if _pt["measured_blocks"] > 0 and _pt["planned_for_measured"] > 0:
        _ratio = _pt["actual_for_measured"] / _pt["planned_for_measured"]
        pfc2.metric("Geplant → real (gemessen)",
                   f'{_fmt_min(_pt["planned_for_measured"])} → {_fmt_min(_pt["actual_for_measured"])}',
                   delta=f"{_ratio:.1f}×", delta_color="off",
                   help=f'{_pt["measured_blocks"]} erledigte(r) Lernplan-Block(e) mit echter '
                        "Pomodoro-Zeitmessung (über „🍅 Pomodoro“ auf der Lernplan-Seite gestartet).")
    else:
        pfc2.metric("Geplant → real (gemessen)", "–",
                   help="Noch keine per Pomodoro erfasste Block-Zeit. Starte Lernplan-Blöcke "
                        "über „🍅 Pomodoro“ statt nur abzuhaken, damit echte Zeit erfasst wird.")
    pfc3.metric("Manuell abgehakt", _pt["manual_blocks"],
               help="Erledigte Blöcke ohne echte Zeitmessung (Haken ohne Timer, z. B. bei "
                    "Programmieraufgaben) – fließen nicht in die Kalibrierung ein.")
    if _pt["measured_blocks"] < 5:
        st.caption(f"Noch zu wenige Messungen ({_pt['measured_blocks']}/5) für einen eigenen "
                  "kalibrierten Faktor – bis dahin gilt der Standard-/manuelle Wert.")

# --------------------------------------------------------------------------- #
# Vergessenskurve (projizierte Bereitschaft zum Klausurtermin)
# --------------------------------------------------------------------------- #
with card("kurve"):
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
            st.markdown(_charts.line_chart(
                [c["tag"] for c in _curve], [c["bereitschaft_pct"] for c in _curve],
                color="#C08A2E", height=220, value_suffix=" %"),
                unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
# Dauerpatzer (Leeches)
# --------------------------------------------------------------------------- #
with card("leeches"):
    st.subheader("🩹 Dauerpatzer")
    leeches = analytics.leeches(subject, limit=40)
    if leeches:
        st.caption(f"{len(leeches)} Karten mit ≥ {settings.LEECH_LAPSES_THRESHOLD} Patzern – "
                   "hier lohnt Umformulieren/Aufteilen statt stumpfem Wiederholen. Frage/Antwort "
                   "direkt hier bearbeiten – meist steckt der Dauerpatzer in einer zu unscharf "
                   "gestellten Frage oder einer zu grossen Antwort.")
        _leech_orig = {c["card_id"]: c for c in leeches}
        _dfl = pd.DataFrame([{
            "Frage": c.get("front") or "",
            "Antwort": c.get("answer") or c.get("back") or "",
            "Fach": _fach(c.get("subject") or ""),
            "Patzer": c.get("lapses"),
            "Schwierigkeit": round(c.get("difficulty") or 0, 1) if c.get("difficulty") else None,
            "_id": c["card_id"],
        } for c in leeches])
        _edited_l = st.data_editor(
            _dfl, hide_index=True, use_container_width=True, key="leech_editor",
            column_config={
                "Frage": st.column_config.TextColumn(width="large"),
                "Antwort": st.column_config.TextColumn(width="large"),
                "Fach": st.column_config.TextColumn(disabled=True),
                "Patzer": st.column_config.NumberColumn(disabled=True),
                "Schwierigkeit": st.column_config.NumberColumn(
                    disabled=True, help="FSRS-Schwierigkeit (1=leicht … 10=schwer)."),
                "_id": None,
            },
        )
        # Dokumente hinter den Dauerpatzern (fuer den Fokus-Lernplan) - nur solche, die
        # tatsaechlich im RAG sind (sonst kann daraus keine Gliederung entstehen).
        _leech_doc_ids: list[str] = []
        for _did in sorted({c.get("doc_id") for c in leeches if c.get("doc_id")}):
            _doc = manifest.get_document(_did)
            if _doc is not None and _doc["use_rag"]:
                _leech_doc_ids.append(_did)

        lb1, lb2, lb3 = st.columns(3)
        if lb1.button("💾 Frage/Antwort speichern", use_container_width=True):
            _n_edit = 0
            for _, row in _edited_l.iterrows():
                o = _leech_orig.get(row["_id"])
                if o is None:
                    continue
                nf, na = (row["Frage"] or "").strip(), (row["Antwort"] or "").strip()
                of = (o.get("front") or "").strip()
                oa = (o.get("answer") or o.get("back") or "").strip()
                if nf != of or na != oa:
                    manifest.update_card(row["_id"], front=nf if nf != of else None,
                                         answer=na if na != oa else None)
                    _n_edit += 1
            st.success(f"{_n_edit} Karte(n) aktualisiert." if _n_edit else "Keine Änderungen.")
            if _n_edit:
                st.rerun()
        if lb2.button(f'➡️ Diese {len(leeches)} Karten als Stapel „Schwachstellen" sammeln',
                     use_container_width=True):
            n = manifest.assign_deck("Schwachstellen",
                                     card_ids=[c["card_id"] for c in leeches])
            st.success(f'{n} Karten dem Stapel „Schwachstellen" zugeordnet – jetzt gezielt '
                       "auf 🎓 Lernen üben.")
            st.rerun()
        if lb3.button(f"📋 Fokus-Lernplan ({len(_leech_doc_ids)} Dok.)", use_container_width=True,
                     disabled=not _leech_doc_ids,
                     help="Legt einen neuen Lernplan-Entwurf an, der sich auf die "
                          "Dokumente hinter diesen Dauerpatzern konzentriert."):
            _leech_subject = subject or (leeches[0].get("subject") if leeches else None)
            _leech_title = ("Fokus: Dauerpatzer " + _fach(_leech_subject)) if _leech_subject \
                else "Fokus: Dauerpatzer"
            st.session_state["splan_prefill"] = {
                "subject": _leech_subject, "doc_ids": _leech_doc_ids, "title": _leech_title,
            }
            st.switch_page("pages/11_📋_Lernplan.py")
    else:
        _max_lapses = analytics.max_lapses(subject)
        st.caption(
            f"Keine Dauerpatzer – gut! 🎉 (höchste Patzer-Zahl aktuell: {_max_lapses}, "
            f"Schwelle: {settings.LEECH_LAPSES_THRESHOLD}. Eine Karte erscheint hier erst, "
            "wenn sie mindestens so oft als „nicht gewusst“ bewertet wurde.)")

# --------------------------------------------------------------------------- #
# Datensicherung
# --------------------------------------------------------------------------- #
with card("backup"):
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

# --------------------------------------------------------------------------- #
# Multi-Device-Sync (Handy ↔ PC)
# --------------------------------------------------------------------------- #
with card("sync"):
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

# --------------------------------------------------------------------------- #
# Anki-Export (Karten unterwegs lernen - ganz ohne PC/Server/Modell)
# --------------------------------------------------------------------------- #
with card("anki"):
    st.subheader("📤 Anki-Export")
    st.caption(
        "Exportiert Frage + Antwort deiner Karten als Anki-Deck (.apkg) – lernbar mit "
        "AnkiDroid/AnkiMobile **komplett ohne diesen Server, ohne PC, ohne Modell**. "
        "Dein Lernfortschritt (Fälligkeit, Klausurplanung) bleibt weiterhin hier die "
        "Quelle der Wahrheit; Anki startet die exportierten Karten als „neu“ und plant "
        "sie mit seinem eigenen Wiederholungs-Algorithmus."
    )
    ac1, ac2 = st.columns(2)
    with ac1:
        _anki_subject = st.selectbox(
            "Fach", ["Alle Fächer"] + subjects, key="anki_subject",
            format_func=lambda s: s if s == "Alle Fächer" else _fach(s))
    with ac2:
        st.write("")
        st.write("")
        if st.button("📤 .apkg erzeugen", use_container_width=True):
            try:
                from ragapp.export_anki import build_apkg
                _sub_arg = None if _anki_subject == "Alle Fächer" else _anki_subject
                _apkg_bytes, _apkg_n = build_apkg(subject=_sub_arg)
                st.session_state["_anki_apkg"] = _apkg_bytes
                st.session_state["_anki_apkg_n"] = _apkg_n
            except ModuleNotFoundError:
                st.error("Dazu fehlt das Paket `genanki` – bitte `pip install -r requirements.txt` "
                          "erneut ausführen.")
    if st.session_state.get("_anki_apkg"):
        st.download_button(
            f'⬇️ {st.session_state["_anki_apkg_n"]} Karten herunterladen (.apkg)',
            data=st.session_state["_anki_apkg"], file_name="rag-lernsystem.apkg",
            mime="application/octet-stream", use_container_width=True)
