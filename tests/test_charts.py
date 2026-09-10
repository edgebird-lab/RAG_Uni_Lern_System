"""Tests fuer ragapp.ui._charts (reine SVG-Bausteine, keine Streamlit-Abhaengigkeit)."""
from __future__ import annotations

from ragapp.ui._charts import line_chart, bar_chart, _pick_label_indices


def test_line_chart_rendert_svg_mit_pfad_und_punkten():
    svg = line_chart(["01", "02", "03"], [10, 45, 30], color="#61C9A8")
    assert "<svg" in svg
    assert "<path" in svg
    assert svg.count("<circle") == 3


def test_line_chart_none_werte_werden_herausgefiltert_nicht_als_null_geplottet():
    # Ein Tag ohne Wiederholungen hat KEINE Trefferquote (None) - das darf nicht
    # als 0 % geplottet werden (saehe wie ein Totalausfall aus) und darf vor
    # allem nicht abstuerzen (max()/min() auf einer Liste mit None crasht).
    svg = line_chart(["01", "02", "03"], [50, None, 80], color="#61C9A8")
    assert svg.count("<circle") == 2


def test_line_chart_nur_none_werte_zeigt_leerzustand_ohne_absturz():
    svg = line_chart(["01", "02"], [None, None])
    assert "Noch keine Daten" in svg


def test_line_chart_leere_liste_zeigt_leerzustand():
    svg = line_chart([], [])
    assert "Noch keine Daten" in svg


def test_bar_chart_none_werte_werden_als_null_gezeichnet():
    # Fuer Zaehlwerte (Wiederholungen/Faellig) ist ein fehlender Tag ehrlich = 0,
    # nicht "keine Daten" - anders als bei line_chart mit Prozentwerten.
    svg = bar_chart(["01", "02"], [5, None], color="#9BA3C9")
    assert svg.count("<rect") == 2
    assert "Noch keine Daten" not in svg


def test_bar_chart_horizontal_rendert_je_kategorie_einen_balken():
    svg = bar_chart(["Mathe", "Info", "BWL"], [70, 40, 90], color="#3E9B6C", horizontal=True)
    assert svg.count("<rect") == 3
    assert "Mathe" in svg and "Info" in svg and "BWL" in svg


def test_bar_chart_leere_liste_zeigt_leerzustand():
    assert "Noch keine Daten" in bar_chart([], [])


def test_pick_label_indices_liefert_nie_zwei_benachbarte_indizes():
    # Regression: bei 14 Punkten/8 Labels lieferte die alte, rundungsbasierte
    # Verteilung u. a. die Indizes 11 UND 13 - benachbart genug, dass sich die
    # Datums-Beschriftungen im gerenderten Chart ueberlappten.
    for n in range(9, 60):
        idx = sorted(_pick_label_indices(n, max_labels=8))
        gaps = [b - a for a, b in zip(idx, idx[1:])]
        assert all(g >= 2 for g in gaps), f"n={n}: zu enge Indizes {idx}"


def test_pick_label_indices_enthaelt_immer_den_letzten_index():
    for n in range(9, 40):
        assert (n - 1) in _pick_label_indices(n, max_labels=8)
