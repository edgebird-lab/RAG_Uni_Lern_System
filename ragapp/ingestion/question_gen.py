"""
Fragen-Generierung (Hypothetical Questions)
==========================================

Für jeden Chunk generiert das LLM mehrere prägnante Prüfungsfragen, die *genau
mit diesem Chunk* beantwortbar sind. Diese Fragen werden zusätzlich zum Chunk in
die Vektordatenbank aufgenommen (als eigene Einträge, die auf den Eltern-Chunk
zeigen).

Warum das die Trefferquote erhöht:
    Nutzer stellen Fragen ("Wie berechnet man den Deckungsbeitrag?"). Solche
    Fragen liegen im Embedding-Raum oft näher an einer *Frage* als am reinen
    Lehrtext. Durch die indexierten Fragen findet das System den richtigen Chunk
    deutlich zuverlässiger (Multi-Representation-Indexing).
"""
from __future__ import annotations

from ragapp.config import settings
from ragapp.llm import get_llm

_SYSTEM = (
    "Du bist ein erfahrener Prüfungs-Coach an einer deutschen Hochschule. "
    "Du formulierst knappe, eigenständige Klausur-/Verständnisfragen auf Deutsch."
)

_PROMPT = """Lies den folgenden Abschnitt aus einer Klausur-Zusammenfassung.

Formuliere genau {n} verschiedene, eigenständige Fragen auf Deutsch, die
AUSSCHLIESSLICH mit den Informationen aus DIESEM Abschnitt beantwortet werden
können. Regeln:
- Jede Frage muss allein aus dem Abschnitt beantwortbar sein (kein Zusatzwissen).
- Verschiedene Aspekte abdecken (Definition, Berechnung, Beispiel, Abgrenzung).
- Natürliche Prüfungssprache, so wie ein Studierender fragen würde.
- Keine Verweise wie "laut Abschnitt" oder "im Text".

Abschnitt:
\"\"\"
{chunk}
\"\"\"

Gib NUR gültiges JSON in diesem Format zurück:
{{"questions": ["...", "..."]}}"""


def generate_questions(chunk_text: str, n: int | None = None, model: str | None = None) -> list[str]:
    n = n or settings.NUM_INDEX_QUESTIONS
    # Für die Bulk-Fragenerzeugung nutzen wir standardmäßig das schnellere Modell.
    llm = get_llm(model or settings.LLM_MODEL_FAST)
    # sehr kurze Chunks lohnen keine Fragen
    if len(chunk_text.strip()) < settings.MIN_CHUNK_CHARS:
        return []
    try:
        data = llm.generate_json(
            _PROMPT.format(n=n, chunk=chunk_text[:2500]),
            system=_SYSTEM,
            temperature=0.3,
        )
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    questions = data.get("questions", [])
    out: list[str] = []
    seen = set()
    for q in questions:
        if isinstance(q, str):
            q = q.strip()
            key = q.lower()
            if q and key not in seen and q.endswith("?"):
                seen.add(key)
                out.append(q)
    return out[:n]
