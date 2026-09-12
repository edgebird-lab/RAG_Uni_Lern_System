"""
Lerndeck teilen (Export/Import fuer Lerngruppen)
=================================================
Karten mit Kommilitonen teilen, ganz ohne Server/Konto/Sync-Dienst: ein
Export buendelt Frage/Antwort/Thema/Stapel als portable JSON-Datei, ein
Kommilitone importiert sie in SEINER EIGENEN Instanz dieser App. Bewusst kein
Live-Sync (der wuerde einen eigenen Server + Nutzerverwaltung brauchen und
stuende quer zum Offline-/Einzelplatz-Grundsatz der App) - Export/Import ist
das naheliegende Muster, das schon beim Anki-Export etabliert ist.

Unterschied zum Anki-Export (ragapp/export_anki.py): dieses Format bleibt IN
der App (der Empfaenger lernt weiter mit FSRS-6/Klausurplanung/Gamification
statt in Anki) und ist absichtlich NICHT an eine bestimmte Karten-ID/ein
bestimmtes Fach des Exporteurs gebunden - der Import fragt aktiv, welchem
EIGENEN Fach die Karten zugeordnet werden sollen, statt das Fach des
Exporteurs unbesehen zu uebernehmen (dessen interne Fach-Codes muessen beim
Empfaenger nicht existieren oder dasselbe bedeuten).

Der Lernfortschritt (FSRS-Zustand) wird NIE mit exportiert - fuer eine andere
Person waere er ohnehin bedeutungslos; importierte Karten starten immer als
"neu".
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Optional

from ragapp import manifest
from ragapp.config import SUBJECT_LABELS

_FORMAT = "rag-lernsystem-deck-v1"


def build_deck_export(subject: Optional[str] = None, deck: Optional[str] = None) -> tuple[bytes, int]:
    """Baut die JSON-Exportdatei aus den (gefilterten) Karten. Gibt
    (Datei-Bytes, Anzahl exportierter Karten) zurueck. Ueberspringt Karten
    ohne Antwort - ohne Beleg-Chunk-Kontext waere der reine Originaltext fuer
    einen Kommilitonen oft nicht verstaendlich."""
    rows = manifest.list_cards(subject=subject, deck=deck)
    cards: list[dict[str, Any]] = []
    for r in rows:
        front = (r.get("front") or "").strip()
        answer = (r.get("answer") or "").strip()
        if not front or not answer:
            continue
        cards.append({
            "front": front, "answer": answer,
            "topic": r.get("topic") or None, "deck": r.get("deck") or None,
        })
    payload = {
        "format": _FORMAT,
        "exported_at": time.time(),
        "subject_label": SUBJECT_LABELS.get(subject, subject) if subject else "Mehrere Fächer",
        "cards": cards,
    }
    return json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8"), len(cards)


def parse_deck_import(content: bytes) -> dict[str, Any]:
    """Liest eine exportierte Lerndeck-Datei fuer eine Vorschau vor dem Import
    (schreibt selbst nichts). Wirft ``ValueError`` bei falschem Format/kaputtem
    Inhalt - der Aufrufer faengt das ab und zeigt eine Fehlermeldung (siehe
    Fortschritt.py)."""
    try:
        data = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Das ist keine gültige Lerndeck-Datei (kein lesbares JSON).") from exc
    if not isinstance(data, dict) or data.get("format") != _FORMAT:
        raise ValueError("Das ist keine gültige Lerndeck-Datei (falsches Format).")
    raw_cards = data.get("cards")
    if not isinstance(raw_cards, list):
        raise ValueError("Keine Karten in dieser Datei gefunden.")
    cleaned: list[dict[str, Any]] = []
    for c in raw_cards:
        if not isinstance(c, dict):
            continue
        front = (c.get("front") or "").strip()
        answer = (c.get("answer") or "").strip()
        if not front or not answer:
            continue
        cleaned.append({
            "front": front, "answer": answer,
            "topic": (c.get("topic") or "").strip() or None,
            "deck": (c.get("deck") or "").strip() or None,
        })
    return {"subject_label": str(data.get("subject_label") or ""), "cards": cleaned}


def import_deck_cards(cards: list[dict[str, Any]], *, subject: str) -> int:
    """Legt die importierten Karten als NEUE Karteikarten im gewaehlten
    (eigenen) Fach an - IMMER frische ``card_id``s (fremde Karten sind nie
    identisch mit einer bestehenden eigenen Karte). Ordnet anschliessend
    Karten mit gesetztem ``deck`` demselben Stapel-Namen zu (zweischrittig,
    gleiches Muster wie beim manuellen Anlegen - siehe manifest.assign_deck()).
    Gibt die Anzahl angelegter Karten zurueck."""
    to_create = []
    for c in cards:
        to_create.append({
            "card_id": uuid.uuid4().hex[:16], "source": "import", "chroma_id": None,
            "subject": subject, "topic": c.get("topic"),
            "front": c["front"], "back": c["answer"], "answer": c["answer"],
            "doc_id": None,
        })
    n = manifest.upsert_review_items(to_create)
    by_deck: dict[str, list[str]] = {}
    for c, created in zip(cards, to_create):
        if c.get("deck"):
            by_deck.setdefault(c["deck"], []).append(created["card_id"])
    for deck_name, ids in by_deck.items():
        manifest.assign_deck(deck_name, card_ids=ids)
    return n
