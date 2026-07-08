"""
Kommandozeilen-Schnittstelle (CLI)
=================================

Beispiele:
    python -m ragapp.scripts.cli ingest                # ganzen Quellordner einlesen
    python -m ragapp.scripts.cli ingest-file datei.pdf # eine Datei einlesen
    python -m ragapp.scripts.cli watch                 # Ordner automatisch überwachen
    python -m ragapp.scripts.cli gold --sample 60      # Gold-Set für Evaluation erzeugen
    python -m ragapp.scripts.cli eval                  # Trefferquote messen
    python -m ragapp.scripts.cli ask "Was ist ein Deckungsbeitrag?"
    python -m ragapp.scripts.cli stats                 # Statusübersicht
    python -m ragapp.scripts.cli reset --yes           # Index komplett leeren
"""
from __future__ import annotations

import argparse
import sys


def _print_progress(msg: str) -> None:
    print("  " + msg)


def cmd_ingest(args):
    from ragapp.ingestion.pipeline import ingest_directory
    res = ingest_directory(args.dir, force=args.force, progress=_print_progress)
    print("\n=== Ingestion abgeschlossen ===")
    print(f"  Neu/aktualisiert: {res['ok']}   Chunks: {res['chunks']}   Fragen: {res['questions']}")
    print(f"  Duplikate: {res['duplicate']}   Unverändert: {res['unchanged']}   "
          f"Übersprungen: {res['skipped']}   Fehler: {res['error']}")


def cmd_ingest_file(args):
    from ragapp.ingestion.pipeline import ingest_file
    res = ingest_file(args.path, force=args.force, progress=_print_progress)
    print(res)


def cmd_watch(args):
    from ragapp.ingestion.watcher import watch
    watch()


def cmd_gold(args):
    from ragapp.eval.gold_set import build_gold_set
    res = build_gold_set(sample_size=args.sample, progress=_print_progress)
    print("\nGold-Set:", res)


def cmd_enrich(args):
    from ragapp.ingestion.enrich import enrich_questions
    from ragapp.retrieval.bm25_index import rebuild_bm25_from_store
    res = enrich_questions(limit=args.limit, subject=args.subject, progress=_print_progress)
    print("\nAnreicherung:", res)


def cmd_catalog(args):
    from ragapp.ingestion.exam_catalog import build_exam_catalog
    from ragapp.retrieval.bm25_index import rebuild_bm25_from_store
    res = build_exam_catalog(args.subject, n_per_section=args.n, progress=_print_progress)
    print("\nLernkatalog:", res)
    if res.get("status") == "ok":
        rebuild_bm25_from_store()
        print("BM25-Index aktualisiert. Katalog:", res.get("markdown"))


def cmd_eval(args):
    from ragapp.eval.run_eval import run_retrieval_eval
    res = run_retrieval_eval(progress=_print_progress)
    if res.get("status") != "ok":
        print(res)
        return
    m = res["metrics"]
    print("\n=== Trefferquote (Retrieval) ===")
    print(f"  Fragen getestet: {res['num_questions']}   (Dauer: {res['elapsed_seconds']}s)")
    for k, v in m["hit@k"].items():
        print(f"  Hit@{k}: {v*100:.1f}%")
    print(f"  MRR: {m['mrr']:.3f}")
    print("\n  Nach Fach:")
    for subj, s in m.get("by_subject", {}).items():
        key = [x for x in s if x.startswith("hit@")][0]
        print(f"    {subj:12s} n={s['n']:3d}  {key}={s[key]*100:5.1f}%  MRR={s['mrr']:.3f}")


def cmd_ask(args):
    from ragapp.graph.rag_graph import answer_query
    res = answer_query(args.question, subject=args.subject)
    print("\n" + "=" * 60)
    print(f"MODUS: {res.get('mode')}   belegt: {res.get('grounded')}   Zeit: {res.get('total_time')}s")
    print("=" * 60)
    print(res.get("answer", ""))
    print("\nQuellen:")
    for s in res.get("sources", []):
        print(f"  [{s['rank']}] {s['filename']} ({s['location']}) · {s['subject']} · score={s['score']}")


def cmd_stats(args):
    from ragapp import manifest
    from ragapp.retrieval.vectorstore import get_vectorstore
    st = manifest.stats()
    print("=== Status ===")
    print(f"  Dokumente:  {st['documents']}")
    print(f"  Chunks:     {st['chunks']}")
    print(f"  Fragen:     {st['questions']}")
    print(f"  Fächer:     {st['subjects']}")
    print(f"  Chroma-Einträge gesamt: {get_vectorstore().count()}")
    print("\n  Dokumente im Detail:")
    for d in manifest.list_documents():
        print(f"    {d['subject']:10s} {d['filename']:45s} "
              f"Chunks={d['num_chunks']:3d} Fragen={d['num_questions']:3d} [{d['status']}]")


def cmd_recommend(args):
    """Misst die Hardware, empfiehlt ein Modell, testet/setzt es optional."""
    from ragapp import hardware
    hw = hardware.detect_hardware()
    print("=== Erkannte Hardware ===")
    print(hardware.format_hardware(hw))
    rec = hardware.recommend_models(hw)
    print("\n=== Empfehlung ===")
    print(rec["reason"])
    print(f"Embedding-Modell: {rec['embed_model']}")
    print("Empfohlene Antwort-Modelle (bestes zuerst):")
    for i, m in enumerate(rec["models"], 1):
        print(f"  {i}. {m['tag']:24s} ({m['params']}, ~{m['gb']} GB)  {m['why']}")

    target = args.model or rec["models"][0]["tag"]
    if args.test:
        print(f"\n=== Benchmark: {target} ===")
        res = hardware.benchmark_model(target, progress=_print_progress)
        if res.get("error"):
            print("  Fehler:", res["error"])
        else:
            print(f"  {res['tokens_per_s']} tok/s | warm {res['warm_s']}s | "
                  f"kalt {res['cold_s']}s -> {res['verdict']}")
    if args.set:
        from ragapp.config import settings
        settings.update(LLM_MODEL=target, LLM_MODEL_FAST=target)
        settings.save()
        print(f"\n-> Gesetzt: LLM_MODEL = {target} (in data/config.json gespeichert)")


def cmd_doctor(args):
    """Prüft die Umgebung (Ollama, Modelle, Index) und meldet Probleme."""
    ok = True
    print("=== Systemprüfung ===")
    # Ollama + Modelle
    try:
        import ollama
        from ragapp.config import settings
        client = ollama.Client(host=settings.OLLAMA_BASE_URL)
        models = [m.get("model", "") for m in client.list().get("models", [])]
        print(f"  [OK] Ollama erreichbar unter {settings.OLLAMA_BASE_URL}")
        for needed in (settings.LLM_MODEL, settings.EMBED_MODEL):
            present = any(needed.split(":")[0] in m for m in models)
            print(f"  [{'OK' if present else 'FEHLT'}] Modell {needed}")
            ok = ok and present
    except Exception as exc:
        print(f"  [FEHLER] Ollama nicht erreichbar: {exc}")
        ok = False
    # Embedding-Test
    try:
        from ragapp.retrieval.embeddings import get_embedder
        v = get_embedder().embed_query("Test")
        print(f"  [OK] Embedding funktioniert (Dim {len(v)})")
    except Exception as exc:
        print(f"  [FEHLER] Embedding: {exc}"); ok = False
    # Reranker
    try:
        from ragapp.retrieval.reranker import get_reranker
        loaded = get_reranker()._ensure_loaded()
        print(f"  [{'OK' if loaded else 'WARN'}] Reranker {'geladen' if loaded else 'nicht verfügbar (Fallback aktiv)'}")
    except Exception as exc:
        print(f"  [WARN] Reranker: {exc}")
    # Index
    try:
        from ragapp import manifest
        from ragapp.retrieval.vectorstore import get_vectorstore
        st = manifest.stats()
        print(f"  [INFO] Index: {st['documents']} Dokumente, {st['chunks']} Chunks, "
              f"{st['questions']} Fragen, {get_vectorstore().count()} Chroma-Einträge")
    except Exception as exc:
        print(f"  [FEHLER] Index: {exc}"); ok = False
    print("\nErgebnis:", "ALLES OK" if ok else "Es gibt Probleme (siehe oben).")


def cmd_reset(args):
    if not args.yes:
        print("Sicherheitsabfrage: '--yes' anhängen, um den Index wirklich zu leeren.")
        return
    from ragapp.retrieval.vectorstore import get_vectorstore
    from ragapp.config import MANIFEST_DB
    get_vectorstore().reset()
    if MANIFEST_DB.exists():
        MANIFEST_DB.unlink()
    from ragapp import manifest
    manifest.init_db()
    print("Index & Manifest geleert.")


def main():
    # stdout/stderr robust auf UTF-8 (Windows-Umleitung nutzt sonst cp1252 und
    # würde bei Umlaut-Dateinamen/Sonderzeichen mit UnicodeEncodeError abbrechen)
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="RAG-Lernsystem CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ingest", help="Ganzen Ordner einlesen")
    p.add_argument("--dir", default=None)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("ingest-file", help="Einzelne Datei einlesen")
    p.add_argument("path")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_ingest_file)

    p = sub.add_parser("watch", help="Ordner automatisch überwachen")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("gold", help="Gold-Set für die Evaluation erzeugen")
    p.add_argument("--sample", type=int, default=None)
    p.set_defaults(func=cmd_gold)

    p = sub.add_parser("enrich", help="Fragen für wichtige Chunks generieren (opt-in)")
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--subject", default=None)
    p.set_defaults(func=cmd_enrich)

    p = sub.add_parser("catalog", help="Klausur-Lernkatalog für ein Fach erzeugen (aus Zusammenfassung + Altklausuren)")
    p.add_argument("subject")
    p.add_argument("--n", type=int, default=3)
    p.set_defaults(func=cmd_catalog)

    p = sub.add_parser("eval", help="Trefferquote messen")
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("ask", help="Frage stellen")
    p.add_argument("question")
    p.add_argument("--subject", default=None)
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("stats", help="Statusübersicht")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("doctor", help="Umgebung prüfen (Ollama, Modelle, Index)")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("recommend", help="Hardware messen + passendes Modell empfehlen/testen")
    p.add_argument("--test", action="store_true", help="empfohlenes Modell benchmarken (tok/s)")
    p.add_argument("--set", action="store_true", help="empfohlenes Modell als Standard setzen")
    p.add_argument("--model", default=None, help="konkretes Modell testen/setzen statt der Empfehlung")
    p.set_defaults(func=cmd_recommend)

    p = sub.add_parser("reset", help="Index komplett leeren")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_reset)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
