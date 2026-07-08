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
#define MyAppVersion "1.0"
#define MyAppPublisher "edgebird-lab"
#define MyAppURL "https://github.com/edgebird-lab/RAG_System"

[Setup]
AppId={{A7F3C2E1-5B4D-4E6A-9C8B-1D2E3F4A5B6C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={localappdata}\{#MyAppName}
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

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; --- App-Code (OHNE .venv, data, ipex-ollama, persoenliche Unterlagen) ---
Source: "ragapp\*";               DestDir: "{app}\ragapp";      Flags: recursesubdirs createallsubdirs
Source: "docs\*.md";              DestDir: "{app}\docs";        Excludes: "Lernkatalog_*.md"; Flags: skipifsourcedoesntexist
Source: ".streamlit\config.toml"; DestDir: "{app}\.streamlit"
Source: "requirements.txt";       DestDir: "{app}"
Source: "install.ps1";            DestDir: "{app}"
Source: "install.sh";             DestDir: "{app}"
Source: "Installieren.bat";       DestDir: "{app}"
Source: "Start.bat";              DestDir: "{app}"
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
Name: "{group}\{#MyAppName} starten";     Filename: "{app}\Start.bat";        WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"
Name: "{group}\Einrichtung ausfuehren";   Filename: "{app}\Installieren.bat"; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"
Name: "{group}\Projektordner oeffnen";    Filename: "{app}"
Name: "{autodesktop}\{#MyAppName}";       Filename: "{app}\Start.bat";        WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"; Tasks: desktopicon

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
