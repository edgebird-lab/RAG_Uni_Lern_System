@echo off
REM ============================================================
REM  RAG-Lernsystem - Start MIT Handy-/Tablet-Zugriff
REM  Macht die App im Netzwerk erreichbar (WLAN + Tailscale) und
REM  aktiviert die PIN-Sperre. Adresse + QR-Code stehen danach in
REM  der App unter Einstellungen -> Handy-Zugriff.
REM  (PIN vorher einmal ueber Start.bat + Einstellungen setzen.)
REM ============================================================
setlocal
cd /d "%~dp0"
set RAG_BIND_HOST=0.0.0.0
set RAG_NETWORK=1

REM Windows-Firewall: Port 8501 im privaten Netz erlauben (falls Adminrechte
REM vorhanden; sonst fragt Windows beim ersten Start einmal nach -> "Zulassen").
netsh advfirewall firewall show rule name="RAG-Lernsystem 8501" >nul 2>&1 || netsh advfirewall firewall add rule name="RAG-Lernsystem 8501" dir=in action=allow protocol=TCP localport=8501 >nul 2>&1

echo ============================================================
echo   RAG-Lernsystem - Handy-/Tablet-Zugriff AKTIV
echo   Die App ist jetzt auch im Netzwerk erreichbar.
echo   Adresse + QR-Code:  in der App unter
echo   Einstellungen  -^>  Handy-Zugriff
echo ============================================================
call "%~dp0Start.bat"
