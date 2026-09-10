"""Pytest-Konfiguration fuer die Offline-Testsuite.

Legt die Repo-Wurzel auf den Importpfad und stellt einen Loader bereit, der
EINZELNE reine Funktionen aus Modulen laedt, deren Vollimport schwer/teuer waere
(z. B. ``ragapp.llm`` zieht ``ollama``, ``ragapp.study`` zieht ``chromadb``).
Dadurch laufen alle Tests OHNE GPU/Modelle/Ollama und ohne diese schweren
Abhaengigkeiten - genau das, was die CI braucht.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

# Repo-Wurzel importierbar machen (``import ragapp...`` in den Tests).
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_functions(source_path, names, extra_globals=None, const_names=None):
    """Extrahiert die genannten top-level-Funktionen aus ``source_path`` und fuehrt
    NUR diese isoliert aus - ohne den restlichen Modulimport (der schwere
    Abhaengigkeiten wie ollama/chromadb ziehen wuerde).

    ``names``          : Liste der zu ladenden Funktionsnamen (auch Hilfsfunktionen,
                         die untereinander aufgerufen werden, teilen sich denselben
                         Namespace).
    ``extra_globals``  : Globals, die die Funktionen erwarten (z. B. ``re``, ``json``,
                         ``time`` oder Modul-Konstanten).
    ``const_names``    : optionale Liste top-level-Konstanten (``NAME = ...``), die die
                         Funktionen erwarten (z. B. ein Regex/Marker-Tupel) - werden aus
                         derselben Quelldatei mitgeladen statt in Tests dupliziert zu
                         werden (sonst driftet die Test-Kopie irgendwann vom Original ab).
    Rueckgabe: ``{name: funktion_oder_konstante}`` (Funktionen + Konstanten gemeinsam).
    """
    source_path = Path(source_path)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    const_names = set(const_names or ())
    wanted = [n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name in set(names)]
    missing = set(names) - {n.name for n in wanted}
    if missing:
        raise LookupError(f"Funktion(en) {sorted(missing)} nicht in {source_path} gefunden")
    const_nodes = [n for n in tree.body
                   if isinstance(n, ast.Assign) and len(n.targets) == 1
                   and isinstance(n.targets[0], ast.Name) and n.targets[0].id in const_names]
    missing_consts = const_names - {n.targets[0].id for n in const_nodes}
    if missing_consts:
        raise LookupError(f"Konstante(n) {sorted(missing_consts)} nicht in {source_path} gefunden")
    # ``from __future__ import annotations`` voranstellen: so werden die
    # Typannotationen NICHT ausgewertet (z. B. ``-> Any`` in ``_safe_json``, dessen
    # Name hier bewusst nicht importiert ist) - die Isolation bleibt schlank.
    future = ast.ImportFrom(module="__future__",
                            names=[ast.alias(name="annotations", asname=None)], level=0)
    module = ast.Module(body=[future, *const_nodes, *wanted], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace: dict = dict(extra_globals or {})
    exec(compile(module, str(source_path), "exec"), namespace)  # noqa: S102 - bewusste Isolation
    return {name: namespace[name] for name in (*names, *const_names)}


@pytest.fixture(scope="session")
def load_functions():
    """Fixture: gibt den Isolations-Loader zurueck (siehe ``_load_functions``)."""
    return _load_functions


@pytest.fixture(scope="session")
def ragapp_dir():
    """Absoluter Pfad zum ``ragapp``-Paket (fuer den Quelltext-Loader)."""
    return ROOT / "ragapp"
