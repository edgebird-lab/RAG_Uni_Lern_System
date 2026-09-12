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
page_boot("🎓 Lernen", page_title="Lernen", icon="🎓", layout="wide", accent="lernen")

from ragapp.ui._style import card

# Nur noch das seiten-spezifische Layout; die Karteikarten-Optik (hell + dunkel)
# kommt jetzt zentral aus ragapp.ui._theme.apply_theme().
st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 900px;}
h1 {font-weight:750; letter-spacing:-0.5px;}
</style>
""", unsafe_allow_html=True)


st.caption("Karteikarten aus deinen eigenen Unterlagen – aktives Abfragen mit "
           "automatischer Wiederholungs-Planung (Spaced Repetition). Das ist der "
           "wirksamste Klausur-Hebel.")

# Schwere Importe/Datenabfragen unter kleinem Ladehinweis; die import-Statements
# binden im Modulscope, daher funktionieren alle spaeteren Verwendungen unveraendert.
with skeleton("Lernen wird geladen ..."):
    import pandas as pd
    from ragapp import manifest, study
    from ragapp.config import settings, SUBJECT_LABELS


def _fach_label(code: str) -> str:
    return SUBJECT_LABELS.get(code, code)


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
with card("kopfzeile"):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Karten gesamt", _counts["total"])
    c2.metric("Jetzt fällig", _counts["due"])
    c3.metric("Neu", _counts["neu"])
    c4.metric("Schon geübt", _counts["gelernt"])

# Hinweis nach Import/Fragen-Anreicherung: Karten oft noch nicht geerntet
if st.session_state.pop("_needs_card_harvest", None):
    st.info("Neue Fragen wurden indexiert. Tippe **🔄 Karten aktualisieren** unten, "
            "damit sie in der Lernrunde erscheinen.")
_offen_global = manifest.count_cards(source="question", only_unanswered=True)
if _offen_global > 0:
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
        if ares.get("filled"):
            st.success(f"✅ {ares['filled']} Musterlösung(en) erzeugt.")
            st.rerun()
        elif ares.get("status") == "llm_error":
            st.error(f"❌ Modellfehler: {ares.get('error_msg', '')}")

# key= haelt den Auf/Zu-Zustand fest - ohne key faellt der Expander sonst bei
# JEDEM Rerun (auch nur durch die "Fach"-Auswahl DARIN) auf zugeklappt zurueck,
# bevor der Klick auf den eigentlichen Knopf erfolgt (gleiches Muster wie beim
# Ausspracheregeln-Expander in Audio-Overview behoben).
with st.expander("⚙️ Karten verwalten", key="hv_expander"):
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

with st.expander("🗂️ Stapel verwalten (Fach → Dokument → Thema → Karten)",
                 expanded=False, key="dk_expander"):
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
                f"({_ov_all_unassigned['due']} fällig)."
            )
        if _ov:
            st.markdown(f"**Stapel in {_fach_label(_dk_subj)}:**")
            for _o in _ov:
                _d = _o["deck"]
                _dc1, _dc2, _dc3, _dc4 = st.columns([3, 1, 1, 1])
                _dc1.markdown(
                    f"🗂️ **{_d}** · {_o['total']} Karten · {_o['due']} fällig"
                )
                if _dc2.button("Auflösen", key=f"dissolve_{_dk_subj}_{_d}",
                               use_container_width=True,
                               help="Zuordnung aufheben, Karten bleiben erhalten."):
                    manifest.dissolve_deck(_d)
                    st.success(f"Stapel „{_d}“ aufgelöst.")
                    st.rerun()
                if _dc3.button("🗑️", key=f"delete_{_dk_subj}_{_d}",
                               use_container_width=True,
                               help="Stapel samt Karten löschen."):
                    manifest.delete_deck(_d)
                    st.success(f"Stapel „{_d}“ gelöscht.")
                    st.rerun()
                with _dc4:
                    with st.popover("✏️"):
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

st.divider()

with st.expander("📋 Karten & Fragen verwalten (auswählen, bearbeiten, löschen)",
                 key="mv_expander"):
    st.caption("Frage/Antwort direkt in der Tabelle bearbeiten. Häkchen setzen, um Karten "
               "zu löschen, einem Stapel zuzuordnen oder Antworten zu erzeugen. "
               "**Abfrage** = in der Lernrunde zeigen · **Embedding** = Frage im Suchindex halten.")
    _mf1, _mf2, _mf3, _mf4 = st.columns(4)
    _mv_subj = _mf1.selectbox("Fach", ["Alle"] + manifest.study_subjects(),
                              format_func=lambda s: "Alle" if s == "Alle" else _fach_label(s),
                              key="mv_subj")
    _mv_subj_arg = None if _mv_subj == "Alle" else _mv_subj
    _mv_decks = manifest.list_decks(_mv_subj_arg)
    _mv_deck = _mf2.selectbox("Stapel", ["Alle", "— ohne Stapel —"] + _mv_decks, key="mv_deck")
    _mv_docs = manifest.list_docs_with_cards(subject=_mv_subj_arg)
    _mv_doc_map = {d["doc_id"]: d["filename"] for d in _mv_docs if d.get("doc_id")}
    _mv_doc = _mf3.selectbox(
        "Dokument",
        ["Alle"] + list(_mv_doc_map.keys()),
        format_func=lambda k: "Alle" if k == "Alle" else _mv_doc_map.get(k, k),
        key="mv_doc",
    )
    _mv_limit = _mf4.number_input("Max. Zeilen", min_value=10, max_value=2000, value=200,
                                  step=10, key="mv_limit")
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
            limit=int(_mv_limit),
        )
        _mv_total = manifest.count_find_cards(
            subject=_mv_subj_arg,
            doc_ids=None if _mv_doc == "Alle" else [_mv_doc],
            topics=_mv_topic or None,
            deck=_mv_deck_arg,
        )
    else:
        _mv_rows = manifest.list_cards(subject=_mv_subj_arg, deck=_mv_deck_arg,
                                       limit=int(_mv_limit))
        _mv_total = manifest.count_cards(subject=_mv_subj_arg, deck=_mv_deck_arg)

    if not _mv_rows:
        st.info("Keine Karten für diese Auswahl.")
    else:
        _orig = {r["card_id"]: r for r in _mv_rows}
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
        _edited = st.data_editor(
            _df, hide_index=True, use_container_width=True, key="mv_editor",
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
        st.caption(f"{len(_sel)} ausgewählt · {len(_mv_rows)} angezeigt · {_mv_total} gesamt "
                   "(mit dieser Filterung)")

        _b1, _b2, _b3, _b4 = st.columns(4)
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

        if _b4.button("⏸️ Auswahl pausieren", use_container_width=True, disabled=not _sel,
                      help="Pausierte Karten erscheinen nicht in Lernrunden (können später "
                           "wieder aktiviert werden)."):
            n = manifest.set_suspended(_sel, True)
            st.success(f"{n} Karte(n) pausiert.")
            st.rerun()
        if st.button("▶️ Auswahl wieder aktivieren", disabled=not _sel,
                     help="Hebt die Pause für die ausgewählten Karten auf."):
            n = manifest.set_suspended(_sel, False)
            st.success(f"{n} Karte(n) wieder aktiv.")
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
        "Stapel (leer = alle)", _deck_opts, placeholder="Alle",
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
                    st.session_state["_study_combo"] = 0
                    st.session_state["_study_combo_best"] = 0
                    st.session_state["_study_leech_cleared"] = 0
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
                st.session_state["_study_combo"] = 0
                st.session_state["_study_combo_best"] = 0
                st.session_state["_study_leech_cleared"] = 0
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
    _combo_now = st.session_state.get("_study_combo", 0)
    # Kombo bleibt waehrend der GANZEN Runde sichtbar (nicht nur im kurzen
    # Toast direkt nach der Bewertung) - erst ab 2 in Folge, damit nicht schon
    # die allererste Karte einer neuen Serie eine Anzeige bekommt.
    _combo_suffix = f"  ·  🔥 {_combo_now}x in Folge" if _combo_now >= 2 else ""
    _capc.caption(f"📚 {_tt}" + (f" · {_topic}" if _topic else "") + _combo_suffix)
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
                st.caption("Konnte keine Optionen erzeugen – decke normal auf.")
                if st.button("👁️ Antwort zeigen", type="primary", use_container_width=True):
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
            if rating == study.NICHT:
                # In derselben Runde erneut ueben (mit zurueckgesetztem Zustand).
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
        # Einmalig auf dem PARENT-Dokument gebunden (siehe _theme_toggle_html-
        # Kommentar in _style.py: Streamlit macht keinen echten Seiten-Reload,
        # ein erneutes Binden bei jedem Rerun wuerde denselben Tastendruck
        # sonst mehrfach ausloesen) - sucht die Buttons bei JEDEM Tastendruck
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
      doc.addEventListener('touchstart', function(e) {
        var el = e.target && e.target.closest ? e.target.closest('.karte-frage') : null;
        if (!el || !e.touches || !e.touches.length) { sx = null; return; }
        sx = e.touches[0].clientX; sy = e.touches[0].clientY; st0 = Date.now();
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
