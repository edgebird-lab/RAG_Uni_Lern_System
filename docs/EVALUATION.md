# Evaluation: die Trefferquote ehrlich messen

Um zu wissen, ob eine Änderung die Suche wirklich verbessert (statt es nur so
wirken zu lassen), misst das System die **Retrieval-Trefferquote** gegen ein
**Gold-Set** aus Testfragen mit bekannter korrekter Quelle. Diese Datei erklärt
Methodik, Metriken, Auswertung und die Grenzen des Verfahrens.

Beteiligte Module: `ragapp/eval/gold_set.py`, `ragapp/eval/metrics.py`,
`ragapp/eval/run_eval.py`.

---

## 1. Gold-Set-Erzeugung (Held-out)

`build_gold_set()` (CLI: `gold`) erzeugt die Testdaten so:

1. **Zufällige Stichprobe** von Chunks aus der Vektordatenbank ziehen
   (`EVAL_SAMPLE_SIZE`, Standard 60; nur inhaltlich substanzielle Chunks ≥
   `MIN_CHUNK_CHARS`). Der Zufall ist mit festem Seed (42) reproduzierbar.
2. Pro Chunk mit dem **Hilfsmodell `gemma4:e2b`** `EVAL_QUESTIONS_PER_CHUNK`
   (Standard 1) **Testfrage(n)** erzeugen, die ausschließlich aus **genau diesem
   Chunk** beantwortbar sind.
3. Als **Gold-Paar** speichern: `(Frage → korrekte chunk_id)`, zusammen mit
   `doc_id`, `filename`, `subject`, `location`.

Ergebnis: `data/eval/gold_set.jsonl` (eine JSON-Zeile pro Testfrage). Die Datei
lässt sich jederzeit neu erzeugen oder von Hand ergänzen.

**Warum „held-out" (nicht indexiert)?** Die Testfragen werden **bewusst nicht** in
den Index aufgenommen. Würde man sie mitindexieren, fände die Suche bei der
Messung schlicht die identische Frage wieder und die Trefferquote wäre künstlich
hoch, die Messung wäre geschönt. Nur getrennte, nicht indexierte Fragen liefern
eine ehrliche Schätzung, wie gut das System **echte, neue** Nutzerfragen auf die
richtige Quelle abbildet.

> Wichtig: Das Gold-Set verweist auf konkrete `chunk_id`s. Nach jeder
> Neu-Ingestion mit geändertem Chunking/Embedding **neu erzeugen**, sonst wird
> gegen nicht mehr existierende IDs gemessen.

---

## 2. Metriken

Ausgangslage ist **Single-Relevant-Retrieval**: Jede Testfrage hat genau **eine**
korrekte Quelle (den Chunk, aus dem sie erzeugt wurde). Gemessen wird, wo dieser
Chunk in der Trefferliste der echten Pipeline landet.

### Hit@k / Recall@k

Anteil der Fragen, bei denen die korrekte Quelle unter den **Top-k** Treffern ist.
Da es je Frage nur eine korrekte Quelle gibt, sind Hit@k und Recall@k hier
identisch.

```
                Anzahl Fragen, bei denen gold_id ∈ Top-k
   Hit@k  =  ───────────────────────────────────────────
                        Anzahl aller Fragen
```

Gemessen für `EVAL_K_VALUES` (Standard 1, 3, 5, 10). Hit@1 ist am strengsten
(richtige Quelle ganz oben), Hit@10 am nachsichtigsten.

### MRR (Mean Reciprocal Rank)

Belohnt eine **hohe Platzierung** der richtigen Quelle: Steht sie auf Rang 1,
zählt 1.0; auf Rang 2 nur 0.5; auf Rang 3 nur 0.33 usw. Wird sie gar nicht
gefunden (innerhalb des größten k), zählt 0.

```
              1     N       1
   MRR   =   ───   Σ    ─────────
              N    i=1   rang_i

     • N      = Anzahl Fragen
     • rang_i = Position der korrekten Quelle bei Frage i (1 = oben)
     • fehlt die Quelle → Beitrag 0
```

MRR ist besonders aussagekräftig, um die Wirkung des **Rerankers** zu sehen: Er
verändert vor allem, *wie weit oben* die richtige Quelle steht.

Die Kennzahlen werden zusätzlich **nach Fach** aufgeschlüsselt (`by_subject`:
n, Hit@kmax, MRR), damit man erkennt, welches Fach schwächelt.

---

## 3. Evaluation ausführen

```powershell
python -m ragapp.scripts.cli eval
```

`run_retrieval_eval()` schickt jede Gold-Frage durch die **echte**
Hybrid-Pipeline (`retrieve(...)`, `subject=None`, mit `final_top_k = max(k)`),
vergleicht die zurückgegebenen `chunk_id`s mit der Gold-`chunk_id` und aggregiert
Hit@k und MRR. Die Ausgabe im Terminal zeigt Hit@1/3/5/10, MRR sowie die
Aufschlüsselung nach Fach und die Dauer.

Gespeichert wird in `data/eval/`:

| Datei | Inhalt |
| ----- | ------ |
| `eval_<zeitstempel>.json` | vollständiger Report: Metriken **und** die verwendete Konfiguration (Embedding, Chunking, Top-K, Reranker an/aus, Fragen-Indexierung …). |
| `per_query_<zeitstempel>.csv` | **jede Testfrage einzeln**, für die Fehleranalyse (siehe §4). UTF-8 mit BOM, direkt Excel-tauglich. |
| `history.jsonl` | kompakter Verlaufseintrag pro Lauf (Hit@k, MRR, Konfiguration), Basis für den Vergleich über die Zeit. |

---

## 4. Fehleranalyse mit der per-query-CSV

Die CSV enthält pro Testfrage die Spalten:

- `question`: die gestellte Testfrage
- `subject`: Fach
- `gold_file` / `gold_location`: wo die korrekte Antwort steht
- `found`: ob die korrekte Quelle in den Top-kmax war (True/False)
- `rank`: auf welchem Rang sie lag (leer, wenn nicht gefunden)
- `top1_file`: welche Datei stattdessen auf Platz 1 stand

So nutzt du sie:

- **Nach `found = False` filtern** → das sind die klaren Misserfolge. Häuft sich
  ein bestimmtes Fach oder eine bestimmte Datei? Dann liegt es oft am Chunking
  oder an fehlender Fragen-Anreicherung dort.
- **Große `rank`-Werte** (Quelle nur weit hinten gefunden) → deutet auf schwache
  Feinsortierung → Reranker prüfen (`USE_RERANKER`), `FINAL_TOP_K`/`FUSION_TOP_K`.
- **`top1_file` vs. `gold_file`** vergleichen → welche „falsche" Quelle drängt
  sich vor? Oft ein Near-Duplicate oder ein thematisch benachbarter Chunk.

Aus solchen Mustern ergeben sich konkrete Stellschrauben, die passende Zuordnung
steht in der Tabelle „Symptom → Stellschraube" in [TUNING.md](TUNING.md).

---

## 5. Verlauf vergleichen (history.jsonl)

Jeder `eval`-Lauf hängt einen Eintrag an `data/eval/history.jsonl`, inklusive der
**Konfiguration**, mit der gemessen wurde. Dadurch kannst du Konfigurationen
direkt gegeneinander stellen: „Mit `USE_RERANKER=True` war Hit@3 = 78 %, ohne nur
64 %." Das Evaluation-Dashboard der UI liest genau diese Historie (`load_history()`)
für die Verlaufskurve.

Der saubere Kreislauf zum Nachjustieren:

```
   Gold-Set erzeugen ──▶ messen ──▶ EINEN Parameter ändern ──▶ erneut messen
          ▲                                                          │
          └──────────────── Verlauf vergleichen ◀────────────────────┘
             (behalten, wenn Hit@k/MRR steigen; sonst zurücknehmen)
```

---

## 6. Ehrliche Grenzen der Methode

Die Messung ist ein **Proxy**, keine absolute Wahrheit. Was man im Hinterkopf
behalten sollte:

- **LLM-generierte Testfragen.** Die Fragen erzeugt ein Modell (`gemma4:e2b`) aus
  den Chunks. Sie können leichter/„sauberer" sein als echte Klausur- oder
  Studierendenfragen und liegen sprachlich oft nah am Quelltext, das kann die
  Trefferquote **optimistischer** erscheinen lassen, als sie im echten Einsatz ist.
- **Single-Relevant-Annahme.** Es zählt nur *der eine* Ursprungs-Chunk als
  korrekt. Findet die Pipeline einen **anderen**, inhaltlich ebenfalls richtigen
  Chunk (das kommt bei überlappenden Zusammenfassungen vor), wird das als Fehler
  gewertet, die reale Nützlichkeit ist dann besser als die Zahl.
- **Nur Retrieval, nicht die Antwortqualität.** Gemessen wird, ob die **richtige
  Quelle gefunden** wird, nicht, wie gut das LLM daraus formuliert oder ob der
  Faithfulness-Check greift. Die Antwortgüte ist separat (u. a. über die
  Query-Logs und stichprobenartiges Lesen der Quellenkarten) zu beurteilen.
- **Stichprobengröße.** Bei `EVAL_SAMPLE_SIZE = 60` sind die Zahlen mit einer
  gewissen Streuung behaftet. Kleine Unterschiede (± wenige Prozentpunkte) sind
  nicht unbedingt signifikant; für belastbarere Aussagen die Stichprobe erhöhen.
- **Reproduzierbarkeit.** Das Gold-Set nutzt einen festen Seed, aber die
  LLM-Fragen selbst sind nicht vollständig deterministisch. Für einen fairen
  A/B-Vergleich zweier Konfigurationen möglichst **dasselbe** Gold-Set verwenden.

Trotz dieser Grenzen ist die Methode das beste verfügbare Werkzeug, um Änderungen
**relativ** zu bewerten: Sie zeigt zuverlässig die *Richtung* („besser/schlechter
als vorher") und macht das Nachjustieren datenbasiert statt gefühlt.
