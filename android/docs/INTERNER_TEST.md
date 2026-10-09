# Interner Test auf Google Play (Version 0.1.0)

Stand 2026-10-08. Das signierte App Bundle liegt nach `./gradlew :app:bundleRelease` unter `app/build/outputs/bundle/release/app-release.aab`
(Paketname `de.edgebird.lernsystem`, Version 0.1.0, Versionscode 1, nur arm64, rund 37 MB; die KI-Modelle lädt die App nach der Installation selbst).

## Was hochgeladen wird

- **Datei:** `app-release.aab` (App Bundle, kein APK).
- **Signierung:** Das Bundle ist mit dem **Upload-Schlüssel** signiert (`~/lernsystem-upload-key/upload.jks`, Zugangsdaten in `keystore.properties`; beides **nicht** im Repo).
  Google signiert die App für die Nutzer danach mit dem eigenen App-Signaturschlüssel („Play App Signing“, beim ersten Hochladen aktivieren).
  **Den Ordner `~/lernsystem-upload-key/` an einem zweiten Ort sichern** (Passwortmanager oder USB-Stick). Geht der Upload-Schlüssel verloren, lässt er sich über den Play-Support zurücksetzen, das dauert aber.
- **Neue Fassung:** vor jedem weiteren Upload `versionCode` in `app/build.gradle.kts` um 1 erhöhen (Google lehnt gleiche Codes ab).

## Schritte in der Play Console

1. App anlegen (Name „Local Study AI“, Standardsprache Deutsch, App, kostenlos).
2. **Test → Interner Test → Neue Version erstellen**, Play App Signing akzeptieren, `app-release.aab` hochladen.
3. Versionshinweise einfügen (Text unten), **Tester** anlegen: Eine E-Mail-Liste (bis zu 100 Adressen, Google-Konten) erstellen und der Spur zuweisen.
4. Version prüfen und für den internen Test freigeben. Der interne Test braucht **keine** Prüfung durch Google und ist meist nach wenigen Minuten verfügbar.
5. Den **Opt-in-Link** der Spur an die Tester schicken; sie installieren die App darüber aus dem Play Store.
6. Für den internen Test reichen die Pflichtangaben der App (Datenschutzerklärung-URL, Data safety, Zielgruppe, Anzeigen: keine). Screenshots und Store-Texte werden erst für den geschlossenen/offenen Test bzw. die Veröffentlichung verlangt.

Hinweis: Für neue private Entwicklerkonten verlangt Google vor der Produktion einen **geschlossenen Test** (mindestens 12 Tester über 14 Tage). Der interne Test zählt dafür nicht, der geschlossene schon.

## Versionshinweise (Deutsch, für „Was ist neu“, höchstens 500 Zeichen)

```
<de-DE>
Erste Testversion von Local Study AI: Dokumente (PDF, Word, PowerPoint, Text, Fotos) importieren, per Chat mit Quellenangaben befragen, Karteikarten, Quiz und Probeklausur, Zusammenfassungen, sokratische Abfragen, Fokus-Timer. Alles läuft auf dem Handy, nichts wird hochgeladen. Beim ersten Start lädt die App einmalig die KI-Modelle (2,8 GB, am besten im WLAN); der erste Start danach dauert 5 bis 10 Minuten. Bitte Fehler und Wünsche melden. Deutsch und Englisch.
</de-DE>
```

## Versionshinweise (Englisch)

```
<en-US>
First test version of Local Study AI: import documents (PDF, Word, PowerPoint, text, photos), ask questions in a chat with source references, flashcards, quiz and mock exam, summaries, Socratic Q&A, focus timer. Everything runs on your phone, nothing is uploaded. On first start the app downloads the AI models once (2.8 GB, Wi-Fi recommended); the first start afterwards takes 5 to 10 minutes. Please report bugs and wishes. German and English.
</en-US>
```

## Was die Tester wissen sollten

- Voraussetzung: Android 12 oder neuer, 64-Bit-ARM, mindestens 6 GB Arbeitsspeicher (am besten 8 GB oder mehr), rund 4 GB freier Speicher. Ohne GPU-fähiges Gerät ist die KI sehr langsam.
- Der erste Start nach dem Modell-Download dauert 5 bis 10 Minuten (die Grafikeinheit wird einmalig eingerichtet): Display an lassen, App offen halten.
- Zum Testen, wo es am ehrlichsten ist: eigene Unterlagen importieren, Fragen stellen, Antworten mit der Quelle vergleichen; Quiz, Zusammenfassung und Abfragen ausprobieren; Sprache umstellen.
- Optional: Stimme zum Vorlesen (Zusatzpaket, enthält GPL-Daten) unter „KI-Modelle“.
- Rückmeldungen an die Kontaktadresse aus der Datenschutzerklärung.

## Geprüft vor dem ersten Bundle (Release-Build mit R8 auf dem Pixel, als eigene App neben der Entwicklerversion)

- Erststart, Modell-Download (Fortsetzen nach Abbruch), Import per Teilen, Chat mit Quellenangabe, Stimme laden und abspielen: laufen.
- Dabei gefundene und behobene Fehler: (1) Der Modell-Download brach mit einem Null-Fehler ab, weil neue Manifest-Felder keinen Standardwert hatten; (2) im Release-Build stürzte der erste Chat ab, weil R8 Klassen umbenannte, die LiteRT-LM aus nativem Code aufruft (Regeln in `app/proguard-rules.pro`).
- Die Texterkennung läuft mit Tesseract (Apache-2.0, ersetzt ML Kit, weil dessen Lizenz nicht zur GPL passt); sie wurde im Release-Build per Teilen-Import geprüft. Widget und Import eines PDFs (Pdfium) bitte im internen Test gezielt ausprobieren. Zum schnellen Ausprobieren gibt es auf der leeren Startseite „Mit einem Beispiel ausprobieren“.

## Offene Pflichtangaben

- **Datenschutzerklärung:** Anbieter und Kontakt (edgebird-lab, kontakt@olbricht-digital.de) sind eingetragen. Play verlangt eine öffentlich erreichbare URL; solange das Repo öffentlich ist und `main` gepusht wurde, ist es `https://github.com/edgebird-lab/RAG_Uni_Lern_System/blob/main/android/docs/DATENSCHUTZ.md`.
- **Data safety:** keine Daten erhoben oder geteilt; Internet nur für den Download der Modelle und Stimmen.

- Alle weiteren Angaben der Play Console (Beschreibungen, Einstufung, Vordergrunddienst, genaue Alarme, Geräteausschluss, Screenshots): siehe [STORE_EINTRAG.md](STORE_EINTRAG.md).
- **Lizenz:** Die App steht unter GPL-3.0-or-later; der Quelltext zur Version liegt unter dem Tag `android-v0.1.0` im öffentlichen Repo.
