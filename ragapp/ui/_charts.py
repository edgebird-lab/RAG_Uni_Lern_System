"""
RAG-Lernsystem: handgezeichnet wirkende SVG-Diagramme ("Manga-Chart"-Optik)
============================================================================
Ersetzt Streamlits generische ``st.line_chart``/``st.bar_chart``/``st.area_chart``
(nur auf der Fortschritt-Seite) durch reine SVG-Bausteine im Stil der
Referenz-Screenshots (weiche Kurve, runde Punktmarker, sanfter Verlaufs-
Fuellbereich, dezente gestrichelte Gitterlinien) - passend zur "Cozy Kawaii"-
Optik des restlichen Redesigns (``ragapp/ui/_style.py``).

Bewusst KEIN Chart-Framework (Plotly/Altair/Vega) - das wuerde eine neue,
schwere Abhaengigkeit samt eigenem (nicht auf unsere Palette abgestimmtem)
Standard-Look einziehen. Reines SVG, wie schon bei den Doodles und dem
Mindmap-Renderer (``ragapp/mindmap_render.py``) etabliert - kein Bild-Asset,
kein Netz, skaliert verlustfrei, faerbt sich mit der Seiten-Akzentfarbe.
"""
from __future__ import annotations

import html


def _smooth_path(points: list[tuple[float, float]]) -> str:
    """Catmull-Rom-Spline durch alle Punkte, als kubische Bezier-Segmente
    ausgedrückt (SVG kennt keine Catmull-Rom-Kurven direkt) - ergibt die
    weiche, "handgezeichnete" Linie der Referenz-Charts statt scharfer
    Knicke zwischen den Messwerten."""
    if len(points) < 2:
        return ""
    pts = [points[0]] + points + [points[-1]]
    d = f"M {pts[1][0]:.2f} {pts[1][1]:.2f} "
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        c1x, c1y = p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6
        c2x, c2y = p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6
        d += f"C {c1x:.2f} {c1y:.2f}, {c2x:.2f} {c2y:.2f}, {p2[0]:.2f} {p2[1]:.2f} "
    return d


def _pick_label_indices(n: int, max_labels: int = 8) -> set:
    """Waehlt bis zu ``max_labels`` Indizes mit MINDESTABSTAND ``stride`` -
    verhindert ueberlappende Achsenbeschriftung bei vielen Punkten (z. B. 30
    Tage). Ein rundungsbasiertes gleichmaessiges Verteilen (i * (n-1)/(max-1))
    kann bei "krummen" n/max_labels-Verhaeltnissen zwei benachbarte Indizes
    liefern (z. B. bei 14 Tagen: ...,11,13 UND 13 nochmal ueber den Endpunkt) -
    hier stattdessen eine feste Schrittweite, der Endpunkt wird nur angehaengt
    (nie zusaetzlich zu einem bereits fast dort liegenden Index)."""
    if n <= max_labels:
        return set(range(n))
    # Mindestschrittweite 2: bei "krummen" n knapp ueber max_labels (z. B. 9/8)
    # waere round(n/max_labels) sonst 1 - wuerde JEDEN Index zeigen und damit
    # die (meist mehrstelligen Datums-)Labels doch wieder kollidieren lassen.
    stride = max(2, round(n / max_labels))
    idx = list(range(0, n, stride))
    if n - 1 - idx[-1] < stride:
        idx[-1] = n - 1
    else:
        idx.append(n - 1)
    return set(idx)


_UID = 0


def _uid(prefix: str) -> str:
    global _UID
    _UID += 1
    return f"{prefix}{_UID}"


def line_chart(labels: list, values: list, *, color: str = "#61C9A8",
                height: int = 220, area: bool = True, value_suffix: str = "") -> str:
    """Weiche Linie + runde Punktmarker + sanfter Verlaufs-Fuellbereich,
    responsiv (``width:100%`` via viewBox). ``area=False`` liefert eine reine
    Linie ohne Fuellung (fuer Vergleichs-/Sekundaerkurven).

    ``None``-Werte (z. B. Tage ohne Wiederholungen -> keine Trefferquote
    messbar) werden herausgefiltert statt als 0 geplottet - das wuerde einen
    ehrlichen "keine Daten"-Tag faelschlich wie einen Totalausfall aussehen
    lassen."""
    pairs = [(lb, v) for lb, v in zip(labels, values) if v is not None]
    labels = [lb for lb, _ in pairs]
    values = [v for _, v in pairs]
    n = len(values)
    if n == 0:
        return f'<div style="height:{height}px;display:flex;align-items:center;justify-content:center;opacity:.5;font-size:.85rem;">Noch keine Daten</div>'

    vw, pad_l, pad_r, pad_t, pad_b = 640, 8, 8, 14, 26
    plot_w, plot_h = vw - pad_l - pad_r, height - pad_t - pad_b
    vmax = max(values) or 1.0
    vmin = min(0.0, min(values))
    span = (vmax - vmin) or 1.0

    def _xy(i: int, v: float) -> tuple[float, float]:
        x = pad_l + (plot_w * i / (n - 1) if n > 1 else plot_w / 2)
        y = pad_t + plot_h * (1 - (v - vmin) / span)
        return (x, y)

    pts = [_xy(i, v) for i, v in enumerate(values)]
    path_d = _smooth_path(pts)
    uid = _uid("ragchart")

    fill_html = ""
    if area:
        base_y = pad_t + plot_h
        fill_d = path_d + f"L {pts[-1][0]:.2f} {base_y:.2f} L {pts[0][0]:.2f} {base_y:.2f} Z"
        fill_html = (f'<defs><linearGradient id="{uid}" x1="0" y1="0" x2="0" y2="1">'
                     f'<stop offset="0%" stop-color="{color}" stop-opacity=".38"/>'
                     f'<stop offset="100%" stop-color="{color}" stop-opacity="0"/>'
                     f'</linearGradient></defs>'
                     f'<path d="{fill_d}" fill="url(#{uid})" stroke="none"/>')

    gridlines = "".join(
        f'<line x1="{pad_l}" y1="{pad_t + plot_h * f:.1f}" x2="{vw - pad_r}" y2="{pad_t + plot_h * f:.1f}" '
        f'stroke="currentColor" stroke-opacity=".08" stroke-dasharray="3,4"/>'
        for f in (0.0, 0.5, 1.0)
    )

    label_idx = _pick_label_indices(n)
    labels_html = "".join(
        f'<text x="{pts[i][0]:.1f}" y="{height - 6}" text-anchor="middle" '
        f'font-size="11" fill="currentColor" opacity=".55">{html.escape(str(labels[i]))}</text>'
        for i in sorted(label_idx)
    )
    dots_html = "".join(
        f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4.5" fill="{color}" stroke="white" stroke-width="2">'
        f'<title>{html.escape(str(labels[i]))}: {values[i]:g}{value_suffix}</title></circle>'
        for i, (x, y) in enumerate(pts)
    )

    return f"""
<div style="width:100%;color:inherit;">
<svg viewBox="0 0 {vw} {height}" width="100%" height="{height}" preserveAspectRatio="none"
     style="display:block;overflow:visible;">
  {gridlines}
  {fill_html}
  <path d="{path_d}" fill="none" stroke="{color}" stroke-width="3.2"
        stroke-linecap="round" stroke-linejoin="round"/>
  {dots_html}
  {labels_html}
</svg>
</div>
"""


def bar_chart(labels: list, values: list, *, color: str = "#61C9A8", height: int = 220,
              horizontal: bool = False, value_suffix: str = "") -> str:
    """Abgerundete Balken in Pastell - vertikal (Standard) oder horizontal
    (fuer Kategorien-Vergleiche wie "Mastery je Fach"). Responsiv. ``None``-
    Werte werden als 0 gezeichnet (ein Balken der Hoehe 0 ist fuer Zaehlwerte
    wie "Wiederholungen"/"Fällig" ehrlich - anders als bei line_chart(), wo ein
    fehlender Prozentwert etwas anderes bedeutet als 0 %)."""
    values = [0 if v is None else v for v in values]
    n = len(values)
    if n == 0:
        return f'<div style="height:{height}px;display:flex;align-items:center;justify-content:center;opacity:.5;font-size:.85rem;">Noch keine Daten</div>'

    vmax = max(values, default=0) or 1.0
    uid = _uid("ragbar")

    if horizontal:
        vw = 640
        pad_l = max(70, min(170, max((len(str(lb)) for lb in labels), default=8) * 7))
        pad_r, row_h_gap = 46, 10
        row_h = max(22, (height - 10) / n - row_h_gap)
        bars = []
        for i, (lb, v) in enumerate(zip(labels, values)):
            y = 6 + i * (row_h + row_h_gap)
            w = max(2.0, (vw - pad_l - pad_r) * (v or 0) / vmax)
            bars.append(
                f'<text x="{pad_l - 10}" y="{y + row_h / 2 + 4:.1f}" text-anchor="end" '
                f'font-size="12" fill="currentColor" opacity=".8">{html.escape(str(lb))}</text>'
                f'<rect x="{pad_l}" y="{y:.1f}" width="{w:.1f}" height="{row_h:.1f}" rx="{min(9, row_h/2):.1f}" '
                f'fill="{color}"/>'
                f'<text x="{pad_l + w + 8:.1f}" y="{y + row_h / 2 + 4:.1f}" font-size="12" '
                f'fill="currentColor" opacity=".7">{v:g}{value_suffix}</text>'
            )
        total_h = 6 + n * (row_h + row_h_gap)
        return f"""
<div style="width:100%;color:inherit;">
<svg viewBox="0 0 {vw} {total_h:.0f}" width="100%" height="{total_h:.0f}" preserveAspectRatio="none"
     style="display:block;overflow:visible;">{''.join(bars)}</svg>
</div>
"""

    vw, pad_l, pad_r, pad_t, pad_b = 640, 8, 8, 10, 26
    plot_w, plot_h = vw - pad_l - pad_r, height - pad_t - pad_b
    gap = plot_w / n * 0.28
    bw = plot_w / n - gap
    label_idx = _pick_label_indices(n)
    bars = []
    for i, v in enumerate(values):
        bh = max(2.0, plot_h * (v or 0) / vmax)
        x = pad_l + i * (bw + gap) + gap / 2
        y = pad_t + plot_h - bh
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" '
            f'rx="{min(6, bw/2):.1f}" fill="{color}">'
            f'<title>{html.escape(str(labels[i]))}: {v:g}{value_suffix}</title></rect>'
        )
        if i in label_idx:
            bars.append(
                f'<text x="{x + bw/2:.1f}" y="{height - 6}" text-anchor="middle" font-size="11" '
                f'fill="currentColor" opacity=".55">{html.escape(str(labels[i]))}</text>'
            )
    return f"""
<div style="width:100%;color:inherit;" id="{uid}">
<svg viewBox="0 0 {vw} {height}" width="100%" height="{height}" preserveAspectRatio="none"
     style="display:block;overflow:visible;">{''.join(bars)}</svg>
</div>
"""
