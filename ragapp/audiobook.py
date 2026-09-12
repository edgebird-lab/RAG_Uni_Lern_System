"""
Hörbuch-Export: mehrere Audio-Overviews zu einem getaggten Kapitel-Satz
=========================================================================
Nutzer-Report: Audio-Overviews werden einzeln als WAV heruntergeladen und von
Hand auf dem Handy zu einem Hörbuch zusammengefügt. Diese Funktion nimmt das
ab: mehrere bestehende Audio-Overviews werden - in einer gewählten Reihenfolge
- je Kapitel als M4A (AAC, deutlich kleiner als WAV) mit Kapitel-/Album-/
Track-Metadaten exportiert und als ZIP gebündelt. Jede Musik-/Hörbuch-App auf
dem Handy gruppiert die Dateien dank Album+Tracknummer automatisch richtig
sortiert unter einem Buchtitel - kein manuelles Zusammenfügen mehr nötig.

BEWUSST kein einzelnes M4B mit eingebetteter Kapitelliste: das bräuchte echte
MP4-Kapitel-Atome ("chpl"), die torchaudio (über sein ffmpeg-Backend) nicht
schreiben kann - nur flache Datei-Metadaten (title/album/track/artist). Die
Album+Track-Lösung erreicht denselben Zweck (richtige Reihenfolge, Kapitel-
Titel, ein Buchtitel) in praktisch jeder Musik-/Hörbuch-App, ganz ohne neue
externe Abhängigkeit: torchaudio bringt sein eigenes ffmpeg-Backend bereits
mit (bestätigt: ``torchaudio.io.StreamWriter`` kann hier live AAC/M4A
schreiben), ein zusätzliches System-``ffmpeg`` ist nicht nötig.

Zusätzlich wird jedes Kapitel per ffmpeg-``loudnorm``-Filter (EBU R128) auf
denselben Lautstärke-Zielwert normalisiert - separat generierte Audio-
Overviews klingen sonst beim Hintereinander-Abspielen oft unterschiedlich
laut, was beim manuellen Zusammenfügen als störender Lautstärke-Sprung
auffällt.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Callable, Optional

from ragapp.config import AUDIO_DIR, AUDIOBOOK_DIR
from ragapp import manifest

ProgressCallback = Optional[Callable[[int, int, str], None]]

# EBU-R128-Zielwerte fuer Sprache/Hoerbuecher (Standardempfehlung, z. B. auch
# von Audible/ACX fuer Hoerbuch-Abgaben genutzt: -16 LUFS integriert).
_LOUDNORM_FILTER = "loudnorm=I=-16:TP=-1.5:LRA=11"


class AudiobookError(RuntimeError):
    """Echter Fehler beim Hörbuch-Export (keine Auswahl, fehlende Audiodatei,
    AAC-Encoder nicht verfügbar)."""


def _safe_filename(name: str) -> str:
    """Macht aus einem Titel einen fuer Dateisystem/ZIP unbedenklichen Namen -
    ersetzt alles ausser Buchstaben/Ziffern/Leerzeichen/Bindestrich, kuerzt auf
    eine vernuenftige Laenge (lange KI-generierte Titel sollen nicht an
    Dateisystem-Grenzen scheitern)."""
    cleaned = re.sub(r"[^\w\- ]+", "", name, flags=re.UNICODE).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return (cleaned or "Hoerbuch")[:80]


def export_audiobook(overview_ids: list[str], book_title: str, *,
                     on_progress: ProgressCallback = None) -> Path:
    """Exportiert die gegebenen Audio-Overviews - IN GENAU DIESER REIHENFOLGE -
    als Hörbuch-ZIP: je Overview eine M4A-Datei (AAC, lautstärke-normalisiert)
    mit ``title``=Overview-Titel, ``album``=``book_title``, ``track``="i/N".
    Wirft ``AudiobookError`` bei leerer Auswahl oder einer fehlenden/gelöschten
    Audiodatei - lieber vorher klar abbrechen als ein unvollständiges Hörbuch
    zu bauen. ``on_progress`` (optional): siehe ``ProgressCallback`` - ein
    Aufruf je fertig kodiertem Kapitel. Gibt den Pfad zur fertigen ZIP-Datei
    zurück (liegt unter ``AUDIOBOOK_DIR``, bleibt zur mehrfachen Nutzung liegen
    - wie die einzelnen Audio-Overview-WAVs auch)."""
    if not overview_ids:
        raise AudiobookError("Bitte mindestens ein Audio-Overview auswählen.")

    rows: list[dict] = []
    for oid in overview_ids:
        row = manifest.get_audio_overview(oid)
        if row is None:
            raise AudiobookError("Ein Audio-Overview wurde nicht gefunden (evtl. gelöscht).")
        audio_path = AUDIO_DIR / row["audio_path"]
        if not audio_path.is_file():
            raise AudiobookError(
                f"Die Audiodatei für „{row['title']}“ fehlt (evtl. manuell gelöscht) - "
                "bitte neu vertonen, bevor du das Hörbuch exportierst.")
        rows.append(row)

    import torchaudio
    import torchaudio.io as tio
    from torchaudio.utils import ffmpeg_utils

    # torchaudios AAC-Encoder braucht die ffmpeg-Shared-Libraries des
    # SYSTEMS (bestaetigt per ldd: das venv bringt sie NICHT selbst mit, nur
    # eine inkompatible OpenCV-eigene Kopie in anderer Version) - anders als
    # der Rest der App (easyocr statt System-Tesseract, kein System-Graphviz
    # bei der Mindmap) ist das hier die einzige Stelle mit einer echten
    # System-Abhaengigkeit (``apt install ffmpeg`` unter Linux, siehe
    # install.sh). Klar abbrechen statt kryptisch mitten in der Kodierung zu
    # crashen, wenn sie fehlt.
    if "aac" not in ffmpeg_utils.get_audio_encoders():
        raise AudiobookError(
            "Für den Hörbuch-Export wird ein AAC-Encoder benötigt, den torchaudio "
            "hier nicht findet - meist fehlt dafür ffmpeg auf dem System. Unter "
            "Linux hilft `sudo apt install ffmpeg` (danach die App neu starten).")

    AUDIOBOOK_DIR.mkdir(parents=True, exist_ok=True)
    total = len(rows)
    digits = max(2, len(str(total)))
    chapters: list[tuple[str, Path]] = []
    try:
        for i, row in enumerate(rows, start=1):
            wav, sr = torchaudio.load(str(AUDIO_DIR / row["audio_path"]))
            chapter_num = str(i).zfill(digits)
            arcname = f"{chapter_num} - {_safe_filename(row['title'])}.m4a"
            tmp_path = AUDIOBOOK_DIR / f"_tmp_{chapter_num}.m4a"
            writer = tio.StreamWriter(str(tmp_path))
            writer.add_audio_stream(sample_rate=sr, num_channels=wav.shape[0],
                                    encoder="aac", filter_desc=_LOUDNORM_FILTER)
            writer.set_metadata({
                "title": row["title"], "album": book_title,
                "artist": "RAG-Lernsystem", "track": f"{i}/{total}",
            })
            with writer.open():
                writer.write_audio_chunk(0, wav.T)
            chapters.append((arcname, tmp_path))
            if on_progress:
                on_progress(i, total, row["title"])
    except Exception as exc:  # noqa: BLE001
        for _, tmp_path in chapters:
            tmp_path.unlink(missing_ok=True)
        raise AudiobookError(f"Hörbuch-Export fehlgeschlagen: {exc}") from exc

    zip_path = AUDIOBOOK_DIR / f"{_safe_filename(book_title)}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
        for arcname, tmp_path in chapters:
            zf.write(tmp_path, arcname=arcname)
    for _, tmp_path in chapters:
        tmp_path.unlink(missing_ok=True)
    return zip_path
