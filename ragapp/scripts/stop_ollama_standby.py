#!/usr/bin/env python3
"""Ollama-Standby beenden: die von DIESER App genutzten Modelle entladen (keep_alive=0).

Gibt sofort RAM/VRAM frei, OHNE den Ollama-Dienst selbst zu stoppen. Damit bleibt
der (per systemd verwaltete) Server und jeder andere Nutzer (z. B. local-agent)
unberuehrt - ein Neustart des Dienstes braeuchte Root, das Entladen des Modells
nicht. Reines stdlib, damit es aus start.sh/stop.sh mit dem venv-Python laeuft.

WICHTIG (Ro5): Es werden AUSSCHLIESSLICH die eigenen Modelle entladen (Antwort-LLM,
schnelles Hilfs-LLM, Autoren-LLM, Embedder, OCR-Vision aus der eigenen Config). Ein
fremdes Modell - etwa das einer zweiten, parallel laufenden lokalen App auf demselben
Ollama-Server - bleibt garantiert unberuehrt. Frueher wurde pauschal ALLES entladen.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.request

# Config-Schluessel, unter denen DIESE App ihre Ollama-Modelle fuehrt.
_OWN_MODEL_KEYS = (
    "LLM_MODEL", "LLM_MODEL_FAST", "LLM_MODEL_AUTHOR",
    "EMBED_MODEL", "OCR_VISION_MODEL",
)
# Fallback-Standardnamen (falls weder Settings-Import noch config.json lesbar sind).
_DEFAULT_OWN_MODELS = ("gemma3:4b", "bge-m3")


def _base_url() -> str:
    for var in ("OLLAMA_BASE_URL", "OLLAMA_HOST", "OLLAMA_API_BASE"):
        v = (os.environ.get(var) or "").strip()
        if v:
            if not v.startswith("http"):
                v = "http://" + v
            return v.rstrip("/")
    return "http://127.0.0.1:11434"


def _own_model_names() -> "set[str]":
    """Namen der Modelle, die DIESE App in Ollama laedt. Bevorzugt die echten
    Settings (Defaults + data/config.json-Overrides); scheitert deren Import,
    werden die Overrides direkt aus data/config.json plus eingebaute Standardnamen
    genutzt. So werden bei einem Import-Problem NICHT versehentlich fremde Modelle
    entladen (im Zweifel lieber zu wenig als ein fremdes)."""
    names: "set[str]" = set()
    root = pathlib.Path(__file__).resolve().parents[2]
    # 1) Bevorzugt: echte Settings (Defaults + Overrides zusammengefuehrt).
    try:
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from ragapp.config import settings as _s  # eigene, stdlib-basierte Config
        for key in _OWN_MODEL_KEYS:
            val = getattr(_s, key, "") or ""
            if str(val).strip():
                names.add(str(val).strip())
    except Exception:  # noqa: BLE001 - Import darf das Entladen nie ganz verhindern
        pass
    # 2) Fallback (Import gescheitert): Overrides direkt lesen + Standardnamen.
    if not names:
        try:
            cfg = root / "data" / "config.json"
            if cfg.is_file():
                data = json.loads(cfg.read_text("utf-8") or "{}")
                for key in _OWN_MODEL_KEYS:
                    val = data.get(key) or ""
                    if str(val).strip():
                        names.add(str(val).strip())
        except Exception:  # noqa: BLE001
            pass
        for n in _DEFAULT_OWN_MODELS:
            names.add(n)
    return names


def _norm_model(name: str) -> str:
    """Kleinschreibung + optionales ':latest' entfernen, damit z. B. 'bge-m3' und
    'bge-m3:latest' als dasselbe Modell gelten."""
    n = (name or "").strip().lower()
    if n.endswith(":latest"):
        n = n[: -len(":latest")]
    return n


def _is_own_model(ps_name: str, own_norm: "set[str]") -> bool:
    """True, wenn das in Ollama geladene Modell zu unserer Menge gehoert. Toleriert
    Tags: ein konfigurierter Name OHNE Tag (z. B. 'bge-m3') deckt jede Tag-Variante
    ab; ein Name MIT Tag (z. B. 'gemma3:4b') muss exakt passen."""
    pn = _norm_model(ps_name)
    if not pn:
        return False
    if pn in own_norm:
        return True
    base = pn.split(":", 1)[0]
    for own in own_norm:
        if ":" not in own and own == base:
            return True
    return False


def unload_resident_models(base_url: "str | None" = None) -> int:
    """Entlaedt jedes in /api/ps gemeldete EIGENE Modell (Ro5: fremde Modelle
    bleiben unberuehrt). Gibt die Anzahl der entladenen Modelle zurueck."""
    base = (base_url or _base_url()).rstrip("/")
    try:
        with urllib.request.urlopen(base + "/api/ps", timeout=3.0) as resp:
            ps = json.loads(resp.read().decode("utf-8") or "{}")
    except Exception:  # noqa: BLE001 - Server nicht erreichbar -> nichts zu tun
        return 0
    own_norm = {_norm_model(n) for n in _own_model_names()}
    own_norm.discard("")
    names = [m.get("model") or m.get("name") for m in ps.get("models", [])]
    unloaded = 0
    for name in [n for n in names if n]:
        # Nur eigene Modelle anfassen - ein fremdes (z. B. einer zweiten lokalen App)
        # ueberspringen, damit dessen Speicher/Modell NICHT entladen wird.
        if not _is_own_model(name, own_norm):
            continue
        # Leere Anfrage + keep_alive:0 -> Ollama entlaedt das Modell sofort.
        payload = json.dumps({"model": name, "keep_alive": 0}).encode("utf-8")
        req = urllib.request.Request(
            base + "/api/generate", data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                resp.read()
            unloaded += 1
        except Exception:  # noqa: BLE001
            pass
    return unloaded


if __name__ == "__main__":
    n = unload_resident_models()
    print(f"[stop] Ollama: {n} eigene(s) Modell(e) entladen."
          if n else "[stop] Ollama: kein eigenes Modell geladen.")
    sys.exit(0)
