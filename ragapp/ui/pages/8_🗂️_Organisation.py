"""
RAG-Lernsystem: Seite „Kurse & Stundenplan" (Kurse, Termine, Aufgaben)
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
page_boot("🗂️ Kurse & Stundenplan", page_title="Kurse & Stundenplan", icon="🗂️", layout="wide",
         accent="organisation")

from ragapp.ui._style import card, delete_button, mark_tight_nums, sticky_expander

st.caption("Fächer, nächste Aktion, Stundenplan und Aufgaben – alles an einem Ort.")

with skeleton("Kurse & Stundenplan werden geladen …"):
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
        headers.append(
            f"<div class='rag-tt-header{_today_cls}'>{_WOCHENTAGE[wd][:2]}"
            + (" <span class='rag-tt-today-tag'>heute</span>" if wd == today_wd else "")
            + "</div>")
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
.rag-tt-header.rag-tt-today {{ color:#1d4ed8; }}
.rag-tt-timeaxis {{ position:relative; font-size:12px; }}
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


from ragapp import student_flow as _sf

_known_subjects = sorted(
    s for s in (
        set(SUBJECT_LABELS.keys())
        | {d["subject"] for d in manifest.list_documents() if d["subject"]}
        | {t["subject"] for t in manifest.list_tasks() if t.get("subject")}
        | {s["subject"] for s in manifest.list_timetable() if s.get("subject")}
        | {e["subject"] for e in manifest.list_exams() if e.get("subject")}
    )
    if s and not _sf.is_inbox_subject(s)
)

# --------------------------------------------------------------------------- #
# Kurs-Cockpit: ein Fach, ein Blick, eine nächste Aktion (C2)
# --------------------------------------------------------------------------- #
_kurs_faecher = list(dict.fromkeys(
    subj for subj in (
        list(manifest.study_subjects())
        + [e["subject"] for e in manifest.list_exams() if e.get("subject")]
        + [s["subject"] for s in manifest.list_timetable() if s.get("subject")]
        + [d["subject"] for d in manifest.list_documents() if d["subject"]]
    )
    if subj and not _sf.is_inbox_subject(subj)
    and not _sf.is_placeholder_subject(subj)
    and not _sf.is_fixture_subject(subj)
))
st.subheader("Kurse")
if not _kurs_faecher:
    from ragapp.ui._style import empty_state
    empty_state(
        "Noch keine Fächer. Importiere das Modulhandbuch oder lege Unterlagen an.",
        cta_label="Semester einrichten",
        page_key="semesterplan",
        icon="📚",
        key="org_empty_semester",
    )
else:
    _act_label = {
        "lernen": "Jetzt lernen",
        "planen": "Lernplan öffnen",
        "Unterlagen": "Unterlagen öffnen",
        "Prüfung": "Prüfung",
    }

    def _render_kurs(_subj: str, _ks: dict, *, quiet: bool = False) -> None:
        import html as _html
        with card(f"kurs_{_subj}"):
            st.markdown(
                f'<p class="rag-kurs-title">{_html.escape(_fach(_subj))}</p>',
                unsafe_allow_html=True)
            _items = []
            if _ks["days_to_exam"] is not None:
                _items.append(
                    (planner.humanize_days(_ks["days_to_exam"]), "Termin"))
            _items.extend([
                (str(_ks["doc_count"] or "–"), "Unterlagen"),
                ("–" if quiet or not _ks["doc_count"]
                 else f'{_ks["retention_pct"]} %', "Behalten"),
                (str(_ks["due_cards"] or "–"), "Fällig"),
            ])
            _cells = "".join(
                f'<span class="rag-kurs-metric"><b>{mark_tight_nums(_html.escape(str(_v)))}</b>'
                f'{_html.escape(_lab)}</span>'
                for _v, _lab in _items
            )
            st.markdown(f'<div class="rag-kurs-metrics">{_cells}</div>',
                        unsafe_allow_html=True)
            if not quiet:
                if _ks.get("coverage_pct") is not None:
                    st.caption(
                        f"Behalten {_ks['retention_pct']} % · "
                        f"Ziele {_ks['coverage_pct']} %")
                if _ks["weak_topics"]:
                    st.caption("Heute lohnt – Klick öffnet Karten zu dem Thema:")
                    _wcols = st.columns(min(3, len(_ks["weak_topics"][:3])))
                    for _wi, _w in enumerate(_ks["weak_topics"][:3]):
                        _wlabel = f'{_w["topic"] or "ohne Thema"} ({_w["mastery_pct"]} %)'
                        if _wcols[_wi].button(
                                _wlabel, key=f"org_weak_{_subj}_{_wi}",
                                use_container_width=True):
                            st.session_state["study_prefill"] = {
                                "source": "weak_topic", "limit": 16, "mode": "reveal",
                                "subject": _subj,
                                "topics": [_w["topic"]] if _w.get("topic") else [],
                            }
                            st.switch_page("pages/4_🎓_Lernen.py")
                from ragapp import coverage as _cov
                _cov_rows = _cov.coverage_for_subject(_subj)
                if _cov_rows:
                    st.caption("Abdeckung der Lernziele")
                    for _row in _cov_rows:
                        _act = _cov.coverage_start_action(_row)
                        _g1, _g2 = st.columns([3, 1])
                        _g1.write(f"· {_row['status']}: {_row['text'][:90]}")
                        if _act["kind"] and _g2.button(
                                _act["label"], key=f"cov_{_subj}_{_row['goal_id']}"):
                            if _act["kind"] == "dokument":
                                st.session_state["doc_folder"] = _subj
                                st.switch_page("pages/9_🗃️_Dokumentenmanager.py")
                            elif _act["kind"] == "lernset":
                                st.session_state["lernset_docs_prefill"] = _row.get("doc_ids") or []
                                st.switch_page("pages/4_🎓_Lernen.py")
                            elif _act["kind"] == "uebung":
                                st.session_state["practice_prefill"] = {
                                    "source": "coverage",
                                    "subject": _subj,
                                    "topic": _row["text"][:80],
                                    "doc_ids": _row.get("doc_ids") or [],
                                    "problem_ids": _row.get("problem_ids") or [],
                                }
                                st.switch_page("pages/13_🧮_Übungsaufgaben.py")
                            else:
                                st.session_state["study_prefill"] = {
                                    "source": "coverage", "limit": 16, "mode": "reveal",
                                    "subject": _subj,
                                    "card_ids": _row.get("card_ids") or [],
                                }
                                st.switch_page("pages/4_🎓_Lernen.py")
            _act = _ks["next_action"]
            if st.button(_act_label.get(_act, "Weiter"),
                         type="secondary" if quiet else "primary",
                         key=f"kurs_act_{_subj}", use_container_width=True):
                if _act == "lernen":
                    st.session_state["study_prefill"] = {
                        "source": "kurs", "limit": 16, "mode": "reveal",
                        "subject": _subj,
                    }
                    st.switch_page("pages/4_🎓_Lernen.py")
                elif _act == "planen":
                    _doc_ids = [
                        d["doc_id"] for d in manifest.list_documents()
                        if d["subject"] == _subj
                    ]
                    st.session_state["splan_prefill"] = {
                        "source": "kurs",
                        "subject": _subj, "doc_ids": _doc_ids,
                        "title": f"Lernplan {_fach(_subj)}",
                    }
                    st.switch_page("pages/11_📋_Lernplan.py")
                elif _act == "Unterlagen":
                    st.session_state["doc_folder"] = _subj
                    st.switch_page("pages/9_🗃️_Dokumentenmanager.py")
                else:
                    st.switch_page("pages/6_📝_Prüfung.py")

    _study_set = set(manifest.study_subjects())
    _kurs_aktiv, _kurs_stoff, _kurs_import = [], [], []
    for _subj in _kurs_faecher:
        _ks = _sf.course_snapshot(_subj)
        _bucket = _sf.course_cockpit_bucket(_ks, has_cards=_subj in _study_set)
        if _bucket == "active":
            _kurs_aktiv.append((_subj, _ks))
        elif _bucket == "stoff":
            _kurs_stoff.append((_subj, _ks))
        elif _bucket == "import":
            _kurs_import.append((_subj, _ks))
    for _subj, _ks in _kurs_aktiv:
        _render_kurs(_subj, _ks)
    if _kurs_stoff:
        with st.expander(
                f"Fächer mit Unterlagen, noch ohne Karten ({len(_kurs_stoff)})",
                expanded=False):
            st.caption("Unterlagen liegen schon da – als Nächstes Karten oder einen Lernplan.")
            for _subj, _ks in _kurs_stoff:
                _render_kurs(_subj, _ks, quiet=True)
    if _kurs_import:
        with st.expander(
                f"Weitere Fächer aus Import ({len(_kurs_import)})", expanded=False):
            st.caption("Noch ohne Unterlagen oder Karten – Namen aus dem Semesterimport.")
            for _subj, _ks in _kurs_import:
                _render_kurs(_subj, _ks, quiet=True)

# --------------------------------------------------------------------------- #
# Wochen-Dashboard
# --------------------------------------------------------------------------- #
with card("heute"):
    st.subheader("📊 Heute im Blick")

    _snap = planner.today_snapshot()
    _overdue = _snap["overdue_tasks"]
    _due_today = _snap["due_today_tasks"]
    _next_exam = _snap["next_exam"]
    _study_min_today = _snap["study_min_today"]
    _plan_blocks_today = _snap["plan_blocks_today"]
    _plan_min_today = _snap["plan_min_today"]
    _plan_done_today = _snap["plan_done_today"]

    d1, d2, d3 = st.columns(3)
    d1.metric("Karten fällig", _snap.get("due_cards") or 0,
              help="Fällige Karteikarten (Tageskontingent neuer Karten eingerechnet).")
    d2.metric("Fällig heute", len(_due_today))
    d3.metric("Überfällig", len(_overdue))
    d4, d5, d6 = st.columns(3)
    d4.metric("Lernzeit heute", f"{_study_min_today} Min")
    d5.metric("Lernplan heute", f"{_plan_done_today}/{_plan_min_today} Min"
             if _plan_blocks_today else "–")
    if _next_exam:
        _dte = planner.days_to_exam(_next_exam["exam_date"])
        d6.metric(f"Termin: {_fach(_next_exam['subject'])}", planner.humanize_days(_dte))
    else:
        _tp = _snap.get("top_priority") or {}
        d6.metric("Heute lohnt", _fach(_tp["subject"]) if _tp.get("subject") else "–")

    with st.expander("Klausurtermine", expanded=not manifest.list_exams()):
        _exams_now = manifest.list_exams()
        if _exams_now:
            for _ex in _exams_now:
                _title = _ex.get("notiz") or _fach(_ex["subject"])
                st.write(f"• {_title}: {_ex.get('exam_date') or 'kein Datum'}"
                         + (f" · {_ex['ects']:g} ECTS" if _ex.get("ects") else ""))
        else:
            st.caption("Noch keine Klausurtermine.")
        st.caption("Termine setzt und ändert du unter **Fortschritt** – hier nur die Übersicht.")
        if st.button("Auf Fortschritt bearbeiten", key="orga_exam_goto",
                     use_container_width=True):
            st.switch_page("pages/5_📈_Fortschritt.py")

    if _overdue:
        _txt = ", ".join(f"{t['title']} ({_fach(t.get('subject'))})" for t in _overdue[:6])
        if len(_overdue) > 6:
            _txt += f" … +{len(_overdue) - 6} weitere"
        st.warning(f"⚠️ Überfällig: {_txt}")

    st.caption("Der volle Tagesüberblick mit Missionen, Sprint und Vorlesung bleibt auf Home.")
    from ragapp.ui._style import PAGE_REGISTRY as _PR_ORG
    _lernen_t = next(p["target"] for p in _PR_ORG if p["key"] == "lernen")
    _h1, _h2 = st.columns(2)
    if _h1.button("Auf Home öffnen", key="org_to_home", use_container_width=True):
        st.switch_page("🏠_Home.py")
    if (_snap.get("due_cards") or 0) > 0:
        if _h2.button("▶ Jetzt lernen", type="primary", key="org_jetzt_lernen",
                      use_container_width=True):
            st.switch_page(_lernen_t)

st.divider()

# --------------------------------------------------------------------------- #
# Stundenplan
# --------------------------------------------------------------------------- #
with card("stundenplan"):
    st.subheader("🗓️ Stundenplan")

    # sticky_expander haelt Auf/Zu in session_state (Streamlit 1.59 braucht
    # on_change="rerun", sonst klappt das Formular beim Fach-Wechsel zu).
    with sticky_expander("➕ Neuen Termin hinzufügen", key="tt_add_expander"):
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

        with sticky_expander("🎨 Fach-Farben", key="tt_colors_expander"):
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
        if delete_button(f"🗑️ Ausgewählte löschen ({len(_tt_del)})",
                         token="orga:tt",
                         body=f"**{len(_tt_del)}** Stundenplan-Termin(e) wirklich löschen?",
                         key="tt_del", disabled=not _tt_del):
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

    with sticky_expander("➕ Neue Aufgabe hinzufügen", key="task_add_expander"):
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
        if delete_button(f"🗑️ Ausgewählte löschen ({len(_task_del)})",
                         token="orga:tasks",
                         body=f"**{len(_task_del)}** Aufgabe(n) wirklich löschen?",
                         key="task_del", disabled=not _task_del):
            for tid in _task_del:
                manifest.delete_task(tid)
            st.success(f"{len(_task_del)} Aufgabe(n) gelöscht.")
            st.rerun()

st.divider()

# --------------------------------------------------------------------------- #
# Kalender-Import (.ics) - z. B. WebUntis-/Schulverwaltungs-Export, oder ein
# abonnierter Uni-/Google-/Outlook-Kalender. Bewusst datei-basiert statt einer
# Live-API-Anbindung (kein OAuth/Konto noetig, bleibt offline-tauglich - siehe
# ragapp/ics_import.py-Modul-Docstring). Vorschau-vor-Import wie beim
# KI-gestuetzten Semesterplan-Import: NICHTS landet ungefragt in der DB.
# --------------------------------------------------------------------------- #
with card("ics_import"):
    st.subheader("📥 Stundenplan & Termine importieren (.ics)")
    # st.success() direkt vor st.rerun() wird nie sichtbar (der Rerun verwirft
    # die Meldung, bevor der Browser sie zeigen konnte - derselbe Bug wie bei
    # "Karten & Fragen verwalten" in Lernen.py) - deshalb ueber session_state
    # ins naechste Laufen retten (Muster "_dl_msg" aus Einstellungen.py).
    _ics_flash = st.session_state.pop("_ics_flash", None)
    if _ics_flash:
        st.success(_ics_flash)
    st.caption('Datei aus WebUntis, DSB Mobile, Outlook oder Google Kalender exportieren '
               '(meist unter „Exportieren"/„Kalender abonnieren" zu finden) und hier '
               'hochladen. Wöchentlich wiederkehrende Stunden landen im Stundenplan, '
               'einmalige Termine als Aufgabe.')
    _ics_file = st.file_uploader("Kalenderdatei (.ics)", type=["ics"], key="ics_upload")
    if _ics_file is not None:
        try:
            from ragapp.ics_import import parse_ics
            _ics_parsed = parse_ics(_ics_file.getvalue())
        except Exception as _exc:  # noqa: BLE001
            _ics_parsed = None
            st.error(f"Konnte die Datei nicht lesen ({_exc}). Ist es eine gültige .ics-Datei?")
        if _ics_parsed is not None:
            _n_tt, _n_tasks = len(_ics_parsed["timetable"]), len(_ics_parsed["tasks"])
            if not _n_tt and not _n_tasks:
                st.info("Keine Termine in dieser Datei gefunden.")
            else:
                st.success(f"Gefunden: {_n_tt} wöchentliche Stunde(n), {_n_tasks} Termin(e)/Aufgabe(n).")
                _sel_tt, _sel_tasks = [], []
                if _n_tt:
                    st.markdown("**🗓️ Als Stundenplan übernehmen**")
                    for i, row in enumerate(_ics_parsed["timetable"]):
                        _lbl = (f"{row['subject']} · {_WOCHENTAGE[row['weekday']]} "
                               f"{row['start_time']}–{row['end_time']}"
                               + (f" · {row['room']}" if row.get("room") else ""))
                        if st.checkbox(_lbl, value=True, key=f"ics_tt_{i}"):
                            _sel_tt.append(row)
                if _n_tasks:
                    st.markdown("**📝 Als Aufgabe übernehmen**")
                    for i, row in enumerate(_ics_parsed["tasks"]):
                        _lbl = f"{row['title']}" + (f" · fällig {row['due_date']}" if row.get("due_date") else "")
                        if st.checkbox(_lbl, value=True, key=f"ics_task_{i}"):
                            _sel_tasks.append(row)
                if st.button("📥 Auswahl importieren", key="ics_import_go",
                            disabled=not _sel_tt and not _sel_tasks):
                    for row in _sel_tt:
                        manifest.upsert_timetable_slot(
                            subject=row["subject"], weekday=row["weekday"],
                            start_time=row["start_time"], end_time=row["end_time"],
                            room=row.get("room"))
                    for row in _sel_tasks:
                        manifest.upsert_task(title=row["title"], due_date=row.get("due_date"),
                                            notiz=row.get("notiz"))
                    st.session_state["_ics_flash"] = (
                        f"{len(_sel_tt)} Stundenplan-Eintrag/Einträge, "
                        f"{len(_sel_tasks)} Aufgabe(n) importiert.")
                    st.rerun()

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
