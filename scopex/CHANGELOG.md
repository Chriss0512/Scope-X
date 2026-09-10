# Änderungen

Versionierung nach Semantic Versioning 2.0.0, Regeln in
`VERSIONIERUNG.md`.

## 4.1.0

**Versionierung**

- `VERSIONIERUNG.md` legt die öffentliche Schnittstelle verbindlich fest:
  Sicherungsformat, Add-on-Optionen, HTTP-Endpunkte und Migrationspfad.
  Alles andere, insbesondere Oberfläche und interne Struktur, gehört
  ausdrücklich nicht dazu.
- Die Prüfschleife erzwingt die Regeln: gültiges SemVer, Abschnitt im
  Änderungsprotokoll, höhere Nummer als zuvor, und ein Abgleich der
  61 API-Pfade gegen die letzte Fassung. Verschwindet ein Pfad oder springt
  das Sicherungsformat ohne MAJOR, schlägt die Prüfung fehl.
- Offen dokumentiert: die Sprünge auf 2.0.0, 3.0.0 und 4.0.0 waren
  SemVer-Verstöße und hätten 1.2.0, 1.3.0 und 1.4.0 heißen müssen.
  Zurückversioniert wird nicht, weil Home Assistant ein Update nur bei
  höherer Nummer anbietet.

**Impressum und Datenschutz**

- Telefonnummer als Pflichtangabe nach § 5 Abs. 1 Nr. 2 DDG, dazu Felder
  für Berufsbezeichnung, zuständige Stelle und berufsrechtliche Regelung
  nach Nr. 5 für reglementierte Berufe.
- Verweis auf Impressum, Datenschutz und Barrierefreiheit im Fuß **jeder**
  Seite. Damit ist die Anbieterkennzeichnung von überall mit einem Klick
  erreichbar; § 5 DDG verlangt höchstens zwei.
- Abschnitt zu Cookies: ausschließlich technisch notwendige, deshalb nach
  § 25 Abs. 2 TDDDG kein Einwilligungsdialog.
- Abschnitt zu Server-Protokollen und zur Speicherung von Herkunftsdaten
  als gekürzter Hashwert.
- Freiwillige Erklärung zur Barrierefreiheit mit Stand der Umsetzung und
  benannten Einschränkungen.

**Auskunft und Löschung**

- Vollständiger Datenauszug nach Art. 15 und 20 DSGVO, im Profil
  selbst herunterladbar. Enthält Konto, Profil, alle Einsätze mit
  Maßnahmen, Parametern, Medikamentengaben und ZEK, Einstellungen und das
  Änderungsprotokoll. Zugangsmittel sind bewusst nicht enthalten.
- Kontolöschung nach Art. 17 DSGVO ohne Umweg über einen Administrator.
  Verlangt Passwort, Code und ein getipptes Bestätigungswort. Das
  Änderungsprotokoll bleibt bestehen, verliert aber den Personenbezug. Der
  letzte aktive Administrator kann sich nicht löschen.

**Änderungsprotokoll**

- Eigene Seite unter `#/protokoll` mit vollständigem Zeitstempel bis zur
  Sekunde und serverseitigem Blättern. Vorher stand es als Karte im Profil
  und hätte diese Seite mit wachsender Länge unbenutzbar gemacht.
- Vorgänge und Objekte werden in Klartext übersetzt statt als interne
  Bezeichner angezeigt.

**Dashboard**

- Liniendiagramm für die Entwicklung über die Zeit, Ringdiagramme für die
  Verteilung nach xABCDE und nach NACA. Reines SVG ohne Bibliothek, Farben
  aus der Markenpalette statt aus einem Regenbogen.

## 4.0.0

**Passkeys mit Biometrie**

- Anmeldung per Passkey nach WebAuthn, entsperrt über Face ID, Touch ID,
  Windows Hello oder die Geräte-PIN. Ersetzt Passwort und Code in einem
  Schritt.
- Phishing-resistent, weil der Schlüssel an die Domain gebunden ist und auf
  einer nachgebauten Seite gar nicht erst antwortet. Der private Schlüssel
  verlässt das Gerät nie.
- Nutzerverifikation ist verpflichtend: ein Passkey ohne Biometrie oder PIN
  wird abgelehnt. `sign_count` erkennt geklonte Authentifikatoren.
- Verwaltung im Profil: Passkeys anlegen, benennen und entfernen. Passwort
  und Zwei-Faktor bleiben immer als Weg bestehen, ein Konto kann sich also
  nicht aussperren.
- Voraussetzung ist eine hinterlegte Basis-Adresse mit HTTPS. Fehlt sie,
  meldet die Oberfläche das ausdrücklich, statt eine Anmeldung anzubieten,
  die scheitern müsste.
- Die kryptografische Prüfung übernimmt py_webauthn. Signaturprüfung und
  CBOR-Auswertung selbst zu schreiben wäre genau die Art von
  Sicherheitscode, die man nicht selbst schreibt.

**DIVI-Spritzenetiketten nach Standardtabelle**

- 22 Wirkungsgruppen statt bisher 14, alle 60 ausgelieferten Wirkstoffe sind
  zugeordnet. Neu darunter Antiarrhythmika, Antikonvulsiva,
  Bronchodilatatoren, Inodilatatoren, Hormone, Antikoagulantien, Heparin und
  Protamin.
- Schrägstreifen bei allen drei Antagonistengruppen, schwarzer Rahmen bei
  Heparin.
- Die Zuordnung eines Wirkstoffs bleibt im Katalog änderbar; selbst
  angelegte Wirkstoffe werden bei der Migration nicht überschrieben.

**Behobener Anzeigefehler**

- Auf schmalen Displays überlagerte die Navigationsleiste den Inhalt der
  Impressumsseite. Ursache: die Klasse für Anmeldeseiten stellte das Layout
  auf `display: block` um und hob damit die Reihenfolge der Flex-Spalte auf,
  wodurch die Leiste an den Seitenanfang rutschte. Der Zustand der Hülle
  wird jetzt bei jedem Seitenwechsel an einer Stelle festgelegt.

## 3.1.0

**Qualitätsschleife**

- `quality/run_quality.py` prüft 24 automatisierbare Anforderungen entlang
  der neun Charakteristiken von ISO/IEC 25010:2023 und schreibt einen
  Bericht. Rückgabewert ungleich null, sobald eine Prüfung fehlschlägt.
- Sechs Punkte erscheinen ausdrücklich als **manuell offen** und zählen
  nicht als bestanden: Penetrationstest, Screenreader-Audit, Risikoanalyse
  nach ISO 14971, Verschlüsselung im Ruhezustand, Betriebsüberwachung und
  die Prüfung gegen MariaDB. Ein Bericht, der Menschenarbeit als erledigt
  ausweist, wäre schlimmer als keiner.
- GitHub-Actions-Workflow bei jedem Push, jedem Pull Request und wöchentlich,
  damit neu veröffentlichte Schwachstellen auch ohne Codeänderung auffallen.

**Im ersten Durchlauf gefunden und behoben**

- Vier Kontrastverstöße nach WCAG: Slate als Textfarbe erreichte auf Weiß nur
  4,41:1, die Statusfarben für erfolgreich und fehlgeschlagen trugen weiße
  Schrift bei 3,9 beziehungsweise 4,2:1. Textfarben sind jetzt abgedunkelt,
  Orange trägt dunkle Schrift und hat für Text auf hellem Grund eine eigene
  Variante. Die Markenpalette bleibt unverändert.
- Zwei Abhängigkeiten mit bekannten Schwachstellen aktualisiert.
- 62 Befunde der statischen Analyse, darunter `zip()` ohne `strict` und
  Ausnahmen ohne `from`.

**DIVI-Spritzenetiketten**

- Das Etikett wird in der Wirkstoffauswahl und im Erfassungsformular
  abgebildet: Hintergrundfarbe der Wirkungsgruppe, Wirkstoffname in
  Versalien, Schrägstreifen bei Antagonisten, zweifarbig bei
  nichtdepolarisierenden Relaxanzien. Wirkstoffe ohne Zuordnung erscheinen
  schraffiert.
- Gruppen feiner aufgelöst: depolarisierende und nichtdepolarisierende
  Relaxanzien getrennt, Antagonisten tragen die Streifen ihrer Bezugsgruppe.
- Reine Abbildung zur Wiedererkennung. SCOPE X erzeugt keine druckbaren
  Etiketten und ist keine Etikettierungsreferenz. Die Farbwerte sind
  Annäherungen an die Pantone-Vorgaben und nicht normativ.

## 3.0.0

**Behobener Fehler mit Sicherheitsbezug**

- Der Zähler für fehlgeschlagene Anmeldungen wurde in derselben Transaktion
  hochgezählt, in der anschließend eine Exception flog, und dadurch stets
  zurückgerollt. Die Kontosperre hat seit Version 1 nie ausgelöst. Zähler
  und Sperre werden jetzt in einer eigenen Transaktion geschrieben. Dieselbe
  Falle beim Nachstempeln der Bearbeitungssperre ist ebenfalls behoben.
- Neu: Bei einer Sperre nach acht Fehlversuchen geht eine Nachricht an die
  hinterlegte Adresse, sofern die Kennung zu einem Konto gehört. Für
  unbekannte Kennungen wird nichts verschickt, und die Nachricht nennt weder
  Zeitpunkt noch Herkunft der Versuche.

**Erfassung**

- Medikamentengaben haben jetzt dieselbe Ergebnisachse wie Maßnahmen, dazu
  Felder für beobachtete Nebenwirkung und für eine dadurch erforderliche
  weitere Intervention. Bestandsdaten gelten als erfolgreich.
- ZEK lassen sich direkt am Einsatz erfassen, für Ereignisse ohne Bezug zu
  einer einzelnen Maßnahme.
- Bereits erfasste Maßnahmen und Medikamentengaben sind innerhalb der Frist
  über eine eigene Schaltfläche bearbeitbar.
- Einsätze tragen Schichtkürzel und Fahrzeugkennung.
- Nur noch eine Bearbeitungsfrist je Einsatz statt eines Countdowns pro
  Eintrag. Die Frist des Einsatzes gilt für alles darin.
- Datum und Alarmzeit werden beim Anlegen ausdrücklich abgefragt.
- Durchführungsart ist mit „eigenverantwortlich" vorbelegt.
- Punktionsort beim intravenösen Zugang als Auswahlliste.

**Medikamentenkatalog**

- Farbgruppe der Spritzenetiketten nach EN ISO 26825 und DIVI-Empfehlung als
  bearbeitbares Feld. Vorbelegt nur, wo die Zuordnung eindeutig ist; alles
  Übrige bleibt offen. Reine Dokumentationsangabe, keine Vorgabe für die
  Etikettierung.
- Optionale Handelsnamen je Wirkstoff.

**Oberfläche**

- Die Navigationsleiste bleibt auf iOS auch bei geöffneter Tastatur stehen.
  Die Höhe kommt jetzt aus `visualViewport`, dem einzigen dort verlässlichen
  Wert.
- Sprung zum Seitenanfang bei jedem Seitenwechsel, dazu eine Schaltfläche
  bei größerer Scrolltiefe.
- Das Code-Feld auf der Anmeldeseite erscheint nur, wenn es gebraucht wird.
  Bei hinterlegtem Gerät bleibt es weg.
- Verweis auf Impressum und Datenschutz von der Startseite aus, ohne
  Anmeldung erreichbar.
- Qualifikationen und Rollenbezeichnungen geschlechtsneutral.

**Dokumentation**

- Qualitätsbericht mit Abbildung auf ISO/IEC 25010:2023, einschließlich der
  offenen Punkte je Charakteristik.

## 2.0.0

**Rollen und Zugänge**

- Rollenmodell mit Gast, Mitarbeiter und Administrator. Jede schreibende
  Route prüft die Rolle serverseitig; das bestehende Konto wird bei der
  Migration Administrator.
- Registrierung nur noch mit gültiger Einladung. Codes werden ausschließlich
  als Hash gespeichert und einmal im Klartext angezeigt.
- Administrationsbereich: Konten einsehen, Rollen ändern, Konten sperren,
  Zurücksetzungs-Links erzeugen, Einladungen verwalten.
- Eingriffe in fremde Konten verlangen einen frischen Code aus der
  Authenticator-App. Ein Vertrauensgerät hilft dabei ausdrücklich nicht.
- Der letzte aktive Administrator kann sich nicht selbst entmachten.

**Anmeldung**

- Passwort-Hashing auf Argon2id umgestellt. Bestehende scrypt-Hashes werden
  bei der nächsten Anmeldung still gehoben, niemand muss sein Passwort
  ändern.
- Passwort vergessen über einen Link per Mail. Der Link allein genügt nicht:
  zusätzlich ist der zweite Faktor nötig.
- Vertrauensgerät: auf Wunsch entfällt der TOTP-Code bei der Anmeldung für
  90 Tage. Im Profil einsehbar und jederzeit widerrufbar.
- Automatische Abmeldung bei Leerlauf, serverseitig durchgesetzt, vom
  Administrator einstellbar.

**Betrieb**

- SMTP-Zugangsdaten als Add-on-Optionen, Passwortfeld maskiert.
- Ohne Mailversand bleibt alles nutzbar: Einladungen und
  Zurücksetzungs-Links lassen sich anzeigen und von Hand weitergeben.

## 1.1.0

- Anmeldung wahlweise über Benutzername oder E-Mail-Adresse, unabhängig von
  Groß- und Kleinschreibung. Beide Angaben stehen sichtbar im Profil.
- Datentabellen laufen auf schmalen Displays nicht mehr über den Kartenrand.

## 1.0.0

- Erste Fassung: Erfassung, Dashboard, PDF-Nachweis, Sicherung und
  Wiederherstellung, Zwei-Faktor-Authentifizierung, Bearbeitungssperre mit
  Änderungsprotokoll.
