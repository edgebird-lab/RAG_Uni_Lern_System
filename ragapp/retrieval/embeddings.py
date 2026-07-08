"""
Embeddings über Ollama (bge-m3)
===============================

bge-m3 ist ein multilinguales Embedding-Modell (u. a. sehr gut für Deutsch),
1024-dimensional. Wir nutzen es lokal über Ollama. Alle Vektoren werden
L2-normalisiert, sodass Skalarprodukt = Kosinus-Ähnlichkeit gilt (nützlich für
Near-Duplicate-Erkennung und konsistente Chroma-Distanzen).
"""
from __future__ import annotations

import math
import time
from typing import Sequence

import ollama

from ragapp.config import settings


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


class Embedder:
    """Dünner, robuster Wrapper um Ollamas Embedding-API."""

    def __init__(self, model: str | None = None):
        self.model = model or settings.EMBED_MODEL
        # Embeddings können auf einem separaten Server laufen (z. B. iGPU/IPEX-LLM)
        host = settings.EMBED_OLLAMA_URL or settings.OLLAMA_BASE_URL
        self._client = ollama.Client(host=host, timeout=settings.LLM_TIMEOUT)

    # ------------------------------------------------------------------ #
    def _embed_batch(self, texts: list[str], retries: int = 3) -> list[list[float]]:
        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                resp = self._client.embed(model=self.model, input=texts)
                embs = resp["embeddings"]
                return [_l2_normalize(list(e)) for e in embs]
            except Exception as exc:  # pragma: no cover - Netzwerk/Ollama
                last_err = exc
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"Embedding fehlgeschlagen ({self.model}): {last_err}")

    def embed_texts(self, texts: Sequence[str], batch_size: int | None = None) -> list[list[float]]:
        bs = batch_size or settings.EMBED_BATCH_SIZE
        texts = [t if t.strip() else " " for t in texts]
        batches = [list(texts[i:i + bs]) for i in range(0, len(texts), bs)]
        workers = max(1, settings.EMBED_CONCURRENCY)

        # Sequenziell, wenn Parallelität aus ist oder nur ein Batch anfällt
        if workers == 1 or len(batches) <= 1:
            out: list[list[float]] = []
            for b in batches:
                out.extend(self._embed_batch(b))
            return out

        # Parallele Embedding-Anfragen (nutzt mehr CPU-Kerne; Reihenfolge bleibt erhalten)
        from concurrent.futures import ThreadPoolExecutor
        out = []
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for res in ex.map(self._embed_batch, batches):
                out.extend(res)
        return out

    def embed_query(self, text: str) -> list[float]:
        return self._embed_batch([text or " "])[0]


# Singleton für Wiederverwendung (Modell muss nicht mehrfach initialisiert werden)
_default_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _default_embedder
    if _default_embedder is None:
        _default_embedder = Embedder()
    return _default_embedder
