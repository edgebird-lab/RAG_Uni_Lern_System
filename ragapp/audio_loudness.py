"""EBU-R128-Lautheit fuer Sprache (Audio-Overview, Hoerbuch, Vortrags-Video)."""
from __future__ import annotations

import tempfile
from pathlib import Path

# Audible/ACX-typische Sprach-Ziele: -16 LUFS, True-Peak -1.5 dB.
LOUDNORM_FILTER = "loudnorm=I=-16:TP=-1.5:LRA=11"


def loudnorm_waveform(wav, sample_rate: int):
    """Normiert eine Wellenform auf Sprach-Lautheit. Wirft bei Encoder-Fehlern."""
    import torchaudio
    import torchaudio.io as tio

    if wav is None or wav.numel() == 0:
        return wav, sample_rate
    with tempfile.TemporaryDirectory() as tmp_dir:
        out = Path(tmp_dir) / "loudnorm.wav"
        writer = tio.StreamWriter(str(out))
        writer.add_audio_stream(
            sample_rate=int(sample_rate), num_channels=int(wav.shape[0]),
            encoder="pcm_s16le", filter_desc=LOUDNORM_FILTER)
        with writer.open():
            writer.write_audio_chunk(0, wav.T)
        return torchaudio.load(str(out))
