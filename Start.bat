@echo off
REM ============================================================
REM  RAG-Lernsystem - Starter (Windows)
REM  Startet das lokale KI-Modell (Ollama, GPU wenn moeglich) UND
REM  die Oberflaeche als eigenes App-Fenster. Beides wird von
REM  ragapp.desktop verwaltet und beim Schliessen des Fensters bzw.
REM  ueber den "Beenden"-Button wieder sauber gestoppt - es laeuft
REM  danach NICHTS mehr im Hintergrund weiter.
REM
REM  Wird im Normalbetrieb ueber Start.vbs (Desktop-Icon) UNSICHTBAR
REM  im Hintergrund gestartet - kein Konsolenfenster. Die Ausgabe
REM  landet in data\app.log (nur fuer den Fehlerfall). Kein 'pause':
REM  beim Beenden der App endet auch dieser Prozess.
REM ============================================================
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
if not exist "data" mkdir "data"
".venv\Scripts\python.exe" -m ragapp.desktop > "data\app.log" 2>&1
