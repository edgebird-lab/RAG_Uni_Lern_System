"""
Seiten-Rahmen: PIN-Sperre (Netzwerk-/Handy-Zugriff) + Beenden-Button
====================================================================
Jede Seite ruft direkt nach ``st.set_page_config`` einmal ``require_pin()`` auf.
Das erledigt zwei Dinge:

  1. PIN-Sperre  - nur im Netzwerkmodus (RAG_NETWORK=1, ueber
     Start_Handy-Zugriff.bat) verlangt jede Seite zuerst den in den
     Einstellungen gesetzten PIN. Im normalen lokalen Betrieb passiert nichts.
  2. Beenden-Button - in der Seitenleiste, der Oberflaeche UND das lokale
     KI-Modell (Ollama) sauber stoppt, damit im Hintergrund nichts weiterlaeuft.
"""
from __future__ import annotations

import streamlit as st

from ragapp.config import settings, SHUTDOWN_SENTINEL
from ragapp import netinfo


def require_pin() -> None:
    _pin_gate()
    _quit_button()


# --------------------------------------------------------------------------- #
# PIN-Sperre
# --------------------------------------------------------------------------- #
def _pin_gate() -> None:
    # Lokaler Modus (Start.bat / App-Fenster): keine Sperre.
    if not netinfo.is_network_mode():
        return

    pin = (str(settings.UI_ACCESS_PIN) if settings.UI_ACCESS_PIN else "").strip()

    # Netzwerkmodus, aber kein PIN gesetzt -> Zugriff sicherheitshalber sperren.
    if not pin:
        st.title("🔒 Kein PIN gesetzt")
        st.error("Der Handy-/Netzwerk-Zugriff ist aktiv, aber es wurde noch kein "
                 "PIN festgelegt.")
        st.info("Starte die App einmal normal (Doppelklick auf **Start.bat**) und "
                "setze unter **⚙️ Einstellungen → 📱 Handy-Zugriff** einen PIN. "
                "Danach den Handy-Zugriff neu starten.")
        st.stop()

    if st.session_state.get("_auth_ok"):
        return

    st.title("🔒 RAG-Lernsystem")
    st.caption("Bitte gib den PIN ein, um fortzufahren.")
    entered = st.text_input("PIN", type="password", key="_pin_input")
    angemeldet = st.button("Anmelden", type="primary")
    if angemeldet or entered:
        if entered and entered == pin:
            st.session_state["_auth_ok"] = True
            st.rerun()
        elif entered:
            st.error("Falscher PIN.")
    st.stop()


# --------------------------------------------------------------------------- #
# Beenden-Button
# --------------------------------------------------------------------------- #
def _best_effort_stop_ollama() -> None:
    """Fallback: Ollama sofort stoppen, falls kein Starter (ragapp.desktop) das
    Beenden-Signal mitliest (z. B. bei direktem 'streamlit run')."""
    import os
    import subprocess
    if os.name != "nt":
        return
    for name in ("ollama.exe", "ollama app.exe", "ollama-lib.exe"):
        try:
            subprocess.run(["taskkill", "/IM", name, "/F", "/T"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except Exception:  # noqa: BLE001
            pass


def _quit_button() -> None:
    with st.sidebar:
        if st.button("⏻ App beenden", use_container_width=True,
                     help="Stoppt die Oberfläche UND das lokale KI-Modell (Ollama), "
                          "damit im Hintergrund nichts weiterläuft und dein System "
                          "nicht belastet wird."):
            # Signal fuer den Starter (ragapp.desktop): Fenster schliessen +
            # Oberflaeche + Ollama stoppen.
            try:
                SHUTDOWN_SENTINEL.write_text("1", encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
            _best_effort_stop_ollama()
            st.session_state["_shutting_down"] = True

    if st.session_state.get("_shutting_down"):
        st.success("✅ App wird beendet – Oberfläche und lokales KI-Modell (Ollama) "
                   "werden gestoppt. Du kannst dieses Fenster jetzt schließen.")
        st.stop()
