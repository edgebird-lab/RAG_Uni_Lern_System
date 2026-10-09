#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Erzeugt Kandidaten fuer das Android-Goldset aus dem freien Korpus.

Ein groesseres lokales Modell (Ollama) schreibt Fragen zu Textabschnitten.
Jede Frage wird maschinell geprueft (Beleg-Zitat muss woertlich im Abschnitt
stehen) und als `reviewed: false` abgelegt. Menschliche Durchsicht ist Pflicht,
bevor das Goldset als Messlatte gilt (siehe ../goldset/README.md).

Typen: direkt | umformuliert | mehrstufig | unbeantwortbar

Aufruf:
  python3 -I generate_goldset.py --plan default [--model gemma4:latest] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import random
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KORPUS = ROOT / "korpus"
OUT = ROOT / "goldset" / "kandidaten.jsonl"
OLLAMA = "http://127.0.0.1:11434"

# Anzahl Kandidaten pro Dokument und Typ (Ueberschuss ~30 %, da Pruefung aussortiert).
# 'unbeantwortbar' wird NICHT generiert, sondern von Hand geschrieben (goldset/unbeantwortbar_manuell.jsonl),
# weil generierte Fangfragen haeufig doch beantwortbar sind (z. B. Wellenlaenge im Photosynthese-Artikel).
PLAN = {
    "gg": {"direkt": 18, "umformuliert": 5, "mehrstufig": 5},
    "bgb": {"direkt": 10, "umformuliert": 3, "mehrstufig": 4},
    "hgb": {"direkt": 7, "umformuliert": 2, "mehrstufig": 3},
    "wiki_photosynthese": {"direkt": 5, "umformuliert": 1, "mehrstufig": 3},
    "wiki_industrielle_revolution": {"direkt": 5, "umformuliert": 1, "mehrstufig": 3},
    "wiki_quicksort": {"direkt": 5, "umformuliert": 1, "mehrstufig": 3},
    "wiki_inflation": {"direkt": 5, "umformuliert": 1, "mehrstufig": 3},
    "wiki_klimawandel": {"direkt": 5, "umformuliert": 1, "mehrstufig": 3},
    "wiki_roemisches_reich": {"direkt": 5, "umformuliert": 1, "mehrstufig": 3},
    "wiki_blutkreislauf": {"direkt": 5, "umformuliert": 1, "mehrstufig": 3},
    "wiki_zelle_biologie": {"direkt": 4, "umformuliert": 1, "mehrstufig": 3},
}

SYS = ("Du erstellst Prüfungsfragen für ein Lernsystem auf Deutsch. Antworte AUSSCHLIESSLICH mit "
       "einem JSON-Objekt. Die Frage muss ohne den Text verständlich sein (nie „im Text“, „laut "
       "Abschnitt“ o. ä.) und genau eine klare Antwort haben.")

P_DIREKT = ('Text:\n"""\n{text}\n"""\n\nSchreibe EINE Faktenfrage, die dieser Text beantwortet.\n'
            'JSON: {{"frage": "...", "antwort": "kurz, 1-2 Sätze", "beleg": "WÖRTLICHES Zitat (max. 200 Zeichen) aus dem Text, das die Antwort enthält"}}')
P_UMFORM = ('Text:\n"""\n{text}\n"""\n\nSchreibe EINE Frage, die dieser Text beantwortet, aber verwende '
            'möglichst KEINE der auffälligen Wörter des Textes (Synonyme, Umschreibungen, Alltagssprache).\n'
            'JSON: {{"frage": "...", "antwort": "kurz, 1-2 Sätze", "beleg": "WÖRTLICHES Zitat (max. 200 Zeichen) aus dem Text"}}')
P_MULTI = ('Zwei benachbarte Textabschnitte:\n[A]\n"""\n{a}\n"""\n[B]\n"""\n{b}\n"""\n\nSchreibe EINE konkrete Frage, die nur '
           'mit je einem Sachverhalt aus A UND aus B vollständig beantwortbar ist (z. B. Vergleich, Gemeinsamkeit oder '
           'Zusammenhang). Nenne in der Frage beide Sachverhalte mit ihren Fachbegriffen, Zahlen oder Artikeln. '
           'Verwende KEINE Meta-Wörter wie „Abschnitt“, „Text“, „Absatz“ oder „genannt“.\n'
           'JSON: {{"frage": "...", "antwort": "kurz, 1-3 Sätze", "beleg": "WÖRTLICHES Zitat (max. 200 Zeichen) aus A", "beleg2": "WÖRTLICHES Zitat (max. 200 Zeichen) aus B"}}')
P_UNANS = ('Thema des Dokuments: {thema}\nAbschnitt:\n"""\n{text}\n"""\n\nSchreibe EINE Frage zum Thema, die thematisch nah '
           'liegt, aber von diesem Abschnitt NICHT beantwortet wird und vermutlich im ganzen Dokument nicht steht '
           '(z. B. ein Detail, eine Zahl oder ein Vergleich, der fehlt). Keine Fangfrage mit falscher Prämisse.\n'
           'JSON: {{"frage": "...", "warum_nicht_beantwortbar": "kurz"}}')


def chat(model: str, prompt: str) -> dict:
    body = json.dumps({"model": model, "stream": False, "format": "json", "think": False,
                       "options": {"temperature": 0.4, "num_ctx": 8192},
                       "messages": [{"role": "system", "content": SYS}, {"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/chat", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        txt = json.load(r)["message"]["content"]
    return json.loads(txt)


def sections(doc: str) -> list[tuple[str, str]]:
    """(Fundstelle, Text) je ### Abschnitt; lange Abschnitte werden an Absatzgrenzen geteilt."""
    raw = (KORPUS / f"{doc}.md").read_text(encoding="utf-8")
    out: list[tuple[str, str]] = []
    head = ""
    h2 = ""
    buf: list[str] = []

    def flush() -> None:
        txt = "\n".join(buf).strip()
        buf.clear()
        if not head or len(txt) < 250:
            return
        paras = [p for p in txt.split("\n") if p.strip()]
        cur = ""
        for p in paras:
            if len(cur) + len(p) > 1400 and cur:
                out.append((f"{head}" + (f" ({h2})" if h2 and h2 != head else ""), cur.strip()))
                cur = ""
            cur += p + "\n"
        if len(cur) >= 250:
            out.append((f"{head}" + (f" ({h2})" if h2 and h2 != head else ""), cur.strip()))

    for line in raw.splitlines():
        if line.startswith("## "):
            flush(); h2 = line[3:].strip(); head = h2
        elif line.startswith("###"):
            flush(); head = line.lstrip("#").strip()
        elif not line.startswith("# ") and not line.startswith("> Quelle:"):
            buf.append(line)
    flush()
    # Rein formale Abschnitte (Inhalts-/Literaturverzeichnis) ausschliessen
    skip = ("Literatur", "Weblinks", "Einzelnachweise", "Siehe auch", "Anmerkungen", "Fußnoten")
    return [(h, t) for h, t in out if not any(h.startswith(s) for s in skip)]


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def quote_ok(quote: str, text: str) -> bool:
    q = norm(quote.strip(" .…\"“„"))
    return len(q) >= 15 and q in norm(text)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemma4:latest")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--only", help="nur dieses Dokument (z. B. gg)")
    ap.add_argument("--scale", type=float, default=1.0, help="Faktor auf die Planmengen (Test: 0.2)")
    ap.add_argument("--typen", help="nur diese Typen, kommagetrennt (z. B. umformuliert,direkt)")
    ap.add_argument("--offset", type=int, default=0, help="ID-Zaehler-Versatz, damit neue Laeufe keine IDs ueberschreiben")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if OUT.exists():
        done = {json.loads(l)["id"] for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip()}
    n_ok = n_bad = 0
    with OUT.open("a", encoding="utf-8") as fh:
        for doc, plan in PLAN.items():
            if a.only and doc != a.only:
                continue
            secs = sections(doc)
            thema = (KORPUS / f"{doc}.md").read_text(encoding="utf-8").splitlines()[0].lstrip("# ")
            ordered = list(secs)
            rnd.shuffle(secs)
            used = 0
            for typ, cnt in plan.items():
                cnt = max(1, round(cnt * a.scale))
                if a.typen and typ not in a.typen.split(","):
                    continue
                for i in range(cnt):
                    qid = f"{doc}-{typ[:4]}-{i + 1 + a.offset:02d}"
                    if qid in done:
                        continue
                    (h1, t1) = secs[used % len(secs)]; used += 1
                    try:
                        if typ == "mehrstufig":
                            pos = ordered.index((h1, t1))
                            (h2, t2) = ordered[pos + 1] if pos + 1 < len(ordered) else ordered[pos - 1]
                            if a.dry_run:
                                print(qid, h1, "+", h2); continue
                            r = chat(a.model, P_MULTI.format(a=t1[:1200], b=t2[:1200]))
                            ok = quote_ok(r.get("beleg", ""), t1) and quote_ok(r.get("beleg2", ""), t2)
                            rec = {"belege": [{"fundstelle": h1, "zitat": r.get("beleg", "")},
                                              {"fundstelle": h2, "zitat": r.get("beleg2", "")}]}
                        elif typ == "unbeantwortbar":
                            if a.dry_run:
                                print(qid, h1); continue
                            r = chat(a.model, P_UNANS.format(thema=thema, text=t1[:1200]))
                            ok = bool(r.get("frage"))
                            rec = {"belege": [], "hinweis": r.get("warum_nicht_beantwortbar", "")}
                            r["antwort"] = "Nicht im Material gefunden."
                        else:
                            if a.dry_run:
                                print(qid, h1); continue
                            r = chat(a.model, (P_DIREKT if typ == "direkt" else P_UMFORM).format(text=t1[:1400]))
                            ok = quote_ok(r.get("beleg", ""), t1)
                            rec = {"belege": [{"fundstelle": h1, "zitat": r.get("beleg", "")}]}
                    except Exception as e:  # noqa: BLE001 - Modell-/JSON-Fehler -> naechster Versuch
                        print("FEHLER", qid, e); n_bad += 1; continue
                    if not ok or not r.get("frage") or re.search(r"\b(im|laut) (text|abschnitt)\b|abschnitt|textstelle|\btexte?s?\b", r["frage"], re.I):
                        print("verworfen", qid); n_bad += 1; continue
                    rec |= {"id": qid, "typ": typ, "dokument": f"{doc}.md", "frage": r["frage"].strip(),
                            "erwartete_antwort": r["antwort"].strip(), "modell": a.model, "reviewed": False}
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n"); fh.flush()
                    n_ok += 1
                    print("ok", qid, "|", rec["frage"][:90])
    print(f"fertig: {n_ok} Kandidaten, {n_bad} verworfen")


if __name__ == "__main__":
    main()
