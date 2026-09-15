"""Tests fuer CC-Musikbett (YouTube-Stil)."""
from __future__ import annotations

from pathlib import Path

from ragapp import talk_bed


def test_fetch_open_music_bed_uses_commons_allowlist(tmp_path, monkeypatch):
    calls = {"search": 0, "info": 0}

    def fake_commons(params, timeout=12.0):
        if params.get("list") == "search":
            calls["search"] += 1
            return {"query": {"search": [
                {"title": "File:Skip.pdf"},
                {"title": "File:Pad.ogg"},
            ]}}
        calls["info"] += 1
        return {"query": {"pages": {"1": {
            "title": "File:Pad.ogg",
            "imageinfo": [{
                "url": "https://upload.wikimedia.org/wikipedia/commons/p/pad.ogg",
                "mime": "audio/ogg",
                "size": 1200,
                "extmetadata": {
                    "LicenseShortName": {"value": "CC0"},
                    "Artist": {"value": "Test"},
                },
            }],
        }}}}

    monkeypatch.setattr(talk_bed, "_commons_get", fake_commons)
    monkeypatch.setattr(
        talk_bed, "_download_bytes",
        lambda url, timeout=20.0: b"OggS" + b"\x00" * 500)
    monkeypatch.setattr(talk_bed, "cached_fetched_bed", lambda: None)
    out = talk_bed.fetch_open_music_bed(tmp_path)
    assert out == tmp_path / "bed.fetched.ogg"
    assert out.is_file()
    meta = (tmp_path / "bed.fetched.json").read_text(encoding="utf-8")
    assert "CC0" in meta
    assert "Pad.ogg" in meta
    assert "reference.wav" not in meta
    assert calls["search"] >= 1
    assert calls["info"] >= 1


def test_fetch_skips_off_allowlist(tmp_path, monkeypatch):
    monkeypatch.setattr(talk_bed, "cached_fetched_bed", lambda: None)
    monkeypatch.setattr(talk_bed, "_pick_commons", lambda: {
        "url": "https://example.com/secret.mp3",
        "mime": "audio/mpeg",
        "title": "Nope",
        "extmetadata": {},
    })
    assert talk_bed.fetch_open_music_bed(tmp_path) is None
    assert not list(tmp_path.glob("bed.fetched.*"))


def test_cached_fetched_bed_skips_reference(tmp_path, monkeypatch):
    monkeypatch.setattr(talk_bed, "fetched_bed_dir", lambda: tmp_path)
    (tmp_path / "reference.wav").write_bytes(b"RIFF" + b"\x00" * 500)
    (tmp_path / "bed.fetched.ogg").write_bytes(b"OggS" + b"\x00" * 500)
    found = talk_bed.cached_fetched_bed()
    assert found == tmp_path / "bed.fetched.ogg"


def test_mux_fetches_bed_only_for_youtube(monkeypatch, tmp_path):
    from ragapp import talk
    called = {"n": 0}

    def fake_fetch(dest_dir=None):
        called["n"] += 1
        return None

    monkeypatch.setattr(talk, "find_talk_music_bed", lambda: None)
    monkeypatch.setattr("ragapp.talk_bed.fetch_open_music_bed", fake_fetch)
    monkeypatch.setattr(talk, "_make_quiet_drone", lambda *a, **k: None)
    out = tmp_path / "mix.mp4"
    assert talk._mux_with_music_bed(
        tmp_path / "v.mp4", tmp_path / "a.wav", out, youtube=False) is None
    assert called["n"] == 0
    assert talk._mux_with_music_bed(
        tmp_path / "v.mp4", tmp_path / "a.wav", out, youtube=True) is None
    assert called["n"] == 1
