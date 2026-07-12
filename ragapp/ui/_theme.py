"""
RAG-Lernsystem: zentrales UI-Theme (Light + Dark)
=================================================
Ein einziger Helfer ``apply_theme()``, den JEDE Seite direkt nach ``require_pin()``
aufruft. Er injiziert einmal ein Stylesheet, das ueber ``@media (prefers-color-
scheme)`` sowohl den hellen als auch den dunklen Modus sauber bedient.

Hintergrund: Bisher hatte nur die Lernen-Seite eine Dark-Mode-Sonderloesung. Auf
allen anderen Seiten blieben eigens injizierte HTML-Bausteine (Quellen-/Dokumenten-
Viewer, Karteikarten, Badges) hell eingefaerbt – im Dark-Mode also dunkler Text auf
dunklem Grund und damit unlesbar. Dieser Helfer zentralisiert die Kontrast-/
Farbfixes fuer Viewer, Tabellen, Code und Eingabefelder an EINER Stelle.

Die Streamlit-Basis ist auf ``light`` gestellt (``.streamlit/config.toml``); der
Dark-Block folgt daher der Betriebssystem-/Browser-Einstellung und faerbt Flaeche
UND Inhalte konsistent dunkel, ohne den hellen Modus anzutasten.
"""
from __future__ import annotations

import streamlit as st

# --------------------------------------------------------------------------- #
# Das komplette Stylesheet. Der Light-Fall braucht (dank Streamlit-Basis „light")
# nur die Basis-Definition der Karteikarte; der Dark-Fall haengt komplett in
# @media (prefers-color-scheme: dark) und ueberschreibt gezielt alle Stellen, die
# sonst hell hart verdrahtet sind. `!important`, weil dieses Stylesheet VOR den
# seiteneigenen (hellen) <style>-Bloecken injiziert wird.
# --------------------------------------------------------------------------- #
_THEME_CSS = """
<style>
/* --- Karteikarte (Lernen): Basis = hell; Dark-Fall unten -------------------- */
.karte {border:1px solid #e2e8f4; border-radius:16px; padding:26px 30px;
    background:linear-gradient(135deg,#f8fafc 0%,#eef2fb 100%); font-size:1.15rem;
    line-height:1.55; min-height:120px;}
.karte-frage {font-weight:650; color:#1f3a63;}

@media (prefers-color-scheme: dark){
  /* --- Flaeche / Grundgeruest ---------------------------------------------- */
  .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"]{
      background-color:#0e1117 !important;}
  [data-testid="stSidebar"]{background-color:#111722 !important;}

  /* --- Standard-Fliesstext hell (Ueberschriften/Absaetze/Metriken/Labels) --- */
  .stApp, [data-testid="stAppViewContainer"],
  [data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] p,
  [data-testid="stMarkdownContainer"] li, [data-testid="stMarkdownContainer"] strong,
  h1, h2, h3, h4, h5, h6,
  [data-testid="stMetricValue"], [data-testid="stMetricLabel"],
  [data-testid="stMetricDelta"], [data-testid="stWidgetLabel"],
  [data-testid="stWidgetLabel"] *{color:#e6edf3 !important;}
  [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] *{
      color:#9aa7b8 !important;}
  a, [data-testid="stMarkdownContainer"] a{color:#8ab4f8 !important;}

  /* --- Hinweisboxen: dunkle Flaeche + heller Text (nie hell-auf-hell) ------- */
  [data-testid="stAlert"], [data-testid="stNotification"]{
      background-color:#161b22 !important; border:1px solid #30363d !important;}
  [data-testid="stAlert"] *, [data-testid="stNotification"] *{color:#e6edf3 !important;}

  /* --- Eingabefelder -------------------------------------------------------- */
  input, textarea, .stTextInput input, .stNumberInput input, .stTextArea textarea,
  [data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"]{
      background-color:#161b22 !important; color:#e6edf3 !important;
      border-color:#30363d !important;}
  [data-baseweb="select"] > div{background-color:#161b22 !important;
      color:#e6edf3 !important; border-color:#30363d !important;}
  [data-baseweb="popover"], [data-baseweb="menu"], [role="listbox"]{
      background-color:#161b22 !important;}
  [data-baseweb="menu"] *, [role="option"]{color:#e6edf3 !important;}
  [data-baseweb="tag"]{background-color:#30363d !important; color:#e6edf3 !important;}

  /* --- Code (inline + Bloecke) --------------------------------------------- */
  code, kbd{background-color:#161b22 !important; color:#f0a8a8 !important;}
  pre, [data-testid="stCode"], .stCodeBlock, pre code{
      background-color:#161b22 !important; color:#e6edf3 !important;}

  /* --- Tabellen (Markdown / st.table) -------------------------------------- */
  table, th, td{color:#e6edf3 !important; border-color:#30363d !important;}
  thead th, table th{background-color:#161b22 !important;}
  tbody tr:nth-child(even){background-color:#12171f !important;}

  /* --- Expander ------------------------------------------------------------ */
  [data-testid="stExpander"]{border-color:#30363d !important;}
  [data-testid="stExpander"] details, [data-testid="stExpander"] summary{
      background-color:#0e1117 !important; color:#e6edf3 !important;}

  /* --- Buttons ------------------------------------------------------------- */
  .stButton > button, .stDownloadButton > button, .stFormSubmitButton > button,
  button[kind="secondary"]{background-color:#21262d !important; color:#e6edf3 !important;
      border:1px solid #30363d !important;}
  button[kind="primary"], button[kind="primaryFormSubmit"]{
      background-color:#4A45C4 !important; color:#ffffff !important;
      border-color:#4A45C4 !important;}

  /* --- Dokumenten-/Quellen-Viewer (eigene HTML-Bausteine) ------------------ */
  .source-card{background:linear-gradient(135deg,#161b22 0%,#0f172a 100%) !important;
      border-color:#30363d !important;}
  .source-title{color:#8ab4f8 !important;}
  .source-meta{color:#9aa7b8 !important;}
  .small{color:#9aa7b8 !important;}
  .badge-answer{background:#0f3d2a !important; color:#4ade80 !important;}
  .badge-fallback{background:#3a2a12 !important; color:#fbbf24 !important;}

  /* --- Karteikarte (Dark) -------------------------------------------------- */
  .karte{background:linear-gradient(135deg,#1e293b 0%,#0f172a 100%) !important;
      border-color:#334155 !important; color:#e2e8f0 !important;}
  .karte-frage{color:#cbd5e1 !important;}
}
</style>
"""


def apply_theme() -> None:
    """Injiziert das zentrale Light-/Dark-Stylesheet.

    Idempotent: mehrfaches Aufrufen erzeugt dasselbe Ergebnis (identisches CSS,
    keine kumulativen Effekte). Muss auf jeder Seite EINMAL direkt nach
    ``require_pin()`` aufgerufen werden – Streamlit baut den Elementbaum bei jedem
    Rerun neu auf, deshalb wird das Stylesheet bewusst bei jedem Lauf emittiert.
    """
    st.markdown(_THEME_CSS, unsafe_allow_html=True)
