"""
Netzwerk-Infos fuer den Handy-/Tablet-Zugriff
=============================================
Ermittelt die Adressen, unter denen die App im Netzwerk erreichbar ist
(lokales WLAN + Tailscale), und erzeugt QR-Codes zum Scannen mit dem Handy.

Der Netzwerkmodus wird ueber Umgebungsvariablen gesteuert, die der Starter
``Start_Handy-Zugriff.bat`` setzt:
    RAG_NETWORK=1          -> Netzwerk-/Handy-Zugriff aktiv (PIN-Sperre greift)
    RAG_BIND_HOST=0.0.0.0  -> Streamlit lauscht auf allen Schnittstellen
"""
from __future__ import annotations

import io
import os
import socket
import pathlib
import subprocess

# Dateien, die der Starter (ragapp.desktop) schreibt.
_TUNNEL_FILE = pathlib.Path(__file__).resolve().parent.parent / "data" / "tunnel_url.txt"
_MODE_FILE = pathlib.Path(__file__).resolve().parent.parent / "data" / ".mode"


def current_mode() -> str:
    """Aktueller Zugriffsmodus: 'local', 'network' oder 'tunnel'."""
    try:
        if _MODE_FILE.is_file():
            m = _MODE_FILE.read_text(encoding="utf-8").strip()
            if m in ("local", "network", "tunnel"):
                return m
    except Exception:
        pass
    # Fallback ueber Umgebungsvariablen (falls kein Starter das File schreibt)
    if os.environ.get("RAG_TUNNEL") == "1":
        return "tunnel"
    if is_network_mode():
        return "network"
    return "local"


def get_port() -> int:
    try:
        return int(os.environ.get("RAG_UI_PORT", "8501"))
    except ValueError:
        return 8501


def is_network_mode() -> bool:
    """True, wenn die App im Netzwerkmodus gestartet wurde (Start_Handy-Zugriff.bat)."""
    return os.environ.get("RAG_NETWORK") == "1"


def _primary_lan_ip() -> "str | None":
    """IP der aktiven Netzwerk-Schnittstelle (Routing-Trick, kein Datenverkehr)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        return None


def _all_ipv4() -> "list[str]":
    ips: set = set()
    try:
        for res in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(res[4][0])
    except Exception:
        pass
    p = _primary_lan_ip()
    if p:
        ips.add(p)
    return sorted(ips)


def _is_tailscale(ip: str) -> bool:
    # Tailscale nutzt den CGNAT-Bereich 100.64.0.0/10  (100.64.x - 100.127.x)
    if not ip.startswith("100."):
        return False
    try:
        return 64 <= int(ip.split(".")[1]) <= 127
    except Exception:
        return False


def _is_private_lan(ip: str) -> bool:
    if ip.startswith("192.168.") or ip.startswith("10."):
        return True
    if ip.startswith("172."):
        try:
            return 16 <= int(ip.split(".")[1]) <= 31
        except Exception:
            return False
    return False


def lan_ip() -> "str | None":
    """Beste lokale WLAN/LAN-IP (bevorzugt die aktive Schnittstelle)."""
    p = _primary_lan_ip()
    if p and _is_private_lan(p):
        return p
    for ip in _all_ipv4():
        if _is_private_lan(ip):
            return ip
    return p  # Fallback: aktive Schnittstelle, auch wenn nicht eindeutig privat


def tailscale_ip() -> "str | None":
    """Tailscale-IP (100.x), falls Tailscale installiert/aktiv ist, sonst None."""
    for exe in ("tailscale", r"C:\Program Files\Tailscale\tailscale.exe"):
        try:
            out = subprocess.run([exe, "ip", "-4"], capture_output=True,
                                 text=True, timeout=4)
            for line in (out.stdout or "").splitlines():
                line = line.strip()
                if _is_tailscale(line):
                    return line
        except Exception:
            continue
    for ip in _all_ipv4():
        if _is_tailscale(ip):
            return ip
    return None


def tunnel_url() -> "str | None":
    """Aktuelle Cloudflare-Tunnel-Adresse (von ragapp.desktop geschrieben) oder None."""
    try:
        if _TUNNEL_FILE.is_file():
            u = _TUNNEL_FILE.read_text(encoding="utf-8").strip()
            return u or None
    except Exception:
        pass
    return None


def access_targets() -> "list[dict]":
    """Erreichbare Adressen: Liste von {kind, label, ip, url}."""
    port = get_port()
    out: list = []
    lan = lan_ip()
    if lan:
        out.append({"kind": "lan", "label": "Im selben WLAN",
                    "ip": lan, "url": f"http://{lan}:{port}"})
    tu = tunnel_url()
    if tu:
        out.append({"kind": "tunnel", "label": "Von überall (Cloudflare)",
                    "ip": "", "url": tu})
    ts = tailscale_ip()
    if ts:
        out.append({"kind": "tailscale", "label": "Von überall (Tailscale)",
                    "ip": ts, "url": f"http://{ts}:{port}"})
    return out


def qr_png_bytes(data: str) -> "bytes | None":
    """QR-Code als PNG-Bytes (nutzt 'qrcode' + das ueber Streamlit vorhandene
    Pillow). Gibt None zurueck, wenn die Bibliothek fehlt."""
    try:
        import qrcode
        img = qrcode.make(data)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None
