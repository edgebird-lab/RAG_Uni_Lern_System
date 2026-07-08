"""
RAG-Lernsystem: Chat-Oberfläche (Streamlit)
============================================
Start:  streamlit run ragapp/ui/Home.py
"""
from __future__ import annotations

import sys
import random
import pathlib

# Projektwurzel auffindbar machen (damit 'ragapp' importierbar ist)
_p = pathlib.Path(__file__).resolve()
for _anc in _p.parents:
    if (_anc / "ragapp").is_dir():
        sys.path.insert(0, str(_anc))
        break

import streamlit as st

from ragapp.config import settings, SUBJECT_LABELS
from ragapp import manifest

# App-Icon (Fenster/Taskleiste/Favicon). Faellt auf ein Emoji zurueck,
# falls die Icon-Datei fehlt (z. B. vor dem ersten Build).
_icon_png = _p.parents[2] / "assets" / "icon.png"
_PAGE_ICON = str(_icon_png) if _icon_png.is_file() else "🎓"

st.set_page_config(page_title="RAG-Lernsystem", page_icon=_PAGE_ICON, layout="wide")

# Motivierende Sprüche für den Denk-/Lademoment (rotieren zufällig)
_LERN_SPRUECHE = [
    "Dranbleiben lohnt sich. Jede Frage bringt dich der Bestnote näher.",
    "Wissen wächst mit jeder Frage. Du schaffst das!",
    "Kleine Schritte, große Wirkung. Bleib neugierig!",
    "Fokus an, Zweifel aus. Deine Klausur kann kommen!",
    "Jede Wiederholung sitzt. Weiter so!",
    "Verstehen schlägt Auswendiglernen. Frag ruhig nach.",
]

# --------------------------------------------------------------------------- #
# Styling ("schick")
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
# Sidebar
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown("### 🎓 Lern-Assistent")
    st.caption(f"Modell: `{settings.LLM_MODEL}` · Embedding: `{settings.EMBED_MODEL}`")

    stats = manifest.stats()
    c1, c2 = st.columns(2)
    c1.metric("Dokumente", stats["documents"])
    c2.metric("Chunks", stats["chunks"])
    c1.metric("Fragen", stats["questions"])
    c2.metric("Fächer", stats["subjects"])

    st.divider()
    subjects = sorted({d["subject"] for d in manifest.list_documents()})
    subject_options = ["Alle Fächer"] + subjects
    chosen = st.selectbox("Fach filtern", subject_options,
                          help="Sucht nur in einem Fach, das ist schneller und präziser.")
    subject_filter = None if chosen == "Alle Fächer" else chosen

    show_sources = st.toggle("Quellen anzeigen", value=True)
    st.divider()
    if st.button("🗑️ Verlauf löschen", use_container_width=True):
        st.session_state.messages = []
        st.rerun()
    st.caption("Seiten links: **Ingestion**, **Evaluation**, **Einstellungen**")


# --------------------------------------------------------------------------- #
# Kopf
# --------------------------------------------------------------------------- #
st.title("Frag deine Zusammenfassungen")
st.markdown(
    "<span class='small'>Antworten kommen <b>ausschließlich</b> aus deinen "
    "Unterlagen. Weiß das System etwas nicht, nennt es dir ehrlich die am besten "
    "passenden Dokumente, <b>ohne zu halluzinieren</b>.</span>",
    unsafe_allow_html=True,
)

if stats["chunks"] == 0:
    st.info("Noch keine Dokumente indexiert. Gehe zu **📥 Ingestion** und starte den "
            "Import oder lege Dateien in den Ordner *Zusammenfassungen SoSE26*.")

if "messages" not in st.session_state:
    st.session_state.messages = []


def render_sources(sources: list[dict]):
    if not sources:
        return
    st.markdown("**Quellen:**")
    for s in sources:
        loc = f" · {s['location']}" if s.get("location") else ""
        st.markdown(
            f"<div class='source-card'>"
            f"<span class='source-title'>[{s['rank']}] {s['filename']}</span>{loc}<br>"
            f"<span class='source-meta'>Fach: {s['subject']} · Score: {s['score']} "
            f"· Retriever: {s.get('retrievers','')}</span></div>",
            unsafe_allow_html=True,
        )
        with st.expander("Textstelle ansehen"):
            st.write(s.get("snippet", ""))


# Verlauf rendern
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="🧑‍🎓" if msg["role"] == "user" else "🤖"):
        st.markdown(msg["content"])
        if msg.get("meta"):
            m = msg["meta"]
            badge = "badge-answer" if m.get("mode") == "answer" else "badge-fallback"
            label = "belegte Antwort" if m.get("mode") == "answer" else "Fallback: passende Dokumente"
            st.markdown(f"<span class='badge {badge}'>{label}</span> "
                        f"<span class='small'>· {m.get('total_time','?')}s</span>",
                        unsafe_allow_html=True)
        if msg.get("sources"):
            render_sources(msg["sources"])


# --------------------------------------------------------------------------- #
# Eingabe
# --------------------------------------------------------------------------- #
prompt = st.chat_input("Stelle eine Frage zu deinem Lernstoff …")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑‍🎓"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner(random.choice(_LERN_SPRUECHE)):
            from ragapp.graph.rag_graph import answer_query
            try:
                result = answer_query(prompt, subject=subject_filter)
            except Exception as exc:
                result = {"answer": f"⚠️ Fehler: {exc}", "mode": "fallback",
                          "sources": [], "total_time": 0}
        st.markdown(result.get("answer", ""))
        meta = {"mode": result.get("mode"), "total_time": result.get("total_time")}
        badge = "badge-answer" if meta["mode"] == "answer" else "badge-fallback"
        label = "belegte Antwort" if meta["mode"] == "answer" else "Fallback: passende Dokumente"
        st.markdown(f"<span class='badge {badge}'>{label}</span> "
                    f"<span class='small'>· {meta.get('total_time','?')}s</span>",
                    unsafe_allow_html=True)
        sources = result.get("sources", []) if show_sources else []
        if sources:
            render_sources(sources)

    st.session_state.messages.append({
        "role": "assistant",
        "content": result.get("answer", ""),
        "meta": meta,
        "sources": sources,
    })
