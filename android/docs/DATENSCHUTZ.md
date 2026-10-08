# Datenschutzerklärung – Lernsystem (Android)

Stand: 2026-10-08

**Kurz:** Die App verarbeitet alles auf deinem Gerät. Es gibt kein Konto, keine Server des Anbieters, kein Tracking und keine Werbung. Deine Dokumente, Fragen und Karten verlassen das Gerät nicht.

## Welche Daten verarbeitet die App?

Die App speichert ausschließlich lokal im privaten App-Speicher: importierte Dokumente (auch aus Fotos und Scans) und ihre Textabschnitte, daraus berechnete Suchdaten (Embeddings), Zusammenfassungen samt Einstellungen und eigenen Vorlagen, Karteikarten mit Lernstand, Ergebnisse der Abfragen (je Thema), Chat-Verläufe der laufenden Sitzung (nicht dauerhaft) und die Fokus-Sitzungen des Timers. Die KI (Sprachmodell und Embedding-Modell) sowie die Texterkennung für Fotos laufen vollständig auf dem Gerät.

## Netzwerkzugriff

Die App benötigt die Berechtigung „Internet“ ausschließlich, um beim ersten Start und bei Updates die KI-Modelle von GitHub (Repository `edgebird-lab/lernsystem-modelle`) zu laden und die Modellliste (`manifest.json`) abzurufen. Dabei werden keine Inhalte aus der App übertragen. Wie jeder Webserver sieht GitHub technisch bedingt deine IP-Adresse und den Zeitpunkt der Anfrage; dafür gilt die Datenschutzerklärung von GitHub.

## Weitergabe

Es werden keine personenbezogenen Daten an den Anbieter oder an Dritte weitergegeben. Es sind keine Analyse-, Absturzberichts- oder Werbe-SDKs eingebunden.

## Berechtigungen

- Benachrichtigungen: Fortschritt von Import und Download, Erinnerungen des Fokus-Timers und die optionale tägliche Lern-Erinnerung.
- Mikrofon (optional): für die Spracheingabe. Die Erkennung läuft mit der Spracherkennung des Geräts **auf dem Gerät**; es wird nichts aufgezeichnet oder gesendet.
- Fotos: Zum Fotografieren öffnet die App die Kamera-App des Geräts (keine Kamera-Berechtigung nötig). Die Bilder bleiben im Zwischenspeicher der App und werden nach dem Erkennen des Textes gelöscht.
- Teilen: Du kannst PDFs, Texte und Bilder aus anderen Apps mit dem Lernsystem teilen; sie werden erst nach deiner Wahl eines Fachs importiert.
- Sprachausgabe (Vorlesen): nutzt die Sprachausgabe des Geräts. Ist eine deutsche **Offline-Stimme** installiert, läuft alles lokal. Fehlt sie, kann der Sprachdienst des Geräteherstellers (z. B. Google) eine Online-Stimme verwenden; dann wird der vorzulesende Text zur Sprachsynthese an diesen Dienst gesendet. Die App weist darauf hin. Wer das vermeiden will, installiert eine Offline-Stimme in den Android-Einstellungen unter Sprachausgabe oder nutzt Vorlesen nicht.
- Genaue Alarme (optional): damit das Ende einer Fokusphase pünktlich gemeldet wird.
- Nach Neustart starten: stellt einen laufenden Fokus-Timer wieder her.
- Vordergrunddienst (Datensynchronisierung): lässt Import, Indexierung und Download bei ausgeschaltetem Display weiterlaufen.

## Deine Rechte

In der App unter *Dokumente → Datenschutz* kannst du alle deine Daten als JSON **exportieren** (Datenübertragbarkeit) und **vollständig löschen** (Recht auf Löschung). Das Deinstallieren der App entfernt ebenfalls alle Daten. Die App ist von der Android-Datensicherung ausgenommen (`allowBackup=false`), damit keine Inhalte in Cloud-Backups gelangen.

## Kontakt

[Name und Kontakt-E-Mail des Anbieters hier eintragen, bevor die Erklärung veröffentlicht wird]
