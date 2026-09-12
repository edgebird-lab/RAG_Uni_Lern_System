"""
Errungenschaften-Katalog (Gamification)
=========================================
Ein kleiner, aber vollständiger Katalog echter Meilensteine - jede
Errungenschaft bezieht sich auf eine bereits vorhandene, echte Kennzahl
(Streak, Wiederholungen insgesamt, Mastery, Probeklausur-Ergebnis,
abgeschlossener Lernplan, erste eigene Notiz, Wochenend-Konsistenz). Einmal
freigeschaltet, bleibt sie für immer freigeschaltet (siehe
``manifest.achievements``) - Sammeln als Belohnungsprinzip statt eines
beliebigen, bedeutungslosen Punktestands.

Zwei Kategorien von Zusatz-Feldern:
- ``progress`` (optional): liefert (aktuell, ziel) für eine ehrliche
  Fortschrittsanzeige VOR dem Freischalten (siehe ``nearest_locked()`` und
  die Anzeige auf Fortschritt) - nur dort gesetzt, wo ein echter Zahlenwert
  sinnvoll ist (nicht bei reinen Ja/Nein-Meilensteinen wie "erste Notiz").
- ``hidden`` (optional): eine ÜBERRASCHUNGS-Errungenschaft, die VOR dem
  Freischalten nicht mit Titel/Beschreibung verraten wird (siehe Anzeige auf
  Fortschritt) - bewusst sehr sparsam eingesetzt (siehe Docstring der
  einzelnen ``hidden=True``-Einträge), sonst verwässert es den seriösen Kern.

``context`` (optional, nur von ragapp/ui/pages/4_🎓_Lernen.py am Ende einer
Lernrunde befüllt) trägt EPHEMERE Rundendaten, die nirgends persistiert
werden (z. B. "war die ganze Runde fehlerfrei?") - Errungenschaften, die
sowas prüfen wollen, lesen ausschliesslich aus diesem Dict und schlagen ohne
Kontext (z. B. beim Check auf Fortschritt/Home) einfach nie an.

``check_and_unlock()`` wird opportunistisch aufgerufen (Home, Fortschritt,
Rundenende in Lernen) - kein Hintergrund-Job nötig, eine leichte Prüfung bei
ohnehin schon geladenen Seiten reicht völlig.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from ragapp import analytics, manifest


@dataclass(frozen=True)
class Achievement:
    id: str
    icon: str
    title: str
    description: str
    check: Callable[[], bool]
    progress: Optional[Callable[[], tuple[float, float]]] = None
    hidden: bool = False


def _mastery_at_least(pct: int) -> bool:
    return any(m["mastery_pct"] >= pct for m in analytics.mastery_by_subject())


def _best_mastery() -> float:
    masteries = analytics.mastery_by_subject()
    return max((m["mastery_pct"] for m in masteries), default=0.0)


def _has_done_plan() -> bool:
    return any(p["status"] == "done" for p in manifest.list_study_plans())


def _has_passed_exam(min_pct: int = 75) -> bool:
    best = manifest.best_exam_pct()
    return best is not None and best >= min_pct


def catalog(context: Optional[dict] = None) -> list[Achievement]:
    """Baut den Katalog frisch auf - die ``check``-Funktionen greifen live auf
    die aktuellen Daten zu, es gibt keinen zwischengespeicherten Zustand
    außer dem, was schon freigeschaltet IST (siehe manifest.achievements).
    ``context`` siehe Modul-Docstring - ohne Kontext liefern die beiden
    rundenbasierten Errungenschaften (perfect_round/leech_buster) einfach
    ``False``."""
    ov = analytics.overview(None)
    ctx = context or {}
    return [
        Achievement("streak_7", "🔥", "Eine Woche dran geblieben",
                   "7 Tage in Folge gelernt.", lambda: ov["streak"] >= 7,
                   progress=lambda: (ov["streak"], 7)),
        Achievement("streak_30", "🔥🔥", "Ein Monat Konstanz",
                   "30 Tage in Folge gelernt.", lambda: ov["streak"] >= 30,
                   progress=lambda: (ov["streak"], 30)),
        Achievement("streak_100", "🔥🔥🔥", "Hundert Tage",
                   "100 Tage in Folge gelernt.", lambda: ov["streak"] >= 100,
                   progress=lambda: (ov["streak"], 100)),
        Achievement("cards_100", "🎴", "Hundert Wiederholungen",
                   "100 Karten insgesamt geübt.",
                   lambda: analytics.total_reviews_count() >= 100,
                   progress=lambda: (analytics.total_reviews_count(), 100)),
        Achievement("cards_1000", "🎴🎴", "Tausend Wiederholungen",
                   "1000 Karten insgesamt geübt.",
                   lambda: analytics.total_reviews_count() >= 1000,
                   progress=lambda: (analytics.total_reviews_count(), 1000)),
        Achievement("mastery_90", "🎯", "Ein Fach sitzt",
                   "Mindestens 90 % Sitzt-Anteil in einem Fach.",
                   lambda: _mastery_at_least(90),
                   progress=lambda: (_best_mastery(), 90)),
        Achievement("plan_done", "📋", "Lernplan durchgezogen",
                   "Einen kompletten Lernplan abgeschlossen.", _has_done_plan),
        Achievement("exam_passed", "📝", "Probeklausur bestanden",
                   "Eine Probeklausur mit mindestens 75 % abgeschlossen.",
                   _has_passed_exam,
                   progress=lambda: (manifest.best_exam_pct() or 0, 75)),
        Achievement("first_note", "🗒️", "Erste eigene Notiz",
                   "Die erste eigene Notiz angelegt.",
                   lambda: bool(manifest.list_notes(limit=1))),
        Achievement("weekend_study", "🏖️", "Kein Wochenende verschont",
                   "An einem Samstag UND dem folgenden Sonntag gelernt.",
                   analytics.has_full_weekend_study),
        # ---- rundenbasiert: nur mit context aus dem Rundenende in Lernen ----
        Achievement("perfect_round", "💯", "Perfekte Runde",
                   "Eine Lernrunde mit mindestens 10 Karten – alle gewusst.",
                   lambda: (ctx.get("round_total", 0) >= 10
                           and ctx.get("round_gewusst", 0) == ctx.get("round_total", 0))),
        Achievement("leech_buster", "🩹", "Dauerpatzer-Bezwinger",
                   'In einer Runde 5 Dauerpatzer (Leech-Karten) nicht mehr '
                   'als „nicht gewusst" bewertet.',
                   lambda: ctx.get("leech_cleared", 0) >= 5),
        # ---- Ueberraschungen: bewusst sparsam (siehe Modul-Docstring) ----
        Achievement("night_owl", "🦉", "Nachteule",
                   "Zwischen Mitternacht und 5 Uhr gelernt.",
                   analytics.has_night_owl_review, hidden=True),
    ]


def check_and_unlock(context: Optional[dict] = None) -> list[Achievement]:
    """Prüft den ganzen Katalog gegen den aktuellen Datenstand und schaltet
    neu erreichte Errungenschaften frei. Gibt NUR die JETZT NEU
    freigeschalteten zurück (für eine Feier-Anzeige) - bereits vorher
    freigeschaltete werden nicht erneut gemeldet. Eine einzelne kaputte
    Prüfung darf die Seite, von der aus das aufgerufen wird, nie crashen."""
    newly: list[Achievement] = []
    for ach in catalog(context):
        try:
            if ach.check() and manifest.unlock_achievement(ach.id):
                newly.append(ach)
        except Exception:  # noqa: BLE001
            continue
    return newly


def nearest_locked(min_pct: float = 70.0) -> Optional[dict]:
    """Die noch GESPERRTE, NICHT-versteckte Errungenschaft mit dem höchsten
    Fortschritt - aber nur, wenn sie wirklich schon nah dran ist (Default
    ≥ 70 %). Grundlage des "Noch X bis ..."-Hinweises auf Home: soll als
    Anreiz JETZT weiterzumachen wirken, nicht als taegliche Dauer-Erinnerung
    fuer alles, was noch weit weg ist."""
    unlocked = manifest.list_unlocked_achievements()
    best: Optional[dict] = None
    for ach in catalog():
        if ach.id in unlocked or ach.hidden or ach.progress is None:
            continue
        try:
            cur, tgt = ach.progress()
        except Exception:  # noqa: BLE001
            continue
        if not tgt:
            continue
        pct = min(100.0, 100.0 * cur / tgt)
        if pct >= min_pct and (best is None or pct > best["pct"]):
            best = {"id": ach.id, "icon": ach.icon, "title": ach.title,
                    "current": cur, "target": tgt, "pct": pct}
    return best
