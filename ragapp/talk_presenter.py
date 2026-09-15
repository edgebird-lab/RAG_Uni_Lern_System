"""Injiziert den suchbaren Vortrags-Presenter in Marp-HTML (nur Video-Pass)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DIR = Path(__file__).resolve().parent
PRESENTER_CSS = _DIR / "talk_presenter.css"
PRESENTER_JS = _DIR / "talk_presenter.js"


def inject_talk_presenter(html: str, cues: dict[str, Any]) -> str:
    """Haengt CSS/JS + Cue-JSON vor ``</body>``. Download-HTML bleibt unangetastet."""
    css = PRESENTER_CSS.read_text(encoding="utf-8")
    js = PRESENTER_JS.read_text(encoding="utf-8")
    payload = json.dumps(cues, ensure_ascii=False).replace("<", "\\u003c")
    snippet = (
        f'<style id="talk-presenter-css">{css}</style>\n'
        f'<script id="talk-cues" type="application/json">{payload}</script>\n'
        f"<script>{js}</script>\n"
    )
    if "</body>" in html:
        return html.replace("</body>", snippet + "</body>", 1)
    return html + snippet
