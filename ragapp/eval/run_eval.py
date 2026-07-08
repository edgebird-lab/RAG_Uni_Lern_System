"""
Evaluations-Runner (Trefferquote messen & protokollieren)
=========================================================

Führt das Gold-Set gegen die echte Retrieval-Pipeline aus und berechnet
Hit@k / MRR, die zentrale Kennzahl, um das System zu bewerten und **nachzu-
justieren**. Ergebnisse werden gespeichert:

    data/eval/eval_<zeitstempel>.json   : vollständiger Report + Konfiguration
    data/eval/per_query_<zeitstempel>.csv : jede Testfrage einzeln (für Fehlersuche)
    data/eval/history.jsonl              : Verlaufskurve für das Dashboard

So lässt sich nach jeder Parameteränderung (Chunk-Größe, Reranker an/aus, k …)
messen, ob sich die Trefferquote verbessert hat.
"""
from __future__ import annotations

import csv
import json
import time
from dataclasses import asdict

from ragapp.config import settings, EVAL_DIR
from ragapp.eval.gold_set import load_gold_set
from ragapp.eval.metrics import aggregate, reciprocal_rank, hit_at_k
from ragapp.retrieval.hybrid import retrieve

HISTORY_FILE = EVAL_DIR / "history.jsonl"


def run_retrieval_eval(progress=None) -> dict:
    gold = load_gold_set()
    if not gold:
        return {"status": "no_gold", "message": "Kein Gold-Set vorhanden. Zuerst erzeugen."}

    k_values = [int(k) for k in settings.EVAL_K_VALUES] if settings.EVAL_K_VALUES else []
    if not k_values:
        k_values = [1, 3, 5, 10]
    kmax = max(k_values)
    per_query: list[dict] = []
    rows: list[dict] = []

    t0 = time.time()
    for i, g in enumerate(gold, 1):
        if progress:
            progress(f"Evaluiere {i}/{len(gold)}")
        # dedup=False: reine Retrieval-Qualität auf den exakten Gold-Chunk messen
        # (der Produktivbetrieb nutzt Dedup gegen doppelte Infos in der Antwort).
        candidates = retrieve(g["question"], subject=None, final_top_k=kmax, dedup=False)
        retrieved_ids = [c["id"] for c in candidates]
        found = g["chunk_id"] in retrieved_ids
        rank = retrieved_ids.index(g["chunk_id"]) + 1 if found else None
        per_query.append({
            "retrieved_ids": retrieved_ids,
            "gold_id": g["chunk_id"],
            "subject": g.get("subject"),
        })
        rows.append({
            "question": g["question"],
            "subject": g.get("subject"),
            "gold_file": g.get("filename"),
            "gold_location": g.get("location"),
            "found": found,
            "rank": rank if rank else "",
            "top1_file": candidates[0]["meta"].get("filename") if candidates else "",
        })

    summary = aggregate(per_query, k_values)
    elapsed = round(time.time() - t0, 1)

    report = {
        "timestamp": time.time(),
        "elapsed_seconds": elapsed,
        "num_questions": len(gold),
        "metrics": summary,
        "config": {
            "EMBED_MODEL": settings.EMBED_MODEL,
            "CHUNK_SIZE": settings.CHUNK_SIZE,
            "CHUNK_OVERLAP": settings.CHUNK_OVERLAP,
            "DENSE_TOP_K": settings.DENSE_TOP_K,
            "BM25_TOP_K": settings.BM25_TOP_K,
            "FUSION_TOP_K": settings.FUSION_TOP_K,
            "USE_RERANKER": settings.USE_RERANKER,
            "RERANKER_MODEL": settings.RERANKER_MODEL,
            "ENABLE_QUESTION_INDEXING": settings.ENABLE_QUESTION_INDEXING,
            "NUM_INDEX_QUESTIONS": settings.NUM_INDEX_QUESTIONS,
        },
    }

    ts = time.strftime("%Y%m%d_%H%M%S")
    (EVAL_DIR / f"eval_{ts}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), "utf-8"
    )
    with open(EVAL_DIR / f"per_query_{ts}.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    # Verlaufseintrag (kompakt)
    hist = {
        "timestamp": report["timestamp"],
        "num_questions": report["num_questions"],
        "hit@k": summary["hit@k"],
        "mrr": summary["mrr"],
        "config": report["config"],
    }
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(hist, ensure_ascii=False) + "\n")

    report["status"] = "ok"
    report["csv"] = str(EVAL_DIR / f"per_query_{ts}.csv")
    return report


def load_history() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    out = []
    with open(HISTORY_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    return out
