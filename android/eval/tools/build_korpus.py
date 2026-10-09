#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Baut das freie Eval-Korpus fuer das Android-Goldset.

Quellen (alle frei weitergebbar):
  * Gesetze: gesetze-im-internet.de (amtliche Werke, gemeinfrei nach Par. 5 UrhG)
  * Wikipedia (de): CC BY-SA 4.0, mit Titel, Revision und URL im Kopf jeder Datei

Aufruf:  python3 build_korpus.py            (aus beliebigem Verzeichnis)
Ergebnis: ../korpus/*.md  +  ../korpus/QUELLEN.md
"""
from __future__ import annotations

import io
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import date
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "korpus"
UA = "RAG-Lernsystem-eval/0.1 (https://github.com/edgebird-lab/RAG_Uni_Lern_System)"

GESETZE = [
    ("gg", "Grundgesetz für die Bundesrepublik Deutschland", "Art"),
    ("bgb", "Bürgerliches Gesetzbuch", "§"),
    ("hgb", "Handelsgesetzbuch", "§"),
]
WIKI = [
    "Photosynthese", "Industrielle Revolution", "Quicksort", "Inflation",
    "Klimawandel", "Römisches Reich", "Blutkreislauf", "Zelle (Biologie)",
]


def _get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60) as r:
        return r.read()


def _text(el: ET.Element) -> str:
    parts: list[str] = []

    def walk(e: ET.Element) -> None:
        if e.tag == "BR":
            parts.append("\n")
        if e.text:
            parts.append(e.text)
        for c in e:
            walk(c)
            if c.tail:
                parts.append(c.tail)

    walk(el)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", "".join(parts))).strip()


def build_gesetz(key: str, titel: str, prefix: str) -> tuple[str, int, str]:
    raw = _get(f"https://www.gesetze-im-internet.de/{key}/xml.zip")
    zf = zipfile.ZipFile(io.BytesIO(raw))
    root = ET.fromstring(zf.read(zf.namelist()[0]))
    stand = ""
    lines = [f"# {titel}", ""]
    n = 0
    for norm in root.findall("norm"):
        meta = norm.find("metadaten")
        if meta is None:
            continue
        sk = meta.find("standangabe/standkommentar")
        if sk is not None and not stand:
            stand = (sk.text or "").strip()
        enbez = (meta.findtext("enbez") or "").strip()
        titel_n = (meta.findtext("titel") or "").strip()
        gl = meta.find("gliederungseinheit")
        body = norm.find("textdaten/text/Content")
        if gl is not None and not enbez:
            lines += [f"\n## {(gl.findtext('gliederungsbez') or '').strip()} {(gl.findtext('gliederungstitel') or '').strip()}".rstrip(), ""]
            continue
        if body is None or not enbez:
            continue
        txt = _text(body)
        if not txt or txt.startswith("(weggefallen)"):
            continue
        lines += [f"### {enbez}" + (f" {titel_n}" if titel_n else ""), "", txt, ""]
        n += 1
    (OUT / f"{key}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return titel, n, stand


def build_wiki(title: str) -> tuple[str, str, str]:
    q = urllib.parse.urlencode({
        "action": "query", "prop": "extracts|revisions", "explaintext": 1, "rvprop": "ids",
        "format": "json", "titles": title, "redirects": 1,
    })
    d = json.loads(_get(f"https://de.wikipedia.org/w/api.php?{q}"))
    page = next(iter(d["query"]["pages"].values()))
    rev = str(page["revisions"][0]["revid"])
    text = page["extract"]
    # "== Ueberschrift ==" -> Markdown
    text = re.sub(r"^====\s*(.+?)\s*====$", r"#### \1", text, flags=re.M)
    text = re.sub(r"^===\s*(.+?)\s*===$", r"### \1", text, flags=re.M)
    text = re.sub(r"^==\s*(.+?)\s*==$", r"## \1", text, flags=re.M)
    url = "https://de.wikipedia.org/wiki/" + urllib.parse.quote(page["title"].replace(" ", "_"))
    slug = re.sub(r"[^a-z0-9]+", "_", page["title"].lower().replace("ö", "oe").replace("ä", "ae").replace("ü", "ue")).strip("_")
    head = (f"# {page['title']}\n\n> Quelle: Wikipedia (de), „{page['title']}“, Revision {rev}, {url}, "
            f"Lizenz CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/deed.de). "
            f"Autorenliste in der Versionsgeschichte des Artikels. Text unverändert bis auf Überschriften-Format.\n\n")
    (OUT / f"wiki_{slug}.md").write_text(head + text.strip() + "\n", encoding="utf-8")
    return page["title"], rev, url


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = ["# Quellen des Eval-Korpus", "", f"Abgerufen am {date.today().isoformat()}.", "",
            "## Gesetze (gemeinfrei, § 5 UrhG, amtliche Werke)", ""]
    for key, titel, prefix in GESETZE:
        t, n, stand = build_gesetz(key, titel, prefix)
        rows.append(f"- `{key}.md`: {t}, {n} Normen. Quelle: https://www.gesetze-im-internet.de/{key}/ ({stand})")
        print(key, n)
    rows += ["", "## Wikipedia (CC BY-SA 4.0)", ""]
    for t in WIKI:
        title, rev, url = build_wiki(t)
        rows.append(f"- {title}, Revision {rev}: {url}")
        print(title, rev)
    (OUT / "QUELLEN.md").write_text("\n".join(rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
