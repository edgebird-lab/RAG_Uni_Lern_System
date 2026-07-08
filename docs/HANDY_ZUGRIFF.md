# Handy-/Tablet-Zugriff

Die App vom Smartphone oder Tablet nutzen, solange der PC laeuft. Es gibt drei
Wege. In allen schuetzt ein **PIN** deine Unterlagen (einmal in den
Einstellungen setzen: **Einstellungen -> Handy-Zugriff -> PIN speichern**,
dazu die App einmal normal mit `Start.bat` starten).

## 1. Zuhause im gleichen WLAN (am einfachsten)
1. Die App normal starten (`Start.bat`).
2. Unter **Einstellungen -> Handy-Zugriff** einen **PIN** setzen und auf
   **"Mit Smartphone verbinden"** klicken. Der Server startet kurz neu (das
   Fenster verbindet sich automatisch wieder).
3. Adresse und **QR-Code** erscheinen dort. Mit dem Handy scannen.
4. Fertig. Kein Internet, kein Dienst noetig. Mit **"Verbindung trennen"** geht
   es wieder auf nur-lokal zurueck.

(Alternativ direkt im Netzmodus starten: `Start_Handy-Zugriff.bat`.)

## 2. Von unterwegs (Cloudflare-Tunnel)
1. App mit **`Start_Unterwegs.bat`** starten.
   * `cloudflared` wird beim ersten Mal automatisch per winget installiert.
   * Es entsteht ein sicherer Tunnel mit einer oeffentlichen `https`-Adresse.
2. Adresse + QR-Code stehen in der App unter **Einstellungen -> Handy-Zugriff**.
3. Hinweis: Die Quick-Tunnel-Adresse **aendert sich bei jedem Start**. Fuer
   den kurzen Zugriff unterwegs einfach den frischen QR-Code scannen.

## 3. Als App aufs Handy (PWA / "Pseudo-App")
Egal ob Weg 1 oder 2: Adresse am Handy im Browser oeffnen, dann im Browser-Menue
**"Zum Home-Bildschirm hinzufuegen"**. Es erscheint ein App-Icon, das die
Oberflaeche **randlos** wie eine echte App oeffnet.

## Feste Adresse von unterwegs (optional, einmalige Einrichtung)
Der Quick-Tunnel aus Weg 2 vergibt bei jedem Start eine neue Adresse. Wer eine
**dauerhaft gleiche** Adresse will (damit die installierte PWA immer passt),
richtet einen **benannten Cloudflare-Tunnel** ein (kostenloses Cloudflare-Konto
noetig):

```
cloudflared tunnel login
cloudflared tunnel create rag-lernsystem
cloudflared tunnel route dns rag-lernsystem lernsystem.deine-domain.tld
cloudflared tunnel run --url http://localhost:8501 rag-lernsystem
```

Dann ist die App dauerhaft unter `https://lernsystem.deine-domain.tld` erreichbar.

## Sicherheit
* Der **PIN** ist bei jedem Netzwerk-/Tunnel-Zugriff noetig.
* Beim ersten Start im WLAN-Modus fragt die **Windows-Firewall** einmal nach ->
  **Zulassen** (privates Netzwerk).
* Der **Beenden**-Button (oder das Schliessen des Fensters) stoppt Oberflaeche,
  KI-Modell **und** den Tunnel wieder vollstaendig.
