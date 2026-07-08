"""
RAG-Lernsystem – Seite „Einstellungen (Tuning)" (Streamlit)
===========================================================
Zentrale Stellschrauben des Systems bequem tunen und persistent in
``data/config.json`` speichern. Nach dem Ändern in der Evaluation messen, ob
sich die Trefferquote verbessert hat.
"""
from __future__ import annotations

import sys
import pathlib

# Projektwurzel auffindbar machen (damit 'ragapp' importierbar ist)
_p = pathlib.Path(__file__).resolve()
for _anc in _p.parents:
    if (_anc / "ragapp").is_dir():
        sys.path.insert(0, str(_anc))
        break

import streamlit as st

from ragapp.config import settings, RUNTIME_CONFIG_FILE
from ragapp import manifest
from ragapp.hardware import (
    detect_hardware,
    format_hardware,
    recommend_models,
    benchmark_model,
)

st.set_page_config(page_title="Einstellungen (Tuning)", page_icon="⚙️", layout="wide")

# --------------------------------------------------------------------------- #
# Styling ("schick") – identisch zur Startseite
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
st.title("⚙️ Einstellungen (Tuning)")
st.markdown(
    "<span class='small'>Stelle die wichtigsten Parameter ein und speichere sie "
    "dauerhaft. <b>Nach dem Ändern in der Evaluation messen</b>, ob sich die "
    "Trefferquote verbessert hat.</span>",
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# Hardware- & Modell-Auswahl (mit Benchmark)
# --------------------------------------------------------------------------- #
st.header("🖥️ Hardware & Modell-Auswahl")
st.markdown(
    "<span class='small'>So findest du das beste Modell für deinen PC: "
    "<b>Empfehlung ansehen → auswählen → testen</b>. Ist die Antwort zu langsam, "
    "wähle ein kleineres Modell und teste erneut.</span>",
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def _hardware_erkennen() -> dict:
    """Erkennt die Hardware (gecacht – ändert sich zur Laufzeit nicht)."""
    return detect_hardware()


def _installierte_modelle() -> list[str] | None:
    """Namen der lokal in Ollama installierten Modelle. ``None`` bei Fehler
    (z. B. Ollama-Server nicht erreichbar)."""
    try:
        import ollama

        client = ollama.Client(host=settings.OLLAMA_BASE_URL)
        data = client.list()
        modelle = (data.get("models", []) if isinstance(data, dict)
                   else getattr(data, "models", []) or [])
        namen: list[str] = []
        for m in modelle:
            if isinstance(m, dict):
                name = m.get("model") or m.get("name") or ""
            else:
                name = getattr(m, "model", "") or getattr(m, "name", "") or ""
            if name:
                namen.append(str(name))
        return sorted(set(namen))
    except Exception:
        return None


# --- Hardware ermitteln (robust) ------------------------------------------- #
try:
    hw = _hardware_erkennen()
except Exception as exc:  # pragma: no cover - defensiv
    hw = None
    st.warning(f"Hardware-Erkennung fehlgeschlagen: {exc}")

if hw:
    g = hw["gpu"]

    st.subheader("Erkannte Hardware")
    h1, h2, h3, h4 = st.columns(4)
    h1.metric("Betriebssystem", str(hw["os"]))
    h2.metric("RAM", f"{hw.get('ram_gb', '?')} GB")
    vram_txt = f"{g['vram_gb']} GB" if g.get("vram_gb") else "shared/?"
    gpu_label = g["vendor"].upper() if g.get("vendor") != "none" else "keine"
    h3.metric("GPU", gpu_label, help=g.get("name", ""))
    h4.metric("VRAM", vram_txt, help=f"Ollama-Variante: {hw['ollama_variant']}")
    st.caption(f"CPU: {hw['cpu']}")
    with st.expander("Vollständige Hardware-Details anzeigen"):
        st.code(format_hardware(hw), language="text")

    # --- Empfehlung -------------------------------------------------------- #
    try:
        rec = recommend_models(hw)
    except Exception as exc:  # pragma: no cover - defensiv
        rec = None
        st.warning(f"Empfehlung konnte nicht erstellt werden: {exc}")

    empf_tags: list[str] = []
    if rec:
        st.subheader("Empfohlene Modelle für deinen PC")
        st.info(f"ℹ️ {rec.get('reason', '')}")
        st.caption(
            f"Empfohlenes Embedding-Modell: `{rec.get('embed_model', 'bge-m3')}`"
        )
        tabelle = "| | Modell (Ollama-Tag) | Params | ~GB | Begründung |\n"
        tabelle += "|---|---|---|---|---|\n"
        for i, m in enumerate(rec.get("models", [])):
            empf_tags.append(m["tag"])
            mark = "⭐ **empfohlen**" if i == 0 else ""
            tabelle += (
                f"| {mark} | `{m['tag']}` | {m.get('params', '')} | "
                f"{m.get('gb', '')} | {m.get('why', '')} |\n"
            )
        st.markdown(tabelle)

    # --- Modell-Picker ----------------------------------------------------- #
    st.subheader("Antwort-Modell wählen")
    installiert = _installierte_modelle()
    if installiert is None:
        st.warning(
            "⚠️ Konnte die installierten Ollama-Modelle nicht abrufen – läuft der "
            f"Ollama-Server unter `{settings.OLLAMA_BASE_URL}`? Angeboten werden "
            "stattdessen die empfohlenen Modelle."
        )
        optionen = list(empf_tags)
    elif not installiert:
        beispiel = empf_tags[0] if empf_tags else "gemma3:4b"
        st.warning(
            "⚠️ Es ist noch **kein** Ollama-Modell installiert. Installiere z. B. "
            f"das empfohlene mit `ollama pull {beispiel}` (oder über den Installer)."
        )
        optionen = list(empf_tags)
    else:
        st.caption(f"{len(installiert)} lokal installierte Modelle gefunden.")
        # Installierte zuerst, dann empfohlene, die noch nicht installiert sind.
        optionen = list(installiert) + [t for t in empf_tags if t not in installiert]

    # Aktuelles Antwort-Modell immer als Option führen und vorauswählen.
    optionen = [o for o in dict.fromkeys(optionen) if o]
    if settings.LLM_MODEL and settings.LLM_MODEL not in optionen:
        optionen = [settings.LLM_MODEL] + optionen
    if not optionen:
        optionen = [settings.LLM_MODEL or "gemma3:4b"]
    default_idx = (optionen.index(settings.LLM_MODEL)
                   if settings.LLM_MODEL in optionen else 0)

    gewaehlt = st.selectbox(
        "Modell für die Antwortgenerierung",
        options=optionen,
        index=default_idx,
        help="Auswahl = lokal installierte Ollama-Modelle (+ Empfehlungen). "
             "Das aktuell aktive Modell ist vorausgewählt.",
    )
    st.caption(f"Aktuell aktives Antwort-Modell: `{settings.LLM_MODEL}`")

    b1, b2 = st.columns(2)
    with b1:
        setzen = st.button("✅ Als Antwort-Modell setzen",
                           use_container_width=True)
    with b2:
        starte_bench = st.button("⏱️ Modell testen (tok/s)",
                                 use_container_width=True)

    if setzen and gewaehlt:
        try:
            settings.update(LLM_MODEL=gewaehlt, LLM_MODEL_FAST=gewaehlt)
            settings.save()
            st.success(
                f"Antwort-Modell auf `{gewaehlt}` gesetzt "
                "(auch als schnelles Hilfsmodell). Neue Fragen nutzen es sofort."
            )
            st.info(
                f"ℹ️ Das Modell muss lokal installiert sein: `ollama pull {gewaehlt}` "
                "(oder über den One-Click-Installer). Ohne installiertes Modell "
                "schlägt die Antwortgenerierung fehl."
            )
        except Exception as exc:  # pragma: no cover - defensiv
            st.error(f"Konnte das Modell nicht setzen: {exc}")

    st.caption(
        "⚠️ Der Benchmark lädt das Modell und generiert zweimal Text (kalt + warm). "
        "Auf CPU oder schwacher GPU kann das **einige Minuten** dauern. Ist das "
        "Modell noch nicht installiert, wird es zuerst heruntergeladen."
    )

    # --- Benchmark ausführen ---------------------------------------------- #
    if starte_bench and gewaehlt:
        with st.status(f"Teste Modell `{gewaehlt}` …", expanded=True) as status:
            def _fortschritt(msg: str) -> None:
                status.update(label=msg)
                st.write(msg)

            try:
                ergebnis = benchmark_model(gewaehlt, progress=_fortschritt)
            except Exception as exc:  # pragma: no cover - defensiv
                ergebnis = {"tag": gewaehlt, "error": f"Unerwarteter Fehler: {exc}"}

            if ergebnis.get("error"):
                status.update(label="Benchmark fehlgeschlagen", state="error")
            else:
                status.update(
                    label=f"Benchmark fertig: {ergebnis.get('tokens_per_s', '?')} tok/s",
                    state="complete",
                )
        st.session_state["_bench_result"] = ergebnis

    # --- Benchmark-Ergebnis anzeigen (überlebt Rerun) --------------------- #
    ergebnis = st.session_state.get("_bench_result")
    if ergebnis:
        tag = ergebnis.get("tag", "?")
        if ergebnis.get("error"):
            st.error(
                f"❌ Benchmark für `{tag}` fehlgeschlagen: {ergebnis['error']}\n\n"
                "Häufigste Ursache: **Modell nicht installiert** – vorher "
                f"`ollama pull {tag}` ausführen. Prüfe außerdem, ob der Ollama-Server "
                f"unter `{settings.OLLAMA_BASE_URL}` läuft."
            )
        else:
            st.success(f"✅ Benchmark für `{tag}` abgeschlossen.")
            m1, m2, m3 = st.columns(3)
            m1.metric("Geschwindigkeit", f"{ergebnis.get('tokens_per_s', '?')} tok/s")
            m2.metric("Warm-Antwort", f"{ergebnis.get('warm_s', '?')} s",
                      help="Antwortzeit bei bereits geladenem Modell.")
            m3.metric("Kalt-Antwort", f"{ergebnis.get('cold_s', '?')} s",
                      help="Erste Antwort inkl. Laden ins GPU-/CPU-RAM.")
            st.info(f"**Einschätzung:** {ergebnis.get('verdict', '')}")

st.divider()

# --------------------------------------------------------------------------- #
# Formular
# --------------------------------------------------------------------------- #
with st.form("einstellungen"):
    neu: dict = {}

    # ------------------------------------------------------------------ #
    st.subheader("Retrieval (Suche)")
    r1, r2, r3 = st.columns(3)
    with r1:
        neu["DENSE_TOP_K"] = st.number_input(
            "DENSE_TOP_K", min_value=1, max_value=500,
            value=int(settings.DENSE_TOP_K), step=1,
            help="Kandidaten aus der Vektorsuche.")
        neu["FUSION_TOP_K"] = st.number_input(
            "FUSION_TOP_K", min_value=1, max_value=500,
            value=int(settings.FUSION_TOP_K), step=1,
            help="Kandidaten nach der Fusion (gehen ins Rerank).")
        neu["FINAL_TOP_K"] = st.number_input(
            "FINAL_TOP_K", min_value=1, max_value=100,
            value=int(settings.FINAL_TOP_K), step=1,
            help="Finale Chunks, die ins LLM gehen.")
    with r2:
        neu["BM25_TOP_K"] = st.number_input(
            "BM25_TOP_K", min_value=1, max_value=500,
            value=int(settings.BM25_TOP_K), step=1,
            help="Kandidaten aus der Keyword-Suche.")
        neu["RRF_K"] = st.number_input(
            "RRF_K", min_value=1, max_value=1000,
            value=int(settings.RRF_K), step=1,
            help="Reciprocal-Rank-Fusion-Konstante.")
        neu["RELEVANCE_MIN_SCORE"] = st.number_input(
            "RELEVANCE_MIN_SCORE", value=float(settings.RELEVANCE_MIN_SCORE), step=0.5,
            help="Mindest-Rerank-Score, ab dem frei geantwortet wird "
                 "(darunter: nur Dokumente nennen, keine Halluzination).")
    with r3:
        neu["DENSE_WEIGHT"] = st.number_input(
            "DENSE_WEIGHT", min_value=0.0, max_value=10.0,
            value=float(settings.DENSE_WEIGHT), step=0.1,
            help="Gewicht der Vektorsuche (falls Rerank aus).")
        neu["BM25_WEIGHT"] = st.number_input(
            "BM25_WEIGHT", min_value=0.0, max_value=10.0,
            value=float(settings.BM25_WEIGHT), step=0.1,
            help="Gewicht der Keyword-Suche (falls Rerank aus).")
        neu["USE_RERANKER"] = st.toggle(
            "USE_RERANKER", value=bool(settings.USE_RERANKER),
            help="Cross-Encoder-Reranking der Kandidaten (Trefferquote ↑).")

    st.divider()

    # ------------------------------------------------------------------ #
    st.subheader("Chunking (Slicing)")
    c1, c2, c3 = st.columns(3)
    with c1:
        neu["CHUNK_SIZE"] = st.number_input(
            "CHUNK_SIZE", min_value=100, max_value=8000,
            value=int(settings.CHUNK_SIZE), step=50,
            help="Zielgröße pro Chunk (Zeichen).")
    with c2:
        neu["CHUNK_OVERLAP"] = st.number_input(
            "CHUNK_OVERLAP", min_value=0, max_value=2000,
            value=int(settings.CHUNK_OVERLAP), step=10,
            help="Überlappung zwischen Chunks (Kontexterhalt).")
    with c3:
        neu["MIN_CHUNK_CHARS"] = st.number_input(
            "MIN_CHUNK_CHARS", min_value=0, max_value=2000,
            value=int(settings.MIN_CHUNK_CHARS), step=10,
            help="Kleinere Fragmente werden verworfen/gemerged.")
    neu["RESPECT_MARKDOWN_HEADERS"] = st.toggle(
        "RESPECT_MARKDOWN_HEADERS", value=bool(settings.RESPECT_MARKDOWN_HEADERS),
        help="Markdown an Überschriften schneiden.")

    st.divider()

    # ------------------------------------------------------------------ #
    st.subheader("Antwort & Anti-Halluzination")
    a1, a2, a3 = st.columns(3)
    with a1:
        neu["LLM_TEMPERATURE"] = st.slider(
            "LLM_TEMPERATURE", min_value=0.0, max_value=1.0,
            value=float(settings.LLM_TEMPERATURE), step=0.05,
            help="Niedrig = faktentreu, wenig Halluzination.")
    with a2:
        neu["LLM_NUM_CTX"] = st.number_input(
            "LLM_NUM_CTX", min_value=512, max_value=131072,
            value=int(settings.LLM_NUM_CTX), step=512,
            help="Kontextfenster für die Generierung.")
    with a3:
        neu["MAX_CONTEXT_CHARS"] = st.number_input(
            "MAX_CONTEXT_CHARS", min_value=500, max_value=100000,
            value=int(settings.MAX_CONTEXT_CHARS), step=500,
            help="Obergrenze des Kontexts an das LLM.")
    neu["ENABLE_FAITHFULNESS_CHECK"] = st.toggle(
        "ENABLE_FAITHFULNESS_CHECK", value=bool(settings.ENABLE_FAITHFULNESS_CHECK),
        help="LLM prüft, ob die Antwort durch den Kontext belegt ist.")

    st.divider()

    # ------------------------------------------------------------------ #
    st.subheader("Deduplizierung")
    d1, d2, d3 = st.columns(3)
    with d1:
        neu["DEDUP_NEAR_DUPLICATE_THRESHOLD"] = st.slider(
            "DEDUP_NEAR_DUPLICATE_THRESHOLD", min_value=0.0, max_value=1.0,
            value=float(settings.DEDUP_NEAR_DUPLICATE_THRESHOLD), step=0.005,
            help="Cosine-Schwelle für Chunk-Near-Duplicates beim Import.")
    with d2:
        neu["RETRIEVAL_DEDUP_JACCARD"] = st.slider(
            "RETRIEVAL_DEDUP_JACCARD", min_value=0.0, max_value=1.0,
            value=float(settings.RETRIEVAL_DEDUP_JACCARD), step=0.01,
            help="Token-Jaccard-Schwelle gegen doppelte Treffer.")
    with d3:
        neu["RETRIEVAL_DEDUP"] = st.toggle(
            "RETRIEVAL_DEDUP", value=bool(settings.RETRIEVAL_DEDUP),
            help="Doppelte Informationen in den Treffern herausfiltern.")

    st.divider()

    # ------------------------------------------------------------------ #
    st.subheader("Modelle")
    st.caption("Lokale Ollama-/HuggingFace-Modellnamen. Müssen lokal verfügbar sein.")
    m1, m2, m3 = st.columns(3)
    with m1:
        neu["LLM_MODEL"] = st.text_input("LLM_MODEL", value=str(settings.LLM_MODEL))
    with m2:
        neu["EMBED_MODEL"] = st.text_input("EMBED_MODEL", value=str(settings.EMBED_MODEL))
    with m3:
        neu["RERANKER_MODEL"] = st.text_input(
            "RERANKER_MODEL", value=str(settings.RERANKER_MODEL))

    st.divider()

    # ------------------------------------------------------------------ #
    st.subheader("Evaluation")
    e1, e2 = st.columns(2)
    with e1:
        neu["EVAL_SAMPLE_SIZE"] = st.number_input(
            "EVAL_SAMPLE_SIZE", min_value=1, max_value=100000,
            value=int(settings.EVAL_SAMPLE_SIZE), step=10,
            help="Anzahl gesampelter Chunks fürs Gold-Set.")
    with e2:
        neu["EVAL_QUESTIONS_PER_CHUNK"] = st.number_input(
            "EVAL_QUESTIONS_PER_CHUNK", min_value=1, max_value=10,
            value=int(settings.EVAL_QUESTIONS_PER_CHUNK), step=1,
            help="Held-out-Fragen pro gesampeltem Chunk.")

    st.caption(
        f"Hinweis: `EVAL_K_VALUES = {tuple(settings.EVAL_K_VALUES)}` (fest, nicht "
        "editierbar)."
    )

    st.divider()
    gespeichert = st.form_submit_button("💾 Speichern", type="primary")

if gespeichert:
    # number_input liefert je nach Startwert int/float – Typen bereinigen
    int_felder = {
        "DENSE_TOP_K", "BM25_TOP_K", "FUSION_TOP_K", "RRF_K", "FINAL_TOP_K",
        "CHUNK_SIZE", "CHUNK_OVERLAP", "MIN_CHUNK_CHARS", "LLM_NUM_CTX",
        "MAX_CONTEXT_CHARS", "EVAL_SAMPLE_SIZE", "EVAL_QUESTIONS_PER_CHUNK",
    }
    for k in int_felder:
        neu[k] = int(neu[k])

    settings.update(**neu)
    settings.save()
    st.success("Einstellungen gespeichert.")
    st.info(
        "ℹ️ **Wann wirkt was?** Retrieval- und Antwort-Parameter greifen **sofort** "
        "bei der nächsten Frage. **Chunking-Werte** (CHUNK_SIZE, CHUNK_OVERLAP, "
        "MIN_CHUNK_CHARS, RESPECT_MARKDOWN_HEADERS) betreffen den Index und wirken "
        "erst nach einem **Neu-Import** der Dokumente. Die Werte werden in "
        "`data/config.json` gespeichert."
    )

# --------------------------------------------------------------------------- #
# Zurücksetzen (außerhalb des Formulars)
# --------------------------------------------------------------------------- #
st.divider()
st.subheader("Zurücksetzen")
st.caption(
    "Löscht `data/config.json` und stellt alle Standardwerte wieder her."
)
if st.button("↩️ Auf Standard zurücksetzen"):
    RUNTIME_CONFIG_FILE.unlink(missing_ok=True)
    # Das laufende (Modul-globale) settings-Objekt ebenfalls auf Defaults setzen,
    # sonst wirken die alten Werte in dieser Sitzung weiter.
    settings.reset()
    st.success("Standardwerte wiederhergestellt (data/config.json gelöscht).")
    st.rerun()
