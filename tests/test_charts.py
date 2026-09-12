"""Tests fuer ragapp.ui._charts (reine SVG-Bausteine, keine Streamlit-Abhaengigkeit)."""
from __future__ import annotations

from ragapp.ui._charts import line_chart, bar_chart, sparkline, progress_bar, _pick_label_indices


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


# --------------------------------------------------------------------------- #
# sparkline - kompakte Balken OHNE Achsen/Beschriftung, fuers Einbetten unter
# einer st.metric()-Kennzahl (z. B. "Streak" auf der Fortschritt-Seite)
# --------------------------------------------------------------------------- #

def test_sparkline_rendert_einen_balken_je_wert():
    svg = sparkline([1, 3, 0, 2, 5, 0, 1])
    assert svg.count("<rect") == 7


def test_sparkline_hat_keine_achsen_oder_beschriftungen():
    svg = sparkline([1, 2, 3])
    assert "<text" not in svg
    assert "gridline" not in svg.lower()


def test_sparkline_none_werte_werden_als_null_gezeichnet_nicht_uebersprungen():
    svg = sparkline([2, None, 4])
    assert svg.count("<rect") == 3


def test_sparkline_leere_liste_gibt_leeren_string_ohne_absturz():
    assert sparkline([]) == ""


def test_sparkline_alle_werte_null_stuerzt_nicht_ab_durch_division():
    # vmax waere 0 - darf nicht durch 0 teilen
    svg = sparkline([0, 0, 0])
    assert svg.count("<rect") == 3


# --------------------------------------------------------------------------- #
# progress_bar() - schmaler Balken unter Prozent-Kennzahlen (Sitzt-Anteil,
# Klausur-Bereitschaft), damit die nackte Zahl eine sofort erfassbare
# visuelle Entsprechung bekommt (gleiches Prinzip wie sparkline() beim Streak).
# --------------------------------------------------------------------------- #
def test_progress_bar_rendert_track_und_fuellung():
    svg = progress_bar(50.0)
    assert svg.count("<rect") == 2


def test_progress_bar_null_prozent_zeigt_mindestbreite_statt_punkt():
    # Ohne Mindestbreite wuerde 0% wie ein kaputter Ein-Pixel-Fehler aussehen.
    svg = progress_bar(0.0)
    assert 'width="8.0"' in svg  # Mindestbreite = Balkenhoehe (Standard 8)


def test_progress_bar_hundert_prozent_fuellt_die_volle_breite():
    svg = progress_bar(100.0)
    assert 'width="200.0"' in svg


def test_progress_bar_kappt_werte_ueber_100():
    svg_100 = progress_bar(100.0)
    svg_ueber = progress_bar(150.0)
    assert svg_100 == svg_ueber


def test_progress_bar_kappt_negative_werte_auf_null():
    svg_null = progress_bar(0.0)
    svg_negativ = progress_bar(-20.0)
    assert svg_null == svg_negativ


def test_progress_bar_nutzt_uebergebene_farbe():
    svg = progress_bar(50.0, color="#FF0000")
    assert "#FF0000" in svg
