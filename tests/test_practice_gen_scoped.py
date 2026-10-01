"""Übungsaufgabe nur aus dem Text eines Lernplan-Themas
(``practice_gen.generate_practice_problem(source_sections=...)``).

Regression: Ohne vorgegebenen Text wählte der Generator über den Themen-Titel passende
Abschnittstitel und füllte sonst mit dem Dokumentanfang auf. Für ein Plan-Thema
„Skalarprodukt“ (Abschnittstitel nur „Seite 11“) hieß das: eine Aufgabe zu den ersten
Seiten des Dokuments statt zum Thema. Offline: kein LLM, kein Chroma.
"""
from __future__ import annotations

import contextlib

import pytest

from ragapp import manifest, practice_gen


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "MANIFEST_DB", tmp_path / "manifest_test.db")
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)


class FakeLLM:
    def __init__(self):
        self.prompts: list[str] = []

    def generate_json(self, prompt, system=None, temperature=None):
        self.prompts.append(prompt)
        return {"problem_text": "Berechne das Skalarprodukt.",
                "given": [{"label": "a", "value": "(1,2)"}],
                "steps": [{"step_text": "Komponenten multiplizieren"}],
                "final_answer": "11", "hints": ["Denk an die Komponenten"]}


@pytest.fixture()
def llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(practice_gen, "get_llm", lambda model=None: fake)
    monkeypatch.setattr(practice_gen, "llm_task", lambda model=None: contextlib.nullcontext())
    return fake


def test_vorgegebener_text_ersetzt_die_dokumentsuche_vollstaendig(db, llm, monkeypatch):
    monkeypatch.setattr(practice_gen, "_gather_source_sections",
                        lambda doc_ids: pytest.fail("darf bei vorgegebenem Text nicht suchen"))
    sections = [("1 Vektorrechnung.pdf", "Seite 11", "SKALARPRODUKT-TEXT: a·b = a1b1 + a2b2."),
                ("1 Vektorrechnung.pdf", "Seite 12", "Orthogonal, wenn das Skalarprodukt 0 ist.")]
    pid = practice_gen.generate_practice_problem(
        subject="LA", doc_ids=["d1"], topic="Skalarprodukt (Punktprodukt)",
        source_sections=sections)
    prompt = llm.prompts[0]
    assert "SKALARPRODUKT-TEXT" in prompt and "Orthogonal, wenn" in prompt
    saved = manifest.get_practice_problem(pid)
    assert saved["doc_id"] == "d1" and saved["topic"] == "Skalarprodukt (Punktprodukt)"
    assert "SKALARPRODUKT-TEXT" in saved["source_excerpt"]


def test_vorgegebener_text_wird_nicht_mit_anderen_abschnitten_aufgefuellt(db, llm, monkeypatch):
    monkeypatch.setattr(practice_gen, "_gather_source_sections", lambda doc_ids: [
        ("doc", "Seite 1", "DOKUMENTANFANG-NICHT-DAS-THEMA " * 20)])
    practice_gen.generate_practice_problem(
        subject="LA", doc_ids=["d1"], topic="Skalarprodukt",
        source_sections=[("doc", "Seite 11", "NUR DIES: Skalarprodukt.")])
    assert "DOKUMENTANFANG" not in llm.prompts[0] and "NUR DIES" in llm.prompts[0]


def test_ohne_vorgabe_bleibt_das_bisherige_verhalten(db, llm, monkeypatch):
    calls = []

    def gather(doc_ids):
        calls.append(doc_ids)
        return [("doc", "Kostenrechnung", "Kosten sind ..."), ("doc", "Seite 2", "Sonstiges")]

    monkeypatch.setattr(practice_gen, "_gather_source_sections", gather)
    practice_gen.generate_practice_problem(subject="BWL", doc_ids=["d1"], topic="kostenrechnung")
    assert calls == [["d1"]]
    # Der Freitext-Titel waehlt hier weiterhin passende Abschnitte (Treffer zuerst).
    assert llm.prompts[0].index("Kosten sind") < llm.prompts[0].index("Sonstiges")


def test_leerer_vorgegebener_text_ist_ein_klarer_fehler(db, llm):
    with pytest.raises(practice_gen.PracticeGenError, match="Keine indexierten Abschnitte"):
        practice_gen.generate_practice_problem(
            subject="LA", doc_ids=["d1"], topic="x", source_sections=[])


def test_mehrere_dokumente_speichern_keine_dokument_id(db, llm):
    pid = practice_gen.generate_practice_problem(
        subject="LA", doc_ids=["d1", "d2"], topic="T",
        source_sections=[("a", "Seite 1", "Text A"), ("b", "Seite 1", "Text B")])
    assert manifest.get_practice_problem(pid)["doc_id"] is None
