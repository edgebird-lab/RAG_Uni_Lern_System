"""CC/Open-Musikbett fuer YouTube-Vortraege (Wikimedia Commons, optional Openverse).

Holt nur Allowlist-Audio, nie die TTS-Referenzstimme. Fehlschlag -> lokales
Brummen in ``talk._mux_with_music_bed``. Cache unter ``data/talks/bed.fetched.*``.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from ragapp.searx_client import domain_allowed

log = logging.getLogger(__name__)

USER_AGENT = (
    "RAG-Lernsystem/1.0 (private study; "
    "+https://github.com/edgebird-lab/RAG_Uni_Lern_System)"
)
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
AUDIO_DOMAIN_ALLOWLIST = (
    "wikimedia.org",
    "wikipedia.org",
    "openverse.org",
    "creativecommons.org",
)
_SKIP_SUFFIX = (
    ".pdf", ".ogv", ".webm", ".mid", ".midi", ".png", ".jpg", ".jpeg", ".svg",
)
_QUERIES = (
    "ambient drone .ogg",
    "Elf Meditation Preview Kevin MacLeod",
    "Scott Buckley Petrichor",
)
MAX_BYTES = 8_000_000
_AUDIO_EXT = {".ogg", ".oga", ".opus", ".mp3", ".wav", ".flac"}


def fetched_bed_dir() -> Path:
    from ragapp.config import TALK_DIR
    TALK_DIR.mkdir(parents=True, exist_ok=True)
    return TALK_DIR


def cached_fetched_bed() -> Optional[Path]:
    root = fetched_bed_dir()
    for path in sorted(root.glob("bed.fetched.*")):
        if path.suffix.lower() in _AUDIO_EXT and path.is_file() and path.stat().st_size > 400:
            if path.name.lower() in {"reference.wav", "ref.wav"}:
                continue
            return path
    return None


def _headers() -> dict[str, str]:
    return {"User-Agent": USER_AGENT, "Accept": "application/json"}


def _commons_get(params: dict[str, Any], *, timeout: float = 12.0) -> dict[str, Any]:
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=_headers()) as client:
        r = client.get(COMMONS_API, params=params)
        r.raise_for_status()
        data = r.json()
    return data if isinstance(data, dict) else {}


def _search_commons(query: str) -> list[str]:
    data = _commons_get({
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": query,
        "srnamespace": 6,
        "srlimit": 8,
    })
    titles: list[str] = []
    for hit in (data.get("query") or {}).get("search") or []:
        title = str(hit.get("title") or "")
        lower = title.lower()
        if not title or any(lower.endswith(suf) for suf in _SKIP_SUFFIX):
            continue
        titles.append(title)
    return titles


def _imageinfo(title: str) -> Optional[dict[str, Any]]:
    data = _commons_get({
        "action": "query",
        "format": "json",
        "titles": title,
        "prop": "imageinfo",
        "iiprop": "url|mime|size|extmetadata",
    })
    pages = (data.get("query") or {}).get("pages") or {}
    for page in pages.values():
        infos = page.get("imageinfo") or []
        if infos:
            info = dict(infos[0])
            info["title"] = page.get("title") or title
            return info
    return None


def _pick_commons() -> Optional[dict[str, Any]]:
    for query in _QUERIES:
        try:
            titles = _search_commons(query)
        except Exception as exc:  # noqa: BLE001
            log.warning("Commons-Suche übersprungen (%s): %s", query, exc)
            continue
        for title in titles:
            try:
                info = _imageinfo(title)
            except Exception as exc:  # noqa: BLE001
                log.debug("imageinfo %s: %s", title, exc)
                continue
            if not info:
                continue
            url = str(info.get("url") or "")
            mime = str(info.get("mime") or "").lower()
            size = int(info.get("size") or 0)
            if not url or "audio" not in mime:
                continue
            if size <= 0 or size > MAX_BYTES:
                continue
            if not domain_allowed(url, AUDIO_DOMAIN_ALLOWLIST):
                continue
            return info
    return None


def _download_bytes(url: str, *, timeout: float = 20.0) -> bytes:
    if not domain_allowed(url, AUDIO_DOMAIN_ALLOWLIST):
        raise ValueError("Host nicht auf der Audio-Allowlist")
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=_headers()) as client:
        r = client.get(url)
        r.raise_for_status()
        final = str(r.url)
        if not domain_allowed(final, AUDIO_DOMAIN_ALLOWLIST):
            raise ValueError("Redirect-Host nicht erlaubt")
        data = r.content or b""
    if len(data) > MAX_BYTES:
        raise ValueError("Datei zu groß")
    if len(data) < 400:
        raise ValueError("Datei leer")
    return data


def _ext_from(url: str, mime: str) -> str:
    path = (urlparse(url).path or "").lower()
    for ext in _AUDIO_EXT:
        if path.endswith(ext):
            return ext
    if "mpeg" in mime or "mp3" in mime:
        return ".mp3"
    if "wav" in mime:
        return ".wav"
    if "opus" in mime:
        return ".opus"
    return ".ogg"


def fetch_open_music_bed(dest_dir: Optional[Path] = None) -> Optional[Path]:
    """Laedt ein CC-Loop nach ``bed.fetched.*``. Cache, falls schon da."""
    cached = cached_fetched_bed()
    if cached:
        return cached
    root = Path(dest_dir) if dest_dir else fetched_bed_dir()
    root.mkdir(parents=True, exist_ok=True)
    info = _pick_commons()
    if not info:
        return None
    url = str(info.get("url") or "")
    mime = str(info.get("mime") or "")
    try:
        payload = _download_bytes(url)
    except Exception as exc:  # noqa: BLE001
        log.warning("Musikbett-Download übersprungen: %s", exc)
        return None
    ext = _ext_from(url, mime)
    path = root / f"bed.fetched{ext}"
    if path.name.lower() in {"reference.wav", "ref.wav"}:
        return None
    path.write_bytes(payload)
    meta = info.get("extmetadata") or {}
    license_name = ""
    artist = ""
    if isinstance(meta, dict):
        license_name = str((meta.get("LicenseShortName") or {}).get("value") or "")
        artist = str((meta.get("Artist") or {}).get("value") or "")
    (root / "bed.fetched.json").write_text(
        json.dumps({
            "title": info.get("title"),
            "source_url": url,
            "license": license_name or "Wikimedia Commons – Lizenz auf der Dateiseite.",
            "artist": artist,
            "file": path.name,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("YouTube-Musikbett: %s (%s)", info.get("title"), license_name)
    return path
