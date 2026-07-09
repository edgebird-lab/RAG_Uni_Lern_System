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
# LLM-Katalog: deutsch-taugliche Modelle fuer Standard-Ollama (NVIDIA/AMD/Apple/CPU).
# "gb" = grober Speicherbedarf in Q4-Quantisierung (Richtwert). "denk" = Denk-/
# Reasoning-Modell (sehr gut fuer schwere Logik, aber langsamer; laeuft in der App
# ohne sichtbare Gedankengaenge, da think=False gesetzt ist).
_LLM: dict[str, dict] = {
    "gemma3:4b":         {"params": "4B",  "gb": 3.3,  "fam": "Gemma 3",     "info": "starkes Deutsch, kompakt"},
    "qwen3:4b":          {"params": "4B",  "gb": 2.6,  "fam": "Qwen3",       "info": "sehr kompakt, aktuell"},
    "mistral:7b":        {"params": "7B",  "gb": 4.4,  "fam": "Mistral",     "info": "schnell, ordentliches Deutsch"},
    "llama3.1:8b":       {"params": "8B",  "gb": 4.9,  "fam": "Llama 3.1",   "info": "solider Allrounder"},
    "qwen3:8b":          {"params": "8B",  "gb": 5.2,  "fam": "Qwen3",       "info": "schnell und stark"},
    "mistral-nemo:12b":  {"params": "12B", "gb": 7.1,  "fam": "Mistral",     "info": "gut mehrsprachig"},
    "gemma3:12b":        {"params": "12B", "gb": 8.1,  "fam": "Gemma 3",     "info": "exzellentes Deutsch"},
    "deepseek-r1:14b":   {"params": "14B", "gb": 9.0,  "fam": "DeepSeek-R1", "info": "Denk-Modell, top Logik", "denk": True},
    "phi4:14b":          {"params": "14B", "gb": 9.1,  "fam": "Phi-4",       "info": "stark in Logik & Mathe"},
    "qwen3:14b":         {"params": "14B", "gb": 9.3,  "fam": "Qwen3",       "info": "sehr stark, aktuell"},
    "mistral-small:24b": {"params": "24B", "gb": 14.0, "fam": "Mistral",     "info": "stark und effizient"},
    "gemma3:27b":        {"params": "27B", "gb": 17.0, "fam": "Gemma 3",     "info": "Spitzen-Deutsch, Top-Qualität"},
    "qwen3:30b":         {"params": "30B (MoE, 3B aktiv)", "gb": 19.0, "fam": "Qwen3", "info": "sehr schnell für die Größe"},
    "qwen3:32b":         {"params": "32B", "gb": 20.0, "fam": "Qwen3",       "info": "sehr stark (dicht)"},
    "deepseek-r1:32b":   {"params": "32B", "gb": 20.0, "fam": "DeepSeek-R1", "info": "Spitzen-Logik, Denk-Modell", "denk": True},
}

# Reihenfolge grob nach Qualitaet fuer deutsches RAG (bestes zuerst). Aus dieser
# Liste werden fuer eine Hardware die groessten noch passenden Modelle vorgeschlagen.
_LLM_ORDER = [
    "gemma3:27b", "qwen3:32b", "deepseek-r1:32b", "qwen3:30b", "mistral-small:24b",
    "gemma3:12b", "qwen3:14b", "phi4:14b", "deepseek-r1:14b", "mistral-nemo:12b",
    "qwen3:8b", "llama3.1:8b", "mistral:7b",
    "gemma3:4b", "qwen3:4b",
]

# Intel-IPEX (altes SYCL-Backend, Ollama 0.9.3): neuere Architekturen laden dort
# nicht -> bewaehrte kleine Modelle.
_INTEL = {
    "gemma3:4b":           {"params": "4B", "gb": 3.3, "info": "läuft stabil auf Intel-Arc, gutes Deutsch, ~13 tok/s"},
    "qwen2.5:3b-instruct": {"params": "3B", "gb": 1.9, "info": "schneller (~19 tok/s), etwas schwächer"},
}

# Embedding-Modelle (Ollama). ACHTUNG: Ein Wechsel aendert die Vektor-Dimension und
# erfordert einen NEU-IMPORT aller Dokumente. bge-m3 ist die beste Wahl fuer Deutsch.
EMBED_MODELS = [
    {"tag": "bge-m3",                  "info": "★ Empfohlen – multilingual, sehr gut für Deutsch (1024-dim)"},
    {"tag": "mxbai-embed-large",      "info": "stark, eher englischlastig (1024-dim)"},
    {"tag": "snowflake-arctic-embed2", "info": "multilingual (1024-dim)"},
    {"tag": "nomic-embed-text",       "info": "kompakt & schnell (768-dim)"},
]

# Reranker (HuggingFace Cross-Encoder; laedt beim ersten Benutzen automatisch).
RERANKER_MODELS = [
    {"tag": "BAAI/bge-reranker-v2-m3",                   "info": "★ Empfohlen – multilingual, sehr genau"},
    {"tag": "BAAI/bge-reranker-base",                    "info": "kleiner & schneller, englischlastig"},
    {"tag": "jinaai/jina-reranker-v2-base-multilingual", "info": "multilingual, schnell"},
]


def recommend_models(hw: dict) -> dict:
    """Empfiehlt anhand der Hardware geeignete Antwort-Modelle (bestes zuerst).
    Gibt bis zu 5 Vorschlaege aus verschiedenen Familien zurueck."""
    gpu = hw["gpu"]
    vendor = gpu["vendor"]
    vram = gpu.get("vram_gb")
    ram = hw.get("ram_gb") or 8

    if vendor == "intel":
        return {
            "reason": "Intel-GPU via IPEX-LLM (Ollama 0.9.3): bewährte, kompatible 3–4B-"
                      "Modelle. Neuere Architekturen (Qwen3, Gemma 4, DeepSeek) laden auf "
                      "diesem alten SYCL-Backend leider nicht.",
            "embed_model": "bge-m3",
            "budget_gb": None,
            "models": [
                {"tag": "gemma3:4b", "fam": "Gemma 3", "denk": False, **_INTEL["gemma3:4b"],
                 "why": _INTEL["gemma3:4b"]["info"]},
                {"tag": "qwen2.5:3b-instruct", "fam": "Qwen2.5", "denk": False,
                 **_INTEL["qwen2.5:3b-instruct"], "why": _INTEL["qwen2.5:3b-instruct"]["info"]},
            ],
        }

    # "Budget" in GB: dedizierte VRAM, sonst grob RAM/2 (CPU teilt sich das RAM).
    if vendor in ("nvidia", "amd") and vram:
        budget, on = vram, "GPU"
    elif vendor in ("nvidia", "amd"):
        budget, on = 8.0, "GPU"   # dedizierte GPU, VRAM unbekannt -> min. 7B-Klasse
    elif vendor == "apple":
        budget, on = (ram or 8) * 0.6, "GPU (Metal)"
    else:
        budget, on = (ram or 8) / 2, "CPU"

    picks: list[dict] = []
    for tag in _LLM_ORDER:
        m = _LLM[tag]
        if m["gb"] <= budget + 2.0:          # +2 GB Toleranz: leichtes Offload ins RAM ist ok
            if on.startswith("GPU"):
                lauf = ("läuft komplett auf der GPU" if m["gb"] <= budget
                        else "läuft teils über RAM (etwas langsamer)")
                why = f"{m['info']} · {lauf}"
            else:
                why = m["info"]
            picks.append({"tag": tag, "params": m["params"], "gb": m["gb"],
                          "fam": m["fam"], "denk": m.get("denk", False), "why": why})
        if len(picks) >= 5:
            break

    if not picks:  # extrem wenig Speicher -> kleinstes Modell
        m = _LLM["qwen3:4b"]
        picks = [{"tag": "qwen3:4b", "params": m["params"], "gb": m["gb"],
                  "fam": m["fam"], "denk": False, "why": m["info"]}]

    note = " (Nur-CPU: Antworten dauern länger, kleineres Modell empfohlen.)" if vendor == "none" else ""
    return {
        "reason": f"{on}, verfügbares Budget ~{budget:.0f} GB.{note} Gezeigt werden die "
                  "stärksten Modelle, die dabei noch flüssig laufen (bestes zuerst).",
        "embed_model": "bge-m3",
        "budget_gb": round(budget, 1),
        "models": picks,
    }


def llm_size_gb(tag: str) -> "float | None":
    """Grober Speicherbedarf (GB) eines bekannten Katalog-Modells, sonst None."""
    m = _LLM.get(tag) or _INTEL.get(tag)
    return m.get("gb") if m else None


def is_model_installed(tag: str, installed: "list[str] | None") -> bool:
    """True, wenn das Ollama-Modell lokal vorhanden ist (exakter Tag; ohne Version
    zaehlt jede vorhandene Version)."""
    if not installed:
        return False
    names = set(installed)
    if tag in names or f"{tag}:latest" in names:
        return True
    if ":" not in tag:
        return any(n.split(":")[0] == tag for n in names)
    return False


def pull_model_stream(tag: str, base_url: "str | None" = None):
    """Generator: laedt ein Ollama-Modell herunter und liefert den Fortschritt als
    Tupel (status_text, fraction|None, done_bytes|None, total_bytes|None). Blockiert
    bis zum Ende bzw. bis eine Exception fliegt (z. B. Modell/Netz nicht verfuegbar)."""
    import ollama
    from ragapp.config import settings

    client = ollama.Client(host=base_url or settings.OLLAMA_BASE_URL, timeout=None)
    for ev in client.pull(tag, stream=True):
        if isinstance(ev, dict):
            status, total, done = ev.get("status"), ev.get("total"), ev.get("completed")
        else:
            status = getattr(ev, "status", None)
            total = getattr(ev, "total", None)
            done = getattr(ev, "completed", None)
        frac = (done / total) if (total and done) else None
        yield str(status or ""), frac, done, total


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
