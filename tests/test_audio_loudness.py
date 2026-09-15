"""EBU-R128-Lautheit: leise und laute Clips landen auf demselben Pegel."""
from __future__ import annotations

import math

import torch

from ragapp.audio_loudness import LOUDNORM_FILTER, loudnorm_waveform


def _sine(peak: float, seconds: float = 2.0, sr: int = 24000):
    n = int(sr * seconds)
    t = torch.arange(n, dtype=torch.float32) / sr
    return (peak * torch.sin(2 * math.pi * 220 * t)).unsqueeze(0), sr


def test_loudnorm_filter_ist_ebu_sprache():
    assert "I=-16" in LOUDNORM_FILTER
    assert "TP=-1.5" in LOUDNORM_FILTER


def test_loudnorm_zieht_leise_und_laute_clips_zusammen():
    quiet, sr = _sine(0.05)
    loud, _ = _sine(0.8)
    qn, _ = loudnorm_waveform(quiet, sr)
    ln, _ = loudnorm_waveform(loud, sr)
    q_rms = float(qn.pow(2).mean().sqrt())
    l_rms = float(ln.pow(2).mean().sqrt())
    assert abs(q_rms - l_rms) < 0.02
    # Deutlich näher als die Roh-Signale (0.035 vs 0.57).
    raw_gap = abs(float(quiet.pow(2).mean().sqrt()) - float(loud.pow(2).mean().sqrt()))
    assert abs(q_rms - l_rms) < raw_gap / 5
