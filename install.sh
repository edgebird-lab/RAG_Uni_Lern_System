#!/usr/bin/env bash
# ============================================================================
#  install.sh  -  One-Click-Installer (Linux / macOS)
# ============================================================================
#  Richtet das lokale RAG-Lernsystem passend zur vorhandenen Hardware ein:
#
#    1. Prueft Python 3.10+
#    2. Erkennt die GPU (NVIDIA / AMD / Intel / Apple-Metal / keine)
#    3. Erstellt die virtuelle Umgebung (.venv) und aktualisiert pip
#    4. Installiert PyTorch passend (NVIDIA -> CUDA/Default, AMD-Linux -> ROCm,
#       macOS -> Default/MPS, sonst -> CPU)
#    5. Installiert die restlichen Abhaengigkeiten (requirements.txt)
#    6. Richtet Ollama ein:
#         - Linux (NVIDIA/AMD/keine): curl -fsSL https://ollama.com/install.sh | sh
#         - macOS: Hinweis auf ollama.com/download
#         - Intel-Linux: IPEX-LLM "Ollama Portable" (Ubuntu-Paket)
#       und zieht das Embedding-Modell bge-m3
#    7. Misst die Hardware und waehlt/laedt/testet das passende LLM
#         (ragapp.scripts.cli recommend --set --test)
#    8. Erfolgsmeldung + Start-Hinweis
#
#  Das Skript ist idempotent. Aufruf:   bash install.sh
#
#  Optionen (Umgebungsvariablen):
#    SKIP_RECOMMEND=1   den Modell-Auswahl-/Benchmark-Schritt ueberspringen
#    CPU_ONLY=1         GPU ignorieren, alles als CPU behandeln
# ============================================================================
set -euo pipefail

# --------------------------------------------------------------------------- #
# Projektwurzel = Ordner dieses Skripts (portabel, kein hartkodierter Pfad)
# --------------------------------------------------------------------------- #
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

IPEX_DIR="$ROOT/ipex-ollama"
IPEX_BIN="$IPEX_DIR/ollama"
IPEX_TGZ="$ROOT/ipex-ollama-ubuntu.tgz"
IPEX_URL="https://github.com/ipex-llm/ipex-llm/releases/download/v2.3.0-nightly/ollama-ipex-llm-2.3.0b20250725-ubuntu.tgz"
VENV_PY="$ROOT/.venv/bin/python"

# --------------------------------------------------------------------------- #
# Ausgabe-Helfer (mit Farbe, falls Terminal)
# --------------------------------------------------------------------------- #
if [ -t 1 ]; then
    C_CY=$'\033[36m'; C_GR=$'\033[32m'; C_YE=$'\033[33m'; C_RE=$'\033[31m'; C_0=$'\033[0m'
else
    C_CY=''; C_GR=''; C_YE=''; C_RE=''; C_0=''
fi
step() { printf '\n%s==> %s%s\n' "$C_CY" "$1" "$C_0"; }
info() { printf '    %s\n' "$1"; }
ok()   { printf '    %s[OK]%s %s\n' "$C_GR" "$C_0" "$1"; }
warn() { printf '    %s[!]%s %s\n'  "$C_YE" "$C_0" "$1"; }
err()  { printf '    %s[X]%s %s\n'  "$C_RE" "$C_0" "$1"; }

# --------------------------------------------------------------------------- #
# 1) Python 3.10+ suchen
# --------------------------------------------------------------------------- #
find_python() {
    for cand in python3.13 python3.12 python3.11 python3.10 python3 python; do
        if command -v "$cand" >/dev/null 2>&1; then
            if "$cand" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,10) else 1)' >/dev/null 2>&1; then
                echo "$cand"; return 0
            fi
        fi
    done
    return 1
}

# --------------------------------------------------------------------------- #
# 2) GPU erkennen -> setzt GPU_VENDOR (nvidia|amd|intel|apple|none)
# --------------------------------------------------------------------------- #
detect_gpu() {
    local os; os="$(uname -s)"
    if [ "${CPU_ONLY:-0}" = "1" ]; then echo "none"; return; fi
    if [ "$os" = "Darwin" ]; then
        # Apple Silicon -> Metal; Intel-Mac -> CPU-Pfad (Ollama nutzt dort CPU)
        if [ "$(uname -m)" = "arm64" ]; then echo "apple"; else echo "none"; fi
        return
    fi
    # Linux
    if command -v nvidia-smi >/dev/null 2>&1; then echo "nvidia"; return; fi
    local lspci_out=""
    if command -v lspci >/dev/null 2>&1; then
        lspci_out="$(lspci 2>/dev/null | grep -Ei 'vga|3d|display' || true)"
    fi
    if command -v rocminfo >/dev/null 2>&1; then echo "amd"; return; fi
    if echo "$lspci_out" | grep -Eiq 'nvidia'; then echo "nvidia"; return; fi
    if echo "$lspci_out" | grep -Eiq 'amd|radeon|advanced micro devices'; then echo "amd"; return; fi
    if echo "$lspci_out" | grep -Eiq 'intel'; then echo "intel"; return; fi
    echo "none"
}

# --------------------------------------------------------------------------- #
# Warten, bis Ollama auf Port 11434 antwortet
# --------------------------------------------------------------------------- #
wait_for_ollama() {
    local timeout="${1:-90}" waited=0
    while [ "$waited" -lt "$timeout" ]; do
        if curl -fsS "http://127.0.0.1:11434/api/version" >/dev/null 2>&1; then return 0; fi
        sleep 1; waited=$((waited + 1))
    done
    return 1
}

# =========================================================================== #
#  HAUPTABLAUF
# =========================================================================== #
echo "============================================================"
echo " RAG-Lernsystem  -  Installer (Linux/macOS)"
echo " Projektordner: $ROOT"
echo "============================================================"

OS="$(uname -s)"

# ---- 1) Python ------------------------------------------------------------- #
step "Python 3.10+ suchen"
if ! PYTHON="$(find_python)"; then
    err "Es wurde kein Python 3.10 oder neuer gefunden."
    info "Bitte Python 3.10+ installieren:"
    info "  Linux (Debian/Ubuntu): sudo apt install python3 python3-venv python3-pip"
    info "  macOS:                 brew install python   (oder https://www.python.org/downloads/)"
    exit 1
fi
ok "Python gefunden: $PYTHON ($("$PYTHON" -c 'import platform;print(platform.python_version())'))"

# ---- 2) GPU ---------------------------------------------------------------- #
step "GPU erkennen"
GPU_VENDOR="$(detect_gpu)"
case "$GPU_VENDOR" in
    nvidia) ok "NVIDIA-GPU erkannt  -> Standard-Ollama (CUDA), torch = CUDA/Default" ;;
    amd)    ok "AMD-GPU erkannt     -> Standard-Ollama (ROCm), torch = ROCm-Index" ;;
    intel)  ok "Intel-GPU erkannt   -> IPEX-LLM (SYCL), torch = CPU" ;;
    apple)  ok "Apple Silicon erkannt -> Standard-Ollama (Metal), torch = Default/MPS" ;;
    *)      ok "Keine unterstuetzte GPU -> Nur-CPU-Betrieb, torch = CPU" ;;
esac

# ---- 3) venv + pip --------------------------------------------------------- #
step "Virtuelle Umgebung (.venv) einrichten"
if [ -x "$VENV_PY" ]; then
    ok ".venv existiert bereits - wird wiederverwendet."
else
    "$PYTHON" -m venv .venv
    [ -x "$VENV_PY" ] || { err ".venv wurde nicht erstellt (kein python)."; exit 1; }
    ok ".venv erstellt."
fi
info "pip / setuptools / wheel aktualisieren ..."
"$VENV_PY" -m pip install --upgrade pip setuptools wheel

# ---- 4) torch + torchvision ------------------------------------------------ #
# torch = Reranker; torchvision = wird von easyocr (OCR) benoetigt. BEIDE aus dem
# GLEICHEN Index installieren - sonst zieht easyocr ueber torchvision spaeter eine
# unpassende (CUDA-)torch nach und ueberschreibt die GPU-Variante (z. B. ROCm).
#
# Versionsbereich (Ro1): torch/torchvision waren bisher voellig ungepinnt. Jetzt eine
# konservative OBERGRENZE (torch<3 / torchvision<1) - das blockt einen kuenftigen,
# potenziell brechenden Major-Release, aendert aber HEUTE nichts an der Aufloesung und
# bricht insbesondere die ROCm-Index-Installation NICHT (dort ist die neueste passende
# Version ohnehin < der Grenze). Bewusst KEIN harter ==-Pin, da die verfuegbaren
# Versionen je Index (cpu / rocm6.0 / default) unterschiedlich sind. Bekannt-gute,
# getestete Referenz auf diesem Rechner: torch 2.4.1+rocm6.0 / torchvision 0.19.1+rocm6.0
# (fuer volle Reproduzierbarkeit ggf. exakt auf die eigene Version pinnen).
TORCH_SPEC="torch<3"
TV_SPEC="torchvision<1"
step "PyTorch (+ torchvision fuer OCR) installieren"
if "$VENV_PY" -c "import torch, torchvision" >/dev/null 2>&1; then
    ok "torch + torchvision bereits installiert - uebersprungen."
else
    case "$GPU_VENDOR" in
        nvidia)
            info "Installiere torch + torchvision (CUDA/Default-Index) ..."
            "$VENV_PY" -m pip install "$TORCH_SPEC" "$TV_SPEC" ;;
        amd)
            info "Installiere torch + torchvision (ROCm 6.0-Index) ..."
            if ! "$VENV_PY" -m pip install "$TORCH_SPEC" "$TV_SPEC" --index-url https://download.pytorch.org/whl/rocm6.0; then
                warn "ROCm-torch fehlgeschlagen - fallback auf CPU-Build."
                "$VENV_PY" -m pip install "$TORCH_SPEC" "$TV_SPEC" --index-url https://download.pytorch.org/whl/cpu
            fi ;;
        apple)
            info "Installiere torch + torchvision (Default-Index, MPS-faehig) ..."
            "$VENV_PY" -m pip install "$TORCH_SPEC" "$TV_SPEC" ;;
        *)
            info "Installiere torch + torchvision (CPU-Build) ..."
            "$VENV_PY" -m pip install "$TORCH_SPEC" "$TV_SPEC" --index-url https://download.pytorch.org/whl/cpu ;;
    esac
    ok "torch + torchvision installiert."
fi

# ---- 5) requirements ------------------------------------------------------- #
step "Abhaengigkeiten installieren (requirements.txt)"
"$VENV_PY" -m pip install -r requirements.txt
ok "Alle Python-Abhaengigkeiten installiert."

# ---- 6) Ollama ------------------------------------------------------------- #
step "Ollama einrichten"
IPEX_STARTED=0
if [ "$GPU_VENDOR" = "intel" ] && [ "$OS" = "Linux" ]; then
    # ---------------- Intel-Linux: IPEX-LLM Ollama Portable ----------------- #
    if [ ! -x "$IPEX_BIN" ]; then
        if [ ! -f "$IPEX_TGZ" ]; then
            info "Lade IPEX-LLM Ollama Portable (Ubuntu) herunter ..."
            info "$IPEX_URL"
            curl -fSL "$IPEX_URL" -o "$IPEX_TGZ"
        else
            info "IPEX-Archiv bereits vorhanden - wird wiederverwendet."
        fi
        info "Entpacke IPEX-LLM ..."
        mkdir -p "$IPEX_DIR"
        tar -xzf "$IPEX_TGZ" -C "$IPEX_DIR"
        # Falls in einen Unterordner entpackt: ollama-Binary hochziehen.
        if [ ! -x "$IPEX_BIN" ]; then
            found="$(find "$IPEX_DIR" -maxdepth 3 -type f -name ollama 2>/dev/null | head -n1 || true)"
            if [ -n "$found" ] && [ "$found" != "$IPEX_BIN" ]; then
                cp -a "$(dirname "$found")/." "$IPEX_DIR/"
            fi
        fi
        chmod +x "$IPEX_BIN" 2>/dev/null || true
        [ -x "$IPEX_BIN" ] || { err "ipex-ollama/ollama nach dem Entpacken nicht gefunden."; exit 1; }
        ok "IPEX-LLM Ollama liegt in $IPEX_DIR"
    else
        ok "IPEX-LLM Ollama bereits vorhanden ($IPEX_DIR)."
    fi

    if curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
        warn "Auf Port 11434 antwortet bereits ein Ollama-Server - er wird genutzt."
    else
        info "Starte IPEX-Ollama-Server auf der Intel-GPU ..."
        ( cd "$IPEX_DIR" && exec env \
          OLLAMA_NUM_GPU=999 ZES_ENABLE_SYSMAN=1 ONEAPI_DEVICE_SELECTOR=level_zero:0 \
          OLLAMA_HOST=127.0.0.1:11434 OLLAMA_MAX_LOADED_MODELS=2 \
          ./ollama serve ) >"$ROOT/ipex-ollama-serve.log" 2>&1 &
        echo $! >"$ROOT/.ipex-ollama.pid"
        IPEX_STARTED=1
        if ! wait_for_ollama 90; then
            err "IPEX-Ollama-Server ist nicht auf Port 11434 erreichbar geworden (siehe ipex-ollama-serve.log)."
            exit 1
        fi
        ok "IPEX-Ollama-Server laeuft (Port 11434)."
    fi
    info "Ziehe Embedding-Modell bge-m3 ..."
    OLLAMA_HOST=127.0.0.1:11434 "$IPEX_BIN" pull bge-m3 || warn "bge-m3-Pull fehlgeschlagen (spaeter wiederholbar)."

elif [ "$OS" = "Darwin" ]; then
    # ---------------- macOS: Standard-Ollama (Metal) ------------------------ #
    if ! command -v ollama >/dev/null 2>&1; then
        warn "Ollama ist nicht installiert."
        info "Bitte Ollama fuer macOS installieren: https://ollama.com/download"
        info "(oder per Homebrew:  brew install ollama )"
        read -r -p "    -> Nach der Ollama-Installation ENTER druecken " _ || true
    fi
    if ! command -v ollama >/dev/null 2>&1; then
        err "Ollama weiterhin nicht gefunden. Bitte installieren und Skript erneut starten."
        exit 1
    fi
    if ! curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
        info "Starte Ollama-Server im Hintergrund ..."
        ( ollama serve >"$ROOT/ollama-serve.log" 2>&1 & ) || true
        wait_for_ollama 60 || warn "Ollama-Server nicht erreichbar - bitte die Ollama-App starten."
    fi
    ok "Ollama bereit."
    info "Ziehe Embedding-Modell bge-m3 ..."
    ollama pull bge-m3 || warn "bge-m3-Pull fehlgeschlagen (spaeter wiederholbar)."

else
    # ---------------- Linux NVIDIA/AMD/keine: Standard-Ollama --------------- #
    if ! command -v ollama >/dev/null 2>&1; then
        info "Installiere Ollama (curl -fsSL https://ollama.com/install.sh | sh) ..."
        curl -fsSL https://ollama.com/install.sh | sh
    fi
    if ! command -v ollama >/dev/null 2>&1; then
        err "Ollama-Installation fehlgeschlagen. Bitte manuell installieren: https://ollama.com/download"
        exit 1
    fi
    if ! curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
        info "Starte Ollama-Server im Hintergrund ..."
        ( ollama serve >"$ROOT/ollama-serve.log" 2>&1 & ) || true
        wait_for_ollama 60 || warn "Ollama-Server nicht erreichbar - ggf. 'systemctl start ollama' oder 'ollama serve'."
    fi
    ok "Ollama bereit."
    info "Ziehe Embedding-Modell bge-m3 ..."
    ollama pull bge-m3 || warn "bge-m3-Pull fehlgeschlagen (spaeter wiederholbar)."
fi

# ---- 7) recommend ---------------------------------------------------------- #
if [ "${SKIP_RECOMMEND:-0}" = "1" ]; then
    step "Modell-Empfehlung uebersprungen (SKIP_RECOMMEND=1)"
else
    step "Hardware messen und passendes LLM waehlen/laden/testen"
    info "python -m ragapp.scripts.cli recommend --set --test"
    if "$VENV_PY" -m ragapp.scripts.cli recommend --set --test; then
        ok "Passendes Modell gewaehlt, getestet und in data/config.json gesetzt."
    else
        warn "Der recommend-Schritt ist nicht durchgelaufen - spaeter nachholbar (siehe unten)."
    fi
fi

# ---- 7b) OCR-Vision-Modell fuer Handschrift/Scans sicherstellen ------------- #
# Handschrift-/Scan-PDFs werden per kleinem Vision-LLM gelesen (viel besser als
# klassisches OCR, das dabei Kauderwelsch liefert). Ist schon ein vision-faehiges
# Modell da (z. B. ein Gemma-Antwortmodell), wird es genutzt; sonst ziehen wir ein
# kleines, laptop-taugliches (gemma3:4b, ~3.3 GB). Ueberspringbar: SKIP_OCR_MODEL=1.
if [ "${SKIP_OCR_MODEL:-0}" != "1" ]; then
    step "OCR-Vision-Modell fuer Handschrift/Scans sicherstellen"
    info "Suche/ziehe ein kleines Vision-Modell (nur falls noch keins installiert ist) ..."
    VMODEL="$("$VENV_PY" -c "from ragapp.ingestion.loaders import has_vision_ocr_model; print(has_vision_ocr_model(pull_if_missing=True))" 2>/dev/null || true)"
    if [ -n "$VMODEL" ]; then
        ok "OCR nutzt Vision-Modell: $VMODEL"
    else
        warn "Kein Vision-Modell verfuegbar - Handschrift-OCR faellt auf easyocr zurueck (spaeter: 'ollama pull gemma3:4b')."
    fi
fi

# ---- 8) Temporaeren IPEX-Server beenden (fuer den Alltag startet ihn start.sh) #
if [ "$IPEX_STARTED" = "1" ] && [ -f "$ROOT/.ipex-ollama.pid" ]; then
    info "Beende temporaeren IPEX-Server (fuer den Alltag startet ihn start.sh)."
    kill "$(cat "$ROOT/.ipex-ollama.pid")" >/dev/null 2>&1 || true
    rm -f "$ROOT/.ipex-ollama.pid"
fi

# ---- 9) cloudflared fuer 'Von unterwegs' (Cloudflare-Tunnel, Linux) --------- #
if [ "$OS" = "Linux" ]; then
    if command -v cloudflared >/dev/null 2>&1 || [ -x "$HOME/.local/bin/cloudflared" ]; then
        ok "cloudflared bereits vorhanden (fuer Zugriff von unterwegs)."
    else
        step "cloudflared installieren (fuer 'Von unterwegs' / Cloudflare-Tunnel)"
        _cfarch="$(uname -m)"
        case "$_cfarch" in
            x86_64) _cfa=amd64;; aarch64|arm64) _cfa=arm64;; armv7l|armv6l) _cfa=arm;; *) _cfa=amd64;;
        esac
        mkdir -p "$HOME/.local/bin"
        if curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${_cfa}" \
                -o "$HOME/.local/bin/cloudflared"; then
            chmod +x "$HOME/.local/bin/cloudflared"
            ok "cloudflared installiert: $HOME/.local/bin/cloudflared"
        else
            warn "cloudflared-Download fehlgeschlagen - 'Von unterwegs' geht erst nach manueller Installation (https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)."
        fi
    fi
fi

# ---- 10) Desktop-/Menue-Starter (Linux) ------------------------------------ #
if [ "$OS" = "Linux" ]; then
    step "Desktop-/Menue-Starter anlegen (Icon)"
    APP_DIR="$HOME/.local/share/applications"
    mkdir -p "$APP_DIR"
    DESKTOP_FILE="$APP_DIR/rag-lernsystem.desktop"
    {
        echo "[Desktop Entry]"
        echo "Type=Application"
        echo "Name=RAG-Lernsystem"
        echo "Comment=Lokales KI-Lernsystem fuer die Klausurvorbereitung"
        echo "Exec=bash -c 'cd \"$ROOT\" && ./start.sh'"
        echo "Path=$ROOT"
        echo "Icon=$ROOT/assets/icon.png"
        # Terminal=false: KEIN gnome-terminal davor. Terminal=true koppelte start.sh
        # an eine fluechtige Terminal-Session, deren Wegfall (SIGHUP/Scope-Abbau) die
        # App "von selbst" beendete ("Streamlit server is not responding"). start.sh
        # laeuft so direkt als langlebiger App-Prozess; Ausgabe steht in data/logs/.
        echo "Terminal=false"
        echo "Categories=Education;Science;"
    } > "$DESKTOP_FILE"
    chmod +x "$DESKTOP_FILE" 2>/dev/null || true
    if [ -d "$HOME/Desktop" ]; then
        cp -f "$DESKTOP_FILE" "$HOME/Desktop/RAG-Lernsystem.desktop" 2>/dev/null || true
        chmod +x "$HOME/Desktop/RAG-Lernsystem.desktop" 2>/dev/null || true
    fi
    # Zweites Icon: Zugriff von UNTERWEGS (sicherer Cloudflare-Tunnel) via
    # Start_Unterwegs.sh -> Handy-Zugriff + QR-Code (PIN noetig).
    UNTERWEGS_FILE="$APP_DIR/rag-lernsystem-unterwegs.desktop"
    {
        echo "[Desktop Entry]"
        echo "Type=Application"
        echo "Name=RAG-Lernsystem – Unterwegs (Handy/Cloudflare)"
        echo "Comment=Startet mit sicherem Cloudflare-Tunnel: Handy-Zugriff + QR-Code (PIN noetig)"
        echo "Exec=bash -c 'cd \"$ROOT\" && ./Start_Unterwegs.sh'"
        echo "Path=$ROOT"
        echo "Icon=$ROOT/assets/icon.png"
        echo "Terminal=false"
        echo "Categories=Education;Science;"
    } > "$UNTERWEGS_FILE"
    chmod +x "$UNTERWEGS_FILE" 2>/dev/null || true
    ok "Starter angelegt: $DESKTOP_FILE (+ Unterwegs-Icon)"
fi

# ---- Erfolgsmeldung -------------------------------------------------------- #
echo ""
echo "============================================================"
echo " Installation abgeschlossen."
echo "============================================================"
echo ""
echo " So startest du das System:"
echo "   ./start.sh"
if [ "$GPU_VENDOR" = "intel" ] && [ "$OS" = "Linux" ]; then
    echo "   (start.sh startet automatisch den Intel-GPU-Server und dann die Oberflaeche.)"
else
    echo "   (Ollama-Dienst muss laufen; start.sh oeffnet die Oberflaeche.)"
fi
echo ""
echo " Dokumente einlesen:  .venv/bin/python -m ragapp.scripts.cli ingest"
echo " System pruefen:      .venv/bin/python -m ragapp.scripts.cli doctor"
if [ "${SKIP_RECOMMEND:-0}" = "1" ]; then
    echo " Modell nachtraeglich waehlen: .venv/bin/python -m ragapp.scripts.cli recommend --set --test"
fi
echo ""
