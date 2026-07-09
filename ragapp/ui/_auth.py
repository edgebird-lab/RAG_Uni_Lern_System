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
    _sync_local_token()
    _pin_gate()
    _quit_button()


# --------------------------------------------------------------------------- #
# PIN-Sperre
# --------------------------------------------------------------------------- #
def _sync_local_token() -> None:
    """In JEDEM Modus ausgeführt: steht das lokale Token in der URL, es merken und
    in localStorage sichern. So überlebt es Navigation + den Moduswechsel-Neustart,
    damit das PC-Fenster danach ohne PIN erkannt wird. (Das erste Laden passiert im
    lokalen Modus, wo das PIN-Gate sonst gar nicht bis hierher käme.)"""
    import os
    token = os.environ.get("RAG_LOCAL_TOKEN", "")
    if not token:
        return
    try:
        q = st.query_params.get("k")
    except Exception:  # noqa: BLE001
        q = None
    if q and q == token:
        st.session_state["_local_ok"] = True
        try:
            import json
            import streamlit.components.v1 as _c
            _c.html("<script>try{window.parent.localStorage.setItem('rag_local_token',"
                    + json.dumps(q) + ");}catch(e){}</script>", height=0)
        except Exception:  # noqa: BLE001
            pass


def _is_local_window() -> bool:
    """True für das lokale PC-Fenster (kennt das geheime Token). Das Handy kennt es
    nicht und muss den PIN eingeben."""
    if st.session_state.get("_local_ok"):
        return True
    import os
    token = os.environ.get("RAG_LOCAL_TOKEN", "")
    if token:
        try:
            if st.query_params.get("k") == token:
                st.session_state["_local_ok"] = True
                return True
        except Exception:  # noqa: BLE001
            pass
    return False


def _pin_gate() -> None:
    # Lokales PC-Fenster (kennt das geheime Token): immer erlaubt, kein PIN.
    if _is_local_window():
        return
    # Nicht-lokaler Zugriff (Handy). Nur wenn am PC freigeschaltet.
    mode = netinfo.current_mode()   # local / network / tunnel
    if mode == "local":
        st.title("🔒 Zugriff nicht aktiv")
        st.info("Der Handy-/Netzwerk-Zugriff ist an diesem PC nicht eingeschaltet. "
                "Schalte ihn dort in der App unter **⚙️ Einstellungen → 📱 "
                "Handy-Zugriff** ein.")
        st.stop()

    pin = (str(settings.UI_ACCESS_PIN) if settings.UI_ACCESS_PIN else "").strip()

    # Zugriff aktiv, aber kein PIN gesetzt -> sicherheitshalber sperren.
    if not pin:
        st.title("🔒 Kein PIN gesetzt")
        st.error("Der Zugriff ist aktiv, aber es wurde noch kein PIN festgelegt.")
        st.info("Setze am PC unter **⚙️ Einstellungen → 📱 Handy-Zugriff** einen PIN.")
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
