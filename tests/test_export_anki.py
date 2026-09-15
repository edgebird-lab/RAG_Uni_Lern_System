"""Anki-HTML: Formeln bleiben MathJax, freier Text bleibt escaped."""
from ragapp.export_anki import _card_html


def test_card_html_haelt_latex_und_escaped_html():
    math = _card_html(r"Ableitung $x<0$ und $\frac{a}{b}$")
    assert "&lt;0" not in math
    assert r"\lt" in math
    assert r"$\frac{a}{b}$" in math or r"$\frac{a}{b}$" in math.replace(" ", "")
    raw = _card_html("<script>alert(1)</script> Deckungsbeitrag")
    assert "<script>" not in raw
    assert "&lt;script&gt;" in raw


def test_card_html_wrappt_nacktes_frac():
    out = _card_html(r"Ableitung \frac{d}{dx}")
    assert "$" in out
    assert "frac" in out
    assert "<script>" not in out
