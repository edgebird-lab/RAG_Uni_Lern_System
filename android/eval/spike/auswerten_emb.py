#!/usr/bin/env python3
"""Treffer@k fuer Embedding-Laeufe (emb-*.json) gegen die PC-Baseline (bge-m3)."""
import json, sys
from pathlib import Path

def stats(per_q):
    out = {}
    for k in (1, 4, 10):
        hits = [all(r <= k for r in q["ranks"]) for q in per_q]
        out[k] = sum(hits) / len(hits)
    mrr = sum(1 / min(q["ranks"]) for q in per_q) / len(per_q)
    return out, mrr

base = json.load(open(Path(__file__).parent / "baseline_bge-m3.json"))
s, m = stats(base["per_question"])
print(f"{'bge-m3 (PC)':28} n={base['n_passages']:5} @1 {s[1]:.2f} @4 {s[4]:.2f} @10 {s[10]:.2f} MRR {m:.2f}")
for p in sorted(Path(__file__).parent.glob("emb-*.json")):
    d = json.load(open(p))
    if d.get("status") != "ok" or "per_question" not in d or not d["per_question"]:
        continue
    s, m = stats(d["per_question"])
    print(f"{d['tag']:28} n={d['n_passages']:5} @1 {s[1]:.2f} @4 {s[4]:.2f} @10 {s[10]:.2f} MRR {m:.2f} | {d['docs_per_s']:.1f} Abschn./s, Anfrage {d['query_ms_avg']:.0f} ms, Laden {d['load_ms']/1000:.0f}s")
