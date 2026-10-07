# Spike-Ergebnis (Phase 1, Stand 2026-10-07)

Gerät: Pixel 9 Pro XL (Tensor G4, Mali-GPU, 16 GB RAM, Android 17). Runtime: LiteRT-LM 0.18.0 (Kotlin). Rohdaten: `eval/spike/*.json`, Auswertung: `eval/spike/auswerten.py`, `auswerten_emb.py`.
Prompts: 21 Goldset-Fragen mit **Orakel-Kontext** (Beleg-Abschnitt + 3 Ablenker, ca. 800–1400 Token), Antwortlimit 256 Token.

## Entscheidung (Tor 1): weiter mit LiteRT-LM + Gemma 4 E2B auf der GPU

Das Abbruchkriterium (unter ca. 8 Token/s oder instabile Qualität) greift nicht.

## Sprachmodell

| Lauf | Laden (Cache warm) | Erstes Token | Prefill | Generieren | RAM-Spitze (RSS) |
|---|---|---|---|---|---|
| E2B, GPU, ohne MTP (n=3) | 288 s beim 1. Mal | 5,7 s | 179 Tok/s | 10,8 Tok/s | 1,9 GB |
| **E2B, GPU, MTP** (n=21) | **25 s** | **1,3 s (Median)** | **~770 Tok/s** | **~18–20 Tok/s** | 2,9 GB |
| E4B, GPU, MTP (n=21) | 25–30 s (nicht separat gemessen) | 2,9 s | 366 Tok/s | 14,4 Tok/s | 3,5 GB |
| E2B, CPU (Standard-Threads) | – | 40–70 s | – | 2–3 Tok/s | – |

- **MTP (Speculative Decoding) bringt fast doppeltes Tempo** und ist für die GPU Pflicht (`ExperimentalFlags.enableSpeculativeDecoding`).
- **CPU-Backend ist so nicht brauchbar.** Mit Standard-Threadzahl 2–3 Tok/s. Als Fallback für Geräte ohne brauchbare GPU müsste man `Backend.CPU(threadCount=…)` abstimmen, das ist nicht gemessen.
- **Einmalige Kompilierung beim ersten Start:** ca. 5 Minuten für die GPU-Kernel (E2B 288 s, danach noch einmal ca. 6 Minuten beim ersten Prompt für den MTP-Entwurf; E4B ähnlich). Ab dem zweiten Start 25 s Laden und 2 s bis zum ersten Token. Die App braucht dafür einen „Gerät wird optimiert“-Schritt.
- **Cache-Größe:** E2B ca. 1,6 GB, E4B ca. 2,2 GB zusätzlich zum Modell (2,6 bzw. 3,7 GB). Der Cache muss in `filesDir` liegen (nicht `cacheDir`, das das System leeren darf, dann folgt wieder die 5-Minuten-Kompilierung). Benötigt also etwa 4–6 GB Speicher.
- **Temperatur:** Akku 34,6 °C nach 21 Prompts, kein Throttling (Thermal-Status 0).
- **Das Display muss an bleiben.** Der Lauf wurde gesperrt (Sperrbildschirm) und kam praktisch zum Stehen. Für lange Jobs (Embedding großer Dokumente) braucht die App einen Foreground-Service mit Wakelock, sonst hängt die GPU-Arbeit im Hintergrund.

## Antwortqualität (Orakel-Kontext, E2B, GPU, MTP)

- Direkte Fragen 8/8 sinngemäß richtig, mit korrekter Quellennummer.
- Mehrstufige 3/3. **Unbeantwortbare 6/6 korrekt mit „Nicht im Material gefunden.“** verweigert. Das war die Hauptsorge bei einem 2B-Modell.
- Umformulierte 3/4: Eine Frage (HGB, Wechselkurs) wurde fälschlich verweigert, obwohl die Antwort im Kontext stand. E4B beantwortete sie richtig.
- E4B vs. E2B: bei diesen 21 Fragen gleichauf (E4B 1 Frage besser, bei Römisches Reich eine ungenauere Zahl). **E4B ist langsamer und braucht mehr RAM, bringt hier keinen klaren Vorteil.** E2B als Standard, E4B als optionale Wahl.
- Grenzen: Stichprobe klein, Orakel-Kontext (kein Retrieval-Fehler), grobe Wortüberlappung als Maß plus Lesen der Antworten. Das ist ein Hinweis, kein Beweis.

## Embeddings (EmbeddingGemma 2 Text 270M, 165 MB, Apache 2.0, Standard `.litertlm`)

Volles Korpus, 3012 Abschnitte, 83 beantwortbare Fragen, nur Vektorsuche, gegen PC-Baseline bge-m3.

| Variante | Treffer@1 | @4 | @10 | MRR | Tempo |
|---|---|---|---|---|---|
| bge-m3 (PC, Ollama) | 0,76 | 0,98 | 1,00 | 0,92 | – |
| **EmbeddingGemma 2, GPU, 768, ohne Präfix** | **0,67** | **0,92** | **0,98** | 0,85 | 4,6 Abschn./s, 262 ms/Frage |
| EmbeddingGemma 2, GPU, 768, mit Aufgaben-Präfix | 0,58 | 0,88 | 0,95 | 0,80 | 4,1 Abschn./s |
| EmbeddingGemma 2, GPU, 256 Dim, mit Präfix | 0,55 | 0,86 | 0,94 | 0,76 | 4,0 Abschn./s |
| EmbeddingGemma 2, CPU (200 Abschn.) | – | – | – | – | 0,6 Abschn./s (unbrauchbar) |

- **Präfixe schaden** (die `.litertlm`-Variante scheint sie selbst zu behandeln oder braucht sie nicht). Ohne Präfix verwenden. `EmbeddingPrompts` in `core` bleibt als Option, ist aber nicht der Standard.
- **Weniger Dimensionen** (256) kosten nur wenig Qualität und sparen Speicher, bei 768 aber besser.
- **Eingabegrenze 512 Token:** Ein Abschnitt mit 519 Token ließ den Batch scheitern. Der Chunker muss Token statt Zeichen begrenzen, oder die App muss zu lange Texte kürzen.
- Ein 100-Seiten-Skript (ca. 300 Chunks) braucht damit etwa 1–1,5 Minuten Embedding, ein 3000-Chunk-Gesetzestext ca. 11 Minuten. Als Hintergrundjob akzeptabel.
- Das Gesetzes-Korpus ist ein schwerer Test (viele fast gleiche Paragrafen).
- **Hybride Suche, offline ausgewertet** (`eval/spike/hybrid_auswertung.py`, Geräte-Vektoren plus BM25 mit Snowball-Stemmer, RRF k=60):

| Verfahren | @1 | @4 | @10 | MRR |
|---|---|---|---|---|
| nur Vektoren (EmbeddingGemma 2, 768, ohne Präfix) | 0,67 | 0,92 | 0,98 | 0,85 |
| nur BM25 | 0,66 | 0,84 | 0,88 | 0,82 |
| **RRF Vektor : BM25 = 1 : 1** | **0,69** | **0,94** | **0,98** | 0,86 |
| RRF 2 : 1 | 0,67 | 0,94 | 0,99 | 0,85 |

  Der Gewinn durch die Hybridsuche ist **klein** (+2 Punkte bei @4). Die Lücke zur PC-Baseline (@4 0,98) bleibt, sie liegt am schwächeren Embedding-Modell, nicht an der Suchart. Für Top-4-RAG heißt das: ca. 94 % der Fragen bekommen ihren Beleg in den Kontext. Hebel für später: Reranking der Top-10 mit dem LLM, größeres Embedding-Modell (EmbeddingGemma 2 740M) oder kleinere Chunks.

## Nicht gemacht / offen

- **llama.cpp (Plan-Schritt 1.4)** wurde nicht gemessen: LiteRT-LM erfüllt die Kriterien deutlich. llama.cpp bleibt Rückfall, falls LiteRT-LM Probleme macht oder für iOS.
- Messung auf nur einem Gerät. Schwächere Handys (z. B. 8 GB RAM, andere GPU) sind unbekannt. Google-Zahlen: Galaxy S26 Ultra GPU 52 Tok/s ohne MTP, also hat das Pixel 9 Pro XL mit der Mali-GPU nur ein Fünftel davon.
- Qualität mit echtem Retrieval (Top-4 aus dem ganzen Korpus) steht aus (Phase 4).
- Alternative für Produktion: Android AICore/Gemini Nano auf unterstützten Geräten (von Google für Produktion empfohlen). Passt nicht zum Ziel „ein Modell, überall gleich, ohne Systemabhängigkeit“, wäre aber ein Zusatzpfad.
