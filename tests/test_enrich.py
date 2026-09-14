"""Fragen-Anreicherung: Mini-Chunks aus Header-Split zusammenziehen."""
from __future__ import annotations

from ragapp.ingestion.enrich import coalesce_short_chunks


def _ch(cid: str, text: str, doc_id: str = "d") -> dict:
    return {"id": cid, "document": text, "meta": {"doc_id": doc_id, "filename": "a.md"}}


def test_coalesce_zieht_header_mini_chunks_zusammen():
    chunks = [
        _ch("d::c0", "A" * 90),
        _ch("d::c1", "B" * 163),
        _ch("d::c2", "C" * 192),
    ]
    out = coalesce_short_chunks(chunks, min_chars=120)
    assert len(out) == 2
    assert out[0]["id"] == "d::c0"
    assert ("A" * 90) in out[0]["document"]
    assert ("B" * 163) in out[0]["document"]
    assert out[1]["id"] == "d::c2"
    assert len(out[1]["document"]) == 192


def test_coalesce_ueberschreitet_keine_dokumentgrenze():
    chunks = [
        _ch("a::c0", "A" * 80, "a"),
        _ch("b::c0", "B" * 80, "b"),
    ]
    out = coalesce_short_chunks(chunks, min_chars=120)
    assert out == []


def test_coalesce_behaelt_schon_lange_chunks():
    chunks = [_ch("d::c0", "X" * 200)]
    out = coalesce_short_chunks(chunks, min_chars=120)
    assert len(out) == 1
    assert out[0]["document"] == "X" * 200
