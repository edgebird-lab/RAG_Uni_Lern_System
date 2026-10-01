"""Lernplan x Karteikarten: Karten zu einem Thema finden, erzeugen, auffüllen.

Verknüpfung OHNE Schema-Änderung: Ein Plan-Thema kennt seine Quellen als
``source_refs`` = ``[{doc_id, filename, section}]`` mit ``section`` = Fundstelle
(„Seite 4“ bzw. Überschriftenpfad) - dieselbe Fundstelle, die jede Karte als ``topic``
trägt (``study._topic``: location, sonst header_path). Karten eines Themas sind also
die Karten des Dokuments mit passender Fundstelle. Das gilt für BESTEHENDE Karten
genauso wie für neue, und eine geänderte Gliederung entwertet keine Karten (sie hängen
an Seiten, nicht an Titeln).

Hat die KI Abschnitte zusammengefasst, steht in ``section`` ein „A / B“ (Menge) bzw.
„A … B“ (Bereich) - siehe ``study_plan._merge_tiny_sections`` und
``study_plan._disp_title``; ``section_locations`` löst das auf.
"""
from __future__ import annotations

import re
import time
from datetime import date, datetime
from typing import Callable, Optional

from ragapp import card_quality, manifest

_RANGE_SEP = " … "
_SET_SEP = " / "
_NO_TITLE = "Abschnitt"        # Titel-Fallback der Abschnittslogik (study_plan/summarize)
_NO_TOPIC = "__none__"         # find_cards: Karten ohne Fundstelle


# --------------------------------------------------------------------------- #
# Fundstellen eines Themas
# --------------------------------------------------------------------------- #
def chunk_title(meta: Optional[dict]) -> str:
    """Titel eines Chunks wie ``summarize._sections_from_chunks`` ihn bildet."""
    m = meta or {}
    return (m.get("location") or m.get("header_path") or _NO_TITLE).strip()


def expand_titles(title: str, ordered: Optional[list[str]] = None) -> list[str]:
    """Löst einen zusammengefassten Quellentitel in einzelne Fundstellen auf.

    „Seite 3 / Seite 4“ -> beide; „Seite 3 … Seite 7“ -> alle Fundstellen dazwischen
    (``ordered`` = Fundstellen des Dokuments in Reihenfolge; ohne sie nur Anfang und
    Ende). Ein gewöhnlicher Titel bleibt unverändert."""
    t = (title or "").strip()
    if not t:
        return []
    if _RANGE_SEP in t:
        left, right = t.split(_RANGE_SEP, 1)
        first = left.split(_SET_SEP)[0].strip()
        last = right.split(_SET_SEP)[-1].strip()
        if ordered and first in ordered and last in ordered:
            a, b = ordered.index(first), ordered.index(last)
            if a <= b:
                return ordered[a:b + 1]
        return [first] if first == last else [first, last]
    if _SET_SEP in t:
        return [x.strip() for x in t.split(_SET_SEP) if x.strip()]
    return [t]


_titles_cache: dict[tuple, list[str]] = {}


def doc_titles(doc_id: str) -> list[str]:
    """Fundstellen eines Dokuments in Dokumentreihenfolge (aus den Chunk-Metadaten).
    Nur nötig, um Bereiche „A … B“ aufzulösen; je Dokument-Stand zwischengespeichert."""
    doc = manifest.get_document(doc_id)
    key = (doc_id, (doc["content_hash"] if doc else None), (doc["num_chunks"] if doc else None))
    if key in _titles_cache:
        return _titles_cache[key]
    from ragapp.retrieval.vectorstore import get_vectorstore
    titles: list[str] = []
    for c in get_vectorstore().get_doc_chunks(doc_id):
        t = chunk_title(c.get("meta"))
        if not titles or titles[-1] != t:
            titles.append(t)
    _titles_cache[key] = titles
    return titles


def section_locations(section: dict) -> dict[str, list[str]]:
    """``{doc_id: [Fundstelle, …]}`` eines Plan-Themas (aus seinen ``source_refs``)."""
    out: dict[str, list[str]] = {}
    for ref in section.get("source_refs") or []:
        did = ref.get("doc_id")
        title = (ref.get("section") or "").strip()
        if not did or not title:
            continue
        if _RANGE_SEP in title or _SET_SEP in title:
            ordered = doc_titles(did)
            titles = [title] if title in ordered else expand_titles(title, ordered)
        else:
            titles = [title]
        bucket = out.setdefault(did, [])
        for t in titles:
            if t not in bucket:
                bucket.append(t)
    return out


# --------------------------------------------------------------------------- #
# Referenz eines Themas: das Dokument, aus dem es entstanden ist
# --------------------------------------------------------------------------- #
_PAGE_RE = re.compile(r"^\s*(?:Seite|Folie|Slide|Page)\s*(\d+)\s*$", re.IGNORECASE)


def page_number(title: Optional[str]) -> Optional[int]:
    """Seitenzahl aus einer Fundstelle der Form „Seite 7“ (sonst None)."""
    m = _PAGE_RE.match(title or "")
    return int(m.group(1)) if m else None


def _title_pages(title: Optional[str]) -> Optional[list[int]]:
    """Seitenzahlen einer Fundstelle: „Seite 4“ -> [4]; „Seite 3 … Seite 6“ -> [3, 4, 5, 6];
    „Seite 3 / Seite 5“ -> [3, 5]. None, wenn es keine Seitenangaben sind."""
    t = (title or "").strip()
    if _RANGE_SEP in t:
        left, right = t.split(_RANGE_SEP, 1)
        a = page_number(left.split(_SET_SEP)[0])
        b = page_number(right.split(_SET_SEP)[-1])
        return list(range(a, b + 1)) if (a is not None and b is not None and a <= b) else None
    parts = expand_titles(t)
    nums = [page_number(x) for x in parts]
    return [n for n in nums if n is not None] if parts and all(n is not None for n in nums) else None


def compress_pages(pages: list[int]) -> str:
    """[1, 2, 3, 7, 8, 12] -> „S. 1–3, 7–8, 12“."""
    nums = sorted(set(pages))
    if not nums:
        return ""
    ranges: list[str] = []
    start = prev = nums[0]
    for n in nums[1:] + [None]:                       # type: ignore[list-item]
        if n is not None and n == prev + 1:
            prev = n
            continue
        ranges.append(str(start) if start == prev else f"{start}–{prev}")
        if n is not None:
            start = prev = n
    return "S. " + ", ".join(ranges)


def section_docs(section: dict) -> list[tuple[str, str]]:
    """``[(doc_id, Dateiname), …]`` der Quellen eines Themas, in Reihenfolge, ohne
    Doppelte. Bei einem sauberen Thema genau EIN Eintrag."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for ref in section.get("source_refs") or []:
        did = ref.get("doc_id")
        if not did or did in seen:
            continue
        seen.add(did)
        out.append((did, ref.get("filename") or did))
    return out


def section_reference(section: dict) -> str:
    """Lesbare Referenz eines Themas: „1 Vektorrechnung.pdf · S. 11–12“. Mehrere
    Dokumente werden mit „ | “ getrennt (sollte bei neuen Gliederungen nicht mehr
    vorkommen: ein Thema stammt aus genau einem Dokument)."""
    parts: list[str] = []
    for did, fname in section_docs(section):
        titles: list[str] = []
        pages: list[int] = []
        all_pages = True
        for ref in section.get("source_refs") or []:
            if ref.get("doc_id") != did:
                continue
            titles += expand_titles(ref.get("section") or "")
            nums = _title_pages(ref.get("section"))
            if nums is None:
                all_pages = False
            else:
                pages += nums
        if titles and all_pages and pages:
            where = compress_pages(pages)
        else:
            shown = [t for t in titles if t][:2]
            where = ", ".join(shown) + (" …" if len([t for t in titles if t]) > 2 else "")
        parts.append(fname + (f" · {where}" if where else ""))
    return " | ".join(parts)


def section_start(section: dict) -> tuple[Optional[str], Optional[int]]:
    """``(doc_id, Seite)`` des Themenanfangs - dorthin springt das Skript. Die Seite ist
    None, wenn die Fundstellen keine Seitenzahlen sind."""
    first_doc: Optional[str] = None
    best: Optional[int] = None
    for ref in section.get("source_refs") or []:
        did = ref.get("doc_id")
        if not did:
            continue
        if first_doc is None:
            first_doc = did
        if did != first_doc:
            continue
        nums = _title_pages(ref.get("section")) or []
        if nums and (best is None or min(nums) < best):
            best = min(nums)
    return first_doc, best


# --------------------------------------------------------------------------- #
# Karten eines Themas
# --------------------------------------------------------------------------- #
def _topic_filter(titles: list[str]) -> list[str]:
    return [_NO_TOPIC if t == _NO_TITLE else t for t in titles]


def section_cards(section: dict, *, limit: int = 500) -> list[dict]:
    """Alle (nicht pausierten) Karten eines Themas."""
    seen: set[str] = set()
    cards: list[dict] = []
    for did, titles in section_locations(section).items():
        for c in manifest.find_cards(doc_ids=[did], topics=_topic_filter(titles), limit=limit):
            if c["card_id"] not in seen:
                seen.add(c["card_id"])
                cards.append(c)
    return cards


def _summarize(cards: list[dict], now: float) -> dict:
    """Kennzahlen eines Kartenbestands. ``known`` = schon geübt und aktuell NICHT fällig (sitzt
    gerade), ``due`` = geübt und fällig, ``new`` = noch nie geübt. ``flawed`` = Karten mit
    Qualitätsmängeln (``card_quality``, ohne Dubletten - die braucht Embeddings)."""
    reviewed = [c for c in cards if (c.get("reps") or 0) > 0]
    due = sum(1 for c in reviewed if (c.get("due") or 0) <= now)
    flagged = card_quality.audit_cards(cards)
    return {
        "cards": len(cards),
        "new": len(cards) - len(reviewed),
        "reviewed": len(reviewed),
        "due": due,
        "known": len(reviewed) - due,
        "unanswered": sum(1 for c in cards
                          if c.get("source") == "question" and not (c.get("answer") or "").strip()),
        "flawed": len(flagged),
        "flawed_ids": list(flagged),
    }


def _cards_by_section(plan: dict, sections: list[dict]) -> dict[str, list[dict]]:
    """Karten je Thema eines Plans mit EINER Abfrage fuer den ganzen Plan (laeuft bei jedem
    Rendern der Lernplan-Seite)."""
    all_cards = manifest.find_cards(doc_ids=list(plan.get("doc_ids") or []) or None, limit=20000)
    by_key: dict[tuple, list[dict]] = {}
    for c in all_cards:
        by_key.setdefault((c.get("doc_id"), (c.get("topic") or _NO_TITLE)), []).append(c)
    out: dict[str, list[dict]] = {}
    for s in sections:
        seen: set[str] = set()
        cards: list[dict] = []
        for did, titles in section_locations(s).items():
            for t in titles:
                for c in by_key.get((did, t), []):
                    if c["card_id"] not in seen:
                        seen.add(c["card_id"])
                        cards.append(c)
        out[s["section_id"]] = cards
    return out


def plan_card_stats(plan: dict, sections: list[dict]) -> dict[str, dict]:
    """Kartenbestand je Thema eines Plans: ``{section_id: {cards, new, reviewed, due, known,
    unanswered, flawed, flawed_ids}}`` (siehe ``_summarize``)."""
    now = time.time()
    return {sid: _summarize(cards, now) for sid, cards in _cards_by_section(plan, sections).items()}


def sections_needing_cards(stats: dict, sections: list[dict], *,
                           with_practice: bool = False) -> list[dict]:
    """Themen, die noch (teilweise) leer sind: ohne Karten oder mit Karten ohne Antwort -
    mit ``with_practice`` auch Themen ohne Übungsaufgabe. Deckt abgebrochene Läufe ab:
    Fragen ohne geerntete Karten zählen als „ohne Karten“, Karten ohne Antwort als
    unvollständig - ein erneuter Lauf macht dort weiter."""
    out = []
    for sec in sections:
        st = stats.get(sec["section_id"]) or {}
        if (st.get("cards", 0) == 0 or st.get("unanswered", 0) > 0
                or (with_practice and st.get("problems", 0) == 0)):
            out.append(sec)
    return out


# Grober Richtwert fuer die Wartezeit-Anzeige (Frage + Musterloesung + Beleg-Pruefung je
# Karte); haengt stark von Modell und Hardware ab - die Oberflaeche sagt das dazu.
SEC_PER_CARD = 6.0
SEC_PER_PROBLEM = 25.0


def estimate_missing_cards(plan: dict, stats: dict) -> int:
    """Grobe Zahl noch fehlender Karten: ein Textabschnitt ~ eine Karte."""
    chunks = 0
    for did in plan.get("doc_ids") or []:
        doc = manifest.get_document(did)
        if doc:
            chunks += int(doc["num_chunks"] or 0)
    return max(0, chunks - sum(v.get("cards", 0) for v in stats.values()))


def estimate_fill_minutes(missing_cards: int, missing_problems: int = 0) -> int:
    return max(1, round((missing_cards * SEC_PER_CARD + missing_problems * SEC_PER_PROBLEM) / 60))


def _quality_note(out: dict) -> str:
    bits = []
    if out.get("rejected"):
        bits.append(f"{out['rejected']} Frage(n) mit Mängeln aussortiert")
    if out.get("duplicates"):
        bits.append(f"{out['duplicates']} doppelte ausgelassen")
    return f" 🧹 {', '.join(bits)}." if bits else ""


def _n(count: int, singular: str, plural: str) -> str:
    """„1 Karte“ / „2 Karten“."""
    return f"{count} {singular if count == 1 else plural}"


def summarize_fill(out: dict) -> tuple[str, str]:
    """(Stufe, Text) für die Rückmeldung nach ``fill_plan_cards``: success | error | info."""
    status = out.get("status")
    if status == "empty":
        return "info", "Es gibt keine Themen, für die Karten erzeugt werden müssten."
    if status in ("no_model", "vram"):
        return "error", out.get("error_msg") or "Die Kartenerzeugung wurde abgebrochen."
    head = "⏹ Abgebrochen – bis dahin:" if status == "cancelled" else "🃏 Fertig:"
    cards, qs, ans = (int(out.get(k) or 0) for k in ("cards_new", "questions", "answers"))
    text = (f"{head} {_n(cards, 'neue Karte', 'neue Karten')} "
            f"({_n(qs, 'Frage', 'Fragen')}, {_n(ans, 'Antwort', 'Antworten')}) "
            f"in {_n(int(out.get('topics_done') or 0), 'Thema', 'Themen')}.")
    if out.get("problems_new"):
        text += f" 🧮 {_n(int(out['problems_new']), 'Übungsaufgabe', 'Übungsaufgaben')} erzeugt."
    if out.get("problems_failed"):
        text += (f" ⚠️ {out['problems_failed']} Übungsaufgabe(n) ließen sich nicht erzeugen"
                 + (f" ({out['practice_error']})" if out.get("practice_error") else "") + ".")
    if out.get("topics_empty"):
        text += (f" {out['topics_empty']} Thema/Themen ohne indexierte Textabschnitte "
                 "wurden übersprungen.")
    text += _quality_note(out)
    if out.get("repair"):
        text += " " + summarize_repair(out["repair"])
    if status == "cancelled":
        text += " Ein erneuter Klick macht dort weiter, wo es aufgehört hat."
        return "info", text
    return "success", text


def study_card_ids(section: dict, limit: int = 16) -> list[str]:
    """Karten fürs Üben: fällige Wiederholungen zuerst, dann neue, dann der Rest."""
    now = time.time()
    cards = section_cards(section)
    due = sorted((c for c in cards if (c.get("reps") or 0) > 0 and (c.get("due") or 0) <= now),
                 key=lambda c: c.get("due") or 0)
    new = [c for c in cards if (c.get("reps") or 0) == 0]
    taken = {c["card_id"] for c in due} | {c["card_id"] for c in new}
    rest = [c for c in cards if c["card_id"] not in taken]
    return [c["card_id"] for c in due + new + rest][:max(1, int(limit))]


# --------------------------------------------------------------------------- #
# Karten erzeugen
# --------------------------------------------------------------------------- #
def section_chunks(section: dict) -> list[dict]:
    """Die Textabschnitte (Chunks) eines Themas in Dokumentreihenfolge."""
    from ragapp.retrieval.vectorstore import get_vectorstore
    store = get_vectorstore()
    out: list[dict] = []
    for did, titles in section_locations(section).items():
        wanted = set(titles)
        out += [c for c in store.get_doc_chunks(did) if chunk_title(c.get("meta")) in wanted]
    return out


def create_section_cards(section: dict, *, n_per_chunk: Optional[int] = 1,
                         max_chunks: Optional[int] = None, with_answers: bool = True,
                         progress: Optional[Callable[[str], None]] = None,
                         should_cancel: Optional[Callable[[], bool]] = None) -> dict:
    """Karten zu EINEM Thema: Fragen zu seinen Textabschnitten, Karten ernten, Antworten
    erzeugen (dieselbe Pipeline wie das Lernset, nur auf die Abschnitte des Themas
    beschränkt). Schon bearbeitete Abschnitte werden übersprungen - der Aufruf ist
    wiederholbar. Rückgabe wie ``study.create_study_set`` plus ``cards_total``.

    Kein Deckel auf die Abschnittszahl (``max_chunks=None``): Themen sind durch
    ``PLAN_TOPIC_MAX_CHARS`` ohnehin begrenzt, und mit Deckel bliebe der Rest eines
    größeren Themas dauerhaft ohne Karten (es zählt danach als „gefüllt“)."""
    from ragapp import study
    chunks = section_chunks(section)
    if not chunks:
        return {"status": "empty", "questions": 0, "cards_new": 0, "answers": 0,
                "cards_total": 0,
                "error_msg": "Zu diesem Thema gibt es keine indexierten Textabschnitte "
                             "(Quelle gelöscht oder neu eingelesen?)."}
    doc_ids = sorted({(c.get("meta") or {}).get("doc_id") for c in chunks} - {None})
    out = study.create_study_set(
        doc_ids, progress=progress, n_per_chunk=n_per_chunk, with_answers=with_answers,
        chunk_ids=[c["id"] for c in chunks], max_chunks=max_chunks, should_cancel=should_cancel)
    out["cards_total"] = len(section_cards(section))
    return out


def section_source_sections(section: dict) -> list[tuple[str, str, str]]:
    """Der Text eines Themas als ``[(Quelle, Titel, Text), …]`` - NUR die Abschnitte der
    Fundstellen des Themas aus seinem Dokument (Grundlage für die Übungsaufgabe)."""
    from ragapp.ingestion.summarize import _sections_from_chunks
    by_doc: dict[Optional[str], list[dict]] = {}
    for c in section_chunks(section):
        by_doc.setdefault((c.get("meta") or {}).get("doc_id"), []).append(c)
    names = dict(section_docs(section))
    out: list[tuple[str, str, str]] = []
    for did, chunks in by_doc.items():
        label = names.get(did) or did or "Quelle"
        for title, body in _sections_from_chunks(chunks):
            out.append((label, title, body))
    return out


def section_problems(section: dict, subject: Optional[str] = None) -> list[dict]:
    """Übungsaufgaben, die zu GENAU diesem Thema erzeugt wurden (Thema-Titel gleich, und
    - falls bekannt - Dokument aus den Quellen des Themas), neueste zuerst. Bewusst keine
    Treffer „irgendeine Aufgabe zum selben Dokument“: das wäre Stoff eines anderen Themas."""
    title = (section.get("title") or "").strip()
    if not title:
        return []
    docs = {d for d, _ in section_docs(section)}
    return [pr for pr in manifest.list_practice_problems(subject=subject, topic=title)
            if not pr.get("doc_id") or not docs or pr["doc_id"] in docs]


def create_section_practice(section: dict, *, subject: Optional[str],
                            kind: Optional[str] = None, model: Optional[str] = None) -> str:
    """EINE Übungsaufgabe zu einem Thema - ausschließlich aus dem Text des Themas (siehe
    ``section_source_sections``). Jede weitere Aufgabe beginnt an einer anderen Stelle des
    Themas, damit nicht zweimal dasselbe herauskommt. Wirft ``PracticeGenError``."""
    from ragapp import practice_gen
    sources = section_source_sections(section)
    if not sources:
        raise practice_gen.PracticeGenError(
            "Zu diesem Thema gibt es keine indexierten Textabschnitte "
            "(Quelle gelöscht oder neu eingelesen?).")
    existing = len(section_problems(section, subject))
    if existing:
        k = existing % len(sources)
        sources = sources[k:] + sources[:k]
    return practice_gen.generate_practice_problem(
        subject=subject, doc_ids=[d for d, _ in section_docs(section)],
        topic=section.get("title"), kind=kind, model=model, source_sections=sources)


def plan_unit_stats(plan: dict, sections: list[dict]) -> dict[str, dict]:
    """Wie ``plan_card_stats``, zusätzlich ``problems`` (Anzahl) und ``problem_ids`` (neueste
    zuerst) je Thema - der Füllstand einer Lerneinheit."""
    stats = plan_card_stats(plan, sections)
    by_topic: dict[str, list[dict]] = {}
    for pr in manifest.list_practice_problems(subject=plan.get("subject")):
        by_topic.setdefault((pr.get("topic") or "").strip(), []).append(pr)
    for sec in sections:
        docs = {d for d, _ in section_docs(sec)}
        mine = [pr for pr in by_topic.get((sec.get("title") or "").strip(), [])
                if not pr.get("doc_id") or not docs or pr["doc_id"] in docs]
        stats[sec["section_id"]]["problems"] = len(mine)
        stats[sec["section_id"]]["problem_ids"] = [pr["problem_id"] for pr in mine]
    return stats


# --------------------------------------------------------------------------- #
# Der Tag im Lernplan
# --------------------------------------------------------------------------- #
def sections_for_day(blocks: list[dict], sections: list[dict], day_iso: str) -> list[dict]:
    """Die Themen, die an diesem Tag geplant sind (in Block-Reihenfolge, ohne Doppelte)."""
    by_id = {s["section_id"]: s for s in sections}
    out: list[dict] = []
    seen: set[str] = set()
    for b in blocks:
        sid = b.get("section_id")
        if b.get("planned_date") == day_iso and sid in by_id and sid not in seen:
            seen.add(sid)
            out.append(by_id[sid])
    return out


def next_study_day(blocks: list[dict], today_iso: str) -> Optional[str]:
    """Der erste Tag ab heute mit noch offenen Blöcken (None, wenn keiner)."""
    days = sorted({b["planned_date"] for b in blocks
                   if b.get("planned_date") and b["planned_date"] >= today_iso
                   and not b.get("done")})
    return days[0] if days else None


def day_card_ids(sections: list[dict], *, per_topic: int = 10, total: int = 30) -> list[str]:
    """Karten für die Themen EINES Tages - und nur für sie: fällige zuerst, dann neue, je
    Thema höchstens ``per_topic``, insgesamt höchstens ``total``."""
    ids: list[str] = []
    seen: set[str] = set()
    for sec in sections:
        for cid in study_card_ids(sec, limit=per_topic):
            if cid not in seen:
                seen.add(cid)
                ids.append(cid)
    return ids[:max(1, int(total))]


def fill_plan_cards(sections: list[dict], *, n_per_chunk: Optional[int] = 1,
                    max_chunks: Optional[int] = None, with_answers: bool = True,
                    with_practice: bool = False, subject: Optional[str] = None,
                    progress: Optional[Callable[[str], None]] = None,
                    should_cancel: Optional[Callable[[], bool]] = None,
                    on_step: Optional[Callable[[int, int], None]] = None) -> dict:
    """Lerneinheiten für ALLE übergebenen Themen nacheinander füllen (ein Klick): Karten
    und - mit ``with_practice`` - eine Übungsaufgabe je Thema, jeweils NUR aus dem Text des
    Themas.

    Das Modell bleibt über alle Themen geladen (``llm_task``). Jedes Thema wird für sich
    gespeichert - ein Abbruch (Tab zu, Modell weg, zu wenig VRAM) verliert nichts, ein
    erneuter Lauf macht dort weiter. Themen ohne Textabschnitte werden übersprungen;
    fehlendes Modell bzw. zu wenig VRAM beenden den Lauf mit einer klaren Meldung. Eine
    fehlgeschlagene Übungsaufgabe stoppt den Lauf nicht (``problems_failed``).

    ``should_cancel`` wird vor jedem Thema und vor jedem Fragen-/Antwortschritt gefragt; True
    beendet den Lauf mit ``status="cancelled"``. ``on_step(erledigt, gesamt)`` meldet die
    Themenzahl für Fortschrittsbalken.

    Rückgabe ``{status, topics, topics_done, topics_empty, questions, cards_new, answers,
    rejected, duplicates, problems_new, problems_failed, error_msg}``; ``status``:
    ok | cancelled | no_model | vram | empty."""
    from ragapp.config import settings
    from ragapp.llm import VramLowError, llm_task

    total = {"status": "ok", "topics": len(sections), "topics_done": 0, "topics_empty": 0,
             "questions": 0, "cards_new": 0, "answers": 0, "rejected": 0, "duplicates": 0,
             "problems_new": 0, "problems_failed": 0, "error_msg": None}
    if not sections:
        total["status"] = "empty"
        return total

    def _stop() -> bool:
        return bool(should_cancel and should_cancel())

    def _say(i: int, title: str, msg: str) -> None:
        if progress:
            progress(f"Thema {i}/{len(sections)} · {title[:46]} – {msg}")

    try:
        with llm_task(settings.LLM_MODEL_FAST):
            for i, sec in enumerate(sections, 1):
                if _stop():
                    total["status"] = "cancelled"
                    return total
                if on_step:
                    on_step(i - 1, len(sections))
                title = sec.get("title") or "Thema"
                _say(i, title, "starte …")
                out = create_section_cards(
                    sec, n_per_chunk=n_per_chunk, max_chunks=max_chunks,
                    with_answers=with_answers, should_cancel=should_cancel,
                    progress=lambda m, i=i, title=title: _say(i, title, m))
                status = out.get("status")
                if status in ("no_model", "vram"):
                    total["status"] = status
                    total["error_msg"] = out.get("error_msg")
                    if total["topics_done"]:
                        total["error_msg"] = (
                            f"{total['topics_done']} Thema/Themen sind fertig. "
                            + (total["error_msg"] or ""))
                    return total
                if status == "empty" and not out.get("cards_total"):
                    total["topics_empty"] += 1
                    continue
                for k in ("questions", "cards_new", "answers", "rejected", "duplicates"):
                    total[k] += int(out.get(k) or 0)
                if status == "cancelled":
                    if out.get("questions") or out.get("cards_new") or out.get("answers"):
                        total["topics_done"] += 1
                    total["status"] = "cancelled"
                    return total
                total["topics_done"] += 1
                if with_practice and not _stop() and not section_problems(sec, subject):
                    _say(i, title, "Übungsaufgabe …")
                    try:
                        # Dasselbe Modell wie der aeussere llm_task - kein Modellwechsel mittendrin.
                        create_section_practice(sec, subject=subject, model=settings.LLM_MODEL_FAST)
                        total["problems_new"] += 1
                    except Exception as exc:  # noqa: BLE001 - Uebung scheitert, Karten bleiben
                        total["problems_failed"] += 1
                        total.setdefault("practice_error", str(exc))
            if on_step:
                on_step(len(sections), len(sections))
    except VramLowError as exc:
        total["status"] = "vram"
        total["error_msg"] = str(exc)
    return total


# --------------------------------------------------------------------------- #
# Lernstand und Wiederholen
# --------------------------------------------------------------------------- #
def learning_line(st: dict) -> str:
    """Lernstand eines Themas als Zeile: „🧠 5 von 12 sitzen · 3 fällig · 4 neu“. Leer, wenn es
    noch keine Karten gibt (dann sagt die Füllstand-Zeile „keine Karten“)."""
    cards = int(st.get("cards") or 0)
    if not cards:
        return ""
    if not st.get("reviewed"):
        return "🆕 noch nicht gelernt"
    parts = [f"🧠 {st.get('known', 0)} von {cards} sitzen"]
    if st.get("due"):
        parts.append(f"{st['due']} fällig")
    if st.get("new"):
        parts.append(f"{st['new']} neu")
    return " · ".join(parts)


def learning_bar_html(st: dict) -> str:
    """Schmaler Balken: grün = sitzt, gelb = fällig, grau = neu (leer ohne Karten)."""
    if not int(st.get("cards") or 0):
        return ""
    segs = "".join(
        f"<div style='flex:{n};background:{color}' title='{n} {label}'></div>"
        for n, color, label in ((st.get("known", 0), "#16a34a", "sitzen"),
                                (st.get("due", 0), "#f59e0b", "fällig"),
                                (st.get("new", 0), "rgba(148,163,184,.55)", "neu")) if n)
    return f"<div class='splan-statebar'>{segs}</div>"


def review_card_ids(section: dict, limit: int = 16) -> list[str]:
    """Nur die FÄLLIGEN Wiederholungen eines Themas (geübt und fällig), die ältesten zuerst.
    Neue Karten gehören nicht dazu - Wiederholen heißt: Gelerntes auffrischen."""
    now = time.time()
    due = [c for c in section_cards(section)
           if (c.get("reps") or 0) > 0 and (c.get("due") or 0) <= now]
    due.sort(key=lambda c: c.get("due") or 0)
    return [c["card_id"] for c in due][:max(1, int(limit))]


def started_sections(blocks: list[dict], sections: list[dict], stats: dict,
                     today_iso: str) -> list[dict]:
    """Die Themen, die schon dran waren oder angefangen sind: mit geübten Karten, mit einem
    Block bis heute (auch erledigt) oder als erledigt markiert. Späteren Themen, die noch
    nie angefasst wurden, wird hier nichts „vorgezogen“."""
    first_block: dict[str, str] = {}
    for b in blocks:
        sid, day = b.get("section_id"), b.get("planned_date")
        if sid and day and (sid not in first_block or day < first_block[sid]):
            first_block[sid] = day
    out = []
    for s in sections:
        sid = s["section_id"]
        if ((stats.get(sid) or {}).get("reviewed", 0) > 0 or s.get("done")
                or (sid in first_block and first_block[sid] <= today_iso)):
            out.append(s)
    return out


def review_card_ids_for(sections: list[dict], stats: dict, *, per_topic: int = 8,
                        total: int = 30) -> list[str]:
    """Fällige Karten aus mehreren (bisherigen) Themen: je Thema höchstens ``per_topic``,
    insgesamt ``total``; Themen ohne fällige Karten werden gar nicht erst abgefragt."""
    ids: list[str] = []
    seen: set[str] = set()
    for sec in sections:
        if not (stats.get(sec["section_id"]) or {}).get("due"):
            continue
        for cid in review_card_ids(sec, limit=per_topic):
            if cid not in seen:
                seen.add(cid)
                ids.append(cid)
    return ids[:max(1, int(total))]


# --------------------------------------------------------------------------- #
# Termine je Thema
# --------------------------------------------------------------------------- #
_WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


def _day(iso: Optional[str]) -> Optional[date]:
    try:
        return datetime.strptime((iso or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def fmt_day(iso: Optional[str]) -> str:
    """„2026-10-08“ -> „Do 08.10.“ (leer bei ungültigem Datum)."""
    d = _day(iso)
    return f"{_WEEKDAYS[d.weekday()]} {d.day:02d}.{d.month:02d}." if d else ""


def day_phrase(iso: Optional[str], today_iso: str) -> str:
    """„heute“, „morgen“, „in 3 Tagen“, „gestern“, „vor 2 Tagen“."""
    d, t = _day(iso), _day(today_iso)
    if d is None or t is None:
        return ""
    n = (d - t).days
    if n == 0:
        return "heute"
    if n == 1:
        return "morgen"
    if n == -1:
        return "gestern"
    return f"in {n} Tagen" if n > 0 else f"vor {-n} Tagen"


def section_schedule(blocks: list[dict]) -> dict[str, dict]:
    """Termine je Thema aus den Plan-Blöcken: ``{section_id: {total, done, open_first, open_last,
    first, last}}`` (Daten als ISO-Text; ``open_*`` nur über noch offene Blöcke)."""
    out: dict[str, dict] = {}
    for b in blocks:
        sid, day = b.get("section_id"), b.get("planned_date")
        if not sid or not day:
            continue
        e = out.setdefault(sid, {"total": 0, "done": 0, "open_first": None, "open_last": None,
                                 "first": day, "last": day})
        e["total"] += 1
        e["first"], e["last"] = min(e["first"], day), max(e["last"], day)
        if b.get("done"):
            e["done"] += 1
        else:
            e["open_first"] = day if e["open_first"] is None else min(e["open_first"], day)
            e["open_last"] = day if e["open_last"] is None else max(e["open_last"], day)
    return out


def schedule_label(sched: Optional[dict], today_iso: str) -> tuple[str, str]:
    """``(Art, Text)`` für die Kachel: Art ∈ none | done | overdue | today | later. „kommt
    später“ markiert Themen, die erst nach heute dran sind."""
    if not sched:
        return "none", "🗓️ noch nicht eingeplant"
    first = sched.get("open_first")
    if first is None:
        return "done", "✅ erledigt"
    if first < today_iso:
        return "overdue", f"⚠️ überfällig seit {fmt_day(first)}"
    last = sched.get("open_last") or first
    if first == today_iso:
        more = f" · bis {fmt_day(last)}" if last > today_iso else ""
        return "today", f"📅 heute{more}"
    return "later", f"🗓️ kommt später · ab {fmt_day(first)} ({day_phrase(first, today_iso)})"


# --------------------------------------------------------------------------- #
# Kartenqualität prüfen und beheben
# --------------------------------------------------------------------------- #
def plan_audit(plan: dict, sections: list[dict], *,
               embed: Optional[Callable[[list[str]], list[list[float]]]] = None) -> dict[str, dict]:
    """Prüft die KI-Karten aller Themen eines Plans (``card_quality.audit_cards``). Mit ``embed``
    zusätzlich Dubletten über den ganzen Plan hinweg. Ergebnis nur für auffällige Karten:
    ``{card_id: {question, answer, section_id}}``."""
    by_section = _cards_by_section(plan, sections)
    owner: dict[str, str] = {}
    cards: list[dict] = []
    for sid, cs in by_section.items():
        for c in cs:
            if c["card_id"] not in owner:
                owner[c["card_id"]] = sid
                cards.append(c)
    audit = card_quality.audit_cards(cards, embed=embed)
    return {cid: {**entry, "section_id": owner[cid]} for cid, entry in audit.items()}


def split_repairs(cards: list[dict], audit: dict) -> dict[str, list[str]]:
    """Was mit den auffälligen Karten geschehen darf. NIE angefasst werden Karten, die schon
    gelernt (``reps > 0``) oder von Hand bearbeitet wurden, sobald die FRAGE den Mangel hat:
    ``protected``. Mangel in der Frage einer unberührten Karte: ``replace`` (löschen, die Lücke
    wird neu gefüllt). Mangel nur in der Antwort: ``answers`` (Antwort neu erzeugen, Frage bleibt)."""
    by_id = {c["card_id"]: c for c in cards}
    replace: list[str] = []
    answers: list[str] = []
    protected: list[str] = []
    for cid, entry in audit.items():
        c = by_id.get(cid)
        if c is None or c.get("source") != "question":
            continue
        edited = bool(c.get("edited"))
        if entry.get("question"):
            (protected if edited or (c.get("reps") or 0) > 0 else replace).append(cid)
        elif entry.get("answer"):
            (protected if edited else answers).append(cid)
    return {"replace": replace, "answers": answers, "protected": protected}


def repair_cards(cards: list[dict], audit: dict, *,
                 progress: Optional[Callable[[str], None]] = None,
                 should_cancel: Optional[Callable[[], bool]] = None) -> dict:
    """Behebt die Mängel aus ``plan_audit`` (siehe ``split_repairs``):

    * Mangel in der Frage, Karte unberührt -> Karte samt Frage im Index löschen (vorher legt
      ``manifest.delete_card_ids`` eine Sicherung an). Der Textabschnitt hat danach keine Frage
      mehr und bekommt beim nächsten Füllen eine neue (mit Qualitätsfilter).
    * Mangel nur in der Antwort -> Antwort neu erzeugen. Gelingt das nicht (Modell/VRAM), wird die
      alte Antwort WIEDERHERGESTELLT: nach einer Reparatur ist nie etwas schlechter als vorher.

    Rückgabe ``{deleted, answers_new, answers_kept_old, protected, protected_ids, replaced_ids,
    answer_ids, status, error_msg}``; ``status``: ok | cancelled | no_model | vram."""
    plan = split_repairs(cards, audit)
    out = {"deleted": 0, "answers_new": 0, "answers_kept_old": 0,
           "protected": len(plan["protected"]), "protected_ids": plan["protected"],
           "replaced_ids": list(plan["replace"]), "answer_ids": list(plan["answers"]),
           "status": "ok", "error_msg": None}
    if plan["replace"]:
        if progress:
            progress(f"{len(plan['replace'])} fehlerhafte Karte(n) entfernen …")
        chroma_ids = manifest.delete_card_ids(plan["replace"])
        if chroma_ids:
            try:
                from ragapp.retrieval.vectorstore import get_vectorstore
                get_vectorstore().delete_by_ids(chroma_ids)
            except Exception as exc:  # noqa: BLE001 - Karte ist weg; Frage bleibt im Index (harmlos)
                out["error_msg"] = f"Fragen im Index nicht entfernt: {exc}"
        out["deleted"] = len(plan["replace"])
    if plan["answers"] and not (should_cancel and should_cancel()):
        from ragapp import study
        old = {c["card_id"]: (c.get("answer") or "") for c in cards if c["card_id"] in plan["answers"]}
        for cid in old:
            manifest.set_answer(cid, "")
        res = study.generate_answers(card_ids=list(old), progress=progress, should_cancel=should_cancel)
        now_answered = {c["card_id"] for c in manifest.get_cards_by_ids(list(old))
                        if (c.get("answer") or "").strip()}
        for cid, text in old.items():
            if cid not in now_answered:
                manifest.set_answer(cid, text)          # nicht schlechter machen als vorher
                out["answers_kept_old"] += 1
        out["answers_new"] = len(now_answered)
        if res.get("status") == "cancelled":
            out["status"] = "cancelled"
        elif res.get("status") == "llm_error":
            low = (res.get("error_msg") or "").lower()
            out["status"] = "vram" if ("vram" in low or "grafikspeicher" in low) else "no_model"
            out["error_msg"] = res.get("error_msg")
    return out


def summarize_repair(rep: dict) -> str:
    bits = []
    if rep.get("deleted"):
        bits.append(f"{rep['deleted']} fehlerhafte Karte(n) entfernt und neu erzeugt")
    if rep.get("answers_new"):
        bits.append(f"{rep['answers_new']} Antwort(en) neu formuliert")
    if rep.get("answers_kept_old"):
        bits.append(f"{rep['answers_kept_old']} Antwort(en) blieben unverändert (Neuerzeugung scheiterte)")
    if rep.get("protected"):
        bits.append(f"{rep['protected']} auffällige Karte(n) bleiben, weil du sie schon gelernt "
                    "oder bearbeitet hast")
    return ("🧹 " + "; ".join(bits) + ".") if bits else ""


def repair_and_fill(plan: dict, sections: list[dict], *, subject: Optional[str],
                    progress: Optional[Callable[[str], None]] = None,
                    should_cancel: Optional[Callable[[], bool]] = None,
                    on_step: Optional[Callable[[int, int], None]] = None,
                    embed: Optional[Callable[[list[str]], list[list[float]]]] = None) -> dict:
    """„Mängel beheben“ in einem Lauf: prüfen (inkl. Dubletten), reparieren, danach die Lücken
    füllen, die dabei entstanden sind - und NUR diese: Themen, in denen nichts gelöscht wurde,
    bleiben unberührt (auch wenn sie noch leer sind; dafür gibt es „Alle Themen füllen“).
    Übungsaufgaben gehören nicht dazu. Rückgabe wie ``fill_plan_cards`` plus ``repair``."""
    from ragapp.config import settings
    from ragapp.llm import VramLowError, llm_task

    def _empty(**extra) -> dict:
        base = fill_plan_cards([], subject=subject)
        base.update(extra)
        return base

    try:
        with llm_task(settings.LLM_MODEL_FAST):
            if progress:
                progress("Prüfe die Karten …")
            audit = plan_audit(plan, sections, embed=embed)
            cards = [c for cs in _cards_by_section(plan, sections).values() for c in cs]
            rep = repair_cards(cards, audit, progress=progress, should_cancel=should_cancel)
            if rep["status"] in ("vram", "no_model", "cancelled"):
                return _empty(status=rep["status"], error_msg=rep.get("error_msg"), repair=rep)
            touched = {audit[cid]["section_id"] for cid in rep["replaced_ids"] + rep["answer_ids"]
                       if cid in audit}
            stats = plan_unit_stats(plan, sections)
            todo = sections_needing_cards(
                stats, [s for s in sections if s["section_id"] in touched], with_practice=False)
            if todo:
                out = fill_plan_cards(todo, with_practice=False, subject=subject, progress=progress,
                                      should_cancel=should_cancel, on_step=on_step)
            else:
                out = _empty(status="ok")
            out["repair"] = rep
            return out
    except VramLowError as exc:
        return _empty(status="vram", error_msg=str(exc))


# --------------------------------------------------------------------------- #
# Hintergrundaufträge
# --------------------------------------------------------------------------- #
def job_key(plan_id: str) -> str:
    return f"plan:{plan_id}:units"


def start_fill_job(plan: dict, sections: list[dict], *, with_practice: bool, title: str,
                   repair: bool = False):
    """Startet das Füllen (bzw. Reparieren + Füllen) im Hintergrund. Es läuft höchstens ein Lauf
    je Plan. Rückgabe ``(Job, neu_gestartet)`` (siehe ``ragapp.jobs.start``)."""
    from ragapp import jobs
    secs = [dict(s) for s in sections]          # Momentaufnahme - die Seite baut sich währenddessen neu auf
    plan_snapshot = dict(plan)
    subject = plan.get("subject")

    def work(ctx):
        kw = dict(subject=subject, progress=ctx.progress, should_cancel=ctx.cancelled,
                  on_step=ctx.steps)
        if repair:
            from ragapp.retrieval.embeddings import get_embedder
            return repair_and_fill(plan_snapshot, secs, embed=get_embedder().embed_texts, **kw)
        return fill_plan_cards(secs, with_practice=with_practice, **kw)

    return jobs.start(job_key(plan["plan_id"]), title, work)


def summarize_job(job) -> tuple[str, str]:
    """``(Stufe, Text)`` zu einem beendeten Auftrag (success | info | error)."""
    from ragapp import jobs
    if job.status == jobs.ERROR:
        return "error", f"Der Lauf ist mit einem Fehler beendet worden: {job.error}"
    out = job.result or {}
    if job.status == jobs.CANCELLED and not out:
        return "info", "⏹ Abgebrochen. Ein erneuter Klick macht dort weiter, wo es aufgehört hat."
    if job.status == jobs.CANCELLED:
        out = {**out, "status": "cancelled"}
    return summarize_fill(out)


# --------------------------------------------------------------------------- #
# Schrittleiste: wo steht der Plan, was ist als Nächstes zu tun?
# --------------------------------------------------------------------------- #
def plan_steps(sections: list[dict], stats: dict, stale: dict, blocks: list[dict],
               today_iso: str) -> list[dict]:
    """Die vier Schritte eines Plans mit Zustand für die Schrittleiste:
    ``[{n, title, sub, state, next}]``, ``state`` ∈ done | todo | warn. Genau ein Schritt trägt
    ``next=True``: der erste, der noch nicht erledigt ist.

    1 Gliederung · 2 Einheiten (Karten + Übungen) · 3 Zeitplan · 4 Lernen. ``stale`` kommt aus
    ``study_plan.plan_staleness``."""
    n = len(sections)
    mixed = sum(1 for s in sections if len(section_docs(s)) > 1)
    if not n:
        s1 = ("todo", "noch keine Themen")
    elif mixed:
        s1 = ("warn", f"{n} Themen · {mixed} aus mehreren Dokumenten")
    else:
        s1 = ("done", f"{n} Themen")

    todo_units = sections_needing_cards(stats, sections, with_practice=True)
    complete = n - len(todo_units)
    cards = sum((stats.get(s["section_id"]) or {}).get("cards", 0) for s in sections)
    if not n:
        s2 = ("todo", "wartet auf die Gliederung")
    elif not todo_units:
        s2 = ("done", f"alle {n} Themen komplett · {cards} Karten")
    else:
        s2 = ("todo", f"{complete} von {n} Themen komplett · {cards} Karten")

    open_blocks = [b for b in blocks if not b.get("done")]
    state = stale.get("state")
    if not n:
        s3 = ("todo", "wartet auf die Gliederung")
    elif state == "missing":
        s3 = ("todo", "noch nicht berechnet")
    elif state == "stale":
        s3 = ("warn", "veraltet – neu berechnen")
    elif open_blocks:
        last = max(b["planned_date"] for b in open_blocks)
        s3 = ("done", f"{len(open_blocks)} offene Blöcke · bis {fmt_day(last)}")
    else:
        s3 = ("done", "aktuell")

    if not blocks:
        s4 = ("todo", "erst nach dem Zeitplan")
    elif not open_blocks:
        s4 = ("done", "alles erledigt 🎉")
    else:
        day = next_study_day(blocks, today_iso)
        if day is None:
            overdue = min(b["planned_date"] for b in open_blocks)
            s4 = ("todo", f"offen seit {fmt_day(overdue)}")
        elif day == today_iso:
            todays = sections_for_day(blocks, sections, day)
            minutes = sum(int(b.get("planned_min") or 0) for b in open_blocks
                          if b.get("planned_date") == day)
            s4 = ("todo", f"heute: {len(todays)} Thema/Themen · {minutes} Min")
        else:
            s4 = ("todo", f"nächster Lerntag: {fmt_day(day)}")

    steps = [{"n": i, "title": t, "state": st, "sub": sub, "next": False}
             for i, (t, (st, sub)) in enumerate(
                 zip(("Gliederung", "Einheiten", "Zeitplan", "Lernen"), (s1, s2, s3, s4)), 1)]
    for step in steps:
        if step["state"] != "done":
            step["next"] = True
            break
    return steps
