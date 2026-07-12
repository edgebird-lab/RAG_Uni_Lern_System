; ============================================================================
;  Inno Setup Skript  ->  baut RAG-Lernsystem-Setup.exe (professioneller Assistent)
;  Buendelt den App-Code (kein Download noetig), erstellt Verknuepfungen und
;  bietet am Ende die Option, die Einrichtung (Python-Abhaengigkeiten, Ollama,
;  Modell) auszufuehren. Desktop-Verknuepfung ist ein Haekchen.
;
;  Bauen:  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" setup.iss
;  Ergebnis:  installer\RAG-Lernsystem-Setup.exe
; ============================================================================

#define MyAppName "RAG-Lernsystem"
#define MyAppVersion "1.2"
#define MyAppPublisher "edgebird-lab"
#define MyAppURL "https://github.com/edgebird-lab/RAG_Uni_Lern_System"

[Setup]
AppId={{A7F3C2E1-5B4D-4E6A-9C8B-1D2E3F4A5B6C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppCopyright=Copyright (C) edgebird-lab - MIT License
; Versions-Metadaten in die Setup.exe schreiben. Auch OHNE Signatur reduziert eine
; ausgefuellte "Details"-Registerkarte (Herausgeber/Produkt/Version) SmartScreen-
; Misstrauen und wirkt serioeser. Die eigentliche Vertrauensstufe kommt aber erst
; ueber die Code-Signatur (siehe SignTool-Block weiter unten).
VersionInfoVersion=1.2.0.0
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoProductName={#MyAppName}
VersionInfoDescription={#MyAppName} - lokaler KI-Lernassistent (Installer)
VersionInfoCopyright=Copyright (C) edgebird-lab - MIT License
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer
OutputBaseFilename=RAG-Lernsystem-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=LICENSE
UninstallDisplayName={#MyAppName}
; Eigenes App-Icon: fuer die Setup.exe selbst und den Eintrag in "Apps & Features"
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\assets\icon.ico

; ---------------------------------------------------------------------------
;  CODE-SIGNATUR (aktivieren, sobald ein Zertifikat vorhanden ist)
;  Ohne Signatur zeigt Windows beim Download den "Unbekannter Herausgeber"-
;  Screen (SmartScreen). Eine gueltige Signatur behebt das (bei EV-Zertifikat
;  sofort, bei OV-Zertifikat, sobald Reputation aufgebaut ist).
;
;  1) In Inno Setup unter  Tools -> Configure Sign Tools...  ein Tool anlegen,
;     z. B. Name "signtool", Kommando:
;       signtool sign /fd sha256 /tr http://timestamp.digicert.com /td sha256 $f
;     (bei Azure Trusted Signing stattdessen den dortigen Signaturbefehl.)
;  2) Dann die folgende Zeile einkommentieren:
; SignTool=signtool
;  3) Optional zusaetzlich die entpackten App-Dateien signieren (falls .exe dabei).
; ---------------------------------------------------------------------------

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; --- App-Code (OHNE .venv, data, ipex-ollama, persoenliche Unterlagen) ---
; __pycache__/*.pyc NICHT mitliefern - Python kompiliert beim ersten Start frisch
; (verhindert veralteten Bytecode und haelt den Installer sauber/kleiner).
Source: "ragapp\*";               DestDir: "{app}\ragapp";      Excludes: "*.pyc,*\__pycache__\*"; Flags: recursesubdirs createallsubdirs
Source: "docs\*.md";              DestDir: "{app}\docs";        Excludes: "Lernkatalog_*.md"; Flags: skipifsourcedoesntexist
Source: ".streamlit\config.toml"; DestDir: "{app}\.streamlit"
Source: "requirements.txt";       DestDir: "{app}"
Source: "install.ps1";            DestDir: "{app}"
Source: "install.sh";             DestDir: "{app}"
Source: "Installieren.bat";       DestDir: "{app}"
Source: "Start.bat";              DestDir: "{app}"
Source: "Start_Handy-Zugriff.bat"; DestDir: "{app}"
Source: "Start_Unterwegs.bat";    DestDir: "{app}"
Source: "Start_GPU_Ollama.bat";   DestDir: "{app}"
Source: "Start_Oberflaeche.bat";  DestDir: "{app}"
Source: "Dokumente_importieren.bat"; DestDir: "{app}"
Source: "Auto_Ueberwachung.bat";  DestDir: "{app}"
Source: "README.md";              DestDir: "{app}"
Source: "LICENSE";                DestDir: "{app}"
Source: "NOTICE.md";              DestDir: "{app}"
; App-Icon (fuer Verknuepfungen + Streamlit-Fenster-Favicon)
Source: "assets\icon.ico";        DestDir: "{app}\assets"
Source: "assets\icon.png";        DestDir: "{app}\assets"
; leere Beispiel-Struktur fuer eigene Unterlagen
Source: "Zusammenfassungen\.gitkeep"; DestDir: "{app}\Zusammenfassungen"; Flags: skipifsourcedoesntexist

[Icons]
; Fensterloser Start ueber pythonw.exe (kein Konsolenfenster, kein VBScript).
; pythonw.exe entsteht im venv, das die Einrichtung (Installieren.bat) anlegt.
Name: "{group}\{#MyAppName} starten";       Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: "-m ragapp.desktop"; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"
Name: "{group}\Mit Handy-Zugriff starten";  Filename: "{app}\Start_Handy-Zugriff.bat"; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"
Name: "{group}\Von unterwegs starten";      Filename: "{app}\Start_Unterwegs.bat";     WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"
Name: "{group}\Einrichtung ausfuehren";     Filename: "{app}\Installieren.bat";        WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"
Name: "{group}\Projektordner oeffnen";    Filename: "{app}"
Name: "{autodesktop}\{#MyAppName}";       Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: "-m ragapp.desktop"; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"; Tasks: desktopicon

[Run]
; Am Ende des Assistenten: die eigentliche Einrichtung anbieten (Haekchen).
Filename: "{app}\Installieren.bat"; \
  Description: "Einrichtung jetzt ausfuehren (laedt Python-Abhaengigkeiten, Ollama & Modell - kann 20-40 Min dauern)"; \
  WorkingDir: "{app}"; Flags: postinstall shellexec skipifsilent

[UninstallDelete]
; Bei Deinstallation die lokal erzeugten Ordner mit entfernen
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\data"
Type: filesandordirs; Name: "{app}\ipex-ollama"
Type: filesandordirs; Name: "{app}\__pycache__"
