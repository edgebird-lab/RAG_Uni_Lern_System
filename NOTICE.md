# NOTICE: Drittanbieter-Modelle und ihre Lizenzen

Der **Code** dieses Projekts steht unter der **MIT-Lizenz** (siehe [`LICENSE`](LICENSE)).

Die **Modelle** hingegen sind **nicht Teil dieses Repositories**. Sie werden erst
zur Laufzeit über [Ollama](https://ollama.com) bzw.
[Hugging Face / sentence-transformers](https://huggingface.co) auf deinen Rechner
geladen. Jedes Modell unterliegt **seiner eigenen Lizenz bzw. Nutzungsbedingung**.
Für die Einhaltung dieser Bedingungen ist **jede Nutzerin / jeder Nutzer selbst
verantwortlich**, die MIT-Lizenz dieses Codes erstreckt sich ausdrücklich nicht
auf die Modelle.

## Standard- und empfohlene Modelle

| Modell (Ollama-/HF-Tag)     | Rolle                | Lizenz / Bedingungen                                   |
| --------------------------- | -------------------- | ------------------------------------------------------ |
| `gemma3:4b`, `gemma3:12b`, `gemma4:*` | Antwort-LLM | **Gemma Terms of Use** (Google), eigene Bedingungen   |
| `qwen2.5:*`, `qwen3:*`      | Antwort-LLM (Alt.)   | **Apache-2.0** (Alibaba/Qwen)                          |
| `bge-m3`                    | Embedding            | **MIT** (BAAI)                                          |
| `BAAI/bge-reranker-v2-m3`   | Reranker (Cross-Enc.)| **Apache-2.0** (BAAI)                                  |

Die konkret genutzten Modelle hängen von deiner Hardware ab (siehe
`python -m ragapp.scripts.cli recommend`) und lassen sich frei austauschen.

## Wichtige Hinweise

- **Gemma-Modelle** unterliegen den *Gemma Terms of Use* und der *Prohibited Use
  Policy* von Google. Bitte vor dem Einsatz prüfen:
  <https://ai.google.dev/gemma/terms>
- **Qwen-Modelle** stehen unter Apache-2.0 (einzelne Varianten können abweichen,
  Modellkarte prüfen).
- **bge-m3** und **bge-reranker-v2-m3** sind quelloffen (MIT bzw. Apache-2.0).
- Modelllizenzen können sich ändern. Maßgeblich ist stets die jeweilige
  **Modellkarte** (Ollama-Library bzw. Hugging Face) zum Zeitpunkt des Downloads.

Dieses Projekt bündelt **keine** Modellgewichte und trifft **keine** Aussage über
die Rechtmäßigkeit deiner konkreten Nutzung. Prüfe die Lizenzen eigenständig.
