"""
Fortschritts-Anzeige für die Ingestion (Streamlit)
==================================================
Konsumiert den erweiterten Ingestion-Callback

    progress(message: str, done: int | None = None, total: int | None = None)

und rendert daraus einen Balken mit Prozent + geschätzter Restzeit (ETA).

Rückwärtskompatibel: Aufrufe ohne done/total (alter Vertrag) zeigen nur die
Meldung; der Balken behält seinen letzten Stand.

Robust gegen wechselnde Zähl-Skalen innerhalb eines Vorgangs (OCR zählt Seiten,
Embedding zählt Batches): sobald sich `total` ändert oder `done` zurückspringt,
beginnt eine neue Stufe und die ETA-Uhr wird zurückgesetzt.
"""
from __future__ import annotations

import time
import streamlit as st


def fmt_dauer(sekunden: float) -> str:
    """Sekunden -> kompakte deutsche Restzeit (z. B. '2 min 05 s')."""
    s = int(max(0, sekunden))
    if s < 60:
        return f"{s} s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m} min {s:02d} s"
    h, m = divmod(m, 60)
    return f"{h} h {m:02d} min"


class ProgressReporter:
    """Ein wiederverwendbarer Fortschritts-Callback für EINEN Balken.
    Aufruf wie der Backend-Callback:  reporter(message, done, total)"""

    def __init__(self, slot=None):
        # Eigener Slot -> Balken lässt sich in-place aktualisieren.
        self._bar = slot if slot is not None else st.empty()
        self._frac = 0.0
        self._stage_total: int | None = None
        self._stage_start: float = 0.0
        self._last_done: int = 0

    def __call__(self, message: str,
                 done: int | None = None, total: int | None = None) -> None:
        # Alter Vertrag / grobe Stufe: nur Text, Balkenstand bleibt.
        if not total or total <= 0 or done is None:
            self._bar.progress(self._frac, text=f"⏳ {message}")
            return

        done = max(0, min(int(done), int(total)))
        # Stufenwechsel (neue Skala oder neue Datei) -> ETA-Uhr neu starten.
        if total != self._stage_total or done < self._last_done:
            self._stage_total = total
            self._stage_start = time.time()
        self._last_done = done

        self._frac = done / total
        eta = ""
        el = time.time() - self._stage_start
        if done > 0 and el > 0.5:
            eta = f" · noch ca. {fmt_dauer((el / done) * (total - done))}"
        self._bar.progress(
            self._frac,
            text=f"{message} · {done}/{total} ({self._frac * 100:.0f} %){eta}",
        )

    def finish(self, message: str = "Fertig") -> None:
        self._bar.progress(1.0, text=f"✅ {message}")

    def clear(self) -> None:
        self._bar.empty()
        self._frac = 0.0
