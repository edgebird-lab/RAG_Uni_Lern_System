"""
Aktives, benotetes Abrufen (Phase 3)
====================================
Ersetzt die reine Ehrlichkeits-Selbstnote durch echtes produktives Abrufen:

  * ``grade_typed_answer``  - der/die Studierende TIPPT die Antwort; ein lokales LLM
    vergleicht sie mit der Musterloesung, vergibt Teilpunkte und nennt, was fehlt
    (Testing-Effekt ist bei produktivem Abruf viel staerker als bei Wiedererkennen).
  * ``make_cloze`` / ``check_cloze`` - Lueckentext, DETERMINISTISCH und OHNE LLM
    (funktioniert sofort/offline, auch auf schwacher Hardware).
  * ``is_grounded`` - Qualitaetsgate: prueft mit dem LLM, ob eine generierte
    Karten-Antwort wirklich durch den Beleg gedeckt ist (kein subtil Falsches lernen).

Alle LLM-Aufrufe fangen Fehler ab und liefern ein ehrliches Fallback (keine
Ausnahme nach oben), damit die Lernrunde nie an einem Modellproblem haengen bleibt.
"""
from __future__ import annotations

import re
from typing import Optional

from ragapp.config import settings
from ragapp.llm import get_llm

# Bewertungen (Spiegel von study.py, ohne Import gegen Zyklen)
_NICHT, _HALB, _GEWUSST = 0, 1, 2


# --------------------------------------------------------------------------- #
# Getippte Freie-Reproduktion mit LLM-Teilbewertung
# --------------------------------------------------------------------------- #
_GRADE_SYSTEM = ("Du bist ein fairer, aber praeziser Klausur-Korrektor an einer "
                 "deutschen Hochschule. Du bewertest INHALTLICH, nicht nach Wortlaut.")

_GRADE_PROMPT = """Bewerte die Antwort eines Studierenden auf eine Pruefungsfrage im
Vergleich zur Musterloesung. Vergib Teilpunkte (0-100) nach inhaltlicher Deckung
(nicht nach exaktem Wortlaut). Sei fair, aber benenne konkret, was fehlt oder falsch ist.

Frage:
{frage}

Musterloesung:
{referenz}

Antwort des Studierenden:
{student}

Gib NUR gueltiges JSON in diesem Format zurueck:
{{"score": <ganze Zahl 0-100>, "fehlt": ["kurzer Punkt", "..."], "feedback": "<1-2 Saetze auf Deutsch>", "note": "<gewusst|halb|nicht>"}}"""


def _rating_from(note: str, score: Optional[int]) -> int:
    note = (note or "").strip().lower()
    if note in ("gewusst", "good", "2"):
        return _GEWUSST
    if note in ("halb", "half", "1"):
        return _HALB
    if note in ("nicht", "again", "0"):
        return _NICHT
    # Fallback aus dem Score ableiten
    if score is None:
        return _HALB
    return _GEWUSST if score >= 75 else (_HALB if score >= 40 else _NICHT)


def grade_typed_answer(question: str, reference: str, student: str,
                       model: Optional[str] = None) -> dict:
    """Benotet eine getippte Antwort gegen die Musterloesung. Gibt
    {score, fehlt, feedback, suggested_rating, ok} zurueck. ``ok=False`` = das LLM
    war nicht auswertbar (die UI faellt dann auf reine Selbstnote zurueck)."""
    q, ref, stu = (question or "").strip(), (reference or "").strip(), (student or "").strip()
    if not stu:
        return {"score": 0, "fehlt": ["(keine Antwort eingegeben)"], "feedback": "",
                "suggested_rating": _NICHT, "ok": True}
    if not ref:
        return {"score": None, "fehlt": [], "feedback": "", "suggested_rating": _HALB, "ok": False}
    try:
        data = get_llm(model or settings.LLM_MODEL).generate_json(
            _GRADE_PROMPT.format(frage=q, referenz=ref[:3000], student=stu[:3000]),
            system=_GRADE_SYSTEM, temperature=0.1)
    except Exception:  # noqa: BLE001
        return {"score": None, "fehlt": [], "feedback": "", "suggested_rating": _HALB, "ok": False}
    if not isinstance(data, dict):
        return {"score": None, "fehlt": [], "feedback": "", "suggested_rating": _HALB, "ok": False}
    try:
        score = int(round(float(data.get("score"))))
        score = max(0, min(100, score))
    except (TypeError, ValueError):
        score = None
    fehlt = [str(x) for x in (data.get("fehlt") or []) if str(x).strip()][:6]
    feedback = str(data.get("feedback") or "").strip()
    return {"score": score, "fehlt": fehlt, "feedback": feedback,
            "suggested_rating": _rating_from(data.get("note"), score), "ok": True}


# --------------------------------------------------------------------------- #
# Lueckentext (deterministisch, offline)
# --------------------------------------------------------------------------- #
_CLOZE_STOP = {"der", "die", "das", "und", "oder", "ein", "eine", "einer", "eines",
               "mit", "von", "zum", "zur", "den", "dem", "des", "auf", "aus", "bei",
               "wird", "sind", "ist", "man", "sich", "nicht", "auch", "durch", "fuer",
               "für", "eine", "einen", "dass", "als", "wie", "wenn", "dann", "diese",
               "dieser", "dieses", "kann", "koennen", "können", "werden", "wurde"}


def make_cloze(text: str, max_blanks: int = 1) -> "tuple[str, list[str]] | None":
    """Erzeugt aus einem Text (Musterloesung) einen Lueckentext: blendet die
    aussagekraeftigsten Begriffe aus. Rein heuristisch, ohne LLM. Gibt
    (text_mit_luecken, [loesungen]) zurueck oder None, wenn kein guter Kandidat da ist."""
    if not text or len(text.strip()) < 25:
        return None
    # Erste sinnvolle Zeile/Satz nehmen (Antworten sind oft mehrzeilig).
    sentence = re.split(r"(?<=[.!?])\s", text.strip())[0]
    if len(sentence) < 20:
        sentence = text.strip()[:200]
    words = re.findall(r"[\wäöüÄÖÜß$\\{}]+", sentence)
    # Kandidaten: lange, inhaltstragende Woerter (Substantive sind im Dt. gross).
    cands = [w for w in words if len(w) >= 5 and w.lower() not in _CLOZE_STOP
             and any(ch.isalpha() for ch in w)]
    cands.sort(key=lambda w: (w[0].isupper(), len(w)), reverse=True)
    if not cands:
        return None
    solutions, blanked = [], sentence
    for w in cands[:max_blanks]:
        # nur die erste Vorkommensstelle ersetzen (Wortgrenze)
        pat = re.compile(r"\b" + re.escape(w) + r"\b")
        if pat.search(blanked):
            blanked = pat.sub("_____", blanked, count=1)
            solutions.append(w)
    if not solutions:
        return None
    return blanked, solutions


def _norm(s: str) -> str:
    """Vergleichs-Normalform: Kleinschreibung, Umlaut-/ß-Faltung (ä->ae, ö->oe,
    ü->ue, ß->ss) und ohne Satzzeichen/Leerraum. So gilt 'Größe' == 'groesse',
    ohne echte Wortunterschiede zu verwischen."""
    s = (s or "").strip().lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return re.sub(r"[^\w]", "", s)


def check_cloze(user: str, solutions: list[str]) -> bool:
    """Prueft eine Lueckentext-Eingabe STRENG gegen die Loesung(en): normalisiert
    (Gross/Klein, Umlaute, Satzzeichen egal), aber es zaehlt nur eine EXAKTE
    Uebereinstimmung der Normalform. Reine Teil-/Oberbegriffe (Teilstrings, z. B.
    'Norm' fuer 'Normalisierung') gelten NICHT als voll korrekt - sonst blaeht
    vages Raten die Mastery auf. Bei mehreren Luecken muss jede Loesung von einer
    Eingabe getroffen werden."""
    ins = {_norm(x) for x in re.split(r"[;,/]| bzw\.? ", user or "") if _norm(x)}
    sols = [_norm(s) for s in solutions if _norm(s)]
    if not sols:
        return False
    return all(s in ins for s in sols)


# --------------------------------------------------------------------------- #
# Qualitaetsgate: ist eine generierte Antwort durch den Beleg gedeckt?
# --------------------------------------------------------------------------- #
_GROUND_PROMPT = """Pruefe streng, ob die ANTWORT inhaltlich vollstaendig durch den
BELEG-Text gedeckt ist (keine erfundenen oder aus Weltwissen ergaenzten Fakten).

Frage: {frage}
Antwort: {antwort}

Beleg:
\"\"\"
{beleg}
\"\"\"

Gib NUR JSON zurueck: {{"grounded": true oder false}}"""


_MCQ_SYSTEM = ("Du bist ein erfahrener Klausur-Ersteller an einer deutschen Hochschule "
               "und formulierst faire, aber trennscharfe Multiple-Choice-Aufgaben.")

_MCQ_PROMPT = """Erzeuge aus Frage und Musterloesung eine Multiple-Choice-Aufgabe.
Gib EINE kurze korrekte Option (1 knapper Satz) und DREI FALSCHE, aber plausible
Optionen GLEICHER Laenge (typische Verwechslungen/Fehlvorstellungen). Alle vier
knapp und vergleichbar formuliert - keine offensichtlich absurden Scherzoptionen.

Frage:
{frage}

Musterloesung (korrekt):
{antwort}

Gib NUR gueltiges JSON zurueck:
{{"richtig": "...", "distraktoren": ["...", "...", "..."]}}"""


def generate_mcq(question: str, answer: str, model: Optional[str] = None) -> "dict | None":
    """Erzeugt on-the-fly eine MCQ (eine richtige + plausible falsche Optionen) aus
    Frage + Musterloesung. Gibt {options: [...gemischt...], correct: str} zurueck oder
    None, wenn nicht genug Optionen entstehen. Distraktoren vom LLM (plausibel)."""
    import random
    ans = (answer or "").strip()
    if not ans:
        return None
    llm = get_llm(model or settings.LLM_MODEL_FAST)
    prompt = _MCQ_PROMPT.format(frage=(question or "")[:400], antwort=ans[:800])
    data = None
    # Bei leerer/trunkierter Antwort (Reasoning-Modelle) einmal mit mehr Budget erneut.
    for np in (settings.LLM_NUM_PREDICT, 2048):
        try:
            data = llm.generate_json(prompt, system=_MCQ_SYSTEM, temperature=0.6, num_predict=np)
        except Exception:  # noqa: BLE001
            data = None
        if isinstance(data, dict) and (data.get("distraktoren") or data.get("richtig")):
            break
    if not isinstance(data, dict):
        return None
    correct = str(data.get("richtig") or "").strip() or ans.split("\n")[0][:200]
    distr = [str(x).strip() for x in (data.get("distraktoren") or []) if str(x).strip()]
    distr = [d for d in distr if d.lower() != correct.lower()][:3]
    if len(distr) < 2:
        return None
    options = [correct] + distr
    random.shuffle(options)
    return {"options": options, "correct": correct}


def is_grounded(frage: str, antwort: str, beleg: str, model: Optional[str] = None) -> bool:
    """Qualitaetsgate fuer generierte Karten: True NUR, wenn das LLM die Antwort
    eindeutig als durch den Beleg gedeckt bestaetigt (streng/fail-closed). Bei
    LLM-Fehler, unparsebarer Antwort ODER fehlendem 'grounded'-Schluessel wird die
    Antwort als NICHT gedeckt gewertet (False) - lieber eine unbelegte Karte
    verwerfen als subtil Falsches lernen. Nur wenn es nichts zu pruefen gibt
    (leere Antwort oder leerer Beleg), wird durchgelassen."""
    if not (antwort or "").strip() or not (beleg or "").strip():
        return True
    try:
        data = get_llm(model or settings.LLM_MODEL_FAST).generate_json(
            _GROUND_PROMPT.format(frage=(frage or "")[:500], antwort=antwort[:1500],
                                  beleg=beleg[:3000]), temperature=0.0)
    except Exception:  # noqa: BLE001
        return False   # fail-closed: bei Modellfehler NICHT durchwinken
    val = data.get("grounded") if isinstance(data, dict) else None
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in {"true", "ja", "yes", "1"}
    return False   # fail-closed: unparsebar / Schluessel fehlt -> nicht gegroundet
