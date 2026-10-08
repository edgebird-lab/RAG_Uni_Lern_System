# Phase 9: Qualität und Release-Vorbereitung

Stand 2026-10-08, Pixel 9 Pro XL (Android 17, 16 GB).

## Messwerte (9.2)

| Messung | Wert |
|---|---|
| Kaltstart bis erster Frame (`am start -W`, 3 Läufe) | 520 / 538 / 533 ms |
| Arbeitsspeicher mit geladenem Sprachmodell (PSS) | 2,6 GB (Grafik 1,9 GB, Native 0,4 GB, Java 12 MB) |
| Erster Start nach Neuinstallation | 5 bis 10 Min (GPU-Kompilierung, einmalig) |

Der Akku-Test über 30 Minuten Chat ist **offen**: Am USB-Kabel lädt das Pixel, die Messung wäre wertlos. Er muss mit dem Handy am Akku (per WLAN-adb oder von Hand) laufen.

## Entscheidungen

- **Sprache:** Erstes Release nur Deutsch (UI, KI-Prompts und Eval sind deutsch). Englisch kommt später, dafür müssen alle UI-Texte in Ressourcen und die Prompts übersetzt und neu gemessen werden.
- **Backup:** `allowBackup=false`. Datenbank und Modelle (2,8 GB) gehören nicht in Cloud-Backups; Mitnehmen geht über den JSON-Export.
- **Dark Mode:** folgt dem System, dynamische Farben (Material You).
- **Barrierefreiheit:** Timer-Ring hat eine gesprochene Beschreibung, alle Aktionen sind Schaltflächen mit Text, Schrift skaliert mit der Systemeinstellung. Ein Durchgang mit TalkBack steht noch aus.

## Fehlerbehandlung (9.1)

- Sprachmodell fehlt: Hinweis mit Knopf „Modelle laden“.
- Laden schlägt fehl (auch zu wenig Arbeitsspeicher): Meldung mit Ursache, „Erneut versuchen“, Hinweis auf „Modelle löschen und neu laden“.
- Keine Dokumente: Der Chat sagt, dass erst importiert werden muss.
- Abbruch mitten im Import: Das Speichern ist eine Datenbank-Transaktion; Reste im Eingangsordner werden nach 24 Stunden entfernt.

## Offen und nur mit deinem Play-Console-Konto möglich

- 9.5 Geschlossener Test (interne Testspur)
- 9.6 Store-Eintrag: Screenshots, Beschreibung, Content-Rating, Data-Safety-Formular (Antworten: keine Daten erhoben oder geteilt; Internet nur für Modell-Download), App Bundle signieren (Upload-Schlüssel anlegen und sicher aufbewahren), Datenschutzerklärung unter öffentlicher URL ([DATENSCHUTZ.md](DATENSCHUTZ.md), Kontaktzeile ausfüllen)
- 9.7 Veröffentlichung
