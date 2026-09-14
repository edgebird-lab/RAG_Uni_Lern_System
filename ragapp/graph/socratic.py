"""Hilfen fuer den sokratischen Dialog (Themenvorschläge aus dem Stoff).

Die Chat-UI darf keine Dateinamen als Themen anbieten – sonst fragt das Modell
nach dem Stem ('Wie wird Livetest_Definitionen beschrieben?') statt nach einem
pruefbaren Begriff. Karten-Themen und Markdown-Ueberschriften sind der Stoff.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional

# Zu generisch oder Fixture-/Fachlabel – nie als Dialogthema vorschlagen.
_GENERIC_LABELS = {
    "anleitung", "begriffskarten", "definitionen", "einleitung", "formeln",
    "inhalt", "inhaltsverzeichnis", "livetest", "livetest-leer",
    "uebersicht", "übersicht", "zusammenfassung",
}

_FRONT_RES = (
    re.compile(r"^was ist (?:der|die|das)\s+(.+?)\s*\??$", re.IGNORECASE),
    re.compile(r"^was ist (?:ein|eine)\s+(.+?)\s*\??$", re.IGNORECASE),
    re.compile(r"^was ist\s+(.+?)\s*\??$", re.IGNORECASE),
    re.compile(r"^was bedeutet\s+(.+?)(?:\s+in\b.*)?\s*\??$", re.IGNORECASE),
    re.compile(r"^was versteht man unter\s+(?:dem|der|den|die)?\s*(.+?)\s*\??$",
               re.IGNORECASE),
    re.compile(r"^erkläre\s+(?:den|die|das)\s+(.+?)\s*\??$", re.IGNORECASE),
    re.compile(r"^erklaere\s+(?:den|die|das)\s+(.+?)\s*\??$", re.IGNORECASE),
)

_NOUN_VON_RE = re.compile(
    r"^([A-ZÄÖÜ][\w\-]*(?:\s+[A-ZÄÖÜ][\w\-]*)?)\s+von\b")
_HEADING_RE = re.compile(r"^#{2,3}\s+(.+?)\s*$", re.MULTILINE)
_NUM_HEAD_RE = re.compile(
    r"^(?:\d+(?:\.\d+){0,3})[.)]?\s+(.{4,48})\s*$", re.MULTILINE)
_LATEX_RE = re.compile(r"\$[^$]*\$")
_FILENAME_LIKE_RE = re.compile(r"^[A-Za-z0-9ÄÖÜäöüß]+(?:_[A-Za-z0-9ÄÖÜäöüß]+)+$")
# PDF-Lesezeichen heissen oft nur "Seite 12" / "Folie 3" – kein Dialogthema.
_PAGE_LABEL_RE = re.compile(
    r"^(?:seite|page|folie|slide|abschnitt|kapitel|chapter)\s*\d+$", re.I)


def filename_stem(name: str) -> str:
    raw = (name or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if raw.lower().endswith(".md"):
        raw = raw[:-3]
    elif "." in raw:
        raw = raw.rsplit(".", 1)[0]
    return raw.strip()


def _strip_subject_prefix(text: str, subject: Optional[str]) -> str:
    t = (text or "").strip()
    subj = (subject or "").strip()
    if subj and t.lower().startswith(subj.lower() + ":"):
        t = t[len(subj) + 1:].strip()
    return t


def topic_from_front(front: str, *, subject: Optional[str] = None) -> str:
    """Zieht ein kurzes Begriffslabel aus einer Kartenfrage, sonst leer."""
    raw = _strip_subject_prefix(_LATEX_RE.sub(" ", front or "").strip(), subject)
    raw = re.sub(r"\s+", " ", raw).strip().rstrip("?.!")
    if not raw:
        return ""
    for pat in _FRONT_RES:
        m = pat.match(raw + "?")
        if m:
            return (m.group(1) or "").strip().rstrip("?.!")
    m = _NOUN_VON_RE.match(raw)
    if m:
        return m.group(1).strip()
    return ""


def is_page_label(label: str) -> bool:
    """True für PDF-Platzhalter wie 'Seite 7' / 'Folie 3' – kein Stoffname."""
    return bool(_PAGE_LABEL_RE.match((label or "").strip()))


def is_usable_topic(label: str, *, subject: Optional[str] = None,
                    filename_stems: Optional[Iterable[str]] = None) -> bool:
    name = re.sub(r"\s+", " ", (label or "").strip())
    if len(name) < 3 or len(name) > 48:
        return False
    key = name.lower()
    if key in _GENERIC_LABELS:
        return False
    if is_page_label(name):
        return False
    subj = (subject or "").strip().lower()
    if subj and (key == subj or key.startswith(subj + " ") or key.startswith(subj + "-")):
        return False
    if "livetest" in key:
        return False
    if _FILENAME_LIKE_RE.match(name):
        return False
    stems = {filename_stem(s).lower() for s in (filename_stems or []) if s}
    if key in stems:
        return False
    return True


def _add(out: list[str], seen: set[str], label: str, *, subject: Optional[str],
         stems: Iterable[str], limit: int) -> bool:
    name = re.sub(r"\s+", " ", (label or "").strip())
    if not is_usable_topic(name, subject=subject, filename_stems=stems):
        return len(out) >= limit
    key = name.lower()
    if key in seen:
        return len(out) >= limit
    seen.add(key)
    out.append(name)
    return len(out) >= limit


def topics_from_markdown(md: str, *, subject: Optional[str] = None,
                         filename_stems: Optional[Iterable[str]] = None,
                         limit: int = 9) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    stems = list(filename_stems or [])
    for m in _HEADING_RE.finditer(md or ""):
        if _add(out, seen, m.group(1), subject=subject, stems=stems, limit=limit):
            break
    if len(out) >= limit:
        return out
    for m in _NUM_HEAD_RE.finditer(md or ""):
        if _add(out, seen, m.group(1), subject=subject, stems=stems, limit=limit):
            break
    return out


def pdf_toc_titles(source_path: str, *, root: Path) -> list[str]:
    """PDF-Lesezeichen (Inhaltsverzeichnis), ohne den ganzen Text zu laden."""
    p = Path(source_path)
    if not p.is_absolute():
        p = root / p
    if not p.is_file() or p.suffix.lower() != ".pdf":
        return []
    try:
        import fitz
        doc = fitz.open(p)
        toc = doc.get_toc() or []
        doc.close()
    except Exception:
        return []
    out: list[str] = []
    for level, title, _page in toc:
        if int(level or 99) > 2:
            continue
        title = (title or "").strip()
        if title:
            out.append(title)
        if len(out) >= 24:
            break
    return out


def collect_socratic_topic_suggestions(
    *,
    cards: Iterable[Mapping],
    documents: Optional[Iterable[Mapping]] = None,
    subject: Optional[str] = None,
    read_text: Optional[Callable[[str], str]] = None,
    extra_headings: Optional[Iterable[str]] = None,
    limit: int = 9,
) -> list[str]:
    """Themen aus Karten, Markdown-/PDF-Ueberschriften, Dateinamen nie."""
    docs = [dict(d) for d in (documents or [])]
    if subject:
        docs = [d for d in docs if d.get("subject") == subject]
    stems = [filename_stem(str(d.get("filename") or "")) for d in docs]
    out: list[str] = []
    seen: set[str] = set()

    for card in cards:
        if _add(out, seen, str(card.get("topic") or ""),
                subject=subject, stems=stems, limit=limit):
            return out
        label = topic_from_front(str(card.get("front") or ""), subject=subject)
        if _add(out, seen, label, subject=subject, stems=stems, limit=limit):
            return out

    if read_text is not None:
        for doc in docs:
            if len(out) >= limit:
                break
            name = str(doc.get("filename") or "")
            path = str(doc.get("source_path") or "")
            if not path:
                continue
            if name.lower().endswith(".pdf"):
                continue
            try:
                text = read_text(path) or ""
            except OSError:
                continue
            for heading in topics_from_markdown(
                    text, subject=subject, filename_stems=stems, limit=limit):
                if _add(out, seen, heading, subject=subject, stems=stems, limit=limit):
                    return out

    for heading in extra_headings or []:
        if _add(out, seen, heading, subject=subject, stems=stems, limit=limit):
            return out
    return out


def chat_onboarding_questions(
        topics: Iterable[str], *, subject_label: str | None = None) -> list[str]:
    """Einstiegsfragen fuer den leeren Chat: Stoff des Filters, sonst allgemein."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in topics or []:
        topic = (raw or "").strip()
        if not topic:
            continue
        key = topic.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(topic)
        if len(cleaned) >= 3:
            break
    if cleaned:
        first, last = cleaned[0], cleaned[-1]
        second = cleaned[1] if len(cleaned) > 1 else first
        return [
            f"Was ist {first}?",
            f"Erkläre {second} einfach und mit Beispiel.",
            f"Was sollte ich zu {last} für die Klausur wiederholen?",
        ]
    if subject_label:
        return [
            f"Was sind die wichtigsten Themen in {subject_label}?",
            f"Erkläre mir ein zentrales Konzept aus {subject_label} einfach und mit Beispiel.",
            f"Was sollte ich in {subject_label} für die Klausur unbedingt wiederholen?",
        ]
    return [
        "Was sind die wichtigsten Themen in meinen Unterlagen?",
        "Erkläre mir ein zentrales Konzept einfach und mit Beispiel.",
        "Was sollte ich für die Klausur unbedingt wiederholen?",
    ]


def read_source_text(source_path: str, *, root: Path) -> str:
    """Liest eine Unterlage relativ zum Projektroot, gekappt fuer Ueberschriften."""
    p = Path(source_path)
    if not p.is_absolute():
        p = root / p
    if not p.is_file():
        return ""
    return p.read_text(encoding="utf-8", errors="ignore")[:12_000]
