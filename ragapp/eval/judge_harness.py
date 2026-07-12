"""
Judge-Zuverlaessigkeit (Kalibrierung der KI-Benotung & des Grounding-Gates)
===========================================================================
Jede Funktion, deren KI-Urteil in die Lernplanung einfliesst (getippte Benotung,
Probeklausur, Qualitaetsgate), kann Lernen aktiv schaden, wenn das Urteil
fehlkalibriert ist. Dieser Harness misst das mit einem kleinen, VON HAND
gelabelten Satz:

  * Benotung: stimmt die vom LLM vorgeschlagene Note (gewusst/halb/nicht) mit dem
    menschlichen Label ueberein? (exakte + benachbarte Uebereinstimmung)
  * Grounding-Gate: erkennt es belegte vs. erfundene Antworten? (Genauigkeit,
    Praezision, Trefferquote)

Der eingebaute Satz ist fachunabhaengig und laeuft sofort (ohne Korpus). Erweiterbar
ueber data/eval/judge_labels.json (gleiches Format) - je mehr eigene Beispiele,
desto belastbarer die Kalibrierung.
"""
from __future__ import annotations

import json
from pathlib import Path

from ragapp.config import EVAL_DIR
from ragapp import grading
from ragapp.eval import metrics

# Bewertungen
_NICHT, _HALB, _GEWUSST = 0, 1, 2
_LABEL2RATING = {"nicht": _NICHT, "halb": _HALB, "gewusst": _GEWUSST}

# Menschenlesbare Richtung der Fehlkalibrierung (siehe metrics.grading_calibration).
_BIAS_TEXT = {
    "milde": "systematisch zu milde",
    "streng": "systematisch zu streng",
    "ausgeglichen": "ausgeglichen",
}

# --------------------------------------------------------------------------- #
# Eingebauter, von Hand gelabelter Satz (Benotung)
# --------------------------------------------------------------------------- #
GRADING_LABELS = [
    {"frage": "Was ist der Deckungsbeitrag?",
     "referenz": "Der Deckungsbeitrag ist die Differenz zwischen Erlös und variablen Kosten.",
     "antwort": "Erlös minus variable Kosten.", "label": "gewusst"},
    {"frage": "Was ist der Deckungsbeitrag?",
     "referenz": "Der Deckungsbeitrag ist die Differenz zwischen Erlös und variablen Kosten.",
     "antwort": "Das ist einfach der Gewinn des Unternehmens.", "label": "nicht"},
    {"frage": "Was ist der Deckungsbeitrag?",
     "referenz": "Der Deckungsbeitrag ist die Differenz zwischen Erlös und variablen Kosten.",
     "antwort": "Irgendwas mit Kosten und Erlös, genau weiß ich es nicht.", "label": "halb"},
    {"frage": "Nenne die 4 P's im Marketing-Mix.",
     "referenz": "Product, Price, Place, Promotion.",
     "antwort": "Product, Price, Place und Promotion.", "label": "gewusst"},
    {"frage": "Nenne die 4 P's im Marketing-Mix.",
     "referenz": "Product, Price, Place, Promotion.",
     "antwort": "Product und Price.", "label": "halb"},
    {"frage": "Nenne die 4 P's im Marketing-Mix.",
     "referenz": "Product, Price, Place, Promotion.",
     "antwort": "Keine Ahnung.", "label": "nicht"},
    {"frage": "Was misst die Standardabweichung?",
     "referenz": "Die Streuung der Daten um ihren Mittelwert.",
     "antwort": "Wie stark die Werte im Schnitt vom Mittelwert abweichen.", "label": "gewusst"},
    {"frage": "Was misst die Standardabweichung?",
     "referenz": "Die Streuung der Daten um ihren Mittelwert.",
     "antwort": "Den Durchschnitt aller Datenpunkte.", "label": "nicht"},
]

# Grounding-Gate: (frage, antwort, beleg, grounded=erwartet)
GROUNDING_LABELS = [
    {"frage": "Was ist X?", "antwort": "X ist die Summe von A und B.",
     "beleg": "X bezeichnet die Summe der Komponenten A und B im System.", "grounded": True},
    {"frage": "Was ist X?", "antwort": "X wurde 1975 von Herrn Mustermann in Paris erfunden.",
     "beleg": "X bezeichnet die Summe der Komponenten A und B im System.", "grounded": False},
    {"frage": "Wie hoch ist der Zinssatz?", "antwort": "Der Zinssatz beträgt 3 %.",
     "beleg": "Der jährliche Zinssatz liegt bei 3 Prozent.", "grounded": True},
    {"frage": "Wie hoch ist der Zinssatz?", "antwort": "Der Zinssatz beträgt 7 % und steigt jährlich.",
     "beleg": "Der jährliche Zinssatz liegt bei 3 Prozent.", "grounded": False},
]


def _load_extra_labels() -> dict:
    path = EVAL_DIR / "judge_labels.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def run_judge_harness(progress=None) -> dict:
    """Misst die Kalibrierung von Benotung und Grounding-Gate gegen den gelabelten
    Satz. Gibt aggregierte Metriken + Detailzeilen zurueck."""
    extra = _load_extra_labels()
    grad = GRADING_LABELS + list(extra.get("grading", []))
    grnd = GROUNDING_LABELS + list(extra.get("grounding", []))

    # ---- Benotung ---- #
    g_rows, exact, adjacent = [], 0, 0
    g_preds: list = []          # fuer die Richtung der Fehlkalibrierung (Bias)
    g_truths: list = []
    for i, ex in enumerate(grad, 1):
        if progress:
            progress(f"Benotung {i}/{len(grad)} …")
        res = grading.grade_typed_answer(ex["frage"], ex["referenz"], ex["antwort"])
        pred = res.get("suggested_rating")
        truth = _LABEL2RATING.get(ex["label"], _HALB)
        g_preds.append(pred)
        g_truths.append(truth)
        if pred == truth:
            exact += 1
        if pred is not None and abs(pred - truth) <= 1:
            adjacent += 1
        # diff > 0 = Judge zu milde, < 0 = zu streng (None = kein Urteil)
        g_rows.append({"frage": ex["frage"][:40], "erwartet": ex["label"],
                       "score": res.get("score"), "vorschlag": pred,
                       "diff": (pred - truth) if pred is not None else None,
                       "treffer": pred == truth})
    n_g = len(grad)
    calib = metrics.grading_calibration(g_preds, g_truths)

    # ---- Grounding-Gate ---- #
    tp = fp = tn = fn = 0
    gr_rows = []
    for i, ex in enumerate(grnd, 1):
        if progress:
            progress(f"Grounding {i}/{len(grnd)} …")
        pred = grading.is_grounded(ex["frage"], ex["antwort"], ex["beleg"])
        truth = bool(ex["grounded"])
        if truth and pred:
            tp += 1
        elif truth and not pred:
            fn += 1
        elif not truth and pred:
            fp += 1
        else:
            tn += 1
        gr_rows.append({"antwort": ex["antwort"][:45], "erwartet": truth, "urteil": pred,
                        "treffer": pred == truth})
    n_gr = len(grnd)
    prec = tp / (tp + fp) if (tp + fp) else None       # Praezision "belegt"
    rec = tp / (tp + fn) if (tp + fn) else None         # Trefferquote "belegt"
    # "Erfundenes erkannt": wie zuverlaessig NICHT-belegte als solche erkannt werden
    reject_rec = tn / (tn + fp) if (tn + fp) else None

    return {
        "status": "ok",
        "grading": {"n": n_g, "exact_pct": round(100 * exact / n_g) if n_g else None,
                    "adjacent_pct": round(100 * adjacent / n_g) if n_g else None,
                    # Richtung der Fehlkalibrierung: Bias = Mittelwert(Judge - Referenz)
                    "bias": calib["bias"], "mae": calib["mae"],
                    "direction": calib["direction"],
                    "bias_text": _BIAS_TEXT.get(calib["direction"]),
                    "rows": g_rows},
        "grounding": {"n": n_gr, "accuracy_pct": round(100 * (tp + tn) / n_gr) if n_gr else None,
                      "precision_pct": round(100 * prec) if prec is not None else None,
                      "recall_pct": round(100 * rec) if rec is not None else None,
                      "reject_recall_pct": round(100 * reject_rec) if reject_rec is not None else None,
                      "rows": gr_rows},
    }
