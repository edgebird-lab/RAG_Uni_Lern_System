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
import os

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

st.set_page_config(
    page_title="RAG-Lernsystem", page_icon=_PAGE_ICON, layout="wide",
    initial_sidebar_state="collapsed")

# Schwere Importe (torch/chromadb) im Hintergrund vorwärmen -> spätere
# Seitenwechsel öffnen sofort statt mit weißem Bildschirm, UND Embedding+Reranker
# schon einmal ins RAM/VRAM laden, damit die erste echte Frage nicht den Kaltstart
# zahlt. Per Einstellung abschaltbar (PREWARM_ON_START) - wer die Sitzung nur zum
# Karteikarten-Lernen oeffnet, will dafuer gar kein Modell laden.
from ragapp.config import settings
if settings.PREWARM_ON_START and os.environ.get("RAG_DISABLE_PREWARM") != "1":
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

# Leichte, einmalige Selbstheilung im Hintergrund: fällige Retry-/OCR-Jobs
# abarbeiten und Manifest/Chroma/BM25 abgleichen, ohne den Seitenaufbau zu blockieren.
if os.environ.get("RAG_DISABLE_PREWARM") != "1":
    try:
        from ragapp.student_flow import start_recovery_worker
        start_recovery_worker()
    except Exception:  # noqa: BLE001
        pass

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
          b.style.cssText = 'position:fixed;left:12px;right:12px;'
            + 'bottom:max(14px,env(safe-area-inset-bottom));margin:0 auto;'
            + 'max-width:520px;z-index:2147483647;background:#12455a;color:#fff;border-radius:14px;'
            + 'padding:12px 14px;box-shadow:0 10px 34px rgba(0,0,0,.4);font-family:system-ui,'
            + '-apple-system,sans-serif;font-size:14px;line-height:1.35;display:flex;'
            + 'align-items:center;gap:10px;';
          b.innerHTML = inner;
          var x = pdoc.createElement('button'); x.textContent = '\\u2715';
          x.type = 'button';
          x.setAttribute('aria-label', 'Installationshinweis schließen');
          x.title = 'Schließen';
          x.style.cssText = 'margin-left:auto;background:transparent;border:0;color:#bcd7df;'
            + 'font-size:17px;cursor:pointer;flex:none;min-width:44px;min-height:44px;';
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
# ist die Kurzwahl der fünf Zielgruppen). Ein Klick auf eine Kachel springt
# direkt zur jeweiligen Seite (st.switch_page, siehe
# ragapp.ui._style.render_nav_tile) - PAGE_REGISTRY dort ist die einzige
# Quelle der Wahrheit fuer Titel/Icon/Zielpfad/Gruppierung.
# --------------------------------------------------------------------------- #
from ragapp.ui._style import (apply_page_style, PAGE_REGISTRY, HOME_PIN_KEYS,
                               HIDDEN_PAGE_KEYS, render_nav_tile,
                               render_hero_title, card,
                               speech_bubble_mascot, mark_tight_nums)
from ragapp.ui._mascot import render_mascot, home_mood, home_mood_line
_theme = apply_page_style("home")

# --------------------------------------------------------------------------- #
# Lernstand VOR dem Maskottchen laden (Mood + Heute-CTA).
# --------------------------------------------------------------------------- #
try:
    import datetime as _dt
    from html import escape as _html_escape
    from ragapp import planner, manifest as _home_manifest
    from ragapp.config import SUBJECT_LABELS

    _snap = planner.today_snapshot()
except Exception:  # noqa: BLE001
    _snap = None

try:
    from ragapp import achievements as _achievements
    _newly_unlocked = _achievements.check_and_unlock()
except Exception:  # noqa: BLE001
    _achievements = None
    _newly_unlocked = []

try:
    from ragapp import study as _study
    _needs_harvest = _study.needs_card_harvest()
except Exception:  # noqa: BLE001
    _needs_harvest = False

_unlocked_title = (_newly_unlocked[0].title if _newly_unlocked else None)
_mood_pose, _mood_anim, _mood_prop = home_mood(
    _snap, celebrate=bool(_newly_unlocked), needs_harvest=_needs_harvest)
_mood_icon, _mood_text = home_mood_line(
    _snap, celebrate=bool(_newly_unlocked), needs_harvest=_needs_harvest,
    unlocked_title=_unlocked_title)

_target = {p["key"]: p["target"] for p in PAGE_REGISTRY}

# Compact hero: kurze Begruessung links, Maskottchen+Blase rechts (eine Einheit)
_hero_l, _hero_r = st.columns([2.4, 1.2])
with _hero_l:
    render_hero_title("Willkommen zurück", accent=_theme["accent"])
    st.caption("Was steht heute an?")
with _hero_r:
    with st.container(key="mascot_hero"):
        speech_bubble_mascot(_mood_text, icon=_mood_icon)
        render_mascot(_theme["accent"], size=140, pose=_mood_pose,
                      animation=_mood_anim, prop=_mood_prop)

if _newly_unlocked:
    st.balloons()
    from ragapp.ui._style import celebration_effects_html as _celebration_effects_html
    _components.html(_celebration_effects_html(), height=0)
    for _na in _newly_unlocked:
        st.success(f"**Neu freigeschaltet:** {_na.icon} {_na.title} – {_na.description}")
elif _achievements is not None:
    _nudge = _achievements.nearest_locked()
    if _nudge:
        _left = _nudge["target"] - _nudge["current"]
        st.caption(f"🎯 Noch **{_left:g}** bis {_nudge['icon']} **{_nudge['title']}**")
        from ragapp.ui import _charts
        st.markdown(_charts.progress_bar(_nudge["pct"], color=_theme["accent"]),
                   unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
# "Heute"-Briefing ZUERST (Hauptinhalt des ersten Viewports)
# --------------------------------------------------------------------------- #
if _snap:
    _WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag",
                   "Samstag", "Sonntag"]
    _today = _dt.date.today()

    with card("heute"):
        st.markdown("#### 🌞 Heute")
        st.markdown(
            f'<p class="rag-heute-date">{_WOCHENTAGE[_today.weekday()]}, '
            f'{_today.strftime("%d.%m.%Y")}</p>',
            unsafe_allow_html=True)

        if _snap["cram_active"] and _snap["next_exam"]:
            _cram_subj = _html_escape(SUBJECT_LABELS.get(
                _snap["next_exam"]["subject"], _snap["next_exam"]["subject"]))
            st.warning(f"🔥 **Fokus-Modus:** {_cram_subj} "
                      f"{planner.humanize_days(_snap['days_to_exam'])} – "
                      "jetzt zählt jede Wiederholung.")

        if _snap["streak_at_risk"]:
            st.error(f"🔥 Dein Streak von {_snap['streak']} Tag(en) reißt heute, "
                    "wenn du jetzt nicht noch kurz lernst.")

        _card_total = int((_home_manifest.review_counts() or {}).get("total") or 0)
        if _card_total > 0:
            if st.button("▶ Heute starten", type="primary",
                          key="heute_start", use_container_width=True,
                          help="Bis zu 16 Karten, fällige zuerst."):
                st.session_state["study_prefill"] = {
                    "source": "heute", "limit": 16, "mode": "reveal",
                    "subject": (
                        (_snap.get("next_exam") or {}).get("subject")
                        if _snap.get("cram_active")
                        else ((_snap.get("top_priority") or {}).get("subject"))
                    ),
                    "cram": bool(_snap.get("cram_active")),
                }
                st.switch_page(_target["lernen"])
        elif _needs_harvest:
            st.caption("Noch keine Karteikarten – zuerst das Lernset übernehmen.")
        else:
            st.caption("Noch keine Karteikarten – unter Karteikarten ein Lernset anlegen.")

        # Dringlichkeit zuerst; max. 3 kurze Chips, Rest steht in der Zeitleiste.
        _chips_priority: list[str] = []
        _chips_rest: list[str] = []
        if _snap["due_cards"]:
            _chips_priority.append(f"🎴 {_snap['due_cards']} fällig")
        if _snap["leeches"]:
            _chips_priority.append(f"🐛 {_snap['leeches']} schwer")
        if _snap["overdue_tasks"]:
            _chips_priority.append(f"⚠️ {len(_snap['overdue_tasks'])} überfällig")
        if _snap["due_today_tasks"]:
            _chips_priority.append(f"✅ {len(_snap['due_today_tasks'])} Aufgabe(n)")
        if _snap["next_exam"] and _snap["days_to_exam"] is not None:
            _ex_subj = _html_escape(SUBJECT_LABELS.get(
                _snap["next_exam"]["subject"], _snap["next_exam"]["subject"]))
            _chips_rest.append(
                f"📝 {_ex_subj}: {planner.humanize_days(_snap['days_to_exam'])}")
        if _snap["overdue_plan_blocks"]:
            _chips_rest.append(
                f"📋 {len(_snap['overdue_plan_blocks'])} im Rückstand")
        if _snap["study_min_today"]:
            _chips_rest.append(f"⏱️ {_snap['study_min_today']} Min")

        _show = (_chips_priority + _chips_rest)[:3]
        if _show:
            st.markdown(
                '<div class="rag-heute-chips">'
                + "".join(
                    f'<span class="rag-heute-chip">{mark_tight_nums(_html_escape(c))}</span>'
                    for c in _show)
                + "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.caption("Für heute liegt nichts Dringendes an – gute Gelegenheit, "
                        "freiwillig etwas zu wiederholen.")

        if _snap.get("open_errors"):
            if st.button(
                    f"📒 {_snap['open_errors']} im Fehlerheft üben",
                    key="home_chip_fehler", use_container_width=True):
                st.session_state["study_prefill"] = {
                    "source": "fehlerheft", "deck": "Fehlerheft",
                    "mode": "reveal", "limit": 15,
                }
                st.switch_page(_target["lernen"])

        if _snap["overdue_plan_blocks"]:
            from ragapp.student_flow import repair_all_overdue_plans as _repair_plans
            if st.button("🔧 Plan reparieren", key="home_repair_plan"):
                st.session_state["_home_repair_preview"] = True
            if st.session_state.get("_home_repair_preview"):
                _repair = _repair_plans(apply=False)
                _by_day: dict[str, int] = {}
                for _move in _repair["moves"]:
                    _by_day[_move["to_date"]] = (
                        _by_day.get(_move["to_date"], 0) + _move["minutes"])
                if _by_day:
                    st.caption("Vorschau: " + " · ".join(
                        f"{_day}: {_mins} Min" for _day, _mins in _by_day.items()))
                if _repair["shortfall_minutes"]:
                    st.warning(
                        f"{_repair['shortfall_minutes']} Min passen noch nicht in die "
                        "Lastgrenze und bleiben sichtbar.")
                _hr1, _hr2 = st.columns(2)
                if _hr1.button(
                        "Anwenden", type="primary", disabled=not _repair["moves"],
                        key="home_repair_apply"):
                    _repair_plans(apply=True)
                    st.session_state.pop("_home_repair_preview", None)
                    st.rerun()
                if _hr2.button("Abbrechen", key="home_repair_cancel"):
                    st.session_state.pop("_home_repair_preview", None)
                    st.rerun()

        _sched: list[str] = []
        for _s in _snap["today_classes"]:
            _room = f" ({_html_escape(_s['room'])})" if _s.get("room") else ""
            _cls_subj = _html_escape(SUBJECT_LABELS.get(_s["subject"], _s["subject"]))
            _sched.append(f"🗓️ {_s['start_time']}–{_s['end_time']} {_cls_subj}{_room}")
        for _b in _snap["plan_blocks_today"]:
            _mark = "✅" if _b["done"] else "📋"
            _sec_title = _html_escape(_b["section_title"] or "Abschnitt")
            _plan_title = _html_escape(_b["plan_title"])
            _sched.append(f"{_mark} {_sec_title} ({_plan_title}, {_b['planned_min']} Min)")
        if _sched:
            st.markdown(
                '<ul class="rag-heute-schedule">'
                + "".join(f"<li>{row}</li>" for row in _sched)
                + "</ul>",
                unsafe_allow_html=True,
            )

        _tp = _snap.get("top_priority") or {}
        _tp_subj = SUBJECT_LABELS.get(_tp.get("subject"), _tp.get("subject")) if _tp else None
        from ragapp import student_flow as _sf
        _vs = _sf.pick_verstehen_topic()
        if _vs:
            _vs_label = (_vs["topic"] or "").strip()
            if len(_vs_label) > 42:
                _vs_label = _vs_label[:40].rstrip() + "…"
            if st.button(
                    f"🧭 Verstehen: {_vs_label} · {_vs['minutes']} Min",
                    type="primary" if not _snap.get("due_cards") else "secondary",
                    key="heute_verstehen",
                    use_container_width=True,
                    help="20 Minuten mit einem Thema: sokratischer Dialog, "
                         "am Ende eine Notiz und ein paar Karten."):
                st.session_state["verstehen_prefill"] = _vs
                st.switch_page(_target["chat"])
        elif _tp_subj:
            st.caption(f"Heute lohnt: **{_tp_subj}**.")

        _faecher = _home_manifest.study_subjects()
        _sprint_choices = ["Alle Fächer"] + _faecher
        if "home_sprint_subject" not in st.session_state:
            _pref = _tp.get("subject")
            st.session_state["home_sprint_subject"] = (
                _pref if _pref in _faecher else "Alle Fächer")
        elif st.session_state.get("home_sprint_subject") not in _sprint_choices:
            st.session_state["home_sprint_subject"] = "Alle Fächer"

        with st.expander("Sprint und Fehlerheft", expanded=False):
            _sp1, _sp2 = st.columns([2, 3])
            with _sp1:
                _sprint_pick = st.selectbox(
                    "Sprint-Fach", _sprint_choices,
                    format_func=lambda s: s if s == "Alle Fächer"
                    else SUBJECT_LABELS.get(s, s),
                    key="home_sprint_subject",
                    help="Welches Fach du im Kurz-Sprint durchgehen willst – "
                         "unabhängig davon, was heute oben steht.")
            _sprint_subj = None if _sprint_pick == "Alle Fächer" else _sprint_pick
            _inv = _sf.sprint_inventory(subject=_sprint_subj)
            with _sp2:
                _sprint_kind = st.radio(
                    "Sprint-Inhalt",
                    ["Beides", "Formeln", "Definitionen"],
                    horizontal=True, key="home_sprint_kind",
                    help="Formeln nur, wenn welche in den Karten stecken. "
                         "Sonst ehrlich leer – kein stilles Ausweichen auf Langtexte.")
            _prefer = {"Formeln": "formula", "Definitionen": "definition",
                       "Beides": "auto"}[_sprint_kind]
            if _sprint_kind == "Formeln":
                _sprint_ok = _inv["formula_n"] > 0
                st.caption(
                    f"⚡ {_inv['formula_n']} Formel-Karten in dieser Auswahl."
                    if _sprint_ok else
                    "Keine Formeln in dieser Auswahl. Anderes Fach wählen oder "
                    "Definitionen sprinten – oder zuerst Karten anlegen.")
            elif _sprint_kind == "Definitionen":
                _sprint_ok = _inv["definition_n"] > 0
                st.caption(
                    f"⚡ {_inv['definition_n']} kurze Definitionen."
                    if _sprint_ok else
                    "Keine kurzen Definitionen in dieser Auswahl.")
            else:
                _sprint_ok = (_inv["formula_n"] + _inv["definition_n"]) > 0
                if _inv["formula_n"]:
                    st.caption(f"⚡ {_inv['formula_n']} Formeln"
                               + (f" · {_inv['definition_n']} Definitionen"
                                  if _inv["definition_n"] else "")
                               + " – Formeln zuerst.")
                elif _inv["definition_n"]:
                    st.caption(f"Keine Formeln – Sprint nimmt {_inv['definition_n']} "
                               "kurze Definitionen.")
                else:
                    st.caption("Nichts zum Sprinten in dieser Auswahl. "
                               "Zuerst Karteikarten anlegen.")

            _h2, _h3 = st.columns(2)
            _sprint_cta = {
                "Formeln": "⚡ Formel-Sprint",
                "Definitionen": "⚡ Definitionen-Sprint",
            }.get(_sprint_kind, "⚡ Sprint starten")
            if _h2.button(_sprint_cta, key="heute_sprint",
                          use_container_width=True, disabled=not _sprint_ok,
                          help="Kurzer Drill der gewählten Formeln oder Definitionen."):
                st.session_state["study_prefill"] = {
                    "source": "sprint", "limit": 12, "mode": "sprint",
                    "subject": _sprint_subj, "sprint": True, "prefer": _prefer,
                }
                st.switch_page(_target["lernen"])
            if _h3.button("📒 Fehlerheft", key="heute_fehler", use_container_width=True):
                st.session_state["study_prefill"] = {
                    "source": "fehlerheft", "deck": "Fehlerheft", "mode": "reveal",
                    "limit": 15,
                }
                st.switch_page(_target["lernen"])

        if _needs_harvest:
            st.warning("📇 Neue Fragen sind indexiert, aber noch **nicht als Karteikarten** "
                       "übernommen.")
            if st.button("Lernset öffnen", type="primary" if _card_total == 0 else "secondary",
                         key="heute_harvest", use_container_width=True):
                st.switch_page(_target["lernen"])
        elif _snap["overdue_tasks"] or _snap["due_today_tasks"]:
            if st.button("🗂️ Aufgaben ansehen", key="heute_tasks",
                         use_container_width=True):
                st.switch_page(_target["organisation"])

_capture_flash = st.session_state.pop("_capture_flash", None)
if _capture_flash:
    if _capture_flash.get("error"):
        st.warning(_capture_flash["message"])
    else:
        st.success(_capture_flash["message"])
with st.expander("📥 Vorlesung einfangen", expanded=False):
            st.caption("Foto, Datei oder Notiz landet im Fach-Ordner und erscheint als Unterlage.")
            from ragapp import manifest as _home_manifest
            _capture_subjects = sorted(
                set(SUBJECT_LABELS)
                | {e["subject"] for e in _home_manifest.list_exams()
                   if e.get("subject")}
                | {d["subject"] for d in _home_manifest.list_documents()
                   if d["subject"]}
                | {s["subject"] for s in _home_manifest.list_timetable()
                   if s.get("subject")}
            )
            _vl_subj = st.selectbox(
                "Fach", ["–"] + _capture_subjects,
                format_func=lambda s: SUBJECT_LABELS.get(s, s),
                key="home_vl_subject")
            _vl_title = st.text_input("Titel (optional)", key="home_vl_title")
            _vl_text = st.text_area("Was war neu?", key="home_vl_text", height=120)
            _vl_file = st.file_uploader(
                "Datei dem Fach zuordnen",
                type=["pdf", "md", "txt", "docx", "pptx"],
                key="home_vl_file")
            _vl_photo = st.camera_input("Tafel / Folie fotografieren", key="home_vl_cam")
            if st.button("Sichern", type="primary", key="home_vl_go"):
                from ragapp.student_flow import add_course_material
                body = (_vl_text or "").strip()
                _img = None
                if _vl_photo is not None:
                    _img = _vl_photo.getvalue()
                    try:
                        from ragapp.ingestion.loaders import ocr_image_bytes
                        _ocr_txt, _eng = ocr_image_bytes(_img)
                        if _ocr_txt:
                            body = (body + "\n\n" + _ocr_txt).strip()
                        elif not _eng:
                            st.warning("Foto-Text nicht gelesen (kein Vision-Modell).")
                    except Exception as _exc:  # noqa: BLE001
                        st.warning(f"Foto-Text nicht gelesen: {_exc}")
                if _vl_subj == "–":
                    st.warning("Bitte ein Fach wählen, damit die Unterlage im Kurs landet.")
                elif not body and _vl_file is None and _img is None:
                    st.warning("Bitte Text, Datei oder Foto.")
                else:
                    _cap = add_course_material(
                        _vl_subj, text=body or None, title=_vl_title or None,
                        file_bytes=_vl_file.getvalue() if _vl_file else None,
                        filename=_vl_file.name if _vl_file else None,
                        image_bytes=_img)
                    _n = len((_cap.get("capture") or {}).get("card_ids") or [])
                    _goals = (_cap.get("capture") or {}).get("goals") or []
                    _block = (_cap.get("capture") or {}).get("block_id")
                    _saved_msg = "Im Fach-Ordner gesichert"
                    if _n:
                        _saved_msg += f" · {_n} Karte(n)"
                    if _goals:
                        _saved_msg += f" · {len(_goals)} Lernziel(e)"
                    if _block:
                        _saved_msg += " · Abend-Block im Plan"
                    _saved_msg += "."
                    st.session_state["_capture_flash"] = {
                        "error": _cap.get("status") == "error",
                        "message": (
                            _saved_msg + " Die Indexierung ist fehlgeschlagen; "
                            "die Unterlage ist noch nicht im Chat durchsuchbar."
                            if _cap.get("status") == "error" else _saved_msg
                        ),
                    }
                    st.rerun()

# Schlanke Suche (kein voller Titel-Block)
with card("suche"):
    _search_q = st.text_input(
        "🔎 Überall suchen", key="global_search_query",
        placeholder="Notizen, Chats, Zusammenfassungen …  (Strg/Cmd+K)",
        label_visibility="visible")
    _components.html("""
<script>
(function() {
  try {
    var win = window.parent;
    if (win.sessionStorage.getItem('ragFocusSearch') !== '1') { return; }
    win.sessionStorage.removeItem('ragFocusSearch');
    var doc = win.document;
    var tries = 0;
    var iv = win.setInterval(function() {
      tries++;
      var input = doc.querySelector('input[aria-label*="Überall suchen"]')
        || doc.querySelector('input[aria-label*="Notizen, Chats"]');
      if (input) {
        input.scrollIntoView({block: 'center'});
        input.focus();
        win.clearInterval(iv);
      } else if (tries > 20) {
        win.clearInterval(iv);
      }
    }, 150);
  } catch (e) {}
})();
</script>
""", height=0)
    if _search_q and len(_search_q.strip()) >= 2:
        from ragapp import search as _search
        from ragapp.config import PROJECT_ROOT as _PROJECT_ROOT
        _results = _search.search_everything(_search_q)
        _total_hits = sum(len(v) for v in _results.values())
        if _total_hits == 0:
            st.caption("Keine Treffer.")
        else:
            if _results["notiz"]:
                st.markdown("**🗒️ Notizen**")
                for _r in _results["notiz"]:
                    if st.button(f"{_r['title']} — {_r['snippet'][:70]}",
                                key=f"gsearch_notiz_{_r['id']}", use_container_width=True):
                        st.session_state["notiz_filter_search"] = _search_q
                        st.switch_page(_target["notizen"])
            if _results["chat"]:
                st.markdown("**💬 Chats**")
                for _r in _results["chat"]:
                    if st.button(f"{_r['title']} — {_r['snippet'][:70]}",
                                key=f"gsearch_chat_{_r['id']}", use_container_width=True):
                        st.session_state["_chat_pending_choice"] = _r["id"]
                        st.switch_page(_target["chat"])
            if _results["zusammenfassung"]:
                st.markdown("**📄 Zusammenfassungen**")
                for _r in _results["zusammenfassung"]:
                    _zc1, _zc2 = st.columns([4, 1])
                    _zc1.caption(f"**{_r['title']}** — {_r['snippet'][:80]}")
                    _zpath = _PROJECT_ROOT / "docs" / _r["id"]
                    if _zpath.is_file():
                        _zc2.download_button(
                            "Download", _zpath.read_bytes(), file_name=_r["id"],
                            mime="text/markdown", key=f"gsearch_zsf_{_r['id']}",
                            help="Zusammenfassung herunterladen")

# Bibliothek-Stats nach hinten (Expander)
from ragapp.ui._loading import skeleton
with skeleton("Wird geladen …"):
    from ragapp import manifest

try:
    _stats = manifest.stats()
    with st.expander("📚 Bibliothek", expanded=False):
        _s1, _s2, _s3, _s4 = st.columns(4)
        _s1.metric("Dokumente", _stats["documents"])
        _s2.metric("Textstellen", _stats["chunks"])
        _s3.metric("Fragen", _stats["questions"])
        _s4.metric("Fächer", _stats["subjects"])
except Exception:  # noqa: BLE001
    pass

st.write("")
from ragapp import analytics as _home_analytics
from ragapp.student_flow import daily_missions as _daily_missions
_missions = _daily_missions()
_goal = _home_analytics.daily_goal_status()
_kind_labels = {"reviews": "Wiederholungen", "minutes": "Minuten", "plan_blocks": "Planblöcke"}
with card("missionen"):
    st.markdown("#### Nächste Schritte")
    _pick = st.segmented_control(
        "Tagesziel",
        options=list(_kind_labels.keys()),
        format_func=lambda k: _kind_labels[k],
        default=_home_analytics.get_daily_goal_kind(),
        key="home_daily_goal_kind",
    )
    if _pick and _pick != _home_analytics.get_daily_goal_kind():
        _home_analytics.set_daily_goal_kind(_pick)
        st.rerun()
    if not _goal.get("applicable", True):
        st.caption(
            "Heute ist kein Planblock vorgesehen. Du kannst trotzdem frei lernen.")
    else:
        _goal_done = int(_goal["done_today"])
        _goal_target = max(1, int(_goal["goal"]))
        _goal_name = _kind_labels.get(_goal.get("kind"), "Wiederholungen")
        st.progress(
            min(1.0, _goal_done / _goal_target),
            text=f"{_goal_done} von {_goal_target} {_goal_name} erledigt")
        st.caption(
            "Tagesziel geschafft."
            if _goal.get("goal_reached")
            else f"Noch {max(0, _goal_target - _goal_done)} {_goal_name}.")
    if _missions:
        for _m in _missions:
            if st.button(
                    f"{_m['title']} · {_m['minutes']} Min",
                    key=f"home_mission_{_m['id']}",
                    help=_m["reason"],
                    use_container_width=True):
                if _m["kind"] == "plan":
                    if _m.get("plan_id"):
                        st.session_state["_splan_pending_choice"] = _m["plan_id"]
                    if _m.get("block_ids"):
                        st.session_state["splan_focus_block_ids"] = list(
                            _m["block_ids"])
                    st.switch_page(_target["lernplan"])
                else:
                    st.session_state["study_prefill"] = {
                        "source": "mission", "limit": 16, "mode": "reveal",
                        "subject": _m.get("subject"),
                        "card_ids": _m.get("card_ids") or [],
                    }
                    st.switch_page(_target["lernen"])
    else:
        st.caption("Keine Missionen – erst Karten oder einen Lernplan anlegen.")

st.markdown("#### Direkt zu")
_pin_cols = st.columns(2)
for _i, _key in enumerate(HOME_PIN_KEYS):
    with _pin_cols[_i % 2]:
        render_nav_tile(_key)

_more_pages = [p for p in PAGE_REGISTRY
               if p.get("category") and p["key"] not in HOME_PIN_KEYS
               and p["key"] not in HIDDEN_PAGE_KEYS]
if _more_pages:
    with st.expander("Mehr Bereiche", expanded=False):
        _categories: list[str] = []
        for _pg in _more_pages:
            if _pg["category"] not in _categories:
                _categories.append(_pg["category"])
        for _cat in _categories:
            st.caption(_cat)
            _pages_in_cat = [p for p in _more_pages if p["category"] == _cat]
            _cols = st.columns(3)
            for _i, _pg in enumerate(_pages_in_cat):
                with _cols[_i % 3]:
                    render_nav_tile(_pg["key"])
            st.write("")
