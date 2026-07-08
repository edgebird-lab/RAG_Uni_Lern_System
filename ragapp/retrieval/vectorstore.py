"""
Vektordatenbank (ChromaDB, persistent)
======================================

Speichert zwei Arten von Einträgen in *einer* Collection, unterschieden über
das Metadatenfeld ``type``:

    type = "chunk"     -> der eigentliche Inhaltsabschnitt
    type = "question"  -> eine generierte Frage; verweist über ``parent_id``
                          auf ihren Chunk

Bei der Suche werden Frage-Treffer auf ihren Eltern-Chunk zurückgeführt, sodass
dem LLM immer der volle Kontext (der Chunk) vorliegt.

Wir übergeben eigene, L2-normalisierte Embeddings; die Collection nutzt
Kosinus-Distanz.
"""
from __future__ import annotations

from typing import Any, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from ragapp.config import settings, CHROMA_DIR

_CHROMA_META_TYPES = (str, int, float, bool)


def _sanitize_meta(meta: dict) -> dict:
    """Chroma erlaubt nur str/int/float/bool, None/Listen werden konvertiert."""
    clean: dict[str, Any] = {}
    for k, v in meta.items():
        if v is None:
            continue
        if isinstance(v, _CHROMA_META_TYPES):
            clean[k] = v
        else:
            clean[k] = str(v)
    return clean


class VectorStore:
    def __init__(self):
        self._client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
        )
        self._col = self._client.get_or_create_collection(
            name=settings.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------ #
    def add(self, ids: list[str], embeddings: list[list[float]],
            documents: list[str], metadatas: list[dict]) -> None:
        if not ids:
            return
        self._col.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=[_sanitize_meta(m) for m in metadatas],
        )

    def query(self, embedding: list[float], n_results: int,
              where: Optional[dict] = None) -> list[dict]:
        res = self._col.query(
            query_embeddings=[embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        out: list[dict] = []
        if not res["ids"] or not res["ids"][0]:
            return out
        for i, _id in enumerate(res["ids"][0]):
            out.append({
                "id": _id,
                "document": res["documents"][0][i],
                "meta": res["metadatas"][0][i],
                "distance": res["distances"][0][i],
                "score": 1.0 - res["distances"][0][i],  # Kosinus-Ähnlichkeit
            })
        return out

    def get_by_ids(self, ids: list[str]) -> dict[str, dict]:
        if not ids:
            return {}
        res = self._col.get(ids=ids, include=["documents", "metadatas"])
        mapping: dict[str, dict] = {}
        for i, _id in enumerate(res["ids"]):
            mapping[_id] = {
                "id": _id,
                "document": res["documents"][i],
                "meta": res["metadatas"][i],
            }
        return mapping

    def get_all_chunks(self) -> list[dict]:
        """Alle Chunk-Einträge (für BM25-Indexaufbau)."""
        res = self._col.get(where={"type": "chunk"}, include=["documents", "metadatas"])
        out = []
        for i, _id in enumerate(res["ids"]):
            out.append({
                "id": _id,
                "document": res["documents"][i],
                "meta": res["metadatas"][i],
            })
        return out

    def delete_by_doc(self, doc_id: str) -> None:
        self._col.delete(where={"doc_id": doc_id})

    def delete_questions_by_doc(self, doc_id: str) -> None:
        """Loescht nur die generierten Fragen eines Dokuments (Chunks bleiben)."""
        self._col.delete(where={"$and": [{"doc_id": doc_id}, {"type": "question"}]})

    def delete_questions_by_subject(self, subject: str) -> None:
        self._col.delete(where={"$and": [{"subject": subject}, {"type": "question"}]})

    def delete_all_questions(self) -> None:
        self._col.delete(where={"type": "question"})

    def count(self) -> int:
        return self._col.count()

    def reset(self) -> None:
        """Löscht die komplette Collection (Neuaufbau)."""
        self._client.delete_collection(settings.COLLECTION_NAME)
        self._col = self._client.get_or_create_collection(
            name=settings.COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
        )


_default_store: VectorStore | None = None


def get_vectorstore() -> VectorStore:
    global _default_store
    if _default_store is None:
        _default_store = VectorStore()
    return _default_store
