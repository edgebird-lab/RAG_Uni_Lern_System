"""Eindeutige Themen-Titel in der Gliederung (``study_plan._disambiguate_titles``)."""
from __future__ import annotations

from ragapp import study_plan

CAPPED = [("A.pdf", f"Seite {i}", "x" * 100) for i in range(1, 21)]      # Seite 1..20, Index = Seite-1


def topic(title, *pages):
    return {"title": title, "summary": "", "indices": [p - 1 for p in pages]}


def titles(topics):
    return [t["title"] for t in topics]


def test_eindeutige_titel_bleiben_unveraendert_und_dieselbe_liste():
    topics = [topic("Vektoren", 1, 2), topic("Matrizen", 3)]
    out = study_plan._disambiguate_titles(topics, CAPPED)
    assert out is topics


def test_gleiche_titel_bekommen_den_seitenbereich():
    topics = [topic("Geometrische Erweiterungen", 8, 9, 10, 11), topic("Geometrische Erweiterungen", 12, 13, 14, 15, 19),
              topic("Vektoren", 1)]
    assert titles(study_plan._disambiguate_titles(topics, CAPPED)) == [
        "Geometrische Erweiterungen (S. 8–11)", "Geometrische Erweiterungen (S. 12–15, 19)", "Vektoren"]


def test_vergleich_ohne_gross_und_kleinschreibung_und_leerzeichen():
    topics = [topic("Skalarprodukt", 1, 2), topic(" skalarprodukt ", 3, 4)]
    out = titles(study_plan._disambiguate_titles(topics, CAPPED))
    assert out[0].endswith("(S. 1–2)") and out[1].endswith("(S. 3–4)")


def test_ohne_seitentitel_wird_gezaehlt():
    capped = [("B.md", "Kapitel 1 > Einleitung", "x" * 100), ("B.md", "Kapitel 2 > Einleitung", "x" * 100)]
    topics = [topic("Einleitung", 1), topic("Einleitung", 2)]
    out = titles(study_plan._disambiguate_titles(topics, capped))
    assert len(set(out)) == 2 and out[0] == "Einleitung" and out[1] == "Einleitung (2)"


def test_der_neue_titel_kollidiert_nicht_mit_einem_vorhandenen():
    topics = [topic("Vektoren", 1, 2), topic("Vektoren", 3), topic("Vektoren (S. 1–2)", 5)]
    out = titles(study_plan._disambiguate_titles(topics, CAPPED))
    assert len({t.casefold() for t in out}) == 3


def test_urspruengliche_themen_werden_nicht_veraendert():
    topics = [topic("A", 1), topic("A", 2)]
    study_plan._disambiguate_titles(topics, CAPPED)
    assert titles(topics) == ["A", "A"]
