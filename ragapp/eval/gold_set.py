"""
Gold-Set-Erzeugung für die Trefferquoten-Messung
================================================

Um die Trefferquote *ehrlich* zu messen, brauchen wir Testfragen mit bekannter
korrekter Quelle. Vorgehen:

    1. Zufällige Stichprobe von Chunks aus der Vektordatenbank ziehen.
    2. Pro Chunk mit dem LLM eine oder mehrere **Testfragen** erzeugen. Diese
       werden bewusst NICHT in den Index aufgenommen (Held-out), damit die
       Messung nicht geschönt ist.
    3. Als Gold-Paar speichern: (Frage → korrekte chunk_id).

Das Gold-Set liegt in ``data/eval/gold_set.jsonl`` und kann jederzeit neu erzeugt
oder manuell ergänzt werden.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from ragapp.config import settings, EVAL_DIR
from ragapp.retrieval.vectorstore import get_vectorstore
from ragapp.llm import get_llm

GOLD_FILE = EVAL_DIR / "gold_set.jsonl"

_EVAL_Q_SYSTEM = (
    "Du bist Prüfer an einer Hochschule und formulierst faire Prüfungsfragen."
)
_EVAL_Q_PROMPT = """Formuliere {n} Prüfungsfrage(n) auf Deutsch, die AUSSCHLIESSLICH
mit dem folgenden Abschnitt beantwortet werden können. Die Fragen sollen
natürlich klingen (wie von einem Studierenden gestellt) und den Kerninhalt
treffen. Keine Verweise auf "den Abschnitt".

Abschnitt:
\"\"\"{chunk}\"\"\"

Nur JSON: {{"questions": ["...", ...]}}"""


def build_gold_set(sample_size: int | None = None,
                   questions_per_chunk: int | None = None,
                   seed: int = 42,
                   progress=None) -> dict:
    sample_size = sample_size or settings.EVAL_SAMPLE_SIZE
    questions_per_chunk = questions_per_chunk or settings.EVAL_QUESTIONS_PER_CHUNK

    chunks = get_vectorstore().get_all_chunks()
    # nur inhaltlich substanzielle Chunks
    chunks = [c for c in chunks if len(c["document"]) >= settings.MIN_CHUNK_CHARS]
    if not chunks:
        return {"status": "no_chunks", "count": 0}

    rng = random.Random(seed)
    rng.shuffle(chunks)
    sample = chunks[:sample_size]

    llm = get_llm(settings.LLM_MODEL_FAST)
    gold: list[dict] = []
    for i, ch in enumerate(sample, 1):
        if progress:
            progress(f"Gold-Set: {i}/{len(sample)}")
        try:
            data = llm.generate_json(
                _EVAL_Q_PROMPT.format(n=questions_per_chunk, chunk=ch["document"][:2500]),
                system=_EVAL_Q_SYSTEM, temperature=0.3,
            )
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for q in data.get("questions", [])[:questions_per_chunk]:
            if isinstance(q, str) and q.strip().endswith("?"):
                gold.append({
                    "question": q.strip(),
                    "chunk_id": ch["id"],
                    "doc_id": ch["meta"].get("doc_id"),
                    "filename": ch["meta"].get("filename"),
                    "subject": ch["meta"].get("subject"),
                    "location": ch["meta"].get("location"),
                })

    with open(GOLD_FILE, "w", encoding="utf-8") as f:
        for g in gold:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")
    return {"status": "ok", "count": len(gold), "file": str(GOLD_FILE)}


def load_gold_set() -> list[dict]:
    if not GOLD_FILE.exists():
        return []
    out = []
    with open(GOLD_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue  # defekte Zeile überspringen, Rest bleibt nutzbar
    return out
