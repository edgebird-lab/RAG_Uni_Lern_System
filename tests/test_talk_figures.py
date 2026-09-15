"""Tests fuer PDF-Abbildungen in Vortragsfolien."""
from __future__ import annotations

from pathlib import Path

from ragapp.talk_figures import (
    attach_figures_to_markdown,
    extract_pdf_figures,
)


def _pdf_with_image(path: Path) -> Path:
    import io
    import fitz
    from PIL import Image

    img = Image.new("RGB", (160, 120), (200, 40, 40))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    doc = fitz.open()
    page = doc.new_page(width=400, height=300)
    page.insert_image(fitz.Rect(40, 40, 200, 160), stream=buf.getvalue())
    page.insert_text((40, 220), "Diagramm Testing-Effekt")
    doc.save(str(path))
    doc.close()
    return path


def test_extract_pdf_figures_saves_png(tmp_path):
    pdf = _pdf_with_image(tmp_path / "fig.pdf")
    dest = tmp_path / "figures"
    figs = extract_pdf_figures(pdf, dest)
    assert figs, "expected at least one figure"
    assert figs[0]["rel"].startswith("figures/")
    assert figs[0]["page"] == 1
    assert (dest / Path(figs[0]["rel"]).name).is_file()
    assert (dest / Path(figs[0]["rel"]).name).stat().st_size > 50


def test_extract_missing_pdf_returns_empty(tmp_path):
    assert extract_pdf_figures(tmp_path / "nope.pdf", tmp_path / "figures") == []


def test_attach_figures_skips_lead_agenda_and_existing_images():
    md = """\
---
marp: true
---

<!-- _class: lead -->

# Titel

---

<!-- _class: agenda -->

## Heute

1. Eins

---

<!-- _class: content -->

## Kern

- Punkt

---

<!-- _class: content -->

## Schon Bild

![da](figures/old.png)
"""
    figs = [
        {"rel": "figures/a.png", "page": 1},
        {"rel": "figures/b.png", "page": 2},
    ]
    out = attach_figures_to_markdown(md, figs)
    assert out.count("![Abbildung](figures/a.png)") == 1
    assert "figures/b.png" not in out
    assert "figures/a.png" in out.split("## Kern", 1)[1]
    assert "figures/a.png" not in out.split("## Kern", 1)[0]
    assert "![da](figures/old.png)" in out


def test_attach_without_figures_unchanged():
    md = "<!-- _class: content -->\n\n## A\n\n- x\n"
    assert attach_figures_to_markdown(md, []) == md


def test_page_hint_prefers_matching_figure():
    md = """\
<!-- _class: content -->

## Seite 3

- Aussage
"""
    figs = [
        {"rel": "figures/p1.png", "page": 1},
        {"rel": "figures/p3.png", "page": 3},
    ]
    out = attach_figures_to_markdown(md, figs)
    assert "figures/p3.png" in out
    assert "figures/p1.png" not in out
