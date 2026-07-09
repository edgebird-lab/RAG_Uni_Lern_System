# winget-Paket (Vorlage)

Diese drei Manifeste ermöglichen später `winget install edgebird-lab.RAG-Lernsystem`.
Die Aufnahme in winget gibt dem Download Legitimität (Microsoft moderiert die
Manifeste) und ein sauberes Install-Narrativ statt „.exe von GitHub laden".

## Vor dem Einreichen

1. **GitHub-Release erstellen** und die `RAG-Lernsystem-Setup.exe` anhängen.
2. **Prüfsumme** holen: `packaging\Pruefsummen-erstellen.ps1` ausführen →
   Wert aus `installer\SHA256SUMS.txt` (in GROSSBUCHSTABEN) in
   `*.installer.yaml` bei `InstallerSha256` eintragen.
3. Alle `<VERSION>`-, `<URL>`- und `<SHA256>`-Platzhalter ersetzen.
4. Lokal prüfen:
   ```powershell
   winget validate --manifest packaging\winget
   winget install --manifest packaging\winget   # Testinstallation
   ```

## Einreichen

- Fork von <https://github.com/microsoft/winget-pkgs>, die drei Dateien nach
  `manifests/e/edgebird-lab/RAG-Lernsystem/<VERSION>/` legen, Pull Request öffnen.
- Alternativ mit `wingetcreate` (`winget install Microsoft.WingetCreate`) den
  PR halbautomatisch erzeugen.

## Hinweis

Der Installer bringt nur den App-Code mit. Python-Abhängigkeiten, Ollama und das
Modell lädt anschließend die Einrichtung (`Installieren.bat`) – wie beim direkten
`.exe`-Download auch. Voraussetzung bleibt **Python 3.10+**.
