"""
Hardware-Erkennung & Modell-Empfehlung (plattformübergreifend)
==============================================================

Erkennt Betriebssystem, CPU, RAM und, am wichtigsten, die **GPU** (Hersteller,
Name, VRAM), um daraus die passende **Ollama-Variante** und ein **passendes
LLM** abzuleiten. Grundlage für den plattformübergreifenden One-Click-Installer
und den ``recommend``-Befehl.

Unterstützte Kombinationen:
    * NVIDIA (Windows/Linux)  -> Standard-Ollama (CUDA, automatisch)
    * AMD (Linux, teils Win)  -> Standard-Ollama (ROCm/Vulkan)
    * Intel (Arc/iGPU)        -> IPEX-LLM-Ollama (SYCL)  [Sonderweg]
    * Apple Silicon           -> Standard-Ollama (Metal)
    * nur CPU                 -> Standard-Ollama (CPU)

Alles best-effort und robust: Fehlt ein Tool, wird sauber zurückgefallen statt
abzustürzen.
"""
from __future__ import annotations

import platform
import shutil
import subprocess


def _run(cmd: list[str], timeout: int = 15) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout, errors="replace").stdout or ""
    except Exception:
        return ""


def _ram_gb() -> float | None:
    try:
        import psutil
        return round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception:
        return None


def _cpu_name() -> str:
    system = platform.system()
    try:
        if system == "Windows":
            out = _run(["powershell", "-NoProfile", "-Command",
                        "(Get-CimInstance Win32_Processor).Name"])
            if out.strip():
                return out.strip().splitlines()[0].strip()
        elif system == "Linux":
            out = _run(["bash", "-c", "grep -m1 'model name' /proc/cpuinfo | cut -d: -f2"])
            if out.strip():
                return out.strip()
        elif system == "Darwin":
            out = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
            if out.strip():
                return out.strip()
    except Exception:
        pass
    return platform.processor() or platform.machine() or "Unbekannte CPU"


# --------------------------------------------------------------------------- #
# GPU-Erkennung
# --------------------------------------------------------------------------- #
def _detect_nvidia() -> dict | None:
    if not shutil.which("nvidia-smi"):
        return None
    out = _run(["nvidia-smi", "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits"])
    line = next((l for l in out.splitlines() if l.strip()), "")
    if not line:
        return None
    parts = [p.strip() for p in line.split(",")]
    name = parts[0] if parts else "NVIDIA GPU"
    vram = None
    if len(parts) > 1:
        try:
            vram = round(int(float(parts[1])) / 1024, 1)  # MiB -> GiB
        except Exception:
            vram = None
    return {"vendor": "nvidia", "name": name, "vram_gb": vram}


def _video_controller_names() -> list[str]:
    system = platform.system()
    if system == "Windows":
        out = _run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_VideoController | "
                    "Select-Object -ExpandProperty Name"])
        return [l.strip() for l in out.splitlines() if l.strip()]
    if system == "Linux":
        out = _run(["bash", "-c", "lspci 2>/dev/null | grep -Ei 'vga|3d|display'"])
        return [l.strip() for l in out.splitlines() if l.strip()]
    if system == "Darwin":
        out = _run(["system_profiler", "SPDisplaysDataType"])
        return [l.strip() for l in out.splitlines() if "Chipset" in l or "Vendor" in l]
    return []


def detect_gpu() -> dict:
    """Erkennt die primäre GPU. Rückgabe: {vendor, name, vram_gb, is_igpu}."""
    nv = _detect_nvidia()
    if nv:
        nv["is_igpu"] = False
        return nv

    system = platform.system()
    if system == "Darwin" and platform.machine() == "arm64":
        return {"vendor": "apple", "name": "Apple Silicon (Metal)",
                "vram_gb": None, "is_igpu": True}

    names = _video_controller_names()
    joined = " ".join(names).lower()

    if "nvidia" in joined or "geforce" in joined or "rtx" in joined:
        return {"vendor": "nvidia", "name": names[0] if names else "NVIDIA GPU",
                "vram_gb": None, "is_igpu": False}
    if "amd" in joined or "radeon" in joined:
        return {"vendor": "amd", "name": next((n for n in names if "amd" in n.lower()
                or "radeon" in n.lower()), "AMD GPU"),
                "vram_gb": None, "is_igpu": "vega" in joined or "graphics" in joined}
    if "intel" in joined:
        name = next((n for n in names if "intel" in n.lower()), "Intel GPU")
        is_arc = "arc" in joined
        return {"vendor": "intel", "name": name, "vram_gb": None,
                "is_igpu": True, "is_arc": is_arc}
    return {"vendor": "none", "name": "(keine unterstützte GPU erkannt)",
            "vram_gb": None, "is_igpu": False}


def detect_hardware() -> dict:
    gpu = detect_gpu()
    variant = "ipex-llm" if gpu["vendor"] == "intel" else "standard"
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "cpu": _cpu_name(),
        "ram_gb": _ram_gb(),
        "gpu": gpu,
        "ollama_variant": variant,
        "gpu_accelerated": gpu["vendor"] in ("nvidia", "amd", "intel", "apple"),
    }


# --------------------------------------------------------------------------- #
# Modell-Empfehlung
# --------------------------------------------------------------------------- #
# Deutsch-taugliche Modelle nach Größe. Jeweils (Ollama-Tag, Params, ~GB).
_MODELS = {
    "small": {"tag": "gemma3:4b", "params": "4B", "gb": 3.3},
    "small_fast": {"tag": "qwen2.5:3b-instruct", "params": "3B", "gb": 1.9},
    "mid": {"tag": "qwen2.5:7b-instruct", "params": "7B", "gb": 4.7},
    "large": {"tag": "gemma3:12b", "params": "12B", "gb": 8.1},
}


def recommend_models(hw: dict) -> dict:
    """Empfiehlt anhand der Hardware geeignete Modelle (bestes zuerst)."""
    gpu = hw["gpu"]
    vendor = gpu["vendor"]
    vram = gpu.get("vram_gb")
    ram = hw.get("ram_gb") or 8

    # Intel iGPU über IPEX-LLM (Ollama 0.9.3): neuere Architekturen (Gemma 4,
    # gemma3n) laden NICHT auf dem SYCL-Backend -> bewährte kleine Modelle.
    if vendor == "intel":
        return {
            "reason": "Intel-GPU via IPEX-LLM (Ollama 0.9.3): bewährte, kompatible "
                      "3 bis 4B-Modelle. Größere/neuere Architekturen laden dort nicht.",
            "embed_model": "bge-m3",
            "models": [
                {**_MODELS["small"], "why": "läuft stabil auf Intel-Arc, gutes Deutsch, ~13 tok/s"},
                {**_MODELS["small_fast"], "why": "schneller (~19 tok/s), etwas schwächer"},
            ],
        }

    # "Budget" in GB: dedizierte VRAM, sonst grob RAM/2 (CPU teilt sich RAM).
    if vendor in ("nvidia", "amd") and vram:
        budget = vram
        on = "GPU"
    elif vendor == "apple":
        budget = (ram or 8) * 0.6  # Apple: unified memory, viel nutzbar
        on = "GPU (Metal)"
    else:  # CPU only oder unbekannte VRAM
        budget = (ram or 8) / 2
        on = "CPU" if vendor == "none" else "GPU"

    if budget >= 15:
        picks = [{**_MODELS["large"], "why": f"bestes Deutsch, passt in ~{budget:.0f} GB"},
                 {**_MODELS["mid"], "why": "sehr gut + schneller"}]
        tier = "groß"
    elif budget >= 7:
        picks = [{**_MODELS["mid"], "why": f"starke Instruktionstreue, passt in ~{budget:.0f} GB"},
                 {**_MODELS["small"], "why": "schneller Fallback, gutes Deutsch"}]
        tier = "mittel"
    else:
        picks = [{**_MODELS["small"], "why": "gutes Deutsch bei kleiner Größe"},
                 {**_MODELS["small_fast"], "why": "am schnellsten"}]
        tier = "klein"

    note = ""
    if vendor == "none":
        note = " (Nur-CPU: Antworten dauern deutlich länger, kleines Modell empfohlen.)"

    return {
        "reason": f"{on}, verfügbares Budget ~{budget:.0f} GB -> Modellklasse '{tier}'.{note}",
        "embed_model": "bge-m3",
        "models": picks,
    }


def speed_verdict(tps: float) -> str:
    if tps >= 15:
        return "schnell (Antworten deutlich unter 30 s)"
    if tps >= 8:
        return "brauchbar (~30 bis 60 s pro Antwort)"
    if tps >= 4:
        return "langsam (~1 bis 2 Min pro Antwort)"
    return "sehr langsam (Antworten dauern minutenlang)"


def benchmark_model(tag: str, base_url: str | None = None,
                    num_predict: int = 120, pull_if_missing: bool = True,
                    progress=None) -> dict:
    """Lädt (falls nötig) ein Modell und misst die echte Tokens/Sekunde."""
    import time
    import ollama
    from ragapp.config import settings

    client = ollama.Client(host=base_url or settings.OLLAMA_BASE_URL,
                           timeout=settings.LLM_TIMEOUT)

    # Modell vorhanden?
    try:
        have = any(tag.split(":")[0] in m.get("model", "")
                   for m in client.list().get("models", []))
    except Exception as exc:
        return {"tag": tag, "error": f"Ollama nicht erreichbar: {exc}"}
    if not have:
        if not pull_if_missing:
            return {"tag": tag, "error": "Modell nicht vorhanden"}
        if progress:
            progress(f"Lade Modell {tag} herunter …")
        try:
            client.pull(tag)
        except Exception as exc:
            return {"tag": tag, "error": f"Download/Load fehlgeschlagen: {exc}"}

    prompt = "Erkläre in 3 bis 4 Sätzen auf Deutsch, was ein Deckungsbeitrag ist."
    opts = {"num_predict": num_predict, "temperature": 0.1}
    try:
        if progress:
            progress(f"Teste {tag} (lädt auf die GPU/CPU) …")
        t0 = time.time()
        client.generate(model=tag, prompt=prompt, options=opts, stream=False)
        cold = time.time() - t0
        if progress:
            progress(f"Messe {tag} (warm) …")
        t0 = time.time()
        r2 = client.generate(model=tag, prompt=prompt, options=opts, stream=False)
        warm = time.time() - t0
    except Exception as exc:
        return {"tag": tag, "error": f"Generierung fehlgeschlagen: {exc}"}

    ev_count = r2.get("eval_count", 0) or 0
    ev_dur = r2.get("eval_duration", 0) or 0
    tps = round(ev_count / (ev_dur / 1e9), 1) if ev_dur else 0.0
    return {"tag": tag, "cold_s": round(cold, 1), "warm_s": round(warm, 1),
            "tokens_per_s": tps, "tokens": ev_count, "verdict": speed_verdict(tps)}


def format_hardware(hw: dict) -> str:
    g = hw["gpu"]
    vram = f"{g['vram_gb']} GB VRAM" if g.get("vram_gb") else "VRAM unbekannt/shared"
    return (f"OS: {hw['os']} {hw.get('os_release','')}\n"
            f"CPU: {hw['cpu']}\n"
            f"RAM: {hw.get('ram_gb','?')} GB\n"
            f"GPU: {g['name']}  [{g['vendor']}, {vram}]\n"
            f"Ollama-Variante: {hw['ollama_variant']}"
            + ("  (Intel -> IPEX-LLM)" if hw['ollama_variant'] == 'ipex-llm' else ""))
