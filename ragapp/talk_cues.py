"""Cue-Liste fuer animierte Vortrags-Videos.

Baut aus Marp-Markdown eine suchbare Eventliste (Folie, Titel, Bullets).
Zeiten sind Platzhalter, solange keine Satz-Timeline aus der Vertonung
vorliegt: Audio-Dauer nach Foliengewicht (Lead/Cold-Open etwas laenger),
innerhalb einer Folie haelt der Titel kurz, der Rest geht an die Listeneintraege.
"""
from __future__ import annotations

import re
from typing import Any, Optional

CUE_VERSION = 5
VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720

_TITLE_HOLD_FRAC = 0.18
_TITLE_HOLD_MIN = 0.4
_TITLE_HOLD_MAX = 1.2
_LEAD_TIME_WEIGHT = 1.65
_LEAD_SENTENCE_WANTS = 2
_CLASS_RE = re.compile(r"<!--\s*_class:\s*([A-Za-z0-9_-]+)\s*-->")
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.MULTILINE)
_LIST_RE = re.compile(r"^(?:[-*+]|\d+[.)])\s+(.+?)\s*$")
_EMPH_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_IMG_RE = re.compile(r"!\[(.*?)\]\(([^)]+)\)")
_EVENT_ORDER = {
    "slide": 0,
    "title": 1,
    "punch": 2,
    "col": 3,
    "figure": 4,
    "bullet": 5,
    "keyword": 6,
    "caption": 7,
}


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


def _emphasis_words(text: str) -> list[str]:
    words: list[str] = []
    for a, b in _EMPH_RE.findall(text or ""):
        w = _plain(a or b)
        if w:
            words.append(w)
    return words


def parse_slide_body(body: str) -> dict[str, Any]:
    """Klasse, Titel, Listeneintraege, Keywords und Merksatz-Flag."""
    raw = (body or "").strip()
    class_m = _CLASS_RE.search(raw)
    class_name = class_m.group(1) if class_m else "content"
    title = ""
    title_keywords: list[str] = []
    head = _HEADING_RE.search(raw)
    if head:
        title_keywords = _emphasis_words(head.group(2))
        title = _plain(head.group(2))
    bullets: list[str] = []
    bullet_keywords: list[list[str]] = []
    has_quote = False
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            has_quote = True
        if not stripped or stripped.startswith("<!--") or stripped.startswith("#"):
            continue
        item = _LIST_RE.match(stripped)
        if item:
            raw_item = item.group(1)
            text = _plain(raw_item)
            if text:
                bullets.append(text)
                bullet_keywords.append(_emphasis_words(raw_item))
    n_cols = 0
    if class_name == "split":
        divs = len(re.findall(r"(?i)<div\b", raw))
        inner_heads = max(0, len(_HEADING_RE.findall(raw)) - 1)
        if divs >= 3:
            n_cols = max(2, divs - 1)
        else:
            n_cols = max(2, inner_heads or 2)
    images = [
        {"alt": (m.group(1) or "").strip(), "src": (m.group(2) or "").strip()}
        for m in _IMG_RE.finditer(raw)
        if (m.group(2) or "").strip()
    ]
    return {
        "class_name": class_name,
        "title": title,
        "bullets": bullets,
        "title_keywords": title_keywords,
        "bullet_keywords": bullet_keywords,
        "punch": class_name == "accent" or has_quote,
        "n_cols": n_cols,
        "images": images,
    }


def _title_hold_s(slide_dur: float, n_bullets: int) -> float:
    if n_bullets <= 0:
        return max(0.0, slide_dur)
    hold = slide_dur * _TITLE_HOLD_FRAC
    return min(_TITLE_HOLD_MAX, max(_TITLE_HOLD_MIN, hold), slide_dur * 0.45)


def _caption_text(text: str) -> str:
    t = " ".join((text or "").split())
    if not t:
        return ""
    if len(t) <= 48:
        return t.rstrip(" .")
    return t[:45].rsplit(" ", 1)[0].rstrip(" .,;:") + "…"


def _round_t(value: float) -> float:
    return round(max(0.0, value), 3)


def _sort_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events.sort(key=lambda e: (
        float(e.get("t") or 0),
        _EVENT_ORDER.get(str(e.get("type") or ""), 9),
        int(e["i"]) if isinstance(e.get("i"), int) else 0,
    ))
    return events


def _keyword_specs(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    idx = 0
    for text in parsed.get("title_keywords") or []:
        specs.append({"i": idx, "anchor": "title", "text": text})
        idx += 1
    for bi, words in enumerate(parsed.get("bullet_keywords") or []):
        for text in words:
            specs.append({"i": idx, "anchor": "bullet", "bullet": bi, "text": text})
            idx += 1
    return specs


def _attach_motion_events(
    slide_events: list[dict[str, Any]],
    parsed: dict[str, Any],
    slide_idx: int,
    *,
    end_s: Optional[float] = None,
) -> list[dict[str, Any]]:
    """Haengt keyword/punch/col an, unbekannte Typen bleiben fuer den Presenter egal."""
    title_t = next((e["t"] for e in slide_events if e.get("type") == "title"), None)
    bullet_t = {
        e["i"]: e["t"] for e in slide_events
        if e.get("type") == "bullet" and isinstance(e.get("i"), int)
    }
    fallback = slide_events[0]["t"] if slide_events else 0.0
    extra: list[dict[str, Any]] = []
    if parsed.get("punch"):
        extra.append({
            "t": _round_t(title_t if title_t is not None else fallback),
            "type": "punch",
            "slide": slide_idx,
        })
    n_cols = int(parsed.get("n_cols") or 0)
    if n_cols > 0:
        start = fallback
        end = float(end_s) if end_s is not None else start + 4.0
        span_start = title_t if title_t is not None else start
        remain = max(0.05, end - span_start)
        for ci in range(n_cols):
            extra.append({
                "t": _round_t(min(span_start + ci * remain / n_cols, max(start, end - 0.01))),
                "type": "col",
                "slide": slide_idx,
                "i": ci,
            })
    for fi, img in enumerate(parsed.get("images") or []):
        extra.append({
            "t": _round_t(title_t if title_t is not None else fallback),
            "type": "figure",
            "slide": slide_idx,
            "i": fi,
            "src": img.get("src") or "",
        })
    for spec in _keyword_specs(parsed):
        if spec["anchor"] == "title":
            t = title_t if title_t is not None else fallback
        else:
            t = bullet_t.get(spec["bullet"], fallback)
        extra.append({
            "t": _round_t(t),
            "type": "keyword",
            "slide": slide_idx,
            "i": spec["i"],
            "text": spec["text"],
        })
    slide_events.extend(extra)
    return _sort_events(slide_events)


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
    parsed_all = [parse_slide_body(body) for body in bodies]
    weights = [
        _LEAD_TIME_WEIGHT if p.get("class_name") == "lead" else 1.0
        for p in parsed_all
    ]
    total_w = sum(weights) or float(n)
    slides: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    acc = 0.0

    for i, parsed in enumerate(parsed_all):
        start = acc
        acc += duration_s * (weights[i] / total_w)
        end = duration_s if i == n - 1 else acc
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
        _attach_motion_events(slide_events, parsed, i, end_s=end)
        events.extend(slide_events)
        slides.append({
            "index": i,
            "class_name": parsed["class_name"],
            "title": title,
            "bullets": bullets,
            "title_keywords": parsed.get("title_keywords") or [],
            "bullet_keywords": parsed.get("bullet_keywords") or [],
            "punch": bool(parsed.get("punch")),
            "n_cols": int(parsed.get("n_cols") or 0),
            "images": parsed.get("images") or [],
            "start_s": _round_t(start),
            "end_s": _round_t(end),
            "events": slide_events,
        })

    _sort_events(events)
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
    wants = []
    for s in slides:
        base = max(1, (1 if s.get("title") else 0) + len(s.get("bullets") or []))
        if s.get("class_name") == "lead":
            wants.append(max(base, _LEAD_SENTENCE_WANTS))
        else:
            wants.append(base)
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
        for sent in sents:
            cap = _caption_text(str(sent.get("text") or ""))
            if cap:
                slide_events.append({
                    "t": _round_t(float(sent.get("start_s") or start)),
                    "type": "caption",
                    "slide": i,
                    "text": cap,
                })
        _attach_motion_events(slide_events, slide, i, end_s=end)
        events.extend(slide_events)
        slides_out.append({
            **slide,
            "start_s": _round_t(start),
            "end_s": _round_t(end),
            "events": slide_events,
        })
    _sort_events(events)
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
