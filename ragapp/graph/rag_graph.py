"""
LangGraph-RAG-Ablauf (mit Anti-Halluzination & Dokument-Fallback)
=================================================================

Graph:

    START
      │
   [retrieve]  ── Hybrid-Retrieval (dense+BM25+Rerank)
      │
      ├─ (kein/zu schwacher Treffer) ─────────────► [fallback]
      │
   [generate]  ── Antwort NUR aus Kontext
      │
      ├─ (Modell: "keine Info") ──────────────────► [fallback]
      │
   [faithfulness] ── LLM prüft Belegtheit
      │
      ├─ (nicht belegt) ──────────────────────────► [fallback]
      │
      └─ (belegt) ────────────────────────────────► END

Der **Fallback** halluziniert nicht: Er sagt ehrlich, dass keine sichere Antwort
möglich ist, und gibt die am besten passenden Dokumente/Stellen aus.
"""
from __future__ import annotations

import time
from typing import Optional, TypedDict

from langgraph.graph import StateGraph, START, END

from ragapp.config import settings
from ragapp.llm import get_llm
from ragapp.retrieval.hybrid import retrieve
from ragapp.graph.prompts import (
    ANSWER_SYSTEM, ANSWER_PROMPT, FAITHFULNESS_PROMPT, NO_ANSWER_TOKEN,
)


class RAGState(TypedDict, total=False):
    question: str
    subject: Optional[str]
    candidates: list[dict]
    sources: list[dict]
    context: str
    answer: str
    mode: str                # "answer" | "fallback"
    grounded: Optional[bool]
    faithfulness_reason: str
    relevance_ok: bool
    timings: dict


def _source_entry(c: dict, rank: int) -> dict:
    meta = c["meta"]
    return {
        "rank": rank,
        "filename": meta.get("filename", "?"),
        "subject": meta.get("subject", "?"),
        "location": meta.get("location", ""),
        "source_path": meta.get("source_path", ""),
        "score": round(c.get("rerank_score", c.get("fusion_score", 0.0)), 4),
        "retrievers": c.get("retrievers", ""),
        "snippet": c["document"][:400],
        "document": c["document"],
    }


def _build_context(candidates: list[dict]) -> tuple[str, list[dict]]:
    parts, sources = [], []
    used = 0
    for i, c in enumerate(candidates, 1):
        block = f"[Quelle {i}] ({c['meta'].get('filename','?')}, {c['meta'].get('location','')})\n{c['document']}"
        if used + len(block) > settings.MAX_CONTEXT_CHARS and parts:
            break
        parts.append(block)
        used += len(block)
        sources.append(_source_entry(c, i))
    return "\n\n---\n\n".join(parts), sources


# --------------------------------------------------------------------------- #
# Knoten
# --------------------------------------------------------------------------- #
def retrieve_node(state: RAGState) -> RAGState:
    t0 = time.time()
    candidates = retrieve(state["question"], state.get("subject"))
    top_score = candidates[0].get("rerank_score", candidates[0].get("fusion_score", 0.0)) if candidates else None
    relevance_ok = bool(candidates) and (
        top_score is None or top_score >= settings.RELEVANCE_MIN_SCORE
    )
    timings = dict(state.get("timings", {}))
    timings["retrieve"] = round(time.time() - t0, 2)
    return {
        "candidates": candidates,
        "relevance_ok": relevance_ok,
        "timings": timings,
    }


def generate_node(state: RAGState) -> RAGState:
    t0 = time.time()
    context, sources = _build_context(state["candidates"])
    prompt = ANSWER_PROMPT.format(
        context=context, question=state["question"], no_answer=NO_ANSWER_TOKEN
    )
    answer = get_llm().generate(prompt, system=ANSWER_SYSTEM).strip()
    timings = dict(state.get("timings", {}))
    timings["generate"] = round(time.time() - t0, 2)
    return {"answer": answer, "context": context, "sources": sources, "timings": timings}


def faithfulness_node(state: RAGState) -> RAGState:
    if not settings.ENABLE_FAITHFULNESS_CHECK:
        return {"grounded": True, "mode": "answer"}
    t0 = time.time()
    # schnelles Modell für die interne Belegtheits-Prüfung (spart CPU-Zeit)
    data = get_llm(settings.LLM_MODEL_FAST).generate_json(
        FAITHFULNESS_PROMPT.format(context=state["context"], answer=state["answer"])
    )
    # Fail-closed: nur bei explizitem, eindeutigem "ja" gilt die Antwort als belegt.
    # Bei None/Parse-Fehler/mehrdeutigem Wert -> nicht belegt -> Fallback (kein
    # Halluzinationsrisiko). (bool("false") wäre True -> deshalb strikte Prüfung.)
    val = data.get("grounded") if isinstance(data, dict) else None
    if isinstance(val, bool):
        grounded = val
    elif isinstance(val, str):
        grounded = val.strip().lower() in {"true", "ja", "yes", "1", "belegt"}
    else:
        grounded = False
    reason = data.get("grund", "") if isinstance(data, dict) else ""
    timings = dict(state.get("timings", {}))
    timings["faithfulness"] = round(time.time() - t0, 2)
    return {
        "grounded": grounded,
        "faithfulness_reason": reason,
        "mode": "answer" if grounded else "fallback",
        "timings": timings,
    }


def fallback_node(state: RAGState) -> RAGState:
    """Ehrlicher Fallback: keine erfundene Antwort, sondern passende Dokumente."""
    candidates = state.get("candidates", [])
    if not candidates:
        msg = ("Zu dieser Frage habe ich in deinen Zusammenfassungen **keine passende "
               "Stelle** gefunden. Vielleicht ist das Thema (noch) nicht enthalten, "
               "oder die Frage lässt sich anders formulieren.")
        return {"answer": msg, "mode": "fallback", "sources": [], "grounded": False}

    sources = state.get("sources") or [_source_entry(c, i) for i, c in enumerate(candidates[:settings.FINAL_TOP_K], 1)]
    lines = [
        "Ich bin mir **nicht sicher genug**, um diese Frage zuverlässig aus deinen "
        "Unterlagen zu beantworten (ich möchte nichts erfinden).",
        "",
        "Am besten passen diese Stellen – schau am besten direkt dort nach:",
        "",
    ]
    for s in sources[:settings.FINAL_TOP_K]:
        loc = f", {s['location']}" if s.get("location") else ""
        lines.append(f"- **{s['filename']}**{loc}  ·  _{s['subject']}_")
    return {"answer": "\n".join(lines), "mode": "fallback",
            "sources": sources, "grounded": False}


# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #
def route_after_retrieve(state: RAGState) -> str:
    return "generate" if state.get("relevance_ok") else "fallback"


def route_after_generate(state: RAGState) -> str:
    answer = state.get("answer", "")
    if NO_ANSWER_TOKEN in answer or not answer.strip():
        return "fallback"
    return "faithfulness"


def route_after_faithfulness(state: RAGState) -> str:
    return "end" if state.get("grounded") else "fallback"


# --------------------------------------------------------------------------- #
# Graph bauen
# --------------------------------------------------------------------------- #
def build_graph():
    g = StateGraph(RAGState)
    g.add_node("retrieve", retrieve_node)
    g.add_node("generate", generate_node)
    g.add_node("faithfulness", faithfulness_node)
    g.add_node("fallback", fallback_node)

    g.add_edge(START, "retrieve")
    g.add_conditional_edges("retrieve", route_after_retrieve,
                            {"generate": "generate", "fallback": "fallback"})
    g.add_conditional_edges("generate", route_after_generate,
                            {"faithfulness": "faithfulness", "fallback": "fallback"})
    g.add_conditional_edges("faithfulness", route_after_faithfulness,
                            {"end": END, "fallback": "fallback"})
    g.add_edge("fallback", END)
    return g.compile()


_compiled = None


def get_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_graph()
    return _compiled


def answer_query(question: str, subject: Optional[str] = None) -> dict:
    """Öffentliche Schnittstelle für UI/CLI. Führt den Graphen aus."""
    t0 = time.time()
    state: RAGState = {"question": question, "subject": subject, "mode": "answer"}
    result = get_graph().invoke(state)
    result["total_time"] = round(time.time() - t0, 2)
    # Query-Log für spätere Analyse/Nachjustierung
    _log_query(question, subject, result)
    return result


def _log_query(question: str, subject: Optional[str], result: dict) -> None:
    import json
    from ragapp.config import LOG_DIR
    try:
        entry = {
            "ts": time.time(),
            "question": question,
            "subject": subject,
            "mode": result.get("mode"),
            "grounded": result.get("grounded"),
            "top_sources": [s.get("filename") for s in result.get("sources", [])[:3]],
            "timings": result.get("timings", {}),
            "total_time": result.get("total_time"),
        }
        with open(LOG_DIR / "queries.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
