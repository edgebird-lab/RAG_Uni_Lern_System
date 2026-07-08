"""
Fragen-Anreicherung (opt-in, gedeckelt)
======================================

Erzeugt und indexiert hypothetische Fragen für bereits vorhandene Chunks,
gezielt und in kontrollierter Menge, damit es auch auf CPU-Hardware praktikabel
bleibt (jede Frage-Generierung kostet dort ~20 s).

Priorisierung: Zusammenfassungs-/Kompakt-/Spickzettel-Dokumente zuerst, dann
längere (informationsreichere) Chunks. Bereits angereicherte Chunks werden
übersprungen (resumierbar).

Aufruf z. B.:
    python -m ragapp.scripts.cli enrich --limit 200
    python -m ragapp.scripts.cli enrich --limit 100 --subject KuLR
"""
from __future__ import annotations

from typing import Optional

from ragapp.config import settings
from ragapp import manifest
from ragapp.retrieval.vectorstore import get_vectorstore
from ragapp.retrieval.embeddings import get_embedder
from ragapp.ingestion.question_gen import generate_questions

_SUMMARY_HINTS = ("zusammenfassung", "kompakt", "spickzettel", "klausur")


def _priority(chunk: dict) -> tuple:
    fn = (chunk["meta"].get("filename") or "").lower()
    is_summary = any(h in fn for h in _SUMMARY_HINTS)
    return (0 if is_summary else 1, -len(chunk["document"]))


def _existing_question_parents() -> set:
    """parent_ids, für die schon Fragen existieren (Skip -> resumierbar)."""
    col = get_vectorstore()._col
    res = col.get(where={"type": "question"}, include=["metadatas"])
    return {m.get("parent_id") for m in res["metadatas"] if m.get("parent_id")}


def enrich_questions(limit: Optional[int] = None,
                     subject: Optional[str] = None,
                     progress=None) -> dict:
    store = get_vectorstore()
    embedder = get_embedder()

    chunks = store.get_all_chunks()
    if subject:
        chunks = [c for c in chunks if c["meta"].get("subject") == subject]
    chunks = [c for c in chunks if len(c["document"]) >= max(settings.MIN_CHUNK_CHARS, 200)]

    already = _existing_question_parents()
    chunks = [c for c in chunks if c["id"] not in already]
    chunks.sort(key=_priority)
    if limit:
        chunks = chunks[:limit]

    if not chunks:
        return {"status": "nothing_to_do", "processed": 0, "questions": 0}

    total_q = 0
    per_doc: dict[str, int] = {}
    for i, ch in enumerate(chunks, 1):
        if progress:
            progress(f"Anreicherung {i}/{len(chunks)} · {ch['meta'].get('filename','?')}")
        qs = generate_questions(ch["document"])
        if not qs:
            continue
        q_embs = embedder.embed_texts(qs)
        ids, embeddings, documents, metadatas = [], [], [], []
        for j, (q, qe) in enumerate(zip(qs, q_embs)):
            qmeta = {k: v for k, v in ch["meta"].items()}
            qmeta["type"] = "question"
            qmeta["parent_id"] = ch["id"]
            ids.append(f"{ch['id']}::eq{j}")
            embeddings.append(qe)
            documents.append(q)
            metadatas.append(qmeta)
        store.add(ids, embeddings, documents, metadatas)
        total_q += len(qs)
        doc_id = ch["meta"].get("doc_id")
        per_doc[doc_id] = per_doc.get(doc_id, 0) + len(qs)

    # Manifest-Zähler aktualisieren
    for doc_id, n in per_doc.items():
        d = manifest.get_document(doc_id)
        if d:
            manifest.upsert_document(
                doc_id=doc_id, content_hash=d["content_hash"], source_path=d["source_path"],
                filename=d["filename"], subject=d["subject"], filetype=d["filetype"],
                num_chunks=d["num_chunks"], num_questions=(d["num_questions"] or 0) + n,
                char_count=d["char_count"], status=d["status"],
            )

    return {"status": "ok", "processed": len(chunks), "questions": total_q}
