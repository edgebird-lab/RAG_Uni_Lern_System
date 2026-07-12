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
import pandas as pd

from ragapp import manifest, study
from ragapp.config import settings, SUBJECT_LABELS

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
            st.warning("Kein Fragenmaterial gefunden – erst auf **📥 Import** Fragen "
                       "anreichern bzw. den Klausur-Lernkatalog erzeugen.")
        elif res["neu"] == 0:
            st.info("Alles aktuell – keine neuen Karten.")
        else:
            st.success(f"➕ {res['neu']} neue Karten hinzugefügt.")

    st.divider()
    _offen = manifest.count_cards(subject=_hv_subj_arg, source="question", only_unanswered=True)
    st.caption(f"**Musterlösungen erzeugen:** {_offen} Karte(n) zeigen bisher nur den "
               "Originaltext. Die KI erzeugt daraus echte Antworten (~20 s pro Karte).")
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
        if ares["status"] == "llm_error":
            st.error(f"❌ Modellfehler: {ares.get('error_msg', '')} – prüfe unter "
                     "**⚙️ Einstellungen** ein laufendes Modell (z. B. `gemma3:4b`).")
        elif ares["status"] == "nothing_to_do":
            st.info("Alle Karten haben bereits eine Antwort.")
        elif ares["filled"] == 0:
            st.warning("Es konnte keine Antwort erzeugt werden (der Text gab nichts her).")
        else:
            st.success(f"✅ {ares['filled']} Musterlösung(en) erzeugt.")
            st.rerun()

with st.expander("🗂️ Stapel verwalten (Themen trennen)"):
    st.caption("Ordne Karten frei benannten Stapeln zu (z. B. Integralrechnung oder "
               "Statistik-Grundlagen), um verschiedene Themen gezielt zu lernen.")
    _ov = [o for o in manifest.deck_overview() if o["deck"]]
    if _ov:
        st.dataframe(pd.DataFrame([{"Stapel": o["deck"], "Karten": o["total"],
                                    "fällig": o["due"]} for o in _ov]),
                     hide_index=True, use_container_width=True)
    _faecher_v = manifest.study_subjects()
    _doc_map = {f"{d['filename']} · {_fach_label(d['subject'] or '—')}": d["doc_id"]
                for d in manifest.list_documents()}
    _name = st.text_input("Stapelname", placeholder="z. B. Integralrechnung", key="deck_name")
    _art = st.radio("Karten auswählen nach", ["Fach", "Dokument"], horizontal=True, key="deck_art")
    _subj_sel, _doc_sel = None, None
    if _art == "Fach":
        _fs = st.multiselect("Fächer", _faecher_v, format_func=_fach_label, key="deck_fs")
        _subj_sel = _fs or None
    else:
        _ds = st.multiselect("Dokumente", list(_doc_map.keys()), key="deck_ds")
        _doc_sel = [_doc_map[k] for k in _ds] or None
    if st.button("➕ Zu Stapel hinzufügen"):
        if not (_name or "").strip():
            st.warning("Bitte einen Stapelnamen eingeben.")
        elif not (_subj_sel or _doc_sel):
            st.warning("Bitte Fächer oder Dokumente auswählen.")
        else:
            _n = manifest.assign_deck(_name.strip(), doc_ids=_doc_sel, subjects=_subj_sel)
            if _n:
                st.success(f"{_n} Karten dem Stapel `{_name.strip()}` zugeordnet.")
                st.rerun()
            else:
                st.warning("0 Karten zugeordnet – zu dieser Auswahl gibt es noch keine "
                           "Karten (erst Fragen/Katalog erzeugen).")
    _ov3 = [o for o in manifest.deck_overview() if o["deck"]]
    if _ov3:
        st.markdown("**Stapel verwalten:**")
        st.caption("**Auflösen** hebt nur die Zuordnung auf (Karten bleiben). "
                   "**Löschen** entfernt den Stapel samt seinen Karten.")
        for _o in _ov3:
            _d = _o["deck"]
            _dc1, _dc2, _dc3 = st.columns([3, 1, 1])
            _dc1.markdown(f"🗂️ **{_d}** · {_o['total']} Karten")
            if _dc2.button("Auflösen", key=f"dissolve_{_d}", use_container_width=True):
                manifest.dissolve_deck(_d)
                st.success(f"Stapel „{_d}“ aufgelöst (Karten bleiben erhalten).")
                st.rerun()
            if _dc3.button("🗑️ Löschen", key=f"delete_{_d}", use_container_width=True):
                manifest.delete_deck(_d)
                st.success(f"Stapel „{_d}“ samt {_o['total']} Karten gelöscht.")
                st.rerun()

with st.expander("📋 Karten & Fragen verwalten (auswählen, bearbeiten, löschen)"):
    st.caption("Frage/Antwort direkt in der Tabelle bearbeiten. Häkchen setzen, um Karten "
               "zu löschen, einem Stapel zuzuordnen oder Antworten zu erzeugen. "
               "**Abfrage** = in der Lernrunde zeigen · **Embedding** = Frage im Suchindex halten.")
    _mf1, _mf2, _mf3 = st.columns(3)
    _mv_subj = _mf1.selectbox("Fach", ["Alle"] + manifest.study_subjects(),
                              format_func=lambda s: "Alle" if s == "Alle" else _fach_label(s),
                              key="mv_subj")
    _mv_decks = manifest.list_decks()
    _mv_deck = _mf2.selectbox("Stapel", ["Alle", "— ohne Stapel —"] + _mv_decks, key="mv_deck")
    _mv_limit = _mf3.number_input("Max. Zeilen", min_value=10, max_value=2000, value=200,
                                  step=10, key="mv_limit")
    _mv_subj_arg = None if _mv_subj == "Alle" else _mv_subj
    _mv_deck_arg = (None if _mv_deck == "Alle"
                    else "__none__" if _mv_deck.startswith("—") else _mv_deck)
    _mv_rows = manifest.list_cards(subject=_mv_subj_arg, deck=_mv_deck_arg, limit=int(_mv_limit))
    _mv_total = manifest.count_cards(subject=_mv_subj_arg, deck=_mv_deck_arg)

    if not _mv_rows:
        st.info("Keine Karten für diese Auswahl.")
    else:
        _orig = {r["card_id"]: r for r in _mv_rows}
        _df = pd.DataFrame([{
            "✓": False,
            "Frage": r["front"],
            "Antwort": r.get("answer") or "",
            "Fach": _fach_label(r.get("subject") or ""),
            "Stapel": r.get("deck") or "",
            "Abfrage": bool(r.get("use_flashcard", 1)),
            "Embedding": bool(r.get("use_embedding", 1)),
            "_id": r["card_id"],
        } for r in _mv_rows])
        _edited = st.data_editor(
            _df, hide_index=True, use_container_width=True, key="mv_editor",
            column_config={
                "✓": st.column_config.CheckboxColumn(width="small"),
                "Frage": st.column_config.TextColumn(width="large"),
                "Antwort": st.column_config.TextColumn(width="large"),
                "Fach": st.column_config.TextColumn(disabled=True),
                "Stapel": st.column_config.TextColumn(help="Stapelname (leer = kein Stapel)"),
                "Abfrage": st.column_config.CheckboxColumn(),
                "Embedding": st.column_config.CheckboxColumn(),
                "_id": None,
            },
        )
        _sel = [row["_id"] for _, row in _edited.iterrows() if row["✓"]]
        st.caption(f"{len(_sel)} ausgewählt · {len(_mv_rows)} angezeigt · {_mv_total} gesamt "
                   "(mit dieser Filterung)")

        _b1, _b2, _b3 = st.columns(3)
        if _b1.button("💾 Änderungen speichern", use_container_width=True):
            from ragapp.retrieval.vectorstore import get_vectorstore
            _n_edit = _emb_changed = 0
            _emb_ids: list[str] = []
            for _, row in _edited.iterrows():
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
            st.success(f"Gespeichert. {_n_edit} Frage/Antwort-Änderung(en), "
                       f"{_emb_changed} Index-Anpassung(en).")
            st.rerun()

        _also_chroma = _b2.checkbox("beim Löschen auch aus Suchindex", key="mv_delchroma",
                                    help="Entfernt die Frage zusätzlich aus dem Katalog/Suchindex.")
        if _b2.button("🗑️ Auswahl löschen", use_container_width=True, disabled=not _sel):
            _chroma = manifest.delete_card_ids(_sel)
            if _also_chroma and _chroma:
                try:
                    from ragapp.retrieval.vectorstore import get_vectorstore
                    get_vectorstore().delete_by_ids(_chroma)
                except Exception:  # noqa: BLE001
                    pass
            st.success(f"{len(_sel)} Karte(n) gelöscht"
                       + (" (auch aus dem Suchindex)." if _also_chroma else "."))
            st.rerun()

        if _b3.button("🤖 Antworten für Auswahl", use_container_width=True, disabled=not _sel):
            with st.status("Erzeuge Musterlösungen …", expanded=True) as s:
                _ar = study.generate_answers(card_ids=_sel, progress=lambda m: s.update(label=m))
                s.update(label="Fertig", state="complete")
            if _ar["status"] == "llm_error":
                st.error(f"❌ Modellfehler: {_ar.get('error_msg', '')}")
            elif _ar["filled"] == 0:
                st.info("Nichts zu erzeugen (Auswahl hat schon Antworten oder ergab keine).")
            else:
                st.success(f"✅ {_ar['filled']} Antwort(en) erzeugt.")
                st.rerun()

        _asg1, _asg2 = st.columns([2, 1])
        _asg_name = _asg1.text_input("Ausgewählte einem Stapel zuordnen", key="mv_assign_name",
                                     placeholder="z. B. Integralrechnung")
        if _asg2.button("➕ zu Stapel", use_container_width=True,
                        disabled=not _sel or not _asg_name.strip()):
            _n = manifest.assign_deck(_asg_name.strip(), card_ids=_sel)
            st.success(f"{_n} Karte(n) dem Stapel „{_asg_name.strip()}“ zugeordnet.")
            st.rerun()

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
    st.subheader("Lernrunde zusammenstellen")
    # 1) Fach
    _faecher = manifest.study_subjects()
    _subj_pick = st.selectbox(
        "Fach", ["Alle Fächer"] + _faecher,
        format_func=lambda s: "Alle Fächer" if s == "Alle Fächer" else _fach_label(s))
    subj = None if _subj_pick == "Alle Fächer" else _subj_pick

    # Klausur-Countdown (falls für dieses Fach ein Termin gesetzt ist)
    if subj:
        from ragapp import planner, analytics
        _ex = manifest.get_exam(subj)
        if _ex and _ex.get("exam_date"):
            _dte = planner.days_to_exam(_ex["exam_date"])
            _rd = analytics.subject_readiness(subj)["readiness_pct"]
            st.info(f"🗓️ Klausur **{_fach_label(subj)}**: {planner.humanize_days(_dte)} "
                    f"({_ex['exam_date']}) · Bereitschaft **{_rd} %**")

    # 2) Stapel-Mehrfachauswahl (welche der Stapel dieses Fachs)
    _decks_here = manifest.list_decks(subj)
    _deck_opts = list(_decks_here) + ["— ohne Stapel —"]
    _deck_pick = st.multiselect(
        "Stapel (leer = alle)", _deck_opts,
        help="Wähle gezielt einzelne Stapel – z. B. 2 von 5 Themen eines Fachs. "
             "Leer lassen = alle Karten des Fachs.")
    decks = None
    if _deck_pick:
        decks = ["__none__" if d == "— ohne Stapel —" else d for d in _deck_pick]

    # 3) Zahlen zur Auswahl
    _fc = manifest.review_counts(subj, decks=decks)
    _neu_heute = manifest.count_new_today(subj, decks=decks)
    faellig = _fc["due"]

    # 4) Tages-Limit neuer Karten
    _c1, _c2 = st.columns(2)
    _new_per_day = _c1.number_input(
        "Neue Karten pro Tag", min_value=0, max_value=500,
        value=int(getattr(settings, "SRS_NEW_PER_DAY", 20)), step=5,
        help="0 = unbegrenzt. Bereits heute gelernte neue Karten werden angerechnet.")
    _rest_neu = None if _new_per_day == 0 else max(0, int(_new_per_day) - _neu_heute)
    _c2.metric("Heute neu gelernt", _neu_heute,
               help="Zählt gegen dein Tages-Limit neuer Karten.")

    _total_avail = _fc.get("total", 0)
    _srs_max = int(getattr(settings, "SRS_MAX_PER_SESSION", 100))
    _ck1, _ck2 = st.columns(2)
    _interleave = _ck1.checkbox(
        "🔀 Themen mischen (Interleaving)", value=False,
        help="Mischt die Karten verschränkt über Themen statt blockweise. Trainiert "
             "das Erkennen, welcher Ansatz/welche Formel zu welcher Aufgabe gehört – "
             "genau das prüft eine Klausur, deren Aufgaben ungeordnet kommen.")
    _cram = _ck2.checkbox(
        "🔥 Klausur-Modus (Cram)", value=False,
        help="Füllt die Runde auch mit den schwächsten NOCH NICHT fälligen Karten auf – "
             "für die heiße Phase kurz vor der Klausur (auch wenn gerade nichts fällig ist).")
    _mode_lbl = st.radio(
        "Übungsmodus",
        ["👁️ Aufdecken", "✍️ Tippen & benoten", "🧩 Lückentext", "🔤 Multiple Choice"],
        horizontal=True,
        help="**Aufdecken**: klassisch, du bewertest dich selbst. **Tippen & benoten**: "
             "du formulierst die Antwort frei, die KI vergibt Teilpunkte und nennt, was "
             "fehlt (stärkster Lerneffekt). **Lückentext**: fülle den fehlenden Fachbegriff "
             "(sofort, ohne KI). **Multiple Choice**: wähle aus plausiblen Optionen "
             "(objektives Ergebnis, trainiert Unterscheidung).")
    _mode_map = {"👁️ Aufdecken": "reveal", "✍️ Tippen & benoten": "type",
                 "🧩 Lückentext": "cloze", "🔤 Multiple Choice": "mcq"}

    # Fächerübergreifende Prüfungsphasen-Runde (nur sinnvoll bei ≥ 2 Fächern)
    if len(_faecher) >= 2:
        with st.container(border=True):
            st.markdown("**🎓 Prüfungsphase** – alle Fächer gemischt, nach Klausurnähe & "
                        "Wissenslücke priorisiert (fächerübergreifendes Interleaving).")
            _pp1, _pp2, _pp3 = st.columns([1, 1, 1])
            _pp_n = _pp1.number_input("Karten", min_value=5, max_value=_srs_max, value=20,
                                      step=5, key="phase_n")
            _pp_cram = _pp2.checkbox("🔥 Cram", key="phase_cram",
                                     help="Auch noch nicht fällige, schwache Karten ziehen.")
            if _pp3.button("▶️ Prüfungsphase", key="phase_start", use_container_width=True):
                from ragapp import planner as _pl
                _pk = _pl.phase_round(limit=int(_pp_n), cram=bool(_pp_cram))
                if not _pk:
                    st.info("Gerade fächerübergreifend nichts fällig – aktiviere 🔥 Cram.")
                else:
                    st.session_state[Q] = _pk
                    st.session_state[ACTIVE] = True
                    st.session_state[REVEAL] = False
                    st.session_state[TALLY] = {"gewusst": 0, "halb": 0, "nicht": 0}
                    st.session_state[ROUND] = len(_pk)
                    st.session_state["_study_mode"] = _mode_map[_mode_lbl]
                    st.rerun()

    if faellig == 0 and not _cram:
        st.success("✅ Für diese Auswahl ist gerade **nichts fällig** – gut gemacht! "
                   "Komm später wieder, wähle etwas anderes, oder aktiviere den "
                   "🔥 **Klausur-Modus**, um trotzdem die schwächsten Karten zu üben.")
    else:
        _cap = _total_avail if _cram else faellig
        _maxr = int(max(1, min(_cap, _srs_max)))
        anzahl = st.slider("Karten in dieser Runde", min_value=1, max_value=_maxr,
                           value=int(min(20, _maxr)))
        _hinweis = (f"{anzahl} · {faellig} fällig"
                    + (f" · max. {_rest_neu} neue" if _rest_neu is not None else "")
                    + (" · 🔥 Cram" if _cram else ""))
        if st.button(f"▶️ Lernrunde starten ({_hinweis})",
                     type="primary", use_container_width=True):
            karten = manifest.get_due_cards(subj, limit=int(anzahl), deck=None,
                                            decks=decks, new_limit=_rest_neu,
                                            order="interleave" if _interleave else "due",
                                            cram=_cram)
            if not karten:
                st.warning("Für diese Auswahl wurden keine Karten gefunden.")
            else:
                st.session_state[Q] = karten
                st.session_state[ACTIVE] = True
                st.session_state[REVEAL] = False
                st.session_state[TALLY] = {"gewusst": 0, "halb": 0, "nicht": 0}
                st.session_state[ROUND] = len(karten)
                st.session_state["_study_mode"] = _mode_map[_mode_lbl]
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
    _capc, _stopc = st.columns([3, 1])
    _capc.caption(f"📚 {_tt}" + (f" · {_topic}" if _topic else ""))
    # Runde JEDERZEIT beenden bzw. Fach/Stapel wechseln (z. B. nach 5 Karten oder wenn
    # das Tagesziel erreicht ist). Schon bewertete Karten sind bereits gespeichert.
    if _stopc.button("⏹ Beenden", use_container_width=True,
                     help="Lernrunde beenden und zurück zur Auswahl (Fach/Stapel "
                          "wechseln). Bereits bewertete Karten bleiben gespeichert."):
        for _k in (Q, ACTIVE, REVEAL, TALLY, ROUND):
            st.session_state.pop(_k, None)
        st.rerun()

    # Vorderseite
    st.markdown(f"<div class='karte karte-frage'>{karte['front']}</div>",
                unsafe_allow_html=True)
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
            cz = st.session_state.get("_cloze")
            if cz is None:
                cz = grading.make_cloze(_ref) or ["", []]
                st.session_state["_cloze"] = cz
            if cz[1]:
                st.markdown(f"<div class='karte'>🧩 {cz[0]}</div>", unsafe_allow_html=True)
                st.write("")
                st.text_input("Fehlender Begriff", key="_cloze_in",
                              placeholder="Wort in die Lücke …")
                if st.button("🧩 Prüfen", type="primary", use_container_width=True):
                    st.session_state["_cloze_ok"] = grading.check_cloze(
                        st.session_state.get("_cloze_in", ""), cz[1])
                    st.session_state[REVEAL] = True
                    st.rerun()
            else:
                st.caption("Für diese Karte ließ sich kein Lückentext bilden – decke normal auf.")
                if st.button("👁️ Antwort zeigen", type="primary", use_container_width=True):
                    st.session_state[REVEAL] = True
                    st.rerun()
        elif _mode == "mcq":
            from ragapp import grading
            mcq = st.session_state.get("_mcq")
            if mcq is None:
                with st.spinner("Erzeuge Antwortoptionen …"):
                    mcq = grading.generate_mcq(karte.get("front", ""), _ref) or {}
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
                st.caption("Konnte keine Optionen erzeugen – decke normal auf.")
                if st.button("👁️ Antwort zeigen", type="primary", use_container_width=True):
                    st.session_state[REVEAL] = True
                    st.rerun()
        else:  # reveal (klassisch, mit Selbst-Konfidenz/JOL)
            st.caption("Überlege (oder tippe für dich) die Antwort – dann aufdecken.")
            _conf_lbl = st.radio(
                "Wie sicher bist du dir?", ["😃 sicher", "😐 mittel", "😟 unsicher"],
                index=None, horizontal=True, key="_jol",
                help="Selbsteinschätzung VOR dem Aufdecken. Wer sich sicher ist und trotzdem "
                     "danebenliegt, hat eine besonders hartnäckige Lücke – die kommt dann "
                     "schneller wieder dran (Hypercorrection).")
            st.session_state["_study_conf"] = {
                "😃 sicher": "sicher", "😐 mittel": "mittel", "😟 unsicher": "unsicher"
            }.get(_conf_lbl)
            if st.button("👁️ Antwort zeigen", type="primary", use_container_width=True):
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
                st.caption("Automatische Benotung war nicht möglich – schätze selbst ein.")
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
            st.markdown(_ans)
            if (karte.get("back") or "").strip() and karte.get("source") == "question":
                with st.expander("📄 Beleg / Originaltext"):
                    st.markdown(karte["back"])
        else:
            st.warning("Für diese Karte gibt es noch **keine** Musterlösung – gezeigt "
                       "wird der Originaltext. Tipp: oben unter **⚙️ Karten verwalten → "
                       "Antworten erzeugen** die KI-Antworten nachziehen.")
            st.markdown(karte.get("back") or "")
        st.write("")
        st.caption("Wie gut wusstest du es?")
        _sg = st.session_state.get("_study_suggest")
        if _sg is not None:
            _sgtxt = {study.GEWUSST: "✅ Gewusst", study.HALB: "🟡 Halb",
                      study.NICHT: "❌ Nicht gewusst"}.get(_sg, "")
            st.caption(f"Vorschlag aus dem Ergebnis: **{_sgtxt}** – du entscheidest.")
        r1, r2, r3 = st.columns(3)

        def _bewerten(rating: int) -> None:
            _conf = st.session_state.get("_study_conf")
            nxt = study.rate_card(karte, rating, confidence=_conf)
            st.toast(f"Nächste Wiederholung: {study.humanize_due(nxt['due'])}")
            t = st.session_state[TALLY]
            t["gewusst" if rating == study.GEWUSST else
              "halb" if rating == study.HALB else "nicht"] += 1
            q = st.session_state[Q]
            q.pop(0)
            if rating == study.NICHT:
                # In derselben Runde erneut ueben (mit zurueckgesetztem Zustand).
                q.append({**karte, **nxt})
            st.session_state[REVEAL] = False
            # Alle Modus-Zustaende fuer die naechste Karte zuruecksetzen.
            for _k in ("_study_conf", "_jol", "_typed_ans", "_grade", "_cloze",
                       "_cloze_in", "_cloze_ok", "_mcq", "_mcq_sel", "_mcq_ok",
                       "_study_suggest"):
                st.session_state.pop(_k, None)
            st.rerun()

        if r1.button("❌ Nicht gewusst", use_container_width=True):
            _bewerten(study.NICHT)
        if r2.button("🟡 Halb", use_container_width=True):
            _bewerten(study.HALB)
        if r3.button("✅ Gewusst", use_container_width=True):
            _bewerten(study.GEWUSST)
