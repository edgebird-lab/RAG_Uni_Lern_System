@echo off
REM ============================================================
REM  RAG-Lernsystem - Weboberflaeche starten
REM  Oeffnet die Chat-Oberflaeche im Browser (http://localhost:8501)
REM ============================================================
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
echo Starte Oberflaeche ... (Browser oeffnet sich automatisch)
".venv\Scripts\python.exe" -m streamlit run "ragapp\ui\Home.py"
pause
