@echo off
REM ============================================================
REM  Build_Setup.bat - Installer-EXE neu bauen (Windows)
REM  Kompiliert setup.iss mit Inno Setup (ISCC.exe) und kopiert
REM  die fertige RAG-Lernsystem-Setup.exe automatisch in den
REM  Downloads-Ordner - so ist sie immer an 2 Stellen aktuell:
REM    1) installer\RAG-Lernsystem-Setup.exe   (Projekt)
REM    2) %USERPROFILE%\Downloads\...           (zum Weitergeben)
REM  Voraussetzung: Inno Setup 6 ist installiert. Falls nicht:
REM    winget install --id JRSoftware.InnoSetup -e
REM  Hinweis: Vor dem Bauen die Version in setup.iss anheben, wenn
REM  sich der neue Build klar unterscheiden soll (MyAppVersion).
REM ============================================================
setlocal
cd /d "%~dp0"

REM --- ISCC.exe suchen (User-Installation zuerst, dann Standardpfade) ---
set "ISCC="
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not defined ISCC (
  echo [X] Inno Setup ^(ISCC.exe^) wurde nicht gefunden.
  echo     Bitte installieren:  winget install --id JRSoftware.InnoSetup -e
  echo.
  pause
  exit /b 1
)

echo ============================================================
echo    Installer wird gebaut ...
echo    ISCC: "%ISCC%"
echo ============================================================
echo.
"%ISCC%" setup.iss
if errorlevel 1 (
  echo.
  echo [X] Build fehlgeschlagen ^(siehe Meldungen oben^).
  echo.
  pause
  exit /b 1
)

set "EXE=%~dp0installer\RAG-Lernsystem-Setup.exe"
if not exist "%EXE%" (
  echo [X] Erwartete Datei nicht gefunden: "%EXE%"
  echo.
  pause
  exit /b 1
)

REM --- fertige EXE nach Downloads kopieren ---
set "DEST=%USERPROFILE%\Downloads"
copy /y "%EXE%" "%DEST%\RAG-Lernsystem-Setup.exe" >nul
if errorlevel 1 (
  echo [!] Kopieren nach "%DEST%" fehlgeschlagen - EXE liegt aber in installer\.
) else (
  echo [OK] Kopiert nach: "%DEST%\RAG-Lernsystem-Setup.exe"
)

echo.
echo ============================================================
echo    Fertig. Die aktuelle Setup.exe liegt jetzt in:
echo      1^) installer\RAG-Lernsystem-Setup.exe   ^(Projekt^)
echo      2^) %DEST%\RAG-Lernsystem-Setup.exe
echo ============================================================
pause
endlocal
