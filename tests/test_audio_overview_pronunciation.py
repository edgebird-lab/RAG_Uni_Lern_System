"""Tests für die Aussprachekorrektur vor der Vertonung (``ragapp.audio_overview``:
``_apply_pronunciation_fixes``/``_PRONUNCIATION_FIXES``/``_keep_case``):

Chatterbox liest Text nach den Standard-Ausspracheregeln der Zielsprache -
bestimmte Abkürzungen/Lehnwörter (z. B. "SSH", "booten") kommen dabei falsch
ausgesprochen raus (siehe Kommentar im Modul). Die Korrektur läuft NUR auf dem
Text, der tatsächlich an die Vertonung geht, NICHT auf dem im UI angezeigten/
bearbeitbaren Skript (siehe ``synthesize_speech``)."""
import re
import types

import pytest
import torch


@pytest.fixture
def fix_fn(load_functions, ragapp_dir):
    return load_functions(
        ragapp_dir / "audio_overview.py",
        ["_apply_pronunciation_fixes", "_keep_case", "_speakify_path", "_speakify_domain",
         "_speakify_suffix"],
        {"re": re},
        const_names=["_PRONUNCIATION_FIXES", "_PATH_PATTERN", "_DOMAIN_PATTERN",
                     "_BARE_SUFFIX_PATTERN"],
    )["_apply_pronunciation_fixes"]


def test_ssh_wird_buchstabiert(fix_fn):
    assert fix_fn("Verbinde dich per SSH mit dem Server.") == \
        "Verbinde dich per Es-Es-Ha mit dem Server."


def test_ssh_als_teilwort_bleibt_unveraendert(fix_fn):
    # kein eigenständiges Akronym -> \b-Grenzen dürfen nicht mitten im Wort greifen
    assert fix_fn("EinSSHalter bleibt gleich.") == "EinSSHalter bleibt gleich."


def test_ssh_kleingeschrieben_als_kommandozeilen_argument_wird_auch_erkannt(fix_fn):
    # z. B. "systemctl status ssh" - Servicename klein, trotzdem dieselbe
    # Ausspracheproblematik wie beim grossgeschriebenen Akronym
    assert fix_fn("systemctl status ssh prüfen.") == "systemctl status Es-Es-Ha prüfen."


def test_booten_wird_zu_buhten(fix_fn):
    assert fix_fn("Wir müssen den Rechner booten.") == \
        "Wir müssen den Rechner buhten."


def test_booten_grossschreibung_am_satzanfang_bleibt_erhalten(fix_fn):
    assert fix_fn("Booten dauert nur Sekunden.") == "Buhten dauert nur Sekunden."


def test_konjugierte_formen_werden_erkannt(fix_fn):
    assert fix_fn(
        "Er bootet den PC, bootete ihn gestern schon und hat ihn oft "
        "gebootet - er ist gut bootbar."
    ) == (
        "Er buhtet den PC, buhtete ihn gestern schon und hat ihn oft "
        "gebuhtet - er ist gut buhtbar."
    )


def test_boot_als_eigenstaendiges_wort_bleibt_unangetastet(fix_fn):
    # "Boot"/"Boote" (das Wasserfahrzeug) wird schon richtig ausgesprochen -
    # keine Teilstring-Ersetzung, die das fälschlich mittreffen würde
    assert fix_fn("Das Boot fährt auf die Boote zu.") == \
        "Das Boot fährt auf die Boote zu."


def test_text_ohne_treffer_bleibt_unveraendert(fix_fn):
    text = "Ein ganz normaler Satz ohne Problemwörter."
    assert fix_fn(text) == text


# --------------------------------------------------------------------------- #
# Pfade und Domains (strukturelle Fixes, siehe _PATH_PATTERN/_DOMAIN_PATTERN)
# --------------------------------------------------------------------------- #

def test_absoluter_pfad_wird_zu_gesprochenem_slash_und_dot(fix_fn):
    # Nutzer-Vorgabe: "/" und "." werden MITGESPROCHEN ("Slash"/"dot"),
    # nicht stillschweigend durch Leerzeichen ersetzt
    assert fix_fn("Die Logs landen unter /var/log/auth.log.") == \
        "Die Logs landen unter Slash var Slash log Slash auth dot log."


def test_pfad_mit_tilde_verliert_die_tilde(fix_fn):
    assert fix_fn("Schreib es nach ~/cron-test.log.") == \
        "Schreib es nach Slash cron test dot log."


def test_verzeichnis_mit_trailing_slash(fix_fn):
    # der Satzpunkt direkt nach dem abschliessenden "/" darf NICHT mit in den
    # Pfad gezogen werden (sonst fehlt pysbd hinterher die Satzgrenze); der
    # abschliessende Slash selbst traegt keine Information und wird verworfen
    assert fix_fn("Das landet unter /var/log/.") == "Das landet unter Slash var Slash log."


def test_alleinstehender_dateiname_mit_bekannter_endung(fix_fn):
    assert fix_fn("Schau dir die Datei auth.log an.") == \
        "Schau dir die Datei auth dot log an."


def test_unbekannte_endung_bleibt_unangetastet(fix_fn):
    # kein Pfad, keine bekannte Endung -> keine Ersetzung (keine Dezimalzahl
    # o. Ae. faelschlich zerlegen)
    assert fix_fn("Das kostet 3.5 Sekunden.") == "Das kostet 3.5 Sekunden."


def test_domain_bekommt_gesprochenes_dot(fix_fn):
    assert fix_fn("Mehr auf linuxjourney.com.") == "Mehr auf linuxjourney dot com."


def test_verschachtelte_subdomain_bekommt_jeden_dot(fix_fn):
    assert fix_fn("Siehe gtfobins.github.io für Details.") == \
        "Siehe gtfobins dot github dot io für Details."


def test_alleinstehende_endung_ohne_dateiname_bekommt_gesprochenes_dot(fix_fn):
    # z. B. beim Erklaeren von systemd-Unit-Typen: "die .service Endung" -
    # hier ist die Endung selbst der Lehrinhalt, "dot" wird MIT gesprochen
    assert fix_fn("Die .service Endung nutzt man für Dienste.") == \
        "Die dot service Endung nutzt man für Dienste."


def test_alleinstehende_endung_direkt_vor_satzpunkt(fix_fn):
    assert fix_fn("Und schließlich gibt es noch .socket.") == \
        "Und schließlich gibt es noch dot socket."


def test_endung_mit_vorangehendem_dateinamen_bleibt_pfad_fall(fix_fn):
    # Gegenprobe: "auth.log" hat einen Buchstaben direkt vor dem Punkt ->
    # muss weiterhin ueber den Pfad-Fall laufen, nicht ueber den
    # alleinstehenden-Endung-Fall (Ergebnis ist hier gleich: "dot")
    assert fix_fn("Schau in die auth.log Datei.") == "Schau in die auth dot log Datei."


# --------------------------------------------------------------------------- #
# Integration: synthesize_speech wendet die Korrektur VOR der Vertonung an,
# ohne script_text selbst zu verändern
# --------------------------------------------------------------------------- #

@pytest.fixture
def synth_with_fixes(load_functions, ragapp_dir, tmp_path):
    generate_calls = []

    class _FakeModel:
        sr = 24000

        def prepare_conditionals(self, wav_fpath, exaggeration=0.5):
            pass

        def generate(self, text, **kwargs):
            generate_calls.append(text)
            return torch.zeros(1, 10)

    settings_obj = types.SimpleNamespace(
        AUDIO_LANGUAGE="de", AUDIO_TTS_PAUSE_MS=0, AUDIO_TTS_EXAGGERATION=0.5,
        AUDIO_TTS_CFG_WEIGHT=0.5, AUDIO_TTS_TEMPERATURE=0.8,
        AUDIO_TTS_REPETITION_PENALTY=2.0, AUDIO_TTS_MIN_P=0.05, AUDIO_TTS_TOP_P=1.0,
    )
    funcs = load_functions(
        ragapp_dir / "audio_overview.py",
        ["synthesize_speech", "_apply_pronunciation_fixes", "_keep_case",
         "_speakify_path", "_speakify_domain", "_speakify_suffix",
         "_split_sentences", "_get_segmenter", "_concat_with_pauses"],
        {
            "settings": settings_obj,
            "_prepare_vram_for_tts": lambda: (True, ""),
            "_get_tts": lambda: _FakeModel(),
            "AudioOverviewError": RuntimeError,
            "Optional": None,
            "Path": __import__("pathlib").Path,
            "re": re,
        },
        const_names=["_PRONUNCIATION_FIXES", "_PATH_PATTERN", "_DOMAIN_PATTERN",
                     "_BARE_SUFFIX_PATTERN", "_segmenter_singleton"],
    )
    return types.SimpleNamespace(**funcs, generate_calls=generate_calls, tmp_path=tmp_path)


def test_synthesize_speech_wendet_ausspracheregeln_vor_der_vertonung_an(synth_with_fixes):
    env = synth_with_fixes
    env.synthesize_speech("Wir booten den Server per SSH.", "ref.wav",
                          str(env.tmp_path / "out.wav"))
    assert env.generate_calls == ["Wir buhten den Server per Es-Es-Ha."]


def test_synthesize_speech_veraendert_script_text_argument_nicht(synth_with_fixes):
    # script_text bleibt unangetastet (nur an Vertonung geht die Korrektur) -
    # relevant, weil das UI dasselbe Skript vor der Vertonung zur Bearbeitung
    # anzeigt und dort NICHT "buhten"/"Es-Es-Ha" auftauchen soll
    env = synth_with_fixes
    original = "Wir booten den Server per SSH."
    env.synthesize_speech(original, "ref.wav", str(env.tmp_path / "out.wav"))
    assert original == "Wir booten den Server per SSH."
