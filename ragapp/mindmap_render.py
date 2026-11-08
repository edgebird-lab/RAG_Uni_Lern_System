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
TEXT_INSET = 8          # Mindestabstand des Titels zum Knotenrand
LABEL_DY = 12           # Hoehe einer Link-Beschriftung (font-size 10)
LINK_SAG = 20           # so weit haengt eine Querverbindung unter die Knoten
LINK_BULGE = 34         # so weit laeuft sie in derselben Spalte rechts aussen
LABEL_CHAR_PX = 5.6     # geschaetzte Zeichenbreite bei font-size 10


def _truncate_title(title: str) -> str:
    t = (title or "").strip()
    return t if len(t) <= _MAX_TITLE_CHARS else t[:_MAX_TITLE_CHARS - 1].rstrip() + "…"


def _node_width(title: str) -> float:
    return min(NODE_MAX_WIDTH, max(NODE_MIN_WIDTH, len(title) * CHAR_PX + 2 * NODE_PAD_X))


def layout_tree(graph: dict, *, labels: Optional[dict] = None) -> dict:
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
        if node_id is None:
            raw_title = graph.get("root", "Übersicht")
        else:
            raw_title = nodes[node_id]["title"]
            if labels:
                raw_title = labels.get(node_id) or labels.get(str(node_id)) or raw_title
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


def clean_links(graph: dict) -> list[dict]:
    """Die Querverbindungen, die wirklich gezeichnet werden.

    Verworfen werden Links zu unbekannten Knoten, Selbst-Links, Links, die nur
    eine Eltern-Kind-Kante wiederholen (die zeichnet der Baum schon), und jede
    weitere Verbindung desselben Knotenpaars, egal in welcher Richtung. Sonst
    liegen gestrichelte Kurven und Beschriftungen exakt uebereinander: kleine
    Modelle liefern gern fuenf Links zwischen Thema und Unterthema."""
    parent_of = {n.get("id"): n.get("parent")
                 for n in graph.get("nodes") or [] if isinstance(n, dict)}
    out: list[dict] = []
    seen: set = set()
    for lk in graph.get("links") or []:
        if not isinstance(lk, dict):
            continue
        f, t = lk.get("from"), lk.get("to")
        if f is None or t is None or f == t or f not in parent_of or t not in parent_of:
            continue
        if parent_of.get(f) == t or parent_of.get(t) == f:
            continue
        pair = frozenset((f, t))
        if pair in seen:
            continue
        seen.add(pair)
        out.append(lk)
    return out


def _link_path(a: dict, b: dict) -> tuple:
    """Querverbindung zwischen zwei Knoten-Boxen als gestrichelter Bogen. Liegen
    beide in derselben Spalte, laeuft der Bogen rechts aussen herum (sonst
    ginge er mitten durch die Knoten dazwischen), ansonsten haengt er von
    Unterkante zu Unterkante nach unten durch. Gibt den SVG-Pfad und die vier
    Bezier-Punkte zurueck."""
    if a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"]:
        xa, xb = a["x"] + a["w"], b["x"] + b["w"]
        ya, yb = a["y"] + a["h"] / 2, b["y"] + b["h"] / 2
        bulge = max(xa, xb) + LINK_BULGE
        pts = ((xa, ya), (bulge, ya), (bulge, yb), (xb, yb))
    else:
        xa, xb = a["x"] + a["w"] / 2, b["x"] + b["w"] / 2
        ya, yb = a["y"] + a["h"], b["y"] + b["h"]
        pts = ((xa, ya), (xa, ya + LINK_SAG), (xb, yb + LINK_SAG), (xb, yb))
    (ax, ay), (bx, by), (cx, cy), (dx, dy) = pts
    return (f"M {ax:.1f} {ay:.1f} C {bx:.1f} {by:.1f}, {cx:.1f} {cy:.1f}, "
            f"{dx:.1f} {dy:.1f}"), pts


def _bezier_point(pts: tuple, t: float) -> tuple:
    (ax, ay), (bx, by), (cx, cy), (dx, dy) = pts
    u = 1 - t
    return (u ** 3 * ax + 3 * u * u * t * bx + 3 * u * t * t * cx + t ** 3 * dx,
            u ** 3 * ay + 3 * u * u * t * by + 3 * u * t * t * cy + t ** 3 * dy)


def _overlaps(box: tuple, other: tuple, pad: float = 2.0) -> bool:
    x0, y0, x1, y1 = box
    a0, b0, a1, b1 = other
    return x0 < a1 + pad and a0 < x1 + pad and y0 < b1 + pad and b0 < y1 + pad


def _place_label(pts: tuple, w: float, node_boxes: list, label_boxes: list) -> tuple:
    """Sucht fuer eine Link-Beschriftung (Breite ``w``) einen Platz auf oder
    nahe am Bogen, der weder einen Knoten noch eine schon gesetzte Beschriftung
    ueberdeckt (Boxen als (x0, y0, x1, y1)). Die gewaehlte Box wird an
    ``label_boxes`` angehaengt. Gibt den Mittelpunkt (x, y) zurueck."""
    h = LABEL_DY

    def _box(px: float, py: float) -> tuple:
        return (px - w / 2, py - h / 2, px + w / 2, py + h / 2)

    blocked = node_boxes + label_boxes
    for t in (0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8, 0.12, 0.88):
        px, py = _bezier_point(pts, t)
        for dx in (0.0, w / 2 + 4, -(w / 2 + 4)):
            for dy in (0.0, -4.0, 4.0, -8.0, 8.0, -12.0, 12.0, -18.0, 18.0, -24.0, 24.0):
                box = _box(px + dx, py + dy)
                if not any(_overlaps(box, bb) for bb in blocked):
                    label_boxes.append(box)
                    return px + dx, py + dy
    # Kein freier Platz: in der Bogenmitte, aber nie auf einer anderen
    # Beschriftung (dann eine Zeile tiefer).
    px, py = _bezier_point(pts, 0.5)
    for _ in range(20):
        if not any(_overlaps(_box(px, py), bb) for bb in label_boxes):
            break
        py += h
    label_boxes.append(_box(px, py))
    return px, py


def _fit_text_attrs(box_w: float) -> str:
    """Verfuegbare Textbreite im Knoten als ``data-fit-w``. Die Knotenbreite ist
    bei ``NODE_MAX_WIDTH`` gedeckelt und die Schrift je nach System breiter;
    das Skript der Mindmap-Seite misst deshalb im Browser nach und setzt nur
    zu lange Titel per ``textLength`` schmaler (gestreckt wird nie)."""
    return f' data-fit-w="{box_w - 2 * TEXT_INSET:.1f}"'


def render_svg(graph: dict, layout: dict, *, base_color: str = "#4A45C4",
               selected_ids: Optional[set] = None,
               labels: Optional[dict] = None) -> str:
    """Baut das Mindmap-SVG als reinen String (in Streamlit via
    ``st.markdown``/Host-Div eingebettet). ``selected_ids`` hebt gewaehlte
    Knoten hervor; ``labels`` ueberschreibt Anzeigetitel (z. B. humanisierte
    'Seite N'-Knoten). Jeder echte Knoten liegt in ``<g data-mm-id>`` damit
    die Seite Klicks an Streamlit-Buttons durchreichen kann."""
    selected_ids = selected_ids or set()
    labels = labels or {}
    nodes_by_id = {n["id"]: n for n in graph.get("nodes", [])}
    parent_of = {nid: n.get("parent") for nid, n in nodes_by_id.items()}
    lnodes = layout["nodes"]
    width, height = layout["width"], layout["height"]

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
            f'width="{width:.0f}" height="{height:.0f}" font-family="sans-serif" '
            f'role="img" aria-label="Mindmap">']

    for nid, parent_id in parent_of.items():
        child_l, parent_l = lnodes[nid], lnodes[parent_id]
        x1, y1 = parent_l["x"] + parent_l["w"], parent_l["y"] + parent_l["h"] / 2
        x2, y2 = child_l["x"], child_l["y"] + child_l["h"] / 2
        parts.append(f'<path d="{_edge_path(x1, y1, x2, y2)}" fill="none" '
                    f'stroke="#94a3b8" stroke-width="1.5" />')

    label_parts: list[str] = []
    node_boxes = [(l["x"], l["y"], l["x"] + l["w"], l["y"] + l["h"]) for l in lnodes.values()]
    label_boxes: list = []
    for lk in clean_links(graph):
        a, b = lnodes.get(lk.get("from")), lnodes.get(lk.get("to"))
        if not a or not b:
            continue
        d, pts = _link_path(a, b)
        parts.append(f'<path d="{d}" fill="none" stroke="#94a3b8" '
                    f'stroke-width="1.2" stroke-dasharray="4,3" />')
        label = str(lk.get("label") or "").strip()
        if label:
            mx, my = _place_label(pts, len(label) * LABEL_CHAR_PX, node_boxes, label_boxes)
            # Beschriftungen erst NACH den Knoten zeichnen und mit hellem Rand
            # (Halo), damit Kanten sie nicht durchstreichen.
            label_parts.append(
                f'<text x="{mx:.1f}" y="{my:.1f}" text-anchor="middle" '
                f'dominant-baseline="middle" font-size="10" '
                f'fill="#64748b" stroke="#ffffff" stroke-width="3" '
                f'stroke-linejoin="round" paint-order="stroke">{html.escape(label)}</text>')

    for nid, l in sorted(lnodes.items(), key=lambda kv: kv[1]["depth"]):
        bg = _depth_color(base_color, l["depth"])
        fg = text_color_for(bg)
        title = _truncate_title(
            labels.get(nid) or labels.get(str(nid)) or l["title"])
        cx, cy = l["x"] + l["w"] / 2, l["y"] + l["h"] / 2
        selected = nid is not None and str(nid) in {str(s) for s in selected_ids}
        stroke = "#f59e0b" if selected else ("#334155" if l["depth"] == 0 else "none")
        sw = "3" if selected else ("1" if l["depth"] == 0 else "0")
        gid = "" if nid is None else html.escape(str(nid), quote=True)
        if nid is not None:
            parts.append(f'<g data-mm-id="{gid}" style="cursor:pointer">')
        parts.append(
            f'<rect x="{l["x"]:.1f}" y="{l["y"]:.1f}" width="{l["w"]:.1f}" '
            f'height="{l["h"]:.1f}" rx="8" fill="{bg}" '
            f'stroke="{stroke}" stroke-width="{sw}" />')
        parts.append(
            f'<text x="{cx:.1f}" y="{cy:.1f}" text-anchor="middle" '
            f'dominant-baseline="middle" font-size="12.5" fill="{fg}"'
            f'{_fit_text_attrs(l["w"])}>'
            f'{html.escape(title)}</text>')
        if nid is not None:
            parts.append("</g>")

    parts.extend(label_parts)
    parts.append("</svg>")
    return "".join(parts)
