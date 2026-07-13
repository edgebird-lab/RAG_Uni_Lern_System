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

import glob
import os
import platform
import shutil
import subprocess


def _no_window_flag() -> int:
    """CREATE_NO_WINDOW unter Windows - sonst blitzt bei jedem Shell-Aufruf (z. B.
    beim Oeffnen der Einstellungen: CPU/GPU-Erkennung, ollama-Abfragen) kurz ein
    Terminalfenster auf."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _run(cmd: list[str], timeout: int = 15) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout, errors="replace",
                              creationflags=_no_window_flag()).stdout or ""
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


def _detect_vram_gb() -> "float | None":
    """Ermittelt den echten VRAM (GB) der primaeren GPU - wichtig, damit die
    Modellwahl ein Modell nimmt, das WIRKLICH ganz auf die GPU passt (sonst
    CPU-Auslagerung -> zaehe Antworten). Best-effort ueber sysfs/rocm-smi (Linux)
    bzw. Registry (Windows). None, wenn nicht ermittelbar."""
    system = platform.system()
    _MIN = 512 * 1024 * 1024
    try:
        if system == "Linux":
            # (a) amdgpu-sysfs: mem_info_vram_total in Bytes (ohne Zusatz-Tools)
            out = _run(["bash", "-c",
                        "cat /sys/class/drm/card*/device/mem_info_vram_total 2>/dev/null "
                        "| sort -rn | head -1"])
            d = "".join(ch for ch in out if ch.isdigit())
            if d and int(d) > _MIN:
                return round(int(d) / (1024 ** 3), 1)
            # (b) rocm-smi (AMD)
            out = _run(["bash", "-c", "rocm-smi --showmeminfo vram 2>/dev/null "
                        "| grep -i 'total memory' | grep -oE '[0-9]{6,}' | head -1"])
            d = out.strip()
            if d.isdigit() and int(d) > _MIN:
                return round(int(d) / (1024 ** 3), 1)
        elif system == "Windows":
            # Registry qwMemorySize = echter VRAM (AdapterRAM ist bei >4 GB abgeschnitten)
            out = _run(["powershell", "-NoProfile", "-Command",
                        "Get-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Class\\"
                        "{4d36e968-e325-11ce-bfc1-08002be10318}\\*' -ErrorAction SilentlyContinue "
                        "| ForEach-Object { $_.'HardwareInformation.qwMemorySize' } "
                        "| Where-Object { $_ } | Sort-Object -Descending | Select-Object -First 1"])
            d = "".join(ch for ch in out if ch.isdigit())
            if d and int(d) > _MIN:
                return round(int(d) / (1024 ** 3), 1)
    except Exception:  # noqa: BLE001
        pass
    return None


def vram_free_gb() -> "float | None":
    """FREIER VRAM (GB) der primaeren GPU = total - used. Best-effort ueber
    nvidia-smi (NVIDIA) bzw. amdgpu-sysfs/rocm-smi (AMD, Linux). None, wenn nicht
    ermittelbar (dann KEIN Pre-Flight-Block). Wichtig, um VOR der ersten Frage zu
    erkennen, dass zu wenig frei ist (z. B. eine zweite GPU-App laeuft) - sonst
    laedt Ollama das Modell zaeh auf die CPU."""
    system = platform.system()
    _MIN = 256 * 1024 * 1024
    try:
        # NVIDIA (Linux + Windows): direkt der freie Wert.
        if shutil.which("nvidia-smi"):
            out = _run(["nvidia-smi", "--query-gpu=memory.free",
                        "--format=csv,noheader,nounits"])
            for line in out.splitlines():
                v = "".join(ch for ch in line if ch.isdigit())
                if v:
                    return round(int(v) / 1024, 1)   # MiB -> GiB
        if system == "Linux":
            # (a) amdgpu-sysfs: total - used aus DERSELBEN (groessten) Karte.
            best = None  # (total, used)
            for total_path in glob.glob("/sys/class/drm/card*/device/mem_info_vram_total"):
                try:
                    total = int(open(total_path, encoding="utf-8").read().strip())
                    used = int(open(total_path.replace("mem_info_vram_total",
                                                       "mem_info_vram_used"),
                                    encoding="utf-8").read().strip())
                except Exception:  # noqa: BLE001
                    continue
                if total > _MIN and (best is None or total > best[0]):
                    best = (total, used)
            if best:
                return round((best[0] - best[1]) / (1024 ** 3), 1)
            # (b) rocm-smi (AMD): 'Total Memory' und 'Total Used Memory'.
            total = _run(["bash", "-c", "rocm-smi --showmeminfo vram 2>/dev/null "
                          "| grep -i 'total memory' | grep -oE '[0-9]{6,}' | head -1"]).strip()
            used = _run(["bash", "-c", "rocm-smi --showmeminfo vram 2>/dev/null "
                         "| grep -i 'used memory' | grep -oE '[0-9]{6,}' | head -1"]).strip()
            if total.isdigit() and used.isdigit() and int(total) > _MIN:
                return round((int(total) - int(used)) / (1024 ** 3), 1)
        # Windows/AMD ohne Zusatztools: kein einfacher freier-VRAM-Wert -> None.
    except Exception:  # noqa: BLE001
        pass
    return None


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
                "vram_gb": _detect_vram_gb(), "is_igpu": False}
    if "amd" in joined or "radeon" in joined:
        return {"vendor": "amd", "name": next((n for n in names if "amd" in n.lower()
                or "radeon" in n.lower()), "AMD GPU"),
                "vram_gb": _detect_vram_gb(),
                "is_igpu": "vega" in joined or "graphics" in joined}
    if "intel" in joined:
        name = next((n for n in names if "intel" in n.lower()), "Intel GPU")
        is_arc = "arc" in joined
        return {"vendor": "intel", "name": name, "vram_gb": _detect_vram_gb() if is_arc else None,
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
# Tags + Groessen wurden im Juli 2026 direkt gegen ollama.com/library verifiziert.
_LLM: dict[str, dict] = {
    # --- klein (~2-5 GB) --------------------------------------------------- #
    "qwen3:4b":          {"params": "4B",  "gb": 2.6, "fam": "Qwen3",       "info": "sehr kompakt, aktuell"},
    "gemma3:4b":         {"params": "4B",  "gb": 3.3, "fam": "Gemma 3",     "info": "starkes Deutsch, kompakt"},
    "mistral:7b":        {"params": "7B",  "gb": 4.4, "fam": "Mistral",     "info": "schnell, ordentliches Deutsch"},
    "llama3.1:8b":       {"params": "8B",  "gb": 4.9, "fam": "Llama 3.1",   "info": "solider Allrounder"},
    "deepseek-r1:8b":    {"params": "8B",  "gb": 5.2, "fam": "DeepSeek-R1", "info": "Denk-Modell (R1-0528), schlank", "denk": True},
    "qwen3:8b":          {"params": "8B",  "gb": 5.2, "fam": "Qwen3",       "info": "schnell und stark"},
    # --- mittel (~7-10 GB) ------------------------------------------------- #
    "mistral-nemo:12b":  {"params": "12B", "gb": 7.1, "fam": "Mistral",     "info": "gut mehrsprachig"},
    "gemma3:12b":        {"params": "12B", "gb": 8.1, "fam": "Gemma 3",     "info": "exzellentes Deutsch"},
    "deepseek-r1:14b":   {"params": "14B", "gb": 9.0, "fam": "DeepSeek-R1", "info": "Denk-Modell, top Logik", "denk": True},
    "phi4:14b":          {"params": "14B", "gb": 9.1, "fam": "Phi-4",       "info": "stark in Logik & Mathe"},
    "qwen3:14b":         {"params": "14B", "gb": 9.3, "fam": "Qwen3",       "info": "sehr stark, aktuell"},
    "gemma4:e4b":        {"params": "E4B (eff. 4B)", "gb": 9.6, "fam": "Gemma 4", "info": "neueste Gemma, sehr gutes Deutsch (App-Standard)"},
    # --- gross (~14-20 GB) ------------------------------------------------- #
    "gpt-oss:20b":       {"params": "20B (MoE, ~3.6B aktiv)", "gb": 14.0, "fam": "GPT-OSS", "info": "OpenAI-Open, schnell (MoE), stark in Logik – etwas englischlastig", "denk": True},
    "mistral-small3.2:24b": {"params": "24B", "gb": 15.0, "fam": "Mistral", "info": "aktuellstes Mistral Small, 128K Kontext"},
    "gemma3:27b":        {"params": "27B", "gb": 17.0, "fam": "Gemma 3",     "info": "Spitzen-Deutsch, Top-Qualität"},
    "gemma4:26b":        {"params": "26B (MoE)", "gb": 18.0, "fam": "Gemma 4", "info": "neueste Gemma, stark & schnell (MoE)"},
    "qwen3:30b":         {"params": "30B (MoE, 3B aktiv)", "gb": 19.0, "fam": "Qwen3", "info": "sehr schnell für die Größe"},
    "gemma4:31b":        {"params": "31B", "gb": 20.0, "fam": "Gemma 4",     "info": "neueste Gemma, Top-Qualität"},
    "qwen3:32b":         {"params": "32B", "gb": 20.0, "fam": "Qwen3",       "info": "sehr stark (dicht)"},
    "deepseek-r1:32b":   {"params": "32B", "gb": 20.0, "fam": "DeepSeek-R1", "info": "Spitzen-Logik, Denk-Modell", "denk": True},
}

# Reihenfolge grob nach Qualitaet fuer deutsches RAG (bestes zuerst). Aus dieser
# Liste werden fuer eine Hardware die groessten noch passenden Modelle vorgeschlagen.
_LLM_ORDER = [
    "gemma3:27b", "gemma4:31b", "gemma4:26b", "qwen3:32b", "mistral-small3.2:24b",
    "deepseek-r1:32b", "qwen3:30b",
    "gemma3:12b", "gemma4:e4b", "qwen3:14b", "phi4:14b", "gpt-oss:20b",
    "deepseek-r1:14b", "mistral-nemo:12b",
    "qwen3:8b", "deepseek-r1:8b", "llama3.1:8b", "mistral:7b",
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
    {"tag": "snowflake-arctic-embed2", "info": "multilingual, für Deutsch optimiert (1024-dim)"},
    {"tag": "embeddinggemma:300m",     "info": "sehr kompakt & CPU-freundlich, multilingual (768-dim)"},
    {"tag": "qwen3-embedding:0.6b",    "info": "stark multilingual, kompakt"},
]

# Reranker (HuggingFace Cross-Encoder; laedt beim ersten Benutzen automatisch).
RERANKER_MODELS = [
    {"tag": "BAAI/bge-reranker-v2-m3",                   "info": "★ Empfohlen – multilingual, sehr genau"},
    {"tag": "jinaai/jina-reranker-v2-base-multilingual", "info": "multilingual, sehr schnell (kompakt)"},
    {"tag": "mixedbread-ai/mxbai-rerank-large-v2",       "info": "SOTA, 109 Sprachen – aber schwerer (2B)"},
]


def _fit_budget(hw: dict) -> "tuple[float, float, str, str]":
    """Effektives Speicher-Budget (GB) fuer die Modellwahl, abgeleitet aus der
    Hardware. Rueckgabe: (fit_budget, hard_budget, on, vram_note).
      * fit_budget  = passt KOMPLETT in den Speicher (fluessig, kein Offload)
      * hard_budget = darf knapp ueberlaufen (nur als markierte Alternative)
    Wird von recommend_models UND recommend_ocr_vision_model genutzt, damit
    Antwort- und OCR-Modell nach DEMSELBEN VRAM-Massstab gewaehlt werden.
    (Intel/IPEX behandeln die Aufrufer gesondert.)"""
    gpu = hw["gpu"]
    vendor = gpu["vendor"]
    vram = gpu.get("vram_gb")
    ram = hw.get("ram_gb") or 8
    if vendor in ("nvidia", "amd") and vram:
        on = "GPU"
        reserve = 1.5 if vram <= 6 else (2.0 if vram <= 9 else 3.0)
        fit_budget = max(2.0, vram - reserve)
        hard_budget = vram + 0.5
        vram_note = f" (~{vram:.0f} GB VRAM erkannt)"
    elif vendor in ("nvidia", "amd"):
        on = "GPU"; fit_budget, hard_budget = 5.5, 8.0
        vram_note = " (VRAM unbekannt -> vorsichtig gewaehlt)"
    elif vendor == "apple":
        on = "GPU (Metal)"; fit_budget = (ram or 8) * 0.5; hard_budget = (ram or 8) * 0.7
        vram_note = ""
    else:
        on = "CPU"; fit_budget = max(3.0, (ram or 8) / 3); hard_budget = (ram or 8) / 2
        vram_note = ""
    return fit_budget, hard_budget, on, vram_note


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

    # Effektives Budget (VRAM/RAM minus Reserve) -> ausgelagert, damit die
    # OCR-Vision-Wahl denselben Massstab nutzt.
    fit_budget, hard_budget, on, vram_note = _fit_budget(hw)

    # _LLM_ORDER ist stark -> schwach. "fits" passt komplett (Standard = staerkstes
    # davon); "spills" ist etwas groesser (nur als markierte Alternative).
    fits = [t for t in _LLM_ORDER if _LLM[t]["gb"] <= fit_budget]
    spills = [t for t in _LLM_ORDER if fit_budget < _LLM[t]["gb"] <= hard_budget]
    if fits:
        ordered = fits[:4] + spills[:1]        # passende zuerst + 1 staerkere Option
    else:                                       # nichts passt komplett -> kleinste (geringstes Offload)
        ordered = sorted(_LLM_ORDER, key=lambda t: _LLM[t]["gb"])[:3]

    picks: list[dict] = []
    for tag in ordered[:5]:
        m = _LLM[tag]
        fully = m["gb"] <= fit_budget
        if on.startswith("GPU"):
            lauf = ("läuft komplett auf der GPU (flüssig)" if fully
                    else "größer als der VRAM – läuft teils über RAM (langsamer)")
            why = f"{m['info']} · {lauf}"
        else:
            why = m["info"]
        picks.append({"tag": tag, "params": m["params"], "gb": m["gb"],
                      "fam": m["fam"], "denk": m.get("denk", False), "why": why})

    note = " (Nur-CPU: Antworten dauern länger, kleines Modell empfohlen.)" if vendor == "none" else ""
    return {
        "reason": f"{on}{vram_note}: Standard ist das stärkste Modell, das noch KOMPLETT in "
                  f"den Speicher passt (flüssig, kein Auslagern).{note} Stärkere Modelle stehen "
                  "in der Liste – sie können aber langsamer sein.",
        "embed_model": "bge-m3",
        "budget_gb": round(fit_budget, 1),
        "models": picks,
    }


# Vision-faehige Katalog-Modelle fuer die Handschrift-/Scan-OCR (beste Lesetreue
# zuerst). Alle multimodal & stark in Deutsch; Groessen kommen aus _LLM.
# Dient zugleich als Quelle fuer den OCR-Modell-Picker in den Einstellungen.
VISION_OCR_MODELS = [
    {"tag": "gemma3:27b", "gb": 17.0, "info": "Spitzen-Deutsch, beste Lesetreue (großer VRAM)"},
    {"tag": "gemma4:26b", "gb": 18.0, "info": "neueste Gemma (MoE), sehr stark"},
    {"tag": "gemma3:12b", "gb":  8.1, "info": "exzellentes Deutsch, guter Kompromiss"},
    {"tag": "gemma4:e4b", "gb":  9.6, "info": "neueste Gemma, effizient"},
    {"tag": "gemma3:4b",  "gb":  3.3, "info": "kompakt & laptop-tauglich (Standard)"},
]
_VISION_OCR_ORDER = [m["tag"] for m in VISION_OCR_MODELS]   # beste -> kleinste


def recommend_ocr_vision_model(hw: dict) -> str:
    """Empfiehlt das BESTE vision-faehige Katalog-Modell fuer die OCR (Handschrift/
    Scan), das noch KOMPLETT in den Speicher passt - nach demselben VRAM-Budget wie
    das Antwort-Modell (recommend_models/_fit_budget). Laptop/kleiner VRAM ->
    gemma3:4b; mehr VRAM -> gemma3:12b, dann gemma4:26b / gemma3:27b. Gibt IMMER
    einen Tag zurueck (Fallback: kleinstes Vision-Modell)."""
    # Intel-IPEX (altes SYCL-Backend): nur das kleine, erprobte Gemma laeuft dort.
    if hw.get("gpu", {}).get("vendor") == "intel":
        return "gemma3:4b"
    fit_budget, _hard, _on, _note = _fit_budget(hw)
    for tag in _VISION_OCR_ORDER:                     # beste Lesetreue zuerst
        if _LLM[tag]["gb"] <= fit_budget:
            return tag
    return min(_VISION_OCR_ORDER, key=lambda t: _LLM[t]["gb"])   # nichts passt -> kleinstes


def llm_size_gb(tag: str) -> "float | None":
    """Grober Speicherbedarf (GB) eines bekannten Katalog-Modells, sonst None."""
    m = _LLM.get(tag) or _INTEL.get(tag)
    return m.get("gb") if m else None


def all_llm_tags() -> "list[str]":
    """Alle Katalog-Modelle in Empfehlungs-Reihenfolge (fuer die Auswahl-Liste, damit
    man auch ausserhalb der Top-Empfehlungen jedes Modell waehlen + laden kann)."""
    return list(_LLM_ORDER)


def probe_model(tag: str, base_url: "str | None" = None, timeout: int = 60) -> "tuple[bool, str]":
    """Prueft SCHNELL, ob ein Ollama-Modell wirklich LAEDT (nicht nur installiert ist) -
    ein winziger generate-Ping. Faengt genau den Intel-IPEX/SYCL-Ladefehler ab
    ("unable to load model ... status code 500"). Gibt (ok, meldung) zurueck."""
    try:
        import ollama
        from ragapp.config import settings
        client = ollama.Client(host=base_url or settings.OLLAMA_BASE_URL, timeout=timeout)
        client.generate(model=tag, prompt="OK", options={"num_predict": 1}, stream=False)
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        low = msg.lower()
        if "unable to load model" in low or "status code: 500" in low or "runner" in low:
            return False, ("Das Modell laedt auf diesem Rechner/Backend nicht (z. B. neuere "
                           "Architektur auf altem Intel-IPEX-Backend).")
        if "not found" in low or "no such model" in low or "status code: 404" in low:
            return False, "Modell ist nicht installiert (erst herunterladen)."
        return False, msg[:200]


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
