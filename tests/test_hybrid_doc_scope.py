"""Dokument-Scoping im Hybrid-Retrieval (``ragapp.retrieval.hybrid``):
``_build_where`` (Chroma-Filter) und ``_bm25_chunk_ranking`` (BM25-Filter).

Sicherheitsrelevant: ein an eine Mindmap gebundener Chat darf NUR in deren
eigenen Quellen suchen, nie in anderen Fächern/Dokumenten der Bibliothek -
siehe ragapp/ui/pages/14_🧠_Mindmap.py.

Isoliert geladen, weil ein Vollimport von ``ragapp.retrieval.hybrid`` über
Embeddings/Chroma/BM25/Reranker schwere Abhängigkeiten (torch, chromadb)
zieht.
"""
import types

import pytest


@pytest.fixture
def build_where(load_functions, ragapp_dir):
    funcs = load_functions(
        ragapp_dir / "retrieval" / "hybrid.py", ["_build_where"], {"Optional": None})
    return funcs["_build_where"]


def test_build_where_nur_subject(build_where):
    assert build_where("DSA", None) == {"subject": "DSA"}


def test_build_where_nur_doc_ids(build_where):
    assert build_where(None, ["d1", "d2"]) == {"doc_id": {"$in": ["d1", "d2"]}}


def test_build_where_subject_und_doc_ids_kombiniert(build_where):
    out = build_where("DSA", ["d1", "d2"])
    assert out == {"$and": [{"subject": "DSA"}, {"doc_id": {"$in": ["d1", "d2"]}}]}


def test_build_where_ohne_filter_ist_none(build_where):
    assert build_where(None, None) is None
    assert build_where("", []) is None


def test_build_where_leere_doc_ids_liste_wirkt_wie_kein_filter(build_where):
    # Eine leere Liste darf NICHT als "$in": [] durchgereicht werden (das waere
    # ein Filter, der NICHTS matcht, statt "kein Dokument-Filter") - sicherer
    # ist "gar kein doc_id-Filter", wenn die Liste leer ist.
    assert build_where("DSA", []) == {"subject": "DSA"}


def test_build_where_doc_ids_als_set_wird_zu_liste(build_where):
    out = build_where(None, {"d1", "d2"})
    assert isinstance(out["doc_id"]["$in"], list)
    assert set(out["doc_id"]["$in"]) == {"d1", "d2"}


# ---------------------------------------------------------------------------
# _bm25_chunk_ranking: BM25 hat keine index-interne Filterung, daher wird der
# Ergebnis-Pool nachtraeglich in Python auf subject/doc_ids gefiltert.
# ---------------------------------------------------------------------------

class _FakeBM25:
    def __init__(self, rows):
        self._rows = rows

    def query(self, text, top_k):
        return self._rows[:top_k]


def _fake_settings(**overrides):
    base = dict(BM25_TOP_K=10)
    base.update(overrides)
    return types.SimpleNamespace(**base)


@pytest.fixture
def bm25_ranking(load_functions, ragapp_dir):
    def _make(rows):
        funcs = load_functions(
            ragapp_dir / "retrieval" / "hybrid.py", ["_bm25_chunk_ranking"],
            {"settings": _fake_settings(), "get_bm25": lambda: _FakeBM25(rows),
             "Optional": None},
        )
        return funcs["_bm25_chunk_ranking"]
    return _make


def _row(rid, subject, doc_id, score=1.0):
    return {"id": rid, "document": "x", "meta": {"subject": subject, "doc_id": doc_id},
            "score": score}


def test_bm25_chunk_ranking_filtert_auf_doc_ids(bm25_ranking):
    rows = [_row("c1", "DSA", "docA"), _row("c2", "DSA", "docB"),
            _row("c3", "DSA", "docA")]
    f = bm25_ranking(rows)
    ordered, scores = f("frage", subject=None, doc_ids=["docA"])
    assert ordered == ["c1", "c3"]
    assert set(scores.keys()) == {"c1", "c3"}


def test_bm25_chunk_ranking_kombiniert_subject_und_doc_ids(bm25_ranking):
    rows = [_row("c1", "DSA", "docA"), _row("c2", "Analysis", "docA"),
            _row("c3", "DSA", "docB")]
    f = bm25_ranking(rows)
    ordered, _ = f("frage", subject="DSA", doc_ids=["docA"])
    assert ordered == ["c1"]


def test_bm25_chunk_ranking_ohne_doc_ids_verhaelt_sich_wie_vorher(bm25_ranking):
    rows = [_row("c1", "DSA", "docA"), _row("c2", "DSA", "docB")]
    f = bm25_ranking(rows)
    ordered, _ = f("frage", subject="DSA", doc_ids=None)
    assert ordered == ["c1", "c2"]


def test_bm25_chunk_ranking_leere_doc_ids_liste_filtert_nicht(bm25_ranking):
    rows = [_row("c1", "DSA", "docA"), _row("c2", "DSA", "docB")]
    f = bm25_ranking(rows)
    ordered, _ = f("frage", subject=None, doc_ids=[])
    assert ordered == ["c1", "c2"]
