#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Goldset mit Beleg-Zitaten als Debug-Asset fuer die Retrieval- und RAG-Auswertung auf dem Geraet."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT.parent / "app" / "src" / "debug" / "assets" / "spike" / "gold_quotes.json"
rows = [json.loads(l) for l in (ROOT / "goldset" / "goldset.jsonl").read_text(encoding="utf-8").splitlines()]
items = [{"id": r["id"], "typ": r["typ"], "frage": r["frage"], "erwartet": r["erwartete_antwort"],
          "dokument": r["dokument"].removesuffix(".md"),
          "belege": [{"dokument": r["dokument"].removesuffix(".md"), "zitat": b["zitat"]} for b in r["belege"]]}
         for r in rows]
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
print(len(items), "Fragen ->", OUT)
