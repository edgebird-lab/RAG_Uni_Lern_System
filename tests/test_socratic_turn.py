"""Ein Zug im sokratischen Dialog (``ragapp.graph.socratic_turn``): Gesprächsstand,
Prompt-Aufbau, Antwort-Prüfung und Wiederholungsschutz.

Regressionstest für einen real gemeldeten Fehler (Chat „Vektorrechnung und Pfeile“,
gemma3:4b): Ab dem dritten Zug lieferte das Modell immer wieder dieselbe Antwort -
egal ob „Hinweis“, „Löse es auf“ oder „Nächster Aspekt“ gedrückt wurde. Hier wird das
Modell durch ein Fake ersetzt, das genau dieses Verhalten zeigt; der Code muss den
Text trotzdem verwerfen und eine ehrliche Rückfallantwort liefern.
"""
import pytest

from ragapp.graph import socratic_turn as st

# Die real geloggte Wiederholungs-Antwort.
LOOP_TEXT = (
    "Sie haben die geometrische Bedeutung eines Vektors als Pfeil mit den Komponenten "
    "v1 und v2 beschrieben, wobei v1 den horizontalen Abstand und v2 den vertikalen "
    "Abstand vom Ursprung darstellt [Quelle 1]. Das ist ein guter erster Schritt, um die "
    "Idee zu verstehen. Können Sie mir noch erklären, was die Länge dieses Pfeils in "
    "Bezug auf die geometrische Darstellung des Vektors bedeutet?")

START = ("Lass uns über Vektorrechnung und Pfeile sprechen. Stelle eine klausurtypische "
         "Einstiegsfrage zu einem prüfbaren Begriff aus dem Kontext.")
HINT = "Gib mir einen Hinweis, ohne die Antwort zu verraten."
CONTROL = (HINT, "Ich weiß es teilweise.", "Löse es auf.", "Nächster Aspekt desselben Themas.")
TOPIC = "Vektorrechnung und Pfeile"


def _is_control(text: str) -> bool:
    return text in CONTROL or text.startswith("Lass uns über")


def _u(text):
    return {"role": "user", "content": text}


def _a(text):
    return {"role": "assistant", "content": text}


class FakeLLM:
    """Liefert die vorgegebenen Antworten der Reihe nach; die letzte wiederholt sich."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls: list[dict] = []

    def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply


def _state(history=None, topic=TOPIC):
    return st.build_state(history or [], topic, is_control=_is_control)


# Typische Verläufe
OPEN_Q = [_u(START), _a("Was ist ein Vektor?")]
OPEN_Q2 = OPEN_Q + [_u("Ein Pfeil"), _a("Und was gehört noch dazu?")]
RESOLVED = OPEN_Q + [_u("Löse es auf."),
                     _a("Ein Vektor hat Länge, Richtung und Richtungssinn [Quelle 1].")]


# --------------------------------------------------------------------------- #
# Offene Frage / Phase
# --------------------------------------------------------------------------- #
def test_last_question_findet_frage_am_ende_auch_vor_quellenmarker():
    assert st.last_question("Das stimmt. Wie lautet die Formel? [Quelle 2]") == "Wie lautet die Formel?"
    assert st.last_question("Nur eine Erklärung ohne Frage.") == ""
    assert st.last_question("") == ""
    assert st.last_question(None) == ""


def test_last_question_erkennt_frage_mit_kurzem_nachsatz():
    # Der real gemeldete Fall: die Frage steht NICHT ganz am Ende.
    text = ("Können Sie mir noch sagen, wie sich die drei Eigenschaften zeigen? "
            "Konzentrieren wir uns dabei auf den Pfeil.")
    assert st.is_open_question(text)
    assert st.last_question(text).endswith("zeigen?")


def test_rhetorische_frage_in_einer_erklaerung_ist_keine_offene_frage():
    text = ("Was bedeutet das? Es bedeutet, dass der Vektor eine Länge hat. "
            "Außerdem hat er eine Richtung und einen Richtungssinn, die zusammen "
            "mit der Länge den Vektor festlegen.")
    assert not st.is_open_question(text)


def test_abkuerzungen_zerreissen_eine_frage_nicht():
    q = "Was bedeutet z. B. Orthogonalität bei zwei Vektoren?"
    assert st.last_question("Gut. " + q) == q


def test_dialog_phase_start_offen_aufgeloest():
    assert st.dialog_phase([]) == "start"
    assert st.dialog_phase([_u(START)]) == "start"
    assert st.dialog_phase(OPEN_Q) == "open"
    assert st.dialog_phase(RESOLVED) == "resolved"


# --------------------------------------------------------------------------- #
# Gesprächsstand
# --------------------------------------------------------------------------- #
def test_build_state_sammelt_ziel_fragen_und_eigene_antworten():
    history = [_u(START), _a("Was ist ein Vektor?"), _u("Ein Pfeil mit Länge und Richtung"),
               _a("Gut, und was gehört noch dazu? [Quelle 1]"), _u(HINT)]
    s = _state(history)
    assert s.phase == "open"
    assert s.goal == "Gut, und was gehört noch dazu?"
    assert s.asked == ["Was ist ein Vektor?", "Gut, und was gehört noch dazu?"]
    # Startphrase und Steuerimpuls zählen nicht als inhaltliche Antwort.
    assert s.answers == ["Ein Pfeil mit Länge und Richtung"]


def test_build_state_antworten_zaehlen_erst_ab_der_letzten_aufloesung():
    history = RESOLVED + [_u("neue Antwort"), _a("Und was ist ein Skalar?")]
    s = _state(history)
    assert s.answers == ["neue Antwort"]
    assert s.goal == "Und was ist ein Skalar?"


def test_build_state_aufgeloest_hat_kein_ziel():
    s = _state(RESOLVED)
    assert (s.phase, s.goal) == ("resolved", "")
    assert s.asked == ["Was ist ein Vektor?"]


def test_build_state_behaelt_nur_die_letzten_drei_ki_texte_und_zwei_antworten():
    history = [_u(START)]
    for i in range(5):
        history += [_a(f"Frage Nummer {i}?"), _u(f"Antwort {i}")]
    s = _state(history + [_a("Letzte Frage?")])
    assert len(s.ai_texts) == 3 and s.ai_texts[-1] == "Letzte Frage?"
    assert s.answers == ["Antwort 3", "Antwort 4"]


# --------------------------------------------------------------------------- #
# Prompt-Aufbau
# --------------------------------------------------------------------------- #
def test_build_messages_hat_nur_system_und_eine_nutzernachricht_ohne_verlauf():
    history = [_u(START), _a(LOOP_TEXT), _u("Löse es auf."), _a(LOOP_TEXT)]
    msgs = st.build_messages(_state(history), "next", None, "Nächster Aspekt desselben Themas.",
                             "KONTEXTTEXT")
    assert [m["role"] for m in msgs] == ["system", "user"]
    user = msgs[1]["content"]
    assert "KONTEXTTEXT" in user and f"THEMA: {TOPIC}" in user
    # Die wiederholte KI-Antwort darf NICHT als Ganzes im Prompt stehen (sonst kopiert
    # das Modell sie wieder) - nur die gestellte Frage taucht als Vermeiden-Liste auf.
    assert LOOP_TEXT not in user
    assert "NICHT wiederholen" in user
    # Steuerphrasen werden beschrieben, nicht zitiert (sonst echoed das Modell sie).
    assert "Nächster Aspekt desselben Themas." not in user


@pytest.mark.parametrize("kind, marker", [
    ("start", "Einstiegsfrage"), ("hint", "Denkanstoß"), ("partial", "nur einen Teil"),
    ("resolve", "JETZT vollständig auf"), ("next", "ANDEREN Teilaspekt"),
    ("answer", "weiterführende Frage")])
def test_build_messages_gibt_je_absicht_genau_eine_passende_aufgabe(kind, marker):
    user = st.build_messages(_state(OPEN_Q), kind, None, "Ein Pfeil.", "K")[1]["content"]
    assert marker in user
    assert user.count("AUFGABE:") == 1


def test_build_messages_zitiert_bei_antwort_den_echten_text_bei_steuerimpuls_nicht():
    antwort = st.build_messages(_state(OPEN_Q), "answer", None,
                                "Ein Pfeil mit Länge und Richtung", "K")[1]["content"]
    assert "„Ein Pfeil mit Länge und Richtung“" in antwort
    hinweis = st.build_messages(_state(OPEN_Q), "hint", None, HINT, "K")[1]["content"]
    assert HINT not in hinweis and "bittet um einen Hinweis" in hinweis


def test_build_messages_aufloesung_erwaehnt_antworten_nur_wenn_es_welche_gibt():
    ohne = st.build_messages(_state(OPEN_Q), "resolve", None, "Löse es auf.", "K")[1]["content"]
    assert "nicht darauf ein" in ohne and "richtig oder falsch" not in ohne
    mit = st.build_messages(_state(OPEN_Q2), "resolve", None, "Löse es auf.", "K")[1]["content"]
    assert "richtig oder falsch" in mit and "nicht darauf ein" not in mit


def test_build_messages_haengt_sonderfall_und_korrektur_an():
    msgs = st.build_messages(_state(OPEN_Q), "next", "complaint", "du wiederholst dich", "K",
                             correction="KORREKTUR: anders")
    user = msgs[1]["content"]
    assert "bemängelt" in user and user.rstrip().endswith("KORREKTUR: anders")


def test_die_offene_frage_steht_bei_hinweis_nicht_in_der_vermeiden_liste():
    user = st.build_messages(_state(OPEN_Q2), "hint", None, HINT, "K")[1]["content"]
    avoid = user.split("NICHT wiederholen")[1]
    assert "Was ist ein Vektor?" in avoid
    assert "Und was gehört noch dazu?" not in avoid


# --------------------------------------------------------------------------- #
# Säubern + Prüfen
# --------------------------------------------------------------------------- #
def test_clean_answer_entfernt_labels_und_rahmen():
    assert st.clean_answer("Rückmeldung: Gut so.\nNächste Frage: Was ist ein Skalar?", "answer") \
        == "Gut so.\nWas ist ein Skalar?"
    assert st.clean_answer("**Frage:** Was ist ein Skalar?", "start") == "Was ist ein Skalar?"
    assert st.clean_answer("„Was ist ein Skalar?“", "start") == "Was ist ein Skalar?"


def test_clean_answer_streicht_quellenverweise_in_fragen_aber_nicht_in_der_aufloesung():
    assert st.clean_answer("Wie ist das in Quelle 1 beschrieben? [Quelle 1]", "next") \
        == "Wie ist das beschrieben?"
    assert st.clean_answer("Was gilt hier [Quelle 2]?", "next") == "Was gilt hier?"
    resolved = "Ein Vektor hat eine Länge [Quelle 1]."
    assert st.clean_answer(resolved, "resolve") == resolved


def test_validate_lineare_abbildung_ist_kein_materialbezug_abbildung_2_schon():
    s = _state(OPEN_Q)
    assert "unterlagen_bezug" not in st.validate(
        "Was ist eine lineare Abbildung zwischen zwei Vektorräumen?", "next", s)
    assert "unterlagen_bezug" in st.validate(
        "Was zeigt dir die Länge des Pfeils in Abbildung 2?", "next", s)
    assert "unterlagen_bezug" in st.validate(
        "Wie steht es in der folgenden Skizze um die Länge?", "next", s)
    assert "unterlagen_bezug" in st.validate("Was sagt Definition 1 über Vektoren?", "next", s)


def test_validate_aufloesung_darf_nicht_mit_frage_enden():
    s = _state(OPEN_Q)
    assert "nicht_aufgeloest" in st.validate(
        "Ein Vektor hat Länge und Richtung. Verstehst du das jetzt besser?", "resolve", s)
    assert st.validate("Ein Vektor hat Länge, Richtung und Richtungssinn [Quelle 1].",
                       "resolve", s) == []


def test_validate_erkennt_wiederholung_der_letzten_antwort_auch_mit_anderen_quellenmarkern():
    s = _state([_u(START), _a(LOOP_TEXT)])
    assert "wiederholung" in st.validate(LOOP_TEXT.replace("[Quelle 1]", "[Quelle 2]"), "next", s)
    # Gleiche Aufgabe, aber wirklich anderer Text -> kein Treffer.
    assert "wiederholung" not in st.validate(
        "Wie unterscheidet sich ein Ortsvektor von einem freien Vektor?", "next", s)


def test_validate_frage_zu_aehnlich_gilt_nicht_fuer_hinweise():
    s = _state([_u(START), _a("Was beschreibt die Länge eines Vektors?")])
    near = "Was beschreibt die Länge eines Vektors denn genau?"
    assert "frage_wiederholt" in st.validate(near, "next", s)
    assert "frage_wiederholt" not in st.validate("Denk an den Betrag. " + near, "hint", s)


def test_validate_dritte_person_und_fehlende_frage_und_leer():
    s = _state(OPEN_Q)
    assert "dritte_person" in st.validate(
        "Die Antwort der/des Studierenden ist teilweise richtig. Was fehlt noch?", "answer", s)
    assert "keine_frage" in st.validate("Das stimmt, ein Vektor hat eine Länge.", "answer", s)
    assert st.validate("  ", "answer", s) == ["leer"]


# --------------------------------------------------------------------------- #
# Ein Zug: Versuche, Neuversuch, Rückfall
# --------------------------------------------------------------------------- #
def test_generate_turn_sauberer_erster_versuch_kein_neuversuch():
    llm = FakeLLM("Was versteht man unter dem Betrag eines Vektors?")
    res = st.generate_turn(llm, kind="start", note=None, state=_state(), question="x", context="K")
    assert res.text == "Was versteht man unter dem Betrag eines Vektors?"
    assert (res.attempts, res.problems, res.fallback) == (1, [], False)
    assert llm.calls[0]["temperature"] == 0.3 and "options" not in llm.calls[0]


def test_generate_turn_verwirft_wiederholung_und_versucht_es_anders_erneut():
    llm = FakeLLM(LOOP_TEXT, "Wie unterscheidet sich ein Ortsvektor von einem freien Vektor?")
    res = st.generate_turn(llm, kind="next", note=None, state=_state([_u(START), _a(LOOP_TEXT)]),
                           question="Nächster Aspekt desselben Themas.", context="K")
    assert res.text == "Wie unterscheidet sich ein Ortsvektor von einem freien Vektor?"
    assert (res.attempts, res.fallback) == (2, False)
    second = llm.calls[1]
    assert second["temperature"] > llm.calls[0]["temperature"]
    assert second["options"]["repeat_penalty"] > 1.0
    assert "KORREKTUR" in second["messages"][1]["content"]
    assert "wiederholte eine frühere Antwort" in second["messages"][1]["content"]


def test_generate_turn_regression_modell_kopiert_immer_dieselbe_antwort():
    """Der gemeldete Hänger: Egal was gefragt wird, das Modell liefert denselben Text.
    Der Code darf ihn nie wieder ausgeben, sondern muss ehrlich neu ansetzen."""
    history = [_u(START), _a(LOOP_TEXT)]
    chunk = ("Ein Vektor wird vollständig beschrieben durch seine Länge, seine Richtung "
             "und seinen Richtungssinn. ") * 3
    for question, kind in [("Löse es auf.", "resolve"), (HINT, "hint"),
                           ("Nächster Aspekt desselben Themas.", "next")]:
        llm = FakeLLM(LOOP_TEXT)
        res = st.generate_turn(llm, kind=kind, note=None, state=_state(history),
                               question=question, context="K", fallback_chunks=[chunk])
        assert res.fallback is True, kind
        assert res.text != LOOP_TEXT, kind
        assert len(llm.calls) == 3, kind                 # alle Versuche genutzt


def test_generate_turn_rueckfall_bei_aufloesung_zitiert_die_unterlage():
    llm = FakeLLM("Und was meinst du dazu? Wie siehst du das?")   # fragt trotz Auflösen-Wunsch
    res = st.generate_turn(
        llm, kind="resolve", note=None, state=_state(OPEN_Q), question="Löse es auf.",
        context="K",
        fallback_chunks=["Kurz.", "Ein Vektor wird vollständig beschrieben durch seine Länge, "
                         "seine Richtung und seinen Richtungssinn, wie die Unterlagen "
                         "festhalten."])
    assert res.fallback is True
    assert "Richtungssinn" in res.text and res.text.endswith("[Quelle 1]")
    assert not st.is_open_question(res.text)


def test_generate_turn_rueckfall_ohne_unterlage_fordert_zum_neuen_anlauf_auf():
    llm = FakeLLM("Frage?")                                       # zu kurz -> "leer"
    res = st.generate_turn(llm, kind="next", note=None, state=_state(OPEN_Q),
                           question="n", context="K")
    assert res.fallback and TOPIC in res.text
    assert st.is_open_question(res.text)


def test_generate_turn_erster_fehler_wird_durchgereicht():
    llm = FakeLLM(RuntimeError("Ollama nicht erreichbar"))
    with pytest.raises(RuntimeError, match="Ollama"):
        st.generate_turn(llm, kind="start", note=None, state=_state(), question="x", context="K")


def test_generate_turn_fehler_im_neuversuch_behaelt_beste_fassung():
    llm = FakeLLM("Was zeigt dir die Länge des Pfeils in Abbildung 2?",   # nur weicher Mangel
                  RuntimeError("Timeout"))
    res = st.generate_turn(llm, kind="start", note=None, state=_state(), question="x", context="K")
    assert res.text.startswith("Was zeigt dir die Länge")
    assert res.problems == ["unterlagen_bezug"] and not res.fallback


def test_generate_turn_weiche_maengel_nach_allen_versuchen_sind_kein_rueckfall():
    llm = FakeLLM("Was zeigt dir die Länge des Pfeils in Abbildung 2?")
    res = st.generate_turn(llm, kind="start", note=None, state=_state(), question="x", context="K")
    assert res.fallback is False and res.attempts == 3
    assert res.problems == ["unterlagen_bezug"]


def test_generate_turn_waehlt_unter_mehreren_mangelhaften_die_mit_dem_kleinsten_mangel():
    llm = FakeLLM("Was zeigt dir die Länge des Pfeils in Abbildung 2?",   # Bezug auf Abbildung
                  "Ein Vektor hat Länge, Richtung und Richtungssinn.",    # keine Frage (leichter)
                  "Was zeigt dir die Länge des Pfeils in Abbildung 3?")
    res = st.generate_turn(llm, kind="start", note=None, state=_state(), question="x", context="K")
    assert res.text == "Ein Vektor hat Länge, Richtung und Richtungssinn."
    assert res.problems == ["keine_frage"] and res.attempts == 3
