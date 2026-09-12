"""
RAG-Lernsystem: Seite „Einstellungen (Tuning)" (Streamlit)
===========================================================
Zentrale Stellschrauben des Systems bequem tunen und persistent in
``data/config.json`` speichern. Nach dem Ändern in der Evaluation messen, ob
sich die Trefferquote verbessert hat.
"""
from __future__ import annotations

import os
import sys
import pathlib

# Projektwurzel auffindbar machen (damit 'ragapp' importierbar ist)
_p = pathlib.Path(__file__).resolve()
for _anc in _p.parents:
    if (_anc / "ragapp").is_dir():
        sys.path.insert(0, str(_anc))
        break

import streamlit as st

from ragapp.ui._loading import page_boot, skeleton

page_boot("⚙️ Einstellungen (Tuning)", page_title="Einstellungen (Tuning)",
          icon="⚙️", layout="wide", accent="einstellungen")

from ragapp.ui._style import card

# --------------------------------------------------------------------------- #
# Styling ("schick"), identisch zur Startseite
# --------------------------------------------------------------------------- #
st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1100px;}
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
.small {color:#7a8aa0; font-size:0.8rem;}
h1 {font-weight: 750; letter-spacing:-0.5px;}
/* Beschriftungen der Tuning-Felder auf einheitliche Mindesthöhe (Platz für bis zu
   2 Zeilen). So beginnen die Eingabefelder einer Zeile ALLE gleich hoch, auch wenn
   manche Beschriftung ein- und manche zweizeilig ist -> ruhiges, symmetrisches Bild. */
div[data-testid="stNumberInput"] [data-testid="stWidgetLabel"],
div[data-testid="stTextInput"] [data-testid="stWidgetLabel"],
div[data-testid="stSlider"] [data-testid="stWidgetLabel"] {
    min-height: 3rem;
    align-items: flex-start;
}
</style>
""", unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
# Schwere Importe unter Ladehinweis (der Seitentitel ist bereits gerendert ->
# kein weißer Bildschirm beim Seitenwechsel). Die Importe binden trotz des
# with-Blocks modulweit, alle späteren Verwendungen funktionieren unverändert.
# --------------------------------------------------------------------------- #
with skeleton("Einstellungen wird geladen ..."):
    from ragapp.config import (
        settings, RUNTIME_CONFIG_FILE, Settings, UI_RESTART_FILE, UI_MODE_FILE,
    )
    from ragapp import manifest, netinfo
    from ragapp.llm import list_installed_models
    from ragapp.hardware import (
        detect_hardware,
        format_hardware,
        recommend_models,
        benchmark_model,
        pull_model_stream,
        is_model_installed,
        llm_size_gb,
        all_llm_tags,
        probe_model,
        EMBED_MODELS,
        RERANKER_MODELS,
    )

# --------------------------------------------------------------------------- #
# Sidebar (Kurzstatistik, wie auf der Startseite)
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown("### 🎓 Lern-Assistent")
    st.caption(f"Modell: `{settings.LLM_MODEL}` · Embedding: `{settings.EMBED_MODEL}`")
    _stats = manifest.stats()
    c1, c2 = st.columns(2)
    c1.metric("Dokumente", _stats["documents"])
    c2.metric("Chunks", _stats["chunks"])
    c1.metric("Fragen", _stats["questions"])
    c2.metric("Fächer", _stats["subjects"])

# --------------------------------------------------------------------------- #
# Kopf
# --------------------------------------------------------------------------- #
st.markdown(
    "<span class='small'>Stelle die wichtigsten Parameter ein und speichere sie "
    "dauerhaft. <b>Nach dem Ändern in der Evaluation messen</b>, ob sich die "
    "Trefferquote verbessert hat.</span>",
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# Sprungmarken: die Seite ist lang (17 Abschnitte) - Streamlit vergibt an jede
# st.subheader()-Überschrift automatisch eine Anker-ID aus dem sichtbaren Text
# (z. B. "Erkannte Hardware" -> "erkannte-hardware"), diese Chips verlinken
# nur direkt dorthin, ohne die Abschnitte selbst anzufassen.
# --------------------------------------------------------------------------- #
with st.expander("📑 Inhalt (Sprungmarken)"):
    st.markdown(
        """
<style>
.settings-toc {display:flex; flex-wrap:wrap; gap:6px;}
.settings-toc a {
  font-size:.82rem; padding:4px 10px; border-radius:999px;
  background:var(--rag-soft, #f3f0fa); border:1px solid rgba(0,0,0,.08);
  text-decoration:none; color:inherit; white-space:nowrap;
}
.settings-toc a:hover {filter:brightness(0.95);}
html.rag-dark .settings-toc a {background:#132b4d !important; border-color:#1e3a5f !important;}
</style>
<div class="settings-toc">
<a href="#erkannte-hardware">🖥️ Hardware</a>
<a href="#empfohlene-modelle-fuer-deinen-pc">⭐ Empfohlene Modelle</a>
<a href="#antwort-modell-waehlen-and-herunterladen">💬 Antwort-Modell</a>
<a href="#autoren-modell-fuer-die-stapel-erzeugung">✍️ Autoren-Modell</a>
<a href="#handschrift-scan-modell-ocr">📝 OCR</a>
<a href="#such-embedding-modell">🔎 Embedding</a>
<a href="#suche-retrieval">🔎 Suche</a>
<a href="#textabschnitte-chunking">✂️ Chunking</a>
<a href="#antwort-and-schutz-vor-erfindungen">💬 Antwort &amp; Schutz</a>
<a href="#doppelte-aussortieren-deduplizierung">🧹 Dedup</a>
<a href="#modell-ladeverhalten">🔌 Ladeverhalten</a>
<a href="#modelle">🧠 Modelle</a>
<a href="#lernplan">📋 Lernplan</a>
<a href="#audio-overview-sprachsynthese">🎧 Audio-Overview</a>
<a href="#externe-quellen-searxng">🌐 SearXNG</a>
<a href="#evaluation-qualitaetsmessung">📊 Evaluation</a>
<a href="#uni-sparmodus">🎓 Uni-Modus</a>
<a href="#zuruecksetzen">↺ Zurücksetzen</a>
</div>
""",
        unsafe_allow_html=True,
    )

# --------------------------------------------------------------------------- #
# Hardware- & Modell-Auswahl (mit Benchmark)
# --------------------------------------------------------------------------- #
st.header("🖥️ Hardware & Modell-Auswahl")
st.markdown(
    "<span class='small'>So findest du das beste Modell für deinen PC: "
    "<b>Empfehlung ansehen → auswählen → testen</b>. Ist die Antwort zu langsam, "
    "wähle ein kleineres Modell und teste erneut.</span>",
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def _hardware_erkennen() -> dict:
    """Erkennt die Hardware (gecacht, ändert sich zur Laufzeit nicht)."""
    return detect_hardware()


def _fmt_dl_label(text: str, done, tot) -> str:
    """Baut das Fortschritts-Label fuer einen Modell-Download (rein/testbar)."""
    lbl = text or "lädt …"
    if done and tot:
        lbl += f" — {done / 1e9:.1f} / {tot / 1e9:.1f} GB"
    return lbl


def _pull_with_progress(tag: str) -> "tuple[bool, str | None]":
    """Laedt ein Ollama-Modell mit Fortschrittsbalken herunter (``ollama pull``).
    KEIN GPU-/Inferenz-Aufruf – reiner Netzwerk-Download. Gibt (ok, fehler) zurueck.
    Wird von allen Download-Bereichen (Antwort-, Autoren-, OCR-, Such-Modell) genutzt."""
    fehler: "str | None" = None
    with st.status(f"Lade `{tag}` herunter … (Fenster geöffnet lassen)",
                   expanded=True) as status:
        bar = st.progress(0.0)
        try:
            for text, frac, done, tot in pull_model_stream(tag):
                if frac is not None:
                    bar.progress(min(max(frac, 0.0), 1.0))
                status.update(label=_fmt_dl_label(text, done, tot))
            bar.progress(1.0)
            status.update(label=f"✅ `{tag}` heruntergeladen", state="complete")
        except Exception as exc:  # noqa: BLE001
            fehler = str(exc)
            status.update(label="Download fehlgeschlagen", state="error")
    return (fehler is None), fehler


# --- Hardware ermitteln (robust) ------------------------------------------- #
try:
    hw = _hardware_erkennen()
except Exception as exc:  # pragma: no cover - defensiv
    hw = None
    st.warning(f"Hardware-Erkennung fehlgeschlagen: {exc}")

if hw:
    g = hw["gpu"]

    st.subheader("Erkannte Hardware")
    h1, h2, h3, h4 = st.columns(4)
    h1.metric("Betriebssystem", str(hw["os"]))
    h2.metric("RAM", f"{hw.get('ram_gb', '?')} GB")
    vram_txt = f"{g['vram_gb']} GB" if g.get("vram_gb") else "shared/?"
    gpu_label = g["vendor"].upper() if g.get("vendor") != "none" else "keine"
    h3.metric("GPU", gpu_label, help=g.get("name", ""))
    h4.metric("VRAM", vram_txt, help=f"Ollama-Variante: {hw['ollama_variant']}")
    st.caption(f"CPU: {hw['cpu']}")
    with st.expander("Vollständige Hardware-Details anzeigen"):
        st.code(format_hardware(hw), language="text")

    # --- installierte Modelle (fuer Markierung "schon da") ----------------- #
    installiert = list_installed_models()

    # --- Empfehlung -------------------------------------------------------- #
    try:
        rec = recommend_models(hw)
    except Exception as exc:  # pragma: no cover - defensiv
        rec = None
        st.warning(f"Empfehlung konnte nicht erstellt werden: {exc}")

    empf_tags: list[str] = []
    if rec:
        st.subheader("Empfohlene Modelle für deinen PC")
        st.info(f"ℹ️ {rec.get('reason', '')}")
        tabelle = "| | Modell | Familie | Größe | ~GB | gut für … |\n"
        tabelle += "|---|---|---|---|---|---|\n"
        for i, m in enumerate(rec.get("models", [])):
            empf_tags.append(m["tag"])
            mark = "⭐" if i == 0 else ""
            da = " ✅" if is_model_installed(m["tag"], installiert) else ""
            denk = " 🧠" if m.get("denk") else ""
            tabelle += (
                f"| {mark} | `{m['tag']}`{da} | {m.get('fam','')}{denk} | "
                f"{m.get('params','')} | {m.get('gb','')} | {m.get('why','')} |\n"
            )
        st.markdown(tabelle)
        st.caption("⭐ beste Empfehlung · ✅ schon installiert · 🧠 Denk-Modell (sehr gut "
                   "für Logik, aber langsamer) · Embedding-Modell für die Suche: "
                   f"`{rec.get('embed_model','bge-m3')}`")

    # --- Modell-Picker + Download ----------------------------------------- #
    st.subheader("Antwort-Modell wählen & herunterladen")
    _dl_msg = st.session_state.pop("_dl_msg", None)
    if _dl_msg:
        st.success("✅ " + _dl_msg)

    if installiert is None:
        st.warning(
            "⚠️ Konnte die installierten Ollama-Modelle nicht abrufen. Läuft der "
            f"Ollama-Server unter `{settings.OLLAMA_BASE_URL}`? Angeboten werden "
            "stattdessen die Empfehlungen."
        )
        optionen = list(empf_tags) + [t for t in all_llm_tags() if t not in empf_tags]
    else:
        if not installiert:
            st.info("Noch **kein** Modell installiert – wähle unten eins aus und klicke "
                    "**Herunterladen**.")
        # Empfehlungen zuerst, dann der restliche Katalog (alles herunterladbar),
        # dann noch nicht katalogisierte, aber installierte Modelle.
        _kat = all_llm_tags()
        optionen = (list(empf_tags)
                    + [t for t in _kat if t not in empf_tags]
                    + [t for t in installiert if t not in empf_tags and t not in _kat])

    optionen = [o for o in dict.fromkeys(optionen) if o]
    if settings.LLM_MODEL and settings.LLM_MODEL not in optionen:
        optionen = [settings.LLM_MODEL] + optionen
    if not optionen:
        optionen = [settings.LLM_MODEL or "gemma3:4b"]
    default_idx = (optionen.index(settings.LLM_MODEL)
                   if settings.LLM_MODEL in optionen else 0)

    def _opt_label(tag: str) -> str:
        stat = "✅ installiert" if is_model_installed(tag, installiert) else "⬇️ noch laden"
        gb = llm_size_gb(tag)
        return f"{tag}   ({stat}{f' · ~{gb:.0f} GB' if gb else ''})"

    gewaehlt = st.selectbox(
        "Modell für die Antwortgenerierung", options=optionen, index=default_idx,
        format_func=_opt_label,
        help="Empfehlungen + bereits installierte Modelle. Noch nicht installierte "
             "kannst du direkt hier herunterladen.")
    st.caption(f"Aktuell aktives Antwort-Modell: `{settings.LLM_MODEL}`")

    _da = is_model_installed(gewaehlt, installiert)
    b1, b2, b3 = st.columns(3)
    setzen = b1.button("✅ Als Antwort-Modell setzen", use_container_width=True)
    if _da:
        b2.button("⬇️ Schon installiert", disabled=True, use_container_width=True)
        starte_dl = False
    else:
        _gb = llm_size_gb(gewaehlt)
        starte_dl = b2.button(f"⬇️ Herunterladen{f' (~{_gb:.0f} GB)' if _gb else ''}",
                              type="primary", use_container_width=True)
    starte_bench = b3.button("⏱️ Testen (tok/s)", use_container_width=True)

    if setzen and gewaehlt:
        _blocked = False
        if _da:
            # Installiert heisst nicht ladbar (z. B. Gemma 4 auf altem Intel-IPEX) ->
            # vorher testen, damit nicht ein nicht-ladbares Modell aktiv gesetzt wird.
            with st.spinner(f"Prüfe, ob `{gewaehlt}` lädt …"):
                _pok, _pmsg = probe_model(gewaehlt)
            if not _pok:
                st.error(f"❌ `{gewaehlt}` lädt auf diesem Rechner nicht: {_pmsg}  Nicht "
                         "gesetzt – wähle ein laufendes Modell (z. B. `gemma3:4b`).")
                _blocked = True
        else:
            st.warning(f"ℹ️ `{gewaehlt}` ist noch nicht installiert – lade es zuerst über "
                       "**Herunterladen**, sonst schlägt die Antwort fehl.")
        if not _blocked:
            try:
                settings.update(LLM_MODEL=gewaehlt, LLM_MODEL_FAST=gewaehlt)
                settings.save()
                st.success(f"Antwort-Modell auf `{gewaehlt}` gesetzt. Neue Fragen nutzen es sofort.")
            except Exception as exc:  # pragma: no cover - defensiv
                st.error(f"Konnte das Modell nicht setzen: {exc}")

    # --- Download (Ollama pull mit Fortschritt) --------------------------- #
    if starte_dl and gewaehlt:
        _ok, _fehler = _pull_with_progress(gewaehlt)
        if not _ok:
            st.error(f"❌ Download fehlgeschlagen: {_fehler}\n\nPrüfe die Internet-"
                     "verbindung und ob der Ollama-Server läuft.")
        else:
            st.session_state["_dl_msg"] = (f"`{gewaehlt}` wurde installiert. Klicke jetzt "
                                           "**Als Antwort-Modell setzen**.")
            st.rerun()

    st.caption(
        "⚠️ Der Benchmark lädt das Modell (falls nötig) und generiert zweimal Text "
        "(kalt + warm). Auf CPU/schwacher GPU kann das **einige Minuten** dauern."
    )

    # --- Benchmark ausführen ---------------------------------------------- #
    if starte_bench and gewaehlt:
        with st.status(f"Teste Modell `{gewaehlt}` …", expanded=True) as status:
            def _fortschritt(msg: str) -> None:
                status.update(label=msg)
                st.write(msg)

            try:
                ergebnis = benchmark_model(gewaehlt, progress=_fortschritt)
            except Exception as exc:  # pragma: no cover - defensiv
                ergebnis = {"tag": gewaehlt, "error": f"Unerwarteter Fehler: {exc}"}

            if ergebnis.get("error"):
                status.update(label="Benchmark fehlgeschlagen", state="error")
            else:
                status.update(
                    label=f"Benchmark fertig: {ergebnis.get('tokens_per_s', '?')} tok/s",
                    state="complete",
                )
        st.session_state["_bench_result"] = ergebnis

    # --- Benchmark-Ergebnis anzeigen (überlebt Rerun) --------------------- #
    ergebnis = st.session_state.get("_bench_result")
    if ergebnis:
        tag = ergebnis.get("tag", "?")
        if ergebnis.get("error"):
            st.error(
                f"❌ Benchmark für `{tag}` fehlgeschlagen: {ergebnis['error']}\n\n"
                "Häufigste Ursache: **Modell nicht installiert**, vorher "
                f"`ollama pull {tag}` ausführen. Prüfe außerdem, ob der Ollama-Server "
                f"unter `{settings.OLLAMA_BASE_URL}` läuft."
            )
        else:
            st.success(f"✅ Benchmark für `{tag}` abgeschlossen.")
            m1, m2, m3 = st.columns(3)
            m1.metric("Geschwindigkeit", f"{ergebnis.get('tokens_per_s', '?')} tok/s")
            m2.metric("Warm-Antwort", f"{ergebnis.get('warm_s', '?')} s",
                      help="Antwortzeit bei bereits geladenem Modell.")
            m3.metric("Kalt-Antwort", f"{ergebnis.get('cold_s', '?')} s",
                      help="Erste Antwort inkl. Laden ins GPU-/CPU-RAM.")
            st.info(f"**Einschätzung:** {ergebnis.get('verdict', '')}")

    # --- Autoren-Modell (nur Batch-Content) ------------------------------- #
    st.divider()
    st.subheader("Autoren-Modell für die Stapel-Erzeugung")
    st.caption(
        "Ein grosses, kluges Modell NUR für die Batch-Erzeugung von Lerninhalten "
        "(z. B. den Klausur-Lernkatalog). Der interaktive Chat bleibt auf dem "
        "schnellen Antwort-Modell – dieses Modell wird erst beim Autoren-Lauf geladen. "
        "Leer lassen = dasselbe wie das Antwort-Modell (kein zweites Modell laden)."
    )
    _KEIN_AUTOR = "— gleiches wie Antwort-Modell —"
    _cur_author = settings.LLM_MODEL_AUTHOR or ""
    _autor_opts = [_KEIN_AUTOR] + optionen
    if _cur_author and _cur_author not in _autor_opts:
        _autor_opts = [_KEIN_AUTOR, _cur_author] + optionen
    _a_idx = _autor_opts.index(_cur_author) if _cur_author in _autor_opts else 0
    autor_gewaehlt = st.selectbox(
        "Modell für die Batch-Content-Erzeugung", options=_autor_opts, index=_a_idx,
        format_func=lambda t: t if t == _KEIN_AUTOR else _opt_label(t),
        help="Wird für Autoren-Aufgaben (Lernkatalog o. ä.) genutzt. Technisch: LLM_MODEL_AUTHOR")
    st.caption(
        f"Aktuell aktives Autoren-Modell: `{settings.author_model()}`"
        + ("" if settings.LLM_MODEL_AUTHOR else "  (Fallback auf das Antwort-Modell)"))

    # Eigener Download-Bereich fuer das Autoren-Modell (statt Umweg ueber den
    # Antwort-Modell-Picker). Nur sichtbar, wenn ein konkretes Modell gewaehlt ist.
    _autor_konkret = "" if autor_gewaehlt == _KEIN_AUTOR else autor_gewaehlt
    if _autor_konkret:
        _autor_da = is_model_installed(_autor_konkret, installiert)
        _al, _ar = st.columns([2, 1])
        _al.markdown(("✅ installiert" if _autor_da else "⬇️ noch nicht installiert")
                     + f" · `{_autor_konkret}`")
        if not _autor_da:
            _agb = llm_size_gb(_autor_konkret)
            if _ar.button(f"⬇️ Herunterladen{f' (~{_agb:.0f} GB)' if _agb else ''}",
                          key="dl_author", type="primary", use_container_width=True):
                _ok, _err = _pull_with_progress(_autor_konkret)
                if _ok:
                    st.success(f"`{_autor_konkret}` installiert. Klicke jetzt "
                               "**Als Autoren-Modell setzen**.")
                    st.rerun()
                else:
                    st.error(f"❌ Download fehlgeschlagen: {_err}  Prüfe Internet + "
                             "Ollama-Server.")

    if st.button("✅ Als Autoren-Modell setzen", use_container_width=True):
        _val = "" if autor_gewaehlt == _KEIN_AUTOR else autor_gewaehlt
        _ok = True
        if _val:
            if is_model_installed(_val, installiert):
                with st.spinner(f"Prüfe, ob `{_val}` lädt …"):
                    _pok, _pmsg = probe_model(_val)
                if not _pok:
                    st.error(f"❌ `{_val}` lädt auf diesem Rechner nicht: {_pmsg}  Nicht gesetzt.")
                    _ok = False
            else:
                st.warning(
                    f"ℹ️ `{_val}` ist noch nicht installiert – lade es zuerst oben im "
                    "Antwort-Modell-Picker über **Herunterladen**, sonst schlägt der "
                    "Autoren-Lauf fehl.")
                _ok = False
        if _ok:
            try:
                settings.update(LLM_MODEL_AUTHOR=_val)
                settings.save()
                st.success(
                    (f"Autoren-Modell auf `{_val}` gesetzt." if _val
                     else "Autoren-Modell zurückgesetzt – es wird das Antwort-Modell genutzt.")
                    + " Neue Autoren-Läufe nutzen es sofort.")
            except Exception as exc:  # pragma: no cover - defensiv
                st.error(f"Konnte das Autoren-Modell nicht setzen: {exc}")

    # --- OCR-/Handschrift-Modell (Vision) --------------------------------- #
    st.divider()
    st.subheader("Handschrift-/Scan-Modell (OCR)")
    st.caption(
        "Modell, das text-lose PDF-Seiten (Scans, Handschrift) liest. "
        "**Automatisch** wählt je nach VRAM das beste installierte Vision-Modell "
        "(mehr VRAM → genauer). Technisch: OCR_VISION_MODEL (leer = automatisch).")

    try:
        from ragapp.hardware import recommend_ocr_vision_model, VISION_OCR_MODELS
        _ocr_empf = recommend_ocr_vision_model(hw)
    except Exception:  # pragma: no cover - defensiv
        _ocr_empf, VISION_OCR_MODELS = "gemma3:4b", []

    _kat_vision = [m["tag"] for m in VISION_OCR_MODELS]
    # zusaetzlich installierte, vermutlich vision-faehige Modelle anbieten (Namensheuristik)
    _vision_kw = ("gemma3", "gemma4", "llava", "minicpm-v", "qwen2.5vl",
                  "qwen3.5", "moondream", "vision")
    _inst_vision = [t for t in (installiert or [])
                    if any(k in t.lower() for k in _vision_kw) and t not in _kat_vision]
    _cur_ocr = (settings.OCR_VISION_MODEL or "").strip()
    _ocr_opts = [""] + _kat_vision + _inst_vision + ([_cur_ocr] if _cur_ocr else [])
    _ocr_opts = [o for o in dict.fromkeys(_ocr_opts)]          # dedup, "" bleibt vorne
    _ocr_idx = _ocr_opts.index(_cur_ocr) if _cur_ocr in _ocr_opts else 0

    def _ocr_label(tag: str) -> str:
        if tag == "":
            return f"Automatisch – empfohlen: {_ocr_empf}"
        stat = "✅ installiert" if is_model_installed(tag, installiert) else "⬇️ noch laden"
        gb = llm_size_gb(tag)
        return f"{tag}   ({stat}{f' · ~{gb:.0f} GB' if gb else ''})"

    _ocr_gewaehlt = st.selectbox(
        "Vision-Modell für die OCR", options=_ocr_opts, index=_ocr_idx,
        format_func=_ocr_label,
        help="Leer = automatisch (bestes installiertes Vision-Modell, das in den "
             "VRAM passt). Nicht installierte Katalog-Modelle lädst du oben im "
             "Antwort-Modell-Picker herunter (gleicher Ollama-Katalog).")
    st.caption("Aktuell aktiv: "
               + (f"automatisch → `{_ocr_empf}`" if not _cur_ocr else f"`{_cur_ocr}`"))

    # Eigener Download-Bereich fuers OCR-Vision-Modell (nur bei konkreter Wahl;
    # "Automatisch" = leer -> nichts zu laden).
    if _ocr_gewaehlt:
        _ocr_da = is_model_installed(_ocr_gewaehlt, installiert)
        _ol, _or = st.columns([2, 1])
        _ol.markdown(("✅ installiert" if _ocr_da else "⬇️ noch nicht installiert")
                     + f" · `{_ocr_gewaehlt}`")
        if not _ocr_da:
            _ogb = llm_size_gb(_ocr_gewaehlt)
            if _or.button(f"⬇️ Herunterladen{f' (~{_ogb:.0f} GB)' if _ogb else ''}",
                          key="dl_ocr", type="primary", use_container_width=True):
                _ok, _err = _pull_with_progress(_ocr_gewaehlt)
                if _ok:
                    st.success(f"`{_ocr_gewaehlt}` installiert. Klicke jetzt "
                               "**OCR-Modell setzen**.")
                    st.rerun()
                else:
                    st.error(f"❌ Download fehlgeschlagen: {_err}  Ohne Vision-Modell "
                             "fällt die OCR auf easyocr zurück.")

    if st.button("✅ OCR-Modell setzen", use_container_width=True):
        try:
            settings.update(OCR_VISION_MODEL=_ocr_gewaehlt)
            settings.save()
            # Auto-Detektions-Cache im Loader invalidieren -> greift sofort
            try:
                import ragapp.ingestion.loaders as _ld
                _ld._VISION_MODEL_RESOLVED = None
            except Exception:  # noqa: BLE001
                pass
            st.success(
                ("OCR-Modell auf **Automatisch** gesetzt." if not _ocr_gewaehlt
                 else f"OCR-Modell auf `{_ocr_gewaehlt}` gesetzt.")
                + " Neue Importe nutzen es sofort.")
        except Exception as exc:  # pragma: no cover - defensiv
            st.error(f"Konnte das OCR-Modell nicht setzen: {exc}")

    # --- Such-/Embedding-Modell (eigener Auswahl-/Download-Bereich) -------- #
    st.divider()
    st.subheader("🔎 Such-/Embedding-Modell")
    st.caption(
        "Das Modell, das Texte für die **Bedeutungssuche** in Vektoren umwandelt "
        "(Ollama). Hier direkt auswählen, herunterladen und aktiv setzen. "
        "⚠️ Ein Wechsel ändert die Vektor-Größe → danach müssen **alle Dokumente neu "
        "importiert** werden. Technisch: EMBED_MODEL.")

    _emb_info = {m["tag"]: m["info"] for m in EMBED_MODELS}
    _emb_kat = [m["tag"] for m in EMBED_MODELS]
    _cur_emb = (settings.EMBED_MODEL or "").strip()
    _emb_opts = _emb_kat + ([_cur_emb] if _cur_emb and _cur_emb not in _emb_kat else [])
    _emb_opts = [o for o in dict.fromkeys(_emb_opts) if o] or [_cur_emb or "bge-m3"]
    _emb_idx = _emb_opts.index(_cur_emb) if _cur_emb in _emb_opts else 0

    def _emb_label(tag: str) -> str:
        stat = "✅ installiert" if is_model_installed(tag, installiert) else "⬇️ noch laden"
        info = _emb_info.get(tag, "")
        return f"{tag}   ({stat})" + (f" — {info}" if info else "")

    _emb_gewaehlt = st.selectbox(
        "Embedding-Modell", options=_emb_opts, index=_emb_idx, format_func=_emb_label,
        key="emb_pick",
        help="Nach dem Herunterladen unten als Such-Modell setzen. Der Wert wird "
             "zusätzlich unten im Formular unter „🧠 Modelle\" geführt.")
    st.caption(f"Aktuell aktives Such-Modell: `{settings.EMBED_MODEL}`")

    _emb_da = is_model_installed(_emb_gewaehlt, installiert)
    _eb1, _eb2 = st.columns(2)
    if _emb_da:
        _eb1.button("⬇️ Schon installiert", disabled=True, use_container_width=True,
                    key="emb_dl_done")
    else:
        if _eb1.button("⬇️ Herunterladen", type="primary", use_container_width=True,
                       key="dl_embed"):
            _ok, _err = _pull_with_progress(_emb_gewaehlt)
            if _ok:
                st.success(f"`{_emb_gewaehlt}` installiert. Klicke jetzt "
                           "**Als Such-Modell setzen**.")
                st.rerun()
            else:
                st.error(f"❌ Download fehlgeschlagen: {_err}  Prüfe Internet + "
                         "Ollama-Server.")
    if _eb2.button("✅ Als Such-Modell setzen", use_container_width=True, key="emb_set"):
        if not is_model_installed(_emb_gewaehlt, installiert):
            st.warning(f"ℹ️ `{_emb_gewaehlt}` ist noch nicht installiert – lade es zuerst "
                       "über **Herunterladen**, sonst schlägt die Suche fehl.")
        else:
            try:
                settings.update(EMBED_MODEL=_emb_gewaehlt)
                settings.save()
                st.success(
                    f"Such-Modell auf `{_emb_gewaehlt}` gesetzt. ⚠️ Bitte jetzt **alle "
                    "Dokumente neu importieren** – der Vektorindex hat sonst die falsche "
                    "Größe.")
            except Exception as exc:  # pragma: no cover - defensiv
                st.error(f"Konnte das Such-Modell nicht setzen: {exc}")

st.divider()

# --------------------------------------------------------------------------- #
# Handy-/Tablet-Zugriff (Netzwerk)
# --------------------------------------------------------------------------- #
@st.fragment(run_every=3)
def _tunnel_wait_box() -> None:
    """Wartet SERVERSEITIG (per st.fragment-Polling, KEIN Browser-Reload), bis die
    Cloudflare-Adresse steht oder ein Fehler gemeldet wird. Das ist unabhaengig von
    localStorage-Token, Vollbild und Seiten-Navigation - dadurch bleibt die Anzeige
    nie mehr auf „wird aufgebaut" haengen. Sobald sich der Zustand aendert, wird die
    ganze Seite neu gerendert (zeigt dann QR-Code bzw. Fehlermeldung)."""
    import os
    # Reiner Lokal-Start (start.sh setzt RAG_LOCAL_ONLY=1): hier gibt es KEINEN Starter,
    # der den Tunnel bauen koennte - sonst haengt die Box ewig auf „wird aufgebaut".
    # Klar auf den sicheren „Unterwegs"-Start hinweisen statt endlos zu pollen.
    if os.environ.get("RAG_LOCAL_ONLY") == "1":
        st.warning("ℹ️ Diese App wurde **rein lokal** gestartet – hier lässt sich der "
                   "Cloudflare-Tunnel nicht aufbauen. Beende die App und starte sie über "
                   "**RAG-Lernsystem – Unterwegs** (bzw. `Start_Unterwegs.sh`). Dort "
                   "erscheinen automatisch die Adresse und der QR-Code, und die "
                   "PIN-Sperre schützt den Zugriff.")
        return
    if netinfo.tunnel_url() is not None or netinfo.tunnel_error():
        st.rerun()   # ganze Seite neu -> QR-Code / Fehlermeldung
    st.info("🌍 Cloudflare-Tunnel wird aufgebaut … (beim ersten Mal inkl. Installation, "
            "1–2 Minuten). Die Seite aktualisiert sich automatisch, sobald die "
            "Adresse bereit ist.")


st.header("📱 Handy-/Tablet-Zugriff")
st.markdown(
    "<span class='small'>Nutze die App vom Handy oder Tablet, solange dieser PC "
    "läuft. Zum Schutz deiner Unterlagen ist ein <b>PIN</b> nötig.</span>",
    unsafe_allow_html=True,
)

_pc1, _pc2 = st.columns([3, 1])
with _pc1:
    _neuer_pin = st.text_input(
        "PIN für den Netzwerk-Zugriff", value=str(settings.UI_ACCESS_PIN or ""),
        type="password",
        help="Diesen PIN gibst du am Handy einmal ein. Leer = kein Zugriff im "
             "Netzwerkmodus.")
with _pc2:
    st.markdown("<div style='height:1.8rem'></div>", unsafe_allow_html=True)
    if st.button("💾 PIN speichern", use_container_width=True):
        settings.update(UI_ACCESS_PIN=_neuer_pin.strip())
        settings.save()
        st.success("PIN gespeichert." if _neuer_pin.strip()
                   else "PIN geleert. Im Netzwerkmodus ist dann kein Zugriff möglich.")

_pin_ok = bool(str(settings.UI_ACCESS_PIN or "").strip())
_cur = netinfo.current_mode()   # "local" / "network" / "tunnel"
_mode_labels = {
    "local": "Aus – nur dieser PC",
    "network": "Im WLAN – Handy im selben Netz (zuhause)",
    "tunnel": "Von überall – über Cloudflare (auch mobil)",
}
_opts = ["local", "network", "tunnel"]
_desired = st.radio(
    "Zugriff", _opts, index=_opts.index(_cur),
    format_func=lambda m: _mode_labels[m],
    help="Alles direkt in der App – keine Extra-Datei nötig. Cloudflare wird beim "
         "ersten Mal automatisch installiert.",
)

# Reiner Lokal-Start (start.sh) kann WLAN/Tunnel nicht bedienen (bindet nur 127.0.0.1
# und fragt keine PIN ab). Klar darauf hinweisen, statt den Nutzer in einen nicht
# funktionierenden Moduswechsel laufen zu lassen.
if os.environ.get("RAG_LOCAL_ONLY") == "1" and _desired != "local":
    st.info("ℹ️ Diese App wurde **rein lokal** gestartet (Icon → `start.sh`) – WLAN- "
            "und Cloudflare-Zugriff funktionieren hier nicht. Für Handy-Zugriff die App "
            "beenden und über **RAG-Lernsystem – Unterwegs** (`Start_Unterwegs.sh`) "
            "starten – dort ist alles inkl. QR-Code und PIN-Schutz aktiv.")

if _desired != _cur:
    if _desired != "local" and not _pin_ok:
        st.warning("⚠️ Setze oben zuerst einen PIN, dann lässt sich der Zugriff einschalten.")
    elif st.button("✅ Übernehmen", type="primary"):
        try:
            UI_MODE_FILE.write_text(_desired, encoding="utf-8")      # Anzeige + Gate sofort
            UI_RESTART_FILE.write_text(_desired, encoding="utf-8")   # Starter: Tunnel an/aus
        except Exception:  # noqa: BLE001
            pass
        st.rerun()   # kein Neustart/Neuladen nötig (Bind ist immer 0.0.0.0)

# ---- Aktueller Zustand + QR-Code ---------------------------------------- #
if _cur == "local":
    st.caption("Der Zugriff ist **aus** – die App ist nur auf diesem PC erreichbar.")
elif _cur == "tunnel" and netinfo.tunnel_url() is None:
    # Cloudflare-Modus, aber die Adresse steht noch nicht -> baut auf ODER fehlgeschlagen.
    # KEINE „Aktiv"-Box und KEIN (falscher WLAN-)QR in diesem Zustand.
    if netinfo.tunnel_error():
        st.error("❌ Der Cloudflare-Tunnel konnte nicht aufgebaut werden – meist fehlt "
                 "Internet, das Netz/die Firewall blockiert, oder die cloudflared-"
                 "Installation ist fehlgeschlagen.")
        st.info("Nimm solange **Im WLAN** (Handy im selben Netz) – oder versuch es erneut.")
        if st.button("🔄 Erneut versuchen", type="primary"):
            netinfo.clear_tunnel_error()
            try:
                UI_RESTART_FILE.write_text("tunnel", encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
            st.rerun()
    else:
        _tunnel_wait_box()
else:
    # network -> WLAN-Ziel; tunnel (bereit) -> Cloudflare-Ziel. Genau EIN passendes Ziel.
    _ziele = netinfo.access_targets()
    if not _ziele:
        st.warning("Noch keine Adresse verfügbar. Ist der PC mit dem Netzwerk verbunden?")
    else:
        _z = _ziele[0]
        st.success("✅ **Aktiv** – dein Handy/Tablet kann zugreifen (PIN nötig).")
        st.markdown(f"**{_z['label']}** — [{_z['url']}]({_z['url']})")
        _png = netinfo.qr_png_bytes(_z["url"])
        if _png:
            st.image(_png, width=240, caption="Mit dem Handy scannen")
        else:
            st.caption("(QR-Code nicht verfügbar, Adresse oben im Handy-Browser eingeben.)")
        _hinweise = {
            "lan": "📶 Funktioniert, wenn das Handy im **selben WLAN** ist.",
            "tunnel": "🌍 Von **überall** erreichbar, **keine App** am Handy nötig.",
        }
        if _hinweise.get(_z["kind"]):
            st.caption(_hinweise[_z["kind"]])
        if _z["kind"] == "lan":
            st.caption(
                "📲 **Dauerhaft aufs Handy**: Adresse öffnen und **installieren** – am "
                "Handy erscheint dazu unten ein Banner (sonst Browser-Menü → *Zum "
                "Startbildschirm hinzufügen*). Die WLAN-Adresse bleibt zuhause "
                "normalerweise gleich; für Garantie im Router eine **feste IP** vergeben.")
        elif _z["kind"] == "tunnel":
            st.caption(
                "ℹ️ Diese Cloudflare-Adresse **ändert sich bei jedem Start** – ideal für "
                "spontanen Zugriff von unterwegs, aber **nicht zum Installieren** "
                "(das Icon würde beim nächsten Mal ins Leere zeigen).")

st.caption(
    "Hinweis: Beim ersten Start im Netzwerkmodus fragt die **Windows-Firewall**, "
    "ob Port 8501 erlaubt sein soll. Dann einmal auf **Zulassen** klicken "
    "(privates Netzwerk).")

st.divider()

# --------------------------------------------------------------------------- #
# Lern-Algorithmus (Spaced Repetition)
# --------------------------------------------------------------------------- #
st.header("🎓 Lern-Algorithmus (Karteikarten)")
st.caption("Legt fest, wie die Wiederholungs-Abstände berechnet werden. FSRS-6 (Free "
           "Spaced Repetition Scheduler, derselbe Algorithmus, auf den Anki inzwischen "
           "standardmäßig umgestiegen ist) lernt aus Millionen echter Wiederholungen ein "
           "Vergessens-Modell statt fixer Formeln – braucht laut Benchmark 20–30 % "
           "weniger Wiederholungen für denselben Lernerfolg als das ältere SM-2.")

_srs_keys = ("FSRS_DESIRED_RETENTION", "FSRS_MAX_INTERVAL_DAYS",
             "SRS_NEW_PER_DAY", "SRS_MAX_PER_SESSION")

with st.form("srs_form"):
    _f1, _f2 = st.columns(2)
    _v_retention = _f1.slider(
        "Ziel-Retention", min_value=0.70, max_value=0.97,
        value=float(settings.FSRS_DESIRED_RETENTION), step=0.01, key="cfg_FSRS_DESIRED_RETENTION",
        help="Wie sicher eine Karte am Fälligkeitstag noch gewusst werden soll. Höher = "
             "häufigere Wiederholungen, aber weniger Vergessen. 90 % ist der verbreitete "
             "Standardwert (auch bei Anki).")
    _v_maxint = _f2.number_input(
        "Max. Abstand (Tage)", min_value=30, max_value=3650,
        value=int(settings.FSRS_MAX_INTERVAL_DAYS), step=30, key="cfg_FSRS_MAX_INTERVAL_DAYS",
        help="Obergrenze für den Abstand zwischen zwei Wiederholungen, auch bei sehr "
             "leichten Karten.")
    _d1, _d2 = st.columns(2)
    _v_npd = _d1.number_input(
        "Neue Karten pro Tag", min_value=0, max_value=500,
        value=int(settings.SRS_NEW_PER_DAY), step=5,
        key="cfg_SRS_NEW_PER_DAY",
        help="Tageskontingent für brandneue Karten (wie bei Anki). Schon gelernte, "
             "fällige Wiederholungen kommen zusätzlich. Eine zweite Lernsitzung am "
             "selben Tag erhöht dieses Kontingent nicht. 0 = unbegrenzt.")
    _v_mps = _d2.number_input(
        "Max. Karten pro Sitzung", min_value=5, max_value=1000,
        value=int(settings.SRS_MAX_PER_SESSION), step=5,
        key="cfg_SRS_MAX_PER_SESSION",
        help="Sicherheitsdeckel, falls sehr viele Karten fällig sind – keine "
             "Rundengröße, die du vor jeder Sitzung einstellen musst.")
    st.caption("**Neue Karten pro Tag** gilt global fürs normale Lernen (Stapel → "
               "Jetzt lernen). Es ist **kein** Quiz von 20 immer gleichen Karten: "
               "fällige Wiederholungen haben Vorrang; neue Karten werden nur "
               "eingeführt, bis das Tageskontingent voll ist.")
    _sc1, _sc2 = st.columns(2)
    _srs_save = _sc1.form_submit_button("💾 Speichern", type="primary")
    _srs_reset = _sc2.form_submit_button("↩︎ Auf Standard zurücksetzen")

if _srs_save:
    settings.update(
        FSRS_DESIRED_RETENTION=float(_v_retention), FSRS_MAX_INTERVAL_DAYS=int(_v_maxint),
        SRS_NEW_PER_DAY=int(_v_npd), SRS_MAX_PER_SESSION=int(_v_mps))
    settings.save()
    st.success("Lern-Einstellungen gespeichert. Gilt ab der nächsten Bewertung.")

if _srs_reset:
    _def = Settings()
    settings.update(**{k: getattr(_def, k) for k in _srs_keys})
    settings.save()
    for _k in _srs_keys:
        st.session_state.pop(f"cfg_{_k}", None)
    st.success("Lern-Algorithmus auf Standard zurückgesetzt.")
    st.rerun()

# Live-Vorschau des resultierenden Zeitplans (frische Karte, immer "Gewusst")
try:
    from ragapp import study as _study_preview
    _card = {"fsrs_state": None, "fsrs_step": None, "stability": None,
            "difficulty": None, "due": 0.0, "last_review": None,
            "reps": 0, "lapses": 0}
    _seq = []
    for _ in range(6):
        _stt = _study_preview.fsrs_next(_study_preview.GEWUSST, _card, now=_card["due"] or 0.0)
        _card = {**_card, **_stt, "last_review": _card["due"] or 0.0}
        _seq.append(_study_preview.humanize_due(_stt["due"], _card["last_review"]).replace("in ", ""))
    st.caption("**Vorschau bei immer Gewusst (frische Karte):** " + " → ".join(_seq))
except Exception:  # noqa: BLE001
    pass

st.divider()

# --------------------------------------------------------------------------- #
# Formular
# --------------------------------------------------------------------------- #
with st.form("einstellungen"):
    neu: dict = {}

    # ------------------------------------------------------------------ #
    st.subheader("🔎 Suche (Retrieval)")
    st.caption("Wie viele Fundstellen gesucht, zusammengeführt und an die KI gegeben werden.")
    r1, r2, r3 = st.columns(3)
    with r1:
        neu["DENSE_TOP_K"] = st.number_input(
            "Fundstellen aus der Bedeutungssuche", min_value=1, max_value=500,
            value=int(settings.DENSE_TOP_K), step=1, key="cfg_DENSE_TOP_K",
            help="Wie viele Treffer die sinngemäße Suche (Vektor/Embedding) liefert. "
                 "Mehr = gründlicher, aber langsamer. Technisch: DENSE_TOP_K")
        neu["FUSION_TOP_K"] = st.number_input(
            "Fundstellen nach dem Zusammenführen", min_value=1, max_value=500,
            value=int(settings.FUSION_TOP_K), step=1, key="cfg_FUSION_TOP_K",
            help="Wie viele der zusammengeführten Treffer feinsortiert werden. "
                 "Technisch: FUSION_TOP_K")
        neu["FINAL_TOP_K"] = st.number_input(
            "Fundstellen an die KI (final)", min_value=1, max_value=100,
            value=int(settings.FINAL_TOP_K), step=1, key="cfg_FINAL_TOP_K",
            help="Wie viele Textstellen am Ende in die Antwort einfließen. Mehr = mehr "
                 "Kontext, aber langsamer/mehr Ablenkung. Technisch: FINAL_TOP_K")
    with r2:
        neu["BM25_TOP_K"] = st.number_input(
            "Fundstellen aus der Stichwortsuche", min_value=1, max_value=500,
            value=int(settings.BM25_TOP_K), step=1, key="cfg_BM25_TOP_K",
            help="Wie viele Treffer die wortgenaue Stichwortsuche liefert. "
                 "Technisch: BM25_TOP_K")
        neu["RRF_K"] = st.number_input(
            "Ausgleich beider Suchen", min_value=1, max_value=1000,
            value=int(settings.RRF_K), step=1, key="cfg_RRF_K",
            help="Steuert, wie stark einzelne Spitzen-Treffer beim Zusammenführen der "
                 "beiden Suchen zählen (höher = ausgeglichener). "
                 "Technisch: RRF_K (Reciprocal Rank Fusion)")
        neu["RELEVANCE_MIN_SCORE"] = st.number_input(
            "Mindest-Relevanz zum freien Antworten",
            value=float(settings.RELEVANCE_MIN_SCORE), step=0.5,
            key="cfg_RELEVANCE_MIN_SCORE",
            help="Ist der beste Treffer schlechter als dieser Wert, antwortet die KI "
                 "NICHT frei, sondern nennt nur die passenden Dokumente (Schutz vor "
                 "Erfindungen). Höher = strenger. Technisch: RELEVANCE_MIN_SCORE")
    with r3:
        neu["DENSE_WEIGHT"] = st.number_input(
            "Gewicht der Bedeutungssuche", min_value=0.0, max_value=10.0,
            value=float(settings.DENSE_WEIGHT), step=0.1, key="cfg_DENSE_WEIGHT",
            help="Wie stark die sinngemäße Suche zählt (nur wenn Feinsortierung aus). "
                 "Technisch: DENSE_WEIGHT")
        neu["BM25_WEIGHT"] = st.number_input(
            "Gewicht der Stichwortsuche", min_value=0.0, max_value=10.0,
            value=float(settings.BM25_WEIGHT), step=0.1, key="cfg_BM25_WEIGHT",
            help="Wie stark die wortgenaue Suche zählt (nur wenn Feinsortierung aus). "
                 "Technisch: BM25_WEIGHT")
        neu["USE_RERANKER"] = st.toggle(
            "Treffer fein nachsortieren", value=bool(settings.USE_RERANKER),
            key="cfg_USE_RERANKER",
            help="Ordnet die Treffer mit einem genaueren Modell noch einmal nach "
                 "Relevanz (bessere Qualität, etwas langsamer). "
                 "Technisch: USE_RERANKER (Reranker)")

    st.divider()

    # ------------------------------------------------------------------ #
    st.subheader("✂️ Textabschnitte (Chunking)")
    st.caption("Wie Dokumente beim Import in durchsuchbare Häppchen zerlegt werden. "
               "Wirkt erst nach einem **Neu-Import**.")
    c1, c2, c3 = st.columns(3)
    with c1:
        neu["CHUNK_SIZE"] = st.number_input(
            "Abschnittsgröße (Zeichen)", min_value=100, max_value=8000,
            value=int(settings.CHUNK_SIZE), step=50, key="cfg_CHUNK_SIZE",
            help="Angepeilte Länge eines Häppchens. Größer = mehr Zusammenhang je "
                 "Treffer, aber weniger gezielt. Technisch: CHUNK_SIZE")
    with c2:
        neu["CHUNK_OVERLAP"] = st.number_input(
            "Überlappung der Abschnitte (Zeichen)", min_value=0, max_value=2000,
            value=int(settings.CHUNK_OVERLAP), step=10, key="cfg_CHUNK_OVERLAP",
            help="Wie stark sich benachbarte Häppchen überschneiden, damit kein "
                 "Zusammenhang verloren geht. Technisch: CHUNK_OVERLAP")
    with c3:
        neu["MIN_CHUNK_CHARS"] = st.number_input(
            "Mindestlänge eines Abschnitts (Zeichen)", min_value=0, max_value=2000,
            value=int(settings.MIN_CHUNK_CHARS), step=10, key="cfg_MIN_CHUNK_CHARS",
            help="Kürzere Schnipsel werden verworfen oder zusammengelegt. "
                 "Technisch: MIN_CHUNK_CHARS")
    neu["RESPECT_MARKDOWN_HEADERS"] = st.toggle(
        "An Überschriften trennen (Markdown)",
        value=bool(settings.RESPECT_MARKDOWN_HEADERS), key="cfg_RESPECT_MARKDOWN_HEADERS",
        help="Schneidet Texte bevorzugt an Überschriften – hält Themen sauber "
             "zusammen. Technisch: RESPECT_MARKDOWN_HEADERS")

    st.divider()

    # ------------------------------------------------------------------ #
    st.subheader("💬 Antwort & Schutz vor Erfindungen")
    st.caption("Wie faktentreu die KI antwortet und wie viel Kontext sie bekommt.")
    a1, a2, a3 = st.columns(3)
    with a1:
        neu["LLM_TEMPERATURE"] = st.slider(
            "Fantasie der KI", min_value=0.0, max_value=1.0,
            value=float(settings.LLM_TEMPERATURE), step=0.05, key="cfg_LLM_TEMPERATURE",
            help="Niedrig = nüchtern & faktentreu (empfohlen), hoch = kreativer, aber "
                 "mehr Erfindungsgefahr. Technisch: LLM_TEMPERATURE")
    with a2:
        neu["LLM_NUM_CTX"] = st.number_input(
            "Gedächtnis der KI (Tokens)", min_value=512, max_value=131072,
            value=int(settings.LLM_NUM_CTX), step=512, key="cfg_LLM_NUM_CTX",
            help="Wie viel Text die KI gleichzeitig verarbeiten kann. Größer = mehr "
                 "Kontext, braucht aber mehr Speicher/Zeit. Technisch: LLM_NUM_CTX")
    with a3:
        neu["MAX_CONTEXT_CHARS"] = st.number_input(
            "Max. Textmenge an die KI (Zeichen)", min_value=500, max_value=100000,
            value=int(settings.MAX_CONTEXT_CHARS), step=500, key="cfg_MAX_CONTEXT_CHARS",
            help="Obergrenze, wie viel aus den Dokumenten mitgegeben wird. "
                 "Technisch: MAX_CONTEXT_CHARS")
    neu["ENABLE_FAITHFULNESS_CHECK"] = st.toggle(
        "Antwort auf Beleg prüfen", value=bool(settings.ENABLE_FAITHFULNESS_CHECK),
        key="cfg_ENABLE_FAITHFULNESS_CHECK",
        help="Die KI prüft am Ende, ob ihre Antwort wirklich durch die Dokumente "
             "gedeckt ist (weniger Erfindungen, etwas langsamer). "
             "Technisch: ENABLE_FAITHFULNESS_CHECK")

    st.divider()

    # ------------------------------------------------------------------ #
    st.subheader("🧹 Doppelte aussortieren (Deduplizierung)")
    st.caption("Filtert doppelte/fast gleiche Inhalte – beim Import und in den Treffern.")
    d1, d2, d3 = st.columns(3)
    with d1:
        neu["DEDUP_NEAR_DUPLICATE_THRESHOLD"] = st.slider(
            "Doppelte beim Import erkennen", min_value=0.0, max_value=1.0,
            value=float(settings.DEDUP_NEAR_DUPLICATE_THRESHOLD), step=0.005,
            key="cfg_DEDUP_NEAR_DUPLICATE_THRESHOLD",
            help="Ab welcher Ähnlichkeit zwei Abschnitte beim Import als Dublette "
                 "gelten (höher = nur sehr Ähnliches wird aussortiert). "
                 "Technisch: DEDUP_NEAR_DUPLICATE_THRESHOLD")
    with d2:
        neu["RETRIEVAL_DEDUP_JACCARD"] = st.slider(
            "Doppelte Treffer erkennen", min_value=0.0, max_value=1.0,
            value=float(settings.RETRIEVAL_DEDUP_JACCARD), step=0.01,
            key="cfg_RETRIEVAL_DEDUP_JACCARD",
            help="Ab welcher Wort-Überschneidung zwei Treffer als doppelt gelten. "
                 "Technisch: RETRIEVAL_DEDUP_JACCARD")
    with d3:
        neu["RETRIEVAL_DEDUP"] = st.toggle(
            "Doppelte Treffer herausfiltern", value=bool(settings.RETRIEVAL_DEDUP),
            key="cfg_RETRIEVAL_DEDUP",
            help="Entfernt fast identische Treffer, damit die Antwort nichts doppelt "
                 "verwendet. Technisch: RETRIEVAL_DEDUP")

    st.divider()

    # ------------------------------------------------------------------ #
    st.subheader("🔌 Modell-Ladeverhalten")
    st.caption("Steuert, WANN Embedding/Antwort-Modell Speicher (RAM/VRAM) belegen – "
               "praktisch, wenn die Sitzung oft nur zum Karteikarten-Lernen offen ist "
               "und dafür gar kein Modell gebraucht wird.")
    m1, m2 = st.columns(2)
    with m1:
        neu["PREWARM_ON_START"] = st.toggle(
            "Beim Öffnen automatisch vorladen", value=bool(settings.PREWARM_ON_START),
            key="cfg_PREWARM_ON_START",
            help="AN: Embedding + Reranker laden schon beim Öffnen der Startseite im "
                 "Hintergrund (erste Frage antwortet dadurch schneller). AUS: Es lädt "
                 "NICHTS automatisch – erst die erste echte Frage/Aktion lädt ein "
                 "Modell. Das Antwort-LLM selbst lädt in beiden Fällen erst bei "
                 "Bedarf. Technisch: PREWARM_ON_START")
    with m2:
        _ka_optionen = {
            "Sofort entladen (0 Min)": 0.0,
            "5 Minuten (Standard)": 5.0,
            "30 Minuten": 30.0,
            "Dauerhaft geladen": -1.0,
        }
        _ka_labels = list(_ka_optionen)
        _ka_aktuell = float(settings.OLLAMA_KEEP_ALIVE_MINUTES)
        _ka_label_default = next(
            (lbl for lbl, v in _ka_optionen.items() if v == _ka_aktuell), _ka_labels[1])
        _ka_sel = st.selectbox(
            "Wie lange bleibt ein geladenes Modell im Speicher?", _ka_labels,
            index=_ka_labels.index(_ka_label_default), key="cfg_OLLAMA_KEEP_ALIVE_MINUTES",
            help="Nach der letzten Nutzung bleibt ein über Ollama geladenes Modell "
                 "(Antwort-LLM, Embedding) so lange im RAM/VRAM, bevor es automatisch "
                 "entladen wird. Kürzer = mehr freier Speicher für andere Programme, "
                 "kostet aber bei der nächsten Nutzung wieder den Kaltstart. "
                 "Technisch: OLLAMA_KEEP_ALIVE_MINUTES")
        neu["OLLAMA_KEEP_ALIVE_MINUTES"] = _ka_optionen[_ka_sel]

    st.divider()

    # ------------------------------------------------------------------ #
    st.subheader("🧠 Modelle")
    st.caption("Das **Antwort-Modell** (KI) wählst und lädst du oben unter "
               "**🖥️ Hardware & Modell-Auswahl**. Hier stellst du das Such- und das "
               "Nachsortier-Modell ein – bequem per Auswahl statt Tippen.")
    _EIGEN = "✏️ eigener Name …"

    def _modell_feld(label, key, current, katalog, hilfe, platzhalter):
        """Auswahl (Katalog + aktuell + eigener Name) + optionales Eigen-Textfeld.
        Gibt den aufgeloesten Modellnamen zurueck (Eigen-Text schlaegt Auswahl)."""
        info = {m["tag"]: m["info"] for m in katalog}
        opts = [m["tag"] for m in katalog]
        if current and current not in opts:
            opts = [current] + opts
        opts = opts + [_EIGEN]
        idx = opts.index(current) if current in opts else 0
        sel = st.selectbox(
            label, opts, index=idx, key=key,
            format_func=lambda t: t if t == _EIGEN else f"{t} — {info.get(t, 'aktuell gesetzt')}",
            help=hilfe)
        eigen = st.text_input("… eigener Name", value="", key=key + "_custom",
                              placeholder=platzhalter, label_visibility="collapsed")
        return eigen.strip() or (current if sel == _EIGEN else sel)

    m1, m2 = st.columns(2)
    with m1:
        neu["EMBED_MODEL"] = _modell_feld(
            "Such-Modell (Embedding)", "cfg_EMBED_MODEL", settings.EMBED_MODEL, EMBED_MODELS,
            "Wandelt Texte in Vektoren für die Bedeutungssuche. ⚠️ Ein Wechsel ändert die "
            "Vektor-Größe → alle Dokumente müssen NEU importiert werden. Technisch: EMBED_MODEL",
            "nur falls oben eigener Name gewählt (Ollama-Tag)")
    with m2:
        neu["RERANKER_MODEL"] = _modell_feld(
            "Nachsortier-Modell (Reranker)", "cfg_RERANKER_MODEL", settings.RERANKER_MODEL,
            RERANKER_MODELS,
            "Sortiert die Treffer nach Relevanz. Lädt beim ersten Benutzen automatisch von "
            "HuggingFace (kein manueller Download nötig). Technisch: RERANKER_MODEL",
            "nur falls oben eigener Name gewählt (HuggingFace-Pfad)")

    st.divider()

    # ------------------------------------------------------------------ #
    st.subheader("📋 Lernplan")
    st.caption("Wie realistisch die KI-Gliederung die Lernzeit schätzt. Sobald genug "
               "echte Pomodoro-Zeiten an erledigten Lernplan-Blöcken vorliegen (Seite "
               "📈 Fortschritt → „Plan vs. Realität“), ersetzt ein selbstlernender "
               "Faktor den Wert unten automatisch – er bleibt aber der Startwert und "
               "das manuelle Sicherheitsnetz.")
    pl1, pl2, pl3 = st.columns(3)
    with pl1:
        neu["PLAN_TIME_FACTOR"] = st.slider(
            "Zeit-Korrekturfaktor", min_value=0.5, max_value=3.0,
            value=float(settings.PLAN_TIME_FACTOR), step=0.1, key="cfg_PLAN_TIME_FACTOR",
            help="Die Formel schätzt Lese- + Übungszeit auf Basis von Vokabel-Lernrate "
                 "(siehe docs/LERNPLAN_FORSCHUNG.md) - für technischen/prozeduralen "
                 "Stoff (Rechnen, Algorithmen, Modelle) meist zu optimistisch. Höher = "
                 "der Plan rechnet mehr Zeit pro Thema ein. 1.0 = reine Formel ohne "
                 "Korrektur. Technisch: PLAN_TIME_FACTOR")
    with pl2:
        neu["PLAN_REVIEW_SEC_PER_CARD"] = st.number_input(
            "Dauer je Karteikarte (Sek.)", min_value=5.0, max_value=120.0,
            value=float(settings.PLAN_REVIEW_SEC_PER_CARD), step=5.0,
            key="cfg_PLAN_REVIEW_SEC_PER_CARD",
            help="Grobe Dauer einer Karteikarten-Wiederholung. Der Lernplan reserviert "
                 "damit täglich Zeit für fällige Wiederholungen, bevor neuer Stoff "
                 "eingeplant wird. Technisch: PLAN_REVIEW_SEC_PER_CARD")
    with pl3:
        neu["PLAN_REVIEW_MAX_SHARE"] = st.slider(
            "Max. Anteil fürs Wiederholen", min_value=0.0, max_value=0.9,
            value=float(settings.PLAN_REVIEW_MAX_SHARE), step=0.05,
            key="cfg_PLAN_REVIEW_MAX_SHARE",
            help="Deckelt, wie viel vom Tagesbudget fällige Wiederholungen höchstens "
                 "belegen dürfen – ein Wiederholungs-Stau soll den Neustoff-Teil des "
                 "Plans nicht komplett verdrängen. Technisch: PLAN_REVIEW_MAX_SHARE")

    st.divider()

    # ------------------------------------------------------------------ #
    st.subheader("🎧 Audio-Overview (Sprachsynthese)")
    st.caption("Pausenlänge und Ausdruck der vorgelesenen Audio-Overviews (Chatterbox "
               "Multilingual). Wirkt erst bei der nächsten Erzeugung/Neuvertonung.")
    a1, a2, a3 = st.columns(3)
    with a1:
        neu["AUDIO_TTS_PAUSE_MS"] = st.slider(
            "Pause zwischen Sätzen (ms)", min_value=50, max_value=600,
            value=int(settings.AUDIO_TTS_PAUSE_MS), step=25, key="cfg_AUDIO_TTS_PAUSE_MS",
            help="Jeder Satz wird einzeln vertont - dazwischen fügen wir diese feste "
                 "Stille selbst ein. Niedriger = zügigeres Vorlesen. "
                 "Technisch: AUDIO_TTS_PAUSE_MS")
    with a2:
        neu["AUDIO_TTS_EXAGGERATION"] = st.slider(
            "Ausdrucksstärke", min_value=0.2, max_value=1.5,
            value=float(settings.AUDIO_TTS_EXAGGERATION), step=0.05,
            key="cfg_AUDIO_TTS_EXAGGERATION",
            help="Wie stark betont/emotional vorgelesen wird. Werte über 1.5 gelten "
                 "als anfälliger für Aussetzer. Technisch: AUDIO_TTS_EXAGGERATION "
                 "(Bibliotheks-Standard: 0.5)")
    with a3:
        neu["AUDIO_TTS_TEMPERATURE"] = st.slider(
            "Stabilität ↔ Ausdruck", min_value=0.3, max_value=1.2,
            value=float(settings.AUDIO_TTS_TEMPERATURE), step=0.05,
            key="cfg_AUDIO_TTS_TEMPERATURE",
            help="Niedriger = ruhiger/stabiler, seltener Versprecher oder komische "
                 "Laute, aber etwas monotoner. Höher = abwechslungsreicher betont, "
                 "aber anfälliger für Aussetzer. Technisch: AUDIO_TTS_TEMPERATURE "
                 "(Bibliotheks-Standard: 0.8)")

    st.divider()

    # ------------------------------------------------------------------ #
    st.subheader("🌐 Externe Quellen (SearXNG)")
    st.caption("Opt-in für die Vortrag-Seite. Standard: aus (App bleibt offline). "
               "Die Instanz ist oft nur per VPN/LAN erreichbar.")
    neu["SEARXNG_ENABLED"] = st.checkbox(
        "SearXNG standardmäßig aktiv (kann auf der Vortrag-Seite überschrieben werden)",
        value=bool(settings.SEARXNG_ENABLED), key="cfg_SEARXNG_ENABLED",
        help="Technisch: SEARXNG_ENABLED")
    neu["SEARXNG_BASE_URL"] = st.text_input(
        "SearXNG-Basis-URL", value=str(settings.SEARXNG_BASE_URL),
        key="cfg_SEARXNG_BASE_URL",
        help="z. B. https://search.olbricht-digital.de/ – Technisch: SEARXNG_BASE_URL")
    sx1, sx2 = st.columns(2)
    with sx1:
        neu["SEARXNG_TIMEOUT_S"] = st.number_input(
            "Timeout (Sekunden)", min_value=3.0, max_value=60.0,
            value=float(settings.SEARXNG_TIMEOUT_S), step=1.0,
            key="cfg_SEARXNG_TIMEOUT_S")
    with sx2:
        neu["SEARXNG_MAX_RESULTS"] = st.number_input(
            "Max. Treffer", min_value=3, max_value=40,
            value=int(settings.SEARXNG_MAX_RESULTS), step=1,
            key="cfg_SEARXNG_MAX_RESULTS")
    st.caption("Verbindungstest: speichere zuerst, dann unten außerhalb des Formulars "
               "auf „Verbindung testen“.")

    st.divider()

    # ------------------------------------------------------------------ #
    st.subheader("📊 Evaluation (Qualitätsmessung)")
    st.caption("Für den Test der Suchqualität auf der Seite „Evaluation\".")
    e1, e2 = st.columns(2)
    with e1:
        neu["EVAL_SAMPLE_SIZE"] = st.number_input(
            "Anzahl Test-Textstellen", min_value=1, max_value=100000,
            value=int(settings.EVAL_SAMPLE_SIZE), step=10, key="cfg_EVAL_SAMPLE_SIZE",
            help="Wie viele zufällige Textstellen für den Qualitätstest gezogen "
                 "werden. Technisch: EVAL_SAMPLE_SIZE")
    with e2:
        neu["EVAL_QUESTIONS_PER_CHUNK"] = st.number_input(
            "Testfragen pro Textstelle", min_value=1, max_value=10,
            value=int(settings.EVAL_QUESTIONS_PER_CHUNK), step=1,
            key="cfg_EVAL_QUESTIONS_PER_CHUNK",
            help="Wie viele Prüf-Fragen je Textstelle erzeugt werden. "
                 "Technisch: EVAL_QUESTIONS_PER_CHUNK")

    st.caption(
        f"Hinweis: `EVAL_K_VALUES = {tuple(settings.EVAL_K_VALUES)}` (fest, nicht "
        "editierbar)."
    )

    st.divider()
    gespeichert = st.form_submit_button("💾 Speichern", type="primary")

if gespeichert:
    # number_input liefert je nach Startwert int/float: Typen bereinigen
    int_felder = {
        "DENSE_TOP_K", "BM25_TOP_K", "FUSION_TOP_K", "RRF_K", "FINAL_TOP_K",
        "CHUNK_SIZE", "CHUNK_OVERLAP", "MIN_CHUNK_CHARS", "LLM_NUM_CTX",
        "MAX_CONTEXT_CHARS", "EVAL_SAMPLE_SIZE", "EVAL_QUESTIONS_PER_CHUNK",
        "SEARXNG_MAX_RESULTS",
    }
    for k in int_felder:
        neu[k] = int(neu[k])

    settings.update(**neu)
    settings.save()
    st.success("Einstellungen gespeichert.")
    st.info(
        "ℹ️ **Wann wirkt was?** Retrieval- und Antwort-Parameter greifen **sofort** "
        "bei der nächsten Frage. **Chunking-Werte** (CHUNK_SIZE, CHUNK_OVERLAP, "
        "MIN_CHUNK_CHARS, RESPECT_MARKDOWN_HEADERS) betreffen den Index und wirken "
        "erst nach einem **Neu-Import** der Dokumente. Die Werte werden in "
        "`data/config.json` gespeichert."
    )

# --------------------------------------------------------------------------- #
# SearXNG-Verbindungstest (außerhalb des Formulars – st.button in forms geht nicht)
# --------------------------------------------------------------------------- #
st.divider()
st.subheader("🌐 SearXNG – Verbindungstest")
st.caption(f"Aktuell: `{settings.SEARXNG_BASE_URL}` · "
           f"{'aktiviert' if settings.SEARXNG_ENABLED else 'deaktiviert (Opt-in)'} · "
           "Oft nur per VPN/LAN erreichbar.")
if st.button("🔌 Verbindung testen", key="searx_health_test"):
    from ragapp.searx_client import health_check
    with st.spinner("Teste SearXNG …"):
        _ok, _msg = health_check()
    if _ok:
        st.success(_msg)
    else:
        st.warning(_msg)

# --------------------------------------------------------------------------- #
# Uni-/Sparmodus (außerhalb des Formulars, da st.button in Formularen nicht
# erlaubt ist) - ein Klick fürs reine Karteikarten-Lernen ohne jeden Modell-Ballast.
# --------------------------------------------------------------------------- #
st.divider()
with card("sparmodus"):
    st.subheader("🎓 Uni-/Sparmodus")
    st.caption(
        "Ein Klick für unterwegs: nichts lädt automatisch, Feinsortierung und "
        "Beleg-Prüfung sind aus, ein geladenes Modell wird sofort wieder entladen. "
        "Zum Karteikarten-Lernen brauchst du davon ohnehin nichts – Chat-Fragen bleiben "
        "möglich, laden dann aber bewusst erst auf Zuruf."
    )
    _spar_werte = {"PREWARM_ON_START": False, "USE_RERANKER": False,
                  "ENABLE_FAITHFULNESS_CHECK": False, "OLLAMA_KEEP_ALIVE_MINUTES": 0.0}
    _normal_werte = {k: getattr(Settings(), k) for k in _spar_werte}
    _aktuell = {k: getattr(settings, k) for k in _spar_werte}
    _ist_sparmodus = _aktuell == _spar_werte
    _ist_normalmodus = _aktuell == _normal_werte

    # Dauerhaft sichtbarer Status (nicht nur eine Toast-Meldung, die nach dem Neuladen
    # wieder verschwindet) - direkt aus den echten Einstellungen abgeleitet.
    if _ist_sparmodus:
        st.success("🎓 **Sparmodus ist aktiv.** Nichts lädt automatisch, Reranker/Beleg-Prüfung "
                   "sind aus, Modelle entladen sofort wieder.")
    elif _ist_normalmodus:
        st.info("💬 **Normalmodus ist aktiv** (Standardwerte für Vorladen/Reranker/Beleg-Prüfung).")
    else:
        st.caption("⚙️ Eigene Mischung aktiv – weder reiner Spar- noch Normalmodus "
                   "(z. B. weil du einzelne Werte oben selbst verändert hast).")

    _sp1, _sp2 = st.columns(2)
    with _sp1:
        if st.button("🎓 Uni-/Sparmodus aktivieren", use_container_width=True,
                     type="primary" if _ist_sparmodus else "secondary",
                     disabled=_ist_sparmodus):
            settings.update(**_spar_werte)
            settings.save()
            for _k in _spar_werte:
                st.session_state.pop(f"cfg_{_k}", None)
            st.rerun()
    with _sp2:
        if st.button("💬 Normalmodus (Chat-Komfort)", use_container_width=True,
                     type="primary" if _ist_normalmodus else "secondary",
                     disabled=_ist_normalmodus):
            settings.update(**_normal_werte)
            settings.save()
            for _k in _normal_werte:
                st.session_state.pop(f"cfg_{_k}", None)
            st.rerun()

    # --------------------------------------------------------------------------- #
    # Zurücksetzen (außerhalb des Formulars, da st.button in Formularen nicht erlaubt ist)
    # --------------------------------------------------------------------------- #
st.divider()
with card("reset"):
    st.subheader("↺ Zurücksetzen")
    st.caption(
        "Einen einzelnen Bereich auf die Standardwerte zurücksetzen – praktisch, wenn du "
        "dich vertippt hast oder ein Wert nicht wie gewünscht funktioniert hat. Betrifft "
        "nur den gewählten Bereich (ungespeicherte Änderungen im Formular gehen dabei "
        "verloren)."
    )

    # Bereich -> zugehörige Einstellungs-Schlüssel (gleiche Namen wie die cfg_-Widget-Keys)
    _BEREICHE = {
        "🔎 Suche": ["DENSE_TOP_K", "BM25_TOP_K", "FUSION_TOP_K", "FINAL_TOP_K", "RRF_K",
                     "RELEVANCE_MIN_SCORE", "DENSE_WEIGHT", "BM25_WEIGHT", "USE_RERANKER"],
        "✂️ Textabschnitte": ["CHUNK_SIZE", "CHUNK_OVERLAP", "MIN_CHUNK_CHARS",
                              "RESPECT_MARKDOWN_HEADERS"],
        "💬 Antwort": ["LLM_TEMPERATURE", "LLM_NUM_CTX", "MAX_CONTEXT_CHARS",
                      "ENABLE_FAITHFULNESS_CHECK"],
        "🧹 Deduplizierung": ["DEDUP_NEAR_DUPLICATE_THRESHOLD", "RETRIEVAL_DEDUP_JACCARD",
                             "RETRIEVAL_DEDUP"],
        "🔌 Modell-Ladeverhalten": ["PREWARM_ON_START", "OLLAMA_KEEP_ALIVE_MINUTES"],
        "🧠 Modelle": ["LLM_MODEL", "LLM_MODEL_FAST", "LLM_MODEL_AUTHOR", "EMBED_MODEL", "RERANKER_MODEL"],
        "📋 Lernplan": ["PLAN_TIME_FACTOR", "PLAN_REVIEW_SEC_PER_CARD", "PLAN_REVIEW_MAX_SHARE"],
        "📊 Evaluation": ["EVAL_SAMPLE_SIZE", "EVAL_QUESTIONS_PER_CHUNK"],
    }


    def _reset_bereich(keys: list) -> None:
        """Setzt nur die angegebenen Schlüssel auf die dataclass-Standardwerte, speichert
        und lädt die zugehörigen Formularfelder neu (Widget-State entfernen)."""
        _def = Settings()
        settings.update(**{k: getattr(_def, k) for k in keys})
        settings.save()
        for k in keys:
            st.session_state.pop(f"cfg_{k}", None)
            st.session_state.pop(f"cfg_{k}_custom", None)   # evtl. Eigen-Namensfeld


    _items = list(_BEREICHE.items())
    for _start in range(0, len(_items), 3):
        _cols = st.columns(3)
        for _col, (_name, _keys) in zip(_cols, _items[_start:_start + 3]):
            if _col.button(f"↺ {_name}", key=f"reset_{_name}", use_container_width=True):
                _reset_bereich(_keys)
                st.success(f"**{_name}** auf Standardwerte zurückgesetzt.")
                st.rerun()

    with st.expander("⚠️ Alles zurücksetzen"):
        st.caption("Löscht `data/config.json` komplett und stellt für **alle** Bereiche die "
                   "Standardwerte wieder her.")
        if st.button("↩️ Alles auf Standard zurücksetzen"):
            RUNTIME_CONFIG_FILE.unlink(missing_ok=True)
            settings.reset()
            for _k in list(st.session_state.keys()):
                if _k.startswith("cfg_"):
                    st.session_state.pop(_k, None)
            st.success("Alle Standardwerte wiederhergestellt (data/config.json gelöscht).")
            st.rerun()
