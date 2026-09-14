"""Filter fuer generierte Kartenfragen (ohne LLM)."""


def test_heading_echo_filtert_ueberschrift_paraphrasen(load_functions, ragapp_dir):
    fns = load_functions(
        ragapp_dir / "ingestion" / "question_gen.py",
        ["_is_frage", "is_heading_echo", "_chunk_heading", "_normalize_question_text"],
        {"re": __import__("re")},
        const_names=["_IMPERATIVE", "_HEADING_ECHO_FILLER"],
    )
    echo = fns["is_heading_echo"]
    chunk = "# Deckungsbeitrag\n\nErlös minus variable Kosten."
    assert echo("Was ist Deckungsbeitrag?", chunk)
    assert echo("Was ist der Deckungsbeitrag?", chunk)
    assert not echo(
        "Wie unterscheidet sich der Deckungsbeitrag vom Gewinn?", chunk)
    assert fns["_is_frage"]("Was ist Deckungsbeitrag?")
    assert fns["_chunk_heading"](chunk) == "Deckungsbeitrag"


def test_is_heading_echo_card_nur_generierte_paraphrasen():
    from ragapp.study import is_heading_echo_card
    echo = {
        "source": "question",
        "front": "Was ist Deckungsbeitrag?",
        "back": "# Deckungsbeitrag\n\nErlös minus variable Kosten.",
    }
    ok = {
        "source": "question",
        "front": "Wie unterscheidet sich der Deckungsbeitrag vom Gewinn?",
        "back": "# Deckungsbeitrag\n\nErlös minus variable Kosten.",
    }
    exam = {
        "source": "exam_qa",
        "front": "Was ist Deckungsbeitrag?",
        "back": "# Deckungsbeitrag\n\nErlös minus variable Kosten.",
    }
    assert is_heading_echo_card(echo)
    assert not is_heading_echo_card(ok)
    assert not is_heading_echo_card(exam)
