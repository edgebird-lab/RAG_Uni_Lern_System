#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Zeichnet das Store-Symbol (512x512) und die Titelgrafik (1024x500) nach der Vorlage des Launcher-Symbols
(app/src/main/res/drawable/ic_launcher_foreground.xml). Aufruf: python3 tools/make_store_icon.py [Ausgabeordner]"""
import sys, pathlib
from PIL import Image, ImageDraw, ImageFont

OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "docs/store"); OUT.mkdir(parents=True, exist_ok=True)
BG, PAGE_L, PAGE_R, LINE, SPARK = (0x1F, 0x2A, 0x44), (0xF5, 0xEF, 0xE2), (0xE4, 0xD8, 0xBE), (0xB7, 0xA7, 0x85), (0xE8, 0xA9, 0x3A)

def bez(p0, p1, p2, p3, n=24):
    pts = []
    for i in range(n + 1):
        t = i / n; u = 1 - t
        pts.append((u**3*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t**3*p3[0], u**3*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t**3*p3[1]))
    return pts

def draw_mark(d, s, ox=0, oy=0):
    """Zeichnet Buch und Funke; Koordinaten der 108er-Vorlage, skaliert mit s."""
    P = lambda pts: [(ox + x * s, oy + y * s) for x, y in pts]
    left = [(54, 77), (54, 41)] + bez((54, 41), (48, 36.5), (38, 35.5), (30, 37.5))[1:] + [(30, 72.5)] + bez((30, 72.5), (38, 70.5), (48, 71.5), (54, 77))[1:]
    right = [(54, 77), (54, 41)] + bez((54, 41), (60, 36.5), (70, 35.5), (78, 37.5))[1:] + [(78, 72.5)] + bez((78, 72.5), (70, 70.5), (60, 71.5), (54, 77))[1:]
    d.polygon(P(left), fill=PAGE_L); d.polygon(P(right), fill=PAGE_R)
    for quad in ([(35, 46), (49, 47), (49, 49), (35, 48)], [(35, 52), (49, 53), (49, 55), (35, 54)], [(35, 58), (45, 58.8), (45, 60.8), (35, 60)],
                 [(59, 47), (73, 46), (73, 48), (59, 49)], [(59, 53), (73, 52), (73, 54), (59, 55)], [(59, 59), (69, 58.2), (69, 60.2), (59, 61)]):
        d.polygon(P(quad), fill=LINE)
    d.polygon(P([(54, 22), (56.4, 28.6), (63, 31), (56.4, 33.4), (54, 40), (51.6, 33.4), (45, 31), (51.6, 28.6)]), fill=SPARK)

def supersample(size, painter, factor=4):
    img = Image.new("RGB", (size[0] * factor, size[1] * factor), BG)
    painter(ImageDraw.Draw(img), factor)
    return img.resize(size, Image.LANCZOS)

# Store-Symbol: das Zeichen füllt die Fläche stärker als im Launcher (dort verdeckt die Maske den Rand)
icon = supersample((512, 512), lambda d, f: draw_mark(d, 512 / 108 * 1.18 * f, ox=-(54 * 1.18 - 54) * 512 / 108 * f, oy=-(54 * 1.18 - 54) * 512 / 108 * f + 8 * f))
icon.save(OUT / "icon-512.png", optimize=True)

# Titelgrafik 1024x500: Zeichen links, Name rechts (Schriftgröße so gewählt, dass der Name in die Spalte passt)
NAME = "Local Study AI"
def feature(d, f):
    draw_mark(d, 440 / 108 * f, ox=10 * f, oy=18 * f)
    path_b, path_r = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
    size = 90
    while size > 30 and ImageFont.truetype(path_b, size * f).getlength(NAME) > 520 * f: size -= 2
    big, small = ImageFont.truetype(path_b, size * f), ImageFont.truetype(path_r, 30 * f)
    d.text((470 * f, 160 * f), NAME, font=big, fill=PAGE_L)
    d.text((474 * f, 160 * f + size * 1.5 * f), "Lernen mit KI – auf dem Handy", font=small, fill=SPARK)
    d.text((474 * f, 160 * f + size * 1.5 * f + 44 * f), "Learn with AI – on your phone", font=small, fill=LINE)
supersample((1024, 500), feature, 2).save(OUT / "feature-graphic-1024x500.png", optimize=True)
print("fertig:", [p.name for p in OUT.iterdir()])
