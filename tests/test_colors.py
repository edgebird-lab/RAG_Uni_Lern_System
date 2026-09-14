"""Kontrast der Fach-Palette: weisser/dunkler Text muss auf jeder Kachel lesbar sein."""
from __future__ import annotations

from ragapp.ui._colors import PALETTE, contrast_ratio, text_color_for


def test_palette_hat_lesbaren_text():
    for bg in PALETTE:
        fg = text_color_for(bg)
        assert contrast_ratio(fg, bg) >= 4.5, (bg, fg, contrast_ratio(fg, bg))


def test_gedaempfte_farben_sind_auf_hell_und_dunkel_lesbar():
    from ragapp.ui._colors import MUTED_LIGHT, MUTED_DARK
    assert contrast_ratio(MUTED_LIGHT, "#ffffff") >= 4.5
    assert contrast_ratio(MUTED_DARK, "#0c1a30") >= 4.5


def test_text_color_for_waehlt_die_bessere_variante():
    assert text_color_for("#ffffff") == "#111111"
    assert text_color_for("#111111") == "#ffffff"
