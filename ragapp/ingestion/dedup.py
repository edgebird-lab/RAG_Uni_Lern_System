"""
Deduplizierung
==============

Drei Ebenen verhindern doppelte Dokumente und doppelte Informationen:

1. **Dokument-Ebene (exakt)**: SHA-256 über den normalisierten Volltext. Gleiche
   Inhalte (auch unter anderem Dateinamen) werden erkannt und übersprungen.
2. **Chunk-Ebene (exakt)**: SHA-256 je Chunk-Text; global über das Manifest.
   Wiederkehrende identische Passagen (Kopfzeilen, Formelsammlungen) landen nur
   einmal im Index.
3. **Chunk-Ebene (near-duplicate)**: Innerhalb eines Dokuments werden Chunks mit
   sehr hoher Embedding-Ähnlichkeit (Kosinus > Schwellwert) zusammengeführt/
   verworfen. Fängt fast-gleiche Formulierungen ab, die kein exakter Hash trifft.
"""
from __future__ import annotations

import hashlib

from ragapp.config import settings


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def doc_id_for(relative_path: str) -> str:
    """Stabile Dokument-ID aus dem (relativen) Pfad."""
    return hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:16]


def chunk_hash(text: str) -> str:
    # Whitespace-robust: Vergleich auf zusammengefasstem Text
    normalized = " ".join(text.lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def filter_near_duplicates(
    embeddings: list[list[float]], threshold: float | None = None
) -> list[int]:
    """
    Greedy Near-Duplicate-Filter über (L2-normalisierte) Embeddings.
    Gibt die Indizes der zu BEHALTENDEN Chunks zurück.
    """
    threshold = settings.DEDUP_NEAR_DUPLICATE_THRESHOLD if threshold is None else threshold
    kept: list[int] = []
    kept_vecs: list[list[float]] = []
    for i, vec in enumerate(embeddings):
        is_dup = False
        for kv in kept_vecs:
            # Skalarprodukt = Kosinus, da normalisiert
            sim = sum(a * b for a, b in zip(vec, kv))
            if sim >= threshold:
                is_dup = True
                break
        if not is_dup:
            kept.append(i)
            kept_vecs.append(vec)
    return kept
