# Goldset (frei, öffentlich)

Messlatte für RAG-Qualität auf dem Handy. Basis ist das freie Korpus in [../korpus/](../korpus/QUELLEN.md): Grundgesetz, BGB, HGB (gemeinfrei, § 5 UrhG) und acht Wikipedia-Artikel (CC BY-SA 4.0). Persönliche Unterlagen gehören nicht hierher, sondern nach `../private/`.

## Format (`goldset.jsonl`, eine Frage pro Zeile)

| Feld | Bedeutung |
|---|---|
| `id` | stabile ID, z. B. `gg-dire-03` |
| `typ` | `direkt`, `umformuliert`, `mehrstufig`, `unbeantwortbar` |
| `frage` | eigenständig verständlich, ohne „im Text“ |
| `erwartete_antwort` | kurz; bei `unbeantwortbar` immer „Nicht im Material gefunden.“ |
| `dokument` | Datei im Korpus |
| `belege` | Liste aus `fundstelle` + wörtlichem `zitat`; leer bei `unbeantwortbar` |
| `reviewed` | `true` erst nach menschlicher Durchsicht |

Belege sind **Zitate, keine Chunk-IDs**: Ein Treffer zählt, wenn das Zitat im abgerufenen Chunk steht. So bleibt das Goldset gültig, wenn sich der Chunker ändert.

## Messgrößen

- **Treffer@k:** Steht ein Beleg-Zitat in den obersten k Chunks? (`mehrstufig`: beide.)
- **Antwort-Treue:** Wird die erwartete Antwort sinngemäß getroffen und die Quelle genannt?
- **Verweigerungsquote:** Bei `unbeantwortbar` antwortet das Modell mit „nicht im Material“ statt zu raten. Für kleine Modelle die wichtigste Zahl.

## Stand (2026-10-07): `goldset.jsonl`, 102 Fragen, alle `reviewed: true`

| Typ | Anzahl | Herkunft |
|---|---|---|
| direkt | 52 | generiert (gemma4:latest), Zitat maschinell geprüft, Richter gemma4:26b, Durchsicht |
| umformuliert | 21 | wie oben |
| mehrstufig | 10 | wie oben, nur nach Einzellesung freigegeben (17 von 27 verworfen) |
| unbeantwortbar | 19 | von Hand geschrieben; der Prüfbegriff kommt im gesamten Korpus nicht vor |

Lehren aus der Durchsicht:
- Der Richter war zu großzügig (fast alles „ok“). Die eigentliche Auswahl fiel bei der Einzellesung (vage Meta-Fragen, Verweise auf „den Text“, Duplikate derselben Fundstelle). Aussortierte IDs stehen in `aussortiert_manuell.json`.
- Generierte „unbeantwortbare“ Fragen waren teils doch beantwortbar (Wellenlänge im Photosynthese-Artikel). Deshalb schreibt man sie von Hand und prüft per Volltextsuche.
- Mehrstufige Fragen taugen nur mit **benachbarten** Abschnitten und konkretem Prompt.
- Ausgewogenheit: Gesetze (GG/BGB/HGB) stellen 46 Fragen, Wikipedia 56. Quicksort ist mit 4 Fragen unterrepräsentiert.

## Ablauf (reproduzierbar)

1. `python3 -I tools/build_korpus.py` baut das Korpus (mit Revisionsangaben).
2. `python3 -I tools/generate_goldset.py [--typen umformuliert --seed 21 --offset 30 --scale 3]` erzeugt Kandidaten in `kandidaten.jsonl`.
3. `python3 -I tools/pruefen.py` lässt einen größeren Richter (bge-m3-Suche + gemma4:26b) jede Kandidatin gegen das ganze Korpus prüfen (`pruefung.jsonl`).
4. Menschliche/zweite Durchsicht, Ergebnis nach `goldset.jsonl` (siehe Stand oben). Unbeantwortbare Fragen kommen aus `unbeantwortbar_manuell.jsonl`.

Ein ungeprüftes Goldset belohnt die Eigenheiten des Generator-Modells. Deshalb zählen nur `reviewed: true`-Zeilen.
