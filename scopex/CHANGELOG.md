# Änderungen

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
