"""Referenzstimme: Dauer/Pegel prüfen, Mono-WAV speichern, alte Datei nicht überschreiben."""
from __future__ import annotations

import io
import math

import pytest
import torch
import torchaudio

from ragapp import student_flow
from ragapp.config import settings


def _wav_bytes(seconds: float, *, sr: int = 44100, peak: float = 0.4, channels: int = 1) -> bytes:
    n = int(seconds * sr)
    t = torch.arange(n, dtype=torch.float32) / float(sr)
    sig = peak * torch.sin(2 * math.pi * 220 * t)
    wav = sig.unsqueeze(0).repeat(channels, 1)
    buf = io.BytesIO()
    torchaudio.save(buf, wav, sr, format="wav")
    return buf.getvalue()


@pytest.fixture()
def ref_path(tmp_path, monkeypatch):
    dest = tmp_path / "reference.wav"
    monkeypatch.setattr(settings, "AUDIO_REFERENCE_WAV", str(dest), raising=False)
    return dest


def test_inspect_leere_bytes_wirft():
    with pytest.raises(student_flow.VoiceReferenceError, match="Keine Audiodaten"):
        student_flow.inspect_voice_audio(b"")


def test_inspect_zu_kurz(ref_path):
    info = student_flow.inspect_voice_audio(_wav_bytes(5))
    assert info["ok"] is False
    assert any("kurz" in e.lower() for e in info["errors"])
    assert "wav" not in info


def test_inspect_zu_leise():
    info = student_flow.inspect_voice_audio(_wav_bytes(31, peak=0.001))
    assert info["ok"] is False
    assert any("leise" in e.lower() for e in info["errors"])


def test_save_gueltige_aufnahme_wird_mono(ref_path):
    out = student_flow.save_voice_reference(_wav_bytes(31, channels=2, sr=16000, peak=0.5))
    assert ref_path.is_file()
    assert out["path"] == str(ref_path)
    assert out["ok"] is True
    assert out["channels_in"] == 1
    assert out["sample_rate"] == student_flow.VOICE_TARGET_SR
    assert out["duration_s"] >= 30
    wav, sr = torchaudio.load(str(ref_path))
    assert wav.shape[0] == 1
    assert int(sr) == student_flow.VOICE_TARGET_SR


def test_save_zu_kurz_ueberschreibt_nicht(ref_path):
    student_flow.save_voice_reference(_wav_bytes(31, peak=0.4))
    first = ref_path.read_bytes()
    with pytest.raises(student_flow.VoiceReferenceError, match="kurz"):
        student_flow.save_voice_reference(_wav_bytes(4, peak=0.4))
    assert ref_path.read_bytes() == first


def test_clipping_warnt_aber_speichert(ref_path):
    n = int(31 * 44100)
    wav = torch.ones(1, n)
    buf = io.BytesIO()
    torchaudio.save(buf, wav, 44100, format="wav")
    raw = buf.getvalue()
    info = student_flow.inspect_voice_audio(raw)
    assert info["ok"] is True
    assert any("clippt" in w.lower() for w in info["warnings"])
    student_flow.save_voice_reference(raw)
    assert ref_path.is_file()


def test_audio_seite_misst_referenz_vor_dem_speichern():
    from pathlib import Path
    src = Path("ragapp/ui/pages/15_🎧_Audio-Overview.py").read_text(encoding="utf-8")
    assert "_voice_capture_ui" in src
    assert "inspect_voice_audio" in src
    assert "Klon-Hörprobe" in src
    assert "disabled=not _preview[\"ok\"]" in src
    assert "synthesize_voice_probe" in src
    assert "def synthesize_voice_probe" in Path("ragapp/audio_overview.py").read_text(
        encoding="utf-8")
