# ============================================================================
#  SHA256SUMS.txt fuer die Release-Dateien erzeugen.
#  Aufruf (aus dem Projektordner):
#      powershell -NoProfile -ExecutionPolicy Bypass -File packaging\Pruefsummen-erstellen.ps1
#  Ergebnis: installer\SHA256SUMS.txt  (der GitHub-Release beilegen).
#  Nutzer koennen damit pruefen, dass ihr Download unveraendert ist:
#      Get-FileHash .\RAG-Lernsystem-Setup.exe -Algorithm SHA256
# ============================================================================
$ErrorActionPreference = "Stop"

# Projektwurzel = ein Ordner ueber diesem Skript.
$root = Split-Path -Parent $PSScriptRoot
$installerDir = Join-Path $root "installer"
$out = Join-Path $installerDir "SHA256SUMS.txt"

if (-not (Test-Path $installerDir)) {
    Write-Error "Ordner 'installer' nicht gefunden. Zuerst die Setup.exe bauen (ISCC.exe setup.iss)."
}

# Alle veroeffentlichbaren Artefakte einsammeln (Setup.exe; bei Bedarf erweitern).
$files = Get-ChildItem -Path $installerDir -File |
    Where-Object { $_.Extension -in @(".exe", ".zip") }

if (-not $files) {
    Write-Error "Keine .exe/.zip in 'installer' gefunden."
}

$lines = foreach ($f in $files) {
    $hash = (Get-FileHash $f.FullName -Algorithm SHA256).Hash.ToLower()
    Write-Host ("{0}  {1}" -f $hash, $f.Name)
    "{0}  {1}" -f $hash, $f.Name
}

# Bewusst UTF-8 ohne BOM, damit die Datei plattformuebergreifend sauber ist.
$enc = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($out, ($lines -join "`n") + "`n", $enc)

Write-Host ""
Write-Host "Geschrieben: $out"
