"""Probeklausur im Streamlit-AppTest: Abgeben -> Ergebnis-Karte, Ergebnis-Lauf ohne st.stop().

Läuft in einem eigenen Prozess (``tests/_pruefung_page_probe.py``), wie der Lernplan-Test.
Temporäre Datenbank, Benotung durch eine Attrappe, keine Modelle, keine echten Daten."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

streamlit_testing = pytest.importorskip("streamlit.testing.v1")

PROBE = Path(__file__).with_name("_pruefung_page_probe.py")


def test_probeklausur_im_apptest(tmp_path):
    proc = subprocess.run([sys.executable, str(PROBE), str(tmp_path)], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=240,
                          cwd=str(PROBE.parents[1]))
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out[-3000:]
    assert "ALLE CHECKS OK" in proc.stdout, out[-3000:]
    for n in range(1, 6):
        assert f"OK {n} " in proc.stdout, f"Prüfung {n} fehlt:\n{out[-3000:]}"
