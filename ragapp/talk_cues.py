"""Cue-Liste fuer animierte Vortrags-Videos.

Baut aus Marp-Markdown eine suchbare Eventliste (Folie, Titel, Bullets).
Zeiten sind Platzhalter, solange keine Satz-Timeline aus der Vertonung
vorliegt: Audio-Dauer gleichmaessig auf Folien, innerhalb einer Folie
haelt der Titel kurz, der Rest geht an die Listeneintraege.
"""
from __future__ import annotations

import re
from typing import Any, Optional

CUE_VERSION = 1
VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720

_TITLE_HOLD_FRAC = 0.18
_TITLE_HOLD_MIN = 0.4
_TITLE_HOLD_MAX = 1.2
_CLASS_RE = re.compile(r"<!--\s*_class:\s*([A-Za-z0-9_-]+)\s*-->")
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.MULTILINE)
_LIST_RE = re.compile(r"^(?:[-*+]|\d+[.)])\s+(.+?)\s*$")


def _strip_frontmatter(md: str) -> str:
    text = (md or "").strip()
    if text.startswith("---"):
        m = re.match(r"^---\s*\n.*?\n---\s*\n?(.*)$", text, re.DOTALL)
        if m:
            return m.group(1).strip()
    return text


def split_marp_slides(marp_md: str) -> list[str]:
    """Folienkoerper ohne YAML-Frontmatter, geteilt an ``---``."""
    body = _strip_frontmatter(marp_md)
    if not body:
        return []
    return [c.strip() for c in re.split(r"(?m)^---\s*$", body) if c.strip()]


def _plain(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*`_]+", "", text)
    return " ".join(text.split())


def parse_slide_body(body: str) -> dict[str, Any]:
    """Klasse, Titel und Listeneintraege einer Marp-Folie."""
    raw = (body or "").strip()
    class_m = _CLASS_RE.search(raw)
    class_name = class_m.group(1) if class_m else "content"
    title = ""
    head = _HEADING_RE.search(raw)
    if head:
        title = _plain(head.group(2))
    bullets: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("<!--") or stripped.startswith("#"):
            continue
        item = _LIST_RE.match(stripped)
        if item:
            text = _plain(item.group(1))
            if text:
                bullets.append(text)
    return {
        "class_name": class_name,
        "title": title,
        "bullets": bullets,
    }


def _title_hold_s(slide_dur: float, n_bullets: int) -> float:
    if n_bullets <= 0:
        return max(0.0, slide_dur)
    hold = slide_dur * _TITLE_HOLD_FRAC
    return min(_TITLE_HOLD_MAX, max(_TITLE_HOLD_MIN, hold), slide_dur * 0.45)


def _round_t(value: float) -> float:
    return round(max(0.0, value), 3)


def build_talk_cues(marp_md: str, *, duration_s: float,
                    width: int = VIDEO_WIDTH,
                    height: int = VIDEO_HEIGHT) -> dict[str, Any]:
    """Platzhalter-Cues: gleiche Folienlaenge, Titel kurz, dann Bullets.

    ``duration_s`` ist die Audiodauer (oder ein Testwert). Folie ohne Liste
    bekommt nur ``slide`` + optional ``title``.
    """
    duration_s = max(0.5, float(duration_s))
    bodies = split_marp_slides(marp_md)
    if not bodies:
        bodies = ["<!-- _class: content -->\n\n# Vortrag"]
    n = len(bodies)
    per = duration_s / n
    slides: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    for i, body in enumerate(bodies):
        parsed = parse_slide_body(body)
        start = i * per
        end = duration_s if i == n - 1 else (i + 1) * per
        slide_dur = max(0.05, end - start)
        bullets = parsed["bullets"]
        title = parsed["title"]
        hold = _title_hold_s(slide_dur, len(bullets))
        slide_events: list[dict[str, Any]] = [
            {"t": _round_t(start), "type": "slide", "slide": i},
        ]
        if title:
            slide_events.append(
                {"t": _round_t(start), "type": "title", "slide": i})
        if bullets:
            remain = max(0.05, slide_dur - hold)
            step = remain / len(bullets)
            for bi, _bullet in enumerate(bullets):
                t = start + hold + bi * step
                slide_events.append({
                    "t": _round_t(min(t, end - 0.01)),
                    "type": "bullet",
                    "slide": i,
                    "i": bi,
                })
        events.extend(slide_events)
        slides.append({
            "index": i,
            "class_name": parsed["class_name"],
            "title": title,
            "bullets": bullets,
            "start_s": _round_t(start),
            "end_s": _round_t(end),
            "events": slide_events,
        })

    return {
        "version": CUE_VERSION,
        "width": int(width),
        "height": int(height),
        "duration_s": _round_t(duration_s),
        "source": "placeholder",
        "slides": slides,
        "events": events,
    }


def _allocate_sentences(slides: list[dict[str, Any]],
                        sentences: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    n = len(slides)
    allocated: list[list[dict[str, Any]]] = [[] for _ in slides]
    if n == 0 or not sentences:
        return allocated
    wants = [max(1, (1 if s.get("title") else 0) + len(s.get("bullets") or []))
             for s in slides]
    si = 0
    for sent in sentences:
        while si < n - 1 and len(allocated[si]) >= wants[si]:
            si += 1
        allocated[si].append(sent)
    return allocated


def map_timeline_to_cues(marp_md: str, timeline: list[dict[str, Any]],
                         *, width: int = VIDEO_WIDTH,
                         height: int = VIDEO_HEIGHT) -> dict[str, Any]:
    """Ersetzt Platzhalter-Zeiten durch Satzstartzeiten aus der Vertonung."""
    sentences = [s for s in (timeline or []) if isinstance(s, dict) and s.get("text")]
    if not sentences:
        return build_talk_cues(marp_md, duration_s=8.0, width=width, height=height)
    last = sentences[-1]
    duration_s = max(
        0.5,
        float(last.get("start_s") or 0) + float(last.get("duration_s") or 0) + 0.05,
    )
    base = build_talk_cues(marp_md, duration_s=duration_s, width=width, height=height)
    allocated = _allocate_sentences(base["slides"], sentences)
    events: list[dict[str, Any]] = []
    slides_out: list[dict[str, Any]] = []
    for i, slide in enumerate(base["slides"]):
        sents = allocated[i]
        next_start = (
            allocated[i + 1][0]["start_s"] if i + 1 < len(allocated) and allocated[i + 1]
            else duration_s
        )
        start = float(sents[0]["start_s"]) if sents else float(slide["start_s"])
        end = float(next_start)
        slide_events: list[dict[str, Any]] = [
            {"t": _round_t(start), "type": "slide", "slide": i},
        ]
        if slide["title"]:
            slide_events.append({"t": _round_t(start), "type": "title", "slide": i})
        bullets = slide["bullets"]
        rest = sents[1:] if slide["title"] and sents else sents
        if bullets:
            for bi, _b in enumerate(bullets):
                if bi < len(rest):
                    t = float(rest[bi]["start_s"])
                elif rest:
                    last_t = float(rest[-1]["start_s"])
                    remain = len(bullets) - len(rest)
                    span = max(0.05, end - last_t)
                    t = last_t + (bi - len(rest) + 1) * span / (remain + 1)
                else:
                    hold = _title_hold_s(max(0.05, end - start), len(bullets))
                    step = max(0.05, (end - start - hold)) / len(bullets)
                    t = start + hold + bi * step
                slide_events.append({
                    "t": _round_t(min(max(t, start), max(start, end - 0.01))),
                    "type": "bullet",
                    "slide": i,
                    "i": bi,
                })
        events.extend(slide_events)
        slides_out.append({
            **slide,
            "start_s": _round_t(start),
            "end_s": _round_t(end),
            "events": slide_events,
        })
    return {
        "version": CUE_VERSION,
        "width": int(width),
        "height": int(height),
        "duration_s": _round_t(duration_s),
        "source": "timeline",
        "slides": slides_out,
        "events": events,
    }


def load_talk_cues(marp_md: str, *, duration_s: float,
                   timeline: Optional[list] = None) -> dict[str, Any]:
    """Timeline aus der Vertonung, sonst Platzhalter-Cues."""
    if timeline:
        return map_timeline_to_cues(marp_md, timeline)
    return build_talk_cues(marp_md, duration_s=duration_s)


def cues_from_talk(row: dict, *, duration_s: Optional[float] = None) -> dict[str, Any]:
    """Cues aus einem Talk-Datensatz; ``duration_s`` sonst aus Skriptlaenge grob."""
    md = row.get("marp_md") or ""
    if duration_s is None:
        script = row.get("script_text") or ""
        duration_s = max(8.0, len(script) / 14.0)
    return build_talk_cues(md, duration_s=duration_s)
