@echo off
REM ============================================================
REM  RAG-Lernsystem - Starter (Windows)
REM  Startet das lokale KI-Modell (Ollama, GPU wenn moeglich) UND
REM  die Oberflaeche als eigenes App-Fenster. Beides wird von
REM  ragapp.desktop verwaltet und beim Schliessen des Fensters bzw.
REM  ueber den "Beenden"-Button wieder sauber gestoppt - es laeuft
REM  danach NICHTS mehr im Hintergrund weiter.
REM  Nutzt %~dp0 -> voll portabel (kein hartkodierter Pfad).
REM ============================================================
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
echo Starte RAG-Lernsystem (KI-Modell + Oberflaeche) ...
".venv\Scripts\python.exe" -m ragapp.desktop
pause
