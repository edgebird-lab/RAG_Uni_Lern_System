#!/usr/bin/env python3
"""Ollama-Standby beenden: alle aktuell geladenen Modelle entladen (keep_alive=0).

Gibt sofort RAM/VRAM frei, OHNE den Ollama-Dienst selbst zu stoppen. Damit bleibt
der (per systemd verwaltete) Server und jeder andere Nutzer (z. B. local-agent)
unberuehrt - ein Neustart des Dienstes braeuchte Root, das Entladen des Modells
nicht. Reines stdlib, damit es aus start.sh/stop.sh mit dem venv-Python laeuft.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request


def _base_url() -> str:
    for var in ("OLLAMA_BASE_URL", "OLLAMA_HOST", "OLLAMA_API_BASE"):
        v = (os.environ.get(var) or "").strip()
        if v:
            if not v.startswith("http"):
                v = "http://" + v
            return v.rstrip("/")
    return "http://127.0.0.1:11434"


def unload_resident_models(base_url: "str | None" = None) -> int:
    """Entlaedt jedes in /api/ps gemeldete Modell. Gibt die Anzahl zurueck."""
    base = (base_url or _base_url()).rstrip("/")
    try:
        with urllib.request.urlopen(base + "/api/ps", timeout=3.0) as resp:
            ps = json.loads(resp.read().decode("utf-8") or "{}")
    except Exception:  # noqa: BLE001 - Server nicht erreichbar -> nichts zu tun
        return 0
    names = [m.get("model") or m.get("name") for m in ps.get("models", [])]
    unloaded = 0
    for name in [n for n in names if n]:
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
    print(f"[stop] Ollama: {n} Modell(e) entladen."
          if n else "[stop] Ollama: kein Modell geladen.")
    sys.exit(0)
