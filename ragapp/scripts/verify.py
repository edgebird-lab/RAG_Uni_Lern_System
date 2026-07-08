"""
End-to-End-Verifikation / Demo
==============================

Führt einen kompletten Selbsttest aus:
    1. Umgebungscheck (Ollama, Modelle, Index)
    2. BM25-Index sicherstellen (neu aufbauen, falls nötig)
    3. Ein paar Beispielfragen durch die volle RAG-Pipeline schicken und die
       Antworten, Quellen, den Modus (belegt/Fallback) und die Zeiten zeigen.

Aufruf:
    python -m ragapp.scripts.verify
    python -m ragapp.scripts.verify --questions "Was ist ein Deckungsbeitrag?" "Erkläre den Erwartungswert"
"""
from __future__ import annotations

import argparse

DEFAULT_QUESTIONS = [
    "Was ist der Deckungsbeitrag und wie berechnet man ihn?",
    "Erkläre den Unterschied zwischen Einzelkosten und Gemeinkosten.",
    "Was besagt der Erwartungswert einer Zufallsvariablen?",
    "Was ist der Unterschied zwischen qualitativer und quantitativer Marktforschung?",
]


def ensure_bm25():
    from ragapp.retrieval.bm25_index import get_bm25, rebuild_bm25_from_store
    bm = get_bm25()
    if bm.bm25 is None or not bm.ids:
        print("BM25-Index wird (neu) aufgebaut …")
        rebuild_bm25_from_store()
        print("  fertig.")


def main():
    # stdout robust auf UTF-8 stellen (Windows-Umleitung nutzt sonst cp1252)
    try:
        import sys
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", nargs="*", default=None)
    args = ap.parse_args()
    questions = args.questions or DEFAULT_QUESTIONS

    from ragapp import manifest
    from ragapp.retrieval.vectorstore import get_vectorstore
    st = manifest.stats()
    print("=" * 70)
    print(f"Index: {st['documents']} Dokumente · {st['chunks']} Chunks · "
          f"{st['questions']} Fragen · {get_vectorstore().count()} Chroma-Einträge")
    print("=" * 70)

    ensure_bm25()

    from ragapp.graph.rag_graph import answer_query
    for q in questions:
        print("\n>> FRAGE: " + q)
        print("-" * 70)
        res = answer_query(q)
        print(f"[Modus: {res.get('mode')} · belegt: {res.get('grounded')} · "
              f"Zeit: {res.get('total_time')}s · {res.get('timings')}]")
        print(res.get("answer", "")[:1200])
        print("Quellen:")
        for s in res.get("sources", [])[:5]:
            print(f"   [{s['rank']}] {s['filename']} · {s['location']} · "
                  f"{s['subject']} · score={s['score']} · {s.get('retrievers','')}")
    print("\n" + "=" * 70)
    print("Verifikation abgeschlossen.")


if __name__ == "__main__":
    main()
