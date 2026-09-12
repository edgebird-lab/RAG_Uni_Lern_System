"""Tests für ragapp.audio_convert (WAV -> MP3/M4A für den Audio-Overview-
Download). Nutzt eine echte, kurze WAV-Datei und lässt torchaudio/ffmpeg
GENUINE konvertieren (kein Mock) - Audio-Qualität/Funktionsfähigkeit lässt
sich nicht durch Mocken verifizieren (Session-Konvention)."""
from __future__ import annotations

import io
import wave

import pytest

from ragapp import audio_convert


@pytest.fixture()
def tiny_wav_bytes() -> bytes:
    """Eine winzige (0.2s, 8kHz, Stille) aber VALIDE WAV-Datei - reicht, um
    echte Encoder-Aufrufe zu pruefen, ohne eine grosse Testdatei zu brauchen."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 1600)
    return buf.getvalue()


def test_supported_formats_enthaelt_wav_m4a_mp3():
    assert set(audio_convert.SUPPORTED_FORMATS.keys()) == {"wav", "m4a", "mp3"}


def test_convert_wav_bytes_wav_ist_passthrough(tiny_wav_bytes):
    assert audio_convert.convert_wav_bytes(tiny_wav_bytes, "wav") == tiny_wav_bytes


def test_convert_wav_bytes_unbekanntes_format_wirft_fehler(tiny_wav_bytes):
    with pytest.raises(audio_convert.AudioConvertError):
        audio_convert.convert_wav_bytes(tiny_wav_bytes, "ogg")


def test_convert_wav_bytes_nach_m4a_liefert_kleinere_valide_datei(tiny_wav_bytes):
    out = audio_convert.convert_wav_bytes(tiny_wav_bytes, "m4a")
    assert isinstance(out, bytes)
    assert len(out) > 0
    # MP4/M4A-Dateien beginnen mit einer "ftyp"-Box (Atom) im Header.
    assert b"ftyp" in out[:64]


def test_convert_wav_bytes_nach_mp3_liefert_valide_datei(tiny_wav_bytes):
    out = audio_convert.convert_wav_bytes(tiny_wav_bytes, "mp3")
    assert isinstance(out, bytes)
    assert len(out) > 0


def test_convert_wav_bytes_kaputte_bytes_wirft_audioconverterror():
    with pytest.raises(audio_convert.AudioConvertError):
        audio_convert.convert_wav_bytes(b"das ist keine WAV-Datei", "m4a")
