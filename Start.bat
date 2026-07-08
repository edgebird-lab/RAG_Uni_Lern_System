@echo off
REM ============================================================
REM  RAG-Lernsystem - Kombi-Starter (Windows)
REM  - Intel-Variante (ipex-ollama\ollama.exe vorhanden):
REM      startet den IPEX-GPU-Server (Start_GPU_Ollama.bat) in
REM      eigenem Fenster, wartet auf Port 11434, dann Oberflaeche.
REM  - Sonst (NVIDIA/AMD/CPU): nimmt an, dass die Ollama-App laeuft,
REM      und startet nur die Weboberflaeche.
REM  Nutzt %~dp0 -> voll portabel (kein hartkodierter Pfad).
REM ============================================================
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

if not exist "%~dp0ipex-ollama\ollama.exe" goto start_ui

echo [Intel-GPU erkannt] IPEX-Ollama-Server (GPU) wird gestartet.
REM Alte Ollama-Instanzen beenden, damit garantiert der GPU-Server laeuft
REM (und nicht versehentlich eine CPU-Ollama-App auf Port 11434).
taskkill /F /IM "ollama.exe" >nul 2>&1
taskkill /F /IM "ollama app.exe" >nul 2>&1
timeout /t 1 >nul
echo Starte IPEX-Ollama-Server in eigenem Fenster ...
start "IPEX-Ollama (GPU) - NICHT schliessen" "%~dp0Start_GPU_Ollama.bat"
echo Warte, bis der GPU-Server bereit ist (Port 11434) ...
powershell -NoProfile -Command "for($t=0; $t -lt 90; $t++){ $c=New-Object Net.Sockets.TcpClient; try { $c.Connect('127.0.0.1',11434); exit 0 } catch { Start-Sleep -Milliseconds 1000 } finally { $c.Close() } }; exit 1"
if not errorlevel 1 goto gpu_ready
echo [!] GPU-Server nicht erreichbar geworden - starte Oberflaeche trotzdem.
echo     Antworten laufen dann ggf. auf der CPU.
goto start_ui

:gpu_ready
echo    -^> GPU-Server bereit.

:start_ui
if not exist "%~dp0ipex-ollama\ollama.exe" echo [Standard-Ollama] Es wird angenommen, dass die Ollama-App laeuft.
echo Starte Oberflaeche als App-Fenster (kein Browser-Tab) ...
".venv\Scripts\python.exe" -m ragapp.desktop
pause
