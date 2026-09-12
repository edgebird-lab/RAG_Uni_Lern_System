"""
RAG-Lernsystem: das "Lernmaskottchen" (eigene Inline-SVG-Figur, kein Fremd-Asset)
==================================================================================
Auf Wunsch des Nutzers sollte die App mehr "Comic-/Manga-Charme" bekommen, so
wie es die als Referenz gezeigten Anime-Dashboard-Screenshots vorleben (Figma-
Case-Studies mit Charakter-Illustrationen). Fertige Anime-/Manga-Grafiken aus
dem Netz liessen sich dafuer NICHT sauber lizenzieren - die einzigen wirklich
frei nutzbaren Quellen (OpenGameArt & Co.) liefern Pixel-/RPG-Sprites in einem
komplett anderen Stil, waehrend die naheliegenden Anime-Illustrationsseiten
(Freepik/Storyset) Downloads hinter Login+manuellem Klick-Dialog verstecken,
den kein Tool hier automatisieren kann - und Clipart-Sammelseiten haben keine
verlaessliche Lizenzkette (siehe Session-Notizen). Deshalb: ein EIGENES,
simples "Mochi-Geist"-Maskottchen, das sich mit der Seiten-Akzentfarbe faerbt -
kein Copyright-Risiko, offlinefaehig wie die bestehenden Doodles.

Aufbau in benannten Gruppen (ID-Praefix ``ragm-``), damit CSS-Keyframes und das
Cursor-Tracking-Skript gezielt einzelne Koerperteile ansteuern koennen, ohne
das SVG bei jeder Variante neu zeichnen zu muessen:
``ragm-pupil-l/r`` (folgen dem Mauszeiger), ``ragm-eye-l/r`` (Blinzeln),
``ragm-arm-r`` (Winken, rotiert um einen Schulter-Pivot), ``ragm-leg-l/r``
(Hüpf-Versatz beim "run"), ``ragm-body-wrap`` (Gesamt-Bounce).

``POSES`` bildet jede Seite (siehe ``ragapp.ui._style.PAGE_THEMES``) auf eine
passende Pose ab - ein Requisit (Buch/Uhr/Gluehbirne/Stift) + eine Animations-
Variante, damit das Maskottchen nicht auf jeder Seite identisch wirkt.
"""
from __future__ import annotations

_MOUTHS = {
    "idle":  '<path d="M 98 152 Q 110 162 122 152" fill="none" stroke="{ink}" stroke-width="3.2" stroke-linecap="round"/>',
    "cheer": '<path d="M 92 150 Q 110 172 128 150 Q 110 166 92 150 Z" fill="{ink}"/>',
    "sleepy": '<path d="M 100 154 Q 110 154 120 154" fill="none" stroke="{ink}" stroke-width="3.2" stroke-linecap="round"/>',
    "focused": '<ellipse cx="110" cy="154" rx="6" ry="5" fill="{ink}"/>',
    "worried": '<path d="M 96 158 Q 110 148 124 158" fill="none" stroke="{ink}" stroke-width="3.2" stroke-linecap="round"/>',
}

# Requisiten (optional, reines Deko-Element rechts neben dem Koerper).
_PROPS = {
    None: "",
    "book": ('<g transform="translate(150,150) rotate(8)">'
             '<rect x="0" y="0" width="34" height="24" rx="3" fill="white" stroke="{ink}" stroke-width="2.5"/>'
             '<line x1="17" y1="2" x2="17" y2="22" stroke="{ink}" stroke-width="1.6"/></g>'),
    "clock": ('<g transform="translate(152,146)">'
              '<circle cx="14" cy="14" r="15" fill="white" stroke="{ink}" stroke-width="2.5"/>'
              '<line x1="14" y1="14" x2="14" y2="5" stroke="{ink}" stroke-width="2"/>'
              '<line x1="14" y1="14" x2="20" y2="16" stroke="{ink}" stroke-width="2"/></g>'),
    "bulb": ('<g transform="translate(150,138)">'
             '<circle cx="15" cy="15" r="15" fill="#FFE9A8" stroke="{ink}" stroke-width="2.5"/>'
             '<rect x="9" y="27" width="12" height="6" rx="2" fill="{ink}"/>'
             '<path d="M 10 16 Q 15 6 20 16" fill="none" stroke="{ink}" stroke-width="1.6"/></g>'),
    "pencil": ('<g transform="translate(150,142) rotate(-20)">'
               '<rect x="0" y="0" width="10" height="34" rx="3" fill="#FFD166" stroke="{ink}" stroke-width="2.2"/>'
               '<polygon points="0,34 10,34 5,44" fill="#e8a45c" stroke="{ink}" stroke-width="2.2"/></g>'),
    "star": ('<g transform="translate(150,140)">'
             '<path d="M15 0 L19 11 L31 11 L21 18 L25 30 L15 22 L5 30 L9 18 L-1 11 L11 11 Z" '
             'fill="#F6C453" stroke="{ink}" stroke-width="2"/></g>'),
    "mic": ('<g transform="translate(156,136)">'
            '<rect x="6" y="0" width="14" height="22" rx="7" fill="white" stroke="{ink}" stroke-width="2.5"/>'
            '<path d="M0 16 a13 13 0 0 0 26 0" fill="none" stroke="{ink}" stroke-width="2.5" stroke-linecap="round"/>'
            '<line x1="13" y1="29" x2="13" y2="35" stroke="{ink}" stroke-width="2.5"/>'
            '<line x1="6" y1="35" x2="20" y2="35" stroke="{ink}" stroke-width="2.5" stroke-linecap="round"/></g>'),
}

# Seite -> (Pose fuer Mund/Arme, Animationsklasse, Requisit). Nur Seiten mit
# einer bewusst ANDEREN Note als "idle" sind hier gelistet - theme_for()-artiger
# Fallback ("idle"/"float"/None) deckt alle unbekannten/neuen Seiten ab.
POSES: dict[str, tuple[str, str, "str | None"]] = {
    "home":            ("cheer", "wave", None),
    "chat":            ("idle", "float", None),
    "lernen":          ("cheer", "float", "star"),
    "mindmap":         ("focused", "float", "bulb"),
    "uebungsaufgaben": ("focused", "float", "pencil"),
    "pruefung":        ("focused", "float", "clock"),
    "lernplan":        ("idle", "float", "book"),
    "zusammenfassung": ("idle", "float", "book"),
    "notizen":         ("idle", "float", "pencil"),
    "fortschritt":     ("cheer", "float", "star"),
    "lernzeit":        ("sleepy", "run", "clock"),
    "ingestion":       ("idle", "float", "book"),
    "dokumente":       ("idle", "float", "book"),
    "organisation":    ("idle", "float", "clock"),
    "evaluation":      ("focused", "float", None),
    "einstellungen":   ("idle", "float", None),
    "audio":           ("cheer", "float", "mic"),
    "semesterplan":    ("idle", "float", "book"),
}


def pose_for(page_key: str) -> tuple[str, str, "str | None"]:
    return POSES.get(page_key, ("idle", "float", None))


# Ab so vielen Problemkarten wirkt das grosse Home-Maskottchen besorgt statt
# neutral-froehlich (siehe home_mood()) - bewusst HOEHER als der Schwellwert,
# ab dem der "🐛 Problemkarten"-Chip ueberhaupt erscheint (der zeigt schon ab
# 1 Karte an), damit die Mimik erst bei einem wirklich spuerbaren Rueckstau
# reagiert statt bei jeder einzelnen liegen gebliebenen Karte.
_HOME_WORRIED_LEECH_THRESHOLD = 5


def home_mood(snapshot: "dict | None", *, celebrate: bool = False) -> tuple[str, str, "str | None"]:
    """Bestimmt Pose/Animation/Requisit des GROSSEN Home-Maskottchens aus dem
    aktuellen Lernstand (``planner.today_snapshot()``) statt einer fest
    verdrahteten Pose - macht die Figur zu einem echten Feedback-Element
    statt reiner Deko (vorher: IMMER "cheer"/"wave", egal was gerade los
    ist). Prioritaet: eine frisch freigeschaltete Errungenschaft (``celebrate``)
    schlaegt alles - das ist der einzige Moment, der uneingeschraenkte Freude
    verdient; danach ein akut reissender Streak (die Mimik soll dieselbe
    Verlustaversion zeigen wie die Textwarnung, siehe Home); danach ein
    spuerbarer Leech-Rueckstau; sonst der freundliche Standard-Gruss."""
    if celebrate:
        return ("cheer", "wave", "star")
    if snapshot:
        if snapshot.get("streak_at_risk"):
            return ("worried", "float", None)
        if (snapshot.get("leeches") or 0) >= _HOME_WORRIED_LEECH_THRESHOLD:
            return ("worried", "float", None)
    return ("cheer", "wave", None)


def mascot_svg(accent: str, *, size: int = 200, ink: str = "#2b2036",
               pose: str = "idle", animation: str = "float",
               prop: "str | None" = None, extra_class: str = "") -> str:
    """Rundlicher, freundlicher "Mochi-Geist" mit Doktorhut - grosse Anime-
    Sparkle-Augen, rosa Wangen, dezenter Tuschestrich (``ink``). ``pose``
    waehlt Mund-/Augen-Ausdruck, ``animation`` die Bewegungs-Variante
    (``float``/``wave``/``run``), ``prop`` ein optionales Requisit-Icon.
    Reines HTML/CSS (kein Skript) - fuer das Pupillen-Tracking siehe
    ``render_mascot()``, das zusaetzlich das noetige Skript injiziert."""
    mouth = _MOUTHS.get(pose, _MOUTHS["idle"]).format(ink=ink)
    prop_html = _PROPS.get(prop, "").format(ink=ink)
    # Augen-Ausdruck je Pose: "idle"/"cheer" zwinkert gelegentlich verspielt
    # (nur links, eigene seltenere Keyframe-Animation), "focused" blinzelt nur
    # ganz natuerlich (beidseitig), "sleepy" haelt die Augen dauerhaft halb
    # geschlossen statt zu animieren (muede Wirkung).
    if pose == "sleepy":
        left_eye_cls = right_eye_cls = "ragm-sleepy"
    elif pose in ("idle", "cheer"):
        left_eye_cls, right_eye_cls = "ragm-wink-loop", "ragm-blink"
    else:
        left_eye_cls = right_eye_cls = "ragm-blink"

    return f"""
<div class="rag-mascot rag-mascot-{animation} {extra_class}">
<svg viewBox="0 0 220 230" width="{size}" height="{size * 230 // 220}"
     xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <ellipse cx="110" cy="205" rx="58" ry="10" fill="{ink}" opacity=".08"/>
  <g class="ragm-leg-l"><ellipse cx="82" cy="198" rx="19" ry="11" fill="{accent}" stroke="{ink}" stroke-width="2.5"/></g>
  <g class="ragm-leg-r"><ellipse cx="138" cy="198" rx="19" ry="11" fill="{accent}" stroke="{ink}" stroke-width="2.5"/></g>
  <g class="ragm-arm-l"><circle cx="32" cy="128" r="17" fill="{accent}" stroke="{ink}" stroke-width="2.5"/></g>
  <circle cx="110" cy="128" r="80" fill="{accent}" stroke="{ink}" stroke-width="3"/>
  <circle cx="110" cy="128" r="80" fill="white" opacity=".14"/>
  <polygon points="55,68 128,46 178,66 108,86" fill="{ink}"/>
  <rect x="86" y="80" width="46" height="12" rx="4" fill="{accent}" stroke="{ink}" stroke-width="2.5"/>
  <circle cx="108" cy="66" r="6" fill="{ink}"/>
  <line x1="112" y1="68" x2="146" y2="92" stroke="{ink}" stroke-width="2.5"/>
  <circle cx="147" cy="95" r="5.5" fill="{ink}"/>
  <ellipse cx="72" cy="146" rx="11" ry="7" fill="#ff9fb0" opacity=".55"/>
  <ellipse cx="148" cy="146" rx="11" ry="7" fill="#ff9fb0" opacity=".55"/>
  <g class="ragm-eye-l {left_eye_cls}" style="transform-origin:83px 122px">
    <ellipse rx="15" ry="19" cx="83" cy="122" fill="white" stroke="{ink}" stroke-width="2.5"/>
    <circle class="ragm-pupil-l" cx="85" cy="128" r="7.5" fill="{ink}"/>
    <circle cx="82.5" cy="123" r="2.4" fill="white"/>
  </g>
  <g class="ragm-eye-r {right_eye_cls}" style="transform-origin:137px 122px">
    <ellipse rx="15" ry="19" cx="137" cy="122" fill="white" stroke="{ink}" stroke-width="2.5"/>
    <circle class="ragm-pupil-r" cx="139" cy="128" r="7.5" fill="{ink}"/>
    <circle cx="136.5" cy="123" r="2.4" fill="white"/>
  </g>
  {mouth}
  <g class="ragm-arm-r" style="transform-origin:188px 118px">
    <circle cx="188" cy="128" r="17" fill="{accent}" stroke="{ink}" stroke-width="2.5"/>
  </g>
  {prop_html}
  <g opacity=".9">
    <path d="M 176 44 l 4 10 l 10 4 l -10 4 l -4 10 l -4 -10 l -10 -4 l 10 -4 Z" fill="{accent}"/>
    <path d="M 26 74 l 3 7 l 7 3 l -7 3 l -3 7 l -3 -7 l -7 -3 l 7 -3 Z" fill="{accent}"/>
  </g>
</svg>
</div>
"""


def render_mascot(accent: str, *, size: int = 200, ink: str = "#2b2036",
                   pose: str = "idle", animation: str = "float",
                   prop: "str | None" = None, extra_class: str = "",
                   track_cursor: bool = True) -> None:
    """Rendert das Maskottchen (st.markdown, reines HTML/CSS) und haengt bei
    Bedarf das Pupillen-Tracking-Skript an. WICHTIG: ein ``<script>``-Tag, das
    per ``st.markdown(unsafe_allow_html=True)`` eingefuegt wird, wird vom
    Browser NIE ausgefuehrt (innerHTML-Injektion fuehrt kein <script> aus) -
    das Tracking-Skript muss deshalb ueber ``st.components.v1.html()`` laufen
    (echtes Iframe-Dokument, Skript darin startet normal und greift ueber
    ``window.parent.document`` aufs eigentliche Fenster zu) - dasselbe
    etablierte Muster wie beim Theme-Toggle/Seitenuebergang in ``_style.py``."""
    import streamlit as st
    import streamlit.components.v1 as components

    st.markdown(mascot_svg(accent, size=size, ink=ink, pose=pose, animation=animation,
                            prop=prop, extra_class=extra_class),
                unsafe_allow_html=True)
    if track_cursor:
        components.html(_pupil_tracking_html(), height=0)


def render_mascot_corner(accent: str, *, pose: str = "idle", animation: str = "float",
                          prop: "str | None" = None, size: int = 92) -> None:
    """Kleines Ecken-Maskottchen, direkt an ``document.body`` angehaengt statt
    in den normalen Streamlit-Elementbaum gerendert. NOETIG, nicht nur Stil:
    ``st.markdown`` haengt Inhalte in ``.block-container`` ein, und dessen
    Fade-in-Animation (``_BASE_CSS``, ``ragFadeIn``) haelt per
    ``animation-fill-mode: both`` dauerhaft einen (wenn auch neutralen)
    ``transform``-Wert - und JEDER Vorfahre mit einem ``transform`` wird zum
    "containing block" fuer ``position:fixed``-Kindelemente (CSS-Spezifikation),
    wodurch das Maskottchen relativ zum Container statt zum Sichtfenster
    positioniert wuerde (in der Praxis: es landet irgendwo ausserhalb des
    sichtbaren Bereichs statt unten links). Direkt an ``body`` gehaengt (wie
    schon der Theme-Toggle-Button) umgeht das zuverlaessig. Ersetzt bei jedem
    Aufruf eine evtl. vorhandene fruehere Instanz (Seitenwechsel = neuer
    Skript-Lauf, alte Figur muss weg, bevor die neue Pose reinkommt)."""
    import streamlit.components.v1 as components

    svg_html = mascot_svg(accent, size=size, pose=pose, animation=animation, prop=prop,
                           extra_class="rag-mascot-corner")
    # In ein Template-Element verpackt uebergeben (nicht direkt als JS-String-
    # Literal), damit Anführungszeichen/Sonderzeichen im SVG (z. B. in
    # style="...") nicht mit der JS-String-Syntax kollidieren koennen.
    components.html(f"""
<template id="rag-mascot-corner-tpl">{svg_html}</template>
<script>
(function() {{
  try {{
    var doc = window.parent.document;
    var old = doc.getElementById('rag-mascot-corner-wrap');
    if (old) {{ old.remove(); }}
    var tpl = document.getElementById('rag-mascot-corner-tpl');
    var wrap = doc.createElement('div');
    wrap.id = 'rag-mascot-corner-wrap';
    wrap.appendChild(doc.importNode(tpl.content, true));
    doc.body.appendChild(wrap);
  }} catch (e) {{}}
}})();
</script>
""", height=0)
    components.html(_pupil_tracking_html(), height=0)


def remove_mascot_corner() -> None:
    """Entfernt ein vorhandenes Ecken-Maskottchen wieder (Home hat sein
    eigenes, grosses Hero-Maskottchen statt des kleinen Ecken-Maskottchens -
    ohne das hier wuerde beim Wechsel von einer ANDEREN Seite zu Home die
    dort injizierte ``document.body``-Instanz einfach stehen bleiben, weil
    Home ``render_mascot_corner()`` selbst nie aufruft)."""
    import streamlit.components.v1 as components
    components.html("""
<script>
(function() {
  try {
    var doc = window.parent.document;
    var old = doc.getElementById('rag-mascot-corner-wrap');
    if (old) { old.remove(); }
  } catch (e) {}
})();
</script>
""", height=0)


def _pupil_tracking_html() -> str:
    """Kleines Skript (per components.html, wie das schon etablierte Muster
    fuer den Theme-Toggle/Seitenuebergang): laesst BEIDE Pupillen dezent dem
    Mauszeiger im ECHTEN Elternfenster folgen (kleiner Bewegungsradius, damit
    es wie ein Augen-Move statt wie ein Springen wirkt). Laeuft ueber alle
    Mascot-Instanzen der Seite hinweg (meist nur eine)."""
    return """
<script>
(function() {
  try {
    var doc = window.parent.document;
    if (doc.__ragPupilBound) { return; }
    doc.__ragPupilBound = true;
    var MAXR = 3.2;
    doc.addEventListener('mousemove', function(e) {
      var pupils = doc.querySelectorAll('.ragm-pupil-l, .ragm-pupil-r');
      pupils.forEach(function(p) {
        var eye = p.closest('svg');
        if (!eye) return;
        var rect = eye.getBoundingClientRect();
        var cx = rect.left + rect.width * (p.classList.contains('ragm-pupil-l') ? 0.385 : 0.625);
        var cy = rect.top + rect.height * 0.535;
        var dx = e.clientX - cx, dy = e.clientY - cy;
        var dist = Math.sqrt(dx * dx + dy * dy) || 1;
        var r = Math.min(MAXR, dist / 14);
        var ox = (dx / dist) * r, oy = (dy / dist) * r;
        p.style.transform = 'translate(' + ox.toFixed(1) + 'px,' + oy.toFixed(1) + 'px)';
      });
    }, {passive: true});
  } catch (e) {}
})();
</script>
"""
