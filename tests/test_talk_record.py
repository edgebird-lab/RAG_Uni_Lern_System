"""Integration: Presenter-HTML wird zu einem kurzen MP4 (Chrome + ffmpeg)."""
from __future__ import annotations

import io
import shutil
import wave
from pathlib import Path

import pytest

from ragapp.talk import TalkError, find_chrome_binary, mux_video_with_talk_audio, record_presenter_video
from ragapp.talk_cues import build_talk_cues
from ragapp.talk_presenter import inject_talk_presenter

pytestmark = pytest.mark.skipif(
    not shutil.which("ffmpeg") or not find_chrome_binary(),
    reason="ffmpeg und Chrome noetig fuer Presenter-Aufnahme",
)

MARP = """\
---
marp: true
---

# Eins

---

## Zwei

- Punkt A
"""


def _tiny_wav(path: Path, seconds: float = 0.8) -> Path:
    n = int(8000 * seconds)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * n)
    path.write_bytes(buf.getvalue())
    return path


def test_record_presenter_video_writes_mp4(tmp_path):
    cues = build_talk_cues(MARP, duration_s=0.8)
    html = inject_talk_presenter(
        Path("tests/fixtures/talk_presenter.html").read_text(encoding="utf-8"), cues)
    html_path = tmp_path / "p.html"
    html_path.write_text(html, encoding="utf-8")
    silent = tmp_path / "silent.mp4"
    record_presenter_video(html_path, silent, duration_s=0.8, fps=5)
    assert silent.is_file()
    assert silent.stat().st_size > 1000

    audio = _tiny_wav(tmp_path / "a.wav", 0.8)
    out = tmp_path / "talk.mp4"
    mux_video_with_talk_audio(silent, audio, out)
    assert out.is_file()
    assert out.stat().st_size > 1000
    bed_out = tmp_path / "talk_bed.mp4"
    mux_video_with_talk_audio(silent, audio, bed_out, music_bed=True)
    assert bed_out.is_file()
    assert bed_out.stat().st_size > 1000
    # ffprobe Dauer grob Audio
    import subprocess
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(out)],
        capture_output=True, text=True, check=False)
    if proc.returncode == 0:
        dur = float(proc.stdout.strip())
        assert 0.4 <= dur <= 2.5


def test_record_presenter_video_youtube_1080(tmp_path):
    from ragapp.talk_cues import load_talk_cues
    cues = load_talk_cues(MARP, duration_s=0.4, youtube=True)
    assert cues["width"] == 1920
    html = inject_talk_presenter(
        Path("tests/fixtures/talk_presenter.html").read_text(encoding="utf-8"), cues)
    html_path = tmp_path / "yt.html"
    html_path.write_text(html, encoding="utf-8")
    silent = tmp_path / "yt.mp4"
    record_presenter_video(
        html_path, silent, duration_s=0.4, fps=5,
        width=1920, height=1080, stillimage=False)
    assert silent.is_file()
    import subprocess
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "csv=p=0", str(silent)],
        capture_output=True, text=True, check=False)
    assert proc.returncode == 0
    assert proc.stdout.strip().startswith("1920,1080")


def test_record_presenter_video_missing_html_raises(tmp_path):
    with pytest.raises(TalkError):
        record_presenter_video(tmp_path / "nope.html", tmp_path / "x.mp4", duration_s=0.5, fps=5)
