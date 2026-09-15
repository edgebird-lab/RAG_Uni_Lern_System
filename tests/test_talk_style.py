"""Tests fuer Erklaervideo vs. YouTube-Stil-Flag."""
from __future__ import annotations

from ragapp.talk_style import is_youtube_style, read_talk_style, write_talk_style


def test_style_default_is_explainer(tmp_path, monkeypatch):
    monkeypatch.setattr("ragapp.config.TALK_DIR", tmp_path)
    assert read_talk_style("missing") == {"style": "explainer", "youtube": False}
    assert is_youtube_style("missing") is False
    assert is_youtube_style("missing", youtube=True) is True
    assert is_youtube_style("missing", youtube=False) is False


def test_write_read_youtube_style(tmp_path, monkeypatch):
    monkeypatch.setattr("ragapp.config.TALK_DIR", tmp_path)
    write_talk_style("t1", youtube=True)
    data = read_talk_style("t1")
    assert data["youtube"] is True
    assert data["style"] == "youtube"
    assert (tmp_path / "t1" / "style.json").is_file()
    write_talk_style("t1", youtube=False)
    assert read_talk_style("t1")["youtube"] is False


def test_ui_has_youtube_checkbox():
    from pathlib import Path
    ui = Path("ragapp/ui/pages/17_🎤_Vortrag.py").read_text(encoding="utf-8")
    assert "talk_youtube_style" in ui
    assert "talk_video_youtube_style" in ui
    src = Path("ragapp/talk.py").read_text(encoding="utf-8")
    assert "youtube_style: bool = False" in src
    assert "youtube_style: Optional[bool] = None" in src
