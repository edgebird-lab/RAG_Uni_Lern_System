"""Tests für practice_gen.generate_formelsammlung() (fasst bisherige
Übungsaufgaben eines Fachs zu einer wachsenden Formel-/Methodensammlung
zusammen). Echter Modulimport (zieht chromadb transitiv, aber schnell genug
für einen eigenen Testlauf) + gefakte LLM (keine echte Ollama-Abhängigkeit) +
isolierte Temp-DB (niemals die echte data/manifest.db)."""
from __future__ import annotations

import pytest

from ragapp import manifest, practice_gen


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "manifest_test.db"
    monkeypatch.setattr(manifest, "MANIFEST_DB", db_path)
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)
    return db_path


class _FakeLLM:
    def __init__(self, *, result=None, raise_exc=None):
        self._result = result
        self._raise_exc = raise_exc

    def generate(self, prompt, system=None, temperature=None):
        self.last_prompt = prompt
        if self._raise_exc:
            raise self._raise_exc
        return self._result


def _add_problem(subject: str, text: str, step: str) -> str:
    return manifest.create_practice_problem(
        subject=subject, problem_text=text, steps=[{"step_text": step}],
        final_answer="x")


def test_ohne_aufgaben_wirft_fehler(isolated_db):
    with pytest.raises(practice_gen.PracticeGenError):
        practice_gen.generate_formelsammlung("mathe")


def test_llm_fehler_wird_zu_practice_gen_error(isolated_db, monkeypatch):
    _add_problem("mathe", "Frage", "Schritt")
    monkeypatch.setattr(practice_gen, "get_llm",
                        lambda model=None: _FakeLLM(raise_exc=RuntimeError("boom")))
    with pytest.raises(practice_gen.PracticeGenError):
        practice_gen.generate_formelsammlung("mathe")


def test_leere_antwort_wirft_fehler(isolated_db, monkeypatch):
    _add_problem("mathe", "Frage", "Schritt")
    monkeypatch.setattr(practice_gen, "get_llm", lambda model=None: _FakeLLM(result="   "))
    with pytest.raises(practice_gen.PracticeGenError):
        practice_gen.generate_formelsammlung("mathe")


def test_erfolgsfall_gibt_markdown_zurueck(isolated_db, monkeypatch):
    _add_problem("mathe", "Schnittmenge A und B?", "Kleinere obere Grenze nehmen.")
    fake = _FakeLLM(result="## Mengenlehre\n- Schnittmenge: ...")
    monkeypatch.setattr(practice_gen, "get_llm", lambda model=None: fake)
    result = practice_gen.generate_formelsammlung("mathe")
    assert result == "## Mengenlehre\n- Schnittmenge: ..."


def test_prompt_enthaelt_nur_das_gewaehlte_fach(isolated_db, monkeypatch):
    _add_problem("mathe", "Mathe-Frage", "Mathe-Schritt")
    _add_problem("physik", "Physik-Frage", "Physik-Schritt")
    fake = _FakeLLM(result="ok")
    monkeypatch.setattr(practice_gen, "get_llm", lambda model=None: fake)
    practice_gen.generate_formelsammlung("mathe")
    assert "Mathe-Frage" in fake.last_prompt
    assert "Physik-Frage" not in fake.last_prompt


def test_kappt_am_zeichenbudget(isolated_db, monkeypatch):
    for i in range(5):
        _add_problem("mathe", f"Frage {i}", "X" * 500)
    fake = _FakeLLM(result="ok")
    monkeypatch.setattr(practice_gen, "get_llm", lambda model=None: fake)
    monkeypatch.setattr(practice_gen.settings, "FORMELSAMMLUNG_MAX_CHARS", 600)
    practice_gen.generate_formelsammlung("mathe")
    # Bei einem Budget von 600 Zeichen und Bloecken von je >500 Zeichen darf
    # nicht der komplette Aufgabenbestand (>2500 Zeichen) im Prompt landen.
    assert len(fake.last_prompt) < 2500
