"""Ein Zug im sokratischen Dialog: Gesprächsstand, Prompt, Prüfung, Wiederholungsschutz.

Warum es dieses Modul gibt (real beobachtet, Chat „Vektorrechnung und Pfeile“,
gemma3:4b, Temperatur 0,1): Ab dem dritten Zug kopierte das Modell seine eigene
letzte Antwort fast wörtlich - egal ob die/der Studierende „Hinweis“, „Löse es auf“
oder „Nächster Aspekt“ drückte; am Ende stand derselbe Text sechsmal im Verlauf. Der
SYSTEMHINWEIS „Löse JETZT auf“ am Ende der Nutzernachricht wurde komplett ignoriert,
weil die als Chat-Turns mitgegebene Historie das Muster „Das ist ein guter erster
Schritt … Können Sie mir noch sagen …?“ vorgab (In-Context-Kopieren). Auch größere
Modelle (qwen2.5:14b, gemma4:e4b) wiederholten im alten Aufbau 3 von 9 Zügen.

Darum:

1. Der Verlauf geht NICHT mehr als Chat-Turns ins Modell, sondern als knapper
   GESPRÄCHSSTAND (offene Frage, bisherige Antworten, schon gestellte Fragen) in EINER
   Nutzernachricht - es gibt nichts mehr zum Weiterkopieren.
2. Der Code entscheidet (Absicht + Phase), was dieser Zug tun soll, und gibt genau
   EINE passende Aufgabe vor (siehe ``prompts.SOKRATISCH_TURN_TASKS``).
3. Die Antwort wird geprüft (Wiederholung, trotz Auflösen-Wunsch weiter gefragt,
   Verweis auf Abbildungen/Quellen, die die/der Studierende nicht sieht, dritte
   Person) und bei Mängeln mit anderer Temperatur/Wiederholungsstrafe neu erzeugt.
   Bleibt es schlecht, greift eine feste, ehrliche Rückfallantwort - nie wieder
   derselbe Text.

Reine Funktionen ohne schwere Importe (kein Ollama/Chroma): das LLM wird übergeben,
damit alles offline testbar bleibt.
"""
from __future__ import annotations

import difflib
import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

from ragapp.graph.prompts import (
    SOKRATISCH_TURN_NOTES, SOKRATISCH_TURN_PROMPT, SOKRATISCH_TURN_RESOLVE_NO_ANSWERS,
    SOKRATISCH_TURN_RESOLVE_WITH_ANSWERS, SOKRATISCH_TURN_SYSTEM, SOKRATISCH_TURN_TASKS,
)

_log = logging.getLogger(__name__)

KINDS = ("start", "hint", "partial", "resolve", "next", "answer")

# --------------------------------------------------------------------------- #
# Text-Helfer
# --------------------------------------------------------------------------- #
_CITE_RE = re.compile(r"\s*[\[(]\s*Quellen?\s*\d[^\])]*[\])]", re.IGNORECASE)
_ABBREVIATIONS = ("z. B.", "z.B.", "d. h.", "d.h.", "u. a.", "u.a.", "z. T.", "bzw.",
                  "ggf.", "vgl.", "Abb.", "Nr.", "usw.", "evtl.", "bspw.", "sog.",
                  "inkl.", "ca.")
_DOT = "․"   # Platzhalter, damit Abkürzungspunkte keinen Satz beenden


def strip_citations(text: Optional[str]) -> str:
    """Entfernt [Quelle N]-Markierungen und glättet die Leerzeichen davor."""
    t = _CITE_RE.sub("", text or "")
    return re.sub(r"[ \t]+([?.!,;:])", r"\1", t).strip()


def _split_sentences(text: str) -> list[str]:
    t = text or ""
    for ab in _ABBREVIATIONS:
        t = t.replace(ab, ab.replace(".", _DOT))
    return [p.replace(_DOT, ".").strip() for p in re.split(r"(?<=[.!?])\s+", t) if p.strip()]


def last_question(text: Optional[str]) -> str:
    """Die offene Frage am Ende einer KI-Antwort ('' = keine). Zählt nur, wenn der
    LETZTE Satz auf '?' endet oder unmittelbar davor eine Frage stand, der nur ein
    kurzer Satz folgt („…? Konzentrieren wir uns auf den Pfeil.“). Eine rhetorische
    Frage mitten in einer Erklärung ist keine offene Frage."""
    tail = _split_sentences(strip_citations(text))[-2:]
    if not tail:
        return ""
    if tail[-1].endswith("?"):
        return tail[-1]
    if len(tail) == 2 and tail[0].endswith("?") and len(tail[1]) <= 140:
        return tail[0]
    return ""


def is_open_question(text: Optional[str]) -> bool:
    return bool(last_question(text))


def _norm(text: Optional[str]) -> str:
    t = strip_citations(text).lower()
    return " ".join(re.sub(r"[^\wäöüß]+", " ", t).split())


def similarity(a: Optional[str], b: Optional[str]) -> float:
    """0..1 - wie ähnlich zwei Texte sind (Satzzeichen, Groß-/Kleinschreibung und
    Quellenmarker zählen nicht)."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    return difflib.SequenceMatcher(None, na, nb, autojunk=False).ratio()


def _clip(text: str, limit: int) -> str:
    t = " ".join((text or "").split())
    return t if len(t) <= limit else t[: limit - 1].rstrip() + "…"


# --------------------------------------------------------------------------- #
# Gesprächsstand
# --------------------------------------------------------------------------- #
@dataclass
class DialogState:
    topic: str
    phase: str                                   # "start" | "open" | "resolved"
    goal: str = ""                               # offene Frage der KI (nur phase=="open")
    asked: list[str] = field(default_factory=list)      # früher gestellte KI-Fragen (alt -> neu)
    answers: list[str] = field(default_factory=list)    # eigene Antworten seit der letzten Auflösung
    ai_texts: list[str] = field(default_factory=list)   # letzte KI-Antworten (alt -> neu)


def dialog_phase(turns: Iterable[dict]) -> str:
    """'start' (noch keine KI-Antwort), 'open' (letzte KI-Antwort endet mit einer
    Frage - die/der Studierende ist dran) oder 'resolved' (letzte KI-Antwort war eine
    Erklärung/Auflösung, es ist keine Frage offen)."""
    last_ai = None
    for t in turns:
        if t.get("role") == "assistant" and (t.get("content") or "").strip():
            last_ai = t["content"]
    if last_ai is None:
        return "start"
    return "open" if is_open_question(last_ai) else "resolved"


def build_state(turns: list[dict], topic: str, *,
                is_control: Callable[[str], bool] = lambda _t: False) -> DialogState:
    """Verdichtet den bisherigen Verlauf (nur role/content, OHNE die aktuelle
    Eingabe) zum Gesprächsstand. ``is_control``: erkennt Steuerimpulse („Hinweis“,
    „Löse es auf“ …), die nicht als inhaltliche Antwort zählen."""
    topic = (topic or "").strip()
    ai = [(t.get("content") or "").strip() for t in turns
          if t.get("role") == "assistant" and (t.get("content") or "").strip()]
    asked: list[str] = []
    for text in ai:
        q = last_question(text)
        if q and q not in asked:
            asked.append(q)
    phase = dialog_phase(turns)

    answers: list[str] = []
    for t in reversed(turns):
        role, content = t.get("role"), (t.get("content") or "").strip()
        if not content:
            continue
        if role == "assistant" and not is_open_question(content):
            break                                   # ab der letzten Auflösung zählt neu
        if role == "user" and not is_control(content) and len(answers) < 2:
            answers.append(_clip(content, 300))
    answers.reverse()

    return DialogState(
        topic=topic, phase=phase,
        goal=last_question(ai[-1]) if (ai and phase == "open") else "",
        asked=asked, answers=answers, ai_texts=ai[-3:])


_INPUT_LINES = {
    "hint": "Die/der Studierende bittet um einen Hinweis.",
    "resolve": "Die/der Studierende möchte die Auflösung sehen.",
    "partial": "Die/der Studierende sagt, dass sie/er nur einen Teil weiß.",
    "next": "Die/der Studierende möchte zum nächsten Teilaspekt.",
}


def _state_lines(state: DialogState, kind: str, question: str) -> str:
    lines: list[str] = []
    if state.phase == "start" or kind == "start":
        lines.append("- Das Gespräch beginnt gerade (kein Verlauf).")
    elif state.phase == "open" and state.goal:
        lines.append(f"- Deine offene Frage an die/den Studierenden: „{_clip(state.goal, 300)}“")
    else:
        lines.append("- Deine letzte Frage ist bereits aufgelöst; es ist keine Frage offen.")
    if state.answers and kind not in ("start",):
        quoted = "; ".join(f"„{a}“" for a in state.answers)
        lines.append(f"- Bisherige Antworten der/des Studierenden darauf: {quoted}")
    if kind == "answer":
        lines.append(f"- Aktuelle Eingabe der/des Studierenden: „{_clip(question, 600)}“")
    elif kind in _INPUT_LINES:
        lines.append(f"- {_INPUT_LINES[kind]}")
    avoid = list(state.asked)
    if kind in ("hint", "partial", "resolve") and state.goal in avoid:
        avoid.remove(state.goal)                    # die offene Frage darf/soll wieder vorkommen
    if avoid:
        lines.append("- Schon gestellte Fragen (NICHT wiederholen, auch nicht umformuliert): "
                     + " | ".join(f"„{_clip(q, 160)}“" for q in avoid[-4:]))
    return "\n".join(lines)


def build_messages(state: DialogState, kind: str, note: Optional[str], question: str,
                   context: str, *, correction: str = "") -> list[dict]:
    """[system, user] - bewusst KEINE früheren Chat-Turns (siehe Moduldoc)."""
    task = SOKRATISCH_TURN_TASKS.get(kind) or SOKRATISCH_TURN_TASKS["answer"]
    if kind == "resolve":
        task += " " + (SOKRATISCH_TURN_RESOLVE_WITH_ANSWERS if state.answers
                       else SOKRATISCH_TURN_RESOLVE_NO_ANSWERS)
    if note and note in SOKRATISCH_TURN_NOTES:
        task += " " + SOKRATISCH_TURN_NOTES[note]
    if correction:
        task += "\n\n" + correction
    user = SOKRATISCH_TURN_PROMPT.format(
        topic=state.topic or "(frei gewählt)", context=context,
        state=_state_lines(state, kind, question), task=task)
    return [{"role": "system", "content": SOKRATISCH_TURN_SYSTEM},
            {"role": "user", "content": user}]


# --------------------------------------------------------------------------- #
# Antwort säubern + prüfen
# --------------------------------------------------------------------------- #
_LABEL_RE = re.compile(
    r"(?im)^[ \t]*(?:\*\*)?(?:Rückmeldung|Feedback|Antwort|Auflösung|Lösung|Hinweis|"
    r"Nächste Frage|Weiterführende Frage|Folgefrage|Frage|Aufgabe)(?:\*\*)?[ \t]*:[ \t]*(?:\*\*)?[ \t]*")
_QUESTION_SPAN_RE = re.compile(r"[^.!?\n]*\?")
_CITE_AFTER_QMARK_RE = re.compile(r"(\?)[ \t]*(?:[\[(]\s*Quellen?\s*\d[^\])]*[\])][ \t]*)+")
# „… in Quelle 1 gelesen“ -> „… gelesen“: kleine Modelle schreiben das auch nach einer
# Korrektur wieder hin; die Wendung ist ohne Quellenliste sinnlos und lässt sich
# verlustfrei streichen.
_INLINE_SOURCE_RE = re.compile(
    r"[ \t]*\b(?:in|aus|laut|gemäß|nach|siehe)[ \t]+Quellen?[ \t]*\d+(?:[ \t]*(?:,|und)[ \t]*\d+)*",
    re.IGNORECASE)


def clean_answer(raw: Optional[str], kind: str) -> str:
    """Entfernt Labels/Anführungszeichen-Rahmen und - außer bei der Auflösung -
    Quellenverweise (die/der Studierende sieht die Quellen-Nummern nicht)."""
    text = (raw or "").strip()
    text = _LABEL_RE.sub("", text)
    if len(text) > 1 and text[0] in "„\"“" and text[-1] in "“\"”" and text.count("„") <= 1:
        text = text[1:-1].strip()
    if kind != "resolve":
        text = _CITE_AFTER_QMARK_RE.sub(r"\1", text)
        text = _QUESTION_SPAN_RE.sub(lambda m: _CITE_RE.sub("", m.group(0)), text)
        text = _INLINE_SOURCE_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# Bezüge auf Dinge, die die/der Studierende im Chat nicht sieht. „Abbildung“ allein
# ist in der Linearen Algebra ein Fachbegriff („lineare Abbildung“) - gezählt wird nur
# ein nummerierter oder hinweisender Bezug („Abbildung 2“, „in der folgenden Skizze“).
_MATERIAL_REF_RE = re.compile(
    r"\b(?:Abbildung|Abb\.|Skizze|Grafik|Folie|Diagramm|Tabelle|Bild|Seite)\s*\d+\b"
    r"|\bQuelle\s*\d+"
    r"|\b(?:Definition|Satz|Beispiel|Kapitel|Abschnitt|Aufgabe)\s*\d+(?:\.\d+)*\b"
    r"|\b(?:in|auf|an|aus|laut|gemäß|siehe)\s+(?:der|dem|den)?\s*"
    r"(?:folgenden|obigen|nebenstehenden|gezeigten|dargestellten|abgebildeten)\s+"
    r"(?:Abbildung|Skizze|Grafik|Darstellung|Bild|Diagramm|Folie)\b",
    re.IGNORECASE)
_THIRD_PERSON_RE = re.compile(
    r"\b(?:der|die|des|dem|den)\s+Studierenden\b|\bdie/der\s+Studierende|\bder/die\s+Studierende"
    r"|\bStudierende\(r\)", re.IGNORECASE)

# Gewicht eines Mangels; >= _HARD gilt als unbrauchbar (-> Rückfallantwort, wenn auch
# der beste Versuch ihn noch hat).
_WEIGHT = {"leer": 100, "wiederholung": 60, "frage_wiederholt": 50, "nicht_aufgeloest": 50,
           "unterlagen_bezug": 12, "dritte_person": 8, "keine_frage": 6}
_HARD = 40
_QUESTION_KINDS = ("start", "hint", "partial", "next", "answer")
REPEAT_THRESHOLD = 0.8
QUESTION_REPEAT_THRESHOLD = 0.75


def validate(text: str, kind: str, state: DialogState) -> list[str]:
    """Mängel einer Antwort als Codes (leer = in Ordnung)."""
    problems: list[str] = []
    body = strip_citations(text)
    if len(body) < 12:
        return ["leer"]
    if any(similarity(text, prev) >= REPEAT_THRESHOLD for prev in state.ai_texts):
        problems.append("wiederholung")
    q = last_question(text)
    if kind == "resolve":
        if is_open_question(text):
            problems.append("nicht_aufgeloest")
    elif kind in _QUESTION_KINDS:
        if not q:
            problems.append("keine_frage")
        elif kind != "hint" and any(
                similarity(q, old) >= QUESTION_REPEAT_THRESHOLD for old in state.asked):
            problems.append("frage_wiederholt")
    if _MATERIAL_REF_RE.search(body):
        problems.append("unterlagen_bezug")
    if _THIRD_PERSON_RE.search(body):
        problems.append("dritte_person")
    return problems


def _score(problems: list[str]) -> int:
    return sum(_WEIGHT.get(p, 5) for p in problems)


_REASONS = {
    "leer": "sie war leer",
    "wiederholung": "sie wiederholte eine frühere Antwort",
    "frage_wiederholt": "die Frage war schon einmal gestellt worden",
    "nicht_aufgeloest": "sie endete mit einer Frage, obwohl aufgelöst werden sollte",
    "unterlagen_bezug": "sie verwies auf Abbildungen, Quellen oder Nummern, die die/der "
                        "Studierende nicht sieht",
    "dritte_person": "sie sprach über die/den Studierenden in der dritten Person",
    "keine_frage": "sie enthielt keine Frage",
}


def _correction(problems: list[str], bad_text: str) -> str:
    why = "; ".join(_REASONS.get(p, p) for p in problems)
    return (f"KORREKTUR: Deine vorige Fassung war nicht brauchbar ({why}). Schreibe eine "
            f"deutlich ANDERE Fassung.\nVorige Fassung (NICHT wiederholen): „{_clip(bad_text, 400)}“")


# --------------------------------------------------------------------------- #
# Rückfallantworten (ohne LLM)
# --------------------------------------------------------------------------- #
def _excerpt(chunks: Iterable[str], limit: int = 600) -> str:
    for chunk in chunks:
        text = " ".join(re.sub(r"\[\s*Quelle[^\]]*\]", "", chunk or "").split())
        if len(text) < 80:
            continue
        if len(text) <= limit:
            return text
        cut = text[:limit]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        return (cut[: end + 1] if end >= 200 else cut.rsplit(" ", 1)[0] + " …")
    return ""


def fallback_text(kind: str, topic: str, chunks: Iterable[str]) -> str:
    """Feste, ehrliche Antwort, wenn auch mehrere Versuche mangelhaft blieben."""
    if kind == "resolve":
        excerpt = _excerpt(chunks)
        if excerpt:
            return ("Ich konnte die Auflösung gerade nicht sauber in eigene Worte fassen. "
                    "Hier die passende Stelle direkt aus deinen Unterlagen:\n\n"
                    f"> {excerpt} [Quelle 1]")
    about = f"„{topic}“" if topic else "diesem Thema"
    # Bewusst eine ECHTE Frage: Dann bleibt der Dialog "offen" (Chips, Zustand).
    return ("Ich merke, dass ich mich im Kreis drehe – lass uns neu ansetzen. Was weißt du zu "
            f"{about} schon? Erkläre es mir in eigenen Worten, dann knüpfe ich genau dort an.")


# --------------------------------------------------------------------------- #
# Ein Zug
# --------------------------------------------------------------------------- #
@dataclass
class TurnResult:
    text: str
    attempts: int
    problems: list[str]            # Mängel der gewählten Fassung ([] = sauber)
    fallback: bool = False


# Beim ersten Versuch leicht über der globalen Temperatur (0,1): sonst ist die Antwort
# bei gleichem Kontext praktisch deterministisch. Bei Mängeln bewusst mehr Streuung
# plus Wiederholungsstrafe.
_ATTEMPTS = (
    {"temperature": 0.3, "options": None},
    {"temperature": 0.7, "options": {"repeat_penalty": 1.15}},
    {"temperature": 0.9, "options": {"repeat_penalty": 1.25, "top_p": 0.95}},
)


def generate_turn(llm, *, kind: str, note: Optional[str], state: DialogState,
                  question: str, context: str, fallback_chunks: Iterable[str] = (),
                  max_attempts: int = 3) -> TurnResult:
    """Erzeugt die Antwort für einen Zug, prüft sie und versucht es bei Mängeln neu.

    Fehler des ersten LLM-Aufrufs werden durchgereicht (Aufrufer zeigt die
    verständliche Meldung); scheitert erst ein späterer Versuch, bleibt die beste
    bisherige Fassung."""
    chunks = list(fallback_chunks)
    candidates: list[tuple[int, str, list[str]]] = []
    correction = ""
    attempts = 0
    for attempt in range(1, max(1, max_attempts) + 1):
        sampling = _ATTEMPTS[min(attempt, len(_ATTEMPTS)) - 1]
        messages = build_messages(state, kind, note, question, context, correction=correction)
        kwargs = {"temperature": sampling["temperature"]}
        if sampling["options"]:
            kwargs["options"] = sampling["options"]
        try:
            raw = llm.chat(messages, **kwargs)
        except Exception:                           # noqa: BLE001
            if not candidates:
                raise
            _log.warning("Sokratisch: Versuch %d fehlgeschlagen - nutze beste Fassung.", attempt)
            break
        attempts = attempt
        text = clean_answer(raw, kind)
        problems = validate(text, kind, state)
        candidates.append((_score(problems), text, problems))
        if not problems:
            break
        _log.info("Sokratisch (%s): Versuch %d verworfen: %s", kind, attempt, ", ".join(problems))
        correction = _correction(problems, text)

    score, text, problems = min(candidates, key=lambda c: c[0])
    if score >= _HARD:
        _log.warning("Sokratisch (%s): alle %d Versuche mangelhaft (%s) - Rückfallantwort.",
                     kind, attempts, ", ".join(problems))
        return TurnResult(fallback_text(kind, state.topic, chunks), attempts, problems, True)
    return TurnResult(text, attempts, problems, False)
