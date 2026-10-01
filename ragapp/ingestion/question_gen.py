"""
Fragen-Generierung (Hypothetical Questions)
==========================================

Für jeden Chunk generiert das LLM mehrere prägnante Prüfungsfragen, die *genau
mit diesem Chunk* beantwortbar sind. Diese Fragen werden zusätzlich zum Chunk in
die Vektordatenbank aufgenommen (als eigene Einträge, die auf den Eltern-Chunk
zeigen).

Warum das die Trefferquote erhöht:
    Nutzer stellen Fragen ("Wie berechnet man den Deckungsbeitrag?"). Solche
    Fragen liegen im Embedding-Raum oft näher an einer *Frage* als am reinen
    Lehrtext. Durch die indexierten Fragen findet das System den richtigen Chunk
    deutlich zuverlässiger (Multi-Representation-Indexing).
"""
from __future__ import annotations

import re

from ragapp import card_quality
from ragapp.config import settings
from ragapp.llm import get_llm


class QuestionGenError(RuntimeError):
    """Echter LLM-/Backend-Fehler bei der Fragen-Generierung (z. B. Modell laedt nicht).
    Wird - anders als ein LEERES Ergebnis - nach oben durchgereicht, damit die UI den
    Fehler sichtbar machen kann (statt faelschlich '0 Fragen = Erfolg')."""


# Auch Aufforderungs-/Imperativ-Fragen sind gueltige Pruefungsfragen ("Berechnen Sie …",
# "Nennen Sie …") - nicht nur solche mit Fragezeichen.
_IMPERATIVE = ("nenne", "erklär", "erklaer", "berechne", "beschreib", "definier",
               "begründe", "begruende", "leite", "zeige", "bestimme", "skizzier",
               "vergleich", "unterscheide", "ordne", "analysier", "diskutier", "gib ",
               "berechnen sie", "nennen sie", "erklären sie", "erklaeren sie",
               "beschreiben sie", "bestimmen sie", "geben sie", "leiten sie")


def _is_frage(q: str) -> bool:
    if len(q) < 10:
        return False
    if "?" in q:
        return True
    ql = q.lower()
    return any(ql.startswith(v) for v in _IMPERATIVE)


_HEADING_ECHO_FILLER = {
    "was", "ist", "sind", "der", "die", "das", "ein", "eine", "einer",
    "eines", "und", "oder", "wie", "wird", "werden", "bitte", "nenne",
    "erklären", "erklaeren", "erklär", "erklaer", "sie", "den", "dem",
    "im", "in", "zu", "zur", "zum", "von", "vom", "über", "ueber",
    "genau", "bitte", "kurz", "sich",
}


def _normalize_question_text(text: str) -> str:
    s = (text or "").strip().lower()
    s = re.sub(r"[^\wäöüß]+", " ", s)
    return " ".join(s.split())


def _chunk_heading(chunk: str) -> str:
    """Erste Zeile eines Chunks, oft die Markdown-/Abschnitt-Überschrift."""
    first = ""
    for line in (chunk or "").splitlines():
        if line.strip():
            first = line.strip()
            break
    return first.lstrip("#").strip()


def is_heading_echo(question: str, chunk: str) -> bool:
    """True, wenn die Frage nur die Überschrift umformuliert ('Was ist X?')."""
    heading = _chunk_heading(chunk)
    hn = _normalize_question_text(heading)
    qn = _normalize_question_text(question)
    if len(hn) < 6 or not qn:
        return False
    h_content = [w for w in hn.split() if w not in _HEADING_ECHO_FILLER]
    q_content = [w for w in qn.split() if w not in _HEADING_ECHO_FILLER]
    if not h_content:
        return False
    if q_content == h_content:
        return True
    if hn in qn and len(q_content) <= len(h_content) + 1:
        return True
    return False


_SYSTEM = (
    "Du bist ein erfahrener Prüfungs-Coach an einer deutschen Hochschule. "
    "Du formulierst knappe, eigenständige Klausur-/Verständnisfragen auf Deutsch."
)

_PROMPT = """Lies den folgenden Abschnitt aus einer Klausur-Zusammenfassung.

Formuliere genau {n} verschiedene, eigenständige Fragen auf Deutsch, die
AUSSCHLIESSLICH mit den Informationen aus DIESEM Abschnitt beantwortet werden
können. Regeln:
- Jede Frage muss allein aus dem Abschnitt beantwortbar sein (kein Zusatzwissen).
- Verschiedene Aspekte abdecken (Definition, Berechnung, Beispiel, Abgrenzung).
- Natürliche Prüfungssprache, so wie ein Studierender fragen würde.
- Keine Verweise wie "laut Abschnitt" oder "im Text".
- Nicht die Überschrift umformulieren ("Was ist …?" mit dem Abschnittstitel).
  Frage nach einem prüfungsrelevanten Aspekt: Definition in eigenen Worten,
  Berechnung, Abgrenzung, Beispiel, Anwendung.
- Formeln und Gleichungen als LaTeX mit einfachem Backslash, in $...$ (inline)
  oder $$...$$ (abgesetzt). Beispiele: $\\frac{{a}}{{b}}$, $f'(x)=2x$, $[a;b)$.
  Keine Unicode-Brüche und kein „a durch b“, wenn der Abschnitt LaTeX hat.

Abschnitt:
\"\"\"
{chunk}
\"\"\"

Gib NUR gültiges JSON in diesem Format zurück:
{{"questions": ["...", "..."]}}"""


_ANSWER_SYSTEM = (
    "Du bist ein präziser Tutor an einer deutschen Hochschule. Du beantwortest "
    "Prüfungsfragen kurz, korrekt und nur mit dem gegebenen Stoff."
)

_ANSWER_PROMPT = """Beantworte die folgende Prüfungsfrage AUSSCHLIESSLICH mit den
Informationen aus dem gegebenen Abschnitt. Schreibe eine klare, vollständige
Musterlösung auf Deutsch (2–6 Sätze; bei Rechnungen die Schritte). Formeln in
LaTeX (z. B. $\\frac{{a}}{{b}}$). Kein Vorspann wie „Antwort:", keine Verweise auf
„den Abschnitt". Steht die Antwort nicht im Abschnitt, schreibe nur: NICHT_IM_TEXT

Frage:
{frage}

Abschnitt:
\"\"\"
{chunk}
\"\"\"

Musterlösung:"""


def _clean_answer(raw: str) -> str:
    """Vorspann-/Codefence-Reste entfernen; '' wenn leer oder NICHT_IM_TEXT."""
    ans = (raw or "").strip()
    if ans.startswith("```"):
        ans = ans.strip("`").split("\n", 1)[-1].strip()
    for pref in ("Antwort:", "Musterlösung:", "Lösung:"):
        if ans.lower().startswith(pref.lower()):
            ans = ans[len(pref):].strip()
    if not ans or "NICHT_IM_TEXT" in ans:
        return ""
    return ans


def generate_answer(chunk_text: str, question: str, model: str | None = None) -> str:
    """Erzeugt aus Frage + Eltern-Chunk eine echte Musterlösung (statt den rohen Chunk
    als 'Antwort' zu zeigen). Gibt '' zurück, wenn die Antwort nicht im Text steht oder
    leer bleibt. Wirft QuestionGenError bei echtem LLM-/Backend-Fehler.

    Hat die Antwort Mängel (Verweis auf „Definition 4“/„im Kapitel 1.2“, kaputte PDF-Zeichen,
    nur die Frage wiederholt, siehe ``card_quality``), gibt es einen Neuversuch mit gezieltem
    Hinweis; behalten wird der Versuch mit weniger Mängeln."""
    if not (question or "").strip() or not (chunk_text or "").strip():
        return ""
    llm = get_llm(model or settings.LLM_MODEL_FAST)
    prompt = _ANSWER_PROMPT.format(frage=question.strip(), chunk=chunk_text[:2800])

    def _ask(extra: str = "", temperature: float = 0.2) -> str:
        try:
            raw = llm.generate(prompt + extra, system=_ANSWER_SYSTEM, temperature=temperature)
        except Exception as exc:  # echter LLM-/Backend-Fehler -> NICHT verschlucken
            raise QuestionGenError(str(exc)) from exc
        return _clean_answer(raw)

    ans = _ask()
    retries = int(getattr(settings, "CARD_QUALITY_RETRIES", 0) or 0)
    problems = card_quality.answer_problems(ans, question) if ans else []
    for attempt in range(retries):
        if not problems:
            break
        try:
            again = _ask(card_quality.retry_hint(problems), temperature=0.3 + 0.1 * attempt)
        except QuestionGenError:
            break                    # Neuversuch scheitert: die erste Antwort bleibt
        again_problems = card_quality.answer_problems(again, question) if again else problems
        if again and len(again_problems) < len(problems):
            ans, problems = again, again_problems
    return ans


def generate_questions(chunk_text: str, n: int | None = None, model: str | None = None,
                       stats: dict | None = None) -> list[str]:
    """Fragen zu einem Abschnitt. Fragen mit Mängeln (siehe ``card_quality``: Quellenbezug,
    kaputte PDF-Zeichen, fehlender Kontext, zu vage) werden verworfen; fehlen dadurch Fragen,
    gibt es bis zu ``CARD_QUALITY_RETRIES`` Neuversuche mit gezieltem Hinweis. ``stats``
    (optional) sammelt ``rejected`` (verworfene Fragen) und ``retries`` (Neuversuche)."""
    n = n or settings.NUM_INDEX_QUESTIONS
    # Für die Bulk-Fragenerzeugung nutzen wir standardmäßig das schnellere Modell.
    llm = get_llm(model or settings.LLM_MODEL_FAST)
    # sehr kurze Chunks lohnen keine Fragen
    if len(chunk_text.strip()) < settings.MIN_CHUNK_CHARS:
        return []
    retries = max(0, int(getattr(settings, "CARD_QUALITY_RETRIES", 0) or 0))
    out: list[str] = []
    seen: set[str] = set()
    rejected_keys: set[str] = set()
    hint = ""
    for attempt in range(retries + 1):
        want = n - len(out)
        try:
            data = llm.generate_json(
                _PROMPT.format(n=want, chunk=chunk_text[:2500]) + hint,
                system=_SYSTEM,
                temperature=0.3 + 0.15 * attempt,
            )
        except Exception as exc:  # echter LLM-/Backend-Fehler -> NICHT verschlucken
            if attempt == 0:
                raise QuestionGenError(str(exc)) from exc
            break                    # Neuversuch scheitert: behalten, was schon gut ist
        questions = data.get("questions", []) if isinstance(data, dict) else []
        codes: list[str] = []
        for q in questions:
            if not isinstance(q, str):
                continue
            q = q.strip()
            key = q.lower()
            if not q or key in seen or not _is_frage(q) or is_heading_echo(q, chunk_text):
                continue
            problems = card_quality.question_problems(q)
            if problems:
                # Auch eine WIEDERHOLTE schlechte Frage zaehlt als Mangel (Neuversuch noetig),
                # in der Statistik aber nur einmal.
                codes += problems
                if key not in rejected_keys:
                    rejected_keys.add(key)
                    if stats is not None:
                        stats["rejected"] = stats.get("rejected", 0) + 1
                continue
            seen.add(key)
            out.append(q)
        if len(out) >= n or not codes:
            break                    # genug, oder das Modell hat von sich aus zu wenige geliefert
        hint = card_quality.retry_hint(codes)
        if stats is not None and attempt < retries:
            stats["retries"] = stats.get("retries", 0) + 1
    return out[:n]
