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

# Dunklere Töne, damit weisser Text auf den Kacheln WCAG-AA (4.5:1) erreicht.
PALETTE = ["#4A45C4", "#2F7A54", "#9A6A12", "#C4485A", "#2E86AB", "#8E44AD",
           "#A85C0C", "#0E7A66", "#943126", "#2471A3", "#7A6A08", "#5B6B85"]

MUTED_LIGHT = "#5b6b85"
MUTED_DARK = "#93a8c4"


def _srgb_channel(value: int) -> float:
    c = value / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(bg_hex: str) -> float:
    h = (bg_hex or "").lstrip("#")
    if len(h) != 6:
        return 0.0
    try:
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return 0.0
    return 0.2126 * _srgb_channel(r) + 0.7152 * _srgb_channel(g) + 0.0722 * _srgb_channel(b)


def contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    l1, l2 = relative_luminance(fg_hex), relative_luminance(bg_hex)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def text_color_for(bg_hex: str) -> str:
    """Heller oder dunkler Text – die Variante mit dem höheren Kontrast."""
    white = contrast_ratio("#ffffff", bg_hex)
    black = contrast_ratio("#111111", bg_hex)
    return "#ffffff" if white >= black else "#111111"


def subject_color(subject: "str | None", colors: dict, ordered_subjects: list) -> str:
    """Frei vergebene Farbe, sonst deterministisch aus der Palette (gleiches Fach
    -> immer gleiche Farbe, auch ohne gespeicherte Auswahl)."""
    if not subject:
        return MUTED_LIGHT
    if subject in colors:
        return colors[subject]
    idx = ordered_subjects.index(subject) if subject in ordered_subjects else 0
    return PALETTE[idx % len(PALETTE)]
