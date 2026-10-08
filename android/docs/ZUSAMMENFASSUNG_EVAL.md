# Zusammenfassungen auf dem Gerät (Phase 6, Stand 2026-10-08)

Pixel 9 Pro XL, Gemma 4 E2B (GPU, MTP). Texte: zwei öffentliche Wikipedia-Artikel (Quicksort: 34 Chunks, 14 Abschnitte; Photosynthese: 137 Chunks, 49 Abschnitte). Eigene Unterlagen der Nutzerin wurden für die Auswertung nicht gelesen.

## Ablauf (Map-Reduce)

1. **Abschnitte bilden:** Chunks mit gleicher Fundstelle werden bis 3000 Zeichen zusammengefasst, die vom Chunker eingefügte Überlappung entfällt, sehr kurze Nachbarn werden vereinigt („Seite 3–4“).
2. **Map:** je Abschnitt ein Modellaufruf. Stil *Gegliedert* (Kernidee, Begriffe, Regeln wie in der PC-App) oder *Stichpunkte* (3 bis 6 Punkte). Das Ergebnis wird sofort gespeichert; nach einem Abbruch geht es beim ersten fehlenden Abschnitt weiter.
3. **Reduce (nur Kurzfassung):** Die Stichpunkte aller Abschnitte werden zu einer Übersicht verdichtet, bei langen Dokumenten stapelweise in mehreren Ebenen (höchstens 4).
4. **Prüfungen je Antwort:** abgeschnittene Sätze (Neuversuch mit mehr Tokens, sonst Kürzen bis zum letzten vollständigen Satz), Zahlen, die im Abschnitt nicht vorkommen (ein Neuversuch mit Hinweis; bleibt der Befund, warnt die App), „kein prüfungsrelevanter Inhalt“ (Abschnitt entfällt).
5. **Neuberechnung:** Wird ein Dokument durch eine geänderte Fassung ersetzt, werden die vorhandenen Zusammenfassungen automatisch neu erstellt (auf dem Gerät mit Quicksort getestet: drei Aufträge starten von selbst).

## Messwerte

| Lauf | Abschnitte | Dauer | Zahlen-Warnungen | übersprungen |
|---|---|---|---|---|
| Quicksort, Stichpunkte | 14 | 165 s (ca. 12 s je Abschnitt) | 0 | 0 |
| Quicksort, Gegliedert | 14 | 317 s (ca. 23 s je Abschnitt) | 0 | 0 |
| Quicksort, Kurzfassung (aus vorhandenen Stichpunkten) | 14 | 95 s | 0 | 0 |
| Photosynthese, Kurzfassung (inkl. 49 Stichpunkt-Abschnitten und 3 Verdichtungsebenen) | 49 | ca. 19 Minuten allein, 28 Minuten bei paralleler Last | 0 | 0 |

Auf dieser Grundlage zeigt die App vor dem Start eine Zeitschätzung an (12 s je Abschnitt, 23 s bei Gegliedert, Kurzfassung plus 1 Minute).

## Qualität (von Hand gelesen: beide Kurzfassungen vollständig, mehrere Abschnitte der Stichpunkte und der Gliederung)

- Inhalt sachlich richtig und am Text geblieben; keine erfundenen Zahlen gefunden (der automatische Abgleich meldete ebenfalls nichts). Das ist **eine Stichprobe, keine systematische Prüfung** der Sachrichtigkeit.
- Fachbegriffe werden fett hervorgehoben, Formeln bleiben als LaTeX erhalten und werden in der App vereinfacht dargestellt.
- Die Kurzfassung eines langen Dokuments gewichtet die **Einleitung stärker** als spätere Kapitel (Photosynthese: Grundlagen und Lichtreaktion sind drin, spätere Spezialthemen kaum). Wer Abdeckung braucht, nimmt *Gegliedert*.

## Fehler, die bei der Auswertung auffielen und behoben wurden

1. **Abgebrochene Sätze:** Die Kurzfassung endete im ersten Absatz mit „Elemente…“. Das Modell schreibt die Auslassungspunkte selbst (nicht nur bei erreichtem Token-Limit), auch beim Neuversuch. Jetzt werden unvollständige Absätze und Listenpunkte automatisch bis zum letzten vollständigen Satz gekürzt.
2. **Kursive Hinweiszeile** erschien mit Sternchen: Der Markdown-Ausschnitt kennt nun auch *kursiv*.
3. **Zeitschätzung** war zu optimistisch (10 s je Abschnitt angenommen, gemessen 12 bis 23 s).

## Bekannte Einschränkungen

- Lange Dokumente brauchen lange (über 100 Seiten: eine halbe Stunde und mehr). Die Erzeugung läuft im Vordergrunddienst, pausiert bei Hitze und Akku unter 20 % und kann unterbrochen werden.
- Das Display sollte während der Erzeugung an bleiben.
- Zusammenfassungen eines ganzen Fachs gibt es erst, wenn Fächer existieren (siehe Feinschliff-Backlog im Plan).
