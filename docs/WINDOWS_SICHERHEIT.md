# Windows-Warnungen & Virenscanner (SmartScreen / Defender)

Wer eine unbekannte `.exe` aus dem Internet lädt, bekommt unter Windows fast
immer erst eine Warnung. Das ist **normal** und liegt nicht daran, dass das
Programm Schadsoftware enthält, sondern an zwei getrennten Mechanismen. Diese
Seite erklärt beide – für **Nutzer** (oberer Teil) und für **Maintainer**
(unterer Teil, wie wir das Schritt für Schritt kostenlos entschärfen).

---

## Für Nutzer: „Windows hat Ihren PC geschützt“ – was tun?

**Kurz: Das RAG-Lernsystem ist quelloffen (MIT-Lizenz), lädt nichts heimlich und
schickt keine Daten in die Cloud. Der Quellcode ist vollständig einsehbar.**

Es gibt zwei verschiedene Meldungen:

### 1. SmartScreen „Unbekannter Herausgeber“
Erscheint beim Start der `RAG-Lernsystem-Setup.exe`, weil sie (noch) **nicht
digital signiert** ist. Signatur-Zertifikate kosten Geld/Zeit; solange wir keins
haben, kennt Windows den Herausgeber nicht.

**So geht’s weiter:** Im blauen Fenster auf **„Weitere Informationen“** klicken →
**„Trotzdem ausführen“**.

### 2. Virenscanner meldet einen Fund (Fehlalarm)
Manche Scanner reagieren heuristisch auf typische Installer-Muster (Skripte, die
weitere Software nachladen). Das sind **Fehlalarme** (False Positives).

**So kannst du selbst prüfen, dass alles sauber ist:**
- **Quellcode ansehen:** Das komplette Repository liegt offen auf GitHub.
- **Prüfsumme vergleichen:** Zu jeder Veröffentlichung gehört eine
  `SHA256SUMS.txt`. Vergleiche die Prüfsumme deiner heruntergeladenen Datei:
  ```powershell
  Get-FileHash .\RAG-Lernsystem-Setup.exe -Algorithm SHA256
  ```
  Stimmt der Wert mit der Veröffentlichung überein, wurde die Datei nicht
  verändert.
- **VirusTotal:** Die Release-Seite verlinkt einen VirusTotal-Bericht, der zeigt,
  welche (wenigen) Scanner heuristisch anschlagen und dass es sich um generische
  Fehlalarme handelt.

**Am sichersten:** Statt den fertigen Installer zu nutzen, das Projekt selbst aus
dem Quellcode einrichten (`git clone` + `Installieren.bat`). Dann läuft nur Code,
den du sehen kannst.

---

## Für Maintainer: Vertrauen aufbauen (Reihenfolge nach Aufwand/Kosten)

### Kostenlos & sofort
1. **Kein `Start.vbs` mehr.** Der lautlose Start läuft über
   `pythonw.exe -m ragapp.desktop` (siehe `setup.iss` → `[Icons]`). Das frühere
   VBScript, das ein Fenster versteckt startete, war ein häufiger Fehlalarm-Auslöser
   und wird von Microsoft ohnehin abgekündigt.
2. **Kein PyInstaller-One-File-Bundle.** Wir liefern echten Python-Code + venv
   aus statt einer gepackten `.exe` – das hat eine drastisch niedrigere
   Fehlalarm-Rate. Nicht „vereinfachen“ zu einem Bundle.
3. **Versions-Metadaten** in der Setup.exe (`VersionInfo*` in `setup.iss`) –
   ausgefüllte „Details“-Registerkarte wirkt seriöser.
4. **VirusTotal-Diagnose:** Jede neue `RAG-Lernsystem-Setup.exe` vor Release auf
   <https://www.virustotal.com> hochladen. Notieren, welche Engines was melden
   (meist generische Heuristik wie „Wacatac“, „Trojan:Script/…“).
5. **Fehlalarm melden:**
   - Microsoft Defender: <https://www.microsoft.com/en-us/wdsi/filesubmission>
     → „Submit a file for analysis“ → *I believe this is clean / false positive*.
   - Andere meldende Hersteller: jeweils deren „False Positive“-Formular. Meist
     Bearbeitung in wenigen Tagen. **Nach jeder Version wiederholen** – bis wir
     signieren, dann entfällt es weitgehend.
6. **Prüfsummen veröffentlichen:** `packaging/Pruefsummen-erstellen.ps1` erzeugt
   `SHA256SUMS.txt`; diese der GitHub-Release beilegen und im README verlinken.

### Günstig & mit großer Wirkung: Code-Signatur
Signieren löst **beide** Probleme dauerhaft (SmartScreen + die meisten AV-Heuristiken).

| Option | Kosten | SmartScreen | Für Einzelperson? |
| --- | --- | --- | --- |
| **Azure Trusted Signing** | ~10 €/Monat | gut | ja, in unterstützten Regionen mit ID-Prüfung (Bedingungen prüfen) |
| **Certum Open-Source-Zertifikat** (OV) | ~100–150 €/Jahr inkl. Token | Reputation baut sich über Downloads auf | ja, an Privatpersonen |
| **EV-Zertifikat** | ~300–600 €/Jahr | **sofort** kein Warnscreen | nein – braucht eingetragenes Unternehmen |

- Seit 2023 muss der Schlüssel auf einem **Hardware-Token/HSM** liegen (bei allen
  drei geregelt).
- Aktivierung im Projekt: `SignTool`-Block in `setup.iss` einkommentieren
  (Anleitung steht dort).
- Wenn ein **Gewerbe** angemeldet wird (für den B2B-Vertrieb ohnehin nötig),
  wird das EV-Zertifikat verfügbar → sofort kein blauer Screen mehr.

### Strukturell: Verteilung über Paketmanager
- **winget** (`winget install`): Manifest-Vorlage unter `packaging/winget/`.
  Aufnahme in `microsoft/winget-pkgs` gibt Legitimität und ein sauberes
  Install-Narrativ ohne „.exe von GitHub laden“.
- Optional zusätzlich **Scoop** / **Chocolatey** für die technische Zielgruppe.

### Hinweis B2B
Bei einer **Vor-Ort-Installation** (Kanzlei/Firma) ist das AV-Thema praktisch
kein Blocker – man installiert selbst und kann lokal freigeben. Der Aufwand oben
zahlt v. a. auf den **öffentlichen Open-Source-Download** ein.
