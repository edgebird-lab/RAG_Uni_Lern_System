"""
RAG-Lernsystem: Seite „Dokumentenmanager" (Kacheln, Vorschau, Kategorien)
============================================================================
Paperless-ngx-artige Übersicht über ALLE registrierten Dokumente (auch die nur
archivierten, ohne RAG) - mit Vorschau-Kacheln, Ansehen, Download und frei
vergebenen Kategorien. Fach & RAG-Auswahl bleiben auf der Seite "Ingestion"
(dort mit dem Import verzahnt); hier geht es um Durchblättern/Wiederfinden.
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

st.caption("Alle Dokumente auf einen Blick – ansehen, herunterladen, Kategorien "
           "vergeben. Auch archivierte (nicht im RAG) Dokumente tauchen hier auf.")

with skeleton("Dokumentenmanager wird geladen ..."):
    import pandas as pd
    from ragapp import manifest
    from ragapp.config import SUBJECT_LABELS, PROJECT_ROOT
    from ragapp.ui import _docviewer
    from ragapp.ui._thumbnails import get_thumbnail, get_text_preview

_ICONS = {"pdf": "📕", "docx": "📄", "pptx": "📊", "md": "📝", "txt": "📄", "catalog": "🗒️"}
_TEXT_PREVIEW_TYPES = ("md", "txt")


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


def _selection_bar(selected: list[dict], key_prefix: str) -> None:
    """Zeigt - wenn welche ausgewählt sind - Anzahl + ZIP-Download-Button. Kacheln
    und Liste führen ihre Auswahl bewusst UNABHÄNGIG (eigene Widgets, eigene
    Zustände) - einfacher und ohne Session-State-Konflikte zwischen den beiden
    Tabs (ein data_editor darf den Wert eines anderswo instanziierten Checkbox-
    Widgets nicht überschreiben)."""
    if not selected:
        return
    c1, c2 = st.columns([3, 2])
    c1.info(f"🗂️ {len(selected)} Dokument(e) ausgewählt.")
    with c2:
        st.download_button(
            f"⬇️ Als ZIP herunterladen ({len(selected)})", data=_build_zip(selected),
            file_name="dokumente.zip", mime="application/zip",
            key=f"{key_prefix}_zip", use_container_width=True)


@st.dialog("📄 Dokument ansehen", width="large")
def _view_doc_dialog(d: dict) -> None:
    st.markdown(f"**{d['filename']}**  ·  Fach: {_fach(d['subject'])}"
               + ("  ·  ⚪ archiviert (nicht im RAG)" if not d.get("use_rag", 1) else ""))
    path = PROJECT_ROOT / (d.get("source_path") or "")
    if not path.is_file():
        st.warning("Originaldatei nicht gefunden.")
        return

    if (d.get("filetype") or "").lower() == "pdf":
        n_pages = _docviewer.pdf_page_count(path)
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
    _subj_opts = sorted({x.get("subject") for x in manifest.list_documents() if x.get("subject")})
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


_docs = [dict(d) for d in manifest.list_documents()]
if not _docs:
    st.info("Noch keine Dokumente indexiert. Gehe zu **📥 Import**, um welche hinzuzufügen.")
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
                    st.caption(f"{_fach(d.get('subject'))} · {_badge}")
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
        st.caption("Kategorien in Serie vergeben (kommagetrennt) und/oder mehrere "
                   "Dokumente für den ZIP-Download markieren. Fach und RAG-Auswahl "
                   "änderst du auf der Seite **📥 Import**.")
        _list_orig = {d["doc_id"]: d for d in _filtered}
        _list_df = pd.DataFrame([{
            "✓": False, "Dateiname": d["filename"], "Fach": _fach(d.get("subject")),
            "Im RAG": "🟢" if d.get("use_rag", 1) else "⚪",
            "Kategorien": d.get("tags") or "", "_id": d["doc_id"],
        } for d in _filtered])
        _list_edited = st.data_editor(
            _list_df, hide_index=True, use_container_width=True, key="docmgr_list_editor",
            column_config={
                "✓": st.column_config.CheckboxColumn(width="small"),
                "Dateiname": st.column_config.TextColumn(disabled=True),
                "Fach": st.column_config.TextColumn(disabled=True),
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
