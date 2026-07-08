# GPU-Beschleunigung auf der Intel-Arc-iGPU (IPEX-LLM)

Dieses Dokument beschreibt, wie das RAG-System die **integrierte Intel-Arc-GPU**
des Laptops (Core Ultra 7 155H) nutzt — für **~7–10× schnellere Antworten** und
**~8× schnellere Embeddings** (Importe).

## Das Ergebnis (empirisch gemessen)

| | CPU (vorher) | Intel-iGPU (jetzt) |
|---|---|---|
| **Antwort** (volle Pipeline, warm) | ~9–10 Min | **~60–85 s** (kurze Fragen ~40 s) |
| **Embedding** (Import) | ~0,6–1,3 Chunks/s | **~5,3 Chunks/s (~8×)** |
| **Modell** | gemma4:e4b (8B) | **gemma3:4b (4B)** |

## Warum ein anderes Modell? (gemma4 → gemma3:4b)

Die GPU-Laufzeit ist **IPEX-LLM „Ollama Portable Zip"** (Intels Ollama-Variante
mit SYCL/Level-Zero-Backend für Intel-GPUs). Sie bündelt **Ollama 0.9.3**.

- **gemma4:e4b lädt darauf NICHT** — die Architektur ist zu neu (braucht Ollama
  ≥ 0.20) und crasht zusätzlich auf dem SYCL-Backend.
- **gemma3:4b läuft einwandfrei auf der iGPU** (~13 tok/s), hat sehr gutes Deutsch
  (Googles multilinguales Modell) und ist mit ~4B klein genug für Tempo. Damit ist
  es der beste Kompromiss aus Qualität und Geschwindigkeit auf dieser Hardware.
  (Recherche-Alternativen: `qwen2.5:7b-instruct`, `qwen3:8b` — etwas besser, aber
  langsamer; `qwen2.5:3b` — schneller, etwas schwächer.)

> Sobald ein neueres IPEX-LLM-Release mit Ollama ≥ 0.20 erscheint, könnte auch
> Gemma 4 auf der iGPU laufen — dann einfach das Paket aktualisieren.

## So nutzt du die GPU

1. **GPU-Server starten:** Doppelklick auf **`Start_GPU_Ollama.bat`**
   (startet Ollama auf der Intel-Arc-iGPU). **Statt** der normalen Ollama-App
   verwenden. Fenster offen lassen.
2. **Oberfläche starten:** `Start_Oberflaeche.bat` wie gewohnt.
3. Fertig — Antworten und Importe laufen jetzt auf der GPU.

Das Paket liegt in `d:\RAG\ipex-ollama\` (heruntergeladen von Intel, 108 MB).

## Tempo vs. Qualität — Stellschrauben

Der Flaschenhals ist **nicht mehr das LLM**, sondern (1) der **Reranker** (läuft
noch auf der CPU, ~20–30 s) und (2) der optionale **Faithfulness-Check** (~18 s).

In der **Einstellungen**-Seite bzw. `data/config.json`:
- **`ENABLE_FAITHFULNESS_CHECK = false`** → −18 s pro Antwort (Relevanz-Gate +
  strikter Prompt schützen weiter vor Halluzination). Für maximales Tempo.
- **`FUSION_TOP_K`** kleiner (z. B. 6) → schnelleres Reranking, minimal weniger Recall.
- Kürzere Antworten (**`LLM_NUM_PREDICT`** kleiner) → schneller, da Zeit ∝ Antwortlänge.

Damit sind **~35–45 s** pro Antwort realistisch (statt ~60–85 s mit voller Sicherheit).

## Architektur mit GPU

```
                 ┌─────────── Intel-Arc-iGPU (IPEX-LLM Ollama, Port 11434) ───────────┐
   Frage ──► RAG │  bge-m3 (Embeddings, ~8×)   +   gemma3:4b (Antworten, ~13 tok/s)   │
                 └────────────────────────────────────────────────────────────────────┘
                         Reranker (bge-reranker-v2-m3) läuft weiter auf der CPU
```

Es läuft **ein** Ollama-Server auf der iGPU, der beide Modelle bedient. Kein
zweiter Server nötig. Fällt der GPU-Server aus, funktioniert alles auch mit der
normalen CPU-Ollama-App weiter (gemma3:4b dann auf CPU — langsamer, aber okay).

## Wichtige Fixes für die GPU-Kompatibilität

- **`generate_json` nutzt KEIN `format="json"`** mehr (Ollama-Grammar): Das
  grammatik-erzwungene Decoding crasht das SYCL-Backend („model runner
  unexpectedly stopped"). Stattdessen freie Generierung + robustes Parsen —
  funktioniert auf CPU und GPU. Betrifft Faithfulness-Check, Fragen-Generierung
  und Gold-Set.
- **Getrennte Server-URLs** (`OLLAMA_BASE_URL` / `EMBED_OLLAMA_URL`) erlauben bei
  Bedarf auch ein Zwei-Server-Setup (Embeddings iGPU, Antworten woanders).
