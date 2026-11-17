# Architektur: SCOPE X Kompetenznetz

Nach der Methode von `replica-architect`. Grundlage: `recon.md`,
`features.csv`.

## Stack

Der vorhandene, aus gutem Grund. Python 3.12, FastAPI, SQLAlchemy Core,
SQLite mit WAL, Vanilla-JS ohne Build-Schritt. Eine Datenbank, kein neuer
Dienst. Einzige neue Abhängigkeit: **Pillow**, um hochgeladene Bilder neu zu
codieren und dabei alle Metadaten zu verwerfen.

## Die Datenschutzgrenze

Die eine Regel, an der alles hängt: **Einsatznummer, Einsatzdatum,
Einsatzuhrzeit, Schicht, Fahrzeug, die Zeitstempel einzelner Maßnahmen und
Medikamentengaben, Freitext-Notizen, Dosierung und Patientenschaden
verlassen das private Logbuch nie.**

Durchgesetzt nicht durch Filtern, sondern durch Bauart:

1. **Keine Spalte dafür.** Die Tabelle `net_posts` hat keine Spalte, in der
   eines dieser Felder landen könnte. Ein Beitrag hält einen
   *Schnappschuss* der freigegebenen Werte, keinen Verweis auf den Einsatz —
   auch keine `encounter_id`. Wer den Beitrag liest, kann nicht einmal
   zurückverfolgen, aus welchem Einsatz er stammt.
2. **Allowlist beim Erzeugen.** Der Kompetenzbeitrag wird aus einer festen
   Liste von Feldern gebaut: Maßnahme, Kategorie, Ergebnis, Rolle bei der
   Durchführung, Medikament mit DIVI-Gruppe, Applikationsweg; optional ZEK
   (nur Bezeichnung) und NACA. Alles, was nicht auf der Liste steht, wird
   nicht gelesen.
3. **Abgleich des Freitexts.** Der Beitragstext wird gegen die eigenen
   Einsatznummern und Fahrzeugkennungen geprüft. Ein Treffer weist den
   Beitrag ab. Uhrzeiten im Muster `hh:mm` werden ebenfalls abgewiesen.
4. **Test über die gesamte Antwort.** Die Testreihe legt Einsätze mit
   eindeutigen Markierwerten an, teilt sie und durchsucht anschließend
   **jede** Antwort, die ein Kontakt erhält, als Zeichenkette nach diesen
   Werten.

Der Veröffentlichungszeitpunkt selbst wird relativ angezeigt („vor 2 Std."),
bewusst so entschieden. Der Composer weist darauf hin, dass ein Beitrag
direkt nach dem Einsatz dessen Zeitpunkt verrät.

## Sichtbarkeit

| Was | Fremdes Mitglied | Kontakt | Selbst |
| --- | --- | --- | --- |
| Name, Kopfzeile, Profilbild | ja, wenn Netzwerk aktiv | ja | ja |
| Kopfbild, Über mich | nein | ja | ja |
| Kompetenzen mit Anzahl | nein | nur freigegebene | alle |
| Beiträge | nein | ja | ja |
| Kontaktliste | nein | nein | ja |
| Privates Logbuch | nie | nie | ja |

Ein Mitglied ohne aktiviertes Netzwerkprofil ist für andere unsichtbar,
auch in der Suche. Voreinstellung ist **inaktiv**: wer nichts tut, dessen
Daten bleiben, wie sie in 4.3 waren.

Administrator*innen haben im Netzwerk keine Sonderrechte beim Lesen. Sie
können Beiträge und Kommentare **entfernen**, mit Pflichtbegründung im
Änderungsprotokoll — für den Fall, dass jemand Patientendaten teilt.

## Schema (Migration 0010_netzwerk)

```
user_profile        + headline, about, net_active, avatar_id, banner_id

net_media           id, user_id, kind (avatar|banner), mime, data BLOB,
                    width, height, created_at

net_connections     id, requester_id, addressee_id,
                    status (pending|accepted), created_at, accepted_at
                    UNIQUE(requester_id, addressee_id)

net_posts           id, author_id, kind (text|wissen|kompetenz), body,
                    link_url, link_title, link_source,
                    snapshot (JSON der freigegebenen Werte),
                    created_at, removed_at, removed_reason

net_reactions       id, post_id, user_id, kind (stark|lehrreich|danke),
                    created_at
                    UNIQUE(post_id, user_id)

net_comments        id, post_id, author_id, body, created_at,
                    removed_at, removed_reason

net_competencies    user_id, measure_id, visible        (Freigabe je Kompetenz)

net_endorsements    id, user_id, measure_id, endorser_id,
                    role (kollegial|praxisanleitung), created_at
                    UNIQUE(user_id, measure_id, endorser_id)

net_notifications   id, user_id, kind, actor_id, post_id, created_at, read_at
```

Alle Schlüssel als UUID-Text, wie im Rest der Anwendung. Indizes auf jeden
Fremdschlüssel und auf `created_at` für den Feed.

## Endpunkte

Alle unter `/api/netz/`, alle verlangen Anmeldung.

```
GET    /profil                      eigenes Netzwerkprofil
PUT    /profil                      Kopfzeile, Über mich, Aktivierung
PUT    /kompetenzen/{measure_id}    Sichtbarkeit einer Kompetenz
POST   /medien/{kind}               Bild hochladen (avatar|banner)
DELETE /medien/{kind}
GET    /medien/{id}                 Bild ausliefern, sichtbarkeitsgeprüft
GET    /personen?q=                 Mitgliedersuche (nur aktive Profile)
GET    /personen/{id}               Profil, Umfang je Beziehung
GET    /kontakte                    Kontakte und offene Anfragen
POST   /kontakte/{id}               Anfrage senden (bei Gegenanfrage: annehmen)
POST   /kontakte/{id}/annehmen
DELETE /kontakte/{id}               ablehnen, zurückziehen oder entfernen
GET    /feed                        Beiträge von Kontakten und eigene
POST   /beitraege                   Text, Wissen oder Kompetenz
DELETE /beitraege/{id}              eigener Beitrag; Administrator*in mit Grund
PUT    /beitraege/{id}/reaktion     setzen oder ändern
DELETE /beitraege/{id}/reaktion
GET    /beitraege/{id}/kommentare
POST   /beitraege/{id}/kommentare
DELETE /kommentare/{id}
POST   /bestaetigungen              Kompetenz eines Kontakts bestätigen
DELETE /bestaetigungen/{id}
GET    /mitteilungen
POST   /mitteilungen/gelesen
```

Jede Route prüft serverseitig, ob der Aufrufer das Objekt sehen darf. Ein
nicht sichtbares Objekt antwortet mit 404, nicht mit 403 — wie im Rest der
Anwendung, damit sich Existenz nicht erfragen lässt.

## Reihenfolge

1. Migration und Sichtbarkeitsfunktion (`darf_sehen`)
2. Profil und Kontakte — ohne sie sieht niemand etwas
3. Beiträge mit Datenschutzgrenze und deren Tests
4. Reaktionen, Kommentare, Mitteilungen
5. Bestätigungen
6. Bilder
7. DSGVO-Auskunft und -Löschung, Sicherung
8. Oberfläche
