@echo off
REM ============================================================
REM  RAG-Lernsystem - Automatische Ordnerueberwachung
REM  Neue/geaenderte Dateien im Quell- oder data\inbox-Ordner werden
REM  automatisch importiert. Beenden mit Strg+C.
REM ============================================================
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" -u -m ragapp.scripts.cli watch
pause
