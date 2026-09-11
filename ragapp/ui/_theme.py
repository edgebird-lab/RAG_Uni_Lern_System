"""
RAG-Lernsystem: zentrales UI-Theme (Light + Dark)
=================================================
Ein einziger Helfer ``apply_theme()``, den JEDE Seite direkt nach ``require_pin()``
aufruft. Er injiziert einmal ein Stylesheet, das sowohl den hellen als auch den
dunklen Modus sauber bedient.

Hintergrund: Bisher hatte nur die Lernen-Seite eine Dark-Mode-Sonderloesung. Auf
allen anderen Seiten blieben eigens injizierte HTML-Bausteine (Quellen-/Dokumenten-
Viewer, Karteikarten, Badges) hell eingefaerbt – im Dark-Mode also dunkler Text auf
dunklem Grund und damit unlesbar. Dieser Helfer zentralisiert die Kontrast-/
Farbfixes fuer Viewer, Tabellen, Code und Eingabefelder an EINER Stelle.

Dark-Mode ist EXPLIZIT umschaltbar (nicht mehr nur ``@media (prefers-color-
scheme)``): ``ragapp/ui/_style.py`` injiziert ein kleines Bootstrap-Skript, das
die Praeferenz aus ``localStorage`` liest (oder bei "Auto" live auf die OS-
Einstellung hoert) und die Klasse ``rag-dark`` auf das ECHTE ``<html>``-Element
setzt. Alle Dark-Regeln haengen deshalb bewusst an ``html.rag-dark ...`` statt an
einer Media Query - so wirkt ein manueller Toggle unabhaengig vom Betriebssystem.
``html.rag-dark`` auf dem Wurzelelement trifft auch von Streamlit "portalierte"
Overlays (BaseWeb-Popover/-Select/-Menu haengen oft direkt an ``<body>``, nicht an
``.stApp``) - waere die Klasse stattdessen auf ``.stApp`` gesetzt, wuerden genau
diese Overlays im Dark-Mode durchrutschen.

Dark-Palette bewusst dunkles MARINEBLAU statt neutralem Schwarz/Grau (Nutzer-
Wunsch) - alle Flaechen (#0a1930/#0f2440/#132b4d/#0c1f3a) und Rahmen (#1e3a5f)
teilen denselben Blauton, nur in unterschiedlicher Helligkeit, statt eines
"toten" Grautons.
"""
from __future__ import annotations

import streamlit as st

# --------------------------------------------------------------------------- #
# Das komplette Stylesheet. Der Light-Fall braucht (dank Streamlit-Basis „light")
# nur die Basis-Definition der Karteikarte; der Dark-Fall haengt komplett an
# ``html.rag-dark`` und ueberschreibt gezielt alle Stellen, die sonst hell hart
# verdrahtet sind. `!important`, weil dieses Stylesheet VOR den seiteneigenen
# (hellen) <style>-Bloecken injiziert wird.
# --------------------------------------------------------------------------- #
_THEME_CSS = """
<style>
/* --- Karteikarte (Lernen): "echte" Karte statt Hinweisbox - erhoehter Schatten,
   farbiger Kopfstreifen (Lernen-Akzent Smaragd), sanfte Einflug-Animation bei
   JEDER neuen Karte (das ist hier gewuenscht, nicht wie bei der Seiten-Uebergang-
   Animation zu drosseln - jede neue Frage soll sich wie ein frisch aufgedecktes
   Kaertchen anfuehlen). Basis = hell; Dark-Fall unten. --------------------- */
@keyframes ragKarteIn {
  from {opacity:0; transform:translateY(10px) scale(.975);}
  to   {opacity:1; transform:translateY(0) scale(1);}
}
.karte {
    position:relative; overflow:hidden;
    border:1px solid rgba(31,58,99,.08); border-radius:22px;
    padding:32px 32px 26px;
    background:linear-gradient(160deg,#ffffff 0%,#eef2fb 100%);
    font-size:1.18rem; line-height:1.6; min-height:130px;
    box-shadow:0 18px 34px -12px rgba(31,58,99,.28), 0 2px 8px rgba(31,58,99,.08);
    animation:ragKarteIn .4s cubic-bezier(.22,1,.36,1) both;
}
.karte::before {
    content:""; position:absolute; top:0; left:0; right:0; height:7px;
    background:linear-gradient(90deg,#61C9A8 0%,#B7ECDC 100%);
}
.karte-frage {font-weight:700; color:#1f3a63; font-size:1.05em;}
@media (prefers-reduced-motion: reduce) {
  .karte {animation:none !important;}
}

/* --- Flaeche / Grundgeruest ---------------------------------------------- */
html.rag-dark .stApp, html.rag-dark [data-testid="stAppViewContainer"],
html.rag-dark [data-testid="stHeader"]{background-color:#0a1930 !important;}
html.rag-dark [data-testid="stSidebar"]{background-color:#0c1f3a !important;}

/* --- Standard-Fliesstext hell (Ueberschriften/Absaetze/Metriken/Labels) --- */
html.rag-dark .stApp, html.rag-dark [data-testid="stAppViewContainer"],
html.rag-dark [data-testid="stMarkdownContainer"], html.rag-dark [data-testid="stMarkdownContainer"] p,
html.rag-dark [data-testid="stMarkdownContainer"] li, html.rag-dark [data-testid="stMarkdownContainer"] strong,
html.rag-dark h1, html.rag-dark h2, html.rag-dark h3, html.rag-dark h4, html.rag-dark h5, html.rag-dark h6,
html.rag-dark [data-testid="stMetricValue"], html.rag-dark [data-testid="stMetricLabel"],
html.rag-dark [data-testid="stMetricDelta"], html.rag-dark [data-testid="stWidgetLabel"],
html.rag-dark [data-testid="stWidgetLabel"] *{color:#e7edf5 !important;}
html.rag-dark [data-testid="stCaptionContainer"], html.rag-dark [data-testid="stCaptionContainer"] *{
    color:#93a8c4 !important;}
html.rag-dark a, html.rag-dark [data-testid="stMarkdownContainer"] a{color:#7fb8f0 !important;}

/* --- Hinweisboxen: dunkle Flaeche + heller Text (nie hell-auf-hell) ------- */
html.rag-dark [data-testid="stAlert"], html.rag-dark [data-testid="stNotification"]{
    background-color:#0f2440 !important; border:1px solid #1e3a5f !important;}
html.rag-dark [data-testid="stAlert"] *, html.rag-dark [data-testid="stNotification"] *{color:#e7edf5 !important;}

/* --- Eingabefelder -------------------------------------------------------- */
html.rag-dark input, html.rag-dark textarea, html.rag-dark .stTextInput input,
html.rag-dark .stNumberInput input, html.rag-dark .stTextArea textarea,
html.rag-dark [data-baseweb="input"], html.rag-dark [data-baseweb="base-input"],
html.rag-dark [data-baseweb="textarea"]{
    background-color:#0f2440 !important; color:#e7edf5 !important;
    border-color:#1e3a5f !important;}
html.rag-dark [data-baseweb="select"] > div{background-color:#0f2440 !important;
    color:#e7edf5 !important; border-color:#1e3a5f !important;}
html.rag-dark [data-baseweb="popover"], html.rag-dark [data-baseweb="menu"], html.rag-dark [role="listbox"]{
    background-color:#0f2440 !important;}
html.rag-dark [data-baseweb="menu"] *, html.rag-dark [role="option"]{color:#e7edf5 !important;}
html.rag-dark [data-baseweb="tag"]{background-color:#1e3a5f !important; color:#e7edf5 !important;}
/* Seit einem Streamlit-Versionssprung bauen Selectbox/Multiselect/Zahlenfeld
   NICHT mehr auf BaseWeb auf, sondern auf react-aria-components (Attribut
   "data-rac", Klassen wie "react-aria-ComboBox") - die obigen [data-baseweb=…]
   Regeln laufen fuer diese Widgets seitdem ins Leere und liessen sie im Dark
   Mode als helle Box stehen. ":has()" grenzt gezielt auf Combobox-Wrapper ein
   (nicht auf andere role="group"-Widgets wie Radio-/Checkbox-Gruppen).
   Gemessen: TESTID-Namen (z. B. "stNumberInputContainer") sind stabil,
   die "st-emotion-cache-…"-Klassen daneben sind es NICHT (Build-Hashes). */
html.rag-dark [role="group"][data-rac]:has(input[role="combobox"]){
    background-color:#0f2440 !important; color:#e7edf5 !important;
    border-color:#1e3a5f !important;}
html.rag-dark [data-testid="stNumberInputContainer"],
html.rag-dark [data-testid="stTextInputRootElement"],
html.rag-dark [data-testid="stTextAreaRootElement"]{
    background-color:#0f2440 !important; border-color:#1e3a5f !important;}
html.rag-dark [data-testid="stNumberInputStepDown"], html.rag-dark [data-testid="stNumberInputStepUp"],
html.rag-dark [data-testid="stElementToolbarButtonContainer"]{
    background-color:#132b4d !important; color:#e7edf5 !important;}
html.rag-dark [data-testid*="Tooltip"], html.rag-dark [data-testid*="stHelp"]{
    background-color:#0f2440 !important; color:#e7edf5 !important;}

/* --- Code (inline + Bloecke) --------------------------------------------- */
html.rag-dark code, html.rag-dark kbd{background-color:#0f2440 !important; color:#f0a8a8 !important;}
html.rag-dark pre, html.rag-dark [data-testid="stCode"], html.rag-dark .stCodeBlock, html.rag-dark pre code{
    background-color:#0f2440 !important; color:#e7edf5 !important;}

/* --- Tabellen (Markdown / st.table) -------------------------------------- */
html.rag-dark table, html.rag-dark th, html.rag-dark td{color:#e7edf5 !important; border-color:#1e3a5f !important;}
html.rag-dark thead th, html.rag-dark table th{background-color:#0f2440 !important;}
html.rag-dark tbody tr:nth-child(even){background-color:#0d2038 !important;}

/* --- Expander ------------------------------------------------------------ */
html.rag-dark [data-testid="stExpander"]{border-color:#1e3a5f !important;}
html.rag-dark [data-testid="stExpander"] details, html.rag-dark [data-testid="stExpander"] summary{
    background-color:#0a1930 !important; color:#e7edf5 !important;}

/* --- Buttons ------------------------------------------------------------- */
html.rag-dark .stButton > button, html.rag-dark .stDownloadButton > button,
html.rag-dark .stFormSubmitButton > button, html.rag-dark button[kind="secondary"]{
    background-color:#132b4d !important; color:#e7edf5 !important;
    border:1px solid #1e3a5f !important;}
html.rag-dark button[kind="primary"], html.rag-dark button[kind="primaryFormSubmit"],
html.rag-dark [data-testid="stBaseButton-primary"], html.rag-dark [data-testid="stBaseButton-primaryFormSubmit"]{
    /* Gleiches Korallrot wie im Hell-Modus (Streamlits Standard-primaryColor
       #FF4B4B, hier ungesetzt gelassen) - vorher stand hier ein unabhaengiges
       Blau-Violett (#4A45C4), das nichts mit der sonstigen Korall-/Rosa-
       Markenfarbe der App zu tun hatte und im Dark Mode wie ein Fremdkoerper
       wirkte. */
    background-color:#FF4B4B !important; color:#ffffff !important;
    border-color:#FF4B4B !important;}

/* --- Dokumenten-/Quellen-Viewer (eigene HTML-Bausteine) ------------------ */
html.rag-dark .source-card{background:linear-gradient(135deg,#0f2440 0%,#0a1930 100%) !important;
    border-color:#1e3a5f !important;}
html.rag-dark .source-title{color:#7fb8f0 !important;}
html.rag-dark .source-meta{color:#93a8c4 !important;}
html.rag-dark .small{color:#93a8c4 !important;}
html.rag-dark .badge-answer{background:#0f3d2a !important; color:#4ade80 !important;}
html.rag-dark .badge-fallback{background:#3a2a12 !important; color:#fbbf24 !important;}

/* --- Karteikarte (Dark) - gleicher Kopfstreifen-Look, marineblaue Flaeche - */
html.rag-dark .karte{
    background:linear-gradient(160deg,#132b4d 0%,#0d2038 100%) !important;
    border-color:#1e3a5f !important; color:#dbe6f5 !important;
    box-shadow:0 18px 34px -12px rgba(0,0,0,.45), 0 2px 8px rgba(0,0,0,.3) !important;
}
html.rag-dark .karte-frage{color:#eaf1fb !important;}
</style>
"""


def apply_theme() -> None:
    """Injiziert das zentrale Light-/Dark-Stylesheet.

    Idempotent: mehrfaches Aufrufen erzeugt dasselbe Ergebnis (identisches CSS,
    keine kumulativen Effekte). Muss auf jeder Seite EINMAL direkt nach
    ``require_pin()`` aufgerufen werden – Streamlit baut den Elementbaum bei jedem
    Rerun neu auf, deshalb wird das Stylesheet bewusst bei jedem Lauf emittiert.
    Den tatsaechlichen Hell/Dunkel-Umschalter (Klasse ``rag-dark`` auf ``<html>``)
    setzt ``ragapp.ui._style.apply_page_style()`` - diese Funktion liefert nur die
    Farbregeln, die darauf reagieren.
    """
    st.markdown(_THEME_CSS, unsafe_allow_html=True)
