"""
Anki-Export (.apkg)
====================
Exportiert deine Karteikarten als Anki-Deck, damit du sie unterwegs mit
AnkiDroid/AnkiMobile lernen kannst - KOMPLETT ohne diesen Server/PC und ohne
jedes lokale Modell. Reiner Inhalts-Export (Frage/Antwort): der Lernfortschritt
(FSRS-6-Zustand, Klausurtermin-Planung) bleibt HIER die Quelle der Wahrheit -
Anki bekommt die Karten als "neu" und plant sie mit seinem eigenen Scheduler.

Deck- und Notiz-IDs werden aus dem Namen bzw. Kartentext deterministisch
abgeleitet (stabiler CRC32/genanki-Hash, NICHT Pythons salted ``hash()``), damit
ein wiederholter Export/Import in Anki als Update erkannt wird statt als Dubletten.
"""
from __future__ import annotations

import html
import io
import zlib

from ragapp import manifest
from ragapp.config import SUBJECT_LABELS

_MODEL_ID = 1607392319          # feste ID: alle Karten teilen sich einen Kartentyp
_DECK_ID_BASE = 1901810100


def _fach_label(code: str) -> str:
    return SUBJECT_LABELS.get(code, code)


def _deck_id(name: str) -> int:
    """Stabiler Deck-ID aus dem Namen (im Gegensatz zu Pythons ``hash()`` ueber
    Prozess-Neustarts hinweg identisch) - so erkennt Anki denselben Stapel wieder."""
    return _DECK_ID_BASE + (zlib.crc32(name.encode("utf-8")) % 1_000_000)


def _card_html(text: str) -> str:
    return html.escape(text or "").replace("\n", "<br>")


def build_apkg(subject: "str | None" = None, deck: "str | None" = None) -> "tuple[bytes, int]":
    """Baut ein .apkg aus den (gefilterten) Karten. Ueberspringt pausierte Karten und
    solche, die in der App vom Abfragen ausgeschlossen sind (``use_flashcard=0``)
    sowie Karten ohne Antwort. Gibt (Datei-Bytes, Anzahl exportierter Karten) zurueck.

    Wirft ``ModuleNotFoundError``, wenn ``genanki`` nicht installiert ist (siehe
    requirements.txt)."""
    import genanki

    rows = manifest.list_cards(subject=subject, deck=deck)
    model = genanki.Model(
        _MODEL_ID, "RAG-Lernsystem Basic",
        fields=[{"name": "Front"}, {"name": "Back"}],
        templates=[{
            "name": "Karte",
            "qfmt": "{{Front}}",
            "afmt": '{{FrontSide}}<hr id="answer">{{Back}}',
        }],
    )

    decks: dict[str, "genanki.Deck"] = {}
    n = 0
    for r in rows:
        if r.get("suspended") or not r.get("use_flashcard", 1):
            continue
        front = (r.get("front") or "").strip()
        # Bevorzugt die echte Antwort; nur ohne generierte Antwort der Beleg-Chunk
        # als Notbehelf (gleiche Regel wie auf der Seite "Lernen").
        back = (r.get("answer") or r.get("back") or "").strip()
        if not front or not back:
            continue
        deck_name = "RAG-Lernsystem::" + _fach_label(r.get("subject") or "Ohne Fach")
        if r.get("deck"):
            deck_name += "::" + r["deck"]
        if deck_name not in decks:
            decks[deck_name] = genanki.Deck(_deck_id(deck_name), deck_name)
        decks[deck_name].add_note(
            genanki.Note(model=model, fields=[_card_html(front), _card_html(back)]))
        n += 1

    buf = io.BytesIO()
    genanki.Package(list(decks.values())).write_to_file(buf)
    return buf.getvalue(), n
