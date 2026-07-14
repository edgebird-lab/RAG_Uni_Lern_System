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

import hmac
import json
import random
import time

import streamlit as st

from ragapp.config import settings, SHUTDOWN_SENTINEL, OPEN_WINDOW_FILE, DATA_DIR
from ragapp import netinfo


# --------------------------------------------------------------------------- #
# Brute-Force-Schutz fuer das PIN-Gate (nur im Netzwerk-/Tunnel-Modus relevant,
# denn dort ist die App ueber trycloudflare.com oeffentlich erreichbar)
# --------------------------------------------------------------------------- #
_PIN_MIN_LENGTH = 6             # Mindestlaenge im WLAN-Modus
_PIN_TUNNEL_MIN_LENGTH = 8      # Tunnel-Modus (weltweit erreichbar) -> laengerer PIN
_PIN_LOCK_AFTER = 5            # so viele Fehlversuche, dann greift die Sperre
_PIN_LOCK_BASE_SECONDS = 5.0   # Basis-Cooldown (waechst exponentiell)
_PIN_LOCK_MAX_SECONDS = 300.0  # Deckel des Cooldowns (5 Minuten)
_PIN_FAIL_DELAY_MAX = 5.0      # kurze serverseitige Verzoegerung je Fehlversuch
# Sitzungsuebergreifender Zaehler (Datei): eine frisch verbundene Websocket-Sitzung
# kann die Sperre so NICHT durch Neuverbinden umgehen (serverseitig erzwungen).
_PIN_GUARD_FILE = DATA_DIR / ".pin_guard.json"
_TRIVIAL_PINS = frozenset({
    "0000", "00000", "000000", "1111", "111111", "1234", "12345", "123456",
    "1234567", "12345678", "123456789", "0123456789", "987654321", "abcdef",
    "password", "passwort", "qwerty", "qwertz", "letmein", "admin", "geheim",
})


def _pin_lock_seconds(fails: int) -> float:
    """Exponentielles Backoff: ab _PIN_LOCK_AFTER Fehlversuchen, gedeckelt. Rein
    (ohne IO/Streamlit) -> von den CI-Tests direkt pruefbar."""
    if fails < _PIN_LOCK_AFTER:
        return 0.0
    over = fails - _PIN_LOCK_AFTER
    return min(_PIN_LOCK_BASE_SECONDS * (2.0 ** over), _PIN_LOCK_MAX_SECONDS)


def _pin_fail_delay(fails: int) -> float:
    """Kleine, serverseitig erzwungene Verzoegerung je Fehlversuch (bremst auch
    scriptgesteuerte Angriffe, die den Zaehler per neuer Sitzung umgehen wollen)."""
    if fails <= 0:
        return 0.0
    return min(float(fails), _PIN_FAIL_DELAY_MAX)


def _is_sequential_pin(p: str) -> bool:
    """Fortlaufende Ziffernfolge (1234.., 9876..) erkennen."""
    if len(p) < 4 or not p.isdigit():
        return False
    diffs = {ord(b) - ord(a) for a, b in zip(p, p[1:])}
    return diffs == {1} or diffs == {-1}


def pin_weakness_reason(pin: str, mode: str = "network") -> "str | None":
    """Klartext-Grund, wenn der PIN fuer den exponierten Betrieb zu schwach ist,
    sonst None. Rein + testbar (keine Streamlit-/IO-Abhaengigkeit). Der Tunnel-Modus
    (weltweit erreichbar) verlangt einen laengeren PIN als der reine WLAN-Modus."""
    p = (pin or "").strip()
    min_len = _PIN_TUNNEL_MIN_LENGTH if mode == "tunnel" else _PIN_MIN_LENGTH
    if len(p) < min_len:
        wo = "Tunnel" if mode == "tunnel" else "Netzwerk"
        return (f"Der PIN ist zu kurz - im {wo}-Modus sind mindestens {min_len} "
                "Zeichen noetig.")
    if len(set(p)) == 1:
        return "Der PIN besteht nur aus einem einzigen wiederholten Zeichen."
    if p.lower() in _TRIVIAL_PINS or _is_sequential_pin(p):
        return "Der PIN ist zu leicht zu erraten (z. B. 1234, 0000, 123456)."
    return None


def _pin_guard_read() -> dict:
    try:
        return json.loads(_PIN_GUARD_FILE.read_text("utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _pin_guard_remaining_lock() -> int:
    """Verbleibende Sperrzeit in Sekunden (0 = nicht gesperrt)."""
    lock_until = 0.0
    try:
        lock_until = float(_pin_guard_read().get("lock_until", 0) or 0)
    except (TypeError, ValueError):
        return 0
    rem = lock_until - time.time()
    return int(rem) + 1 if rem > 0 else 0


def _pin_guard_register_failure() -> None:
    """Fehlversuch zaehlen, ggf. sperren und kurz serverseitig verzoegern."""
    d = _pin_guard_read()
    try:
        fails = int(d.get("fails", 0) or 0) + 1
    except (TypeError, ValueError):
        fails = 1
    lock = _pin_lock_seconds(fails)
    d["fails"] = fails
    d["lock_until"] = (time.time() + lock) if lock > 0 else 0
    try:
        _PIN_GUARD_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PIN_GUARD_FILE.write_text(json.dumps(d), "utf-8")
    except Exception:  # noqa: BLE001
        pass
    try:
        time.sleep(_pin_fail_delay(fails))
    except Exception:  # noqa: BLE001
        pass


def _pin_guard_reset() -> None:
    try:
        _PIN_GUARD_FILE.unlink()
    except OSError:
        pass


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

    # Zugriff aktiv, aber der gesetzte PIN ist fuer den exponierten Betrieb zu schwach.
    # Serverseitig erzwingen (die Einstellungen-Seite kann das Setzen nicht garantiert
    # validieren): lieber den Zugriff verweigern als mit einem trivial erratbaren PIN
    # ins offene Netz / den Tunnel gehen. Im Tunnel-Modus ist der PIN die EINZIGE Barriere.
    weak = pin_weakness_reason(pin, mode)
    if weak:
        st.title("🔒 PIN zu schwach")
        st.error(weak)
        st.info("Setze am PC unter **⚙️ Einstellungen → 📱 Handy-Zugriff** einen "
                "laengeren, nicht erratbaren PIN (am besten Buchstaben **und** Zahlen). "
                "Gerade im Modus **Von überall** (Cloudflare) ist der PIN der einzige "
                "Schutz - die zufällige Web-Adresse ist KEIN Geheimnis.")
        st.stop()

    if st.session_state.get("_auth_ok"):
        return

    # Brute-Force-Sperre (serverseitig, sitzungsuebergreifend): nach zu vielen
    # Fehlversuchen wird fuer eine exponentiell wachsende Zeit gesperrt. Wird VOR der
    # Auswertung geprueft, damit eine aktive Sperre keinen weiteren Versuch zulaesst.
    locked = _pin_guard_remaining_lock()
    if locked > 0:
        st.title("🔒 Zu viele Fehlversuche")
        st.error(f"Zu viele falsche PIN-Eingaben. Bitte warte etwa {locked} Sekunden "
                 "und lade die Seite dann neu.")
        st.stop()

    st.title("🔒 RAG-Lernsystem")
    st.caption("Bitte gib den PIN ein, um fortzufahren.")
    # Formular: die Eingabe wird nur bei einem echten Absenden (Button/Enter) EINMAL
    # ausgewertet - nicht bei jedem Tastendruck-Rerun (sonst zaehlten Teil-Eingaben
    # eines langen PIN faelschlich als Fehlversuche).
    with st.form("_pin_form", clear_on_submit=True):
        entered = st.text_input("PIN", type="password", key="_pin_input")
        submitted = st.form_submit_button("Anmelden", type="primary")
    if submitted:
        if not entered:
            st.warning("Bitte gib den PIN ein.")
        # Timing-sicherer Vergleich (hmac.compare_digest statt ==). Als UTF-8-Bytes,
        # damit auch PINs mit Umlauten/Sonderzeichen funktionieren (compare_digest
        # wirft bei Nicht-ASCII-str sonst TypeError).
        elif hmac.compare_digest(str(entered).encode("utf-8"), pin.encode("utf-8")):
            _pin_guard_reset()
            st.session_state["_auth_ok"] = True
            st.rerun()
        else:
            _pin_guard_register_failure()
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
    # POSIX (Linux/macOS): nur die EIGENEN geladenen Modelle via API entladen
    # (keep_alive=0). Ein fremdes Modell - z. B. das einer zweiten, parallel
    # laufenden lokalen App auf demselben Ollama-Server - bleibt so unberuehrt (Ro5).
    try:
        from ragapp.scripts.stop_ollama_standby import unload_resident_models
        base = str(settings.OLLAMA_BASE_URL or "http://127.0.0.1:11434").rstrip("/")
        unload_resident_models(base)
    except Exception:  # noqa: BLE001
        pass


# Kleine Motivations-/Abschiedssprueche fuer die Erfolgsmeldung beim Beenden.
_ABSCHIED_SPRUECHE = [
    "Heute etwas geschafft – morgen wieder ein Stück näher an der Bestnote. 💪",
    "Pause gehört zum Lernen dazu. Komm frisch zurück – wir sind bereit! ✨",
    "Gut gemacht! Dein Wissen von heute wartet morgen geduldig auf dich. 📚",
    "Jede Sitzung zählt. Kopf hoch, Klausur im Blick – bis zum nächsten Mal! 🎯",
    "Dranbleiben lohnt sich. Wir sehen uns bald wieder! 🌟",
    "Schön war's – ruh dich aus, das Gelernte sacken lassen. Bis bald! 🌙",
]


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
            # 1) Grosses KI-Modell SOFORT entladen -> Grafikspeicher (VRAM) frei.
            _best_effort_stop_ollama()
            # 2) Server NICHT sofort stoppen! Sonst sieht der Nutzer im noch offenen
            #    Tab nur "Connection error" statt der Abschiedsmeldung. Stattdessen den
            #    Server beenden, SOBALD der Tab geschlossen ist (kein Verbindungsfehler).
            try:
                from ragapp.ui._shutdown_watchdog import arm_shutdown_on_tab_close
                arm_shutdown_on_tab_close()
            except Exception:  # noqa: BLE001
                pass
            st.session_state["_shutting_down"] = True

    if st.session_state.get("_shutting_down"):
        # Kleine, einmalige Feier-Animation zum Abschied.
        if not st.session_state.get("_bye_done"):
            st.session_state["_bye_done"] = True
            try:
                st.balloons()
            except Exception:  # noqa: BLE001
                pass
        # Spruch einmal fest waehlen (nicht bei jedem Rerun neu).
        if "_bye_spruch" not in st.session_state:
            st.session_state["_bye_spruch"] = random.choice(_ABSCHIED_SPRUECHE)
        st.markdown("## 👋 Bis bald – und gut gemacht!")
        st.info(f"💬 _{st.session_state['_bye_spruch']}_")
        st.success(
            "**Fertig für heute:**\n\n"
            "🧠 Das lokale KI-Modell (Ollama) wurde **entladen** – dein "
            "**Grafikspeicher (VRAM) ist wieder frei**.\n\n"
            "🔋 Es läuft keine KI-Berechnung mehr, dein System wird nicht belastet.")
        st.markdown("### 🪟 Schließe jetzt dieses Fenster/Tab.")
        st.caption("Sobald das Fenster zu ist, fährt die App automatisch komplett "
                   "herunter (der Server stoppt von selbst).")
        st.stop()
