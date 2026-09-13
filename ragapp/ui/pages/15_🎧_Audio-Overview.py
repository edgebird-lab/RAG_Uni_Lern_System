"""
RAG-Lernsystem: Seite „Audio-Overview" (Vorlesen mit der eigenen Stimme)
==========================================================================
Erzeugt aus den gewählten Dokumenten ein gesprochen klingendes Erklär-Skript
und vertont es mit der eigenen, geklonten Stimme (Chatterbox Multilingual,
siehe ``ragapp/audio_overview.py`` und docs/STIMME_AUFNEHMEN.md) - bewusst KEINE
generische KI-Stimme. Die KI-Generierung laeuft bewusst ZWEISTUFIG: erst nur
das Skript schreiben lassen und zur Kontrolle anzeigen, DANACH erst auf einen
eigenen Klick hin vertonen - ein Fehler im Text faellt so auf, BEVOR die
mehrminuetige Vertonung laeuft, nicht erst danach. Alternativ laesst sich ein
Skript auch komplett selbst schreiben (keine Dokumente/KI noetig) und ein
bestehendes Skript laesst sich bearbeiten und NUR neu vertonen, ohne die
KI-Generierung erneut anzustossen.

Fachjargon (Kommandos, Abkuerzungen wie "nmap") wird von JEDEM TTS-Modell nach
Standard-Ausspracheregeln vorgelesen, nicht wie im IT-Jargon ueblich - das ist
ein Text-Normalisierungs-, kein Stimmqualitaets-Problem (siehe Moduldoc
``ragapp/audio_overview.py``). ``_render_pronunciation_hints`` laesst dafuer
das LLM Aussprache-Vorschlaege machen; bestaetigte Korrekturen werden
dauerhaft gemerkt (``manifest.pronunciation_fixes``) und gelten automatisch
fuer alle kuenftigen Audio-Overviews.

Mehrere Audio-Overviews lassen sich zusaetzlich zu einem Hoerbuch buendeln
(siehe ``ragapp/audiobook.py``) - statt die einzelnen WAVs von Hand aufs
Handy zu ziehen und dort zusammenzufuegen.
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

from ragapp.ui._loading import page_boot, skeleton
page_boot("🎧 Audio-Overview", page_title="Audio-Overview", icon="🎧", layout="wide",
         accent="audio")

from ragapp.ui._style import card

st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1000px;}
h1 {font-weight: 750; letter-spacing:-0.5px;}
</style>
""", unsafe_allow_html=True)

st.caption("Lässt deine Dokumente als gesprochenes Erklär-Skript zusammenfassen und vertont "
           "es mit deiner eigenen (geklonten) Stimme - keine generische KI-Stimme. Skripte "
           "lassen sich auch selbst schreiben oder im Nachgang bearbeiten.")

with skeleton("Audio-Overview wird geladen ..."):
    from ragapp import manifest, audio_overview, audiobook
    from ragapp.config import settings, SUBJECT_LABELS, PROJECT_ROOT, AUDIO_DIR
    from ragapp.llm import list_installed_models
    # _fmt_dauer/_progress_tracker liegen jetzt gemeinsam mit Zusammenfassung in
    # ragapp/ui/_progress.py (identisches Muster, zwei driftende Kopien vermieden).
    from ragapp.ui._progress import fmt_dauer as _fmt_dauer, progress_tracker as _progress_tracker

_KEIN_FACH = "— Kein Fach —"


def _fach(code: "str | None") -> str:
    return SUBJECT_LABELS.get(code, code) if code else "–"


from ragapp.ui._pronunciation import render_pronunciation_hints as _render_pronunciation_hints


def _model_picker(key: str) -> "str | None":
    """Modellwahl fürs Sprech-Skript (nicht die Sprachsynthese selbst - dort
    gibt es nur Chatterbox Multilingual) - gleiches Gründlich/Schnell-Muster
    wie bei Mindmap/Lernplan/Übungsaufgaben."""
    _author = settings.author_model()
    _fast = settings.LLM_MODEL_FAST
    _installed = list_installed_models() or []
    _options = [f"🎯 Gründlich ({_author})", f"⚡ Schnell ({_fast})"] + sorted(
        m for m in _installed if m not in (_author, _fast))
    _choice = st.selectbox("Modell fürs Skript", _options, key=key,
                           help="Nur für den Text - die Stimme kommt immer aus Chatterbox "
                                "Multilingual.")
    if _choice.startswith("🎯 Gründlich"):
        return None
    if _choice.startswith("⚡ Schnell"):
        return _fast
    return _choice


_ref_path = PROJECT_ROOT / settings.AUDIO_REFERENCE_WAV
if not _ref_path.is_file():
    with card("keine_stimme"):
        st.markdown("##### 🎙️ Noch keine Stimm-Referenz vorhanden")
        st.write(
            "Bevor Audio-Overviews erzeugt werden können, braucht die App eine kurze "
            "Aufnahme deiner Stimme (mehrere Minuten, einmalig - kann später jederzeit "
            "durch eine neue Aufnahme ersetzt werden)."
        )
        st.markdown(
            "**So geht's:** Anleitung + fertiger Vorlesetext stehen in "
            "`docs/STIMME_AUFNEHMEN.md`. Die Aufnahme danach unter "
            f"`{settings.AUDIO_REFERENCE_WAV}` ablegen."
        )
        st.caption("Direkt in der App aufnehmen oder eine WAV-Datei hochladen:")
        _rec = st.audio_input("Stimme aufnehmen", key="voice_record")
        _uploaded = st.file_uploader("Oder WAV hochladen", type=["wav"], key="voice_upload")
        _blob = None
        if _rec is not None:
            _blob = _rec.getvalue()
        elif _uploaded is not None:
            _blob = _uploaded.getvalue()
        if _blob and st.button("💾 Als Referenz speichern", type="primary"):
            from ragapp.student_flow import save_voice_reference
            save_voice_reference(_blob)
            st.success("Gespeichert. Die Seite lädt jetzt neu.")
            st.rerun()
    st.stop()

_all_docs = [dict(d) for d in manifest.list_documents()
            if d["use_rag"] and d["num_chunks"] > 0]
_subjects_with_docs = sorted({d["subject"] for d in _all_docs if d["subject"]})

_overviews = manifest.list_audio_overviews()
_ov_by_id = {o["overview_id"]: o for o in _overviews}

if "_audio_pending_choice" in st.session_state:
    st.session_state["audio_choice"] = st.session_state.pop("_audio_pending_choice")
elif st.session_state.get("audio_choice") not in ([None] + list(_ov_by_id.keys())):
    st.session_state["audio_choice"] = None


def _fmt_ov_option(oid: "str | None") -> str:
    if oid is None:
        return "➕ Neues Audio-Overview"
    o = _ov_by_id.get(oid)
    return f"{o['title']}  ·  {_fach(o['subject'])}" if o else "(gelöscht)"


st.selectbox("Audio-Overview wählen", [None] + list(_ov_by_id.keys()),
            format_func=_fmt_ov_option, key="audio_choice")
_active_id = st.session_state.get("audio_choice")

# --------------------------------------------------------------------------- #
# Dauerhaft gemerkte Ausspracheregeln (siehe _render_pronunciation_hints/
# manifest.pronunciation_fixes) - Uebersicht mit Bearbeiten/Loeschen, falls
# sich eine Korrektur im Nachhinein als falsch herausstellt, PLUS die
# Moeglichkeit, eigene Regeln unabhaengig von einer KI-Erkennung neu
# anzulegen (z. B. ein Fachbegriff, den die KI noch nie als falsch
# ausgesprochen gemeldet hat). Der Expander bleibt daher immer sichtbar,
# auch ohne bereits gespeicherte Regeln.
# --------------------------------------------------------------------------- #
# Nach erfolgreichem Hinzufuegen die beiden Eingabefelder leeren - MUSS vor der
# Widget-Erzeugung passieren (siehe unten): st.session_state[key] direkt nach
# dem Klick zu setzen, waere zu spaet und wirft StreamlitAPIException
# ("cannot be modified after the widget ... is instantiated"), weil die
# Widgets in DEMSELBEN Skriptlauf schon vorher gerendert wurden - deshalb der
# Umweg ueber einen "pending"-Schluessel (gleiches Muster wie
# "_audio_pending_choice" oben).
if st.session_state.pop("_pron_new_clear_pending", False):
    st.session_state["pron_new_word"] = ""
    st.session_state["pron_new_replacement"] = ""

_pron_fixes = manifest.list_pronunciation_fixes()
_pron_label = (f"🔤 {len(_pron_fixes)} gespeicherte Ausspracheregel(n) verwalten"
              if _pron_fixes else "🔤 Ausspracheregeln verwalten")
with st.expander(_pron_label, key="pron_manage_expander"):
    st.caption("Gilt automatisch für alle Audio-Overviews (KI-generiert, selbst "
               "geschrieben oder neu vertont).")
    if _pron_fixes:
        for _word, _replacement in _pron_fixes.items():
            _pc1, _pc2, _pc3, _pc4 = st.columns([2, 3, 1, 1])
            _pc1.markdown(f"**{_word}**")
            _new_repl = _pc2.text_input(
                "Ersetzung", value=_replacement, key=f"pron_edit_{_word}",
                label_visibility="collapsed")
            if _pc3.button("💾", key=f"pron_save_{_word}", help="Änderung speichern"):
                _clean_repl = (_new_repl or "").strip()
                if _clean_repl:
                    manifest.upsert_pronunciation_fix(_word, _clean_repl)
                    st.success(f"„{_word}“ aktualisiert.")
                    st.rerun()
                else:
                    st.warning("Ersetzung darf nicht leer sein.")
            if _pc4.button("🗑️", key=f"pron_del_{_word}", help="Regel löschen"):
                manifest.delete_pronunciation_fix(_word)
                st.rerun()
        st.divider()

    st.markdown("**➕ Neue Regel hinzufügen**")
    st.caption("Für eigene Sprachregeln - z. B. ein Fachbegriff, den die KI falsch vorschlägt "
              "oder noch gar nicht erkannt hat.")
    _npc1, _npc2, _npc3 = st.columns([2, 3, 1])
    _new_word_val = _npc1.text_input("Wort/Ausdruck", key="pron_new_word",
                                     placeholder="z. B. nmap")
    _new_repl_val = _npc2.text_input("Gesprochene Ersetzung", key="pron_new_replacement",
                                     placeholder="z. B. en map")
    if _npc3.button("➕ Hinzufügen", key="pron_add_new", use_container_width=True):
        _w = (_new_word_val or "").strip()
        _r = (_new_repl_val or "").strip()
        if not _w or not _r:
            st.warning("Bitte Wort UND Ersetzung eingeben.")
        else:
            manifest.upsert_pronunciation_fix(_w, _r)
            st.session_state["_pron_new_clear_pending"] = True
            st.success(f"Regel für „{_w}“ gespeichert.")
            st.rerun()

# --------------------------------------------------------------------------- #
# Hörbuch-Export: mehrere Audio-Overviews in gewählter Reihenfolge zu einem
# getaggten ZIP bündeln (siehe ragapp/audiobook.py) - erspart das manuelle
# Zusammenfügen einzelner WAV-Downloads auf dem Handy. Reihenfolge per
# ⬆️/⬇️ statt Drag&Drop (Streamlit hat kein natives Umsortieren einer Liste);
# eine eigene session_state-Liste haelt die Sortierung ueber Reruns hinweg
# und wird nur bei einer NEUEN Auswahl (anderer Wortlaut/Anzahl) aus der
# Multiselect-Reihenfolge neu aufgebaut.
# --------------------------------------------------------------------------- #
if _ov_by_id:
    # key= haelt den Auf/Zu-Zustand explizit ueber Reruns hinweg fest - ohne
    # key faellt der Expander sonst bei JEDEM Rerun auf expanded=False zurueck,
    # auch wenn nur ein WIDGET DARIN (das Multiselect) den Rerun ausgeloest
    # hat: beobachtet, dass eine Auswahl die gerade geoeffnete Box sofort
    # wieder zuklappte.
    with st.expander("📚 Mehrere Audio-Overviews als Hörbuch exportieren",
                     key="audiobook_expander"):
        st.caption("Wählt mehrere Audio-Overviews aus, bringt sie in die gewünschte "
                   "Reihenfolge und ladet sie als EIN ZIP herunter - saubere "
                   "Kapitel-Dateien (kleiner als WAV, mit Titel/Album/Kapitelnummer "
                   "getaggt und lautstärke-angeglichen), fürs direkte Reinziehen in "
                   "eine Musik-/Hörbuch-App aufs Handy statt manuellem Zusammenfügen.")

        _book_selected = st.multiselect(
            "Audio-Overviews auswählen", list(_ov_by_id.keys()),
            format_func=_fmt_ov_option, key="audiobook_selected",
            placeholder="Auswählen …")

        if _book_selected:
            if st.session_state.get("_audiobook_order_base") != _book_selected:
                st.session_state["_audiobook_order"] = list(_book_selected)
                st.session_state["_audiobook_order_base"] = list(_book_selected)
            _order: list[str] = st.session_state["_audiobook_order"]

            st.caption("Reihenfolge (Kapitel 1 zuerst):")
            for _idx, _oid in enumerate(_order):
                _oc1, _oc2, _oc3 = st.columns([7, 1, 1])
                _oc1.write(f"{_idx + 1}. {_fmt_ov_option(_oid)}")
                if _oc2.button("⬆️", key=f"book_up_{_oid}", disabled=_idx == 0,
                              help="Nach oben"):
                    _order[_idx - 1], _order[_idx] = _order[_idx], _order[_idx - 1]
                    st.rerun()
                if _oc3.button("⬇️", key=f"book_down_{_oid}",
                              disabled=_idx == len(_order) - 1, help="Nach unten"):
                    _order[_idx + 1], _order[_idx] = _order[_idx], _order[_idx + 1]
                    st.rerun()

            _book_title = st.text_input("Buchtitel", value="Mein Hörbuch",
                                        key="audiobook_title")

            if st.button("📚 Hörbuch exportieren", type="primary", key="audiobook_export"):
                _book_bar = st.progress(0.0)
                _book_cap = st.empty()
                try:
                    _zip_path = audiobook.export_audiobook(
                        _order, _book_title or "Mein Hörbuch",
                        on_progress=_progress_tracker(_book_bar, _book_cap, "Export"))
                except audiobook.AudiobookError as exc:
                    st.error(str(exc))
                    st.stop()
                st.success("Hörbuch-ZIP erstellt.")
                st.download_button(
                    "⬇️ ZIP herunterladen", data=_zip_path.read_bytes(),
                    file_name=_zip_path.name, mime="application/zip",
                    use_container_width=True)

st.divider()

with st.expander("🎙️ Stimme ersetzen", expanded=False):
    _rec2 = st.audio_input("Neu aufnehmen", key="voice_replace_rec")
    _up2 = st.file_uploader("Oder neue WAV", type=["wav"], key="voice_replace_up")
    _blob2 = (_rec2.getvalue() if _rec2 is not None
              else _up2.getvalue() if _up2 is not None else None)
    if _blob2 and st.button("Referenz überschreiben", key="voice_replace_save"):
        from ragapp.student_flow import save_voice_reference
        save_voice_reference(_blob2)
        st.success("Neue Stimme gespeichert.")
        st.rerun()

# --------------------------------------------------------------------------- #
# Neues Audio-Overview: aus Dokumenten (KI) ODER selbst geschrieben
# --------------------------------------------------------------------------- #
if _active_id is None:
    _pref_script = st.session_state.pop("audio_prefill_script", None)
    if _pref_script:
        st.session_state["audio_create_mode"] = "✍️ Eigenes Skript schreiben"
        st.session_state["audio_manual_script"] = _pref_script
    st.markdown("##### Neues Audio-Overview anlegen")
    if st.button("🎯 Nur schwaches Fach vorlesen", key="audio_weak"):
        from ragapp.student_flow import weak_subject
        _ws = weak_subject()
        if _ws:
            st.session_state["audio_new_subject"] = _ws
            st.info(f"Fach {_ws} vorausgewählt (niedrigste Mastery/höchste Priorität).")
    _mode = st.radio(
        "Woher kommt der Text?",
        ["🤖 Aus Dokumenten generieren lassen", "✍️ Eigenes Skript schreiben"],
        horizontal=True, key="audio_create_mode",
        help="Eigenes Skript: kein Dokument/keine KI nötig - direkt Text eingeben und "
             "mit deiner Stimme vorlesen lassen.")

    if _mode.startswith("🤖"):
        if not _subjects_with_docs:
            st.info("Noch keine indexierten Dokumente (im RAG) vorhanden. Gehe zu "
                    "**📥 Ingestion**, um welche hinzuzufügen - oder nutze oben "
                    "„✍️ Eigenes Skript schreiben“, das braucht keine Dokumente.")
            st.stop()

        # Erst NUR das Skript schreiben lassen und zur Kontrolle anzeigen - die
        # (mehrminütige) Vertonung startet erst auf einen eigenen Klick hin,
        # NACHDEM der Text geprüft/korrigiert wurde. Vorher lief beides in
        # einem Rutsch durch: ein Fehler im Skript (falscher Fakt, abgehackter
        # Satz) fiel erst NACH der teuren Vertonung auf und kostete eine
        # zweite komplette Runde. Der Zwischenstand liegt bis zum "Jetzt
        # vertonen"-Klick nur im Session-State, nicht in der DB.
        _draft = st.session_state.get("_audio_script_draft")

        if _draft is None:
            nc1, nc2 = st.columns(2)
            with nc1:
                _new_subject = st.selectbox(
                    "Fach (optional)", [None] + _subjects_with_docs,
                    format_func=lambda s: _KEIN_FACH if s is None else _fach(s),
                    key="audio_new_subject",
                    help="Nur zum Filtern der Dokumentliste unten und zur Anzeige - "
                         "nicht zwingend nötig.")
            with nc2:
                if st.session_state.get("_audio_title_for_subject") != _new_subject:
                    st.session_state["audio_new_title"] = (
                        f"Audio-Overview {_fach(_new_subject)}" if _new_subject
                        else "Audio-Overview")
                    st.session_state["_audio_title_for_subject"] = _new_subject
                _new_title = st.text_input("Titel", key="audio_new_title")

            _subj_docs = {d["filename"]: d["doc_id"] for d in _all_docs
                          if _new_subject is None or d["subject"] == _new_subject}
            _new_doc_names = st.multiselect("Dokument(e)", list(_subj_docs.keys()),
                                            key="audio_new_docs", placeholder="Auswählen …")
            st.caption("Das Skript deckt den Inhalt vollständig ab (Abschnitt für Abschnitt) - "
                       "Erzeugungsdauer UND Audiolänge wachsen deshalb mit der Menge an "
                       "gewählten Dokumenten. Für ein kürzeres Overview lieber gezielt einzelne "
                       "Dokumente statt eines ganzen Fachs wählen.")

            _new_model = _model_picker("audio_new_model")

            if st.button("📝 Skript schreiben lassen", type="primary",
                        disabled=not _new_doc_names):
                _doc_ids = [_subj_docs[n] for n in _new_doc_names]
                _script_bar = st.progress(0.0)
                _script_cap = st.empty()
                try:
                    _script, _warning = audio_overview.generate_overview_script(
                        _doc_ids, _new_subject, model=_new_model,
                        on_progress=_progress_tracker(_script_bar, _script_cap, "Skript"))
                except audio_overview.AudioOverviewError as exc:
                    st.error(str(exc))
                    st.stop()
                st.session_state["_audio_script_draft"] = {
                    "script": _script, "warning": _warning,
                    "title": _new_title or f"Audio-Overview {_fach(_new_subject)}",
                    "subject": _new_subject, "doc_ids": _doc_ids, "model": _new_model,
                }
                st.rerun()

        else:
            st.markdown("##### 📝 Skript prüfen, bevor daraus Audio wird")
            st.caption("Kurz drüberlesen und korrigieren, was falsch klingt, sich wiederholt "
                       "oder zu lang ist - erspart einen zweiten, mehrminütigen Vertonungslauf.")
            if _draft["warning"]:
                st.warning(_draft["warning"])
            _draft_key = "audio_draft_script_edit"
            st.text_area("Skript-Text", value=_draft["script"], height=320, key=_draft_key)
            st.caption(f"{len(st.session_state[_draft_key])} Zeichen · {_fach(_draft['subject'])} "
                      f"· {len(_draft['doc_ids'])} Dokument(e)")
            _render_pronunciation_hints(st.session_state[_draft_key], key_prefix="draft")

            dc1, dc2 = st.columns([1, 1])
            if dc1.button("🎙️ Jetzt vertonen", type="primary", use_container_width=True,
                         key="audio_draft_vertonen"):
                _audio_bar = st.progress(0.0)
                _audio_cap = st.empty()
                try:
                    _new_oid = audio_overview.synthesize_and_save_overview(
                        st.session_state[_draft_key], _draft["title"], _draft["subject"],
                        _draft["doc_ids"], _draft["model"],
                        on_progress=_progress_tracker(_audio_bar, _audio_cap, "Vertonung"))
                except audio_overview.AudioOverviewError as exc:
                    st.error(str(exc))
                    st.stop()
                st.success("Audio erstellt.")
                st.session_state.pop("_audio_script_draft", None)
                st.session_state.pop(_draft_key, None)
                st.session_state["_audio_pending_choice"] = _new_oid
                st.rerun()
            if dc2.button("🗑️ Verwerfen & neu anfangen", use_container_width=True,
                         key="audio_draft_discard"):
                st.session_state.pop("_audio_script_draft", None)
                st.session_state.pop(_draft_key, None)
                st.rerun()

    else:
        _man_subject = st.selectbox(
            "Fach (optional)", [None] + sorted(SUBJECT_LABELS.keys() | set(_subjects_with_docs)),
            format_func=lambda s: _KEIN_FACH if s is None else _fach(s), key="audio_manual_subject")
        _man_title = st.text_input("Titel", value="Meine Sprachnotiz", key="audio_manual_title")
        _man_script = st.text_area(
            "Skript-Text", height=280, key="audio_manual_script",
            placeholder="Schreib hier deinen eigenen Text - wird 1:1 mit deiner Stimme "
                        "vorgelesen, ganz ohne KI-Generierung oder Dokumente.")
        st.caption(f"{len(_man_script)} Zeichen. Kein Dokument nötig - der Text wird direkt "
                   "vertont.")
        _render_pronunciation_hints(_man_script, key_prefix="manual")

        if st.button("🎧 Audio erzeugen", type="primary", disabled=not _man_script.strip()):
            _audio_bar = st.progress(0.0)
            _audio_cap = st.empty()
            try:
                _new_oid = audio_overview.create_manual_audio_overview(
                    _man_script, _man_title or "Meine Sprachnotiz", subject=_man_subject,
                    on_progress=_progress_tracker(_audio_bar, _audio_cap, "Vertonung"))
            except audio_overview.AudioOverviewError as exc:
                st.error(str(exc))
                st.stop()
            st.success("Audio erstellt.")
            st.session_state["_audio_pending_choice"] = _new_oid
            st.rerun()
    st.stop()

# --------------------------------------------------------------------------- #
# Bestehendes Audio-Overview anzeigen
# --------------------------------------------------------------------------- #
_active = manifest.get_audio_overview(_active_id)
if _active is None:
    st.session_state["_audio_pending_choice"] = None
    st.rerun()

_audio_path = AUDIO_DIR / _active["audio_path"]
_has_source_docs = bool(_active["doc_ids"])

with card("player"):
    hh1, hh2 = st.columns([3, 1])
    with hh1:
        st.markdown(f"##### {_active['title']}")
        st.caption(_fach(_active["subject"]))
    with hh2:
        _doc_label = f"{len(_active['doc_ids'])} Dokument(e)" if _has_source_docs else "✍️ Eigenes Skript"
        st.markdown(f"<div style='text-align:right;padding-top:6px;font-size:.8rem;opacity:.7'>"
                   f"{_doc_label}</div>", unsafe_allow_html=True)

    _gen_warning = st.session_state.pop("_audio_gen_warning", None)
    if _gen_warning:
        st.warning(_gen_warning)
    _gen_notice = st.session_state.pop("_audio_gen_notice", None)
    if _gen_notice:
        st.info(_gen_notice)

    if not _audio_path.is_file():
        st.error("Die Audiodatei fehlt (evtl. manuell gelöscht) - bitte neu erzeugen.")
    else:
        _audio_bytes = _audio_path.read_bytes()
        st.audio(_audio_bytes, format="audio/wav")

        # Nutzer-Wunsch: weg von reinem WAV, Dateityp beim Download waehlbar
        # machen ("eigene Converter integrieren") - nutzt denselben
        # torchaudio/ffmpeg-Weg, der sich beim Hoerbuch-Export schon bewaehrt
        # hat (siehe ragapp/audio_convert.py). Ergebnis pro (Overview, Format)
        # zwischengespeichert, damit ein Klick auf "Herunterladen" (das selbst
        # einen Rerun ausloest) nicht jedes Mal neu konvertiert.
        from ragapp import audio_convert
        _dl_format = st.selectbox(
            "Format zum Herunterladen", list(audio_convert.SUPPORTED_FORMATS.keys()),
            format_func=lambda f: audio_convert.SUPPORTED_FORMATS[f]["label"],
            key=f"audio_dl_format_{_active_id}")
        _dl_spec = audio_convert.SUPPORTED_FORMATS[_dl_format]
        _cache_key = f"_audio_dl_cache_{_active_id}_{_dl_format}"
        if _dl_format == "wav":
            st.session_state[_cache_key] = _audio_bytes
        elif _cache_key not in st.session_state:
            with st.spinner(f"Wandle nach {_dl_format.upper()} um …"):
                try:
                    st.session_state[_cache_key] = audio_convert.convert_wav_bytes(
                        _audio_bytes, _dl_format)
                except audio_convert.AudioConvertError as exc:
                    st.session_state[_cache_key] = None
                    st.error(str(exc))
        _dl_bytes = st.session_state.get(_cache_key)
        if _dl_bytes:
            st.download_button(
                f"⬇️ Herunterladen ({_dl_spec['ext'].upper()})", data=_dl_bytes,
                file_name=f"{_active['title']}.{_dl_spec['ext']}", mime=_dl_spec["mime"],
                use_container_width=True, key=f"audio_dl_go_{_active_id}_{_dl_format}")

    _chaps = [p.strip() for p in (_active.get("script_text") or "").split("\n\n")
              if len(p.strip()) >= 40][:16]
    if _chaps:
        with st.expander(f"Kapitel ({len(_chaps)})", expanded=False):
            for _i, _ch in enumerate(_chaps, 1):
                st.caption(f"{_i}. {_ch.splitlines()[0][:90]}")
    st.markdown("##### 📝 Skript bearbeiten")
    st.caption("Text kürzen, falsche Angaben rausnehmen oder frei umschreiben - „Speichern & "
               "nur Audio neu erzeugen“ vertont GENAU diesen Text neu, ohne die KI erneut zu "
               "bemühen (schnell, kein neuer Durchlauf durch die Dokumente).")
    _edit_key = f"audio_script_edit_{_active_id}"
    # Nach "Neu von der KI schreiben lassen" (siehe Popover unten) steht ein frisches
    # Skript bereit, das dieses Feld hier zeigen soll - direktes Ueberschreiben von
    # st.session_state[_edit_key] NACH dem Rerun waere zu spaet (Widget schon
    # instanziiert), deshalb der Umweg ueber einen "pending"-Schluessel, der VOR der
    # Widget-Erzeugung geleert wird (gleiches Muster wie "_audio_pending_choice" oben).
    _pending_regen = st.session_state.pop("_audio_regen_pending_script", None)
    if _pending_regen is not None:
        st.session_state[_edit_key] = _pending_regen
    st.text_area("Skript-Text", value=_active["script_text"], height=280, key=_edit_key)
    _render_pronunciation_hints(st.session_state[_edit_key], key_prefix=f"existing_{_active_id}")

    ec1, ec2 = st.columns([1, 1])
    if ec1.button("💾 Speichern & nur Audio neu erzeugen", key=f"audio_resynth_{_active_id}",
                 type="primary", use_container_width=True):
        _edited = st.session_state[_edit_key]
        _audio_bar = st.progress(0.0)
        _audio_cap = st.empty()
        try:
            audio_overview.resynthesize_audio_overview(
                _active_id, _edited,
                on_progress=_progress_tracker(_audio_bar, _audio_cap, "Vertonung"))
        except audio_overview.AudioOverviewError as exc:
            st.error(str(exc))
            st.stop()
        st.success("Audio neu erzeugt.")
        st.rerun()

    if _has_source_docs:
        with ec2:
            with st.popover("🔄 Stattdessen komplett neu von der KI schreiben lassen",
                            use_container_width=True):
                st.caption("Verwirft den aktuellen (auch den von dir bearbeiteten) Text und "
                          "lässt die KI aus den ursprünglichen Dokumenten ein komplett neues "
                          "Skript schreiben - vertont wird NICHT automatisch, das neue Skript "
                          "landet zur Kontrolle erst im Textfeld oben.")
                _regen_model = _model_picker(f"audio_regen_model_{_active_id}")
                if st.button("Neues Skript schreiben lassen", key=f"audio_regen_{_active_id}"):
                    _rscript_bar = st.progress(0.0)
                    _rscript_cap = st.empty()
                    try:
                        _script, _regen_warning = audio_overview.generate_overview_script(
                            _active["doc_ids"], _active["subject"], model=_regen_model,
                            on_progress=_progress_tracker(_rscript_bar, _rscript_cap, "Skript"))
                    except audio_overview.AudioOverviewError as exc:
                        st.error(str(exc))
                        st.stop()
                    manifest.update_audio_overview(
                        _active_id, script_text=_script,
                        model=_regen_model or settings.author_model())
                    st.session_state["_audio_regen_pending_script"] = _script
                    if _regen_warning:
                        st.session_state["_audio_gen_warning"] = _regen_warning
                    else:
                        st.session_state["_audio_gen_notice"] = (
                            "📝 Neues Skript erzeugt - oben prüfen/bearbeiten und dann "
                            "„💾 Speichern & nur Audio neu erzeugen“ klicken, um es auch zu hören.")
                    st.rerun()

    # key= haelt den Auf/Zu-Zustand fest - ohne key faellt der Expander sonst schon
    # beim Tippen im Textfeld (loest beim Verlassen des Felds einen Rerun aus) wieder
    # zu, bevor "Titel speichern" ueberhaupt geklickt werden kann.
    with st.expander("✏️ Umbenennen", key=f"audio_rename_expander_{_active_id}"):
        _new_title_val = st.text_input("Titel", value=_active["title"],
                                       key=f"audio_rename_{_active_id}")
        if st.button("💾 Titel speichern", key=f"audio_rename_save_{_active_id}"):
            _clean_title = _new_title_val.strip()
            if _clean_title:
                manifest.update_audio_overview(_active_id, title=_clean_title)
                st.success("Titel gespeichert.")
                st.rerun()
            else:
                st.warning("Titel darf nicht leer sein.")

    with st.expander("🗑️ Löschen"):
        if st.button("Audio-Overview löschen", key=f"audio_delete_{_active_id}"):
            manifest.delete_audio_overview(_active_id)
            st.session_state["_audio_pending_choice"] = None
            st.success("Gelöscht.")
            st.rerun()
