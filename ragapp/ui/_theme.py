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
/* --- Karteikarte (Lernen): Basis = hell; Dark-Fall unten -------------------- */
.karte {border:1px solid #e2e8f4; border-radius:16px; padding:26px 30px;
    background:linear-gradient(135deg,#f8fafc 0%,#eef2fb 100%); font-size:1.15rem;
    line-height:1.55; min-height:120px;}
.karte-frage {font-weight:650; color:#1f3a63;}

/* --- Flaeche / Grundgeruest ---------------------------------------------- */
html.rag-dark .stApp, html.rag-dark [data-testid="stAppViewContainer"],
html.rag-dark [data-testid="stHeader"]{background-color:#0e1117 !important;}
html.rag-dark [data-testid="stSidebar"]{background-color:#111722 !important;}

/* --- Standard-Fliesstext hell (Ueberschriften/Absaetze/Metriken/Labels) --- */
html.rag-dark .stApp, html.rag-dark [data-testid="stAppViewContainer"],
html.rag-dark [data-testid="stMarkdownContainer"], html.rag-dark [data-testid="stMarkdownContainer"] p,
html.rag-dark [data-testid="stMarkdownContainer"] li, html.rag-dark [data-testid="stMarkdownContainer"] strong,
html.rag-dark h1, html.rag-dark h2, html.rag-dark h3, html.rag-dark h4, html.rag-dark h5, html.rag-dark h6,
html.rag-dark [data-testid="stMetricValue"], html.rag-dark [data-testid="stMetricLabel"],
html.rag-dark [data-testid="stMetricDelta"], html.rag-dark [data-testid="stWidgetLabel"],
html.rag-dark [data-testid="stWidgetLabel"] *{color:#e6edf3 !important;}
html.rag-dark [data-testid="stCaptionContainer"], html.rag-dark [data-testid="stCaptionContainer"] *{
    color:#9aa7b8 !important;}
html.rag-dark a, html.rag-dark [data-testid="stMarkdownContainer"] a{color:#8ab4f8 !important;}

/* --- Hinweisboxen: dunkle Flaeche + heller Text (nie hell-auf-hell) ------- */
html.rag-dark [data-testid="stAlert"], html.rag-dark [data-testid="stNotification"]{
    background-color:#161b22 !important; border:1px solid #30363d !important;}
html.rag-dark [data-testid="stAlert"] *, html.rag-dark [data-testid="stNotification"] *{color:#e6edf3 !important;}

/* --- Eingabefelder -------------------------------------------------------- */
html.rag-dark input, html.rag-dark textarea, html.rag-dark .stTextInput input,
html.rag-dark .stNumberInput input, html.rag-dark .stTextArea textarea,
html.rag-dark [data-baseweb="input"], html.rag-dark [data-baseweb="base-input"],
html.rag-dark [data-baseweb="textarea"]{
    background-color:#161b22 !important; color:#e6edf3 !important;
    border-color:#30363d !important;}
html.rag-dark [data-baseweb="select"] > div{background-color:#161b22 !important;
    color:#e6edf3 !important; border-color:#30363d !important;}
html.rag-dark [data-baseweb="popover"], html.rag-dark [data-baseweb="menu"], html.rag-dark [role="listbox"]{
    background-color:#161b22 !important;}
html.rag-dark [data-baseweb="menu"] *, html.rag-dark [role="option"]{color:#e6edf3 !important;}
html.rag-dark [data-baseweb="tag"]{background-color:#30363d !important; color:#e6edf3 !important;}

/* --- Code (inline + Bloecke) --------------------------------------------- */
html.rag-dark code, html.rag-dark kbd{background-color:#161b22 !important; color:#f0a8a8 !important;}
html.rag-dark pre, html.rag-dark [data-testid="stCode"], html.rag-dark .stCodeBlock, html.rag-dark pre code{
    background-color:#161b22 !important; color:#e6edf3 !important;}

/* --- Tabellen (Markdown / st.table) -------------------------------------- */
html.rag-dark table, html.rag-dark th, html.rag-dark td{color:#e6edf3 !important; border-color:#30363d !important;}
html.rag-dark thead th, html.rag-dark table th{background-color:#161b22 !important;}
html.rag-dark tbody tr:nth-child(even){background-color:#12171f !important;}

/* --- Expander ------------------------------------------------------------ */
html.rag-dark [data-testid="stExpander"]{border-color:#30363d !important;}
html.rag-dark [data-testid="stExpander"] details, html.rag-dark [data-testid="stExpander"] summary{
    background-color:#0e1117 !important; color:#e6edf3 !important;}

/* --- Buttons ------------------------------------------------------------- */
html.rag-dark .stButton > button, html.rag-dark .stDownloadButton > button,
html.rag-dark .stFormSubmitButton > button, html.rag-dark button[kind="secondary"]{
    background-color:#21262d !important; color:#e6edf3 !important;
    border:1px solid #30363d !important;}
html.rag-dark button[kind="primary"], html.rag-dark button[kind="primaryFormSubmit"]{
    background-color:#4A45C4 !important; color:#ffffff !important;
    border-color:#4A45C4 !important;}

/* --- Dokumenten-/Quellen-Viewer (eigene HTML-Bausteine) ------------------ */
html.rag-dark .source-card{background:linear-gradient(135deg,#161b22 0%,#0f172a 100%) !important;
    border-color:#30363d !important;}
html.rag-dark .source-title{color:#8ab4f8 !important;}
html.rag-dark .source-meta{color:#9aa7b8 !important;}
html.rag-dark .small{color:#9aa7b8 !important;}
html.rag-dark .badge-answer{background:#0f3d2a !important; color:#4ade80 !important;}
html.rag-dark .badge-fallback{background:#3a2a12 !important; color:#fbbf24 !important;}

/* --- Karteikarte (Dark) -------------------------------------------------- */
html.rag-dark .karte{background:linear-gradient(135deg,#1e293b 0%,#0f172a 100%) !important;
    border-color:#334155 !important; color:#e2e8f0 !important;}
html.rag-dark .karte-frage{color:#cbd5e1 !important;}
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
