"""
RAG-Lernsystem: Seite „Dokumente & Ingestion" (Streamlit)
==========================================================
Verwaltet die Wissensbasis: neue Dateien hochladen und indexieren, den
Quellordner importieren, Fragen anreichern und Dokumente löschen.
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

import pandas as pd
import streamlit as st

from ragapp.config import settings, INBOX_DIR, SOURCE_DIR, SUBJECT_LABELS
from ragapp import manifest
from ragapp.ingestion.pipeline import (
    ingest_file, ingest_directory, remove_document, remove_questions,
)
from ragapp.ingestion.enrich import enrich_questions

st.set_page_config(page_title="Dokumente & Ingestion", page_icon="📥", layout="wide")

from ragapp.ui._auth import require_pin
require_pin()

# --------------------------------------------------------------------------- #
# Styling ("schick"), identisch zur Startseite
# --------------------------------------------------------------------------- #
st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1100px;}
.stChatMessage {border-radius: 14px;}
.source-card {
    background: linear-gradient(135deg, #f6f8fc 0%, #eef2fb 100%);
    border: 1px solid #e2e8f4; border-radius: 12px; padding: 12px 16px;
    margin-bottom: 8px;
}
.source-title {font-weight: 600; color: #1f3a63;}
.source-meta {color: #5b6b85; font-size: 0.85rem;}
.badge {display:inline-block; padding: 2px 10px; border-radius: 999px;
    font-size: 0.78rem; font-weight: 600;}
.badge-answer {background:#e6f7ee; color:#137a4b;}
.badge-fallback {background:#fdf0e3; color:#a15a13;}
.small {color:#7a8aa0; font-size:0.8rem;}
h1 {font-weight: 750; letter-spacing:-0.5px;}
</style>
""", unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
# Sidebar (Kurzstatistik, wie auf der Startseite)
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown("### 🎓 Lern-Assistent")
    st.caption(f"Modell: `{settings.LLM_MODEL}` · Embedding: `{settings.EMBED_MODEL}`")
    _stats = manifest.stats()
    c1, c2 = st.columns(2)
    c1.metric("Dokumente", _stats["documents"])
    c2.metric("Chunks", _stats["chunks"])
    c1.metric("Fragen", _stats["questions"])
    c2.metric("Fächer", _stats["subjects"])

# --------------------------------------------------------------------------- #
# Kopf
# --------------------------------------------------------------------------- #
st.title("📥 Dokumente & Ingestion")
st.markdown(
    "<span class='small'>Hier verwaltest du die Wissensbasis: Dateien hochladen, "
    "den Quellordner importieren, Fragen anreichern und Dokumente löschen.</span>",
    unsafe_allow_html=True,
)

st.info(
    "🔎 **Automatische Deduplizierung:** Inhaltsgleiche Dateien (auch unter anderem "
    "Namen) werden erkannt und übersprungen. Ebenso werden identische Textstellen "
    "(z. B. wiederkehrende Kopfzeilen oder Formelsammlungen) nur **einmal** indexiert. "
    "Du kannst also bedenkenlos importieren."
)

# Klartext-Fach als Hilfe (Kürzel -> Klartext)
def _subject_label(code: str) -> str:
    return SUBJECT_LABELS.get(code, code)


# --------------------------------------------------------------------------- #
# 1) Datei-Upload
# --------------------------------------------------------------------------- #
st.subheader("Dateien hochladen & indexieren")
st.caption(
    "Unterstützt: PDF, Markdown, Text, Word (docx), PowerPoint (pptx). "
    "Hochgeladene Dateien werden im Ordner `data/inbox/` abgelegt und sofort indexiert."
)

uploads = st.file_uploader(
    "Dateien auswählen (Mehrfachauswahl möglich)",
    type=["pdf", "md", "txt", "docx", "pptx"],
    accept_multiple_files=True,
)

# Fach-Zuordnung für den Upload (sonst landet der Upload unter „inbox")
_known_subjects = sorted(
    set(SUBJECT_LABELS.keys())
    | {d["subject"] for d in manifest.list_documents() if d["subject"]}
)
_up_choice = st.selectbox(
    "Fach für die hochgeladenen Dateien",
    ["(neues Fach eingeben …)"] + _known_subjects,
    help="Ordnet den Upload einem Fach zu (für Filter & Übersicht).",
)
if _up_choice == "(neues Fach eingeben …)":
    upload_subject = st.text_input("Neues Fach", value="").strip() or None
else:
    upload_subject = _up_choice

if uploads and st.button("📥 Hochgeladene Dateien indexieren", type="primary"):
    ergebnisse: list[dict] = []
    with st.status("Verarbeite hochgeladene Dateien …", expanded=True) as status:
        for up in uploads:
            ziel = INBOX_DIR / up.name
            try:
                ziel.write_bytes(up.getbuffer())
            except Exception as exc:
                status.write(f"⚠️ {up.name}: konnte nicht gespeichert werden ({exc})")
                ergebnisse.append({"Datei": up.name, "Status": "error", "Info": str(exc)})
                continue

            status.update(label=f"Indexiere {up.name} …")

            def _fortschritt(msg: str, _name: str = up.name) -> None:
                status.write(f"· {_name}: {msg}")

            try:
                r = ingest_file(ziel, subject=upload_subject, progress=_fortschritt)
            except Exception as exc:
                r = {"status": "error", "file": up.name, "error": str(exc)}

            info = ""
            if r["status"] == "duplicate":
                info = f"Duplikat von {r.get('duplicate_of', '?')}"
            elif r["status"] == "unchanged":
                info = "unverändert, bereits im Index"
            elif r["status"] == "ok":
                info = f"{r.get('chunks', 0)} Chunks, {r.get('questions', 0)} Fragen"
            elif r["status"] in ("skipped", "duplicate_chunks"):
                info = r.get("reason", "übersprungen")
            elif r["status"] == "error":
                info = r.get("error", "Fehler")
            ergebnisse.append({"Datei": r.get("file", up.name),
                               "Status": r["status"], "Info": info})
            status.write(f"✔️ {r.get('file', up.name)} → **{r['status']}** {info}")

        status.update(label="Fertig", state="complete")

    st.dataframe(pd.DataFrame(ergebnisse), use_container_width=True, hide_index=True)
    ok = sum(1 for e in ergebnisse if e["Status"] == "ok")
    st.success(f"{ok} von {len(ergebnisse)} Datei(en) neu indexiert.")

st.divider()

# --------------------------------------------------------------------------- #
# 2) Kompletten Quellordner importieren
# --------------------------------------------------------------------------- #
st.subheader("Kompletten Quellordner importieren")
st.caption(f"Quellordner: `{SOURCE_DIR}`")
st.warning(
    "⏳ **Achtung, sehr lange Laufzeit.** Der Erstimport eines großen Korpus läuft "
    "auf CPU in der Größenordnung von **1 bis 2 Stunden** (Embeddings pro Chunk). Der "
    "Streamlit-Prozess ist währenddessen blockiert. Für den **Erstimport** ist der "
    "Ordnerwächter bzw. das CLI (`python -m ragapp.scripts.cli ingest`) empfehlenswert, "
    "es läuft im Hintergrund und ist unterbrechbar/fortsetzbar."
)

if st.button("📚 Kompletten Quellordner importieren"):
    with st.status("Importiere Quellordner … (das kann sehr lange dauern)",
                   expanded=True) as status:
        def _fortschritt_dir(msg: str) -> None:
            status.update(label=msg)

        try:
            summary = ingest_directory(progress=_fortschritt_dir)
            status.update(label="Import abgeschlossen", state="complete")
        except Exception as exc:
            status.update(label=f"Fehler: {exc}", state="error")
            summary = None

    if summary is not None:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Neu", summary.get("ok", 0))
        m2.metric("Duplikate", summary.get("duplicate", 0))
        m3.metric("Unverändert", summary.get("unchanged", 0))
        m4.metric("Fehler", summary.get("error", 0))
        st.success(
            f"Fertig: {summary.get('chunks', 0)} Chunks und "
            f"{summary.get('questions', 0)} Fragen indexiert."
        )

st.divider()

# --------------------------------------------------------------------------- #
# 3) Fragen-Anreicherung
# --------------------------------------------------------------------------- #
st.subheader("🧠 Fragen-Anreicherung")
st.caption(
    "Erzeugt hypothetische Fragen zu vorhandenen Chunks und indexiert sie. Das "
    "**erhöht die Trefferquote** und liefert **Karteikarten** für die 🎓 Lernen-Seite. "
    "Kostet auf CPU **~20 s pro Chunk** – deshalb gedeckelt (Limit) und resumierbar "
    "(bereits angereicherte Chunks werden übersprungen)."
)

_docs_all = manifest.list_documents()
_subjects = sorted({d["subject"] for d in _docs_all if d["subject"]})
_doc_label = {
    f"{d['filename']}  ·  {d['subject'] or '—'}  ({d['num_chunks']} Chunks · "
    f"{d['num_questions']} Fragen)": d["doc_id"]
    for d in _docs_all
}
_sel_docs = st.multiselect(
    "Dateien auswählen (leer = alle passenden)", list(_doc_label.keys()),
    help="Gezielt nur diese Dateien anreichern. Leer lassen = alle (nach Priorität).")
_doc_ids = [_doc_label[k] for k in _sel_docs] or None

col_a, col_b, col_c = st.columns(3)
with col_a:
    enrich_limit = st.number_input(
        "Maximale Anzahl Chunks (Limit)", min_value=1, max_value=100000,
        value=100, step=10, help="Deckelt die Menge; wichtige/kompakte Dokumente zuerst.")
with col_b:
    enrich_choice = st.selectbox(
        "Fach-Filter (optional)", ["Alle Fächer"] + _subjects,
        help="Nur Chunks dieses Fachs (wirkt zusätzlich zur Datei-Auswahl).")
with col_c:
    enrich_n = st.number_input(
        "Fragen pro Chunk", min_value=1, max_value=10,
        value=int(getattr(settings, "NUM_INDEX_QUESTIONS", 3)), step=1,
        help="Wie viele verschiedene Fragen je Textabschnitt erzeugt werden.")
enrich_subject = None if enrich_choice == "Alle Fächer" else enrich_choice
enrich_answers = st.checkbox(
    "Musterlösungen gleich mitgenerieren (KI-Antwort statt Chunk)", value=True,
    help="Erzeugt zu jeder Frage direkt eine echte Antwort. Braucht mehr Zeit "
         "(~20 s pro Frage zusätzlich), spart aber das spätere Nachziehen auf der Lernen-Seite.")

_mt1, _mt2 = st.columns([1, 2])
with _mt1:
    if st.button("🩺 Modell testen"):
        from ragapp.hardware import probe_model
        with st.spinner(f"Teste `{settings.LLM_MODEL_FAST}` …"):
            _ok, _msg = probe_model(settings.LLM_MODEL_FAST)
        if _ok:
            st.success(f"✅ `{settings.LLM_MODEL_FAST}` antwortet – die Anreicherung kann starten.")
        else:
            st.error(f"❌ `{settings.LLM_MODEL_FAST}` läuft nicht: {_msg}  Wähle unter "
                     "**⚙️ Einstellungen → Hardware & Modell-Auswahl** ein laufendes "
                     "Modell (z. B. `gemma3:4b`).")

if st.button("🧠 Fragen-Anreicherung starten", type="primary"):
    with st.status("Reichere Fragen an … (~20 s pro Chunk)", expanded=True) as status:
        def _fortschritt_enrich(msg: str) -> None:
            status.update(label=msg)

        try:
            r = enrich_questions(limit=int(enrich_limit), subject=enrich_subject,
                                 doc_ids=_doc_ids, n_per_chunk=int(enrich_n),
                                 with_answers=bool(enrich_answers),
                                 progress=_fortschritt_enrich)
            status.update(label="Anreicherung abgeschlossen", state="complete")
        except Exception as exc:  # noqa: BLE001
            status.update(label=f"Fehler: {exc}", state="error")
            r = None

    if r is not None:
        _st = r.get("status")
        if _st == "nothing_to_do":
            st.info("Nichts zu tun – die gewählten Chunks sind bereits angereichert.")
        elif _st == "llm_error":
            st.error(
                f"❌ Es wurden **0 Fragen** erzeugt. {r.get('error_msg', '')}  Meist lädt "
                "das schnelle Modell nicht: prüfe es oben mit **Modell testen** und wähle "
                "unter **⚙️ Einstellungen** ein laufendes Modell (z. B. `gemma3:4b`).")
        elif r.get("questions", 0) == 0:
            st.warning("Es wurden **0 Fragen** erzeugt – die Chunks ergaben keine (kein "
                       "Modellfehler). Wähle ggf. andere/längere Dokumente.")
        else:
            st.success(
                f"✅ **{r['questions']} Fragen** für {r['processed']} Chunk(s) erzeugt und "
                "indexiert. Tipp: auf **🎓 Lernen** die Karten aktualisieren, dann üben.")
            _rows = [{"Datei": v["filename"], "Fragen erzeugt": v["questions"]}
                     for v in r.get("per_doc", {}).values() if v["questions"]]
            if _rows:
                st.dataframe(pd.DataFrame(_rows), hide_index=True, use_container_width=True)

st.divider()

# --------------------------------------------------------------------------- #
# 4) Dokumentübersicht
# --------------------------------------------------------------------------- #
st.subheader("Indexierte Dokumente")

_docs = manifest.list_documents()
if not _docs:
    st.info("Noch keine Dokumente indexiert.")
else:
    df = pd.DataFrame([{
        "Fach": d["subject"],
        "Dateiname": d["filename"],
        "Chunks": d["num_chunks"],
        "Fragen": d["num_questions"],
        "Status": d["status"],
    } for d in _docs])
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(f"{len(_docs)} Dokument(e) insgesamt.")

    # ----------------------------------------------------------------- #
    # Dokumente löschen (Mehrfachauswahl)
    # ----------------------------------------------------------------- #
    st.markdown("##### 🗑️ Dokumente löschen")
    st.caption("Entfernt die gewählten Dokumente **samt Chunks und Fragen** aus "
               "Vektordatenbank, Manifest und Suchindex (BM25).")
    _doc_label = {
        f"[{d['subject']}] {d['filename']}  ·  {d['num_chunks']} Chunks, {d['num_questions']} Fragen": d["doc_id"]
        for d in _docs
    }
    _del_sel = st.multiselect("Dokument(e) auswählen", list(_doc_label.keys()))
    if st.button("🗑️ Ausgewählte Dokumente löschen", type="secondary",
                 disabled=not _del_sel):
        fehler = 0
        with st.status(f"Lösche {len(_del_sel)} Dokument(e) …", expanded=False) as status:
            for lbl in _del_sel:
                try:
                    remove_document(_doc_label[lbl])
                except Exception as exc:  # noqa: BLE001
                    fehler += 1
                    status.write(f"⚠️ {lbl}: {exc}")
            status.update(label="Fertig", state="error" if fehler else "complete")
        st.success(f"{len(_del_sel) - fehler} Dokument(e) entfernt.")
        st.rerun()

    # ----------------------------------------------------------------- #
    # Nur Fragen löschen (Dokumente/Chunks bleiben)
    # ----------------------------------------------------------------- #
    st.markdown("##### 🧠 Nur Fragen löschen (Dokumente & Chunks bleiben)")
    st.caption("Generierte Fragen erhöhen die Trefferquote, aber sehr viele können "
               "die Suche verlangsamen. Hier gezielt welche entfernen, ohne die "
               "Dokumente selbst anzutasten.")
    _q_total = sum(d["num_questions"] for d in _docs)
    st.write(f"Aktuell **{_q_total}** Fragen im Index.")
    _q_scope = st.radio("Umfang", ["Alle Fragen", "Nur ein Fach", "Nur bestimmte Dokumente"],
                        horizontal=True)

    if _q_scope == "Alle Fragen":
        if st.button(f"🧹 Alle {_q_total} Fragen löschen", disabled=_q_total == 0):
            remove_questions()
            st.success("Alle Fragen wurden gelöscht (Chunks bleiben erhalten).")
            st.rerun()
    elif _q_scope == "Nur ein Fach":
        _subj_q: dict = {}
        for d in _docs:
            _subj_q[d["subject"]] = _subj_q.get(d["subject"], 0) + d["num_questions"]
        _subj_map = {f"{s}  ·  {n} Fragen": s for s, n in sorted(_subj_q.items())}
        _sel_subj = st.selectbox("Fach", list(_subj_map.keys()))
        if st.button("🧹 Fragen dieses Fachs löschen"):
            remove_questions(subject=_subj_map[_sel_subj])
            st.success(f"Fragen im Fach „{_subj_map[_sel_subj]}“ gelöscht.")
            st.rerun()
    else:  # Nur bestimmte Dokumente
        _q_docs = {
            f"[{d['subject']}] {d['filename']}  ·  {d['num_questions']} Fragen": d["doc_id"]
            for d in _docs if d["num_questions"] > 0
        }
        if not _q_docs:
            st.info("Kein Dokument hat aktuell Fragen.")
        else:
            _sel_qdocs = st.multiselect("Dokument(e)", list(_q_docs.keys()))
            if st.button("🧹 Fragen der gewählten Dokumente löschen",
                         disabled=not _sel_qdocs):
                for lbl in _sel_qdocs:
                    remove_questions(doc_id=_q_docs[lbl])
                st.success(f"Fragen aus {len(_sel_qdocs)} Dokument(en) gelöscht.")
                st.rerun()
