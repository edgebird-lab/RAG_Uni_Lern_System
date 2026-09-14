"""Klausur-Gesamtscore: kein 100-%-Ergebnis aus einer Teilmenge."""
from ragapp.grading import aggregate_exam_scores


def test_aggregate_alle_benotet():
    assert aggregate_exam_scores([80, 100, 60]) == {
        "total_pct": 80, "graded": 3, "partial": False,
    }


def test_aggregate_eine_note_ist_unvollstaendig():
    out = aggregate_exam_scores([100, None, None])
    assert out["total_pct"] == 100
    assert out["graded"] == 1
    assert out["partial"] is True


def test_aggregate_keine_note():
    out = aggregate_exam_scores([None, None])
    assert out["total_pct"] is None
    assert out["graded"] == 0
    assert out["partial"] is True
