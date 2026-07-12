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

import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, TypedDict

from langgraph.graph import StateGraph, START, END

from ragapp.config import settings
from ragapp.llm import get_llm, diagnose_error
from ragapp.retrieval.hybrid import retrieve
from ragapp.retrieval.reranker import get_reranker
from ragapp.graph.prompts import (
    ANSWER_SYSTEM, ANSWER_PROMPT, FAITHFULNESS_PROMPT, NO_ANSWER_TOKEN,
)

# Logger (zentrales Setup; faellt defensiv auf die stdlib zurueck, falls das Modul
# in einer Teil-Installation noch nicht vorhanden ist).
try:
    from ragapp.logging_setup import get_logger
    _log = get_logger(__name__)
except Exception:  # pragma: no cover - defensiver Fallback
    import logging as _logging
    _log = _logging.getLogger(__name__)


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
    # Vertrauens-Badge fuer die UI. Werte:
    #   "belegt"     -> Faithfulness-Check bestanden
    #   "unsicher"   -> Check unsicher/negativ, Antwort aber behalten (nicht sicher belegt)
    #   "ungeprueft" -> Faithfulness-Check war abgeschaltet
    #   "fallback"   -> Dokument-Fallback (keine frei formulierte Antwort)
    confidence: str
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


# --------------------------------------------------------------------------- #
# S5: Prompt-Injection-Haertung des Kontexts
# --------------------------------------------------------------------------- #
# Kontext-Chunks sind NICHT vertrauenswuerdige DATEN (Dokument-/OCR-Inhalte). Ein
# praepariertes Dokument koennte die Prompt-Struktur aufbrechen. Diese Muster werden
# im Dokumenttext neutralisiert, BEVOR er in einen Prompt eingebettet wird:
#   * Dreifach-Anfuehrungszeichen (Delimiter der GRADE-/FAITHFULNESS-Prompts),
#   * die <KONTEXT>-Markierungen des Antwort-Prompts,
#   * der Antwort-Sentinel (koennte sonst "keine Info" einschleusen),
#   * gefaelschte [Quelle N]-Zitatmarker.
_TRIPLE_QUOTE_RE = re.compile(r'"{3,}')
_KONTEXT_TAG_RE = re.compile(r'</?\s*KONTEXT\s*>', re.IGNORECASE)
_FAKE_CITE_RE = re.compile(r'\[\s*Quelle\b', re.IGNORECASE)


def _sanitize_context_text(text: str) -> str:
    """Neutralisiert Delimiter/Marker in nicht vertrauenswuerdigem Dokumenttext,
    damit er die Prompt-Struktur nicht aufbrechen oder Anweisungen einschleusen kann.
    Aendert nur potenzielle Kontrollsequenzen, nicht den fachlichen Inhalt."""
    if not text:
        return text
    text = _TRIPLE_QUOTE_RE.sub('"', text)                 # """-Fence entschaerfen
    text = _KONTEXT_TAG_RE.sub("(kontext)", text)          # <KONTEXT>/</KONTEXT> entschaerfen
    text = text.replace(NO_ANSWER_TOKEN, "KEINE AUSREICHENDE INFORMATION")  # Sentinel entschaerfen
    text = _FAKE_CITE_RE.sub("[ Quelle", text)             # gefaelschte Zitatmarker entschaerfen
    return text


def _build_context(candidates: list[dict]) -> tuple[str, list[dict]]:
    parts, sources = [], []
    used = 0
    for i, c in enumerate(candidates, 1):
        doc = _sanitize_context_text(c["document"])
        block = f"[Quelle {i}] ({c['meta'].get('filename','?')}, {c['meta'].get('location','')})\n{doc}"
        if used + len(block) > settings.MAX_CONTEXT_CHARS and parts:
            break
        parts.append(block)
        used += len(block)
        sources.append(_source_entry(c, i))
    return "\n\n---\n\n".join(parts), sources


# --------------------------------------------------------------------------- #
# Knoten
# --------------------------------------------------------------------------- #
def _fusion_candidates(query: str, subject: Optional[str]) -> list[dict]:
    """Nur die Fusionskandidaten einer (Teil-)Frage holen – OHNE den teuren
    Cross-Encoder-Rerank (use_reranker=False). ``final_top_k=FUSION_TOP_K`` liefert
    genug Kandidaten zum Poolen (statt nur der finalen FINAL_TOP_K)."""
    return retrieve(query, subject, final_top_k=settings.FUSION_TOP_K,
                    use_reranker=False)


def _pool_fusion_candidates(queries: list[str], subject: Optional[str]) -> list[dict]:
    """Fusionskandidaten aller (Teil-)Fragen poolen und per Dokument deduplizieren
    (hoeheren fusion_score behalten). Mehrere Teilfragen werden parallel gesucht."""
    results: list[list[dict]]
    if len(queries) > 1:
        # Rein lesende Fusionssuchen (Embedding/Chroma/BM25) -> parallelisierbar.
        # Fehler einer Teilfrage duerfen den Gesamtlauf nicht kippen.
        results = []
        with ThreadPoolExecutor(max_workers=min(4, len(queries))) as pool:
            futures = [pool.submit(_fusion_candidates, qq, subject) for qq in queries]
            for fut in futures:
                try:
                    results.append(fut.result())
                except Exception as exc:  # noqa: BLE001
                    _log.warning("Fusionssuche fuer Teilfrage fehlgeschlagen: %s", exc)
                    results.append([])
    else:
        results = [_fusion_candidates(queries[0], subject)]

    pooled: dict = {}
    for cand_list in results:
        for c in cand_list:
            key = (c.get("document") or "")[:120]
            sc = c.get("fusion_score", 0.0)
            prev = pooled.get(key)
            if prev is None or sc > prev.get("fusion_score", -1e9):
                pooled[key] = c
    # Nach fusion_score sortieren: Im Schnell-Modus (Reranker AUS) uebernimmt
    # reranker.rerank die bestehende Reihenfolge und schneidet auf FINAL_TOP_K ab –
    # ohne Vorsortierung wuerde sonst die Dict-Einfuegereihenfolge gewinnen.
    return sorted(pooled.values(),
                  key=lambda c: c.get("fusion_score", 0.0), reverse=True)


def _relevance_ok(candidates: list[dict]) -> bool:
    """Relevanz-Gate: waehlt die zur genutzten Score-Quelle passende, WIRKSAME
    Schwelle.
      * Reranker AKTIV -> Cross-Encoder-Logit gegen RELEVANCE_MIN_SCORE (Logit-Skala).
      * Reranker AUS (Schnell-Modus) -> der RRF-Fusionswert ist rangbasiert und misst
        KEINE Relevanz; deshalb auf die DENSE-Kosinus-Aehnlichkeit (bge-m3) des
        Top-Treffers gaten (echtes Relevanzsignal) gegen DENSE_RELEVANCE_MIN_SCORE.
        Nur wenn der Top-Treffer keinen Dense-Score hat (rein aus BM25), bleibt der
        RRF-Mindestwert der Rueckfall.
    Datengetrieben unterschieden: bei aktivem Rerank ist rerank_score != fusion_score;
    im Fusions-Fall setzt reranker.rerank rerank_score = fusion_score."""
    if not candidates:
        return False
    top = candidates[0]
    rr = top.get("rerank_score")
    fu = top.get("fusion_score")
    if rr is None:                     # kein Score vorhanden -> nicht blockieren
        return True
    reranked = (fu is None) or (rr != fu)
    if reranked:
        return rr >= settings.RELEVANCE_MIN_SCORE
    # Schnell-Modus: "gibt es ueberhaupt EINEN semantisch relevanten Chunk?" – daher
    # das BESTE Dense-Signal ueber ALLE Kandidaten, nicht nur candidates[0]. Sonst
    # koennte ein rein per BM25 (Stichwort) nach oben gespuelter, semantisch schwacher
    # Top-1-Treffer die ganze Frage faelschlich in den Fallback schicken, obwohl der
    # eigentlich passende Treffer knapp dahinter liegt.
    dense = [c.get("dense_score") for c in candidates if c.get("dense_score") is not None]
    if dense:
        return max(dense) >= settings.DENSE_RELEVANCE_MIN_SCORE
    return (fu or 0.0) >= settings.RELEVANCE_MIN_FUSION_SCORE


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
    # R2: pro Teilfrage NUR Fusionskandidaten holen, alle poolen (dedupe) und dann
    # EINMAL gegen die urspruengliche Originalfrage (queries[0]) reranken. So laeuft
    # der teure Cross-Encoder genau einmal (statt N-fach) und die Rangfolge bleibt an
    # der echten Nutzerintention konsistent (kein max()-Mix von Teilfrage-Scores).
    pool = _pool_fusion_candidates(queries, subj)
    candidates = get_reranker().rerank(
        queries[0], pool, top_k=settings.FINAL_TOP_K, use_reranker=use_rr)
    timings = dict(state.get("timings", {}))
    timings["retrieve"] = round(time.time() - t0, 2)
    return {
        "candidates": candidates,
        "relevance_ok": _relevance_ok(candidates),
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
        return {"grounded": True, "mode": "answer", "faith_checked": False,
                "confidence": "ungeprueft"}
    t0 = time.time()
    # schnelles Modell für die interne Belegtheits-Prüfung (spart CPU-Zeit)
    data = get_llm(settings.LLM_MODEL_FAST).generate_json(
        FAITHFULNESS_PROMPT.format(context=state["context"], answer=state["answer"])
    )
    # DREI Zustaende unterscheiden (nicht nur belegt/unbelegt), damit R5 nicht ins
    # Gegenteil kippt: (bool("false") waere True -> deshalb strikte Pruefung.)
    #   belegt     -> Modell sagt eindeutig JA
    #   unbelegt   -> Modell sagt eindeutig NEIN (es ist sich SICHER: nicht belegt)
    #   unsicher   -> None / Parse-Fehler / mehrdeutig (kleines 4B-Modell hat gehedged)
    val = data.get("grounded") if isinstance(data, dict) else None
    if isinstance(val, bool):
        verdict = "belegt" if val else "unbelegt"
    elif isinstance(val, str):
        # Robust gegen mehrwortige/gehedgte Urteile ("nein, nicht gedeckt"): per
        # Praefix/Teilstring statt Exakt-Match. NEGATIV hat Vorrang (Anti-Halluzination:
        # ein klar unbelegtes Urteil darf nicht als 'unsicher' die Antwort behalten).
        v = val.strip().lower()
        neg = (v.startswith(("false", "nein", "no", "unbelegt"))
               or "nicht belegt" in v or "nicht gedeckt" in v
               or "nicht im kontext" in v or v == "0")
        pos = v.startswith(("true", "ja", "yes", "belegt")) or v == "1"
        verdict = "unbelegt" if neg else ("belegt" if pos else "unsicher")
    else:
        verdict = "unsicher"
    reason = data.get("grund", "") if isinstance(data, dict) else ""
    timings = dict(state.get("timings", {}))
    timings["faithfulness"] = round(time.time() - t0, 2)
    # R5 ausbalanciert: eine mit [Quelle N] belegte Antwort NICHT mehr komplett
    # verwerfen, nur weil das kleine Modell unsicher ist – aber die Anti-Halluzination
    # erhalten, wenn es sich SICHER ist, dass nichts belegt ist.
    #   belegt   -> gruenes Badge, Antwort behalten.
    #   unbelegt -> ehrlicher Dokument-Fallback (Modell ist sicher: nicht belegt).
    #   unsicher -> Antwort BEHALTEN, aber Vertrauen herabstufen (Badge "nicht sicher
    #               belegt", von der UI gelesen) statt eine evtl. gute Antwort wegzuwerfen.
    # (Der frühere 'elif not relevance_ok'-Zweig war toter Code: faithfulness wird nur
    #  erreicht, wenn relevance_ok bereits True ist – route_after_retrieve gated davor.)
    if verdict == "belegt":
        grounded, mode, confidence = True, "answer", "belegt"
    elif verdict == "unbelegt":
        grounded, mode, confidence = False, "fallback", "fallback"
    else:
        grounded, mode, confidence = False, "answer", "unsicher"
    return {
        "grounded": grounded,
        "faith_checked": True,
        "faithfulness_reason": reason,
        "mode": mode,
        "confidence": confidence,
        "timings": timings,
    }


def fallback_node(state: RAGState) -> RAGState:
    """Ehrlicher Fallback: keine erfundene Antwort, sondern passende Dokumente."""
    candidates = state.get("candidates", [])
    if not candidates:
        msg = ("Zu dieser Frage habe ich in deinen Zusammenfassungen **keine passende "
               "Stelle** gefunden. Vielleicht ist das Thema (noch) nicht enthalten, "
               "oder die Frage lässt sich anders formulieren.")
        return {"answer": msg, "mode": "fallback", "sources": [],
                "grounded": False, "confidence": "fallback"}

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
            "sources": sources, "grounded": False, "confidence": "fallback"}


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
    # R5: nicht mehr strikt an grounded haengen. Der Faithfulness-Knoten entscheidet
    # ueber mode ("answer" behalten vs. "fallback"); wir folgen dieser Entscheidung.
    return "fallback" if state.get("mode") == "fallback" else "end"


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


def answer_query_stream(question: str, subject: Optional[str] = None,
                        use_reranker: Optional[bool] = None,
                        check_faithfulness: Optional[bool] = None,
                        history: Optional[list] = None,
                        decompose: bool = True):
    """Streaming-Variante von :func:`answer_query` fuer den SCHNELL-Modus.

    Rueckgabe ``(stream, holder)``:
        * ``stream`` - Generator ueber Antwort-Token (``str``). Erschoepft man ihn
          (z. B. via ``st.write_stream`` oder einer ``for``-Schleife), rendert er die
          Antwort Token fuer Token. ``None``, wenn NICHT gestreamt werden soll
          (strenger Modus mit aktiver Gegenpruefung) - der Aufrufer nutzt dann das
          blockierende :func:`answer_query`.
        * ``holder`` - anfangs leeres ``dict``, das NACH dem Erschoepfen des Streams
          die vollstaendigen Ergebnisfelder traegt (answer/sources/mode/confidence/
          faith_checked/timings/total_time - analog zu :func:`answer_query`). Vor dem
          Erschoepfen nicht auslesen.

    Warum nur im Schnell-Modus: Bei aktiver Gegenpruefung (Faithfulness) kann die
    Antwort nach der Generierung noch verworfen werden - dann haette man bereits
    verworfenen Text gestreamt. Im Schnell-Modus entfaellt dieser Schritt (konsistent
    zu R5: Badge ``ungeprueft``), Streaming ist also gefahrlos. Die oeffentliche
    :func:`answer_query`-Signatur bleibt unveraendert - dieser Pfad ist rein additiv.
    """
    faith_enabled = (settings.ENABLE_FAITHFULNESS_CHECK
                     if check_faithfulness is None else check_faithfulness)
    if faith_enabled:
        # Strenger Modus: nicht streamen (Aufrufer nimmt das blockierende answer_query).
        return None, {}

    holder: dict = {}

    def _gen():
        t0 = time.time()
        flushed = False              # wurde bereits echter Antworttext ausgegeben?
        accumulated: list[str] = []
        try:
            # 1) Vorbereitung wie in answer_query: Rueckfrage verselbststaendigen,
            #    breite Fragen fuers Retrieval zerlegen.
            search_query = question
            if history and _looks_followup(question):
                search_query = _condense_query(question, history)
            sub_queries = _decompose_query(search_query) \
                if (decompose and _is_broad(question)) else []
            queries = [search_query] + [q for q in sub_queries if q]

            # 2) Retrieval + (optionaler) Rerank - identisch zu retrieve_node.
            tr = time.time()
            pool = _pool_fusion_candidates(queries, subject)
            candidates = get_reranker().rerank(
                queries[0], pool, top_k=settings.FINAL_TOP_K, use_reranker=use_reranker)
            relevance_ok = _relevance_ok(candidates)
            timings = {"retrieve": round(time.time() - tr, 2)}

            base: dict = {"question": question, "subject": subject,
                          "candidates": candidates, "relevance_ok": relevance_ok}
            if search_query != question:
                base["search_query"] = search_query
            if sub_queries:
                base["sub_queries"] = sub_queries

            # 3) Relevanz-Gate: kein tragfaehiger Treffer -> ehrlicher Dokument-Fallback
            #    (kein LLM-Text; die Fallback-Meldung wird als ein Block ausgegeben).
            if not relevance_ok:
                fb = fallback_node({"candidates": candidates})
                yield fb.get("answer", "")
                holder.update(base)
                holder.update(fb)
                holder["faith_checked"] = False
                holder["timings"] = timings
                return

            # 4) Kontext bauen und Antwort Token fuer Token streamen.
            context, sources = _build_context(candidates)
            prompt = ANSWER_PROMPT.format(
                context=context, question=question, no_answer=NO_ANSWER_TOKEN)
            tg = time.time()

            # "Keine-Info"-Schutz: einen kleinen Kopf puffern, BEVOR gestreamt wird -
            # so wird der reine NO_ANSWER-Sentinel nie sichtbar (dann Dokument-Fallback),
            # ohne das Streaming spuerbar zu verzoegern (nur die ersten ~40 Zeichen).
            head = ""
            guard = len(NO_ANSWER_TOKEN) + 12
            no_answer = False
            for delta in get_llm().generate_stream(prompt, system=ANSWER_SYSTEM):
                accumulated.append(delta)
                if flushed:
                    yield delta
                    continue
                head += delta
                if NO_ANSWER_TOKEN in head:
                    no_answer = True
                    break
                if len(head) >= guard:
                    flushed = True
                    yield head
            if not no_answer and not flushed:        # kurze Antwort: Puffer noch offen
                if NO_ANSWER_TOKEN in head:
                    no_answer = True
                else:
                    flushed = True
                    yield head

            timings["generate"] = round(time.time() - tg, 2)
            answer = "".join(accumulated).replace(NO_ANSWER_TOKEN, "").strip()

            # 5a) Modell signalisiert "keine Info" (oder leer) -> Dokument-Fallback.
            if no_answer or not answer:
                fb = fallback_node({"candidates": candidates, "sources": sources})
                if not flushed:                      # noch nichts ausgegeben -> Fallback zeigen
                    yield fb.get("answer", "")
                holder.update(base)
                holder.update(fb)
                holder["faith_checked"] = False
                holder["timings"] = timings
                return

            # 5b) Erfolg: belegte, im Schnell-Modus aber NICHT gegengeprüfte Antwort
            #     (mode="answer"/confidence="ungeprueft" - konsistent zu faithfulness_node
            #     bei abgeschalteter Pruefung).
            holder.update(base)
            holder.update({
                "answer": answer,
                "context": context,
                "sources": sources,
                "mode": "answer",
                "grounded": True,
                "faith_checked": False,
                "confidence": "ungeprueft",
                "timings": timings,
            })
        except Exception as exc:  # noqa: BLE001 - Netz-/Backend-Fehler nie roh anzeigen
            _log.warning("Streaming-Antwort fehlgeschlagen: %s", exc)
            msg = diagnose_error(exc)
            partial = "".join(accumulated).strip()
            if flushed:                              # schon Text sichtbar -> Hinweis anhaengen
                yield "\n\n_" + msg + "_"
            else:                                    # noch nichts sichtbar -> Fehlermeldung zeigen
                yield msg
            holder.setdefault("answer", (partial + ("\n\n" + msg if partial else msg)).strip())
            holder.setdefault("sources", [])
            holder.setdefault("mode", "fallback")
            holder.setdefault("grounded", False)
            holder.setdefault("confidence", "fallback")
            holder.setdefault("faith_checked", False)
        finally:
            holder.setdefault("answer", "")
            holder["total_time"] = round(time.time() - t0, 2)
            try:
                _log_query(question, subject, holder)
            except Exception:  # noqa: BLE001 - Logging darf den Antwortpfad nie stoeren
                pass

    return _gen(), holder


# Groessenbasierte Rotation des Query-Logs: waechst es ueber diese Groesse, wird es
# einmalig auf ".1" umbenannt (ein Backup, keine Endlos-Historie).
_QUERIES_LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


def _rotate_if_large(path, max_bytes: int = _QUERIES_LOG_MAX_BYTES) -> None:
    """Rotiert ``path`` auf ``<name>.1``, sobald es ``max_bytes`` uebersteigt.
    Fehler sind unkritisch (Logging darf den Antwortpfad nie stoeren)."""
    try:
        if path.exists() and path.stat().st_size > max_bytes:
            backup = path.parent / (path.name + ".1")
            try:
                if backup.exists():
                    backup.unlink()
            except OSError:
                pass
            path.replace(backup)
    except OSError as exc:
        _log.debug("Rotation von %s fehlgeschlagen: %s", path, exc)


def _log_query(question: str, subject: Optional[str], result: dict) -> None:
    import json
    from ragapp.config import LOG_DIR
    try:
        log_path = LOG_DIR / "queries.jsonl"
        _rotate_if_large(log_path)
        entry = {
            "ts": time.time(),
            "question": question,
            "subject": subject,
            "mode": result.get("mode"),
            "grounded": result.get("grounded"),
            "confidence": result.get("confidence"),
            "top_sources": [s.get("filename") for s in result.get("sources", [])[:3]],
            "timings": result.get("timings", {}),
            "total_time": result.get("total_time"),
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001
        _log.debug("Query-Log konnte nicht geschrieben werden: %s", exc)
