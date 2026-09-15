"""Tests fuer optionale B-Roll (kein Netz in der Suite)."""
from __future__ import annotations

from ragapp import talk_broll, talk_figures
from ragapp.searx_client import SearxResult


def test_slots_without_figure_skips_lead_and_existing():
    md = """\
---
marp: true
---

<!-- _class: lead -->

# T

---

<!-- _class: content -->

## A

- x

---

<!-- _class: content -->

## B

![da](figures/old.png)
"""
    assert talk_broll.slots_without_figure(md) == 1


def test_slots_without_figure_counts_youtube_cards_skips_takeaway():
    md = """\
<!-- _class: lead -->

# T

---

<!-- _class: card -->

## **Grounding**

---

<!-- _class: accent -->

## Merke dir das

> x

---

<!-- _class: accent -->

## Abruf hält
"""
    assert talk_broll.slots_without_figure(md) == 1
    assert talk_broll.slots_without_figure(md, allow_cards=True) == 2


def test_attach_without_broll_does_not_search(monkeypatch, tmp_path):
    called = {"n": 0}

    def _boom(*a, **k):
        called["n"] += 1
        raise AssertionError("search should not run")

    monkeypatch.setattr(talk_broll, "download_broll", _boom)
    md = "<!-- _class: content -->\n\n## A\n\n- x\n"
    out = talk_figures.attach_talk_figures(
        md, [], dest_dir=tmp_path / "figures", broll=False, broll_query="x")
    assert out == md
    assert called["n"] == 0


def test_attach_with_broll_fills_empty_slot(monkeypatch, tmp_path):
    monkeypatch.setattr(
        talk_broll, "download_broll",
        lambda *a, **k: [{"rel": "figures/broll_0.png", "page": 0}],
    )
    md = "<!-- _class: content -->\n\n## A\n\n- x\n"
    out = talk_figures.attach_talk_figures(
        md, [], dest_dir=tmp_path / "figures", broll=True, broll_query="q")
    assert "figures/broll_0.png" in out


def test_attach_youtube_broll_fills_card(monkeypatch, tmp_path):
    monkeypatch.setattr(
        talk_broll, "download_broll",
        lambda *a, **k: [{"rel": "figures/broll_0.png", "page": 0}],
    )
    md = "<!-- _class: card -->\n\n## **Grounding**\n"
    out = talk_figures.attach_talk_figures(
        md, [], dest_dir=tmp_path / "figures", broll=True, broll_query="q",
        youtube=True)
    assert "figures/broll_0.png" in out
    skipped = talk_figures.attach_talk_figures(
        md, [], dest_dir=tmp_path / "figures", broll=True, broll_query="q",
        youtube=False)
    assert "figures/broll_0.png" not in skipped


def test_download_broll_writes_files_and_license(monkeypatch, tmp_path):
    hits = [
        SearxResult(
            title="A", url="https://commons.wikimedia.org/wiki/A",
            content="", img_src="https://upload.wikimedia.org/wikipedia/commons/a.png"),
        SearxResult(
            title="B", url="https://commons.wikimedia.org/wiki/B",
            content="", img_src="https://upload.wikimedia.org/wikipedia/commons/b.png"),
        SearxResult(
            title="C", url="https://commons.wikimedia.org/wiki/C",
            content="", img_src="https://upload.wikimedia.org/wikipedia/commons/c.png"),
    ]
    monkeypatch.setattr(talk_broll, "search_images", lambda *a, **k: hits)

    class _Resp:
        status_code = 200
        content = b"\x89PNG\r\n" + b"x" * 80
        headers = {"content-type": "image/png"}
        url = "https://upload.wikimedia.org/wikipedia/commons/a.png"

    class _Client:
        def __init__(self, *a, **k):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def get(self, url):
            return _Resp()

    monkeypatch.setattr(talk_broll.httpx, "Client", _Client)
    dest = tmp_path / "figures"
    saved = talk_broll.download_broll("testing", dest, max_n=2)
    assert len(saved) == 2
    assert (dest / "broll_licenses.json").is_file()
    assert (dest / "broll_0.png").is_file()
    text = (dest / "broll_licenses.json").read_text(encoding="utf-8")
    assert "Wikimedia" in text
    assert "broll_0.png" in text
