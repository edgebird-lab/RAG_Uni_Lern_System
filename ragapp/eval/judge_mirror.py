"""
Altklausur-Spiegel-Items fuer die Judge-Kalibrierung (F3)
=========================================================
Der Judge-Harness (``judge_harness.run_judge_harness``) misst, wie gut die
KI-Benotung kalibriert ist - gegen einen von Hand gelabelten Satz plus die
Beispiele aus ``data/eval/judge_labels.json``. Der eingebaute Satz ist
fachneutral; je mehr Beispiele aus dem EIGENEN Stoff, desto belastbarer die
Kalibrierung.

Dieses Modul erzeugt solche Beispiele automatisch aus den Karteikarten des
Nutzers ("spiegelt" die Altklausur-Fragen): Es nimmt bis zu ``n`` Karten eines
Fachs, deren Musterantwort (``answer``) als Referenz dient, und laesst das LLM
je Karte

  * drei realistische Studenten-Antworten (``gewusst`` / ``halb`` / ``nicht``)
    -> Kalibrierung der BENOTUNG, sowie
  * zwei Antworten fuers Grounding-Gate (eine durch die Musterloesung GEDECKTE
    und eine mit erfundener Behauptung) -> Kalibrierung von GROUNDING /
    FAITHFULNESS.

So waechst nicht nur die Benotungs-, sondern auch die Grounding-Kalibrierbasis
mit dem eigenen Stoff (statt dauerhaft nur gegen die Handbeispiele zu messen).
Beide Sorten werden ADDITIV und DEDUPLIZIERT nach ``data/eval/judge_labels.json``
gemergt (Format identisch zu ``judge_harness._load_extra_labels``), sodass der
naechste Judge-Test sie automatisch mitnutzt. Bestehende Eintraege bleiben
erhalten.
"""
from __future__ import annotations

import json
import re

from ragapp.config import EVAL_DIR, settings
from ragapp.llm import get_llm
from ragapp import manifest

# Muss zu judge_harness._LABEL2RATING passen (nicht=0, halb=1, gewusst=2).
_LABELS = ("gewusst", "halb", "nicht")

_MIRROR_SYSTEM = ("Du bist Tutor an einer deutschen Hochschule und kennst die "
                  "typischen Antworten von Studierenden - von der perfekten "
                  "Musterantwort bis zum blossen Raten.")

_MIRROR_PROMPT = """Zu einer Pruefungsfrage und ihrer Musterloesung sollst du DREI
realistische Antworten von Studierenden erfinden - je eine pro Qualitaetsstufe.
Sie dienen als Kalibrier-Beispiele fuer einen KI-Korrektor, die Stufen muessen
daher klar unterscheidbar sein:

- "gewusst": inhaltlich korrekt UND vollstaendig, aber in EIGENEN Worten
  (die Musterloesung NICHT woertlich abschreiben).
- "halb": nur teilweise richtig - ein zentraler Punkt fehlt, ist ungenau oder vage
  (z. B. "irgendwas mit ...", nur die Haelfte genannt). Nicht komplett falsch.
- "nicht": falsch, verwechselt oder ohne Substanz ("keine Ahnung", ein Ratewort,
  eine voellig andere Sache).

Halte jede Antwort kurz (1-2 Saetze), so wie ein Studierender sie unter Zeitdruck
in der Klausur tippen wuerde.

Erzeuge ausserdem ZWEI Antworten fuer die Pruefung, ob eine Aussage durch die
Musterloesung GEDECKT ist (Grounding-Gate) - beide 1-2 Saetze:

- "beleg_treu": inhaltlich korrekt UND ausschliesslich mit Informationen aus der
  Musterloesung (nichts hinzuerfinden, keine neue Zahl/Name/Jahr).
- "beleg_erfunden": klingt plausibel, enthaelt aber mindestens EINE konkrete
  Behauptung (Zahl, Name, Jahr, Zusatzfakt), die in der Musterloesung NICHT
  vorkommt oder ihr widerspricht.

Frage:
{frage}

Musterloesung:
{referenz}

Gib NUR gueltiges JSON in diesem Format zurueck:
{{"gewusst": "...", "halb": "...", "nicht": "...", "beleg_treu": "...", "beleg_erfunden": "..."}}"""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _dedup_key(item: dict) -> tuple:
    """Identitaet eines Benotungs-Beispiels (Frage + Antwort + Label, normalisiert)."""
    return (_norm(item.get("frage")), _norm(item.get("antwort")), _norm(item.get("label")))


def _dedup_key_grounding(item: dict) -> tuple:
    """Identitaet eines Grounding-Beispiels (Frage + Antwort + grounded-Flag)."""
    return (_norm(item.get("frage")), _norm(item.get("antwort")),
            bool(item.get("grounded")))


def _merge_additive(existing: list[dict], new_items: list[dict], key_fn) -> tuple[list, int]:
    """Haengt ``new_items`` dedupliziert (per ``key_fn``) an ``existing`` an.
    Gibt (zusammengefuehrte_liste, neu_hinzugefuegt) zurueck."""
    seen = {key_fn(it) for it in existing}
    added = 0
    for it in new_items:
        k = key_fn(it)
        if k in seen:
            continue
        seen.add(k)
        existing.append(it)
        added += 1
    return existing, added


def _merge_labels(new_grading: list[dict], new_grounding: list[dict]) -> dict:
    """Mergt neue Benotungs- UND Grounding-Beispiele additiv & dedupliziert in
    judge_labels.json. Bestehende Eintraege beider Sorten bleiben erhalten. Gibt
    ``{grading_added, grading_total, grounding_added, grounding_total}`` zurueck."""
    path = EVAL_DIR / "judge_labels.json"
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text("utf-8"))
        except Exception:  # noqa: BLE001
            data = {}
    if not isinstance(data, dict):
        data = {}

    grading = [it for it in (data.get("grading") or []) if isinstance(it, dict)]
    grading, added_g = _merge_additive(grading, new_grading, _dedup_key)

    grounding = [it for it in (data.get("grounding") or []) if isinstance(it, dict)]
    grounding, added_r = _merge_additive(grounding, new_grounding, _dedup_key_grounding)

    data["grading"] = grading
    data["grounding"] = grounding
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
    return {"grading_added": added_g, "grading_total": len(grading),
            "grounding_added": added_r, "grounding_total": len(grounding)}


def generate_mirror_items(subject: str, n: int = 6, progress=None) -> dict:
    """Erzeugt aus bis zu ``n`` Karten eines Fachs (mit Musterantwort) je drei
    Beispiel-Studentenantworten (gewusst/halb/nicht) und mergt sie dedupliziert
    nach data/eval/judge_labels.json. Gibt eine Ergebnis-Zusammenfassung zurueck.

    Fehler pro Karte werden abgefangen (eine kaputte LLM-Antwort stoppt den Lauf
    nicht). ``progress(msg)`` wird - wie im uebrigen Code - je Karte aufgerufen."""
    # 1) Karten mit brauchbarer Referenz (Musterantwort) waehlen.
    cards = [c for c in manifest.list_cards(subject=subject)
             if (c.get("answer") or "").strip() and (c.get("front") or "").strip()]
    path = str(EVAL_DIR / "judge_labels.json")
    if not cards:
        return {"status": "no_cards", "subject": subject, "cards": 0,
                "generated": 0, "merged": 0, "path": path}
    cards = cards[:max(1, int(n))]

    llm = get_llm(settings.LLM_MODEL_FAST)
    new_grading: list[dict] = []
    new_grounding: list[dict] = []
    for i, c in enumerate(cards, 1):
        if progress:
            progress(f"Spiegel-Antworten {i}/{len(cards)} …")
        frage = (c.get("front") or "").strip()
        referenz = (c.get("answer") or "").strip()
        prompt = _MIRROR_PROMPT.format(frage=frage[:600], referenz=referenz[:1500])
        data = None
        # Bei leerem/trunkiertem JSON (Reasoning-Modelle) einmal mit mehr Budget erneut.
        for np in (settings.LLM_NUM_PREDICT, 2048):
            try:
                data = llm.generate_json(prompt, system=_MIRROR_SYSTEM,
                                         temperature=0.7, num_predict=np)
            except Exception:  # noqa: BLE001
                data = None
            if isinstance(data, dict) and any(str(data.get(l) or "").strip() for l in _LABELS):
                break
        if not isinstance(data, dict):
            continue
        # Benotungs-Spiegel (gewusst/halb/nicht).
        for label in _LABELS:
            ant = str(data.get(label) or "").strip()
            if ant:
                new_grading.append({"frage": frage, "referenz": referenz,
                                    "antwort": ant, "label": label})
        # Grounding-Spiegel: Musterloesung als Beleg, belegte vs. erfundene Antwort.
        treu = str(data.get("beleg_treu") or "").strip()
        erfunden = str(data.get("beleg_erfunden") or "").strip()
        if treu:
            new_grounding.append({"frage": frage, "antwort": treu,
                                  "beleg": referenz, "grounded": True})
        if erfunden:
            new_grounding.append({"frage": frage, "antwort": erfunden,
                                  "beleg": referenz, "grounded": False})

    counts = _merge_labels(new_grading, new_grounding)
    return {"status": "ok", "subject": subject, "cards": len(cards),
            "generated": counts["grading_added"], "merged": counts["grading_total"],
            "grounding_generated": counts["grounding_added"],
            "grounding_merged": counts["grounding_total"], "path": path}
