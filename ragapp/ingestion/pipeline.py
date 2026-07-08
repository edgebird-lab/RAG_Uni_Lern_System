"""
Ingestion-Pipeline
==================

Der automatische Weg vom Rohdokument in die Vektordatenbank:

    Datei  →  Laden  →  Dedup(Dokument)  →  Chunking  →  Dedup(Chunk, exakt)
          →  Embeddings  →  Dedup(Chunk, near-duplicate)  →  Fragen-Generierung
          →  Speichern (Chroma)  →  BM25-Neuaufbau  →  Manifest-Eintrag

Ein PDF (oder MD/DOCX/PPTX) einfach in den Quell- oder Inbox-Ordner legen und
``ingest_directory`` bzw. den Ordnerwächter laufen lassen – der Rest passiert
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

_INGEST_LOG = LOG_DIR / "ingestion.jsonl"
ProgressFn = Optional[Callable[[str], None]]


def _log(entry: dict) -> None:
    entry["ts"] = time.time()
    with open(_INGEST_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


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
    p = lambda m: progress(m) if progress else None  # noqa: E731

    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return {"status": "skipped", "reason": "unsupported", "file": path.name}

    ok, why = should_ingest(path)
    if not ok:
        return {"status": "skipped", "reason": why, "file": path.name}

    rel = _relative_path(path)
    doc_id = dedup.doc_id_for(rel)
    subject = subject or _subject_for(path)

    p(f"Lade {path.name} …")
    loaded = load_document(path)
    if not loaded.text.strip():
        _log({"event": "ingest", "file": rel, "status": "empty"})
        return {"status": "skipped", "reason": "empty", "file": path.name}

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

    # Update (Inhalt geändert) oder Force: alte Einträge entfernen
    if existing_doc:
        p("Aktualisiere – entferne alte Chunks …")
        get_vectorstore().delete_by_doc(doc_id)
        manifest.clear_chunk_hashes(doc_id)

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

    if not kept_chunks:
        manifest.upsert_document(
            doc_id=doc_id, content_hash=chash, source_path=rel, filename=path.name,
            subject=subject, filetype=loaded.filetype, num_chunks=0, num_questions=0,
            char_count=len(loaded.text), status="all_duplicate",
        )
        # BM25 ggf. neu aufbauen: im Update-Pfad wurden oben alte Chunks aus
        # Chroma gelöscht – sonst behielte der BM25-Index verwaiste IDs.
        if rebuild_bm25:
            rebuild_bm25_from_store()
        _log({"event": "ingest", "file": rel, "status": "all_chunks_duplicate"})
        return {"status": "duplicate_chunks", "file": path.name, "chunks": 0}

    # ---- Embeddings der Chunks --------------------------------------- #
    p(f"Berechne Embeddings ({len(kept_chunks)} Chunks) …")
    embedder = get_embedder()
    chunk_embeddings = embedder.embed_texts([c.text for c in kept_chunks])

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

    for ch, emb in zip(kept_chunks, chunk_embeddings):
        idx = ch.meta.get("chunk_index", len(ids))
        chunk_id = f"{doc_id}::c{idx}"
        meta = {k: v for k, v in ch.meta.items() if not k.startswith("_")}
        meta["type"] = "chunk"
        ids.append(chunk_id)
        embeddings.append(emb)
        documents.append(ch.text)
        metadatas.append(meta)
        manifest.register_chunk_hash(ch.meta["_chunk_hash"], doc_id, chunk_id)

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

    # ---- Speichern in Chroma ----------------------------------------- #
    p("Speichere in Vektordatenbank …")
    get_vectorstore().add(ids, embeddings, documents, metadatas)

    manifest.upsert_document(
        doc_id=doc_id, content_hash=chash, source_path=rel, filename=path.name,
        subject=subject, filetype=loaded.filetype, num_chunks=len(kept_chunks),
        num_questions=n_questions, char_count=len(loaded.text), status="ok",
    )

    if rebuild_bm25:
        p("Aktualisiere BM25-Index …")
        rebuild_bm25_from_store()

    _log({"event": "ingest", "file": rel, "status": "ok",
          "chunks": len(kept_chunks), "questions": n_questions, "subject": subject})
    return {"status": "ok", "file": path.name, "subject": subject,
            "chunks": len(kept_chunks), "questions": n_questions}


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
    for i, f in enumerate(files, 1):
        if progress:
            try:
                progress(f"[{i}/{len(files)}] {f.name}")
            except Exception:
                pass  # z. B. Encoding-Fehler dürfen den Batch nicht abbrechen
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
