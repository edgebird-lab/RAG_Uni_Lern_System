"""Optionale lizenzierte B-Roll fuer Vortraege (Wikimedia/Openverse)."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from ragapp.searx_client import IMAGE_DOMAIN_ALLOWLIST, domain_allowed, search_images

log = logging.getLogger(__name__)

MAX_BROLL = 2
MAX_BYTES = 2_500_000


def _ext_from(url: str, content_type: str) -> str:
    path = (urlparse(url).path or "").lower()
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    ct = (content_type or "").lower()
    if "png" in ct:
        return ".png"
    if "webp" in ct:
        return ".webp"
    if "gif" in ct:
        return ".gif"
    return ".jpg"


def download_broll(query: str, dest_dir: Path, *, max_n: int = MAX_BROLL) -> list[dict[str, Any]]:
    """Laedt 0–N Allowlist-Bilder und schreibt broll_licenses.json."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    q = (query or "").strip()
    if not q or max_n <= 0:
        return []
    try:
        hits = search_images(q, max_results=max(4, max_n), require_enabled=False)
    except Exception as exc:  # noqa: BLE001
        log.warning("B-Roll-Suche übersprungen: %s", exc)
        return []
    saved: list[dict[str, Any]] = []
    licenses: list[dict[str, Any]] = []
    for hit in hits:
        if len(saved) >= max_n:
            break
        url = (hit.img_src or hit.url or "").strip()
        if not url or not (
            domain_allowed(url, IMAGE_DOMAIN_ALLOWLIST)
            or domain_allowed(hit.url, IMAGE_DOMAIN_ALLOWLIST)
        ):
            continue
        try:
            with httpx.Client(timeout=12.0, follow_redirects=True) as client:
                r = client.get(url)
            if r.status_code >= 400 or not r.content:
                continue
            final = str(r.url)
            if not domain_allowed(final, IMAGE_DOMAIN_ALLOWLIST):
                continue
            if len(r.content) > MAX_BYTES:
                continue
            ct = r.headers.get("content-type") or ""
            if ct and "image" not in ct.lower() and "octet-stream" not in ct.lower():
                continue
            ext = _ext_from(final, ct)
            name = f"broll_{len(saved)}{ext}"
            path = dest_dir / name
            path.write_bytes(r.content)
            rec = {
                "rel": f"figures/{name}",
                "page": 0,
                "path": path,
                "source_url": final,
                "page_url": hit.url,
                "title": hit.title,
            }
            saved.append(rec)
            licenses.append({
                "file": name,
                "title": hit.title,
                "source_url": final,
                "page_url": hit.url,
                "license": "Wikimedia/Openverse – Lizenz auf der Quellseite prüfen.",
            })
        except Exception as exc:  # noqa: BLE001
            log.debug("B-Roll-Download übersprungen (%s): %s", url, exc)
    if licenses:
        (dest_dir / "broll_licenses.json").write_text(
            json.dumps(licenses, ensure_ascii=False, indent=2), encoding="utf-8")
    return saved


def slots_without_figure(marp_md: str) -> int:
    """Inhaltsfolien ohne Bild – Lead/Agenda/Quellen zaehlen nicht."""
    from ragapp.talk_cues import parse_slide_body, split_marp_slides
    n = 0
    for body in split_marp_slides(marp_md):
        parsed = parse_slide_body(body)
        if parsed["class_name"] in {"lead", "agenda", "sources", "card"}:
            continue
        if parsed.get("images"):
            continue
        if re.search(r"!\[.*?\]\([^)]+\)|<img\b", body, re.I):
            continue
        n += 1
    return n
