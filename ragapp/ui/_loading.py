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

    threading.Thread(target=_run, name="rag-prewarm", daemon=True).start()
