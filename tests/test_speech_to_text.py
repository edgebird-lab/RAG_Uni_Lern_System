"""Tests für ragapp.speech_to_text (Sprachnotizen, lokales Whisper). Die echte
Modell-Transkription (Audio -> Text) wird bewusst NICHT hier, sondern per
echter Hörprobe/Live-Test verifiziert (siehe Session-Notizen: Audio-Qualität
lässt sich nicht durch Unit-Tests ersetzen) - diese Tests decken nur die
Fehler-/Grenzfaelle ab, die ohne Modell-Download pruefbar sind."""
from __future__ import annotations

from ragapp import speech_to_text


def test_is_available_meldet_installierte_pakete():
    # In dieser Testumgebung sind transformers/librosa installiert (siehe
    # requirements.txt) - is_available() soll das korrekt erkennen.
    assert speech_to_text.is_available() is True


def test_transcribe_audio_mit_leeren_bytes_liefert_leeren_string():
    assert speech_to_text.transcribe_audio(b"") == ""


def test_transcribe_audio_mit_kaputten_bytes_liefert_leeren_string():
    assert speech_to_text.transcribe_audio(b"das ist kein Audio, nur Text") == ""
