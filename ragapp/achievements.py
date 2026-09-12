"""
Errungenschaften-Katalog (Gamification)
=========================================
Ein kleiner, aber vollständiger Katalog echter Meilensteine - jede
Errungenschaft bezieht sich auf eine bereits vorhandene, echte Kennzahl
(Streak, Wiederholungen insgesamt, Mastery, Probeklausur-Ergebnis,
abgeschlossener Lernplan, erste eigene Notiz). Einmal freigeschaltet, bleibt
sie für immer freigeschaltet (siehe ``manifest.achievements``) - Sammeln als
Belohnungsprinzip statt eines beliebigen, bedeutungslosen Punktestands.

``check_and_unlock()`` wird opportunistisch aufgerufen (z. B. beim Laden der
Startseite) - kein Hintergrund-Job nötig, eine leichte Prüfung bei ohnehin
schon geladenen Seiten reicht völlig.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ragapp import analytics, manifest


@dataclass(frozen=True)
class Achievement:
    id: str
    icon: str
    title: str
    description: str
    check: Callable[[], bool]


def _mastery_at_least(pct: int) -> bool:
    return any(m["mastery_pct"] >= pct for m in analytics.mastery_by_subject())


def _has_done_plan() -> bool:
    return any(p["status"] == "done" for p in manifest.list_study_plans())


def _has_passed_exam(min_pct: int = 75) -> bool:
    best = manifest.best_exam_pct()
    return best is not None and best >= min_pct


def catalog() -> list[Achievement]:
    """Baut den Katalog frisch auf - die ``check``-Funktionen greifen live auf
    die aktuellen Daten zu, es gibt keinen zwischengespeicherten Zustand
    außer dem, was schon freigeschaltet IST (siehe manifest.achievements)."""
    ov = analytics.overview(None)
    return [
        Achievement("streak_7", "🔥", "Eine Woche dran geblieben",
                   "7 Tage in Folge gelernt.", lambda: ov["streak"] >= 7),
        Achievement("streak_30", "🔥🔥", "Ein Monat Konstanz",
                   "30 Tage in Folge gelernt.", lambda: ov["streak"] >= 30),
        Achievement("streak_100", "🔥🔥🔥", "Hundert Tage",
                   "100 Tage in Folge gelernt.", lambda: ov["streak"] >= 100),
        Achievement("cards_100", "🎴", "Hundert Wiederholungen",
                   "100 Karten insgesamt geübt.",
                   lambda: analytics.total_reviews_count() >= 100),
        Achievement("cards_1000", "🎴🎴", "Tausend Wiederholungen",
                   "1000 Karten insgesamt geübt.",
                   lambda: analytics.total_reviews_count() >= 1000),
        Achievement("mastery_90", "🎯", "Ein Fach sitzt",
                   "Mindestens 90 % Sitzt-Anteil in einem Fach.",
                   lambda: _mastery_at_least(90)),
        Achievement("plan_done", "📋", "Lernplan durchgezogen",
                   "Einen kompletten Lernplan abgeschlossen.", _has_done_plan),
        Achievement("exam_passed", "📝", "Probeklausur bestanden",
                   "Eine Probeklausur mit mindestens 75 % abgeschlossen.",
                   _has_passed_exam),
        Achievement("first_note", "🗒️", "Erste eigene Notiz",
                   "Die erste eigene Notiz angelegt.",
                   lambda: bool(manifest.list_notes(limit=1))),
    ]


def check_and_unlock() -> list[Achievement]:
    """Prüft den ganzen Katalog gegen den aktuellen Datenstand und schaltet
    neu erreichte Errungenschaften frei. Gibt NUR die JETZT NEU
    freigeschalteten zurück (für eine Feier-Anzeige) - bereits vorher
    freigeschaltete werden nicht erneut gemeldet. Eine einzelne kaputte
    Prüfung darf die Seite, von der aus das aufgerufen wird, nie crashen."""
    newly: list[Achievement] = []
    for ach in catalog():
        try:
            if ach.check() and manifest.unlock_achievement(ach.id):
                newly.append(ach)
        except Exception:  # noqa: BLE001
            continue
    return newly
