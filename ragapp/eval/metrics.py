"""
Retrieval-Metriken
==================

Für Single-Relevant-Retrieval (jede Testfrage hat genau eine korrekte Quelle):

    * **Hit@k / Recall@k**: Anteil der Fragen, bei denen die korrekte Quelle in
      den Top-k Treffern liegt. Das ist die zentrale "Trefferquote".
    * **MRR (Mean Reciprocal Rank)**: Belohnt hohe Platzierung der richtigen
      Quelle (1/Rang).
"""
from __future__ import annotations

from typing import Iterable


def reciprocal_rank(retrieved_ids: list[str], gold_id: str) -> float:
    for rank, cid in enumerate(retrieved_ids, 1):
        if cid == gold_id:
            return 1.0 / rank
    return 0.0


def hit_at_k(retrieved_ids: list[str], gold_id: str, k: int) -> bool:
    return gold_id in retrieved_ids[:k]


def aggregate(per_query: list[dict], k_values: Iterable[int]) -> dict:
    """per_query: Liste mit {'retrieved_ids', 'gold_id', 'subject'}."""
    n = len(per_query)
    if n == 0:
        return {"n": 0}
    summary: dict = {"n": n, "hit@k": {}, "mrr": 0.0}
    for k in k_values:
        hits = sum(1 for q in per_query if hit_at_k(q["retrieved_ids"], q["gold_id"], k))
        summary["hit@k"][str(k)] = round(hits / n, 4)
    summary["mrr"] = round(sum(reciprocal_rank(q["retrieved_ids"], q["gold_id"]) for q in per_query) / n, 4)

    # Aufschlüsselung nach Fach
    by_subject: dict[str, list[dict]] = {}
    for q in per_query:
        by_subject.setdefault(q.get("subject") or "?", []).append(q)
    summary["by_subject"] = {}
    kmax = max(k_values)
    for subj, items in by_subject.items():
        hits = sum(1 for q in items if hit_at_k(q["retrieved_ids"], q["gold_id"], kmax))
        summary["by_subject"][subj] = {
            "n": len(items),
            f"hit@{kmax}": round(hits / len(items), 4),
            "mrr": round(sum(reciprocal_rank(q["retrieved_ids"], q["gold_id"]) for q in items) / len(items), 4),
        }
    return summary
