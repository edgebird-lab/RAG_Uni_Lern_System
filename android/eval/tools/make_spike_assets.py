#!/usr/bin/env python3
"""Erzeugt die Prompts fuer den Geraete-Spike (Phase 1) aus dem Goldset.

Je Frage werden 4 Kontext-Abschnitte gebaut: die Beleg-Abschnitte (Gold) plus Ablenker
aus demselben Dokument, gemischt. Das entspricht einem Abruf mit Top-4 und misst
Prefill-Last und Antwortqualitaet mit ORAKEL-Kontext (ohne Retrieval-Fehler).

Ausgabe: app/src/debug/assets/spike/prompts.json
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import generate_goldset as gg  # noqa: E402

ROOT = HERE.parent
OUT = ROOT.parent / "app" / "src" / "debug" / "assets" / "spike" / "prompts.json"
N = {"direkt": 8, "umformuliert": 4, "mehrstufig": 3, "unbeantwortbar": 6}
K = 4


def main() -> None:
    rnd = random.Random(5)
    rows = [json.loads(l) for l in (ROOT / "goldset" / "goldset.jsonl").read_text(encoding="utf-8").splitlines()]
    cache: dict[str, list[tuple[str, str]]] = {}
    items = []
    for typ, n in N.items():
        pool = [r for r in rows if r["typ"] == typ]
        rnd.shuffle(pool)
        seen_docs: set[str] = set()
        picked = []
        for r in pool:  # moeglichst verschiedene Dokumente
            if r["dokument"] not in seen_docs or len(picked) >= n // 2 + 2:
                picked.append(r); seen_docs.add(r["dokument"])
            if len(picked) == n:
                break
        for r in picked:
            doc = r["dokument"].removesuffix(".md")
            secs = cache.setdefault(doc, gg.sections(doc))
            gold = []
            for b in r["belege"]:
                q = gg.norm(b["zitat"].strip(" .…\"“„"))
                hit = next((s for s in secs if q in gg.norm(s[1])), None)
                if hit:
                    gold.append(hit)
            if len(gold) != len(r["belege"]):
                continue
            others = [s for s in secs if s not in gold]
            rnd.shuffle(others)
            ctx = gold + others[: K - len(gold)]
            rnd.shuffle(ctx)
            items.append({
                "id": r["id"], "typ": typ, "frage": r["frage"], "erwartet": r["erwartete_antwort"],
                "gold": [ctx.index(g) + 1 for g in gold],
                "kontext": [{"quelle": f"{doc}: {h}", "text": t[:1400]} for h, t in ctx],
            })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    chars = [sum(len(c["text"]) for c in i["kontext"]) for i in items]
    print(len(items), "Prompts, Kontext-Zeichen min/mittel/max:", min(chars), sum(chars) // len(chars), max(chars))


if __name__ == "__main__":
    main()
