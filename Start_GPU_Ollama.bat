@echo off
REM ============================================================
REM  Ollama auf der Intel-Arc-iGPU starten (IPEX-LLM)
REM  -> schnelle Antworten (gemma3:4b, ~12s statt ~10 Min)
REM  -> schnelle Embeddings (bge-m3, ~8x)
REM
REM  WICHTIG: Diesen Server STATT der normalen Ollama-App starten.
REM  Danach die Oberflaeche mit Start_Oberflaeche.bat oeffnen.
REM  Fenster offen lassen, solange du das System nutzt.
REM ============================================================
cd /d "%~dp0ipex-ollama"
set OLLAMA_NUM_GPU=999
set ZES_ENABLE_SYSMAN=1
set ONEAPI_DEVICE_SELECTOR=level_zero:0
set OLLAMA_HOST=127.0.0.1:11434
set OLLAMA_KEEP_ALIVE=30m
set OLLAMA_NUM_PARALLEL=1
REM Beide Modelle (Embedding bge-m3 + Antwort gemma3:4b) gleichzeitig geladen halten
REM -> kein Modell-Swapping pro Frage (spart ~20s/Antwort)
set OLLAMA_MAX_LOADED_MODELS=2
:restart
echo Starte Ollama auf der Intel-Arc-iGPU (gemma3:4b + bge-m3) ...
echo (Erststart laedt das Modell auf die GPU - einen Moment Geduld.)
ollama.exe serve
echo.
echo [!] Der GPU-Server hat sich beendet (die iGPU-Laufzeit ist experimentell).
echo     Automatischer Neustart in 3 Sekunden ... (Fenster einfach offen lassen)
timeout /t 3 >nul
goto restart
