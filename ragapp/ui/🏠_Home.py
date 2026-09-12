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
from ragapp.ui._style import (apply_page_style, PAGE_REGISTRY, render_nav_tile,
                               render_hero_title, card, speech_bubble)
from ragapp.ui._mascot import render_mascot
_theme = apply_page_style("home")

_hero_l, _hero_r = st.columns([3, 1])
with _hero_l:
    render_hero_title("Willkommen zurück 👋", accent=_theme["accent"])
    speech_bubble("Wähle unten einen Bereich – oder nutze das ☰-Menü links für die Kurzwahl.",
                  icon="✨")
with _hero_r:
    render_mascot(_theme["accent"], pose="cheer", animation="wave")

# --------------------------------------------------------------------------- #
# "Heute"-Briefing: das Wichtigste des Tages auf einen Blick, statt es sich aus
# fuenf Seiten (Lernen/Fortschritt/Lernplan/Organisation/Lernzeit) zusammen-
# suchen zu muessen. Nutzt dieselbe planner.today_snapshot()-Funktion wie
# Organisation's "Heute im Blick" (siehe dort) - damit laufen die Zahlen nie
# auseinander. Rein informativ/optional: schlaegt fehl -> Karte wird einfach
# uebersprungen, blockiert nie den Rest der Seite.
# --------------------------------------------------------------------------- #
try:
    import datetime as _dt
    from html import escape as _html_escape
    from ragapp import planner
    from ragapp.config import SUBJECT_LABELS

    _snap = planner.today_snapshot()
except Exception:  # noqa: BLE001
    _snap = None

if _snap:
    _WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag",
                   "Samstag", "Sonntag"]
    _today = _dt.date.today()

    with card("heute"):
        st.markdown(f"#### 🌞 Heute · {_WOCHENTAGE[_today.weekday()]}, "
                    f"{_today.strftime('%d.%m.%Y')}")

        # Cram-Modus: kurz vor der Klausur bekommt die Seite bewusst eine
        # dringlichere Note statt einer weiteren Chip zwischen den anderen -
        # das soll auffallen, nicht nur mitlaufen (siehe CRAM_MODE_DAYS).
        if _snap["cram_active"] and _snap["next_exam"]:
            _cram_subj = _html_escape(SUBJECT_LABELS.get(
                _snap["next_exam"]["subject"], _snap["next_exam"]["subject"]))
            st.warning(f"🔥 **Fokus-Modus:** {_cram_subj} "
                      f"{planner.humanize_days(_snap['days_to_exam'])} – "
                      "jetzt zählt jede Wiederholung.")

        # Streak-Warnung: bewusst SEPARAT von den Chips (Verlust-Framing statt
        # nur einer weiteren neutralen Info) - nur ab STREAK_RISK_HOUR und nur,
        # wenn heute wirklich noch nichts geuebt wurde (siehe today_snapshot()).
        if _snap["streak_at_risk"]:
            st.error(f"🔥 Dein Streak von {_snap['streak']} Tag(en) reißt heute, "
                    "wenn du jetzt nicht noch kurz lernst.")

        _chips: list[str] = []
        if _snap["due_cards"]:
            _chips.append(f"🎴 {_snap['due_cards']} Karten fällig")
        if _snap["leeches"]:
            _chips.append(f"🐛 {_snap['leeches']} Problemkarten")
        if _snap["next_exam"] and _snap["days_to_exam"] is not None:
            _ex_subj = _html_escape(SUBJECT_LABELS.get(
                _snap["next_exam"]["subject"], _snap["next_exam"]["subject"]))
            _chips.append(f"📝 {_ex_subj}: {planner.humanize_days(_snap['days_to_exam'])}")
        if _snap["overdue_tasks"]:
            _chips.append(f"⚠️ {len(_snap['overdue_tasks'])} überfällige Aufgabe(n)")
        if _snap["due_today_tasks"]:
            _chips.append(f"✅ {len(_snap['due_today_tasks'])} Aufgabe(n) heute fällig")
        if _snap["overdue_plan_blocks"]:
            _chips.append(f"📋 {len(_snap['overdue_plan_blocks'])} Lernplan-Block(e) "
                          f"im Rückstand ({_snap['overdue_plan_min']} Min)")
        if _snap["study_min_today"]:
            _chips.append(f"⏱️ {_snap['study_min_today']} Min heute gelernt")

        if _chips:
            st.markdown(
                '<div class="rag-heute-chips">'
                + "".join(f'<span class="rag-heute-chip">{c}</span>' for c in _chips)
                + "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.caption("Für heute liegt nichts Dringendes an – gute Gelegenheit, "
                        "freiwillig etwas zu wiederholen.")

        _rows: list[str] = []
        for _s in _snap["today_classes"]:
            _room = f" ({_html_escape(_s['room'])})" if _s.get("room") else ""
            _cls_subj = _html_escape(SUBJECT_LABELS.get(_s["subject"], _s["subject"]))
            _rows.append(f"🗓️ {_s['start_time']}–{_s['end_time']} {_cls_subj}{_room}")
        for _b in _snap["plan_blocks_today"]:
            _mark = "✅" if _b["done"] else "📋"
            _sec_title = _html_escape(_b["section_title"] or "Abschnitt")
            _plan_title = _html_escape(_b["plan_title"])
            _rows.append(f"{_mark} {_sec_title} ({_plan_title}, {_b['planned_min']} Min)")
        if _rows:
            st.markdown(f'<div class="rag-heute-row">{" · ".join(_rows)}</div>',
                        unsafe_allow_html=True)

        # CTA: springt zur Seite, die heute am meisten weiterhilft - fällige
        # Karten zuerst (staerkster FSRS-Hebel), dann offene Aufgaben, dann der
        # Lernplan, sonst das Fach mit der hoechsten Prioritaet (siehe
        # planner.all_priorities()). Zielpfade kommen bewusst aus PAGE_REGISTRY
        # (die "einzige Quelle der Wahrheit", siehe Modul-Docstring von
        # _style.py) statt als eigene String-Literale - damit ein spaeter
        # umbenannter Dateiname nicht still zwei Stellen auseinanderlaufen laesst.
        _target = {p["key"]: p["target"] for p in PAGE_REGISTRY}
        if _snap["due_cards"]:
            _cta_label, _cta_target = "▶ Jetzt lernen", _target["lernen"]
        elif _snap["overdue_tasks"] or _snap["due_today_tasks"]:
            _cta_label, _cta_target = "🗂️ Aufgaben ansehen", _target["organisation"]
        elif (_snap["overdue_plan_blocks"]
              or (_snap["plan_blocks_today"] and _snap["plan_done_today"] < _snap["plan_min_today"])):
            _cta_label, _cta_target = "📋 Lernplan ansehen", _target["lernplan"]
        elif _snap["cram_active"]:
            # Keine faelligen Karten mehr, Klausur aber ganz nah -> aktiv eine
            # Probeklausur unter Zeitdruck anbieten statt nur "nichts zu tun".
            _cta_label, _cta_target = "📝 Probeklausur starten", _target["pruefung"]
        elif _snap["top_priority"]:
            _tp_subj = SUBJECT_LABELS.get(_snap["top_priority"]["subject"],
                                          _snap["top_priority"]["subject"])
            _cta_label = f"🎯 {_tp_subj} vertiefen"
            _cta_target = _target["lernen"]
        else:
            _cta_label, _cta_target = None, None

        if _cta_label:
            if st.button(_cta_label, key="heute_cta", type="primary"):
                st.switch_page(_cta_target)

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
