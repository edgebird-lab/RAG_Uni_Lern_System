"""
RAG-Lernsystem: Seite „Lernplan" (KI-Gliederung + realistischer Zeitplan)
============================================================================
Wählst Dokument(e) + Zeitbudget → die KI gliedert den Stoff, du kannst die
Gliederung anpassen → das System rechnet einen ehrlichen, auf Tage verteilten
Plan in Pomodoro-Blöcken (siehe ragapp/study_plan.py, docs/LERNPLAN_FORSCHUNG.md
für die wissenschaftliche Herleitung der Zeitschätzung).
"""
from __future__ import annotations

import sys
import pathlib
from datetime import date, timedelta

_p = pathlib.Path(__file__).resolve()
for _anc in _p.parents:
    if (_anc / "ragapp").is_dir():
        sys.path.insert(0, str(_anc))
        break

import streamlit as st

from ragapp.ui._loading import page_boot, skeleton
page_boot("📋 Lernplan", page_title="Lernplan", icon="📋", layout="wide", accent="lernplan")

from ragapp.ui._style import card, delete_button

st.markdown("""
<style>
.splan-badge {display:inline-block; padding:2px 12px; border-radius:999px;
  font-size:.78rem; font-weight:650; letter-spacing:.2px;}
.splan-topic-card {border-radius:10px; padding:10px 12px; margin-bottom:8px;}
.splan-topic-title {font-weight:700; font-size:.92rem; margin-bottom:2px;}
.splan-topic-meta {font-size:.78rem;}
.splan-tl-wrap {overflow-x:auto; padding:6px 2px 20px 2px;}
.splan-tl-row {display:flex; gap:4px; align-items:flex-end; height:56px; min-width:min-content;}
.splan-tl-seg {position:relative; flex:0 0 26px; height:100%; background:rgba(148,163,184,.16);
  border-radius:5px; overflow:hidden; display:flex; align-items:flex-end;}
.splan-tl-seg.splan-tl-today {box-shadow:0 0 0 2px #2563eb;}
.splan-tl-fill {width:100%;}
.splan-tl-label {position:absolute; bottom:-18px; left:0; right:0; text-align:center;
  font-size:12px; white-space:nowrap;}
html.rag-dark .splan-tl-seg {background:rgba(148,163,184,.2);}
.splan-statebar {display:flex; gap:1px; height:6px; border-radius:3px; overflow:hidden;
  margin:2px 0 6px 0; background:rgba(148,163,184,.25);}
.splan-steps {display:flex; flex-wrap:wrap; gap:8px; margin:4px 0 10px 0;}
.splan-step {flex:1 1 150px; min-width:140px; border-radius:10px; padding:8px 10px;
  background:rgba(148,163,184,.10); border:1px solid rgba(148,163,184,.30);}
.splan-step-title {font-weight:700; font-size:.88rem;}
.splan-step-title .splan-step-n {display:inline-block; width:1.35em; height:1.35em; line-height:1.35em;
  text-align:center; border-radius:50%; margin-right:6px; font-size:.78rem;
  background:rgba(148,163,184,.35);}
.splan-step-sub {font-size:.76rem; opacity:.85; margin-top:1px;}
.splan-step-done {border-color:#16a34a; background:rgba(22,163,74,.10);}
.splan-step-done .splan-step-n {background:#16a34a; color:#fff;}
.splan-step-next {border-color:#2563eb; box-shadow:0 0 0 2px rgba(37,99,235,.25);}
.splan-step-next .splan-step-n {background:#2563eb; color:#fff;}
.splan-step-warn {border-color:#f59e0b; background:rgba(245,158,11,.12);}
.splan-step-warn .splan-step-n {background:#f59e0b; color:#fff;}
/* Laufender Hintergrundauftrag: bleibt beim Scrollen sichtbar. Sticky greift nur am
   AEUSSERSTEN Wrapper des Fragments (direktes Kind des Seitencontainers) - die Leiste selbst hat
   in ihrem Eltern-Element keinen Spielraum. */
.stMainBlockContainer > div[data-testid="stVerticalBlock"] >
  div[data-testid="stLayoutWrapper"]:has(.st-key-card_splan_jobbar) {
  position:sticky; top:4rem; z-index:90;}
</style>
""", unsafe_allow_html=True)

st.caption("Themen aus deinen Unterlagen auf Tage verteilen – mit Zeitbudget "
           "und Ruhetagen, ohne den bisherigen Fortschritt zu verlieren.")

with skeleton("Lernplan wird geladen …"):
    import html as _html
    import re as _re
    import pandas as pd
    from ragapp import card_quality, jobs, manifest, study_plan, planner, plan_cards
    from ragapp.config import SUBJECT_LABELS, settings
    from ragapp.ui._colors import PALETTE, text_color_for, subject_color


def _fach(code: "str | None") -> str:
    return SUBJECT_LABELS.get(code, code) if code else "–"


def _fmt_min(m: int) -> str:
    m = int(m)
    if m < 60:
        return f"{m} Min"
    h, r = divmod(m, 60)
    return f"{h} Std {r} Min" if r else f"{h} Std"


def _plan_label(p: dict) -> str:
    return f"{p['title']}  ·  {_fach(p['subject'])}  ·  {p['status']}"


_TF_SOURCE_TXT = {
    "subject": "aus deinen echten Pomodoro-Zeiten für dieses Fach kalibriert",
    "global": "aus deinen echten Pomodoro-Zeiten (alle Fächer) kalibriert",
    "default": "Standardwert (noch zu wenige echte Zeitmessungen)",
}


def _time_factor_caption(subject: "str | None") -> str:
    _tf = study_plan.time_factor_info(subject)
    return (f"Zeit-Korrekturfaktor: **{_tf['factor']:.2f}×** "
           f"({_TF_SOURCE_TXT.get(_tf['source'], 'Standardwert')}, "
           "einstellbar unter ⚙️ Einstellungen → 📋 Lernplan).")


_STATUS_META = {
    "draft": ("📝 Entwurf", "#94a3b8"),
    "active": ("🟢 Aktiv", "#2563eb"),
    "done": ("✅ Abgeschlossen", "#16a34a"),
}


def _status_badge(status: str) -> str:
    label, bg = _STATUS_META.get(status, (status, "#94a3b8"))
    return (f"<span class='splan-badge' style='background:{bg};"
           f"color:{text_color_for(bg)};'>{label}</span>")


_all_docs = [dict(d) for d in manifest.list_documents()
            if d["use_rag"] and d["num_chunks"] > 0]
_subjects_with_docs = sorted({d["subject"] for d in _all_docs if d["subject"]})
_plan_colors = manifest.subject_colors_map()
_weekday_names = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
                  "Freitag", "Samstag", "Sonntag"]

# --------------------------------------------------------------------------- #
# Plan-Auswahl
# --------------------------------------------------------------------------- #
_plans_all = manifest.list_study_plans()

with card("planwahl"):
    st.subheader("📋 Deine Lernpläne")
    c1, c2 = st.columns([3, 1])
    with c2:
        st.write("")
        _show_done = st.checkbox("✅ Abgeschlossene anzeigen", key="splan_show_done")

    _plans = _plans_all if _show_done else [p for p in _plans_all if p["status"] != "done"]
    _plan_by_id = {p["plan_id"]: p for p in _plans}
    _n_hidden = len(_plans_all) - len(_plans)


    def _fmt_plan_option(pid: "str | None") -> str:
        if pid is None:
            return "➕ Neuer Plan"
        p = _plan_by_id.get(pid)
        return _plan_label(p) if p else "(gelöscht)"


    # Die Auswahl haengt am STABILEN plan_id (nicht an einem Text-Label, das sich mit
    # Titel/Status aendert) - sonst waere die Auswahl z. B. nach einem automatischen
    # Statuswechsel active -> done (siehe sync_plan_status) ploetzlich ungueltig.
    if "_splan_pending_choice" in st.session_state:
        # Widget-eigene session_state-Keys duerfen NICHT gesetzt werden, nachdem das
        # Widget in diesem Lauf schon gerendert wurde - daher der "pending"-Umweg,
        # angewendet HIER, VOR der Instanziierung (das ist erlaubt).
        st.session_state["splan_choice"] = st.session_state.pop("_splan_pending_choice")
    elif st.session_state.get("splan_choice") not in ([None] + list(_plan_by_id.keys())):
        # Der zuletzt gewaehlte Plan ist nicht mehr in der (ggf. gefilterten) Liste -
        # z. B. gerade abgeschlossen und "Abgeschlossene anzeigen" ist aus. Ohne diesen
        # Reset wuerde die Selectbox unten mit einem ungueltigen Wert abstuerzen.
        st.session_state["splan_choice"] = None

    with c1:
        _active_plan_id = st.selectbox(
            "Plan wählen", [None] + list(_plan_by_id.keys()),
            format_func=_fmt_plan_option, key="splan_choice")
    if _n_hidden:
        st.caption(f"{_n_hidden} abgeschlossene(r) Plan/Pläne ausgeblendet.")

# --------------------------------------------------------------------------- #
# Cross-Plan-Uebersicht: andere laufende Plaene auf einen Blick, ohne jeden
# einzeln anklicken zu muessen (praktisch beim Jonglieren mehrerer Faecher).
# --------------------------------------------------------------------------- #
_other_plans = [p for p in _plans if p["plan_id"] != _active_plan_id and p["status"] == "active"]
if _other_plans:
    with st.expander(f"📚 Weitere laufende Pläne ({len(_other_plans)})"):
        for _i in range(0, len(_other_plans), 3):
            _row_plans = _other_plans[_i:_i + 3]
            _row_cols = st.columns(3)
            for _col, _p in zip(_row_cols, _row_plans):
                with _col, st.container(border=True):
                    _p_blocks = manifest.list_plan_blocks(_p["plan_id"])
                    _p_total = sum(b["planned_min"] for b in _p_blocks)
                    _p_done = sum(b["planned_min"] for b in _p_blocks if b["done"])
                    _p_color = subject_color(_p["subject"], _plan_colors, _subjects_with_docs)
                    st.markdown(
                        f"<div style='font-weight:700;color:{_p_color}'>"
                        f"{_html.escape(_p['title'])}</div>"
                        f"<div style='font-size:.8rem;opacity:.75'>{_fach(_p['subject'])}</div>",
                        unsafe_allow_html=True)
                    st.progress(
                        _p_done / _p_total if _p_total else 0.0,
                        text=(f"{_fmt_min(_p_done)} / {_fmt_min(_p_total)}"
                             if _p_total else "Noch kein Zeitplan"))
                    if st.button("Öffnen", key=f"splan_open_{_p['plan_id']}",
                                use_container_width=True):
                        st.session_state["_splan_pending_choice"] = _p["plan_id"]
                        st.rerun()

# --------------------------------------------------------------------------- #
# Neuer Plan
# --------------------------------------------------------------------------- #
if _active_plan_id is None:
    if not _subjects_with_docs:
        from ragapp.ui._style import empty_state, page_title as _pt
        empty_state(
            "Noch keine indexierten Dokumente vorhanden.",
            cta_label=f"Zu {_pt('dokumente')}",
            page_key="dokumente",
            icon="📥",
            key="lernplan_empty_dokumente",
        )
        st.stop()

    # Vorbelegung aus "Dauerpatzer -> Fokus-Lernplan" (Fortschritt-Seite). Muss VOR
    # den betroffenen Widgets (Fach/Titel/Dokumente) gesetzt werden - siehe die
    # gleiche Regel beim Pomodoro-Sprung auf der Lernzeit-Seite.
    _plan_prefill = st.session_state.pop("splan_prefill", None)
    if _plan_prefill and _plan_prefill.get("subject") in _subjects_with_docs:
        st.session_state["splan_new_subject"] = _plan_prefill["subject"]
        st.session_state["splan_new_title"] = (
            _plan_prefill.get("title") or f"Lernplan {_fach(_plan_prefill['subject'])}")
        st.session_state["_splan_title_for_subject"] = _plan_prefill["subject"]
        st.session_state["_splan_prefill_doc_ids"] = _plan_prefill.get("doc_ids") or []
        _n_docs = len(_plan_prefill.get("doc_ids") or [])
        if _plan_prefill.get("source") == "kurs":
            st.info(f"📋 Vorbelegt aus dem Kurs: {_n_docs} Dokument(e) ausgewählt.")
        else:
            st.info(f"📋 Vorbelegt aus den Dauerpatzern: "
                   f"{_n_docs} Dokument(e) ausgewählt.")
    elif _plan_prefill and _plan_prefill.get("subject"):
        st.warning(
            f"Keine indexierten Unterlagen für {_fach(_plan_prefill['subject'])} – "
            "zuerst unter Dokumente einlesen, dann den Lernplan anlegen.")

    st.markdown("##### Neuen Lernplan anlegen")
    nc1, nc2 = st.columns(2)
    with nc1:
        _new_subject = st.selectbox("Fach", _subjects_with_docs, format_func=_fach,
                                    key="splan_new_subject")
    with nc2:
        # Titelvorschlag reaktiv an die Fach-Auswahl anpassen: 'value=' greift bei
        # Streamlit nur beim ALLERERSTEN Rendern, ein Fach-Wechsel liesse den Titel
        # sonst stehen. Daher VOR der Instanziierung zuruecksetzen, wenn sich das
        # Fach seit dem letzten Durchlauf geaendert hat (das ist erlaubt).
        if st.session_state.get("_splan_title_for_subject") != _new_subject:
            st.session_state["splan_new_title"] = f"Lernplan {_fach(_new_subject)}"
            st.session_state["_splan_title_for_subject"] = _new_subject
        _new_title = st.text_input("Titel", key="splan_new_title")

    _subj_docs = {d["filename"]: d["doc_id"] for d in _all_docs if d["subject"] == _new_subject}
    _prefill_doc_ids = set(st.session_state.pop("_splan_prefill_doc_ids", []))
    if _prefill_doc_ids:
        st.session_state["splan_new_docs"] = [n for n, did in _subj_docs.items()
                                              if did in _prefill_doc_ids]
    _new_doc_names = st.multiselect("Dokument(e)", list(_subj_docs.keys()),
                                    key="splan_new_docs", placeholder="Auswählen …")

    tc1, tc2, tc3 = st.columns(3)
    with tc1:
        _new_daily = st.number_input("Verfügbare Zeit/Tag (Min)", min_value=15, max_value=600,
                                     value=45, step=15, key="splan_new_daily")
        st.caption(f"Wird auf max. {settings.PLAN_MAX_DAILY_FOCUS_MIN} Min gedeckelt "
                   "(nachhaltige Tagesobergrenze, siehe Forschung).")
    with tc2:
        from ragapp.student_flow import default_plan_deadline
        _exam_dl = default_plan_deadline(_new_subject)
        _has_deadline = st.checkbox(
            "Zieldatum setzen", value=bool(_exam_dl),
            key="splan_new_has_deadline",
            help="Nur wenn du selbst einen Horizont willst. Ohne Datum bleibt der Plan offen.")
    with tc3:
        _dl_guess = study_plan.parse_iso_date(_exam_dl) or date.today()
        _new_deadline = (st.date_input("Zieldatum", value=_dl_guess,
                                       key="splan_new_deadline") if _has_deadline else None)
        st.caption("Standard: Klausurdatum des Fachs, sonst keines.")
    _new_rest_days = st.multiselect(
        "Ruhetage",
        options=list(range(7)),
        default=list(settings.PLAN_REST_WEEKDAYS),
        format_func=lambda i: _weekday_names[i],
        key="splan_new_rest_days",
        help="Gilt nur für diesen Lernplan. Die App plant dort keine Blöcke ein.",
    )

    _new_model_choice = st.radio(
        "Modell für die Gliederung", ["🎯 Gründlich (langsamer)", "⚡ Schnell (gröber)"],
        horizontal=True, key="splan_new_model")
    _new_model = (settings.LLM_MODEL_FAST if "Schnell" in _new_model_choice else None)
    if _new_doc_names:
        _eta = study_plan.estimate_outline_eta_seconds(
            [_subj_docs[n] for n in _new_doc_names], model=_new_model)
        _eta_txt = f"~{_eta // 60} Min" if _eta >= 90 else f"~{_eta} Sek."
        _eta_hint = (" – mit „Schnell“ oft deutlich weniger" if _new_model is None else "")
        st.caption(f"Geschätzte Wartezeit: {_eta_txt} (grober Richtwert, hängt stark "
                   f"von deiner Hardware ab{_eta_hint}).")
        st.caption(_time_factor_caption(_new_subject))

    if st.button("🧠 Gliederung erzeugen", type="primary", disabled=not _new_doc_names):
        from ragapp.ui._progress import LlmWait
        doc_ids = [_subj_docs[n] for n in _new_doc_names]
        with LlmWait("Suche in den Unterlagen …") as wait:
            wait.set("Formuliere die Gliederung …")
            try:
                outline, _outline_warning = study_plan.generate_outline(
                    doc_ids, _new_subject, model=_new_model)
            except study_plan.OutlineError as exc:
                wait.done("Nicht geklappt", ok=False)
                st.error(str(exc))
                st.stop()
            wait.done()
        pid = manifest.create_study_plan(
            title=_new_title or f"Lernplan {_fach(_new_subject)}", subject=_new_subject,
            doc_ids=doc_ids, deadline=_new_deadline.isoformat() if _new_deadline else None,
            daily_minutes=int(_new_daily),
            rest_weekdays=sorted(_new_rest_days))
        manifest.replace_plan_sections(pid, outline)
        if _outline_warning:
            st.session_state["_splan_gen_warning"] = _outline_warning
        else:
            st.success(f"Gliederung mit {len(outline)} Themen erzeugt.")
        # Auswahl auf den neuen Plan setzen - ueber den "pending"-Umweg, da die
        # Selectbox in diesem Lauf schon gerendert wurde (siehe Kommentar oben).
        st.session_state["_splan_pending_choice"] = pid
        st.rerun()
    st.stop()

# --------------------------------------------------------------------------- #
# Bestehenden Plan anzeigen/bearbeiten
# --------------------------------------------------------------------------- #
_plan = manifest.get_study_plan(_active_plan_id)
if _plan is None:
    st.error("Plan nicht gefunden.")
    st.stop()

# Einmal geladen, im Rest der Seite wiederverwendet (Header-Kennzahlen, Themen-
# Kacheln, Zeitplan) - Einstellungen/Gliederung aendern sich nur ueber Buttons,
# die ohnehin ``st.rerun()`` ausloesen, daher unproblematisch.
_sections = manifest.list_plan_sections(_active_plan_id)
_blocks = manifest.list_plan_blocks(_active_plan_id)
_plan_color = subject_color(_plan["subject"], _plan_colors, _subjects_with_docs)
_plan_rest_days = (
    _plan.get("rest_weekdays")
    if _plan.get("rest_weekdays") is not None
    else settings.PLAN_REST_WEEKDAYS
)

# Einmal berechnet und von Schrittleiste, Kacheln und Zeitplan gemeinsam genutzt:
# Kartenstand je Thema, Live-Vorschau des Zeitplans (mit dem aktuell GESPEICHERTEN Stand),
# "passt der gespeicherte Zeitplan noch zur Gliederung?" und der laufende Hintergrundauftrag.
_unit_stats = plan_cards.plan_unit_stats(_plan, _sections) if _sections else {}
_preview = study_plan.build_schedule(
    [{"section_id": s["section_id"], "est_minutes": s["est_minutes"]} for s in _sections],
    daily_minutes=_plan["daily_minutes"], deadline=_plan.get("deadline"),
    subject=_plan["subject"], rest_weekdays=set(_plan_rest_days))
_stale = study_plan.plan_staleness(
    _sections, _blocks, allow_shortfall=_preview["shortfall_minutes"] > 0)
_job = jobs.get(plan_cards.job_key(_active_plan_id))
_job_running = _job is not None and _job.status == jobs.RUNNING
_today_str = date.today().isoformat()

st.divider()
with card("kopf"):
    hh1, hh2 = st.columns([3, 1])
    with hh1:
        st.markdown(
            f"<h3 style='margin-bottom:0;border-left:5px solid {_plan_color};"
            f"padding-left:10px;'>{_html.escape(_plan['title'])}</h3>",
            unsafe_allow_html=True)
        st.caption(_fach(_plan["subject"]))
    with hh2:
        st.markdown(f"<div style='text-align:right;padding-top:10px'>"
                   f"{_status_badge(_plan['status'])}</div>", unsafe_allow_html=True)

    # Kennzahlen-Kopfzeile: der aktuelle Stand auf einen Blick, ohne erst runter-
    # scrollen zu muessen.
    _total_planned_all = sum(b["planned_min"] for b in _blocks)
    _done_planned_all = sum(b["planned_min"] for b in _blocks if b["done"])
    _dl_date = study_plan.parse_iso_date(_plan.get("deadline"))
    _days_left = (_dl_date - date.today()).days if _dl_date else None

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Themen", len(_sections))
    m2.metric("Lernzeit gesamt", _fmt_min(_total_planned_all) if _total_planned_all else "–")
    m3.metric("Erledigt", (f"{round(100 * _done_planned_all / _total_planned_all)} %"
                           if _total_planned_all else "–"))
    m4.metric("Bis Zieldatum", (f"{_days_left} Tag(e)" if _days_left is not None else "offen"))

    # Rueckstand: unerledigte Bloecke mit Datum VOR heute - vorher zeigte der
    # naechste Block einfach sein rohes (vergangenes) Datum an, ohne dass
    # sichtbar wurde, dass der Plan bereits hinterherhinkt (siehe UX-Analyse:
    # ein verpasster Tag verschwand so unbemerkt aus dem Blick).
    _today_iso_plan = date.today().isoformat()
    _overdue_blocks = manifest.list_overdue_plan_blocks(_today_iso_plan, plan_id=_active_plan_id)
    _repair_now = study_plan.repair_overdue_blocks(_active_plan_id, apply=False)
    if _overdue_blocks or _repair_now["moves"] or _repair_now["shortfall_minutes"]:
        _overdue_min = sum(b["planned_min"] for b in _overdue_blocks)
        oc1, oc2 = st.columns([3, 1])
        if _overdue_blocks:
            oc1.warning(f"⚠️ **{len(_overdue_blocks)} Block(e) im Rückstand** "
                       f"({_fmt_min(_overdue_min)}) – ältester: {_overdue_blocks[0]['planned_date']}")
        else:
            oc1.warning(
                "⚠️ Geplante Blöcke liegen auf einem neu gewählten Ruhetag.")
        if oc2.button("🔧 Plan reparieren", key=f"splan_catchup_{_active_plan_id}",
                     use_container_width=True):
            st.session_state[f"_splan_repair_preview_{_active_plan_id}"] = True
        if st.session_state.get(f"_splan_repair_preview_{_active_plan_id}"):
            _repair = study_plan.repair_overdue_blocks(_active_plan_id, apply=False)
            if _repair["moves"]:
                _by_day: dict[str, int] = {}
                for _move in _repair["moves"]:
                    _by_day[_move["to_date"]] = (
                        _by_day.get(_move["to_date"], 0) + _move["minutes"])
                st.caption("Vorschau: " + " · ".join(
                    f"{_day}: {_fmt_min(_mins)}" for _day, _mins in _by_day.items()))
            if _repair["shortfall_minutes"]:
                st.warning(
                    f"{_fmt_min(_repair['shortfall_minutes'])} passen bis zum Horizont "
                    "nicht in die Lastgrenze und bleiben als Rückstand sichtbar.")
            _rp1, _rp2 = st.columns(2)
            if _rp1.button(
                    "Reparatur anwenden", type="primary",
                    disabled=not _repair["moves"],
                    key=f"splan_repair_apply_{_active_plan_id}"):
                study_plan.repair_overdue_blocks(_active_plan_id, apply=True)
                st.session_state.pop(f"_splan_repair_preview_{_active_plan_id}", None)
                st.rerun()
            if _rp2.button("Abbrechen", key=f"splan_repair_cancel_{_active_plan_id}"):
                st.session_state.pop(f"_splan_repair_preview_{_active_plan_id}", None)
                st.rerun()

    _next_block = next((b for b in _blocks if not b["done"]), None)
    if _next_block is not None:
        _next_title = next((s["title"] for s in _sections
                            if s["section_id"] == _next_block["section_id"]), "Abschnitt")
        if _next_block["planned_date"] == _today_iso_plan:
            _nb_when = "heute"
        elif _next_block["planned_date"] < _today_iso_plan:
            _nb_when = f"{_next_block['planned_date']} (überfällig)"
        else:
            _nb_when = _next_block["planned_date"]
        st.info(f"▶️ **Nächster Block:** {_next_title} · "
               f"{_fmt_min(_next_block['planned_min'])} · {_nb_when}")
    elif _total_planned_all:
        st.success("✅ Alle Blöcke dieses Plans sind erledigt.")

# --------------------------------------------------------------------------- #
# Schrittleiste: wo steht der Plan, was kommt als Nächstes?
# --------------------------------------------------------------------------- #
_STEP_HINT = {1: "„🧠 Gliederung“ unten", 2: "„📦 Lerneinheiten“ unten",
              3: "„📐 Plan berechnen“ unten", 4: "„🗓️ Zeitplan“ unten"}


def _steps_html(steps: list) -> str:
    parts = []
    for stp in steps:
        cls = {"done": " splan-step-done", "warn": " splan-step-warn"}.get(stp["state"], "")
        if stp["next"] and stp["state"] != "warn":
            cls += " splan-step-next"
        sub = _html.escape(stp["sub"]) + (
            f" · <b>als Nächstes</b> → {_STEP_HINT[stp['n']]}" if stp["next"] else "")
        mark = "✓" if stp["state"] == "done" else stp["n"]
        parts.append(
            f"<div class='splan-step{cls}'><div class='splan-step-title'>"
            f"<span class='splan-step-n'>{mark}</span>{_html.escape(stp['title'])}</div>"
            f"<div class='splan-step-sub'>{sub}</div></div>")
    return "<div class='splan-steps'>" + "".join(parts) + "</div>"


if _sections or _blocks:
    st.markdown(_steps_html(plan_cards.plan_steps(
        _sections, _unit_stats, _stale, _blocks, _today_str)), unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Hintergrundauftrag (Karten/Übungen füllen): Fortschritt, Abbrechen, Ergebnis. Läuft in
# einem eigenen Thread (ragapp/jobs.py), die Seite bleibt bedienbar und die Leiste folgt
# beim Scrollen. Als Fragment, das sich alle 2 s selbst aktualisiert, solange etwas läuft.
# --------------------------------------------------------------------------- #
def _fmt_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d} Min"


def _render_job_panel() -> None:
    import time as _time
    job = jobs.get(plan_cards.job_key(_active_plan_id))
    if job is None:
        return
    running_flag = f"_splan_job_seen_running_{job.job_id}"
    if job.status == jobs.RUNNING:
        st.session_state[running_flag] = True
    elif st.session_state.pop(running_flag, False):
        # Der Lauf ist gerade fertig geworden: ganze Seite neu aufbauen (Kacheln, Zähler).
        st.rerun()
    with card("splan_jobbar"):
        if job.status == jobs.RUNNING:
            jc1, jc2 = st.columns([4, 1.3])
            jc1.markdown(f"**⏳ {_html.escape(job.title)}**")
            jc1.progress(min(1.0, job.step / job.total) if job.total else 0.0,
                         text=(job.message or "startet …")[:110])
            jc1.caption(f"läuft seit {_fmt_elapsed(_time.time() - job.started)} · "
                        "Fertiges ist schon gespeichert")
            if job.cancel_requested:
                jc2.button("⏳ Stoppt …", disabled=True, use_container_width=True,
                           key=f"splan_job_stopping_{job.job_id}",
                           help="Der Lauf hört nach dem aktuellen Schritt auf.")
            elif jc2.button("⏹ Abbrechen", use_container_width=True,
                            key=f"splan_job_cancel_{job.job_id}",
                            help="Hört nach dem aktuellen Schritt auf. Was bis dahin fertig "
                                 "ist, bleibt erhalten; ein erneuter Klick macht weiter."):
                jobs.cancel(plan_cards.job_key(_active_plan_id))
                st.rerun(scope="fragment")
        else:
            level, text = plan_cards.summarize_job(job)
            getattr(st, level)(text)
            if st.button("OK", key=f"splan_job_ok_{job.job_id}"):
                jobs.dismiss(plan_cards.job_key(_active_plan_id))
                st.rerun()


if _job is not None:
    st.fragment(run_every=2 if _job_running else None)(_render_job_panel)()

# key= haelt den Auf/Zu-Zustand fest - ohne key faellt der Expander sonst bei
# JEDEM Rerun (auch nur durch das "Zieldatum setzen"-Haekchen DARIN) auf
# zugeklappt zurueck, bevor gespeichert wird.
with st.expander("⚙️ Einstellungen & Löschen", key=f"splan_settings_expander_{_active_plan_id}"):
    ec1, ec2, ec3 = st.columns(3)
    with ec1:
        _edit_daily = st.number_input("Verfügbare Zeit/Tag (Min)", min_value=15, max_value=600,
                                      value=int(_plan["daily_minutes"]), step=15,
                                      key=f"splan_edit_daily_{_active_plan_id}")
    with ec2:
        _edit_has_deadline = st.checkbox("Zieldatum setzen", value=bool(_plan.get("deadline")),
                                         key=f"splan_edit_hasdl_{_active_plan_id}")
    with ec3:
        _dl_default = (study_plan.parse_iso_date(_plan.get("deadline"))
                      or date.today() + timedelta(days=7))
        _edit_deadline = (st.date_input("Zieldatum", value=_dl_default,
                                        key=f"splan_edit_dl_{_active_plan_id}")
                          if _edit_has_deadline else None)
    _edit_rest_days = st.multiselect(
        "Ruhetage",
        options=list(range(7)),
        default=list(_plan_rest_days),
        format_func=lambda i: _weekday_names[i],
        key=f"splan_rest_days_{_active_plan_id}",
        help="Gilt nur für diesen Lernplan; an diesen Tagen ist sein Planbudget 0.",
    )
    if st.button("💾 Einstellungen speichern", key=f"splan_save_settings_{_active_plan_id}"):
        manifest.update_study_plan(
            _active_plan_id, daily_minutes=int(_edit_daily),
            deadline=_edit_deadline.isoformat() if _edit_deadline else None,
            rest_weekdays=sorted(_edit_rest_days))
        st.session_state["_splan_flash"] = (
            "Einstellungen gespeichert. Damit die Termine dazu passen, klicke auf "
            "**📐 Plan berechnen**.")
        st.rerun()
    if delete_button("🗑️ Plan löschen", token=f"plan:{_active_plan_id}",
                     body=f"Lernplan **{_plan.get('title') or 'ohne Titel'}** wirklich löschen?",
                     key=f"splan_delete_{_active_plan_id}"):
        manifest.delete_study_plan(_active_plan_id)
        st.success("Plan gelöscht.")
        st.rerun()

# --------------------------------------------------------------------------- #
# Gliederung (editierbar)
# --------------------------------------------------------------------------- #
st.markdown("##### 🧠 Gliederung")

_regen_model_choice = st.radio(
    "Modell für die Gliederung", ["🎯 Gründlich (langsamer)", "⚡ Schnell (gröber)"],
    horizontal=True, key=f"splan_regen_model_{_active_plan_id}")
_regen_model = settings.LLM_MODEL_FAST if "Schnell" in _regen_model_choice else None
_regen_eta = study_plan.estimate_outline_eta_seconds(_plan["doc_ids"], model=_regen_model)
st.caption(f"Geschätzte Wartezeit: ~{_regen_eta // 60} Min" if _regen_eta >= 90
          else f"Geschätzte Wartezeit: ~{_regen_eta} Sek.")
st.caption(_time_factor_caption(_plan["subject"]))

with st.expander("ℹ️ Wie kommt die Zeitschätzung zustande?",
                 key=f"splan_time_explain_{_active_plan_id}"):
    import statistics as _statistics
    _chars_known = [s["est_chars"] for s in _sections if s.get("est_chars")]
    _example_chars = (max(1000, int(round(_statistics.median(_chars_known) / 500.0)) * 500)
                      if _chars_known else 6000)
    for _line in study_plan.explain_time_estimate(_plan["subject"], _example_chars):
        st.markdown("- " + _line)

if st.button("🔄 Gliederung neu erzeugen", key=f"splan_regen_{_active_plan_id}",
             disabled=_job_running,
             help="Läuft gerade ein Karten-Lauf? Erst abbrechen oder abwarten." if _job_running
             else None):
    from ragapp.ui._progress import LlmWait
    with LlmWait("Suche in den Unterlagen …") as wait:
        wait.set("Formuliere die Gliederung …")
        try:
            outline, _regen_warning = study_plan.generate_outline(
                _plan["doc_ids"], _plan["subject"], model=_regen_model)
        except study_plan.OutlineError as exc:
            wait.done("Nicht geklappt", ok=False)
            st.error(str(exc))
            st.stop()
        wait.done()
    manifest.replace_plan_sections(_active_plan_id, outline)
    if _regen_warning:
        st.session_state["_splan_gen_warning"] = _regen_warning
    else:
        st.success(f"Gliederung mit {len(outline)} Themen neu erzeugt.")
    st.rerun()

_splan_gen_warning = st.session_state.pop("_splan_gen_warning", None)
if _splan_gen_warning:
    st.warning(_splan_gen_warning)
_splan_flash = st.session_state.pop("_splan_flash", None)
if _splan_flash:
    st.info(_splan_flash)

# --------------------------------------------------------------------------- #
# Lerneinheiten fuellen - HALBAUTOMATISCH: ein Klick erzeugt aus dem Dokument, aus dem
# ein Thema entstanden ist, Karten + Uebungsaufgabe, und zwar NUR aus dem Text dieses
# Themas (siehe ragapp/plan_cards.py). Nichts laeuft von allein. Das Fuellen mehrerer
# Themen laeuft als Hintergrundauftrag (Fortschritt + "Abbrechen" in der Leiste oben, die
# Seite bleibt bedienbar); einzelne Themen fuer "Karten ueben"/"Uebung" werden direkt unter
# dem Knopf erzeugt, weil danach sofort die Lernseite aufgeht.
# --------------------------------------------------------------------------- #
_RUNNING_HELP = "Es läuft gerade ein Karten-Lauf (siehe oben) – erst abbrechen oder abwarten."


def _unit_line(sec: dict) -> str:
    """Fuellstand einer Lerneinheit: „🃏 12 Karten · 2 fällig · 🧮 1 Übung“."""
    su = _unit_stats.get(sec["section_id"]) or {}
    cards = su.get("cards", 0)
    parts = [f"🃏 {cards} Karten" if cards else "🃏 keine Karten"]
    if su.get("due"):
        parts.append(f"{su['due']} fällig")
    if su.get("unanswered"):
        parts.append(f"{su['unanswered']} ohne Antwort")
    parts.append(f"🧮 {su['problems']} Übung(en)" if su.get("problems") else "🧮 keine Übung")
    return " · ".join(parts)


def _ensure_cards(sec: dict, slot) -> bool:
    """Karten zu EINEM Thema - nur wenn es noch keine hat. True, wenn danach welche da sind."""
    if plan_cards.study_card_ids(sec, limit=1):
        return True
    if _job_running:
        slot.warning("Für dieses Thema gibt es noch keine Karten, und gerade läuft ein "
                     "Karten-Lauf. Erst abwarten oder abbrechen – dann klappt es.")
        return False
    with slot:
        with st.status(f"Karten zu „{sec['title'][:50]}“ …", expanded=True) as _stat:
            out = plan_cards.create_section_cards(
                sec, progress=lambda m: _stat.update(label=f"„{sec['title'][:40]}“ – {m}"))
            ok = out.get("status") == "ok" and int(out.get("cards_total") or 0) > 0
            _stat.update(label="Fertig" if ok else "Nicht geklappt",
                         state="complete" if ok else "error")
    if not ok:
        slot.error(out.get("error_msg") or "Es konnten keine Karten erzeugt werden.")
    return ok


def _ensure_practice(sec: dict, slot) -> "str | None":
    """Uebungsaufgabe zu EINEM Thema: die neueste vorhandene, sonst eine neue (nur aus dem
    Text des Themas). None, wenn die Erzeugung scheitert."""
    have = plan_cards.section_problems(sec, _plan["subject"])
    if have:
        return have[0]["problem_id"]
    if _job_running:
        slot.warning("Für dieses Thema gibt es noch keine Übung, und gerade läuft ein "
                     "Karten-Lauf. Erst abwarten oder abbrechen – dann klappt es.")
        return None
    with slot:
        with st.status(f"Übungsaufgabe zu „{sec['title'][:50]}“ …", expanded=True) as _stat:
            try:
                pid = plan_cards.create_section_practice(sec, subject=_plan["subject"])
            except Exception as exc:  # noqa: BLE001 - PracticeGenError, LLM, VRAM ...
                _stat.update(label="Nicht geklappt", state="error")
                slot.error(str(exc))
                return None
            _stat.update(label="Fertig", state="complete")
    return pid


def _fill_units(secs: list, *, with_practice: bool, title: str, repair: bool = False) -> None:
    """Karten (+ Uebung) fuer mehrere Themen im HINTERGRUND starten (ein Auftrag je Plan);
    Fortschritt und "Abbrechen" erscheinen in der Leiste oben. Jedes Thema wird einzeln
    gespeichert - ein Abbruch verliert nichts, ein erneuter Klick macht dort weiter."""
    _job_new, _started = plan_cards.start_fill_job(
        _plan, secs, with_practice=with_practice, title=title, repair=repair)
    if not _started:
        st.toast("Es läuft schon ein Lauf für diesen Plan.", icon="⏳")
    st.rerun()


if not _sections:
    st.info("Noch keine Gliederung vorhanden.")
else:
    _sec_orig = {s["section_id"]: s for s in _sections}
    _sched = plan_cards.section_schedule(_blocks)

    # Lerneinheiten-Leiste: wie voll sind die Themen, und alle auf einen Klick fuellen.
    _mixed = [s for s in _sections if len(plan_cards.section_docs(s)) > 1]
    _n_cards_all = sum(v["cards"] for v in _unit_stats.values())
    _n_probs_all = sum(v.get("problems", 0) for v in _unit_stats.values())
    _n_complete = len(_sections) - len(
        plan_cards.sections_needing_cards(_unit_stats, _sections, with_practice=True))
    _flawed_ids = [cid for v in _unit_stats.values() for cid in v.get("flawed_ids", [])]
    with st.container(border=True):
        _kc1, _kc2 = st.columns([3, 1.6])
        _kc1.markdown(
            f"**📦 Lerneinheiten:** {_n_complete} von {len(_sections)} Themen komplett · "
            f"{_n_cards_all} Karten · {_n_probs_all} Übungen")
        _with_pr = _kc1.checkbox(
            "🧮 mit je einer Übungsaufgabe pro Thema", value=True,
            key=f"splan_fill_pr_{_active_plan_id}",
            help="Karten gibt es immer; die Übungsaufgabe dauert pro Thema etwa eine "
                 "halbe Minute länger.")
        _todo_units = plan_cards.sections_needing_cards(
            _unit_stats, _sections, with_practice=_with_pr)
        if _todo_units:
            _miss_cards = plan_cards.estimate_missing_cards(_plan, _unit_stats)
            _miss_pr = (sum(1 for s in _todo_units
                            if (_unit_stats.get(s["section_id"]) or {}).get("problems", 0) == 0)
                        if _with_pr else 0)
            _kc1.caption(
                f"{len(_todo_units)} Thema/Themen noch nicht komplett – grob {_miss_cards} "
                f"Karten, etwa {plan_cards.estimate_fill_minutes(_miss_cards, _miss_pr)} Min "
                "(hängt stark von Modell und Hardware ab). Der Lauf geht im Hintergrund: "
                "du siehst den Fortschritt oben und kannst jederzeit abbrechen. Jedes Thema "
                "wird einzeln gespeichert; ein erneuter Klick macht dort weiter.")
        else:
            _kc1.caption("✅ Alle Lerneinheiten sind gefüllt.")
        if _todo_units and _kc2.button(
                "📦 Alle Themen füllen", type="primary", use_container_width=True,
                disabled=_job_running, key=f"splan_fill_{_active_plan_id}",
                help=_RUNNING_HELP if _job_running else None):
            _fill_units(_todo_units, with_practice=_with_pr,
                        title="Alle Lerneinheiten werden gefüllt")

    # Kartenqualität: Karten müssen OHNE das Dokument verständlich sein.
    if _n_cards_all >= 2:
        with st.expander(
                "🧹 Kartenqualität – " + (f"{len(_flawed_ids)} Karte(n) mit Mängeln"
                                          if _flawed_ids else "keine Mängel erkannt"),
                key=f"splan_quality_{_active_plan_id}"):
            st.caption(
                "Eine Karte soll auch unterwegs ohne das Skript Sinn ergeben. Auffällig sind "
                "Verweise („im Abschnitt“, „Abbildung 2“, „Definition 4“), kaputte PDF-Zeichen "
                "und Fragen, die an einem Beweisschritt hängen. Neue Karten werden schon beim "
                "Erzeugen so gefiltert (und bei Mängeln neu formuliert).")
            _q_cards = {c["card_id"]: c for c in manifest.get_cards_by_ids(_flawed_ids)}
            _q_audit = card_quality.audit_cards(list(_q_cards.values()))
            _q_plan = plan_cards.split_repairs(list(_q_cards.values()), _q_audit)
            _q_owner = {cid: s for s in _sections
                        for cid in (_unit_stats.get(s["section_id"]) or {}).get("flawed_ids", [])}
            _q_status = {**{c: "wird ersetzt" for c in _q_plan["replace"]},
                         **{c: "Antwort wird neu formuliert" for c in _q_plan["answers"]},
                         **{c: "bleibt (schon gelernt/bearbeitet)" for c in _q_plan["protected"]}}
            if _q_audit:
                # Liste statt Tabelle: bleibt auch auf dem Handy lesbar (keine Querscroll-Spalten).
                _md_special = _re.compile(r"([\\`*_{}\[\]<>$#|~])")

                def _esc(txt: str) -> str:
                    return _md_special.sub(r"\\\1", txt or "")

                _q_items = list(_q_audit.items())
                st.markdown("\n".join(
                    f"- **{_esc((_q_owner.get(cid) or {}).get('title', ''))}** · "
                    f"„{_esc((_q_cards[cid].get('front') or '')[:140])}“  \n"
                    f"  ↳ {_esc(card_quality.describe_audit(entry))} · **{_q_status.get(cid, '')}**"
                    for cid, entry in _q_items[:30]))
                if len(_q_items) > 30:
                    st.caption(f"… und {len(_q_items) - 30} weitere.")
            st.caption(
                "„Mängel beheben“ prüft zusätzlich auf **doppelte Fragen**, ersetzt unberührte "
                "Karten mit Mängeln (die Lücke wird mit dem Qualitätsfilter neu gefüllt) und "
                "formuliert Antworten mit Mängeln neu. Karten, die du schon gelernt oder "
                "selbst bearbeitet hast, bleiben unangetastet. Vorher legt die App eine "
                "Sicherung an. Das Ergebnis siehst du oben in der Leiste.")
            _q_flag = f"_splan_quality_confirm_{_active_plan_id}"
            if not st.session_state.get(_q_flag):
                if st.button("🧹 Mängel beheben …", disabled=_job_running,
                             key=f"splan_quality_ask_{_active_plan_id}",
                             help=_RUNNING_HELP if _job_running else None):
                    st.session_state[_q_flag] = True
                    st.rerun()
            else:
                st.warning(
                    f"Wirklich beheben? {len(_q_plan['replace'])} Karte(n) werden ersetzt, "
                    f"bei {len(_q_plan['answers'])} wird nur die Antwort neu formuliert, "
                    f"{len(_q_plan['protected'])} bleiben. Dazu kommen ggf. doppelte Fragen.")
                _qa, _qb = st.columns(2)
                if _qa.button("Ja, beheben", type="primary", use_container_width=True,
                              key=f"splan_quality_go_{_active_plan_id}"):
                    st.session_state.pop(_q_flag, None)
                    _fill_units(_sections, with_practice=False, repair=True,
                                title="Kartenqualität: Mängel beheben")
                if _qb.button("Abbrechen", use_container_width=True,
                              key=f"splan_quality_no_{_active_plan_id}"):
                    st.session_state.pop(_q_flag, None)
                    st.rerun()

    st.caption("Karten und Übungen entstehen ausschließlich aus dem Dokument, aus dem das "
               "jeweilige Thema stammt – und nur aus dem Text dieses Themas. Im Lernplan "
               "kommt beim Üben nur der Stoff dran, der für das Thema bzw. den Tag gedacht "
               "ist; die normalen Karteikarten bleiben unverändert.")
    if _mixed:
        st.warning(
            f"⚠️ {len(_mixed)} Thema/Themen stammen aus mehreren Dokumenten (Karten und "
            "Übungen mischen dort deren Stoff). **🔄 Gliederung neu erzeugen** bildet "
            "dokumentreine Themen: ein Thema = ein Dokument.")

    st.markdown("###### Themen im Überblick")
    _WHEN_COLOR = {"overdue": "#dc2626", "today": "#2563eb", "done": "#16a34a",
                   "later": "inherit", "none": "inherit"}
    for _row_start in range(0, len(_sections), 3):
        _row_cols = st.columns(3)
        _row_slot = st.container()      # Rueckmeldung direkt unter der Kachelreihe
        for _col, _s in zip(_row_cols, _sections[_row_start:_row_start + 3]):
            with _col:
                _sid = _s["section_id"]
                _s_done = bool(_s.get("done"))
                _su = _unit_stats.get(_sid) or {}
                _kind, _when = plan_cards.schedule_label(_sched.get(_sid), _today_str)
                _card_bg = "rgba(22,163,74,.12)" if _s_done else "rgba(148,163,184,.10)"
                _card_border = "#16a34a" if _s_done else _plan_color
                _summary = (_s.get("summary") or "").strip()
                _summary_short = (_summary[:90] + "…") if len(_summary) > 90 else _summary
                st.markdown(
                    f"<div class='splan-topic-card' style='background:{_card_bg};"
                    f"border-left:4px solid {_card_border};'>"
                    f"<div class='splan-topic-title'>{'✅ ' if _s_done else ''}"
                    f"{_s['order_index'] + 1}. {_html.escape(_s['title'])}</div>"
                    f"<div class='splan-topic-meta'>{_fmt_min(_s['est_minutes'])} · "
                    f"<span style='color:{_WHEN_COLOR[_kind]};font-weight:"
                    f"{'650' if _kind in ('today', 'overdue') else '400'}'>"
                    f"{_html.escape(_when)}</span>"
                    + (f"<br>{_html.escape(_summary_short)}" if _summary_short else "")
                    + "</div></div>", unsafe_allow_html=True)
                st.caption("📄 " + (plan_cards.section_reference(_s) or "Quelle unbekannt"))
                st.caption(_unit_line(_s))
                _learn = plan_cards.learning_line(_su)
                if _learn:
                    st.markdown(plan_cards.learning_bar_html(_su), unsafe_allow_html=True)
                    st.caption(_learn)
                if _su.get("flawed"):
                    st.caption(f"🧹 {_su['flawed']} Karte(n) mit Mängeln")
                _incomplete = (_su.get("cards", 0) == 0 or _su.get("unanswered", 0) > 0
                               or _su.get("problems", 0) == 0)
                if _incomplete and st.button(
                        "📦 Einheit füllen",
                        type="primary" if _kind in ("today", "overdue") else "secondary",
                        use_container_width=True, disabled=_job_running,
                        key=f"splan_unit_{_sid}",
                        help=_RUNNING_HELP if _job_running else
                        "Erzeugt aus dem Dokument dieses Themas die fehlenden Karten "
                        "und eine Übungsaufgabe - ein Klick, nur dieser Stoff."):
                    _fill_units([_s], with_practice=True,
                                title=f"„{_s['title'][:40]}“ wird gefüllt")
                _bc1, _bc2 = st.columns(2)
                if _bc1.button("▶ Karten", key=f"splan_cardstudy_{_sid}",
                               use_container_width=True,
                               help="Karten NUR zu diesem Thema üben - gibt es noch keine, "
                                    "werden sie jetzt erzeugt."):
                    if _ensure_cards(_s, _row_slot):
                        st.session_state["study_prefill"] = {
                            "source": "plan", "subject": _plan["subject"], "mode": "reveal",
                            "limit": 16, "card_ids": plan_cards.study_card_ids(_s, limit=16),
                            "scope": f"Thema „{_s['title']}“ · 📄 "
                                     + (plan_cards.section_reference(_s) or "Quelle unbekannt"),
                        }
                        st.switch_page("pages/4_🎓_Lernen.py")
                if _bc2.button("🧮 Übung", key=f"splan_practice_{_sid}",
                               use_container_width=True,
                               help="Übungsaufgabe zu diesem Thema - gibt es noch keine, "
                                    "wird sie jetzt aus dem Text des Themas erzeugt."):
                    _pid = _ensure_practice(_s, _row_slot)
                    if _pid:
                        st.session_state["practice_prefill"] = {
                            "source": "plan", "subject": _plan["subject"],
                            "doc_ids": [d for d, _n in plan_cards.section_docs(_s)]
                                       or list(_plan["doc_ids"]),
                            "topic": _s["title"], "problem_ids": [_pid],
                        }
                        st.switch_page("pages/13_🧮_Übungsaufgaben.py")
                if _su.get("due") and st.button(
                        f"🔁 Wiederholen · {_su['due']} fällig", use_container_width=True,
                        key=f"splan_review_{_sid}",
                        help="Nur die FÄLLIGEN Karten dieses Themas auffrischen - Gelerntes "
                             "wiederholen, keine neuen Karten."):
                    st.session_state["study_prefill"] = {
                        "source": "plan", "subject": _plan["subject"], "mode": "reveal",
                        "limit": 16, "card_ids": plan_cards.review_card_ids(_s, limit=16),
                        "scope": f"Wiederholung: Thema „{_s['title']}“ · 📄 "
                                 + (plan_cards.section_reference(_s) or "Quelle unbekannt"),
                    }
                    st.switch_page("pages/4_🎓_Lernen.py")

    _sec_df = pd.DataFrame([{
        "🗑️": False, "Reihenfolge": s["order_index"], "Titel": s["title"],
        "Zusammenfassung": s.get("summary") or "", "Zeichen": s["est_chars"],
        "Minuten": s["est_minutes"], "_id": s["section_id"],
    } for s in _sections])
    _sec_edited = st.data_editor(
        _sec_df, hide_index=True, use_container_width=True,
        key=f"splan_sections_editor_{_active_plan_id}",
        column_config={
            "🗑️": st.column_config.CheckboxColumn(width="small"),
            "Reihenfolge": st.column_config.NumberColumn(min_value=0, step=1),
            "Zeichen": st.column_config.NumberColumn(disabled=True, help="Grundlage der Zeitschätzung"),
            "Minuten": st.column_config.NumberColumn(min_value=5, step=5,
                                                      help="Automatisch geschätzt, überschreibbar"),
            "_id": None,
        },
    )
    if st.button("💾 Gliederung speichern", key=f"splan_save_sections_{_active_plan_id}"):
        kept = [row for _, row in _sec_edited.iterrows() if not row["🗑️"]]
        kept.sort(key=lambda row: row["Reihenfolge"])
        new_sections = [{
            "section_id": row["_id"] if row["_id"] in _sec_orig else None,
            "title": row["Titel"], "summary": row["Zusammenfassung"],
            "est_chars": row["Zeichen"], "est_minutes": row["Minuten"],
            "done": _sec_orig.get(row["_id"], {}).get("done", False),
            "source_refs": _sec_orig.get(row["_id"], {}).get("source_refs", []),
        } for row in kept]
        manifest.replace_plan_sections(_active_plan_id, new_sections)
        st.success("Gliederung gespeichert.")
        st.rerun()

    _total_min = sum(s["est_minutes"] for s in _sections)
    st.caption(f"Geschätzter Gesamtaufwand: **{_fmt_min(_total_min)}** für {len(_sections)} Themen.")

    # Live-Vorschau (oben berechnet, siehe ``_preview``): rechnet bei JEDEM Rendern mit dem
    # aktuell GESPEICHERTEN Stand (Zeit/Tag, Zieldatum, Gliederung) - so ist die Engpass-/
    # Deckelungs-Warnung immer sichtbar, nicht nur direkt nach einem Klick auf "Plan berechnen".
    if _preview["capped_daily"]:
        st.caption(
            f"⏱️ {_plan['daily_minutes']} Min/Tag sind mehr, als nachhaltig hochfokussiert "
            f"lernbar ist – der Plan rechnet realistisch mit "
            f"**{_preview['effective_daily_min']} Min/Tag** (siehe Forschung oben).")
    if _preview["review_minutes_reserved"] > 0:
        st.caption(
            f"🔁 Zusätzlich sind **{_fmt_min(_preview['review_minutes_reserved'])}** für "
            "fällige Karteikarten-Wiederholungen reserviert (aus der Fälligkeits-Prognose) "
            "– die belegen echte Zeit, bevor neuer Stoff drankommt.")
    if _preview["class_minutes_reserved"] > 0:
        st.caption(
            f"🗓️ Außerdem sind **{_fmt_min(_preview['class_minutes_reserved'])}** durch "
            "Vorlesungen/Kurse aus **Kurse & Stundenplan** belegt – der Plan "
            "rechnet nur noch mit der Zeit, die daneben realistisch übrig bleibt.")
    if _preview["shortfall_minutes"] > 0:
        st.warning(
            f"⚠️ Ehrlich gesagt: Bis zum Zieldatum passen nur "
            f"{_fmt_min(_preview['total_minutes'] - _preview['shortfall_minutes'])} von "
            f"{_fmt_min(_preview['total_minutes'])} – **{_fmt_min(_preview['shortfall_minutes'])} "
            f"fehlen**. Entweder Zieldatum verschieben, mehr Zeit/Tag einplanen oder "
            f"Gliederung kürzen.")
    else:
        st.caption(
            f"✅ Passt: {_fmt_min(_preview['total_minutes'])} über "
            f"{_preview['days_needed_total']} Tag(e)"
            + (" bis zum Zieldatum." if _plan.get("deadline") else " in deinen Zeitrahmen."))

    # Zieldatum/Klausur/Tempo in Klartext - mit den echten Zahlen der Vorschau.
    from ragapp.student_flow import default_plan_deadline
    _exam_iso = default_plan_deadline(_plan["subject"])
    for _hi, _hint in enumerate(study_plan.deadline_hints(_plan, _preview, exam_iso=_exam_iso)):
        if _hint["level"] == "warning":
            st.warning("⚠️ " + _hint["text"])
        else:
            st.caption("ℹ️ " + _hint["text"])
        if _hint["action"] == "use_exam_date" and _exam_iso and st.button(
                "📅 Klausurdatum als Zieldatum übernehmen",
                key=f"splan_use_exam_{_active_plan_id}_{_hi}",
                help="Setzt das Zieldatum dieses Plans auf das Klausurdatum des Fachs. Danach "
                     "„📐 Plan berechnen“ klicken, damit die Termine dazu passen."):
            manifest.update_study_plan(_active_plan_id, deadline=_exam_iso)
            st.session_state["_splan_flash"] = (
                "Zieldatum auf das Klausurdatum gesetzt. Klicke jetzt auf **📐 Plan berechnen**, "
                "damit die Termine dazu passen.")
            st.rerun()

    if _stale["state"] == "stale":
        st.warning("⚠️ **Der Zeitplan ist veraltet** – " + " ".join(_stale["reasons"])
                   + " Klicke auf **📐 Plan berechnen**, damit er wieder zur Gliederung passt. "
                   "Erledigte Blöcke bleiben dabei erhalten.")
    elif _stale["state"] == "missing":
        st.info("Der Zeitplan ist noch nicht berechnet – **📐 Plan berechnen** verteilt die "
                "Themen auf Tage.")

    if st.button("📐 Plan berechnen", type="primary", key=f"splan_build_{_active_plan_id}"):
        manifest.replace_plan_blocks(_active_plan_id, _preview["blocks"])
        manifest.update_study_plan(_active_plan_id, status="active")
        st.toast("Zeitplan aktualisiert.", icon="📐")
        st.rerun()

st.divider()

# --------------------------------------------------------------------------- #
# Zeitplan (Tagesblöcke)
# --------------------------------------------------------------------------- #
with card("zeitplan"):
    st.markdown("##### 🗓️ Zeitplan")
    if not _blocks:
        st.caption("Noch kein Zeitplan berechnet – Gliederung anpassen und oben "
                   "„📐 Plan berechnen“ klicken.")
    else:
        _sec_title = {s["section_id"]: s["title"] for s in _sections}
        _sec_by_id = {s["section_id"]: s for s in _sections}
        _total_planned = sum(b["planned_min"] for b in _blocks)
        _done_planned = sum(b["planned_min"] for b in _blocks if b["done"])
        st.progress(_done_planned / _total_planned if _total_planned else 0.0,
                   text=f"{_fmt_min(_done_planned)} von {_fmt_min(_total_planned)} erledigt")

        _by_date: dict = {}
        for b in _blocks:
            _by_date.setdefault(b["planned_date"], []).append(b)


        def _render_timeline(by_date: dict, color: str) -> str:
            """Horizontale Fortschritts-Zeitleiste: ein Segment pro Tag, Fuellhoehe =
            Anteil erledigt an diesem Tag, gruen sobald der Tag komplett ist, der
            heutige Tag hervorgehoben."""
            today_iso = date.today().isoformat()
            segs = []
            for day in sorted(by_date.keys()):
                day_blocks = by_date[day]
                total = sum(bl["planned_min"] for bl in day_blocks)
                done = sum(bl["planned_min"] for bl in day_blocks if bl["done"])
                pct = round(100 * done / total) if total else 0
                is_today = " splan-tl-today" if day == today_iso else ""
                fill = "#16a34a" if pct == 100 else color
                label = "Heute" if day == today_iso else day[5:].replace("-", ".")
                segs.append(
                    f"<div class='splan-tl-seg{is_today}' "
                    f"title='{day}: {_fmt_min(done)} / {_fmt_min(total)}'>"
                    f"<div class='splan-tl-fill' style='height:{pct}%;background:{fill};'></div>"
                    f"<div class='splan-tl-label'>{label}</div></div>")
            return f"<div class='splan-tl-wrap'><div class='splan-tl-row'>{''.join(segs)}</div></div>"


        st.markdown(_render_timeline(_by_date, _plan_color), unsafe_allow_html=True)

        # Der Tag: nur der Stoff, der fuer ihn geplant ist. "Karten fuer diesen Tag" nimmt
        # ausschliesslich die Themen der Bloecke dieses Tages - nichts aus spaeteren Themen
        # (kein "Matrizen", solange Vektormultiplikation dran ist).
        _today_iso = date.today().isoformat()
        _day_iso = (_today_iso if any(b["planned_date"] == _today_iso for b in _blocks)
                    else plan_cards.next_study_day(_blocks, _today_iso))
        _day_secs = (plan_cards.sections_for_day(_blocks, _sections, _day_iso)
                     if _day_iso else [])
        if _day_secs:
            _day_name = ("Heute" if _day_iso == _today_iso
                         else f"Nächster Lerntag ({plan_cards.fmt_day(_day_iso)})")
            with st.container(border=True):
                st.markdown(f"**📅 {_day_name}** · {len(_day_secs)} Thema/Themen")
                for _ds in _day_secs:
                    st.markdown(f"<b>{_html.escape(_ds['title'])}</b>", unsafe_allow_html=True)
                    st.caption(f"📄 {plan_cards.section_reference(_ds) or 'Quelle unbekannt'}"
                               f" · {_unit_line(_ds)}")
                _dc1, _dc2, _dc3 = st.columns(3)
                _day_slot = st.container()
                _day_need = plan_cards.sections_needing_cards(
                    _unit_stats, _day_secs, with_practice=True)
                if _day_need and _dc1.button(
                        "📦 Tag vorbereiten", use_container_width=True,
                        disabled=_job_running, key=f"splan_dayfill_{_day_iso}",
                        help=_RUNNING_HELP if _job_running else
                        "Erzeugt die fehlenden Karten und Übungen für die Themen "
                        "dieses Tages - ein Klick, nur dieser Stoff."):
                    _fill_units(_day_need, with_practice=True,
                                title=f"{_day_name} wird vorbereitet")
                # Wiederholen: nur FAELLIGE Karten aus bisherigen/angefangenen Themen - nie aus
                # Themen, die noch nicht dran waren.
                _past = plan_cards.started_sections(_blocks, _sections, _unit_stats, _today_iso)
                _past_due = sum((_unit_stats.get(x["section_id"]) or {}).get("due", 0)
                                for x in _past)
                if _past_due and _dc3.button(
                        f"🔁 Wiederholen · {_past_due} fällig", use_container_width=True,
                        key=f"splan_dayreview_{_day_iso}",
                        help="Fällige Karten aus den Themen, die schon dran waren oder "
                             "angefangen sind - Gelerntes auffrischen, nichts Neues."):
                    _past_with_due = [x for x in _past
                                      if (_unit_stats.get(x["section_id"]) or {}).get("due")]
                    st.session_state["study_prefill"] = {
                        "source": "plan", "subject": _plan["subject"], "mode": "reveal",
                        "limit": 30,
                        "card_ids": plan_cards.review_card_ids_for(
                            _past_with_due, _unit_stats, per_topic=8, total=30),
                        "scope": (f"Wiederholung bisheriger Themen: "
                                  + ", ".join(x["title"] for x in _past_with_due))[:200],
                    }
                    st.switch_page("pages/4_🎓_Lernen.py")
                if _dc2.button("▶ Karten für diesen Tag", type="primary",
                               use_container_width=True, key=f"splan_daystudy_{_day_iso}",
                               help="Nur die Karten der Themen, die für diesen Tag geplant "
                                    "sind - fehlende werden jetzt erzeugt."):
                    _day_ok = True
                    for _ds in _day_secs:
                        if not _ensure_cards(_ds, _day_slot):
                            _day_ok = False
                            break
                    if _day_ok and _day_secs:
                        st.session_state["study_prefill"] = {
                            "source": "plan", "subject": _plan["subject"], "mode": "reveal",
                            "limit": 30, "card_ids": plan_cards.day_card_ids(_day_secs),
                            "scope": (f"{_day_name}: "
                                      + ", ".join(s["title"] for s in _day_secs))[:200],
                        }
                        st.switch_page("pages/4_🎓_Lernen.py")

        _focus_blocks = set(st.session_state.get("splan_focus_block_ids") or [])

        for d in sorted(_by_date.keys()):
            _day_blocks = _by_date[d]
            _label = "**Heute**" if d == date.today().isoformat() else d
            _day_done = sum(bl["planned_min"] for bl in _day_blocks if bl["done"])
            _day_total = sum(bl["planned_min"] for bl in _day_blocks)
            _day_focus = any(bl["block_id"] in _focus_blocks for bl in _day_blocks)
            with st.expander(f"{_label} · {_fmt_min(_day_total)}"
                            + (" ✅" if _day_done == _day_total else "")
                            + (" · Fokus" if _day_focus else ""),
                            expanded=(d == date.today().isoformat() or _day_focus)):
                for bl in _day_blocks:
                    title = _sec_title.get(bl["section_id"], "Abschnitt")
                    section = _sec_by_id.get(bl["section_id"], {})
                    source_doc_ids = list(dict.fromkeys(
                        ref.get("doc_id") for ref in section.get("source_refs", [])
                        if ref.get("doc_id")
                    )) or list(_plan.get("doc_ids") or [])
                    # Ehrlich sichtbar machen, WORAUF ein "erledigt" beruht: 🍅 = echte
                    # Pomodoro-Zeit erfasst, ✍️ = manuell abgehakt (z. B. Programmier-
                    # aufgaben, die sich nicht sinnvoll per Timer tracken lassen - beide
                    # Wege bleiben gleichwertig moeglich, siehe Verbesserungsvorschlag).
                    _via = {"pomodoro": " 🍅", "manual": " ✍️"}.get(bl.get("done_via"), "")
                    _mark = f"✅{_via}" if bl["done"] else "⬜"
                    # Referenz des Themas: das Dokument, aus dem es entstanden ist.
                    _src_txt = (f" · 📄 {plan_cards.section_reference(section)}"
                                if section else "")
                    _su_b = _unit_stats.get(bl["section_id"]) or {}
                    _fill_txt = (f" · 🃏 {_su_b.get('cards', 0)} · 🧮 {_su_b.get('problems', 0)}"
                                 if section else "")
                    _focus_mark = " · 👈 Fokus" if bl["block_id"] in _focus_blocks else ""
                    bcol1, bcol2 = st.columns([4.2, 1])
                    bcol1.write(
                        f"{_mark} {title}{_src_txt} · {_fmt_min(bl['planned_min'])}"
                        f"{_fill_txt}{_focus_mark}")
                    if bcol2.button("Erledigt" if not bl["done"] else "↩️",
                                   key=f"splan_block_{bl['block_id']}", use_container_width=True):
                        manifest.set_block_done(bl["block_id"], not bl["done"],
                                                via=None if bl["done"] else "manual")
                        _new_status = manifest.sync_plan_status(_active_plan_id)
                        if _new_status == "done":
                            st.balloons()
                        st.rerun()
                    if not bl["done"]:
                        a1, a2, a3, a4, a5 = st.columns(5)
                        _blk_slot = st.container()   # Fortschritt direkt unter den Knoepfen
                        if a1.button("🍅 Pomodoro", key=f"splan_pomo_{bl['block_id']}",
                                     use_container_width=True,
                                     help="Startet einen Pomodoro-Arbeitsblock auf der "
                                          "Lernzeit-Seite; nach Abschluss gilt dieser "
                                          "Block automatisch als erledigt."):
                            st.session_state["pomo_prefill"] = {
                                "subject": _plan["subject"], "minutes": bl["planned_min"],
                                "block_id": bl["block_id"],
                            }
                            st.switch_page("pages/10_⏱️_Lernzeit.py")
                        if a2.button("Karten", key=f"splan_cards_{bl['block_id']}",
                                     use_container_width=True,
                                     help="Karten zu diesem Stoffabschnitt - gibt es noch keine, "
                                          "werden sie jetzt erzeugt"):
                            from ragapp.student_flow import prefill_from_plan_block
                            if section and not _ensure_cards(section, _blk_slot):
                                st.stop()
                            st.session_state["study_prefill"] = prefill_from_plan_block(
                                bl["block_id"], limit=12, mode="reveal")
                            st.switch_page("pages/4_🎓_Lernen.py")
                        if a3.button("Übung", key=f"splan_prac_{bl['block_id']}",
                                     use_container_width=True,
                                     help="Übung zu diesem Abschnitt - gibt es noch keine, "
                                          "wird sie jetzt aus dem Text des Themas erzeugt"):
                            _pid = _ensure_practice(section, _blk_slot) if section else None
                            if section and not _pid:
                                st.stop()
                            _prac = {
                                "source": "plan",
                                "subject": _plan.get("subject"),
                                "doc_ids": ([d for d, _n in plan_cards.section_docs(section)]
                                            if section else list(source_doc_ids)),
                                "topic": title,
                                "block_id": bl["block_id"],
                            }
                            if _pid:
                                _prac["problem_ids"] = [_pid]
                            st.session_state["practice_prefill"] = _prac
                            st.switch_page("pages/13_🧮_Übungsaufgaben.py")
                        if a4.button("Skript", key=f"splan_docs_{bl['block_id']}",
                                     use_container_width=True,
                                     help="20 Minuten in der Unterlage zu diesem Abschnitt"):
                            # Das Dokument UND die Seite, an der das Thema beginnt.
                            _did, _pg = (plan_cards.section_start(section) if section
                                         else (None, None))
                            st.session_state["skript_prefill"] = {
                                "subject": _plan.get("subject"),
                                "doc_id": _did or (source_doc_ids[0] if source_doc_ids else None),
                                "heading": title,
                                "page": _pg or 0,
                                "block_id": bl["block_id"],
                                "minutes": 20,
                            }
                            st.switch_page("pages/18_📖_Skript.py")
                        if a5.button("Verstehen", key=f"splan_verstehen_{bl['block_id']}",
                                     use_container_width=True,
                                     help="20 Minuten Dialog zu diesem Abschnitt"):
                            st.session_state["verstehen_prefill"] = {
                                "subject": _plan.get("subject"),
                                "topic": title,
                                "minutes": 20,
                                "block_id": bl["block_id"],
                                # Der Dialog sucht NUR im Dokument des Themas.
                                "doc_ids": ([d for d, _n in plan_cards.section_docs(section)]
                                            if section else []),
                                "reference": (plan_cards.section_reference(section)
                                              if section else ""),
                            }
                            st.switch_page("pages/0_💬_Chat.py")
