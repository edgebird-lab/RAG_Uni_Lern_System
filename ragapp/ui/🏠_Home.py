"""
RAG-Lernsystem: Home (Streamlit-Einstiegspunkt)
==================================================
Start:  streamlit run ragapp/ui/🏠_Home.py

Diese Datei ist weiterhin der tatsaechliche Prozess-Einstiegspunkt (start.sh /
ragapp/desktop.py starten sie namentlich) - deshalb bleiben Prewarm/Watchdog/
Backup-Snapshot/PWA-Banner hier. Inhaltlich zeigt sie jetzt aber die Home-
Kachel-Uebersicht statt der Chat-Oberflaeche; die ist nach
``pages/0_💬_Chat.py`` umgezogen (siehe dort).
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

# App-Icon (Fenster/Taskleiste/Favicon). Faellt auf ein Emoji zurueck,
# falls die Icon-Datei fehlt (z. B. vor dem ersten Build).
_icon_png = _p.parents[2] / "assets" / "icon.png"
_PAGE_ICON = str(_icon_png) if _icon_png.is_file() else "🎓"

st.set_page_config(page_title="RAG-Lernsystem", page_icon=_PAGE_ICON, layout="wide")

# Schwere Importe (torch/chromadb) im Hintergrund vorwärmen -> spätere
# Seitenwechsel öffnen sofort statt mit weißem Bildschirm, UND Embedding+Reranker
# schon einmal ins RAM/VRAM laden, damit die erste echte Frage nicht den Kaltstart
# zahlt. Per Einstellung abschaltbar (PREWARM_ON_START) - wer die Sitzung nur zum
# Karteikarten-Lernen oeffnet, will dafuer gar kein Modell laden.
from ragapp.config import settings
if settings.PREWARM_ON_START:
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

# Einheitliches Theme (idempotent) - direkt nach der PIN-Sperre anwenden.
from ragapp.ui._theme import apply_theme
apply_theme()

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

# --------------------------------------------------------------------------- #
# Home-Kachel-Uebersicht - die eigentliche Navigation der App (Hamburger-Menue
# links ist nur die Kurzwahl der 4 meistgenutzten Seiten). Ein Klick auf eine
# Kachel springt direkt zur jeweiligen Seite (st.switch_page, siehe
# ragapp.ui._style.render_nav_tile) - PAGE_REGISTRY dort ist die einzige
# Quelle der Wahrheit fuer Titel/Icon/Zielpfad/Gruppierung.
# --------------------------------------------------------------------------- #
from ragapp.ui._style import apply_page_style, PAGE_REGISTRY, render_nav_tile, render_hero_title, card
_theme = apply_page_style("home")

render_hero_title("Willkommen zurück 👋", accent=_theme["accent"])
st.markdown(
    "<span style='opacity:.72'>Wähle unten einen Bereich – oder nutze das "
    "☰-Menü links für die Kurzwahl.</span>", unsafe_allow_html=True)

with st.spinner("Wird geladen ..."):
    from ragapp import manifest

try:
    _stats = manifest.stats()
    with card("stats"):
        _s1, _s2, _s3, _s4 = st.columns(4)
        _s1.metric("📄 Dokumente", _stats["documents"])
        _s2.metric("🧩 Textstellen", _stats["chunks"])
        _s3.metric("❓ Fragen", _stats["questions"])
        _s4.metric("🏷️ Fächer", _stats["subjects"])
except Exception:  # noqa: BLE001 - Statistik ist ein Bonus, nie blockierend
    pass

st.write("")

_categories: list[str] = []
for _pg in PAGE_REGISTRY:
    if _pg["category"] and _pg["category"] not in _categories:
        _categories.append(_pg["category"])

for _cat in _categories:
    st.markdown(f"#### {_cat}")
    _pages_in_cat = [p for p in PAGE_REGISTRY if p["category"] == _cat]
    _cols = st.columns(3)
    for _i, _pg in enumerate(_pages_in_cat):
        with _cols[_i % 3]:
            render_nav_tile(_pg["key"])
    st.write("")
