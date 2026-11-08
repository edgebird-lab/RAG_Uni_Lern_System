"""Retrieval-Metriken und die Reihenfolge im Hit@k-Diagramm der Evaluationsseite."""
from __future__ import annotations

from pathlib import Path

from ragapp.eval.metrics import aggregate, hit_at_k_series


def test_hit_at_k_series_sortiert_numerisch_nicht_alphabetisch():
    hit = {"1": 0.421, "10": 0.842, "3": 0.737, "5": 0.763}
    series = hit_at_k_series(hit)
    assert [label for label, _ in series] == ["k=1", "k=3", "k=5", "k=10"]
    assert [round(v, 1) for _, v in series] == [42.1, 73.7, 76.3, 84.2]


def test_hit_at_k_series_passt_zu_aggregate():
    per_query = [
        {"retrieved_ids": ["a", "b", "c"], "gold_id": "a", "subject": "X"},
        {"retrieved_ids": ["b", "c", "a"], "gold_id": "a", "subject": "X"},
    ]
    summary = aggregate(per_query, (1, 3, 10))
    assert hit_at_k_series(summary["hit@k"]) == [("k=1", 50.0), ("k=3", 100.0), ("k=10", 100.0)]


def test_evaluationsseite_laesst_die_balkenreihenfolge_unveraendert():
    # st.bar_chart sortiert Kategorien alphabetisch (k=1, k=10, k=3, k=5); die Seite muss
    # die gelieferte Reihenfolge behalten (Altair mit sort=None).
    src = Path("ragapp/ui/pages/2_📊_Evaluation.py").read_text(encoding="utf-8")
    assert "hit_at_k_series(hit_at_k)" in src
    assert 'alt.X("k:N", sort=None' in src
    assert "st.bar_chart(chart_df)" not in src
