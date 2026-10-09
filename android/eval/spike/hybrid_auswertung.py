#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Hybrid-Suche offline: Geraete-Vektoren (emb-dump-*.vec) + BM25 (Snowball, wie PC-App) mit RRF.
Aufruf: ../../../.venv/bin/python3 hybrid_auswertung.py emb-dump-768-raw"""
import json, re, sys
from pathlib import Path
import numpy as np
import snowballstemmer
from rank_bm25 import BM25Okapi

HERE = Path(__file__).resolve().parent
tag = sys.argv[1]
meta = json.load(open(HERE / f"{tag}.json"))
dim, ids, nq = meta["dim"], meta["id_list"], meta["n_queries"]
raw = np.frombuffer((HERE / f"{tag}.vec").read_bytes(), dtype="<f4").reshape(-1, dim)
D, Q = raw[: len(ids)], raw[len(ids):]
assert len(Q) == nq
corpus = json.load(open(HERE.parent.parent / "app/src/debug/assets/spike/corpus.json"))
gold = json.load(open(HERE.parent.parent / "app/src/debug/assets/spike/gold.json"))
texts = [corpus[i]["titel"] + " " + corpus[i]["text"] for i in ids]
pos = {pid: n for n, pid in enumerate(ids)}

STOP = set("""der die das den dem des ein eine einer eines einem einen und oder aber ist sind war waren sein wird werden wurde wurden
hat haben hatte kann können muss müssen soll sollen wie was wer wo warum dass es sie er wir ihr man sich nicht kein keine nur so im am
diese dieser dieses welche welcher welchen auf in an zu von mit für bei nach aus über unter wenn als auch""".split())
st = snowballstemmer.stemmer("german")
def tok(t):
    ts = [w.lower() for w in re.findall(r"[A-Za-zÀ-ÿ0-9]+", t)]
    return st.stemWords([w for w in ts if w not in STOP and len(w) > 1]) or ["_"]

bm = BM25Okapi([tok(t) for t in texts])

def ranks_of(scores):
    order = np.argsort(-scores)
    r = np.empty(len(order), dtype=int); r[order] = np.arange(1, len(order) + 1)
    return r

def rrf(rank_lists, weights, k=60):
    return sum(w / (k + r) for r, w in zip(rank_lists, weights))

def evaluate(name, fn):
    hits = {1: 0, 4: 0, 10: 0}; mrr = 0
    for qi, g in enumerate(gold):
        sc = fn(qi, g)
        r = ranks_of(sc)
        gr = [int(r[pos[b]]) for b in g["belege"]]
        for k in hits: hits[k] += all(x <= k for x in gr)
        mrr += 1 / min(gr)
    n = len(gold)
    print(f"{name:34} @1 {hits[1]/n:.2f} @4 {hits[4]/n:.2f} @10 {hits[10]/n:.2f} MRR {mrr/n:.2f}")

dense = lambda qi, g: D @ Q[qi]
bm25 = lambda qi, g: np.array(bm.get_scores(tok(g["frage"])))
evaluate("dense (Geraet, " + tag + ")", dense)
evaluate("BM25 (Snowball)", bm25)
for w in (1.0, 2.0, 0.5):
    evaluate(f"RRF dense:bm25 = {w}:1", lambda qi, g, w=w: rrf([ranks_of(dense(qi, g)), ranks_of(bm25(qi, g))], [w, 1.0]))
