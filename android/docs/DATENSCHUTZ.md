# Datenschutzerklärung – Local Study AI (Android)

Stand: 2026-10-08 · English version: [PRIVACY.md](PRIVACY.md)

**Anbieter und Verantwortlicher:** edgebird-lab (Robin Olbricht – Olbricht Digital) · **Kontakt:** kontakt@olbricht-digital.de

**Kurz:** Die App verarbeitet alles auf deinem Gerät. Es gibt kein Konto, keine Server des Anbieters, kein Tracking und keine Werbung. Deine Dokumente, Fragen und Karten verlassen das Gerät nicht, es sei denn, du teilst, speicherst oder meldest sie selbst (siehe unten).

## Welche Daten verarbeitet die App?

Die App speichert ausschließlich lokal im privaten App-Speicher: importierte Dokumente samt ihrem Original (PDF, Bild, Textdatei; bei Fotos und Scans ein PDF der Seiten) und ihre Textabschnitte, deine Fächer und Kapitel und die Reihenfolge deiner Quellen, daraus berechnete Suchdaten (Embeddings), Zusammenfassungen samt Einstellungen und eigenen Vorlagen, Chat-Verläufe (mehrere Chats je Fach), Karteikarten mit Lernstand, Ergebnisse von Quiz und Abfragen (je Thema) und die Fokus-Sitzungen des Timers. Die KI (Sprachmodell und Embedding-Modell), die Texterkennung für Fotos (Tesseract) und die Sprachausgabe laufen vollständig auf dem Gerät.

## Netzwerkzugriff

Die App benötigt die Berechtigung „Internet“ ausschließlich, um beim ersten Start und bei Updates die KI-Modelle und die optionalen Stimmenpakete von GitHub (Repository `edgebird-lab/lernsystem-modelle`) zu laden und die Modellliste (`manifest.json`) abzurufen. Dabei werden keine Inhalte aus der App übertragen. Wie jeder Webserver sieht GitHub technisch bedingt deine IP-Adresse und den Zeitpunkt der Anfrage; dafür gilt die Datenschutzerklärung von GitHub.

## Weitergabe

Es werden keine personenbezogenen Daten an den Anbieter oder an Dritte weitergegeben. Es sind keine Analyse-, Absturzberichts- oder Werbe-SDKs eingebunden. Daten verlassen das Gerät nur, wenn du das selbst auslöst:

- **Teilen, Drucken, Speichern, Öffnen in anderer App:** Die gewählte App oder der Drucker erhält die Datei oder den Text. Für deren Umgang gelten deren Bedingungen.
- **Rückmeldung und Meldung von KI-Inhalten:** Die App öffnet einen E-Mail-Entwurf an kontakt@olbricht-digital.de (mit Appversion, Gerätemodell und Android-Version und bei einer Meldung dem gemeldeten Text). Gesendet wird erst, wenn du in deinem E-Mail-Programm auf „Senden“ tippst; vorher kannst du alles ansehen und ändern. Wir nutzen die E-Mail nur, um dein Anliegen zu bearbeiten, und löschen sie, sobald wir sie nicht mehr brauchen.

## KI-Inhalte

Antworten, Zusammenfassungen, Quizfragen und Abfragen erzeugt ein Sprachmodell auf deinem Gerät. Sie können falsch sein oder unpassende Inhalte enthalten. Die App stützt Antworten auf deine Quellen und nennt die Fundstelle; prüfe wichtige Aussagen dort. Unangemessene oder falsche Inhalte kannst du über „Melden“ (Chat, Abfrage, Zusammenfassung) an den Anbieter schicken.

## Berechtigungen

- Benachrichtigungen: Fortschritt von Import und Download, Erinnerungen des Fokus-Timers und die optionale tägliche Lern-Erinnerung.
- Mikrofon (optional): für die Spracheingabe. Die Erkennung läuft mit der Spracherkennung des Geräts **auf dem Gerät**; die App zeichnet nichts auf und sendet nichts. Fehlt das Sprachpaket, kann Android es einmalig laden.
- Fotos: Zum Fotografieren öffnet die App die Kamera-App des Geräts (keine Kamera-Berechtigung nötig). Das Foto und der erkannte Text werden als Quelle gespeichert; die Zwischenbilder werden danach gelöscht.
- Teilen: Du kannst PDFs, Texte und Bilder aus anderen Apps mit Local Study AI teilen; sie werden erst nach deiner Wahl eines Fachs importiert.
- Sprachausgabe (Vorlesen): Die App verwendet ausschließlich ihre **eigene Offline-Stimme** (ein optional geladenes Stimmenpaket, Piper über sherpa-onnx). Das Vorlesen und das Erzeugen von Audiodateien laufen vollständig auf dem Gerät. Online-Stimmen der System-Sprachausgabe werden bewusst nicht benutzt.
- Genaue Alarme (optional): damit das Ende einer Fokusphase pünktlich gemeldet wird.
- Nach Neustart starten: stellt einen laufenden Fokus-Timer wieder her.
- Vordergrunddienst (Datensynchronisierung): lässt Import, Indexierung, Zusammenfassungen und Download bei ausgeschaltetem Display weiterlaufen.

## Deine Rechte

In der App unter *Menü → Datenschutz* kannst du alle deine Daten als JSON **exportieren** (Datenübertragbarkeit) und **vollständig löschen** (Recht auf Löschung). Das Deinstallieren der App entfernt ebenfalls alle Daten. Die App ist von der Android-Datensicherung ausgenommen (`allowBackup=false`), damit keine Inhalte in Cloud-Backups gelangen. Da der Anbieter keine Daten über dich speichert, gibt es dort nichts, worüber wir Auskunft geben könnten; Auskunft, Berichtigung oder Löschung von E-Mails, die du uns geschickt hast, verlangst du unter kontakt@olbricht-digital.de. Du hast das Recht, dich bei einer Datenschutz-Aufsichtsbehörde zu beschweren.

## Quelltext und Lizenz

Die App ist freie Software unter der GNU General Public License (Version 3 oder später). Den Quelltext und die Lizenzen der Bestandteile findest du unter https://github.com/edgebird-lab/RAG_Uni_Lern_System (Ordner `android`) und in der App unter *Menü → Über die App und Lizenz*.

## Änderungen

Wir passen diese Erklärung an, wenn sich die App ändert. Die jeweils gültige Fassung steht im Quelltext-Repository und in der App.

## Kontakt

edgebird-lab (Robin Olbricht – Olbricht Digital), kontakt@olbricht-digital.de
