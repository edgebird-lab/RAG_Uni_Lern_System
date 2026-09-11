"""
Zentrales visuelles Design-System ("Cozy Game"-Optik)
=========================================================
Pastellige Seitenthemen, Doodle-Hintergründe, Kachel-Hover-Animationen, ein
kaschierter Seitenübergang und die Hamburger-Kurzwahl-Navigation - alles an
EINER Stelle, damit jede Seite es mit einem einzigen Aufruf bekommt
(``apply_page_style()``, von ``page_boot()`` aufgerufen).

Bewusst KEINE externe Font-/Icon-CDN (Offline-Grundsatz der App, siehe
``easyocr`` statt System-Tesseract, kein System-Graphviz bei der Mindmap) -
Doodles sind handgebaute Inline-SVGs, keine Bild-Assets. Farben/Layout bauen
auf dem bestehenden ``_theme.py`` auf (Dark-Mode-Fixes bleiben dort), diese
Datei ergänzt nur den "Marken"-Layer obendrauf.

``PAGE_REGISTRY`` ist die EINE Quelle der Wahrheit für: Seiten-Akzentfarbe,
die Home-Kachel-Übersicht UND die Hamburger-Kurzwahl - neue Seiten werden hier
einmal eingetragen, nicht an drei Stellen gepflegt.
"""
from __future__ import annotations

from html import escape as html_escape

import streamlit as st
import streamlit.components.v1 as components

# --------------------------------------------------------------------------- #
# Seiten-Register: (key, icon, titel, untertitel, zielpfad, kategorie)
# zielpfad=None -> Home selbst (kein Sprung noetig). Kategorien gruppieren die
# Home-Kacheln; Reihenfolge hier = Anzeige-Reihenfolge auf der Home-Seite.
# --------------------------------------------------------------------------- #
PAGE_REGISTRY: list[dict] = [
    {"key": "home", "icon": "🏠", "title": "Home", "subtitle": "Alle Bereiche auf einen Blick",
     "target": None, "category": None},
    {"key": "chat", "icon": "💬", "title": "Chat", "subtitle": "Frag deine Unterlagen",
     "target": "pages/0_💬_Chat.py", "category": "Lernen & Fragen"},
    {"key": "lernen", "icon": "🎓", "title": "Karteikarten", "subtitle": "Wiederholen mit FSRS",
     "target": "pages/4_🎓_Lernen.py", "category": "Lernen & Fragen"},
    {"key": "mindmap", "icon": "🧠", "title": "Mindmap", "subtitle": "Themen visuell verknüpfen",
     "target": "pages/14_🧠_Mindmap.py", "category": "Lernen & Fragen"},
    {"key": "uebungsaufgaben", "icon": "🧮", "title": "Übungsaufgaben",
     "subtitle": "Rechnen & Anwenden", "target": "pages/13_🧮_Übungsaufgaben.py",
     "category": "Lernen & Fragen"},
    {"key": "pruefung", "icon": "📝", "title": "Probeklausur", "subtitle": "Echte Prüfungssimulation",
     "target": "pages/6_📝_Prüfung.py", "category": "Lernen & Fragen"},
    {"key": "lernplan", "icon": "📋", "title": "Lernplan", "subtitle": "KI-Gliederung + Zeitplan",
     "target": "pages/11_📋_Lernplan.py", "category": "Erstellen"},
    {"key": "zusammenfassung", "icon": "📄", "title": "Zusammenfassung", "subtitle": "KI-Lernkatalog",
     "target": "pages/7_📄_Zusammenfassung.py", "category": "Erstellen"},
    {"key": "audio", "icon": "🎧", "title": "Audio-Overview", "subtitle": "Vorgelesen mit deiner Stimme",
     "target": "pages/15_🎧_Audio-Overview.py", "category": "Erstellen"},
    {"key": "notizen", "icon": "🗒️", "title": "Notizen", "subtitle": "Eigene Gedanken",
     "target": "pages/12_🗒️_Notizen.py", "category": "Erstellen"},
    {"key": "fortschritt", "icon": "📈", "title": "Fortschritt", "subtitle": "Dein Lernfortschritt",
     "target": "pages/5_📈_Fortschritt.py", "category": "Fortschritt"},
    {"key": "lernzeit", "icon": "⏱️", "title": "Lernzeit", "subtitle": "Pomodoro & Zeittracking",
     "target": "pages/10_⏱️_Lernzeit.py", "category": "Fortschritt"},
    {"key": "ingestion", "icon": "📥", "title": "Ingestion", "subtitle": "Dokumente einlesen",
     "target": "pages/1_📥_Ingestion.py", "category": "Verwalten"},
    {"key": "dokumente", "icon": "🗃️", "title": "Dokumente", "subtitle": "Bibliothek verwalten",
     "target": "pages/9_🗃️_Dokumentenmanager.py", "category": "Verwalten"},
    {"key": "organisation", "icon": "🗂️", "title": "Organisation", "subtitle": "Stundenplan & Fächer",
     "target": "pages/8_🗂️_Organisation.py", "category": "Verwalten"},
    {"key": "evaluation", "icon": "📊", "title": "Evaluation", "subtitle": "Retrieval-Qualität messen",
     "target": "pages/2_📊_Evaluation.py", "category": "Verwalten"},
    {"key": "einstellungen", "icon": "⚙️", "title": "Einstellungen", "subtitle": "Modelle & Feintuning",
     "target": "pages/3_⚙️_Einstellungen.py", "category": "Verwalten"},
]
_PAGE_BY_KEY = {p["key"]: p for p in PAGE_REGISTRY}

# Hamburger-Kurzwahl: die 4 meistgenutzten Seiten (Home immer als erste dabei).
HAMBURGER_KEYS = ["home", "chat", "lernen", "lernplan"]

# --------------------------------------------------------------------------- #
# Pastell-Palette je Seite (Akzent + weicher Hintergrundton + Anzeigename).
# Bewusst gedaempfte Pastelltoene ("Cozy Game"-Optik) statt kraeftiger Farben -
# muss in Hell- UND Dunkel-Modus gut aussehen (siehe _BASE_CSS unten).
# --------------------------------------------------------------------------- #
PAGE_THEMES: dict[str, dict] = {
    "home":            {"accent": "#FF8FA3", "soft": "#FFE3E8", "name": "Koralle"},
    "chat":            {"accent": "#5FB6E8", "soft": "#DFF1FC", "name": "Himmelblau"},
    "lernen":          {"accent": "#61C9A8", "soft": "#DFF5EC", "name": "Smaragd"},
    "mindmap":         {"accent": "#B98CE0", "soft": "#F0E3FA", "name": "Amethyst"},
    "uebungsaufgaben": {"accent": "#8CC63F", "soft": "#E9F6D8", "name": "Limette"},
    "pruefung":        {"accent": "#EF7A7A", "soft": "#FBDEDE", "name": "Koralle-Rot"},
    "lernplan":        {"accent": "#B79CED", "soft": "#EEE6FC", "name": "Lavendel"},
    "zusammenfassung": {"accent": "#F6C453", "soft": "#FDF1D3", "name": "Butter"},
    "notizen":         {"accent": "#F2A0C4", "soft": "#FCE4EF", "name": "Rosé"},
    "fortschritt":     {"accent": "#FF9F5A", "soft": "#FFE9D6", "name": "Pfirsich"},
    "lernzeit":        {"accent": "#FF8A5B", "soft": "#FFE4D6", "name": "Tomate"},
    "ingestion":       {"accent": "#7FD8A6", "soft": "#E1F8EC", "name": "Minze"},
    "dokumente":       {"accent": "#8C8FE0", "soft": "#E7E7FA", "name": "Indigo"},
    "organisation":    {"accent": "#4FBFB8", "soft": "#DCF4F2", "name": "Türkis"},
    "evaluation":      {"accent": "#F4B942", "soft": "#FDEFD2", "name": "Honig"},
    "einstellungen":   {"accent": "#A9A6D4", "soft": "#EAE9F7", "name": "Fliederblau"},
    "audio":           {"accent": "#4FC3D9", "soft": "#DCF4F8", "name": "Aquamarin"},
}
_DEFAULT_THEME = PAGE_THEMES["home"]


def theme_for(page_key: str) -> dict:
    """Akzent/Soft-Farbe + Name fuer eine Seite - falls unbekannt, neutraler
    Home-Ton (nie ein KeyError fuer eine neue/vergessene Seite)."""
    return PAGE_THEMES.get(page_key, _DEFAULT_THEME)


# --------------------------------------------------------------------------- #
# Schriften: einmalig lokal heruntergeladen (Variable Fonts, "latin"-Subset -
# deckt deutsche Umlaute/ß bereits ab), ausgeliefert ueber Streamlits eigenes
# Static-Serving (``enableStaticServing = true``, siehe .streamlit/config.toml)
# unter dem SERVERWEITEN Pfad ``/app/static/...`` - bewusst mit fuehrendem "/"
# (nicht relativ), weil Streamlit-Multipage-Routen alle auf unterschiedlichen
# Unterpfaden liegen (z. B. "/Chat") und ein relativer Pfad dort auf
# "/Chat/app/static/..." aufloesen wuerde. Kein Nachladen von einer externen
# Font-CDN zur Laufzeit - bleibt mit dem Offline-Grundsatz der App vereinbar,
# obwohl das Herunterladen von Grafiken/Schriften aus dem Netz erlaubt wurde.
# Fredoka = rundlich-verspielt fuer Ueberschriften, Nunito = ruhig/gut lesbar
# fuer Fliesstext - beide als Variable Font (eine Datei deckt alle Schnitte ab).
# --------------------------------------------------------------------------- #
_FONT_FACE_CSS = """
<style>
@font-face {
  font-family: 'RAG Heading';
  src: url('/app/static/fonts/Fredoka-Variable.woff2') format('woff2');
  font-weight: 400 700;
  font-style: normal;
  font-display: swap;
}
@font-face {
  font-family: 'RAG Body';
  src: url('/app/static/fonts/Nunito-Variable.woff2') format('woff2');
  font-weight: 400 700;
  font-style: normal;
  font-display: swap;
}
html, body, .stApp,
[data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li, [data-testid="stWidgetLabel"],
[data-testid="stCaptionContainer"], [data-testid="stMetricValue"],
[data-testid="stMetricLabel"], [data-testid="stMetricDelta"],
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button,
input, textarea, select, table, th, td {
  font-family: 'RAG Body', 'Nunito', -apple-system, BlinkMacSystemFont,
    'Segoe UI', sans-serif !important;
}
h1, h2, h3, h4, h5, h6 {
  font-family: 'RAG Heading', 'Fredoka', -apple-system, BlinkMacSystemFont,
    'Segoe UI', sans-serif !important;
}
/* Streamlits Icon-Glyphen (Sidebar-Pfeil, Expander-Chevron, Button-Icons wie
   "keyboard_double_arrow_right"/"expand_more") sind KEIN Text, sondern
   Ligaturen der "Material Symbols Rounded"-Iconschrift - ein zu breiter
   Font-Family-Selektor (frueher u. a. [class*="st-emotion"], das praktisch
   JEDES Streamlit-Element trifft) hat diese Schrift ueberschrieben, sodass
   der rohe Ligatur-Name als Text ueber dem eigentlichen Label auftauchte.
   Deshalb hier explizit wieder auf die Iconschrift zurueckgesetzt. */
[data-testid="stIconMaterial"], [data-testid^="stIcon"],
span[class*="material-symbols"], span[class*="MaterialSymbol"] {
  font-family: 'Material Symbols Rounded' !important;
}
</style>
"""


# --------------------------------------------------------------------------- #
# Doodles: handgebaute, dezente Deko-SVGs (Sterne/Wolke/Blatt/Funkeln) - fixe
# Position, niedrige Deckkraft, NIE klickbar (pointer-events:none), liegen
# HINTER dem Inhalt (z-index negativ + .block-container bekommt z-index:1).
# --------------------------------------------------------------------------- #
def _doodle_layer(accent: str, soft: str) -> str:
    return f"""
<div class="rag-doodles" aria-hidden="true">
  <svg class="rag-doodle rag-doodle-1" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
    <path fill="{accent}" d="M50 6 L58 40 L92 50 L58 60 L50 94 L42 60 L8 50 L42 40 Z"/>
  </svg>
  <svg class="rag-doodle rag-doodle-2" viewBox="0 0 120 70" xmlns="http://www.w3.org/2000/svg">
    <ellipse cx="35" cy="42" rx="26" ry="20" fill="{soft}"/>
    <ellipse cx="62" cy="30" rx="30" ry="24" fill="{soft}"/>
    <ellipse cx="90" cy="44" rx="22" ry="17" fill="{soft}"/>
  </svg>
  <svg class="rag-doodle rag-doodle-3" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
    <path fill="{accent}" d="M50 4 C74 20 90 42 90 62 C90 82 72 96 50 96 C28 96 10 82 10 62
      C10 42 26 20 50 4 Z M50 20 C58 44 58 60 50 86" stroke="{soft}" stroke-width="2" fill="{accent}"/>
  </svg>
  <svg class="rag-doodle rag-doodle-4" viewBox="0 0 60 60" xmlns="http://www.w3.org/2000/svg">
    <path fill="{soft}" d="M30 4 L34 24 L54 30 L34 36 L30 56 L26 36 L6 30 L26 24 Z"/>
  </svg>
</div>
"""


# --------------------------------------------------------------------------- #
# Basis-CSS: Kachel-/Karten-Hover, Fade-in, Doodle-Positionierung, Hamburger-
# Popover-Optik, Titel-Akzent. Wird JE SEITE mit der eigenen Akzentfarbe neu
# injiziert (Streamlit dedupliziert wiederholte <style>-Bloecke ohnehin nicht,
# das ist hier egal - reine CSS-Regeln, keine Seiteneffekte bei Mehrfachladung).
# --------------------------------------------------------------------------- #
_BASE_CSS = """
<style>
/* Native Streamlit-Seitenliste aus - ersetzt durch Hamburger + Home-Kacheln. */
[data-testid="stSidebarNav"] {{display:none;}}

@keyframes ragFadeIn {{
  from {{opacity:0; transform:translateY(6px);}}
  to   {{opacity:1; transform:translateY(0);}}
}}
.block-container {{
  position:relative; z-index:1;
  animation:ragFadeIn .45s ease-out both;
}}

/* Seiten-Hintergrund: weicher Farbverlauf statt reinem Weiss, je Seite im
   eigenen Akzent - dezent genug, dass Inhalt/Kontrast unangetastet bleibt. */
[data-testid="stAppViewContainer"] {{
  background:
    radial-gradient(circle at 10% -8%, {soft} 0%, transparent 42%),
    radial-gradient(circle at 92% 108%, {soft} 0%, transparent 38%),
    #fbfaf7 !important;
  background-attachment:fixed !important;
}}
[data-testid="stHeader"] {{background:transparent !important;}}

@keyframes ragTitleFly {{
  from {{opacity:0; transform:translateX(-16px);}}
  to   {{opacity:1; transform:translateX(0);}}
}}
h1 {{
  font-weight:800 !important; letter-spacing:-0.5px;
  background:linear-gradient(90deg, {accent} 0%, {accent} 55%, {soft} 100%);
  -webkit-background-clip:text; background-clip:text; color:transparent !important;
  display:inline-block; padding-bottom:2px;
  border-bottom:4px solid {soft}; margin-bottom:.3rem !important;
  animation:ragTitleFly .5s cubic-bezier(.22,1,.36,1) both;
}}

/* Optionale "Hero"-Ueberschrift (siehe render_hero_title()): Buchstabe-fuer-
   Buchstabe-Einflug statt Gradient (Gradient-Text-Clip wuerde pro <span>
   neu ansetzen und in Streifen zerfallen - daher hier stattdessen Vollton). */
.rag-hero-title {{
  font-weight:800 !important; letter-spacing:-0.5px;
  border-bottom:4px solid {soft}; padding-bottom:2px; margin-bottom:.3rem !important;
  color:{accent} !important;
}}
.rag-hero-title span {{display:inline-block; opacity:0; animation:ragLetterIn .45s ease forwards;}}
@keyframes ragLetterIn {{
  from {{opacity:0; transform:translateY(10px) scale(.85);}}
  to   {{opacity:1; transform:translateY(0) scale(1);}}
}}

/* Wiederverwendbare "weiche Karte" fuer Inhalts-Gruppen auf einzelnen Seiten
   (siehe card()) - echter st.container(key=...), Klasse st-key-card_<key>.
   "Manga-Panel"-Optik: sichtbarer Tuschestrich-Rahmen (statt nur eines
   hauchduennen Pastell-Randes) + ein extrem dezentes Halbton-Punktraster im
   Hintergrund (Comic-Screentone-Anspielung, kaum wahrnehmbar, stoert keinen
   Text) - zusammen wirkt die Karte wie ein gezeichnetes Panel statt wie eine
   austauschbare graue Box. */
div[class*="st-key-card_"] {{
  background:
    radial-gradient(circle, rgba(43,32,54,.05) 1px, transparent 1.3px) 0 0/16px 16px,
    linear-gradient(160deg, #ffffff 0%, {soft} 145%) !important;
  border:2px solid rgba(43,32,54,.14) !important; border-radius:20px !important;
  padding:1.15rem 1.35rem !important; margin-bottom:1rem !important;
  box-shadow:0 3px 0 rgba(43,32,54,.06), 0 2px 14px rgba(0,0,0,.05) !important;
}}

/* Sprechblasen-Kasten fuer Tipps/Hinweise (siehe speech_bubble() in _style.py) -
   kleines Schwaenzchen unten links, wie eine Comic-Sprechblase. */
.rag-bubble {{
  position:relative; border:2px solid rgba(43,32,54,.16); border-radius:16px;
  background:#ffffff; padding:.7rem 1rem; margin:.4rem 0 1.1rem 6px;
  font-size:.92rem; box-shadow:0 2px 0 rgba(43,32,54,.05);
}}
.rag-bubble::after {{
  content:""; position:absolute; left:18px; bottom:-9px; width:16px; height:16px;
  background:#ffffff; border-right:2px solid rgba(43,32,54,.16);
  border-bottom:2px solid rgba(43,32,54,.16);
  clip-path:polygon(0 0, 100% 100%, 0 100%);
}}
html.rag-dark .rag-bubble {{background:#0f2440; border-color:rgba(231,237,245,.16);}}
html.rag-dark .rag-bubble::after {{background:#0f2440; border-color:rgba(231,237,245,.16);}}

/* Lernmaskottchen (siehe ragapp.ui._mascot) - Grundgeruest + drei
   Bewegungs-Varianten (float/wave/run, je nach Pose der Seite) plus
   Augen-Ausdruck (Blinzeln/Zwinkern/schlaefrig) und Pupillen-Tracking. */
.rag-mascot svg {{display:block; margin:0 auto; filter:drop-shadow(0 10px 14px rgba(43,32,54,.16));
  overflow:visible;}}
.ragm-pupil-l, .ragm-pupil-r {{transition:transform .09s linear;}}

/* Variante 1: sanftes Schweben (Standard-Idle). */
.rag-mascot-float {{animation:ragMascotFloat 3.6s ease-in-out infinite;}}
@keyframes ragMascotFloat {{
  0%,100% {{transform:translateY(0) rotate(-1.5deg);}}
  50%     {{transform:translateY(-9px) rotate(1.5deg);}}
}}

/* Variante 2: Schweben + der rechte Arm winkt (Begruessungs-Pose). */
.rag-mascot-wave {{animation:ragMascotFloat 3.6s ease-in-out infinite;}}
.rag-mascot-wave .ragm-arm-r {{animation:ragmArmWave 1.15s ease-in-out infinite;}}
@keyframes ragmArmWave {{
  0%,100% {{transform:rotate(0deg);}}
  30%     {{transform:rotate(-26deg);}}
  60%     {{transform:rotate(-6deg);}}
}}

/* Variante 3: huepfender "Renn"-Bounce, Beine wechseln sich ab (Lernzeit-
   Seite - passt zum Pomodoro-Timer-Tempo). */
.rag-mascot-run {{animation:ragmRunBounce .62s ease-in-out infinite;}}
@keyframes ragmRunBounce {{
  0%,100% {{transform:translateY(0) rotate(-3deg);}}
  50%     {{transform:translateY(-13px) rotate(3deg);}}
}}
.rag-mascot-run .ragm-leg-l {{animation:ragmLegHop .62s ease-in-out infinite;}}
.rag-mascot-run .ragm-leg-r {{animation:ragmLegHop .62s ease-in-out infinite .31s;}}
@keyframes ragmLegHop {{
  0%,100% {{transform:translateY(0);}}
  50%     {{transform:translateY(-6px);}}
}}

/* Augen: natuerliches beidseitiges Blinzeln (selten, kurz)... */
.ragm-blink {{animation:ragmBlink 5.4s ease-in-out infinite;}}
@keyframes ragmBlink {{
  0%, 92%, 100% {{transform:scaleY(1);}}
  95%           {{transform:scaleY(.12);}}
}}
/* ...das linke Auge zwinkert bei verspielten Posen stattdessen SELTENER,
   dafuer einzeln (Wink statt Blink) - laeuft bewusst NICHT synchron zum
   rechten Auge (andere Dauer), damit es wie ein bewusster Zwinker wirkt. */
.ragm-wink-loop {{animation:ragmWink 6.8s ease-in-out infinite;}}
@keyframes ragmWink {{
  0%, 90%, 100% {{transform:scaleY(1);}}
  94%           {{transform:scaleY(.08);}}
}}
/* Schlaefrig (Lernzeit im "run"-Pomodoro-Kontext): Augen bleiben schlicht
   halb geschlossen statt zu animieren. */
.ragm-sleepy {{transform:scaleY(.45);}}
@media (prefers-reduced-motion: reduce) {{
  .rag-mascot-float, .rag-mascot-wave, .rag-mascot-run,
  .rag-mascot-wave .ragm-arm-r, .rag-mascot-run .ragm-leg-l, .rag-mascot-run .ragm-leg-r,
  .ragm-blink, .ragm-wink-loop {{animation:none !important;}}
}}

/* Kleines Ecken-Maskottchen auf allen Nicht-Home-Seiten (siehe
   apply_page_style()) - fix unten RECHTS (unten links waere die Sidebar,
   die optisch ueber allem liegt und die Figur verdecken wuerde),
   klickdurchlaessig (blockiert nie Inhalte dahinter). Auf schmalen/kurzen
   Fenstern ausgeblendet, damit es auf dem Handy keinen Platz wegnimmt. */
.rag-mascot-corner {{
  position:fixed; right:16px; bottom:10px; z-index:5; pointer-events:none;
  opacity:.92;
}}
@media (max-height: 620px), (max-width: 700px) {{
  .rag-mascot-corner {{display:none;}}
}}

/* Kacheln (Home-Navigation) + wiederverwendbare "weiche Karte" fuer alle
   Seiten - Klick-Ziel ist ein ECHTER st.button in einem st.container(key=...),
   dessen automatisch vergebene CSS-Klasse (".st-key-<key>") wir hier stylen -
   kein HTML-Overlay-Trick, der Button bleibt voll funktionsfaehig/barrierefrei. */
div[class*="st-key-tile_"] button {{
  height:100%; min-height:132px; width:100%;
  display:flex; flex-direction:column; align-items:flex-start; justify-content:flex-end;
  gap:.15rem; text-align:left; white-space:pre-line;
  border-radius:22px !important; border:1px solid {soft} !important;
  background:linear-gradient(150deg, {soft} 0%, #ffffff 75%) !important;
  box-shadow:0 2px 10px rgba(0,0,0,.06);
  padding:18px 18px 16px 18px !important;
  transition:transform .18s ease, box-shadow .18s ease, border-color .18s ease;
  font-size:1rem !important; color:#2a2a35 !important;
}}
div[class*="st-key-tile_"] button:hover {{
  transform:scale(1.045) translateY(-3px);
  box-shadow:0 10px 24px rgba(0,0,0,.13);
  border-color:{accent} !important;
}}
div[class*="st-key-tile_"] button p {{
  font-size:1rem !important; line-height:1.3;
}}

/* Hamburger-Popover (st.popover) freundlicher rund statt eckig-technisch. */
[data-testid="stPopover"] button {{
  border-radius:14px !important;
}}

/* Dark-Mode-Umschalter (siehe _theme_toggle_html()) - schwebender runder
   Button oben rechts, ausserhalb des Streamlit-Baums direkt an <body>. */
#rag-theme-toggle {{
  position:fixed; top:14px; right:18px; z-index:1000000;
  width:42px; height:42px; border-radius:50%;
  border:1px solid {soft}; background:#ffffff; cursor:pointer;
  font-size:1.15rem; line-height:1; display:flex; align-items:center; justify-content:center;
  box-shadow:0 2px 10px rgba(0,0,0,.10);
  transition:transform .18s ease, box-shadow .18s ease;
}}
#rag-theme-toggle:hover {{transform:scale(1.08); box-shadow:0 6px 16px rgba(0,0,0,.16);}}
html.rag-dark #rag-theme-toggle {{
  background:#0f2440; border-color:#1e3a5f; box-shadow:0 2px 10px rgba(0,0,0,.35);
}}

/* Doodle-Hintergrund: fix positioniert, klickdurchlaessig, dezent. */
.rag-doodles {{position:fixed; inset:0; z-index:0; pointer-events:none; overflow:hidden;}}
.rag-doodle {{position:absolute; opacity:.16;}}
.rag-doodle-1 {{top:6%;  right:5%;  width:70px;  animation:ragFloat 7s ease-in-out infinite;}}
.rag-doodle-2 {{top:14%; left:-2%;  width:190px; opacity:.20; animation:ragDrift 22s linear infinite;}}
.rag-doodle-3 {{bottom:4%; right:8%; width:90px; opacity:.13; animation:ragFloat 9s ease-in-out infinite reverse;}}
.rag-doodle-4 {{bottom:18%; left:4%; width:46px; animation:ragFloat 6s ease-in-out infinite;}}
@keyframes ragFloat {{
  0%,100% {{transform:translateY(0) rotate(0deg);}}
  50%     {{transform:translateY(-10px) rotate(6deg);}}
}}
@keyframes ragDrift {{
  0%   {{transform:translateX(0);}}
  50%  {{transform:translateX(18px);}}
  100% {{transform:translateX(0);}}
}}
/* Dark-Mode: haengt an der Klasse "rag-dark" auf <html> (siehe
   _theme_toggle_html() unten) statt an @media - so wirkt der manuelle
   Umschalter unabhaengig von der Betriebssystem-Einstellung. */
html.rag-dark [data-testid="stAppViewContainer"] {{
  background:
    radial-gradient(circle at 10% -8%, {accent}22 0%, transparent 45%),
    radial-gradient(circle at 92% 108%, {accent}18 0%, transparent 40%),
    #0a1930 !important;
}}
html.rag-dark .rag-doodle {{opacity:.10;}}
html.rag-dark div[class*="st-key-tile_"] button {{
  background:linear-gradient(150deg, #132b4d 0%, #0d2038 75%) !important;
  color:#e7edf5 !important; border-color:#1e3a5f !important;
}}
html.rag-dark div[class*="st-key-tile_"] button:hover {{border-color:{accent} !important;}}
html.rag-dark div[class*="st-key-card_"] {{
  background:linear-gradient(160deg, #132b4d 0%, #0d2038 145%) !important;
  border-color:#2a4a72 !important;
  box-shadow:0 3px 0 rgba(0,0,0,.25), 0 2px 14px rgba(0,0,0,.3) !important;
}}
html.rag-dark .rag-hero-title {{color:{accent} !important;}}

@media (prefers-reduced-motion: reduce) {{
  .block-container, .rag-doodle, h1, .rag-hero-title span {{animation:none !important;}}
}}
</style>
"""


# --------------------------------------------------------------------------- #
# Seitenuebergang ("Aufzugtueren"): zwei Panels legen sich kurz ueber den
# Viewport und gleiten auseinander. NUR bei echter Navigation ausgeloest (siehe
# apply_page_style), sonst wuerde jeder Button-Klick/Widget-Rerun (Streamlit
# fuehrt dabei IMMER einen Full-Rerun des Skripts aus) die Animation erneut
# abspielen - das waere nach dem 2. Klick nur noch nervig, nicht mehr "modern".
# Per components.html (Iframe) injiziert, greift aber via window.parent.document
# auf das ECHTE Elternfenster zu - dasselbe etablierte Muster wie der
# bestehende Scroll-Fix/PWA-Banner in 🏠_Home.py und der Local-Token-Sync in
# _auth.py. Reines CSS/JS, kein Netzwerk-/Font-Nachladen noetig.
# --------------------------------------------------------------------------- #
def _transition_html(accent: str, soft: str) -> str:
    return f"""
<style>
  #rag-elevator {{position:fixed; inset:0; z-index:999999; pointer-events:none;}}
  #rag-elevator .door {{
    position:absolute; top:0; bottom:0; width:50%;
    background:linear-gradient(135deg, {accent} 0%, {soft} 100%);
  }}
  #rag-elevator .door-l {{left:0;}}
  #rag-elevator .door-r {{right:0;}}
  #rag-elevator.rag-open .door-l {{transform:translateX(-100%);}}
  #rag-elevator.rag-open .door-r {{transform:translateX(100%);}}
  #rag-elevator .door {{transition:transform .5s cubic-bezier(.65,0,.35,1);}}
  #rag-elevator .spark {{
    position:absolute; top:50%; left:50%; transform:translate(-50%,-50%);
    font-size:2.4rem; opacity:0; transition:opacity .25s ease .05s;
  }}
  #rag-elevator.rag-show .spark {{opacity:1;}}
</style>
<script>
(function() {{
  try {{
    var doc = window.parent.document;
    var old = doc.getElementById('rag-elevator');
    if (old) {{ old.remove(); }}
    var el = doc.createElement('div');
    el.id = 'rag-elevator';
    el.innerHTML = '<div class="door door-l"></div><div class="door door-r"></div>'
                  + '<div class="spark">✨</div>';
    doc.body.appendChild(el);
    requestAnimationFrame(function() {{
      el.classList.add('rag-show');
      setTimeout(function() {{ el.classList.add('rag-open'); }}, 260);
      setTimeout(function() {{ el.remove(); }}, 820);
    }});
  }} catch (e) {{}}
}})();
</script>
"""


# --------------------------------------------------------------------------- #
# Dark-Mode-Umschalter: kleiner runder Button, oben rechts im ECHTEN Elternfenster
# (nicht nur im Chat/dieser Seite) - 3 Zustaende (Auto/Hell/Dunkel), persistiert in
# localStorage, wirkt SOFORT ohne Streamlit-Rerun (reiner Client-Toggle, setzt die
# Klasse "rag-dark"/"rag-light" direkt auf <html>). Bei "Auto" hoert ein
# matchMedia-Listener live auf OS-Aenderungen. Bewusst UNBEDINGT (nicht nur bei
# Seitenwechsel) injiziert, weil Idempotenz billig ist und so auch nach einem
# reinen Widget-Rerun garantiert der richtige Zustand steht.
# --------------------------------------------------------------------------- #
def _theme_toggle_html() -> str:
    return """
<script>
(function() {
  try {
    var doc = window.parent.document;
    var root = doc.documentElement;
    var KEY = 'rag-theme';
    var mql = window.parent.matchMedia ? window.parent.matchMedia('(prefers-color-scheme: dark)') : null;

    function label(mode) {
      return mode === 'dark' ? '🌙' : (mode === 'light' ? '☀️' : '🌗');
    }
    function title(mode) {
      return 'Darstellung: ' + (mode === 'dark' ? 'Dunkel' : (mode === 'light' ? 'Hell' : 'Automatisch'));
    }
    function apply(mode) {
      root.classList.remove('rag-dark', 'rag-light');
      if (mode === 'dark') { root.classList.add('rag-dark'); }
      else if (mode === 'light') { root.classList.add('rag-light'); }
      else if (mql && mql.matches) { root.classList.add('rag-dark'); }
    }

    var saved = localStorage.getItem(KEY) || 'auto';
    apply(saved);

    if (mql && !mql._ragBound) {
      mql._ragBound = true;
      mql.addEventListener('change', function() {
        if ((localStorage.getItem(KEY) || 'auto') === 'auto') { apply('auto'); }
      });
    }

    var btn = doc.getElementById('rag-theme-toggle');
    if (!btn) {
      btn = doc.createElement('button');
      btn.id = 'rag-theme-toggle';
      btn.setAttribute('aria-label', 'Darstellung wechseln');
      doc.body.appendChild(btn);
      btn.addEventListener('click', function() {
        var cur = localStorage.getItem(KEY) || 'auto';
        var next = cur === 'auto' ? 'light' : (cur === 'light' ? 'dark' : 'auto');
        localStorage.setItem(KEY, next);
        apply(next);
        btn.textContent = label(next);
        btn.title = title(next);
      });
    }
    var cur2 = localStorage.getItem(KEY) || 'auto';
    btn.textContent = label(cur2);
    btn.title = title(cur2);
  } catch (e) {}
})();
</script>
"""


# --------------------------------------------------------------------------- #
# Hamburger-Kurzwahl (Sidebar-Popover): Home + die 3 meistgenutzten Seiten.
# Ergaenzt die Sidebar, ersetzt sie nicht - require_pin()'s "Zweites Fenster"/
# "App beenden"-Buttons bleiben unangetastet (siehe _auth.py).
# --------------------------------------------------------------------------- #
def render_hamburger_nav(current_page_key: str) -> None:
    with st.sidebar:
        with st.popover("☰ Menü", use_container_width=True):
            for key in HAMBURGER_KEYS:
                page = _PAGE_BY_KEY.get(key)
                if not page:
                    continue
                is_here = key == current_page_key
                label = f"{page['icon']} {page['title']}" + ("  ·  hier" if is_here else "")
                if st.button(label, key=f"hamburger_{key}", use_container_width=True,
                            disabled=is_here):
                    _go_to(page)


def _go_to(page: dict) -> None:
    # st.switch_page() stoppt die Skript-Ausfuehrung selbst (wie st.stop()) und
    # navigiert - kein zusaetzliches st.rerun() noetig/erreichbar danach.
    target = page["target"]
    if target is None:
        st.switch_page("🏠_Home.py")
    else:
        st.switch_page(target)


def render_nav_tile(page_key: str) -> None:
    """Eine Home-Kachel fuer die gegebene Seite (aus PAGE_REGISTRY) - echter
    st.button in einem benannten Container (siehe _BASE_CSS-Selektor oben),
    kein HTML-Overlay-Trick noetig (Streamlit >=1.something vergibt bei
    ``key=`` automatisch die CSS-Klasse ``st-key-<key>``)."""
    page = _PAGE_BY_KEY[page_key]
    with st.container(key=f"tile_{page_key}"):
        label = f"{page['icon']}\n\n**{page['title']}**\n{page['subtitle']}"
        if st.button(label, key=f"tile_btn_{page_key}", use_container_width=True):
            _go_to(page)


def card(key: str):
    """Weiche, abgerundete Karte fuer eine Inhalts-Gruppe auf einer Seite -
    als Kontext-Manager verwenden: ``with card("stats"): st.metric(...)``.
    Echter ``st.container(key=...)``, gestylt ueber die automatisch vergebene
    Klasse ``st-key-card_<key>`` (siehe _BASE_CSS) - kein HTML-Overlay noetig."""
    return st.container(key=f"card_{key}")


def render_hero_title(text: str, *, accent: str | None = None) -> None:
    """Grosse Willkommens-Ueberschrift mit Buchstabe-fuer-Buchstabe-Einflug -
    fuer den EINEN Blickfang-Moment einer Seite (z. B. Home), nicht als
    Ersatz fuer normale ``st.title()``-Aufrufe gedacht (die bekommen ihre
    eigene, dezentere Fly-in-Animation schon automatisch ueber den globalen
    ``h1``-Stil in _BASE_CSS)."""
    accent = accent or _DEFAULT_THEME["accent"]
    spans = "".join(
        f'<span style="animation-delay:{i * 0.035:.3f}s">{"&nbsp;" if ch == " " else ch}</span>'
        for i, ch in enumerate(text)
    )
    st.markdown(f'<h1 class="rag-hero-title">{spans}</h1>', unsafe_allow_html=True)


def speech_bubble(text: str, *, icon: str = "💡") -> None:
    """Comic-Sprechblase fuer einen kurzen Tipp/Hinweis (siehe ``.rag-bubble``
    in _BASE_CSS) - dezenter als ``st.info()``, aber verspielter: Text wird
    NICHT als Markdown interpretiert (nur escaped), da hier ausschliesslich
    kurze, feste Hinweistexte reinsollen, keine Nutzereingaben."""
    st.markdown(f'<div class="rag-bubble">{icon} {html_escape(text)}</div>',
                unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Haupt-Einstiegspunkt: von page_boot() fuer jede normale Seite aufgerufen,
# und direkt von der Home-Seite (🏠_Home.py), die ihre Boot-Sequenz aus
# Prozess-Start-Gruenden (Prewarm/Watchdog/Backup/PWA-Banner) manuell macht.
# --------------------------------------------------------------------------- #
def apply_page_style(page_key: str, *, show_nav: bool = True) -> dict:
    theme = theme_for(page_key)
    accent, soft = theme["accent"], theme["soft"]

    st.markdown(
        _FONT_FACE_CSS + _BASE_CSS.format(accent=accent, soft=soft) + _doodle_layer(accent, soft),
        unsafe_allow_html=True,
    )

    # Dark-Mode-Bootstrap + Umschalt-Button: UNBEDINGT bei jedem Aufruf (billig,
    # idempotent) - garantiert den richtigen Hell/Dunkel-Zustand auch direkt
    # nach einem reinen Widget-Rerun (siehe _theme_toggle_html Docstring).
    components.html(_theme_toggle_html(), height=0)

    # Uebergangs-Animation NUR bei echter Seiten-Navigation abspielen (nicht
    # bei jedem Widget-Rerun innerhalb derselben Seite - siehe _transition_html
    # Docstring-Kommentar oben).
    if st.session_state.get("_rag_last_page") != page_key:
        st.session_state["_rag_last_page"] = page_key
        components.html(_transition_html(accent, soft), height=0)

    if show_nav:
        render_hamburger_nav(page_key)

    # Kleines Ecken-Maskottchen mit seiner Pose (siehe ragapp.ui._mascot.POSES) -
    # NICHT auf Home, das zeigt bereits sein eigenes, grosses Hero-Maskottchen.
    if page_key != "home":
        from ragapp.ui._mascot import render_mascot_corner, pose_for
        _pose, _anim, _prop = pose_for(page_key)
        render_mascot_corner(accent, pose=_pose, animation=_anim, prop=_prop)

    return theme
