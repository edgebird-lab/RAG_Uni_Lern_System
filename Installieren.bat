@echo off
REM ============================================================
REM  RAG-Lernsystem - Installation per Doppelklick (Windows)
REM  Startet install.ps1 mit erlaubter Skript-Ausfuehrung.
REM  (PowerShell-Skripte .ps1 laufen sonst nicht per Doppelklick,
REM   sondern oeffnen nur im Editor - dieser Wrapper loest das.)
REM  Voraussetzung: Python 3.10+ ist installiert (python.org).
REM ============================================================
cd /d "%~dp0"
echo ============================================================
echo    RAG-Lernsystem wird installiert ...
echo    (Das kann 20-40 Minuten dauern - vor allem Downloads.)
echo ============================================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
echo.
echo ============================================================
echo    Installation beendet. Fenster kann geschlossen werden.
echo    Starten mit:  Start.bat  (Doppelklick)
echo ============================================================
pause
