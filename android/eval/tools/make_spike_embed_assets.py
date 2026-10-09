#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Erzeugt Korpus + Fragen fuer den Embedding-Spike (Retrieval-Qualitaet auf dem Geraet).

corpus.json: alle Abschnitte des Korpus (id, titel, text)
gold.json:   beantwortbare Goldset-Fragen mit den Indizes der Beleg-Abschnitte
Zusaetzlich: bge-m3-Baseline (PC) mit denselben Daten -> eval/spike/baseline_bge-m3.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import generate_goldset as gg  # noqa: E402
import pruefen as pf  # noqa: E402

ROOT = HERE.parent
OUT = ROOT.parent / "app" / "src" / "debug" / "assets" / "spike"


def main() -> None:
    ps = pf.passages()
    rows = [json.loads(l) for l in (ROOT / "goldset" / "goldset.jsonl").read_text(encoding="utf-8").splitlines()]
    gold = []
    for r in rows:
        if r["typ"] == "unbeantwortbar":
            continue
        idx = [pf.find_source(ps, r["dokument"], b["zitat"]) for b in r["belege"]]
        if any(i is None for i in idx):
            continue
        gold.append({"id": r["id"], "typ": r["typ"], "frage": r["frage"], "belege": idx})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "corpus.json").write_text(json.dumps(
        [{"id": i, "titel": f"{p['doc']}: {p['head']}"[:120], "text": p["text"][:1400]} for i, p in enumerate(ps)],
        ensure_ascii=False), encoding="utf-8")
    (OUT / "gold.json").write_text(json.dumps(gold, ensure_ascii=False), encoding="utf-8")
    print(len(ps), "Abschnitte,", len(gold), "Fragen")

    # PC-Baseline mit bge-m3 (Cache aus pruefen.py)
    emb = pf.embed_all(ps)
    res = {"model": "bge-m3 (PC, Ollama)", "n_passages": len(ps), "per_question": []}
    for g in gold:
        qv = np.array(pf.post("/api/embed", {"model": "bge-m3", "input": [g["frage"]]})["embeddings"][0], dtype=np.float32)
        qv /= np.linalg.norm(qv)
        order = list(np.argsort(-(emb @ qv)))
        ranks = [order.index(b) + 1 for b in g["belege"]]
        res["per_question"].append({"id": g["id"], "typ": g["typ"], "ranks": ranks})
    base = ROOT / "spike" / "baseline_bge-m3.json"
    base.write_text(json.dumps(res, indent=1), encoding="utf-8")
    for k in (1, 4, 10):
        hits = [all(r <= k for r in q["ranks"]) for q in res["per_question"]]
        print(f"bge-m3 Treffer@{k}: {sum(hits)}/{len(hits)} = {sum(hits) / len(hits):.2f}")


if __name__ == "__main__":
    main()
