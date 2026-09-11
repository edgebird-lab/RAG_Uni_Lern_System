"""Tests für das Sprachqualitäts-/Tempo-Tuning der XTTS-v2-Synthese
(``ragapp.audio_overview``):
- ``_pause_ms_to_samples``: reine Umrechnung ms -> Samples für den Pausen-Fix
  (coqui-tts fügt sonst nach JEDEM Satz eine feste ~417ms-Stille an, siehe
  Moduldoc/Kommentare in audio_overview.py).
- ``synthesize_speech``: reicht die Tuning-Parameter (speed/temperature/
  repetition_penalty/gpt_cond_*) tatsächlich an ``tts.tts_to_file`` durch,
  statt sie nur in ``settings`` liegen zu lassen.
- ``_apply_fade``/``_rebuild_from_speech_regions``: die reine Logik hinter
  ``_clean_audio_gaps`` (Nachbearbeitung gegen ein bekanntes, in der
  coqui-tts-Community dokumentiertes XTTS-v2-Artefakt: hörbares Rauschen/
  Gebrabbel an Satzgrenzen UND Klick-Geräusche an Schnittstellen) - OHNE den
  eigentlichen Silero-VAD-Aufruf, der echte Sprache in echten Audiodaten
  braucht und deshalb nur per echtem End-to-End-Test sinnvoll verifizierbar
  ist (siehe Commit-Beschreibung für den realen Vorher-Nachher-Vergleich).

Isoliert geladen - ``_apply_pause_length``/``_get_tts``/``_clean_audio_gaps``
werden hier gefaked, damit KEIN echter TTS/transformers-Import ausgelöst wird
(das würde ohne den isin_mps_friendly-Shim aus ``_get_tts`` fehlschlagen und
wäre für einen reinen Kwargs-Durchreich-Test ohnehin unnötig langsam).
``_apply_fade``/``_rebuild_from_speech_regions`` brauchen dagegen nur
``array`` (Stdlib) - kein TTS/Torch-Import nötig."""
import array
import types

import pytest


def _fake_settings(**overrides):
    base = dict(
        AUDIO_LANGUAGE="de", AUDIO_TTS_SPEED=1.1, AUDIO_TTS_TEMPERATURE=0.7,
        AUDIO_TTS_REPETITION_PENALTY=4.0, AUDIO_TTS_PAUSE_MS=250,
        AUDIO_TTS_GPT_COND_LEN=24, AUDIO_TTS_GPT_COND_CHUNK_LEN=6, AUDIO_TTS_MAX_REF_LEN=30,
        AUDIO_TTS_MAX_GAP_MS=900,
    )
    base.update(overrides)
    return types.SimpleNamespace(**base)


# --------------------------------------------------------------------------- #
# _pause_ms_to_samples
# --------------------------------------------------------------------------- #

@pytest.fixture
def pause_fn(load_functions, ragapp_dir):
    return load_functions(
        ragapp_dir / "audio_overview.py", ["_pause_ms_to_samples"], {},
        const_names=["_XTTS_OUTPUT_SAMPLE_RATE"],
    )["_pause_ms_to_samples"]


def test_pause_ms_to_samples_rechnet_mit_24khz_um(pause_fn):
    assert pause_fn(250) == 6000       # 0.25s * 24000Hz
    assert pause_fn(1000) == 24000
    assert pause_fn(0) == 0


def test_pause_ms_to_samples_urspruenglicher_modell_standard_ist_rund_417ms(pause_fn):
    # coqui-tts' eigener Default PAD_SILENCE_SAMPLES=10000 entspricht ~417ms -
    # Regressionsanker dafür, dass die Umrechnung zur echten Modell-Samplerate passt.
    assert pause_fn(417) == pytest.approx(10008, abs=50)


def test_pause_ms_to_samples_negativ_wird_auf_null_gekappt(pause_fn):
    assert pause_fn(-50) == 0


# --------------------------------------------------------------------------- #
# synthesize_speech: Tuning-Parameter werden durchgereicht
# --------------------------------------------------------------------------- #

@pytest.fixture
def synth_env(load_functions, ragapp_dir):
    def _make(*, settings_obj=None, vram_ok=True):
        settings_obj = settings_obj or _fake_settings()
        pause_calls = []
        tts_to_file_calls = []
        clean_calls = []

        class _FakeTTS:
            def tts_to_file(self, **kwargs):
                tts_to_file_calls.append(kwargs)

        funcs = load_functions(
            ragapp_dir / "audio_overview.py", ["synthesize_speech"],
            {
                "settings": settings_obj,
                "_prepare_vram_for_tts": lambda: (vram_ok, "" if vram_ok else "kein VRAM"),
                "_get_tts": lambda: _FakeTTS(),
                "_apply_pause_length": lambda ms: pause_calls.append(ms),
                "_clean_audio_gaps": lambda *a, **kw: clean_calls.append(kw) or 0,  # eigene Tests unten
                "AudioOverviewError": RuntimeError,
                "Optional": None,
                "Path": __import__("pathlib").Path,
            },
        )
        return types.SimpleNamespace(
            **funcs, pause_calls=pause_calls, tts_to_file_calls=tts_to_file_calls,
            clean_calls=clean_calls)
    return _make


def test_synthesize_speech_reicht_tuning_parameter_durch(synth_env):
    env = synth_env()
    env.synthesize_speech("Text.", "ref.wav", "out.wav")

    assert env.pause_calls == [250]
    assert len(env.tts_to_file_calls) == 1
    call = env.tts_to_file_calls[0]
    assert call["speed"] == 1.1
    assert call["temperature"] == 0.7
    assert call["repetition_penalty"] == 4.0
    assert call["gpt_cond_len"] == 24
    assert call["gpt_cond_chunk_len"] == 6
    assert call["max_ref_len"] == 30
    assert call["text"] == "Text."
    assert call["language"] == "de"
    assert env.clean_calls == [{"max_pause_ms": 900}]


def test_synthesize_speech_nutzt_geaenderte_settings(synth_env):
    settings_obj = _fake_settings(AUDIO_TTS_SPEED=1.25, AUDIO_TTS_PAUSE_MS=100,
                                  AUDIO_TTS_TEMPERATURE=0.5, AUDIO_TTS_MAX_GAP_MS=600)
    env = synth_env(settings_obj=settings_obj)
    env.synthesize_speech("Text.", "ref.wav", "out.wav")

    assert env.pause_calls == [100]
    assert env.tts_to_file_calls[0]["speed"] == 1.25
    assert env.tts_to_file_calls[0]["temperature"] == 0.5
    assert env.clean_calls == [{"max_pause_ms": 600}]


def test_synthesize_speech_kein_vram_wirft_error_ohne_zu_vertonen(synth_env):
    env = synth_env(vram_ok=False)
    with pytest.raises(RuntimeError):
        env.synthesize_speech("Text.", "ref.wav", "out.wav")
    assert env.tts_to_file_calls == []
    assert env.pause_calls == []
    assert env.clean_calls == []


# --------------------------------------------------------------------------- #
# _apply_fade
# --------------------------------------------------------------------------- #

@pytest.fixture
def fade_fn(load_functions, ragapp_dir):
    return load_functions(
        ragapp_dir / "audio_overview.py", ["_apply_fade"], {"array": array},
    )["_apply_fade"]


def test_apply_fade_rampt_erste_und_letzte_samples_herunter(fade_fn):
    chunk = array.array("h", [1000] * 40)
    out = fade_fn(chunk, 10)
    assert out[0] == 0                 # erstes Sample: Fade startet bei 0
    assert 0 < out[5] < 1000           # mittendrin in der Rampe
    assert out[10] == 1000             # Rampe fertig, voller Pegel
    assert out[-1] == 0                # letztes Sample: Fade endet bei 0
    assert out[-11] == 1000            # kurz vor der End-Rampe: noch voller Pegel


def test_apply_fade_null_laenge_laesst_unveraendert(fade_fn):
    chunk = array.array("h", [500, -500, 500, -500])
    out = fade_fn(chunk, 0)
    assert list(out) == list(chunk)


def test_apply_fade_laenger_als_chunk_wird_gekappt(fade_fn):
    # Fade-Länge > halbe Chunk-Länge -> darf nicht crashen/über die Mitte hinausgehen
    chunk = array.array("h", [1000] * 6)
    out = fade_fn(chunk, 100)
    assert len(out) == 6
    assert out[0] == 0
    assert out[-1] == 0


# --------------------------------------------------------------------------- #
# _rebuild_from_speech_regions
# --------------------------------------------------------------------------- #

@pytest.fixture
def rebuild_fn(load_functions, ragapp_dir):
    funcs = load_functions(
        ragapp_dir / "audio_overview.py",
        ["_rebuild_from_speech_regions", "_apply_fade"], {"array": array},
    )
    return funcs["_rebuild_from_speech_regions"]


def _tone(n, amp=1000):
    return array.array("h", [amp if i % 2 == 0 else -amp for i in range(n)])


def test_rebuild_ersetzt_luecken_durch_stille_und_behaelt_sprache(rebuild_fn):
    fr = 8000
    # "Rauschen"/Nicht-Sprache zwischen zwei Sprachabschnitten - simuliert durch
    # Ton AUSSERHALB der als Sprache markierten Regionen (0-800, 1600-2400).
    samples = _tone(2400, amp=1000)
    out, gaps = rebuild_fn(samples, fr, [(0, 800), (1600, 2400)],
                           max_pause_ms=1000, fade_ms=0)
    assert gaps == 1
    # die Luecke (800-1600, 800 Samples = 100ms) ist jetzt echte Stille:
    gap_region = out[800:1600]
    assert all(s == 0 for s in gap_region)
    assert len(out) == len(samples)


def test_rebuild_kappt_zu_lange_luecken(rebuild_fn):
    fr = 8000
    samples = _tone(800) + array.array("h", [0] * 8000) + _tone(800)   # 1s "Rauschen"-Luecke
    out, gaps = rebuild_fn(samples, fr, [(0, 800), (8800, 9600)],
                           max_pause_ms=200, fade_ms=0)
    assert gaps == 1
    # 200ms gekappt statt der vollen 1000ms Original-Luecke
    assert len(out) == pytest.approx(800 + 1600 + 800, abs=10)


def test_rebuild_keine_sprachregionen_laesst_original_unveraendert(rebuild_fn):
    samples = _tone(500)
    out, gaps = rebuild_fn(samples, 8000, [], max_pause_ms=500)
    assert gaps == 0
    assert out is samples   # bewusst: nichts tun statt zu raten


def test_rebuild_fade_wird_an_sprachraendern_angewendet(rebuild_fn):
    fr = 8000
    samples = _tone(800, amp=1000)
    out, gaps = rebuild_fn(samples, fr, [(0, 800)], max_pause_ms=500, fade_ms=10)
    assert out[0] == 0          # Fade-in am Anfang der Sprachregion
    assert out[-1] == 0         # Fade-out am Ende


def test_rebuild_mehrere_luecken_werden_alle_gesaeubert(rebuild_fn):
    fr = 8000
    rauschen = _tone(400, amp=1000)
    sprache = _tone(400, amp=1000)
    samples = sprache + rauschen + sprache + rauschen + sprache
    speech_regions = [(0, 400), (800, 1200), (1600, 2000)]
    out, gaps = rebuild_fn(samples, fr, speech_regions, max_pause_ms=1000, fade_ms=0)
    assert gaps == 2
    assert all(s == 0 for s in out[400:800])
    assert all(s == 0 for s in out[1200:1600])
