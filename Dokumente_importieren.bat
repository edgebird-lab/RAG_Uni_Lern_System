@echo off
REM ============================================================
REM  RAG-Lernsystem - Alle Dokumente aus dem Quellordner importieren
REM  Liest "Zusammenfassungen SoSE26" ein (resumierbar - kann erneut
REM  gestartet werden, bereits importierte Dateien werden uebersprungen).
REM ============================================================
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" -u -m ragapp.scripts.cli ingest
echo.
echo Fertig. Fenster kann geschlossen werden.
pause
