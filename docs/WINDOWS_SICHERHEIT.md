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

## Netzwerk- & Fernzugriff: das größte reale Risiko

Der Virenscanner-Alarm oben ist meist ein **Fehlalarm**. Das **eigentliche**
Sicherheitsthema im Alltag ist der optionale **Fernzugriff** (Handy/unterwegs) über
den Cloudflare-Tunnel – denn der öffnet die App bewusst nach außen.

> ### ⚠️ Wenn du den „Unterwegs"-Modus (Cloudflare-Tunnel) nutzt
> Mit `Start_Unterwegs.bat` wird die App über eine öffentliche
> `*.trycloudflare.com`-Adresse aus dem **GESAMTEN INTERNET** erreichbar. Das TLS
> des Tunnels verschlüsselt nur den **Transport** – die **einzige Zugangssperre ist
> der PIN**. Deshalb:
> * **Langen, starken PIN** setzen (nicht `1234`/`0000`, kein Geburtstag). Er ist
>   die einzige Hürde zwischen dem Internet und all deinen Unterlagen samt lokalem
>   KI-Modell.
> * Die zufällige Tunnel-**Adresse ist KEIN Geheimnis** (u. a. über
>   Zertifikats-Transparenz-Logs auffindbar) – niemals als Schutz werten.
> * Den **Tunnel nur bei Bedarf** einschalten und danach **trennen / App beenden**.
>   Der Beenden-Button stoppt Oberfläche, KI-Modell **und** Tunnel vollständig.

Der Tunnel ist ein **kostenloser, anonymer TryCloudflare-Quick-Tunnel** (kein
Cloudflare-Konto, keine Anmeldung, pro Rechner ein eigener kurzlebiger Tunnel – ein
Test-Dienst ohne Uptime-Garantie). Es entstehen also keine Kosten und niemand
erhält Zugriff auf ein fremdes Konto; das Expositions-Risiko liegt allein in der
Erreichbarkeit aus dem Netz.

**Nur zuhause im WLAN** (`Start_Handy-Zugriff.bat`) ist die App lediglich im
**lokalen Netz** erreichbar, nicht aus dem Internet – deutlich risikoärmer, aber
auch hier bleibt der PIN Pflicht. Im **reinen Lokalbetrieb** (`Start.bat`, ohne
Handy-Zugriff) verlässt nichts den Rechner.

> **Technischer Hinweis (Windows):** Der Windows-Starter bindet den Port aus
> praktischen Gründen immer an alle Schnittstellen (`0.0.0.0`) – so ist beim
> Wechsel zwischen lokal/Netzwerk/Tunnel kein Neustart nötig. Der **Seiteninhalt**
> bleibt im Lokalmodus gesperrt („Zugriff nicht aktiv"), der Port selbst ist im LAN
> aber sichtbar. Wer das ausschließen will, lässt den Handy-Zugriff aus und/oder
> blockt den Port in der Windows-Firewall für andere Geräte. (Unter Linux/macOS
> bindet `start.sh` bereits fest an `127.0.0.1`.)

Schritt-für-Schritt-Anleitung und weitere Hinweise:
[HANDY_ZUGRIFF.md](HANDY_ZUGRIFF.md).

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
