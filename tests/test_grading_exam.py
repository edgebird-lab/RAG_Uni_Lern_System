"""Klausur-Gesamtscore: kein 100-%-Ergebnis aus einer Teilmenge."""
from ragapp.grading import aggregate_exam_scores, grounding_verdict, is_grounded


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


def test_is_grounded_leere_seite_laesst_durch():
    assert is_grounded("Frage?", "", "Beleg") is True
    assert is_grounded("Frage?", "Antwort", "") is True


def test_is_grounded_parst_int_und_string(monkeypatch):
    class _Llm:
        def __init__(self, payload):
            self.payload = payload

        def generate_json(self, *a, **k):
            return self.payload

    monkeypatch.setattr("ragapp.grading.get_llm", lambda *a, **k: _Llm({"grounded": 1}))
    assert is_grounded("q", "a", "b") is True
    monkeypatch.setattr("ragapp.grading.get_llm", lambda *a, **k: _Llm({"grounded": "false"}))
    assert is_grounded("q", "a", "b") is False
    monkeypatch.setattr("ragapp.grading.get_llm", lambda *a, **k: _Llm({}))
    assert is_grounded("q", "a", "b") is False
    assert grounding_verdict("q", "a", "b") == "unknown"


def test_grounding_verdict_unknown_bei_llm_fehler(monkeypatch):
    class _Boom:
        def generate_json(self, *a, **k):
            raise RuntimeError("down")

    monkeypatch.setattr("ragapp.grading.get_llm", lambda *a, **k: _Boom())
    assert grounding_verdict("q", "a", "b") == "unknown"
    assert is_grounded("q", "a", "b") is False


def test_ground_prompt_kennt_latex_paraphrase():
    from pathlib import Path
    src = Path("ragapp/grading.py").read_text(encoding="utf-8")
    assert "Gleichwertiges LaTeX" in src
    assert "kappe Formel" in src or "knappe Formel" in src
    assert "check_grounding" in Path("ragapp/study.py").read_text(encoding="utf-8")
    assert "generate_answers" in Path("ragapp/study.py").read_text(encoding="utf-8")
