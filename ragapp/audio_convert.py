"""
Audio-Format-Konvertierung (WAV -> MP3/M4A)
=============================================
Nutzer-Wunsch: weg von reinen WAV-Downloads, stattdessen beim Herunterladen
eines Audio-Overviews den Dateityp waehlen koennen ("normales Hoerbuch-
Format", "eigene Converter integrieren"). Nutzt DENSELBEN torchaudio/ffmpeg-
Weg, der sich beim Hoerbuch-Export (ragapp/audiobook.py) schon bewaehrt hat -
kein neuer Dienst, kein neues System-Paket (ffmpeg wird dort schon
vorausgesetzt, siehe install.sh). Bewusst als EIGENES, kleines Modul statt in
audiobook.py: dort geht es um das MEHR-Kapitel-ZIP, hier nur um "eine WAV-
Datei in ein anderes Format wandeln" - beide Seiten (Einzel-Download,
Hoerbuch-Export) koennten diese Funktion nutzen.
"""
from __future__ import annotations

import io
import tempfile
from pathlib import Path

# label = UI-Text, ext = Datei-Endung, mime = fuer st.download_button(),
# encoder = torchaudio/ffmpeg-Encoder-Name ("" = WAV, keine Konvertierung noetig).
SUPPORTED_FORMATS: dict[str, dict] = {
    "wav": {"label": "WAV (unkomprimiert, größte Datei)", "ext": "wav",
            "mime": "audio/wav", "encoder": ""},
    "m4a": {"label": "M4A / AAC (Hörbuch-Standard, kleine Datei)", "ext": "m4a",
            "mime": "audio/mp4", "encoder": "aac"},
    "mp3": {"label": "MP3 (überall abspielbar, kleine Datei)", "ext": "mp3",
            "mime": "audio/mpeg", "encoder": "libmp3lame"},
}


class AudioConvertError(RuntimeError):
    """Konvertierung fehlgeschlagen (Encoder fehlt, kaputte Eingabedatei)."""


def convert_wav_bytes(wav_bytes: bytes, target_format: str) -> bytes:
    """Wandelt WAV-Bytes in das gewuenschte Zielformat (siehe SUPPORTED_FORMATS)
    um. ``target_format="wav"`` gibt die Eingabe unveraendert zurueck (kein
    Konvertierungsschritt noetig - WAV ist ja schon das Quellformat). Wirft
    ``AudioConvertError`` bei fehlendem Encoder oder Konvertierungsfehler -
    der Aufrufer zeigt dann eine klare Meldung statt einer kaputten Datei."""
    if target_format not in SUPPORTED_FORMATS:
        raise AudioConvertError(f"Unbekanntes Zielformat: {target_format!r}")
    spec = SUPPORTED_FORMATS[target_format]
    if not spec["encoder"]:
        return wav_bytes

    import torchaudio
    import torchaudio.io as tio
    from torchaudio.utils import ffmpeg_utils

    # Gleiche Absicherung wie beim Hoerbuch-Export: klar abbrechen statt
    # kryptisch mitten in der Kodierung zu crashen, wenn der System-ffmpeg
    # (torchaudios Backend) den Encoder nicht mitbringt.
    if spec["encoder"] not in ffmpeg_utils.get_audio_encoders():
        raise AudioConvertError(
            f"Für {target_format.upper()} wird der Encoder „{spec['encoder']}\" benötigt, "
            "den torchaudio hier nicht findet - meist fehlt dafür ffmpeg auf dem "
            "System (unter Linux hilft `sudo apt install ffmpeg`, danach die App "
            "neu starten).")

    try:
        wav, sr = torchaudio.load(io.BytesIO(wav_bytes))
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / f"out.{spec['ext']}"
            writer = tio.StreamWriter(str(tmp_path))
            writer.add_audio_stream(sample_rate=sr, num_channels=wav.shape[0],
                                    encoder=spec["encoder"])
            with writer.open():
                writer.write_audio_chunk(0, wav.T)
            return tmp_path.read_bytes()
    except Exception as exc:  # noqa: BLE001
        raise AudioConvertError(
            f"Konvertierung nach {target_format.upper()} fehlgeschlagen: {exc}") from exc
