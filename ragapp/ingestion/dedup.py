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

import numpy as np

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

    Vektorisiert: die Kosinus-Matrix wird EINMAL per Matmul berechnet (statt
    O(n^2) Python-Skalarprodukte über 1024-dim Vektoren); die Greedy-Auswahl
    liest daraus nur noch vorberechnete Werte. Ergebnis identisch, nur schneller.
    """
    threshold = settings.DEDUP_NEAR_DUPLICATE_THRESHOLD if threshold is None else threshold
    n = len(embeddings)
    if n == 0:
        return []

    arr = np.asarray(embeddings, dtype=np.float64)
    # normieren (idempotent bei bereits normalisierten Embeddings) -> Kosinus = Skalarprodukt
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    unit = arr / norms
    sim = unit @ unit.T                     # (n, n) Kosinus-Matrix, ein Matmul

    kept: list[int] = []
    for i in range(n):
        # Duplikat, sobald ein bereits BEHALTENER Chunk >= Schwellwert ähnelt.
        if kept and bool(np.any(sim[i, kept] >= threshold)):
            continue
        kept.append(i)
    return kept
