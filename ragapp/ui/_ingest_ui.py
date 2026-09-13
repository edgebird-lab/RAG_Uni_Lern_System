"""
Gemeinsame Import-Bausteine (Upload, OCR, Inbox, Anreicherung, Katalog)
=======================================================================
Früher lag alles auf dem Import-Reiter. Upload/Index/OCR/Inbox gehören zum
Dokumentenmanager, Fragen-Anreicherung und Klausur-Katalog zu den Karteikarten.
"""
from __future__ import annotations

import time
from typing import Optional

import streamlit as st

from ragapp import manifest
from ragapp.config import INBOX_DIR, SOURCE_DIR, SUBJECT_LABELS, PROJECT_ROOT, settings
from ragapp.ui._style import card


def subject_label(code: Optional[str]) -> str:
    if not code:
        return "–"
    return SUBJECT_LABELS.get(code, code)


def extra_folders() -> list[str]:
    raw = st.session_state.get("doc_extra_folders") or []
    return [s for s in raw if s]


def _as_dict(row) -> dict:
    if isinstance(row, dict):
        return row
    keys = row.keys() if hasattr(row, "keys") else []
    return {k: row[k] for k in keys}


def _document_dicts() -> list[dict]:
    return [_as_dict(d) for d in manifest.list_documents()]


def known_subjects() -> list[str]:
    found = {d["subject"] for d in _document_dicts() if d.get("subject")}
    return sorted(set(SUBJECT_LABELS.keys()) | found | set(extra_folders()))


def remember_folder(name: str) -> None:
    name = (name or "").strip()
    if not name:
        return
    folders = extra_folders()
    if name not in folders:
        st.session_state["doc_extra_folders"] = folders + [name]
    st.session_state["doc_folder"] = name


@st.cache_data(show_spinner=False)
def cached_page_count(path_str: str, updated_at: float) -> int:
    from ragapp.ui._docviewer import pdf_page_count
    return pdf_page_count(path_str)


def document_page_count(d: dict) -> int:
    if (d.get("filetype") or "").lower() != "pdf":
        return 0
    path = PROJECT_ROOT / (d.get("source_path") or "")
    if not path.is_file():
        return 0
    return cached_page_count(str(path), float(d.get("updated_at") or 0))


def document_page_label(d: dict) -> str:
    n = document_page_count(d)
    if n > 0:
        return f"{n} Seite" if n == 1 else f"{n} Seiten"
    if (d.get("filetype") or "").lower() == "pdf":
        return "Seiten unbekannt"
    return "–"


def delete_documents(doc_ids: list[str]) -> tuple[int, list[str]]:
    from ragapp.ingestion.pipeline import remove_document
    ok = 0
    errors: list[str] = []
    for did in doc_ids:
        try:
            remove_document(did)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
    return ok, errors


def render_ocr_warnings() -> None:
    ocr = manifest.documents_needing_ocr()
    if not ocr:
        return
    n_partial = sum(1 for d in ocr if d.get("reason") == "partial")
    with st.expander(f"⚠️ {len(ocr)} Dokument(e) evtl. unvollständig eingelesen "
                     "(Scan/Bild – OCR empfohlen)", expanded=True):
        st.caption("Bei diesen Dateien wurde wenig oder unlesbarer Text extrahiert – "
                   "ihr Inhalt ist vermutlich **nicht vollständig** in der Wissensbasis. "
                   "Ersetze sie durch eine echte Textversion (oder OCR) und lies sie neu ein.")
        if n_partial:
            st.caption(f"🧩 Davon **{n_partial}** mit einzelnen unvollständig gelesenen "
                       "Scan-Seiten (Rest ist brauchbar) – bitte diese Seiten prüfen/ersetzen.")
        st.caption("🛡️ **VRAM-sicher:** Beim Neu-Einlesen wird für die OCR kurz das "
                   "Chat-Modell entladen, damit **nur das OCR-Modell** den Grafikspeicher "
                   "nutzt.")
        for d in ocr:
            oc1, oc2 = st.columns([4, 1])
            if d.get("reason") == "partial":
                pp = int(d.get("ocr_partial_pages", 0) or 0)
                hinweis = f"🧩 {pp} Seite(n) unvollständig gelesen – bitte prüfen/ersetzen"
            else:
                hinweis = "📄 kein Text extrahierbar (Scan/Bild – OCR nötig)"
            oc1.markdown(f"📄 **{d['filename']}** · _{subject_label(d.get('subject') or '—')}_ "
                         f"· {d.get('char_count', 0)} Zeichen · {hinweis}")
            if oc2.button("Neu einlesen", key=f"reocr_{d['doc_id']}", use_container_width=True):
                pth = PROJECT_ROOT / (d.get("source_path") or "")
                if pth.is_file():
                    from ragapp.ingestion.pipeline import ingest_file
                    with st.spinner(f"Lese {d['filename']} neu ein …"):
                        r = ingest_file(pth, force=True)
                    st.success(f"Neu eingelesen – Status: {r.get('status')}.")
                    st.rerun()
                else:
                    st.error("Originaldatei nicht gefunden.")


def render_upload(*, default_subject: Optional[str] = None,
                  key_prefix: str = "up") -> None:
    with card("upload"):
        st.subheader("Dateien hochladen & indexieren")
        st.caption(
            "Unterstützt: PDF, Markdown, Text, Word (docx), PowerPoint (pptx). "
            "Hochgeladene Dateien werden im Ordner `data/inbox/` abgelegt und sofort indexiert."
        )
        if default_subject:
            st.caption(f"Aktueller Ordner: **{subject_label(default_subject)}** "
                       "– neue Dateien landen dort, sofern du kein anderes Fach wählst.")

        uploads = st.file_uploader(
            "Dateien auswählen (Mehrfachauswahl möglich)",
            type=["pdf", "md", "txt", "docx", "pptx"],
            accept_multiple_files=True,
            key=f"{key_prefix}_files",
        )

        subjects = known_subjects()
        opts = ["(neues Fach eingeben …)"] + subjects
        index = 0
        if default_subject and default_subject in subjects:
            index = opts.index(default_subject)
        choice = st.selectbox(
            "Fach / Ordner für die hochgeladenen Dateien",
            opts, index=index,
            help="Ordnet den Upload einem Fach zu (wie ein Ordner in der Bibliothek).",
            key=f"{key_prefix}_subj",
        )
        if choice == "(neues Fach eingeben …)":
            upload_subject = st.text_input(
                "Neues Fach", value=default_subject or "",
                key=f"{key_prefix}_subj_new").strip() or None
        else:
            upload_subject = choice

        upload_use_rag = st.checkbox(
            "Ins RAG aufnehmen (durchsuchbar & im Chat zitierbar)", value=True,
            key=f"{key_prefix}_rag",
            help="AUS: die Datei wird geladen und in der Bibliothek registriert, aber "
                 "NICHT gechunkt/eingebettet – z. B. für Prüfungsordnungen. Später "
                 "jederzeit nachträglich ein- oder ausschaltbar.")

        if uploads and st.button("📥 Hochgeladene Dateien indexieren", type="primary",
                                 key=f"{key_prefix}_go"):
            _run_upload(uploads, upload_subject, upload_use_rag)
            if upload_subject:
                remember_folder(upload_subject)


def _run_upload(uploads, upload_subject: Optional[str], upload_use_rag: bool) -> None:
    import pandas as pd
    from ragapp.ingestion.pipeline import ingest_file
    from ragapp.ui._progress import ProgressReporter, fmt_dauer

    ergebnisse: list[dict] = []
    n_up = len(uploads)
    outer = st.progress(0.0, text=f"0/{n_up} Dateien")
    inner = ProgressReporter()
    t0 = time.time()
    bytes_total = sum(int(getattr(u, "size", 0) or 0) for u in uploads)
    bytes_done = 0

    with st.status("Verarbeite hochgeladene Dateien …", expanded=True) as status:
        for k, up in enumerate(uploads, 1):
            ziel = INBOX_DIR / up.name
            try:
                ziel.write_bytes(up.getbuffer())
            except Exception as exc:  # noqa: BLE001
                status.write(f"⚠️ {up.name}: konnte nicht gespeichert werden ({exc})")
                ergebnisse.append({"Datei": up.name, "Status": "error", "Info": str(exc)})
                continue

            status.update(label=f"[{k}/{n_up}] Indexiere {up.name} …")

            def _fortschritt(msg: str, done=None, total=None, _name=up.name) -> None:
                if total:
                    inner(f"{_name}: {msg}", done, total)
                else:
                    status.write(f"· {_name}: {msg}")
                    inner(f"{_name}: {msg}")

            try:
                r = ingest_file(ziel, subject=upload_subject, progress=_fortschritt,
                                use_rag=upload_use_rag)
            except Exception as exc:  # noqa: BLE001
                r = {"status": "error", "file": up.name, "error": str(exc)}

            info = ""
            if r["status"] == "duplicate":
                info = f"Duplikat von {r.get('duplicate_of', '?')}"
            elif r["status"] == "unchanged":
                info = "unverändert, bereits im Index"
            elif r["status"] == "ok":
                info = f"{r.get('chunks', 0)} Chunks, {r.get('questions', 0)} Fragen"
            elif r["status"] == "archived":
                info = "nur archiviert (nicht im RAG)"
            elif r["status"] in ("skipped", "duplicate_chunks"):
                info = r.get("reason", "übersprungen")
            elif r["status"] == "error":
                info = r.get("error", "Fehler")
            ergebnisse.append({"Datei": r.get("file", up.name),
                               "Status": r["status"], "Info": info})
            status.write(f"✔️ {r.get('file', up.name)} → **{r['status']}** {info}")

            bytes_done += int(getattr(up, "size", 0) or 0)
            elapsed = time.time() - t0
            if bytes_total > 0 and bytes_done > 0:
                eta = elapsed * (bytes_total - bytes_done) / bytes_done
            else:
                eta = (elapsed / k) * (n_up - k)
            outer.progress(k / n_up,
                           text=f"{k}/{n_up} Dateien · noch ca. {fmt_dauer(eta)}")

        status.update(label="Fertig", state="complete")

    inner.clear()
    outer.progress(1.0, text=f"{n_up}/{n_up} Dateien · fertig")
    st.dataframe(pd.DataFrame(ergebnisse), use_container_width=True, hide_index=True)
    ok = sum(1 for e in ergebnisse if e["Status"] == "ok")
    st.success(f"{ok} von {len(ergebnisse)} Datei(en) neu indexiert.")


def render_source_folder(*, key_prefix: str = "src") -> None:
    with card("quellordner"):
        st.subheader("Kompletten Quellordner importieren")
        st.caption(f"Quellordner: `{SOURCE_DIR}`")
        st.warning(
            "⏳ **Achtung, langer Erstimport.** Ein **großer** Korpus dauert beim "
            "ersten Import eine Weile. **Ohne GPU** grob **1–2 Stunden**; **mit GPU "
            "meist nur Minuten**. Für den Erstimport lieber CLI/Ordnerwächter "
            "(`python -m ragapp.scripts.cli ingest`).")
        if st.button("📚 Kompletten Quellordner importieren", key=f"{key_prefix}_go"):
            _run_source_folder()


def _run_source_folder() -> None:
    import re as re_dir
    from ragapp.ingestion.pipeline import ingest_directory
    from ragapp.ui._progress import ProgressReporter

    file_tick = re_dir.compile(r"^\[(\d+)\s*/\s*(\d+)\]")
    outer = ProgressReporter()
    inner_slot = st.empty()
    inner = ProgressReporter(inner_slot)

    with st.status("Importiere Quellordner … (das kann sehr lange dauern)",
                   expanded=True) as status:
        def _fortschritt_dir(msg: str, done=None, total=None) -> None:
            m = file_tick.match(msg)
            if m:
                i, n = int(m.group(1)), int(m.group(2))
                outer(msg, done if done is not None else i,
                      total if total is not None else n)
                inner_slot.empty()
                status.update(label=msg)
            elif total:
                inner(msg, done, total)
            else:
                status.write(msg)

        try:
            summary = ingest_directory(progress=_fortschritt_dir)
            status.update(label="Import abgeschlossen", state="complete")
        except Exception as exc:  # noqa: BLE001
            status.update(label=f"Fehler: {exc}", state="error")
            summary = None

    inner_slot.empty()
    if summary is not None:
        outer.finish("Import abgeschlossen")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Neu", summary.get("ok", 0))
        m2.metric("Duplikate", summary.get("duplicate", 0))
        m3.metric("Unverändert", summary.get("unchanged", 0))
        m4.metric("Fehler", summary.get("error", 0))
        st.success(
            f"Fertig: {summary.get('chunks', 0)} Chunks und "
            f"{summary.get('questions', 0)} Fragen indexiert.")


def render_inbox_scan(*, key_prefix: str = "inbox") -> None:
    with card("inbox_scan"):
        st.subheader("📥 Inbox jetzt einlesen")
        st.caption("Liest neue Dateien aus data/inbox einmalig ein.")
        if st.button("Inbox scannen", key=f"{key_prefix}_scan"):
            from ragapp.student_flow import scan_inbox_once
            with st.status("Scanne Inbox …") as status:
                res = scan_inbox_once(progress=lambda m: status.update(label=m))
                status.update(state="complete")
            st.success(f"{res['ok']}/{res['scanned']} Datei(en).")
            if res["errors"]:
                st.warning(" · ".join(res["errors"][:4]))


def render_enrich(*, key_prefix: str = "en") -> None:
    with card("anreicherung"):
        st.subheader("🧠 Fragen-Anreicherung")
        st.caption(
            "Erzeugt mit dem LLM hypothetische Fragen je Chunk und indexiert sie. "
            "Das **erhöht die Trefferquote** und liefert Rohmaterial für Karteikarten. "
            "Ohne GPU ~20 s pro Chunk – deshalb gedeckelt und resumierbar.")

        docs_all = _document_dicts()
        subjects = sorted({d["subject"] for d in docs_all if d["subject"]})
        doc_label = {
            f"{d['filename']}  ·  {d['subject'] or '—'}  ({d['num_chunks']} Chunks · "
            f"{d['num_questions']} Fragen)": d["doc_id"]
            for d in docs_all
        }
        sel_docs = st.multiselect(
            "Dateien auswählen (leer = alle passenden)", list(doc_label.keys()),
            help="Gezielt nur diese Dateien anreichern. Leer lassen = alle (nach Priorität).",
            placeholder="Alle", key=f"{key_prefix}_docs")
        doc_ids = [doc_label[k] for k in sel_docs] or None

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            enrich_limit = st.number_input(
                "Maximale Anzahl Chunks (Limit)", min_value=1, max_value=100000,
                value=100, step=10, key=f"{key_prefix}_limit",
                help="Deckelt die Menge; wichtige/kompakte Dokumente zuerst.")
        with col_b:
            enrich_choice = st.selectbox(
                "Fach-Filter (optional)", ["Alle Fächer"] + subjects,
                key=f"{key_prefix}_subj",
                help="Nur Chunks dieses Fachs (wirkt zusätzlich zur Datei-Auswahl).")
        with col_c:
            enrich_n = st.number_input(
                "Fragen pro Chunk", min_value=1, max_value=10,
                value=int(getattr(settings, "NUM_INDEX_QUESTIONS", 3)), step=1,
                key=f"{key_prefix}_n",
                help="Wie viele verschiedene Fragen je Textabschnitt erzeugt werden.")
        enrich_subject = None if enrich_choice == "Alle Fächer" else enrich_choice
        enrich_answers = st.checkbox(
            "Musterlösungen gleich mitgenerieren (KI-Antwort statt Chunk)", value=True,
            key=f"{key_prefix}_answers",
            help="Erzeugt zu jeder Frage direkt eine echte Antwort. Braucht mehr Zeit "
                 "(~20 s pro Frage zusätzlich), insofern späteres Nachziehen entfällt.")

        mt1, _mt2 = st.columns([1, 2])
        with mt1:
            if st.button("🩺 Modell testen", key=f"{key_prefix}_probe"):
                from ragapp.hardware import probe_model
                with st.spinner(f"Teste `{settings.LLM_MODEL_FAST}` …"):
                    ok, msg = probe_model(settings.LLM_MODEL_FAST)
                if ok:
                    st.success(f"✅ `{settings.LLM_MODEL_FAST}` antwortet – die "
                               "Anreicherung kann starten.")
                else:
                    st.error(f"❌ `{settings.LLM_MODEL_FAST}` läuft nicht: {msg}  "
                             "Wähle unter **⚙️ Einstellungen** ein laufendes Modell.")

        if st.button("🧠 Fragen-Anreicherung starten", type="primary",
                     key=f"{key_prefix}_go"):
            _run_enrich(int(enrich_limit), enrich_subject, doc_ids,
                        int(enrich_n), bool(enrich_answers))


def _run_enrich(limit: int, subject: Optional[str], doc_ids, n_per_chunk: int,
                with_answers: bool) -> None:
    import re as re_en
    import pandas as pd
    from ragapp.ingestion.enrich import enrich_questions
    from ragapp.ui._progress import ProgressReporter

    tick = re_en.compile(r"(\d+)\s*/\s*(\d+)")
    bar = ProgressReporter()
    with st.status("Reichere Fragen an … (~20 s pro Chunk)", expanded=True) as status:
        def _fortschritt(msg: str, done=None, total=None) -> None:
            if total:
                bar(msg, done, total)
            else:
                mm = tick.search(msg)
                if mm:
                    bar(msg, int(mm.group(1)), int(mm.group(2)))
                else:
                    status.update(label=msg)

        try:
            r = enrich_questions(limit=limit, subject=subject, doc_ids=doc_ids,
                                 n_per_chunk=n_per_chunk, with_answers=with_answers,
                                 progress=_fortschritt)
            status.update(label="Anreicherung abgeschlossen", state="complete")
        except Exception as exc:  # noqa: BLE001
            status.update(label=f"Fehler: {exc}", state="error")
            r = None

    if r is None:
        return
    st_status = r.get("status")
    if st_status == "nothing_to_do":
        st.info("Nichts zu tun – die gewählten Chunks sind bereits angereichert.")
        return
    if st_status == "llm_error":
        st.error(
            f"❌ Es wurden **0 Fragen** erzeugt. {r.get('error_msg', '')}  "
            "Meist lädt das schnelle Modell nicht: prüfe es oben mit **Modell testen**.")
        return
    if r.get("questions", 0) == 0:
        st.warning("Es wurden **0 Fragen** erzeugt – die Chunks ergaben keine "
                   "(kein Modellfehler). Wähle ggf. andere/längere Dokumente.")
        return

    st.success(f"✅ **{r['questions']} Fragen** für {r['processed']} Chunk(s) erzeugt "
               "und indexiert.")
    from ragapp import study as study_h
    study_h.mark_needs_card_harvest()
    st.session_state["_needs_card_harvest"] = True
    with st.status("Übernehme Fragen als Karten …") as hs:
        hres = study_h.harvest_cards(progress=lambda m: hs.update(label=m))
        hs.update(state="complete", label=f"{hres.get('neu', 0)} neue Karte(n)")
    st.success(f"Karten aktualisiert: +{hres.get('neu', 0)}")
    rows = [{"Datei": v["filename"], "Fragen erzeugt": v["questions"]}
            for v in r.get("per_doc", {}).values() if v["questions"]]
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def render_exam_catalog(*, key_prefix: str = "catalog") -> None:
    docs_all = _document_dicts()
    subjects = sorted({d["subject"] for d in docs_all if d["subject"]})
    with card("lernkatalog"):
        st.subheader("📚 Klausur-Lernkatalog")
        st.caption("Prüfungstypische Fragen aus Zusammenfassung + optionaler Altklausur – "
                   "landet als Karten nach der Ernte.")
        cat_subj = st.selectbox("Fach für den Katalog", ["–"] + subjects,
                                key=f"{key_prefix}_subj")
        cat_n = st.number_input("Fragen je Abschnitt", min_value=1, max_value=8, value=3,
                                key=f"{key_prefix}_n")
        cat_exams = st.file_uploader("Altklausur (optional, PDF)", type=["pdf"],
                                     accept_multiple_files=True,
                                     key=f"{key_prefix}_exams")
        if st.button("📚 Lernkatalog erzeugen", type="primary",
                     disabled=cat_subj == "–", key=f"{key_prefix}_go"):
            from ragapp.ingestion.exam_catalog import build_exam_catalog
            from ragapp.config import DATA_DIR
            exam_paths = []
            if cat_exams:
                tmp = DATA_DIR / "inbox"
                tmp.mkdir(parents=True, exist_ok=True)
                for f in cat_exams:
                    p = tmp / f.name
                    p.write_bytes(f.getvalue())
                    exam_paths.append(p)
            with st.status("Erzeuge Katalog …", expanded=True) as cs:
                try:
                    cres = build_exam_catalog(
                        cat_subj, exam_files=exam_paths or None,
                        n_per_section=int(cat_n),
                        progress=lambda m: cs.update(label=str(m)))
                    if cres.get("status") == "no_summary":
                        st.warning("Keine Zusammenfassung.md für dieses Fach. "
                                   "Erst auf **Zusammenfassung** erzeugen, dann Katalog.")
                    else:
                        cs.update(state="complete", label="Katalog fertig")
                        st.success(f"{len(cres.get('pairs') or [])} Fragenpaare.")
                        from ragapp import study as stc
                        stc.harvest_cards()
                        st.info("Karten wurden übernommen.")
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))


def render_question_cleanup() -> None:
    """Fragen (nicht Dokumente) löschen – bleibt bei den Dokumenten, weil es den Index betrifft."""
    from ragapp.ingestion.pipeline import remove_questions

    docs = _document_dicts()
    if not docs:
        return
    with card("fragen_cleanup"):
        st.subheader("🧠 Nur Fragen löschen (Dokumente & Chunks bleiben)")
        st.caption("Generierte Fragen erhöhen die Trefferquote, aber sehr viele können "
                   "die Suche verlangsamen. Hier gezielt welche entfernen, ohne die "
                   "Dokumente selbst anzutasten.")
        q_total = sum(d["num_questions"] for d in docs)
        st.write(f"Aktuell **{q_total}** Fragen im Index.")
        q_scope = st.radio("Umfang", ["Alle Fragen", "Nur ein Fach", "Nur bestimmte Dokumente"],
                           horizontal=True, key="q_cleanup_scope")

        if q_scope == "Alle Fragen":
            if st.button(f"🧹 Alle {q_total} Fragen löschen", disabled=q_total == 0,
                         key="q_cleanup_all"):
                remove_questions()
                st.success("Alle Fragen wurden gelöscht (Chunks bleiben erhalten).")
                st.rerun()
        elif q_scope == "Nur ein Fach":
            subj_q: dict = {}
            for d in docs:
                subj_q[d["subject"]] = subj_q.get(d["subject"], 0) + d["num_questions"]
            subj_map = {f"{s}  ·  {n} Fragen": s for s, n in sorted(subj_q.items())}
            sel_subj = st.selectbox("Fach", list(subj_map.keys()), key="q_cleanup_subj")
            if st.button("🧹 Fragen dieses Fachs löschen", key="q_cleanup_subj_go"):
                remove_questions(subject=subj_map[sel_subj])
                st.success(f"Fragen im Fach „{subj_map[sel_subj]}“ gelöscht.")
                st.rerun()
        else:
            q_docs = {
                f"[{d['subject']}] {d['filename']}  ·  {d['num_questions']} Fragen": d["doc_id"]
                for d in docs if d["num_questions"] > 0
            }
            if not q_docs:
                st.info("Kein Dokument hat aktuell Fragen.")
            else:
                sel_qdocs = st.multiselect("Dokument(e)", list(q_docs.keys()),
                                           placeholder="Auswählen …",
                                           key="q_cleanup_docs")
                if st.button("🧹 Fragen der gewählten Dokumente löschen",
                             disabled=not sel_qdocs, key="q_cleanup_docs_go"):
                    for lbl in sel_qdocs:
                        remove_questions(doc_id=q_docs[lbl])
                    st.success(f"Fragen aus {len(sel_qdocs)} Dokument(en) gelöscht.")
                    st.rerun()
