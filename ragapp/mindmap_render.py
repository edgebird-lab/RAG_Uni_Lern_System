"""
Mindmap-Rendering: reine Geometrie (``layout_tree``) + SVG-String-Erzeugung
(``render_svg``) - BEWUSST ohne Streamlit-Import, unabhängig testbar.

Kein System-Graphviz verfügbar/gewünscht (weder das ``dot``-Binary noch das
Python-Paket ``graphviz`` sind installiert) - eine neue System-Abhängigkeit
widerspräche der im Projekt etablierten Policy "kein System-X nötig" (z. B.
``easyocr`` statt System-Tesseract). Stattdessen ein selbstgerechnetes
horizontales Schichten-Layout (links->rechts, wie ``dot -Grankdir=LR``, aber
selbst gerechnet) - bei Tiefe <=3 und wenigen Dutzend Knoten (siehe
``MINDMAP_MAX_NODES``) völlig ausreichend, ein vollständiger Reingold-Tilford-
Algorithmus wäre hier Overkill.
"""
from __future__ import annotations

import html
from typing import Optional

from ragapp.ui._colors import text_color_for

LEVEL_DX = 260
ROW_DY = 50
MARGIN = 30
NODE_HEIGHT = 34
NODE_PAD_X = 14
CHAR_PX = 7.5
NODE_MIN_WIDTH = 70
NODE_MAX_WIDTH = 220
_MAX_TITLE_CHARS = 34


def _truncate_title(title: str) -> str:
    t = (title or "").strip()
    return t if len(t) <= _MAX_TITLE_CHARS else t[:_MAX_TITLE_CHARS - 1].rstrip() + "…"


def _node_width(title: str) -> float:
    return min(NODE_MAX_WIDTH, max(NODE_MIN_WIDTH, len(title) * CHAR_PX + 2 * NODE_PAD_X))


def layout_tree(graph: dict) -> dict:
    """Reine Geometrie-Berechnung (keine Farben, kein SVG): jeder Knoten bekommt
    ``x``/``y``/``w``/``h``/``title``/``depth``. Verfahren: Post-order-DFS -
    Blätter bekommen einen fortlaufenden ``y_index``, jeder innere Knoten den
    Mittelwert der ``y_index`` seiner Kinder (klassisches, einfaches
    Baum-Layout). ``x`` ergibt sich rein aus der Tiefe (``depth * LEVEL_DX``).

    Erwartet einen bereits von ``mindmap._repair_mindmap`` bereinigten Graphen
    (eindeutige IDs, gültige/azyklische ``parent``-Referenzen) - baut sonst
    keinen konsistenten Baum. Die synthetische Wurzel hat die ID ``None``.

    Rückgabe: ``{"nodes": {id: {"x","y","w","h","title","depth"}}, "width",
    "height"}``."""
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    children: dict[Optional[str], list[str]] = {}
    for n in graph.get("nodes", []):
        children.setdefault(n.get("parent"), []).append(n["id"])

    depth: dict[Optional[str], int] = {None: 0}
    order: list[Optional[str]] = [None]
    i = 0
    while i < len(order):
        cur = order[i]
        i += 1
        for cid in children.get(cur, []):
            depth[cid] = depth[cur] + 1
            order.append(cid)

    y_index: dict[Optional[str], float] = {}
    _next_leaf_y = [0]

    def _visit(node_id: Optional[str]) -> float:
        kids = children.get(node_id, [])
        if not kids:
            y = float(_next_leaf_y[0])
            _next_leaf_y[0] += 1
        else:
            y = sum(_visit(k) for k in kids) / len(kids)
        y_index[node_id] = y
        return y

    _visit(None)

    layout_nodes: dict[Optional[str], dict] = {}
    for node_id, d in depth.items():
        raw_title = graph.get("root", "Übersicht") if node_id is None else nodes[node_id]["title"]
        title = _truncate_title(raw_title)
        layout_nodes[node_id] = {
            "x": MARGIN + d * LEVEL_DX, "y": MARGIN + y_index[node_id] * ROW_DY,
            "w": _node_width(title), "h": NODE_HEIGHT, "title": title, "depth": d,
        }

    max_y = max((nd["y"] for nd in layout_nodes.values()), default=0.0)
    max_x = max((nd["x"] + nd["w"] for nd in layout_nodes.values()), default=0.0)
    return {"nodes": layout_nodes, "width": max_x + MARGIN, "height": max_y + NODE_HEIGHT + MARGIN}


def _lighten(hex_color: str, amount: float) -> str:
    h = (hex_color or "").lstrip("#")
    if len(h) != 6:
        return hex_color
    try:
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return hex_color
    r = int(r + (255 - r) * amount)
    g = int(g + (255 - g) * amount)
    b = int(b + (255 - b) * amount)
    return f"#{r:02x}{g:02x}{b:02x}"


def _depth_color(base_color: str, depth: int) -> str:
    if depth <= 0:
        return "#64748b"   # neutrale Wurzel-Farbe, kein Fach-Bezug
    return _lighten(base_color, min(0.65, (depth - 1) * 0.28))


def _edge_path(x1: float, y1: float, x2: float, y2: float) -> str:
    mx = (x1 + x2) / 2
    return f"M {x1:.1f} {y1:.1f} C {mx:.1f} {y1:.1f}, {mx:.1f} {y2:.1f}, {x2:.1f} {y2:.1f}"


def render_svg(graph: dict, layout: dict, *, base_color: str = "#4A45C4") -> str:
    """Baut das Mindmap-SVG als reinen String (in Streamlit via
    ``st.markdown(svg, unsafe_allow_html=True)`` eingebettet). Knoten als
    abgerundete Rechtecke (Farbe nach Tiefe abgestuft), Eltern-Kind-Kanten als
    kubische Bézier-Kurven (zuerst gezeichnet, liegen also unter den Knoten),
    Querverbindungen gestrichelt mit optionalem Label."""
    nodes_by_id = {n["id"]: n for n in graph.get("nodes", [])}
    parent_of = {nid: n.get("parent") for nid, n in nodes_by_id.items()}
    lnodes = layout["nodes"]
    width, height = layout["width"], layout["height"]

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
            f'width="{width:.0f}" height="{height:.0f}" font-family="sans-serif">']

    for nid, parent_id in parent_of.items():
        child_l, parent_l = lnodes[nid], lnodes[parent_id]
        x1, y1 = parent_l["x"] + parent_l["w"], parent_l["y"] + parent_l["h"] / 2
        x2, y2 = child_l["x"], child_l["y"] + child_l["h"] / 2
        parts.append(f'<path d="{_edge_path(x1, y1, x2, y2)}" fill="none" '
                    f'stroke="#94a3b8" stroke-width="1.5" />')

    for lk in graph.get("links", []):
        a, b = lnodes.get(lk.get("from")), lnodes.get(lk.get("to"))
        if not a or not b:
            continue
        x1, y1 = a["x"] + a["w"] / 2, a["y"] + a["h"]
        x2, y2 = b["x"] + b["w"] / 2, b["y"] + b["h"]
        parts.append(f'<path d="{_edge_path(x1, y1, x2, y2)}" fill="none" '
                    f'stroke="#94a3b8" stroke-width="1.2" stroke-dasharray="4,3" />')
        if lk.get("label"):
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            parts.append(f'<text x="{mx:.1f}" y="{my:.1f}" font-size="10" '
                        f'fill="#64748b">{html.escape(lk["label"])}</text>')

    for nid, l in sorted(lnodes.items(), key=lambda kv: kv[1]["depth"]):
        bg = _depth_color(base_color, l["depth"])
        fg = text_color_for(bg)
        cx, cy = l["x"] + l["w"] / 2, l["y"] + l["h"] / 2
        parts.append(
            f'<rect x="{l["x"]:.1f}" y="{l["y"]:.1f}" width="{l["w"]:.1f}" '
            f'height="{l["h"]:.1f}" rx="8" fill="{bg}" '
            f'stroke="{"#334155" if l["depth"] == 0 else "none"}" />')
        parts.append(
            f'<text x="{cx:.1f}" y="{cy:.1f}" text-anchor="middle" '
            f'dominant-baseline="middle" font-size="12.5" fill="{fg}">'
            f'{html.escape(l["title"])}</text>')

    parts.append("</svg>")
    return "".join(parts)
