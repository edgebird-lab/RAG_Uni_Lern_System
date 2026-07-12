"""Kauderwelsch-Gate ``ragapp.ingestion.textquality.is_gibberish``.

Regressions-Absicherung des Filters: echtes (strukturell verunstaltetes)
Kauderwelsch -> True, dichter deutscher Fachabsatz (mit Komposita) -> False.
``textquality.py`` importiert oben nur ``re``; das Woerterbuch (pyspellchecker)
wird lazy geladen und faellt sauber zurueck.

Design-Hinweis: Das Primaersignal ist der KOMPOSITUM-bewusste Echtwort-Anteil
(rwr). Er faengt dichte Fachabsaetze (Komposita werden an Fugen zerlegt -> hoher
Anteil -> KEIN Kauderwelsch) UND 'aussprechbares' Kauderwelsch mit niedrigem
Echtwort-Anteil. Die Struktur darf rwr NICHT ueberstimmen (sonst rutscht
strukturell 'sauberes' Kauderwelsch durch); sie ist nur das Ersatzsignal, wenn
kein Woerterbuch verfuegbar ist. Getestete Invarianten:
  * dichtes Deutsch -> kein Kauderwelsch (Struktur- UND Woerterbuch-Pfad)
  * struktureller Zeichenmuell -> Kauderwelsch (Struktur- UND Woerterbuch-Pfad)
  * aussprechbares Kauderwelsch (hohe Struktur, wenig echte Woerter) -> nur der
    Woerterbuch-Pfad fangt es (Regressionsschutz gegen frueheres max()).
"""
import pytest

from ragapp.ingestion import textquality as tq


# Dichter deutscher Fachabsatz mit Komposita (Kostenrechnung, Deckungsbeitrag, ...).
GERMAN = (
    "Die Kostenrechnung ist ein wichtiges Werkzeug in dem Betrieb. Sie zeigt, "
    "wie sich der Deckungsbeitrag aus dem Umsatz und den variablen Kosten ergibt. "
    "Wenn die Fixkosten hoch sind, dann muss der Preis auch hoeher sein, damit am "
    "Ende ein Gewinn bleibt. Diese Regel gilt fast immer und ist leicht zu verstehen."
)

# Struktureller Zeichenmuell: Ziffern-im-Wort + Konsonantenbrei (typisches
# OCR-Kauderwelsch). Beide Signale sind niedrig -> sicher als Kauderwelsch erkannt.
STRUCTURAL_GARBAGE = "ridht8en 2at d3r zqwrtx fhgklm pfkztss xcvbnm qwrtz"

# 'Aussprechbares' Kauderwelsch: strukturell sauber (grossbuchstaben-Tokens ohne
# Ziffernmuell -> hohe Struktur), aber KEINE echten Woerter. Fing das frühere
# max(rwr, structural) NICHT (Struktur ueberstimmte) -> Regressionsfall.
PRONOUNCEABLE_GARBAGE = "EBEHSOHFTEH FTEH SHFT QWLKJ ZZFT HGTR PLMN BVCX RTZU"


def test_dense_german_ist_kein_kauderwelsch_strukturell(monkeypatch):
    # Woerterbuch deaktivieren -> deterministisch die Struktur-Heuristik pruefen.
    monkeypatch.setattr(tq, "_SPELL", False)
    is_gib, grund = tq.is_gibberish(GERMAN)
    assert is_gib is False, grund


def test_struktureller_muell_ist_kauderwelsch_strukturell(monkeypatch):
    monkeypatch.setattr(tq, "_SPELL", False)
    is_gib, _grund = tq.is_gibberish(STRUCTURAL_GARBAGE)
    assert is_gib is True


def test_dense_german_ueber_woerterbuch_kein_kauderwelsch(monkeypatch):
    # Mit Woerterbuch: Komposita werden an bekannten Fugen zerlegt -> hoher Echtwort-
    # Anteil -> KEIN Kauderwelsch (Absicherung gegen falsch-positives Verwerfen).
    monkeypatch.setattr(tq, "_SPELL", None)          # Lazy-Load wieder erlauben
    if tq.real_word_ratio(GERMAN) is None:
        pytest.skip("kein Woerterbuch (pyspellchecker) verfuegbar")
    is_gib, grund = tq.is_gibberish(GERMAN)
    assert is_gib is False, grund


def test_struktureller_muell_ueber_woerterbuch_bleibt_kauderwelsch(monkeypatch):
    monkeypatch.setattr(tq, "_SPELL", None)
    if tq.real_word_ratio(STRUCTURAL_GARBAGE) is None:
        pytest.skip("kein Woerterbuch (pyspellchecker) verfuegbar")
    is_gib, _grund = tq.is_gibberish(STRUCTURAL_GARBAGE)
    assert is_gib is True


def test_namensliste_ist_kein_kauderwelsch(monkeypatch):
    # Reine Eigennamen-/Wirkstoff-/Bibliografielisten: strukturell perfekt, aber
    # wörterbuch-UNbekannt (niedriges rwr). Sollen NICHT verworfen werden – die
    # praktisch perfekte Struktur (>=0.9) rettet echten, wörterbuch-unbekannten Inhalt.
    monkeypatch.setattr(tq, "_SPELL", None)
    namen = ("Habermas Luhmann Bourdieu Foucault Adorno Horkheimer Simmel Weber "
             "Durkheim Parsons Giddens Beck")
    if tq.real_word_ratio(namen) is None:
        pytest.skip("kein Woerterbuch (pyspellchecker) verfuegbar")
    is_gib, grund = tq.is_gibberish(namen)
    assert is_gib is False, grund


def test_aussprechbares_kauderwelsch_wird_ueber_woerterbuch_erkannt(monkeypatch):
    # Regressionsschutz gegen frueheres max(rwr, structural): 'EBEHSOHFTEH ...' ist
    # strukturell sauber (hohe Struktur), enthaelt aber kaum echte Woerter -> muss
    # ueber den Echtwort-Anteil (rwr) als Kauderwelsch erkannt werden.
    monkeypatch.setattr(tq, "_SPELL", None)
    rwr = tq.real_word_ratio(PRONOUNCEABLE_GARBAGE)
    if rwr is None:
        pytest.skip("kein Woerterbuch (pyspellchecker) verfuegbar")
    assert rwr < 0.4                      # Echtwort-Anteil klar niedrig
    is_gib, _grund = tq.is_gibberish(PRONOUNCEABLE_GARBAGE)
    assert is_gib is True
