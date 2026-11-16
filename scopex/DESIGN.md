---
name: scope-x
description: >
  Ein ruhiges, medizinisch-präzises Werkzeug in Deep Navy und Petrol auf
  kühlem Weiß. Farbe codiert ausschließlich Information — Status,
  xABCDE-Kategorie, DIVI-Etikett, Sperrfrist — nie Dekoration. Signal Lime
  erscheint an genau drei Stellen und sonst nirgends. Formensprache sind
  unvollständige Ringe, dünne Linien und ein geometrisches X.
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

## Farben

```yaml
marke:
  deep-navy:   "#102533"   # Navigation, Wortmarke, stärkster Text
  petrol:      "#126878"   # jede Interaktion: Knöpfe, Links, aktive Chips
  cyan:        "#19A6B5"   # Scope-Ring, Zweitdiagramme, Fokusring
  signal-lime: "#B9D936"   # NUR: X der Wortmarke, X des Icons, aktiver Nav-Marker
  cool-white:  "#F6F8F9"   # Seitengrund
  charcoal:    "#17242C"   # Fließtext
  slate:       "#667680"   # Markenwert; als Textfarbe stattdessen #5B6873 (Kontrast)
  soft-grey:   "#DCE3E6"   # Linien

status:                    # Füllflächen tragen weiße Schrift mit >= 4,5:1
  erfolgreich:   "#1F7554"
  fehlgeschlagen:"#BC3F3F"
  abgebrochen:   "#D9862C" # trägt dunkle Schrift; als Text auf hell: #8A5209
  zek:           "#A63D4A"

kategorien:                # xABCDE als 4px-Seitenlinie und Buchstaben-Badge
  X: "#A63D4A"
  A: "#725FA6"
  B: "#2995A8"
  C: "#C55454"
  D: "#C48B32"
  E: "#628B68"
  DIAG: "#4E70A8"
  TRAUMA: "#8A6F52"

divi-etiketten:            # Annäherung an EN ISO 26825, nicht normativ,
  regel: >                 # Zuordnung je Wirkstoff im Katalog änderbar
    Farbe und Muster kommen ausschließlich über data-divi-Attribute aus
    dem Stylesheet. Die Gruppen stehen in app/seed.py.
```

Dunkler Modus: Navy- und Anthrazitflächen ab `#0C1820`, nie reines
Schwarz. Auf dunklem Grund übernimmt Petrol die Hauptaktion.

## Typografie

```yaml
schrift: InterVariable, lokal ausgeliefert (344 KB, SIL OFL), kein CDN
gewichte:
  ueberschrift: 600-650
  fliesstext:   400
  label:        500
  kennzahl:     700, tabellarische Ziffern
```

## Form

```yaml
radien:
  karte:   14px        # --radius
  innen:    9px        # --radius-sm; konzentrisch: außen = innen + Abstand
  pille:  999px
ring: >
  Der unvollständige Scope-Ring ist eine Geometrie in fünf Auflösungen:
  Wortmarke, Hintergrundbogen, leere Zustände, Avatar-Rahmen, PDF-Kopf.
  Er schließt sich nirgends.
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
3. **Lime nirgendwo sonst.** Nicht für Erfolg, nicht für Akzente, nicht
   „weil noch Farbe fehlt".
4. **Farbe trägt nie allein Information.** Jede Statuspille trägt Text,
   jedes Etikett seinen Gruppennamen.
5. **Keine Zweckentfremdung der Fläche.** Keine Indikationen, keine
   Dosierungen, keine Algorithmen — auch nicht als „hilfreiche" UI-Idee.
6. **Touch-Flächen ≥ 44px**, sichtbarer Fokusring,
   `prefers-reduced-motion` wird respektiert.
7. **Budget**: JS + CSS + Schrift ≤ 700 KB, geprüft von der
   Qualitätsschleife.
