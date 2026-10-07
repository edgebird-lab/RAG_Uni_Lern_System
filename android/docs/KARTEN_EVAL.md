# Karteikarten auf dem Gerät (Phase 5, Stand 2026-10-08)

Pixel 9 Pro XL, Gemma 4 E2B (GPU, MTP) für Fragen und Antworten, EmbeddingGemma 2 für die Dublettenprüfung.

## Was verglichen und geprüft wurde

- **FSRS-6:** 2553 zufällige Bewertungen (300 Folgen, Zeitabstände von Sekunden bis 60 Tage) mit dem Python-Paket `fsrs` 6.3 verglichen: Zustand, Schritt, Stabilität, Schwierigkeit und Fälligkeit sind identisch (Toleranz 1e-9). Läuft als JVM-Test und auf dem Gerät.
- **Kartenqualität** (`card_quality.py`): 133 Fragen (27 mit Mängeln) und 213 Antworten (10 mit Mängeln) liefern in Kotlin dieselben Mängel-Codes wie in Python. Läuft ebenfalls auf dem Gerät.
- **Migration** der Datenbank von Version 1 auf 2 mit echten Altdaten (Dokument + Abschnitt) auf dem Gerät getestet.

## Erzeugungslauf (je Dokument bis zu 10–15 Karten)

| Dokument | Karten | Bemerkung |
|---|---|---|
| Grundgesetz | 9 von 10 | 1 Dublette verworfen |
| Quicksort (Wikipedia) | 15 | |
| Photosynthese (Wikipedia) | 8 von 12, später 15 | 2 Fragen vom Qualitätsfilter verworfen |

Dauer: etwa 7 Sekunden je Karte bei warmem Modell, beim allerersten Lauf bis ca. 20 Sekunden.

**Von Hand gelesene Qualität** (ca. 30 Karten): etwa zwei Drittel sind gute, eigenständige Prüfungsfragen mit korrekter Musterlösung. Typische Schwächen von E2B:
- fast gleiche Fragen aus demselben Abschnitt (z. B. zweimal „Besatzungskosten“, zweimal „zyklischer Elektronentransport“), die der Dublettenfilter mit Schwelle 0,89 nicht fängt (gemessene Ähnlichkeit der klarsten Dublette: 0,912, ähnlich, aber unterschiedliche Fragen: 0,80–0,86);
- Fragen, die vom Quelltext abhängen („… `rechts` und `teiler` …“ in Code-Beschreibungen);
- sehr lange, zusammengesetzte Fragen („… und welche Rolle spielt …“);
- einzelne Antworten, die nur die Frage wiederholen.
Deshalb gibt es in der App Bearbeiten und Löschen für jede Karte.

## Bugs, die erst auf dem Gerät auffielen

1. **Androids Regex-Engine (ICU) ist strenger als die der JVM:** Das Flag `U` (Unicode-Zeichenklassen) und ein einzelnes `}` im Muster wirken auf der JVM, werfen auf Android aber `PatternSyntaxException`. Beides führte zu App-Abstürzen (Kartenerzeugung, Aufdecken einer Karte). Die JVM-Tests haben das nicht gezeigt. Seitdem laufen alle Paritätstests zusätzlich auf dem Gerät (`CoreParityOnDeviceTest`).
2. **Die Dublettenprüfung lief anfangs still ins Leere**, weil der Embedder im Hintergrundjob nie geladen wurde und der Fehler verschluckt wurde. Behoben; der Test deckt das ab.

## Bekannte Einschränkungen

- Kein LaTeX-Renderer: Formeln werden vereinfacht als Text angezeigt (`$E_{\text{chem}}$` → `E_chem`); gespeichert wird das Original.
- Nur Frage-Antwort-Karten (wie in der PC-App), keine Lückentexte.
- Die Kartenerzeugung blockiert den Chat zwischen einzelnen Generierungen kurz (ein Modell, eine Anfrage nach der anderen).
- Das Display muss während der Erzeugung an bleiben.
