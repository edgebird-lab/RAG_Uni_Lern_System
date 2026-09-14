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
from ragapp.llm import require_vram, release_llm, VramLowError
from ragapp.hardware import probe_model
from ragapp.ingestion.question_gen import (
    QuestionGenError, generate_answer, generate_questions,
)

_SUMMARY_HINTS = ("zusammenfassung", "kompakt", "spickzettel", "klausur")


def _priority(chunk: dict) -> tuple:
    fn = (chunk["meta"].get("filename") or "").lower()
    is_summary = any(h in fn for h in _SUMMARY_HINTS)
    return (0 if is_summary else 1, -len(chunk["document"]))


def coalesce_short_chunks(chunks: list[dict], min_chars: int) -> list[dict]:
    """Zieht Mini-Abschnitte desselben Dokuments zusammen, bis sie fragentauglich sind.

    Markdown-Header-Splitting erzeugt oft 80–180-Zeichen-Chunks (Definition,
    Formel). Die sind lernbar, einzeln aber unter einer hart kodierten
    200-Zeichen-Schwelle – Lernset blieb dann leer. Zusammenziehen in
    Dateireihenfolge, nicht über Dokumentgrenzen.
    """
    ordered = sorted(
        chunks,
        key=lambda c: (str(c.get("meta", {}).get("doc_id") or ""), str(c.get("id") or "")),
    )
    out: list[dict] = []
    for ch in ordered:
        doc_id = (ch.get("meta") or {}).get("doc_id")
        text = ch.get("document") or ""
        if (
            out
            and (out[-1].get("meta") or {}).get("doc_id") == doc_id
            and len(out[-1].get("document") or "") < min_chars
        ):
            prev = out[-1]
            merged = dict(prev)
            merged["document"] = (prev.get("document") or "").rstrip() + "\n\n" + text
            merged["meta"] = dict(prev.get("meta") or {})
            out[-1] = merged
        else:
            out.append({
                "id": ch.get("id"),
                "document": text,
                "meta": dict(ch.get("meta") or {}),
            })
    return [c for c in out if len(c.get("document") or "") >= min_chars]


def _existing_question_parents() -> set:
    """parent_ids, für die schon Fragen existieren (Skip -> resumierbar)."""
    col = get_vectorstore()._col
    res = col.get(where={"type": "question"}, include=["metadatas"])
    return {m.get("parent_id") for m in res["metadatas"] if m.get("parent_id")}


def enrich_questions(limit: Optional[int] = None,
                     subject: Optional[str] = None,
                     doc_ids: Optional[list[str]] = None,
                     n_per_chunk: Optional[int] = None,
                     with_answers: bool = False,
                     progress=None) -> dict:
    """Erzeugt Fragen fuer noch nicht angereicherte Chunks. Optional gezielt fuer ein
    Fach (subject) und/oder bestimmte Dateien (doc_ids), mit ``n_per_chunk`` Fragen je
    Chunk. Mit ``with_answers`` wird zu jeder Frage gleich eine KI-Musterloesung erzeugt
    und in den Frage-Metadaten (Feld 'answer') abgelegt. Gibt ein EHRLICHES Ergebnis
    zurueck: status (ok/empty/llm_error/nothing_to_do), Zahlen, Fehlermeldung und eine
    Aufschluesselung pro Dokument (per_doc)."""
    store = get_vectorstore()
    embedder = get_embedder()

    chunks = store.get_all_chunks()
    if subject:
        chunks = [c for c in chunks if c["meta"].get("subject") == subject]
    if doc_ids:
        _wanted = set(doc_ids)
        chunks = [c for c in chunks if c["meta"].get("doc_id") in _wanted]
    min_chars = int(getattr(settings, "MIN_CHUNK_CHARS", 120) or 120)
    chunks = coalesce_short_chunks(chunks, min_chars)

    already = _existing_question_parents()
    chunks = [c for c in chunks if c["id"] not in already]
    chunks.sort(key=_priority)
    if limit:
        chunks = chunks[:limit]

    if not chunks:
        return {"status": "nothing_to_do", "processed": 0, "questions": 0,
                "errors": 0, "error_msg": None, "per_doc": {}}

    # Erst Platz schaffen (ohne ein schon geladenes Zielmodell zu killen),
    # dann erst den Intel-IPEX-Ping. Andersherum: probe lädt, require_vram
    # entlädt, GPU-Speicher ist noch belegt → falscher VRAM-Abbruch.
    try:
        require_vram(settings.LLM_MODEL_FAST)
    except VramLowError as exc:
        return {"status": "llm_error", "processed": 0, "questions": 0, "errors": 0,
                "error_msg": str(exc), "per_doc": {}}

    ok, msg = probe_model(settings.LLM_MODEL_FAST)
    if not ok:
        return {"status": "llm_error", "processed": 0, "questions": 0, "errors": 0,
                "error_msg": f"Modell '{settings.LLM_MODEL_FAST}' laeuft nicht: {msg}",
                "per_doc": {}}

    total_q = 0
    errors = 0
    error_msg: Optional[str] = None
    per_doc: dict[str, dict] = {}
    try:
        for i, ch in enumerate(chunks, 1):
            did = ch["meta"].get("doc_id")
            slot = per_doc.setdefault(did, {"filename": ch["meta"].get("filename"),
                                            "questions": 0, "chunks": 0, "errors": 0})
            if progress:
                progress(f"Anreicherung {i}/{len(chunks)} · {ch['meta'].get('filename', '?')}")
            try:
                qs = generate_questions(ch["document"], n=n_per_chunk)
            except QuestionGenError as exc:          # echter LLM-Fehler -> sichtbar machen
                errors += 1
                slot["errors"] += 1
                if error_msg is None:
                    error_msg = str(exc)
                if errors >= 3 and total_q == 0:     # Fail-fast: nicht endlos ins Leere
                    return {"status": "llm_error", "processed": i, "questions": total_q,
                            "errors": errors, "error_msg": error_msg, "per_doc": per_doc}
                continue
            slot["chunks"] += 1
            if not qs:
                continue
            # Optional: zu jeder Frage gleich eine Musterloesung erzeugen (kostet extra Zeit).
            answers: list[str] = []
            if with_answers:
                for q in qs:
                    try:
                        answers.append(generate_answer(ch["document"], q))
                    except QuestionGenError as exc:
                        answers.append("")
                        if error_msg is None:
                            error_msg = str(exc)
            q_embs = embedder.embed_texts(qs)
            ids, embeddings, documents, metadatas = [], [], [], []
            for j, (q, qe) in enumerate(zip(qs, q_embs)):
                qmeta = {k: v for k, v in ch["meta"].items()}
                qmeta["type"] = "question"
                qmeta["parent_id"] = ch["id"]
                if with_answers and j < len(answers) and answers[j]:
                    qmeta["answer"] = answers[j]
                ids.append(f"{ch['id']}::eq{j}")
                embeddings.append(qe)
                documents.append(q)
                metadatas.append(qmeta)
            store.add(ids, embeddings, documents, metadatas)
            total_q += len(qs)
            slot["questions"] += len(qs)

        # Manifest-Zähler aktualisieren
        for did, slot in per_doc.items():
            n = slot["questions"]
            if n <= 0:
                continue
            d = manifest.get_document(did)
            if d:
                d = dict(d)
                manifest.upsert_document(
                    doc_id=did, content_hash=d["content_hash"], source_path=d["source_path"],
                    filename=d["filename"], subject=d["subject"], filetype=d["filetype"],
                    num_chunks=d["num_chunks"], num_questions=(d["num_questions"] or 0) + n,
                    char_count=d["char_count"], status=d["status"],
                    ocr_partial_pages=int(d.get("ocr_partial_pages") or 0),
                )

        if total_q > 0:
            from ragapp.study import mark_needs_card_harvest
            mark_needs_card_harvest()

        status = "ok" if total_q > 0 else ("llm_error" if errors else "empty")
        return {"status": status, "processed": len(chunks), "questions": total_q,
                "errors": errors, "error_msg": error_msg, "per_doc": per_doc}
    finally:
        release_llm()
