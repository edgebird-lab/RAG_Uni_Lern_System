"""
RAG-Lernsystem: Chat-Oberfläche (Streamlit)
============================================
Start:  streamlit run ragapp/ui/Home.py
"""
from __future__ import annotations

import sys
import html
import random
import pathlib

# Projektwurzel auffindbar machen (damit 'ragapp' importierbar ist)
_p = pathlib.Path(__file__).resolve()
for _anc in _p.parents:
    if (_anc / "ragapp").is_dir():
        sys.path.insert(0, str(_anc))
        break

import streamlit as st

from ragapp.config import settings, SUBJECT_LABELS, PROJECT_ROOT
from ragapp import manifest

# App-Icon (Fenster/Taskleiste/Favicon). Faellt auf ein Emoji zurueck,
# falls die Icon-Datei fehlt (z. B. vor dem ersten Build).
_icon_png = _p.parents[2] / "assets" / "icon.png"
_PAGE_ICON = str(_icon_png) if _icon_png.is_file() else "🎓"

st.set_page_config(page_title="RAG-Lernsystem", page_icon=_PAGE_ICON, layout="wide")

# Schwere Importe (torch/chromadb) im Hintergrund vorwärmen -> spätere
# Seitenwechsel öffnen sofort statt mit weißem Bildschirm. Reine Optimierung.
from ragapp.ui._loading import prewarm
prewarm("ragapp.retrieval.embeddings",
        "ragapp.retrieval.vectorstore",
        "ragapp.ingestion.pipeline")

# Tab-Close-Waechter: beendet die App sauber, wenn kein Browser-Tab mehr offen ist
# (nur aktiv im lokalen Starter-Betrieb via start.sh -> RAG_IDLE_SHUTDOWN=1).
from ragapp.ui._shutdown_watchdog import ensure_shutdown_watchdog
ensure_shutdown_watchdog()

# Automatischer Lernstand-Snapshot beim Start (nur, wenn der letzte > 24 h alt ist).
if not st.session_state.get("_backup_checked"):
    st.session_state["_backup_checked"] = True
    try:
        from ragapp import backup
        backup.snapshot_if_stale("autostart")
    except Exception:  # noqa: BLE001
        pass

# Netzwerk-/Handy-Zugriff: PIN-Sperre (nur im Netzwerkmodus aktiv, sonst wirkungslos)
from ragapp.ui._auth import require_pin
require_pin()

# PWA: Manifest + Apple-Meta in den echten Seitenkopf injizieren UND ein
# Installations-Banner ("Als App aufs Handy") anbieten - nur auf dem Handy (nicht am
# PC-Fenster) und nur, wenn noch nicht installiert. Android/Chrome: echter
# Installieren-Button ueber 'beforeinstallprompt'. iOS/Safari: Kurzanleitung.
import streamlit.components.v1 as _components
_components.html(
    """
    <script>
    (function () {
      try {
        var pwin = window.parent, pdoc = pwin.document, head = pdoc.head;
        function add(tag, attrs) {
          var el = pdoc.createElement(tag);
          for (var k in attrs) { el.setAttribute(k, attrs[k]); }
          head.appendChild(el);
        }
        if (!head.querySelector('link[rel="manifest"]')) {
          add('link', {rel: 'manifest', href: 'app/static/manifest.json'});
          add('meta', {name: 'apple-mobile-web-app-capable', content: 'yes'});
          add('meta', {name: 'mobile-web-app-capable', content: 'yes'});
          add('meta', {name: 'apple-mobile-web-app-status-bar-style', content: 'black-translucent'});
          add('meta', {name: 'apple-mobile-web-app-title', content: 'Lernsystem'});
          add('meta', {name: 'theme-color', content: '#12455a'});
          add('link', {rel: 'apple-touch-icon', href: 'app/static/icon-180.png'});
        }
        if ('serviceWorker' in pwin.navigator) {
          pwin.navigator.serviceWorker.register('app/static/sw.js').catch(function () {});
        }

        // Banner NUR auf dem Handy: das PC-Fenster hat das lokale Token.
        var isPC = false;
        try { isPC = !!pwin.localStorage.getItem('rag_local_token'); } catch (e) {}
        var standalone = (pwin.matchMedia && pwin.matchMedia('(display-mode: standalone)').matches)
                         || pwin.navigator.standalone === true;
        if (isPC || standalone) return;
        // Installieren nur bei STABILER Adresse anbieten (WLAN/LAN, localhost) - NICHT
        // bei der wechselnden Cloudflare-Adresse (dort waere das Icon morgen tot).
        var host = pwin.location.hostname || '';
        var isLan = (host === 'localhost') || (host.slice(-6) === '.local')
          || (host.indexOf('192.168.') === 0) || (host.indexOf('10.') === 0)
          || (host.indexOf('172.') === 0 && (function () {
               var o = parseInt(host.split('.')[1], 10); return o >= 16 && o <= 31; })());
        if (!isLan) return;
        if (pwin.__ragPwaInit) return; pwin.__ragPwaInit = true;   // Listener nur einmal binden

        function banner(inner) {
          var old = pdoc.getElementById('rag-pwa'); if (old) old.remove();
          var b = pdoc.createElement('div'); b.id = 'rag-pwa';
          b.style.cssText = 'position:fixed;left:12px;right:12px;bottom:14px;margin:0 auto;'
            + 'max-width:520px;z-index:2147483647;background:#12455a;color:#fff;border-radius:14px;'
            + 'padding:12px 14px;box-shadow:0 10px 34px rgba(0,0,0,.4);font-family:system-ui,'
            + '-apple-system,sans-serif;font-size:14px;line-height:1.35;display:flex;'
            + 'align-items:center;gap:10px;';
          b.innerHTML = inner;
          var x = pdoc.createElement('button'); x.textContent = '\\u2715';
          x.style.cssText = 'margin-left:auto;background:transparent;border:0;color:#bcd7df;'
            + 'font-size:17px;cursor:pointer;flex:none;';
          x.onclick = function () { b.remove(); };
          b.appendChild(x);
          pdoc.body.appendChild(b); return b;
        }

        var deferred = null;
        pwin.addEventListener('beforeinstallprompt', function (e) {
          e.preventDefault(); deferred = e;
          var b = banner('<span style="font-size:20px">\\uD83D\\uDCF2</span>'
                         + '<span>Als App aufs Handy installieren?</span>');
          var btn = pdoc.createElement('button'); btn.textContent = 'Installieren';
          btn.style.cssText = 'background:#fff;color:#12455a;border:0;border-radius:9px;'
            + 'padding:7px 15px;font-weight:600;cursor:pointer;flex:none;';
          btn.onclick = function () {
            b.remove();
            if (deferred) { deferred.prompt(); deferred.userChoice.finally(function () { deferred = null; }); }
          };
          b.insertBefore(btn, b.lastChild);
        });
        pwin.addEventListener('appinstalled', function () {
          var b = pdoc.getElementById('rag-pwa'); if (b) b.remove();
        });

        // Nach kurzem Warten: falls KEIN Installieren-Button kam (kein
        // 'beforeinstallprompt' - z. B. iOS/Safari oder Android ueber http) -> Anleitung.
        var ua = pwin.navigator.userAgent || '';
        var isIOS = /iphone|ipad|ipod/i.test(ua);
        pwin.setTimeout(function () {
          if (pdoc.getElementById('rag-pwa')) return;   // Button-Banner ist schon da
          if (isIOS) {
            banner('<span style="font-size:20px">\\uD83D\\uDCF2</span>'
                   + '<span>Als App installieren: unten auf das <b>Teilen</b>-Symbol '
                   + 'tippen, dann <b>Zum Home-Bildschirm</b>.</span>');
          } else {
            banner('<span style="font-size:20px">\\uD83D\\uDCF2</span>'
                   + '<span>Als App installieren: im Browser-Men&uuml; (&#8942;) auf '
                   + '<b>Zum Startbildschirm hinzuf&uuml;gen</b> tippen.</span>');
          }
        }, 2200);
      } catch (e) {}
    })();
    </script>
    """,
    height=0,
)

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
.block-container {padding-top: 2rem; padding-bottom: 6rem; max-width: 1100px;}
/* Aufklapp-Listen (z. B. Fach-Dropdown) in der Hoehe begrenzen und scrollbar
   machen, damit sie nie unten aus dem Fenster / hinter die Taskleiste laufen. */
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

    # Zwei getrennte Tempo-/Genauigkeits-Schalter (pro Anfrage, überschreiben die
    # globalen Einstellungen nur für die aktuelle Sitzung). Beides AUS = schnellste
    # Antworten. Startwert = die gespeicherte globale Einstellung.
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


def _load_full_text(src: dict) -> "str | None":
    """Volltext des Quell-Dokuments laden (aus der Originaldatei)."""
    sp = src.get("source_path", "")
    if not sp:
        return None
    path = PROJECT_ROOT / sp
    if not path.is_file():
        return None
    try:
        from ragapp.ingestion.loaders import load_document
        return load_document(path).text
    except Exception:
        return None


def _locate(full: str, chunk: str) -> "tuple[int, int]":
    """Textstelle im Volltext finden - robust auch bei Markdown (der Chunk hat dort
    einen Breadcrumb-Präfix, der so nicht im Original steht)."""
    if chunk:
        i = full.find(chunk[:200])
        if i >= 0:
            return i, min(i + len(chunk), len(full))
    # Anker: längste inhaltliche Zeilen des Chunks, die im Volltext vorkommen
    cands = sorted((ln.strip() for ln in (chunk or "").split("\n") if len(ln.strip()) >= 20),
                   key=len, reverse=True)
    for c in cands[:10]:
        i = full.find(c)
        if i >= 0:
            return i, min(i + len(chunk), len(full))
    return -1, -1


def _render_pdf_page(src: dict, page_num: int, chunk: str) -> "bytes | None":
    """Rendert die ECHTE PDF-Seite als Bild mit gemaltem Highlight auf der gefundenen
    Stelle (Layout, Formeln, Diagramme bleiben lesbar; aktiviert räumliches Gedächtnis
    als Abrufhinweis). Gibt PNG-Bytes zurück oder None. CPU-only, offline (fitz)."""
    path = PROJECT_ROOT / (src.get("source_path") or "")
    if not path.is_file():
        return None
    try:
        import fitz  # PyMuPDF (bereits Abhängigkeit der Loader)
        doc = fitz.open(str(path))
        if page_num < 1 or page_num > doc.page_count:
            return None
        page = doc.load_page(page_num - 1)
        anchors = sorted((ln.strip() for ln in (chunk or "").split("\n")
                          if len(ln.strip()) >= 15), key=len, reverse=True)[:6]
        for a in anchors:
            try:
                for rect in page.search_for(a[:90]):
                    page.add_highlight_annot(rect)
            except Exception:  # noqa: BLE001
                pass
        return page.get_pixmap(dpi=140).tobytes("png")
    except Exception:  # noqa: BLE001
        return None


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
        _png = _render_pdf_page(src, int(_m.group(1)), chunk)
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
    start, end = _locate(full, chunk)
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
    if mode == "answer" and meta.get("faith_checked", True):
        badge, label = "badge-answer", "belegte Antwort"
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
                      "(üben auf der Seite 🎓 Lernen)."):
        from ragapp import study
        subj = subject_filter or ((sources or [{}])[0].get("subject") if sources else None)
        cid = study.card_from_chat(question, answer, subject=subj, sources=sources)
        st.toast("📇 Als Karteikarte gespeichert – üben auf 🎓 Lernen!"
                 if cid else "Konnte keine Karte anlegen.")


# Verlauf rendern
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
        if msg.get("sources"):
            render_sources(msg["sources"], key_prefix=f"h{_mi}")


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
                result = answer_query(prompt, subject=subject_filter,
                                      use_reranker=use_reranker_ui,
                                      check_faithfulness=check_faith_ui,
                                      history=st.session_state.messages[:-1])
            except Exception as exc:
                result = {"answer": f"⚠️ Fehler: {exc}", "mode": "fallback",
                          "sources": [], "total_time": 0}
        _answer = result.get("answer", "")
        st.markdown(_answer if show_sources else _strip_source_labels(_answer))
        meta = {"mode": result.get("mode"), "total_time": result.get("total_time"),
                "faith_checked": result.get("faith_checked", True)}
        _render_status_badge(meta)
        if show_sources:
            _citation_warning(_answer, result.get("sources", []))
        sources = result.get("sources", []) if show_sources else []
        if sources:
            render_sources(sources, key_prefix="new")

    st.session_state.messages.append({
        "role": "assistant",
        "content": result.get("answer", ""),
        "meta": meta,
        "sources": sources,
    })

    # Nach dem Generieren an den ANFANG der Antwort scrollen (mehrfach, um Streamlits
    # Auto-Scroll ans Ende zu ueberstimmen).
    _components.html(
        """
        <script>
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
