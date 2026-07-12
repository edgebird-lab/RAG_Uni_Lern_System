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
    search_query: str        # fuer die Suche genutzte (ggf. verlaufsbereinigte) Frage
    sub_queries: list        # Teilfragen bei breiten Fragen (vergleiche/nenne alle/...)
    subject: Optional[str]
    use_reranker: Optional[bool]        # None = Einstellung, False = "Schnelle Antworten"
    check_faithfulness: Optional[bool]  # None = Einstellung, False = "Schnelle Antworten"
    candidates: list[dict]
    sources: list[dict]
    context: str
    answer: str
    mode: str                # "answer" | "fallback"
    grounded: Optional[bool]
    faith_checked: bool       # wurde die Beleg-Prüfung tatsächlich ausgeführt?
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
    # Fuer die Suche die (ggf. verlaufsbereinigte) eigenstaendige Frage nutzen;
    # die Antwort/Zitate arbeiten weiterhin mit der Originalfrage (state["question"]).
    # Bei breiten Fragen (vergleiche/nenne alle/mehrschritt) zusaetzlich fuer jede
    # Teilfrage suchen und die Treffer zusammenfuehren -> bessere Abdeckung.
    queries = [state.get("search_query") or state["question"]]
    queries += [q for q in (state.get("sub_queries") or []) if q]
    use_rr = state.get("use_reranker")
    subj = state.get("subject")
    merged: dict = {}
    for qq in queries:
        for c in retrieve(qq, subj, use_reranker=use_rr):
            key = (c.get("document") or "")[:120]
            sc = c.get("rerank_score", c.get("fusion_score", 0.0))
            prev = merged.get(key)
            if prev is None or sc > prev.get("rerank_score", prev.get("fusion_score", -1e9)):
                merged[key] = c
    candidates = sorted(
        merged.values(),
        key=lambda c: c.get("rerank_score", c.get("fusion_score", 0.0)), reverse=True)
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
    # Pro Anfrage abschaltbar ("Schnelle Antworten"): None = globale Einstellung.
    enabled = (settings.ENABLE_FAITHFULNESS_CHECK
               if state.get("check_faithfulness") is None
               else state.get("check_faithfulness"))
    if not enabled:
        # Nicht geprüft -> die Antwort NICHT als "belegt" auszeichnen (ehrlich bleiben).
        return {"grounded": True, "mode": "answer", "faith_checked": False}
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
        "faith_checked": True,
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
        "Am besten passen diese Stellen, schau am besten direkt dort nach:",
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


# --------------------------------------------------------------------------- #
# Verlaufsbewusstes Query-Rewriting (Rueckfragen eigenstaendig machen)
# --------------------------------------------------------------------------- #
_CONDENSE_PROMPT = (
    "Formuliere die folgende Anschlussfrage zu EINER eigenständigen, vollständigen "
    "Suchanfrage um, die ohne den bisherigen Gesprächsverlauf verständlich ist. Löse "
    "Bezüge wie 'das', 'dazu', 'und warum', 'ein Beispiel' anhand des Verlaufs auf. "
    "Antworte NUR mit der umformulierten Frage – ohne Erklärung, ohne Anführungszeichen.\n\n"
    "Gesprächsverlauf:\n{history}\n\nAnschlussfrage: {question}\n\nEigenständige Frage:"
)
_FOLLOWUP_MARKERS = ("und ", "warum", "wieso", "weshalb", "wozu", "wofür", "beispiel",
                     "genauer", "mehr", "erklär", "das ", "dies", "davon", "dazu",
                     "daran", "unterschied", "vergleich", "welche", "was noch")


def _looks_followup(q: str) -> bool:
    """Grobe Heuristik: kurze/anaphorische Frage -> vermutlich Rueckfrage."""
    ql = (q or "").strip().lower()
    if not ql:
        return False
    if len(ql.split()) <= 6:
        return True
    return any(ql.startswith(m) or f" {m}" in f" {ql}" for m in _FOLLOWUP_MARKERS)


def _condense_query(question: str, history: list) -> str:
    """Formuliert eine Rueckfrage anhand der letzten Turns eigenstaendig um.
    Faellt bei jedem Fehler auf die Originalfrage zurueck (kein Risiko)."""
    turns = [h for h in (history or []) if h.get("content")][-4:]
    if not turns:
        return question
    hist = "\n".join((("Frage" if h.get("role") == "user" else "Antwort") + ": "
                      + (h.get("content") or "")[:400]) for h in turns)
    try:
        rewritten = get_llm(settings.LLM_MODEL_FAST).generate(
            _CONDENSE_PROMPT.format(history=hist, question=question)).strip()
        rewritten = rewritten.splitlines()[0].strip().strip('"„“') if rewritten else ""
        if rewritten and 3 <= len(rewritten) <= 300:
            return rewritten
    except Exception:  # noqa: BLE001
        pass
    return question


# --------------------------------------------------------------------------- #
# Fragetyp-Router: breite Fragen (vergleiche / nenne alle / mehrschritt) zerlegen
# --------------------------------------------------------------------------- #
_BROAD_MARKERS = ("vergleich", "unterschied", "gegenüber", "gegenueber", "nenne alle",
                  "alle ", "welche ", "vor- und nach", "vor und nach", "sowie",
                  "zusammenhang zwischen", "mehrere", "aufzählen", "aufzaehlen",
                  "liste", "schritte", "herleit")

_DECOMPOSE_PROMPT = (
    "Zerlege die folgende, breit gestellte Pruefungsfrage in 2-4 KURZE, eigenstaendige "
    "Teilfragen, die zusammen die ganze Frage abdecken (z. B. je Vergleichsseite, je "
    "geforderten Punkt, je Rechenschritt). Antworte NUR mit JSON: "
    '{{"teilfragen": ["...", "..."]}}\n\nFrage: {frage}')


def _is_broad(question: str) -> bool:
    ql = (question or "").lower()
    if ql.count("?") >= 2:
        return True
    return any(m in ql for m in _BROAD_MARKERS)


def _decompose_query(question: str) -> list:
    """Zerlegt eine breite Frage in Teilfragen (fuers Retrieval). Faellt bei jedem
    Fehler auf [] zurueck (dann normale Einzel-Suche)."""
    try:
        data = get_llm(settings.LLM_MODEL_FAST).generate_json(
            _DECOMPOSE_PROMPT.format(frage=question))
    except Exception:  # noqa: BLE001
        return []
    subs = data.get("teilfragen") if isinstance(data, dict) else None
    out = []
    for s in (subs or []):
        s = str(s).strip()
        if s and 5 <= len(s) <= 200:
            out.append(s)
    return out[:4]


def answer_query(question: str, subject: Optional[str] = None,
                 use_reranker: Optional[bool] = None,
                 check_faithfulness: Optional[bool] = None,
                 history: Optional[list] = None,
                 decompose: bool = True) -> dict:
    """Öffentliche Schnittstelle für UI/CLI. Führt den Graphen aus.

    use_reranker / check_faithfulness: None = globale Einstellung; False =
    überspringen ("Schnelle Antworten" auf der Startseite -> schneller, dafür
    gröbere Trefferreihenfolge bzw. keine zusätzliche Beleg-Prüfung).
    history: bisherige Chat-Nachrichten -> kurze Rückfragen werden für die Suche zu
    eigenständigen Fragen umformuliert (die Antwort nutzt die Originalfrage)."""
    t0 = time.time()
    search_query = question
    if history and _looks_followup(question):
        search_query = _condense_query(question, history)
    sub_queries = _decompose_query(search_query) if (decompose and _is_broad(question)) else []
    state: RAGState = {"question": question, "search_query": search_query,
                       "sub_queries": sub_queries, "subject": subject,
                       "use_reranker": use_reranker,
                       "check_faithfulness": check_faithfulness, "mode": "answer"}
    result = get_graph().invoke(state)
    if search_query != question:
        result["search_query"] = search_query
    if sub_queries:
        result["sub_queries"] = sub_queries
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
