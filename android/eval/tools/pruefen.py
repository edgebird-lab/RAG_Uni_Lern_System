#!/usr/bin/env python3
"""Prueft die Goldset-Kandidaten maschinell vor (zweites, groesseres Modell als Richter).

Pro Kandidat wird die Frage gegen die dichteste Umgebung im GANZEN Korpus gehalten:
  1. Embedding-Suche (bge-m3 ueber Ollama) liefert die 6 aehnlichsten Abschnitte,
     bei beantwortbaren Fragen wird der Quellabschnitt zusaetzlich eingemischt.
  2. Der Richter (Standard: gemma4:26b) beurteilt:
       - ist die Frage eigenstaendig verstaendlich?
       - beantwortet der Quellabschnitt sie, und stimmt die erwartete Antwort?
       - beantworten weitere Abschnitte sie ebenfalls? (-> werden als zusaetzliche Belege vermerkt)
       - unbeantwortbar: beantwortet IRGENDEIN Abschnitt die Frage? (-> verworfen)
Ergebnis: goldset/pruefung.jsonl (Urteil je Kandidat). Die endgueltige Freigabe
(reviewed: true) erfolgt danach durch eine menschliche/zweite Durchsicht.

Aufruf: python3 -I pruefen.py [--judge gemma4:26b] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import generate_goldset as gg  # noqa: E402

ROOT = HERE.parent
CAND = ROOT / "goldset" / "kandidaten.jsonl"
OUT = ROOT / "goldset" / "pruefung.jsonl"
CACHE = ROOT / "goldset" / ".cache"
OLLAMA = gg.OLLAMA

SYS = ("Du bist ein strenger Prüfer für Lernfragen. Antworte AUSSCHLIESSLICH mit einem JSON-Objekt. "
       "Beurteile nur anhand der gegebenen Abschnitte, nicht anhand deines Weltwissens.")

P_ANS = ('Frage: {frage}\nErwartete Antwort: {antwort}\n\nAbschnitte:\n{abschnitte}\n\n'
         'Beurteile:\n'
         '- "eigenstaendig": Ist die Frage ohne Kontext verständlich, konkret und hat genau eine klare Antwort '
         '(true/false)? Vage Meta-Fragen („welche Strukturen werden beschrieben“) sind false.\n'
         '- "quelle_beantwortet": Beantwortet Abschnitt [{src}] die Frage vollständig (true/false)?\n'
         '- "antwort_korrekt": Stimmt die erwartete Antwort mit dem Abschnitt überein (true/false)?\n'
         '- "weitere": Liste der Nummern ANDERER Abschnitte, die die Frage ebenfalls vollständig beantworten.\n'
         'JSON: {{"eigenstaendig": true, "quelle_beantwortet": true, "antwort_korrekt": true, "weitere": [], "kommentar": "kurz"}}')

P_MULTI = ('Frage: {frage}\nErwartete Antwort: {antwort}\n\nAbschnitte:\n{abschnitte}\n\n'
           'Diese Frage soll nur durch Kombination der Abschnitte [{src}] und [{src2}] beantwortbar sein.\n'
           '- "eigenstaendig": konkret, ohne Kontext verständlich, eine klare Antwort (true/false)?\n'
           '- "braucht_beide": Wird für die vollständige Antwort Information aus BEIDEN Abschnitten gebraucht (true/false)?\n'
           '- "antwort_korrekt": Stimmt die erwartete Antwort mit den Abschnitten überein (true/false)?\n'
           'JSON: {{"eigenstaendig": true, "braucht_beide": true, "antwort_korrekt": true, "kommentar": "kurz"}}')

P_UNANS = ('Frage: {frage}\n\nAbschnitte:\n{abschnitte}\n\n'
           'Beantwortet einer dieser Abschnitte die Frage vollständig oder in der Sache ausreichend? '
           '- "beantwortet_von": Liste der Nummern, die die Frage beantworten (leer, wenn keiner).\n'
           '- "eigenstaendig": Ist die Frage konkret und ohne Kontext verständlich (true/false)?\n'
           'JSON: {{"beantwortet_von": [], "eigenstaendig": true, "kommentar": "kurz"}}')


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(f"{OLLAMA}{path}", json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.load(r)


def passages() -> list[dict]:
    out = []
    for f in sorted(gg.KORPUS.glob("*.md")):
        if f.stem == "QUELLEN":
            continue
        for head, text in gg.sections(f.stem):
            out.append({"doc": f.stem, "head": head, "text": text})
    return out


def embed_all(ps: list[dict]) -> np.ndarray:
    CACHE.mkdir(parents=True, exist_ok=True)
    cf = CACHE / f"emb_{len(ps)}.npy"
    if cf.exists():
        return np.load(cf)
    vecs = []
    for i in range(0, len(ps), 32):
        batch = [f"{p['head']}\n{p['text']}"[:2000] for p in ps[i:i + 32]]
        vecs += post("/api/embed", {"model": "bge-m3", "input": batch})["embeddings"]
        print(f"embed {i + len(batch)}/{len(ps)}", flush=True)
    arr = np.array(vecs, dtype=np.float32)
    arr /= np.linalg.norm(arr, axis=1, keepdims=True)
    np.save(cf, arr)
    return arr


def judge(model: str, prompt: str) -> dict:
    r = post("/api/chat", {"model": model, "stream": False, "format": "json", "think": False,
                           "options": {"temperature": 0.0, "num_ctx": 12288},
                           "messages": [{"role": "system", "content": SYS}, {"role": "user", "content": prompt}]})
    return json.loads(r["message"]["content"])


def find_source(ps: list[dict], doc: str, quote: str) -> int | None:
    q = gg.norm(quote.strip(" .…\"“„"))
    for i, p in enumerate(ps):
        if p["doc"] == doc.removesuffix(".md") and q in gg.norm(p["text"]):
            return i
    return None


def render(ps: list[dict], idx: list[int]) -> str:
    return "\n\n".join(f"[{n + 1}] ({ps[i]['doc']}: {ps[i]['head']})\n{ps[i]['text'][:1400]}" for n, i in enumerate(idx))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", default="gemma4:26b")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    ps = passages()
    emb = embed_all(ps)
    cands = [json.loads(l) for l in CAND.read_text(encoding="utf-8").splitlines() if l.strip()]
    if a.limit:
        cands = cands[:a.limit]
    done = {json.loads(l)["id"] for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip()} if OUT.exists() else set()
    with OUT.open("a", encoding="utf-8") as fh:
        for c in cands:
            if c["id"] in done:
                continue
            qv = np.array(post("/api/embed", {"model": "bge-m3", "input": [c["frage"]]})["embeddings"][0], dtype=np.float32)
            qv /= np.linalg.norm(qv)
            top = list(np.argsort(-(emb @ qv))[:6])
            src_idx = [find_source(ps, c["dokument"], b["zitat"]) for b in c["belege"]]
            src_idx = [i for i in src_idx if i is not None]
            if c["typ"] != "unbeantwortbar" and len(src_idx) != len(c["belege"]):
                res = {"urteil": "verwerfen", "grund": "Beleg im Korpus nicht auffindbar"}
            else:
                idx = list(dict.fromkeys(src_idx + [int(t) for t in top]))[:8]
                try:
                    if c["typ"] == "unbeantwortbar":
                        r = judge(a.judge, P_UNANS.format(frage=c["frage"], abschnitte=render(ps, idx)))
                        ok = not r.get("beantwortet_von") and r.get("eigenstaendig", False)
                        res = {"urteil": "ok" if ok else "verwerfen", "grund": r.get("kommentar", ""), "roh": r}
                    elif c["typ"] == "mehrstufig":
                        s1, s2 = idx.index(src_idx[0]) + 1, idx.index(src_idx[1]) + 1
                        r = judge(a.judge, P_MULTI.format(frage=c["frage"], antwort=c["erwartete_antwort"],
                                                          abschnitte=render(ps, idx), src=s1, src2=s2))
                        ok = r.get("eigenstaendig") and r.get("braucht_beide") and r.get("antwort_korrekt")
                        res = {"urteil": "ok" if ok else "verwerfen", "grund": r.get("kommentar", ""), "roh": r}
                    else:
                        s1 = idx.index(src_idx[0]) + 1
                        r = judge(a.judge, P_ANS.format(frage=c["frage"], antwort=c["erwartete_antwort"],
                                                        abschnitte=render(ps, idx), src=s1))
                        ok = r.get("eigenstaendig") and r.get("quelle_beantwortet") and r.get("antwort_korrekt")
                        extra = [{"fundstelle": ps[idx[n - 1]]["head"], "dokument": ps[idx[n - 1]]["doc"] + ".md"}
                                 for n in r.get("weitere", []) if isinstance(n, int) and 1 <= n <= len(idx) and n != s1]
                        res = {"urteil": "ok" if ok else "verwerfen", "grund": r.get("kommentar", ""),
                               "weitere_fundstellen": extra, "roh": r}
                except Exception as e:  # noqa: BLE001
                    res = {"urteil": "fehler", "grund": str(e)}
            fh.write(json.dumps({"id": c["id"], **res}, ensure_ascii=False) + "\n"); fh.flush()
            print(c["id"], res["urteil"], "|", res.get("grund", "")[:80], flush=True)


if __name__ == "__main__":
    main()
