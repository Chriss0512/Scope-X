---
name: scope-x
description: >
  Ein ruhiges, medizinisch-präzises Werkzeug in Deep Navy und Petrol auf
  kühlem Weiß. Farbe codiert ausschließlich Information — Status,
  xABCDE-Kategorie, DIVI-Etikett, Sperrfrist — nie Dekoration. Signal Lime
  erscheint an genau drei Stellen und sonst nirgends. Formensprache sind
  das Fadenkreuz, dünne Linien und ein X aus zwei Winkeln.
---

# SCOPE X — Designsprache

Festgeschrieben, damit jede Erweiterung dieselbe Sprache spricht. Die
Datei folgt dem Muster der DESIGN.md-Sammlungen: erst die Werte, dann die
Regeln, dann die Verbote. Was hier steht, setzt `app/static/app.css` um;
bei Widerspruch gilt diese Datei als Absicht und das CSS als Fehler.

## Herkunft der Prinzipien

Struktur und Haltung übernehmen bewusst Ideen von außen, die Werte nicht:

- **Apple Human Interface**: Klarheit, Zurückhaltung, Tiefe; Hierarchie
  über Größe, Abstand und Stellung statt über Signalfarbe; konzentrische
  Radien. Apples Schriften, Symbole und Farbwelt bleiben draußen — die
  Prinzipien sind frei, die Dateien nicht, und die eigene Designsprache
  führt.
- **Notfallguru**: Inhalt zuerst, große ruhige Flächen, farbkodierte
  Kacheln für den Abruf unter Stress.
- **Feed-Muster** (Instagram-Familie): untere Tab-Leiste mit zentraler
  Haupthandlung, Einträge als Beitragskarten, Profilseite mit
  Kennzahlen-Kopf. Nur der Aufbau — es gibt keinen geteilten Feed, die
  Datentrennung je Konto bleibt vollständig.

## Quelle

Verbindlich ist das **Markenhandbuch 2.0** in `brand/` im Wurzelordner des
Repos (`SCOPE_X_Markenhandbuch.pdf`, Quelle `brand/handbuch/`). Logo,
Favicons, App-Icons und die PDF-Schriften erzeugt
`tools/marke_erzeugen.py`; nichts davon wird von Hand nachgebaut.

## Farben

```yaml
marke:
  deep-navy:   "#102533"   # Navigation, Wortmarke, stärkster Text
  petrol:      "#126878"   # jede Interaktion: Knöpfe, Links, aktive Chips
  cyan:        "#19A6B5"   # Ringsegmente, Fokusring
  signal-lime: "#B9D936"   # X im Logo, aktiver Nav-Marker, Beta-Badge
  cool-white:  "#F6F8F9"   # Seitengrund
  charcoal:    "#17242C"   # Fließtext
  slate:       "#667680"   # Markenwert; als Textfarbe #5B6873 (Kontrast)
  soft-grey:   "#DCE3E6"   # Linien

# Jede Signalfarbe hat zwei Werte. Der Grundwert (--ok) ist der Textwert:
# >= 5:1 auf Weiß und unter weißer Schrift, gilt für Schrift, Badges,
# Chips. Der Flächenwert (--ok-fill) nur für Balken, Punkte, Seitenlinien.
status:            # Text      Fläche     Dunkelmodus
  erfolgreich:     ["#297D5E", "#2E8B68", "#5CA589"]
  fehlgeschlagen:  ["#BD4747", "#C94C4C", "#D87C7C"]
  frustran:        ["#9C6020", "#D9862C", "#E0A052"]
  zek:             ["#A63D4A", "#A63D4A", "#C7858D"]
  information:     ["#3973B9", "#3973B9", "#6E99CC"]
  neutral:         ["#667178", "#7B8890", "#8D99A0"]

kategorien:
  X:      ["#B14149", "#B14149", "#CC8287"]
  A:      ["#7A59A6", "#7A59A6", "#A38CC2"]
  B:      ["#1D7B7E", "#259EA2", "#46B9CC"]
  C:      ["#BB4848", "#D05050", "#DC7C7C"]
  D:      ["#996126", "#D88935", "#D88935"]
  E:      ["#387C51", "#4AA36B", "#51A771"]
  DIAG:   ["#4E719E", "#5B83B8", "#7999C5"]
  TRAUMA: ["#8A6F52", "#8A6F52", "#B39A80"]
  MED:    ["#667178", "#7B8890", "#8D99A0"]

divi-etiketten: >
  Annäherung an die DIVI-Empfehlung 2012 und ISO 26825, nicht normativ.
  Farbe über data-divi, Muster über pattern-* (stripes, stripes-bar,
  split, framed, striped-frame). Weiße Schrift nur je Wirkstoff aus
  DIVI_WEISSE_SCHRIFT (Suxamethonium, Midazolam). Gruppen in app/seed.py,
  Regeln im Handbuch, Kapitel 07.
```

Dunkler Modus: Flächen ab `#0C1820`, nie reines Schwarz. Signalfarben
aufgehellt, darauf dunkle Schrift (`#08181F`).

## Typografie

```yaml
schrift: InterVariable, lokal ausgeliefert (SIL OFL), kein CDN
skala:            # Größe/Zeile in px, Gewicht
  h1:     32/40 700   # Seitentitel                 --fs-h1
  h2:     24/32 700   # Abschnitte langer Textseiten --fs-h2
  h3:     20/28 600   # Karten- und Abschnittstitel  --fs-h3 (in der App: h2)
  text:   16/24 400   # --fs-body
  klein:  14/20 400   # --fs-small, Untergrenze für jeden Oberflächentext
  kennzahl: 28/32 700, tabellarische Ziffern
ausnahme: DIVI-Etikett mindestens 12 px, fett
pdf: Inter Regular und Bold als statische TTF in app/data/fonts
```

## Form

```yaml
radien:   # --radius-xs … --radius-xl
  xs:  2px   # DIVI-Etikett
  sm:  4px   # Badge, Kategorie-Buchstabe
  md:  8px   # Button, Feld, Kachel
  lg: 12px   # Karte (--radius)
  xl: 16px   # Sheet, Dialog
  pill: 999px
abstand: 4 · 8 · 12 · 16 · 24 · 32 px (--space-1 … --space-6)
schatten:
  sm: 0 1px 2px rgba(16,37,51,.10)    # Karten
  md: 0 4px 12px rgba(16,37,51,.12)   # Menüs
  lg: 0 8px 24px rgba(16,37,51,.16)   # Dialoge, Sheets
icons: Linien, 24er-Raster, 2 px Strich, runde Enden
zeichen: >
  Fadenkreuz aus vier Ringsegmenten mit Strichmarken, in der Mitte das X
  aus zwei Winkeln (Navy und Lime). Farben über die Klassen ma, mb, mt,
  mi, mx; auf hellem Grund Variante dark, im Dunkelmodus light.
```

## Aufbau

- **Tab-Leiste unten** (mobil) bzw. Seitenleiste ab 900px, als
  Flex-Element in der Spalte — nie `position: fixed` auf Mobilgeräten,
  die iOS-Adressleiste zerlegt das (gelernt in Update 1).
- Punkte: Einsätze · Auswertung · **Neu** (mittig, angehobene Scheibe in
  Petrol) · Profil · Verwaltung (nur Administrator*innen, sonst nicht
  gerendert).
- **Feed**: ein Einsatz = eine Beitragskarte. Kopf (Ringmarke, Zeitpunkt,
  Einsatzkontext, Frist-Chip), Inhalt als Chips. Null-Werte erscheinen
  nicht.
- **Profil**: Kopf mit Initialen im Ring, Qualifikations-Chips,
  Kennzahlenzeile; darunter Segmentschalter Konto · Sicherheit ·
  Erfassung · Daten. Karten tragen ihre Gruppe über die Überschrift,
  nicht über ihre Position.
- **Kachelwahl**: Maßnahmen als Kacheln mit Kategorie-Seitenlinie,
  Medikamente mit DIVI-Etikettenband als Kopf — die Auswahl in der App
  sieht aus wie die Spritze in der Hand.

## Verbote

1. **Kein `style="…"`.** Die Content-Security-Policy verwirft es
   stillschweigend. Abstände über `data-s`-Tokens, Kategorien über
   `data-cat`, Etiketten über `data-divi`.
2. **Kein CDN, kein externer Aufruf zur Laufzeit.** CSP erlaubt nur
   `'self'`.
3. **Lime nur für X, Nav-Marker und Beta-Badge.** Nicht für Erfolg, nie
   als Textfarbe auf Weiß, nicht „weil noch Farbe fehlt".
4. **Farbe trägt nie allein Information.** Jede Statuspille trägt Text,
   jedes Etikett seinen Gruppennamen.
5. **Keine Zweckentfremdung der Fläche.** Keine Indikationen, keine
   Dosierungen, keine Algorithmen — auch nicht als „hilfreiche" UI-Idee.
6. **Touch-Flächen ≥ 44px**, sichtbarer Fokusring,
   `prefers-reduced-motion` wird respektiert, kein Text unter 14 px.
7. **Budget**: JS + CSS + Schrift ≤ 700 KB, geprüft von der
   Qualitätsschleife.
