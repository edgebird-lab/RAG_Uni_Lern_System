# Handy-/Tablet-Zugriff

Die App vom Smartphone oder Tablet nutzen, solange der PC laeuft. Es gibt drei
Wege. In allen schuetzt ein **PIN** deine Unterlagen (einmal in den
Einstellungen setzen: **Einstellungen -> Handy-Zugriff -> PIN speichern**,
dazu die App einmal normal mit `Start.bat` starten).

> **Plattform-Hinweis:** Der Handy-/Netzwerk-/Tunnel-Zugriff ist die **Windows**-
> Desktop-Variante (die `.bat`-Starter, App laeuft ueber `ragapp.desktop`). Unter
> **Linux/macOS** startet `start.sh` die App bewusst **nur lokal** (Bindung an
> `127.0.0.1`) - dort ist kein PIN noetig, weil von aussen ohnehin niemand
> zugreifen kann. Die hier beschriebenen Ein-Klick-Wege fuer Handy/Tunnel gelten
> also fuer **Windows**.

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
   * Es entsteht ein Tunnel mit einer oeffentlichen `https`-Adresse. TLS sichert
     dabei nur die **Verbindung** (Transport gegen Mitlesen) - die
     **Zugangskontrolle** haengt allein am PIN (siehe Abschnitt „Sicherheit").
2. Adresse + QR-Code stehen in der App unter **Einstellungen -> Handy-Zugriff**.
3. Hinweis: Die Quick-Tunnel-Adresse **aendert sich bei jedem Start**. Fuer
   den kurzen Zugriff unterwegs einfach den frischen QR-Code scannen.

### Kostenlos, anonym, ohne Anmeldung (haeufige Frage)
Genutzt wird ein **TryCloudflare-Quick-Tunnel**. Das ist **kostenlos** und
**anonym**: Es ist **KEIN Cloudflare-Konto** und **KEINE Anmeldung** noetig, es
werden keine Zahlungsdaten hinterlegt. Jeder Nutzer startet auf dem **eigenen
Rechner** seinen **eigenen, kurzlebigen** Tunnel; es entstehen keine Kosten und
niemand bekommt Zugriff auf ein fremdes Konto. Ehrlich dazugesagt: Es ist ein
**Test-Dienst ohne Uptime-Garantie** - fuer den gelegentlichen Zugriff unterwegs
gedacht, nicht fuer Dauerbetrieb. Wer eine feste, zuverlaessige Adresse will, nimmt
den benannten Tunnel (siehe unten, kostenloses Konto noetig).

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

> ### ⚠️ Wichtig im Tunnel-Modus (Weg 2)
> Der oeffentliche Cloudflare-Tunnel macht die App aus dem **GESAMTEN INTERNET**
> erreichbar - der **PIN ist die EINZIGE Barriere**. Daher:
> * **Starken, langen PIN waehlen** (moeglichst viele Stellen, nicht `1234`/`0000`
>   und keine Geburtstage). Ein kurzer PIN ist ueber das offene Netz zu leicht zu
>   erraten.
> * **Die Tunnel-Adresse ist KEIN Geheimnis.** Zufaellige `*.trycloudflare.com`-
>   Adressen tauchen u. a. in oeffentlichen Zertifikats-Logs (Certificate
>   Transparency) auf und werden von Scannern gefunden - verlass dich nicht darauf,
>   dass „die URL ja niemand kennt". Der Schutz kommt allein vom PIN.
> * **Tunnel nur bei Bedarf einschalten** und danach wieder **trennen**
>   („Verbindung trennen" bzw. App beenden). Nicht dauerhaft offen lassen.
> * Zuhause im eigenen WLAN (Weg 1) ist das Risiko deutlich kleiner: Die App ist
>   dann nur im **lokalen Netz** erreichbar, nicht aus dem Internet.

* Der **PIN** ist bei jedem Netzwerk-/Tunnel-Zugriff noetig (im reinen Lokalbetrieb
  nicht).
* Beim ersten Start im WLAN-Modus fragt die **Windows-Firewall** einmal nach ->
  **Zulassen** (privates Netzwerk).
* Der **Beenden**-Button (oder das Schliessen des Fensters) stoppt Oberflaeche,
  KI-Modell **und** den Tunnel wieder vollstaendig - so ist die App nach dem
  Zugriff nicht laenger aus dem Netz erreichbar.
