"""Tests für die Chatterbox-Multilingual-Synthese (``ragapp.audio_overview``,
Ersatz für XTTS-v2 - siehe Moduldoc/config.py für die Begründung):
- ``_split_sentences``: Satzgrenzenerkennung (pysbd) vor der satzweisen
  Vertonung (ein Aufruf mit dem kompletten Skript auf einmal klang in echten
  Tests unnatürlich gehetzt).
- ``_concat_with_pauses``: reine Tensor-Logik - fügt zwischen den pro Satz
  erzeugten Audio-Stücken echte Stille fester Länge ein (WIR bestimmen die
  Pausenlänge selbst, statt uns wie bei XTTS auf modellinterne Pausen-
  behandlung zu verlassen).
- ``synthesize_speech``: ruft das Modell PRO SATZ auf, reicht die Chatterbox-
  Parameter durch, prüft VRAM/Text VOR dem teuren Modell-Laden.

Isoliert geladen - ``_get_tts``/``_prepare_vram_for_tts``/``_split_sentences``
werden in den synthesize_speech-Tests gefaked (kein echtes Modell laden).
torch/torchaudio/pysbd sind echte, leichte Importe (kein transformers/
Chatterbox-Modell-Download nötig)."""
import types

import pytest
import torch


def _fake_settings(**overrides):
    base = dict(
        AUDIO_LANGUAGE="de", AUDIO_TTS_PAUSE_MS=250, AUDIO_TTS_EXAGGERATION=0.5,
        AUDIO_TTS_CFG_WEIGHT=0.5, AUDIO_TTS_TEMPERATURE=0.8,
        AUDIO_TTS_REPETITION_PENALTY=2.0, AUDIO_TTS_MIN_P=0.05, AUDIO_TTS_TOP_P=1.0,
    )
    base.update(overrides)
    return types.SimpleNamespace(**base)


# --------------------------------------------------------------------------- #
# _split_sentences
# --------------------------------------------------------------------------- #

@pytest.fixture
def split_fn(load_functions, ragapp_dir):
    return load_functions(
        ragapp_dir / "audio_overview.py", ["_split_sentences", "_get_segmenter"], {},
        const_names=["_segmenter_singleton"],
    )["_split_sentences"]


def test_split_sentences_trennt_an_satzgrenzen(split_fn):
    assert split_fn("Das ist Satz eins. Das ist Satz zwei!") == \
        ["Das ist Satz eins.", "Das ist Satz zwei!"]


def test_split_sentences_erkennt_abkuerzungen_nicht_als_satzende(split_fn):
    assert split_fn("Dr. Müller sagt: Ja.") == ["Dr. Müller sagt: Ja."]


def test_split_sentences_leerer_text_gibt_leere_liste(split_fn):
    assert split_fn("   ") == []


def test_split_sentences_filtert_leere_stuecke(split_fn):
    assert split_fn("Satz eins.\n\n\nSatz zwei.") == ["Satz eins.", "Satz zwei."]


# --------------------------------------------------------------------------- #
# _concat_with_pauses
# --------------------------------------------------------------------------- #

@pytest.fixture
def concat_fn(load_functions, ragapp_dir):
    return load_functions(
        ragapp_dir / "audio_overview.py", ["_concat_with_pauses"],
        {"torch": torch, "AudioOverviewError": RuntimeError},
    )["_concat_with_pauses"]


def test_concat_with_pauses_fuegt_stille_zwischen_stuecken_ein(concat_fn):
    out = concat_fn([torch.ones(1, 100), torch.ones(1, 50)], pause_samples=10)
    assert out.shape == (1, 160)
    assert torch.all(out[0, 100:110] == 0)
    assert torch.all(out[0, :100] == 1)
    assert torch.all(out[0, 110:] == 1)


def test_concat_with_pauses_einzelnes_stueck_ohne_pause(concat_fn):
    out = concat_fn([torch.ones(1, 100)], pause_samples=10)
    assert out.shape == (1, 100)


def test_concat_with_pauses_pause_null_haengt_direkt_an(concat_fn):
    out = concat_fn([torch.ones(1, 10), torch.ones(1, 10)], pause_samples=0)
    assert out.shape == (1, 20)


def test_concat_with_pauses_ohne_stuecke_wirft_error(concat_fn):
    with pytest.raises(RuntimeError):
        concat_fn([], pause_samples=10)


def test_concat_with_pauses_mehrere_stuecke_drei_pausen_zwei(concat_fn):
    out = concat_fn([torch.ones(1, 5), torch.ones(1, 5), torch.ones(1, 5)], pause_samples=2)
    assert out.shape == (1, 5 * 3 + 2 * 2)


# --------------------------------------------------------------------------- #
# synthesize_speech
# --------------------------------------------------------------------------- #

@pytest.fixture
def synth_env(load_functions, ragapp_dir, tmp_path):
    def _make(*, settings_obj=None, vram_ok=True, sentences=None):
        settings_obj = settings_obj or _fake_settings()
        sentences = sentences if sentences is not None else ["Satz eins.", "Satz zwei."]
        generate_calls = []

        class _FakeModel:
            sr = 24000

            def generate(self, text, **kwargs):
                generate_calls.append({"text": text, **kwargs})
                return torch.zeros(1, 100)

        funcs = load_functions(
            ragapp_dir / "audio_overview.py",
            ["synthesize_speech", "_concat_with_pauses"],
            {
                "settings": settings_obj,
                "_prepare_vram_for_tts": lambda: (vram_ok, "" if vram_ok else "kein VRAM"),
                "_get_tts": lambda: _FakeModel(),
                "_split_sentences": lambda text: sentences,
                "AudioOverviewError": RuntimeError,
                "Optional": None,
                "Path": __import__("pathlib").Path,
            },
        )
        return types.SimpleNamespace(
            **funcs, generate_calls=generate_calls, tmp_path=tmp_path)
    return _make


def test_synthesize_speech_ruft_modell_pro_satz_auf_und_schreibt_datei(synth_env):
    env = synth_env()
    out_path = env.tmp_path / "out.wav"
    env.synthesize_speech("Satz eins. Satz zwei.", "ref.wav", str(out_path))

    assert len(env.generate_calls) == 2
    call = env.generate_calls[0]
    assert call["text"] == "Satz eins."
    assert call["audio_prompt_path"] == "ref.wav"
    assert call["language_id"] == "de"
    assert call["exaggeration"] == 0.5
    assert call["cfg_weight"] == 0.5
    assert call["temperature"] == 0.8
    assert call["repetition_penalty"] == 2.0
    assert call["min_p"] == 0.05
    assert call["top_p"] == 1.0
    assert out_path.is_file()


def test_synthesize_speech_nutzt_geaenderte_settings(synth_env):
    settings_obj = _fake_settings(AUDIO_TTS_EXAGGERATION=0.9, AUDIO_LANGUAGE="en")
    env = synth_env(settings_obj=settings_obj)
    out_path = env.tmp_path / "out.wav"
    env.synthesize_speech("Satz eins. Satz zwei.", "ref.wav", str(out_path))
    assert env.generate_calls[0]["exaggeration"] == 0.9
    assert env.generate_calls[0]["language_id"] == "en"


def test_synthesize_speech_eigene_sprache_ueberschreibt_settings(synth_env):
    env = synth_env()
    out_path = env.tmp_path / "out.wav"
    env.synthesize_speech("Satz eins. Satz zwei.", "ref.wav", str(out_path), language="fr")
    assert env.generate_calls[0]["language_id"] == "fr"


def test_synthesize_speech_kein_vram_wirft_error_ohne_zu_vertonen(synth_env):
    env = synth_env(vram_ok=False)
    with pytest.raises(RuntimeError):
        env.synthesize_speech("Satz eins.", "ref.wav", str(env.tmp_path / "out.wav"))
    assert env.generate_calls == []


def test_synthesize_speech_ruft_on_progress_je_satz_auf(synth_env):
    env = synth_env(sentences=["Satz eins.", "Satz zwei.", "Satz drei."])
    calls = []
    env.synthesize_speech("Satz eins. Satz zwei. Satz drei.", "ref.wav",
                          str(env.tmp_path / "out.wav"),
                          on_progress=lambda done, total, label: calls.append((done, total, label)))
    assert calls == [(1, 3, "Satz eins."), (2, 3, "Satz zwei."), (3, 3, "Satz drei.")]


def test_synthesize_speech_ohne_on_progress_funktioniert_weiterhin(synth_env):
    env = synth_env()
    out_path = env.tmp_path / "out.wav"
    env.synthesize_speech("Satz eins. Satz zwei.", "ref.wav", str(out_path))
    assert out_path.is_file()


def test_synthesize_speech_keine_saetze_wirft_error_vor_vram_check(synth_env):
    env = synth_env(sentences=[], vram_ok=False)
    with pytest.raises(RuntimeError, match="vertonbar"):
        env.synthesize_speech("   ", "ref.wav", str(env.tmp_path / "out.wav"))
    assert env.generate_calls == []


def test_synthesize_speech_modellfehler_wird_zu_audiooverviewerror(synth_env):
    env = synth_env()

    def _boom(text, **kwargs):
        raise ValueError("boom")

    env.synthesize_speech.__globals__["_get_tts"] = lambda: types.SimpleNamespace(
        sr=24000, generate=_boom)
    with pytest.raises(RuntimeError):
        env.synthesize_speech("Satz eins.", "ref.wav", str(env.tmp_path / "out.wav"))
