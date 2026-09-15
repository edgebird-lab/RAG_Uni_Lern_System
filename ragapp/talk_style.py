"""Video-Stil eines Vortrags: Erklärvideo (Default) oder YouTube-Shots.

Das Flag liegt in ``data/talks/<id>/style.json``, nicht in der DB.
Unbekannt oder fehlend = Erklärvideo wie bisher.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from ragapp.config import TALK_DIR as _TALK_DIR_DEFAULT

STYLE_EXPLAINER = "explainer"
STYLE_YOUTUBE = "youtube"


def _talk_root() -> Path:
    from ragapp import config
    return getattr(config, "TALK_DIR", _TALK_DIR_DEFAULT)


def talk_style_path(talk_id: str) -> Path:
    return _talk_root() / str(talk_id) / "style.json"


def write_talk_style(talk_id: str, *, youtube: bool = False) -> Path:
    path = talk_style_path(talk_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "style": STYLE_YOUTUBE if youtube else STYLE_EXPLAINER,
                "youtube": bool(youtube),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def read_talk_style(talk_id: str) -> dict[str, Any]:
    path = talk_style_path(talk_id)
    if not path.is_file():
        return {"style": STYLE_EXPLAINER, "youtube": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"style": STYLE_EXPLAINER, "youtube": False}
    if not isinstance(data, dict):
        return {"style": STYLE_EXPLAINER, "youtube": False}
    youtube = bool(data.get("youtube") or data.get("style") == STYLE_YOUTUBE)
    return {
        "style": STYLE_YOUTUBE if youtube else STYLE_EXPLAINER,
        "youtube": youtube,
    }


def is_youtube_style(talk_id: Optional[str] = None, *, youtube: Optional[bool] = None) -> bool:
    if youtube is not None:
        return bool(youtube)
    if not talk_id:
        return False
    return bool(read_talk_style(talk_id).get("youtube"))
