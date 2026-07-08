"""
Hybrid-Retrieval (Dense + BM25 → RRF → Rerank)
==============================================

Pipeline für maximale Trefferquote:

    1. **Dense-Suche** (bge-m3) über Chunks *und* generierte Fragen. Frage-Treffer
       werden auf ihren Eltern-Chunk zurückgeführt.
    2. **BM25-Suche** (Keyword) über Chunks.
    3. **Reciprocal Rank Fusion (RRF)** vereint beide Ranglisten robust ohne
       Score-Skalierungsprobleme.
    4. **Cross-Encoder-Rerank** sortiert die Top-Kandidaten final.

Rückgabe: Liste finaler Chunk-Kandidaten mit Scores und Herkunftsangabe.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from ragapp.config import settings
from ragapp.retrieval.embeddings import get_embedder
from ragapp.retrieval.vectorstore import get_vectorstore
from ragapp.retrieval.bm25_index import get_bm25
from ragapp.retrieval.reranker import get_reranker


def _dense_chunk_ranking(query_emb: list[float], where: Optional[dict]) -> tuple[list[str], dict]:
    """Dense-Suche; Frage-Treffer -> Eltern-Chunk. Liefert geordnete Chunk-IDs."""
    store = get_vectorstore()
    raw = store.query(query_emb, n_results=settings.DENSE_TOP_K, where=where)
    ordered: list[str] = []
    seen = set()
    dense_score: dict[str, float] = {}
    for r in raw:
        meta = r["meta"]
        if meta.get("type") == "question":
            chunk_id = meta.get("parent_id")
        else:
            chunk_id = r["id"]
        if not chunk_id or chunk_id in seen:
            continue
        seen.add(chunk_id)
        ordered.append(chunk_id)
        dense_score[chunk_id] = r["score"]
    return ordered, dense_score


def _bm25_chunk_ranking(query: str, subject: Optional[str]) -> tuple[list[str], dict]:
    results = get_bm25().query(query, top_k=settings.BM25_TOP_K * 2)
    ordered: list[str] = []
    bm25_score: dict[str, float] = {}
    for r in results:
        if subject and r["meta"].get("subject") != subject:
            continue
        ordered.append(r["id"])
        bm25_score[r["id"]] = r["score"]
        if len(ordered) >= settings.BM25_TOP_K:
            break
    return ordered, bm25_score


def _tokset(text: str) -> set:
    return set(text.lower().split())


def _dedup_candidates(candidates: list[dict], threshold: float) -> list[dict]:
    """Entfernt Near-Duplicate-Chunks (Token-Jaccard) – gegen doppelte Infos.

    Behält den jeweils höher platzierten Kandidaten; günstig, da nur über die
    ~20 fusionierten Kandidaten (nicht den ganzen Index)."""
    kept: list[dict] = []
    kept_sets: list[set] = []
    for c in candidates:
        ts = _tokset(c["document"])
        if not ts:
            continue
        dup = False
        for ks in kept_sets:
            inter = len(ts & ks)
            union = len(ts | ks) or 1
            if inter / union >= threshold:
                dup = True
                break
        if not dup:
            kept.append(c)
            kept_sets.append(ts)
    return kept


def _rrf(rank_lists: list[tuple[list[str], float]], k: int) -> dict[str, float]:
    """Reciprocal Rank Fusion mit optionaler Gewichtung pro Liste."""
    fused: dict[str, float] = defaultdict(float)
    for ids, weight in rank_lists:
        for rank, cid in enumerate(ids):
            fused[cid] += weight * (1.0 / (k + rank + 1))
    return fused


def retrieve(query: str, subject: Optional[str] = None,
             final_top_k: Optional[int] = None,
             dedup: Optional[bool] = None) -> list[dict]:
    """Führt die vollständige Hybrid-Retrieval-Pipeline aus.

    final_top_k überschreibt die Anzahl finaler Treffer (z. B. für die Evaluation,
    die Hit@k für größere k messen muss).
    dedup überschreibt den Near-Duplicate-Filter (in der Evaluation aus, um die
    reine Retrieval-Qualität auf den exakten Gold-Chunk zu messen).
    """
    embedder = get_embedder()
    store = get_vectorstore()

    where = {"subject": subject} if subject else None
    query_emb = embedder.embed_query(query)

    dense_ids, dense_score = _dense_chunk_ranking(query_emb, where)
    bm25_ids, bm25_score = _bm25_chunk_ranking(query, subject)

    fused = _rrf(
        [(dense_ids, settings.DENSE_WEIGHT), (bm25_ids, settings.BM25_WEIGHT)],
        settings.RRF_K,
    )
    if not fused:
        return []

    top_ids = sorted(fused, key=lambda c: fused[c], reverse=True)[: settings.FUSION_TOP_K]

    # Chunk-Dokumente auflösen
    docs = store.get_by_ids(top_ids)
    candidates: list[dict] = []
    for cid in top_ids:
        d = docs.get(cid)
        if not d:
            continue
        candidates.append({
            "id": cid,
            "document": d["document"],
            "meta": d["meta"],
            "fusion_score": fused[cid],
            "dense_score": dense_score.get(cid),
            "bm25_score": bm25_score.get(cid),
            "retrievers": ",".join(
                s for s, present in (("dense", cid in dense_score), ("bm25", cid in bm25_score)) if present
            ),
        })

    # Near-Duplicate-Kandidaten entfernen (keine doppelten Informationen)
    use_dedup = settings.RETRIEVAL_DEDUP if dedup is None else dedup
    if use_dedup:
        candidates = _dedup_candidates(candidates, settings.RETRIEVAL_DEDUP_JACCARD)

    # Finaler Rerank
    reranked = get_reranker().rerank(
        query, candidates, top_k=final_top_k or settings.FINAL_TOP_K
    )
    return reranked
