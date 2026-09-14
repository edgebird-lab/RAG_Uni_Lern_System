"""
RAG-Lernsystem: Chat-Oberfläche (Streamlit)
============================================
Umgezogen vom früheren Einstiegspunkt (jetzt ``🏠_Home.py``, Kachel-Übersicht)
hierher - reine Chat-Funktion, unverändert bis auf Ort + Optik (Akzentfarbe,
Doodles, Hamburger-Navigation kommen zentral über
``page_boot(..., accent="chat")``). Der Prozess-Start-Kram (Prewarm/Watchdog/
Backup-Snapshot/PWA-Banner) bleibt bewusst in ``🏠_Home.py``, weil DAS
weiterhin die von start.sh/desktop.py gestartete Datei ist.
"""
from __future__ import annotations

import sys
import html
import pathlib
import time

_p = pathlib.Path(__file__).resolve()
for _anc in _p.parents:
    if (_anc / "ragapp").is_dir():
        sys.path.insert(0, str(_anc))
        break

import streamlit as st
import streamlit.components.v1 as _components

from ragapp.ui._loading import page_boot, skeleton
page_boot("💬 Chat", page_title="Chat", icon="💬",
          layout="wide", accent="chat")

from ragapp.ui._style import card, delete_button, seed_selectbox_from_query, sticky_expander, sync_query_param

# --------------------------------------------------------------------------- #
# Styling - Rest kommt zentral aus apply_theme()/apply_page_style(); hier nur
# die chat-funktionsspezifischen Klassen (Quellen-Karten, Badges, Dropdown-
# Höhenbegrenzung), die die Rendering-Funktionen unten brauchen.
# --------------------------------------------------------------------------- #
st.markdown("""
<style>
.block-container {padding-bottom: 6rem;}
#rag-mascot-corner-wrap {bottom: 5.8rem;}
ul[role="listbox"], [data-testid="stSelectboxVirtualDropdown"] ul,
[data-baseweb="menu"] {max-height: 45vh !important; overflow-y: auto !important;}
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
.badge-plain {background:#eef1f5; color:#5b6b85;}
.badge-unsure {background:#fef6e0; color:#8a6d1a;}
/* Höhe-0-Komponenten (Maskottchen, Scroll) dürfen Chips nicht überdecken. */
div[data-testid="stIFrame"]:has(iframe[height="0"]),
iframe[height="0"] {
    pointer-events: none !important;
    position: absolute !important;
    width: 0 !important; height: 0 !important;
    overflow: hidden !important; border: 0 !important;
}
.small {color:#7a8aa0; font-size:0.8rem;}
</style>
""", unsafe_allow_html=True)

st.markdown(
    "<p class='rag-page-lede small'>Antworten kommen <b>ausschließlich</b> aus deinen "
    "Unterlagen. Weiß das System etwas nicht, nennt es dir ehrlich die am besten "
    "passenden Dokumente, <b>ohne zu halluzinieren</b>.</p>",
    unsafe_allow_html=True,
)

# Seitenspezifische ragapp-Importe erst JETZT - unter einem Ladehinweis, damit beim
# ersten (kalten) Laden ein Spinner statt eines weissen Bereichs erscheint. Der
# import im with-Block bindet modulweit -> alle spaeteren Verwendungen unveraendert.
with skeleton("Chat wird geladen …"):
    from ragapp.config import settings, SUBJECT_LABELS, PROJECT_ROOT
    from ragapp import manifest

# --------------------------------------------------------------------------- #
# Chat wählen (Hauptspalte, nicht Sidebar – auf dem Handy sonst unsichtbar)
# --------------------------------------------------------------------------- #
_chat_sessions = manifest.list_chat_sessions()
_sess_by_id = {s["session_id"]: s for s in _chat_sessions}

_verstehen_prefill = st.session_state.pop("verstehen_prefill", None)
if _verstehen_prefill:
    st.session_state["_chat_pending_choice"] = None
    st.session_state["_verstehen_keep_topic"] = True
    st.session_state["ui_chat_mode"] = "🧭 Sokratischer Dialog"
    _vs_subj = (_verstehen_prefill.get("subject") or "").strip()
    _vs_docs = {d["subject"] for d in manifest.list_documents() if d["subject"]}
    if _vs_subj in _vs_docs:
        st.session_state["chat_subject_filter"] = _vs_subj
    _vs_topic = (_verstehen_prefill.get("topic") or "").strip()
    st.session_state["socratic_topic"] = _vs_topic
    st.session_state["verstehen_session"] = {
        "subject": _vs_subj or None,
        "topic": _vs_topic,
        "minutes": int(_verstehen_prefill.get("minutes") or 20),
        "started_at": time.time(),
    }
    st.session_state.messages = []

if "_chat_pending_choice" in st.session_state:
    st.session_state["chat_session_choice"] = st.session_state.pop("_chat_pending_choice")
elif st.session_state.get("chat_session_choice") not in ([None] + list(_sess_by_id.keys())):
    st.session_state["chat_session_choice"] = None

def _fmt_session_option(sid: "str | None") -> str:
    if sid is None:
        return "➕ Neuer Chat"
    s = _sess_by_id.get(sid)
    return s["title"] if s else "(gelöscht)"

st.selectbox("Chat wählen", [None] + list(_sess_by_id.keys()),
            format_func=_fmt_session_option, key="chat_session_choice")
_active_session_id = st.session_state.get("chat_session_choice")

# Verlauf nur bei einer ECHTEN Auswahländerung neu laden (nicht bei jedem
# Rerun waehrend einer laufenden Antwort) - _chat_loaded_session_id merkt
# sich, welche Sitzung zuletzt in st.session_state.messages geladen wurde.
if st.session_state.get("_chat_loaded_session_id", "__unset__") != _active_session_id:
    st.session_state["_chat_loaded_session_id"] = _active_session_id
    _keep_verstehen = bool(st.session_state.pop("_verstehen_keep_topic", False))
    if _keep_verstehen:
        st.session_state.messages = []
    else:
        _sess = _sess_by_id.get(_active_session_id) if _active_session_id else None
        st.session_state.messages = list(_sess["messages"]) if _sess else []
        if _sess and _sess.get("subject"):
            st.session_state["chat_subject_filter"] = _sess["subject"]
        st.session_state.pop("socratic_topic", None)
        _m0 = ""
        if st.session_state.messages:
            _m0 = (st.session_state.messages[0].get("content") or "").strip()
        if _m0.startswith("Lass uns über ") and " sprechen." in _m0:
            st.session_state["socratic_topic"] = (
                _m0[len("Lass uns über "):].split(" sprechen.", 1)[0].strip())
else:
    st.session_state.pop("_verstehen_keep_topic", None)

with sticky_expander("⚙️ Chat & Filter", key="chat_filter_expander", expanded=False):
    st.caption(f"Modell: `{settings.LLM_MODEL}` · Embedding: `{settings.EMBED_MODEL}`")
    if _active_session_id is not None:
        _new_title = st.text_input(
            "Titel", value=_sess_by_id.get(_active_session_id, {}).get("title", ""),
            key=f"chat_title_{_active_session_id}")
        if st.button("💾 Titel speichern", key=f"chat_save_title_{_active_session_id}"):
            manifest.update_chat_session(_active_session_id, title=_new_title)
            st.rerun()

    from ragapp.llm import model_status, warm_llm
    _mst = model_status()
    if not _mst["reachable"]:
        st.caption("⚠️ Ollama nicht erreichbar.")
    elif _mst["resident"]:
        st.caption(f"🟢 `{_mst['model']}` ist geladen (belegt RAM/VRAM).")
    else:
        st.caption(f"⚪ `{_mst['model']}` ist nicht geladen (lädt bei der "
                   "nächsten Frage automatisch).")
    _mc1, _mc2 = st.columns(2)
    if _mc1.button("▶️ Jetzt laden", use_container_width=True,
                   disabled=not _mst["reachable"] or _mst["resident"]):
        with st.spinner("Modell wird geladen …"):
            try:
                warm_llm()
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
    if _mc2.button("⏹️ Jetzt entladen", use_container_width=True,
                   disabled=not _mst["reachable"] or not _mst["resident"]):
        from ragapp.scripts.stop_ollama_standby import unload_resident_models
        unload_resident_models(settings.OLLAMA_BASE_URL)
        st.rerun()

    stats = manifest.stats()
    c1, c2 = st.columns(2)
    c1.metric("Dokumente", stats["documents"])
    c2.metric("Chunks", stats["chunks"])
    c1.metric("Fragen", stats["questions"])
    c2.metric("Fächer", stats["subjects"])

    subjects = sorted({d["subject"] for d in manifest.list_documents()})
    subject_options = ["Alle Fächer"] + subjects
    seed_selectbox_from_query("chat_subject_filter", subject_options)
    chosen = st.selectbox("Fach filtern", subject_options, key="chat_subject_filter",
                          help="Sucht nur in einem Fach, das ist schneller und präziser. "
                               "Die Wahl bleibt in dieser Sitzung merken.")
    subject_filter = None if chosen == "Alle Fächer" else chosen
    sync_query_param("fach", subject_filter)
    if _active_session_id and subject_filter:
        try:
            manifest.update_chat_session(_active_session_id, subject=subject_filter)
        except Exception:  # noqa: BLE001
            pass

    include_notes_ui = st.toggle(
        "🗒️ Eigene Notizen mitdurchsuchen",
        value=bool(st.session_state.get("chat_include_notes", False)),
        key="chat_include_notes",
        help="Hängt passende Mitschriften als Extra-Kontext an – nicht als nummerierte Quelle.")

    st.caption("⚡ Tempo ↔ Genauigkeit")
    use_reranker_ui = st.toggle(
        "🎯 Feine Nachsortierung", value=bool(settings.USE_RERANKER), key="ui_reranker",
        help="Sortiert die gefundenen Stellen mit einem genaueren Modell (Reranker) "
             "noch einmal nach Relevanz. AUS = spürbar schneller, dafür ist die "
             "Reihenfolge der Treffer etwas gröber. Technisch: Reranker.")
    check_faith_ui = st.toggle(
        "🛡️ Antwort gegenprüfen", value=bool(settings.ENABLE_FAITHFULNESS_CHECK),
        key="ui_faithfulness",
        help="Zusätzliche KI-Prüfung, ob die Antwort wirklich durch deine Unterlagen "
             "belegt ist (Schutz vor erfundenen Aussagen). AUS = schneller, dafür wird "
             "die Antwort weniger streng gegengeprüft. Sie stammt aber weiterhin nur "
             "aus deinen Unterlagen. Technisch: Faithfulness-Check.")
    _mode_choice = st.radio(
        "Gesprächsmodus", ["🎯 Strikt", "🗣️ Tutor-Gespräch", "🧭 Sokratischer Dialog"],
        key="ui_chat_mode",
        help="🎯 Strikt: nur Antworten, die direkt aus deinen Unterlagen belegt "
             "sind. 🗣️ Tutor-Gespräch: freier formuliert, strukturiert, "
             "priorisiert, Lernüberblick. 🧭 Sokratischer Dialog: stellt dir "
             "gezielte Rückfragen und hilft, die Antwort SELBST zu erarbeiten. "
             "Zuerst das Thema festlegen, dann auf einer Linie bleiben "
             "(Hinweis / Teilwissen / Auflösen) – gut zum wirklichen Verstehen "
             "statt Nachschlagen. In allen drei Modi kommen Fakten weiterhin "
             "ausschließlich aus dem RAG – nichts wird erfunden. Gegenprüfung "
             "ist in Tutor-Gespräch und Sokratischem Dialog aus (sonst würde "
             "Synthese oft verworfen).")
    _chat_mode = {"🎯 Strikt": "strict", "🗣️ Tutor-Gespräch": "tutor",
                 "🧭 Sokratischer Dialog": "sokratisch"}[_mode_choice]

    show_sources = st.toggle("Quellen anzeigen", value=True)

    _del_label = ("🗑️ Diesen Chat löschen" if _active_session_id
                  else "🗑️ Verlauf leeren")
    _del_body = (
        f"Chat **{_sess_by_id.get(_active_session_id, {}).get('title', 'ohne Titel')}** "
        "und den gespeicherten Verlauf wirklich löschen?"
        if _active_session_id else
        "Den aktuellen, noch nicht gespeicherten Verlauf wirklich leeren?"
    )
    if delete_button(_del_label, token=f"chat:{_active_session_id or 'new'}",
                     body=_del_body, key="chat_delete"):
        if _active_session_id is not None:
            manifest.delete_chat_session(_active_session_id)
        st.session_state.messages = []
        st.session_state["_chat_pending_choice"] = None
        st.session_state.pop("socratic_topic", None)
        st.session_state.pop("verstehen_session", None)
        st.rerun()


if stats["chunks"] == 0:
    from ragapp.ui._style import empty_state, page_title as _pt
    empty_state(
        "Noch keine Dokumente indexiert. Lade Dateien unter **Dokumente** hoch "
        "oder lege sie in den Quellordner.",
        cta_label=f"Zu {_pt('dokumente')}",
        page_key="dokumente",
        icon="📥",
        key="chat_empty_dokumente",
    )


from ragapp.ui import _docviewer


def _load_full_text(src: dict) -> "str | None":
    """Volltext des Quell-Dokuments laden (aus der Originaldatei)."""
    sp = src.get("source_path", "")
    if not sp:
        return None
    return _docviewer.load_full_text(PROJECT_ROOT / sp)


@st.dialog("📄 Dokument ansehen", width="large")
def _view_document(src: dict) -> None:
    """Zeigt das Dokument und springt zur gefundenen Stelle. Bei PDFs die echte Seite als
    Bild mit Highlight; sonst der markierte Volltext."""
    _loc = f"  ·  {src['location']}" if src.get("location") else ""
    st.markdown(f"**{src.get('filename', '?')}**  ·  Fach: {src.get('subject', '?')}{_loc}")
    chunk = (src.get("document") or src.get("snippet") or "").strip()

    # PDF: echte Seite als Bild mit Highlight (Seitenzahl aus 'location', z. B. "Seite 5").
    import re as _re3
    _m = _re3.search(r"(\d+)", src.get("location", "") or "")
    if _m and (src.get("filename", "").lower().endswith(".pdf")):
        _png = _docviewer.render_pdf_page(PROJECT_ROOT / (src.get("source_path") or ""),
                                          int(_m.group(1)), highlight_text=chunk)
        if _png:
            st.image(_png, use_container_width=True)
            st.caption(f"Seite {int(_m.group(1))} – die gefundene Stelle ist gelb markiert.")
            return

    full = _load_full_text(src)
    if not full:
        st.info("Der Volltext ist nicht verfügbar (Originaldatei nicht gefunden). "
                "Hier die gefundene Textstelle:")
        st.write(chunk or "—")
        return
    start, end = _docviewer.locate(full, chunk)
    if start < 0:
        body = html.escape(full)
    else:
        body = (html.escape(full[:start])
                + "<mark id='rag-hl' style='background:#ffe98a; padding:1px 0;'>"
                + html.escape(full[start:end]) + "</mark>"
                + html.escape(full[end:]))
    _components.html(
        "<div style='max-height:58vh; overflow:auto; white-space:pre-wrap; "
        "font-family:system-ui,-apple-system,sans-serif; font-size:14px; "
        "line-height:1.55; padding:10px; color:#1a2233;'>" + body + "</div>"
        "<script>var e=document.getElementById('rag-hl');"
        "if(e){setTimeout(function(){e.scrollIntoView({block:'center'});}, 60);}</script>",
        height=470, scrolling=True,
    )
    st.caption("Die gelb markierte Stelle ist die gefundene Textstelle.")


def render_sources(sources: list[dict], key_prefix: str = "s"):
    if not sources:
        return
    # Quellen eingeklappt: so bleibt die Antwort im Blick und man landet nicht
    # unter einer langen Quellen-Liste.
    with st.expander(f"📚 Quellen ({len(sources)})", expanded=False):
        for s in sources:
            loc = f" · {s['location']}" if s.get("location") else ""
            st.markdown(
                f"<div class='source-card'>"
                f"<span class='source-title'>[{s['rank']}] {s['filename']}</span>{loc}<br>"
                f"<span class='source-meta'>Fach: {s['subject']} · Score: {s['score']} "
                f"· Retriever: {s.get('retrievers','')}</span></div>",
                unsafe_allow_html=True,
            )
            _snip = s.get("snippet", "")
            st.caption("„" + _snip[:240] + ("…" if len(_snip) > 240 else "") + "”")
            if st.button("📄 Im Dokument ansehen", key=f"doc_{key_prefix}_{s['rank']}"):
                _view_document(s)


import re as _re
# Quellen-Verweise im Antworttext, z. B. [Quelle 1], [Quelle 1, 2], (Quelle 3).
_SOURCE_CITE_RE = _re.compile(r"[ \t]*[\[(]\s*Quellen?\s*\d[^\])]*[\])]")


def _strip_source_labels(text: str) -> str:
    """Entfernt die [Quelle N]-Verweise aus dem Antworttext. Wird genutzt, wenn die
    Quellen-Anzeige AUS ist - sonst zeigen die Verweise ins Leere (inkonsistent)."""
    if not text:
        return text
    cleaned = _SOURCE_CITE_RE.sub("", text)
    # eine evtl. übrig gebliebene, jetzt leere "Quellen:"-Zeile entfernen
    cleaned = _re.sub(r"(?im)^[ \t]*Quellen?[ \t]*:[ \t]*[,;.–\-\s]*$", "", cleaned)
    # Reste glätten: Leerzeichen vor Satzzeichen, Doppel-Leerzeichen, Leerzeilen
    cleaned = _re.sub(r"[ \t]+([.,;:!?])", r"\1", cleaned)
    cleaned = _re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = _re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


_CITE_NUM_RE = _re_cite = __import__("re").compile(r"[\[(]\s*Quellen?\s*([\d,\s]+)")


def _verify_citations(answer: str, sources: list) -> list:
    """Prueft die [Quelle N]-Verweise im Antworttext gegen die tatsaechlich
    vorhandenen Quellen. Gibt die Liste ERFUNDENER/ungueltiger Nummern zurueck
    (N < 1 oder N > Anzahl Quellen) - schuetzt vor falschen Belegangaben."""
    import re as _re2
    n = len(sources or [])
    nums = set()
    for m in _CITE_NUM_RE.finditer(answer or ""):
        for tok in _re2.split(r"[,\s]+", m.group(1).strip()):
            if tok.isdigit():
                nums.add(int(tok))
    return sorted(x for x in nums if x < 1 or x > n)


def _citation_warning(answer: str, sources: list) -> None:
    bad = _verify_citations(answer, sources)
    if bad:
        st.warning("⚠️ Zitat-Prüfung: Die Antwort verweist auf "
                   + ", ".join(f"Quelle {x}" for x in bad)
                   + " – diese Quelle(n) gibt es hier nicht. Bitte die belegten "
                     "Stellen unten selbst gegenprüfen.")


def _render_status_badge(meta: dict) -> None:
    """Status-Badge unter der Antwort. Die Beleg-Prüfung (Faithfulness) läuft nicht
    immer -> nur dann als 'belegte Antwort' auszeichnen, wenn wirklich geprüft
    wurde; sonst neutral 'ungeprüft' (ehrlich)."""
    mode = meta.get("mode")
    # R5: der Graph liefert jetzt ein feineres confidence-Feld
    # ("belegt" | "unsicher" | "ungeprueft" | "fallback"). Eine belegte, aber vom
    # Faithfulness-Check als unsicher eingestufte Antwort wird behalten und ehrlich
    # als "nicht sicher belegt" markiert statt fälschlich grün ausgezeichnet.
    confidence = meta.get("confidence")
    if confidence is None:  # Rückwärtskompat für ältere Nachrichten ohne Feld
        if mode == "answer":
            confidence = "belegt" if meta.get("faith_checked", True) else "ungeprueft"
        else:
            confidence = "fallback"
    if mode == "answer" and confidence == "belegt":
        badge, label = "badge-answer", "belegte Antwort"
    elif mode == "answer" and confidence == "unsicher":
        badge, label = "badge-unsure", "⚠️ nicht sicher belegt"
    elif mode == "answer":
        badge, label = "badge-plain", "⚡ ungeprüft"
    else:
        badge, label = "badge-fallback", "Fallback: passende Dokumente"
    st.markdown(f"<span class='badge {badge}'>{label}</span> "
                f"<span class='small'>· {meta.get('total_time','?')}s</span>",
                unsafe_allow_html=True)


def _save_card_button(question: str, answer: str, meta: dict,
                      sources: "list | None", key: str) -> None:
    """Bietet unter einer belegten Antwort an, sie als Karteikarte zu speichern.
    Der Moment der Frage markiert die echte Wissensluecke - ideal fuer die
    Wiederholung. Nur bei echten (belegten) Antworten, nicht beim Dokument-Fallback."""
    if not question or (meta or {}).get("mode") != "answer":
        return
    if st.button("➕ Als Karteikarte speichern", key=key,
                 help="Legt aus dieser Frage + Antwort eine Karteikarte an "
                      "(üben auf 🎓 Karteikarten)."):
        from ragapp import study
        subj = subject_filter or ((sources or [{}])[0].get("subject") if sources else None)
        cid = study.card_from_chat(question, answer, subject=subj, sources=sources)
        st.toast("📇 Als Karteikarte gespeichert – üben auf 🎓 Karteikarten!"
                 if cid else "Konnte keine Karte anlegen.")


def _save_note_button(question: "str | None", answer: str,
                      sources: "list | None", key: str) -> None:
    """Bietet an, die Antwort als FREIE Notiz zu speichern - im Unterschied zur
    Karteikarte kein Abfrage-Material, sondern editierbarer Ausgangstext zum
    Weiterdenken/Ergänzen. Springt über das Prefill-Muster zur Notizen-Seite."""
    if not (answer or "").strip():
        return
    if st.button("📝 Als Notiz speichern", key=key,
                 help="Öffnet die Notizen-Seite mit dieser Antwort als Ausgangstext."):
        subj = subject_filter or ((sources or [{}])[0].get("subject") if sources else None)
        st.session_state["note_prefill"] = {
            "subject": subj, "title": (question or "").strip()[:80] or None,
            "body": answer,
        }
        st.switch_page("pages/12_🗒️_Notizen.py")


def _followup_chips(idx: int) -> None:
    cols = st.columns(3)
    prompts = (
        ("Einfacher", "Erklär das einfacher, in Alltagsbegriffen."),
        ("Beispiel", "Gib ein konkretes Prüfungsbeispiel dazu."),
        ("Prüfungsfrage", "Formuliere eine typische Klausurfrage dazu und beantworte sie kurz."),
    )
    for col, (label, q) in zip(cols, prompts):
        if col.button(label, key=f"fu_{idx}_{label}"):
            st.session_state["_pending_prompt"] = q
            st.rerun()


def _socratic_chips(idx: int) -> None:
    """Steuerung auf derselben Dialoglinie statt thematisch zu springen."""
    cols = st.columns(4)
    prompts = (
        ("Hinweis", "Gib mir einen Hinweis, ohne die Antwort zu verraten."),
        ("Teilweise", "Ich weiß es teilweise."),
        ("Auflösen", "Löse es auf."),
        ("Nächster Aspekt", "Nächster Aspekt desselben Themas."),
    )
    for col, (label, q) in zip(cols, prompts):
        if col.button(label, key=f"soc_{idx}_{label}"):
            st.session_state["_pending_prompt"] = q
            st.rerun()


def _apply_chat_mascot(*, waiting: bool = False, waiting_stage: str = "retrieve",
                       last_meta: "dict | None" = None,
                       last_content: "str | None" = None,
                       last_user: "str | None" = None) -> None:
    """Setzt die Ecken-Figur auf Chat-Stimmung (Warten oder letzte Antwort)."""
    from ragapp.ui._style import theme_for
    from ragapp.ui._mascot import chat_mood, chat_mood_line, render_mascot_corner
    msgs = st.session_state.get("messages") or []
    if last_meta is None:
        for m in reversed(msgs):
            if m.get("role") == "assistant":
                last_meta = m.get("meta")
                last_content = last_content if last_content is not None else m.get("content")
                break
    if last_user is None:
        for m in reversed(msgs):
            if m.get("role") == "user":
                last_user = m.get("content")
                break
    pose, anim, prop = chat_mood(
        waiting=waiting, empty=not msgs and not waiting,
        chat_mode=_chat_mode, last_meta=last_meta,
        last_content=last_content, last_user=last_user)
    line = chat_mood_line(waiting=waiting, waiting_stage=waiting_stage,
                          chat_mode=_chat_mode)
    icon, bubble = (line if line else ("", None))
    render_mascot_corner(
        theme_for("chat")["accent"], pose=pose, animation=anim, prop=prop,
        bubble=bubble, bubble_icon=icon)


# Verlauf rendern
if st.session_state.pop("_chat_scroll_last", False):
    from ragapp.ui._mascot import _disable_host_iframe_js
    _components.html(
        "<script>" + _disable_host_iframe_js() + """
        var n = 0;
        function toAnswer() {
          try {
            var m = window.parent.document.querySelectorAll('[data-testid="stChatMessage"]');
            if (m.length) { m[m.length - 1].scrollIntoView({block: 'start'}); }
          } catch (e) {}
          if (++n < 6) setTimeout(toAnswer, 280);
        }
        setTimeout(toAnswer, 250);
        </script>
        """,
        height=0,
    )
for _mi, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"], avatar="🧑‍🎓" if msg["role"] == "user" else "🤖"):
        st.markdown(msg["content"] if show_sources else _strip_source_labels(msg["content"]))
        if msg.get("meta"):
            _render_status_badge(msg["meta"])
            if show_sources:
                _citation_warning(msg["content"], msg.get("sources") or [])
            _prev = st.session_state.messages[_mi - 1] if _mi > 0 else {}
            _q = _prev.get("content") if _prev.get("role") == "user" else None
            _save_card_button(_q, msg["content"], msg.get("meta"), msg.get("sources"),
                              key=f"card_h{_mi}")
            _save_note_button(_q, msg["content"], msg.get("sources"), key=f"note_h{_mi}")
            if _chat_mode == "sokratisch":
                if _mi == len(st.session_state.messages) - 1:
                    _socratic_chips(_mi)
            else:
                _followup_chips(_mi)
        if msg.get("sources"):
            if (msg.get("meta") or {}).get("mode") == "fallback":
                st.caption("Keine sichere Antwort – Stelle unten nachlesen.")
            render_sources(msg["sources"], key_prefix=f"h{_mi}")


def _socratic_topic_suggestions(subject: "str | None") -> list[str]:
    from ragapp.graph.socratic import (
        collect_socratic_topic_suggestions, pdf_toc_titles, read_source_text,
    )
    cards = manifest.list_cards(subject=subject, limit=40)
    docs = [dict(d) for d in manifest.list_documents()]
    extras: list[str] = []
    for d in docs:
        if subject and d.get("subject") != subject:
            continue
        extras.extend(pdf_toc_titles(str(d.get("source_path") or ""), root=PROJECT_ROOT))
    return collect_socratic_topic_suggestions(
        cards=cards, documents=docs, subject=subject,
        read_text=lambda p: read_source_text(p, root=PROJECT_ROOT),
        extra_headings=extras,
        limit=9,
    )


def _start_socratic_dialog(topic: str) -> None:
    from ragapp.graph.prompts import SOKRATISCH_START_USER
    topic = (topic or "").strip()
    if not topic:
        return
    st.session_state["socratic_topic"] = topic
    st.session_state.pop("_socratic_pick_again", None)
    st.session_state["_pending_prompt"] = SOKRATISCH_START_USER.format(topic=topic)
    # Ein kurzer Rerun ohne LLM, damit die Startkarte weg ist, bevor die
    # Generierung die Seite lange blockiert (sonst bleiben die Picker-Widgets
    # während des Wartens sichtbar und deaktiviert).
    st.session_state["_socratic_boot"] = True
    st.rerun()


def _render_socratic_start() -> None:
    """Leerer sokratischer Chat: erst das Thema, dann der Dialog – ohne Pflicht,
    irgendetwas ins Eingabefeld zu tippen."""
    with card("socratic_start"):
        st.markdown("##### Worum soll der Dialog gehen?")
        st.caption(
            "Erst das Thema festlegen. Danach bleibt das Gespräch auf einer Linie: "
            "eine Frage, deine Antwort, ein Hinweis oder die nächste Vertiefung – "
            "kein Sprung zu einem Nachbar-Thema.")
        with st.form("socratic_start_form", clear_on_submit=False):
            topic = st.text_input(
                "Thema", key="socratic_topic_input",
                placeholder="z. B. Schutzziele der Informationssicherheit")
            started = st.form_submit_button("Dialog starten", type="primary")
        if started:
            if not (topic or "").strip():
                st.warning("Bitte zuerst ein Thema eintragen – oder unten einen Vorschlag wählen.")
            else:
                _start_socratic_dialog(topic)
        suggestions = _socratic_topic_suggestions(subject_filter)
        if suggestions:
            st.caption("Vorschläge aus deinen Unterlagen:")
            cols = st.columns(3)
            for i, name in enumerate(suggestions):
                if cols[i % 3].button(name, key=f"soc_sug_{i}",
                                      use_container_width=True):
                    _start_socratic_dialog(name)
        else:
            st.caption("Keine Vorschläge aus den Unterlagen – tippe den Begriff "
                       "ins Feld oder unten in die Eingabe.")


def _render_onboarding() -> None:
    """Leerer Chat: klickbare Beispiel-Fragen, bei Fachfilter aus dem Stoff."""
    from ragapp.graph.socratic import chat_onboarding_questions
    _label = (SUBJECT_LABELS.get(subject_filter, subject_filter)
              if subject_filter else None)
    _topics = _socratic_topic_suggestions(subject_filter)
    questions = chat_onboarding_questions(_topics, subject_label=_label)
    with card("onboarding"):
        st.markdown("<span class='small'>Neu hier? Starte mit einer dieser Fragen "
                    "– oder tippe unten einfach deine eigene:</span>",
                    unsafe_allow_html=True)
        cols = st.columns(len(questions))
        for _i, (_col, _q) in enumerate(zip(cols, questions)):
            if _col.button(_q, key=f"example_{_i}", use_container_width=True):
                st.session_state["_pending_prompt"] = _q
                st.rerun()


def _friendly_error(exc: Exception) -> str:
    """Übersetzt eine rohe Exception in eine verständliche Meldung. Nutzt die
    Diagnose-Funktion aus llm.py, falls vorhanden; sonst eine generische,
    freundliche Meldung (nie der nackte Traceback-Text)."""
    try:
        from ragapp.llm import diagnose_error  # type: ignore[attr-defined]
        msg = diagnose_error(exc)
        if msg:
            return str(msg)
    except Exception:  # noqa: BLE001 - Diagnose optional; nie hart abstürzen
        pass
    return ("⚠️ Da ist gerade etwas schiefgelaufen. Bitte versuche es in einem "
            "Moment noch einmal. Falls es bestehen bleibt: Läuft Ollama, und ist "
            "unter ⚙️ Einstellungen das richtige Modell geladen?")


# Leerer Chat + vorhandene Dokumente -> Einstieg (sokratisch: erst Thema).
# Slot bleibt in JEDEM Rerun stehen, damit die Startkarte sofort leergeräumt
# wird – nicht erst nach der langen LLM-Antwort (sonst bleibt sie deaktiviert
# sichtbar). _pending_prompt / socratic_topic: Dialog schon gestartet.
_incoming = bool(st.session_state.get("_pending_prompt"))
_socratic_started = bool(st.session_state.get("socratic_topic"))
_pick_again = bool(st.session_state.get("_socratic_pick_again"))
_intro_slot = st.empty()
if (stats["chunks"] > 0 and not _incoming and not _socratic_started
        and (_pick_again or not st.session_state.messages)):
    with _intro_slot.container():
        if _chat_mode == "sokratisch":
            _render_socratic_start()
        elif not st.session_state.messages:
            _render_onboarding()

_vs_flash = st.session_state.pop("_verstehen_flash", None)
if _vs_flash:
    st.success(_vs_flash)

if _chat_mode == "sokratisch" and st.session_state.get("socratic_topic"):
    _topic_now = st.session_state["socratic_topic"]
    _vs_sess = st.session_state.get("verstehen_session") or {}
    if _vs_sess.get("topic") == _topic_now:
        _left = max(0, int(_vs_sess.get("minutes") or 20) - int(
            (time.time() - float(_vs_sess.get("started_at") or time.time())) / 60))
        st.info(f"Verstehen-Sitzung · **{_topic_now}** · noch etwa {_left} Min")
        _has_msgs = bool(st.session_state.get("messages"))
        _pending = bool(st.session_state.get("_pending_prompt"))
        _end_clicked = False
        if not _has_msgs and not _pending:
            _c_go, _c_end = st.columns(2)
            with _c_go:
                if st.button("Los geht’s", type="primary", key="verstehen_los",
                             use_container_width=True):
                    _start_socratic_dialog(_topic_now)
            with _c_end:
                _end_clicked = st.button(
                    "Sitzung beenden – Notiz + Karten",
                    key="verstehen_end", use_container_width=True)
        else:
            _end_clicked = st.button(
                "Sitzung beenden – Notiz + Karten",
                key="verstehen_end", use_container_width=True)
        if _end_clicked:
            from ragapp import student_flow as _sf
            _out = _sf.finish_verstehen_session(
                st.session_state.get("messages") or [],
                topic=_topic_now,
                subject=str(_vs_sess.get("subject") or "") or None,
                started_at=float(_vs_sess.get("started_at") or time.time()),
                minutes=int(_vs_sess.get("minutes") or 20),
            )
            st.session_state.pop("verstehen_session", None)
            _n = 1 if _out.get("note_id") else 0
            _k = len(_out.get("card_ids") or [])
            st.session_state["_verstehen_flash"] = (
                f"Notiz + {_k} Karte(n) gespeichert" if (_n or _k)
                else "Sitzung beendet")
            if not st.session_state.get("messages"):
                st.session_state.pop("socratic_topic", None)
                st.session_state["_socratic_pick_again"] = True
            st.rerun()
    else:
        _tb1, _tb2 = st.columns([4, 1])
        _tb1.caption(f"🧭 Thema: **{_topic_now}**")
        if _tb2.button("Neues Thema", key="soc_reset_topic",
                       help="Nächste Dialoglinie – der Verlauf bleibt."):
            st.session_state.pop("socratic_topic", None)
            st.session_state["_socratic_pick_again"] = True
            st.rerun()


# --------------------------------------------------------------------------- #
# Eingabe
# --------------------------------------------------------------------------- #
_chat_ph = "Stelle eine Frage zu deinem Lernstoff …"
if _chat_mode == "sokratisch":
    _chat_ph = ("Deine Antwort zum Thema …"
                if st.session_state.get("socratic_topic")
                else "Oder tippe hier das Thema …")
prompt = st.chat_input(_chat_ph)
# Leerer Chat: oben bleiben (Beispiel-Fragen, Filter), nicht zur Eingabe springen.
if (not st.session_state.messages
        and not st.session_state.get("_pending_prompt")
        and not prompt):
    from ragapp.ui._mascot import _disable_host_iframe_js as _chat_disable_iframe
    _components.html(
        "<script>" + _chat_disable_iframe() + """
        (function () {
          try {
            var win = window.parent, doc = win.document;
            if (doc.querySelector('[data-testid="stChatMessage"]')) return;
            function pinTop() {
              try {
                var ta = doc.querySelector('[data-testid="stChatInputTextArea"]')
                  || doc.querySelector('[data-testid="stChatInput"] textarea');
                if (ta && doc.activeElement === ta) ta.blur();
                var menu = null;
                var buttons = doc.querySelectorAll('button');
                for (var i = 0; i < buttons.length; i++) {
                  if ((buttons[i].innerText || '').indexOf('Menü') >= 0) {
                    menu = buttons[i]; break;
                  }
                }
                var target = menu || doc.querySelector('h1');
                if (target) target.scrollIntoView({block: 'start', inline: 'nearest'});
              } catch (e) {}
            }
            pinTop();
            var n = 0;
            var iv = win.setInterval(function () {
              pinTop();
              if (++n >= 8) win.clearInterval(iv);
            }, 180);
          } catch (e) {}
        })();
        </script>
        """,
        height=0,
    )
if st.session_state.pop("_socratic_boot", False):
    st.rerun()
# Klick auf eine Beispiel-Frage (Onboarding) wirkt wie eine getippte Eingabe.
if not prompt:
    prompt = st.session_state.pop("_pending_prompt", None)

if not prompt:
    _apply_chat_mascot(waiting=False)
else:
    _wait_stage = ("load" if not st.session_state.get("_first_query_done")
                   else "retrieve")
    _apply_chat_mascot(waiting=True, waiting_stage=_wait_stage)
    if (_chat_mode == "sokratisch" and not st.session_state.get("socratic_topic")
            and not st.session_state.messages):
        st.session_state["socratic_topic"] = prompt.strip().splitlines()[0][:120]
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑‍🎓"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="🤖"):
        # Beim allerersten Query werden die Modelle ggf. noch geladen (~einmalig,
        # bis zu ~20 s). Ehrliches Erwartungsmanagement statt stiller Wartezeit.
        _first_query = not st.session_state.get("_first_query_done")
        if _first_query:
            _wait_retrieve = "Modelle werden einmalig geladen, danach Suche in den Unterlagen …"
            _wait_generate = "Formuliere Antwort …"
        elif _chat_mode == "sokratisch":
            _wait_retrieve = "Suche im vereinbarten Thema …"
            _wait_generate = "Formuliere die nächste Dialogfrage …"
        else:
            _wait_retrieve = "Suche in deinen Unterlagen …"
            _wait_generate = "Formuliere Antwort …"

        result = None
        _streamed = False

        # --- Pre-Flight: genug freier Grafikspeicher (VRAM) fuer das Modell? ------
        # Nur entladen, wenn das Chat-Modell NICHT schon resident ist. Sonst
        # zahlen wir den Reload und der VRAM-Check sieht kurz „zu wenig frei“.
        from ragapp.llm import release_llm, vram_preflight, model_status
        _ms_now = model_status()
        if not _ms_now.get("resident"):
            release_llm()
        _pf = vram_preflight()
        _vram_low = _pf.get("status") == "low"
        if _vram_low:
            _vram_msg = (
                f"⚠️ **Zu wenig freier Grafikspeicher (VRAM).** Aktuell sind nur "
                f"**{_pf.get('free_gb')} GB frei**, aber das Modell "
                f"`{_pf.get('model')}` braucht ~**{_pf.get('need_gb')} GB**.\n\n"
                f"Bitte schließe andere GPU-Programme (z. B. eine zweite KI-/Grafik-App) "
                f"und stelle die Frage dann **erneut**.\n\n"
                f"_(Sonst müsste die Antwort auf der CPU laufen und würde mehrere "
                f"Minuten dauern.)_")
            st.warning(_vram_msg)
            result = {"answer": _vram_msg, "mode": "vram_warn", "sources": [],
                      "total_time": 0}
            _streamed = True
            _apply_chat_mascot(waiting=False, last_meta={"mode": "vram_warn"},
                               last_user=prompt)

        from ragapp.graph.rag_graph import answer_query, answer_query_stream

        # Tutor/Sokratisch: Faithfulness aus (Synthese), Streaming erlaubt
        _faith_for_call = False if _chat_mode != "strict" else check_faith_ui
        _soc_topic = (st.session_state.get("socratic_topic")
                      if _chat_mode == "sokratisch" else None)

        _status_box = None if _vram_low else st.status(_wait_retrieve, expanded=True)

        def _on_stage(name: str) -> None:
            if _status_box is None:
                return
            if name == "generate":
                _status_box.update(label=_wait_generate)
                _apply_chat_mascot(waiting=True, waiting_stage="generate",
                                   last_user=prompt)
            else:
                _status_box.update(label=_wait_retrieve)
                _apply_chat_mascot(waiting=True, waiting_stage="retrieve",
                                   last_user=prompt)

        # Schnell-Modus (Gegenprüfung AUS) / Tutor UND Quellen-Anzeige AN -> streamen
        if not _vram_low and _faith_for_call is False:
            try:
                _stream, _holder = answer_query_stream(
                    prompt, subject=subject_filter,
                    use_reranker=use_reranker_ui,
                    check_faithfulness=_faith_for_call,
                    history=st.session_state.messages[:-1],
                    chat_mode=_chat_mode,
                    include_notes=bool(st.session_state.get("chat_include_notes")),
                    socratic_topic=_soc_topic,
                    on_stage=_on_stage)
            except Exception:  # noqa: BLE001 - Setup-Fehler -> blockierender Fallback
                _stream, _holder = None, {}
            if _stream is not None:
                try:
                    st.write_stream(_stream)   # rendert Token für Token
                    result = _holder or {}
                    _streamed = True
                except Exception as exc:  # noqa: BLE001 - Stream-Fehler nie roh anzeigen
                    # Bereits gestreamter Text bleibt sichtbar; Rest als Ergebnis führen.
                    result = _holder or {"answer": _friendly_error(exc),
                                         "mode": "fallback", "sources": [],
                                         "total_time": 0}
                    _streamed = True

        # Nicht-Stream-Pfad (strenger Modus, Quellen aus, oder Streaming nicht möglich).
        if result is None:
            _on_stage("retrieve")
            try:
                result = answer_query(prompt, subject=subject_filter,
                                      use_reranker=use_reranker_ui,
                                      check_faithfulness=_faith_for_call,
                                      history=st.session_state.messages[:-1],
                                      chat_mode=_chat_mode,
                                      include_notes=bool(st.session_state.get("chat_include_notes")),
                                      socratic_topic=_soc_topic)
            except Exception as exc:  # noqa: BLE001 - rohe Fehler nie roh anzeigen
                result = {"answer": _friendly_error(exc), "mode": "fallback",
                          "sources": [], "total_time": 0}

        if _status_box is not None:
            _ok = (result or {}).get("mode") != "fallback"
            _status_box.update(label="Fertig" if _ok else "Keine sichere Antwort",
                               state="complete" if _ok else "error")
        st.session_state["_first_query_done"] = True
        _answer = result.get("answer", "")
        # Im Stream-Pfad ist die Antwort bereits gerendert (st.write_stream); sonst
        # hier nachziehen (bei ausgeschalteter Quellen-Anzeige [Quelle N] entfernen).
        if not _streamed:
            st.markdown(_answer if show_sources else _strip_source_labels(_answer))
        if _vram_low:
            # VRAM-Warnung: kein Status-Badge / keine Quellen / keine Karten-Aktion
            # (leeres meta -> der History-Renderer zeigt ebenfalls kein Badge).
            meta = {}
            sources = []
        else:
            meta = {"mode": result.get("mode"), "total_time": result.get("total_time"),
                    "faith_checked": result.get("faith_checked", True),
                    "confidence": result.get("confidence")}
            _render_status_badge(meta)
            if show_sources:
                _citation_warning(_answer, result.get("sources", []))
            sources = result.get("sources", []) if show_sources else []
            if sources:
                render_sources(sources, key_prefix="new")
            _save_card_button(prompt, _answer, meta, sources, key="card_new")
            _save_note_button(prompt, _answer, sources, key="note_new")
            if _chat_mode == "sokratisch":
                _socratic_chips("new")
            else:
                _followup_chips("new")
            _apply_chat_mascot(
                waiting=False, last_meta=meta, last_content=_answer, last_user=prompt)

    st.session_state.messages.append({
        "role": "assistant",
        "content": result.get("answer", ""),
        "meta": meta,
        "sources": sources,
    })

    # Verlauf dauerhaft speichern (siehe manifest.chat_sessions) - beim ALLER-
    # ERSTEN gespeicherten Austausch eines neuen Chats wird die Sitzung jetzt
    # angelegt (Titel aus der ersten Frage), sonst nur aktualisiert. Die
    # "pending choice" sorgt dafuer, dass die Auswahlbox oben beim NAECHSTEN
    # Rerun automatisch auf die neue Sitzung zeigt (siehe Muster in
    # 15_🎧_Audio-Overview.py).
    if _active_session_id is None:
        _title = prompt.strip().splitlines()[0][:60] or "Neuer Chat"
        if _chat_mode == "sokratisch" and st.session_state.get("socratic_topic"):
            _title = st.session_state["socratic_topic"].strip()[:60] or _title
        if len(prompt.strip()) > 60 and _title == prompt.strip()[:60]:
            _title += "…"
        _new_sid = manifest.create_chat_session(
            title=_title, subject=subject_filter, messages=st.session_state.messages)
        st.session_state["_chat_pending_choice"] = _new_sid
        st.session_state["_chat_loaded_session_id"] = _new_sid
    else:
        manifest.update_chat_session(_active_session_id, messages=st.session_state.messages)

    # Stabiler Rerun: Chips/Speichern liegen im Verlauf, Scroll-Iframe oben –
    # nicht über den Buttons am Ende der Generierung.
    st.session_state["_chat_scroll_last"] = True
    st.rerun()
