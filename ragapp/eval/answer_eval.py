"""
Antwort-Qualitaets-Evaluation (RAGAS-lite)
==========================================
Die bisherige Evaluation misst nur, ob der richtige CHUNK gefunden wird (Hit@k).
Sie sagt NICHTS darueber, ob die generierte ANTWORT korrekt, vollstaendig und
belegt ist - eine fluent-aber-falsche Antwort besteht dort still. Dieses Modul
schliesst die Luecke: Es laesst das echte RAG-System die Gold-Fragen beantworten
und bewertet die Antworten mit einem LLM-Judge (grosses Modell) gegen den
Quelltext (Ground Truth) - Korrektheit / Vollstaendigkeit / Treue (0-100). Zudem
werden erfundene [Quelle N]-Verweise und Fallback-Quote gemessen.

Ehrliche Einschraenkung: Der Judge ist selbst LLM-basiert; die Werte sind ein
brauchbares, aber nicht perfektes Signal. Fuer Vertrauen einen kleinen, von Hand
gelabelten Anker-Satz mitfuehren (siehe README/roadmap).
"""
from __future__ import annotations

import json
import random
import re
import time
from pathlib import Path
from typing import Optional

from ragapp.config import settings, EVAL_DIR
from ragapp.eval.gold_set import load_gold_set
from ragapp.llm import get_llm
from ragapp.retrieval.vectorstore import get_vectorstore

HISTORY_FILE = EVAL_DIR / "answer_eval_history.jsonl"

_JUDGE_SYSTEM = ("Du bist ein strenger, fairer Pruefer und bewertest Antworten auf "
                 "Faktentreue und Korrektheit anhand eines maßgeblichen Quelltextes.")

_JUDGE_PROMPT = """Bewerte die Antwort eines Lern-Systems auf eine Pruefungsfrage.
Der QUELLTEXT ist die maßgebliche Grundlage (Ground Truth).

Frage:
{frage}

Quelltext (Ground Truth):
\"\"\"{quelle}\"\"\"

Antwort des Systems:
{antwort}

Bewerte jeweils 0-100:
- korrektheit: Stimmt die Antwort inhaltlich mit dem Quelltext ueberein?
- vollstaendigkeit: Deckt sie die Kernpunkte der Frage ab?
- treue: Enthaelt sie NUR durch den Quelltext gedeckte Aussagen (keine Erfindungen)?

Gib NUR JSON zurueck:
{{"korrektheit": <0-100>, "vollstaendigkeit": <0-100>, "treue": <0-100>}}"""

_CITE_RE = re.compile(r"[\[(]\s*Quellen?\s*([\d,\s]+)")


def _num(v) -> Optional[float]:
    try:
        return max(0.0, min(100.0, float(v)))
    except (TypeError, ValueError):
        return None


def _avg(xs: list) -> Optional[int]:
    return round(sum(xs) / len(xs)) if xs else None


def _invalid_citations(answer: str, n_sources: int) -> bool:
    nums = set()
    for m in _CITE_RE.finditer(answer or ""):
        for tok in re.split(r"[,\s]+", m.group(1).strip()):
            if tok.isdigit():
                nums.add(int(tok))
    return any(x < 1 or x > n_sources for x in nums)


def run_answer_eval(sample_size: int = 10, seed: int = 42, progress=None) -> dict:
    """Beantwortet eine Stichprobe der Gold-Fragen mit dem echten System und bewertet
    die Antworten per LLM-Judge. Schreibt einen Verlaufseintrag. Ehrliches Ergebnis."""
    gold = load_gold_set()
    if not gold:
        return {"status": "no_gold", "n": 0}
    rng = random.Random(seed)
    rng.shuffle(gold)
    sample = gold[:int(sample_size)]

    store = get_vectorstore()
    from ragapp.graph.rag_graph import answer_query
    judge = get_llm(settings.LLM_MODEL)   # grosses Modell fuer das Urteil

    korr, voll, treu = [], [], []
    fallback = badcite = 0
    rows = []
    for i, g in enumerate(sample, 1):
        if progress:
            progress(f"Antwort-Eval {i}/{len(sample)} …")
        try:
            res = answer_query(g["question"], subject=None)
        except Exception:  # noqa: BLE001
            continue
        ans = res.get("answer", "")
        n_src = len(res.get("sources", []))
        if res.get("mode") != "answer":
            fallback += 1
        if _invalid_citations(ans, n_src):
            badcite += 1
        src_txt = (store.get_by_ids([g["chunk_id"]]) or {}).get(g["chunk_id"], {}).get("document", "")
        try:
            j = judge.generate_json(
                _JUDGE_PROMPT.format(frage=g["question"], quelle=src_txt[:2500], antwort=ans[:2000]),
                system=_JUDGE_SYSTEM, temperature=0.0)
        except Exception:  # noqa: BLE001
            j = {}
        k, v, t = _num(j.get("korrektheit")), _num(j.get("vollstaendigkeit")), _num(j.get("treue"))
        if k is not None:
            korr.append(k)
        if v is not None:
            voll.append(v)
        if t is not None:
            treu.append(t)
        rows.append({"frage": g["question"], "mode": res.get("mode"),
                     "korrektheit": k, "vollstaendigkeit": v, "treue": t})

    n = len(sample)
    result = {"status": "ok", "n": n, "ts": time.time(),
              "korrektheit": _avg(korr), "vollstaendigkeit": _avg(voll), "treue": _avg(treu),
              "fallback_pct": round(100 * fallback / n) if n else 0,
              "invalid_citation_pct": round(100 * badcite / n) if n else 0,
              "rows": rows}
    _append_history(result)
    return result


def _append_history(result: dict) -> None:
    try:
        EVAL_DIR.mkdir(parents=True, exist_ok=True)
        entry = {k: result[k] for k in ("ts", "n", "korrektheit", "vollstaendigkeit",
                                        "treue", "fallback_pct", "invalid_citation_pct")
                 if k in result}
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


def load_answer_history() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    out = []
    with open(HISTORY_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    continue
    return out
