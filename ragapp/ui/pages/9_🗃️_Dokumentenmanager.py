"""
RAG-Lernsystem: Seite „Dokumentenmanager" (Ordner, Upload, Bibliothek)
=======================================================================
Fach-Ordner, Hochladen/Indexieren, Vorschau-Kacheln, Seitenzahl, Löschen.
Fragen-Anreicherung und Karten-Ernte liegen bei den Karteikarten.
"""
from __future__ import annotations

import sys
import pathlib

_p = pathlib.Path(__file__).resolve()
for _anc in _p.parents:
    if (_anc / "ragapp").is_dir():
        sys.path.insert(0, str(_anc))
        break

import streamlit as st

from ragapp.ui._loading import page_boot, skeleton
page_boot("🗃️ Dokumentenmanager", page_title="Dokumentenmanager", icon="🗃️", layout="wide",
         accent="dokumente")

from ragapp.ui._style import card

st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1250px;}
h1 {font-weight: 750; letter-spacing:-0.5px;}
</style>
""", unsafe_allow_html=True)

st.caption("Ordner = Fächer. Lade Dokumente direkt in ein Fach, sieh sie an "
           "(inkl. Seitenzahl), lösche sie hier. Auch archivierte (nicht im RAG) "
           "Dokumente tauchen auf. Fragen und Karteikarten erzeugst du unter "
           "**🎓 Karteikarten**.")

with skeleton("Dokumentenmanager wird geladen ..."):
    import pandas as pd
    from ragapp import manifest
    from ragapp.config import SUBJECT_LABELS, PROJECT_ROOT
    from ragapp.ui import _docviewer, _ingest_ui
    from ragapp.ui._thumbnails import get_thumbnail, get_text_preview

_ICONS = {"pdf": "📕", "docx": "📄", "pptx": "📊", "md": "📝", "txt": "📄", "catalog": "🗒️"}
_TEXT_PREVIEW_TYPES = ("md", "txt")


_flash = st.session_state.pop("_docmgr_flash", None)
if _flash:
    st.success(_flash)


def _fach(code: "str | None") -> str:
    return SUBJECT_LABELS.get(code, code) if code else "–"


@st.cache_data(show_spinner=False)
def _read_file_bytes(path_str: str, updated_at: float) -> bytes:
    """Datei-Bytes gecacht nach Pfad+``updated_at`` (Cache-Bruch bei Re-Ingest).
    Wird bewusst erst beim tatsächlichen Download-Wunsch aufgerufen (siehe
    Zwei-Klick-Muster unten), nicht schon beim Rendern jeder Kachel."""
    return pathlib.Path(path_str).read_bytes()


def _build_zip(docs: list[dict]) -> bytes:
    """Baut ein ZIP aus mehreren Dokumenten (Sammel-Download). Dateien, die nicht
    mehr existieren, werden stillschweigend übersprungen; Namensdopplungen bekommen
    die doc_id vorangestellt."""
    import io
    import zipfile

    buf = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for d in docs:
            path = PROJECT_ROOT / (d.get("source_path") or "")
            if not path.is_file():
                continue
            name = d["filename"]
            if name in used:
                name = f"{d['doc_id']}_{name}"
            used.add(name)
            zf.write(path, arcname=name)
    return buf.getvalue()


def _execute_purge(doc_ids: list[str], *, library: bool, index: bool,
                   cards: bool) -> dict:
    """Direkt auf der Seite, damit Streamlit nicht an einer alten ``_ingest_ui``-Signatur hängt."""
    from ragapp.ingestion.pipeline import remove_document, set_document_use_rag

    agg = {"ok": 0, "errors": [], "cards": 0, "library": 0, "index": 0,
           "cards_requested": bool(cards)}
    for did in doc_ids:
        if not did:
            continue
        try:
            if cards:
                ids = manifest.list_card_ids_matching(doc_ids=[did])
                chroma = manifest.delete_card_ids(ids)
                agg["cards"] += len(ids)
                if chroma:
                    try:
                        from ragapp.retrieval.vectorstore import get_vectorstore
                        get_vectorstore().delete_by_ids(chroma)
                    except Exception:  # noqa: BLE001
                        pass
            if library and index:
                remove_document(did)
                agg["library"] += 1
                agg["index"] += 1
            elif index:
                set_document_use_rag(did, False)
                agg["index"] += 1
            elif library:
                manifest.delete_document(did)
                agg["library"] += 1
            agg["ok"] += 1
        except Exception as exc:  # noqa: BLE001
            agg["errors"].append(str(exc))
    return agg


def _purge_flash(result: dict) -> str:
    parts: list[str] = []
    if result.get("library"):
        parts.append(f"{result['library']} Dokument(e) aus der Bibliothek")
    if result.get("index"):
        parts.append("Suchindex")
    if result.get("cards"):
        parts.append(f"{result['cards']} Karteikarte(n)")
    if result.get("errors"):
        err = " · ".join(result["errors"][:3])
        base = "Gelöscht: " + ", ".join(parts) + "." if parts else "Nichts gelöscht."
        return f"{base} Fehler: {err}"
    if not parts:
        if result.get("cards_requested"):
            return ("Keine Karteikarten zu dieser Datei gefunden – "
                    "Dokument und Index sind unverändert.")
        return "Nichts gelöscht."
    return "Gelöscht: " + ", ".join(parts) + "."


def _queue_delete(docs: list[dict]) -> None:
    st.session_state["docmgr_delete_docs"] = [dict(d) for d in docs]
    st.session_state["docmgr_purge_lib"] = True
    st.session_state["docmgr_purge_idx"] = True
    st.session_state["docmgr_purge_cards"] = True
    st.rerun()


def _dismiss_delete_dialog() -> None:
    st.session_state.pop("docmgr_delete_docs", None)


@st.dialog("🗑️ Wirklich löschen?", width="small", on_dismiss=_dismiss_delete_dialog)
def _confirm_delete_dialog(docs: list[dict]) -> None:
    names = [d.get("filename") or d.get("doc_id") or "?" for d in docs]
    shown = ", ".join(names[:3])
    if len(names) > 3:
        shown += f" (+{len(names) - 3} weitere)"
    n_cards = 0
    try:
        n_cards = len(manifest.list_card_ids_matching(
            doc_ids=[d["doc_id"] for d in docs if d.get("doc_id")]))
    except Exception:  # noqa: BLE001
        n_cards = 0
    st.markdown(f"**{len(docs)} Datei(en):** {shown}")
    st.caption("Jedes Häkchen ist unabhängig: du kannst z. B. nur die Karteikarten "
               "löschen und Dokument plus Suchindex behalten.")
    want_lib = st.checkbox("Dokument aus der Bibliothek", value=True,
                           key="docmgr_purge_lib",
                           help="Entfernt den Eintrag hier in der Übersicht. "
                                "Die Originaldatei im Ordner bleibt liegen.")
    want_idx = st.checkbox("Suchindex (Chunks, Chat-Treffer, generierte Fragen)",
                           value=True, key="docmgr_purge_idx",
                           help="Chat und Suche finden die Datei danach nicht mehr. "
                                "Das Dokument kann in der Bibliothek bleiben.")
    want_cards = st.checkbox(
        f"Zugehörige Karteikarten ({n_cards})",
        value=True, key="docmgr_purge_cards",
        help="Nur Karten, die aus genau diesen Dokumenten stammen. "
             "Dokument und Index bleiben, wenn du sie oben nicht anhakt.")
    if n_cards == 0:
        st.caption("Zu dieser Datei sind keine Karteikarten verknüpft – das Häkchen "
                   "allein löscht dann nichts.")
    if want_lib and not want_idx:
        st.warning("Ohne Suchindex bleiben Chat-Treffer erhalten (verwaiste Chunks).")
    elif want_idx and not want_lib:
        st.caption("Das Dokument bleibt in der Übersicht, ist danach aber nicht mehr "
                   "im Chat auffindbar.")
    elif want_cards and not want_lib and not want_idx:
        st.caption("Nur Karten werden entfernt. Datei und Suchindex bleiben.")
    can_go = bool(want_lib or want_idx or (want_cards and n_cards > 0))
    if not can_go:
        st.warning("Mindestens eine Option mit Inhalt wählen.")
    c1, c2 = st.columns(2)
    if c1.button("Abbrechen", use_container_width=True, key="docmgr_purge_cancel"):
        st.session_state.pop("docmgr_delete_docs", None)
        st.rerun()
    if c2.button("Jetzt löschen", type="primary", use_container_width=True,
                 disabled=not can_go, key="docmgr_purge_go"):
        res = _execute_purge(
            [d["doc_id"] for d in docs if d.get("doc_id")],
            library=bool(want_lib), index=bool(want_idx), cards=bool(want_cards))
        st.session_state.pop("docmgr_delete_docs", None)
        st.session_state["_docmgr_flash"] = _purge_flash(res)
        st.rerun()


def _selection_bar(selected: list[dict], key_prefix: str) -> None:
    """Zeigt - wenn welche ausgewählt sind - Anzahl, ZIP und Löschen. Kacheln
    und Liste führen ihre Auswahl bewusst UNABHÄNGIG (eigene Widgets, eigene
    Zustände) - einfacher und ohne Session-State-Konflikte zwischen den beiden
    Tabs (ein data_editor darf den Wert eines anderswo instanziierten Checkbox-
    Widgets nicht überschreiben)."""
    if not selected:
        return
    c1, c2, c3 = st.columns([2, 2, 2])
    c1.info(f"🗂️ {len(selected)} Dokument(e) ausgewählt.")
    with c2:
        st.download_button(
            f"⬇️ Als ZIP ({len(selected)})", data=_build_zip(selected),
            file_name="dokumente.zip", mime="application/zip",
            key=f"{key_prefix}_zip", use_container_width=True)
    if c3.button(f"🗑️ {len(selected)} löschen …", type="secondary",
                 key=f"{key_prefix}_del", use_container_width=True):
        _queue_delete(selected)


@st.dialog("📄 Dokument ansehen", width="large")
def _view_doc_dialog(d: dict) -> None:
    _pages = _ingest_ui.document_page_label(d)
    st.markdown(f"**{d['filename']}**  ·  Fach: {_fach(d['subject'])}"
               + f"  ·  {_pages}"
               + ("  ·  ⚪ archiviert (nicht im RAG)" if not d.get("use_rag", 1) else ""))
    path = PROJECT_ROOT / (d.get("source_path") or "")
    if not path.is_file():
        st.warning("Originaldatei nicht gefunden.")
        return

    if (d.get("filetype") or "").lower() == "pdf":
        n_pages = _docviewer.pdf_page_count(path)
        st.caption(f"PDF · **{n_pages} Seite(n)**" if n_pages else "PDF · Seitenzahl unbekannt")
        page = (st.number_input("Seite", min_value=1, max_value=max(1, n_pages), value=1,
                                key=f"docmgr_page_{d['doc_id']}")
               if n_pages > 1 else 1)
        png = _docviewer.render_pdf_page(path, int(page))
        if png:
            st.image(png, use_container_width=True)
            st.caption(f"Seite {int(page)} von {n_pages}")
        else:
            st.warning("Seite konnte nicht gerendert werden.")
    else:
        full = _docviewer.load_full_text(path)
        st.text_area("Inhalt", value=full or "(kein Text extrahierbar)", height=380,
                    disabled=True, key=f"docmgr_full_{d['doc_id']}")

    st.divider()
    st.markdown("##### 🏷️ Kategorien")
    _new_tags = st.text_input("Kategorien (kommagetrennt)", value=d.get("tags") or "",
                              key=f"docmgr_tags_{d['doc_id']}")
    tcol1, tcol2 = st.columns(2)
    if tcol1.button("💾 Kategorien speichern", key=f"docmgr_tagsave_{d['doc_id']}",
                    use_container_width=True):
        manifest.set_document_tags(d["doc_id"], _new_tags)
        st.success("Gespeichert.")
        st.rerun()
    tcol2.download_button(
        "⬇️ Herunterladen", data=_read_file_bytes(str(path), d.get("updated_at") or 0),
        file_name=d["filename"], key=f"docmgr_dldlg_{d['doc_id']}", use_container_width=True)

    if st.button("📝 Notiz zu diesem Dokument", key=f"docmgr_note_{d['doc_id']}",
                use_container_width=True):
        st.session_state["note_prefill"] = {
            "subject": d.get("subject"), "doc_id": d["doc_id"],
            "title": d["filename"],
        }
        st.switch_page("pages/12_🗒️_Notizen.py")
    st.markdown("##### Fach & RAG")
    _subj_opts = sorted({x.get("subject") for x in _ingest_ui._document_dicts() if x.get("subject")})
    if d.get("subject") and d["subject"] not in _subj_opts:
        _subj_opts.insert(0, d["subject"])
    _new_subj = st.selectbox("Fach", _subj_opts or [d.get("subject") or "–"],
                             index=max(0, (_subj_opts or [d.get("subject")]).index(d.get("subject"))
                                       if d.get("subject") in (_subj_opts or []) else 0),
                             key=f"docmgr_subj_{d['doc_id']}")
    if st.button("Fach speichern", key=f"docmgr_subj_save_{d['doc_id']}"):
        manifest.set_document_subject(d["doc_id"], _new_subj)
        st.success("Fach geändert.")
        st.rerun()
    _rag_on = st.toggle("Im RAG (Chat/Suche)", value=bool(d.get("use_rag", 1)),
                        key=f"docmgr_rag_{d['doc_id']}")
    if _rag_on != bool(d.get("use_rag", 1)):
        from ragapp.ingestion.pipeline import set_document_use_rag
        with st.spinner("RAG-Status wird geändert …"):
            set_document_use_rag(d["doc_id"], _rag_on)
        st.rerun()
    _tag_now = (d.get("tags") or "")
    _want_exam = st.checkbox(
        "Als Altklausur markieren",
        value="altklausur" in _tag_now.lower(),
        key=f"docmgr_examtag_{d['doc_id']}")
    _has_exam = "altklausur" in _tag_now.lower()
    if _want_exam and not _has_exam:
        manifest.set_document_tags(d["doc_id"], (_tag_now + ", altklausur").strip(", "))
        st.rerun()
    if (not _want_exam) and _has_exam:
        _cleaned = ", ".join(t.strip() for t in _tag_now.split(",")
                             if t.strip().lower() != "altklausur")
        manifest.set_document_tags(d["doc_id"], _cleaned)
        st.rerun()
    a1, a2, a3 = st.columns(3)
    if a1.button("📄 Zusammenfassung", key=f"docmgr_sum_{d['doc_id']}"):
        st.session_state["zus_prefill_subject"] = d.get("subject")
        st.switch_page("pages/7_📄_Zusammenfassung.py")
    if a2.button("🎴 Karten", key=f"docmgr_cards_{d['doc_id']}"):
        st.session_state["study_prefill"] = {"subject": d.get("subject"), "limit": 12}
        st.switch_page("pages/4_🎓_Lernen.py")
    if a3.button("🎧 Audio", key=f"docmgr_audio_{d['doc_id']}"):
        st.session_state["audio_prefill_subject"] = d.get("subject")
        st.switch_page("pages/15_🎧_Audio-Overview.py")

    st.divider()
    if st.button("🗑️ Löschen …", type="secondary",
                 key=f"docmgr_del_{d['doc_id']}", use_container_width=True):
        _queue_delete([d])


# --------------------------------------------------------------------------- #
# Ordner (= Fächer) + Upload, bevor die Bibliothek kommt – auch bei 0 Dokumenten
# --------------------------------------------------------------------------- #
_pending_del = st.session_state.get("docmgr_delete_docs")
if _pending_del:
    _confirm_delete_dialog(_pending_del)

_all_docs = [dict(d) for d in manifest.list_documents()]
_folder_names = sorted({d["subject"] for d in _all_docs if d.get("subject")}
                       | set(_ingest_ui.extra_folders()))
_folder = st.session_state.get("doc_folder")
if _folder and _folder not in _folder_names:
    _folder_names = [_folder] + _folder_names

with card("ordner"):
    st.subheader("📁 Fächer als Ordner")
    st.caption("Wähle einen Ordner – neue Uploads landen dort. Ein leerer Ordner "
               "bleibt nach dem Löschen aller Dateien ausgewählt.")
    _chip_labels = ["Alle"] + _folder_names
    _per = 6
    for _row_i in range(0, len(_chip_labels), _per):
        _row = _chip_labels[_row_i:_row_i + _per]
        _chip_cols = st.columns(len(_row))
        for _col, _name in zip(_chip_cols, _row):
            _here = (_name == "Alle" and not _folder) or (_name == _folder)
            if _col.button(
                f"{'📂' if _name == 'Alle' else '📁'} "
                f"{'Alle' if _name == 'Alle' else _fach(_name)}",
                type="primary" if _here else "secondary",
                key=f"doc_folder_chip_{_name}",
                use_container_width=True,
            ):
                st.session_state["doc_folder"] = None if _name == "Alle" else _name
                st.rerun()
    _nf1, _nf2 = st.columns([3, 1])
    _new_folder = _nf1.text_input("Neuer Ordner (Fachname)", key="doc_new_folder",
                                  placeholder="z. B. BWL oder Statistik")
    if _nf2.button("➕ Ordner", use_container_width=True, key="doc_new_folder_go",
                   disabled=not (_new_folder or "").strip()):
        _ingest_ui.remember_folder(_new_folder.strip())
        st.rerun()

_ingest_ui.render_upload(default_subject=st.session_state.get("doc_folder"))
_ingest_ui.render_ocr_warnings()
with st.expander("Weitere Importwege (Inbox, Quellordner)", expanded=False):
    _ingest_ui.render_inbox_scan()
    _ingest_ui.render_source_folder()

_docs = [dict(d) for d in manifest.list_documents()]
_folder = st.session_state.get("doc_folder")
if _folder:
    _docs = [d for d in _docs if d.get("subject") == _folder]
if not _docs:
    if _folder:
        st.info(f"Ordner **{_fach(_folder)}** ist leer. Lade oben Dateien hoch – "
                "sie werden diesem Fach zugeordnet.")
    else:
        st.info("Noch keine Dokumente. Lade oben welche hoch und wähle ein Fach.")
    st.stop()

# --------------------------------------------------------------------------- #
# Filter + Sortierung
# --------------------------------------------------------------------------- #
_subjects_present = sorted({d["subject"] for d in _docs if d["subject"]})
_tags_present = manifest.all_document_tags()

with card("filter"):
    f1, f2, f3, f4, f5 = st.columns([1, 1, 1, 1.2, 0.9])
    with f1:
        _subj_filter = st.multiselect("Fach", _subjects_present, format_func=_fach,
                                      placeholder="Alle")
    with f2:
        _tag_filter = st.multiselect(
            "Kategorie", _tags_present, placeholder="Alle") if _tags_present else []
    with f3:
        _rag_filter = st.selectbox("RAG-Status", ["Alle", "Nur im RAG", "Nur archiviert"])
    with f4:
        _search = st.text_input("Suche (Dateiname)", placeholder="z. B. Klausur_2023 …")
    with f5:
        _sort_choice = st.selectbox("Sortierung", ["Fach", "Name", "Zuletzt geändert"])


def _matches(d: dict) -> bool:
    if _subj_filter and d.get("subject") not in _subj_filter:
        return False
    if _tag_filter:
        _dtags = {t.strip() for t in (d.get("tags") or "").split(",") if t.strip()}
        if not _dtags & set(_tag_filter):
            return False
    if _rag_filter == "Nur im RAG" and not d.get("use_rag", 1):
        return False
    if _rag_filter == "Nur archiviert" and d.get("use_rag", 1):
        return False
    if _search and _search.lower() not in (d.get("filename") or "").lower():
        return False
    return True


_filtered = [d for d in _docs if _matches(d)]
if _sort_choice == "Name":
    _filtered.sort(key=lambda d: (d.get("filename") or "").lower())
elif _sort_choice == "Zuletzt geändert":
    _filtered.sort(key=lambda d: d.get("updated_at") or 0, reverse=True)
# "Fach" ist bereits die Reihenfolge aus manifest.list_documents() (Fach, Dateiname)

st.caption(f"{len(_filtered)} von {len(_docs)} Dokument(en)")

tab_kacheln, tab_liste = st.tabs(["🗃️ Kacheln", "📋 Liste & Kategorien"])

# --------------------------------------------------------------------------- #
# Kachel-Ansicht (mit Vorschau)
# --------------------------------------------------------------------------- #
with tab_kacheln:
    if not _filtered:
        st.info("Keine Dokumente für diese Filterung.")
    else:
        if "docmgr_page_size" not in st.session_state:
            st.session_state["docmgr_page_size"] = 24
        _shown = _filtered[: st.session_state["docmgr_page_size"]]
        _cols_per_row = 4
        for i in range(0, len(_shown), _cols_per_row):
            _row = _shown[i:i + _cols_per_row]
            _cols = st.columns(_cols_per_row)
            for _col, d in zip(_cols, _row):
                _ftype = (d.get("filetype") or "").lower()
                with _col, st.container(border=True):
                    _thumb = get_thumbnail(d)
                    if _thumb:
                        st.image(_thumb, use_container_width=True)
                    elif _ftype in _TEXT_PREVIEW_TYPES:
                        with st.container(height=120, border=False):
                            _preview = get_text_preview(d)
                            if _preview:
                                # Als Klartext, NICHT gerendertes Markdown: eine
                                # "#"-Überschrift am Dateianfang wuerde sonst als
                                # grosse fette Zeile dargestellt und die kleine
                                # Vorschau-Kachel sprengen (Zeilenumbruch mitten
                                # im Wort, siehe App-Rundgang-Review).
                                st.text(_preview)
                            else:
                                st.caption("(kein Text)")
                    else:
                        _icon = _ICONS.get(_ftype, "📄")
                        st.markdown(
                            f"<div style='text-align:center;font-size:48px;"
                            f"padding:16px 0;'>{_icon}</div>", unsafe_allow_html=True)
                    st.caption(f"**{d['filename']}**")
                    _badge = "🟢 im RAG" if d.get("use_rag", 1) else "⚪ archiviert"
                    st.caption(f"{_fach(d.get('subject'))} · {_ingest_ui.document_page_label(d)} · {_badge}")
                    if d.get("tags"):
                        st.caption(f"🏷️ {d['tags']}")
                    st.checkbox("Auswählen", key=f"docmgr_sel_{d['doc_id']}",
                               label_visibility="collapsed")
                    _b1, _b2 = _col.columns(2)
                    if _b1.button("👁️ Ansehen", key=f"docmgr_view_{d['doc_id']}",
                                 use_container_width=True):
                        _view_doc_dialog(d)
                    _fpath = PROJECT_ROOT / (d.get("source_path") or "")
                    _dl_prep_key = f"docmgr_dlprep_{d['doc_id']}"
                    if not _fpath.is_file():
                        _b2.button("⬇️", disabled=True, key=f"docmgr_dlx_{d['doc_id']}",
                                  use_container_width=True, help="Originaldatei fehlt")
                    elif st.session_state.get(_dl_prep_key):
                        # Erst JETZT werden die Datei-Bytes gelesen (gecacht) -
                        # nicht schon beim blossen Anzeigen der Kachel.
                        _b2.download_button(
                            "💾", data=_read_file_bytes(str(_fpath), d.get("updated_at") or 0),
                            file_name=d["filename"], key=f"docmgr_dl_{d['doc_id']}",
                            use_container_width=True, help="Jetzt herunterladen")
                    else:
                        if _b2.button("⬇️", key=f"docmgr_dlbtn_{d['doc_id']}",
                                     use_container_width=True, help="Herunterladen vorbereiten"):
                            st.session_state[_dl_prep_key] = True
                            st.rerun()
                    if st.button("🗑️ Löschen", key=f"docmgr_tile_del_{d['doc_id']}",
                                 use_container_width=True,
                                 help="Dokument, Index und/oder Karteikarten entfernen"):
                        _queue_delete([d])
        if len(_filtered) > len(_shown):
            if st.button(f"🔁 Weitere laden ({len(_filtered) - len(_shown)} übrig)"):
                st.session_state["docmgr_page_size"] += 24
                st.rerun()

        st.divider()
        _kachel_selected = [d for d in _filtered
                           if st.session_state.get(f"docmgr_sel_{d['doc_id']}", False)]
        _selection_bar(_kachel_selected, "docmgr_kacheln")

# --------------------------------------------------------------------------- #
# Listen-Ansicht: Kategorien in Serie bearbeiten + Sammel-Download
# --------------------------------------------------------------------------- #
with tab_liste:
    if not _filtered:
        st.info("Keine Dokumente für diese Filterung.")
    else:
        st.caption("Kategorien in Serie vergeben (kommagetrennt), markieren für "
                   "ZIP-Download oder Löschen. Fach und RAG änderst du im Dialog "
                   "**Ansehen**.")
        _list_orig = {d["doc_id"]: d for d in _filtered}
        _list_df = pd.DataFrame([{
            "✓": False, "Dateiname": d["filename"], "Fach": _fach(d.get("subject")),
            "Seiten": _ingest_ui.document_page_label(d),
            "Im RAG": "🟢" if d.get("use_rag", 1) else "⚪",
            "Kategorien": d.get("tags") or "", "_id": d["doc_id"],
        } for d in _filtered])
        _list_edited = st.data_editor(
            _list_df, hide_index=True, use_container_width=True, key="docmgr_list_editor",
            column_config={
                "✓": st.column_config.CheckboxColumn(width="small"),
                "Dateiname": st.column_config.TextColumn(disabled=True),
                "Fach": st.column_config.TextColumn(disabled=True),
                "Seiten": st.column_config.TextColumn(disabled=True, width="small"),
                "Im RAG": st.column_config.TextColumn(disabled=True, width="small"),
                "_id": None,
            },
        )

        if st.button("💾 Kategorien speichern", key="docmgr_list_save"):
            _n = 0
            for _, row in _list_edited.iterrows():
                o = _list_orig.get(row["_id"])
                if o is None:
                    continue
                if (row["Kategorien"] or "") != (o.get("tags") or ""):
                    manifest.set_document_tags(row["_id"], row["Kategorien"])
                    _n += 1
            st.success(f"{_n} Dokument(e) aktualisiert.")
            st.rerun()

        st.divider()
        _liste_selected = [_list_orig[row["_id"]] for _, row in _list_edited.iterrows()
                          if row["✓"] and row["_id"] in _list_orig]
        _selection_bar(_liste_selected, "docmgr_liste")

with st.expander("Nur Fragen löschen (Dokumente bleiben)", expanded=False):
    _ingest_ui.render_question_cleanup()
