"""Mindmap-Layout/-Rendering (``ragapp.mindmap_render``): reine Geometrie
(``layout_tree``) und SVG-String-Erzeugung (``render_svg``).

Direkt importierbar (kein chromadb/torch/streamlit in der Abhängigkeitskette),
daher kein AST-Isolationsloader nötig.
"""
from ragapp.mindmap_render import layout_tree, render_svg, _lighten, _truncate_title


def _graph(**overrides):
    base = {
        "root": "Algorithmen",
        "nodes": [
            {"id": "n1", "title": "Sortieren", "parent": None, "indices": [0]},
            {"id": "n2", "title": "Graphen", "parent": None, "indices": [1]},
            {"id": "n3", "title": "QuickSort", "parent": "n1", "indices": [2]},
            {"id": "n4", "title": "MergeSort", "parent": "n1", "indices": [3]},
            {"id": "n5", "title": "DFS", "parent": "n2", "indices": [4]},
        ],
        "links": [{"from": "n3", "to": "n5", "label": "Vergleich"}],
    }
    base.update(overrides)
    return base


def test_layout_tree_weist_korrekte_tiefen_zu():
    layout = layout_tree(_graph())
    assert layout["nodes"][None]["depth"] == 0
    assert layout["nodes"]["n1"]["depth"] == 1
    assert layout["nodes"]["n2"]["depth"] == 1
    assert layout["nodes"]["n3"]["depth"] == 2
    assert layout["nodes"]["n5"]["depth"] == 2


def test_layout_tree_innerer_knoten_ist_mittelwert_seiner_kinder():
    layout = layout_tree(_graph())
    n1_y = layout["nodes"]["n1"]["y"]
    n3_y = layout["nodes"]["n3"]["y"]
    n4_y = layout["nodes"]["n4"]["y"]
    assert abs(n1_y - (n3_y + n4_y) / 2) < 1e-6
    root_y = layout["nodes"][None]["y"]
    n2_y = layout["nodes"]["n2"]["y"]
    assert abs(root_y - (n1_y + n2_y) / 2) < 1e-6


def test_layout_tree_x_haengt_nur_von_der_tiefe_ab():
    layout = layout_tree(_graph())
    assert layout["nodes"]["n1"]["x"] == layout["nodes"]["n2"]["x"]
    assert layout["nodes"]["n3"]["x"] == layout["nodes"]["n4"]["x"] == layout["nodes"]["n5"]["x"]
    assert layout["nodes"]["n1"]["x"] < layout["nodes"]["n3"]["x"]


def test_layout_tree_einzelner_blattknoten_unter_wurzel():
    graph = {"root": "X", "nodes": [{"id": "a", "title": "A", "parent": None, "indices": [0]}],
            "links": []}
    layout = layout_tree(graph)
    assert set(layout["nodes"].keys()) == {None, "a"}
    assert layout["width"] > 0 and layout["height"] > 0


def test_layout_tree_breite_waechst_mit_titel_laenge():
    short = layout_tree({"root": "R", "nodes": [
        {"id": "a", "title": "Kurz", "parent": None, "indices": [0]}], "links": []})
    long = layout_tree({"root": "R", "nodes": [
        {"id": "a", "title": "Ein deutlich längerer Titel hier", "parent": None,
         "indices": [0]}], "links": []})
    assert long["nodes"]["a"]["w"] > short["nodes"]["a"]["w"]


def test_truncate_title_kuerzt_lange_titel_mit_ellipse():
    long_title = "x" * 100
    out = _truncate_title(long_title)
    assert len(out) <= 34
    assert out.endswith("…")


def test_truncate_title_laesst_kurze_titel_unveraendert():
    assert _truncate_title("Kurzer Titel") == "Kurzer Titel"


def test_lighten_bewegt_farbe_richtung_weiss():
    base = "#4A45C4"
    lighter = _lighten(base, 0.5)
    assert lighter != base
    # Rot-Kanal muss naeher an 255 sein als vorher.
    r_base = int(base[1:3], 16)
    r_lighter = int(lighter[1:3], 16)
    assert r_lighter > r_base


def test_lighten_ignoriert_ungueltige_farben():
    assert _lighten("nope", 0.5) == "nope"
    assert _lighten("", 0.5) == ""


# ---------------------------------------------------------------------------
# render_svg
# ---------------------------------------------------------------------------

def test_render_svg_erzeugt_gueltiges_svg_mit_allen_titeln():
    graph = _graph()
    svg = render_svg(graph, layout_tree(graph))
    assert svg.startswith("<svg")
    assert svg.endswith("</svg>")
    for title in ("Algorithmen", "Sortieren", "Graphen", "QuickSort", "MergeSort", "DFS"):
        assert title in svg


def test_render_svg_escaped_html_in_titeln():
    graph = {"root": "R", "nodes": [
        {"id": "a", "title": "<script>alert(1)</script>", "parent": None, "indices": [0]}],
        "links": []}
    svg = render_svg(graph, layout_tree(graph))
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg


def test_render_svg_enthaelt_link_label():
    graph = _graph()
    svg = render_svg(graph, layout_tree(graph))
    assert "Vergleich" in svg


def test_render_svg_ignoriert_link_mit_unbekannter_id():
    graph = _graph(links=[{"from": "n1", "to": "nicht-vorhanden", "label": "x"}])
    # darf nicht crashen (KeyError o. Ae.), Link wird einfach uebersprungen
    svg = render_svg(graph, layout_tree(graph))
    assert svg.startswith("<svg")


def test_render_svg_ohne_knoten_ausser_wurzel():
    graph = {"root": "Leer", "nodes": [], "links": []}
    layout = layout_tree(graph)
    svg = render_svg(graph, layout)
    assert svg.startswith("<svg")
    assert "Leer" in svg
