"""
Lernplan: KI-Gliederung + realistischer, tagesverteilter Zeitplan
====================================================================
Erzeugt aus den bereits indexierten Abschnitten gewaehlter Dokumente eine
KI-Gliederung (grosses Autoren-Modell, wie bei der Zusammenfassung) und rechnet
daraus einen auf Tage verteilten Lernplan in Pomodoro-grossen Bloecken. Alle
Zeitschaetzungen sind Formel-basiert aus der echten Zeichenzahl (KEIN LLM-Raten) -
Herleitung + Quellen: docs/LERNPLAN_FORSCHUNG.md.

Design-Prinzip (wie beim Chat): lieber ehrlich einen Fehlbetrag melden, als einen
Wunschplan zu erfinden, der nicht in die verfuegbare Zeit passt.
"""
from __future__ import annotations

import math
import time
from datetime import date, timedelta
from typing import Optional

from ragapp.config import settings
from ragapp.llm import get_llm
from ragapp import manifest
from ragapp.retrieval.vectorstore import get_vectorstore
from ragapp.ingestion.summarize import _sections_from_chunks


class OutlineError(RuntimeError):
    """Echter Fehler bei der Gliederungs-Erzeugung (kein Modell, keine Abschnitte)."""


_OUTLINE_SYSTEM = (
    "Du bist ein erfahrener Lern-Coach und erstellst sinnvolle Lern-Gliederungen "
    "aus dem Inhaltsverzeichnis einer Quelle. Du erfindest keine Inhalte, sondern "
    "ordnest und benennst nur, was im Inhaltsverzeichnis bereits steht."
)

_OUTLINE_PROMPT = """Das ist das Inhaltsverzeichnis einer Lernquelle (Fach: {fach}) mit
{n} Original-Abschnitten. Jede Zeile: Nummer, Titel, ungefaehre Zeichenzahl.

{toc}

Fasse das zu HOECHSTENS {max_sections} sinnvollen LERN-Themen zusammen (verwandte
oder kleine Abschnitte zusammenlegen), in guter Lernreihenfolge (meist die
Dokument-Reihenfolge, Grundlagen vor Aufbauendem). Antworte NUR als JSON-Liste:
[{{"title": "kurzer Themen-Titel", "summary": "1 Satz, worum es geht", "indices": [0,2,3]}}, ...]
Jede Original-Nummer (0 bis {max_idx}) sollte in einem Thema in "indices" vorkommen."""


def _author_model() -> str:
    return settings.author_model()


def _merge_tiny_sections(
    sections: list[tuple[str, str, str]],
) -> list[tuple[str, str, str]]:
    """Legt aufeinanderfolgende SEHR KURZE Original-Abschnitte (< PLAN_MIN_GRANULAR_
    CHARS) innerhalb desselben Dokuments zusammen, bevor sie der KI vorgelegt
    werden. Ohne das erzeugt ein Dokument mit vielen kleinen Chunks eine unnoetig
    feinteilige Gliederung (Uebersegmentierung) UND einen laengeren, langsameren
    Prompt - beides unerwuenscht."""
    min_chars = max(0, int(settings.PLAN_MIN_GRANULAR_CHARS))
    if min_chars <= 0:
        return sections
    merged: list[list] = []   # je Eintrag: [quelle, [titel, ...], text]
    for label, title, body in sections:
        if merged and merged[-1][0] == label and len(merged[-1][2]) < min_chars:
            merged[-1][1].append(title)
            merged[-1][2] += "\n\n" + body
        else:
            merged.append([label, [title], body])
    out: list[tuple[str, str, str]] = []
    for label, titles, body in merged:
        if len(titles) == 1:
            t = titles[0]
        elif len(titles) == 2:
            t = f"{titles[0]} / {titles[1]}"
        else:
            t = f"{titles[0]} … {titles[-1]}"
        out.append((label, t, body))
    return out


def _granular_sections(doc_ids: list[str]) -> list[tuple[str, str, str]]:
    """(Quelle, Titel, Text) je granularem Abschnitt ueber alle gewaehlten
    Dokumente - nutzt dieselbe Abschnittslogik wie die Zusammenfassung-Seite
    (``_sections_from_chunks``), holt ``get_all_chunks()`` aber NUR EINMAL (statt
    einmal pro Dokument wie ``summarize._source_chunks`` es einzeln taete) - bei
    mehreren gewaehlten Dokumenten spart das entsprechend viele Chroma-Abfragen.
    Sehr kurze Abschnitte werden vorab zusammengelegt (siehe ``_merge_tiny_sections``)."""
    all_chunks = get_vectorstore().get_all_chunks()
    out: list[tuple[str, str, str]] = []
    for doc_id in doc_ids:
        doc = manifest.get_document(doc_id)
        label = doc["filename"] if doc else doc_id
        chunks = sorted(
            (c for c in all_chunks if c["meta"].get("doc_id") == doc_id),
            key=lambda c: int(c["meta"].get("chunk_index", 0)))
        for title, body in _sections_from_chunks(chunks):
            out.append((label, title, body))
    return _merge_tiny_sections(out)


def _toc_text(granular: list[tuple[str, str, str]]) -> str:
    return "\n".join(f"{i}. {t} (~{len(b)} Zeichen)" for i, (_, t, b) in enumerate(granular))


def _disp_title(first: str, last: str) -> str:
    return first if first == last else f"{first} … {last}"


def _cap_granular_for_prompt(
    granular: list[tuple[str, str, str]], max_toc_chars: int,
) -> list[tuple[str, str, str]]:
    """Legt bei SEHR grossen Dokumenten (viele granulare Abschnitte) benachbarte
    Abschnitte DERSELBEN Quelle so lange paarweise zusammen, bis das Inhalts-
    verzeichnis sicher ins Kontextfenster passt. Ohne diese Bremse sieht das
    Modell bei "viel Text" nur einen mitten abgeschnittenen TOC-Rest und erfindet
    frei weiter (beobachtet: Marketing-PDF -> Gliederung ueber Deutsch-Grammatik) -
    das widerspricht dem Grundprinzip, nur zu ordnen statt zu erfinden.

    Intern (label, erster Titel, letzter Titel, Text): der ANGEZEIGTE Titel
    einer Merge-Gruppe bleibt so ueber beliebig viele Merge-Runden beschraenkt
    (nur "erster … letzter", wie bei ``_merge_tiny_sections``) - wuerde man bei
    jeder Runde die vollen Titel aneinanderhaengen, wuechse die TOC trotz
    sinkender Zeilenzahl kaum und der Zweck der Funktion waere verfehlt."""
    groups = [(label, title, title, body) for label, title, body in granular]

    def toc_len(gs: list[tuple[str, str, str, str]]) -> int:
        return sum(len(f"{i}. {_disp_title(f, l)} (~{len(b)} Zeichen)\n")
                   for i, (_, f, l, b) in enumerate(gs))

    while len(groups) > 1 and toc_len(groups) > max_toc_chars:
        merged: list[tuple[str, str, str, str]] = []
        i = 0
        while i < len(groups):
            if i + 1 < len(groups) and groups[i][0] == groups[i + 1][0]:
                label, first1, _, body1 = groups[i]
                _, _, last2, body2 = groups[i + 1]
                merged.append((label, first1, last2, body1 + "\n\n" + body2))
                i += 2
            else:
                merged.append(groups[i])
                i += 1
        if len(merged) == len(groups):     # keine gleichquelligen Nachbarn mehr -> Abbruch
            break
        groups = merged
    return [(label, _disp_title(first, last), body) for label, first, last, body in groups]


def estimate_outline_eta_seconds(doc_ids: list[str], model: Optional[str] = None) -> int:
    """Wartezeit-Schaetzung fuer die UI (VOR dem Klick). Selbstlernend: sobald
    genug ECHTE Messungen fuer das gewaehlte Modell vorliegen (siehe
    ``manifest.eta_calibration``), ersetzt deren Durchschnitt die statische
    PLAN_ETA_*-Formel aus config.py. Haengt stark von der Hardware ab, daher in
    der UI immer als Richtwert kommunizieren, nie als Zusage."""
    total_chars = 0
    for d in doc_ids:
        doc = manifest.get_document(d)
        if doc is not None:
            total_chars += doc["char_count"] or 0
    rate = manifest.eta_calibration(model or _author_model())
    if rate is not None:
        return round(settings.PLAN_ETA_BASE_SEC + total_chars / 1000.0 * rate)
    return round(settings.PLAN_ETA_BASE_SEC
                + total_chars / 1000.0 * settings.PLAN_ETA_SEC_PER_1000_CHARS)


def estimate_minutes(chars: int) -> int:
    """Formel-basierte Zeitschaetzung (Minuten) aus Zeichenzahl - siehe
    docs/LERNPLAN_FORSCHUNG.md fuer Herleitung + Quellen."""
    reading_min = chars / settings.PLAN_CHARS_PER_PAGE * (60.0 / settings.PLAN_PAGES_PER_HOUR)
    concepts = chars / settings.PLAN_CHARS_PER_CONCEPT
    practice_min = concepts * (60.0 / settings.PLAN_ITEMS_PER_HOUR)
    return max(5, round(reading_min + practice_min))


def _repair_outline(data: object, n: int) -> "list[dict] | None":
    """Reinigt die KI-Antwort statt sie bei kleinen Fehlern komplett zu verwerfen:
    Mehrfach zugeordnete Original-Indizes zaehlen nur beim ERSTEN Thema, nicht
    zugeordnete werden dem letzten Thema angehaengt (kein Inhalt geht beim
    Zeitbudget verloren). Gibt ``None`` zurueck, wenn die Antwort unbrauchbar ist
    (dann greift der 1:1-Fallback in ``generate_outline``)."""
    if not isinstance(data, list) or not data:
        return None
    used: set[int] = set()
    cleaned: list[dict] = []
    for item in data:
        if not isinstance(item, dict) or not str(item.get("title") or "").strip():
            continue
        idxs: list[int] = []
        # dict.fromkeys statt set(): dedupliziert Wiederholungen INNERHALB dieses
        # Items, behaelt aber die vom Modell gelieferte Reihenfolge.
        for i in dict.fromkeys(item.get("indices") or []):
            if isinstance(i, int) and 0 <= i < n and i not in used:
                idxs.append(i)
                used.add(i)   # sofort eintragen -> auch spaetere Items im selben
                              # Durchlauf sehen diesen Index schon als vergeben
        if not idxs:
            continue
        cleaned.append({"title": str(item["title"]).strip(),
                        "summary": str(item.get("summary") or "").strip(),
                        "indices": idxs})
    if not cleaned:
        return None
    missing = sorted(set(range(n)) - used)
    if missing:
        cleaned[-1]["indices"].extend(missing)
    return cleaned


def generate_outline(doc_ids: list[str], subject: Optional[str],
                     model: Optional[str] = None) -> list[dict]:
    """Erzeugt eine KI-Gliederung ueber die gewaehlten (bereits im RAG indexierten)
    Dokumente. Gibt eine Liste ``{title, summary, est_chars, est_minutes}`` in
    Lernreihenfolge zurueck. Wirft ``OutlineError``, wenn keine Abschnitte
    gefunden wurden oder das Modell gar nicht antwortet (Verbindung/Backend).

    ``model``: None -> grosses Autoren-Modell (gruendlicher, langsamer); explizit
    z. B. ``settings.LLM_MODEL_FAST`` uebergeben fuer eine schnellere, dafuer
    groebere Gliederung (Geschwindigkeit/Qualitaet-Abwaegung fuer die UI)."""
    granular = _granular_sections(doc_ids)
    if not granular:
        raise OutlineError(
            "Keine indexierten Abschnitte gefunden. Die gewaehlten Dokumente "
            "muessen im RAG sein (Seite Ingestion -> 'Im RAG'-Haekchen).")

    total_chars = sum(len(b) for _, _, b in granular)
    # Bei SEHR grossen/vielen Dokumenten benachbarte Abschnitte weiter zusammen-
    # legen, bis das Inhaltsverzeichnis sicher ins Kontextfenster passt - sonst
    # sieht das Modell nur einen abgeschnittenen Rest und erfindet frei (siehe
    # Docstring von ``_cap_granular_for_prompt``). ``total_chars`` bleibt am
    # UNGEKUERZTEN Original bemessen (echtes Zeichenvolumen fuer die ETA-Messung).
    capped = _cap_granular_for_prompt(granular, settings.PLAN_MAX_TOC_CHARS)

    max_sections = max(1, int(settings.PLAN_MAX_OUTLINE_SECTIONS))
    toc = _toc_text(capped)
    fach = subject or "unbekannt"
    used_model = model or _author_model()

    llm = get_llm(used_model)
    _t0 = time.monotonic()
    try:
        data = llm.generate_json(
            _OUTLINE_PROMPT.format(fach=fach, n=len(capped), toc=toc,
                                   max_sections=max_sections, max_idx=len(capped) - 1),
            system=_OUTLINE_SYSTEM, temperature=0.2)
    except Exception as exc:  # noqa: BLE001
        raise OutlineError(f"KI-Gliederung fehlgeschlagen: {exc}") from exc
    # Echte Dauer als Messwert sichern -> kalibriert die ETA-Schaetzung der
    # Oberflaeche selbstlernend nach (siehe estimate_outline_eta_seconds). Rein
    # additiv/optional: ein Fehler hier darf die Gliederung nicht kaputt machen.
    try:
        manifest.log_eta_sample(used_model, total_chars, time.monotonic() - _t0)
    except Exception:  # noqa: BLE001
        pass

    sections = _repair_outline(data, len(capped))
    if sections is None:
        # Nie ganz scheitern: granulare Abschnitte 1:1 als Gliederung uebernehmen.
        sections = [{"title": t, "summary": "", "indices": [i]}
                    for i, (_, t, _) in enumerate(capped)]

    out = []
    for s in sections:
        chars = sum(len(capped[i][2]) for i in s["indices"] if 0 <= i < len(capped))
        out.append({"title": s["title"], "summary": s.get("summary") or "",
                    "est_chars": chars, "est_minutes": estimate_minutes(chars)})
    return out


def parse_iso_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        y, m, d = (int(x) for x in s.split("-")[:3])
        return date(y, m, d)
    except Exception:  # noqa: BLE001
        return None


def build_schedule(sections: list[dict], daily_minutes: int,
                   deadline: Optional[str], start: Optional[date] = None) -> dict:
    """Verteilt die Abschnitte (mit ``section_id`` + ``est_minutes``) auf Tage in
    PLAN_BLOCK_MIN-Portionen (verteiltes statt massiertes Lernen). Das taegliche
    Zeitbudget wird auf PLAN_MAX_DAILY_FOCUS_MIN gedeckelt, selbst wenn der Nutzer
    mehr angibt (siehe docs/LERNPLAN_FORSCHUNG.md). Reicht ein gesetztes Zieldatum
    nicht, werden nur so viele Bloecke erzeugt, wie bis dahin passen - der Rest
    wird als ``shortfall_minutes`` ehrlich ausgewiesen statt stillschweigend
    ueber das Zieldatum hinausgeplant.

    Rueckgabe: {blocks, effective_daily_min, capped_daily, total_minutes,
    days_needed_total, shortfall_minutes, deadline_days}."""
    start = start or date.today()
    effective_daily = min(int(daily_minutes), settings.PLAN_MAX_DAILY_FOCUS_MIN)
    capped = effective_daily < int(daily_minutes)
    block_min = max(5, int(settings.PLAN_BLOCK_MIN))
    total_minutes = sum(int(s.get("est_minutes") or 0) for s in sections)

    deadline_date = parse_iso_date(deadline)
    deadline_days = None
    capacity_minutes = None
    if deadline_date:
        deadline_days = max(1, (deadline_date - start).days + 1)
        capacity_minutes = deadline_days * effective_daily

    shortfall_minutes = (0 if capacity_minutes is None
                         else max(0, total_minutes - capacity_minutes))
    budget_left = total_minutes if capacity_minutes is None else min(total_minutes, capacity_minutes)

    blocks: list[dict] = []
    cur_date = start
    remaining_today = effective_daily
    for s in sections:
        remaining_section = int(s.get("est_minutes") or 0)
        while remaining_section > 0 and budget_left > 0:
            if remaining_today <= 0:
                cur_date = cur_date + timedelta(days=1)
                remaining_today = effective_daily
            take = min(block_min, remaining_section, remaining_today, budget_left)
            blocks.append({"section_id": s.get("section_id"),
                           "planned_date": cur_date.isoformat(), "planned_min": take})
            remaining_section -= take
            remaining_today -= take
            budget_left -= take
        if budget_left <= 0:
            break

    days_needed_total = math.ceil(total_minutes / effective_daily) if effective_daily > 0 else 0
    return {
        "blocks": blocks, "effective_daily_min": effective_daily, "capped_daily": capped,
        "total_minutes": total_minutes, "days_needed_total": days_needed_total,
        "shortfall_minutes": shortfall_minutes, "deadline_days": deadline_days,
    }
