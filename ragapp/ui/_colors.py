"""
Fach-Farben (geteilte Bausteine)
=================================
Gemeinsame Farblogik fuer alles, was ein Fach visuell kennzeichnet (Stundenplan-
Kacheln auf der Organisation-Seite, Lernplan-Karten/-Zeitleiste): eine feste
Palette weist jedem Fach deterministisch eine Farbe zu (gleiches Fach -> immer
gleiche Farbe, auch ohne gespeicherte Auswahl in ``subject_colors``); frei
vergebene Farben (``manifest.subject_colors_map()``) haben Vorrang.
"""
from __future__ import annotations

PALETTE = ["#4A45C4", "#3E9B6C", "#C08A2E", "#C4485A", "#2E86AB", "#8E44AD",
          "#D68910", "#16A085", "#943126", "#2471A3", "#B7950B", "#5B6B85"]


def text_color_for(bg_hex: str) -> str:
    """Weisser oder schwarzer Text - je nachdem, was auf dieser Hintergrundfarbe
    besser lesbar ist (einfache Luminanz-Schaetzung)."""
    h = (bg_hex or "").lstrip("#")
    if len(h) != 6:
        return "#111111"
    try:
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return "#111111"
    return "#111111" if (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.6 else "#ffffff"


def subject_color(subject: "str | None", colors: dict, ordered_subjects: list) -> str:
    """Frei vergebene Farbe, sonst deterministisch aus der Palette (gleiches Fach
    -> immer gleiche Farbe, auch ohne gespeicherte Auswahl)."""
    if not subject:
        return "#94a3b8"
    if subject in colors:
        return colors[subject]
    idx = ordered_subjects.index(subject) if subject in ordered_subjects else 0
    return PALETTE[idx % len(PALETTE)]
