"""Qualitätsfilter für Karteikarten (``ragapp.card_quality``) - rein offline.

Die Beispiele sind an echten Mängeln von gemma3:4b-Karten (Lineare Algebra) orientiert, aber
frei formuliert: Verweis auf die Quelle, kaputte PDF-Zeichen, Beweisschritt-Kontext, Dubletten.
Wichtig ist ebenso die Gegenprobe: ganz normale gute Fragen dürfen NIE angeschlagen werden."""
from __future__ import annotations

import pytest

from ragapp import card_quality as cq


# --------------------------------------------------------------------------- #
# Fragen mit Mangel
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("question", [
    "Wie lautet die Definition von OD im Abschnitt?",
    "Wie lautet die Definition des Betrags, dargestellt im Abschnitt?",
    "Was zeigt Abbildung 2?",
    "Was ist in Abb. 3.1 dargestellt?",
    "Welche Aussage macht Definition 4 über den Nullvektor?",
    "Wie lautet Satz 3.2?",
    "Was folgt laut Formel (7.1) für die Länge?",
    "Wie lautet die Aussage aus Aufgabe 5?",
    "Was steht auf Seite 12 über Matrizen?",
    "Was wird im folgenden Abschnitt über Determinanten gesagt?",
    "Welche Eigenschaft hat der Vektor laut Skript?",
    "Was besagt der obige Satz?",
    "Wie wird das Verfahren in der Abbildung gezeigt?",
    "Wie ist der Begriff nach der Vorlesung definiert?",
])
def test_quellenbezug_wird_erkannt(question):
    assert cq.QUELLENBEZUG in cq.question_problems(question), question


@pytest.mark.parametrize("question", [
    "Wie berechnet man das Skalarprodukt zwischen den Vektoren ⎛ ⎞ ⎛ ⎞ und ⎜⎜⎜⎜⎜ ⎟⎟⎟⎟⎟ ?",
    "Wie lautet die Komponentendarstellung von 2⃗a +⃗b ?",
    "Wie lässt sich Vektor ⃗v im R3 definieren?",
    "Was bedeutet das Zeichen � in der Formel?",
    "Was ist  in diesem Satz?",
])
def test_kaputte_pdf_zeichen_werden_erkannt(question):
    assert cq.UNLESERLICH in cq.question_problems(question), question


@pytest.mark.parametrize("question", [
    "Wie lautet die Behauptung, die durch die Subtraktion gleicher Terme bewiesen wird?",
    "Wie lautet die vereinfachte Formel, die aus der Abschätzung abgeleitet wird?",
    "Wie lautet die Koordinatendarstellung des Vektors, der durch die drei angegebenen Bewegungen entsteht?",
    "Warum ist dieser Schritt in diesem Kontext formal zu betrachten?",
    "Wie ändert sich der betrachtete Raum durch Linearkombinationen?",
    "Was bedeutet diese Gleichung für die Lösungsmenge?",
    "Was ergibt sich in diesem Fall für die Determinante?",
    "Welche Größe wurde oben genannt?",
])
def test_fehlender_kontext_wird_erkannt(question):
    assert cq.KONTEXT in cq.question_problems(question) \
        or cq.QUELLENBEZUG in cq.question_problems(question), question


@pytest.mark.parametrize("question", ["Was ist das?", "Wie funktioniert dies?", "Erkläre das kurz."])
def test_inhaltsleere_fragen_sind_zu_vage(question):
    assert cq.VAGE in cq.question_problems(question)


def test_leere_frage_ist_vage():
    assert cq.question_problems("") == [cq.VAGE]
    assert cq.question_problems("   ") == [cq.VAGE]


# --------------------------------------------------------------------------- #
# Gegenprobe: gute Fragen werden NICHT angeschlagen
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("question", [
    "Was ist ein Vektorraum?",
    "Wie berechnet man das Skalarprodukt zweier Vektoren im $\\mathbb{R}^3$?",
    "Welche Eigenschaft muss eine Matrix haben, damit sie invertierbar ist?",
    "Nenne die drei Axiome einer Norm.",
    "Wie lautet der Satz des Pythagoras?",
    "Was besagt die Cauchy-Schwarzsche Ungleichung?",
    "Erkläre den Unterschied zwischen Kovarianz und Korrelation.",
    "Berechnen Sie die Determinante von $A = \\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix}$.",
    "Wie wird der Deckungsbeitrag pro Stück berechnet?",
    "Warum ist die Laufzeit von Quicksort im schlechtesten Fall quadratisch?",
    "Wie unterscheidet sich ein symmetrisches von einem asymmetrischen Verschlüsselungsverfahren?",
    "Wie berechnet man die Koordinaten des vierten Eckpunkts D eines Parallelogramms, wenn die "
    "Koordinaten der anderen drei Ecken gegeben sind?",
    "Was ist eine quadratische Gleichung 2. Grades und wie löst man sie?",
    "Wie lautet die Formel für die Länge eines Vektors und wie wird sie hergeleitet?",
    "Wie heißt der Satz von Bayes und was besagt er?",
    "Was ändert sich an der Richtung eines Vektors, wenn man ihn mit -1 multipliziert?",
    "Definieren Sie den Begriff Linearkombination.",
    "Wie hängen Rang und Dimension des Kerns einer Matrix zusammen?",
    "Berechne $3\\vec{a} - 2\\vec{b}$ für $\\vec{a}=(1,2)$ und $\\vec{b}=(0,1)$.",
    "Was bedeutet es, wenn zwei Vektoren orthogonal sind?",
    "Wie lautet die Formel für den Umfang eines Kreises mit Radius r?",
    "Welche Seite eines Dreiecks liegt dem rechten Winkel gegenüber?",
])
def test_gute_fragen_bleiben_unbeanstandet(question):
    assert cq.question_problems(question) == [], question


def test_diese_formel_ist_in_ordnung_wenn_die_frage_sie_selbst_nennt():
    assert cq.KONTEXT not in cq.question_problems(
        "Wie lautet die Formel für den Betrag und wie wird diese Formel hergeleitet?")
    assert cq.KONTEXT in cq.question_problems("Wie wird diese Formel hergeleitet?")


# --------------------------------------------------------------------------- #
# Antworten
# --------------------------------------------------------------------------- #
def test_antwort_mit_verweis_auf_definition_oder_kapitel():
    assert cq.QUELLENBEZUG in cq.answer_problems(
        "Der entgegengesetzte Vektor, definiert durch Definition 4, unterscheidet sich "
        "vom Nullvektor.", "Was ist der entgegengesetzte Vektor?")
    assert cq.QUELLENBEZUG in cq.answer_problems(
        "Die im Kapitel 1.2 definierten Begriffe gelten auch im Raum.", "Gilt das im Raum?")
    assert cq.QUELLENBEZUG in cq.answer_problems(
        "Das zeigt die Abbildung 4 als Gleichung.", "Wie lautet die Gleichung?")


def test_antwort_mit_kaputten_klammerzeichen():
    assert cq.UNLESERLICH in cq.answer_problems("Es gilt v = ⎛ ⎞ ⎝ ⎠ für den Spaltenvektor.", "Wie?")


def test_antwort_die_nur_die_frage_wiederholt_ist_zirkulaer():
    q = "Was versteht man unter dem Betrag eines Vektors?"
    assert cq.ZIRKULAER in cq.answer_problems("Unter dem Betrag eines Vektors versteht man den Betrag eines Vektors.", q)


def test_antwort_mit_neuer_information_oder_formel_ist_nicht_zirkulaer():
    q = "Was versteht man unter dem Betrag eines Vektors?"
    assert cq.answer_problems("Der Betrag eines Vektors ist seine Länge, also die Wurzel aus der Summe der Quadrate.", q) == []
    # Aussage steckt in der Formel: kein Fehlalarm, auch wenn der Satz die Frage umformuliert.
    assert cq.answer_problems("Die Behauptung lautet $0 = v_1 w_1 + v_2 w_2$.",
                              "Wie lautet die Behauptung?") == []


def test_leere_antwort_ist_kein_antwortmangel():
    assert cq.answer_problems("", "Frage?") == []


# --------------------------------------------------------------------------- #
# Neuversuch-Hinweis + Beschreibung
# --------------------------------------------------------------------------- #
def test_retry_hint_nennt_nur_die_festgestellten_maengel():
    hint = cq.retry_hint([cq.QUELLENBEZUG, cq.QUELLENBEZUG, cq.UNLESERLICH])
    assert "Abbildung" in hint and "LaTeX" in hint
    assert "Kontext" not in hint
    assert cq.retry_hint([]) == ""
    assert cq.retry_hint(["unbekannt"]) == ""


def test_describe_und_describe_audit():
    assert "Quelle" in cq.describe([cq.QUELLENBEZUG])
    text = cq.describe_audit({"question": [cq.DUPLIKAT], "answer": [cq.QUELLENBEZUG]})
    assert text.startswith("Frage:") and "Antwort:" in text
    assert cq.describe_audit({"question": [], "answer": []}) == ""


# --------------------------------------------------------------------------- #
# Dubletten
# --------------------------------------------------------------------------- #
def test_cosine_und_schwelle():
    assert cq.cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cq.cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert cq.cosine([0, 0], [1, 0]) == 0.0
    assert cq.is_duplicate([1, 0], [[0, 1], [0.99, 0.1]])          # 0.995
    assert not cq.is_duplicate([1, 0], [[0, 1], [0.8, 0.6]])       # 0.8 < 0.89
    assert not cq.is_duplicate([1, 0], [])


def _fake_embed(table):
    return lambda texts: [table[t] for t in texts]


def test_find_duplicates_behaelt_die_erste_und_meldet_spaetere():
    emb = _fake_embed({"a": [1, 0], "b": [0.99, 0.05], "c": [0, 1], "d": [0.98, 0.1]})
    dups = cq.find_duplicates([("1", "a"), ("2", "b"), ("3", "c"), ("4", "d")], emb)
    assert dups == {"2": "1", "4": "1"}


def test_find_duplicates_ohne_paar_ist_leer():
    assert cq.find_duplicates([("1", "a")], lambda t: [[1, 0]]) == {}
    assert cq.find_duplicates([], lambda t: []) == {}


def test_audit_cards_trennt_frage_und_antwortmangel_und_ignoriert_fremde_quellen():
    cards = [
        {"card_id": "gut", "source": "question", "front": "Was ist ein Vektorraum?",
         "answer": "Eine Menge mit Addition und Skalarmultiplikation.", "doc_id": "d"},
        {"card_id": "frage", "source": "question", "front": "Was zeigt Abbildung 2?",
         "answer": "Einen Pfeil.", "doc_id": "d"},
        {"card_id": "antwort", "source": "question", "front": "Wie lang ist ein Vektor?",
         "answer": "Er ist so lang wie in Definition 8 festgelegt.", "doc_id": "d"},
        {"card_id": "klausur", "source": "exam_qa", "front": "Was zeigt Abbildung 2?",
         "answer": "Wie in Definition 8.", "doc_id": "d"},
    ]
    res = cq.audit_cards(cards)
    assert set(res) == {"frage", "antwort"}
    assert res["frage"]["question"] == [cq.QUELLENBEZUG] and res["frage"]["answer"] == []
    assert res["antwort"]["question"] == [] and res["antwort"]["answer"] == [cq.QUELLENBEZUG]


def test_audit_cards_findet_dubletten_nur_innerhalb_eines_dokuments():
    cards = [
        {"card_id": "a1", "source": "question", "front": "Frage A", "answer": "x y z w", "doc_id": "d1"},
        {"card_id": "a2", "source": "question", "front": "Frage A anders", "answer": "x y z w", "doc_id": "d1"},
        {"card_id": "b1", "source": "question", "front": "Frage A dritte", "answer": "x y z w", "doc_id": "d2"},
    ]
    table = {"Frage A": [1, 0], "Frage A anders": [0.99, 0.05], "Frage A dritte": [0.99, 0.04]}
    res = cq.audit_cards(cards, embed=_fake_embed(table))
    assert res == {"a2": {"question": [cq.DUPLIKAT], "answer": []}}     # b1 ist in einem anderen Dokument


def test_audit_cards_ohne_embedder_prueft_keine_dubletten():
    cards = [
        {"card_id": "a1", "source": "question", "front": "Wie lang ist ein Vektor?", "answer": "Lang genug sein Betrag", "doc_id": "d"},
        {"card_id": "a2", "source": "question", "front": "Wie lang ist ein Vektor?", "answer": "Lang genug sein Betrag", "doc_id": "d"},
    ]
    assert cq.audit_cards(cards) == {}
