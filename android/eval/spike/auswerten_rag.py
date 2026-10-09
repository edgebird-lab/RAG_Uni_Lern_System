#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Wertet RAG-Laeufe (rag-*.json, SpikeRagEvalActivity) aus.

Beantwortbare Fragen:  Quellen-Treffer (alle Belege unter den 4 Quellen), falsche Verweigerung,
                       Antwort-Ueberlappung mit der erwarteten Antwort (Orientierung, kein Ersatz fuers Lesen),
                       Verweis auf eine Gold-Quelle.
Unbeantwortbare:       Verweigerungsquote.
"""
import json, re, statistics as st, sys
from pathlib import Path

def words(s): return {w for w in re.findall(r"\w{4,}", s.lower())}

def main(p):
    d = json.load(open(p, encoding="utf-8"))
    rs = d["results"]
    ans = [r for r in rs if r["typ"] != "unbeantwortbar"]
    una = [r for r in rs if r["typ"] == "unbeantwortbar"]
    print(f"{d['tag']}: {len(rs)} Fragen ({len(ans)} beantwortbar, {len(una)} unbeantwortbar), {d.get('chunks')} Chunks, Laden {d.get('load_ms', 0)/1000:.0f}s")
    def src_hit(r): return all(h is not None for h in r["source_hits"])
    hit = [r for r in ans if src_hit(r)]
    miss = [r for r in ans if not src_hit(r)]
    refused_hit = [r for r in hit if r["not_found"]]
    ok = []
    for r in hit:
        if r["not_found"]: continue
        ew = words(r["erwartet"]); ok.append(len(ew & words(r["antwort"])) / max(1, len(ew)) >= 0.5)
    cites_gold = [any(c in [h for h in r["source_hits"] if h] for c in r["cited"]) for r in hit if not r["not_found"]]
    print(f"Quellen-Treffer (Beleg in den 4 Quellen): {len(hit)}/{len(ans)} = {len(hit)/len(ans):.2f}")
    print(f"  davon falsch verweigert: {len(refused_hit)}/{len(hit)}")
    print(f"  davon Antwort deckt erwartete Begriffe (>=50 %): {sum(ok)}/{len(ok)}")
    print(f"  davon Antwort nennt eine Gold-Quelle: {sum(cites_gold)}/{len(cites_gold)}")
    print(f"Beleg NICHT in den Quellen: {len(miss)}; davon verweigert: {sum(r['not_found'] for r in miss)}, geantwortet: {sum(not r['not_found'] for r in miss)}")
    print(f"Unbeantwortbar korrekt verweigert: {sum(r['not_found'] for r in una)}/{len(una)}")
    for typ in ("direkt", "umformuliert", "mehrstufig"):
        t = [r for r in ans if r["typ"] == typ]
        if t: print(f"  {typ}: Quellen-Treffer {sum(src_hit(r) for r in t)}/{len(t)}, verweigert {sum(r['not_found'] for r in t)}")
    gen = [r for r in rs if r["ttft_ms"] >= 0]
    print(f"Latenz: erstes Token Median {st.median(r['ttft_ms'] for r in gen)/1000:.1f}s, gesamt Median {st.median(r['total_ms'] for r in rs)/1000:.1f}s, max {max(r['total_ms'] for r in rs)/1000:.1f}s")

main(sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).parent / "rag-1.json"))
