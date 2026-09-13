"""
Ehemaliger Import-Reiter – leitet auf Dokumente weiter.
=======================================================
Upload/Index liegen beim Dokumentenmanager, Fragen/Karten bei Karteikarten.
Die Datei bleibt, weil Streamlit sie sonst als tote Multipage-Seite listet.
"""
from __future__ import annotations

import sys
import pathlib

_p = pathlib.Path(__file__).resolve()
for _anc in _p.parents:
    if (_anc / "ragapp").is_dir():
        sys.path.insert(0, str(_anc))
        break

import streamlit as st

from ragapp.ui._loading import page_boot
page_boot("📥 Import", page_title="Import", icon="📥", layout="wide",
          accent="dokumente")

from ragapp.ui._style import PAGE_REGISTRY

st.info("Hochladen und die Bibliothek sind jetzt unter **🗃️ Dokumente**. "
        "Fragen anreichern und Karteikarten erstellen findest du unter **🎓 Karteikarten**.")
_docs_target = next(p["target"] for p in PAGE_REGISTRY if p["key"] == "dokumente")
st.switch_page(_docs_target)
