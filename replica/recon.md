# Recon map: LinkedIn (Web, Mobil) → SCOPE X Kompetenznetz

Scope: Feed, Profil, Kontakte, Kompetenzen mit Bestätigung, Reaktionen,
Kommentare, Mitteilungen — zugeschnitten auf ein geschlossenes
Kompetenz- und Lernnetzwerk für den Rettungsdienst.
For: die eingeladenen Mitglieder einer SCOPE-X-Instanz.
Date: 2026-11-17

Erstellt nach der Methode von `replica-recon` (Jakeschincariol/replica-skill,
MIT). Clean-room: nur öffentliche Quellen, kein Login in fremde Konten, kein
Quellcode, keine privaten Schnittstellen, keine Screenshots im Produkt.
Übernommen werden **Funktionen und Abläufe**, nie Name, Logo, Farben, Texte
oder Inhalte des Originals. SCOPE X behält seine eigene Designsprache
(`scopex/DESIGN.md`).

## Sources

| # | source | URL | notes |
| --- | --- | --- | --- |
| 1 | Help: Reaktionen | https://www.linkedin.com/help/lms/answer/101466 | Reaktionsarten statt eines einzelnen Likes |
| 2 | Blog: Einführung der Reaktionen | https://blog.linkedin.com/2019/april-/11/introducing-linkedin-reactions-more-ways-to-express-yourself | Begründung: professionellere Rückmeldung als „Gefällt mir" |
| 3 | Help: Skill endorsements | https://www.linkedin.com/help/linkedin/answer/31888 | Bestätigung nur durch Kontakte |
| 4 | Help: Endorsements verwalten | https://www.linkedin.com/help/linkedin/answer/88215 | Empfänger steuert, was angezeigt wird |
| 5 | Help: Einladungen | https://www.linkedin.com/help/linkedin/answer/4800 | Anfrage, ausstehend, annehmen, ignorieren, zurückziehen |
| 6 | TechCrunch zu den Reaktionen | https://techcrunch.com/2019/04/11/linkedin-adds-a-range-of-reactions-to-spur-more-engagement-in-conversations | Reaktionsarten und Ziel |

Nicht genutzt: das eigene Konto des Auftraggebers (nicht nötig, die Muster
sind öffentlich dokumentiert), App-Store-Screenshots.

## Core loop

Ein Mitglied teilt einen Lernmoment — eine selbst durchgeführte Maßnahme,
eine Studie, eine Leitlinie, eine Neuigkeit —, sein Netzwerk reagiert,
kommentiert und bestätigt Kompetenzen, die durch das eigene Logbuch belegt
sind.

**Der Unterschied zum Original, und der Grund, warum das hier mehr ist als
eine Kopie:** Eine Kompetenz auf LinkedIn ist eine Selbstauskunft. Eine
Kompetenz in SCOPE X ist durch dokumentierte Maßnahmen gedeckt — „i.o.-Zugang,
14× dokumentiert, 2 Bestätigungen, davon 1 Praxisanleitung".

## Screens

| ID | screen | route | purpose | key components | states seen |
| --- | --- | --- | --- | --- | --- |
| S01 | Feed | `#/feed` | Beiträge des eigenen Netzes | Composer-Karte, Beitragskarte, Reaktionsleiste, Kommentare | leer (kein Netz), leer (Netz ohne Beiträge), gefüllt, Netzwerk inaktiv |
| S02 | Beitrag verfassen | Sheet aus S01, S07, Leiste | Text, Wissen, Kompetenz teilen | Segment, Textfeld, Linkfelder, Auswahl der Maßnahmen, Teilbarkeitsliste | leer, Fehler (private Angabe im Text), gesendet |
| S03 | Person | `#/person/{id}` | Profil eines Mitglieds | Kopfbild, Avatar, Kopfzeile, Kontaktknopf, Kompetenzen, Beiträge | fremd, Anfrage gesendet, Anfrage erhalten, Kontakt, eigenes |
| S04 | Kontakte | `#/kontakte` | Netz pflegen | Suche, eingehende/ausgehende Anfragen, Kontaktliste | leer, gefüllt |
| S05 | Mitteilungen | `#/mitteilungen` | Reaktionen, Kommentare, Anfragen, Bestätigungen | Mitteilungszeile, ungelesen-Markierung | leer, gefüllt |
| S06 | Profil → Netzwerk | `#/profil`, Segment Netzwerk | eigenes öffentliches Profil verwalten | Aktivierung, Bilder-Upload, Kopfzeile, Über mich, Kompetenz-Sichtbarkeit | inaktiv, aktiv |
| S07 | Einsatz | `#/einsatz/{id}` | Teilen einer Maßnahme | Teilen-Knopf je Maßnahme | — |

## Flows

```
F01 Netzwerk aktivieren
    S06 Aktivieren -> Kopfzeile, Bild -> Speichern
    happy path clicks: 3
    edge: Bild zu groß, kein Bildformat, Bild mit GPS-Metadaten

F02 Vernetzen
    S04 Suche -> S03 Vernetzen -> (andere Seite) S05 -> Annehmen
    happy path clicks: 4
    edge: doppelte Anfrage, Anfrage an sich selbst, gegenseitige Anfrage,
          Anfrage an inaktives Netzwerkprofil, Zurückziehen

F03 Kompetenz aus einem Einsatz teilen
    S07 Teilen -> S02 (vorbelegt) -> Reflexion -> Teilen -> S01
    happy path clicks: 3
    edge: fremde Maßnahme (IDOR), Einsatznummer/Fahrzeug im Text,
          gestrichene Maßnahme, Schicht oder Uhrzeit im Text

F04 Studie oder Leitlinie teilen
    Leiste + -> S02 Wissen -> Titel, Quelle, Link -> Teilen
    happy path clicks: 4
    edge: javascript:-Link, Link ohne Schema, kein Titel

F05 Reagieren und kommentieren
    S01 Reaktion / Kommentar
    happy path clicks: 1 / 2
    edge: Beitrag nicht sichtbar, Kommentar auf gelöschten Beitrag

F06 Kompetenz bestätigen
    S03 Kompetenz -> Bestätigen (als Kolleg*in oder Praxisanleitung)
    happy path clicks: 2
    edge: kein Kontakt, sich selbst, verborgene Kompetenz, doppelt

F07 Moderation
    S01 Beitrag eines anderen -> Entfernen (nur Administrator*in)
    edge: Begründung Pflicht, Änderungsprotokoll
```

## Components

| component | variants | states | used on |
| --- | --- | --- | --- |
| Beitragskarte | Text, Wissen, Kompetenz | eigen, fremd, entfernt | S01, S03 |
| Reaktionsleiste | Stark, Lehrreich, Danke | keine, eigene gesetzt | S01, S03 |
| Avatar | mit Bild, Initialen im Scope-Ring | klein (32), mittel (44), groß (88) | überall |
| Kontaktknopf | Vernetzen, Ausstehend, Annehmen, Vernetzt | — | S03, S04 |
| Kompetenzzeile | mit Zahl, mit Bestätigungen | eigene, fremde | S03, S06 |
| Mitteilungszeile | ungelesen, gelesen | — | S05 |
| Linkkarte | Studie, Leitlinie, Artikel | — | S01 |

## Inferred data model

```
Profil       headline, about, avatar, banner, netz_aktiv
             evidence: Profilkopf, Help 88215
             confidence: high

Verbindung   requester, addressee, status (pending|accepted), created, accepted
             evidence: Help 4800 (annehmen, ignorieren, zurückziehen)
             confidence: high

Beitrag      author, kind, body, link, Kompetenz-Schnappschuss, created
             evidence: Feed, Composer
             confidence: high

Reaktion     post, user, kind — eine je Person und Beitrag
             evidence: Help 101466
             confidence: high

Kommentar    post, author, body, created, removed
Bestätigung  user, measure, endorser, role
             evidence: Help 31888 (nur Kontakte bestätigen)
             confidence: high
Mitteilung   user, kind, actor, post, created, read
```

## Feature matrix

See `features.csv`. Must: 24, should: 7, could: 3, skip: 9.

## Out of scope (cannot or should not be cloned)

- Name, Logo, Blau, Wortlaut und Ikonografie des Originals.
- Das Netzwerk selbst und seine Mitglieder.
- Stellenanzeigen, Recruiting, Premium, Werbung, Unternehmensseiten,
  Gruppen, Video/Live, Direktnachrichten.
- Algorithmischer Feed mit Engagement-Optimierung. SCOPE X sortiert
  chronologisch. Ein Feed, der auf Verweildauer optimiert, hätte in einem
  Werkzeug für Kompetenznachweis keinen Platz.
- Linkvorschau mit Abruf der Zielseite: wäre ein externer Aufruf zur
  Laufzeit und ein SSRF-Risiko. Links werden mit Titel und Quelle von Hand
  erfasst.

## Size

Screens 7, flows 7, entities 7. Hard parts: die Datenschutzgrenze zwischen
privatem Logbuch und geteiltem Beitrag, Bild-Uploads ohne Metadaten,
Sichtbarkeitsregeln über das Kontaktmodell, Löschung und Auskunft nach
DSGVO über alle neuen Tabellen. Size: M.
