"""Countdown der Probeklausur (``_countdown`` in ``6_📝_Prüfung.py``).

Nach "Abgeben & auswerten" konnte ein Countdown-Tick aus dem Browser erst NACH dem
Ergebnis-Lauf ausgefuehrt werden (der endet mit ``st.stop()``, das raeumt das Fragment
nicht ab). Das Fragment schrieb dann an seine alte Position, also ueber die
Ergebnis-Karte: im Browser fehlte das Ergebnis und der Countdown blieb stehen.
Das Fragment darf deshalb nur fuer die laufende, noch nicht abgegebene Klausur
etwas ausgeben. Isoliert geladen (kein Streamlit-Server, kein Modell)."""
from __future__ import annotations

import pytest

PAGE = "ui/pages/6_📝_Prüfung.py"
EXAM = "_exam"   # wie in der Seite (siehe test_seitenkonstante_passt)


class _FakeSt:
    def __init__(self, session_state: dict):
        self.session_state = session_state
        self.out: list[str] = []
        self.reruns = 0

    def fragment(self, run_every=None):
        return lambda fn: fn

    def markdown(self, text, **_):
        self.out.append(text)

    def caption(self, text, **_):
        self.out.append(text)

    def rerun(self):
        self.reruns += 1


@pytest.fixture
def countdown(load_functions, ragapp_dir):
    def _make(exam: dict, session_state: dict, remaining: float = 600.0):
        st = _FakeSt(session_state)
        funcs = load_functions(ragapp_dir / PAGE, ["_countdown"], {
            "st": st, "exam": exam, "EXAM": EXAM, "_remaining": lambda: remaining})
        return funcs["_countdown"], st
    return _make


def test_laufende_klausur_zeigt_den_countdown(countdown):
    exam = {"done": False}
    fn, st = countdown(exam, {EXAM: exam}, remaining=125)
    fn()
    assert any("02:05 verbleibend" in t for t in st.out)


def test_nach_der_abgabe_schreibt_das_fragment_nichts(countdown):
    exam = {"done": True, "result": {}}
    fn, st = countdown(exam, {EXAM: exam})
    fn()
    assert st.out == [] and st.reruns == 0


def test_nach_neuer_pruefung_schreibt_das_alte_fragment_nichts(countdown):
    alt = {"done": True}
    fn, st = countdown(alt, {})                       # "Neue Prüfung": EXAM geloescht
    fn()
    assert st.out == [] and st.reruns == 0
    fn, st = countdown(alt, {EXAM: {"done": False}})  # "Nur Fehler wiederholen": neue Klausur
    fn()
    assert st.out == [] and st.reruns == 0


def test_abgelaufene_zeit_loest_weiter_die_auto_abgabe_aus(countdown):
    exam = {"done": False}
    fn, st = countdown(exam, {EXAM: exam}, remaining=0)
    fn()
    assert st.reruns == 1


def test_seitenkonstante_passt(ragapp_dir):
    src = (ragapp_dir / PAGE).read_text(encoding="utf-8")
    assert f'EXAM = "{EXAM}"' in src
    # Der Waechter steht VOR allem anderen im Fragment.
    body = src.split("def _countdown() -> None:", 1)[1]
    guard = 'if exam.get("done") or st.session_state.get(EXAM) is not exam:'
    assert body.index(guard) < body.index("rem = _remaining()")
