#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Referenzdaten fuer den Paritaetstest der Kartenqualitaet (Kotlin vs. ragapp/card_quality.py und question_gen.py).
Aufruf (Repo-Root, .venv): .venv/bin/python android/eval/tools/make_cards_fixture.py"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ragapp import card_quality as cq  # noqa: E402
from ragapp.ingestion import question_gen as qg  # noqa: E402

gold = [json.loads(l) for l in (ROOT / "android/eval/goldset/goldset.jsonl").read_text(encoding="utf-8").splitlines()]
rag = json.loads((ROOT / "android/eval/spike/rag-1.json").read_text(encoding="utf-8"))["results"]

bad_questions = [
    "Wie lautet die Definition von OD im Abschnitt?", "Was zeigt Abbildung 2?", "Erkläre Definition 4.", "Was besagt Satz 3.1 genau?",
    "Wie folgt aus Formel (2.3) die Gleichung (2.4)?", "Was steht laut Skript über Kosten?", "Nenne die in der Tabelle dargestellten Werte.",
    "Welche Aussage trifft die obige Gleichung?", "Was bedeutet diese Formel?", "Wie lautet die angegebene Aufgabe?",
    "Warum gilt das in diesem Kontext?", "Was ist die betrachtete Funktion?", "Was erklärt man, die durch die Division bewiesen wird?",
    "Wie funktioniert das kurz?", "Was bedeutet das genau?", "", "   ", "Wie berechnet man $x^2+1$?", "Was ist ⎛ ⎞ ⎜⎜⎜ der Vektor?",
    "Was ist 2⃗a + ⃗b?", "Wie hoch ist der Gewinn bei 40 Stück?", "Was ist der Deckungsbeitrag?", "Erläutere die Übung 3 näher.",
    "Beschreibe das Beispiel 2.1.", "Wie wird in der Folie 4 argumentiert?", "Siehe Abschnitt 3: Was gilt?", "Gemäß dem Text, was gilt?",
    "Was ist DIESE ABBILDUNG?", "Was wird in der Abbildung gezeigt?", "Wie heißt das unten genannte Verfahren?", "Wie berechnet man die Herstellkosten je Stück?",
]
bad_answers = [
    ("Die Definition 4 besagt, dass das Eigentum übergeht.", "Wie geht Eigentum über?"),
    ("Siehe Abbildung 2.", "Was zeigt das Diagramm?"),
    ("Eigentum geht über Eigentum über.", "Wie geht Eigentum über?"),
    ("Kosten sind bewertete Güter.", "Was sind Kosten?"),
    ("Der Deckungsbeitrag ist $p - k_v$.", "Was ist der Deckungsbeitrag?"),
    ("⎛x⎞ ⎜y⎟", "Was ist der Vektor?"), ("", "Was?"), ("Die Kosten der Kosten sind die Kosten", "Was sind Kosten der Kosten?"),
    ("Im Kapitel 1.2 steht die Antwort.", "Was steht dort?"),
]
questions = [g["frage"] for g in gold] + bad_questions
answers = [(r["antwort"], r["frage"]) for r in rag] + [(g["erwartete_antwort"], g["frage"]) for g in gold] + bad_answers
raw_answers = ["Antwort: Das ist es.", "```\nMusterlösung: 42\n```", "NICHT_IM_TEXT", "  ", "Lösung:\n\nKosten", "Text NICHT_IM_TEXT hier", "Normale Antwort."]
frage_cases = ["Was ist X?", "kurz", "Berechnen Sie den Gewinn", "Nenne drei Beispiele", "Gib den Wert an", "Wie hoch ist der Gewinn bei 40 Stück?", "Zu kurz?", "Erkläre die Photosynthese."]
echo_cases = [
    ("Was ist Photosynthese?", "# Photosynthese\nBei der Photosynthese wandeln Pflanzen Licht um."),
    ("Wie funktioniert die Photosynthese bei C4-Pflanzen?", "# Photosynthese\nText"),
    ("Was ist der Deckungsbeitrag?", "## Deckungsbeitrag\nDer Deckungsbeitrag ist ..."),
    ("Nenne den Deckungsbeitrag.", "Deckungsbeitrag\nText"),
    ("Was ist X?", "# X\ntext"), ("Erkläre kurz die Kosten", "# Kosten\nKosten sind ..."), ("", "# Kosten"), ("Was ist Kostenrechnung genau?", "### Kostenrechnung\nz"),
]
out = {
    "questions": [{"text": q, "problems": cq.question_problems(q)} for q in questions],
    "answers": [{"text": a, "question": q, "problems": cq.answer_problems(a, q)} for a, q in answers],
    "clean": [{"raw": r, "clean": qg._clean_answer(r)} for r in raw_answers],
    "is_frage": [{"text": t, "value": qg._is_frage(t)} for t in frage_cases] + [{"text": q, "value": qg._is_frage(q)} for q in questions[:20]],
    "echo": [{"question": q, "chunk": c, "value": qg.is_heading_echo(q, c)} for q, c in echo_cases],
}
dest = ROOT / "android/core/src/test/resources/cards/quality_fixture.json"
dest.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
flagged_q = sum(1 for x in out["questions"] if x["problems"])
flagged_a = sum(1 for x in out["answers"] if x["problems"])
print(len(questions), "Fragen (", flagged_q, "mit Maengeln),", len(answers), "Antworten (", flagged_a, "mit Maengeln )")

# Kopie fuer die Geraetetests (data/src/androidTest/assets/parity)
import shutil as _sh
_sh.copy('android/core/src/test/resources/cards/quality_fixture.json' if __import__('os').path.exists('android/core/src/test/resources/cards/quality_fixture.json') else str(ROOT / 'core/src/test/resources/cards/quality_fixture.json'), 'android/data/src/androidTest/assets/parity/' + 'quality_fixture.json')
