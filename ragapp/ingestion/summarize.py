"""
Zusammenfassung schreiben (grounded)
====================================

Erzeugt aus einem indexierten Dokument (doc_id) ODER aus allen Chunks eines
Fachs (subject) eine strukturierte, klausurtaugliche Markdown-Zusammenfassung.

GEGROUNDET: Es wird ausschliesslich der Quelltext (die bereits indexierten,
bereinigten Chunks aus der Vektordatenbank) verwendet; das grosse Autoren-Modell
(settings.LLM_MODEL_AUTHOR, Fallback LLM_MODEL) fasst je Abschnitt zusammen und
erfindet nichts. Ausgabe: docs/Zusammenfassung_<name>.md.

Design analog ragapp/ingestion/exam_catalog.py (Abschnittslogik, Anti-
Halluzinations-Bindung, Fortschritts-Callback), aber OHNE Vektorindex-Add:
diese Funktion schreibt nur Markdown.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Callable

from ragapp.config import settings, PROJECT_ROOT, SUBJECT_LABELS
from ragapp import manifest
from ragapp.retrieval.vectorstore import get_vectorstore
from ragapp.llm import get_llm

# Zeichenbudget je LLM-Abschnitt: klein genug, dass die feste num_predict-Grenze
# (settings.LLM_NUM_PREDICT, i. d. R. 1024) fuer eine vollstaendige Zusammen-
# fassung reicht; gross genug fuer thematische Kohaerenz.
_SECTION_CHAR_BUDGET = 5000
_MIN_SECTION_CHARS = 150          # zu kurze Abschnitte ueberspringen (wie exam_catalog)
_PREFIX_RE = re.compile(r"^\[[^\]]{0,120}\]\n")   # entfernt den [header_path]-Prefix der Chunks


_SYSTEM = (
    "Du bist ein erfahrener Hochschul-Tutor und schreibst praezise, klausur-"
    "taugliche Lern-Zusammenfassungen. Du bleibst strikt am gelieferten Quelltext "
    "und erfindest nichts hinzu."
)

_PROMPT = """Abschnitt der Quelle "{doc_label}" (Thema: {title}).
Nur der folgende Quelltext ist erlaubte Wissensgrundlage:
\"\"\"
{section}
\"\"\"

Schreibe eine praegnante, klausurtaugliche Zusammenfassung DIESES Abschnitts als
Markdown. Regeln:
- Verwende AUSSCHLIESSLICH Informationen aus dem Quelltext oben. Erfinde nichts,
  ergaenze kein Fremdwissen, rate keine Zahlen.
- Struktur (nur die zutreffenden Punkte, in dieser Reihenfolge):
  - **Kernidee:** 1-2 Saetze, worum es geht.
  - **Definitionen & Begriffe:** als Stichpunkte.
  - **Formeln / Regeln:** exakt aus dem Quelltext uebernehmen, LaTeX beibehalten
    (EINFACHER Backslash, in $...$ bzw. $$...$$).
  - **Vorgehen / Merksaetze:** knappe Schritt-fuer-Schritt- bzw. Merk-Punkte.
  - **Typische Stolperfallen:** nur falls im Quelltext genannt.
- Kurz und dicht (Stichpunkte bevorzugt), keine Wiederholung des Rohtexts.
- Beginne NICHT mit einer eigenen Ueberschrift (die Ueberschrift setzt das System);
  gib nur den Fliess-/Stichpunkt-Inhalt aus.
Wenn der Abschnitt keine pruefungsrelevante Substanz enthaelt, gib exakt
"(kein pruefungsrelevanter Inhalt)" aus."""


# --------------------------------------------------------------------------- #
# Quelltext beschaffen
# --------------------------------------------------------------------------- #
def _author_model() -> str:
    """Grosses Autoren-Modell mit Fallback auf das Haupt-Modell."""
    return (getattr(settings, "LLM_MODEL_AUTHOR", "") or "").strip() or settings.LLM_MODEL


def _source_chunks(target: str, mode: str) -> tuple[list[dict], str]:
    """Liefert (geordnete Chunks, Anzeige-Label) fuer ein Dokument oder ein Fach.

    mode: 'document' -> target ist doc_id; 'subject' -> target ist Fachkuerzel;
    'auto' -> per Manifest erraten (doc_id, sonst Fach).
    Chunks kommen aus dem Vektorindex (bereits bereinigt/dedupt), geordnet nach
    meta['chunk_index'] (bzw. filename + chunk_index bei Faechern)."""
    store = get_vectorstore()
    all_chunks = store.get_all_chunks()   # nur type=='chunk'

    if mode == "auto":
        mode = "document" if manifest.get_document(target) else "subject"

    if mode == "document":
        doc = manifest.get_document(target)
        chunks = [c for c in all_chunks if c["meta"].get("doc_id") == target]
        label = (doc["filename"] if doc else target)
        chunks.sort(key=lambda c: int(c["meta"].get("chunk_index", 0)))
    else:  # subject
        chunks = [c for c in all_chunks if c["meta"].get("subject") == target]
        label = SUBJECT_LABELS.get(target, target)
        chunks.sort(key=lambda c: (c["meta"].get("filename") or "",
                                   int(c["meta"].get("chunk_index", 0))))
    return chunks, label


def _clean(text: str) -> str:
    """Entfernt den vom Chunker vorangestellten [header_path]-Prefix."""
    return _PREFIX_RE.sub("", text or "").strip()


def _sections_from_chunks(chunks: list[dict]) -> list[tuple[str, str]]:
    """Baut geordnete (Titel, Text)-Abschnitte:
    - Gruppiert aufeinanderfolgende Chunks mit gleichem 'header_path'/'location'.
    - Splittet uebergrosse Gruppen am Zeichenbudget (_SECTION_CHAR_BUDGET),
      damit jeder LLM-Aufruf beschraenkt bleibt.
    Fallback-Titel: 'location' -> 'header_path' -> 'Abschnitt'."""
    sections: list[tuple[str, str]] = []
    cur_title: Optional[str] = None
    buf: list[str] = []
    size = 0

    def flush():
        nonlocal buf, size
        body = "\n\n".join(buf).strip()
        if body:
            sections.append((cur_title or "Abschnitt", body))
        buf, size = [], 0

    for c in chunks:
        meta = c["meta"]
        title = (meta.get("location") or meta.get("header_path") or "Abschnitt").strip()
        piece = _clean(c["document"])
        if not piece:
            continue
        # Neuer Abschnitt bei Themenwechsel ODER wenn Budget gesprengt wuerde
        if cur_title is None:
            cur_title = title
        if title != cur_title or (size + len(piece) > _SECTION_CHAR_BUDGET and buf):
            flush()
            cur_title = title
        buf.append(piece)
        size += len(piece)
    flush()
    return sections


def _safe_name(name: str) -> str:
    """Dateinamens-sicheres Kuerzel (fuer docs/Zusammenfassung_<name>.md)."""
    stem = re.sub(r"\.(pdf|md|docx?|pptx?|txt)$", "", name, flags=re.I)
    stem = re.sub(r"[^\w\-]+", "_", stem, flags=re.U).strip("_")
    return stem or "Quelle"


# --------------------------------------------------------------------------- #
# Hauptfunktion
# --------------------------------------------------------------------------- #
def write_summary(
    doc_id_oder_subject: str,
    mode: str = "auto",                       # 'document' | 'subject' | 'auto'
    progress: Optional[Callable[[str], None]] = None,
    write_markdown: bool = True,
) -> Path:
    """Erzeugt eine gegroundete, strukturierte Markdown-Zusammenfassung und
    schreibt sie nach docs/Zusammenfassung_<name>.md. Gibt den Pfad zurueck.

    Wirft ValueError, wenn zur Auswahl keine (ausreichenden) Chunks vorliegen."""
    chunks, label = _source_chunks(doc_id_oder_subject, mode)
    if not chunks:
        raise ValueError(f"Keine indexierten Chunks fuer '{doc_id_oder_subject}' gefunden.")

    sections = _sections_from_chunks(chunks)
    llm = get_llm(_author_model())            # grosses Autoren-Modell

    out: list[str] = [
        f"# Zusammenfassung: {label}\n",
        f"*KI-generierte, gegroundete Zusammenfassung aus deinen indexierten "
        f"Inhalten. Modell: `{_author_model()}`. Im Zweifel immer mit der "
        f"Originalquelle abgleichen.*\n",
    ]

    total = len(sections)
    written = 0
    for i, (title, body) in enumerate(sections, 1):
        if len(body) < _MIN_SECTION_CHARS:
            continue
        if progress:
            progress(f"Zusammenfassung {label}: '{title[:40]}' ({i}/{total}) …")
        try:
            md = llm.generate(
                _PROMPT.format(doc_label=label, title=title, section=body[:_SECTION_CHAR_BUDGET]),
                system=_SYSTEM, temperature=0.2, think="low",   # Reasoning knapp -> Antwort statt Gedankenkette
            ).strip()
        except Exception:                     # einzelnen Abschnitt ueberspringen (wie exam_catalog)
            continue
        if not md or md.startswith("(kein pruefungsrelevant"):
            continue
        out.append(f"\n## {title}\n")
        out.append(md + "\n")
        written += 1

    if written == 0:
        raise ValueError("Es konnte kein Abschnitt zusammengefasst werden (leer/Fehler).")

    md_path = PROJECT_ROOT / "docs" / f"Zusammenfassung_{_safe_name(label)}.md"
    if write_markdown:
        if progress:
            progress(f"Schreibe {md_path.name} …")
        md_path.write_text("\n".join(out), "utf-8")
    return md_path
