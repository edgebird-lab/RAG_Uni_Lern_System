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
einmal eingetragen, nicht an drei Stellen gepflegt. Kategorien sind die fünf
Zielgruppen Heute, Kurse, Lernen, Werkzeuge, Fortschritt.
"""
from __future__ import annotations

from html import escape as html_escape

import streamlit as st
import streamlit.components.v1 as components

# --------------------------------------------------------------------------- #
# Seiten-Register: (key, icon, titel, untertitel, zielpfad, kategorie)
# zielpfad=None -> Home selbst (kein Sprung noetig). Kategorien sind die fünf
# studentischen Zielgruppen (GOAL_CATEGORIES); Reihenfolge hier = Anzeige-
# Reihenfolge in Hamburger und Home-Mehr. PAGE_REGISTRY bleibt die einzige
# Navigationsquelle - HAMBURGER_KEYS / HOME_PIN_KEYS / HIDDEN_PAGE_KEYS
# verweisen nur auf Keys aus dieser Liste.
# --------------------------------------------------------------------------- #
GOAL_CATEGORIES = ("Heute", "Kurse", "Lernen", "Werkzeuge", "Fortschritt")

PAGE_REGISTRY: list[dict] = [
    {"key": "home", "icon": "🏠", "title": "Home", "subtitle": "Alle Bereiche auf einen Blick",
     "target": None, "category": None},
    {"key": "lernplan", "icon": "📋", "title": "Lernplan", "subtitle": "KI-Gliederung + Zeitplan",
     "target": "pages/11_📋_Lernplan.py", "category": "Heute"},
    {"key": "lernzeit", "icon": "⏱️", "title": "Lernzeit", "subtitle": "Pomodoro & Zeittracking",
     "target": "pages/10_⏱️_Lernzeit.py", "category": "Heute"},
    {"key": "organisation", "icon": "🗂️", "title": "Kurse & Stundenplan",
     "subtitle": "Fächer, Termine & Aufgaben",
     "target": "pages/8_🗂️_Organisation.py", "category": "Kurse"},
    {"key": "semesterplan", "icon": "📚", "title": "Semester einrichten",
     "subtitle": "Modulhandbuch importieren",
     "target": "pages/16_📚_Semesterplan.py", "category": "Kurse"},
    {"key": "dokumente", "icon": "🗃️", "title": "Dokumente", "subtitle": "Hochladen, Ordner, Bibliothek",
     "target": "pages/9_🗃️_Dokumentenmanager.py", "category": "Kurse"},
    {"key": "lernen", "icon": "🎓", "title": "Karteikarten", "subtitle": "Wiederholen mit FSRS",
     "target": "pages/4_🎓_Lernen.py", "category": "Lernen"},
    {"key": "chat", "icon": "💬", "title": "Chat", "subtitle": "Frag deine Unterlagen",
     "target": "pages/0_💬_Chat.py", "category": "Lernen"},
    {"key": "uebungsaufgaben", "icon": "🧮", "title": "Übungsaufgaben",
     "subtitle": "Rechnen, Begründen, Anwenden", "target": "pages/13_🧮_Übungsaufgaben.py",
     "category": "Lernen"},
    {"key": "pruefung", "icon": "📝", "title": "Prüfung", "subtitle": "Schriftlich oder mündlich",
     "target": "pages/6_📝_Prüfung.py", "category": "Lernen"},
    {"key": "mindmap", "icon": "🧠", "title": "Mindmap", "subtitle": "Themen visuell verknüpfen",
     "target": "pages/14_🧠_Mindmap.py", "category": "Lernen"},
    {"key": "zusammenfassung", "icon": "📄", "title": "Zusammenfassung", "subtitle": "Grounded auf den Stoff",
     "target": "pages/7_📄_Zusammenfassung.py", "category": "Lernen"},
    {"key": "audio", "icon": "🎧", "title": "Audio-Übersicht", "subtitle": "Vorgelesen mit deiner Stimme",
     "target": "pages/15_🎧_Audio-Overview.py", "category": "Lernen"},
    {"key": "vortrag", "icon": "🎤", "title": "Vortrag", "subtitle": "Marp-Folien + Lernvideo",
     "target": "pages/17_🎤_Vortrag.py", "category": "Lernen"},
    {"key": "notizen", "icon": "🗒️", "title": "Notizen", "subtitle": "Eigene Gedanken",
     "target": "pages/12_🗒️_Notizen.py", "category": "Werkzeuge"},
    {"key": "einstellungen", "icon": "⚙️", "title": "Einstellungen", "subtitle": "Modelle & Feintuning",
     "target": "pages/3_⚙️_Einstellungen.py", "category": "Werkzeuge"},
    {"key": "ingestion", "icon": "📥", "title": "Import", "subtitle": "Dokumente einlesen",
     "target": "pages/1_📥_Ingestion.py", "category": "Werkzeuge"},
    {"key": "fortschritt", "icon": "📈", "title": "Fortschritt", "subtitle": "Dein Lernfortschritt",
     "target": "pages/5_📈_Fortschritt.py", "category": "Fortschritt"},
    {"key": "evaluation", "icon": "📊", "title": "Evaluation", "subtitle": "Retrieval-Qualität messen",
     "target": "pages/2_📊_Evaluation.py", "category": "Fortschritt"},
]
_PAGE_BY_KEY = {p["key"]: p for p in PAGE_REGISTRY}

# Eine Hub-Seite je Zielgruppe. Kurzwahl und Home-Pins zeigen diese Ziele,
# nicht Chat/Karten/Fortschritt als gleichrangige Werkzeuge. Generatoren
# (Zusammenfassung, Audio, Vortrag, Mindmap) bleiben hinter "Mehr".
GOAL_HUB_KEYS: dict[str, str] = {
    "Heute": "home",
    "Kurse": "organisation",
    "Lernen": "lernen",
    "Werkzeuge": "notizen",
    "Fortschritt": "fortschritt",
}

# Hamburger-Kurzwahl: die fünf Zielgruppen (Home steht fuer Heute).
HAMBURGER_KEYS = [GOAL_HUB_KEYS[c] for c in GOAL_CATEGORIES]

# Home-Kacheln: dieselben fünf Ziele; Home hat keine Kachel zu sich selbst,
# daher Lernplan als Heute-Einstieg. Generatoren liegen hinter "Mehr".
HOME_PIN_KEYS = [
    "lernplan" if GOAL_HUB_KEYS[c] == "home" else GOAL_HUB_KEYS[c]
    for c in GOAL_CATEGORIES
]

# Operator-Seiten: nicht im Studenten-Alltag (Home/Hamburger-Gruppen).
HIDDEN_PAGE_KEYS = {"evaluation", "ingestion"}

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
    "vortrag":         {"accent": "#E07A9A", "soft": "#F9E0E8", "name": "Himbeer"},
    "semesterplan":    {"accent": "#D9A464", "soft": "#F7E7CE", "name": "Karamell"},
}
_DEFAULT_THEME = PAGE_THEMES["home"]

# --------------------------------------------------------------------------- #
# "Technische" Seiten (Evaluation, Einstellungen): Betreiber-/Admin-Werkzeuge
# fuer Retrieval-Tuning und Modell-Konfiguration statt Lernoberflaeche - hier
# passt die verspielte "Cozy Kawaii"-Optik (Doodles, Halbton-Punktraster,
# Farbverlauf-Titel) tonal nicht. Siehe _technical_override_css() unten.
# --------------------------------------------------------------------------- #
TECHNICAL_PAGE_KEYS = frozenset({"evaluation", "einstellungen"})


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
/* Lange deutsche Komposita ("Dokumentenmanager", "Uebungsaufgaben") brechen
   bei Handy-Breite sonst MITTEN im Wort um, ohne jede Kennzeichnung (Live-
   Test bei 390px: "Dokumentenman/ager") - der Browser braucht dafuer
   ausser einer Leerstelle KEINE Erlaubnis, sobald sein eigenes Overflow-
   Verhalten das Wort schon irgendwo trennt. "hyphens: auto" laesst ihn an
   einer echten Silbengrenze MIT sichtbarem Trennstrich umbrechen - dafuer
   muss der Browser aber wissen, dass der Text deutsch ist (siehe
   _i18n_patch_html(), setzt document.documentElement.lang = "de"). */
h1, h2, h3, h4, h5, h6 {
  hyphens: auto; -webkit-hyphens: auto; -ms-hyphens: auto;
  overflow-wrap: break-word;
}
/* Die App nutzt Emoji als durchgaengige Icon-Sprache (Navigation, Maskottchen-
   Requisiten, Errungenschaften) - eine bewusste Stilentscheidung fuer
   Comic-/Manga-Charme statt eines sterilen SVG-Icon-Sets. Der Nebeneffekt:
   Emoji rendern je nach Betriebssystem unterschiedlich (manche Schriften
   zeigen sie ohne diese Regel sogar als schwarz-weisses TEXT-Glyph statt
   Farbbild). "font-variant-emoji: emoji" erzwingt ueberall die farbige
   Emoji-Darstellung (CSS Fonts Level 4, in aktuellen Chromium/Firefox
   unterstuetzt, sonst folgenlos ignoriert) - behebt die groebste
   Inkonsistenz, OHNE die Emoji-Identitaet der App aufzugeben oder einen
   zusaetzlichen Font-Download (der die Offline-Faehigkeit gefaehrden wuerde). */
.rag-heute-date, [data-testid="stCaptionContainer"],
[data-testid="stMetricValue"], input, textarea {
  font-variant-emoji: text;
}
.rag-heute-chip, .rag-bubble, .rag-bubble-mascot {
  font-variant-emoji: emoji;
}
/* Streamlit-Kennzahlen (st.metric): Default-Schriftgroesse (~2.25rem) + unsere
   etwas breitere Body-Schrift (Nunito) + Streamlits text-overflow:ellipsis
   schneiden in engen Spalten (4er-Karten auf Lernen/Home/Fortschritt) Werte
   wie "302" oder "20/20" zu "3 0 2 …" / "2 0 /…" ab. Kompakter, engeres
   Tracking, kein Ellipsis - gilt app-weit fuer JEDE Seite mit Zahlen. */
[data-testid="stMetricValue"],
[data-testid="stMetricValue"] * {
  font-size: 1.35rem !important;
  font-weight: 700 !important;
  letter-spacing: -0.03em !important;
  line-height: 1.15 !important;
  overflow: visible !important;
  text-overflow: clip !important;
  white-space: nowrap !important;
  overflow-wrap: normal !important;
  word-break: keep-all !important;
  font-variant-numeric: normal !important;
  font-feature-settings: normal !important;
  max-width: none !important;
}
[data-testid="stMetricLabel"],
[data-testid="stMetricDelta"] {
  overflow: visible !important;
  text-overflow: clip !important;
}
[data-testid="stMetric"],
[data-testid="stMetricContainer"],
div[data-testid="metric-container"],
[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
  overflow: visible !important;
}
/* Datums-/Zahlenzeilen in Ueberschriften (z. B. Home "Heute · Sa, 12.09.2026"):
   Fredoka (Heading) ist rund und breit - ohne engeres Tracking und normalen
   Umbruch wirken Datumsangaben abgehakt oder gequetscht. */
h2, h3, h4, h5, h6 {
  letter-spacing: -0.02em;
  overflow-wrap: break-word;
}
/* Nunito-Subset hat keine echten OpenType-Zahlenfeatures. `tabular-nums` /
   `lining-nums` werden dann mit ~doppelter Ziffernbreite nachgebildet
   ("14.09.2026" wirkt wie "1 4 . 0 9 . 2 0 2 6"). Deshalb bewusst aus. */
html, body, .stApp, [data-testid="stCaptionContainer"],
[data-testid="stMarkdownContainer"], [data-testid="stWidgetLabel"] {
  font-variant-numeric: normal;
  font-feature-settings: normal;
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
# Ueberschreibung fuer TECHNICAL_PAGE_KEYS: sachlicherer Auftritt statt der
# verspielten Basis-Optik - kein Halbton-Punktraster in den Karten, kleinerer
# Radius, entsaettigter Seitenhintergrund, Titel in Volltonfarbe statt
# Farbverlauf-Text-Clip. Wird ZUSAETZLICH zu _BASE_CSS injiziert (reine
# Ueberschreibung per spaeterer Deklaration im selben <style>-Block, kein
# eigenes CSS-Grundsystem) - der Doodle-Layer wird fuer diese Seiten in
# apply_page_style() gleich gar nicht erst mit ausgeliefert.
# --------------------------------------------------------------------------- #
def _technical_override_css(soft: str) -> str:
    return f"""
<style>
[data-testid="stAppViewContainer"] {{
  background:#f4f6fa !important; background-attachment:fixed !important;
}}
html.rag-dark [data-testid="stAppViewContainer"] {{background:#0c1a30 !important;}}
h1 {{
  background:none !important; -webkit-background-clip:unset !important;
  background-clip:unset !important; color:#2b2036 !important;
  border-bottom-color:{soft} !important;
}}
html.rag-dark h1 {{color:#e7edf5 !important;}}
div[class*="st-key-card_"] {{
  background:#ffffff !important;
  border:1px solid rgba(43,32,54,.14) !important; border-radius:12px !important;
  box-shadow:0 1px 3px rgba(0,0,0,.05) !important;
}}
html.rag-dark div[class*="st-key-card_"] {{
  background:#0f2440 !important; border-color:rgba(231,237,245,.16) !important;
  box-shadow:0 1px 3px rgba(0,0,0,.25) !important;
}}
</style>
"""


# --------------------------------------------------------------------------- #
# Basis-CSS: Kachel-/Karten-Hover, Fade-in, Doodle-Positionierung, Hamburger-
# Popover-Optik, Titel-Akzent. Wird JE SEITE mit der eigenen Akzentfarbe neu
# injiziert (Streamlit dedupliziert wiederholte <style>-Bloecke ohnehin nicht,
# das ist hier egal - reine CSS-Regeln, keine Seiteneffekte bei Mehrfachladung).
# --------------------------------------------------------------------------- #
_BASE_CSS = """
<style>
/* Ruhiger, zugänglicher Grundrahmen: breite Dashboards nutzen den Platz,
   Text bleibt gut umbrechbar und native Controls kennen den aktiven Modus. */
html {{ color-scheme:light; overflow-x:hidden; }}
html.rag-dark {{ color-scheme:dark; }}
body, .stApp {{ overflow-x:hidden; }}
.block-container {{
  position:relative; z-index:1;
  max-width:1180px;
  padding-top:2rem !important;
  padding-left:clamp(1rem, 3vw, 3rem) !important;
  padding-right:clamp(1rem, 3vw, 3rem) !important;
  animation:ragFadeIn .45s ease-out both;
}}
h1, h2, h3, h4 {{ text-wrap:balance; }}
p, li, [data-testid="stCaptionContainer"] {{ text-wrap:pretty; }}
[data-testid="stCaptionContainer"] {{
  color:#606778 !important; line-height:1.45 !important;
}}
html.rag-dark [data-testid="stCaptionContainer"] {{
  color:#aebdd1 !important;
}}
/* Gedämpfte Meta-Zeilen (Zeitleiste, Stundenplan, Listen): eine Token-Farbe
   statt Opacity-Stapeln, Mindestgröße 12px – sonst fällt „Heute“/Uhrzeit
   unter WCAG-AA und wirkt auf dem Handy wie Deko. */
.splan-tl-label, .rag-tt-timeaxis, .rag-tt-hour,
.pa-item-meta, .notiz-item-meta, .splan-topic-meta,
.source-meta, .small {{
  color:#5b6b85 !important; font-size:12px !important; opacity:1 !important;
}}
html.rag-dark .splan-tl-label, html.rag-dark .rag-tt-timeaxis,
html.rag-dark .rag-tt-hour, html.rag-dark .pa-item-meta,
html.rag-dark .notiz-item-meta, html.rag-dark .splan-topic-meta,
html.rag-dark .source-meta, html.rag-dark .small {{
  color:#93a8c4 !important;
}}
.splan-tl-seg.splan-tl-today .splan-tl-label,
.rag-tt-header.rag-tt-today {{
  color:#1d4ed8 !important; font-weight:700;
}}
.rag-tt-today-tag {{
  display:inline-block; margin-left:4px; font-size:10px; font-weight:700;
  letter-spacing:.02em; text-transform:uppercase; color:#1d4ed8;
}}
html.rag-dark .splan-tl-seg.splan-tl-today .splan-tl-label,
html.rag-dark .rag-tt-header.rag-tt-today,
html.rag-dark .rag-tt-today-tag {{
  color:#93c5fd !important;
}}
button, a, input, textarea, select, summary {{
  touch-action:manipulation;
  -webkit-tap-highlight-color:rgba(49,70,110,.14);
}}
button:focus-visible, a:focus-visible, input:focus-visible,
textarea:focus-visible, select:focus-visible, summary:focus-visible,
[role="button"]:focus-visible, [role="tab"]:focus-visible {{
  outline:3px solid #244f7a !important;
  outline-offset:3px !important;
  box-shadow:0 0 0 5px rgba(255,255,255,.92) !important;
}}
html.rag-dark button:focus-visible, html.rag-dark a:focus-visible,
html.rag-dark input:focus-visible, html.rag-dark textarea:focus-visible,
html.rag-dark select:focus-visible, html.rag-dark summary:focus-visible,
html.rag-dark [role="button"]:focus-visible,
html.rag-dark [role="tab"]:focus-visible {{
  outline-color:#9bc9f2 !important;
  box-shadow:0 0 0 5px rgba(10,25,48,.94) !important;
}}

/* Native Streamlit-Seitenliste aus - ersetzt durch Hamburger + Home-Kacheln. */
[data-testid="stSidebarNav"] {{display:none;}}

@keyframes ragFadeIn {{
  from {{opacity:0; transform:translateY(6px);}}
  to   {{opacity:1; transform:translateY(0);}}
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
  color:#2b2036 !important;
  display:inline-block; max-width:100%; padding-bottom:2px;
  border-bottom:4px solid {accent}; margin-bottom:.3rem !important;
  animation:ragTitleFly .5s cubic-bezier(.22,1,.36,1) both;
}}
html.rag-dark h1 {{ color:#e7edf5 !important; }}

/* Optionale "Hero"-Ueberschrift (siehe render_hero_title()): Buchstabe-fuer-
   Buchstabe-Einflug statt Gradient (Gradient-Text-Clip wuerde pro <span>
   neu ansetzen und in Streifen zerfallen - daher hier stattdessen Vollton). */
h1.rag-hero-title, .rag-hero-title {{
  font-weight:800 !important; letter-spacing:-0.5px;
  border-bottom:4px solid {accent}; padding-bottom:2px; margin-bottom:.3rem !important;
  color:#2b2036 !important; -webkit-text-fill-color:#2b2036 !important;
  background:none !important; -webkit-background-clip:unset !important;
  background-clip:unset !important;
  animation:none !important; opacity:1 !important;
}}
html.rag-dark h1.rag-hero-title, html.rag-dark .rag-hero-title {{
  color:#e7edf5 !important; -webkit-text-fill-color:#e7edf5 !important;
}}
/* Wort-Wrapper (siehe render_hero_title()-Docstring): macht ein ganzes Wort
   umbruch-atomar, waehrend zwischen Woertern weiterhin normal umgebrochen
   werden darf - behebt den "Willkommen zurü/ck"-Mitten-im-Wort-Umbruch bei
   schmalen (Handy-)Breiten. */
.rag-hero-word {{display:inline-block; white-space:nowrap;}}
/* opacity bleibt 1 (Erstframe lesbar). Animation nur Transform; Delay darf
   Buchstaben nicht unsichtbar lassen (Live-Test: Desktop-Titel war weiss). */
.rag-hero-title .rag-hero-letter {{
  display:inline-block; opacity:1;
  animation:ragLetterIn .45s ease both;
}}
/* Auf Home verbraucht die Kombination aus grosser Hero-Ueberschrift + grossem
   Maskottchen bei Handy-Breite sehr viel Platz, bevor ueberhaupt etwas
   Nuetzliches (Suche, Kacheln) sichtbar wird (Live-Test bei 390px zeigte:
   mehrere Bildschirme scrollen, bevor die eigentliche Seite anfaengt).
   Kompakter statt kleiner - der Effekt bleibt erkennbar, nimmt aber deutlich
   weniger vertikalen Raum ein. Betrifft NUR das grosse Home-Maskottchen
   (render_mascot(), einzige Verwendung), nicht das kleine Eck-Maskottchen
   (das ist ohnehin schon unter 700px ausgeblendet). */
@media (max-width: 480px) {{
  .rag-hero-title {{font-size:1.9rem !important;}}
  .rag-hero-title .rag-hero-letter {{
    animation:none !important; opacity:1 !important; transform:none !important;
  }}
}}
@keyframes ragLetterIn {{
  from {{transform:translateY(8px) scale(.96);}}
  to   {{transform:translateY(0) scale(1);}}
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

/* "Heute"-Briefing auf der Startseite (siehe planner.today_snapshot()) - Chips
   fassen das Wichtigste des Tages auf einen Blick zusammen. */
.rag-heute-chips {{display:flex; flex-wrap:wrap; gap:8px; margin:.5rem 0 .7rem;}}
.rag-heute-chip {{
  font-size:.86rem; font-weight:600; padding:5px 12px; border-radius:999px;
  background:{soft}; border:1.5px solid {accent}55; color:#2b2036; white-space:nowrap;
}}
html.rag-dark .rag-heute-chip {{background:#132b4d; border-color:{accent}66; color:#e7edf5;}}
.rag-heute-row {{font-size:.88rem; opacity:.85; margin:.15rem 0;}}
.rag-heute-date {{
  margin:.15rem 0 .45rem; color:#606778; font-size:.9rem; line-height:1.4;
  font-variant-numeric:normal; font-feature-settings:normal;
  font-variant-emoji:text;
  letter-spacing:0; white-space:nowrap; overflow-wrap:normal; word-break:keep-all;
}}
html.rag-dark .rag-heute-date {{ color:#aebdd1; }}

/* Lernmaskottchen (siehe ragapp.ui._mascot) - Grundgeruest + Bewegungs-
   Varianten (float/wave/run/shake) plus Augen, Props und Sparkles. */
.rag-mascot svg {{display:block; margin:0 auto; filter:drop-shadow(0 10px 14px rgba(43,32,54,.16));
  overflow:visible;}}
.ragm-pupil-l, .ragm-pupil-r {{transition:transform .09s linear;}}

/* Idle: Atmen + leichtes Schweben (lebiger als reines Float). */
.rag-mascot-float {{animation:ragMascotBreathe 3.6s ease-in-out infinite;}}
@keyframes ragMascotBreathe {{
  0%,100% {{transform:translateY(0) rotate(-1.2deg) scale(1);}}
  50%     {{transform:translateY(-8px) rotate(1.2deg) scale(1.02);}}
}}
.rag-mascot-float .ragm-body {{animation:ragmBodyPulse 3.6s ease-in-out infinite;}}
@keyframes ragmBodyPulse {{
  0%,100% {{transform:scale(1); transform-origin:110px 128px;}}
  50%     {{transform:scale(1.015); transform-origin:110px 128px;}}
}}
.rag-mascot-float .ragm-prop,
.rag-mascot-wave .ragm-prop {{animation:ragmPropBob 2.8s ease-in-out infinite;}}
@keyframes ragmPropBob {{
  0%,100% {{transform:translateY(0);}}
  50%     {{transform:translateY(-4px);}}
}}

/* Begruessung: Schweben + rechter Arm winkt, linker Arm leicht gegenphasig. */
.rag-mascot-wave {{animation:ragMascotBreathe 3.6s ease-in-out infinite;}}
.rag-mascot-wave .ragm-arm-r {{animation:ragmArmWave 1.15s ease-in-out infinite;}}
.rag-mascot-wave .ragm-arm-l {{animation:ragmArmWaveSoft 1.15s ease-in-out infinite .2s;}}
@keyframes ragmArmWave {{
  0%,100% {{transform:rotate(0deg);}}
  30%     {{transform:rotate(-26deg);}}
  60%     {{transform:rotate(-6deg);}}
}}
@keyframes ragmArmWaveSoft {{
  0%,100% {{transform:rotate(0deg);}}
  40%     {{transform:rotate(12deg);}}
}}

/* Besorgt: leichtes Zittern (Streak/Leeches). */
.rag-mascot-shake {{animation:ragmShake .55s ease-in-out infinite;}}
@keyframes ragmShake {{
  0%,100% {{transform:translateX(0) rotate(-2deg);}}
  25%     {{transform:translateX(-3px) rotate(-4deg);}}
  75%     {{transform:translateX(3px) rotate(1deg);}}
}}

/* Huepfender "Renn"-Bounce (Lernzeit / Pomodoro). */
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

/* Cheer-Sparkles: leichte Puls-/Drehung. */
.ragm-sparkle {{animation:ragmSparkle 1.8s ease-in-out infinite; transform-origin:110px 60px;}}
@keyframes ragmSparkle {{
  0%,100% {{opacity:.7; transform:scale(1) rotate(0deg);}}
  50%     {{opacity:1; transform:scale(1.12) rotate(8deg);}}
}}

.ragm-blink {{animation:ragmBlink 5.4s ease-in-out infinite;}}
@keyframes ragmBlink {{
  0%, 92%, 100% {{transform:scaleY(1);}}
  95%           {{transform:scaleY(.12);}}
}}
.ragm-wink-loop {{animation:ragmWink 6.8s ease-in-out infinite;}}
@keyframes ragmWink {{
  0%, 90%, 100% {{transform:scaleY(1);}}
  94%           {{transform:scaleY(.08);}}
}}
.ragm-sleepy {{transform:scaleY(.45);}}
@media (prefers-reduced-motion: reduce) {{
  .rag-mascot-float, .rag-mascot-wave, .rag-mascot-run, .rag-mascot-shake,
  .rag-mascot-wave .ragm-arm-r, .rag-mascot-wave .ragm-arm-l,
  .rag-mascot-run .ragm-leg-l, .rag-mascot-run .ragm-leg-r,
  .rag-mascot-float .ragm-body, .rag-mascot-float .ragm-prop, .rag-mascot-wave .ragm-prop,
  .ragm-blink, .ragm-wink-loop, .ragm-sparkle {{animation:none !important;}}
}}

/* Home: Maskottchen + Sprechblase als eine Einheit (Blase zeigt nach rechts). */
.rag-mascot-hero-unit {{
  display:flex; flex-direction:column; align-items:center; gap:.35rem;
}}
.rag-bubble-mascot {{
  position:relative; border:2px solid rgba(43,32,54,.16); border-radius:16px;
  background:#ffffff; padding:.55rem .85rem; margin:0 0 .2rem;
  font-size:.88rem; font-weight:600; line-height:1.35; text-align:center;
  box-shadow:0 2px 0 rgba(43,32,54,.05); max-width:220px;
}}
.rag-bubble-mascot::after {{
  content:""; position:absolute; left:50%; bottom:-8px; width:14px; height:14px;
  margin-left:-7px; background:#ffffff; border-right:2px solid rgba(43,32,54,.16);
  border-bottom:2px solid rgba(43,32,54,.16); transform:rotate(45deg);
}}
html.rag-dark .rag-bubble-mascot {{background:#0f2440; border-color:rgba(231,237,245,.16); color:#e7edf5;}}
html.rag-dark .rag-bubble-mascot::after {{background:#0f2440; border-color:rgba(231,237,245,.16);}}

.rag-heute-schedule {{list-style:none; padding:0; margin:.35rem 0 .55rem;}}
.rag-heute-schedule li {{
  font-size:.88rem; opacity:.9; padding:.2rem 0; border-bottom:1px solid rgba(43,32,54,.06);
}}
html.rag-dark .rag-heute-schedule li {{border-bottom-color:rgba(231,237,245,.08);}}

.rag-mascot-corner {{
  position:fixed; right:16px; bottom:10px; z-index:5; pointer-events:none;
  opacity:.92;
}}
@media (max-height: 620px), (max-width: 700px) {{
  .rag-mascot-corner {{display:none;}}
}}
@media (max-width: 480px) {{
  .rag-mascot-hero-unit .rag-mascot svg {{width:110px !important; height:auto !important;}}
  .rag-bubble-mascot {{max-width:100%; font-size:.82rem;}}
}}

/* Einheitliches Hover-/Klick-Gefuehl fuer ALLE normalen Buttons app-weit -
   vorher fuehlten sich nur die Home-Kacheln "lebendig" an (Skalierung +
   Schatten beim Hover), jeder andere Button ueberall sonst blieb komplett
   statisch - Klickbares und nicht-Klickbares liess sich dadurch nicht auf
   den ersten Blick unterscheiden. Bewusst DEZENTER als die grossen Kacheln
   (kein Scale, nur ein kleines Anheben) - bei vielen Buttons auf einer Seite
   waere eine kachel-starke Animation ueberall zu viel Bewegung auf einmal.
   Kommt VOR der Kachel-Regel unten, die (durch die spezifischere
   Attribut-Selektor-Kombination) ihr eigenes, staerkeres Hover-Verhalten
   trotzdem behaelt. */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{
  transition:transform .12s ease, box-shadow .12s ease, border-color .12s ease;
}}
.stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover {{
  transform:translateY(-1px);
  box-shadow:0 3px 10px rgba(0,0,0,.10);
}}
.stButton > button:active, .stDownloadButton > button:active, .stFormSubmitButton > button:active {{
  transform:translateY(0);
  box-shadow:0 1px 3px rgba(0,0,0,.08);
}}
.stButton > button:disabled, .stDownloadButton > button:disabled,
.stFormSubmitButton > button:disabled,
button[kind="primary"]:disabled, [data-testid="stBaseButton-primary"]:disabled {{
  transform:none !important; box-shadow:none !important; opacity:1 !important;
  background:#e8e4df !important; border-color:#ddd8d2 !important;
  color:#6b6570 !important;
}}
html.rag-dark .stButton > button:disabled,
html.rag-dark button[kind="primary"]:disabled,
html.rag-dark [data-testid="stBaseButton-primary"]:disabled {{
  background:#2a3a52 !important; border-color:#3a4d68 !important; color:#9aa8bb !important;
}}
button[kind="primary"], button[kind="primaryFormSubmit"],
[data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-primaryFormSubmit"] {{
  background:#b83250 !important; border-color:#b83250 !important;
  color:#ffffff !important; font-weight:750 !important;
}}
button[kind="primary"]:hover, button[kind="primaryFormSubmit"]:hover,
[data-testid="stBaseButton-primary"]:hover,
[data-testid="stBaseButton-primaryFormSubmit"]:hover {{
  background:#982a43 !important; border-color:#982a43 !important;
}}
html.rag-dark .stButton > button:hover, html.rag-dark .stDownloadButton > button:hover,
html.rag-dark .stFormSubmitButton > button:hover {{
  box-shadow:0 3px 10px rgba(0,0,0,.35);
}}

/* Tap-Ziele am Handy: ein Live-Test bei 390px zeigte 40px hohe Buttons (z. B.
   die drei Bewertungs-Knoepfe beim Lernen) - knapp unter der von Apple/Google
   empfohlenen 44px-Komfortzone. Nur auf schmalen Viewports angehoben (auf
   dem Desktop bleibt die kompaktere Groesse, dort tippt niemand mit dem
   Finger). */
@media (max-width: 480px) {{
  .block-container {{
    padding-top:3.5rem !important;
    padding-left:1rem !important; padding-right:1rem !important;
  }}
  .stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{
    min-height:44px;
  }}
  /* Der native Chat-Senden-Knopf (st.chat_input) ist mit 32x32px der am
     haeufigsten getippte Button der App und blieb bei der obigen Regel aussen
     vor (kein .stButton, sondern ein eigenes Streamlit-Element). */
  [data-testid="stChatInputSubmitButton"] {{
    min-width:44px !important; min-height:44px !important;
  }}
  /* Streamlit wickelt benachbarte markdown-Divs nicht zu einem Parent -
     deshalb haengt das Hero-Maskottchen in einem benannten Container. */
  div[class*="st-key-mascot_hero"],
  .rag-mascot-hero-unit {{display:none !important;}}
  .rag-hero-title {{
    display:block !important; width:100% !important; max-width:100% !important;
    font-size:1.7rem !important; line-height:1.08 !important;
    overflow:visible !important;
  }}
  .rag-hero-title .rag-hero-letter {{
    animation:none !important; opacity:1 !important; transform:none !important;
  }}
}}

/* Skeleton-Ladeplatzhalter (siehe ragapp.ui._loading.skeleton()) - schimmernde
   graue Balken statt Spinner+Text beim ersten Oeffnen einer Seite. Der
   Farbverlauf wandert per Keyframe von links nach rechts durch jeden Balken;
   ``prefers-reduced-motion`` deckelt das auf ein reines, unbewegtes Grau. */
.rag-skel {{ display:flex; flex-direction:column; gap:10px; margin:.35rem 0 .6rem; }}
.rag-skel-bar {{
  height:16px; border-radius:8px; background-color:{soft};
  background-image:linear-gradient(90deg, {soft} 0%, rgba(255,255,255,.85) 50%, {soft} 100%);
  background-size:200% 100%;
  animation:ragSkelShimmer 1.4s ease-in-out infinite;
}}
@keyframes ragSkelShimmer {{
  0% {{ background-position:200% 0; }}
  100% {{ background-position:-200% 0; }}
}}
html.rag-dark .rag-skel-bar {{
  background-color:#3a3450;
  background-image:linear-gradient(90deg, #3a3450 0%, #55507a 50%, #3a3450 100%);
}}
@media (prefers-reduced-motion: reduce) {{
  .rag-skel-bar {{ animation:none; background-image:none; }}
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

/* Hamburger-Popover (st.popover) freundlicher rund statt eckig-technisch.
   Inhalt scrollbar, sonst schneidet Mobile die unteren Einträge ab. */
[data-testid="stPopover"] button {{
  border-radius:14px !important;
}}
[data-testid="stPopoverBody"],
div[data-baseweb="popover"] [data-testid="stVerticalBlock"] {{
  max-height:min(80vh, 560px); overflow-y:auto;
}}
@media (max-width: 700px) {{
  [data-testid="stPopover"] {{ width:100%; }}
}}
.rag-nav-here {{
  display:block; padding:.45rem .75rem; margin:.12rem 0; border-radius:12px;
  background:{soft}; color:#2b2036; font-weight:650;
  border:2px solid {accent};
}}
html.rag-dark .rag-nav-here {{ color:#e7edf5; background:#132b4d; }}
.rag-kurs-title {{
  font-weight:700; margin:0 0 .35rem; overflow-wrap:anywhere; line-height:1.3;
}}

/* Dark-Mode-Umschalter (siehe _theme_toggle_html()) - schwebender runder
   Button oben rechts, ausserhalb des Streamlit-Baums direkt an <body>.
   z-index MUSS ueber Streamlits eigenem (immer im DOM vorhandenem, auch ohne
   offenen Dialog) stDialog-Portal-Wrapper liegen (dort per Playwright
   gemessen: z-index 1000059, volle Viewport-Flaeche, pointer-events:auto -
   faengt sonst JEDEN Klick ab, obwohl visuell nichts zu sehen ist) - daher
   bewusst der maximal moegliche CSS-z-index statt nur "hoch genug fuer jetzt". */
#rag-theme-switch {{
  position:fixed; top:max(14px, env(safe-area-inset-top));
  right:max(18px, env(safe-area-inset-right)); z-index:2147483647;
  width:44px; height:44px; border-radius:50%;
  border:1px solid {soft}; background:#ffffff; cursor:pointer;
  font-size:1.15rem; line-height:1; display:flex; align-items:center; justify-content:center;
  box-shadow:0 2px 10px rgba(0,0,0,.10);
  transition:transform .18s ease, box-shadow .18s ease;
}}
#rag-theme-switch:hover {{transform:scale(1.08); box-shadow:0 6px 16px rgba(0,0,0,.16);}}
html.rag-dark #rag-theme-switch {{
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
html.rag-dark .rag-hero-title {{color:#e7edf5 !important;}}

@media (prefers-reduced-motion: reduce) {{
  .block-container, .rag-doodle, h1, .rag-hero-title span,
  .rag-hero-title .rag-hero-letter {{
    animation:none !important; opacity:1 !important; transform:none !important;
  }}
  .stButton > button, .stDownloadButton > button, .stFormSubmitButton > button,
  div[class*="st-key-tile_"] button, #rag-theme-switch {{
    transition:none !important;
  }}
  .stButton > button:hover, .stDownloadButton > button:hover,
  .stFormSubmitButton > button:hover, div[class*="st-key-tile_"] button:hover {{
    transform:none !important;
  }}
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
  @media (prefers-reduced-motion: reduce) {{
    #rag-elevator {{ display:none !important; }}
  }}
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
# (nicht nur im Chat/dieser Seite), persistiert in parent.localStorage, wirkt
# SOFORT ohne Streamlit-Rerun (reiner Client-Toggle, setzt "rag-dark"/"rag-light"
# direkt auf <html>). Bewusst NUR 2 Klick-Zustaende (Hell/Dunkel) statt 3
# (Auto/Hell/Dunkel) - ein Nutzer-Report zeigte: bei OS-Einstellung "Hell" sah ein
# Klick von Auto auf Hell OPTISCH GAR NICHTS anders aus (beides rendert hell), was
# wie ein kaputter Button wirkte, obwohl der Klick technisch funktionierte.
#
# WARUM der Handler am Button haengt und bei JEDEM Inject neu gesetzt wird:
# ``components.html()`` laeuft in einem Iframe. Ein einmalig auf parent.document
# gebundener Listener (plus Flag "schon gebunden") ist nach der ersten
# Streamlit-Navigation tot: React unmountet das Iframe, der Browser verwirft
# dessen Event-Listener, das Flag auf dem Parent bleibt aber stehen - jeder
# weitere Inject ueberspringt das Binden, Klicks tun dann gar nichts. Live
# reproduziert: Home (frisch) klickt, nach Menue->Chat klickt nichts mehr.
# ``btn.onclick = ...`` vom jeweils lebenden Iframe ueberschreibt den toten
# Handler. Speicher/matchMedia laufen bewusst ueber window.parent, nicht ueber
# das Iframe (dessen localStorage nach Unmount unbrauchbar ist).
# --------------------------------------------------------------------------- #
def _theme_toggle_html() -> str:
    return """
<script>
(function() {
  try {
    var parent = window.parent;
    var doc = parent.document;
    var root = doc.documentElement;
    var store = parent.localStorage;
    var KEY = 'rag-theme';
    var mql = parent.matchMedia ? parent.matchMedia('(prefers-color-scheme: dark)') : null;

    function effective(saved) {
      if (saved === 'light' || saved === 'dark') { return saved; }
      return (mql && mql.matches) ? 'dark' : 'light';
    }
    function label(effMode) { return effMode === 'dark' ? '🌙' : '☀️'; }
    function title(effMode) {
      return 'Darstellung: ' + (effMode === 'dark' ? 'Dunkel' : 'Hell') +
             ' (Klick zum Umschalten)';
    }
    function apply(effMode) {
      root.classList.remove('rag-dark', 'rag-light');
      root.classList.add(effMode === 'dark' ? 'rag-dark' : 'rag-light');
    }
    function readSaved() {
      try { return store.getItem(KEY); } catch (err) { return null; }
    }
    function writeSaved(value) {
      try { store.setItem(KEY, value); } catch (err) {}
    }

    apply(effective(readSaved()));

    if (mql && !parent.__ragThemeMqlBound) {
      parent.__ragThemeMqlBound = true;
      mql.addEventListener('change', function() {
        if (!readSaved()) { apply(effective(null)); }
      });
    }

    // Neue id, damit ein noch lebender Capture-Listener alter Builds
    // (closest('#rag-theme-toggle')) diesen Button nicht mehr mit-umschaltet
    // und den Klick optisch wieder zurueckdreht.
    var btn = doc.getElementById('rag-theme-switch') || doc.getElementById('rag-theme-toggle');
    if (!btn) {
      btn = doc.createElement('button');
      btn.setAttribute('aria-label', 'Darstellung wechseln');
      btn.setAttribute('aria-pressed', effective(readSaved()) === 'dark' ? 'true' : 'false');
      doc.body.appendChild(btn);
    }
    btn.id = 'rag-theme-switch';
    btn.type = 'button';
    btn.inert = false;
    btn.textContent = label(effective(readSaved()));
    btn.title = title(effective(readSaved()));
    btn.setAttribute('aria-pressed', effective(readSaved()) === 'dark' ? 'true' : 'false');

    // Jeder Inject ersetzt den Handler. Nicht einmalig auf document delegieren:
    // der alte Iframe-Listener stirbt, ein Flag auf dem Parent wuerde Rebinds
    // danach dauerhaft verhindern (siehe Funktions-Docstring).
    btn.onclick = function(e) {
      e.preventDefault();
      e.stopPropagation();
      var next = effective(readSaved()) === 'dark' ? 'light' : 'dark';
      writeSaved(next);
      apply(next);
      btn.textContent = label(next);
      btn.title = title(next);
      btn.setAttribute('aria-pressed', next === 'dark' ? 'true' : 'false');
    };

    // Streamlit setzt bei Navigation "inert" auf direkte body-Kinder. Der
    // Timer muss auf dem PARENT laufen - ein setInterval im Iframe stirbt
    // mit dem Iframe, genau wie der alte Klick-Listener.
    if (!parent.__ragThemeInertTimer) {
      parent.__ragThemeInertTimer = parent.setInterval(function() {
        var b = parent.document.getElementById('rag-theme-switch');
        if (b && b.inert) { b.inert = false; }
      }, 200);
    }
  } catch (e) {
    try { console.warn('rag-theme', e); } catch (err) {}
  }
})();
</script>
"""


def _command_palette_shortcut_html() -> str:
    """Strg/Cmd+K springt von JEDER Seite direkt zur "Ueberall suchen"-Box auf
    Home (ragapp/search.py) - angelehnt an die Befehlspaletten grosser Apps
    (Notion/Linear/Superhuman), aber der Streamlit-Seitenarchitektur angepasst:
    kein schwebendes Overlay (das braeuchte eine eigenstaendige, seiten-
    uebergreifende Komponente), sondern ein echter Sprung zu Home + Auto-Fokus
    dort. Ist das Suchfeld schon auf der aktuellen Seite (= wir sind schon auf
    Home), wird nur gescrollt/fokussiert statt neu geladen. Einmalig pro
    Sitzung gebunden.

    WICHTIG: ``components.html()`` rendert in ein sandboxed Iframe OHNE
    ``allow-top-navigation`` - ein direktes ``window.parent.location.href = ..``
    wird darin vom Browser verweigert (getestet: "Unsafe attempt to initiate
    navigation ... sandboxed"). Deshalb NICHT selbst navigieren, sondern
    Streamlits eigenen, echten Sidebar-Link zu Home (der schon Teil des NICHT
    sandboxed Eltern-Dokuments ist) per ``.click()`` ausloesen - das zaehlt als
    normale Link-Navigation und ist erlaubt. Ein sessionStorage-Flag (reine
    Speicheroperation, keine Navigation, daher ebenfalls erlaubt) sagt Home
    hinterher, den Fokus zu setzen (siehe Home.py)."""
    return """
<script>
(function() {
  try {
    var win = window.parent;
    var doc = win.document;
    if (doc.__ragCmdKBound) { return; }
    doc.__ragCmdKBound = true;
    doc.addEventListener('keydown', function(e) {
      if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== 'k') { return; }
      var t = e.target;
      var tag = t && t.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || (t && t.isContentEditable)) { return; }
      e.preventDefault();
      var input = doc.querySelector('input[aria-label*="Überall suchen"]')
        || doc.querySelector('input[aria-label*="Notizen, Chats"]')
        || doc.querySelector('input[aria-label*="Notizen, Chats und Zusammenfassungen"]');
      if (input) {
        input.scrollIntoView({block: 'center', behavior: 'smooth'});
        input.focus();
        return;
      }
      var links = doc.querySelectorAll('a[href]');
      for (var i = 0; i < links.length; i++) {
        try {
          if (new win.URL(links[i].href, win.location.href).pathname === '/') {
            win.sessionStorage.setItem('ragFocusSearch', '1');
            links[i].click();
            break;
          }
        } catch (e2) {}
      }
    }, true);
  } catch (e) {}
})();
</script>
"""


# --------------------------------------------------------------------------- #
# Sound/Vibration - BEWUSST sparsam (siehe Docstrings): ein Studien-Tool wird
# oft in der Bibliothek/im Hoersaal benutzt, wo ein hoerbarer Ton bei JEDER
# einzelnen Karte stoeren bzw. peinlich sein koennte (anders als bei einer
# Casual-App wie Duolingo). Deshalb: Ton NUR beim seltenen, echten Meilenstein
# (Errungenschaft freigeschaltet), Vibration zusaetzlich auch beim haeufigeren,
# aber stillen/privaten Kombo-Meilenstein (3er-Schritte, siehe Lernen.py).
# Beides synthetisiert per Web Audio API - kein Audio-Asset noetig, bleibt
# offlinefaehig. Vibration ist eh geraeuschlos (nur am Handy spuerbar) und
# daher grosszuegiger einsetzbar als Ton.
# --------------------------------------------------------------------------- #
def celebration_effects_html() -> str:
    """Kurzer, freundlicher Zweiklang (Web Audio API, keine Datei) + stuermischeres
    Vibrationsmuster - fuer den SELTENEN, echten Feiermoment (Errungenschaft
    frisch freigeschaltet). Ergaenzt die schon vorhandenen Balloons/den
    Maskottchen-Jubel um eine hoer-/spuerbare Komponente, statt rein visuell zu
    bleiben. Nutzt einen auf ``window.parent`` zwischengespeicherten
    AudioContext (nicht bei jedem Aufruf neu erzeugen - Browser drosseln/warnen
    sonst)."""
    return """
<script>
(function() {
  try {
    var win = window.parent;
    var Ctx = win.AudioContext || win.webkitAudioContext;
    if (Ctx) {
      var ctx = win.__ragAudioCtx || (win.__ragAudioCtx = new Ctx());
      if (ctx.state === 'suspended') { ctx.resume().catch(function(){}); }
      var now = ctx.currentTime;
      [523.25, 659.25, 783.99].forEach(function(freq, i) {
        var osc = ctx.createOscillator();
        var gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.value = freq;
        var t0 = now + i * 0.09;
        gain.gain.setValueAtTime(0.0001, t0);
        gain.gain.exponentialRampToValueAtTime(0.16, t0 + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.3);
        osc.connect(gain); gain.connect(ctx.destination);
        osc.start(t0); osc.stop(t0 + 0.32);
      });
    }
    if (win.navigator && win.navigator.vibrate) { win.navigator.vibrate([30, 40, 30, 40, 60]); }
  } catch (e) {}
})();
</script>
"""


def combo_pulse_html() -> str:
    """Ein einzelner, ganz kurzer Vibrations-Puls fuer den Kombo-Meilenstein
    (jede 3. Karte in Folge "gewusst", siehe Lernen.py) - bewusst OHNE Ton
    (haeufiger als ein Errungenschaft-Unlock, ein Ton dafuer waere zu viel),
    aber ein kaum wahrnehmbarer Handy-Puls schadet nicht und gibt der
    haeufigsten guten Serie trotzdem ein kleines haptisches Echo."""
    return """
<script>
(function() {
  try {
    var win = window.parent;
    if (win.navigator && win.navigator.vibrate) { win.navigator.vibrate(15); }
  } catch (e) {}
})();
</script>
"""


# --------------------------------------------------------------------------- #
# Uebersetzt die wenigen fest verdrahteten englischen Strings, die Streamlit
# selbst (nicht ueber unseren Code) ausgibt - z. B. der Datei-Upload-Button
# ("Upload"/"500MB per file"), fuer die es keinen deutschen Parameter gibt.
# Per MutationObserver dauerhaft nachgefuehrt (nicht nur einmalig), da
# Streamlit den Dropzone-Inhalt bei jedem Rerun neu rendert. Absichtlich als
# EIGENE, erweiterbare Stelle angelegt - weitere fest verdrahtete englische
# Reste landen hier, statt verstreut an vielen Seiten gepatcht zu werden.
# --------------------------------------------------------------------------- #
def _i18n_patch_html() -> str:
    return """
<script>
(function() {
  try {
    var doc = window.parent.document;
    // Fuer "hyphens: auto" auf Ueberschriften (siehe _BASE_CSS) muss der
    // Browser wissen, dass der Text deutsch ist - Streamlit setzt selbst
    // kein lang-Attribut auf <html>.
    if (doc.documentElement.lang !== 'de') { doc.documentElement.lang = 'de'; }

    function patchOnce() {
      doc.querySelectorAll('[data-testid="stFileUploaderDropzone"]').forEach(function(dz) {
        var label = dz.querySelector('[data-testid="stBaseButton-secondary"] [data-testid="stMarkdownContainer"]');
        if (label && label.textContent.trim() === 'Upload') { label.textContent = 'Hochladen'; }
        var instr = dz.querySelector('[data-testid="stFileUploaderDropzoneInstructions"]');
        if (instr) {
          Array.from(instr.querySelectorAll('span')).forEach(function(span) {
            var t = span.textContent;
            if (t.indexOf('Drag and drop') !== -1) {
              span.textContent = 'Datei hierher ziehen';
            } else if (t.indexOf('Limit') !== -1 || t.indexOf('per file') !== -1) {
              span.textContent = t.replace('Limit', 'Grenze').replace('per file', 'pro Datei');
            }
          });
        }
      });
      doc.querySelectorAll('p, span, div').forEach(function(el) {
        if (el.children.length) { return; }
        var t = (el.textContent || '').trim();
        if (t === 'Choose options' || t === 'Choose an option') {
          el.textContent = 'Auswählen …';
        }
      });
    }

    patchOnce();
    if (!doc.__ragI18nBound) {
      doc.__ragI18nBound = true;
      new MutationObserver(patchOnce).observe(doc.body, {childList: true, subtree: true});
    }
  } catch (e) {}
})();
</script>
"""


# --------------------------------------------------------------------------- #
# Hamburger-Kurzwahl: die fünf Zielgruppen (GOAL_HUB_KEYS), darunter alle
# uebrigen Seiten nach Kategorie. Beenden und zweites Fenster liegen zusaetzlich
# im Menue (nicht nur in der auf dem Handy unsichtbaren Sidebar).
# --------------------------------------------------------------------------- #
def render_hamburger_nav(current_page_key: str) -> None:
    """Kurzwahl der fünf Zielgruppen (HAMBURGER_KEYS) PLUS - darunter,
    nach Kategorie gruppiert wie die Home-Kacheln - alle uebrigen Seiten. Bis
    Version X gab es hier NUR die Kurzwahl: von einer Nicht-Kurzwahl-Seite
    (14 von 18) aus fuehrte JEDE Navigation ueber einen Umweg zurueck zu Home.
    Die Kategorie-Gruppierung uebernimmt bewusst dieselbe Reihenfolge/
    Einteilung wie PAGE_REGISTRY (siehe Home-Kacheln), damit Nutzer nicht
    zwei verschiedene Gliederungen im Kopf behalten muessen.

    BEWUSST NICHT (mehr) in ``st.sidebar``: Streamlit klappt die Sidebar auf
    schmalen (Handy-)Viewports automatisch komplett aus dem sichtbaren Bereich
    (``transform: translateX(-300px)``, ausserhalb des Viewports) - ein
    Live-Test mit echter Handy-Breite (390px) zeigte, dass der Menu-Button
    dadurch fuer Playwright/einen Finger schlicht UNERREICHBAR war, ohne
    vorher den winzigen 28px-Pfeil oben links zu treffen. Die eigentliche
    Navigation der App gehoert deshalb in den normalen Seiteninhalt (oben,
    vor dem Titel) - dort ist sie auf jedem Geraet ohne Umweg erreichbar."""
    with st.popover("☰ Menü", use_container_width=False):
        st.caption("Schnellzugriff")
        for cat, key in zip(GOAL_CATEGORIES, HAMBURGER_KEYS, strict=True):
            page = _PAGE_BY_KEY.get(key)
            if not page:
                continue
            is_here = key == current_page_key
            shown = "Heute" if key == "home" else page["title"]
            if is_here:
                st.markdown(
                    f'<div class="rag-nav-here">{page["icon"]} {shown} · hier</div>',
                    unsafe_allow_html=True)
            elif st.button(f"{page['icon']} {shown}", key=f"hamburger_{key}",
                           use_container_width=True):
                _go_to(page)

        st.divider()
        _seen_categories: list[str] = []
        for page in PAGE_REGISTRY:
            cat = page["category"]
            if not cat or cat in _seen_categories:
                continue
            _seen_categories.append(cat)
            st.caption(cat)
            for _p in PAGE_REGISTRY:
                if _p["category"] != cat:
                    continue
                if _p["key"] in HIDDEN_PAGE_KEYS or _p["key"] in HAMBURGER_KEYS:
                    continue
                is_here = _p["key"] == current_page_key
                if is_here:
                    st.markdown(
                        f'<div class="rag-nav-here">{_p["icon"]} {_p["title"]} · hier</div>',
                        unsafe_allow_html=True)
                elif st.button(f"{_p['icon']} {_p['title']}",
                               key=f"hamburger_all_{_p['key']}",
                               use_container_width=True):
                    _go_to(_p)

        st.divider()
        st.caption("Sitzung")
        from ragapp.ui._auth import render_session_controls
        render_session_controls(key_suffix="hamburger")


def _go_to(page: dict) -> None:
    # st.switch_page() stoppt die Skript-Ausfuehrung selbst (wie st.stop()) und
    # navigiert - kein zusaetzliches st.rerun() noetig/erreichbar danach.
    target = page["target"]
    if target is None:
        st.switch_page("🏠_Home.py")
    else:
        st.switch_page(target)


def render_nav_tile(page_key: str, *, title: str | None = None,
                    subtitle: str | None = None) -> None:
    """Eine Home-Kachel fuer die gegebene Seite (aus PAGE_REGISTRY) - echter
    st.button in einem benannten Container (siehe _BASE_CSS-Selektor oben),
    kein HTML-Overlay-Trick noetig (Streamlit >=1.something vergibt bei
    ``key=`` automatisch die CSS-Klasse ``st-key-<key>``)."""
    page = _PAGE_BY_KEY[page_key]
    with st.container(key=f"tile_{page_key}"):
        shown_title = title if title is not None else page["title"]
        shown_sub = subtitle if subtitle is not None else page["subtitle"]
        label = f"{page['icon']}\n\n**{shown_title}**\n{shown_sub}"
        if st.button(label, key=f"tile_btn_{page_key}", use_container_width=True):
            _go_to(page)


def render_goal_tile(category: str) -> None:
    """Home-Kachel mit einem konkreten Ziel statt abstraktem Gruppennamen."""
    hub = GOAL_HUB_KEYS[category]
    page_key = "lernplan" if hub == "home" else hub
    page = _PAGE_BY_KEY[page_key]
    render_nav_tile(page_key, title=page["title"], subtitle=page["subtitle"])


def card(key: str):
    """Weiche, abgerundete Karte fuer eine Inhalts-Gruppe auf einer Seite -
    als Kontext-Manager verwenden: ``with card("stats"): st.metric(...)``.
    Echter ``st.container(key=...)``, gestylt ueber die automatisch vergebene
    Klasse ``st-key-card_<key>`` (siehe _BASE_CSS) - kein HTML-Overlay noetig."""
    return st.container(key=f"card_{key}")


def _hero_title_html(text: str) -> str:
    """Baut das HTML fuer render_hero_title() (reine String-Funktion, siehe
    dort fuer die Wort-Wrapper-Begruendung) - ausgelagert, damit die
    Umbruch-Korrektheit ohne Streamlit-Laufzeit testbar ist."""
    words = text.split(" ")
    letter_i = 0
    word_htmls = []
    for word in words:
        letters = []
        for ch in word:
            letters.append(f'<span class="rag-hero-letter" '
                          f'style="animation-delay:{letter_i * 0.035:.3f}s">{ch}</span>')
            letter_i += 1
        word_htmls.append(f'<span class="rag-hero-word">{"".join(letters)}</span>')
        letter_i += 1  # kleine zusaetzliche Verzoegerung fuer die Wortluecke
    return f'<h1 class="rag-hero-title">{" ".join(word_htmls)}</h1>'


def render_hero_title(text: str, *, accent: str | None = None) -> None:
    """Grosse Willkommens-Ueberschrift mit Buchstabe-fuer-Buchstabe-Einflug -
    fuer den EINEN Blickfang-Moment einer Seite (z. B. Home), nicht als
    Ersatz fuer normale ``st.title()``-Aufrufe gedacht (die bekommen ihre
    eigene, dezentere Fly-in-Animation schon automatisch ueber den globalen
    ``h1``-Stil in _BASE_CSS).

    Jedes WORT (nicht jeder Buchstabe) steckt in einem eigenen
    ``display:inline-block``-Wrapper (siehe ``_hero_title_html()``): ein
    Live-Test bei Handy-Breite (390px) zeigte, dass der Browser sonst mitten
    im Wort umbricht ("Willkommen zurü/ck") - jeder Buchstabe war zuvor SEIN
    EIGENES inline-block-Element, wodurch der Browser die Wortgrenze
    verliert und zwischen JEDEM Buchstaben umbrechen darf. Der Wort-Wrapper
    macht das Wort selbst wieder atomar; umbrechen darf der Browser
    weiterhin (normal) zwischen den Woertern."""
    st.markdown(_hero_title_html(text), unsafe_allow_html=True)


def speech_bubble(text: str, *, icon: str = "💡") -> None:
    """Comic-Sprechblase fuer einen kurzen Tipp/Hinweis (siehe ``.rag-bubble``
    in _BASE_CSS) - dezenter als ``st.info()``, aber verspielter: Text wird
    NICHT als Markdown interpretiert (nur escaped), da hier ausschliesslich
    kurze, feste Hinweistexte reinsollen, keine Nutzereingaben."""
    st.markdown(f'<div class="rag-bubble">{icon} {html_escape(text)}</div>',
                unsafe_allow_html=True)


def speech_bubble_mascot(text: str, *, icon: str = "👋") -> None:
    """Sprechblase direkt UEBER dem Maskottchen (Pfeil nach unten zur Figur)."""
    st.markdown(
        f'<div class="rag-bubble-mascot">{icon} {html_escape(text)}</div>',
        unsafe_allow_html=True,
    )


def empty_state(message: str, *, cta_label: str, page_key: str,
                icon: str = "📭", key: str | None = None) -> None:
    """Einheitlicher Leerzustand: Hinweis + Primaerbutton zu einer Registry-Seite."""
    st.info(f"{icon} {message}")
    page = _PAGE_BY_KEY.get(page_key)
    if not page or not page.get("target"):
        return
    btn_key = key or f"empty_cta_{page_key}"
    if st.button(cta_label, type="primary", key=btn_key, use_container_width=True):
        st.switch_page(page["target"])


def page_title(page_key: str) -> str:
    """Anzeigename aus PAGE_REGISTRY (fuer konsistente Texte)."""
    p = _PAGE_BY_KEY.get(page_key) or {}
    return f'{p.get("icon", "")} {p.get("title", page_key)}'.strip()


# --------------------------------------------------------------------------- #
# Loeschen mit Bestaetigung: gleicher Dialog auf allen Seiten (Dokumentenmanager
# behält seinen Spezial-Dialog mit Bibliothek/Index/Karten-Häkchen).
# --------------------------------------------------------------------------- #
_DELETE_PENDING = "_rag_delete_pending"
_DELETE_CONFIRMED = "_rag_delete_confirmed"


def _dismiss_shared_delete() -> None:
    st.session_state.pop(_DELETE_PENDING, None)


@st.dialog("🗑️ Wirklich löschen?", width="small", on_dismiss=_dismiss_shared_delete)
def _shared_delete_dialog(token: str, body: str) -> None:
    st.markdown(body)
    c1, c2 = st.columns(2)
    if c1.button("Abbrechen", use_container_width=True, key=f"_rag_del_cancel_{token}"):
        st.session_state.pop(_DELETE_PENDING, None)
        st.rerun()
    if c2.button("Jetzt löschen", type="primary", use_container_width=True,
                 key=f"_rag_del_go_{token}"):
        st.session_state[_DELETE_CONFIRMED] = token
        st.session_state.pop(_DELETE_PENDING, None)
        st.rerun()


def _open_pending_delete_dialog() -> None:
    pending = st.session_state.get(_DELETE_PENDING)
    if isinstance(pending, dict) and pending.get("token"):
        _shared_delete_dialog(
            str(pending["token"]), pending.get("body") or "Wirklich löschen?")


def sticky_expander(label: str, *, key: str, expanded: bool = False, **kwargs):
    """Expander, dessen Auf/Zu Streamlit über Reruns in ``session_state[key]`` hält.

    Ab Streamlit 1.59 greift ``key=`` dafür nur noch mit ``on_change="rerun"``.
    Ohne das klappt ein Formular-Expander beim ersten Widget-Rerun wieder zu,
    und Prefills können ihn nicht programmatisch öffnen.
    """
    kwargs.setdefault("on_change", "rerun")
    return st.expander(label, expanded=expanded, key=key, **kwargs)


def delete_button(label: str, *, token: str, body: str, key: str, **btn_kwargs) -> bool:
    """Lösch-Button mit Bestätigungsdialog. Gibt True zurück, nachdem bestätigt."""
    if st.session_state.get(_DELETE_CONFIRMED) == token:
        st.session_state.pop(_DELETE_CONFIRMED, None)
        return True
    kwargs = dict(btn_kwargs)
    kwargs.setdefault("use_container_width", True)
    if st.button(label, key=key, **kwargs):
        st.session_state[_DELETE_PENDING] = {"token": token, "body": body}
        st.rerun()
    return False


def block_done_banner(*, state_key: str, key_prefix: str) -> None:
    """Fragt nach einer Plan-Session, ob der Block erledigt ist."""
    bid = st.session_state.get(state_key)
    if not bid:
        return
    with st.container(border=True):
        st.markdown("##### Block erledigt?")
        st.caption("Du bist über den Lernplan hierher gekommen. "
                   "Soll der Block als erledigt gelten?")
        yes, no = st.columns(2)
        if yes.button("Ja, Block erledigt", type="primary",
                      key=f"{key_prefix}_block_yes", use_container_width=True):
            from ragapp.student_flow import mark_plan_block_done
            mark_plan_block_done(bid, via="manual")
            st.session_state.pop(state_key, None)
            st.success("Block als erledigt markiert.")
            st.rerun()
        if no.button("Noch offen lassen", key=f"{key_prefix}_block_no",
                     use_container_width=True):
            st.session_state.pop(state_key, None)
            st.rerun()


# --------------------------------------------------------------------------- #
# Haupt-Einstiegspunkt: von page_boot() fuer jede normale Seite aufgerufen,
# und direkt von der Home-Seite (🏠_Home.py), die ihre Boot-Sequenz aus
# Prozess-Start-Gruenden (Prewarm/Watchdog/Backup/PWA-Banner) manuell macht.
# --------------------------------------------------------------------------- #
def apply_page_style(page_key: str, *, show_nav: bool = True) -> dict:
    theme = theme_for(page_key)
    accent, soft = theme["accent"], theme["soft"]

    css = _FONT_FACE_CSS + _BASE_CSS.format(accent=accent, soft=soft)
    if page_key in TECHNICAL_PAGE_KEYS:
        css += _technical_override_css(soft)          # kein Doodle-Layer hier
    else:
        css += _doodle_layer(accent, soft)
    st.markdown(css, unsafe_allow_html=True)

    # Dark-Mode-Bootstrap + Umschalt-Button: UNBEDINGT bei jedem Aufruf. Der
    # Button-Handler MUSS nach jedem Iframe-Unmount neu gesetzt werden
    # (siehe _theme_toggle_html Docstring) - "einmalig binden" ist hier falsch.
    components.html(_theme_toggle_html(), height=0)
    components.html(_i18n_patch_html(), height=0)
    components.html(_command_palette_shortcut_html(), height=0)

    # Uebergangs-Animation NUR bei echter Seiten-Navigation abspielen (nicht
    # bei jedem Widget-Rerun innerhalb derselben Seite - siehe _transition_html
    # Docstring-Kommentar oben).
    if st.session_state.get("_rag_last_page") != page_key:
        st.session_state.pop(_DELETE_PENDING, None)
        st.session_state.pop(_DELETE_CONFIRMED, None)
        st.session_state["_rag_last_page"] = page_key
        components.html(_transition_html(accent, soft), height=0)

    _open_pending_delete_dialog()

    if show_nav:
        render_hamburger_nav(page_key)

    # Kleines Ecken-Maskottchen mit seiner Pose (siehe ragapp.ui._mascot.POSES) -
    # NICHT auf Home, das zeigt bereits sein eigenes, grosses Hero-Maskottchen.
    # Auf Home stattdessen eine evtl. von der VORHERIGEN Seite noch vorhandene
    # Instanz aktiv entfernen (sie haengt direkt an document.body, siehe
    # render_mascot_corner-Docstring - ein Seitenwechsel zu Home raeumt sie
    # sonst nie weg, weil Home render_mascot_corner() selbst nie aufruft).
    from ragapp.ui._mascot import render_mascot_corner, remove_mascot_corner, pose_for
    if page_key != "home":
        _pose, _anim, _prop = pose_for(page_key)
        render_mascot_corner(accent, pose=_pose, animation=_anim, prop=_prop)
    else:
        remove_mascot_corner()

    return theme
