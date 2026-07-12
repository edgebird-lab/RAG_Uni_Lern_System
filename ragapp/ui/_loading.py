"""
Lade-Anzeige beim Seitenwechsel (Streamlit)
===========================================
Beim ERSTEN Öffnen einer Seite lädt Streamlit schwere Bibliotheken (torch,
chromadb, sentence-transformers) träge nach - das dauert Sekunden und zeigt
solange einen weißen Bildschirm. Diese Helfer importieren solche Module unter
einem Spinner, NACHDEM der Seitenkopf schon gerendert wurde.
"""
from __future__ import annotations

import importlib
import sys
import streamlit as st


def page_boot(title: str, *, page_title: "str | None" = None,
              icon: "str | None" = None, layout: str = "wide") -> None:
    """Einheitlicher Seitenkopf, der den WEISSEN BILDSCHIRM beim Seitenwechsel
    beseitigt: set_page_config -> PIN-Gate -> Theme -> und rendert SOFORT den
    Seitentitel. Weil Streamlit die neue Seite erst weiss macht und dann Zeile
    fuer Zeile rendert, sieht der Nutzer so unmittelbar den Titel statt Leere.

    Danach sollte die Seite ihre SCHWEREN Importe/Datenabfragen in einen
    ``with st.spinner(...)``-Block legen, damit waehrend des (kalten) Ladens ein
    kleiner Ladehinweis statt eines weissen Bereichs erscheint. Beispiel:

        import streamlit as st
        from ragapp.ui._loading import page_boot
        page_boot("Fortschritt", icon="chart", layout="wide")
        with st.spinner("Fortschritt wird geladen ..."):
            import pandas as pd
            from ragapp import analytics
        ...  # restlicher Seiteninhalt
    """
    st.set_page_config(page_title=page_title or title, page_icon=icon, layout=layout)
    # PIN-Gate + Theme werden bewusst hier importiert (leichtgewichtig), damit die
    # Seiten-Kopfzeile ohne vorherige schwere Importe rendern kann.
    from ragapp.ui._auth import require_pin
    require_pin()
    from ragapp.ui._theme import apply_theme
    apply_theme()
    if title:
        st.title(title)


def lazy_import(spinner_text: str, *module_names: str):
    """Importiert die Module (unter Spinner, falls noch nicht geladen) und gibt
    sie zurück (ein Modul -> Modul; mehrere -> Tupel). Zweiter Aufruf ~ gratis."""
    need_spinner = any(m not in sys.modules for m in module_names)
    if need_spinner:
        with st.spinner(spinner_text):
            mods = [importlib.import_module(m) for m in module_names]
    else:
        mods = [importlib.import_module(m) for m in module_names]
    return mods[0] if len(mods) == 1 else tuple(mods)


def prewarm(*module_names: str) -> None:
    """Importiert schwere Module in einem Hintergrund-Thread (App-Start), damit
    spätere Seitenwechsel sofort öffnen. Fehler werden bewusst verschluckt (reine
    Optimierung). Läuft prozessweit nur EINMAL."""
    import threading

    if getattr(prewarm, "_started", False):
        return
    prewarm._started = True  # type: ignore[attr-defined]

    def _run():
        for m in module_names:
            try:
                importlib.import_module(m)
            except Exception:
                pass
        # Nicht nur die Module importieren, sondern auch die Modell-GEWICHTE laden.
        # Sonst zahlt die ERSTE Frage den ~21 s-Kaltstart. Das geschieht hier,
        # waehrend der Nutzer die Startseite liest. Jeder Schritt ist bewusst
        # einzeln exception-safe (reine Optimierung, darf nie die App stoeren).
        try:
            from ragapp.retrieval.reranker import get_reranker
            get_reranker().warm()
        except Exception:
            pass
        try:
            from ragapp.retrieval.embeddings import get_embedder
            get_embedder().embed_query("warmup")
        except Exception:
            pass

    threading.Thread(target=_run, name="rag-prewarm", daemon=True).start()
