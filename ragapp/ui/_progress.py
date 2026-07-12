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

    # ETA aus dem AKTUELLEN Tempo (gleitendes Zeitfenster) statt aus dem
    # Gesamtdurchschnitt seit Stufenbeginn: sonst bleibt die Schätzung von den
    # (oft schnellen) ersten Einheiten dauerhaft zu optimistisch und "hängt"
    # (z. B. 14 min -> nach 10 min immer noch 12 min). Das Fenster misst, wie
    # viele Einheiten in den letzten ~_WINDOW_S Sekunden wirklich geschafft
    # wurden; eine leichte Glättung (EMA) verhindert Zappeln, ohne die
    # Konvergenz zu bremsen.
    _WINDOW_S: float = 15.0

    def __init__(self, slot=None):
        # Eigener Slot -> Balken lässt sich in-place aktualisieren.
        self._bar = slot if slot is not None else st.empty()
        self._frac = 0.0
        self._stage_total: int | None = None
        self._last_done: int = 0
        self._samples: list[tuple[float, int]] = []   # (Zeit, done) im Fenster
        self._eta_smooth: float | None = None         # geglättete Restsekunden

    def __call__(self, message: str,
                 done: int | None = None, total: int | None = None) -> None:
        # Alter Vertrag / grobe Stufe: nur Text, Balkenstand bleibt.
        if not total or total <= 0 or done is None:
            self._bar.progress(self._frac, text=f"⏳ {message}")
            return

        done = max(0, min(int(done), int(total)))
        now = time.time()
        # Stufenwechsel (neue Skala oder neue Datei) -> Fenster + ETA neu starten.
        if total != self._stage_total or done < self._last_done:
            self._stage_total = total
            self._samples = [(now, done)]
            self._eta_smooth = None
        self._last_done = done
        self._frac = done / total

        # Nur die Messpunkte der letzten _WINDOW_S Sekunden behalten (aber immer
        # den ältesten Punkt jenseits des Fensters als Anker lassen, damit auch
        # bei seltenen Updates eine Rate berechenbar ist).
        self._samples.append((now, done))
        cutoff = now - self._WINDOW_S
        # Alles vor dem Fenster verwerfen; immer >=2 Punkte behalten, damit auch
        # bei seltenen Updates eine Rate berechenbar bleibt. Basis = ältester Punkt
        # IM Fenster -> Rate spiegelt das Tempo der letzten ~_WINDOW_S Sekunden.
        while len(self._samples) > 2 and self._samples[0][0] < cutoff:
            self._samples.pop(0)

        eta = ""
        base_t, base_d = self._samples[0]
        dt, dd = now - base_t, done - base_d
        if dd > 0 and dt > 0.3:
            remaining = (total - done) * (dt / dd)          # Sek. beim aktuellen Tempo
            self._eta_smooth = (remaining if self._eta_smooth is None
                                else 0.5 * self._eta_smooth + 0.5 * remaining)
            eta = f" · noch ca. {fmt_dauer(self._eta_smooth)}"
        self._bar.progress(
            self._frac,
            text=f"{message} · {done}/{total} ({self._frac * 100:.0f} %){eta}",
        )

    def finish(self, message: str = "Fertig") -> None:
        self._bar.progress(1.0, text=f"✅ {message}")

    def clear(self) -> None:
        self._bar.empty()
        self._frac = 0.0
