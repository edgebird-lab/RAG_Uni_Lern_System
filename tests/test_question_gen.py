"""Filter fuer generierte Kartenfragen (ohne LLM)."""


def test_heading_echo_filtert_ueberschrift_paraphrasen(load_functions, ragapp_dir):
    fns = load_functions(
        ragapp_dir / "ingestion" / "question_gen.py",
        ["_is_frage", "_is_heading_echo", "_chunk_heading", "_normalize_question_text"],
        {"re": __import__("re")},
        const_names=["_IMPERATIVE", "_HEADING_ECHO_FILLER"],
    )
    echo = fns["_is_heading_echo"]
    chunk = "# Deckungsbeitrag\n\nErlös minus variable Kosten."
    assert echo("Was ist Deckungsbeitrag?", chunk)
    assert echo("Was ist der Deckungsbeitrag?", chunk)
    assert not echo(
        "Wie unterscheidet sich der Deckungsbeitrag vom Gewinn?", chunk)
    assert fns["_is_frage"]("Was ist Deckungsbeitrag?")
    assert fns["_chunk_heading"](chunk) == "Deckungsbeitrag"
