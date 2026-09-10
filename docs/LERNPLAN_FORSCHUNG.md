# Lernplan: wissenschaftliche Grundlage

Die Seite **📋 Lernplan** rechnet aus einer KI-Gliederung einen realistischen,
tages-verteilten Lernplan aus. Die dabei verwendeten Parameter (`ragapp/config.py`,
Abschnitt „Lernplan") sind bewusst **nicht frei erfunden**, sondern an
Forschungsbefunde angelehnt. Diese Seite dokumentiert die Herleitung, damit die
Werte bei Bedarf nachvollziehbar nachjustiert werden können.

## Verwendete Befunde

| Parameter | Wert | Begründung | Quelle |
| --- | --- | --- | --- |
| `PLAN_PAGES_PER_HOUR` | 25 Seiten/h | Verstehendes Lesen dichten/technischen Stoffs liegt bei ~20–30 Seiten/h (deutlich unter Freizeit-Lesetempo von 40–55 S/h). | [ReadingSpeedTest.net](https://readingspeedtest.net/blog/average-pages-read-per-hour-for-adults-and-students) |
| `PLAN_ITEMS_PER_HOUR` | 10 Items/h | Studien zu Vokabel-/Fakten-Lernen zeigen ~9–10 neu erlernte und behaltene Items pro Stunde aktiver Übung. | [SpanishDict – 1000 Wörter in 15h](https://www.spanishdict.com/guide/learn-1000-words-in-15-hours) |
| `PLAN_MAX_DAILY_FOCUS_MIN` | 240 Min (4h) | Kognitive Produktivität sinkt spürbar nach 4–5 Std fokussierter Arbeit/Tag; 3–4 Std gelten als nachhaltig optimal. Das ist die harte Obergrenze gegen "8 Stunden frei = 8 Stunden lernen". | [Studwy – Science-Based Study Hours](https://studwy.com/blog/how-many-hours-study-per-day-science-based-answer), [Learning Rabbit Hole](https://learningrabbithole.com/how-many-hours-a-day-can-you-effectively-study/) |
| `PLAN_BLOCK_MIN` | 25 Min | Aufmerksamkeit lässt nach ~25–30 Min fokussierter Arbeit spürbar nach (ultradiane Rhythmik) – Standard-Pomodoro-Länge. Eine Meta-Analyse (32 Studien) findet r=0,65 Korrelation mit Studienleistung. | [PMC – Pomodoro/Flowtime-Studie](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12292963/), [Brown Daily Herald](https://www.browndailyherald.com/article/2026/03/fact-check-is-the-pomodoro-technique-actually-effective-for-studying) |
| Verteilung über mehrere Tage statt einer Session | – | Verteiltes Lernen verbessert die Behaltensleistung um 40–60 % gegenüber Blockbüffeln, bei gleichem Gesamtaufwand. | [Digital Promise – Distributed Practice](https://digitalpromise.org/2019/05/08/ask-the-cognitive-scientist-distributed-practice/), [Frontiers in Psychology](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2021.685245/full) |
| Begrenzte Anzahl neuer Konzepte je Lerneinheit | (Design-Prinzip, kein Parameter) | Arbeitsgedächtnis verarbeitet zuverlässig nur ~4 neue Informationseinheiten gleichzeitig (Cowan) – Tiefe statt Breite pro Abschnitt. | [Structural Learning – Cognitive Load Theory](https://www.structural-learning.com/post/cognitive-load-theory-a-teachers-guide) |
| `PLAN_CHARS_PER_PAGE` / `PLAN_CHARS_PER_CONCEPT` | 3000 / 1000 | Grobe technische Umrechnung (keine eigene Forschung): ~500 Wörter × ~6 Zeichen ≈ 3000 Zeichen/Seite; ein "lernbares Konzept" wird pauschal mit ~1000 Zeichen Quelltext veranschlagt. | – |

## Wie die Werte verwendet werden

```
Lesezeit (Min)    = Zeichen / PLAN_CHARS_PER_PAGE × (60 / PLAN_PAGES_PER_HOUR)
Übungszeit (Min)  = (Zeichen / PLAN_CHARS_PER_CONCEPT) × (60 / PLAN_ITEMS_PER_HOUR)
Geschätzte Zeit   = Lesezeit + Übungszeit   (siehe ragapp/study_plan.py:_estimate_minutes)

Effektive Tageszeit = min(vom Nutzer angegebene Minuten/Tag, PLAN_MAX_DAILY_FOCUS_MIN)
```

Der Plan wird in `PLAN_BLOCK_MIN`-Portionen über die verfügbaren Tage verteilt.
Reicht die Zeit bis zu einem gesetzten Zieldatum nicht aus, meldet das System den
fehlenden Umfang **explizit** (keine stillschweigende Kürzung) – siehe
`ragapp/study_plan.py:build_schedule`.

## Grenzen

Das ist eine grobe, Zeichen-basierte Schätzung – keine individuelle Diagnostik.
Tatsächliches Lerntempo hängt stark von Vorwissen, Fach und Person ab. Die Werte
sind über `ragapp/config.py` anpassbar, falls sie sich in der Praxis als zu
optimistisch oder zu konservativ erweisen.
