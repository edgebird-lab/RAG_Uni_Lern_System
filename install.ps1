#Requires -Version 5.0
<#
============================================================================
 install.ps1  -  One-Click-Installer (Windows / PowerShell)
============================================================================
 Richtet das lokale RAG-Lernsystem passend zur vorhandenen Hardware ein:

   1. Prueft Python 3.10+
   2. Erkennt die GPU grob (NVIDIA / AMD / Intel / keine)
   3. Erstellt die virtuelle Umgebung (.venv) und aktualisiert pip
   4. Installiert PyTorch passend (NVIDIA -> CUDA/Default, sonst CPU)
   5. Installiert die restlichen Abhaengigkeiten (requirements.txt)
   6. Richtet Ollama ein:
        - NVIDIA/AMD/keine -> Standard-Ollama (ollama.com), zieht bge-m3
        - Intel            -> IPEX-LLM "Ollama Portable Zip" (SYCL), zieht bge-m3
   7. Misst die Hardware und waehlt/laedt/testet das passende LLM
        (ragapp.scripts.cli recommend --set --test)
   8. Gibt eine Erfolgsmeldung + Start-Hinweis aus

 Das Skript ist idempotent: mehrfaches Ausfuehren richtet nichts an.
 Aufruf:   Rechtsklick -> "Mit PowerShell ausfuehren"
     oder: powershell -ExecutionPolicy Bypass -File .\install.ps1

 Optionen:
     -SkipRecommend   den Modell-Auswahl-/Benchmark-Schritt ueberspringen
     -CpuOnly         GPU ignorieren, alles als CPU behandeln (torch = CPU)
============================================================================
#>
[CmdletBinding()]
param(
    [switch]$SkipRecommend,
    [switch]$CpuOnly
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # spuerbar schnellere Invoke-WebRequest-Downloads

# --------------------------------------------------------------------------- #
# Projektwurzel = Ordner dieses Skripts (portabel, kein hartkodierter Pfad)
# --------------------------------------------------------------------------- #
if ($PSScriptRoot) { $Root = $PSScriptRoot }
else { $Root = Split-Path -Parent $MyInvocation.MyCommand.Definition }
Set-Location -LiteralPath $Root

$IpexDir  = Join-Path $Root 'ipex-ollama'
$IpexExe  = Join-Path $IpexDir 'ollama.exe'
$IpexZip  = Join-Path $Root 'ipex-ollama.zip'
$IpexUrl  = 'https://github.com/ipex-llm/ipex-llm/releases/download/v2.3.0-nightly/ollama-ipex-llm-2.3.0b20250725-win.zip'
$VenvPy   = Join-Path $Root '.venv\Scripts\python.exe'

# --------------------------------------------------------------------------- #
# Ausgabe-Helfer
# --------------------------------------------------------------------------- #
function Write-Step($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }
function Write-Info($m) { Write-Host "    $m" -ForegroundColor Gray }
function Write-Ok  ($m) { Write-Host "    [OK] $m" -ForegroundColor Green }
function Write-Warn2($m){ Write-Host "    [!] $m" -ForegroundColor Yellow }
function Write-Err ($m) { Write-Host "    [X] $m" -ForegroundColor Red }

function Invoke-Native {
    param([Parameter(Mandatory)][string]$File,
          [string[]]$Arguments = @(),
          [Parameter(Mandatory)][string]$What)
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$What fehlgeschlagen (Exit-Code $LASTEXITCODE)." }
}

# --------------------------------------------------------------------------- #
# Netzwerk-Helfer: auf den Ollama-Port (11434) warten
# --------------------------------------------------------------------------- #
function Test-Port {
    param([string]$OllamaHost = '127.0.0.1', [int]$Port = 11434, [int]$TimeoutMs = 800)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect($OllamaHost, $Port, $null, $null)
        if ($iar.AsyncWaitHandle.WaitOne($TimeoutMs)) {
            $client.EndConnect($iar); return $true
        }
        return $false
    } catch { return $false }
    finally { $client.Close() }
}

function Wait-Port {
    param([int]$Port = 11434, [int]$TimeoutSec = 90, [string]$Label = 'Ollama')
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        if (Test-Port -Port $Port) { return $true }
        Start-Sleep -Milliseconds 700
    }
    return $false
}

# --------------------------------------------------------------------------- #
# 1) Python 3.10+ suchen
# --------------------------------------------------------------------------- #
function Get-BootstrapPython {
    # Kandidaten als leerzeichen-getrennte Strings (NICHT als verschachtelte
    # Arrays): @( ,@('py','-3.13'), ... ) verschachtelt sich in PowerShell falsch,
    # sodass $t[0] teils selbst ein Array wird. Dann ist $py.Exe ein Object[] und
    # spaeter scheitert 'Invoke-Native -File $py.Exe' an der String-Transformation
    # (tritt nur auf einem frischen PC ohne .venv auf, weil sonst Schritt 3 uebersprungen wird).
    $tries = @('py -3.13','py -3.12','py -3.11','py -3.10','python','python3','py -3')
    foreach ($spec in $tries) {
        $parts = $spec.Split(' ')
        $exe   = $parts[0]
        $rest  = if ($parts.Count -gt 1) { $parts[1..($parts.Count - 1)] } else { @() }
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        $ver = ''
        try { $ver = (& $exe @rest -c "import sys;print('%d.%d'%sys.version_info[:2])" 2>$null) }
        catch { continue }
        if (-not $ver) { continue }
        $p = "$ver".Trim().Split('.')
        if ($p.Count -lt 2) { continue }
        $maj = [int]$p[0]; $min = [int]$p[1]
        if ($maj -gt 3 -or ($maj -eq 3 -and $min -ge 10)) {
            return [pscustomobject]@{ Exe = "$exe"; Args = [string[]]$rest; Version = "$maj.$min" }
        }
    }
    return $null
}

# --------------------------------------------------------------------------- #
# 2) GPU-Hersteller grob erkennen
# --------------------------------------------------------------------------- #
function Get-GpuVendor {
    if ($CpuOnly) { return 'none' }
    $names = @()
    try {
        $names = @(Get-CimInstance Win32_VideoController -ErrorAction Stop |
                   Select-Object -ExpandProperty Name)
    } catch {
        try {
            $names = @(Get-WmiObject Win32_VideoController -ErrorAction Stop |
                       Select-Object -ExpandProperty Name)
        } catch { $names = @() }
    }
    $joined = ($names -join ' ').ToLower()
    # Reihenfolge: dedizierte NVIDIA/AMD schlagen die Intel-iGPU (Standard-Ollama nutzbar)
    if ($joined -match 'nvidia|geforce|rtx|quadro|tesla') { return 'nvidia' }
    if ($joined -match 'amd|radeon')                      { return 'amd' }
    if ($joined -match 'intel')                           { return 'intel' }
    return 'none'
}

# --------------------------------------------------------------------------- #
# Ollama (Standard) im Dateisystem finden
# --------------------------------------------------------------------------- #
function Resolve-OllamaExe {
    $c = Get-Command ollama -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $cands = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'),
        'C:\Program Files\Ollama\ollama.exe'
    )
    foreach ($p in $cands) { if (Test-Path -LiteralPath $p) { return $p } }
    return $null
}

# =========================================================================== #
#  HAUPTABLAUF
# =========================================================================== #
$ipexProc = $null      # Handle auf den ggf. von uns gestarteten IPEX-Server
try {
    Write-Host "============================================================" -ForegroundColor White
    Write-Host " RAG-Lernsystem  -  Installer (Windows)" -ForegroundColor White
    Write-Host " Projektordner: $Root" -ForegroundColor White
    Write-Host "============================================================" -ForegroundColor White

    # ---- 1) Python --------------------------------------------------------- #
    Write-Step "Python 3.10+ suchen"
    $py = Get-BootstrapPython
    if (-not $py) {
        Write-Warn2 "Kein Python 3.10+ gefunden - versuche automatische Installation via winget ..."
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            try {
                & winget install --id Python.Python.3.12 -e --silent `
                    --accept-source-agreements --accept-package-agreements 2>&1 | Out-Null
                # PATH im laufenden Prozess aktualisieren, damit python sofort gefunden wird
                $env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' +
                            [System.Environment]::GetEnvironmentVariable('Path','User')
                Write-Ok "Python via winget installiert."
            } catch { Write-Warn2 "Automatische Python-Installation fehlgeschlagen: $($_.Exception.Message)" }
            $py = Get-BootstrapPython
        }
    }
    if (-not $py) {
        Write-Err "Kein Python 3.10+ gefunden (auch die Auto-Installation half nicht)."
        Write-Info "Bitte Python 3.10+ installieren: https://www.python.org/downloads/"
        Write-Info "Beim Setup 'Add python.exe to PATH' aktivieren, danach erneut ausfuehren."
        exit 1
    }
    Write-Ok "Python $($py.Version) gefunden ($($py.Exe) $($py.Args -join ' '))"

    # ---- 2) GPU ------------------------------------------------------------ #
    Write-Step "GPU erkennen"
    $vendor = Get-GpuVendor
    switch ($vendor) {
        'nvidia' { Write-Ok "NVIDIA-GPU erkannt  -> Standard-Ollama (CUDA), torch = CUDA/Default" }
        'amd'    { Write-Ok "AMD-GPU erkannt     -> Standard-Ollama (ROCm/Vulkan), torch = CPU" }
        'intel'  { Write-Ok "Intel-GPU erkannt   -> IPEX-LLM (SYCL), torch = CPU" }
        default  { Write-Ok "Keine unterstuetzte GPU -> Nur-CPU-Betrieb, torch = CPU" }
    }

    # ---- 3) venv + pip ----------------------------------------------------- #
    Write-Step "Virtuelle Umgebung (.venv) einrichten"
    if (Test-Path -LiteralPath $VenvPy) {
        Write-Ok ".venv existiert bereits - wird wiederverwendet."
    } else {
        Invoke-Native -File $py.Exe -Arguments (@($py.Args) + @('-m','venv','.venv')) -What "venv-Erstellung"
        if (-not (Test-Path -LiteralPath $VenvPy)) { throw ".venv wurde nicht erstellt (kein python.exe)." }
        Write-Ok ".venv erstellt."
    }
    Write-Info "pip / setuptools / wheel aktualisieren ..."
    Invoke-Native -File $VenvPy -Arguments @('-m','pip','install','--upgrade','pip','setuptools','wheel') -What "pip-Update"

    # ---- 4) torch ---------------------------------------------------------- #
    Write-Step "PyTorch installieren (nur fuer den Reranker noetig)"
    & $VenvPy -c "import torch" 1>$null 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "torch ist bereits installiert - uebersprungen."
    } else {
        if ($vendor -eq 'nvidia') {
            Write-Info "Installiere torch (CUDA/Default-Index) ..."
            Invoke-Native -File $VenvPy -Arguments @('-m','pip','install','torch') -What "torch (CUDA)"
        } else {
            Write-Info "Installiere torch (CPU-Build) ..."
            Invoke-Native -File $VenvPy -Arguments @('-m','pip','install','torch','--index-url','https://download.pytorch.org/whl/cpu') -What "torch (CPU)"
        }
        Write-Ok "torch installiert."
    }

    # ---- 5) requirements --------------------------------------------------- #
    Write-Step "Abhaengigkeiten installieren (requirements.txt)"
    Invoke-Native -File $VenvPy -Arguments @('-m','pip','install','-r','requirements.txt') -What "requirements.txt"
    Write-Ok "Alle Python-Abhaengigkeiten installiert."

    # ---- 6) Ollama --------------------------------------------------------- #
    Write-Step "Ollama einrichten"
    if ($vendor -eq 'intel') {
        # ---------------- Intel: IPEX-LLM Ollama Portable Zip --------------- #
        if (-not (Test-Path -LiteralPath $IpexExe)) {
            if (-not (Test-Path -LiteralPath $IpexZip)) {
                Write-Info "Lade IPEX-LLM Ollama Portable Zip (~108 MB) herunter ..."
                Write-Info $IpexUrl
                Invoke-WebRequest -Uri $IpexUrl -OutFile $IpexZip -UseBasicParsing
            } else {
                Write-Info "IPEX-Zip bereits vorhanden - wird wiederverwendet."
            }
            Write-Info "Entpacke IPEX-LLM ..."
            Expand-Archive -LiteralPath $IpexZip -DestinationPath $Root -Force
            # Das Zip entpackt in einen Unterordner (ollama-ipex-llm-...-win).
            # Inhalt nach .\ipex-ollama\ normalisieren, damit Start_GPU_Ollama.bat passt.
            if (-not (Test-Path -LiteralPath $IpexExe)) {
                $found = Get-ChildItem -LiteralPath $Root -Recurse -Filter 'ollama.exe' -ErrorAction SilentlyContinue |
                         Where-Object { $_.FullName -notmatch '\\\.venv\\' } | Select-Object -First 1
                if ($found) {
                    $srcDir = $found.Directory.FullName
                    if ($srcDir -ne $IpexDir) {
                        if (-not (Test-Path -LiteralPath $IpexDir)) { New-Item -ItemType Directory -Path $IpexDir | Out-Null }
                        Copy-Item -Path (Join-Path $srcDir '*') -Destination $IpexDir -Recurse -Force
                    }
                }
            }
            if (-not (Test-Path -LiteralPath $IpexExe)) {
                throw "ipex-ollama\ollama.exe wurde nach dem Entpacken nicht gefunden."
            }
            Write-Ok "IPEX-LLM Ollama liegt in $IpexDir"
        } else {
            Write-Ok "IPEX-LLM Ollama bereits vorhanden ($IpexDir)."
        }

        # IPEX-Server fuer Modell-Pull + Benchmark auf der iGPU starten.
        if (Test-Port -Port 11434) {
            Write-Warn2 "Auf Port 11434 antwortet bereits ein Ollama-Server - er wird genutzt."
            Write-Warn2 "Fuer echte iGPU-Nutzung sollte das die IPEX-Variante sein (nicht die Standard-App)."
        } else {
            Write-Info "Starte IPEX-Ollama-Server auf der Intel-GPU ..."
            $env:OLLAMA_NUM_GPU          = '999'
            $env:ZES_ENABLE_SYSMAN       = '1'
            $env:ONEAPI_DEVICE_SELECTOR  = 'level_zero:0'
            $env:OLLAMA_HOST             = '127.0.0.1:11434'
            $env:OLLAMA_MAX_LOADED_MODELS= '2'
            $ipexProc = Start-Process -FilePath $IpexExe -ArgumentList 'serve' `
                        -WorkingDirectory $IpexDir -PassThru -WindowStyle Minimized
            if (-not (Wait-Port -Port 11434 -TimeoutSec 90)) {
                throw "IPEX-Ollama-Server ist nicht auf Port 11434 erreichbar geworden."
            }
            Write-Ok "IPEX-Ollama-Server laeuft (Port 11434)."
        }

        Write-Info "Ziehe Embedding-Modell bge-m3 ..."
        try { Invoke-Native -File $IpexExe -Arguments @('pull','bge-m3') -What "ollama pull bge-m3" }
        catch { Write-Warn2 $_.Exception.Message }

    } else {
        # ---------------- NVIDIA / AMD / keine: Standard-Ollama ------------- #
        $ollama = Resolve-OllamaExe
        if (-not $ollama) {
            Write-Warn2 "Ollama ist nicht installiert."
            Write-Info  "Es oeffnet sich die Download-Seite. Bitte den Windows-Installer ausfuehren."
            try { Start-Process 'https://ollama.com/download' } catch { Write-Info "https://ollama.com/download" }
            Read-Host  "    -> Nach der Ollama-Installation hier ENTER druecken"
            $ollama = Resolve-OllamaExe
            if (-not $ollama) {
                Write-Err "Ollama wurde weiterhin nicht gefunden. Bitte installieren und Skript erneut starten."
                exit 1
            }
        }
        Write-Ok "Ollama gefunden: $ollama"

        if (-not (Test-Port -Port 11434)) {
            Write-Info "Starte Ollama-Server ..."
            try { Start-Process -FilePath $ollama -ArgumentList 'serve' -WindowStyle Hidden | Out-Null } catch {}
            if (-not (Wait-Port -Port 11434 -TimeoutSec 60)) {
                Write-Warn2 "Ollama-Server nicht erreichbar - bitte sicherstellen, dass die Ollama-App laeuft."
            }
        }
        if (Test-Port -Port 11434) { Write-Ok "Ollama-Server erreichbar (Port 11434)." }

        Write-Info "Ziehe Embedding-Modell bge-m3 ..."
        try { Invoke-Native -File $ollama -Arguments @('pull','bge-m3') -What "ollama pull bge-m3" }
        catch { Write-Warn2 $_.Exception.Message }
    }

    # ---- 7) recommend: Hardware messen, Modell waehlen/laden/testen -------- #
    if ($SkipRecommend) {
        Write-Step "Modell-Empfehlung uebersprungen (-SkipRecommend)"
    } else {
        Write-Step "Hardware messen und passendes LLM waehlen/laden/testen"
        Write-Info "python -m ragapp.scripts.cli recommend --set --test"
        try {
            & $VenvPy -m ragapp.scripts.cli recommend --set --test
            if ($LASTEXITCODE -ne 0) { throw "recommend endete mit Exit-Code $LASTEXITCODE." }
            Write-Ok "Passendes Modell gewaehlt, getestet und in data/config.json gesetzt."
        } catch {
            Write-Warn2 "Der recommend-Schritt ist nicht durchgelaufen: $($_.Exception.Message)"
            Write-Info  "Das laesst sich spaeter nachholen (siehe Hinweise unten)."
        }
    }

    # ---- 8) IPEX-Server (falls von uns gestartet) wieder beenden ----------- #
    if ($ipexProc -and -not $ipexProc.HasExited) {
        Write-Info "Beende temporaeren IPEX-Server (fuer den Alltag startet ihn Start.bat)."
        try { Stop-Process -Id $ipexProc.Id -Force -ErrorAction SilentlyContinue } catch {}
    }

    # ---- Erfolgsmeldung ---------------------------------------------------- #
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host " Installation abgeschlossen." -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host " So startest du das System:" -ForegroundColor White
    Write-Host "   Doppelklick auf  Start.bat" -ForegroundColor White
    if ($vendor -eq 'intel') {
        Write-Host "   (Start.bat startet automatisch den Intel-GPU-Server und dann die Oberflaeche.)" -ForegroundColor Gray
    } else {
        Write-Host "   (Ollama-App muss laufen; Start.bat oeffnet nur die Oberflaeche.)" -ForegroundColor Gray
    }
    Write-Host ""
    Write-Host " Dokumente einlesen:  .venv\Scripts\python.exe -m ragapp.scripts.cli ingest" -ForegroundColor Gray
    Write-Host " System pruefen:      .venv\Scripts\python.exe -m ragapp.scripts.cli doctor" -ForegroundColor Gray
    if ($SkipRecommend) {
        Write-Host " Modell nachtraeglich waehlen: .venv\Scripts\python.exe -m ragapp.scripts.cli recommend --set --test" -ForegroundColor Gray
    }
    Write-Host ""
}
catch {
    if ($ipexProc -and -not $ipexProc.HasExited) {
        try { Stop-Process -Id $ipexProc.Id -Force -ErrorAction SilentlyContinue } catch {}
    }
    Write-Host ""
    Write-Err "Installation abgebrochen: $($_.Exception.Message)"
    Write-Info "Nach Behebung des Problems kann das Skript einfach erneut gestartet werden (idempotent)."
    exit 1
}
