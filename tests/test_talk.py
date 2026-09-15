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


def test_clamp_content_five_bullets_to_three():
    from ragapp.talk import clamp_slide_grammar, validate_slides_script
    raw = (
        "<!-- _class: content -->\n\n## Wand\n\n"
        "- eins\n- zwei\n- drei\n- vier\n- fünf\n"
    )
    out = clamp_slide_grammar(raw)
    assert out.count("\n- ") == 3
    assert "- vier" not in out
    assert validate_slides_script(
        out, "Wir klären die drei Kernaussagen nacheinander und bleiben knapp.",
        body_chars=200) == []
    errs = validate_slides_script(
        raw, "Wir klären die drei Kernaussagen nacheinander und bleiben knapp.",
        body_chars=200)
    assert any("Stichpunkt" in e for e in errs)


def test_clamp_accent_and_lead_and_split():
    from ragapp.talk import clamp_slide_grammar
    accent = clamp_slide_grammar(
        "<!-- _class: accent -->\n\n## Merksatz\n\n- a\n- b\n- c\n")
    assert accent.count("\n- ") == 1
    lead = clamp_slide_grammar(
        "<!-- _class: lead -->\n\n# Titel\n\n- weg\n- auch weg\n")
    assert "- weg" not in lead
    split = clamp_slide_grammar(
        "<!-- _class: split -->\n\n## Vergleich\n\n"
        "### Links\n- a1\n- a2\n- a3\n- a4\n\n"
        "### Rechts\n- b1\n- b2\n- b3\n- b4\n"
    )
    assert "- a4" not in split
    assert "- b4" not in split
    assert "- a3" in split
    assert "- b3" in split
    agenda = clamp_slide_grammar(
        "<!-- _class: agenda -->\n\n## Heute\n\n"
        "1. eins\n2. zwei\n3. drei\n4. vier\n5. fünf\n6. sechs\n7. sieben\n"
    )
    assert "6. sechs" in agenda
    assert "7. sieben" not in agenda
    sources = clamp_slide_grammar(
        "<!-- _class: sources -->\n\n## Quellen\n\n"
        "- [A](http://a)\n- [B](http://b)\n- [C](http://c)\n"
        "- [D](http://d)\n"
    )
    assert sources.count("- [") == 4


def test_section_prompt_asks_for_sparse_slides():
    from ragapp.talk import _OPENING_PROMPT, _SECTION_PROMPT
    assert "höchstens 3" in _SECTION_PROMPT
    assert "**Keyword**" in _SECTION_PROMPT
    assert "KEINE Stichpunkte" in _OPENING_PROMPT
    assert "**Hook-Wort**" in _OPENING_PROMPT


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
    joined = " ".join(cmd)
    assert "xfade" in joined
    assert str(out) in cmd
    assert "loudnorm" in joined
    assert "-af" in cmd


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
    assert "loudnorm" in " ".join(cmd)
    assert "-af" in cmd


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
    assert row["forced_eos"] == []

    manifest.update_talk(
        tid, forced_eos=[{"index": 1, "text": "Abgeschnittener Satz."}, "   "])
    assert manifest.get_talk(tid)["forced_eos"] == [
        {"index": 1, "text": "Abgeschnittener Satz."}]
    manifest.update_talk(tid, forced_eos=[])
    assert manifest.get_talk(tid)["forced_eos"] == []

    # Ordner anlegen und loeschen
    d = tmp_path / "talks" / tid
    d.mkdir(parents=True)
    (d / "audio.wav").write_bytes(b"RIFF")
    manifest.delete_talk(tid)
    assert manifest.get_talk(tid) is None
    assert not d.exists()


def test_join_talk_script_uses_section_pauses():
    from ragapp.talk import _join_talk_script
    out = _join_talk_script(["Eröffnung.", "Abschnitt eins.", "", " Quellen. "])
    assert out == "Eröffnung.\n\n\nAbschnitt eins.\n\n\nQuellen."


def test_synthesize_talk_audio_persists_forced_eos(isolated_db, tmp_path, monkeypatch):
    talks_dir = tmp_path / "talks"
    talks_dir.mkdir()
    monkeypatch.setattr(talk, "TALK_DIR", talks_dir)
    tid = manifest.create_talk(
        title="EOS", subject="Livetest", doc_ids=[],
        marp_md="---\nmarp: true\n---\n\n# Hi",
        script_text="Hallo Welt.",
        talk_id="talkeos1",
    )

    def fake_synth(text, ref, out, on_progress=None, timeline=None):
        Path(out).write_bytes(b"RIFF")
        if timeline is not None:
            timeline.append({"index": 0, "text": "Hallo Welt.",
                             "start_s": 0.0, "duration_s": 0.4})
        return [{"index": 0, "text": "Abbruch."}]

    monkeypatch.setattr("ragapp.audio_overview.synthesize_speech", fake_synth)
    monkeypatch.setattr(
        "ragapp.audio_overview._require_reference_wav", lambda: tmp_path / "ref.wav")
    rel = talk.synthesize_talk_audio(tid, "Hallo Welt.")
    assert rel == "talkeos1/audio.wav"
    row = manifest.get_talk(tid)
    assert row["forced_eos"] == [{"index": 0, "text": "Abbruch."}]
    assert row["audio_path"] == rel
    assert (talks_dir / rel).is_file()
    assert (talks_dir / tid / "timeline.json").is_file()


def test_mux_video_with_talk_audio_uses_loudnorm():
    src = Path("ragapp/talk.py").read_text(encoding="utf-8")
    assert "def mux_video_with_talk_audio" in src
    assert "record_presenter_video" in src
    assert "Fallback Diashow" in src
    assert "_video_aac_args()" in src


def test_render_talk_video_falls_back_when_record_fails(isolated_db, tmp_path, monkeypatch):
    talks_dir = tmp_path / "talks"
    talks_dir.mkdir()
    monkeypatch.setattr(talk, "TALK_DIR", talks_dir)
    monkeypatch.setattr("ragapp.config.TALK_DIR", talks_dir)
    tid = "talkfb1"
    tid = manifest.create_talk(
        title="Fallback", subject="Livetest", doc_ids=[],
        marp_md="---\nmarp: true\n---\n\n# Hi\n\n---\n\n## Zwei",
        script_text="Hallo.",
        audio_path=f"{tid}/audio.wav",
        talk_id=tid,
    )
    d = talks_dir / tid
    d.mkdir(parents=True)
    (d / "audio.wav").write_bytes(b"RIFF")
    (d / "talk.md").write_text("# Hi", encoding="utf-8")

    monkeypatch.setattr(talk, "run_marp", lambda *a, **k: d / "talk.html")
    (d / "talk.html").write_text("<html><body></body></html>", encoding="utf-8")
    monkeypatch.setattr(talk, "probe_audio_duration_s", lambda p: 2.0)

    def boom(*_a, **_k):
        raise talk.TalkError("boom")

    called = {}

    def fake_slideshow(html_path, md_path, dd, audio_path, out_path):
        called["slideshow"] = True
        Path(out_path).write_bytes(b"mp4fake")

    monkeypatch.setattr(talk, "record_presenter_video", boom)
    monkeypatch.setattr(talk, "_render_slideshow_video", fake_slideshow)
    rel = talk.render_talk_video(tid)
    assert rel == "talkfb1/talk.mp4"
    assert called.get("slideshow") is True
    assert (talks_dir / rel).is_file()
    meta = talk.read_talk_video_meta(tid)
    assert meta.get("backend") == "slideshow"


def test_vortrag_seite_zeigt_video_hinweise():
    src = Path("ragapp/ui/pages/17_🎤_Vortrag.py").read_text(encoding="utf-8")
    helper = Path("ragapp/ui/_pronunciation.py").read_text(encoding="utf-8")
    assert "_render_forced_eos" in src
    assert "erst dann das Video erzeugen" in src
    assert "Animierte Folien, synchron zur Stimme" in src
    assert "Diashow-Video erzeugt" in src
    assert "passgenaue Punkte" in src
    assert "Abgebrochene Sätze" in helper
