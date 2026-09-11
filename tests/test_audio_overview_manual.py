"""Tests für die manuellen/teilweisen Audio-Overview-Workflows:
- ``create_manual_audio_overview``: selbst geschriebenes Skript, kein LLM-Aufruf,
  keine Quelldokumente nötig.
- ``resynthesize_audio_overview``: NUR die Audiodatei aus einem (ggf. von Hand
  bearbeiteten) Skript neu erzeugen, ohne die KI-Generierung erneut anzustoßen.
- ``create_and_save_audio_overview``: prüft die Stimm-Referenz JETZT VOR der
  (teuren) Skript-Generierung, nicht erst danach.

Isoliert geladen (siehe test_audio_overview_script.py für die Begründung) -
``manifest``, ``synthesize_speech``, ``unload_tts_model`` werden gefaked, damit
kein echtes XTTS-v2/torch geladen wird."""
import types

import pytest


def _fake_settings(**overrides):
    base = dict(AUDIO_REFERENCE_WAV="voice/reference.wav", AUDIO_MAX_SCRIPT_CHARS=40000,
                LLM_MODEL_AUTHOR="", LLM_MODEL="fallback-model")
    base.update(overrides)
    ns = types.SimpleNamespace(**base)
    ns.author_model = lambda: (ns.LLM_MODEL_AUTHOR or "").strip() or ns.LLM_MODEL
    return ns


class _FakeManifest:
    """Sammelt Aufrufe zum Nachprüfen, hält eine kleine In-Memory-'DB' für
    ``get_audio_overview`` (so wie sie ``resynthesize_audio_overview`` vorher
    abfragt)."""
    def __init__(self, rows=None):
        self.rows = dict(rows or {})
        self.create_calls = []
        self.update_calls = []

    def create_audio_overview(self, **kwargs):
        oid = kwargs.get("overview_id") or "generated-id"
        self.rows[oid] = dict(kwargs, overview_id=oid)
        self.create_calls.append(kwargs)
        return oid

    def get_audio_overview(self, overview_id):
        return self.rows.get(overview_id)

    def update_audio_overview(self, overview_id, **fields):
        self.update_calls.append((overview_id, fields))
        if overview_id in self.rows:
            self.rows[overview_id].update(fields)


@pytest.fixture
def audio_funcs(load_functions, ragapp_dir, tmp_path):
    def _make(*, settings_obj=None, manifest_obj=None, synth_raises=None,
              generate_script_result=("Skript-Text.", None)):
        settings = settings_obj or _fake_settings()
        manifest_obj = manifest_obj or _FakeManifest()
        synth_calls = []

        def _fake_synthesize_speech(script_text, reference_wav_path, output_path, language=None):
            synth_calls.append({
                "script_text": script_text, "reference_wav_path": str(reference_wav_path),
                "output_path": str(output_path),
            })
            if synth_raises:
                raise synth_raises

        def _fake_generate_overview_script(doc_ids, subject, model=None):
            return generate_script_result

        funcs = load_functions(
            ragapp_dir / "audio_overview.py",
            ["create_manual_audio_overview", "resynthesize_audio_overview",
             "create_and_save_audio_overview", "_synthesize_and_persist",
             "_require_reference_wav"],
            {
                "settings": settings,
                "manifest": manifest_obj,
                "PROJECT_ROOT": tmp_path,
                "AUDIO_DIR": tmp_path / "audio_overviews",
                "synthesize_speech": _fake_synthesize_speech,
                "unload_tts_model": lambda: None,
                "generate_overview_script": _fake_generate_overview_script,
                "AudioOverviewError": RuntimeError,
                "Optional": None,
                "uuid": __import__("uuid"),
                "Path": __import__("pathlib").Path,
            },
        )
        return types.SimpleNamespace(
            **funcs, manifest=manifest_obj, synth_calls=synth_calls, tmp_path=tmp_path)
    return _make


def _write_reference(tmp_path):
    ref = tmp_path / "voice" / "reference.wav"
    ref.parent.mkdir(parents=True, exist_ok=True)
    ref.write_bytes(b"RIFF....WAVEfmt ")
    return ref


# --------------------------------------------------------------------------- #
# create_manual_audio_overview
# --------------------------------------------------------------------------- #

def test_manual_overview_leerer_text_wirft_error(audio_funcs):
    env = audio_funcs()
    _write_reference(env.tmp_path)
    with pytest.raises(RuntimeError, match="Skript-Text eingeben"):
        env.create_manual_audio_overview("   ", "Titel")


def test_manual_overview_ohne_referenzstimme_wirft_error(audio_funcs):
    env = audio_funcs()  # keine reference.wav geschrieben
    with pytest.raises(RuntimeError, match="Stimm-Referenz"):
        env.create_manual_audio_overview("Mein eigener Text.", "Titel")
    assert env.synth_calls == []  # gar nicht erst versucht zu vertonen


def test_manual_overview_erfolgsfall_speichert_ohne_dokumente_und_modell(audio_funcs):
    env = audio_funcs()
    _write_reference(env.tmp_path)
    oid = env.create_manual_audio_overview("Mein eigener Text.", "Meine Notiz", subject=None)
    assert len(env.synth_calls) == 1
    assert env.synth_calls[0]["script_text"] == "Mein eigener Text."
    assert len(env.manifest.create_calls) == 1
    call = env.manifest.create_calls[0]
    assert call["doc_ids"] == []
    assert call["subject"] is None
    assert call["model"] is None
    assert call["script_text"] == "Mein eigener Text."
    assert call["overview_id"] == oid


def test_manual_overview_mit_fach(audio_funcs):
    env = audio_funcs()
    _write_reference(env.tmp_path)
    env.create_manual_audio_overview("Text.", "Titel", subject="DSA")
    assert env.manifest.create_calls[0]["subject"] == "DSA"


# --------------------------------------------------------------------------- #
# resynthesize_audio_overview
# --------------------------------------------------------------------------- #

def test_resynthesize_unbekannte_id_wirft_error(audio_funcs):
    env = audio_funcs()
    _write_reference(env.tmp_path)
    with pytest.raises(RuntimeError, match="nicht gefunden"):
        env.resynthesize_audio_overview("unbekannt", "Neuer Text.")


def test_resynthesize_leerer_text_wirft_error(audio_funcs):
    manifest_obj = _FakeManifest(rows={"abc": {"audio_path": "abc.wav"}})
    env = audio_funcs(manifest_obj=manifest_obj)
    _write_reference(env.tmp_path)
    with pytest.raises(RuntimeError, match="leer"):
        env.resynthesize_audio_overview("abc", "   ")


def test_resynthesize_nutzt_denselben_dateinamen_und_aktualisiert_nur_skript(audio_funcs):
    manifest_obj = _FakeManifest(rows={"abc": {"audio_path": "abc.wav", "title": "Alt"}})
    env = audio_funcs(manifest_obj=manifest_obj)
    _write_reference(env.tmp_path)
    env.resynthesize_audio_overview("abc", "Korrigierter Text ohne den falschen Fakt.")

    assert len(env.synth_calls) == 1
    assert env.synth_calls[0]["output_path"].endswith("abc.wav")  # GLEICHE Datei, keine neue ID
    assert env.synth_calls[0]["script_text"] == "Korrigierter Text ohne den falschen Fakt."
    # KEIN neuer DB-Eintrag - nur ein update_audio_overview-Aufruf:
    assert len(env.manifest.create_calls) == 0
    assert len(env.manifest.update_calls) == 1
    oid, fields = env.manifest.update_calls[0]
    assert oid == "abc"
    assert fields == {"script_text": "Korrigierter Text ohne den falschen Fakt."}


def test_resynthesize_ohne_referenzstimme_wirft_error_und_vertont_nicht(audio_funcs):
    manifest_obj = _FakeManifest(rows={"abc": {"audio_path": "abc.wav"}})
    env = audio_funcs(manifest_obj=manifest_obj)  # keine reference.wav
    with pytest.raises(RuntimeError, match="Stimm-Referenz"):
        env.resynthesize_audio_overview("abc", "Text.")
    assert env.synth_calls == []


# --------------------------------------------------------------------------- #
# create_and_save_audio_overview: Referenz-Check VOR der Skript-Generierung
# --------------------------------------------------------------------------- #

def test_create_and_save_prueft_referenz_bevor_skript_generiert_wird(audio_funcs):
    calls = []

    def _tracking_generate(doc_ids, subject, model=None):
        calls.append((doc_ids, subject))
        return ("Skript.", None)

    env = audio_funcs()  # keine reference.wav
    # generate_overview_script durch eine trackende Fake-Funktion ersetzen,
    # um zu pruefen, dass sie bei fehlender Referenz NIE aufgerufen wird.
    env.create_and_save_audio_overview.__globals__["generate_overview_script"] = _tracking_generate
    with pytest.raises(RuntimeError, match="Stimm-Referenz"):
        env.create_and_save_audio_overview(["doc1"], "DSA", "Titel")
    assert calls == []  # teure Skript-Generierung wurde gar nicht erst versucht


def test_create_and_save_erfolgsfall(audio_funcs):
    env = audio_funcs(generate_script_result=("Generiertes Skript.", None))
    _write_reference(env.tmp_path)
    oid, warning = env.create_and_save_audio_overview(["doc1"], "DSA", "Titel", model=None)
    assert warning is None
    assert env.manifest.create_calls[0]["doc_ids"] == ["doc1"]
    assert env.manifest.create_calls[0]["script_text"] == "Generiertes Skript."
