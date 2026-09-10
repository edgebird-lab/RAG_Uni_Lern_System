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

from ragapp.ui._loading import page_boot
page_boot("📋 Lernplan", page_title="Lernplan", icon="📋", layout="wide", accent="lernplan")

from ragapp.ui._style import card

st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1150px;}
h1 {font-weight: 750; letter-spacing:-0.5px;}
.splan-badge {display:inline-block; padding:2px 12px; border-radius:999px;
  font-size:.78rem; font-weight:650; letter-spacing:.2px;}
.splan-topic-card {border-radius:10px; padding:10px 12px; margin-bottom:8px;}
.splan-topic-title {font-weight:700; font-size:.92rem; margin-bottom:2px;}
.splan-topic-meta {font-size:.78rem; opacity:.85;}
.splan-tl-wrap {overflow-x:auto; padding:6px 2px 20px 2px;}
.splan-tl-row {display:flex; gap:4px; align-items:flex-end; height:56px; min-width:min-content;}
.splan-tl-seg {position:relative; flex:0 0 26px; height:100%; background:rgba(148,163,184,.16);
  border-radius:5px; overflow:hidden; display:flex; align-items:flex-end;}
.splan-tl-seg.splan-tl-today {box-shadow:0 0 0 2px #2563eb;}
.splan-tl-fill {width:100%;}
.splan-tl-label {position:absolute; bottom:-18px; left:0; right:0; text-align:center;
  font-size:9.5px; color:#94a3b8; white-space:nowrap;}
html.rag-dark .splan-tl-seg {background:rgba(148,163,184,.2);}
</style>
""", unsafe_allow_html=True)

st.caption("KI-Gliederung aus deinen Dokumenten + ein realistischer, auf Tage "
           "verteilter Lernplan – Zeitschätzungen sind formelbasiert aus "
           "Forschung zu Lesetempo & Lernrate, nicht geraten "
           "(Herleitung: docs/LERNPLAN_FORSCHUNG.md).")

with st.spinner("Lernplan wird geladen ..."):
    import html as _html
    import pandas as pd
    from ragapp import manifest, study_plan, planner
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
        st.info("Noch keine indexierten Dokumente (im RAG) vorhanden. Gehe zu "
                "**📥 Ingestion**, um welche hinzuzufügen.")
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
        st.info(f"📋 Vorbelegt aus den Dauerpatzern: "
               f"{len(_plan_prefill.get('doc_ids') or [])} Dokument(e) ausgewählt.")

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
                                    key="splan_new_docs")

    tc1, tc2, tc3 = st.columns(3)
    with tc1:
        _new_daily = st.number_input("Verfügbare Zeit/Tag (Min)", min_value=15, max_value=600,
                                     value=120, step=15, key="splan_new_daily")
        st.caption(f"Wird auf max. {settings.PLAN_MAX_DAILY_FOCUS_MIN} Min gedeckelt "
                   "(nachhaltige Tagesobergrenze, siehe Forschung).")
    with tc2:
        _has_deadline = st.checkbox("Zieldatum setzen", value=False, key="splan_new_has_deadline")
    with tc3:
        _new_deadline = (st.date_input("Zieldatum", value=date.today() + timedelta(days=7),
                                       key="splan_new_deadline") if _has_deadline else None)

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
        doc_ids = [_subj_docs[n] for n in _new_doc_names]
        with st.spinner("KI erstellt die Gliederung … das kann je nach Umfang und "
                        "Hardware einige Zeit dauern (siehe Schätzung oben)."):
            try:
                outline, _outline_warning = study_plan.generate_outline(
                    doc_ids, _new_subject, model=_new_model)
            except study_plan.OutlineError as exc:
                st.error(str(exc))
                st.stop()
        pid = manifest.create_study_plan(
            title=_new_title or f"Lernplan {_fach(_new_subject)}", subject=_new_subject,
            doc_ids=doc_ids, deadline=_new_deadline.isoformat() if _new_deadline else None,
            daily_minutes=int(_new_daily))
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

    _next_block = next((b for b in _blocks if not b["done"]), None)
    if _next_block is not None:
        _next_title = next((s["title"] for s in _sections
                            if s["section_id"] == _next_block["section_id"]), "Abschnitt")
        _nb_when = ("heute" if _next_block["planned_date"] == date.today().isoformat()
                   else _next_block["planned_date"])
        st.info(f"▶️ **Nächster Block:** {_next_title} · "
               f"{_fmt_min(_next_block['planned_min'])} · {_nb_when}")
    elif _total_planned_all:
        st.success("✅ Alle Blöcke dieses Plans sind erledigt.")

with st.expander("⚙️ Einstellungen & Löschen"):
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
    if st.button("💾 Einstellungen speichern", key=f"splan_save_settings_{_active_plan_id}"):
        manifest.update_study_plan(
            _active_plan_id, daily_minutes=int(_edit_daily),
            deadline=_edit_deadline.isoformat() if _edit_deadline else None)
        st.success("Gespeichert.")
        st.rerun()
    if st.button("🗑️ Plan löschen", key=f"splan_delete_{_active_plan_id}"):
        manifest.delete_study_plan(_active_plan_id)
        st.success("Plan gelöscht.")
        st.rerun()

_plan = manifest.get_study_plan(_active_plan_id)  # ggf. aktualisierte Werte nachladen

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

if st.button("🔄 Gliederung neu erzeugen", key=f"splan_regen_{_active_plan_id}"):
    with st.spinner("KI erstellt die Gliederung neu … das kann je nach Umfang und "
                    "Hardware einige Zeit dauern."):
        try:
            outline, _regen_warning = study_plan.generate_outline(
                _plan["doc_ids"], _plan["subject"], model=_regen_model)
        except study_plan.OutlineError as exc:
            st.error(str(exc))
            st.stop()
    manifest.replace_plan_sections(_active_plan_id, outline)
    if _regen_warning:
        st.session_state["_splan_gen_warning"] = _regen_warning
    else:
        st.success(f"Gliederung mit {len(outline)} Themen neu erzeugt.")
    st.rerun()

_splan_gen_warning = st.session_state.pop("_splan_gen_warning", None)
if _splan_gen_warning:
    st.warning(_splan_gen_warning)

if not _sections:
    st.info("Noch keine Gliederung vorhanden.")
else:
    _sec_orig = {s["section_id"]: s for s in _sections}

    st.markdown("###### Themen im Überblick")
    _tile_cols = st.columns(3)
    for _ti, _s in enumerate(_sections):
        with _tile_cols[_ti % 3]:
            _s_done = bool(_s.get("done"))
            _card_bg = "rgba(22,163,74,.12)" if _s_done else "rgba(148,163,184,.10)"
            _card_border = "#16a34a" if _s_done else _plan_color
            _summary = (_s.get("summary") or "").strip()
            _summary_short = (_summary[:90] + "…") if len(_summary) > 90 else _summary
            st.markdown(
                f"<div class='splan-topic-card' style='background:{_card_bg};"
                f"border-left:4px solid {_card_border};'>"
                f"<div class='splan-topic-title'>{'✅ ' if _s_done else ''}"
                f"{_s['order_index'] + 1}. {_html.escape(_s['title'])}</div>"
                f"<div class='splan-topic-meta'>{_fmt_min(_s['est_minutes'])}"
                + (f" · {_html.escape(_summary_short)}" if _summary_short else "")
                + "</div></div>", unsafe_allow_html=True)
            if st.button("🧮 Übungsaufgabe", key=f"splan_practice_{_s['section_id']}",
                        use_container_width=True):
                st.session_state["practice_prefill"] = {
                    "subject": _plan["subject"], "doc_ids": _plan["doc_ids"],
                    "topic": _s["title"],
                }
                st.switch_page("pages/13_🧮_Übungsaufgaben.py")

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
        } for row in kept]
        manifest.replace_plan_sections(_active_plan_id, new_sections)
        st.success("Gliederung gespeichert.")
        st.rerun()

    _total_min = sum(s["est_minutes"] for s in _sections)
    st.caption(f"Geschätzter Gesamtaufwand: **{_fmt_min(_total_min)}** für {len(_sections)} Themen.")

    # Live-Vorschau: rechnet bei JEDEM Rendern mit dem aktuell GESPEICHERTEN Stand
    # (Zeit/Tag, Zieldatum, Gliederung) - so ist die Engpass-/Deckelungs-Warnung
    # immer sichtbar, nicht nur direkt nach einem Klick auf "Plan berechnen".
    _preview = study_plan.build_schedule(
        [{"section_id": s["section_id"], "est_minutes": s["est_minutes"]} for s in _sections],
        daily_minutes=_plan["daily_minutes"], deadline=_plan.get("deadline"),
        subject=_plan["subject"])
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
                label = day[5:].replace("-", ".")
                segs.append(
                    f"<div class='splan-tl-seg{is_today}' "
                    f"title='{day}: {_fmt_min(done)} / {_fmt_min(total)}'>"
                    f"<div class='splan-tl-fill' style='height:{pct}%;background:{fill};'></div>"
                    f"<div class='splan-tl-label'>{label}</div></div>")
            return f"<div class='splan-tl-wrap'><div class='splan-tl-row'>{''.join(segs)}</div></div>"


        st.markdown(_render_timeline(_by_date, _plan_color), unsafe_allow_html=True)

        for d in sorted(_by_date.keys()):
            _day_blocks = _by_date[d]
            _label = "**Heute**" if d == date.today().isoformat() else d
            _day_done = sum(bl["planned_min"] for bl in _day_blocks if bl["done"])
            _day_total = sum(bl["planned_min"] for bl in _day_blocks)
            with st.expander(f"{_label} · {_fmt_min(_day_total)}"
                            + (" ✅" if _day_done == _day_total else ""),
                            expanded=(d == date.today().isoformat())):
                for bl in _day_blocks:
                    bcol1, bcol2, bcol3 = st.columns([4, 1.3, 1.3])
                    title = _sec_title.get(bl["section_id"], "Abschnitt")
                    # Ehrlich sichtbar machen, WORAUF ein "erledigt" beruht: 🍅 = echte
                    # Pomodoro-Zeit erfasst, ✍️ = manuell abgehakt (z. B. Programmier-
                    # aufgaben, die sich nicht sinnvoll per Timer tracken lassen - beide
                    # Wege bleiben gleichwertig moeglich, siehe Verbesserungsvorschlag).
                    _via = {"pomodoro": " 🍅", "manual": " ✍️"}.get(bl.get("done_via"), "")
                    _mark = f"✅{_via}" if bl["done"] else "⬜"
                    bcol1.write(f"{_mark} {title} · {_fmt_min(bl['planned_min'])}")
                    if bcol2.button("Erledigt" if not bl["done"] else "↩️",
                                   key=f"splan_block_{bl['block_id']}", use_container_width=True):
                        manifest.set_block_done(bl["block_id"], not bl["done"],
                                                via=None if bl["done"] else "manual")
                        _new_status = manifest.sync_plan_status(_active_plan_id)
                        if _new_status == "done":
                            st.balloons()
                        st.rerun()
                    if not bl["done"]:
                        if bcol3.button("🍅 Pomodoro", key=f"splan_pomo_{bl['block_id']}",
                                        use_container_width=True,
                                        help="Startet einen Pomodoro-Arbeitsblock auf der "
                                             "Lernzeit-Seite; nach Abschluss gilt dieser "
                                             "Block automatisch als erledigt."):
                            st.session_state["pomo_prefill"] = {
                                "subject": _plan["subject"], "minutes": bl["planned_min"],
                                "block_id": bl["block_id"],
                            }
                            st.switch_page("pages/10_⏱️_Lernzeit.py")
