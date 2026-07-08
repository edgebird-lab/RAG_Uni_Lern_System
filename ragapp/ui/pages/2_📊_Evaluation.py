"""
RAG-Lernsystem: Seite „Evaluation: Trefferquote" (Streamlit)
==============================================================
Misst die Trefferquote (Hit@k / MRR) des Retrievals gegen ein Gold-Set aus
Held-out-Testfragen und zeigt den Verlauf über die Zeit, die Grundlage zum
Nachjustieren der Parameter.
"""
from __future__ import annotations

import sys
import time
import pathlib

# Projektwurzel auffindbar machen (damit 'ragapp' importierbar ist)
_p = pathlib.Path(__file__).resolve()
for _anc in _p.parents:
    if (_anc / "ragapp").is_dir():
        sys.path.insert(0, str(_anc))
        break

import pandas as pd
import streamlit as st

from ragapp.config import settings
from ragapp import manifest
from ragapp.eval.gold_set import build_gold_set, load_gold_set
from ragapp.eval.run_eval import run_retrieval_eval, load_history

st.set_page_config(page_title="Evaluation: Trefferquote", page_icon="📊", layout="wide")

# --------------------------------------------------------------------------- #
# Styling ("schick"), identisch zur Startseite
# --------------------------------------------------------------------------- #
st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1100px;}
.stChatMessage {border-radius: 14px;}
.source-card {
    background: linear-gradient(135deg, #f6f8fc 0%, #eef2fb 100%);
    border: 1px solid #e2e8f4; border-radius: 12px; padding: 12px 16px;
    margin-bottom: 8px;
}
.source-title {font-weight: 600; color: #1f3a63;}
.source-meta {color: #5b6b85; font-size: 0.85rem;}
.badge {display:inline-block; padding: 2px 10px; border-radius: 999px;
    font-size: 0.78rem; font-weight: 600;}
.badge-answer {background:#e6f7ee; color:#137a4b;}
.badge-fallback {background:#fdf0e3; color:#a15a13;}
.small {color:#7a8aa0; font-size:0.8rem;}
h1 {font-weight: 750; letter-spacing:-0.5px;}
</style>
""", unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
# Sidebar (Kurzstatistik, wie auf der Startseite)
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown("### 🎓 Lern-Assistent")
    st.caption(f"Modell: `{settings.LLM_MODEL}` · Embedding: `{settings.EMBED_MODEL}`")
    _stats = manifest.stats()
    c1, c2 = st.columns(2)
    c1.metric("Dokumente", _stats["documents"])
    c2.metric("Chunks", _stats["chunks"])
    c1.metric("Fragen", _stats["questions"])
    c2.metric("Fächer", _stats["subjects"])

# --------------------------------------------------------------------------- #
# Kopf
# --------------------------------------------------------------------------- #
st.title("📊 Evaluation: Trefferquote")
st.markdown(
    "<span class='small'>Es wird ein <b>Gold-Set</b> aus Testfragen erzeugt "
    "(<i>Held-out</i>: die Fragen werden bewusst <b>nicht</b> indexiert, damit die "
    "Messung nicht geschönt ist). Dann wird gemessen, wie oft die korrekte Quelle in "
    "den Top-k landet: <b>Hit@k</b> (Trefferquote) und <b>MRR</b> "
    "(mittlerer reziproker Rang).</span>",
    unsafe_allow_html=True,
)

# Ergebnis des letzten Laufs über Reruns hinweg sichtbar halten
if "eval_report" not in st.session_state:
    st.session_state.eval_report = None

st.divider()

# --------------------------------------------------------------------------- #
# 1) Gold-Set erzeugen
# --------------------------------------------------------------------------- #
st.subheader("1. Gold-Set erzeugen")
st.caption(
    "Zieht eine Zufallsstichprobe von Chunks und lässt das LLM je eine Testfrage "
    "formulieren, deren korrekte Quelle bekannt ist."
)
st.warning("⏳ Dauert auf CPU spürbar: **~20 s pro Frage**.")

sample_size = st.number_input(
    "Stichprobengröße (Anzahl Chunks / Fragen)",
    min_value=1, max_value=100000,
    value=int(settings.EVAL_SAMPLE_SIZE), step=10,
)

if st.button("🧪 Gold-Set erzeugen", type="primary"):
    with st.status("Erzeuge Gold-Set … (~20 s pro Frage)", expanded=True) as status:
        def _fortschritt_gold(msg: str) -> None:
            status.update(label=msg)

        try:
            res = build_gold_set(sample_size=int(sample_size), progress=_fortschritt_gold)
            status.update(label="Gold-Set erzeugt", state="complete")
        except Exception as exc:
            status.update(label=f"Fehler: {exc}", state="error")
            res = None

    if res is not None:
        if res.get("status") == "no_chunks":
            st.error("Keine Chunks vorhanden, bitte zuerst Dokumente indexieren.")
        else:
            st.success(f"{res.get('count', 0)} Testfragen erzeugt.")

_gold = load_gold_set()
st.info(f"Aktuelles Gold-Set: **{len(_gold)}** Frage(n).")

st.divider()

# --------------------------------------------------------------------------- #
# 2) Evaluation ausführen
# --------------------------------------------------------------------------- #
st.subheader("2. Evaluation ausführen")
st.caption(
    "Führt jede Gold-Frage durch die echte Retrieval-Pipeline und misst, ob und auf "
    "welchem Rang die korrekte Quelle gefunden wird."
)

if st.button("▶️ Evaluation starten"):
    if not _gold:
        st.error("Kein Gold-Set vorhanden. Bitte zuerst unter Schritt 1 erzeugen.")
    else:
        with st.status("Evaluiere Retrieval …", expanded=True) as status:
            def _fortschritt_eval(msg: str) -> None:
                status.update(label=msg)

            try:
                report = run_retrieval_eval(progress=_fortschritt_eval)
                status.update(label="Evaluation abgeschlossen", state="complete")
            except Exception as exc:
                status.update(label=f"Fehler: {exc}", state="error")
                report = None

        if report is not None:
            if report.get("status") == "no_gold":
                st.error(report.get("message", "Kein Gold-Set vorhanden."))
            else:
                st.session_state.eval_report = report

# ---- Ergebnis des letzten Laufs anzeigen -------------------------------- #
report = st.session_state.eval_report
if report and report.get("status") == "ok":
    metrics = report["metrics"]
    hit_at_k = metrics.get("hit@k", {})

    st.markdown("#### Ergebnis")
    # Große Metriken: Hit@k (als Prozent) + MRR
    k_sorted = sorted(hit_at_k.keys(), key=lambda x: int(x))
    cols = st.columns(len(k_sorted) + 1)
    for col, k in zip(cols, k_sorted):
        col.metric(f"Hit@{k}", f"{hit_at_k[k] * 100:.1f} %")
    cols[-1].metric("MRR", f"{metrics.get('mrr', 0):.3f}")

    st.caption(
        f"{report.get('num_questions', 0)} Fragen · "
        f"{report.get('elapsed_seconds', '?')} s Laufzeit"
    )

    # Balkendiagramm Hit@k über k
    chart_df = pd.DataFrame(
        {"Hit@k (%)": [hit_at_k[k] * 100 for k in k_sorted]},
        index=[f"k={k}" for k in k_sorted],
    )
    st.bar_chart(chart_df)

    # Tabelle „Nach Fach"
    by_subject = metrics.get("by_subject", {})
    if by_subject:
        st.markdown("#### Nach Fach")
        rows = []
        for subj, vals in sorted(by_subject.items()):
            row = {"Fach": subj, "n": vals.get("n", 0)}
            for key, val in vals.items():
                if key.startswith("hit@"):
                    row[key] = round(val * 100, 1)
            row["mrr"] = vals.get("mrr", 0.0)
            rows.append(row)
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Hinweis auf CSV für Fehleranalyse
    if report.get("csv"):
        st.caption(
            f"📄 Detail-Auswertung je Frage (für Fehleranalyse) gespeichert unter: "
            f"`{report['csv']}`"
        )

st.divider()

# --------------------------------------------------------------------------- #
# 3) Verlauf
# --------------------------------------------------------------------------- #
st.subheader("3. Verlauf")
st.caption(
    "Zeigt, ob deine Änderungen (Chunking, Reranker, k-Werte …) die Trefferquote "
    "über die Zeit verbessert haben."
)

_history = load_history()
if not _history:
    st.info("Noch kein Verlauf vorhanden. Führe zuerst eine Evaluation aus.")
else:
    # größtes k über den gesamten Verlauf bestimmen (für eine stabile Spalte)
    alle_ks = set()
    for h in _history:
        alle_ks.update(int(k) for k in h.get("hit@k", {}).keys())
    kmax = max(alle_ks) if alle_ks else None
    hit_col = f"Hit@{kmax}"

    verlauf = []
    for h in _history:
        hk = h.get("hit@k", {})
        zeit = time.strftime("%d.%m.%Y %H:%M", time.localtime(h.get("timestamp", 0)))
        eintrag = {
            "Zeit": zeit,
            "Fragen": h.get("num_questions"),
            "MRR": h.get("mrr"),
        }
        if kmax is not None and str(kmax) in hk:
            eintrag[hit_col] = round(hk[str(kmax)] * 100, 1)
        verlauf.append(eintrag)

    df_hist = pd.DataFrame(verlauf)

    # Liniendiagramm über die Zeit (MRR und Hit@größtes k)
    chart_cols = [c for c in ("MRR", hit_col) if c in df_hist.columns]
    if chart_cols:
        st.line_chart(df_hist.set_index("Zeit")[chart_cols])

    st.dataframe(df_hist, use_container_width=True, hide_index=True)
