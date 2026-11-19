# SCOPE X

**Skills · Competencies · Outcomes · Procedures · Emergency eXperience**

Das Maßnahmen- und Kompetenzlogbuch für den Rettungsdienst – mit einem
geschlossenen Fachnetzwerk für Lernen, Praxisanleitung und kollegiale
Unterstützung. Selbst betrieben als Add-on für Home Assistant, ohne Cloud,
ohne Werbung, ohne Tracking. Eine private Initiative, derzeit in der
erweiterten Beta.

---

## Vision

Jede Notfallsanitäterin, jeder Notfallsanitäter und jede Praxisanleitung
weiß jederzeit, was sie oder er wirklich kann – belegt durch das eigene
Logbuch und nicht durch Erinnerung. Und niemand muss eine seltene
Situation, eine Komplikation oder eine schwere Schicht allein verarbeiten,
weil es einen geschützten Ort gibt, an dem Kolleginnen und Kollegen
voneinander lernen.

## Die Idee

Im Rettungsdienst sind die entscheidenden Maßnahmen selten. Eine
Koniotomie, eine Thoraxentlastung, eine Geburt im RTW, eine Reanimation
beim Kind – vieles davon erlebt man in einem Berufsleben eine Handvoll
Male. Wer weiß, wann er etwas zuletzt gemacht hat und wie oft es gelang,
kann gezielt üben. Wer seltene Fälle teilt, macht sie für andere weniger
selten.

SCOPE X verbindet deshalb zwei Dinge, die sonst getrennt sind:

1. **Ein privates Logbuch**: Einsätze, Maßnahmen, Medikamentengaben,
   Ergebnisse und Komplikationen, schnell erfasst und für sich selbst
   ausgewertet. Einsatznummer, Ort, Fahrzeug und Zeitpunkt sieht niemand
   außer der Person selbst – nie, auch nicht beim Teilen.
2. **Ein fachliches Netzwerk**: Feed, Profil, Chronik, Nachrichten, Bilder
   und Videos – aber um Lernen herum gebaut statt um Aufmerksamkeit.
   Fallberichte, strukturierte Fallvorstellungen mit Frage an die
   Community, Wissen mit Quelle, Kompetenzen aus dem Logbuch, die
   Kolleg*innen bestätigen können.

## Ziel

- **Kompetenz sichtbar machen**: wie oft, wie erfolgreich, wann zuletzt –
  als Zählwerte aus dem Logbuch, freigegeben je Maßnahme.
- **Lernen aus seltenen Situationen**: Fallberichte und Fallvorstellungen
  steigen im Feed, Maßnahmen, die man selbst selten dokumentiert, ebenso.
- **Praxisanleitung unterstützen**: Bestätigungen durch Praxisanleitung,
  Fortbildungsnachweis mit Jahrespflicht, Themen wie #Praxisanleitung.
- **Qualifikationen im Blick behalten**: Kurse mit Ablaufdatum (ERC,
  NAEMT, AHA), Erinnerung vor Ablauf, Abzeichen für gültige Kurse.
- **Peer-to-Peer-Hilfe**: Fragen an die Community, Einsatznachsorge als
  eigenes Thema, Nachrichten unter Kolleg*innen.
- **Datenschutz durch Bauart**, nicht durch Versprechen.

## Zielgruppe

- Notfallsanitäter*innen und Rettungssanitäter*innen
- Praxisanleiter*innen und Auszubildende im Rettungsdienst
- Notärztinnen und Notärzte, Pflegende in Notaufnahme und Intensivmedizin
- Luftrettung, Intensivtransport, Leitstelle, Wasser- und Bergrettung
- Wachen, Organisationen und Bildungsträger, die eine eigene, geschlossene
  Installation betreiben wollen

Zugang gibt es nur auf Einladung oder nach angenommener Bewerbung. Eine
Installation ist ein geschlossener Kreis.

## Was SCOPE X kann

| Bereich | Funktionen |
|---|---|
| **Logbuch** | Einsätze, Maßnahmen nach xABCDE, Medikamente mit DIVI-Etiketten, Ergebnis und Komplikationen (ZEK), NACA, Bearbeitungsfrist mit Sperre, Auswertung, Nachweise als PDF und CSV, Fortbildungsnachweis |
| **Feed** | „Für dich“ mit nachvollziehbarem Algorithmus und „Warum sehe ich das?“, „Folge ich“, „Meine Themen“, Filter nach Kompetenz-Themen |
| **Beiträge** | Text, Bilder, Videos, Fallbericht, Fallvorstellung (Meldebild → xABCDE → Maßnahmen → Frage), Algorithmus mit Pflichtquelle, Wissen mit Link, Kompetenz aus dem Logbuch, Repost |
| **Reaktionen** | Gefällt mir, Kommentieren, Repost, Senden, Speichern; hilfreiche Antwort markieren; Kommentare ausschalten |
| **Profil** | Profilbild, Titelbild, Chronik, Kompetenzen mit Bestätigungen, Info, Region, Organisation, Wache, Qualifikationen, Abzeichen; öffentlich oder privat |
| **Netzwerk** | Folgen, Folgeanfragen annehmen oder ignorieren, Vorschläge aus Wache, Organisation und Kreis, Blockieren, Direktnachrichten |
| **Suche** | Personen mit Filtern nach Kreis, Organisation, Qualifikation; Themen; Beiträge – Suchfeld auf jeder Seite |
| **Zugang** | Einladung durch die Administration, Bewerbung mit Bürgschaft, Einladung durch Mitglieder mit Entscheidung der Administration, Nutzungsvereinbarung mit Fassungen |
| **Administration** | Konten, Rollen, Einladungen, Bewerbungen, Kataloge (Organisationen, Wachen, Qualifikationen, Themen), Moderation, Stammdaten, Sicherung, Änderungsprotokoll |

## Umsetzung

- **Home-Assistant-Add-on**: ein Container, Daten unter `/data`, Updates
  über den Add-on Store. Kein Fremddienst, keine externen Skripte, Schriften
  oder Bilder.
- **Backend**: Python 3.12, FastAPI, SQLAlchemy Core, SQLite (WAL) mit
  portablem SQL; Migrationen laufen beim Start automatisch.
- **Frontend**: Vanilla JavaScript ohne Build-Schritt und ohne Framework –
  die Anwendung soll in fünf Jahren noch starten, ohne dass jemand eine
  Abhängigkeitskette aktualisieren muss. Gestaltung nach dem eigenen
  Markenhandbuch (`brand/SCOPE_X_Markenhandbuch.pdf`), mobil wie am
  Rechner. Logo, Icons und Farben liegen als Dateien in `brand/`.
- **Medien**: Bilder werden neu berechnet (Metadaten wie Aufnahmeort
  verschwinden), Videos mit ffmpeg neu codiert, Eingabeformate und
  Protokolle streng begrenzt.
- **Algorithmus**: eine gewichtete Summe aus Aktualität, Resonanz, Nähe,
  Art und Lernrelevanz, ergänzt um Abwertung bereits gesehener Beiträge,
  negative Signale, Vorrang des eigenen Netzes und Vielfalt je Person. Die
  Gründe stehen an jedem Beitrag. Optimiert wird auf Lernen, nicht auf
  Verweildauer.

## Datenschutz und Sicherheit

- Einsatznummer, Ort, Fahrzeug, Zeitpunkt, Notizen und Dosierungen
  verlassen das Logbuch nie. Geteilt wird nur über eine Allowlist; Texte
  werden auf eigene Einsatznummern, Fahrzeuge, Daten und Uhrzeiten
  geprüft.
- Passwörter mit Argon2id, Zwei-Faktor-Authentifizierung Pflicht, Passkeys,
  Arbeitsnachweis und Drosselung vor jeder Anmeldung, Herkunftsfilter.
- Verschlüsselung im Ruhezustand mit AES-256-GCM: Nachrichten, Namen,
  E-Mail-Adressen, Profilangaben, Beiträge, Einsatzkennungen, Notizen sowie
  alle Bilder und Videos; Suche nach E-Mail-Adressen über einen Blindindex.
- Ausschließlich parametrisierte SQL-Abfragen, Prüfung jeder Eingabe im
  Server, Objekte anderer antworten mit 404.
- Statische Sicherheitsanalyse mit Semgrep (OWASP Top Ten) und Prüfung der
  Abhängigkeiten mit pip-audit bei jedem Push.
- Keine personenbezogenen Daten in Protokollen; IP-Adressen nur gekürzt
  gehasht.
- Strenge Content-Security-Policy ohne Inline-Skripte und -Stile.
- Datenauskunft und Kontolöschung jederzeit selbst im Profil.
- SCOPE X gibt keine Indikationen, Dosierungen oder Algorithmen vor.
  Maßgeblich bleiben Leitlinien, die Vorgaben des ÄLRD und die SOPs vor Ort.

## Qualität

Eine Prüfschleife entlang ISO/IEC 25010:2023 läuft bei jedem Release:
funktionale Testreihen, Rollen- und Datenschutzgrenzen, Barrierefreiheit
mit axe-core in einem echten Browser, Antwortzeiten, Auslieferungsgröße,
SQL-Portabilität, Abhängigkeiten. Details in
[`scopex/QUALITAET-ISO-25010.md`](scopex/QUALITAET-ISO-25010.md) und
[`scopex/QUALITAETSPRUEFUNG.md`](scopex/QUALITAETSPRUEFUNG.md).

## Installation

Einstellungen → Add-ons → Add-on Store → Menü oben rechts →
**Repositories** → URL dieses Repositories eintragen → **Hinzufügen**.

Danach erscheint SCOPE X im Store. Bei jeder neuen Version zeigt Home
Assistant automatisch einen **Update**-Knopf. HACS wird dafür nicht
gebraucht und kann Add-ons auch nicht verwalten: dafür ist der Supervisor
zuständig. Einrichtung mit Reverse Proxy, Mailversand und erster
Anmeldung: [`scopex/README.md`](scopex/README.md).

## Aktualisieren

1. Neue Dateien in dieses Repository committen und die `version` in
   `scopex/config.yaml` erhöhen.
2. In Home Assistant im Add-on Store **Nach Updates suchen**.
3. Bei SCOPE X erscheint **Update**. Der Änderungstext kommt aus
   `scopex/CHANGELOG.md`.

Datenbankmigrationen laufen beim Start automatisch und überspringen bereits
angewendete Versionen. `/data` bleibt beim Update erhalten.

## Versionierung

Semantische Versionierung: MAJOR bei größeren oder inkompatiblen
Änderungen, MINOR für neue Funktionen, PATCH für Korrekturen. Regeln in
[`scopex/VERSIONIERUNG.md`](scopex/VERSIONIERUNG.md).

## Roadmap

- Lernpfade und Übungserinnerungen für selten dokumentierte Maßnahmen
- Gruppen für Wachen und Lehrgänge
- Auswertung für Praxisanleitung mit Einverständnis der Auszubildenden
- Export des Fortbildungsnachweises

## Quellen und Dank

- Kreise und kreisfreie Städte: Statistisches Bundesamt (Destatis),
  Gemeindeverzeichnis, Stand 31.12.2024, Datenlizenz Deutschland –
  Namensnennung – Version 2.0.
- Schrift: Inter (SIL Open Font License).
- Anregungen für Feed und Gemeinschaftsfunktionen aus den offenen
  Projekten [x-algorithm](https://github.com/xai-org/x-algorithm) und
  [Forem](https://github.com/forem/forem).

SCOPE X ist ein privates Projekt aus dem Rettungsdienst für den
Rettungsdienst.
