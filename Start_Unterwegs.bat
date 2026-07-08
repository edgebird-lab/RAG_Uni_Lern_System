@echo off
REM ============================================================
REM  RAG-Lernsystem - Start MIT Zugriff von UNTERWEGS (Cloudflare)
REM  Baut einen sicheren Cloudflare-Tunnel auf: die App bekommt eine
REM  oeffentliche https-Adresse. Adresse + QR-Code stehen dann in der
REM  App unter Einstellungen -> Handy-Zugriff. Die PIN-Sperre ist aktiv.
REM  cloudflared wird beim ersten Mal automatisch via winget installiert.
REM  (Hinweis: Die Adresse aendert sich pro Start - fuer eine feste
REM   Adresse siehe docs/HANDY_ZUGRIFF.md, benannter Tunnel.)
REM ============================================================
setlocal
cd /d "%~dp0"

where cloudflared >nul 2>&1
if not errorlevel 1 goto have_cf
echo cloudflared wird installiert (einmalig, via winget) ...
where winget >nul 2>&1
if errorlevel 1 goto no_winget
winget install --id Cloudflare.cloudflared -e --silent --accept-source-agreements --accept-package-agreements
set "PATH=%PATH%;%LOCALAPPDATA%\Microsoft\WinGet\Links"
goto have_cf
:no_winget
echo [!] winget nicht gefunden. Bitte cloudflared manuell installieren:
echo     https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
:have_cf

set RAG_BIND_HOST=0.0.0.0
set RAG_NETWORK=1
set RAG_TUNNEL=1
echo ============================================================
echo   RAG-Lernsystem - Zugriff von UNTERWEGS (Cloudflare) AKTIV
echo   Oeffentliche Adresse + QR-Code:  in der App unter
echo   Einstellungen  -^>  Handy-Zugriff
echo   (PIN vorher setzen. Adresse aendert sich pro Start.)
echo ============================================================
call "%~dp0Start.bat"
