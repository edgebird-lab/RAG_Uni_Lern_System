"""Abbildungen aus Quell-PDFs fuer Vortragsfolien.

Zieht eingebettete Bilder (und als Fallback diagrammlastige Seiten) aus den
gewaehlten Dokumenten, legt sie unter ``figures/`` neben der Marp-Datei ab
und haengt hoechstens ein Bild je Inhaltsfolie an. Das LLM erfindet keine
Bild-URLs.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

from ragapp.config import PROJECT_ROOT
from ragapp import manifest

log = logging.getLogger(__name__)

MIN_SIDE = 80
MIN_PIXELS = 80 * 80
MAX_PER_DOC = 8
MAX_PER_TALK = 6
_SKIP_CLASSES = frozenset({"lead", "agenda", "sources"})
_CLASS_RE = re.compile(r"<!--\s*_class:\s*(\w+)\s*-->")
_HAS_IMG_RE = re.compile(r"!\[.*?\]\([^)]+\)|<img\b", re.IGNORECASE)
_PAGE_HINT_RE = re.compile(r"seite\s*(\d+)|page\s*(\d+)", re.IGNORECASE)


def _page_is_mostly_blank(pix) -> bool:
    try:
        samples = pix.samples
        if not samples:
            return True
        step = max(1, len(samples) // 4000)
        sample = samples[::step]
        nonwhite = sum(1 for b in sample if b < 245)
        return (nonwhite / max(1, len(sample))) < 0.02
    except Exception:  # noqa: BLE001
        return False


def extract_pdf_figures(pdf_path: Path, dest_dir: Path, *,
                        max_n: int = MAX_PER_DOC) -> list[dict[str, Any]]:
    """Speichert brauchbare PDF-Bilder nach ``dest_dir``. Rel-Pfade ab Talk-Ordner."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out: list[dict[str, Any]] = []
    try:
        import fitz
    except Exception as exc:  # noqa: BLE001
        log.warning("PyMuPDF fehlt, keine Vortrags-Abbildungen: %s", exc)
        return out
    path = Path(pdf_path)
    if not path.is_file():
        return out
    seen: set[int] = set()
    try:
        doc = fitz.open(str(path))
    except Exception as exc:  # noqa: BLE001
        log.warning("PDF nicht lesbar (%s): %s", path, exc)
        return out
    try:
        for page_i, page in enumerate(doc, start=1):
            if len(out) >= max_n:
                break
            for img in page.get_images(full=True) or []:
                xref = int(img[0])
                if xref in seen:
                    continue
                seen.add(xref)
                rec = _save_xref(doc, xref, dest_dir, page_i)
                if rec:
                    out.append(rec)
                    if len(out) >= max_n:
                        break
            if len(out) >= max_n:
                break
            if not (page.get_images(full=True) or []) and page.get_drawings():
                text_len = len((page.get_text("text") or "").strip())
                if text_len < 500:
                    rec = _save_page_render(page, dest_dir, page_i)
                    if rec:
                        out.append(rec)
    finally:
        doc.close()
    return out


def _save_xref(doc, xref: int, dest_dir: Path, page_i: int) -> Optional[dict[str, Any]]:
    import fitz
    try:
        pix = fitz.Pixmap(doc, xref)
        if pix.n - pix.alpha >= 4:
            pix = fitz.Pixmap(fitz.csRGB, pix)
        if pix.width < MIN_SIDE or pix.height < MIN_SIDE:
            return None
        if pix.width * pix.height < MIN_PIXELS:
            return None
        if _page_is_mostly_blank(pix):
            return None
        name = f"p{page_i}_{xref}.png"
        dest = dest_dir / name
        pix.save(str(dest))
        return {
            "rel": f"figures/{name}",
            "page": page_i,
            "width": pix.width,
            "height": pix.height,
            "path": dest,
        }
    except Exception as exc:  # noqa: BLE001
        log.debug("Abbildung xref %s übersprungen: %s", xref, exc)
        return None


def _save_page_render(page, dest_dir: Path, page_i: int) -> Optional[dict[str, Any]]:
    try:
        pix = page.get_pixmap(dpi=110)
        if pix.width < MIN_SIDE or pix.height < MIN_SIDE:
            return None
        if _page_is_mostly_blank(pix):
            return None
        name = f"p{page_i}_page.png"
        dest = dest_dir / name
        pix.save(str(dest))
        return {
            "rel": f"figures/{name}",
            "page": page_i,
            "width": pix.width,
            "height": pix.height,
            "path": dest,
        }
    except Exception as exc:  # noqa: BLE001
        log.debug("Seitenrender %s übersprungen: %s", page_i, exc)
        return None


def collect_talk_figures(doc_ids: list[str], dest_dir: Path) -> list[dict[str, Any]]:
    """Zieht Abbildungen aus allen PDF-Dokumenten des Vortrags."""
    figures: list[dict[str, Any]] = []
    for doc_id in doc_ids or []:
        if len(figures) >= MAX_PER_TALK:
            break
        row = manifest.get_document(doc_id)
        if not row:
            continue
        src = row.get("source_path") or ""
        path = Path(src)
        if not path.is_file():
            path = PROJECT_ROOT / src
        if path.suffix.lower() != ".pdf" or not path.is_file():
            continue
        room = MAX_PER_TALK - len(figures)
        figures.extend(extract_pdf_figures(path, dest_dir, max_n=min(MAX_PER_DOC, room)))
    return figures[:MAX_PER_TALK]


def _slide_class(body: str) -> str:
    m = _CLASS_RE.search(body or "")
    return m.group(1) if m else "content"


def _page_hint(body: str) -> Optional[int]:
    m = _PAGE_HINT_RE.search(body or "")
    if not m:
        return None
    return int(m.group(1) or m.group(2))


def attach_figures_to_markdown(marp_md: str, figures: list[dict[str, Any]]) -> str:
    """Haengt unused figures an Inhaltsfolien (max. eins je Folie)."""
    if not figures:
        return marp_md
    text = marp_md or ""
    fm = ""
    body = text
    if text.strip().startswith("---"):
        m = re.match(r"^(---\s*\n.*?\n---\s*\n?)(.*)$", text, re.DOTALL)
        if m:
            fm = m.group(1)
            body = m.group(2)
    chunks = re.split(r"(?m)^---\s*$", body)
    unused = list(figures)
    new_chunks: list[str] = []
    for chunk in chunks:
        cls = _slide_class(chunk)
        if (
            unused
            and chunk.strip()
            and cls not in _SKIP_CLASSES
            and not _HAS_IMG_RE.search(chunk)
        ):
            hint = _page_hint(chunk)
            pick_i = 0
            if hint is not None:
                for fi, fig in enumerate(unused):
                    if int(fig.get("page") or 0) == hint:
                        pick_i = fi
                        break
            fig = unused.pop(pick_i)
            chunk = chunk.rstrip() + f"\n\n![Abbildung]({fig['rel']})\n"
        new_chunks.append(chunk)
    return fm + "\n---\n".join(new_chunks)


def attach_talk_figures(marp_md: str, doc_ids: list[str], *, dest_dir: Path,
                        broll: bool = False, broll_query: str = "") -> str:
    """Extract + attach. Bei Fehlern unveraendertes Markdown zurueck."""
    try:
        figures = collect_talk_figures(doc_ids, dest_dir)
        if broll:
            from ragapp.talk_broll import download_broll, slots_without_figure
            need = max(0, slots_without_figure(marp_md) - len(figures))
            if need:
                figures.extend(download_broll(
                    broll_query, dest_dir, max_n=min(2, need)))
        return attach_figures_to_markdown(marp_md, figures)
    except Exception as exc:  # noqa: BLE001
        log.warning("Vortrags-Abbildungen übersprungen: %s", exc)
        return marp_md
