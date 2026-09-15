"""
Skript-Sitzung: 20 Minuten in der Unterlage nacharbeiten.
=========================================================
Seite bleibt sichtbar. Absätze antippen markiert sie. Karten und Notiz
entstehen ohne LLM. Fragen zur Stelle kommen erst, wenn man sie anstößt.
"""
from __future__ import annotations

import sys
import time
import pathlib

_p = pathlib.Path(__file__).resolve()
for _anc in _p.parents:
    if (_anc / "ragapp").is_dir():
        sys.path.insert(0, str(_anc))
        break

import streamlit as st

from ragapp.ui._loading import page_boot, skeleton
page_boot("📖 Skript", page_title="Skript", icon="📖", layout="wide", accent="skript")

from ragapp.ui._style import empty_state, page_title as _pt

st.markdown(
    "<p class='rag-page-lede small'>20 Minuten <b>in</b> der Unterlage: "
    "Absatz antippen, Karte legen, am Ende eine Notiz. "
    "Das Modell startet nicht von allein.</p>",
    unsafe_allow_html=True,
)

with skeleton("Skript wird geladen …"):
    from ragapp.config import PROJECT_ROOT, SUBJECT_LABELS
    from ragapp import student_flow as _sf
    from ragapp.ui import _docviewer


@st.cache_data(show_spinner=False)
def _skript_png(path_str: str, mtime: float, page: int):
    return _docviewer.render_pdf_page(path_str, page)


_pre = st.session_state.pop("skript_prefill", None)
if _pre:
    _spot = _sf.hydrate_skript_spot(_pre)
    if _spot:
        st.session_state["skript_session"] = {
            **_spot,
            "started_at": time.time(),
            "marks": [],
            "current": None,
        }

if "skript_session" not in st.session_state:
    _flash = st.session_state.pop("_skript_flash", None)
    if _flash:
        st.success(_flash)
        if st.button("Nächste Skript-Sitzung", type="primary", key="skript_again"):
            _spot = _sf.pick_skript_spot()
            if _spot:
                st.session_state["skript_session"] = {
                    **_spot, "started_at": time.time(),
                    "marks": [], "current": None,
                }
                st.rerun()
        st.stop()
    _spot = _sf.pick_skript_spot()
    if _spot:
        st.session_state["skript_session"] = {
            **_spot,
            "started_at": time.time(),
            "marks": [],
            "current": None,
        }

_sess = st.session_state.get("skript_session")
if not _sess:
    empty_state(
        "Keine Unterlage zum Nacharbeiten. Lade Dateien unter **Dokumente** hoch.",
        cta_label=f"Zu {_pt('dokumente')}",
        page_key="dokumente",
        icon="📥",
        key="skript_empty_dokumente",
    )
    st.stop()

_sp = _sess.get("source_path") or ""
_path = pathlib.Path(_sp) if pathlib.Path(_sp).is_absolute() else PROJECT_ROOT / _sp
_heading = (_sess.get("heading") or "Skript").strip()
_page = max(1, int(_sess.get("page") or 1))
_is_pdf = _path.suffix.lower() == ".pdf"
_n_pages = _docviewer.pdf_page_count(_path) if _is_pdf else 1
if _is_pdf and _n_pages:
    _page = min(_page, _n_pages)
    _sess["page"] = _page

_left = max(0, int(_sess.get("minutes") or 20) - int(
    (time.time() - float(_sess.get("started_at") or time.time())) / 60))
_fach = SUBJECT_LABELS.get(_sess.get("subject"), _sess.get("subject")) or ""

st.info(f"Skript-Sitzung · **{_heading}** · noch etwa {_left} Min")
st.caption(f"{_sess.get('filename') or _path.name}"
           + (f"  ·  {_fach}" if _fach else ""))
_flash = st.session_state.pop("_skript_flash", None)
if _flash:
    st.success(_flash)

if not _path.is_file():
    st.warning("Originaldatei nicht gefunden – unter Dokumente prüfen.")
    st.stop()

if _is_pdf:
    _nav1, _nav2, _nav3 = st.columns([1, 2, 1])
    with _nav1:
        if st.button("← Vorherige", disabled=_page <= 1, use_container_width=True,
                     key="skript_prev"):
            _sess["page"] = _page - 1
            _sess["current"] = None
            st.rerun()
    _nav2.markdown(
        f"<p style='text-align:center;margin:.55rem 0 0'>Seite {_page} / "
        f"{max(1, _n_pages)}</p>",
        unsafe_allow_html=True)
    with _nav3:
        if st.button("Nächste →", disabled=_n_pages <= _page, use_container_width=True,
                     key="skript_next"):
            _sess["page"] = _page + 1
            _sess["current"] = None
            st.rerun()

    _mtime = _path.stat().st_mtime
    _png = _skript_png(str(_path), _mtime, _page)
    if _png:
        st.image(_png, use_container_width=True)
    else:
        st.warning("Seite konnte nicht gerendert werden.")
    _passages = _docviewer.passages_on_page(_path, _page, heading=_heading)
else:
    _full = _docviewer.load_full_text(_path) or ""
    if _full:
        st.markdown(_full if len(_full) < 4000 else _full[:4000] + "\n\n…")
    else:
        st.caption("Kein Text extrahierbar.")
    _passages = _docviewer.passages_on_page(_path, heading=_heading)

if _passages:
    st.markdown("##### Absätze auf dieser Seite")
    st.caption("Antippen markiert den Absatz – daraus wird später die Karte.")
    for _i, _row in enumerate(_passages):
        _txt = (_row.get("text") or "").strip()
        _lab = _txt if len(_txt) <= 90 else _txt[:88].rstrip() + "…"
        if st.button(_lab, key=f"skript_p_{_page}_{_i}", use_container_width=True):
            _mark = {"text": _txt, "heading": _heading, "page": _page}
            _sess["current"] = _mark
            _marks = list(_sess.get("marks") or [])
            _key = _txt[:80].lower()
            if _key not in {((m.get("text") or "")[:80].lower()) for m in _marks}:
                _marks.append(_mark)
                _sess["marks"] = _marks
            st.rerun()
else:
    st.caption("Keine Absätze auf dieser Seite.")

_cur = _sess.get("current") or {}
if _cur.get("text"):
    st.caption("Markiert: **" + (_cur["text"][:160]
               + ("…" if len(_cur["text"]) > 160 else "")) + "**")

if st.button("Karte aus Markierung", type="secondary",
             disabled=not (_cur.get("text")),
             key="skript_card", use_container_width=True):
    _cid = _sf.card_from_text(
        (_cur.get("heading") or _heading)[:120],
        _cur["text"], source="skript",
        subject=_sess.get("subject"), topic=_heading,
        doc_id=_sess.get("doc_id"))
    if _cid:
        st.session_state["_skript_flash"] = "Karte gespeichert"
    else:
        st.session_state["_skript_flash"] = "Karte konnte nicht angelegt werden"
    st.rerun()

if st.button("Sitzung beenden – Notiz + Karten", key="skript_end",
             use_container_width=True):
    _out = _sf.finish_skript_session(
        _sess.get("marks") or [],
        heading=_heading,
        subject=_sess.get("subject"),
        doc_id=_sess.get("doc_id"),
        filename=_sess.get("filename"),
        started_at=float(_sess.get("started_at") or time.time()),
        minutes=int(_sess.get("minutes") or 20),
        block_id=_sess.get("block_id"),
    )
    st.session_state.pop("skript_session", None)
    _k = len(_out.get("card_ids") or [])
    st.session_state["_skript_flash"] = (
        f"Notiz + {_k} Karte(n) gespeichert" if _out.get("note_id")
        else "Sitzung beendet")
    st.rerun()

st.markdown("<div style='height:4.5rem'></div>", unsafe_allow_html=True)
