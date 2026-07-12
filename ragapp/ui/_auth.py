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

from ragapp.config import settings, SHUTDOWN_SENTINEL, OPEN_WINDOW_FILE
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
    import os
    # Reiner localhost-Betrieb (Linux/macOS start.sh bindet Streamlit an 127.0.0.1):
    # es kann NUR der eigene Rechner zugreifen, ein Netzwerk-Zugriff ist gar nicht
    # möglich. Dann ist kein Token/PIN nötig -> immer als lokales Fenster werten.
    # (Auf Windows läuft der Zugriff stattdessen über das geheime Token, weil
    # ragapp.desktop bewusst an 0.0.0.0 bindet.)
    if os.environ.get("RAG_LOCAL_ONLY") == "1":
        return True
    if st.session_state.get("_local_ok"):
        return True
    token = os.environ.get("RAG_LOCAL_TOKEN", "")
    if token:
        try:
            if st.query_params.get("k") == token:
                st.session_state["_local_ok"] = True
                return True
        except Exception:  # noqa: BLE001
            pass
    return False


def _restore_local_token_from_storage() -> None:
    """PC-Fenster nach einem Neuladen/Seitenwechsel wieder erkennen.

    Die Freischaltung des PC-Fensters haengt am geheimen Token in der Adresse
    (``?k=…``). Verwirft ein Neuladen oder ein Seitenwechsel diesen Parameter (und
    ist die Streamlit-Sitzung frisch, also ``_local_ok`` noch nicht gesetzt), wuerde
    das PC-Fenster faelschlich wie ein fremdes Geraet gesperrt ("Zugriff nicht
    aktiv" bzw. PIN-Abfrage). Das zuletzt gueltige Token liegt aber noch im
    Browser-Speicher (``rag_local_token``, von ``_sync_local_token`` gesichert).

    Fehlt es in der Adresse, haengen wir es hier EINMAL wieder an und laden neu -
    danach greift die normale ``?k``-Pruefung. Das Handy hat dieses Token nie
    gesetzt -> dort ist der Speicher leer und es passiert nichts (normale
    PIN-Abfrage bleibt).

    Schleifensicher: neu geladen wird nur, wenn das gespeicherte Token NICHT bereits
    identisch in der Adresse steht. Steht es schon drin und wird trotzdem nicht
    akzeptiert (veraltet), bleibt es bei der normalen Sperre - kein Reload-Kreis."""
    import os
    if not os.environ.get("RAG_LOCAL_TOKEN"):
        return   # ohne lokales Token (z. B. reiner 'streamlit run') nichts zu tun
    try:
        import streamlit.components.v1 as _c
        _c.html(
            "<script>try{"
            "var w=window.parent,raw=w.localStorage.getItem('rag_local_token');"
            "if(raw){var t=JSON.parse(raw);"
            "if(t){var u=new URL(w.location.href);"
            "if(u.searchParams.get('k')!==t){u.searchParams.set('k',t);"
            "w.location.replace(u.toString());}}}"
            "}catch(e){}</script>", height=0)
    except Exception:  # noqa: BLE001
        pass


def _pin_gate() -> None:
    # Lokales PC-Fenster (kennt das geheime Token): immer erlaubt, kein PIN.
    if _is_local_window():
        return
    # PC-Fenster, dem nur der ?k-Parameter fehlt (nach Neuladen/Seitenwechsel):
    # Token aus dem Browser-Speicher zurueckholen und neu laden, bevor gesperrt wird.
    _restore_local_token_from_storage()
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
    """Fallback: das lokale KI-Modell sofort aus dem Speicher entladen, falls kein
    Starter (start.sh-Waechter / ragapp.desktop) das Beenden-Signal mitliest
    (z. B. bei direktem 'streamlit run'). Der Ollama-Dienst selbst wird NICHT
    gestoppt - so bleiben andere Nutzer unberuehrt und es ist kein Root noetig."""
    import os
    if os.name == "nt":
        import subprocess
        _flag = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # kein aufblitzendes Terminal
        for name in ("ollama.exe", "ollama app.exe", "ollama-lib.exe"):
            try:
                subprocess.run(["taskkill", "/IM", name, "/F", "/T"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               check=False, creationflags=_flag)
            except Exception:  # noqa: BLE001
                pass
        return
    # POSIX (Linux/macOS): geladene Modelle via API entladen (keep_alive=0).
    try:
        import json
        import urllib.request
        base = str(settings.OLLAMA_BASE_URL or "http://127.0.0.1:11434").rstrip("/")
        with urllib.request.urlopen(base + "/api/ps", timeout=3.0) as r:
            ps = json.loads(r.read().decode("utf-8") or "{}")
        for m in ps.get("models", []):
            name = m.get("model") or m.get("name")
            if not name:
                continue
            data = json.dumps({"model": name, "keep_alive": 0}).encode("utf-8")
            req = urllib.request.Request(
                base + "/api/generate", data=data,
                headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    resp.read()
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass


def _quit_button() -> None:
    with st.sidebar:
        # Zweites Fenster (z. B. fuer einen zweiten Bildschirm) - nur sinnvoll, wenn
        # die App ueber den Starter (ragapp.desktop) laeuft, der den Wunsch mitliest.
        import os as _os
        if _os.environ.get("RAG_LOCAL_TOKEN"):
            if st.button("🖥️ Zweites Fenster öffnen", use_container_width=True,
                         help="Öffnet die App in einem zweiten Fenster – ideal für einen "
                              "zweiten Bildschirm. Beide Fenster teilen sich denselben "
                              "Server und dasselbe KI-Modell."):
                try:
                    OPEN_WINDOW_FILE.write_text("1", encoding="utf-8")
                    st.toast("Zweites Fenster wird geöffnet …")
                except Exception:  # noqa: BLE001
                    pass
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
