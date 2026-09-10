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
"""
from __future__ import annotations


def mascot_svg(accent: str, *, size: int = 200, ink: str = "#2b2036") -> str:
    """Rundlicher, freundlicher "Mochi-Geist" mit Doktorhut - grosse Anime-
    Sparkle-Augen, rosa Wangen, dezenter Tuschestrich (``ink``) um die
    Koerperform, damit es wie eine kleine Comic-Figur statt wie eine reine
    Pastell-Blase wirkt. ``accent`` faerbt Koerper + Hut-Band."""
    return f"""
<svg viewBox="0 0 220 230" width="{size}" height="{size * 230 // 220}"
     xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <ellipse cx="110" cy="205" rx="58" ry="10" fill="{ink}" opacity=".08"/>
  <ellipse cx="82" cy="198" rx="19" ry="11" fill="{accent}" stroke="{ink}" stroke-width="2.5"/>
  <ellipse cx="138" cy="198" rx="19" ry="11" fill="{accent}" stroke="{ink}" stroke-width="2.5"/>
  <circle cx="32" cy="128" r="17" fill="{accent}" stroke="{ink}" stroke-width="2.5"/>
  <circle cx="188" cy="128" r="17" fill="{accent}" stroke="{ink}" stroke-width="2.5"/>
  <circle cx="110" cy="128" r="80" fill="{accent}" stroke="{ink}" stroke-width="3"/>
  <circle cx="110" cy="128" r="80" fill="white" opacity=".14"/>
  <polygon points="55,68 128,46 178,66 108,86" fill="{ink}"/>
  <rect x="86" y="80" width="46" height="12" rx="4" fill="{accent}" stroke="{ink}" stroke-width="2.5"/>
  <circle cx="108" cy="66" r="6" fill="{ink}"/>
  <line x1="112" y1="68" x2="146" y2="92" stroke="{ink}" stroke-width="2.5"/>
  <circle cx="147" cy="95" r="5.5" fill="{ink}"/>
  <ellipse cx="72" cy="146" rx="11" ry="7" fill="#ff9fb0" opacity=".55"/>
  <ellipse cx="148" cy="146" rx="11" ry="7" fill="#ff9fb0" opacity=".55"/>
  <ellipse cx="83" cy="122" rx="15" ry="19" fill="white" stroke="{ink}" stroke-width="2.5"/>
  <ellipse cx="137" cy="122" rx="15" ry="19" fill="white" stroke="{ink}" stroke-width="2.5"/>
  <circle cx="85" cy="128" r="7.5" fill="{ink}"/>
  <circle cx="139" cy="128" r="7.5" fill="{ink}"/>
  <circle cx="82.5" cy="123" r="2.4" fill="white"/>
  <circle cx="136.5" cy="123" r="2.4" fill="white"/>
  <path d="M 98 152 Q 110 162 122 152" fill="none" stroke="{ink}" stroke-width="3.2" stroke-linecap="round"/>
  <g opacity=".9">
    <path d="M 176 44 l 4 10 l 10 4 l -10 4 l -4 10 l -4 -10 l -10 -4 l 10 -4 Z" fill="{accent}"/>
    <path d="M 26 74 l 3 7 l 7 3 l -7 3 l -3 7 l -3 -7 l -7 -3 l 7 -3 Z" fill="{accent}"/>
  </g>
</svg>
"""
