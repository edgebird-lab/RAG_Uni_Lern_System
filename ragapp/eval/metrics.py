"""
Retrieval-Metriken
==================

Für Single-Relevant-Retrieval (jede Testfrage hat genau eine korrekte Quelle):

    * **Hit@k / Recall@k**: Anteil der Fragen, bei denen die korrekte Quelle in
      den Top-k Treffern liegt. Das ist die zentrale "Trefferquote".
    * **MRR (Mean Reciprocal Rank)**: Belohnt hohe Platzierung der richtigen
      Quelle (1/Rang).
"""
from __future__ import annotations

from typing import Iterable


def reciprocal_rank(retrieved_ids: list[str], gold_id: str) -> float:
    for rank, cid in enumerate(retrieved_ids, 1):
        if cid == gold_id:
            return 1.0 / rank
    return 0.0


def hit_at_k(retrieved_ids: list[str], gold_id: str, k: int) -> bool:
    return gold_id in retrieved_ids[:k]


def aggregate(per_query: list[dict], k_values: Iterable[int]) -> dict:
    """per_query: Liste mit {'retrieved_ids', 'gold_id', 'subject'}."""
    n = len(per_query)
    if n == 0:
        return {"n": 0}
    summary: dict = {"n": n, "hit@k": {}, "mrr": 0.0}
    for k in k_values:
        hits = sum(1 for q in per_query if hit_at_k(q["retrieved_ids"], q["gold_id"], k))
        summary["hit@k"][str(k)] = round(hits / n, 4)
    summary["mrr"] = round(sum(reciprocal_rank(q["retrieved_ids"], q["gold_id"]) for q in per_query) / n, 4)

    # Aufschlüsselung nach Fach
    by_subject: dict[str, list[dict]] = {}
    for q in per_query:
        by_subject.setdefault(q.get("subject") or "?", []).append(q)
    summary["by_subject"] = {}
    kmax = max(k_values)
    for subj, items in by_subject.items():
        hits = sum(1 for q in items if hit_at_k(q["retrieved_ids"], q["gold_id"], kmax))
        summary["by_subject"][subj] = {
            "n": len(items),
            f"hit@{kmax}": round(hits / len(items), 4),
            "mrr": round(sum(reciprocal_rank(q["retrieved_ids"], q["gold_id"]) for q in items) / len(items), 4),
        }
    return summary


# --------------------------------------------------------------------------- #
# Kalibrierungs-Metrik der KI-Benotung (RICHTUNG der Fehlkalibrierung)
# --------------------------------------------------------------------------- #
# Notenstufen der Benotung: 0 = nicht, 1 = halb, 2 = gewusst. Eine reine
# Trefferquote (exakt / ±1 Stufe) sagt NICHT, in welche RICHTUNG der Judge
# danebenliegt. Deshalb messen wir zusaetzlich den Vorzeichen-Bias =
# Mittelwert(Judge-Note - Referenz-Note):
#   > 0  -> Judge vergibt im Schnitt HOEHERE Noten  -> systematisch zu MILDE
#   < 0  -> Judge vergibt im Schnitt NIEDRIGERE Noten -> systematisch zu STRENG
# Ein zu milde kalibrierter Korrektor ist fuers Lernen gefaehrlich (Wissensluecken
# werden als "gewusst" abgehakt), daher wird die Richtung explizit ausgewiesen.

# Ab welchem |Bias| (in Notenstufen) die Fehlkalibrierung als gerichtet gilt.
CALIBRATION_BIAS_TOL = 0.15


def grading_calibration(preds: Iterable, truths: Iterable,
                        tol: float = CALIBRATION_BIAS_TOL) -> dict:
    """Misst die RICHTUNG der Fehlkalibrierung der KI-Benotung.

    ``preds`` / ``truths`` sind gleich lange Folgen von Notenstufen (0/1/2);
    Paare mit ``None`` (LLM ohne Urteil) werden verworfen. Gibt
    ``{n, bias, mae, direction}`` zurueck:

      * ``bias``  = Mittelwert(pred - truth); positiv = zu milde, negativ = zu streng.
      * ``mae``   = mittlerer Betrag der Abweichung (Staerke der Fehlkalibrierung).
      * ``direction`` = ``"milde"`` / ``"streng"`` / ``"ausgeglichen"`` (``None`` ohne Daten).
    """
    pairs = [(p, t) for p, t in zip(preds, truths)
             if p is not None and t is not None]
    n = len(pairs)
    if n == 0:
        return {"n": 0, "bias": None, "mae": None, "direction": None}
    diffs = [p - t for p, t in pairs]
    bias = sum(diffs) / n
    mae = sum(abs(d) for d in diffs) / n
    if bias > tol:
        direction = "milde"
    elif bias < -tol:
        direction = "streng"
    else:
        direction = "ausgeglichen"
    return {"n": n, "bias": round(bias, 3), "mae": round(mae, 3),
            "direction": direction}
