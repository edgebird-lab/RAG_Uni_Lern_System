"""
Klausur-Lernkatalog (exam-driven Frage-Antwort-Katalog)
=======================================================

Idee (vom Nutzer): Die kommende Klausur folgt den Altklausuren. Wenn wir die
Themen der Altklausuren abdecken und zu jedem fundierte Frage-Antwort-Paare
haben, ist man vorbereitet.

Dieser Generator nimmt:
    * eine **saubere Markdown-Zusammenfassung** (mit LaTeX-Formeln!) eines Fachs,
      gegliedert nach ``##``-Abschnitten (die oft 1:1 den Klausur-Aufgaben
      entsprechen), und
    * die **Altklausuren** (PDF) als Themen-/Aufgabentyp-Hinweis,

und erzeugt pro Abschnitt mit dem lokalen LLM mehrere **Frage-Antwort-Paare**:
    * Frage: so, wie ein Studierender sie stellt ("Wie berechne ich …?").
    * Antwort: erklärt das **Vorgehen Schritt für Schritt** (Rezept, Formeln aus
      dem Abschnitt exakt übernommen, typische Stolperfallen), damit man die
      Aufgabe **selbst rechnen** kann. Es wird nichts Neues erfunden.

Ergebnis:
    1. Jedes Q&A-Paar wird als eigener, frage-förmiger Chunk in die
       Vektordatenbank indexiert -> Konzeptfragen werden zuverlässig gefunden.
    2. Zusätzlich wird ein lesbarer **Lernkatalog** als Markdown geschrieben
       (``docs/Lernkatalog_<Fach>.md``) zum direkten Durchlernen.

Sicherheit gegen Halluzination: Die Antworten sind an den Abschnitt gebunden;
die Original-Zusammenfassung ist ebenfalls indexiert; jede Antwort trägt die
Quelle und einen Hinweis, im Zweifel die Zusammenfassung zu prüfen.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Optional

from ragapp.config import settings, SOURCE_DIR, PROJECT_ROOT
from ragapp import manifest
from ragapp.ingestion.loaders import load_document
from ragapp.ingestion import dedup
from ragapp.retrieval.embeddings import get_embedder
from ragapp.retrieval.vectorstore import get_vectorstore
from ragapp.llm import get_llm

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.*)$")

_SYSTEM = (
    "Du bist ein erfahrener Analysis-/Mathematik-Tutor an einer Hochschule und "
    "bereitest Studierende gezielt auf die Klausur vor. Du erklärst so, dass man "
    "die Aufgaben danach selbst rechnen kann."
)

_PROMPT = """Thema/Abschnitt der Zusammenfassung (enthält die relevanten Formeln in LaTeX):
\"\"\"
{section}
\"\"\"

Passender Klausur-Aufgabentyp (aus Altklausuren, nur als Kontext):
{exam_hint}

Erzeuge {n} Frage-Antwort-Paare für einen Klausur-Lernkatalog. Regeln:
- FRAGE: natürlich formuliert, wie ein Studierender sie stellt (z. B. "Wie berechne
  ich die Summe einer unendlichen geometrischen Reihe und wann konvergiert sie?").
- ANTWORT: erkläre das VORGEHEN Schritt für Schritt (Rezept), übernimm die
  relevanten Formeln EXAKT aus dem Abschnitt (LaTeX beibehalten), nenne typische
  Stolperfallen und, wenn im Abschnitt vorhanden, ein kurzes Beispiel.
- Ziel ist ERKLÄREN, nicht eine konkrete Zahl ausrechnen.
- Verwende AUSSCHLIESSLICH Informationen aus dem Abschnitt. Erfinde nichts.
- Verschiedene Aspekte pro Thema abdecken (Definition, Vorgehen, Sonderfälle).

Gib die Paare GENAU in diesem Textformat aus (KEIN JSON!). Schreibe alle Formeln
ganz normal als LaTeX mit EINFACHEM Backslash (nicht doppelt), in $...$ bzw. $$...$$:

<<<FRAGE>>>
(die Frage)
<<<ANTWORT>>>
(die Antwort mit Formeln)
<<<PAAR-ENDE>>>

Wiederhole diesen Block für jedes der {n} Paare. Sonst keine Ausgabe."""


def _parse_pairs(text: str) -> list[dict]:
    """Parst das Textformat <<<FRAGE>>>…<<<ANTWORT>>>…<<<PAAR-ENDE>>> (LaTeX-sicher)."""
    pairs = []
    for block in text.split("<<<PAAR-ENDE>>>"):
        if "<<<FRAGE>>>" not in block or "<<<ANTWORT>>>" not in block:
            continue
        after_q = block.split("<<<FRAGE>>>", 1)[1]
        frage = after_q.split("<<<ANTWORT>>>", 1)[0].strip()
        antwort = after_q.split("<<<ANTWORT>>>", 1)[1].strip()
        if frage and antwort:
            pairs.append({"frage": frage, "antwort": antwort})
    return pairs


def _split_sections(md_text: str) -> list[tuple[str, str]]:
    """Zerlegt Markdown in (Abschnittstitel, Abschnittstext) an ##/###-Überschriften."""
    lines = md_text.split("\n")
    sections: list[tuple[str, str]] = []
    title = "Einleitung"
    buf: list[str] = []
    for line in lines:
        m = _HEADER_RE.match(line.strip())
        if m and len(m.group(1)) <= 3:  # nur #, ##, ###
            body = "\n".join(buf).strip()
            if body:
                sections.append((title, body))
            title = m.group(2).strip()
            buf = []
        else:
            buf.append(line)
    body = "\n".join(buf).strip()
    if body:
        sections.append((title, body))
    return sections


def _exam_hints(exam_files: list[Path]) -> dict[str, str]:
    """Extrahiert 'Aufgabe N …'-Zeilen aus den Altklausuren als Themen-Hinweise."""
    hints: dict[str, str] = {}
    for f in exam_files:
        try:
            text = load_document(f).text
        except Exception:
            continue
        for m in re.finditer(r"(Aufgabe\s*\d+[^\n]{0,160})", text):
            line = m.group(1).strip()
            num = re.match(r"Aufgabe\s*(\d+)", line)
            if num:
                key = num.group(1)
                hints.setdefault(key, line)
    return hints


def _match_hint(title: str, hints: dict[str, str]) -> str:
    """Ordnet einem Abschnittstitel (z. B. '§ 4: Reihen (Aufg. 4)') die Klausur-Aufgabe zu."""
    m = re.search(r"Aufg\.?\s*(\d+)", title) or re.search(r"§\s*(\d+)", title)
    if m and m.group(1) in hints:
        return hints[m.group(1)]
    return "(kein direkter Aufgaben-Bezug)"


def build_exam_catalog(
    subject: str,
    summary_path: str | Path | None = None,
    exam_files: Optional[list[str | Path]] = None,
    n_per_section: int = 3,
    write_markdown: bool = True,
    progress=None,
) -> dict:
    """Erzeugt den Klausur-Lernkatalog für ein Fach und indexiert ihn."""
    # Quelle bestimmen
    if summary_path is None:
        cands = list((SOURCE_DIR / subject).rglob("*Zusammenfassung*.md"))
        if not cands:
            cands = list((SOURCE_DIR / subject).rglob("*.md"))
        if not cands:
            return {"status": "no_summary", "subject": subject}
        summary_path = cands[0]
    summary_path = Path(summary_path)

    if exam_files is None:
        exam_files = list((SOURCE_DIR / subject).rglob("Klausur_*.pdf"))
    exam_files = [Path(f) for f in exam_files]

    md_text = summary_path.read_text("utf-8", errors="replace")
    sections = _split_sections(md_text)
    hints = _exam_hints(exam_files)

    llm = get_llm(settings.LLM_MODEL)  # Haupt-Modell für gute Erklärqualität
    embedder = get_embedder()
    store = get_vectorstore()

    doc_id = dedup.doc_id_for(f"lernkatalog::{subject}")
    catalog_md = [f"# Klausur-Lernkatalog: {subject}\n",
                  f"*KI-generierter Lernkatalog aus deiner Zusammenfassung + Altklausuren. "
                  f"Grundlage: `{summary_path.name}`. Im Zweifel immer mit der Zusammenfassung "
                  f"abgleichen.*\n"]

    ids, embeddings, documents, metadatas = [], [], [], []
    total_pairs = 0
    idx = 0

    # Nur inhaltlich relevante Abschnitte (überspringe reine Kurzcheck-/Ergebnislisten)
    for title, body in sections:
        if len(body) < 150:
            continue
        if progress:
            progress(f"Lernkatalog {subject}: '{title[:40]}' …")
        exam_hint = _match_hint(title, hints)
        try:
            raw = llm.generate(
                _PROMPT.format(section=body[:3500], exam_hint=exam_hint, n=n_per_section),
                system=_SYSTEM, temperature=0.2,
            )
        except Exception:
            continue
        pairs = _parse_pairs(raw)  # LaTeX-sicher (kein JSON)
        if not pairs:
            continue

        catalog_md.append(f"\n## {title}\n")
        for pair in pairs:
            frage = (pair.get("frage") or "").strip()
            antwort = (pair.get("antwort") or "").strip()
            if not frage or not antwort:
                continue
            # frage-förmiger, selbst-enthaltender Chunk für gutes Retrieval
            doc = (f"[Klausur-Lernkatalog · {subject} · {title}]\n"
                   f"FRAGE: {frage}\n\nERKLÄRUNG (Vorgehen):\n{antwort}")
            ids.append(f"{doc_id}::qa{idx}")
            documents.append(doc)
            metadatas.append({
                "type": "chunk", "doc_id": doc_id, "subject": subject,
                "filename": f"Lernkatalog_{subject}.md", "source_path": f"docs/Lernkatalog_{subject}.md",
                "location": title, "header_path": title, "kind": "exam_qa",
            })
            catalog_md.append(f"**F: {frage}**\n\n{antwort}\n")
            idx += 1
            total_pairs += 1

    if not ids:
        return {"status": "empty", "subject": subject}

    if progress:
        progress(f"Berechne Embeddings ({len(ids)} Q&A) …")
    embeddings = embedder.embed_texts(documents)
    store.add(ids, embeddings, documents, metadatas)

    manifest.upsert_document(
        doc_id=doc_id, content_hash=dedup.content_hash("".join(documents)),
        source_path=f"docs/Lernkatalog_{subject}.md", filename=f"Lernkatalog_{subject}.md",
        subject=subject, filetype="catalog", num_chunks=len(ids), num_questions=0,
        char_count=sum(len(d) for d in documents), status="ok",
    )

    md_path = None
    if write_markdown:
        md_path = PROJECT_ROOT / "docs" / f"Lernkatalog_{subject}.md"
        md_path.write_text("\n".join(catalog_md), "utf-8")

    return {"status": "ok", "subject": subject, "pairs": total_pairs,
            "sections": len(sections), "markdown": str(md_path) if md_path else None}
