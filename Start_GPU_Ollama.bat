@echo off
REM ============================================================
REM  Ollama auf der Intel-Arc-iGPU starten (IPEX-LLM) - MANUELL.
REM
REM  HINWEIS: Im Normalbetrieb NICHT noetig! Start.bat (bzw. das
REM  Desktop-Icon) startet den GPU-Server automatisch mit und
REM  beendet ihn beim Schliessen/Beenden wieder. Diese Datei ist
REM  nur ein manueller Einzelstart - OHNE Auto-Neustart-Schleife.
REM ============================================================
cd /d "%~dp0ipex-ollama"
set OLLAMA_NUM_GPU=999
set ZES_ENABLE_SYSMAN=1
set ONEAPI_DEVICE_SELECTOR=level_zero:0
set OLLAMA_HOST=127.0.0.1:11434
set OLLAMA_KEEP_ALIVE=30m
set OLLAMA_NUM_PARALLEL=1
set OLLAMA_MAX_LOADED_MODELS=2

echo Starte Ollama auf der Intel-Arc-iGPU (gemma3:4b + bge-m3) ...
echo (Fenster schliessen = Server beenden. KEIN automatischer Neustart.)
echo.
ollama.exe serve

echo.
echo ============================================================
echo  Ollama-Server beendet. Dieses Fenster kann geschlossen werden.
echo ============================================================
pause
