#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Erzeugt Referenz-Chunks mit dem PC-Chunker (ragapp) fuer den Paritaetstest des Kotlin-Chunkers.
Aufruf (aus dem Repo-Root, mit .venv): .venv/bin/python android/eval/tools/make_chunker_fixture.py"""
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ragapp.ingestion import chunker as pc  # noqa: E402
from ragapp.ingestion.loaders import Block, LoadedDoc  # noqa: E402

pc.settings = types.SimpleNamespace(CHUNK_SIZE=1000, CHUNK_OVERLAP=150, MIN_CHUNK_CHARS=120, RESPECT_MARKDOWN_HEADERS=True)
K = ROOT / "android" / "eval" / "korpus"
OUT = ROOT / "android" / "core" / "src" / "test" / "resources" / "chunker"
OUT.mkdir(parents=True, exist_ok=True)

cases = []
# Markdown (Wikipedia-Artikel, Gesetz-Ausschnitt)
for name in ["wiki_quicksort.md", "wiki_zelle_biologie.md"]:
    text = (K / name).read_text(encoding="utf-8")
    cases.append({"name": name, "markdown": True, "blocks": [], "text": text,
                  "chunks": [(c.text, c.meta["location"]) for c in pc.chunk_document(LoadedDoc(text=text, blocks=[], filetype="md", is_markdown=True), {})]})
# Seitenweise (simulierte PDF-Seiten aus dem Grundgesetz-Text, ohne Markdown-Struktur)
gg = (K / "gg.md").read_text(encoding="utf-8")
pages = [gg[i:i + 3500] for i in range(0, 35000, 3500)]
blocks = [Block(text=p, page=n + 1) for n, p in enumerate(pages)]
cases.append({"name": "gg-seiten", "markdown": False, "text": "", "blocks": [{"text": b.text, "page": b.page} for b in blocks],
              "chunks": [(c.text, c.meta["location"]) for c in pc.chunk_document(LoadedDoc(text="", blocks=blocks, filetype="pdf", is_markdown=False), {})]})
# Tabelle
table = "\n".join(f"| Posten {i} | {i * 17} EUR | Bemerkung zu {i} |" for i in range(1, 80))
tb = [Block(text=table, page=1)]
cases.append({"name": "tabelle", "markdown": False, "text": "", "blocks": [{"text": table, "page": 1}],
              "chunks": [(c.text, c.meta["location"]) for c in pc.chunk_document(LoadedDoc(text="", blocks=tb, filetype="pdf"), {})]})
(OUT / "fixture.json").write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")
print({c["name"]: len(c["chunks"]) for c in cases})
