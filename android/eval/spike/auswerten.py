#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fasst Spike-Laeufe (*.json) zusammen. Qualitaet grob: Wortueberlappung mit der erwarteten
Antwort (nur Orientierung, kein Ersatz fuers Lesen) bzw. Verweigerungsformel bei unbeantwortbar."""
import json, re, statistics as st, sys
from pathlib import Path

def words(s): return {w for w in re.findall(r"\w{4,}", s.lower())}
def med(xs): return round(st.median(xs), 1) if xs else None

def summarize(p):
    d = json.load(open(p, encoding="utf-8"))
    rs = d.get("results", [])
    ok = {"direkt": [], "umformuliert": [], "mehrstufig": [], "unbeantwortbar": []}
    for r in rs:
        a, e = r["antwort"], r["erwartet"]
        if r["typ"] == "unbeantwortbar":
            hit = "nicht im material" in a.lower()
        else:
            ew = words(e); hit = len(ew & words(a)) / max(1, len(ew)) >= 0.5
        ok[r["typ"]].append(hit)
    b = [r["bench"] for r in rs if "bench" in r]
    print(f"{d['tag']:18} {d['model'][:22]:22} {d['backend']:3} mtp={d['mtp']!s:5} Laden {d.get('load_ms',0)/1000:6.1f}s | "
          f"TTFT med {med([x['ttft_s'] for x in b])}s | Prefill {med([x['prefill_tps'] for x in b])} tok/s | "
          f"Decode {med([x['decode_tps'] for x in b])} tok/s | RAM-Spitze {d.get('env_end',{}).get('hwm_mb')} MB | "
          f"Temp {d.get('env_end',{}).get('batt_temp_c')}C | Ergebnis " +
          " ".join(f"{k[:4]} {sum(v)}/{len(v)}" for k, v in ok.items() if v) + f" | n={len(rs)} {d.get('status')}")

for p in sorted(Path(__file__).parent.glob("*.json")) if len(sys.argv) < 2 else map(Path, sys.argv[1:]):
    try: summarize(p)
    except Exception as ex: print(p.name, "Fehler", ex)
