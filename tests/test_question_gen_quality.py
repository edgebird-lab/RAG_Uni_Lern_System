"""Qualitätsfilter in der Fragen-/Antworterzeugung (``question_gen``): verwerfen und mit
gezieltem Hinweis neu formulieren lassen. Kein echtes Modell: ein Fake-LLM liefert vorbereitete
Antworten und merkt sich die Prompts."""
from __future__ import annotations

import pytest

from ragapp.ingestion import question_gen as qg

CHUNK = ("Das Skalarprodukt zweier Vektoren ist die Summe der Produkte ihrer Komponenten. "
         "Der Betrag eines Vektors ist die Wurzel aus dem Skalarprodukt mit sich selbst. ") * 2

GOOD_1 = "Wie berechnet man das Skalarprodukt zweier Vektoren?"
GOOD_2 = "Wie ist der Betrag eines Vektors definiert?"
GOOD_3 = "Wann sind zwei Vektoren orthogonal?"
BAD_SRC = "Wie lautet die Definition von OD im Abschnitt?"
BAD_GLYPH = "Wie lautet die Komponentendarstellung von 2⃗a +⃗b ?"


class FakeLLM:
    def __init__(self, json_replies=(), text_replies=()):
        self._json = list(json_replies)
        self._text = list(text_replies)
        self.json_calls: list[tuple[str, float]] = []
        self.text_calls: list[tuple[str, float]] = []

    @staticmethod
    def _next(queue):
        r = queue.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def generate_json(self, prompt, system=None, temperature=None):
        self.json_calls.append((prompt, temperature))
        return self._next(self._json)

    def generate(self, prompt, system=None, temperature=None):
        self.text_calls.append((prompt, temperature))
        return self._next(self._text)


@pytest.fixture()
def use_llm(monkeypatch):
    def _install(llm, retries=2):
        monkeypatch.setattr(qg, "get_llm", lambda model=None: llm)
        monkeypatch.setattr(qg.settings, "CARD_QUALITY_RETRIES", retries)
        return llm
    return _install


# --------------------------------------------------------------------------- #
# Fragen
# --------------------------------------------------------------------------- #
def test_gute_fragen_brauchen_nur_einen_aufruf(use_llm):
    llm = use_llm(FakeLLM(json_replies=[{"questions": [GOOD_1, GOOD_2, GOOD_3]}]))
    stats: dict = {}
    assert qg.generate_questions(CHUNK, n=3, stats=stats) == [GOOD_1, GOOD_2, GOOD_3]
    assert len(llm.json_calls) == 1
    assert stats == {}
    assert "WICHTIG" not in llm.json_calls[0][0]       # erster Prompt unveraendert


def test_mangelhafte_fragen_werden_verworfen_und_gezielt_neu_erfragt(use_llm):
    llm = use_llm(FakeLLM(json_replies=[
        {"questions": [BAD_SRC, GOOD_1]},
        {"questions": [GOOD_2]},
    ]))
    stats: dict = {}
    out = qg.generate_questions(CHUNK, n=2, stats=stats)
    assert out == [GOOD_1, GOOD_2]
    assert len(llm.json_calls) == 2
    retry_prompt, retry_temp = llm.json_calls[1]
    assert "genau 1 verschiedene" in retry_prompt          # nur noch die fehlende Frage
    assert "Abbildungen" in retry_prompt and "WICHTIG" in retry_prompt
    assert retry_temp > llm.json_calls[0][1]               # etwas mehr Abwechslung
    assert stats == {"rejected": 1, "retries": 1}


def test_hinweis_nennt_den_festgestellten_mangel(use_llm):
    llm = use_llm(FakeLLM(json_replies=[{"questions": [BAD_GLYPH]}, {"questions": [GOOD_1]}]))
    qg.generate_questions(CHUNK, n=1)
    hint_prompt = llm.json_calls[1][0]
    assert "LaTeX" in hint_prompt and "Abbildungen" not in hint_prompt


def test_neuversuche_enden_nach_dem_limit_und_es_bleibt_leer_statt_schlecht(use_llm):
    llm = use_llm(FakeLLM(json_replies=[{"questions": [BAD_SRC]}] * 3))
    stats: dict = {}
    assert qg.generate_questions(CHUNK, n=1, stats=stats) == []
    assert len(llm.json_calls) == 3                        # 1 + 2 Neuversuche
    assert stats == {"rejected": 1, "retries": 2}          # dieselbe schlechte Frage zaehlt einmal


def test_ohne_neuversuche_wird_nur_verworfen(use_llm):
    llm = use_llm(FakeLLM(json_replies=[{"questions": [BAD_SRC, GOOD_1]}]), retries=0)
    assert qg.generate_questions(CHUNK, n=2) == [GOOD_1]
    assert len(llm.json_calls) == 1


def test_fehler_im_neuversuch_behaelt_die_guten_fragen(use_llm):
    use_llm(FakeLLM(json_replies=[{"questions": [BAD_SRC, GOOD_1]}, RuntimeError("Ollama weg")]))
    assert qg.generate_questions(CHUNK, n=2) == [GOOD_1]


def test_fehler_im_ersten_aufruf_ist_ein_questiongenerror(use_llm):
    use_llm(FakeLLM(json_replies=[RuntimeError("Modell laedt nicht")]))
    with pytest.raises(qg.QuestionGenError, match="Modell laedt nicht"):
        qg.generate_questions(CHUNK, n=2)


def test_liefert_das_modell_von_sich_aus_zu_wenig_gibt_es_keinen_neuversuch(use_llm):
    llm = use_llm(FakeLLM(json_replies=[{"questions": [GOOD_1]}]))
    assert qg.generate_questions(CHUNK, n=3) == [GOOD_1]
    assert len(llm.json_calls) == 1


def test_gleiche_frage_wird_nicht_doppelt_gezaehlt_und_der_rest_bleibt_erhalten(use_llm):
    use_llm(FakeLLM(json_replies=[{"questions": [GOOD_1, GOOD_1.upper(), GOOD_2]}]))
    assert qg.generate_questions(CHUNK, n=3) == [GOOD_1, GOOD_2]


def test_kurzer_chunk_ruft_das_modell_gar_nicht_erst(use_llm):
    llm = use_llm(FakeLLM())
    assert qg.generate_questions("zu kurz", n=3) == []
    assert llm.json_calls == []


def test_ohne_stats_parameter_funktioniert_alles_wie_vorher(use_llm):
    use_llm(FakeLLM(json_replies=[{"questions": [BAD_SRC]}, {"questions": [GOOD_1]}]))
    assert qg.generate_questions(CHUNK, n=1) == [GOOD_1]


# --------------------------------------------------------------------------- #
# Antworten
# --------------------------------------------------------------------------- #
CLEAN_ANSWER = "Man multipliziert die Komponenten paarweise und addiert die Produkte."
BAD_ANSWER = "Das ergibt sich nach Definition 4 aus den Komponenten."


def test_saubere_antwort_braucht_einen_aufruf(use_llm):
    llm = use_llm(FakeLLM(text_replies=[CLEAN_ANSWER]))
    assert qg.generate_answer(CHUNK, GOOD_1) == CLEAN_ANSWER
    assert len(llm.text_calls) == 1


def test_antwort_mit_verweis_wird_neu_erzeugt_und_die_bessere_behalten(use_llm):
    llm = use_llm(FakeLLM(text_replies=[BAD_ANSWER, CLEAN_ANSWER]))
    assert qg.generate_answer(CHUNK, GOOD_1) == CLEAN_ANSWER
    assert len(llm.text_calls) == 2
    assert "Definitionsnummern" in llm.text_calls[1][0]


def test_wird_der_neuversuch_nicht_besser_bleibt_die_erste_antwort(use_llm):
    worse = "Siehe Definition 4 und Abbildung 2, wie im Kapitel 1.2 gezeigt."
    llm = use_llm(FakeLLM(text_replies=[BAD_ANSWER, worse, worse]))
    assert qg.generate_answer(CHUNK, GOOD_1) == BAD_ANSWER


def test_fehler_im_antwort_neuversuch_behaelt_die_erste(use_llm):
    use_llm(FakeLLM(text_replies=[BAD_ANSWER, RuntimeError("weg")]))
    assert qg.generate_answer(CHUNK, GOOD_1) == BAD_ANSWER


def test_ohne_neuversuche_bleibt_die_erste_antwort(use_llm):
    llm = use_llm(FakeLLM(text_replies=[BAD_ANSWER]), retries=0)
    assert qg.generate_answer(CHUNK, GOOD_1) == BAD_ANSWER
    assert len(llm.text_calls) == 1


def test_nicht_im_text_bleibt_leer_ohne_neuversuch(use_llm):
    llm = use_llm(FakeLLM(text_replies=["NICHT_IM_TEXT"]))
    assert qg.generate_answer(CHUNK, GOOD_1) == ""
    assert len(llm.text_calls) == 1


def test_vorspann_wird_wie_bisher_entfernt(use_llm):
    use_llm(FakeLLM(text_replies=["Antwort: " + CLEAN_ANSWER]))
    assert qg.generate_answer(CHUNK, GOOD_1) == CLEAN_ANSWER


def test_fehler_im_ersten_antwortaufruf_ist_ein_questiongenerror(use_llm):
    use_llm(FakeLLM(text_replies=[RuntimeError("kaputt")]))
    with pytest.raises(qg.QuestionGenError):
        qg.generate_answer(CHUNK, GOOD_1)


def test_leere_eingaben_ergeben_leere_antwort(use_llm):
    llm = use_llm(FakeLLM())
    assert qg.generate_answer("", GOOD_1) == ""
    assert qg.generate_answer(CHUNK, "  ") == ""
    assert llm.text_calls == []
