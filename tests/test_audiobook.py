"""Tests für ``ragapp.audiobook`` (Hörbuch-Export mehrerer Audio-Overviews als
getaggtes M4A-ZIP): Nutzer-Report - Audio-Overviews wurden bisher einzeln als
WAV heruntergeladen und von Hand auf dem Handy zu einem Hörbuch zusammen-
gefügt. Reale Kodierung über torchaudios eigenes ffmpeg-Backend (kein System-
``ffmpeg`` nötig, leichte CPU-Operation - kein Chatterbox-Modell, deshalb NICHT
über den AST-Isolationslader geladen, direkter Modul-Import genügt)."""
from __future__ import annotations

import zipfile

import pytest
import torch
import torchaudio

from ragapp import audiobook, manifest


@pytest.fixture()
def isolated_env(tmp_path, monkeypatch):
    """Isolierte Manifest-DB + isolierte AUDIO_DIR/AUDIOBOOK_DIR (niemals die
    echte data/-Struktur) - gleiches Muster wie test_manifest_audio_overviews.py,
    zusätzlich auf die in ``ragapp.audiobook`` per ``from ... import`` bereits
    gebundenen Namen angewendet (ein ``monkeypatch`` auf ``ragapp.config``
    allein würde diese gebundenen Kopien nicht erreichen)."""
    db_path = tmp_path / "manifest_test.db"
    monkeypatch.setattr(manifest, "MANIFEST_DB", db_path)
    monkeypatch.setattr(manifest, "_initialized", False, raising=False)

    audio_dir = tmp_path / "audio_overviews"
    audiobook_dir = tmp_path / "audiobooks"
    audio_dir.mkdir()
    monkeypatch.setattr(audiobook, "AUDIO_DIR", audio_dir)
    monkeypatch.setattr(audiobook, "AUDIOBOOK_DIR", audiobook_dir)
    return {"audio_dir": audio_dir, "audiobook_dir": audiobook_dir}


def _make_overview(isolated_env, *, title: str, filename: str, seconds: float = 0.2) -> str:
    """Legt einen echten (winzigen) WAV-Clip ab und registriert ihn als
    Audio-Overview - reale, aber sehr kurze Audiodaten, damit die Kodierung
    in den Tests schnell bleibt."""
    sr = 8000
    wav = 0.1 * torch.sin(torch.linspace(0, 440 * 2 * 3.14159 * seconds, int(sr * seconds))) \
        .unsqueeze(0)
    torchaudio.save(str(isolated_env["audio_dir"] / filename), wav, sr)
    return manifest.create_audio_overview(
        title=title, subject=None, doc_ids=[], script_text="x", audio_path=filename)


def test_leere_auswahl_wirft_error(isolated_env):
    with pytest.raises(audiobook.AudiobookError, match="mindestens ein"):
        audiobook.export_audiobook([], "Mein Buch")


def test_unbekannte_id_wirft_error(isolated_env):
    with pytest.raises(audiobook.AudiobookError, match="nicht gefunden"):
        audiobook.export_audiobook(["existiert-nicht"], "Mein Buch")


def test_fehlende_audiodatei_wirft_error(isolated_env):
    oid = manifest.create_audio_overview(
        title="Kaputt", subject=None, doc_ids=[], script_text="x", audio_path="fehlt.wav")
    with pytest.raises(audiobook.AudiobookError, match="fehlt"):
        audiobook.export_audiobook([oid], "Mein Buch")


def test_export_erzeugt_zip_mit_korrekter_kapitel_reihenfolge_und_tags(isolated_env):
    oid1 = _make_overview(isolated_env, title="Kapitel Eins", filename="a.wav")
    oid2 = _make_overview(isolated_env, title="Kapitel Zwei", filename="b.wav")

    zip_path = audiobook.export_audiobook([oid1, oid2], "Testbuch")

    assert zip_path.is_file()
    assert zip_path.suffix == ".zip"
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert names == ["01 - Kapitel Eins.m4a", "02 - Kapitel Zwei.m4a"]


def test_export_reihenfolge_folgt_uebergebener_liste_nicht_erstellungsreihenfolge(isolated_env):
    # oid2 wurde ZUERST angelegt, soll aber als KAPITEL 2 exportiert werden,
    # weil die uebergebene overview_ids-Liste das so vorgibt
    oid2 = _make_overview(isolated_env, title="Wird Kapitel Zwei", filename="a.wav")
    oid1 = _make_overview(isolated_env, title="Wird Kapitel Eins", filename="b.wav")

    zip_path = audiobook.export_audiobook([oid1, oid2], "Testbuch")
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert names == ["01 - Wird Kapitel Eins.m4a", "02 - Wird Kapitel Zwei.m4a"]


def test_zip_eintraege_haben_keine_ueberfluessigen_temp_dateien_hinterlassen(isolated_env):
    oid = _make_overview(isolated_env, title="Einzelkapitel", filename="a.wav")
    audiobook.export_audiobook([oid], "Solobuch")
    leftover = [p for p in isolated_env["audiobook_dir"].iterdir() if p.name.startswith("_tmp_")]
    assert leftover == []


def test_on_progress_wird_je_kapitel_aufgerufen(isolated_env):
    oid1 = _make_overview(isolated_env, title="Eins", filename="a.wav")
    oid2 = _make_overview(isolated_env, title="Zwei", filename="b.wav")
    calls = []
    audiobook.export_audiobook(
        [oid1, oid2], "Testbuch",
        on_progress=lambda done, total, label: calls.append((done, total, label)))
    assert calls == [(1, 2, "Eins"), (2, 2, "Zwei")]


def test_safe_filename_entfernt_unsichere_zeichen():
    assert audiobook._safe_filename('Fach: "Netzwerke" / "Sicherheit"?!') == "Fach Netzwerke Sicherheit"


def test_safe_filename_leer_nach_bereinigung_gibt_fallback():
    assert audiobook._safe_filename("###???") == "Hoerbuch"


def test_fehler_beim_kodieren_raeumt_bereits_erzeugte_temp_dateien_auf(isolated_env, monkeypatch):
    oid1 = _make_overview(isolated_env, title="Eins", filename="a.wav")
    oid2 = _make_overview(isolated_env, title="Zwei", filename="b.wav")

    import torchaudio.io as real_tio
    call_count = {"n": 0}
    real_stream_writer = real_tio.StreamWriter

    def _boom_on_second(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] >= 2:
            raise RuntimeError("Encoder-Fehler (simuliert)")
        return real_stream_writer(*args, **kwargs)

    monkeypatch.setattr(real_tio, "StreamWriter", _boom_on_second)
    with pytest.raises(audiobook.AudiobookError, match="fehlgeschlagen"):
        audiobook.export_audiobook([oid1, oid2], "Testbuch")
    leftover = list(isolated_env["audiobook_dir"].glob("_tmp_*"))
    assert leftover == []
