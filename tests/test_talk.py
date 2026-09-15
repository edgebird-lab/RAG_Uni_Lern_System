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
    card = clamp_slide_grammar(
        "<!-- _class: card -->\n\n## **42 %**\n\n- weg\n- auch weg\n")
    assert "- weg" not in card
    promoted = clamp_slide_grammar(
        "<!-- _class: content -->\n\n## **Grounding**\n")
    assert "_class: card" in promoted
    keep = clamp_slide_grammar(
        "<!-- _class: content -->\n\n## Langer Titel ohne Zahl\n")
    assert "_class: content" in keep
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
    assert "_class: content --> oder accent|split|warn|card" in _SECTION_PROMPT
    assert "bevorzugt **card**" in _SECTION_PROMPT
    assert "KEINE Stichpunkte" in _OPENING_PROMPT
    assert "**Hook-Wort**" in _OPENING_PROMPT
    assert "Cold Open" in _OPENING_PROMPT
    assert "KEIN Begrüßungs-Fluff" in _OPENING_PROMPT
    assert "ZUERST" in _OPENING_PROMPT
    from ragapp.talk import _OPENING_PROMPT_YOUTUBE, _SECTION_PROMPT_YOUTUBE
    assert "GENAU EINE Folie" in _OPENING_PROMPT_YOUTUBE
    assert "KEINE Agenda-Folie" in _OPENING_PROMPT_YOUTUBE
    assert "VERBOTEN: content" in _SECTION_PROMPT_YOUTUBE
    assert "Du-Form" in _SECTION_PROMPT_YOUTUBE
    assert "Klausur" in _SECTION_PROMPT_YOUTUBE
    assert "Erste 3 Sekunden" in _OPENING_PROMPT_YOUTUBE
    assert "Klausur" in _OPENING_PROMPT_YOUTUBE


def test_fallback_opening_is_cold_open_not_welcome():
    from ragapp.talk import (
        _fallback_hook_line,
        _fallback_opening_script,
        _fallback_opening_slides,
    )
    excerpt = (
        "Grounding heißt: nur schreiben, was in der Unterlage steht. "
        "Der Rest ist Spekulation."
    )
    hook = _fallback_hook_line("Livetest Grounding", excerpt)
    assert hook.startswith("Grounding")
    assert not hook.lower().startswith("willkommen")
    slides = _fallback_opening_slides(
        "Livetest Grounding", "Livetest",
        ["Begriff klären", "Beispiel"], hook)
    assert slides.strip().startswith("<!-- _class: lead -->")
    assert "<!-- _class: agenda -->" in slides
    assert slides.index("lead") < slides.index("agenda")
    assert "Was du heute mitnimmst" not in slides
    assert hook in slides
    script = _fallback_opening_script(
        "Livetest Grounding", hook, ["Begriff klären", "Beispiel"])
    assert not script.lower().startswith("willkommen")
    assert hook in script
    assert "Fahrplan" in script


def test_pack_youtube_slides_drops_agenda_and_cards_content():
    from ragapp.talk import (
        _fallback_opening_slides_youtube,
        pack_youtube_slides,
    )
    raw = (
        "<!-- _class: lead -->\n\n# T\n\n---\n\n"
        "<!-- _class: agenda -->\n\n## Heute\n\n1. A\n2. B\n\n---\n\n"
        "<!-- _class: content -->\n\n## Grounding\n\n- nur schreiben was da steht\n"
    )
    out = pack_youtube_slides(raw)
    assert "_class: agenda" not in out
    assert "_class: lead" in out
    assert "_class: card" in out
    assert "Grounding" in out
    yt = _fallback_opening_slides_youtube("Livetest", "Livetest", "Abrufen schlägt Nachlesen.")
    assert "_class: lead" in yt
    assert "_class: agenda" not in yt
    mashed = pack_youtube_slides(
        "<!-- _class: card --> Testing\n<!-- _class: accent --> Abruf hält.")
    assert mashed.count("_class: card") == 1
    assert mashed.count("_class: accent") == 1
    assert "## **Testing**" in mashed
    assert "## **Abruf hält.**" in mashed


def test_sanitize_lead_eyebrow_and_glued_hr():
    import re
    from ragapp.talk import _sanitize_one_slide, pack_youtube_slides, validate_marp_markdown
    lead = (
        '<!-- _class: lead -->\n'
        '<p class="eyebrow">Livetest</p>\n'
        "# **Hook**\n"
        "### Behauptung\n"
    )
    out = _sanitize_one_slide(lead)
    assert re.search(r"</p>\s*\n\s*\n# \*\*Hook\*\*", out)
    glued = (
        "<!-- _class: accent -->\n\n"
        "## **Aktiver Abruf verlängert das Behalten.---**\n"
    )
    clean = _sanitize_one_slide(glued)
    assert "---" not in clean
    assert "Behalten.**" in clean
    packed = pack_youtube_slides(lead + "\n---\n\n" + glued)
    assert "---**" not in packed
    md = validate_marp_markdown("---\nmarp: true\n---\n\n" + lead)
    assert re.search(r"</p>\s*\n\s*\n# \*\*Hook\*\*", md)


def test_ensure_youtube_takeaway_adds_accent_before_sources():
    from ragapp.talk import (
        _ensure_youtube_takeaway,
        _fallback_opening_script_youtube,
    )
    body = (
        "<!-- _class: card -->\n\n## Karte 1\n\n"
        "---\n\n<!-- _class: sources -->\n\n## Quellen\n- a\n"
    )
    packed = _ensure_youtube_takeaway(body, "Hallo Welt. Das merkst du dir.")
    assert "Merke dir das" in packed
    assert "_class: accent" in packed
    assert packed.rfind("Merke dir das") < packed.rfind("Quellen")
    assert "Das merkst du dir." in packed
    again = _ensure_youtube_takeaway(packed, "Anderer Satz.")
    assert again.count("Merke dir das") == 1
    opening = _fallback_opening_script_youtube(
        "Grounding", "Abrufen schlägt Nachlesen.")
    assert "Weißt du" in opening
    assert "Klausur" in opening
    assert "Abrufen schlägt Nachlesen." in opening
    src = Path("ragapp/talk.py").read_text(encoding="utf-8")
    assert "body = _ensure_youtube_takeaway(body, script)" in src


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
    assert "1280:720" in joined
    assert "-tune" in cmd and "stillimage" in cmd
    yt = build_ffmpeg_xfade_cmd(
        [p1, p2], audio, out, per_slide_s=3.0,
        width=1920, height=1080, stillimage=False)
    yt_join = " ".join(yt)
    assert "1920:1080" in yt_join
    assert "stillimage" not in yt_join
    assert "-crf" in yt
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
    assert "stillimage" in cmd
    yt = build_ffmpeg_concat_cmd(concat, audio, out, stillimage=False)
    assert "stillimage" not in yt
    assert "-crf" in yt


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


def test_find_talk_music_bed_skips_reference(tmp_path, monkeypatch):
    monkeypatch.setattr(talk, "TALK_DIR", tmp_path)
    monkeypatch.setattr("ragapp.config.DATA_DIR", tmp_path)
    monkeypatch.setattr("ragapp.config.PROJECT_ROOT", tmp_path)
    (tmp_path / "reference.wav").write_bytes(b"RIFF")
    assert talk.find_talk_music_bed() is None
    bed = tmp_path / "bed.wav"
    bed.write_bytes(b"RIFF....")
    found = talk.find_talk_music_bed()
    assert found == bed


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
    assert talk.RECORD_FPS == 30
    rec = Path("ragapp/marp_record.mjs").read_text(encoding="utf-8")
    assert "Math.min(30" in rec
    assert "process.argv[6]" in rec
    assert "jpegQuality" in rec
    assert "width >= 1920 ? 95" in rec
    assert "deviceScaleFactor = width >= 1920 ? 2" in rec
    assert "music_bed: bool = False" in src
    assert "sidechaincompress" in src
    assert "YOUTUBE_HOLD_S" in src
    assert "YOUTUBE_BED_VOLUME" in src
    assert "_mix_cut_sfx" in src
    assert 'scale={width}:{height}:flags=lanczos' in src
    ui = Path("ragapp/ui/pages/17_🎤_Vortrag.py").read_text(encoding="utf-8")
    assert "talk_use_music_bed" in ui
    assert "talk_use_broll" in ui
    assert "talk_youtube_style" in ui
    assert "bool(_broll) or bool(_youtube)" in ui


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

    def fake_slideshow(html_path, md_path, dd, audio_path, out_path, **_k):
        called["slideshow"] = True
        Path(out_path).write_bytes(b"mp4fake")

    monkeypatch.setattr(talk, "record_presenter_video", boom)
    monkeypatch.setattr(talk, "_render_slideshow_video", fake_slideshow)
    rel = talk.render_talk_video(tid)
    assert rel == "talkfb1/talk.mp4"
    assert called.get("slideshow") is True
    assert (talks_dir / rel).is_file()
    from ragapp.talk_cues import CUE_VERSION
    meta = talk.read_talk_video_meta(tid)
    assert meta.get("backend") == "slideshow"
    assert meta.get("cues_version") == CUE_VERSION
    assert meta.get("figures") == []
    assert meta.get("music_bed") is False
    assert meta.get("youtube") is False
    assert meta.get("broll") == []


def test_vortrag_seite_zeigt_video_hinweise():
    src = Path("ragapp/ui/pages/17_🎤_Vortrag.py").read_text(encoding="utf-8")
    helper = Path("ragapp/ui/_pronunciation.py").read_text(encoding="utf-8")
    assert "_render_forced_eos" in src
    assert "erst dann das Video erzeugen" in src
    assert "Animierte Folien, synchron zur Stimme" in src
    assert "statische Handout" in src
    assert "B-Roll" in src
    assert "Unterzeile aus den Sätzen" in src
    assert "Diashow-Video erzeugt" in src
    assert "passgenaue Punkte" in src
    assert "Abgebrochene Sätze" in helper
    assert "Stille kürzen" in src
    assert "Im YouTube-Stil trotzdem an" in src


def test_speech_windows_merge_and_remap():
    from ragapp.talk import remap_timeline_to_windows, speech_windows_from_timeline
    timeline = [
        {"index": 0, "text": "A", "start_s": 0.0, "duration_s": 0.5},
        {"index": 1, "text": "B", "start_s": 0.7, "duration_s": 0.5},
        {"index": 2, "text": "C", "start_s": 3.0, "duration_s": 0.5},
    ]
    windows = speech_windows_from_timeline(timeline, 4.0, pad_s=0.14)
    assert len(windows) == 2
    assert windows[0][0] == 0.0
    assert windows[0][1] == pytest.approx(1.34)
    assert windows[1][0] == pytest.approx(2.86)
    remapped = remap_timeline_to_windows(timeline, windows)
    assert remapped[0]["start_s"] == 0.0
    assert remapped[1]["start_s"] == pytest.approx(0.7)
    assert remapped[2]["start_s"] < 3.0
    assert remapped[2]["duration_s"] == 0.5


def test_trim_talk_wav_drops_long_pauses(tmp_path):
    import shutil
    import subprocess
    from ragapp.talk import probe_audio_duration_s, trim_talk_wav_to_speech
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg fehlt")
    wav = tmp_path / "src.wav"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=24000:duration=0.6",
        "-f", "lavfi", "-t", "1.8", "-i", "anullsrc=r=24000:cl=mono",
        "-f", "lavfi", "-i", "sine=frequency=660:sample_rate=24000:duration=0.6",
        "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1[out]",
        "-map", "[out]", str(wav),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        pytest.skip(proc.stderr[-200:] if proc.stderr else "ffmpeg lavfi skip")
    timeline = [
        {"index": 0, "text": "eins", "start_s": 0.0, "duration_s": 0.6},
        {"index": 1, "text": "zwei", "start_s": 2.4, "duration_s": 0.6},
    ]
    out = tmp_path / "yt.wav"
    new_tl, path, trimmed = trim_talk_wav_to_speech(wav, timeline, out)
    assert trimmed is True
    assert path == out
    assert wav.stat().st_size > 0
    src_dur = probe_audio_duration_s(wav)
    out_dur = probe_audio_duration_s(out)
    assert src_dur == pytest.approx(3.0, abs=0.15)
    assert out_dur < src_dur - 0.8
    assert new_tl[1]["start_s"] < 1.6


def test_render_talk_video_trims_silence_only_for_youtube(isolated_db, tmp_path, monkeypatch):
    talks_dir = tmp_path / "talks"
    talks_dir.mkdir()
    monkeypatch.setattr(talk, "TALK_DIR", talks_dir)
    monkeypatch.setattr("ragapp.config.TALK_DIR", talks_dir)
    tid = manifest.create_talk(
        title="Trim", subject="Livetest", doc_ids=[],
        marp_md="---\nmarp: true\n---\n\n# Hi",
        script_text="Hallo.",
        audio_path="trim1/audio.wav",
        talk_id="trim1",
    )
    d = talks_dir / "trim1"
    d.mkdir(parents=True)
    (d / "audio.wav").write_bytes(b"RIFF")
    (d / "timeline.json").write_text(
        '[{"index":0,"text":"Hallo.","start_s":0.0,"duration_s":0.4},'
        '{"index":1,"text":"Welt.","start_s":2.0,"duration_s":0.4}]',
        encoding="utf-8")
    monkeypatch.setattr(talk, "run_marp", lambda *a, **k: d / "talk.html")
    (d / "talk.html").write_text("<html><body></body></html>", encoding="utf-8")
    monkeypatch.setattr(talk, "probe_audio_duration_s", lambda p: 2.5)
    calls = []

    def fake_trim(wav, timeline, out, **_k):
        calls.append(str(out))
        Path(out).write_bytes(b"RIFFYT")
        return ([{"index": 0, "start_s": 0.0, "duration_s": 0.4, "text": "Hallo."}],
                Path(out), True)

    monkeypatch.setattr(talk, "trim_talk_wav_to_speech", fake_trim)

    def boom(*_a, **_k):
        raise talk.TalkError("boom")

    monkeypatch.setattr(talk, "record_presenter_video", boom)
    monkeypatch.setattr(talk, "_render_slideshow_video", lambda *a, **k: (d / "talk.mp4").write_bytes(b"mp4"))
    talk.render_talk_video("trim1", youtube_style=True)
    assert calls
    meta = talk.read_talk_video_meta("trim1")
    assert meta.get("youtube") is True
    assert meta.get("silence_trim") is True
    calls.clear()
    talk.render_talk_video("trim1", youtube_style=False)
    assert not calls
    meta2 = talk.read_talk_video_meta("trim1")
    assert meta2.get("youtube") is False
    assert meta2.get("silence_trim") is False


def test_shot_cut_times_skips_open_and_tail():
    times = talk._shot_cut_times({
        "duration_s": 10.0,
        "events": [
            {"type": "shot", "t": 0.0},
            {"type": "shot", "t": 3.2},
            {"type": "word", "t": 4.0},
            {"type": "shot", "t": 9.8},
        ],
    })
    assert times == [3.2]


def test_make_cut_click_skips_reference_name(tmp_path):
    assert talk._make_cut_click(tmp_path / "reference.wav") is None
    assert talk._make_cut_click(tmp_path / "ref.wav") is None


def test_make_cut_click_writes_wav(tmp_path):
    import shutil
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg fehlt")
    path = tmp_path / "_yt_cut_click.wav"
    out = talk._make_cut_click(path)
    assert out == path
    assert path.is_file()
    assert path.stat().st_size > 200


def test_create_talk_record_youtube_enables_broll(isolated_db, tmp_path, monkeypatch):
    called = {}

    def fake_attach(md, doc_ids, *, dest_dir, broll=False, broll_query=""):
        called["broll"] = bool(broll)
        return md

    monkeypatch.setattr("ragapp.talk_figures.attach_talk_figures", fake_attach)
    talks_dir = tmp_path / "talks"
    talks_dir.mkdir()
    monkeypatch.setattr(talk, "TALK_DIR", talks_dir)
    monkeypatch.setattr("ragapp.config.TALK_DIR", talks_dir)
    talk.create_talk_record(
        title="T", subject="Livetest", doc_ids=[],
        marp_md="---\nmarp: true\n---\n\n# Hi",
        script_text="Hallo.",
        broll=False, youtube_style=True, talk_id="ytbroll1")
    assert called.get("broll") is True

