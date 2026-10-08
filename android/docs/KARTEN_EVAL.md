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

## Dublettenschwelle für EmbeddingGemma (Feinschliff, 2026-10-08)

Mit 15 von Hand gelabelten Paraphrasen (echte Dubletten) und 25 verwandten, aber verschiedenen Fragen (z. B. „Was ist oxygene / anoxygene Photosynthese?“, „Best Case / Worst Case von Quicksort“) auf dem Pixel gemessen:

| Paare | Kosinus (EmbeddingGemma 2) |
|---|---|
| echte Dubletten | 0,947 bis 0,991 (Mittel 0,97) |
| verschiedene Fragen | 0,72 bis 0,975 (15 von 25 über 0,89) |

| Regel | Dubletten erkannt | verschiedene Fragen fälschlich verworfen |
|---|---|---|
| bisher: Kosinus ≥ 0,89 | 15 von 15 | **16 von 25** |
| Kosinus ≥ 0,94 | 15 von 15 | 6 von 25 |
| Kosinus ≥ 0,955 | 11 von 15 | 4 von 25 |
| **neu:** ≥ 0,955, oder ≥ 0,93 bei Wortüberlappung ≥ 0,7, oder ≥ 0,90 bei Überlappung ≥ 0,85 | **13 von 15** | **4 von 25** |

Die alte Schwelle stammte von bge-m3 (PC-App); EmbeddingGemma bewertet verwandte Fragen deutlich ähnlicher. Die neue Regel verwirft nur noch eine von sechs verschiedenen Fragen und lässt wenige Dubletten durch, die sich per Bearbeiten/Löschen entfernen lassen. Rohdaten und Auswertung: `DebugDupActivity`.

## Neu im Feinschliff

- **Lückentext-Karten:** Das Modell wählt Satz und Schlüsselbegriff, der Code prüft, dass beides wörtlich im Quelltext steht, und baut die Karte (alle Vorkommen des Begriffs werden verdeckt). Ein Modellaufruf je Abschnitt statt zwei, etwa 3 statt 7 Sekunden je Karte.
- **Code-Abschnitte** werden erkannt und bekommen einen eigenen Fragen-Prompt (Verhalten, Ergebnis, Laufzeit, ohne Verweis auf Variablennamen); sie fallen nicht mehr durch den Zeichenfilter.
- Beim Erzeugen wählt man **Fragen, Lückentext oder Gemischt**.

## Bugs, die erst auf dem Gerät auffielen

1. **Androids Regex-Engine (ICU) ist strenger als die der JVM:** Das Flag `U` (Unicode-Zeichenklassen) und ein einzelnes `}` im Muster wirken auf der JVM, werfen auf Android aber `PatternSyntaxException`. Beides führte zu App-Abstürzen (Kartenerzeugung, Aufdecken einer Karte). Die JVM-Tests haben das nicht gezeigt. Seitdem laufen alle Paritätstests zusätzlich auf dem Gerät (`CoreParityOnDeviceTest`).
2. **Die Dublettenprüfung lief anfangs still ins Leere**, weil der Embedder im Hintergrundjob nie geladen wurde und der Fehler verschluckt wurde. Behoben; der Test deckt das ab.

## Bekannte Einschränkungen

- Kein LaTeX-Renderer: Formeln werden vereinfacht als Text angezeigt (`$E_{\text{chem}}$` → `E_chem`); gespeichert wird das Original.
- Die Kartenerzeugung blockiert den Chat zwischen einzelnen Generierungen kurz (ein Modell, eine Anfrage nach der anderen).
- Das Display muss während der Erzeugung an bleiben.
