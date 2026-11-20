"""Baut das Markenhandbuch als PDF.

    python brand/handbuch/bauen.py            # aus dem Wurzelordner des Repos

Liest handbuch.html, setzt Logos, Tabellen und Icons ein und druckt mit
Playwright (Chromium) nach brand/SCOPE_X_Markenhandbuch.pdf. Die Logos
kommen aus brand/, die Icons aus der Navigation der App, damit Handbuch und
App nicht auseinanderlaufen.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
BRAND = HIER.parent
REPO = BRAND.parent
INDEX = REPO / "scopex" / "app" / "static" / "index.html"
AUS_HTML = HIER / "_gebaut.html"
AUS_PDF = BRAND / "SCOPE_X_Markenhandbuch.pdf"

# Fläche, Text auf Weiß (>= 5:1), Dunkelmodus
STATUS = [
    ("Erfolgreich", "✓", "#2E8B68", "#297D5E", "#5CA589"),
    ("Fehlgeschlagen", "✕", "#C94C4C", "#BD4747", "#D87C7C"),
    ("Frustran", "◐", "#D9862C", "#9C6020", "#E0A052"),
    ("ZEK", "!", "#A63D4A", "#A63D4A", "#C7858D"),
    ("Information", "i", "#3973B9", "#3973B9", "#6E99CC"),
    ("Neutral", "–", "#7B8890", "#667178", "#8D99A0"),
]
KATEGORIEN = [
    ("x", "Exsanguination", "#B14149", "#B14149", "#CC8287"),
    ("A", "Atemweg", "#7A59A6", "#7A59A6", "#A38CC2"),
    ("B", "Belüftung", "#259EA2", "#1D7B7E", "#46B9CC"),
    ("C", "Kreislauf", "#D05050", "#BB4848", "#DC7C7C"),
    ("D", "Neurologie", "#D88935", "#996126", "#D88935"),
    ("E", "Exposition", "#4AA36B", "#387C51", "#51A771"),
    ("Dx", "Diagnostik", "#5B83B8", "#4E719E", "#7999C5"),
    ("Tr", "Trauma", "#8A6F52", "#8A6F52", "#B39A80"),
    ("Med", "Medikamente", "#7B8890", "#667178", "#8D99A0"),
]
ABSTAENDE = [(1, 4, "Symbol, Text"), (2, 8, "in einer Zeile"),
             (3, 12, "Feld zu Feld"), (4, 16, "in der Karte"),
             (5, 24, "Abschnitte"), (6, 32, "Seitenblöcke")]
RADIEN = [("xs", 2, "DIVI-Etikett"), ("sm", 4, "Badge"), ("md", 8, "Button, Feld"),
          ("lg", 12, "Karte"), ("xl", 16, "Sheet, Dialog"), ("pill", 999, "Chip")]
MODULE = [
    ("Logbuch", "Logbuch", "Einsätze, Maßnahmen nach xABCDE, Medikamente mit DIVI-Etikett, "
     "Ergebnis, Komplikationen. Blutzucker in mg/dl oder mmol/l. Privat.", "nur selbst"),
    ("Auswertung", "Auswertung", "Kennzahlen, Verläufe, Nachweis als PDF und CSV. "
     "Grundlage für die Praxisanleitung.", "nur selbst"),
    ("Feed", "Feed &amp; Beiträge", "Fallberichte, Wissen mit Quelle, Fragen. @Erwähnung "
     "von Konten, denen man folgt, mit Mitteilung. Auf Lernen ausgerichtet statt auf "
     "Verweildauer.", "Mitglieder"),
    ("Entdecken", "Fallvorstellung &amp; Themen", "Anonymisierte Fälle mit Frage an die "
     "Community, Themen wie #Atemwegsmanagement. Suche nach Personen und Inhalten.",
     "Mitglieder"),
    ("Nachrichten", "Nachrichten", "Direktnachrichten zwischen zwei Mitgliedern, mit "
     "Kontaktanfrage. Transport über TLS, gespeichert verschlüsselt.", "Beteiligte"),
    ("Netzwerk", "Netzwerk", "Kontakte, Anfragen, Bestätigung von Kompetenzen, Einladung "
     "neuer Kolleg*innen zur Bewerbung.", "Mitglieder"),
    ("Profil", "Profil &amp; Chronik", "Werdegang, Qualifikationen, Fortbildungen und eigene "
     "Beiträge. Sichtbarkeit je Angabe einstellbar.", "nach Einstellung"),
    ("Mitteilungen", "Mitteilungen", "Reaktionen, Kommentare, Anfragen und Hinweise der "
     "Administration, gebündelt statt einzeln gemeldet.", "nur selbst"),
    ("Administration", "Administration", "Bewerbungen, Einladungen, Kataloge, Moderation "
     "und Sicherung. Nur für die Administration sichtbar.", "Administration"),
]
ETIKETTEN = [
    ("Hypnotika", "#fedd00", "#111", "", "PROPOFOL", "10 mg/ml"),
    ("Benzodiazepine", "#ff8200", "#111", "", "DIAZEPAM", "5 mg/ml"),
    ("Benzodiazepine, Midazolam", "#ff8200", "#fff", "hell", "MIDAZOLAM", "1 mg/ml"),
    ("Benzodiazepin-Antagonisten", "#ff8200", "#111", "streifen", "FLUMAZENIL", "0,1 mg/ml"),
    ("Opioide", "#71c5e8", "#111", "", "FENTANYL", "50 µg/ml"),
    ("Opioid-Antagonisten", "#71c5e8", "#111", "streifen", "NALOXON", "0,4 mg/ml"),
    ("Relaxantien, depolarisierend", "#f9423a", "#fff", "hell", "SUXAMETHONIUM", "20 mg/ml"),
    ("Relaxantien, nichtdepolarisierend", "#f9423a", "#111", "split", "ROCURONIUM", "10 mg/ml"),
    ("Relaxans-Antagonisten", "#f9423a", "#111", "streifen balken", "SUGAMMADEX", "100 mg/ml"),
    ("Vasopressoren", "#d6bfdd", "#111", "", "NORADRENALIN", "0,1 mg/ml"),
    ("Antihypertonika", "#d6bfdd", "#111", "streifen", "URAPIDIL", "5 mg/ml"),
    ("Lokalanästhetika", "#c4bfb6", "#111", "", "LIDOCAIN", "10 mg/ml"),
    ("Anticholinergika", "#a4d65e", "#111", "", "ATROPIN", "0,5 mg/ml"),
    ("Antiemetika", "#efbe7d", "#111", "", "ONDANSETRON", "2 mg/ml"),
    ("Heparin", "#ffffff", "#111", "rahmen", "HEPARIN", "5000 I.E./ml"),
    ("Protamin", "#ffffff", "#111", "streifrand", "PROTAMIN", "1000 I.E./ml"),
    ("Elektrolyte ¹", "#046a38", "#fff", "", "NACL 0,9 %", "10 ml"),
    ("Verschiedene", "#ffffff", "#111", "", "PARACETAMOL", "10 mg/ml"),
]


def icons() -> dict[str, str]:
    html = INDEX.read_text(encoding="utf-8")
    gefunden = {}
    for m in re.finditer(
            r'<svg class="glyph"[^>]*>(.*?)</svg>(?:</span>)?<span class="lbl">([^<]+)</span>',
            html, re.S):
        gefunden[m.group(2)] = m.group(1).strip()
    abm = re.search(r'class="nav-abmelden"[^>]*>\s*<svg[^>]*>(.*?)</svg>', html, re.S)
    if abm:
        gefunden["Abmelden"] = abm.group(1).strip()
    gefunden["Suche"] = gefunden.get("Entdecken", "")
    gefunden["schloss"] = ('<rect x="5" y="10.5" width="14" height="10" rx="2.5"/>'
                           '<path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5M12 14.5v2.5"/>')
    gefunden["Auswertung"] = gefunden.get("Auswertung", "")
    return gefunden


def svg_icon(inhalt: str) -> str:
    return ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{inhalt}</svg>')


def motiv() -> str:
    boegen = []
    for a0, a1, r in ((-76, -14, 44), (14, 76, 44), (104, 166, 44), (194, 256, 44)):
        import math

        def p(a, r=r):
            w = math.radians(a - 90)
            return 50 + r * math.cos(w), 50 + r * math.sin(w)
        (x0, y0), (x1, y1) = p(a0), p(a1)
        boegen.append(f'<path d="M{x0:.2f} {y0:.2f}A{r} {r} 0 0 1 {x1:.2f} {y1:.2f}" '
                      'fill="none" stroke-width="5"/>')
    return f'<svg class="motiv" viewBox="0 0 100 100" aria-hidden="true">{"".join(boegen)}</svg>'


def bauen() -> str:
    html = (HIER / "handbuch.html").read_text(encoding="utf-8")
    ic = icons()

    def svg(m):
        datei = BRAND / f"{m.group(1)}.svg"
        inhalt = datei.read_text(encoding="utf-8")
        return re.sub(r"<title>.*?</title>", "", inhalt)

    html = re.sub(r"\{\{svg:([a-z_]+)\}\}", svg, html)
    html = re.sub(r"\{\{ico:([a-zA-Z]+)\}\}", lambda m: svg_icon(ic[m.group(1)]), html)

    kopf = (f'<div class="kopf"><div class="logo">{svg(re.match("(.*)", "logo_horizontal_dark"))}'
            '</div><div class="meta">Markenhandbuch · Version 2.1<br>'
            'Private Initiative · erweiterte Beta</div></div>')
    symbol = svg(re.match("(.*)", "logo_symbol_dark"))
    html = html.replace("{{kopf}}", kopf).replace("{{motiv}}", motiv())
    html = re.sub(
        r"\{\{fuss:(\d+)\}\}",
        lambda m: (f'<div class="fuss">{symbol}<span><b>SCOPE X</b> Markenhandbuch 2.1</span>'
                   '<span class="mitte">Das Maßnahmen- und Kompetenzlogbuch für den '
                   f'Rettungsdienst</span><span class="nr">{m.group(1)}</span></div>'), html)

    zeilen = []
    for name, zeichen, fl, tx, dk in STATUS:
        zeilen.append(
            f'<tr><td><span class="badge" style="background:{tx}">{zeichen} {name}</span></td>'
            f'<td><span class="punkt" style="background:{fl}"></span>{fl}</td>'
            f'<td><span class="punkt" style="background:{tx}"></span>{tx}</td>'
            f'<td><span class="punkt" style="background:{dk}"></span>{dk}</td></tr>')
    html = html.replace("{{status}}", "".join(zeilen))

    zeilen = []
    for kurz, name, fl, tx, dk in KATEGORIEN:
        zeilen.append(
            f'<tr><td><span class="badge kat" style="background:{tx}">{kurz}</span> {name}</td>'
            f'<td><span class="punkt" style="background:{fl}"></span>{fl}</td>'
            f'<td><span class="punkt" style="background:{tx}"></span>{tx}</td>'
            f'<td><span class="punkt" style="background:{dk}"></span>{dk}</td></tr>')
    html = html.replace("{{kategorien}}", "".join(zeilen))

    html = html.replace("{{abstaende}}", "".join(
        f'<tr><td class="nw"><code>space-{n}</code></td><td class="r nw">{px} px</td>'
        f'<td><span style="display:inline-block;height:2.4mm;width:{px * .3}mm;'
        f'background:#19A6B5;border-radius:.4mm;vertical-align:middle"></span></td>'
        f'<td class="mini nw">{wo}</td></tr>' for n, px, wo in ABSTAENDE))
    html = html.replace("{{radien}}", "".join(
        f'<div style="border-radius:{min(px, 30) * .45}mm"><b>{n} · {px if px < 99 else "∞"}'
        f'{" px" if px < 99 else ""}</b><span>{wo}</span></div>' for n, px, wo in RADIEN))

    namen = ["Feed", "Entdecken", "Netzwerk", "Nachrichten", "Mitteilungen", "Neu",
             "Logbuch", "Auswertung", "Profil", "Administration", "Abmelden", "schloss"]
    beschr = {"schloss": "Privat"}
    html = html.replace("{{icons}}", "".join(
        f'<div>{svg_icon(ic[n])}<span>{beschr.get(n, n)}</span></div>' for n in namen))
    html = html.replace("{{navliste}}", "".join(
        f'<div class="nav-punkt{" an" if n == "Logbuch" else ""}">{svg_icon(ic[n])}{n}</div>'
        for n in ["Feed", "Entdecken", "Netzwerk", "Nachrichten", "Mitteilungen", "Logbuch",
                  "Auswertung", "Profil", "Administration"]))
    html = html.replace("{{module}}", "".join(
        f'<div class="karte modul"><h2>{svg_icon(ic[i])}{t}</h2><div class="inhalt">'
        f'<p>{txt}</p><div class="wo">Sichtbar für: <b>{wo}</b></div></div></div>'
        for i, t, txt, wo in MODULE))
    html = html.replace("{{etiketten}}", "".join(
        f'<div><span class="etikett {kl}" style="--bg:{bg};--fg:{fg}"><span>{name}</span>'
        f'<small>{st}</small></span><span class="g"><b>{gruppe}</b></span></div>'
        for gruppe, bg, fg, kl, name, st in ETIKETTEN)
        + '<div class="g" style="grid-column:span 2;align-self:end">¹ Festlegung von SCOPE X, '
          'nicht Teil der DIVI-Empfehlung 2012. Konzentrationen sind Beispiele für die '
          'Darstellung, keine Empfehlung.</div>')

    rest = re.findall(r"\{\{[^}]+\}\}", html)
    if rest:
        sys.exit(f"Nicht ersetzt: {rest}")
    return html


def main() -> None:
    from playwright.sync_api import sync_playwright

    AUS_HTML.write_text(bauen(), encoding="utf-8")
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        s = b.new_page()
        s.goto(AUS_HTML.as_uri())
        s.wait_for_load_state("networkidle")
        s.evaluate("document.fonts.ready")
        ueber = s.evaluate("""() => [...document.querySelectorAll('.seite')].map((p, i) => {
            const r = p.getBoundingClientRect(); let max = 0;
            p.querySelectorAll('.karte, .hinweis, .lead, table').forEach(e => {
              if (e.closest('.fuss')) return;
              max = Math.max(max, e.getBoundingClientRect().bottom - r.top); });
            return [i + 1, Math.round(max), Math.round(r.height)]; })""")
        for nr, unten, hoehe in ueber:
            frei = hoehe - unten
            print(f"Seite {nr:2}: Inhalt bis {unten}px, frei {frei}px"
                  + ("  << UEBERLAUF" if frei < 54 else ""))
        s.pdf(path=str(AUS_PDF), prefer_css_page_size=True, print_background=True)
        b.close()
    print(AUS_PDF)


if __name__ == "__main__":
    main()
