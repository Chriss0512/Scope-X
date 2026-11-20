"""Erzeugt die Logo-Dateien von SCOPE X als Vektorgrafik und Rastergrafik.

Aufruf aus dem Ordner scopex/:

    python tools/marke_erzeugen.py

Ergebnis:
    ../brand/                  alle Varianten nach Markenhandbuch, Kapitel 8
    app/static/                icon.svg, mark.svg, Favicons und App-Icons
    app/data/fonts/            Inter als statische TTF für den PDF-Nachweis
    icon.png, logo.png         Bilder für den Add-on-Store von Home Assistant

Die Schrift wird in Pfade umgewandelt, damit jede SVG-Datei ohne
installierte Schrift gleich aussieht. Quelle ist die Inter-Datei der App
(SIL Open Font License, siehe app/static/fonts/Inter-LICENSE.txt).

Benennung: <typ>_<inhalt>_<variante>.<format>
    Variante dark  = dunkle Zeichen, für helle Flächen
    Variante light = helle Zeichen, für dunkle Flächen
    Variante mono  = einfarbig, für Stempel, Gravur und Fax

Benötigt fonttools mit brotli und für die Rastergrafik Playwright.
"""
from __future__ import annotations

import math
import shutil
import sys
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

HIER = Path(__file__).resolve().parent.parent
ZIEL = HIER.parent / "brand"
STATIC = HIER / "app" / "static"
SCHRIFT = STATIC / "fonts" / "InterVariable.woff2"

NAVY = "#102533"
PETROL = "#126878"
CYAN = "#19A6B5"
LIME = "#B9D936"
WEISS = "#FFFFFF"

CLAIM = ("Das Maßnahmen- und Kompetenzlogbuch", "für den Rettungsdienst")

_FONTS: dict[int, TTFont] = {}


def _font(gewicht: int) -> TTFont:
    if gewicht not in _FONTS:
        f = TTFont(str(SCHRIFT))
        _FONTS[gewicht] = instantiateVariableFont(
            f, {"wght": gewicht, "opsz": 32}, inplace=False)
    return _FONTS[gewicht]


def text_pfad(text: str, x: float, y: float, groesse: float,
              gewicht: int = 800, sperrung: float = 0.0) -> tuple[str, float]:
    """Gibt (Pfaddaten, Breite) zurück. y ist die Grundlinie."""
    f = _font(gewicht)
    upm = f["head"].unitsPerEm
    s = groesse / upm
    cmap = f.getBestCmap()
    glyphen = f.getGlyphSet()
    hmtx = f["hmtx"]
    teile = []
    cx = x
    for i, z in enumerate(text):
        name = cmap[ord(z)]
        pen = SVGPathPen(glyphen, lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
        glyphen[name].draw(TransformPen(pen, (s, 0, 0, -s, cx, y)))
        teile.append(pen.getCommands())
        cx += hmtx[name][0] * s
        if i < len(text) - 1:
            cx += sperrung * groesse
    return " ".join(t for t in teile if t), cx - x


# ---------------------------------------------------------------- Zeichen

def _bogen(r: float, a0: float, a1: float) -> str:
    """Kreisbogen im Uhrzeigersinn, 0 Grad oben."""
    def p(a):
        w = math.radians(a - 90)
        return 50 + r * math.cos(w), 50 + r * math.sin(w)
    (x0, y0), (x1, y1) = p(a0), p(a1)
    gross = 1 if (a1 - a0) % 360 > 180 else 0
    return f"M{x0:.2f} {y0:.2f}A{r} {r} 0 {gross} 1 {x1:.2f} {y1:.2f}"


def zeichen(tinte: str, ring_a: str, ring_b: str, akzent: str,
            dx: float = 0, dy: float = 0, s: float = 1) -> str:
    """Das Fadenkreuz in einem 100er-Raster.

    Vier Ringsegmente, an den Lücken die Strichmarken, in der Mitte das X
    aus zwei Winkeln. Der linke Winkel trägt die Schriftfarbe, der rechte
    den Akzent. Zusammen ergeben sie das X des Namens.
    """
    r, luecke = 34, 14
    boegen = []
    for i, farbe in enumerate((ring_a, ring_b, ring_a, ring_b)):
        a = i * 90 - 90
        boegen.append(f'<path d="{_bogen(r, a + luecke, a + 90 - luecke)}" '
                      f'stroke="{farbe}"/>')
    marken = ("M50 3V22M50 78V97M3 50H22M78 50H97")
    links = "27,30 39,30 49.4,50 39,70 27,70 37.4,50"
    rechts = "73,30 61,30 50.6,50 61,70 73,70 62.6,50"
    return (f'<g transform="translate({dx} {dy}) scale({s})">'
            f'<g fill="none" stroke-width="7">{"".join(boegen)}</g>'
            f'<path d="{marken}" stroke="{tinte}" stroke-width="5" fill="none"/>'
            f'<polygon points="{links}" fill="{tinte}"/>'
            f'<polygon points="{rechts}" fill="{akzent}"/></g>')


def _svg(breite: float, hoehe: float, inhalt: str, titel: str = "SCOPE X") -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {breite:g} {hoehe:g}" '
            f'role="img" aria-label="{titel}"><title>{titel}</title>{inhalt}</svg>\n')


def farben(variante: str) -> dict:
    if variante == "dark":
        return {"tinte": NAVY, "ring_a": PETROL, "ring_b": CYAN, "akzent": LIME,
                "claim": PETROL}
    if variante == "light":
        return {"tinte": WEISS, "ring_a": CYAN, "ring_b": "#7FD3DC", "akzent": LIME,
                "claim": "#C9D6DC"}
    return {"tinte": NAVY, "ring_a": NAVY, "ring_b": NAVY, "akzent": NAVY,
            "claim": NAVY}


def wortmarke(f: dict, x: float, grund: float, groesse: float) -> tuple[str, float]:
    p1, b1 = text_pfad("SCOPE", x, grund, groesse, 800, 0.02)
    lx = x + b1 + groesse * 0.22
    p2, b2 = text_pfad("X", lx, grund, groesse, 800)
    return (f'<path d="{p1}" fill="{f["tinte"]}"/>'
            f'<path d="{p2}" fill="{f["akzent"]}"/>'), lx + b2 - x


def logo_primaer(variante: str, claim: bool = True) -> str:
    f = farben(variante)
    z = zeichen(f["tinte"], f["ring_a"], f["ring_b"], f["akzent"])
    if claim:
        wm, bw = wortmarke(f, 118, 50, 46)
        c1, w1 = text_pfad(CLAIM[0], 119, 72, 13.5, 500)
        c2, w2 = text_pfad(CLAIM[1], 119, 89, 13.5, 500)
        breite = 118 + max(bw, w1, w2) + 4
        inhalt = z + wm + f'<path d="{c1} {c2}" fill="{f["claim"]}"/>'
    else:
        wm, bw = wortmarke(f, 116, 67, 48)
        breite = 116 + bw + 4
        inhalt = z + wm
    return _svg(breite, 100, inhalt)


def logo_kompakt(variante: str) -> str:
    f = farben(variante)
    wm, bw = wortmarke(f, 0, 0, 30)
    breite = max(100, bw) + 8
    z = zeichen(f["tinte"], f["ring_a"], f["ring_b"], f["akzent"],
                dx=(breite - 100) / 2)
    wm, _ = wortmarke(f, (breite - bw) / 2, 134, 30)
    return _svg(breite, 142, z + wm)


def logo_zeichen(variante: str) -> str:
    f = farben(variante)
    return _svg(100, 100, zeichen(f["tinte"], f["ring_a"], f["ring_b"], f["akzent"]))


def icon_app() -> str:
    f = farben("light")
    return _svg(100, 100, f'<rect width="100" height="100" rx="22" fill="{NAVY}"/>'
                + zeichen(f["tinte"], f["ring_a"], f["ring_b"], LIME,
                          dx=12, dy=12, s=0.76))


def icon_klein() -> str:
    """Favicon bis 32 px: ohne Strichmarken, dickere Formen."""
    inhalt = (f'<rect width="100" height="100" rx="20" fill="{NAVY}"/>'
              f'<g fill="none" stroke-width="10">'
              f'<path d="{_bogen(36, -76, -14)}" stroke="{CYAN}"/>'
              f'<path d="{_bogen(36, 14, 76)}" stroke="#7FD3DC"/>'
              f'<path d="{_bogen(36, 104, 166)}" stroke="{CYAN}"/>'
              f'<path d="{_bogen(36, 194, 256)}" stroke="#7FD3DC"/></g>'
              f'<polygon points="24,27 39,27 50,50 39,73 24,73 35,50" fill="{WEISS}"/>'
              f'<polygon points="76,27 61,27 50,50 61,73 76,73 65,50" fill="{LIME}"/>')
    return _svg(100, 100, inhalt)


def addon_logo() -> str:
    """250 x 100 für den Add-on-Store: Zeichen und Wortmarke, ohne Claim."""
    f = farben("dark")
    z = zeichen(f["tinte"], f["ring_a"], f["ring_b"], f["akzent"], dx=4, dy=14, s=0.72)
    wm, _ = wortmarke(f, 86, 64, 34)
    return _svg(250, 100, z + wm)


# ---------------------------------------------------------------- Ausgabe

def schreiben() -> dict[str, Path]:
    ZIEL.mkdir(exist_ok=True)
    dateien = {}
    for v in ("dark", "light", "mono"):
        dateien[f"logo_primary_{v}.svg"] = logo_primaer(v)
        dateien[f"logo_horizontal_{v}.svg"] = logo_primaer(v, claim=False)
        dateien[f"logo_compact_{v}.svg"] = logo_kompakt(v)
        dateien[f"logo_symbol_{v}.svg"] = logo_zeichen(v)
    dateien["icon_app.svg"] = icon_app()
    dateien["icon_favicon.svg"] = icon_klein()
    dateien["logo_addon_store.svg"] = addon_logo()
    pfade = {}
    for name, inhalt in dateien.items():
        p = ZIEL / name
        p.write_text(inhalt, encoding="utf-8")
        pfade[name] = p
    return pfade


def rastern(pfade: dict[str, Path]) -> None:
    from playwright.sync_api import sync_playwright

    auftraege = [
        ("icon_favicon.svg", 16, 16, ZIEL / "favicon_16.png"),
        ("icon_favicon.svg", 32, 32, ZIEL / "favicon_32.png"),
        ("icon_app.svg", 48, 48, ZIEL / "favicon_48.png"),
        ("icon_app.svg", 64, 64, ZIEL / "favicon_64.png"),
        ("icon_app.svg", 180, 180, ZIEL / "icon_app_180.png"),
        ("icon_app.svg", 192, 192, ZIEL / "icon_app_192.png"),
        ("icon_app.svg", 512, 512, ZIEL / "icon_app_512.png"),
        ("icon_app.svg", 128, 128, HIER / "icon.png"),
        ("logo_addon_store.svg", 250, 100, HIER / "logo.png"),
    ]
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for quelle, b, h, ziel in auftraege:
            seite = browser.new_page(viewport={"width": b, "height": h})
            svg = pfade[quelle].read_text(encoding="utf-8")
            seite.set_content(
                "<style>html,body{margin:0;background:transparent}"
                f"svg{{display:block;width:{b}px;height:{h}px}}</style>{svg}")
            seite.screenshot(path=str(ziel), omit_background=True)
            seite.close()
        browser.close()


# Zeichenvorrat der PDF-Schriften: Lateinisch mit Erweiterung A, typografische
# Satzzeichen, Euro, Pfeile, Minus. Reicht für deutsche und europäische Namen;
# fehlende Zeichen ersetzt app/pdf.py vor der Ausgabe.
PDF_ZEICHEN = (list(range(0x20, 0x7F)) + list(range(0xA0, 0x180))
               + list(range(0x2010, 0x2028)) + list(range(0x2030, 0x203B))
               + [0x20AC, 0x2116, 0x2122, 0x2190, 0x2191, 0x2192, 0x2193, 0x2212,
                  0x2026, 0x00B7])


def schriften_pdf() -> None:
    """Statische Inter-Schnitte für fpdf2, das keine variablen Schriften
    einbetten kann. Auf den Zeichenvorrat oben reduziert."""
    from fontTools import subset

    ziel = HIER / "app" / "data" / "fonts"
    ziel.mkdir(parents=True, exist_ok=True)
    for name, gewicht in (("Inter-Regular", 400), ("Inter-Bold", 700)):
        f = TTFont(str(SCHRIFT))
        f = instantiateVariableFont(f, {"wght": gewicht, "opsz": 14})
        opt = subset.Options()
        opt.layout_features = ["kern", "liga", "tnum"]
        opt.name_IDs = ["*"]
        opt.notdef_outline = True
        s = subset.Subsetter(options=opt)
        s.populate(unicodes=PDF_ZEICHEN)
        s.subset(f)
        f.flavor = None
        f.save(str(ziel / f"{name}.ttf"))
    shutil.copy(SCHRIFT.parent / "Inter-LICENSE.txt", ziel / "Inter-LICENSE.txt")


def main() -> None:
    pfade = schreiben()
    shutil.copy(pfade["icon_app.svg"], STATIC / "icon.svg")
    shutil.copy(pfade["icon_favicon.svg"], STATIC / "favicon.svg")
    shutil.copy(pfade["logo_symbol_dark.svg"], STATIC / "mark.svg")
    schriften_pdf()
    if "--ohne-raster" not in sys.argv:
        rastern(pfade)
        for n in ("favicon_32.png", "icon_app_180.png"):
            shutil.copy(ZIEL / n, STATIC / n)
    print(f"{len(pfade)} SVG-Dateien in {ZIEL}")


if __name__ == "__main__":
    main()
