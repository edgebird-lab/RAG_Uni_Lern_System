"""
RAG-Lernsystem: Seite „Organisation" (Stundenplan, Aufgaben, Wochen-Dashboard)
================================================================================
Verwaltungsbereich fuer den Uni-Alltag - unabhaengig vom RAG/Lern-Layer: kein
LLM, kein Embedding, laeuft sofort und komplett offline. Zeigt auf einen Blick,
was heute anliegt (Vorlesungen + faellige Aufgaben + naechste Klausur), und
verwaltet Stundenplan + Aufgabenliste. Klausurtermine selbst bleiben auf der
Seite "Fortschritt" (dort mit Gewicht/ECTS fuer die Lern-Priorisierung).
"""
from __future__ import annotations

import sys
import pathlib
from datetime import date

_p = pathlib.Path(__file__).resolve()
for _anc in _p.parents:
    if (_anc / "ragapp").is_dir():
        sys.path.insert(0, str(_anc))
        break

import streamlit as st

from ragapp.ui._loading import page_boot, skeleton
page_boot("🗂️ Organisation", page_title="Organisation", icon="🗂️", layout="wide",
         accent="organisation")

from ragapp.ui._style import card

st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1150px;}
h1 {font-weight: 750; letter-spacing:-0.5px;}
</style>
""", unsafe_allow_html=True)

st.caption("Stundenplan, Aufgaben/Hausaufgaben und ein Wochen-Dashboard – "
           "organisatorisch, unabhängig von RAG/Chat. Komplett offline, ohne Modell.")

with skeleton("Organisation wird geladen ..."):
    import pandas as pd
    from ragapp import manifest, planner
    from ragapp.config import SUBJECT_LABELS

_WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
_today = date.today()
_today_wd = _today.weekday()


def _fach(code: "str | None") -> str:
    if not code:
        return "–"
    return SUBJECT_LABELS.get(code, code)


# --------------------------------------------------------------------------- #
# Fach-Farben (Stundenplan-Kacheln) - geteilte Logik, siehe ragapp/ui/_colors.py
# (auch vom Lernplan fuer Themen-Karten/Zeitleiste genutzt).
# --------------------------------------------------------------------------- #
from ragapp.ui._colors import PALETTE as _PALETTE
from ragapp.ui._colors import text_color_for as _text_color_for
from ragapp.ui._colors import subject_color as _subject_color


_PX_PER_HOUR = 56
_MIN_SPAN_HOURS = 4  # auch bei nur einem Termin ein sinnvoll grosses Raster


def _render_week_grid(slots: list, colors: dict, ordered_subjects: list, today_wd: int) -> str:
    """Baut das HTML/CSS fuer die Wochenansicht: die vertikale Position jedes
    Termins richtet sich nach der echten Uhrzeit (gleiche Uhrzeit = gleiche Hoehe,
    UNABHAENGIG vom Wochentag); der Zeitstrahl deckt nur die Spanne von der
    fruehesten bis zur spaetesten Vorlesung ab (auf volle Stunden gerundet)."""
    import html as _html

    def _mins(hhmm: str) -> int:
        h, m = (int(x) for x in hhmm.split(":")[:2])
        return h * 60 + m

    starts = [_mins(s["start_time"]) for s in slots]
    ends = [_mins(s["end_time"]) for s in slots]
    lo = (min(starts) // 60) * 60 if starts else 8 * 60
    hi = -(-max(ends) // 60) * 60 if ends else (8 + _MIN_SPAN_HOURS) * 60
    if hi - lo < _MIN_SPAN_HOURS * 60:
        hi = lo + _MIN_SPAN_HOURS * 60
    span = hi - lo
    total_h = round(span / 60 * _PX_PER_HOUR)

    def _y(m: int) -> float:
        return (m - lo) / span * total_h

    # Ueberlappende Termine am selben Tag nebeneinander statt uebereinander legen
    # (einfache Intervall-Faerbung: gleiche Spur, solange kein Zeitkonflikt).
    def _lanes(day_slots: list) -> list:
        lanes: list[list[dict]] = []
        for s in sorted(day_slots, key=lambda s: _mins(s["start_time"])):
            placed = False
            for lane in lanes:
                if _mins(lane[-1]["end_time"]) <= _mins(s["start_time"]):
                    lane.append(s)
                    placed = True
                    break
            if not placed:
                lanes.append([s])
        out = []
        for li, lane in enumerate(lanes):
            for s in lane:
                out.append((s, li, len(lanes)))
        return out

    hours = list(range(lo, hi + 1, 60))
    time_axis = "".join(
        f"<div class='rag-tt-hour' style='top:{_y(m):.1f}px'>{m // 60:02d}:00</div>"
        for m in hours)

    headers = []
    columns = []
    for wd in range(7):
        day_slots = [s for s in slots if int(s["weekday"]) == wd]
        gridlines = "".join(
            f"<div class='rag-tt-gridline' style='top:{_y(m):.1f}px'></div>" for m in hours)
        blocks = ""
        for s, lane, n_lanes in _lanes(day_slots):
            top, bottom = _y(_mins(s["start_time"])), _y(_mins(s["end_time"]))
            bg = _subject_color(s["subject"], colors, ordered_subjects)
            fg = _text_color_for(bg)
            w = 100 / n_lanes
            room = f"<div class='rag-tt-room'>{_html.escape(s.get('room') or '')}</div>" \
                if s.get("room") else ""
            blocks += (
                f"<div class='rag-tt-block' title='{_html.escape(_fach(s['subject']))} "
                f"{s['start_time']}–{s['end_time']}' style='top:{top:.1f}px; "
                f"height:{max(bottom - top, 16):.1f}px; left:{lane * w:.2f}%; "
                f"width:{w - 1.5:.2f}%; background:{bg}; color:{fg};'>"
                f"<div class='rag-tt-fach'>{_html.escape(_fach(s['subject']))}</div>"
                f"<div class='rag-tt-time'>{s['start_time']}–{s['end_time']}</div>"
                f"{room}</div>"
            )
        _today_cls = " rag-tt-today" if wd == today_wd else ""
        headers.append(f"<div class='rag-tt-header{_today_cls}'>{_WOCHENTAGE[wd][:2]}</div>")
        columns.append(
            f"<div class='rag-tt-daycol{_today_cls}' style='height:{total_h}px'>"
            f"{gridlines}{blocks}</div>"
        )

    return f"""
<style>
.rag-tt-wrap {{ overflow-x:auto; }}
.rag-tt-grid {{ display:grid; grid-template-columns: 54px repeat(7, minmax(90px, 1fr));
  column-gap:4px; font-family:system-ui,-apple-system,sans-serif; min-width:640px; }}
.rag-tt-corner {{ }}
.rag-tt-header {{ text-align:center; font-weight:650; font-size:13px; padding-bottom:6px;
  color:#475569; }}
.rag-tt-header.rag-tt-today {{ color:#2563eb; }}
.rag-tt-timeaxis {{ position:relative; font-size:11px; color:#94a3b8; }}
.rag-tt-hour {{ position:absolute; right:6px; transform:translateY(-50%); white-space:nowrap; }}
.rag-tt-daycol {{ position:relative; background:rgba(148,163,184,0.06);
  border-radius:6px; border:1px solid rgba(148,163,184,0.18); }}
.rag-tt-daycol.rag-tt-today {{ background:rgba(37,99,235,0.07);
  border-color:rgba(37,99,235,0.35); }}
.rag-tt-gridline {{ position:absolute; left:0; right:0; border-top:1px dashed
  rgba(148,163,184,0.3); }}
.rag-tt-block {{ position:absolute; border-radius:6px; padding:4px 6px; overflow:hidden;
  box-shadow:0 1px 3px rgba(0,0,0,0.18); line-height:1.25; }}
.rag-tt-fach {{ font-weight:700; font-size:12px; white-space:nowrap; overflow:hidden;
  text-overflow:ellipsis; }}
.rag-tt-time {{ font-size:10.5px; opacity:0.92; }}
.rag-tt-room {{ font-size:10.5px; opacity:0.85; }}
html.rag-dark .rag-tt-daycol {{ background:rgba(31,58,99,0.35); border-color:rgba(30,58,95,0.7); }}
html.rag-dark .rag-tt-header {{ color:#c7d6ea; }}
</style>
<div class="rag-tt-wrap"><div class="rag-tt-grid">
<div class="rag-tt-corner"></div>
{''.join(headers)}
<div class="rag-tt-timeaxis" style="height:{total_h}px">{time_axis}</div>
{''.join(columns)}
</div></div>
"""


_known_subjects = sorted(
    set(SUBJECT_LABELS.keys())
    | {d["subject"] for d in manifest.list_documents() if d["subject"]}
    | {t["subject"] for t in manifest.list_tasks() if t.get("subject")}
    | {s["subject"] for s in manifest.list_timetable() if s.get("subject")}
)

# --------------------------------------------------------------------------- #
# Wochen-Dashboard
# --------------------------------------------------------------------------- #
with card("heute"):
    st.subheader("📊 Heute im Blick")

    # Gemeinsame Grundlage mit dem "Heute"-Block auf der Startseite (siehe
    # planner.today_snapshot) - dieselbe Funktion, damit die Zahlen nie
    # auseinanderlaufen.
    _snap = planner.today_snapshot()
    _today_classes = _snap["today_classes"]
    _overdue = _snap["overdue_tasks"]
    _due_today = _snap["due_today_tasks"]
    _next_exam = _snap["next_exam"]
    _study_min_today = _snap["study_min_today"]
    _plan_blocks_today = _snap["plan_blocks_today"]
    _plan_min_today = _snap["plan_min_today"]
    _plan_done_today = _snap["plan_done_today"]

    # Zwei Reihen zu je drei Spalten statt sechs nebeneinander - bei sechs
    # Spalten wurde "Heute Vorlesungen" (und "Nächste Klausur: <Fach>" bei
    # langen Fachnamen) auf normaler Desktop-Breite abgeschnitten.
    d1, d2, d3 = st.columns(3)
    d1.metric("Heute Vorlesungen", len(_today_classes))
    d2.metric("Fällig heute", len(_due_today))
    d3.metric("Überfällig", len(_overdue))
    d4, d5, d6 = st.columns(3)
    d4.metric("Lernzeit heute", f"{_study_min_today} Min")
    d5.metric("Lernplan heute", f"{_plan_done_today}/{_plan_min_today} Min"
             if _plan_blocks_today else "–")
    if _next_exam:
        _dte = planner.days_to_exam(_next_exam["exam_date"])
        d6.metric(f"Nächste Klausur: {_fach(_next_exam['subject'])}", planner.humanize_days(_dte))
    else:
        d6.metric("Nächste Klausur", "–")

    if _today_classes:
        st.caption("**Heute:** " + " · ".join(
            f"{s['start_time']}–{s['end_time']} {_fach(s['subject'])}"
            + (f" ({s['room']})" if s.get("room") else "")
            for s in _today_classes))
    if _plan_blocks_today:
        st.caption("**Lernplan heute:** " + " · ".join(
            f"{'✅' if b['done'] else '⬜'} {b['section_title'] or 'Abschnitt'} "
            f"({b['plan_title']}, {b['planned_min']} Min)" for b in _plan_blocks_today))
    if _overdue:
        _txt = ", ".join(f"{t['title']} ({_fach(t.get('subject'))})" for t in _overdue[:6])
        if len(_overdue) > 6:
            _txt += f" … +{len(_overdue) - 6} weitere"
        st.warning(f"⚠️ Überfällig: {_txt}")

st.divider()

# --------------------------------------------------------------------------- #
# Stundenplan
# --------------------------------------------------------------------------- #
with card("stundenplan"):
    st.subheader("🗓️ Stundenplan")

    # key= haelt den Auf/Zu-Zustand fest - ohne key faellt der Expander sonst bei
    # JEDEM Rerun (auch nur durch die "Fach"-Auswahl DARIN) auf zugeklappt
    # zurueck, bevor der Rest des Formulars ausgefuellt ist (gleiches Muster wie
    # beim Ausspracheregeln-Expander in Audio-Overview behoben).
    with st.expander("➕ Neuen Termin hinzufügen", key="tt_add_expander"):
        tc1, tc2, tc3, tc4 = st.columns(4)
        with tc1:
            _tt_choice = st.selectbox("Fach", _known_subjects + ["(neues Fach …)"], key="tt_new_subject")
            _tt_subject = (st.text_input("Neues Fach", key="tt_new_subject_text").strip()
                           if _tt_choice == "(neues Fach …)" else _tt_choice)
        with tc2:
            _tt_wd_label = st.selectbox("Wochentag", _WOCHENTAGE, key="tt_new_wd")
        with tc3:
            _tt_start = st.time_input("Start", key="tt_new_start")
        with tc4:
            _tt_end = st.time_input("Ende", key="tt_new_end")
        _tt_room = st.text_input("Raum (optional)", key="tt_new_room")
        if st.button("➕ Hinzufügen", key="tt_add"):
            if not _tt_subject:
                st.error("Bitte ein Fach wählen oder eingeben.")
            elif _tt_end <= _tt_start:
                st.error("Ende muss nach Start liegen.")
            else:
                manifest.upsert_timetable_slot(
                    subject=_tt_subject, weekday=_WOCHENTAGE.index(_tt_wd_label),
                    start_time=_tt_start.strftime("%H:%M"), end_time=_tt_end.strftime("%H:%M"),
                    room=_tt_room.strip() or None)
                st.success("Termin hinzugefügt.")
                st.rerun()

    _slots = manifest.list_timetable()
    if not _slots:
        st.info("Noch kein Stundenplan angelegt.")
    else:
        _tt_subjects = sorted({s["subject"] for s in _slots if s.get("subject")})
        _tt_colors = manifest.subject_colors_map()

        with st.expander("🎨 Fach-Farben", key="tt_colors_expander"):
            st.caption("Jedes Fach hat automatisch eine Farbe; hier lässt sie sich anpassen.")
            _color_cols = st.columns(4)
            _new_colors: dict = {}
            for i, subj in enumerate(_tt_subjects):
                with _color_cols[i % 4]:
                    _cur = _subject_color(subj, _tt_colors, _tt_subjects)
                    _new_colors[subj] = st.color_picker(_fach(subj), value=_cur,
                                                        key=f"color_{subj}")
            if st.button("💾 Farben speichern", key="color_save"):
                for subj, col in _new_colors.items():
                    manifest.set_subject_color(subj, col)
                st.success("Farben gespeichert.")
                st.rerun()

        st.markdown(_render_week_grid(_slots, _tt_colors, _tt_subjects, _today_wd),
                   unsafe_allow_html=True)

        st.markdown("##### Bearbeiten / Löschen")
        _tt_orig = {s["slot_id"]: s for s in _slots}
        _tt_df = pd.DataFrame([{
            "🗑️": False, "Fach": s["subject"], "Wochentag": _WOCHENTAGE[int(s["weekday"])],
            "Start": s["start_time"], "Ende": s["end_time"], "Raum": s.get("room") or "",
            "_id": s["slot_id"],
        } for s in _slots])
        _tt_edited = st.data_editor(
            _tt_df, hide_index=True, use_container_width=True, key="tt_editor",
            column_config={
                "🗑️": st.column_config.CheckboxColumn(width="small"),
                "Wochentag": st.column_config.SelectboxColumn(options=_WOCHENTAGE),
                "_id": None,
            },
        )
        ttb1, ttb2 = st.columns(2)
        if ttb1.button("💾 Änderungen speichern", key="tt_save"):
            _n = 0
            for _, row in _tt_edited.iterrows():
                if row["_id"] not in _tt_orig or row["🗑️"]:
                    continue
                manifest.upsert_timetable_slot(
                    slot_id=row["_id"], subject=row["Fach"],
                    weekday=_WOCHENTAGE.index(row["Wochentag"]),
                    start_time=row["Start"], end_time=row["Ende"], room=row["Raum"] or None)
                _n += 1
            st.success(f"{_n} Termin(e) aktualisiert.")
            st.rerun()
        _tt_del = [row["_id"] for _, row in _tt_edited.iterrows() if row["🗑️"]]
        if ttb2.button(f"🗑️ Ausgewählte löschen ({len(_tt_del)})", disabled=not _tt_del, key="tt_del"):
            for sid in _tt_del:
                manifest.delete_timetable_slot(sid)
            st.success(f"{len(_tt_del)} Termin(e) gelöscht.")
            st.rerun()

st.divider()

# --------------------------------------------------------------------------- #
# Aufgaben & Hausaufgaben
# --------------------------------------------------------------------------- #
with card("aufgaben"):
    st.subheader("📝 Aufgaben & Hausaufgaben")

    with st.expander("➕ Neue Aufgabe hinzufügen", key="task_add_expander"):
        ac1, ac2, ac3 = st.columns(3)
        with ac1:
            _task_title = st.text_input("Titel", key="task_new_title")
        with ac2:
            _task_choice = st.selectbox("Fach (optional)", ["(kein Fach)"] + _known_subjects
                                        + ["(neues Fach …)"], key="task_new_subject")
            if _task_choice == "(neues Fach …)":
                _task_subject = st.text_input("Neues Fach", key="task_new_subject_text").strip() or None
            elif _task_choice == "(kein Fach)":
                _task_subject = None
            else:
                _task_subject = _task_choice
        with ac3:
            _task_has_due = st.checkbox("Frist setzen", value=True, key="task_new_has_due")
            _task_due = (st.date_input("Frist", value=_today, key="task_new_due")
                        if _task_has_due else None)
        _task_notiz = st.text_area("Notiz (optional)", key="task_new_notiz", height=68)
        if st.button("➕ Hinzufügen", key="task_add"):
            if not _task_title.strip():
                st.error("Bitte einen Titel eingeben.")
            else:
                manifest.upsert_task(
                    subject=_task_subject, title=_task_title,
                    due_date=_task_due.isoformat() if _task_due else None,
                    notiz=_task_notiz.strip() or None)
                st.success("Aufgabe hinzugefügt.")
                st.rerun()

    _task_filter = st.radio("Anzeige", ["Offen", "Alle", "Erledigt"], horizontal=True, key="task_filter")
    _all_tasks = manifest.list_tasks()
    if _task_filter == "Offen":
        _shown_tasks = [t for t in _all_tasks if not t["done"]]
    elif _task_filter == "Erledigt":
        _shown_tasks = [t for t in _all_tasks if t["done"]]
    else:
        _shown_tasks = _all_tasks


    def _task_status(t: dict) -> str:
        if t["done"]:
            return "✅ erledigt"
        return planner.humanize_days(planner.days_to_exam(t.get("due_date")))


    if not _shown_tasks:
        st.info("Keine Aufgaben in dieser Ansicht.")
    else:
        _task_orig = {t["task_id"]: t for t in _shown_tasks}
        _task_df = pd.DataFrame([{
            "Erledigt": bool(t["done"]), "Titel": t["title"], "Fach": t.get("subject") or "",
            "Frist": t.get("due_date") or "", "Status": _task_status(t),
            "Notiz": t.get("notiz") or "", "🗑️": False, "_id": t["task_id"],
        } for t in _shown_tasks])
        _task_edited = st.data_editor(
            _task_df, hide_index=True, use_container_width=True, key="task_editor",
            column_config={
                "Status": st.column_config.TextColumn(disabled=True),
                "Frist": st.column_config.TextColumn(help="ISO-Format JJJJ-MM-TT, leer = kein Termin"),
                "🗑️": st.column_config.CheckboxColumn(width="small"),
                "_id": None,
            },
        )
        tb1, tb2 = st.columns(2)
        if tb1.button("💾 Änderungen speichern", key="task_save"):
            _n = 0
            for _, row in _task_edited.iterrows():
                o = _task_orig.get(row["_id"])
                if o is None or row["🗑️"]:
                    continue
                nf = (row["Frist"] or "").strip() or None
                manifest.upsert_task(
                    task_id=row["_id"], subject=row["Fach"] or None, title=row["Titel"],
                    notiz=row["Notiz"] or None, due_date=nf, done=bool(row["Erledigt"]))
                _n += 1
            st.success(f"{_n} Aufgabe(n) aktualisiert.")
            st.rerun()
        _task_del = [row["_id"] for _, row in _task_edited.iterrows() if row["🗑️"]]
        if tb2.button(f"🗑️ Ausgewählte löschen ({len(_task_del)})", disabled=not _task_del, key="task_del"):
            for tid in _task_del:
                manifest.delete_task(tid)
            st.success(f"{len(_task_del)} Aufgabe(n) gelöscht.")
            st.rerun()

st.divider()

# --------------------------------------------------------------------------- #
# Kalender-Export
# --------------------------------------------------------------------------- #
with card("export"):
    st.subheader("📤 Kalender-Export")
    _ics = planner.organizer_to_ics()
    if _ics:
        st.download_button(
            "📅 Klausuren + Aufgaben + Stundenplan als Kalender (.ics)",
            data=_ics, file_name="organisation.ics", mime="text/calendar",
            help="In Google/Apple/Outlook-Kalender importieren. Der Stundenplan wird als "
                 "wöchentlich wiederkehrender Termin exportiert.")
    else:
        st.caption("Noch keine Termine für den Export vorhanden (Klausurtermin, Aufgaben-Frist "
                   "oder Stundenplan-Eintrag anlegen).")
