"""Gemeinsame Aussprache-Hinweise fuer Audio-Overview und Vortrag."""
from __future__ import annotations

import html
import re

import streamlit as st

from ragapp import manifest, audio_overview


def render_pronunciation_hints(text: str, *, key_prefix: str,
                               apply_label: str = "Audio-Overviews und Vorträge") -> None:
    """LLM + Regex-Hinweise fuer falsch vorzulesende Woerter; Speichern in
    ``manifest.pronunciation_fixes`` (wirkt bei naechster Vertonung)."""
    text = (text or "").strip()
    if not text:
        return

    cache_key = f"_pron_suggest_{key_prefix}_{hash(text)}"
    if cache_key not in st.session_state:
        with st.spinner("Text wird auf falsch vorzulesende Wörter geprüft …"):
            st.session_state[cache_key] = audio_overview.suggest_pronunciations(text)
    suggestions = st.session_state[cache_key]

    candidates = audio_overview.find_pronunciation_candidates(text)
    words = list(suggestions.keys()) + [w for w in candidates if w not in suggestions]
    if not words:
        return

    escaped = html.escape(text)
    pattern = re.compile(
        r"\b(?:" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
        + r")\b")
    highlighted = pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", escaped)
    highlighted = highlighted.replace("\n", "<br>")

    with st.expander(
        f"🔍 {len(words)} möglicherweise falsch ausgesprochene(s) "
        "Wort/Wörter - Aussprache prüfen",
        key=f"pron_expander_{key_prefix}",
    ):
        st.caption(
            "Vorschläge vom KI-Modell (z. B. „nmap“ → „en map“) – kurz prüfen und "
            "übernehmen. Übernommene Korrekturen gelten dauerhaft für alle "
            f"{apply_label}."
        )
        st.markdown(f'<div style="line-height:1.6">{highlighted}</div>',
                    unsafe_allow_html=True)
        st.write("")

        rows = []
        for word in words:
            c1, c2, c3 = st.columns([2, 3, 1])
            c1.markdown(f"**{word}**")
            sugg = suggestions.get(word, "")
            val = c2.text_input(
                f"Aussprache für {word}", value=sugg,
                key=f"pron_val_{key_prefix}_{word}", label_visibility="collapsed",
                placeholder="normale Aussprache (kein Fix nötig)")
            take = c3.checkbox(
                "✓ übernehmen", value=bool(sugg),
                key=f"pron_take_{key_prefix}_{word}",
                label_visibility="collapsed",
                help="Übernehmen & dauerhaft merken")
            rows.append((word, val.strip(), take))

        if st.button("💾 Ausgewählte Korrekturen übernehmen & merken",
                     key=f"pron_apply_{key_prefix}"):
            n = 0
            for word, val, take in rows:
                if take and val:
                    manifest.upsert_pronunciation_fix(word, val)
                    n += 1
            if n:
                st.session_state.pop(cache_key, None)
                st.success(
                    f"{n} Aussprache-Korrektur(en) gespeichert – gelten ab sofort "
                    f"automatisch für {apply_label}."
                )
                st.rerun()
            else:
                st.info("Keine Korrektur ausgewählt.")
