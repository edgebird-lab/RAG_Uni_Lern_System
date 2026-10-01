"""Qualitätsprüfung für Karteikarten: Frage und Antwort müssen OHNE das Dokument verständlich sein.

Kleine Modelle formulieren gern „Wie lautet die Definition von OD im Abschnitt?“, „Was zeigt
Abbildung 2?“ oder „… nach Definition 4“ - auf einer Karteikarte, die man unterwegs ohne Skript
durchgeht, ist das wertlos. Dazu kommen kaputte PDF-Zeichen („⎛ ⎞ ⎜⎜⎜“, abgetrennte
Vektorpfeile), Fragen, die an einem Beweisschritt hängen („… die durch die Division bewiesen
wird“), und Dubletten.

Alles hier ist regelbasiert, deterministisch und offline (kein LLM, kein Netz) - nur die
Duplikat-Erkennung nutzt Embeddings, die der Aufrufer hineinreicht. Die Schwellen sind an
echten Karten kalibriert (gemma3:4b, Lineare Algebra, 40 Karten): die beiden echten Dubletten
lagen bei Kosinus 0,94 und 0,90, das nächste verschiedene Paar bei 0,86.

Verwendet von ``ingestion.question_gen`` (verwerfen + neu formulieren lassen),
``ingestion.enrich`` (Dubletten) und der Lernplan-Seite (Prüfung vorhandener Karten).
"""
from __future__ import annotations

import re
from typing import Callable, Optional, Sequence

QUELLENBEZUG = "quellenbezug"
UNLESERLICH = "unleserlich"
KONTEXT = "kontext"
VAGE = "vage"
ZIRKULAER = "zirkulaer"
DUPLIKAT = "duplikat"

LABELS = {
    QUELLENBEZUG: "verweist auf die Quelle (Abschnitt, Abbildung, Definition N …)",
    UNLESERLICH: "enthält kaputte PDF-Zeichen",
    KONTEXT: "hängt von fehlendem Kontext ab (Abbildung, Beweisschritt, „diese …“)",
    VAGE: "zu unbestimmt",
    ZIRKULAER: "Antwort wiederholt nur die Frage",
    DUPLIKAT: "doppelt (fast dieselbe Frage gibt es schon)",
}

# Kosinus-Ähnlichkeit (bge-m3, L2-normalisiert) ab der zwei Fragen als Dublette gelten.
DUP_THRESHOLD = 0.89

_FLAGS = re.IGNORECASE

# --------------------------------------------------------------------------- #
# Quellenbezug
# --------------------------------------------------------------------------- #
_FIG = (r"abbildung|abb\.|bild|grafik|diagramm|skizze|zeichnung|tabelle|tab\.|folie|slide|"
        r"seite|kapitel|abschnitt|aufgabe|beispiel|übung|uebung")
_NUMBERED_FIG = re.compile(rf"\b(?:{_FIG})\s*\d+(?:\.\d+)*\b", _FLAGS)
_NUMBERED_THEOREM = re.compile(
    r"\b(?:satz|definition|lemma|korollar|theorem|proposition|bemerkung|axiom)\s+\d+(?:\.\d+)*\b",
    _FLAGS)
_NUMBERED_EQ = re.compile(
    r"\b(?:formel|gleichung|ungleichung|gl\.)\s*\(\s*\d+(?:\.\d+)*\s*\)", _FLAGS)
_SOURCE_PHRASE = re.compile(
    r"\b(?:im|in diesem|in dem|im folgenden|im obigen|im vorliegenden|im gegebenen|"
    r"im genannten|im betrachteten)\s+(?:abschnitt|text|skript|dokument|kapitel|beispiel|bild|"
    r"textabschnitt|auszug)\b"
    r"|\b(?:laut|gemäß|gemaess|siehe|nach)\s+(?:dem\s+|der\s+|den\s+)?"
    r"(?:text|skript|vorlesung|folie|abschnitt|abbildung|aufgabe|beispiel|unterlagen)\b"
    r"|\b(?:in|auf)\s+(?:der|dieser|folgender|obiger)\s+"
    r"(?:abbildung|grafik|skizze|tabelle|folie|zeichnung|darstellung)\b"
    r"|\b(?:oben|unten)\s+(?:genannt|stehend|beschrieben|angegeben|gezeigt|erwähnt|"
    r"abgebildet|dargestellt)\w*"
    r"|\b(?:obige|obigen|obiger|obiges|untenstehende\w*|obenstehende\w*)\b"
    r"|\b(?:dargestellt|abgebildet|gezeigt|beschrieben|erwähnt|genannt)\s+"
    r"(?:im|in der|in dem|auf der)\b", _FLAGS)

# --------------------------------------------------------------------------- #
# Kaputte PDF-Zeichen
# --------------------------------------------------------------------------- #
# U+239B-23B3: Klammer-/Summen-Bausteine; U+E000-F8FF: Private-Use-Glyphen von PDF-Schriften;
# U+FFFD: Ersatzzeichen; U+20D7: kombinierender Vektorpfeil (landet beim Kopieren aus PDFs
# vom Buchstaben getrennt: "2⃗a +⃗b"); dazu Steuerzeichen.
_GARBLED = re.compile("[⎛-⎳⏐-�⃗\x00-\x08\x0b\x0c\x0e-\x1f]")

# --------------------------------------------------------------------------- #
# Fehlender Kontext (nur Fragen)
# --------------------------------------------------------------------------- #
_DEICTIC_NOUNS = ("abbildung|grafik|skizze|tabelle|formel|gleichung|aufgabe|beispiel|zeichnung|"
                  "darstellung|schritt|umformung|rechnung|herleitung")
_DEICTIC = re.compile(rf"\bdiese[rnms]?\s+({_DEICTIC_NOUNS})\b", _FLAGS)
_CONTEXT = re.compile(
    r"\bin\s+diesem\s+(?:kontext|zusammenhang|fall|schritt|beispiel|abschnitt|kapitel|text)\b"
    r"|\bangegeben\w*"
    r"|\bgegebene[nrsm]?\s+(?:abbildung|skizze|figur|aufgabe|zeichnung|grafik|tabelle|text|beispiel)\b"
    r"|\bbetrachtete[nrsm]?\b"
    r"|,\s*(?:die|der|das|den|dem|welche[rnms]?)\b[^?,;]*"
    r"\b(?:bewiesen|gezeigt|hergeleitet|abgeleitet|erhalten|ermittelt)\s+(?:wird|werden)\b"
    r"|\b(?:wie|was)\s+(?:oben|unten|zuvor|vorher)\b", _FLAGS)

# --------------------------------------------------------------------------- #
# Zu vage / zirkulär
# --------------------------------------------------------------------------- #
_WORD = re.compile(r"[a-zäöüß]{4,}")
_STOP = frozenset((
    "wird", "werden", "sind", "wurde", "wurden", "sein", "welche", "welcher", "welches",
    "welchen", "welchem", "diese", "dieser", "dieses", "diesen", "diesem", "nenne", "nennen",
    "erkläre", "erklären", "erklaere", "erklaeren", "beschreibe", "beschreiben", "definiere",
    "definieren", "berechne", "berechnen", "bestimme", "bestimmen", "gibt", "gebe", "geben",
    "lautet", "lauten", "heißt", "heisst", "versteht", "dass", "wenn", "dann", "auch", "noch",
    "eine", "einer", "eines", "einem", "einen", "oder", "sich", "nicht", "kann", "können",
    "koennen", "wieso", "warum", "weshalb", "wozu", "wann", "dies", "dazu", "dabei", "damit",
    "dafür", "dafuer", "durch", "für", "fuer", "mit", "von", "vom", "zum", "zur", "über",
    "ueber", "unter", "nach", "bei", "aus", "wie", "was", "wer", "wo",
    # Allerweltsverben/-fuellwoerter: sie machen eine Frage nicht konkret
    "funktioniert", "funktionieren", "kurz", "genau", "bedeutet", "bedeuten", "gilt", "gelten",
    "passiert", "geschieht", "ergibt", "ergeben", "macht", "machen", "stimmt", "erklärt",
    "erklaert", "sagen", "sagt", "meint", "meinen", "bitte", "einfach", "etwas", "alles",
    "ganz", "mehr", "sehr"))
_MATH = re.compile(r"[$=<>≤≥≈∑∫√±^_\\]|\d")


def _content_words(text: str) -> list[str]:
    return [w for w in _WORD.findall((text or "").lower()) if w not in _STOP]


def _has_math(text: str) -> bool:
    return bool(_MATH.search(text or ""))


# --------------------------------------------------------------------------- #
# Öffentliche Prüfungen
# --------------------------------------------------------------------------- #
def _source_reference(text: str) -> bool:
    return bool(_NUMBERED_FIG.search(text) or _NUMBERED_THEOREM.search(text)
                or _NUMBERED_EQ.search(text) or _SOURCE_PHRASE.search(text))


def _lacks_context(question: str) -> bool:
    if _CONTEXT.search(question):
        return True
    low = question.lower()
    for m in _DEICTIC.finditer(question):
        # „diese Formel“ ist in Ordnung, wenn die Frage die Formel vorher selbst nennt.
        if m.group(1).lower() not in low[:m.start()]:
            return True
    return False


def question_problems(question: str) -> list[str]:
    """Mängel einer Kartenfrage (leer = in Ordnung): ``quellenbezug``, ``unleserlich``,
    ``kontext``, ``vage``."""
    q = (question or "").strip()
    out: list[str] = []
    if not q:
        return [VAGE]
    if _source_reference(q):
        out.append(QUELLENBEZUG)
    if _GARBLED.search(q):
        out.append(UNLESERLICH)
    if _lacks_context(q):
        out.append(KONTEXT)
    if not _content_words(q) and not _has_math(q):
        out.append(VAGE)
    return out


def answer_problems(answer: str, question: str = "") -> list[str]:
    """Mängel einer Musterlösung: ``quellenbezug``, ``unleserlich``, ``zirkulaer``."""
    a = (answer or "").strip()
    if not a:
        return []
    out: list[str] = []
    if _source_reference(a):
        out.append(QUELLENBEZUG)
    if _GARBLED.search(a):
        out.append(UNLESERLICH)
    if question and not _has_math(a):
        a_words = _content_words(a)
        if len(a_words) >= 3:
            q_stems = {w[:5] for w in _content_words(question)}
            new = [w for w in a_words if w[:5] not in q_stems]
            if len(new) / len(a_words) <= 0.15:
                out.append(ZIRKULAER)
    return out


_RETRY_HINTS = {
    QUELLENBEZUG: ("Keine Verweise auf Abschnitte, Abbildungen, Seiten, Formel- oder "
                   "Definitionsnummern (z. B. „im Abschnitt“, „Abbildung 2“, „Definition 4“) - "
                   "nenne stattdessen den Inhalt selbst."),
    UNLESERLICH: ("Schreibe Formeln und Vektoren als LaTeX in $...$ (z. B. $\\vec{v}$), keine "
                  "Sonderzeichen aus PDF-Schriften."),
    KONTEXT: ("Die Frage muss ohne Abbildung, Beispiel oder vorherigen Rechenschritt "
              "verständlich sein: benenne Begriffe und Größen ausdrücklich, kein „diese …“, "
              "„angegebene …“, „betrachtete …“, „in diesem Kontext“."),
    VAGE: "Die Frage muss einen konkreten Begriff oder eine konkrete Größe nennen.",
    ZIRKULAER: "Die Antwort muss neue Information enthalten und darf die Frage nicht nur wiederholen.",
}


def retry_hint(codes: Sequence[str]) -> str:
    """Zusatzanweisung für den Neuversuch, passend zu den festgestellten Mängeln."""
    lines = [_RETRY_HINTS[c] for c in dict.fromkeys(codes) if c in _RETRY_HINTS]
    if not lines:
        return ""
    return ("\n\nWICHTIG - der letzte Versuch hatte Mängel. Beachte jetzt:\n"
            + "\n".join(f"- {t}" for t in lines))


def describe(codes: Sequence[str]) -> str:
    """Lesbare Kurzform für die Oberfläche: „verweist auf die Quelle …; doppelt …“."""
    return "; ".join(LABELS.get(c, c) for c in dict.fromkeys(codes))


# --------------------------------------------------------------------------- #
# Dubletten (Embeddings kommen vom Aufrufer)
# --------------------------------------------------------------------------- #
def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Kosinus-Ähnlichkeit. Die Embeddings der App sind L2-normalisiert (Skalarprodukt reicht),
    hier wird trotzdem normiert, damit die Funktion auch für andere Vektoren stimmt."""
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def is_duplicate(vec: Sequence[float], others: Sequence[Sequence[float]],
                 threshold: float = DUP_THRESHOLD) -> bool:
    """Ist ``vec`` einer der ``others`` fast gleich?"""
    return any(cosine(vec, o) >= threshold for o in others)


def find_duplicates(items: Sequence[tuple[str, str]],
                    embed: Callable[[list[str]], list[list[float]]],
                    threshold: float = DUP_THRESHOLD) -> dict[str, str]:
    """``items`` = ``[(id, Frage), …]`` in der Reihenfolge, in der die ERSTE behalten wird.
    Gibt ``{spätere_id: frühere_id}`` zurück: welche Karten Dubletten welcher früheren sind."""
    if len(items) < 2:
        return {}
    vecs = embed([t for _, t in items])
    kept: list[tuple[str, Sequence[float]]] = []
    dups: dict[str, str] = {}
    for (cid, _), v in zip(items, vecs):
        match = next((kid for kid, kv in kept if cosine(v, kv) >= threshold), None)
        if match is None:
            kept.append((cid, v))
        else:
            dups[cid] = match
    return dups


# --------------------------------------------------------------------------- #
# Prüfung vorhandener Karten
# --------------------------------------------------------------------------- #
def audit_cards(cards: Sequence[dict], *,
                embed: Optional[Callable[[list[str]], list[list[float]]]] = None,
                threshold: float = DUP_THRESHOLD) -> dict[str, dict[str, list[str]]]:
    """Prüft KI-generierte Karten (``source == "question"``). Ergebnis nur für auffällige Karten:
    ``{card_id: {"question": [Mängel], "answer": [Mängel]}}`` - getrennt, weil ein Mangel nur in
    der Antwort (Verweis auf „Definition 4“) bedeutet: Antwort neu erzeugen, Frage behalten;
    ein Mangel in der Frage: Karte ersetzen. Mit ``embed`` werden zusätzlich Dubletten je Dokument
    erkannt (Mangel ``duplikat`` an der Frage; die spätere Karte gilt als Dublette, Reihenfolge =
    Reihenfolge von ``cards``)."""
    flagged: dict[str, dict[str, list[str]]] = {}
    gen = [c for c in cards if (c.get("source") or "") == "question"]
    for c in gen:
        q_codes = question_problems(c.get("front") or "")
        a_codes = answer_problems(c.get("answer") or "", c.get("front") or "")
        if q_codes or a_codes:
            flagged[c["card_id"]] = {"question": q_codes, "answer": a_codes}
    if embed is not None:
        by_doc: dict[Optional[str], list[tuple[str, str]]] = {}
        for c in gen:
            by_doc.setdefault(c.get("doc_id"), []).append((c["card_id"], c.get("front") or ""))
        for items in by_doc.values():
            for dup in find_duplicates(items, embed, threshold):
                entry = flagged.setdefault(dup, {"question": [], "answer": []})
                if DUPLIKAT not in entry["question"]:
                    entry["question"].append(DUPLIKAT)
    return flagged


def describe_audit(entry: dict[str, list[str]]) -> str:
    """Eintrag von ``audit_cards`` lesbar: „Frage: … · Antwort: …“."""
    parts = []
    if entry.get("question"):
        parts.append("Frage: " + describe(entry["question"]))
    if entry.get("answer"):
        parts.append("Antwort: " + describe(entry["answer"]))
    return " · ".join(parts)
