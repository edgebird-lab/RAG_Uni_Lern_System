"""
Ingestion-Pipeline
==================

Der automatische Weg vom Rohdokument in die Vektordatenbank:

    Datei  →  Laden  →  Dedup(Dokument)  →  Chunking  →  Dedup(Chunk, exakt)
          →  Embeddings  →  Dedup(Chunk, near-duplicate)  →  Fragen-Generierung
          →  Speichern (Chroma)  →  BM25-Neuaufbau  →  Manifest-Eintrag

Ein PDF (oder MD/DOCX/PPTX) einfach in den Quell- oder Inbox-Ordner legen und
``ingest_directory`` bzw. den Ordnerwächter laufen lassen, der Rest passiert
automatisch. Alles wird in ``data/logs/ingestion.jsonl`` protokolliert.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Optional

from ragapp.config import settings, SOURCE_DIR, PROJECT_ROOT, LOG_DIR
from ragapp import manifest
from ragapp.ingestion.loaders import load_document, SUPPORTED_EXTENSIONS
from ragapp.ingestion.chunker import chunk_document
from ragapp.ingestion import dedup
from ragapp.ingestion.question_gen import generate_questions
from ragapp.retrieval.embeddings import get_embedder
from ragapp.retrieval.vectorstore import get_vectorstore
from ragapp.retrieval.bm25_index import rebuild_bm25_from_store
from ragapp.ingestion.textquality import is_gibberish   # NEU

_INGEST_LOG = LOG_DIR / "ingestion.jsonl"
# Erweiterter Fortschritts-Contract: progress(message, done=None, total=None).
# Rueckwaertskompatibel - alte Ein-Argument-Callbacks progress("...") bleiben gueltig.
ProgressFn = Optional[Callable[..., None]]


def _log(entry: dict) -> None:
    entry["ts"] = time.time()
    with open(_INGEST_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _emit(progress: ProgressFn, message: str,
          done: int | None = None, total: int | None = None) -> None:
    """Ruft den Fortschritts-Callback gemaess erweitertem Contract auf
    (message, done, total). Faellt auf die alte Ein-Argument-Form zurueck, falls
    der Callback done/total (noch) nicht akzeptiert. Fehler im Callback duerfen
    den Import nie abbrechen."""
    if not progress:
        return
    try:
        progress(message, done, total)
    except TypeError:
        try:
            progress(message)
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        pass


def _pdf_stems() -> set:
    """Alle PDF-Dateinamen (ohne Endung, klein) im Quellordner."""
    return {p.stem.lower() for p in SOURCE_DIR.rglob("*.pdf")}


def _md_stems() -> set:
    """Alle Markdown-Dateinamen (ohne Endung, klein) im Quellordner."""
    return {p.stem.lower() for p in SOURCE_DIR.rglob("*.md")} | \
           {p.stem.lower() for p in SOURCE_DIR.rglob("*.markdown")}


def should_ingest(path: Path, pdf_stems: set | None = None,
                  md_stems: set | None = None) -> tuple[bool, str]:
    """Entscheidet, ob eine Datei importiert wird.

    - Anki-/Karteikarten-Dateien werden ausgeschlossen.
    - Markdown wird gegenüber gleichnamiger PDF bevorzugt (Formeln bleiben erhalten):
      die PDF wird dann übersprungen, die .md indexiert.
    - .txt, zu dem eine gleichnamige PDF ODER .md existiert, wird als Duplikat verworfen.
    """
    name = path.name.lower()
    for sub in settings.INGEST_EXCLUDE_NAME_SUBSTRINGS:
        if sub in name:
            return False, f"ausgeschlossen ({sub})"
    if settings.INGEST_PREFER_MARKDOWN:
        ext = path.suffix.lower()
        stem = path.stem.lower()
        if ext == ".pdf":
            mstems = md_stems if md_stems is not None else _md_stems()
            if stem in mstems:
                return False, "Markdown-Version bevorzugt (Formeln bleiben erhalten)"
        elif ext == ".txt":
            pstems = pdf_stems if pdf_stems is not None else _pdf_stems()
            mstems = md_stems if md_stems is not None else _md_stems()
            if stem in pstems or stem in mstems:
                return False, "Duplikat (gleichnamige PDF/MD vorhanden)"
    return True, ""


def extraction_quality(text: str, filetype: str = "") -> tuple[bool, str]:
    """Grobe Heuristik, ob die Textextraktion plausibel gelungen ist. Faengt still
    verunglueckte Importe ab (Scan/Bild-PDF ohne Text, kaputte Kodierung, Zeichenbrei),
    damit der Nutzer nicht einer Vollstaendigkeit vertraut, die nicht existiert.
    Gibt (ok, grund) zurueck - ok=False -> 'OCR/Neu-Import empfohlen'."""
    import re
    t = text or ""
    n = len(t)
    if n < 200:
        return False, "sehr wenig Text extrahiert – vermutlich Scan/Bild (OCR nötig)"
    letters = sum(1 for ch in t if ch.isalnum())
    if letters / max(1, n) < 0.45:
        return False, "viele unlesbare Zeichen – Textextraktion vermutlich fehlerhaft"
    if t.count("�") > n * 0.005:
        return False, "viele Ersatzzeichen (�) – Kodierung/Extraktion fehlerhaft"
    words = re.findall(r"\S+", t)
    if words:
        avg = sum(len(w) for w in words) / len(words)
        if avg > 25 or avg < 2:
            return False, "unplausible Wortstruktur – Textextraktion vermutlich fehlerhaft"
    # NEU: harter Kauderwelsch-Test auf Dokumentebene. Anders als die weichen
    # Checks oben BLOCKT dieses Ergebnis den Import (ingest_file wertet das
    # Präfix "gibberish:" aus). Strengere Schwelle als der Chunk-Filter, damit
    # gemischte Dokumente NICHT komplett verworfen werden.
    if settings.GIBBERISH_FILTER:
        g, why = is_gibberish(
            t,
            min_chars=settings.GIBBERISH_MIN_CHARS,
            min_alpha_ratio=settings.GIBBERISH_MIN_ALPHA_RATIO,
            min_tokens=settings.GIBBERISH_MIN_TOKENS,
            max_meaningfulness=settings.GIBBERISH_DOC_MAX_MEANINGFULNESS,
        )
        if g:
            return False, "gibberish: " + why
    return True, ""


def _subject_for(path: Path) -> str:
    """Fach = erster Unterordner unter dem Quellordner; sonst Ordnername/Allgemein."""
    try:
        rel = path.resolve().relative_to(SOURCE_DIR.resolve())
        parts = rel.parts
        if len(parts) >= 2:
            return parts[0]
    except Exception:
        pass
    parent = path.parent.name
    return parent or "Allgemein"


def _relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except Exception:
        return str(path.resolve())


def ingest_file(
    path: str | Path,
    *,
    subject: Optional[str] = None,
    force: bool = False,
    rebuild_bm25: bool = True,
    progress: ProgressFn = None,
) -> dict:
    path = Path(path)
    # Fortschritts-Contract: p(message, done=None, total=None) - done/total
    # optional (fuer zaehlbare Stufen: OCR-Seiten, Embedding-Batches).
    p = lambda m, done=None, total=None: _emit(progress, m, done, total)  # noqa: E731

    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return {"status": "skipped", "reason": "unsupported", "file": path.name}

    ok, why = should_ingest(path)
    if not ok:
        return {"status": "skipped", "reason": why, "file": path.name}

    rel = _relative_path(path)
    doc_id = dedup.doc_id_for(rel)
    subject = subject or _subject_for(path)

    p(f"Lade {path.name} …")
    loaded = load_document(path, progress=p)   # p meldet OCR-Seiten (done/total)
    # F2: unvollstaendig gelesene OCR-Seiten (fuer Ingestion-Warnung sichtbar machen)
    _ocr_partial = int((loaded.meta or {}).get("ocr_low_pages", 0) or 0)
    if not loaded.text.strip():
        # Leerer Text: bei PDFs fast immer ein Scan/Bild -> SICHTBAR machen (OCR nötig)
        # statt still zu überspringen. Andere leere Dateien: wie bisher überspringen.
        if (loaded.filetype or path.suffix.lower().lstrip(".")) == "pdf":
            manifest.upsert_document(
                doc_id=doc_id, content_hash=dedup.content_hash(loaded.text),
                source_path=rel, filename=path.name, subject=subject,
                filetype=loaded.filetype, num_chunks=0, num_questions=0,
                char_count=0, status="ocr_needed")
            _log({"event": "ingest", "file": rel, "status": "ocr_needed", "reason": "empty_pdf"})
            return {"status": "ocr_needed", "file": path.name,
                    "reason": "kein Text extrahierbar (Scan/Bild – OCR nötig)"}
        _log({"event": "ingest", "file": rel, "status": "empty"})
        return {"status": "skipped", "reason": "empty", "file": path.name}

    # Qualitaets-Gate: verunglueckte Extraktion (Zeichenbrei, kaputte Kodierung) melden.
    _q_ok, _q_reason = extraction_quality(loaded.text, loaded.filetype)

    chash = dedup.content_hash(loaded.text)

    # ---- Dedup auf Dokumentebene -------------------------------------- #
    existing_same_content = manifest.find_document_by_content(chash)
    existing_doc = manifest.get_document(doc_id)

    if existing_same_content and existing_same_content["doc_id"] != doc_id and not force:
        _log({"event": "ingest", "file": rel, "status": "duplicate",
              "duplicate_of": existing_same_content["source_path"]})
        return {"status": "duplicate", "file": path.name,
                "duplicate_of": existing_same_content["filename"]}

    if existing_doc and existing_doc["content_hash"] == chash and not force:
        return {"status": "unchanged", "file": path.name,
                "chunks": existing_doc["num_chunks"]}

    # Update (Inhalt geändert) oder Force. Idempotenz-Fix (Ro3):
    # 'write-new-then-delete-old'. Die alten Chunks werden hier NICHT mehr sofort
    # gelöscht. Stattdessen werden zuerst die neuen Chunks/Embeddings geschrieben
    # und der content_hash gesetzt (weiter unten); ERST danach werden die alten/
    # verwaisten Einträge entfernt. So hinterlässt ein Abbruch dazwischen nie ein
    # verwaistes Leer-Dokument (leere Chroma trotz gemeldeter num_chunks>0), das
    # fälschlich als 'vorhanden/unverändert' gälte.
    is_update = existing_doc is not None
    if is_update:
        p("Aktualisiere Dokument …")

    # ---- Früh-Block: gesamtes Dokument ist Kauderwelsch (Handschrift/Scan) ---- #
    # extraction_quality hat den harten Kauderwelsch-Test bereits gefahren
    # (Reason-Präfix "gibberish:"). Dann gar nicht erst chunken/einbetten.
    if _q_reason.startswith("gibberish:"):
        manifest.upsert_document(
            doc_id=doc_id, content_hash=chash, source_path=rel, filename=path.name,
            subject=subject, filetype=loaded.filetype, num_chunks=0, num_questions=0,
            char_count=len(loaded.text), status="unreadable")
        if is_update:
            # content_hash steht -> jetzt erst die alten Chunks entfernen.
            get_vectorstore().delete_by_doc(doc_id)
            manifest.clear_chunk_hashes(doc_id)
            if rebuild_bm25:
                rebuild_bm25_from_store()  # verwaiste BM25-IDs nach Löschung vermeiden
        _log({"event": "ingest", "file": rel, "status": "unreadable",
              "reason": _q_reason})
        return {"status": "unreadable", "file": path.name,
                "reason": "Text unlesbar – Handschrift/Scan; nichts gespeichert"}

    # ---- Chunking ----------------------------------------------------- #
    base_meta = {
        "doc_id": doc_id,
        "subject": subject,
        "filename": path.name,
        "source_path": rel,
        "filetype": loaded.filetype,
    }
    p("Zerlege in Chunks …")
    chunks = chunk_document(loaded, base_meta)

    # ---- Exakte Chunk-Dedup (pro Dokument) ---------------------------- #
    # Bewusst dokument-lokal (nicht global): globale Dedup würde einen geteilten
    # Chunk nur beim ERSTEN Dokument speichern; beim Löschen/Aktualisieren dieses
    # Dokuments verschwände der Inhalt aus dem Index, obwohl ihn ein anderes
    # Dokument noch enthält. Ein lokales Set entfernt zuverlässig exakt gleiche
    # Textstücke INNERHALB des Dokuments (z. B. wiederholte Formelkästen).
    # Doppelte Informationen über Dokumentgrenzen hinweg werden zur Query-Zeit
    # per Jaccard-Dedup entfernt.
    kept_chunks = []
    seen_hashes: set[str] = set()
    for ch in chunks:
        h = dedup.chunk_hash(ch.text)
        if h in seen_hashes:
            continue
        seen_hashes.add(h)
        ch.meta["_chunk_hash"] = h
        kept_chunks.append(ch)

    # ---- Kauderwelsch-Gate pro Chunk (die eigentliche Garantie) --------- #
    # KEIN Zeichenmüll landet als Chunk im Index. Es wird NIE umgeschrieben,
    # nur verworfen -> native Dokumente bleiben wortgetreu. Bleibt (fast) nichts
    # übrig, wird das Dokument NICHT aufgenommen (Status "unreadable").
    dropped_gibberish = 0
    if settings.GIBBERISH_FILTER and kept_chunks:
        n_before = len(kept_chunks)
        readable = []
        for ch in kept_chunks:
            g, why = is_gibberish(
                ch.text,
                min_chars=settings.GIBBERISH_MIN_CHARS,
                min_alpha_ratio=settings.GIBBERISH_MIN_ALPHA_RATIO,
                min_tokens=settings.GIBBERISH_MIN_TOKENS,
                max_meaningfulness=settings.GIBBERISH_MAX_MEANINGFULNESS,
            )
            if g:
                dropped_gibberish += 1
                _log({"event": "chunk_dropped", "file": rel, "reason": "gibberish",
                      "detail": why, "chunk_index": ch.meta.get("chunk_index")})
            else:
                readable.append(ch)
        drop_ratio = dropped_gibberish / max(1, n_before)
        if not readable or drop_ratio >= settings.GIBBERISH_DOC_DROP_RATIO:
            manifest.upsert_document(
                doc_id=doc_id, content_hash=chash, source_path=rel, filename=path.name,
                subject=subject, filetype=loaded.filetype, num_chunks=0, num_questions=0,
                char_count=len(loaded.text), status="unreadable")
            if is_update:
                # content_hash steht -> alte Chunks erst danach entfernen.
                get_vectorstore().delete_by_doc(doc_id)
                manifest.clear_chunk_hashes(doc_id)
            if rebuild_bm25:
                rebuild_bm25_from_store()
            _log({"event": "ingest", "file": rel, "status": "unreadable",
                  "dropped": dropped_gibberish, "of": n_before})
            return {"status": "unreadable", "file": path.name,
                    "reason": "Text unlesbar – Handschrift/Scan; nichts gespeichert",
                    "dropped_chunks": dropped_gibberish}
        kept_chunks = readable

    if not kept_chunks:
        manifest.upsert_document(
            doc_id=doc_id, content_hash=chash, source_path=rel, filename=path.name,
            subject=subject, filetype=loaded.filetype, num_chunks=0, num_questions=0,
            char_count=len(loaded.text), status="all_duplicate",
        )
        if is_update:
            # content_hash steht -> alte Chunks erst danach entfernen, sonst
            # behielte der BM25-Index verwaiste IDs.
            get_vectorstore().delete_by_doc(doc_id)
            manifest.clear_chunk_hashes(doc_id)
        if rebuild_bm25:
            rebuild_bm25_from_store()
        _log({"event": "ingest", "file": rel, "status": "all_chunks_duplicate"})
        return {"status": "duplicate_chunks", "file": path.name, "chunks": 0}

    # ---- Embeddings der Chunks (batch-weise, mit Fortschritt) -------- #
    # Eine Fortschritts-Stufe = so viele Chunks, wie ohnehin parallel verarbeitet
    # werden (EMBED_BATCH_SIZE * EMBED_CONCURRENCY). Dadurch bleibt das bisherige
    # parallele Embedding-Verhalten erhalten und der UI-Balken bekommt done/total.
    embedder = get_embedder()
    _texts = [c.text for c in kept_chunks]
    _total = len(_texts)
    _step = max(1, settings.EMBED_BATCH_SIZE) * max(1, settings.EMBED_CONCURRENCY)
    p(f"Berechne Embeddings ({_total} Chunks) …", 0, _total)
    chunk_embeddings: list[list[float]] = []
    for _bi in range(0, _total, _step):
        chunk_embeddings.extend(embedder.embed_texts(_texts[_bi:_bi + _step]))
        _done = min(_total, _bi + _step)
        p(f"Berechne Embeddings ({_done}/{_total} Chunks) …", _done, _total)

    # ---- Near-Duplicate-Filter (innerhalb Dokument) ------------------ #
    keep_idx = dedup.filter_near_duplicates(chunk_embeddings)
    kept_chunks = [kept_chunks[i] for i in keep_idx]
    chunk_embeddings = [chunk_embeddings[i] for i in keep_idx]

    # ---- Fragen-Generierung ------------------------------------------ #
    ids: list[str] = []
    embeddings: list[list[float]] = []
    documents: list[str] = []
    metadatas: list[dict] = []
    n_questions = 0

    chunk_ids: list[str] = []            # nur die Chunk-IDs (fuer die Alt-Bereinigung)
    chunk_hash_regs: list[tuple[str, str]] = []  # (chunk_hash, chunk_id) - erst NACH dem Schreiben registrieren
    for ch, emb in zip(kept_chunks, chunk_embeddings):
        idx = ch.meta.get("chunk_index", len(ids))
        chunk_id = f"{doc_id}::c{idx}"
        meta = {k: v for k, v in ch.meta.items() if not k.startswith("_")}
        meta["type"] = "chunk"
        ids.append(chunk_id)
        embeddings.append(emb)
        documents.append(ch.text)
        metadatas.append(meta)
        chunk_ids.append(chunk_id)
        # Registrierung der Chunk-Hashes bewusst aufschieben (Ro3): erst NACH dem
        # erfolgreichen Schreiben in Chroma, damit die Alt-/Neu-Bereinigung sauber greift.
        chunk_hash_regs.append((ch.meta["_chunk_hash"], chunk_id))

    # Fragen erzeugen + einbetten (Batch für Effizienz)
    if settings.ENABLE_QUESTION_INDEXING:
        p("Generiere Indexierungs-Fragen (Trefferquote ↑) …")
        all_questions: list[tuple[str, str, dict]] = []  # (parent_id, question, base_meta)
        for ch, chunk_id in zip(kept_chunks, ids):
            qs = generate_questions(ch.text)
            for q in qs:
                qmeta = {k: v for k, v in ch.meta.items() if not k.startswith("_")}
                qmeta["type"] = "question"
                qmeta["parent_id"] = chunk_id
                all_questions.append((chunk_id, q, qmeta))
        if all_questions:
            q_embs = embedder.embed_texts([q for _, q, _ in all_questions])
            for (parent_id, q, qmeta), qe in zip(all_questions, q_embs):
                qid = f"{parent_id}::q{n_questions}"
                ids.append(qid)
                embeddings.append(qe)
                documents.append(q)
                metadatas.append(qmeta)
                n_questions += 1

    # ---- Speichern in Chroma (write-new-then-delete-old, Ro3) --------- #
    # Bei einem Update zuerst die bisherigen Chunk-IDs merken und die alten
    # (abgeleiteten) Fragen entfernen, DANN die neuen Einträge schreiben. Der
    # content_hash wird erst NACH dem erfolgreichen Schreiben gesetzt.
    old_chunk_ids: set[str] = set()
    if is_update:
        # Verlässliche Quelle der alten Chunk-IDs: die TATSÄCHLICH in Chroma liegenden
        # Chunks dieses Dokuments (per Metadaten) – registry- UND index-unabhängig.
        # Deckt auch Waisen ab, die die Hash-Registry (PK = Chunk-Hash) bei
        # doc-übergreifend text-identischen Chunks verfehlt, und ist robust gegen
        # Index-Lücken (gedroppte Chunks) im deterministischen ID-Schema. Die Registry
        # wird zusätzlich vereinigt (Gürtel + Hosenträger).
        old_chunk_ids = set(get_vectorstore().chunk_ids_for_doc(doc_id))
        old_chunk_ids |= set(manifest.chunk_ids_for_doc(doc_id))
        # Alte Fragen sind abgeleitete Daten und müssen VOR dem Schreiben weg
        # (danach träfe delete_questions_by_doc auch die neuen Fragen).
        get_vectorstore().delete_questions_by_doc(doc_id)

    p("Speichere in Vektordatenbank …")
    get_vectorstore().add(ids, embeddings, documents, metadatas)

    # content_hash erst jetzt setzen: ab hier gilt das Dokument als vorhanden -
    # und seine Chunks liegen bereits in Chroma. Ein Abbruch vor diesem Punkt
    # lässt die ALTE (vollständige) Version stehen, nie einen Leer-Zustand.
    manifest.upsert_document(
        doc_id=doc_id, content_hash=chash, source_path=rel, filename=path.name,
        subject=subject, filetype=loaded.filetype, num_chunks=len(kept_chunks),
        num_questions=n_questions, char_count=len(loaded.text),
        status="ok" if _q_ok else "ocr_needed",
        ocr_partial_pages=_ocr_partial,
    )

    # Jetzt erst die verwaisten ALTEN Chunks entfernen (die die neue Version nicht
    # mehr enthält). Neue Chunks mit gleicher ID wurden oben bereits überschrieben.
    if is_update:
        new_ids = set(chunk_ids)
        stale = [cid for cid in old_chunk_ids if cid not in new_ids]
        if stale:
            get_vectorstore().delete_by_ids(stale)

    # Chunk-Hash-Registry auf den neuen Stand bringen (bewusst nach dem Schreiben;
    # reine Buchführung, index-unkritisch): alte Einträge des Dokuments ersetzen.
    manifest.clear_chunk_hashes(doc_id)
    for _h, _cid in chunk_hash_regs:
        manifest.register_chunk_hash(_h, doc_id, _cid)

    if rebuild_bm25:
        p("Aktualisiere BM25-Index …")
        rebuild_bm25_from_store()

    _log({"event": "ingest", "file": rel, "status": "ok" if _q_ok else "low_quality",
          "chunks": len(kept_chunks), "questions": n_questions, "subject": subject,
          "quality_reason": _q_reason or None})
    return {"status": "ok", "file": path.name, "subject": subject,
            "chunks": len(kept_chunks), "questions": n_questions,
            "quality_ok": _q_ok, "quality_reason": _q_reason,
            "dropped_chunks": dropped_gibberish}   # NEU


def ingest_directory(
    directory: str | Path | None = None,
    *,
    force: bool = False,
    progress: ProgressFn = None,
) -> dict:
    directory = Path(directory) if directory else SOURCE_DIR
    files = [p for p in directory.rglob("*") if p.suffix.lower() in SUPPORTED_EXTENSIONS]

    # Anki-/Karteikarten-Dateien ausschließen, Markdown vor gleichnamiger PDF bevorzugen
    _pstems = {p.stem.lower() for p in files if p.suffix.lower() == ".pdf"}
    _mstems = {p.stem.lower() for p in files if p.suffix.lower() in (".md", ".markdown")}
    _before = len(files)
    files = [f for f in files if should_ingest(f, _pstems, _mstems)[0]]
    if progress:
        progress(f"{_before - len(files)} Dateien ausgeschlossen (Anki/Duplikate), "
                 f"{len(files)} werden importiert.")

    # Priorisierung: Zusammenfassungs-/Kompakt-Dokumente zuerst (wichtigstes
    # Lernmaterial), dann kleinere vor größeren Dateien -> früh viele Dokumente
    # verfügbar. (Betrifft nur die Reihenfolge; es werden trotzdem alle geladen.)
    _hints = ("zusammenfassung", "kompakt", "spickzettel", "klausur")

    def _prio(p: Path) -> tuple:
        name = p.name.lower()
        is_summary = any(h in name for h in _hints)
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        return (0 if is_summary else 1, size)

    files.sort(key=_prio)
    results = {"ok": 0, "duplicate": 0, "unchanged": 0, "skipped": 0, "error": 0,
               "chunks": 0, "questions": 0, "details": []}
    _n = len(files)
    for i, f in enumerate(files, 1):
        # Fortschritts-Contract: done/total pro Datei (fuer UI-Balken + ETA).
        _emit(progress, f"[{i}/{_n}] {f.name}", i, _n)
        try:
            r = ingest_file(f, force=force, rebuild_bm25=False, progress=progress)
        except Exception as exc:  # pragma: no cover
            _log({"event": "ingest", "file": str(f), "status": "error", "error": str(exc)})
            r = {"status": "error", "file": f.name, "error": str(exc)}
        st = r["status"]
        if st == "ok":
            results["ok"] += 1
            results["chunks"] += r.get("chunks", 0)
            results["questions"] += r.get("questions", 0)
        elif st in ("duplicate", "duplicate_chunks"):
            results["duplicate"] += 1
        elif st == "unchanged":
            results["unchanged"] += 1
        elif st == "error":
            results["error"] += 1
        else:
            results["skipped"] += 1
        results["details"].append(r)

    if progress:
        progress("Baue BM25-Index neu auf …")
    rebuild_bm25_from_store()
    return results


def remove_document(doc_id: str) -> None:
    """Entfernt ein Dokument vollständig (Chroma + Manifest)."""
    get_vectorstore().delete_by_doc(doc_id)
    manifest.delete_document(doc_id)
    rebuild_bm25_from_store()


def remove_questions(doc_id: str | None = None, subject: str | None = None) -> None:
    """Entfernt generierte Fragen selektiv - Dokumente und Chunks bleiben erhalten.

    - ``doc_id`` gesetzt   -> nur die Fragen dieses Dokuments,
    - ``subject`` gesetzt  -> alle Fragen dieses Fachs,
    - beides ``None``      -> alle Fragen im Index.

    Der BM25-Index bleibt unberührt (er enthält nur Chunks, keine Fragen).
    """
    vs = get_vectorstore()
    if doc_id:
        vs.delete_questions_by_doc(doc_id)
        manifest.set_num_questions(doc_id, 0)
    elif subject:
        vs.delete_questions_by_subject(subject)
        manifest.clear_questions(subject=subject)
    else:
        vs.delete_all_questions()
        manifest.clear_questions()
