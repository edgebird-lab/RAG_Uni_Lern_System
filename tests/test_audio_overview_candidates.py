"""Tests für ``ragapp.audio_overview.find_pronunciation_candidates`` - die
Heuristik fürs manuelle Skript-Prüfen in der UI (siehe
``ragapp/ui/pages/15_🎧_Audio-Overview.py``): schlägt Wörter vor, die
MÖGLICHERWEISE falsch ausgesprochen werden (kurze GROSSBUCHSTABEN-Kürzel,
CamelCase-Compounds, vokallose Kurzwörter) - explizit KEIN Wörterbuch-Abgleich
(deutsche Komposita sind unbegrenzt zusammensetzbar) und KEIN automatischer
Fix, nur ein Vorschlag zum Gegenhören."""
import re
import types

import pytest


@pytest.fixture
def find_fn(load_functions, ragapp_dir):
    return load_functions(
        ragapp_dir / "audio_overview.py",
        ["find_pronunciation_candidates"],
        {"re": re, "manifest": types.SimpleNamespace(list_pronunciation_fixes=lambda: {})},
        const_names=["_PRONUNCIATION_FIXES", "_CANDIDATE_PATTERN",
                     "_CANDIDATE_SHORT_WORD", "_VOWELS"],
    )["find_pronunciation_candidates"]


@pytest.fixture
def find_fn_with_dynamic(load_functions, ragapp_dir):
    """Wie ``find_fn``, aber mit einem gefakten ``manifest.list_pronunciation_fixes()``
    fuer Tests, ob dauerhaft gemerkte Korrekturen die Kandidatenliste kuerzen."""
    def _make(dynamic_fixes: dict):
        return load_functions(
            ragapp_dir / "audio_overview.py",
            ["find_pronunciation_candidates"],
            {"re": re,
             "manifest": types.SimpleNamespace(list_pronunciation_fixes=lambda: dynamic_fixes)},
            const_names=["_PRONUNCIATION_FIXES", "_CANDIDATE_PATTERN",
                         "_CANDIDATE_SHORT_WORD", "_VOWELS"],
        )["find_pronunciation_candidates"]
    return _make


def test_kurzes_grossbuchstaben_kuerzel_wird_erkannt(find_fn):
    assert find_fn("Die PID ist eindeutig.") == ["PID"]


def test_akronym_praefix_mit_kleinbuchstaben_endung(find_fn):
    assert find_fn("Schau dir GTFOBins an.") == ["GTFOBins"]


def test_eingebettetes_camel_case_wird_erkannt(find_fn):
    assert find_fn("Definiere ExecStart und WantedBy.") == ["ExecStart", "WantedBy"]


def test_vokalloses_kurzwort_wird_erkannt(find_fn):
    assert find_fn("Starte den Befehl ps im Hintergrund.") == ["ps"]


def test_normales_deutsches_wort_mit_vokal_bleibt_unerkannt(find_fn):
    # "du" hat einen Vokal - haeufigstes Wort im Text, darf NICHT anschlagen
    assert find_fn("Wenn du das machst, ist alles gut.") == []


def test_satzanfang_mit_einem_grossbuchstaben_bleibt_unerkannt(find_fn):
    assert find_fn("Schauen wir uns das jetzt an.") == []


def test_normales_kapitalisiertes_substantiv_bleibt_unerkannt(find_fn):
    assert find_fn("Der Server läuft stabil.") == []


def test_bereits_bestaetigte_fixes_werden_nicht_vorgeschlagen(find_fn):
    # "SSH" wird schon automatisch korrigiert (_PRONUNCIATION_FIXES) - soll
    # deshalb NICHT nochmal als Kandidat auftauchen
    assert find_fn("Verbinde dich per SSH.") == []


def test_duplikate_werden_nur_einmal_gelistet_in_reihenfolge(find_fn):
    assert find_fn("PID und PID und dann UID.") == ["PID", "UID"]


def test_mehrere_kategorien_gemischt(find_fn):
    # Reihenfolge: erst alle GROSSBUCHSTABEN-/CamelCase-Treffer in Textreihen-
    # folge, danach die vokallosen Kurzwoerter (zwei getrennte Durchlaeufe)
    result = find_fn("Der Befehl ps nutzt ExecStart und die PID.")
    assert result == ["ExecStart", "PID", "ps"]


def test_leerer_text_gibt_leere_liste(find_fn):
    assert find_fn("") == []


def test_dauerhaft_gemerkte_korrektur_wird_nicht_mehr_vorgeschlagen(find_fn_with_dynamic):
    # "PID" waere ohne gemerkte Korrektur ein Grossbuchstaben-Kuerzel und
    # wuerde auftauchen (siehe test_kurzes_grossbuchstaben_kuerzel_wird_erkannt)
    # - einmal vom Nutzer bestaetigt (manifest.pronunciation_fixes), soll es
    # nie wieder als "moeglicherweise falsch" gemeldet werden.
    fn = find_fn_with_dynamic({"PID": "pie-ai-di"})
    assert fn("Die PID ist eindeutig.") == []


def test_dauerhaft_gemerkte_korrektur_ist_case_insensitive(find_fn_with_dynamic):
    fn = find_fn_with_dynamic({"pid": "pie-ai-di"})
    assert fn("Die PID ist eindeutig.") == []


def test_andere_kandidaten_bleiben_trotz_gemerkter_korrektur_erkannt(find_fn_with_dynamic):
    fn = find_fn_with_dynamic({"PID": "pie-ai-di"})
    assert fn("Die PID und die UID sind beide gesetzt.") == ["UID"]
