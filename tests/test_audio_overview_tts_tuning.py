"""Tests für das Sprachqualitäts-/Tempo-Tuning der XTTS-v2-Synthese
(``ragapp.audio_overview``):
- ``_pause_ms_to_samples``: reine Umrechnung ms -> Samples für den Pausen-Fix
  (coqui-tts fügt sonst nach JEDEM Satz eine feste ~417ms-Stille an, siehe
  Moduldoc/Kommentare in audio_overview.py).
- ``synthesize_speech``: reicht die Tuning-Parameter (speed/temperature/
  repetition_penalty/gpt_cond_*) tatsächlich an ``tts.tts_to_file`` durch,
  statt sie nur in ``settings`` liegen zu lassen.
- ``_cap_long_silences``: Nachbearbeitungs-Sicherheitsnetz gegen ein reales,
  in einem End-to-End-Testlauf gemessenes XTTS-v2-Artefakt (gelegentliche
  mehrsekündige "tote" Passagen mitten im Skript) - kappt lange Stille-Läufe,
  lässt normale kurze Satzpausen unangetastet.

Isoliert geladen - ``_apply_pause_length``/``_get_tts`` werden hier gefaked,
damit KEIN echter TTS/transformers-Import ausgelöst wird (das würde ohne den
isin_mps_friendly-Shim aus ``_get_tts`` fehlschlagen und wäre für einen
reinen Kwargs-Durchreich-Test ohnehin unnötig langsam). ``_cap_long_silences``
braucht dagegen nur ``wave``/``array`` (Stdlib) - kein TTS-Import nötig."""
import array
import types
import wave

import pytest


def _fake_settings(**overrides):
    base = dict(
        AUDIO_LANGUAGE="de", AUDIO_TTS_SPEED=1.1, AUDIO_TTS_TEMPERATURE=0.7,
        AUDIO_TTS_REPETITION_PENALTY=4.0, AUDIO_TTS_PAUSE_MS=250,
        AUDIO_TTS_GPT_COND_LEN=24, AUDIO_TTS_GPT_COND_CHUNK_LEN=6, AUDIO_TTS_MAX_REF_LEN=30,
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
                "_cap_long_silences": lambda *a, **kw: 0,  # eigene Tests unten
                "AudioOverviewError": RuntimeError,
                "Optional": None,
                "Path": __import__("pathlib").Path,
            },
        )
        return types.SimpleNamespace(
            **funcs, pause_calls=pause_calls, tts_to_file_calls=tts_to_file_calls)
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


def test_synthesize_speech_nutzt_geaenderte_settings(synth_env):
    settings_obj = _fake_settings(AUDIO_TTS_SPEED=1.25, AUDIO_TTS_PAUSE_MS=100,
                                  AUDIO_TTS_TEMPERATURE=0.5)
    env = synth_env(settings_obj=settings_obj)
    env.synthesize_speech("Text.", "ref.wav", "out.wav")

    assert env.pause_calls == [100]
    assert env.tts_to_file_calls[0]["speed"] == 1.25
    assert env.tts_to_file_calls[0]["temperature"] == 0.5


def test_synthesize_speech_kein_vram_wirft_error_ohne_zu_vertonen(synth_env):
    env = synth_env(vram_ok=False)
    with pytest.raises(RuntimeError):
        env.synthesize_speech("Text.", "ref.wav", "out.wav")
    assert env.tts_to_file_calls == []
    assert env.pause_calls == []


# --------------------------------------------------------------------------- #
# _cap_long_silences
# --------------------------------------------------------------------------- #

@pytest.fixture
def cap_fn(load_functions, ragapp_dir):
    return load_functions(
        ragapp_dir / "audio_overview.py", ["_cap_long_silences"],
        {"wave": wave, "array": array},
    )["_cap_long_silences"]


def _make_wav(path, segments, fr=8000):
    """``segments``: Liste (kind, ms) mit kind 'ton' oder 'stille'. Baut eine
    mono 16-bit-WAV, wie sie XTTS-v2 auch ausgibt (nur andere Samplerate,
    fürs schnelle Testen)."""
    samples = array.array("h")
    for kind, ms in segments:
        n = int(fr * ms / 1000)
        if kind == "stille":
            samples.extend([0] * n)
        else:
            samples.extend([8000 if i % 2 == 0 else -8000 for i in range(n)])
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(fr)
        w.writeframes(samples.tobytes())


def _wav_duration_ms(path) -> float:
    with wave.open(str(path), "rb") as w:
        return 1000.0 * w.getnframes() / w.getframerate()


def test_cap_long_silences_kappt_lange_luecke(cap_fn, tmp_path):
    p = tmp_path / "long_gap.wav"
    _make_wav(p, [("ton", 300), ("stille", 2000), ("ton", 300)])
    cuts = cap_fn(p, max_gap_ms=900, cap_ms=300)
    assert cuts == 1
    # 300 Ton + 300 gekappte Stille + 300 Ton = 900ms (statt urspruenglich 2600ms)
    assert _wav_duration_ms(p) == pytest.approx(900, abs=40)


def test_cap_long_silences_laesst_kurze_pausen_unangetastet(cap_fn, tmp_path):
    p = tmp_path / "short_gap.wav"
    _make_wav(p, [("ton", 300), ("stille", 400), ("ton", 300)])
    original_ms = _wav_duration_ms(p)
    cuts = cap_fn(p, max_gap_ms=900, cap_ms=300)
    assert cuts == 0
    assert _wav_duration_ms(p) == pytest.approx(original_ms, abs=5)


def test_cap_long_silences_mehrere_luecken_werden_alle_gekappt(cap_fn, tmp_path):
    p = tmp_path / "multi_gap.wav"
    _make_wav(p, [("ton", 200), ("stille", 1500), ("ton", 200),
                 ("stille", 1500), ("ton", 200)])
    cuts = cap_fn(p, max_gap_ms=900, cap_ms=250)
    assert cuts == 2
    assert _wav_duration_ms(p) == pytest.approx(200 * 3 + 250 * 2, abs=60)


def test_cap_long_silences_stereo_wird_uebersprungen(cap_fn, tmp_path):
    p = tmp_path / "stereo.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(array.array("h", [0] * 8000 * 2 * 3).tobytes())  # 3s Stille, stereo
    original_ms = _wav_duration_ms(p)
    cuts = cap_fn(p, max_gap_ms=900, cap_ms=250)
    assert cuts == 0
    assert _wav_duration_ms(p) == pytest.approx(original_ms, abs=1)
