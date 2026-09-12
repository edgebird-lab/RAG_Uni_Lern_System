"""
Sprachnotizen: lokale Spracherkennung (Whisper)
================================================
Wandelt eine kurze Sprachaufnahme (siehe ``st.audio_input`` in Notizen.py) in
Text um - komplett lokal ueber ein Whisper-Modell (transformers-Pipeline,
kein Internet zur LAUFZEIT noetig, nur einmalig beim allerersten Aufruf zum
Herunterladen der Modellgewichte - genau dasselbe Muster wie ein einmaliger
Ollama-Modell-Pull). Ergaenzt die schon vorhandene Text-zu-Sprache
(Audio-Overview mit geklonter Stimme) um die umgekehrte Richtung: schneller
als Tippen auf dem Handy zwischen zwei Vorlesungen.

Laeuft standardmaessig auf der CPU (siehe settings.STT_MODEL-Kommentar in
config.py - dieselbe Vorsicht wie bei easyocr: eine GPU-Allokation unter
VRAM-Druck neben Ollama kann den amdgpu-Treiber haengen lassen). Fuer eine
kurze Sprachnotiz reicht CPU-Tempo voellig aus; bewusst aktivierbar mit
RAG_STT_GPU=1.
"""
from __future__ import annotations

import io
import os

from ragapp.config import settings

_PIPELINE = None
_PIPELINE_TRIED = False


def _get_pipeline():
    """Gibt die (gecachte) Whisper-ASR-Pipeline zurueck oder None, wenn
    transformers/das Modell nicht verfuegbar ist."""
    global _PIPELINE, _PIPELINE_TRIED
    if _PIPELINE_TRIED:
        return _PIPELINE
    _PIPELINE_TRIED = True
    try:
        from transformers import pipeline
        use_gpu = os.environ.get("RAG_STT_GPU") == "1"
        device = 0 if use_gpu else -1
        _PIPELINE = pipeline("automatic-speech-recognition", model=settings.STT_MODEL,
                             device=device)
    except Exception:  # noqa: BLE001
        _PIPELINE = None
    return _PIPELINE


def is_available() -> bool:
    """True, wenn eine Sprachnotiz-Transkription grundsaetzlich moeglich ist
    (benoetigte Pakete installiert) - fuer eine fruehe, klare Fehlermeldung
    in der UI statt eines stillen leeren Transkripts."""
    try:
        import transformers  # noqa: F401
        import librosa  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def transcribe_audio(audio_bytes: bytes) -> str:
    """Transkribiert eine Sprachaufnahme (WAV/OGG/... - jedes von librosa
    lesbare Format) zu deutschem Text. Gibt bei Fehler/fehlendem Modell/
    leerer Aufnahme einen leeren String zurueck (Aufrufer zeigt dann eine
    Fehlermeldung statt eines rätselhaft leeren Notiz-Entwurfs, siehe
    Notizen.py)."""
    if not audio_bytes:
        return ""
    # Erst dekodieren (billig), DANACH erst das schwere Modell laden - eine
    # kaputte/leere Aufnahme soll nicht erst einen Modell-Download/-Ladevorgang
    # ausloesen, nur um dann doch nichts zu transkribieren.
    try:
        import librosa
        audio, _sr = librosa.load(io.BytesIO(audio_bytes), sr=16000, mono=True,
                                  duration=float(settings.STT_MAX_SECONDS))
    except Exception:  # noqa: BLE001
        return ""
    if audio is None or len(audio) == 0:
        return ""
    pipe = _get_pipeline()
    if pipe is None:
        return ""
    try:
        result = pipe(audio, generate_kwargs={"language": settings.STT_LANGUAGE,
                                              "task": "transcribe"})
        return (result.get("text") or "").strip()
    except Exception:  # noqa: BLE001
        return ""
