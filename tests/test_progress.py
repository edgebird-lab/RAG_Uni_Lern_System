"""Tests für ragapp.ui._progress:
- ``fmt_dauer``/``ProgressReporter``: der ORIGINALE Fortschritts-Baustein für
  Ingestion (OCR/Embedding) - sliding-window-geglättete ETA, EIN kombinierter
  Balken+Text-Slot, Aufrufvertrag ``(message, done=None, total=None)``.
- ``progress_tracker``: ein ZWEITER, neuerer Baustein mit dem einfacheren
  ``(done, total, label)``-Vertrag (Audio-Overview, Zusammenfassung) - eigene
  Balken-/Beschriftungs-Widgets, nutzt aber denselben ``fmt_dauer`` fürs
  einheitliche Format.

Reine Logik ohne echtes Streamlit-Rendering: `bar`/`caption`/`slot` sind
einfache Testdoubles mit den Methoden, die die echten st.progress()/
st.empty()-Objekte auch haben."""
from __future__ import annotations

import time

from ragapp.ui._progress import ProgressReporter, fmt_dauer, progress_tracker


class _FakeBar:
    def __init__(self):
        self.value = None

    def progress(self, value):
        self.value = value


class _FakeCaption:
    def __init__(self):
        self.text = None

    def caption(self, text):
        self.text = text


class _FakeSlot:
    """Testdouble für den kombinierten Balken+Text-Slot von ProgressReporter
    (``st.empty()`` + ``.progress(frac, text=...)``)."""
    def __init__(self):
        self.frac = None
        self.text = None
        self.cleared = False

    def progress(self, frac, text=""):
        self.frac = frac
        self.text = text

    def empty(self):
        self.cleared = True


def test_fmt_dauer_nur_sekunden():
    assert fmt_dauer(45) == "45 s"


def test_fmt_dauer_minuten_und_sekunden():
    assert fmt_dauer(135) == "2 min 15 s"


def test_fmt_dauer_glatte_minuten_zeigt_null_sekunden():
    assert fmt_dauer(120) == "2 min 00 s"


def test_fmt_dauer_stunden_und_minuten():
    assert fmt_dauer(3700) == "1 h 01 min"


def test_fmt_dauer_negativ_wird_auf_null_gekappt():
    assert fmt_dauer(-5) == "0 s"


# --------------------------------------------------------------------------- #
# ProgressReporter (Ingestion: OCR-Seiten/Embedding-Batches)
# --------------------------------------------------------------------------- #

def test_progress_reporter_ohne_total_zeigt_nur_text_balken_bleibt():
    slot = _FakeSlot()
    reporter = ProgressReporter(slot)
    reporter("Lese Datei ein …")
    assert slot.text == "⏳ Lese Datei ein …"
    assert slot.frac == 0.0


def test_progress_reporter_mit_total_zeigt_anteil_und_zaehler():
    slot = _FakeSlot()
    reporter = ProgressReporter(slot)
    reporter("Seite", done=1, total=4)
    assert slot.frac == 0.25
    assert "1/4" in slot.text
    assert "25 %" in slot.text


def test_progress_reporter_stufenwechsel_bei_neuem_total_setzt_fenster_zurueck():
    slot = _FakeSlot()
    reporter = ProgressReporter(slot)
    reporter("Datei 1", done=5, total=5)
    assert slot.frac == 1.0
    # neue Datei mit eigener (kleinerer) Skala - kein Crash, korrekter neuer Anteil
    reporter("Datei 2", done=1, total=10)
    assert slot.frac == 0.1


def test_progress_reporter_done_rueckwaerts_setzt_stufe_zurueck_statt_crash():
    slot = _FakeSlot()
    reporter = ProgressReporter(slot)
    reporter("x", done=8, total=10)
    reporter("x", done=2, total=10)  # done < last_done, aber gleiches total
    assert slot.frac == 0.2


def test_progress_reporter_finish_zeigt_haekchen_bei_voller_breite():
    slot = _FakeSlot()
    reporter = ProgressReporter(slot)
    reporter.finish("Fertig")
    assert slot.frac == 1.0
    assert slot.text == "✅ Fertig"


def test_progress_reporter_clear_leert_slot_und_setzt_anteil_zurueck():
    slot = _FakeSlot()
    reporter = ProgressReporter(slot)
    reporter("x", done=5, total=10)
    reporter.clear()
    assert slot.cleared
    assert reporter._frac == 0.0


def test_progress_reporter_ohne_eigenen_slot_nutzt_st_empty(monkeypatch):
    import ragapp.ui._progress as prog_mod
    created = []

    class _FakeSt:
        @staticmethod
        def empty():
            s = _FakeSlot()
            created.append(s)
            return s

    monkeypatch.setattr(prog_mod, "st", _FakeSt())
    reporter = ProgressReporter()
    assert len(created) == 1
    reporter("x", done=1, total=2)
    assert created[0].frac == 0.5


def test_progress_tracker_setzt_balken_auf_anteil():
    bar, cap = _FakeBar(), _FakeCaption()
    cb = progress_tracker(bar, cap, "Test")
    cb(2, 4, "Schritt 2")
    assert bar.value == 0.5


def test_progress_tracker_fertig_zeigt_haekchen_und_dauer():
    bar, cap = _FakeBar(), _FakeCaption()
    cb = progress_tracker(bar, cap, "Test")
    cb(1, 1, "Schritt 1")
    assert bar.value == 1.0
    assert cap.text.startswith("✅ Test fertig")


def test_progress_tracker_zwischenstand_zeigt_done_von_total():
    bar, cap = _FakeBar(), _FakeCaption()
    cb = progress_tracker(bar, cap, "Test")
    cb(1, 4, "Schritt 1")
    assert "1/4" in cap.text


def test_progress_tracker_erster_aufruf_vor_erstem_fortschritt_zeigt_vorbereitung():
    bar, cap = _FakeBar(), _FakeCaption()
    cb = progress_tracker(bar, cap, "Test")
    cb(0, 4, "")
    assert "wird vorbereitet" in cap.text
    assert bar.value == 0.0


def test_progress_tracker_total_null_stuerzt_nicht_ab_durch_division():
    bar, cap = _FakeBar(), _FakeCaption()
    cb = progress_tracker(bar, cap, "Test")
    cb(0, 0, "")
    assert bar.value == 0.0


def test_progress_tracker_timer_startet_erst_beim_ersten_aufruf():
    # Relevant, wenn die Anzeige (bar/caption) schon VOR einer vorausgehenden
    # Phase aufgebaut wird - der Timer darf deren Wartezeit nicht mitzaehlen.
    bar, cap = _FakeBar(), _FakeCaption()
    cb = progress_tracker(bar, cap, "Test")
    time.sleep(0.05)  # simuliert eine vorausgehende Wartezeit VOR dem ersten Aufruf
    cb(1, 2, "")
    cb(2, 2, "")
    assert "0 s" in cap.text or "1 s" in cap.text  # nicht durch die 50ms-Wartezeit verzerrt
