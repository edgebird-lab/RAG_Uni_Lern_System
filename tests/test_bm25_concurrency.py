"""BM25-Snapshots werden atomar und wieder ladbar geschrieben."""
from __future__ import annotations

from ragapp.retrieval import bm25_index, vectorstore


def test_bm25_rebuild_schreibt_atomaren_snapshot(tmp_path, monkeypatch):
    target = tmp_path / "bm25.pkl"
    monkeypatch.setattr(bm25_index, "_INDEX_FILE", target)
    monkeypatch.setattr(
        bm25_index, "_REBUILD_LOCK_FILE", tmp_path / ".rebuild.lock")
    monkeypatch.setattr(
        vectorstore, "get_vectorstore",
        lambda: type("_Store", (), {"get_all_chunks": lambda self: [{
            "id": "c1", "document": "Deckungsbeitrag berechnen",
            "meta": {"doc_id": "d1"},
        }]})())
    rebuilt = bm25_index.rebuild_bm25_from_store()
    assert target.is_file()
    assert not target.with_suffix(".pkl.tmp").exists()
    loaded = bm25_index.BM25Index()
    assert loaded.load() is True
    assert loaded.ids == rebuilt.ids == ["c1"]
