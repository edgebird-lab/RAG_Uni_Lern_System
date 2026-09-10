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
    ANSWER_SYSTEM, ANSWER_PROMPT, TUTOR_SYSTEM, TUTOR_PROMPT,
    FAITHFULNESS_PROMPT, NO_ANSWER_TOKEN,
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
    chat_mode: str           # "strict" | "tutor" – Tutor = freier, weiterhin gegroundet
    syllabus: bool           # Ueberblicks-/Lernstoff-Frage -> breiteres Retrieval
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


# Tutor-/Syllabus-Budgets (nur fuer diesen Pfad; Strict bleibt bei settings.*)
_TUTOR_SYLLABUS_TOP_K = 12
_TUTOR_SYLLABUS_MAX_CHARS = 14000
_PEDAGOGICAL_NAME_RE = re.compile(
    r"zusammenfassung|kompakt|klausur|katalog|lern|ueberblick|überblick", re.I
)
_SYLLABUS_MARKERS = (
    "was muss ich lernen", "was soll ich lernen", "was lernen", "lernen muss",
    "wichtigste themen", "wichtigsten themen", "überblick", "ueberblick",
    "zusammenfassung des fachs", "zusammenfassung vom fach", "lernplan",
    "was wiederholen", "prüfungsstoff", "pruefungsstoff", "welche themen",
    "stoff für", "stoff fuer", "was kommt in der klausur", "klausur relevant",
    "was brauche ich für", "was brauche ich fuer", "was steht auf dem plan",
    "inhalte des fachs", "themenübersicht", "themenuebersicht",
)
# Zusaetzlich: "was … lernen" / "was … wiederholen" mit Worten dazwischen
_SYLLABUS_RE = re.compile(
    r"was\s+(muss|soll|sollte|brauche)\s+ich\b.{0,40}\b(lernen|wiederholen|wissen|koennen|können)"
    r"|welche[sn]?\s+themen\b|lern\s*stoff\b|pruefungs\s*stoff\b|prüfungs\s*stoff\b",
    re.I | re.DOTALL,
)

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


def _build_context(candidates: list[dict],
                   max_chars: Optional[int] = None,
                   extra_prefix: str = "") -> tuple[str, list[dict]]:
    parts, sources = [], []
    used = 0
    limit = max_chars if max_chars is not None else settings.MAX_CONTEXT_CHARS
    if extra_prefix:
        block = _sanitize_context_text(extra_prefix)
        parts.append(block)
        used += len(block)
    for i, c in enumerate(candidates, 1):
        doc = _sanitize_context_text(c["document"])
        block = f"[Quelle {i}] ({c['meta'].get('filename','?')}, {c['meta'].get('location','')})\n{doc}"
        if used + len(block) > limit and parts:
            break
        parts.append(block)
        used += len(block)
        sources.append(_source_entry(c, i))
    return "\n\n---\n\n".join(parts), sources


def _is_tutor(state: RAGState) -> bool:
    return (state.get("chat_mode") or "strict") == "tutor"


def _is_syllabus_intent(question: str) -> bool:
    ql = (question or "").strip().lower()
    if not ql:
        return False
    if any(m in ql for m in _SYLLABUS_MARKERS):
        return True
    return bool(_SYLLABUS_RE.search(ql))


def _pedagogical_boost(candidates: list[dict]) -> list[dict]:
    """Bevorzugt Chunks aus Zusammenfassungs-/Klausur-/Katalog-Dateien."""
    if not candidates:
        return candidates
    boosted = []
    for c in candidates:
        meta = c.get("meta") or {}
        blob = f"{meta.get('filename', '')} {meta.get('header_path', '')} {meta.get('location', '')}"
        sc = float(c.get("fusion_score") or 0.0)
        if _PEDAGOGICAL_NAME_RE.search(blob):
            sc += 0.025
        nc = dict(c)
        nc["fusion_score"] = sc
        boosted.append(nc)
    return sorted(boosted, key=lambda x: x.get("fusion_score", 0.0), reverse=True)


def _load_existing_summary_md(subject: Optional[str], max_chars: int = 6000) -> str:
    """Liest eine bereits erzeugte docs/Zusammenfassung_*.md zum Fach, falls vorhanden."""
    if not subject:
        return ""
    try:
        from ragapp.config import PROJECT_ROOT, SUBJECT_LABELS
        docs_dir = PROJECT_ROOT / "docs"
        if not docs_dir.is_dir():
            return ""
        label = SUBJECT_LABELS.get(subject, subject)
        keys = {subject.lower(), label.lower(),
                re.sub(r"[^\w]+", "_", subject, flags=re.U).lower(),
                re.sub(r"[^\w]+", "_", label, flags=re.U).lower()}
        # Kuerzel wie "MF" / erster Token der Label
        for part in re.split(r"[\s_/]+", label):
            if len(part) >= 2:
                keys.add(part.lower())
        best = None
        for path in sorted(docs_dir.glob("Zusammenfassung_*.md")):
            stem = path.stem.lower().replace("zusammenfassung_", "")
            if any(k and k in stem for k in keys):
                best = path
                break
        if best is None:
            return ""
        text = best.read_text("utf-8")[:max_chars].strip()
        if not text:
            return ""
        return (f"[Quelle Summary] (bereits erzeugte Zusammenfassung: {best.name})\n{text}")
    except Exception as exc:  # noqa: BLE001
        _log.debug("Zusammenfassungs-MD nicht ladbar: %s", exc)
        return ""


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


def _relevance_ok(candidates: list[dict], *, tutor: bool = False,
                  subject: Optional[str] = None) -> bool:
    """Relevanz-Gate: waehlt die zur genutzten Score-Quelle passende, WIRKSAME
    Schwelle.
      * Reranker AKTIV -> Cross-Encoder-Logit gegen RELEVANCE_MIN_SCORE (Logit-Skala).
      * Reranker AUS (Schnell-Modus) -> der RRF-Fusionswert ist rangbasiert und misst
        KEINE Relevanz; deshalb auf die DENSE-Kosinus-Aehnlichkeit (bge-m3) des
        Top-Treffers gaten (echtes Relevanzsignal) gegen DENSE_RELEVANCE_MIN_SCORE.
        Nur wenn der Top-Treffer keinen Dense-Score hat (rein aus BM25), bleibt der
        RRF-Mindestwert der Rueckfall.
    Tutor + Fach: etwas toleranter, damit Ueberblicksfragen nicht sofort fallen."""
    if not candidates:
        return False
    top = candidates[0]
    rr = top.get("rerank_score")
    fu = top.get("fusion_score")
    if rr is None:                     # kein Score vorhanden -> nicht blockieren
        return True
    # Tutor mit Fachfilter: irgendwelche Treffer im Fach reichen oft fuer Teilanworten
    if tutor and subject and len(candidates) >= 2:
        dense_any = [c.get("dense_score") for c in candidates
                     if c.get("dense_score") is not None]
        if dense_any and max(dense_any) >= (settings.DENSE_RELEVANCE_MIN_SCORE * 0.75):
            return True
    reranked = (fu is None) or (rr != fu)
    if reranked:
        thr = settings.RELEVANCE_MIN_SCORE
        if tutor:
            thr = thr - 1.5          # Logit-Skala: etwas weicher
        return rr >= thr
    dense = [c.get("dense_score") for c in candidates if c.get("dense_score") is not None]
    dense_thr = settings.DENSE_RELEVANCE_MIN_SCORE
    if tutor:
        dense_thr = dense_thr * 0.85
    if dense:
        return max(dense) >= dense_thr
    return (fu or 0.0) >= settings.RELEVANCE_MIN_FUSION_SCORE


def retrieve_node(state: RAGState) -> RAGState:
    t0 = time.time()
    queries = [state.get("search_query") or state["question"]]
    queries += [q for q in (state.get("sub_queries") or []) if q]
    use_rr = state.get("use_reranker")
    subj = state.get("subject")
    syllabus = bool(state.get("syllabus"))
    tutor = _is_tutor(state)
    top_k = (_TUTOR_SYLLABUS_TOP_K if (syllabus and subj) else settings.FINAL_TOP_K)
    pool = _pool_fusion_candidates(queries, subj)
    if syllabus:
        pool = _pedagogical_boost(pool)
    candidates = get_reranker().rerank(
        queries[0], pool, top_k=top_k, use_reranker=use_rr)
    timings = dict(state.get("timings", {}))
    timings["retrieve"] = round(time.time() - t0, 2)
    return {
        "candidates": candidates,
        "relevance_ok": _relevance_ok(candidates, tutor=tutor, subject=subj),
        "timings": timings,
    }


def generate_node(state: RAGState) -> RAGState:
    t0 = time.time()
    tutor = _is_tutor(state)
    syllabus = bool(state.get("syllabus"))
    max_chars = (_TUTOR_SYLLABUS_MAX_CHARS
                 if (syllabus and state.get("subject")) else None)
    extra = ""
    if syllabus and state.get("subject"):
        extra = _load_existing_summary_md(state.get("subject"))
    context, sources = _build_context(
        state["candidates"], max_chars=max_chars, extra_prefix=extra)
    if tutor:
        prompt = TUTOR_PROMPT.format(context=context, question=state["question"])
        system = TUTOR_SYSTEM
    else:
        prompt = ANSWER_PROMPT.format(
            context=context, question=state["question"], no_answer=NO_ANSWER_TOKEN
        )
        system = ANSWER_SYSTEM
    answer = get_llm().generate(prompt, system=system).strip()
    if tutor and NO_ANSWER_TOKEN in answer:
        answer = answer.replace(NO_ANSWER_TOKEN, "").strip()
    timings = dict(state.get("timings", {}))
    timings["generate"] = round(time.time() - t0, 2)
    return {"answer": answer, "context": context, "sources": sources, "timings": timings}


def faithfulness_node(state: RAGState) -> RAGState:
    # Pro Anfrage abschaltbar ("Schnelle Antworten"): None = globale Einstellung.
    # Tutor-Modus: Faithfulness standardmaessig AUS (Synthese sonst oft verworfen).
    if state.get("check_faithfulness") is None:
        enabled = (False if _is_tutor(state)
                   else settings.ENABLE_FAITHFULNESS_CHECK)
    else:
        enabled = bool(state.get("check_faithfulness"))
    if not enabled:
        # Nicht geprüft -> die Antwort NICHT als "belegt" auszeichnen (ehrlich bleiben).
        return {"grounded": True, "mode": "answer", "faith_checked": False,
                "confidence": "ungeprueft"}
    t0 = time.time()
    # schnelles Modell für die interne Belegtheits-Prüfung (spart CPU-Zeit)
    data = get_llm(settings.LLM_MODEL_FAST).generate_json(
        FAITHFULNESS_PROMPT.format(context=state["context"], answer=state["answer"])
    )
    val = data.get("grounded") if isinstance(data, dict) else None
    if isinstance(val, bool):
        verdict = "belegt" if val else "unbelegt"
    elif isinstance(val, str):
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
    if verdict == "belegt":
        grounded, mode, confidence = True, "answer", "belegt"
    elif verdict == "unbelegt":
        # Tutor: Soft-Fail – Antwort behalten, Badge unsicher (kein harter Fallback)
        if _is_tutor(state):
            grounded, mode, confidence = False, "answer", "unsicher"
        else:
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
    if state.get("relevance_ok"):
        return "generate"
    # Tutor: bei vorhandenen Kandidaten trotzdem versuchen (Teilanwort + Luecken)
    if _is_tutor(state) and state.get("candidates"):
        return "generate"
    return "fallback"


def route_after_generate(state: RAGState) -> str:
    answer = state.get("answer", "")
    if not answer.strip():
        return "fallback"
    if NO_ANSWER_TOKEN in answer:
        # Tutor: generate_node entfernt den Sentinel bereits; Restfall -> Fallback
        if _is_tutor(state):
            return "faithfulness"
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
                 decompose: bool = True,
                 chat_mode: str = "strict") -> dict:
    """Öffentliche Schnittstelle für UI/CLI. Führt den Graphen aus.

    use_reranker / check_faithfulness: None = globale Einstellung; False =
    überspringen ("Schnelle Antworten" auf der Startseite -> schneller, dafür
    gröbere Trefferreihenfolge bzw. keine zusätzliche Beleg-Prüfung).
    history: bisherige Chat-Nachrichten -> kurze Rückfragen werden für die Suche zu
    eigenständigen Fragen umformuliert (die Antwort nutzt die Originalfrage).
    chat_mode: "strict" (Default, Sentinel/Faithfulness) oder "tutor" (freier
    Dialog, Fakten weiterhin nur aus dem Kontext)."""
    t0 = time.time()
    mode = "tutor" if chat_mode == "tutor" else "strict"
    syllabus = _is_syllabus_intent(question)
    search_query = question
    if history and _looks_followup(question):
        search_query = _condense_query(question, history)
    # Syllabus/Ueberblick: kein teures Decompose (breiteres Retrieval reicht)
    do_decompose = decompose and _is_broad(question) and not syllabus
    sub_queries = _decompose_query(search_query) if do_decompose else []
    # Tutor: Faithfulness default aus, sofern nicht explizit gesetzt
    faith = check_faithfulness
    if mode == "tutor" and faith is None:
        faith = False
    state: RAGState = {"question": question, "search_query": search_query,
                       "sub_queries": sub_queries, "subject": subject,
                       "chat_mode": mode, "syllabus": syllabus,
                       "use_reranker": use_reranker,
                       "check_faithfulness": faith, "mode": "answer"}
    result = get_graph().invoke(state)
    if search_query != question:
        result["search_query"] = search_query
    if sub_queries:
        result["sub_queries"] = sub_queries
    result["chat_mode"] = mode
    result["syllabus"] = syllabus
    result["total_time"] = round(time.time() - t0, 2)
    _log_query(question, subject, result)
    return result


def answer_query_stream(question: str, subject: Optional[str] = None,
                        use_reranker: Optional[bool] = None,
                        check_faithfulness: Optional[bool] = None,
                        history: Optional[list] = None,
                        decompose: bool = True,
                        chat_mode: str = "strict"):
    """Streaming-Variante von :func:`answer_query` fuer den SCHNELL-/Tutor-Modus.

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

    Warum nur im Schnell-/Tutor-Modus: Bei aktiver Gegenpruefung (Faithfulness) kann
    die Antwort nach der Generierung noch verworfen werden - dann haette man bereits
    verworfenen Text gestreamt.
    """
    mode = "tutor" if chat_mode == "tutor" else "strict"
    faith_arg = check_faithfulness
    if mode == "tutor" and faith_arg is None:
        faith_arg = False
    faith_enabled = (settings.ENABLE_FAITHFULNESS_CHECK
                     if faith_arg is None else faith_arg)
    if faith_enabled:
        return None, {}

    holder: dict = {}
    syllabus = _is_syllabus_intent(question)

    def _gen():
        t0 = time.time()
        flushed = False
        accumulated: list[str] = []
        try:
            search_query = question
            if history and _looks_followup(question):
                search_query = _condense_query(question, history)
            do_decompose = decompose and _is_broad(question) and not syllabus
            sub_queries = _decompose_query(search_query) if do_decompose else []
            queries = [search_query] + [q for q in sub_queries if q]

            tr = time.time()
            pool = _pool_fusion_candidates(queries, subject)
            if syllabus:
                pool = _pedagogical_boost(pool)
            top_k = (_TUTOR_SYLLABUS_TOP_K if (syllabus and subject)
                     else settings.FINAL_TOP_K)
            candidates = get_reranker().rerank(
                queries[0], pool, top_k=top_k, use_reranker=use_reranker)
            relevance_ok = _relevance_ok(
                candidates, tutor=(mode == "tutor"), subject=subject)
            timings = {"retrieve": round(time.time() - tr, 2)}

            base: dict = {"question": question, "subject": subject,
                          "candidates": candidates, "relevance_ok": relevance_ok,
                          "chat_mode": mode, "syllabus": syllabus}
            if search_query != question:
                base["search_query"] = search_query
            if sub_queries:
                base["sub_queries"] = sub_queries

            allow_weak = (mode == "tutor" and bool(candidates))
            if not relevance_ok and not allow_weak:
                fb = fallback_node({"candidates": candidates})
                yield fb.get("answer", "")
                holder.update(base)
                holder.update(fb)
                holder["faith_checked"] = False
                holder["timings"] = timings
                return

            max_chars = (_TUTOR_SYLLABUS_MAX_CHARS
                         if (syllabus and subject) else None)
            extra = (_load_existing_summary_md(subject)
                     if (syllabus and subject) else "")
            context, sources = _build_context(
                candidates, max_chars=max_chars, extra_prefix=extra)
            if mode == "tutor":
                prompt = TUTOR_PROMPT.format(context=context, question=question)
                system = TUTOR_SYSTEM
                guard_sentinel = False
            else:
                prompt = ANSWER_PROMPT.format(
                    context=context, question=question, no_answer=NO_ANSWER_TOKEN)
                system = ANSWER_SYSTEM
                guard_sentinel = True
            tg = time.time()

            head = ""
            guard = len(NO_ANSWER_TOKEN) + 12
            no_answer = False
            for delta in get_llm().generate_stream(prompt, system=system):
                accumulated.append(delta)
                if flushed:
                    yield delta
                    continue
                head += delta
                if guard_sentinel and NO_ANSWER_TOKEN in head:
                    no_answer = True
                    break
                if len(head) >= guard:
                    flushed = True
                    yield head
            if not no_answer and not flushed:
                if guard_sentinel and NO_ANSWER_TOKEN in head:
                    no_answer = True
                else:
                    flushed = True
                    yield head

            timings["generate"] = round(time.time() - tg, 2)
            answer = "".join(accumulated).replace(NO_ANSWER_TOKEN, "").strip()

            if no_answer or not answer:
                fb = fallback_node({"candidates": candidates, "sources": sources})
                if not flushed:
                    yield fb.get("answer", "")
                holder.update(base)
                holder.update(fb)
                holder["faith_checked"] = False
                holder["timings"] = timings
                return

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
        except Exception as exc:  # noqa: BLE001
            _log.warning("Streaming-Antwort fehlgeschlagen: %s", exc)
            msg = diagnose_error(exc)
            partial = "".join(accumulated).strip()
            if flushed:
                yield "\n\n_" + msg + "_"
            else:
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
            except Exception:  # noqa: BLE001
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
            "chat_mode": result.get("chat_mode"),
            "syllabus": result.get("syllabus"),
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
