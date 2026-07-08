"""
BM25-Keyword-Index (mit deutscher Sprachverarbeitung)
=====================================================

Die semantische (dense) Suche findet sinngemäße Treffer, versagt aber manchmal
bei exakten Fachbegriffen, Abkürzungen, Formelnamen oder Zahlen. BM25 fängt
genau das ab. Beide zusammen (Hybrid) liefern die höchste Trefferquote.

Deutsch-spezifisch:
    * Tokenisierung unicode-bewusst (Umlaute/ß bleiben erhalten)
    * Entfernung deutscher Stoppwörter
    * Stemming mit Snowball (reduziert Flexion: "Kosten"/"Kostens"/"kostet")
"""
from __future__ import annotations

import pickle
import re
from pathlib import Path
from typing import Optional

from rank_bm25 import BM25Okapi

from ragapp.config import BM25_DIR

_INDEX_FILE = BM25_DIR / "bm25.pkl"

# kompakte, praxistaugliche deutsche Stoppwortliste
_STOPWORDS = {
    "der", "die", "das", "und", "oder", "aber", "wenn", "dann", "als", "auch",
    "an", "auf", "aus", "bei", "bis", "durch", "für", "gegen", "in", "mit",
    "nach", "über", "um", "unter", "vom", "von", "vor", "zu", "zum", "zur",
    "ein", "eine", "einer", "eines", "einem", "einen", "ist", "sind", "war",
    "waren", "sein", "wird", "werden", "wurde", "wurden", "hat", "haben",
    "hatte", "kann", "können", "muss", "müssen", "soll", "sollen", "wie",
    "was", "wer", "wo", "warum", "dass", "es", "sie", "er", "wir", "ihr",
    "man", "sich", "nicht", "kein", "keine", "nur", "so", "im", "am", "dem",
    "den", "des", "diese", "dieser", "dieses", "welche", "welcher",
}

try:
    import snowballstemmer

    _STEMMER = snowballstemmer.stemmer("german")
except Exception:  # pragma: no cover
    _STEMMER = None

_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ0-9]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    tokens = [t.lower() for t in _TOKEN_RE.findall(text)]
    tokens = [t for t in tokens if t not in _STOPWORDS and len(t) > 1]
    if _STEMMER is not None:
        tokens = _STEMMER.stemWords(tokens)
    return tokens


class BM25Index:
    def __init__(self):
        self.bm25: Optional[BM25Okapi] = None
        self.ids: list[str] = []
        self.documents: list[str] = []
        self.metas: list[dict] = []

    # ------------------------------------------------------------------ #
    def build(self, chunks: list[dict]) -> None:
        """chunks: Liste von {id, document, meta}."""
        self.ids = [c["id"] for c in chunks]
        self.documents = [c["document"] for c in chunks]
        self.metas = [c["meta"] for c in chunks]
        corpus = [tokenize(doc) for doc in self.documents]
        # BM25Okapi verträgt keine leeren Dokumente
        corpus = [toks if toks else ["_"] for toks in corpus]
        self.bm25 = BM25Okapi(corpus) if corpus else None
        self.save()

    def query(self, text: str, top_k: int) -> list[dict]:
        if self.bm25 is None or not self.ids:
            return []
        tokens = tokenize(text)
        if not tokens:
            return []
        scores = self.bm25.get_scores(tokens)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        out = []
        for i in ranked[:top_k]:
            if scores[i] <= 0:
                continue
            out.append({
                "id": self.ids[i],
                "document": self.documents[i],
                "meta": self.metas[i],
                "score": float(scores[i]),
            })
        return out

    # ------------------------------------------------------------------ #
    def save(self) -> None:
        with open(_INDEX_FILE, "wb") as f:
            pickle.dump(
                {"ids": self.ids, "documents": self.documents,
                 "metas": self.metas, "bm25": self.bm25}, f
            )

    def load(self) -> bool:
        if not _INDEX_FILE.exists():
            return False
        try:
            with open(_INDEX_FILE, "rb") as f:
                data = pickle.load(f)
            self.ids = data["ids"]
            self.documents = data["documents"]
            self.metas = data["metas"]
            self.bm25 = data["bm25"]
            return True
        except Exception:
            return False


_default_bm25: BM25Index | None = None


def get_bm25() -> BM25Index:
    global _default_bm25
    if _default_bm25 is None:
        _default_bm25 = BM25Index()
        _default_bm25.load()
    return _default_bm25


def rebuild_bm25_from_store() -> BM25Index:
    """Baut den BM25-Index aus allen Chunks der Vektordatenbank neu auf."""
    from ragapp.retrieval.vectorstore import get_vectorstore

    idx = BM25Index()
    idx.build(get_vectorstore().get_all_chunks())
    global _default_bm25
    _default_bm25 = idx
    return idx
