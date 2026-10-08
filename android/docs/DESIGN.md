# Design und Navigation (Feinschliff-Phase)

Stand 2026-10-08. Entscheidungen nach Sichtung von NotebookLM (Web und App): Dort ist ein **Notizbuch** der Einstieg; darin liegen **Quellen**, **Chat** und **Studio** (Zusammenfassungen, Audio). Auf dem Handy sind es drei Bereiche in einer unteren Leiste. Die Chat-Antworten stützen sich nur auf die **angehakten Quellen**.

## Übernommen, aber angepasst

| NotebookLM | Lernsystem |
|---|---|
| Notizbuch | **Fach** (heißt schon so in der PC-App). Jedes Dokument gehört zu genau einem Fach. |
| Quellen anhaken, Chat nutzt nur diese | Gleich. Ersetzt den geplanten Filter „Fach oder Dokument“: Alles angehakt = ganzes Fach, ein Haken = ein Dokument. |
| Studio (Audio, Mindmap, Berichte) | **Studio**: Zusammenfassungen (Kurz, Ausführlich, Stichpunkte) je Quelle und für das ganze Fach. Audio bleibt ein späterer Ausbau. |
| nur Chat und Berichte | Zusätzlich unser Kern: **Lernen** mit Karteikarten (FSRS) und **Abfragen** (sokratischer Dialog). Das ist unser Alleinstellungsmerkmal, deshalb ein eigener Bereich. |
| Startseite mit Notizbuch-Karten | Startseite „Meine Fächer“ mit Tagesstreifen (fällige Karten, Fokus-Minuten, Serie). |

## Aufbau

```
Start (Fächer)  ──►  Fach
  Tagesstreifen        Kopf: Fachname in Fachfarbe, Fokus-Chip
  Fach-Karten          Untere Leiste:  Quellen | Chat | Lernen | Studio
  + Neues Fach
  Menü: KI-Modelle, Datenschutz, Fokus
```

- **Quellen:** Liste mit Häkchen, Import, Umbenennen, Verschieben, Löschen, Suche.
- **Chat:** Kopfzeile „3 von 5 Quellen“ (tippen = Auswahl), Eingabe mit **Mikrofon** (Spracherkennung auf dem Gerät), Startfragen, Quellenverweise wie bisher.
- **Lernen:** Umschalter *Karten* | *Abfragen*. Karten: Fälligkeiten, Wochenstatistik, Verwalten. Abfragen: sokratischer Dialog zu einem Thema aus den Quellen.
- **Studio:** Zusammenfassung je Quelle und Fach-Zusammenfassung.
- **Fokus-Timer** ist global (ein Timer, nicht pro Fach); erreichbar über den Chip in der Kopfzeile, die Zeit wird dem Fach zugerechnet, in dem er gestartet wurde.

## Eigene Handschrift („Papier und Tinte“)

- Kein Standard-Lila und keine dynamischen Farben. Hell: warmes Papier (#F6F1E7), Tinte (#1F2A44), Akzent Bernstein. Dunkel: Tintenschwarz (#14161C) mit Papiertext.
- Jedes Fach hat eine **Fachfarbe** aus acht gedeckten Tönen (Terrakotta, Salbei, Indigo, Senf, Pflaume, Petrol, Rosenholz, Graphit). Fach-Karten haben einen farbigen **Buchrücken** links.
- Überschriften in Serifenschrift (wie ein Buch), Fließtext serifenlos.
- Große, runde Karten (20 dp), wenige Linien, viel Luft. Primäraktion immer unten erreichbar (Daumenzone).
- Querformat und Tablet: untere Leiste wird zur seitlichen Leiste.

## Umsetzungsschritte (Schritte 1 bis 4 und 6 umgesetzt, Stand siehe PLAN.md, Abschnitt 5a)

1. Datenmodell: Fächer, Zuordnung von Dokumenten und Karten, Suchfilter nach Dokumenten.
2. Designsystem und Navigation: Start, Fach, vier Bereiche.
3. Chat: Quellenauswahl, Spracheingabe.
4. Sokratischer Dialog (Abfragen).
5. Studio: Fach-Zusammenfassung; Quellen umbenennen, suchen.
6. Politur: Tablet, Tests, Messung.
