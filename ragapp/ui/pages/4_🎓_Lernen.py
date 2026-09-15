"""
RAG-Lernsystem: Seite „Lernen" (Karteikarten + Spaced Repetition)
=================================================================
Aktives Ueben statt nur Nachschlagen: Die App erntet aus dem schon indexierten
Fragenmaterial (Klausur-Katalog + generierte Fragen) Karteikarten und plant sie
mit FSRS-6 (verteiltes Wiederholen). Alles offline, ohne LLM zur Laufzeit.
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
import streamlit.components.v1 as components

from ragapp.ui._loading import page_boot, skeleton

# set_page_config -> PIN-Gate -> Theme -> und rendert SOFORT den Seitentitel,
# damit beim Seitenwechsel kein weisser Bildschirm entsteht.
page_boot("🎓 Karteikarten", page_title="Karteikarten", icon="🎓", layout="wide", accent="lernen")

from ragapp.ui._style import block_done_banner, delete_button, seed_selectbox_from_query, sync_query_param

# Nur noch das seiten-spezifische Layout; die Karteikarten-Optik (hell + dunkel)
# kommt jetzt zentral aus ragapp.ui._theme.apply_theme().
st.markdown("""
<style>
.block-container {max-width: 900px;}
</style>
""", unsafe_allow_html=True)


# Schwere Importe/Datenabfragen unter kleinem Ladehinweis; die import-Statements
# binden im Modulscope, daher funktionieren alle spaeteren Verwendungen unveraendert.
with skeleton("Karteikarten werden geladen …"):
    import pandas as pd
    from ragapp import manifest, study
    from ragapp.config import settings, SUBJECT_LABELS


def _fach_label(code: str) -> str:
    return SUBJECT_LABELS.get(code, code)


def _render_karte(text: str, *, kind: str = "front") -> None:
    """Kartenfläche mit Markdown/KaTeX – nicht als HTML-Div (sonst bleiben $...$ roh)."""
    from ragapp.student_flow import normalize_card_latex
    body = normalize_card_latex(text)
    key = {"front": "karte_front", "back": "karte_back", "cloze": "karte_cloze"}.get(
        kind, "karte_front")
    with st.container(key=key):
        st.markdown(body or "")


def _show_answer_result(ares: dict) -> bool:
    """Meldung nach generate_answers. True, wenn etwas gespeichert wurde (dann rerun)."""
    filled = int(ares.get("filled") or 0)
    ungrounded = int(ares.get("ungrounded") or 0)
    unchecked = int(ares.get("unchecked") or 0)
    if ares.get("status") == "llm_error":
        st.error(f"❌ Modellfehler: {ares.get('error_msg', '')} – prüfe unter "
                 "**⚙️ Einstellungen** ein laufendes Modell.")
        return False
    if ares.get("status") == "nothing_to_do":
        st.info("Alle Karten haben bereits eine Antwort.")
        return False
    if filled == 0:
        if ungrounded:
            st.warning(
                f"Keine Musterlösung gespeichert: {ungrounded} Antwort(en) "
                "waren nicht durch den Abschnitt gedeckt.")
        else:
            st.warning("Es konnte keine Antwort erzeugt werden (der Text gab nichts her).")
        return False
    msg = f"✅ {filled} Musterlösung(en) erzeugt."
    if ungrounded:
        msg += f" {ungrounded} verworfen (nicht im Beleg)."
    if unchecked:
        msg += f" {unchecked} ohne klare Prüfung behalten."
    st.success(msg)
    return True


def _show_recheck_result(rres: dict) -> bool:
    """Meldung nach recheck_answers. True, wenn sich Karten geändert haben."""
    if rres.get("status") == "llm_error":
        st.error(f"❌ Modellfehler: {rres.get('error_msg', '')} – prüfe unter "
                 "**⚙️ Einstellungen** ein laufendes Modell.")
        return False
    if rres.get("status") == "nothing_to_do":
        st.info("Keine gespeicherten Musterlösungen zum Prüfen.")
        return False
    cleared = int(rres.get("cleared") or 0)
    kept = int(rres.get("kept") or 0)
    unknown = int(rres.get("unknown") or 0)
    tidied = int(rres.get("tidied") or 0)
    msg = f"{kept} belegt behalten"
    if cleared:
        msg += f", {cleared} unbelegt entfernt"
    if unknown:
        msg += f", {unknown} ohne klare Prüfung behalten"
    if tidied:
        msg += f", {tidied} Formel geglättet"
    st.success(msg + ".")
    return bool(cleared or tidied)


# --------------------------------------------------------------------------- #
# Karten-Bestand
# --------------------------------------------------------------------------- #
_counts = manifest.review_counts()

# Ganz oben zeigen, VOR dem "keine Karten"-Abbruch (st.stop() unten): wer
# gerade seine letzten Karten geloescht hat, faellt direkt in den leeren
# Zustand - die Erfolgsmeldung stand vorher weiter unten und wurde dann nie
# angezeigt (per Live-Test gefunden: "alle loeschen" landet oft genau hier).
_mv_flash = st.session_state.pop("_mv_flash", None)
if _mv_flash:
    st.success(_mv_flash)

def _render_lernset_pfad(*, heading: bool = True) -> None:
    """Standardweg: Dokumente wählen → Lernset erstellen → Vorschau → Jetzt lernen."""
    from ragapp.ui._style import empty_state, page_title as _pt

    docs = [dict(r) for r in manifest.list_documents()]
    if heading:
        st.markdown("##### Lernset erstellen")
    st.caption("Wähle Unterlagen, erzeuge in einem Schritt Fragen und Karten, "
               "prüfe die Vorschau und starte die erste Runde.")
    if not docs:
        empty_state(
            "Noch keine Unterlagen. Lade zuerst Dateien hoch, danach wird hier "
            "das Lernset gebaut – nicht über Chunk-Limits.",
            cta_label=f"Zu {_pt('dokumente')}",
            page_key="dokumente",
            icon="🗃️",
            key="lernset_to_dokumente",
        )
        return

    _pre = st.session_state.pop("lernset_docs_prefill", None)
    if _pre and "lernset_docs" not in st.session_state:
        st.session_state["lernset_docs"] = [i for i in _pre if i in {d["doc_id"] for d in docs}]

    labels = {
        d["doc_id"]: f'{d.get("filename") or d["doc_id"]} · {_fach_label(d.get("subject") or "")}'
        for d in docs
    }
    picked = st.multiselect(
        "Dokumente", list(labels),
        format_func=lambda i: labels.get(i, i),
        key="lernset_docs",
    )
    if st.button("Lernset erstellen",
                 type="secondary" if _needs_harvest else "primary",
                 disabled=not picked,
                 key="lernset_go", use_container_width=True):
        with st.status("Lernset wird erzeugt …", expanded=True) as s:
            out = study.create_study_set(
                picked, n_per_chunk=1, progress=lambda m: s.update(label=m))
            s.update(label="Fertig" if out["status"] == "ok" else "Abgebrochen",
                     state="complete" if out["status"] == "ok" else "error")
        st.session_state["_lernset_result"] = out
        st.rerun()

    out = st.session_state.get("_lernset_result")
    if not out:
        return
    if out.get("status") != "ok":
        st.error(out.get("error_msg") or "Lernset konnte nicht erzeugt werden.")
        return
    prev = out.get("preview") or {}
    st.success(
        f'{out.get("questions", 0)} Fragen · {out.get("cards_new", 0)} neue Karten'
        + (f' · {out.get("answers", 0)} Antworten' if out.get("answers") else "")
        + "."
    )
    st.caption(
        f'{prev.get("cards", 0)} Karten insgesamt · {prev.get("unanswered", 0)} ohne Antwort'
        + (f' · Themen: {", ".join(prev.get("topics") or [])}' if prev.get("topics") else "")
    )
    for ex in prev.get("examples") or []:
        st.markdown(f"- {ex.get('front') or ''}")
    if st.button("Dieses Lernset lernen", key="lernset_now",
                 use_container_width=True):
        st.session_state["study_prefill"] = {
            "source": "lernset", "limit": 16, "mode": "reveal",
            "doc_ids": prev.get("doc_ids") or picked,
            "card_ids": prev.get("card_ids") or [
                ex.get("card_id") for ex in (prev.get("examples") or [])
                if ex.get("card_id")
            ],
            "topics": prev.get("topics") or [],
        }
        st.session_state.pop("_lernset_result", None)
        st.rerun()


def _render_karten_erstellen() -> None:
    """Fragen anreichern, Katalog, Ernten – auch im leeren Zustand sichtbar."""
    from ragapp.ui import _ingest_ui

    st.caption("Karten kommen aus dem generierten Fragenmaterial. Wähle, aus welchem "
               "Fach und wie viele Fragen je Textabschnitt du aufnimmst.")
    cc1, cc2, cc3 = st.columns(3)
    _hv_subj = cc1.selectbox("Fach", ["Alle Fächer"] + manifest.study_subjects(),
                             format_func=lambda s: "Alle Fächer" if s == "Alle Fächer"
                             else _fach_label(s), key="hv_subj")
    _hv_max = cc2.number_input("Max. Fragen pro Chunk", min_value=0, max_value=20, value=0,
                               step=1, key="hv_max",
                               help="0 = alle vorhandenen Fragen aufnehmen.")
    _hv_subj_arg = None if _hv_subj == "Alle Fächer" else _hv_subj
    _hv_max_arg = int(_hv_max) or None
    if cc3.button("🔄 Karten aktualisieren", use_container_width=True):
        with st.status("Aktualisiere …", expanded=True) as s:
            res = study.harvest_cards(subject=_hv_subj_arg, max_per_chunk=_hv_max_arg,
                                      progress=lambda m: s.update(label=m))
            s.update(label="Aktualisierung fertig", state="complete")
        if res["gefunden"] == 0:
            st.warning("Kein Fragenmaterial gefunden – zuerst unten Fragen anreichern "
                       "oder den Klausur-Lernkatalog erzeugen. Dokumente liegen unter "
                       "**🗃️ Dokumente**.")
        elif res["neu"] == 0:
            st.info("Alles aktuell – keine neuen Karten.")
        else:
            st.success(f"➕ {res['neu']} neue Karten hinzugefügt.")
            st.rerun()

    st.divider()
    _offen = manifest.count_cards(subject=_hv_subj_arg, source="question", only_unanswered=True)
    st.caption(f"**Musterlösungen erzeugen:** {_offen} Karte(n) zeigen bisher nur den "
               "Originaltext. Die KI erzeugt daraus echte Antworten und prüft jede "
               "gegen den Abschnitt. Nur klar unbelegte Antworten werden verworfen; "
               "scheitert die Prüfung, bleibt die Lösung.")
    ca1, ca2 = st.columns([1, 2])
    _ans_n = ca1.number_input("Anzahl", min_value=1, max_value=500,
                              value=min(20, max(1, _offen)), step=5, key="ans_n",
                              disabled=_offen == 0)
    if ca2.button(f"🤖 Antworten erzeugen ({_offen} offen)", disabled=_offen == 0,
                  use_container_width=True):
        with st.status("Erzeuge Musterlösungen …", expanded=True) as s:
            ares = study.generate_answers(subject=_hv_subj_arg, limit=int(_ans_n),
                                          progress=lambda m: s.update(label=m))
            s.update(label="Fertig", state="complete")
        if _show_answer_result(ares):
            st.rerun()

    _mit_antw = max(0, manifest.count_cards(subject=_hv_subj_arg, source="question") - _offen)
    st.caption(f"**Belege nachprüfen:** {_mit_antw} gespeicherte Lösung(en). "
               "Nur klar unbelegte werden entfernt; Formeln werden mitgeglättet.")
    rc1, rc2 = st.columns([1, 2])
    _rc_n = rc1.number_input("Anzahl", min_value=1, max_value=500,
                             value=min(50, max(1, _mit_antw)), step=5, key="recheck_n",
                             disabled=_mit_antw == 0)
    if rc2.button(f"🔎 Belege prüfen ({_mit_antw})", disabled=_mit_antw == 0,
                  use_container_width=True):
        with st.status("Prüfe Belege …", expanded=True) as s:
            rres = study.recheck_answers(subject=_hv_subj_arg, limit=int(_rc_n),
                                         progress=lambda m: s.update(label=m))
            s.update(label="Fertig", state="complete")
        if _show_recheck_result(rres):
            st.rerun()

    st.divider()
    _ingest_ui.render_enrich()
    _ingest_ui.render_exam_catalog()


# Bestand kompakt – die nächste Tat ist Stapel + Jetzt lernen, nicht vier Kacheln.
if _counts["total"] > 0:
    _bd_all = manifest.due_breakdown()
    _rest_neu_all = manifest.remaining_new_quota()
    _new_show = (_bd_all["due_new"] if _rest_neu_all is None
                 else min(_bd_all["due_new"], _rest_neu_all))
    _due_now = manifest.effective_due_count()
    with st.expander(
            f"Bestand · {_counts['total']} Karten · {_due_now} fällig",
            expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Karten gesamt", _counts["total"])
        c2.metric("Jetzt fällig", _due_now,
                 help="Lernen + Wiederholen + neue Karten bis zum Tageskontingent "
                      "(Einstellungen → Neue Karten pro Tag).")
        c3.metric("Neu heute", _new_show,
                  help="Brandneue Karten, die heute noch eingeführt werden können "
                       f"(Tageskontingent: "
                       f"{'unbegrenzt' if int(getattr(settings, 'SRS_NEW_PER_DAY', 20)) <= 0 else int(getattr(settings, 'SRS_NEW_PER_DAY', 20))}"
                       "). Nicht die Rundengröße.")
        c4.metric("Wiederholen", _bd_all["due_review"] + _bd_all["due_learning"],
                  help="Fällige Wiederholungen inkl. Lern-/Relearn-Schritte.")

_in_round = bool(st.session_state.get("_study_active"))
_needs_harvest = study.needs_card_harvest() or st.session_state.pop("_needs_card_harvest", None)
_offen_global = manifest.count_cards(source="question", only_unanswered=True)

st.divider()

# --------------------------------------------------------------------------- #
# Lernen (Anki-artig) / aktive Sitzung
# --------------------------------------------------------------------------- #
Q = "_study_queue"
ACTIVE = "_study_active"
REVEAL = "_study_reveal"
TALLY = "_study_tally"
ROUND = "_study_round"
_MODE_MAP = {"👁️ Aufdecken": "reveal", "✍️ Tippen & benoten": "type",
             "🧩 Lückentext": "cloze", "🔤 Multiple Choice": "mcq"}
_MODE_LABELS = list(_MODE_MAP.keys())


def _start_study(karten: list, mode: str) -> None:
    """Gemeinsamer Sitzungsstart fuer Standard-Lernen und Challenge."""
    st.session_state[Q] = karten
    st.session_state[ACTIVE] = True
    st.session_state[REVEAL] = False
    st.session_state[TALLY] = {"gewusst": 0, "halb": 0, "nicht": 0}
    st.session_state["_session_jol"] = {"n": 0, "sicher_wrong": 0}
    st.session_state["_study_combo"] = 0
    st.session_state["_study_combo_best"] = 0
    st.session_state["_study_leech_cleared"] = 0
    st.session_state[ROUND] = len(karten)
    st.session_state["_study_mode"] = mode


_prefill = st.session_state.get("study_prefill")
if _prefill and not st.session_state.get(ACTIVE):
    _src = _prefill.get("source") or _prefill.get("mode") or "Sitzung"
    _subj_txt = _fach_label(_prefill["subject"]) if _prefill.get("subject") else "alle Fächer"
    _lim = int(_prefill.get("limit") or 16)
    with st.container(border=True):
        st.markdown("##### Sitzung vorbereitet")
        st.caption(f"{_src} · {_subj_txt} · bis zu {_lim} Karten. "
                   "Startest du jetzt, oder wählst du unten selbst einen Stapel?")
        _pf1, _pf2 = st.columns(2)
        if _pf1.button("▶️ Jetzt starten", type="primary", key="prefill_go",
                       use_container_width=True):
            _prefill = st.session_state.pop("study_prefill", {}) or {}
            from ragapp import student_flow as _sf
            if _prefill.get("sprint") or _prefill.get("mode") == "sprint":
                st.session_state["_study_sprint"] = True
                st.session_state["_study_sprint_prefer"] = _prefill.get("prefer") or "auto"
            if _prefill.get("block_id"):
                st.session_state["_study_from_block_id"] = _prefill["block_id"]
            _pk = _sf.cards_for_prefill(_prefill)
            _pmode = _prefill.get("mode") or "reveal"
            if _pmode == "sprint":
                _pmode = "reveal"
            if _pk:
                _start_study(_pk, _pmode if _pmode in ("reveal", "type", "cloze", "mcq") else "reveal")
                st.rerun()
            else:
                st.info("Keine passenden Karten für diesen Start – wähle unten einen Stapel.")
        if _pf2.button("Stapel selbst wählen", key="prefill_skip",
                       use_container_width=True):
            st.session_state.pop("study_prefill", None)
            st.rerun()


if not st.session_state.get(ACTIVE):
    block_done_banner(state_key="_study_from_block_id", key_prefix="study")


if not st.session_state.get(ACTIVE):
    if _counts["total"] == 0:
        _render_lernset_pfad()
        st.stop()
    st.subheader("Stapel")
    st.caption("Fach, dann **Jetzt lernen**. Stapel nur ankreuzen, wenn nicht alle.")

    _faecher = manifest.study_subjects()
    _subj_opts = ["Alle Fächer"] + _faecher
    seed_selectbox_from_query("study_subj", _subj_opts)
    _subj_pick = st.selectbox(
        "Fach", _subj_opts,
        format_func=lambda s: "Alle Fächer" if s == "Alle Fächer" else _fach_label(s),
        key="study_subj")
    subj = None if _subj_pick == "Alle Fächer" else _subj_pick
    sync_query_param("fach", subj)

    if subj:
        from ragapp import planner, analytics
        _ex = manifest.get_exam(subj)
        if _ex and _ex.get("exam_date"):
            _dte = planner.days_to_exam(_ex["exam_date"])
            _rd = analytics.subject_readiness(subj)["retention_pct"]
            st.caption(
                f"Termin {planner.humanize_days(_dte)} ({_ex['exam_date']}) · "
                f"Behalten {_rd} %"
            )

    # Auswahl aus dem letzten Lauf (Default: alle). Tabelle erst NACH der
    # Hauptaktion, damit „Jetzt lernen“ auf dem Handy im ersten Screen liegt.
    _ov_rows = manifest.deck_overview(subject=subj, only_flashcard=True)
    _deck_keys: list[str] = []
    for _o in _ov_rows:
        _deck_keys.append("__none__" if not _o.get("deck") else str(_o["deck"]))

    _sel_key = f"_study_deck_sel::{subj or '__all__'}"
    if _sel_key not in st.session_state:
        st.session_state[_sel_key] = set(_deck_keys)

    _selected = [k for k in _deck_keys if k in st.session_state[_sel_key]]
    decks = _selected if _selected else None
    # Leere Auswahl = bewusst nichts lernen (nicht "alle")
    if _ov_rows and not _selected:
        decks = []

    _breakdown = (manifest.due_breakdown(subj, decks=decks)
                  if decks is not None else
                  {"due_learning": 0, "due_review": 0, "due_new": 0})
    _neu_heute = (manifest.count_new_today(subj, decks=decks)
                  if decks is not None else 0)
    _rest_neu = manifest.remaining_new_quota(subj, decks=decks) if decks is not None else 0
    _new_eff = (0 if decks is None or decks == []
                else (_breakdown["due_new"] if _rest_neu is None
                      else min(_breakdown["due_new"], _rest_neu)))
    faellig = (_breakdown["due_learning"] + _breakdown["due_review"] + _new_eff
               if decks is not None else 0)

    _npd = int(getattr(settings, "SRS_NEW_PER_DAY", 20))
    _npd_txt = "unbegrenzt" if _npd <= 0 else str(_npd)
    st.caption(
        f"**{_breakdown.get('due_review', 0)}** Wdh. · "
        f"**{_breakdown.get('due_learning', 0)}** Lernen · "
        f"**{_new_eff}**/{_npd_txt} neu"
        + (f" · heute {_neu_heute}" if _neu_heute else "")
    )

    # Primary CTA before alerts/mode so the phone bar cannot cover it.
    _mode_lbl = st.session_state.get("study_mode_choice", _MODE_LABELS[0])
    if st.button(
        "▶️ Jetzt lernen",
        type="primary",
        use_container_width=True,
        key="start_study",
        disabled=not decks or faellig == 0,
        help="Zieht Lernen → Wiederholen → neue Karten bis zum Tageskontingent.",
    ):
        karten = manifest.gather_study_cards(subj, decks=decks)
        if not karten:
            st.warning("Für diese Auswahl wurden keine Karten gefunden.")
        else:
            _start_study(karten, _MODE_MAP[_mode_lbl])
            st.rerun()

    if decks == []:
        st.warning("Kein Stapel ausgewählt – mindestens einen ankreuzen.")
    elif faellig == 0:
        st.success("Nichts fällig. Später wiederkommen oder unten Cram.")

    _mode_lbl = st.selectbox(
        "Übungsmodus",
        _MODE_LABELS,
        key="study_mode_choice",
        help="**Aufdecken**: klassisch. **Tippen & benoten**: KI-Teilpunkte. "
             "**Lückentext** / **Multiple Choice**: andere Abfrageformen.")
    _go2, _go3, _go4 = st.columns(3)
    if _go2.button("🔥 Cram", use_container_width=True, disabled=not decks):
        karten = manifest.get_due_cards(subj, limit=20, cram=True,
                                        decks=decks if decks else None)
        if karten:
            _start_study(karten, _MODE_MAP[_mode_lbl])
            st.rerun()
        else:
            st.warning("Keine Karten für Cram.")
    if _go3.button("⚡ Sprint", use_container_width=True, disabled=not decks,
                   help="Formel- und Definitionskarten der angekreuzten Stapel. "
                        "Formeln zuerst, falls welche da sind – sonst kurze Definitionen."):
        from ragapp import student_flow as _sf
        _inv = _sf.sprint_inventory(subject=subj, decks=decks)
        if _inv["formula_n"]:
            karten = _sf.sprint_cards(subject=subj, decks=decks, limit=12, prefer="auto")
            st.session_state["_study_sprint"] = True
            st.session_state["_study_sprint_prefer"] = "auto"
            _start_study(karten, "reveal")
            st.rerun()
        elif _inv["definition_n"]:
            karten = _sf.sprint_cards(subject=subj, decks=decks, limit=12,
                                      prefer="definition")
            st.session_state["_study_sprint"] = True
            st.session_state["_study_sprint_prefer"] = "definition"
            st.info(f"Keine Formeln in dieser Auswahl – Sprint mit "
                    f"{_inv['definition_n']} kurzen Definitionen.")
            _start_study(karten, "reveal")
            st.rerun()
        else:
            st.warning("Keine Formeln und keine kurzen Definitionen in den "
                       "angekreuzten Stapeln. Anderes Fach/anderen Stapel wählen.")
    if _go4.button("📒 Fehlerheft", use_container_width=True):
        from ragapp import student_flow as _sf
        karten = _sf.fehlerheft_cards(limit=15, subject=subj)
        if karten:
            _start_study(karten, _MODE_MAP[_mode_lbl])
            st.rerun()
        else:
            st.info("Fehlerheft ist leer – gut so.")

    if _needs_harvest and not _in_round:
        _nh1, _nh2 = st.columns([3, 1])
        _nh1.info("Neue Fragen wurden indexiert. Übernimm sie jetzt als Karteikarten.")
        if _nh2.button("🔄 Karten aktualisieren", type="primary", key="top_harvest",
                       use_container_width=True):
            with st.status("Aktualisiere …", expanded=True) as s:
                res = study.harvest_cards(progress=lambda m: s.update(label=m))
                s.update(label="Aktualisierung fertig", state="complete")
            if res["gefunden"] == 0:
                st.warning("Kein Fragenmaterial gefunden.")
            elif res["neu"] == 0:
                st.info("Alles aktuell – keine neuen Karten.")
                st.rerun()
            else:
                st.success(f"➕ {res['neu']} neue Karten hinzugefügt.")
                st.rerun()

    if _offen_global > 0 and not _in_round:
        _aw1, _aw2 = st.columns([3, 1])
        _aw1.warning(
            f"**{_offen_global} Karte(n) ohne Musterlösung** – beim Üben siehst du sonst nur "
            "den Originaltext. Erzeuge Antworten unter **⚙️ Karten verwalten**.")
        if _aw2.button("🤖 Antworten erzeugen", key="quick_ans", use_container_width=True):
            with st.status("Erzeuge Musterlösungen …", expanded=True) as s:
                ares = study.generate_answers(
                    limit=min(20, _offen_global),
                    progress=lambda m: s.update(label=m))
                s.update(label="Fertig", state="complete")
            if _show_answer_result(ares):
                st.rerun()

    _err_open = manifest.list_errors(limit=8)
    if _err_open:
        with st.expander(
                f"📒 Fehlerheft ({manifest.count_open_errors()} offen)",
                expanded=False):
            st.caption("Offene Lücken – üben oder als erledigt abhaken.")
            for _err in _err_open:
                _e1, _e2, _e3 = st.columns([3.2, 1, 1])
                _e1.write((_err.get("front") or _err.get("detail") or "Eintrag")[:90])
                if _e2.button("Üben", key=f"err_practice_{_err['error_id']}",
                              use_container_width=True):
                    st.session_state["study_prefill"] = {
                        "source": "fehlerheft", "deck": "Fehlerheft",
                        "mode": "reveal", "limit": 15,
                        "subject": _err.get("subject"),
                        "card_ids": (
                            [_err["card_id"]] if _err.get("card_id") else []),
                    }
                    st.rerun()
                if _e3.button("Erledigt", key=f"err_done_{_err['error_id']}",
                              use_container_width=True):
                    manifest.resolve_error(_err["error_id"])
                    st.rerun()

    with st.expander(
            (f"Stapel ankreuzen · {len(_selected)} von {len(_deck_keys)}"
             if _deck_keys else "Stapel ankreuzen"),
            expanded=False):
        if not _ov_rows:
            st.info("Keine Karten in dieser Auswahl.")
        else:
            _sa1, _sa2 = st.columns(2)
            if _sa1.button("Alle Stapel", key="deck_sel_all",
                           use_container_width=True):
                st.session_state[_sel_key] = set(_deck_keys)
                for _dk in _deck_keys:
                    st.session_state[f"deck_cb_{subj or 'all'}_{_dk}"] = True
                st.rerun()
            if _sa2.button("Keine Stapel", key="deck_sel_none",
                           use_container_width=True):
                st.session_state[_sel_key] = set()
                for _dk in _deck_keys:
                    st.session_state[f"deck_cb_{subj or 'all'}_{_dk}"] = False
                st.rerun()
            _picked: list[str] = []
            _h1, _h2, _h3, _h4, _h5 = st.columns([0.5, 3.5, 1, 1, 1])
            _h1.caption("")
            _h2.caption("Stapel")
            _h3.caption("Neu")
            _h4.caption("Lernen")
            _h5.caption("Wiederholen")
            for _o in _ov_rows:
                _dk = "__none__" if not _o.get("deck") else str(_o["deck"])
                _label = "— ohne Stapel —" if _dk == "__none__" else _dk
                _c1, _c2, _c3, _c4, _c5 = st.columns([0.5, 3.5, 1, 1, 1])
                _checked = _c1.checkbox(
                    "✓", key=f"deck_cb_{subj or 'all'}_{_dk}",
                    value=_dk in st.session_state[_sel_key],
                    label_visibility="collapsed")
                if _checked:
                    _picked.append(_dk)
                _c2.markdown(f"**{_label}** · {_o['total']} Karten")
                _c3.write(str(_o["new"]))
                _c4.write(str(_o["learning"]))
                _c5.write(str(_o["review"]))
            st.session_state[_sel_key] = set(_picked)

    with st.expander(
            "Lernset erstellen",
            expanded=bool(st.session_state.get("_lernset_result")
                          or st.session_state.get("lernset_docs_prefill"))):
        _render_lernset_pfad(heading=False)

    # --- Karten ankreuzen (dauerhaft use_flashcard) ---
    with st.expander("Karten fürs Lernen ankreuzen", expanded=False):
        st.caption("Abgewählte Karten bleiben gespeichert, erscheinen aber nicht in "
                   "Lernsitzungen (wie Anki Suspend / Browser).")
        if not decks:
            st.caption("Zuerst oben mindestens einen Stapel ankreuzen.")
        else:
            _browse = []
            for _dk in decks:
                _browse.extend(manifest.list_cards(
                    subject=subj, deck=_dk, limit=500))
            # Dedup by card_id
            _seen_ids: set[str] = set()
            _browse_u = []
            for _r in _browse:
                if _r["card_id"] in _seen_ids:
                    continue
                _seen_ids.add(_r["card_id"])
                _browse_u.append(_r)
            if not _browse_u:
                st.caption("Keine Karten in den gewählten Stapeln.")
            else:
                _bdf = pd.DataFrame([{
                    "Lernen": bool(r.get("use_flashcard", 1)),
                    "Frage": (r.get("front") or "")[:120],
                    "Stapel": r.get("deck") or "—",
                    "_id": r["card_id"],
                } for r in _browse_u])
                _bed = st.data_editor(
                    _bdf, hide_index=True, use_container_width=True,
                    key="browse_flash_editor",
                    column_config={
                        "Lernen": st.column_config.CheckboxColumn(width="small"),
                        "Frage": st.column_config.TextColumn(disabled=True),
                        "Stapel": st.column_config.TextColumn(disabled=True),
                        "_id": None,
                    },
                )
                if st.button("Auswahl speichern", key="browse_flash_save"):
                    _on = [row["_id"] for _, row in _bed.iterrows() if row["Lernen"]]
                    _off = [row["_id"] for _, row in _bed.iterrows() if not row["Lernen"]]
                    if _on:
                        manifest.set_card_usage(_on, use_flashcard=True)
                    if _off:
                        manifest.set_card_usage(_off, use_flashcard=False)
                    st.success("Gespeichert.")
                    st.rerun()

    # --- Challenge: bisheriger Runden-Baukasten ---
    with st.expander("🏆 Challenge – Themen mischen", expanded=False):
        st.caption("Cram und Sprint liegen oben bei **Jetzt lernen**. "
                   "Schriftlich und mündlich mit Zeitlimit stehen unter **Prüfung**. "
                   "Hier nur: Themen verschränken oder alle Fächer in einer Kartenrunde.")
        _srs_max = int(getattr(settings, "SRS_MAX_PER_SESSION", 100))
        _ch_decks = decks if decks else None
        _ch_fc = manifest.review_counts(subj, decks=_ch_decks) if _ch_decks is not None else {"total": 0}
        _ch_bd = (manifest.due_breakdown(subj, decks=_ch_decks)
                  if _ch_decks is not None else
                  {"due_learning": 0, "due_review": 0, "due_new": 0})
        _ch_rest = (manifest.remaining_new_quota(subj, decks=_ch_decks)
                    if _ch_decks is not None else 0)
        _ch_faellig = (
            _ch_bd["due_learning"] + _ch_bd["due_review"]
            + (_ch_bd["due_new"] if _ch_rest is None else min(_ch_bd["due_new"], _ch_rest or 0))
        )
        _ck1, _ck2 = st.columns(2)
        _interleave = _ck1.checkbox(
            "🔀 Themen mischen (Interleaving)", value=False, key="ch_interleave",
            help="Mischt Karten verschränkt über Themen statt blockweise.")
        _cram = _ck2.checkbox(
            "🔥 Klausur-Modus (Cram)", value=False, key="ch_cram",
            help="Auch noch nicht fällige, schwache Karten ziehen.")
        if len(_faecher) >= 2:
            with st.container(border=True):
                st.markdown("**Alle Fächer in einer Runde**")
                st.caption("Gemischte Karteikarten – keine Simulation mit Zeitlimit.")
                _pp1, _pp2, _pp3 = st.columns([1, 1, 1])
                _pp_n = _pp1.number_input(
                    "Karten", min_value=5, max_value=_srs_max, value=20,
                    step=5, key="phase_n")
                _pp_cram = _pp2.checkbox("🔥 Cram", key="phase_cram")
                if _pp3.button("▶️ Gemischte Runde", key="phase_start",
                               use_container_width=True):
                    from ragapp import planner as _pl
                    _pk = _pl.phase_round(limit=int(_pp_n), cram=bool(_pp_cram))
                    if not _pk:
                        st.info("Nichts fällig – aktiviere 🔥 Cram.")
                    else:
                        _start_study(_pk, _MODE_MAP[_mode_lbl])
                        st.rerun()
                if st.button("📝 Zur Prüfung", key="phase_to_exam",
                             use_container_width=True):
                    st.session_state["exam_prefill"] = {"mode": "written"}
                    st.switch_page("pages/6_📝_Prüfung.py")
        if _ch_faellig == 0 and not _cram:
            st.caption("Nichts fällig – Cram aktivieren oder später wiederkommen.")
        else:
            _cap = _ch_fc.get("total", 0) if _cram else max(1, _ch_faellig)
            _maxr = int(max(1, min(_cap, _srs_max)))
            # Streamlit verbietet min_value == max_value (Live-Test nach kurzer Runde).
            if _maxr < 2:
                anzahl = 1
                st.caption("Nur eine Karte in dieser Auswahl.")
            else:
                anzahl = st.slider(
                    "Karten in dieser Challenge", min_value=1, max_value=_maxr,
                    value=int(min(20, _maxr)), key="ch_anzahl")
            if st.button(
                f"▶️ Challenge starten ({anzahl}"
                + (" · 🔥 Cram" if _cram else "") + ")",
                use_container_width=True, key="ch_start",
                disabled=_ch_decks is None or _ch_decks == [],
            ):
                karten = manifest.get_due_cards(
                    subj, limit=int(anzahl), decks=_ch_decks,
                    new_limit=_ch_rest, order="interleave" if _interleave else "due",
                    cram=_cram)
                if not karten:
                    st.warning("Keine Karten für diese Challenge.")
                else:
                    _start_study(karten, _MODE_MAP[_mode_lbl])
                    st.rerun()

else:
    queue = st.session_state.get(Q) or []
    tally = st.session_state.get(TALLY, {"gewusst": 0, "halb": 0, "nicht": 0})

    if not queue:
        # Runde fertig
        beantwortet = sum(tally.values())
        st.success(f"🎉 Runde geschafft! **{beantwortet}** Karten geübt.")
        _jol_sess = st.session_state.get("_session_jol") or {}
        _sw = int(_jol_sess.get("sicher_wrong") or 0)
        if _sw:
            st.info(
                f"{_sw}× warst du sicher und lagst daneben. Das markiert eine harte Lücke, "
                "kein Versagen – die Karten landen im Fehlerheft.")
        elif int(_jol_sess.get("n") or 0):
            st.caption("Sicherheit und Ergebnis lagen in dieser Runde nah beieinander.")
        _combo_best = st.session_state.get("_study_combo_best", 0)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("✅ Gewusst", tally["gewusst"])
        m2.metric("🟡 Halb", tally["halb"])
        m3.metric("❌ Nicht", tally["nicht"])
        if _combo_best >= 2:
            m4.metric("🔥 Beste Serie", _combo_best)

        # Errungenschaften direkt HIER pruefen (nicht erst beim naechsten
        # Fortschritt-Besuch) - der eigentliche Feiermoment ist JETZT, direkt
        # nach der Runde, nicht Minuten/Tage spaeter auf einer anderen Seite.
        # Der Kontext traegt rundeninterne, nirgends persistierte Werte fuer
        # die beiden rundenbasierten Errungenschaften (siehe achievements.py).
        try:
            from ragapp import achievements as _achievements
            _round_newly = _achievements.check_and_unlock(context={
                "round_total": beantwortet, "round_gewusst": tally["gewusst"],
                "leech_cleared": st.session_state.get("_study_leech_cleared", 0),
            })
        except Exception:  # noqa: BLE001
            _round_newly = []
        if _round_newly:
            st.balloons()
            from ragapp.ui._style import celebration_effects_html as _celebration_effects_html
            components.html(_celebration_effects_html(), height=0)
            for _na in _round_newly:
                st.success(f"**Neu freigeschaltet:** {_na.icon} {_na.title} – {_na.description}")

        block_done_banner(state_key="_study_from_block_id", key_prefix="study_round")

        b1, b2 = st.columns(2)
        if b1.button("🔁 Neue Runde", use_container_width=True):
            for k in (Q, ACTIVE, REVEAL, TALLY, ROUND, "_session_jol"):
                st.session_state.pop(k, None)
            st.rerun()
        if b2.button("Zur Stapelliste", use_container_width=True):
            for k in (Q, ACTIVE, REVEAL, TALLY, ROUND, "_session_jol"):
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
    _capc, _stopc = st.columns([3, 1])
    _combo_now = st.session_state.get("_study_combo", 0)
    # Kombo bleibt waehrend der GANZEN Runde sichtbar (nicht nur im kurzen
    # Toast direkt nach der Bewertung) - erst ab 2 in Folge, damit nicht schon
    # die allererste Karte einer neuen Serie eine Anzeige bekommt.
    _combo_suffix = f"  ·  🔥 {_combo_now}x in Folge" if _combo_now >= 2 else ""
    _capc.caption(f"📚 {_tt}" + (f" · {_topic}" if _topic else "") + _combo_suffix)
    # Runde JEDERZEIT beenden bzw. Fach/Stapel wechseln (z. B. nach 5 Karten oder wenn
    # das Tagesziel erreicht ist). Schon bewertete Karten sind bereits gespeichert.
    if _stopc.button("⏹ Runde beenden", use_container_width=True,
                     help="Lernrunde beenden und zurück zur Auswahl (Fach/Stapel "
                          "wechseln). Bereits bewertete Karten bleiben gespeichert."):
        for _k in (Q, ACTIVE, REVEAL, TALLY, ROUND, "_study_sprint",
                   "_study_sprint_prefer"):
            st.session_state.pop(_k, None)
        st.rerun()

    if st.session_state.get("_study_sprint"):
        _sp = st.session_state.get("_study_sprint_prefer") or "auto"
        if _sp == "definition":
            st.caption("⚡ Definitionssprint – kurze Begriffe, etwa 30 Sekunden pro Karte.")
        elif _sp == "formula":
            st.caption("⚡ Formelsprint – nur Formel-Karten, etwa 30 Sekunden pro Karte.")
        else:
            st.caption("⚡ Formel-/Definitionssprint – kurz und knapp, etwa 30 Sekunden pro Karte.")

    # Vorderseite
    _render_karte(karte.get("front") or "", kind="front")
    st.write("")

    _mode = st.session_state.get("_study_mode", "reveal")
    _ref = (karte.get("answer") or karte.get("back") or "").strip()

    if not st.session_state.get(REVEAL):
        if _mode == "type":
            # Getippte Freie-Reproduktion -> KI-Teilbewertung
            _typed = st.text_area("Deine Antwort (frei formulieren)", key="_typed_ans",
                                  height=130, placeholder="Formuliere die Antwort in eigenen Worten …")
            if st.button("✍️ Abgeben & benoten", type="primary", use_container_width=True):
                from ragapp import grading
                with st.spinner("Die KI bewertet deine Antwort …"):
                    st.session_state["_grade"] = grading.grade_typed_answer(
                        karte.get("front", ""), _ref, _typed)
                st.session_state[REVEAL] = True
                st.rerun()
        elif _mode == "cloze":
            from ragapp import grading
            from ragapp.student_flow import card_looks_like_formula as _is_form
            if _is_form(karte):
                st.info("Formelkarten eignen sich nicht für Lückentext – "
                        "die Formel bleibt beim Aufdecken lesbar.")
                if st.button("👁️ Antwort zeigen", type="primary", use_container_width=True,
                             key="cloze_formula_reveal"):
                    st.session_state[REVEAL] = True
                    st.rerun()
            else:
                cz = st.session_state.get("_cloze")
                if cz is None:
                    cz = grading.make_cloze(_ref) or ["", []]
                    st.session_state["_cloze"] = cz
                if cz[1]:
                    _render_karte("🧩 " + cz[0], kind="cloze")
                    st.write("")
                    st.text_input("Fehlender Begriff", key="_cloze_in",
                                  placeholder="Wort in die Lücke …")
                    if st.button("🧩 Prüfen", type="primary", use_container_width=True):
                        st.session_state["_cloze_ok"] = grading.check_cloze(
                            st.session_state.get("_cloze_in", ""), cz[1])
                        st.session_state[REVEAL] = True
                        st.rerun()
                else:
                    st.warning("Für diese Karte ließ sich kein Lückentext bilden. "
                               "Die Karte wird klassisch aufgedeckt – das ist kein Fehler.")
                    if st.button("👁️ Antwort zeigen", type="primary", use_container_width=True,
                                 key="cloze_fallback_reveal"):
                        st.session_state[REVEAL] = True
                        st.rerun()
        elif _mode == "mcq":
            from ragapp import grading
            from ragapp.student_flow import card_looks_like_formula as _is_form
            if _is_form(karte):
                st.info("Formelkarten eignen sich nicht für Multiple Choice – "
                        "kein Modellaufruf, klassisch aufdecken.")
                if st.button("👁️ Antwort zeigen", type="primary", use_container_width=True,
                             key="mcq_formula_reveal"):
                    st.session_state[REVEAL] = True
                    st.rerun()
            else:
                mcq = st.session_state.get("_mcq")
                if mcq is None:
                    with st.spinner("Erzeuge Antwortoptionen …"):
                        mcq = grading.generate_mcq(
                            karte.get("front", ""), _ref,
                            cache_key=karte.get("card_id")) or {}
                    st.session_state["_mcq"] = mcq
                _opts = mcq.get("options") or []
                if len(_opts) >= 2:
                    _sel = st.radio("Wähle die richtige Antwort:", _opts, index=None, key="_mcq_sel")
                    if st.button("🔤 Antwort prüfen", type="primary", use_container_width=True,
                                 disabled=_sel is None):
                        st.session_state["_mcq_ok"] = (_sel == mcq.get("correct"))
                        st.session_state[REVEAL] = True
                        st.rerun()
                else:
                    st.warning("Konnte keine Multiple-Choice-Optionen erzeugen. "
                               "Die Karte wird klassisch aufgedeckt – das ist kein Fehler.")
                    if st.button("👁️ Antwort zeigen", type="primary", use_container_width=True,
                                 key="mcq_fallback_reveal"):
                        st.session_state[REVEAL] = True
                        st.rerun()
        else:  # reveal (klassisch, mit Selbst-Konfidenz/JOL)
            st.caption("Überlege (oder tippe für dich) die Antwort – dann aufdecken "
                       "(oder Enter im Feld unten).")
            _conf_lbl = st.radio(
                "Wie sicher bist du dir?", ["😃 sicher", "😐 mittel", "😟 unsicher"],
                index=None, horizontal=True, key="_jol",
                help="Selbsteinschätzung VOR dem Aufdecken. Wer sich sicher ist und trotzdem "
                     "danebenliegt, hat eine besonders hartnäckige Lücke – die kommt dann "
                     "schneller wieder dran (Hypercorrection).")
            st.session_state["_study_conf"] = {
                "😃 sicher": "sicher", "😐 mittel": "mittel", "😟 unsicher": "unsicher"
            }.get(_conf_lbl)
            # Enter im Textfeld = Aufdecken (Streamlit-natives Tastatur-Shortcut)
            with st.form("reveal_form", clear_on_submit=False):
                st.text_input("Kurznotiz (optional) – Enter oder Button zum Aufdecken",
                              key="_reveal_note", label_visibility="collapsed",
                              placeholder="Enter = Antwort zeigen …")
                if st.form_submit_button("👁️ Antwort zeigen", type="primary",
                                         use_container_width=True):
                    st.session_state[REVEAL] = True
                    st.rerun()
    else:
        # Feedback der aktiven Modi (Benotung / Lückentext-Ergebnis) VOR der Musterlösung.
        _suggest = None
        if _mode == "type" and st.session_state.get("_grade"):
            g = st.session_state["_grade"]
            if g.get("ok") and g.get("score") is not None:
                st.markdown(f"### Bewertung: {g['score']} %")
                st.progress(min(1.0, g["score"] / 100))
                if g.get("feedback"):
                    st.info(g["feedback"])
                if g.get("fehlt"):
                    st.caption("Noch nicht genannt: " + " · ".join(g["fehlt"]))
                _suggest = g.get("suggested_rating")
            else:
                st.warning("Automatische Benotung war nicht möglich – schätze selbst ein.")
            with st.expander("Deine Antwort", expanded=False):
                st.write(st.session_state.get("_typed_ans") or "—")
            st.divider()
        elif _mode == "cloze" and "_cloze_ok" in st.session_state:
            if st.session_state["_cloze_ok"]:
                st.success("✅ Richtig!")
                _suggest = study.GEWUSST
            else:
                _cz = st.session_state.get("_cloze") or ["", []]
                st.error("❌ Nicht ganz – Lösung: **" + ", ".join(_cz[1]) + "**")
                _suggest = study.NICHT
            st.divider()
        elif _mode == "mcq" and "_mcq_ok" in st.session_state:
            if st.session_state["_mcq_ok"]:
                st.success("✅ Richtig gewählt!")
                _suggest = study.GEWUSST
            else:
                _mc = st.session_state.get("_mcq") or {}
                st.error("❌ Falsch – richtig war: **" + str(_mc.get("correct", "")) + "**")
                _suggest = study.NICHT
            st.divider()
        st.session_state["_study_suggest"] = _suggest
        # Rueckseite: bevorzugt die echte Antwort (Musterloesung); nur wenn keine da
        # ist, der Original-Chunk als Notbehelf. LaTeX rendert via Markdown.
        _ans = (karte.get("answer") or "").strip()
        if _ans:
            _render_karte(_ans, kind="back")
            if (karte.get("back") or "").strip() and karte.get("source") == "question":
                from ragapp.student_flow import normalize_card_latex as _ntex
                with st.expander("📄 Beleg / Originaltext"):
                    st.markdown(_ntex(karte["back"]))
        else:
            st.warning("Für diese Karte gibt es noch **keine** Musterlösung – gezeigt "
                       "wird der Originaltext. Tipp: oben unter **⚙️ Karten verwalten → "
                       "Antworten erzeugen** die KI-Antworten nachziehen.")
            _render_karte(karte.get("back") or "", kind="back")
        st.write("")
        st.caption("Wie gut wusstest du es? (**1** Nicht · **2** Halb · **3** Gewusst · "
                   "am Handy: Karte ← nicht / gewusst → wischen)")
        _sg = st.session_state.get("_study_suggest")
        if _sg is not None:
            _sgtxt = {study.GEWUSST: "✅ Gewusst", study.HALB: "🟡 Halb",
                      study.NICHT: "❌ Nicht gewusst"}.get(_sg, "")
            st.caption(f"Vorschlag aus dem Ergebnis: **{_sgtxt}** – du entscheidest.")
        r1, r2, r3 = st.columns(3)

        def _bewerten(rating: int) -> None:
            _conf = st.session_state.get("_study_conf")
            nxt = study.rate_card(karte, rating, confidence=_conf)
            _jol = st.session_state.setdefault("_session_jol", {"n": 0, "sicher_wrong": 0})
            if _conf:
                _jol["n"] = int(_jol.get("n") or 0) + 1
                if _conf == "sicher" and rating <= study.NICHT:
                    _jol["sicher_wrong"] = int(_jol.get("sicher_wrong") or 0) + 1
            # Dezentes, aber SPUERBARES Feedback fuer die haeufigste Aktion der
            # ganzen App - vorher gab es hier nur einen stillen Hinweis auf das
            # naechste Faelligkeitsdatum, unabhaengig vom Ergebnis. Ein Kombo-
            # Zaehler (in Folge "Gewusst") macht kleine Erfolgsstrecken sichtbar,
            # ohne bei JEDER einzelnen Karte schon zu uebertreiben (siehe
            # Balloons-Regel weiter unten in der App: nur fuer echte Meilen-
            # steine, sonst nutzt sich die Freude schnell ab).
            if rating == study.GEWUSST:
                _combo = st.session_state.get("_study_combo", 0) + 1
                st.session_state["_study_combo"] = _combo
                st.session_state["_study_combo_best"] = max(
                    st.session_state.get("_study_combo_best", 0), _combo)
                if _combo >= 3 and _combo % 3 == 0:
                    st.toast(f"🔥 {_combo}x in Folge gewusst!", icon="🔥")
                    from ragapp.ui._style import combo_pulse_html as _combo_pulse_html
                    components.html(_combo_pulse_html(), height=0)
                else:
                    st.toast(f"✅ Gewusst! · Nächste Wiederholung: {study.humanize_due(nxt['due'])}")
            else:
                st.session_state["_study_combo"] = 0
                st.toast(f"Nächste Wiederholung: {study.humanize_due(nxt['due'])}")
            # Fuer die Errungenschaft "leech_buster" (siehe ragapp/achievements.py):
            # zaehlt, wie viele Dauerpatzer in DIESER Runde nicht mehr mit
            # "Nicht gewusst" bewertet wurden - also wirklich Fortschritt statt
            # nur erneutem Scheitern an derselben Karte.
            if karte.get("lapses", 0) >= settings.LEECH_LAPSES_THRESHOLD and rating >= study.HALB:
                st.session_state["_study_leech_cleared"] = (
                    st.session_state.get("_study_leech_cleared", 0) + 1)
            t = st.session_state[TALLY]
            t["gewusst" if rating == study.GEWUSST else
              "halb" if rating == study.HALB else "nicht"] += 1
            q = st.session_state[Q]
            q.pop(0)
            # Anki: Learning/Relearning mit kurzem due bleibt in der Sitzung
            # (nicht nur bei "Nicht gewusst").
            if study.should_requeue_in_session(nxt):
                q.append({**karte, **nxt})
            st.session_state[REVEAL] = False
            # Alle Modus-Zustaende fuer die naechste Karte zuruecksetzen.
            for _k in ("_study_conf", "_jol", "_typed_ans", "_grade", "_cloze",
                       "_cloze_in", "_cloze_ok", "_mcq", "_mcq_sel", "_mcq_ok",
                       "_study_suggest", "_reveal_note"):
                st.session_state.pop(_k, None)
            st.rerun()

        if r1.button("1️⃣ Nicht gewusst", use_container_width=True, key="rate_nicht"):
            _bewerten(study.NICHT)
        if r2.button("2️⃣ Halb", use_container_width=True, key="rate_halb"):
            _bewerten(study.HALB)
        if r3.button("3️⃣ Gewusst", use_container_width=True, key="rate_gewusst"):
            _bewerten(study.GEWUSST)

        # Aus der Tastatur-Ziffer im Hinweis oben (siehe Caption "1 Nicht ·
        # 2 Halb · 3 Gewusst") eine ECHTE Tastenkombination machen, nicht nur
        # eine Beschriftung - fuer Vielnutzer (wie bei Anki) die Haupt-
        # Beschleunigung: bewerten ohne die Hand von der Tastatur zu nehmen.
        # Einmalig auf dem PARENT-Dokument gebunden (Streamlit macht keinen
        # echten Seiten-Reload; ein erneutes Binden bei jedem Rerun wuerde
        # denselben Tastendruck sonst mehrfach ausloesen) - sucht die Buttons bei JEDEM Tastendruck
        # live per Klasse, dadurch automatisch wirkungslos, wenn gerade keine
        # Bewertung ansteht (z. B. auf einer anderen Seite oder vor dem
        # Aufdecken) statt Zustand zwischen Skript und Streamlit abgleichen
        # zu muessen. Ziffern in einem Text-/Zahlenfeld loesen NICHTS aus.
        # Zusaetzlich (am Handy): die Karte nach links/rechts wischen bewertet
        # direkt "Nicht gewusst"/"Gewusst" - wie bei Quizlet/Ankidroid, die
        # verbreitetste Handy-Geste fuer Karteikarten. "Halb" bleibt bewusst
        # nur per Tap/Taste 2 erreichbar (eine dritte Wisch-Richtung waere
        # keine natuerliche Erweiterung eines Links-Rechts-Spektrums mehr,
        # eher verwirrend als hilfreich). Passiv gebunden (kein preventDefault)
        # - blockiert normales vertikales Scrollen der Karte nicht.
        components.html("""
<script>
(function() {
  try {
    var doc = window.parent.document;
    function clickByKey(key) {
      var el = doc.querySelector('.st-key-' + key + ' button');
      if (el) { el.click(); }
    }
    if (!doc.__ragRatingKeysBound) {
      doc.__ragRatingKeysBound = true;
      doc.addEventListener('keydown', function(e) {
        if (e.ctrlKey || e.metaKey || e.altKey) { return; }
        var t = e.target;
        var tag = t && t.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA' || (t && t.isContentEditable)) { return; }
        if (e.key === '1') { clickByKey('rate_nicht'); }
        else if (e.key === '2') { clickByKey('rate_halb'); }
        else if (e.key === '3') { clickByKey('rate_gewusst'); }
      }, true);
    }
    if (!doc.__ragSwipeBound) {
      doc.__ragSwipeBound = true;
      var sx = null, sy = null, st0 = 0;
      var EDGE = 24; // px - siehe Kommentar unten
      doc.addEventListener('touchstart', function(e) {
        var el = e.target && e.target.closest
          ? e.target.closest('.karte, .karte-frage, [class*="st-key-karte_"], [data-testid="stHorizontalBlock"]')
          : null;
        // Nur werten, wenn eine Karte sichtbar ist (Bewertungsbuttons existieren)
        if (!doc.querySelector('.st-key-rate_gewusst button')) { sx = null; return; }
        if (!el || !e.touches || !e.touches.length) { sx = null; return; }
        var x = e.touches[0].clientX;
        // Touches, die ganz am Bildschirmrand starten, NICHT als Wisch-
        // Bewertung behandeln: auf iOS Safari loest ein Wisch von der
        // aeussersten Kante (unabhaengig davon, was dort gerendert ist) die
        // systemweite "Zurueck"-Geste aus, BEVOR unser Skript ueberhaupt
        // greift. Indem wir dort gar nicht erst reagieren, konkurriert
        // unsere Geste nicht mit der des Betriebssystems - der Nutzer landet
        // einfach zuverlaessig bei der einen oder der anderen, nie bei einem
        // Konflikt zwischen beiden.
        if (x < EDGE || x > (doc.documentElement.clientWidth - EDGE)) { sx = null; return; }
        sx = x; sy = e.touches[0].clientY; st0 = Date.now();
      }, {passive: true});
      doc.addEventListener('touchend', function(e) {
        if (sx === null || !e.changedTouches || !e.changedTouches.length) { return; }
        var dx = e.changedTouches[0].clientX - sx;
        var dy = e.changedTouches[0].clientY - sy;
        var dt = Date.now() - st0;
        sx = null;
        if (dt > 800 || Math.abs(dx) < 60 || Math.abs(dx) < Math.abs(dy) * 1.5) { return; }
        clickByKey(dx > 0 ? 'rate_gewusst' : 'rate_nicht');
      }, {passive: true});
    }
  } catch (e) {}
})();
</script>
""", height=0)

if st.session_state.get(ACTIVE):
    st.stop()

st.divider()

# --------------------------------------------------------------------------- #
# Verwaltung: Karten ernten, Stapel organisieren, bearbeiten/loeschen - BEWUSST
# unterhalb der Lernrunde: ein Live-Test zeigte, dass man vorher an drei
# Verwaltungs-Abschnitten vorbei musste, nur um eine Runde zu starten.
# --------------------------------------------------------------------------- #
# Drei getrennte Expander wirkten als eigene Ueberschriften-Reihe sehr lang
# (Nutzer-Feedback: "komplett unuebersichtlich") - EIN klar abgegrenzter
# "Verwaltung"-Block statt drei. Bewusst KEIN st.tabs(): st.tabs() merkt sich
# den aktiven Tab nur ueber automatische, vom Widget selbst ausgeloeste
# Reruns - ein Klick auf "Speichern"/"Löschen" INNERHALB eines Tabs braucht
# aber ein eigenes st.rerun() (um z.B. die Kartenliste nach dem Loeschen neu
# zu laden), was st.tabs() zurueck auf den ERSTEN Tab springen liess (per
# Live-Test entdeckt). st.segmented_control() ist dagegen ein echtes, an
# session_state gebundenes Widget - bleibt auf dem gewaehlten Bereich, egal
# ob der Rerun automatisch oder explizit ausgeloest wird.
_active_tab = st.segmented_control(
    "Verwaltungsbereich",
    ["🌾 Karten erstellen", "🗂️ Stapel verwalten", "📋 Bearbeiten & Löschen"],
    default="🌾 Karten erstellen", key="lernen_verwaltung_tab",
    label_visibility="collapsed", required=True,
)

if _active_tab == "🌾 Karten erstellen":
    st.caption("Neues Lernset: oben unter **Lernset erstellen**. "
               "Fragen anreichern, manuelles Ernten und Klausurkatalog bleiben "
               "im Expertenmodus.")
    with st.expander("Expertenmodus", expanded=False):
        _render_karten_erstellen()

if _active_tab == "🗂️ Stapel verwalten":
    st.caption(
        "Stapel nach **Fach** organisieren. Innerhalb eines Fachs: nach **Dokument**, "
        "**Thema/Inhaltsverzeichnis** oder **einzelnen Karten** zusammenstellen. "
        "Unterstapel z. B. als `Kapitel 3 / Regression` benennen."
    )

    _faecher_v = manifest.study_subjects()
    if not _faecher_v:
        st.info("Noch keine Karten – erst Fragen/Katalog erzeugen und Karten aktualisieren.")
    else:
        _dk_subj = st.selectbox(
            "1. Fach",
            _faecher_v,
            format_func=_fach_label,
            key="dk_subj",
            help="Stapel werden je Fach gepflegt. Wechsle das Fach, um andere Stapel zu sehen.",
        )

        # --- Bestehende Stapel dieses Fachs ---
        _ov = [o for o in manifest.deck_overview(subject=_dk_subj) if o.get("deck")]
        _ov_all_unassigned = next(
            (o for o in manifest.deck_overview(subject=_dk_subj) if not o.get("deck")),
            None,
        )
        if _ov_all_unassigned:
            st.caption(
                f"Ohne Stapel in {_fach_label(_dk_subj)}: "
                f"**{_ov_all_unassigned['total']}** Karten "
                f"(Neu {_ov_all_unassigned.get('new', 0)} · "
                f"Lernen {_ov_all_unassigned.get('learning', 0)} · "
                f"Wiederholen {_ov_all_unassigned.get('review', 0)})."
            )
        if _ov:
            st.markdown(f"**Stapel in {_fach_label(_dk_subj)}:**")
            for _o in _ov:
                _d = _o["deck"]
                _dc1, _dc2, _dc3, _dc4 = st.columns([3, 1, 1, 1])
                _dc1.markdown(
                    f"🗂️ **{_d}** · {_o['total']} Karten · "
                    f"N {_o.get('new', 0)} / L {_o.get('learning', 0)} / "
                    f"W {_o.get('review', 0)}"
                )
                if _dc2.button("Auflösen", key=f"dissolve_{_dk_subj}_{_d}",
                               use_container_width=True,
                               help="Zuordnung aufheben, Karten bleiben erhalten."):
                    manifest.dissolve_deck(_d)
                    st.success(f"Stapel „{_d}“ aufgelöst.")
                    st.rerun()
                with _dc3:
                    if delete_button("Löschen", token=f"deck:{_dk_subj}:{_d}",
                                     body=f"Stapel **{_d}** samt Karten wirklich löschen?",
                                     key=f"delete_{_dk_subj}_{_d}"):
                        manifest.delete_deck(_d)
                        st.success(f"Stapel „{_d}“ gelöscht.")
                        st.rerun()
                with _dc4:
                    with st.popover("Umbenennen"):
                        _rn = st.text_input("Neuer Name", value=_d,
                                            key=f"rn_in_{_dk_subj}_{_d}")
                        if st.button("Umbenennen", key=f"rn_btn_{_dk_subj}_{_d}"):
                            n = manifest.rename_deck(_d, (_rn or "").strip())
                            if n:
                                st.success(f"{n} Karten umbenannt.")
                                st.rerun()
                            else:
                                st.warning("Name unverändert oder leer.")
        else:
            st.caption(f"Noch keine Stapel in {_fach_label(_dk_subj)}.")

        st.divider()
        st.markdown("**2. Stapel anlegen oder erweitern**")

        _existing_decks = manifest.list_decks(_dk_subj)
        _dk_mode = st.radio(
            "Ziel",
            ["Neuer Stapel", "Bestehenden Stapel erweitern"],
            horizontal=True,
            key="dk_mode",
        )
        if _dk_mode.startswith("Bestehend") and _existing_decks:
            _name = st.selectbox("Stapel", _existing_decks, key="dk_exist_name")
        elif _dk_mode.startswith("Bestehend"):
            st.info("Noch kein Stapel in diesem Fach – lege zuerst einen neuen an.")
            _name = ""
        else:
            _name = st.text_input(
                "Stapelname",
                placeholder="z. B. Klausur-Kompakt  oder  Kap. 3 / Stichproben",
                key="deck_name",
                help="Frei wählbar. Schrägstrich für Unterstruktur: „Kapitel / Thema“.",
            )

        # --- Filter-Hierarchie ---
        _docs_here = manifest.list_docs_with_cards(subject=_dk_subj)
        _doc_labels = {
            d["doc_id"]: f"{d['filename']}  ({d['n_cards']} Karten)"
            for d in _docs_here if d.get("doc_id")
        }
        _sel_docs = st.multiselect(
            "3. Dokumente (optional – leer = alle des Fachs)",
            list(_doc_labels.keys()),
            format_func=lambda k: _doc_labels.get(k, k),
            key="dk_docs",
            help="Bei mehreren Uploads: Stapel pro Dokument. Bei einem Dokument "
                 "weiter unten nach Themen/TOC filtern.",
            placeholder="Alle",
        )
        _doc_ids_arg = _sel_docs or None

        _topics_here = manifest.list_topics(subject=_dk_subj, doc_ids=_doc_ids_arg)
        _sel_topics = st.multiselect(
            "4. Themen / Inhaltsverzeichnis (optional)",
            _topics_here,
            key="dk_topics",
            placeholder="Alle",
            help="Abschnitte aus deinen Unterlagen (location/header). "
                 "Ideal, wenn nur ein Dokument indexiert ist.",
        )
        _topics_arg = _sel_topics or None

        _c_only, _c_search = st.columns([1, 2])
        _only_free = _c_only.checkbox(
            "Nur Karten ohne Stapel",
            value=True,
            key="dk_only_free",
            help="Verhindert, dass Karten aus anderen Stapeln still überschrieben werden.",
        )
        _search = _c_search.text_input(
            "Textsuche in Frage/Antwort",
            key="dk_search",
            placeholder="optional filtern …",
        )

        _preview = manifest.find_cards(
            subject=_dk_subj,
            doc_ids=_doc_ids_arg,
            topics=_topics_arg,
            search=_search or None,
            only_unassigned=bool(_only_free),
            limit=400,
        )
        _n_match = manifest.count_find_cards(
            subject=_dk_subj,
            doc_ids=_doc_ids_arg,
            topics=_topics_arg,
            search=_search or None,
            only_unassigned=bool(_only_free),
        )
        st.caption(
            f"**{_n_match}** Karte(n) passen zur Filterung"
            + (f" · Vorschau {_n_match - len(_preview)}+ ausgeblendet" if _n_match > len(_preview) else "")
            + "."
        )

        if not _preview:
            st.info("Keine Karten für diese Filter – Auswahl lockern oder Karten ernten.")
        else:
            _pdf = pd.DataFrame([{
                "✓": True,
                "Frage": (r.get("front") or "")[:120],
                "Thema": (r.get("topic") or "")[:60],
                "Stapel": r.get("deck") or "—",
                "Dokument": next(
                    (d["filename"] for d in _docs_here if d["doc_id"] == r.get("doc_id")),
                    r.get("doc_id") or "—",
                ),
                "_id": r["card_id"],
            } for r in _preview])
            _pa1, _pa2, _pa3 = st.columns(3)
            if _pa1.button("Alle anwählen", key="dk_sel_all"):
                st.session_state["dk_force_sel"] = True
                st.session_state["dk_picker_ver"] = st.session_state.get("dk_picker_ver", 0) + 1
                st.rerun()
            if _pa2.button("Alle abwählen", key="dk_sel_none"):
                st.session_state["dk_force_sel"] = False
                st.session_state["dk_picker_ver"] = st.session_state.get("dk_picker_ver", 0) + 1
                st.rerun()
            _force = st.session_state.get("dk_force_sel")
            if _force is not None:
                _pdf["✓"] = bool(_force)
            _picker_key = f"dk_picker_{st.session_state.get('dk_picker_ver', 0)}"

            _pedited = st.data_editor(
                _pdf,
                hide_index=True,
                use_container_width=True,
                key=_picker_key,
                column_config={
                    "✓": st.column_config.CheckboxColumn("Mitnehmen", width="small"),
                    "Frage": st.column_config.TextColumn(width="large"),
                    "Thema": st.column_config.TextColumn(width="medium"),
                    "Stapel": st.column_config.TextColumn(width="small"),
                    "Dokument": st.column_config.TextColumn(width="medium"),
                    "_id": None,
                },
                disabled=["Frage", "Thema", "Stapel", "Dokument"],
            )
            _pick_ids = [row["_id"] for _, row in _pedited.iterrows() if row["✓"]]
            st.caption(f"**{len(_pick_ids)}** ausgewählt zum Hinzufügen.")

            _add_disabled = not (_name or "").strip() or not _pick_ids
            if st.button(
                f"➕ {len(_pick_ids)} Karte(n) zu „{(_name or '').strip() or '…'}“",
                type="primary",
                use_container_width=True,
                disabled=_add_disabled,
                key="dk_add",
            ):
                _n = manifest.assign_deck(
                    (_name or "").strip(),
                    card_ids=_pick_ids,
                )
                if _n:
                    st.success(
                        f"{_n} Karten dem Stapel „{(_name or '').strip()}“ "
                        f"({_fach_label(_dk_subj)}) zugeordnet."
                    )
                    st.rerun()
                else:
                    st.warning("0 Karten zugeordnet.")

            # Schnellaktion: Filter komplett ohne Einzelauswahl (alle Treffer)
            if st.button(
                f"⚡ Alle {_n_match} Filter-Treffer zuordnen (ohne Abwahl)",
                disabled=not (_name or "").strip() or _n_match == 0,
                key="dk_add_all_filt",
                help="Setzt den Stapel für alle Karten, die den Filtern entsprechen "
                     "(auch über die Vorschau-Grenze hinaus).",
            ):
                _deck_nm = (_name or "").strip()
                if (_search or "").strip():
                    _all = manifest.find_cards(
                        subject=_dk_subj,
                        doc_ids=_doc_ids_arg,
                        topics=_topics_arg,
                        search=_search,
                        only_unassigned=bool(_only_free),
                        limit=5000,
                    )
                    _n = manifest.assign_deck(
                        _deck_nm, card_ids=[c["card_id"] for c in _all],
                    )
                else:
                    _n = manifest.assign_deck(
                        _deck_nm,
                        subjects=[_dk_subj],
                        doc_ids=_doc_ids_arg,
                        topics=_topics_arg,
                        only_unassigned=bool(_only_free),
                    )
                if _n:
                    st.success(f"{_n} Karten zugeordnet.")
                    st.rerun()
                else:
                    st.warning("0 Karten zugeordnet.")

if _active_tab == "📋 Bearbeiten & Löschen":
    st.caption("Frage/Antwort direkt in der Tabelle bearbeiten. Häkchen setzen, um Karten "
               "zu löschen, einem Stapel zuzuordnen oder Antworten zu erzeugen. "
               "**Abfrage** = in der Lernrunde zeigen · **Embedding** = Frage im Suchindex halten.")
    # Erfolgsmeldung fuer diese Sektion wird ganz oben im Skript angezeigt
    # (vor dem "keine Karten"-Abbruch) - siehe Kommentar dort.
    from ragapp.student_flow import card_wipe_message, keep_filter_option

    _mf1, _mf2, _mf3, _mf4 = st.columns(4)
    _cur_subj = st.session_state.get("mv_subj")
    _subj_opts = keep_filter_option(_cur_subj, manifest.study_subjects())
    _mv_subj = _mf1.selectbox("Fach", _subj_opts,
                              format_func=lambda s: "Alle" if s == "Alle" else _fach_label(s),
                              key="mv_subj")
    _mv_subj_arg = None if _mv_subj == "Alle" else _mv_subj
    _mv_decks = manifest.list_decks(_mv_subj_arg)
    _mv_deck = _mf2.selectbox("Stapel", ["Alle", "— ohne Stapel —"] + _mv_decks, key="mv_deck")
    _mv_docs = manifest.list_docs_with_cards(subject=_mv_subj_arg)
    _mv_doc_map = {d["doc_id"]: d["filename"] for d in _mv_docs if d.get("doc_id")}
    _cur_doc = st.session_state.get("mv_doc")
    if _cur_doc and _cur_doc not in _mv_doc_map and _cur_doc != "Alle":
        _mv_doc_map[_cur_doc] = st.session_state.get("mv_doc_label") or _cur_doc
    _mv_doc = _mf3.selectbox(
        "Dokument",
        keep_filter_option(_cur_doc, list(_mv_doc_map.keys())),
        format_func=lambda k: "Alle" if k == "Alle" else _mv_doc_map.get(k, k),
        key="mv_doc",
    )
    if _mv_doc != "Alle":
        st.session_state["mv_doc_label"] = _mv_doc_map.get(_mv_doc, _mv_doc)
    _mv_limit = _mf4.number_input("Max. Zeilen", min_value=10, max_value=10000, value=500,
                                  step=50, key="mv_limit",
                                  help="Nur die Anzeige. ‚Alle im Filter löschen‘ trifft "
                                       "trotzdem jede Karte der Filterung, nicht nur diese Zeilen.")
    _mv_deck_arg = (None if _mv_deck == "Alle"
                    else "__none__" if _mv_deck.startswith("—") else _mv_deck)
    _mv_topics = manifest.list_topics(
        subject=_mv_subj_arg,
        doc_ids=None if _mv_doc == "Alle" else [_mv_doc],
    )
    _mv_topic = st.multiselect("Thema filtern", _mv_topics, key="mv_topics",
                               placeholder="Alle")
    if _mv_doc != "Alle" or _mv_topic:
        _mv_rows = manifest.find_cards(
            subject=_mv_subj_arg,
            doc_ids=None if _mv_doc == "Alle" else [_mv_doc],
            topics=_mv_topic or None,
            deck=_mv_deck_arg,
            exclude_suspended=False,
            limit=int(_mv_limit),
        )
        _mv_total = manifest.count_find_cards(
            subject=_mv_subj_arg,
            doc_ids=None if _mv_doc == "Alle" else [_mv_doc],
            topics=_mv_topic or None,
            deck=_mv_deck_arg,
            exclude_suspended=False,
        )
    else:
        _mv_rows = manifest.list_cards(subject=_mv_subj_arg, deck=_mv_deck_arg,
                                       limit=int(_mv_limit))
        _mv_total = manifest.count_cards(subject=_mv_subj_arg, deck=_mv_deck_arg)

    _mv_doc_ids = None if _mv_doc == "Alle" else [_mv_doc]
    _mv_doc_name = None if _mv_doc == "Alle" else _mv_doc_map.get(_mv_doc)
    _mv_wipe_kw = dict(
        subject=_mv_subj_arg, doc_ids=_mv_doc_ids,
        topics=_mv_topic or None, deck=_mv_deck_arg,
    )

    def _flash_card_wipe(deleted: int, remaining: int) -> None:
        st.session_state["_mv_flash"] = card_wipe_message(
            deleted=deleted, remaining=remaining,
            subject=_mv_subj_arg,
            subject_label=_fach_label(_mv_subj_arg) if _mv_subj_arg else None,
            document=_mv_doc_name,
        )

    if _mv_total > len(_mv_rows):
        st.warning(
            f"Es werden nur {len(_mv_rows)} von {_mv_total} Karten angezeigt. "
            f"‚Alle im Filter löschen‘ entfernt trotzdem alle {_mv_total} "
            "Karten dieser Filterung – nicht nur die sichtbaren Zeilen."
        )

    if not _mv_rows:
        if _mv_subj_arg or _mv_doc != "Alle":
            st.info("Keine Karten mehr für diese Filterung. Der Filter bleibt stehen, "
                    "damit du nicht versehentlich ein anderes Fach oder Dokument löschst.")
        else:
            st.info("Keine Karten für diese Auswahl.")
    else:
        _orig = {r["card_id"]: r for r in _mv_rows}

        # "Wenn man ein Fach nicht mehr hat, kann man nur einzeln Karten
        # löschen" (Nutzer-Feedback): vorher gab es fuer diese Sektion KEIN
        # "alle auswaehlen" - man musste jede der (moeglicherweise hunderten)
        # Karten einzeln antippen, bevor "Auswahl löschen" ueberhaupt etwas
        # tat. Fach oben filtern + hier "Alle auswaehlen" + "Auswahl löschen"
        # loescht jetzt ein ganzes Fach in drei Klicks. Gleiches Muster wie
        # "Alle anwaehlen"/"Alle abwaehlen" bei "Stapel verwalten" oben.
        _sa1, _sa2 = st.columns(2)
        if _sa1.button("✅ Alle auswählen", key="mv_sel_all", use_container_width=True):
            st.session_state["mv_force_sel"] = True
            st.session_state["mv_picker_ver"] = st.session_state.get("mv_picker_ver", 0) + 1
            for _r in _mv_rows:
                st.session_state[f"mv_cv_sel_{_r['card_id']}"] = True
            # Bewusst KEIN st.rerun(): der Button-Klick loest ohnehin schon
            # einen Rerun aus, und die obigen session_state-Werte wirken
            # sofort auf die Widgets weiter unten IM SELBEN Durchlauf. Ein
            # zusaetzliches st.rerun() hier hat den aktiven Tab (📋 Bearbeiten
            # & Löschen) zurueck auf den ersten Tab gesprungen - st.tabs()
            # merkt sich die Auswahl nur ueber den normalen, vom Widget
            # ausgeloesten Rerun, nicht ueber einen erzwungenen.
        if _sa2.button("❌ Alle abwählen", key="mv_sel_none", use_container_width=True):
            st.session_state["mv_force_sel"] = False
            st.session_state["mv_picker_ver"] = st.session_state.get("mv_picker_ver", 0) + 1
            for _r in _mv_rows:
                st.session_state[f"mv_cv_sel_{_r['card_id']}"] = False
            # Siehe Kommentar oben - kein st.rerun() noetig/gewuenscht.

        # Kompakte Listenansicht statt breiter Tabelle: ein Live-Test bei
        # Handy-Breite (375px) zeigte, dass die 8-spaltige Tabelle dort nur
        # noch die "Frage"-Spalte zeigt - der Rest liegt hinter einem
        # Scroll-im-Scroll (die Tabelle scrollt seitlich INNERHALB einer
        # Seite, die selbst hoch/runter scrollt), was auf dem Handy leicht zu
        # Fehlbedienung fuehrt. Als Toggle (nicht automatisch erkannt -
        # Streamlit kennt die Bildschirmbreite serverseitig nicht) statt
        # Ersatz, damit die schnelle Tabellen-Bearbeitung am Desktop bleibt.
        _compact = st.toggle("📱 Kompakte Liste (statt Tabelle – besser für schmale Bildschirme)",
                             key="mv_compact")
        if _compact:
            st.caption('Tipp: „Max. Zeilen" oben klein halten, dann bleibt die Liste kurz.')
            _sel: list[str] = []
            _rows_for_save: list[dict] = []
            for r in _mv_rows:
                cid = r["card_id"]
                with st.container(border=True):
                    _c1, _c2 = st.columns([5, 1])
                    _c1.caption(f"{_fach_label(r.get('subject') or '')}"
                               + (f" · {r['topic']}" if r.get("topic") else ""))
                    _checked = _c2.checkbox("✓", key=f"mv_cv_sel_{cid}", label_visibility="collapsed")
                    _front = st.text_area("Frage", value=r["front"], key=f"mv_cv_front_{cid}",
                                          height=80, label_visibility="collapsed")
                    _answer = st.text_area("Antwort", value=r.get("answer") or "",
                                           key=f"mv_cv_answer_{cid}", height=80,
                                           label_visibility="collapsed",
                                           placeholder="Antwort …")
                    _d1, _d2, _d3 = st.columns([2, 1, 1])
                    _deck = _d1.text_input("Stapel", value=r.get("deck") or "",
                                           key=f"mv_cv_deck_{cid}", label_visibility="collapsed",
                                           placeholder="Stapel …")
                    _use_fc = _d2.checkbox("Abfrage", value=bool(r.get("use_flashcard", 1)),
                                           key=f"mv_cv_fc_{cid}")
                    _use_em = _d3.checkbox("Embed.", value=bool(r.get("use_embedding", 1)),
                                          key=f"mv_cv_em_{cid}")
                if _checked:
                    _sel.append(cid)
                _rows_for_save.append({
                    "_id": cid, "Frage": _front, "Antwort": _answer, "Stapel": _deck,
                    "Abfrage": _use_fc, "Embedding": _use_em,
                })
        else:
            _df = pd.DataFrame([{
                "✓": False,
                "Frage": r["front"],
                "Antwort": r.get("answer") or "",
                "Thema": r.get("topic") or "",
                "Fach": _fach_label(r.get("subject") or ""),
                "Stapel": r.get("deck") or "",
                "Abfrage": bool(r.get("use_flashcard", 1)),
                "Embedding": bool(r.get("use_embedding", 1)),
                "_id": r["card_id"],
            } for r in _mv_rows])
            _mv_force = st.session_state.get("mv_force_sel")
            if _mv_force is not None:
                _df["✓"] = bool(_mv_force)
            # Versionierter Key: nur so erzwingt "Alle auswaehlen/abwaehlen"
            # WIRKLICH einen neu befuellten Editor - ohne das haengt der
            # data_editor am alten internen Zustand seines Keys, selbst wenn
            # die Quell-DataFrame-Werte sich geaendert haben.
            _mv_editor_key = f"mv_editor_{st.session_state.get('mv_picker_ver', 0)}"
            _edited = st.data_editor(
                _df, hide_index=True, use_container_width=True, key=_mv_editor_key,
                column_config={
                    "✓": st.column_config.CheckboxColumn(width="small"),
                    "Frage": st.column_config.TextColumn(width="large"),
                    "Antwort": st.column_config.TextColumn(width="large"),
                    "Thema": st.column_config.TextColumn(disabled=True, width="medium"),
                    "Fach": st.column_config.TextColumn(disabled=True),
                    "Stapel": st.column_config.TextColumn(help="Stapelname (leer = kein Stapel)"),
                    "Abfrage": st.column_config.CheckboxColumn(),
                    "Embedding": st.column_config.CheckboxColumn(),
                    "_id": None,
                },
            )
            _sel = [row["_id"] for _, row in _edited.iterrows() if row["✓"]]
            _rows_for_save = [
                {"_id": row["_id"], "Frage": row["Frage"], "Antwort": row["Antwort"],
                 "Stapel": row["Stapel"], "Abfrage": row["Abfrage"], "Embedding": row["Embedding"]}
                for _, row in _edited.iterrows()
            ]
        st.caption(f"{len(_sel)} ausgewählt · {len(_mv_rows)} angezeigt · {_mv_total} gesamt "
                   "in dieser Filterung. Die Anzeige-Grenze gilt nur für die Tabelle – "
                   "löschen kannst du unten alle Treffer auf einmal.")

        _b1, _b2, _b3, _b4 = st.columns(4)
        if _b1.button("💾 Änderungen speichern", use_container_width=True):
            from ragapp.retrieval.vectorstore import get_vectorstore
            _n_edit = _emb_changed = 0
            _emb_ids: list[str] = []
            for row in _rows_for_save:
                cid = row["_id"]
                o = _orig.get(cid)
                if o is None:
                    continue
                nf, na = (row["Frage"] or "").strip(), (row["Antwort"] or "").strip()
                of, oa = (o["front"] or "").strip(), (o.get("answer") or "").strip()
                if nf != of or na != oa:
                    manifest.update_card(cid, front=nf if nf != of else None,
                                         answer=na if na != oa else None)
                    if nf != of and o.get("source") == "question" and o.get("chroma_id"):
                        try:
                            get_vectorstore().update_document(o["chroma_id"], nf)
                        except Exception:  # noqa: BLE001
                            pass
                    _n_edit += 1
                nd = (row["Stapel"] or "").strip() or None
                if nd != (o.get("deck") or None):
                    manifest.assign_deck(nd, card_ids=[cid])
                nfc, nem = bool(row["Abfrage"]), bool(row["Embedding"])
                ofc, oem = bool(o.get("use_flashcard", 1)), bool(o.get("use_embedding", 1))
                if nfc != ofc or nem != oem:
                    manifest.set_card_usage([cid],
                                            use_flashcard=nfc if nfc != ofc else None,
                                            use_embedding=nem if nem != oem else None)
                    if nem != oem:
                        _emb_ids.append(cid)
            if _emb_ids:
                _r = study.apply_embedding_flags(_emb_ids)
                _emb_changed = _r["removed"] + _r["added"]
            st.session_state["_mv_flash"] = (
                f"Gespeichert. {_n_edit} Frage/Antwort-Änderung(en), "
                f"{_emb_changed} Index-Anpassung(en).")
            st.rerun()

        _also_chroma = _b2.checkbox("beim Löschen auch aus Suchindex", key="mv_delchroma",
                                    help="Entfernt die Frage zusätzlich aus dem Katalog/Suchindex.")
        if delete_button("🗑️ Auswahl löschen", token="cards:sel",
                         body=f"**{len(_sel)}** ausgewählte Karte(n) wirklich löschen?",
                         key="mv_del_sel", disabled=not _sel):
            _chroma = manifest.delete_card_ids(_sel)
            if _also_chroma and _chroma:
                try:
                    from ragapp.retrieval.vectorstore import get_vectorstore
                    get_vectorstore().delete_by_ids(_chroma)
                except Exception:  # noqa: BLE001
                    pass
            _flash_card_wipe(len(_sel), max(0, _mv_total - len(_sel)))
            st.rerun()

        _wipe_scope = []
        if _mv_subj_arg:
            _wipe_scope.append(f"Fach „{_fach_label(_mv_subj_arg)}“")
        if _mv_doc_name:
            _wipe_scope.append(f"Dokument „{_mv_doc_name}“")
        _wipe_where = " und ".join(_wipe_scope) if _wipe_scope else "der aktuellen Filterung"
        _wipe_all_ok = st.checkbox(
            f"Ja, wirklich ALLE {_mv_total} Karten {_wipe_where} löschen",
            key="mv_wipe_all_ok",
            help="Unabhängig von der Zeilen-Anzeige. Der Filter bleibt danach stehen.")
        if not _wipe_scope:
            st.caption("Ohne Fach- oder Dokumentfilter betrifft das **alle** Karteikarten.")
        if delete_button(f"🗑️ Alle {_mv_total} im Filter löschen",
                         token="cards:wipe",
                         body=f"Wirklich **alle {_mv_total}** Karten {_wipe_where} löschen?",
                         key="mv_wipe_all", type="secondary",
                         disabled=not _wipe_all_ok or _mv_total == 0):
            _wipe_ids = manifest.list_card_ids_matching(**_mv_wipe_kw)
            _chroma = manifest.delete_card_ids(_wipe_ids)
            if _also_chroma and _chroma:
                try:
                    from ragapp.retrieval.vectorstore import get_vectorstore
                    get_vectorstore().delete_by_ids(_chroma)
                except Exception:  # noqa: BLE001
                    pass
            _flash_card_wipe(len(_wipe_ids), 0)
            st.session_state["mv_wipe_all_ok"] = False
            st.rerun()

        if _b3.button("🤖 Antworten für Auswahl", use_container_width=True, disabled=not _sel):
            with st.status("Erzeuge Musterlösungen …", expanded=True) as s:
                _ar = study.generate_answers(card_ids=_sel, progress=lambda m: s.update(label=m))
                s.update(label="Fertig", state="complete")
            if _show_answer_result(_ar):
                st.session_state["_mv_flash"] = (
                    f"✅ {_ar['filled']} Antwort(en) erzeugt"
                    + (f", {_ar.get('ungrounded') or 0} verworfen"
                       if _ar.get("ungrounded") else "")
                    + (f", {_ar.get('unchecked') or 0} ungeprüft behalten"
                       if _ar.get("unchecked") else "")
                    + ".")
                st.rerun()

        if _b4.button("⏸️ Auswahl pausieren", use_container_width=True, disabled=not _sel,
                      help="Pausierte Karten erscheinen nicht in Lernrunden (können später "
                           "wieder aktiviert werden)."):
            n = manifest.set_suspended(_sel, True)
            st.session_state["_mv_flash"] = f"{n} Karte(n) pausiert."
            st.rerun()
        if st.button("▶️ Auswahl wieder aktivieren", disabled=not _sel,
                     help="Hebt die Pause für die ausgewählten Karten auf."):
            n = manifest.set_suspended(_sel, False)
            st.session_state["_mv_flash"] = f"{n} Karte(n) wieder aktiv."
            st.rerun()
        if st.button("🔎 Belege der Auswahl prüfen", use_container_width=True, disabled=not _sel):
            with st.status("Prüfe Belege …", expanded=True) as s:
                _rr = study.recheck_answers(card_ids=_sel, progress=lambda m: s.update(label=m))
                s.update(label="Fertig", state="complete")
            if _show_recheck_result(_rr):
                st.session_state["_mv_flash"] = (
                    f"{_rr.get('kept') or 0} behalten, {_rr.get('cleared') or 0} entfernt.")
                st.rerun()

        _asg1, _asg2 = st.columns([2, 1])
        _asg_name = _asg1.text_input("Ausgewählte einem Stapel zuordnen", key="mv_assign_name",
                                     placeholder="z. B. Integralrechnung")
        if _asg2.button("➕ zu Stapel", use_container_width=True,
                        disabled=not _sel or not _asg_name.strip()):
            _n = manifest.assign_deck(_asg_name.strip(), card_ids=_sel)
            st.session_state["_mv_flash"] = (
                f"{_n} Karte(n) dem Stapel „{_asg_name.strip()}“ zugeordnet.")
            st.rerun()
