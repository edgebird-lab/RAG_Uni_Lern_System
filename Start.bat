@echo off
REM ============================================================
REM  RAG-Lernsystem - Starter (Windows, MIT sichtbarem Fenster)
REM  Startet das lokale KI-Modell (Ollama, GPU wenn moeglich) UND
REM  die Oberflaeche als eigenes App-Fenster. Beides wird von
REM  ragapp.desktop verwaltet und beim Schliessen des Fensters bzw.
REM  ueber den "Beenden"-Button wieder sauber gestoppt - es laeuft
REM  danach NICHTS mehr im Hintergrund weiter.
REM
REM  Dies ist der SICHTBARE Starter (mit Konsole) - praktisch zum
REM  Mitlesen/Fehlersuchen. Der lautlose Start ohne Konsolenfenster
REM  laeuft ueber die Verknuepfung (Startmenue/Desktop), die
REM  pythonw.exe -m ragapp.desktop aufruft; die Ausgabe landet dann
REM  in data\app.log. (Fruehere Start.vbs entfaellt - VBScript loeste
REM  haeufig Virenscanner-Fehlalarme aus.)
REM ============================================================
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
if not exist "data" mkdir "data"
".venv\Scripts\python.exe" -m ragapp.desktop > "data\app.log" 2>&1
