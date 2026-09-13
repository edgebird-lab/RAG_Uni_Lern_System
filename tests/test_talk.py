"""Tests fuer ragapp.talk: Marp-Validierung, ffmpeg-Kommando, Manifest-CRUD."""
from __future__ import annotations

from pathlib import Path

import pytest

from ragapp import manifest, talk
from ragapp.talk import (
    TalkError,
    build_ffmpeg_concat_cmd,
    validate_marp_markdown,
    write_concat_list,
)


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "manifest_test.db"
    monkeypatch.setattr(manifest, "MANIFEST_DB", db_path)
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)
    return db_path


def test_validate_marp_adds_frontmatter_if_missing():
    md = validate_marp_markdown("# Hello\n\n---\n\n## Slide 2")
    assert md.startswith("---")
    assert "marp: true" in md
    assert "style: |" in md
    assert "--petrol" in md or "petrol" in md


def test_validate_marp_keeps_existing_frontmatter():
    raw = "---\nmarp: true\ntheme: default\n---\n\n# Titel\n\n---\n\n## Zwei"
    out = validate_marp_markdown(raw)
    assert out.startswith("---")
    assert "marp: true" in out
    assert "section.lead" in out


def test_validate_marp_rejects_empty():
    with pytest.raises(TalkError):
        validate_marp_markdown("   ")


def test_apply_talk_theme_idempotent():
    from ragapp.talk import apply_talk_theme
    raw = "---\nmarp: true\n---\n\n<!-- _class: lead -->\n# Hi\n\n---\n\n## Zwei"
    once = apply_talk_theme(raw)
    twice = apply_talk_theme(once)
    assert once.count("section.lead") == twice.count("section.lead")
    assert twice.count("style: |") == 1


def test_normalize_and_parse_slides_script():
    from ragapp.talk import _normalize_slides_chunk, _parse_slides_script, _join_slide_chunks
    raw = {
        "slides": "---\nmarp: true\n---\n\n# Hi\n\n---\n\n## Zwei",
        "script": "Hallo Welt.",
    }
    slides, script = _parse_slides_script(raw)
    assert "marp:" not in slides
    assert "Hallo" in script
    assert _normalize_slides_chunk("## Nur Titel").startswith("<!-- _class:")
    joined = _join_slide_chunks(["<!-- _class: lead -->\n# A", "<!-- _class: content -->\n## B"])
    assert "\n\n---\n\n" in joined


def test_validate_slides_script_rejects_json_leak():
    from ragapp.talk import validate_slides_script
    errs = validate_slides_script(
        '{"slides": "# Hi", "script": "x"}',
        "Ein ganz normaler Vorlesetext ohne Markdown.",
    )
    assert any("JSON" in e for e in errs)


def test_validate_slides_script_rejects_page_only_agenda():
    from ragapp.talk import validate_slides_script
    slides = (
        "<!-- _class: agenda -->\n\n## Heute\n\n"
        "1. Seite 1\n"
        "2. Seite 2\n"
    )
    errs = validate_slides_script(
        slides, "Willkommen zum Vortrag wir gehen die Themen durch und erklären alles.")
    assert any("Agenda" in e or "Platzhalter" in e for e in errs)


def test_validate_slides_script_accepts_clean():
    from ragapp.talk import validate_slides_script
    slides = "<!-- _class: content -->\n\n## Kernidee\n\n- Aussage eins\n- Aussage zwei\n"
    script = (
        "Schauen wir uns die Kernidee an. Aussage eins erklärt den Zusammenhang, "
        "Aussage zwei vertieft das praktische Beispiel."
    )
    assert validate_slides_script(slides, script, body_chars=200) == []


def test_thematic_toc_filters_page_titles():
    from ragapp.talk import _thematic_toc_and_excerpts
    toc, excerpts = _thematic_toc_and_excerpts([
        ("doc.pdf", "Seite 1", "Supereffizienz bedeutet Prozessoptimierung entlang der Wertschöpfung."),
    ])
    assert "Seite 1" in toc
    assert "Platzhalter" in toc or "inhaltlich" in toc
    assert "Supereffizienz" in excerpts


def test_build_ffmpeg_xfade_cmd_structure(tmp_path):
    from ragapp.talk import build_ffmpeg_xfade_cmd
    p1 = tmp_path / "a.png"
    p2 = tmp_path / "b.png"
    p1.write_bytes(b"x")
    p2.write_bytes(b"x")
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"x")
    out = tmp_path / "o.mp4"
    cmd = build_ffmpeg_xfade_cmd([p1, p2], audio, out, per_slide_s=3.0)
    assert "xfade" in " ".join(cmd)
    assert str(out) in cmd


def test_build_ffmpeg_concat_cmd_structure(tmp_path):
    concat = tmp_path / "concat.txt"
    audio = tmp_path / "a.wav"
    out = tmp_path / "o.mp4"
    audio.write_bytes(b"x")
    cmd = build_ffmpeg_concat_cmd(concat, audio, out)
    assert cmd[0].endswith("ffmpeg") or cmd[0] == "ffmpeg"
    assert "-f" in cmd and "concat" in cmd
    assert str(audio) in cmd
    assert str(out) in cmd
    assert "-shortest" in cmd
    assert "libx264" in cmd


def test_write_concat_list(tmp_path):
    p1 = tmp_path / "slide001.png"
    p2 = tmp_path / "slide002.png"
    p1.write_bytes(b"png")
    p2.write_bytes(b"png")
    lst = tmp_path / "concat.txt"
    write_concat_list([p1, p2], 3.5, lst)
    text = lst.read_text(encoding="utf-8")
    assert "duration 3.500" in text
    assert "slide001.png" in text
    assert text.count("file ") >= 3  # last image repeated


def test_create_list_update_delete_talk(isolated_db, tmp_path, monkeypatch):
    monkeypatch.setattr(talk, "TALK_DIR", tmp_path / "talks")
    monkeypatch.setattr("ragapp.config.TALK_DIR", tmp_path / "talks")
    (tmp_path / "talks").mkdir()

    tid = manifest.create_talk(
        title="Testvortrag", subject="mathe", doc_ids=["d1"],
        marp_md="---\nmarp: true\n---\n\n# Hi",
        script_text="Hallo Welt.",
        sources=[{"title": "Paper", "url": "https://arxiv.org/abs/1"}],
        model="test-model",
        talk_id="talkabc123",
    )
    assert tid == "talkabc123"
    row = manifest.get_talk(tid)
    assert row["title"] == "Testvortrag"
    assert row["doc_ids"] == ["d1"]
    assert row["sources"][0]["url"].startswith("https://arxiv.org")

    manifest.update_talk(tid, script_text="Neu.", audio_path="talkabc123/audio.wav")
    row2 = manifest.get_talk(tid)
    assert row2["script_text"] == "Neu."
    assert row2["audio_path"] == "talkabc123/audio.wav"

    listed = manifest.list_talks(subject="mathe")
    assert len(listed) == 1

    # Ordner anlegen und loeschen
    d = tmp_path / "talks" / tid
    d.mkdir(parents=True)
    (d / "audio.wav").write_bytes(b"RIFF")
    manifest.delete_talk(tid)
    assert manifest.get_talk(tid) is None
    assert not d.exists()
