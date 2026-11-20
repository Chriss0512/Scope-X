# Änderungen

Versionierung nach Semantic Versioning 2.0.0, Regeln in
`VERSIONIERUNG.md`.

## 4.6.1

PATCH: neues Erscheinungsbild nach dem Markenhandbuch 2.0 und berichtigte
DIVI-Etiketten, keine neuen Funktionen. Eine Migration
(`0013_divi_relaxantien`); Endpunkte, Sicherungsformat und Add-on-Optionen
bleiben unverändert.

### Markenhandbuch 2.0

- Das Handbuch liegt überarbeitet im Repo unter `brand/`
  (`SCOPE_X_Markenhandbuch.pdf`, Quelle in `brand/handbuch/`). Berichtigt
  sind Inhaltsverzeichnis, DIVI-Darstellung, Kontrastwerte, Kontakt und
  die Beschreibung der Module; Dosierungs- und SOP-Beispiele sind
  entfernt, nicht gebaute Funktionen als geplant markiert.
- Neues Logo als Vektordatei in allen Varianten (Primär, horizontal,
  kompakt, Zeichen, App-Icon, einfarbig, hell und dunkel), Favicons in
  16 bis 64 px, App-Icons, Bilder für den Add-on-Store. Alles erzeugt
  `tools/marke_erzeugen.py`.

### Oberfläche

- **Neues Zeichen** in Navigation, Kopfzeile, leeren Zuständen und als
  Favicon; Wortmarke in Inter ExtraBold.
- **Größere Schrift:** Fließtext 16 px, Seitentitel 32 px, Kartentitel
  20 px. Kein Text in der Oberfläche ist mehr kleiner als 14 px.
- **Farben nach Handbuch:** jede Signalfarbe mit Textwert (mindestens 5 : 1)
  und Flächenwert, neue Werte für den Dunkelmodus. Frustran trägt jetzt
  weiße Schrift auf dunklerem Orange. Alle xABCDE-Buchstaben in der
  Fallvorstellung tragen ihre Kategoriefarbe.
- Radien 2 / 4 / 8 / 12 / 16 px, Schatten und Abstände als Tokens; Icons
  einheitlich mit 2 px Strich.
- Anmeldeseite und „Über SCOPE X“ kennzeichnen die erweiterte Beta und
  die private Initiative.

### DIVI-Etiketten

- **Rocuronium und Vecuronium** stehen in der neuen Gruppe
  „Muskelrelaxantien, nichtdepolarisierend“: obere Hälfte weiß, untere
  warmrot, schwarze Schrift. Vorher waren die Hälften vertauscht.
  Bestehende Installationen werden umgestellt, sofern die Zuordnung im
  Katalog nicht selbst geändert wurde.
- **Relaxans-Antagonisten** tragen zusätzlich den schwarzen Querstrich,
  **Protamin** weißen Grund mit schwarz-weiß gestreiftem Rand.
- **Weiße Schrift** nur noch bei Suxamethonium und Midazolam, mit feiner
  dunkler Kontur für die Lesbarkeit. Auf Streifen liegt der Name auf einer
  Unterlage in der Grundfarbe.
- Mindestgröße der Etikettenschrift 12 px.

### Nachweis als PDF

- Schrift Inter statt Helvetica, damit auch Namen mit Zeichen außerhalb
  von Latin-1 richtig erscheinen; neues Logo im Kopf.
- Fußzeile „Selbstdokumentation, erstellt mit SCOPE X“ mit Seite x von y.

## 4.6.0

MINOR: neue Funktionen und eine Migration (`0012_schutz_empfehlungen`).
Bestehende Endpunkte, Sicherungsformat und Add-on-Optionen bleiben
erhalten; neu ist die optionale Option `schluessel`.

### Bitte lesen: Verschlüsselung im Ruhezustand

Beim ersten Start nach dem Update legt SCOPE X einen Schlüssel an
(`/data/scopex.key`, nur für den Dienst lesbar) und verschlüsselt den
vorhandenen Bestand. Das dauert bei großen Mediensammlungen einen Moment.

- **Verschlüsselt mit AES-256-GCM:** Direktnachrichten, Namen,
  E-Mail-Adressen, Profilangaben, Beiträge, Kommentare, Werdegang,
  Fortbildungen, Einsatznummer, Fahrzeug, Schicht, Notizen zu Maßnahmen
  und Medikamenten, Bewerbungen, Einladungen, die Werte im
  Änderungsprotokoll sowie alle Bilder und Videos auf dem Datenträger.
- **Nicht verschlüsselt**, weil Auswertung, Sortierung und Sichtbarkeit
  sie brauchen: Datum und Uhrzeit von Einsätzen, Maßnahmen und Medikamente
  samt Ergebnis, NACA, Benutzernamen, Schlagwörter, Zeitstempel.
- **Wie bei großen Netzwerken:** Transport per TLS, Speicherung
  verschlüsselt, Schlüssel beim Betreiber. Das ist keine
  Ende-zu-Ende-Verschlüsselung; wer den laufenden Server und den
  Schlüssel kontrolliert, könnte lesen.
- **Den Schlüssel sichern.** Ohne ihn sind die geschützten Daten nicht
  mehr lesbar. Er liegt neben der Datenbank und ist damit in jeder
  Home-Assistant-Sicherung enthalten. Wer ihn getrennt verwahren will,
  setzt die Option `schluessel` (32 Byte Base64) **vor** dem ersten Start
  mit 4.6.0. Ein falscher oder fehlender Schlüssel lässt die Anwendung
  nicht starten, statt Daten unlesbar zu machen.
- E-Mail-Adressen werden über einen Blindindex (HMAC-SHA-256) gefunden;
  Anmeldung per E-Mail funktioniert wie bisher.
- Die JSON-Sicherung der Administration enthält weiterhin Klartext, damit
  sie sich auf jeder Installation einspielen lässt; eingespielt wird
  wieder verschlüsselt. Der Fingerabdruck des Schlüssels gehört nicht
  hinein.

### Kolleg*innen einladen

- Mitglieder laden unter **Netzwerk → Kolleg*innen einladen** per E-Mail
  ein. Daraus wird kein Konto, sondern eine **Bewerbung**: die
  eingeladene Person füllt das Formular aus, das Mitglied steht schon als
  Kontakt fest und wird **nicht noch einmal gefragt**, die
  **Administration entscheidet**.
- Kam die Bewerbung von der eingeladenen Adresse, entfällt die
  Bestätigungsmail; der Link in der Einladung hat die Adresse bestätigt.
- Höchstens fünf offene und zehn Einladungen in 30 Tagen je Mitglied,
  nicht für Gäste. Gibt es zur Adresse schon ein Konto, geht keine Mail
  raus; das Mitglied erfährt davon nichts. Einladungen lassen sich
  zurückziehen und verschwinden 90 Tage nach Ablauf.
- Die Einladungen der Administration bleiben, wie sie sind: direkt zur
  Registrierung.

### Korrekturen

- **Zurück-Knopf auf „Impressum und Datenschutz“** führte ins Leere, wenn
  die Seite der erste Eintrag des Tabs war, etwa aus dem Link im
  Bewerbungsformular, der sich in einem neuen Tab öffnete. Zurück führt
  jetzt immer zu einer Seite, und Rechtstexte öffnen sich aus Formularen
  in einem Blatt über dem Formular, das dabei erhalten bleibt.
- **Datums- und Monatsfelder auf iOS** liefen in das Nachbarfeld und
  waren höher als die übrigen Felder (Fortbildung, Qualifikationen,
  Werdegang, Einsatz). Felder im Raster halten jetzt ihre Spalte ein.
- Verknüpfungen unter Feldern („Organisation fehlt?“, „Kurs fehlt?“) sind
  als solche erkennbar.

### Neu

- **Abmelden auf jeder Seite:** in der Seitenleiste unten, auf dem
  Telefon in der Kopfzeile, jeweils mit kurzer Rückfrage.
- **„Über SCOPE X“** (`#/ueber`), öffentlich und von der Anmeldung, der
  Bewerbung und dem Seitenfuß verlinkt: was SCOPE X ist, für wen, wie man
  dazukommt, wie Daten geschützt sind.

### Sicherheitsprüfung

- Neue Prüfung in der Schleife und in der CI: **Semgrep** mit den
  Regelsätzen für Python, JavaScript und die OWASP Top Ten – dasselbe
  Werkzeug, das Cloudflare im Repository `cloudflare/advisories` für jeden
  Pull Request einsetzt. Befunde der Stufe ERROR lassen die Prüfung
  scheitern. Stand dieser Version: keine.
- Das Advisory-Repository selbst listet Schwachstellen in Produkten von
  Cloudflare. SCOPE X nutzt keines davon; die Abhängigkeiten werden wie
  bisher mit `pip-audit` gegen die öffentlichen Datenbanken geprüft.
- Neue Testreihe `test_schutz.py`: Markierwerte gehen über die API in
  jede geschützte Spalte, danach werden Datenbankdatei und WAL als Bytes
  durchsucht; jede geschützte Spalte muss das Präfix tragen; manipulierte
  Mediendateien werden nicht ausgeliefert; falscher und fehlender
  Schlüssel werden erkannt; Sicherung und Wiederherstellung; Empfehlungen.

## 4.5.0

MINOR: neue Funktionen und eine Migration (`0011_bewerbung_kataloge`).
Bestehende Endpunkte bleiben erhalten; `GET /api/netz/suche` liefert
zusätzlich Personen, Themen und Beiträge. Sicherungsformat und
Add-on-Optionen bleiben unverändert.

### Bitte beachten

- **Nutzungsvereinbarung.** Alle Mitglieder werden bei der nächsten
  Anfrage einmal gebeten, der neuen Nutzungsvereinbarung zuzustimmen.
  Bis dahin beantwortet der Server alles außer Anmeldung, Vereinbarung,
  Datenauskunft und Kontolöschung mit 428. Neue Konten stimmen bei der
  Registrierung zu. Der Text steht in `app/nutzung.py`; er ist eine
  sorgfältige Vorlage, keine Rechtsberatung, und sollte vor dem Einsatz
  für andere geprüft werden. Eine inhaltliche Änderung bekommt eine neue
  `VERSION` und löst eine erneute Zustimmung aus.
- **„Verwaltung“ heißt jetzt „Administration“**, Adresse
  `#/administration`. Alte Lesezeichen auf `#/verwaltung` leiten um.
- **Skripte und Stile werden komprimiert ausgeliefert** (nur unter
  `/assets`, nicht die API). Die Prüfschleife misst seither die
  Übertragung und getrennt die einzulesende Menge, siehe unten.

### Zugang

- **Bewerbung um Zugang** unter `#/bewerben`, verlinkt von der Anmeldung:
  Name, E-Mail, Beruf, Kreis, optional Organisation, Wache, Begründung
  und ein Mitglied, das bürgen kann. Rechenaufgabe und Drosselung wie bei
  der Anmeldung, höchstens drei Bewerbungen je Herkunft und Tag.
- **Doppelte Bestätigung**: erst nach Klick auf den Link in der Mail geht
  die Bewerbung an die Administration. Unbestätigte verfallen nach
  48 Stunden spurlos.
- **Mitglied bürgt, Administration entscheidet.** Das genannte Mitglied
  findet die Anfrage unter „Netzwerk“ und per Mail und sagt, ob es die
  Person kennt. Es sieht Name, Beruf, Region und Begründung, nie die
  E-Mail-Adresse. Antworten kann nur dieses Mitglied.
- **Gleiche Antwort für alle**: ob es die Adresse schon als Konto gibt,
  ob eine Bewerbung offen ist oder ob das genannte Mitglied existiert,
  lässt sich über das Formular nicht herausfinden. Wer schon ein Konto
  hat, bekommt eine Mail mit dem Weg zu „Passwort vergessen“.
- **Annahme nur mit frischem Code** aus der Authenticator-App, nur als
  Mitarbeiter oder Gast. Die Einladung geht an die bestätigte Adresse,
  füllt den Namen vor und übernimmt den Kreis ins Profil. Mit der
  Registrierung wird die Bewerbung gelöscht; abgelehnte und angenommene
  30 Tage nach der Entscheidung.
- Bewerbungen lassen sich in der Administration abschalten. Ohne
  Mailversand gibt es keine Bewerbung.

### Netzwerk

- **Neue Übersicht „Netzwerk“** (`#/netzwerk`, auf dem Telefon in der
  Leiste statt „Entdecken“): Bürgschaftsanfragen, Folgeanfragen mit
  **Annehmen** oder **Ignorieren**, Vorschläge mit Begründung, „Ich
  folge“, Follower, offene eigene Anfragen, Themen, Gespeichertes.
- **Ignorieren sendet kein Signal**: die Anfrage verschwindet aus Liste
  und Zähler, für die anfragende Person bleibt sie „angefragt“. Annehmen
  geht später noch.
- **Vorschläge aus Zusammenhängen**: gleiche Wache, gleiche Organisation
  im selben Kreis, gleicher Kreis (etwa „Auch Heidekreis“), gleiche
  Organisation, folgt dir, gemeinsame Kontakte, gleiche Kurse, neu im
  Netz. Ort und Kurse privater Konten fließen nicht ein, solange man
  ihnen nicht folgt. Ausgeblendete Vorschläge kommen nicht wieder. Im
  Feed erscheinen Vorschläge an fester Stelle als Karte.
- **Region, Organisation und Wache aus Listen** statt Freitext: die 400
  Kreise und kreisfreien Städte aus dem Gemeindeverzeichnis des
  Statistischen Bundesamtes (Stand 31.12.2024, Datenlizenz Deutschland –
  Namensnennung 2.0), eine Grundliste von Organisationen, Wachen
  ausschließlich aus Einreichungen der Mitglieder. Die Administration
  sichtet, benennt um und führt Doppelte zusammen.

### Qualifikationen und Fortbildung

- **Kuratierte Liste** von Berufsabschlüssen, Funktionen und Kursen
  (Praxisanleitung, OrgL, LNA, ERC BLS/ILS/ALS/EPALS/NLS, AHA BLS/ACLS/PALS,
  PHTLS, AMLS, TECC, ITLS, ATLS u. a.). Fehlendes lässt sich vorschlagen;
  frei wählbar ist es erst nach Freigabe.
- **Ablaufdaten** werden aus den Angaben der Herausgeber berechnet, soweit
  belegt: ERC drei Jahre, AHA zwei Jahre, NAEMT-Providerkurse vier Jahre.
  Wo keine belegte Angabe vorlag, steht keine Dauer. 90 Tage vor Ablauf
  kommt eine Mitteilung. Andere sehen nur gültige Einträge, keine Daten.
- **Abzeichen**: gültige Kurse und Funktionen erscheinen kurz am Namen
  (bei privaten Konten nur für Follower).
- **Fortbildungsnachweis** im Logbuch (`#/fortbildung`), privat: Stunden je
  Jahr, angerechnet auf eine Qualifikation, mit Pflichtstand, etwa
  24 Stunden berufspädagogische Fortbildung für Praxisanleitung
  (NotSan-APrV § 3).

### Beiträge

- **Fallvorstellung** als eigene Beitragsart: Meldebild → Befund nach
  xABCDE → Maßnahmen → Frage an die Community. Nur Altersgruppe, kein
  Alter; dieselbe Prüfung auf Uhrzeiten, Einsatznummern und Fahrzeuge wie
  überall. Antworten sind Kommentare; die fragende Person markiert die
  hilfreichste, sie steht dann oben.
- **Themen als Kompetenz-Routing**: kuratierte Themen wie
  #Atemwegsmanagement, #EKG-Quiz, #Recht-2aNotSanG, #Praxisanleitung,
  #Luftrettung, #Intensivverlegung, #Peer-to-Peer-Hilfe. Beim Teilen
  wählbar, im Feed als Filter, „Meine Themen“ als eigener Reiter, Themen
  lassen sich folgen. Die Administration pflegt die Liste.
- **Kommentare ausschalten** durch Autor*in (auch schon beim Teilen) oder
  Administration. Hat die Administration geschlossen, kann nur sie wieder
  öffnen.
- **Speichern**: Beiträge anderer merken, Liste unter `#/gespeichert`.
  Merken verschafft keinen Zugriff: was nicht mehr sichtbar ist, fällt
  heraus.

### Suche

- **Eigene Seite** `#/suche` für Personen, Themen und Beiträge, mit
  Filtern nach Kreis, Organisation und Qualifikation. Leer zeigt sie, was
  es zu entdecken gibt.
- **Suchfeld auf jeder Seite** direkt am Logo: in der Seitenleiste unter
  dem Logo, auf dem Telefon in einer Kopfzeile mit Mitteilungen und
  Nachrichten.

### „Für dich“

Nach dem Vorbild offen dokumentierter Feed-Systeme ergänzt, weiterhin
als nachvollziehbare gewichtete Summe:

- Bereits Ausgeliefertes sinkt je Auslieferung (höchstens dreimal).
- Beiträge von außerhalb des eigenen Netzes zählen 85 %.
- „Nicht interessiert“ wirkt auf weitere Beiträge derselben Person
  (75 % je Ausblendung, mindestens 40 %).
- Gemerkte Beiträge sind das stärkste positive Signal.
- Gefolgte Themen heben die Relevanz; offene Fallvorstellungen steigen in
  den ersten drei Tagen; neue Mitglieder bekommen einen kleinen Zuschlag.
- „Warum sehe ich das?“ nennt die neuen Gründe.

### Datenschutz

- Datenauskunft enthält Region, Qualifikationen, Fortbildungen,
  Gespeichertes, gefolgte Themen, ausgeblendete Vorschläge, Gesehenes,
  Zustimmungen und eigene Einreichungen. Kontolöschung entfernt all das;
  eingereichte Katalogeinträge bleiben ohne Personenbezug.
- Die JSON-Sicherung der Administration enthält Kataloge, Bewerbungen und
  Zustimmungen nicht, wie schon die übrigen Netztabellen; das
  Home-Assistant-Backup sichert `/data` vollständig.

### Qualität

- Neue Testreihe `test_zugang.py` (Vereinbarung, Bewerbung, Bürgschaft,
  Kataloge, Vorschläge und Suchfilter bei privaten Konten, Ignorieren,
  Themen, Fallvorstellung, Kommentare aus, Speichern, Löschung).
- Rollenprüfung um die neuen Administrationsrouten erweitert.
- Barrierefreiheit auf den neuen Seiten geprüft. Die Messung des
  Seitenendes ignoriert jetzt den Inhalt geschlossener Aufklappbereiche,
  den Chromium mit Layout versieht, obwohl er nicht zu sehen ist.
- Auslieferungsgröße: Übertragung höchstens 500 KB (komprimierte Skripte
  und Stile plus Schrift), einzulesen höchstens 480 KB Skript und Stil.
  Vorher zählten die unkomprimierten Bytes gegen 700 KB.

## 4.4.0

MINOR: neue Funktion mit neuen Endpunkten unter `/api/netz/` und einer
Migration (`0010_netzwerk`). Bestehende Endpunkte, Sicherungsformat und
Add-on-Optionen bleiben unverändert. Die Migration läuft beim Start
automatisch; vorhandene Daten bleiben unberührt.

### Sicherheit — bitte lesen

**Sicherung war für jedes Mitglied abrufbar.** `GET /api/exports/backup`
prüfte nur, ob jemand angemeldet ist. Jedes Mitglied konnte damit die
Logbücher **aller** Mitglieder herunterladen — mit Einsatznummern,
Fahrzeugen, Zeitpunkten und Notizen. Der Fehler bestand seit der
Mehrbenutzerfähigkeit. Die Sicherung verlangt jetzt die
Administrationsrolle; eine neue Prüfung in der Berechtigungsreihe legt
ein markiertes Admin-Logbuch an und stellt sicher, dass es bei einem
Mitglied nicht ankommt. Mit der alten Fassung schlägt sie an.

Empfehlung: im Änderungsprotokoll nach Einträgen `exports … backup`
suchen, die nicht von einem Administrationskonto stammen.

Im selben Zug:

- **Wiederherstellung behält die Zuordnung.** Bis 4.3.1 wurden beim
  Einspielen alle Einsätze und Profile dem wiederherstellenden Konto
  zugeschrieben. Jetzt behalten sie ihren Besitzer; nur verwaiste
  Datensätze gehen an das wiederherstellende Konto.
- **ZEK auf Einsatzebene in der Sicherung.** `encounter_complications`
  fehlte seit 4.0 in Sicherung und Wiederherstellung und ging dabei still
  verloren.
- **Pillow 13.0.0** als direkte Abhängigkeit (11.3.0 hatte vier bekannte
  Schwachstellen). Neue Bilder werden ausschließlich darüber verarbeitet.

### Kompetenznetz

Ein soziales Netz für beruflichen Support in der Notfallmedizin, nach dem
Muster großer Bild- und Berufsnetzwerke. Abgeschaltet, bis ein
Mitglied es selbst einschaltet; das Logbuch funktioniert ohne es
unverändert.

- **Feed** mit zwei Reitern: **Für dich**, sortiert von einem
  nachvollziehbaren Algorithmus, und **Folge ich**, chronologisch. An
  jedem Beitrag steht unter „Warum sehe ich das?“, warum er erscheint.
- **Algorithmus** (`app/algorithmus.py`): gewichtete Summe aus
  Aktualität, Resonanz, Nähe zur Person, Art des Beitrags und Relevanz für
  das eigene Lernen. Fallberichte zu seltenen Situationen und
  Komplikationen sowie Maßnahmen, die man selbst selten oder nie
  dokumentiert hat (Lernlücke), steigen. Danach Vielfalt: jeder weitere
  Beitrag derselben Person zählt weniger. „Nicht interessiert“ blendet
  einen Beitrag aus.
- **Beitragsarten**: Beitrag (Text, bis zu zehn Bilder oder Videos),
  **Fallbericht** (seltene Situation, Komplikation, Lernfall; was war
  besonders, was lief gut, was würde ich anders machen; optional Einträge
  aus dem Logbuch), **Algorithmus** (SOP oder Ablaufschema mit
  Pflichtquelle, Stand und Geltungsbereich), Wissen (Studie, Leitlinie),
  Kompetenz (Einträge aus einem eigenen Einsatz) und Repost.
- **Reaktionen** wie in Bildnetzwerken: Gefällt mir, Kommentieren, Repost,
  Senden.
- **Folgen** wie in Bildnetzwerken: öffentliche Konten (innerhalb der
  Installation) oder private Konten mit Folgeanfrage. Dazu
  **Blockieren**: keine Sicht, kein Folgen, keine Nachricht in beide
  Richtungen.
- **Profil** mit Titelbild, Profilbild, Zahlen, Kurzbeschreibung und
  Reitern Beiträge (Raster), **Chronik** (Beiträge und Lebensstationen
  in einer Zeitleiste), Kompetenzen (belegt durch das Logbuch,
  bestätigbar bei gegenseitigem Folgen) und **Info** (persönliche
  Angaben, Werdegang, Ausbildung, Zertifikate mit Gültigkeit, Sprachen).
- **Entdecken**: Raster aus dem ganzen Netz, Suche nach Personen, Wachen
  und #Hashtags, eigene Seiten je Hashtag.
- **Nachrichten**: Direktnachrichten mit Text, Bildern und gesendeten
  Beiträgen, Ordner „Anfragen“ für Personen, die einem nicht folgen,
  „gesehen“, Zurücknehmen, Ausblenden. Am Rechner zweispaltig.
- **Mitteilungen** mit Folgeanfragen, gruppiert nach Heute, Woche, Monat.
- **Medien**: Bilder werden mit Pillow neu codiert (Beitragsbilder 4:5
  bis 1,91:1), Videos mit ffmpeg aus `imageio-ffmpeg` (H.264/AAC,
  höchstens 90 Sekunden, Metadaten und Daten- und Untertitelspuren
  verworfen). Videos werden im Hintergrund verarbeitet; ein Neustart
  markiert unterbrochene Verarbeitungen als fehlgeschlagen. ffmpeg nimmt
  nur die Containerformate von Telefonen und Kameras an (MP4, MOV, 3GP,
  Matroska, WebM) und nur lokale Dateien: eine als Video getarnte
  Wiedergabeliste kann keine Serverdateien einlesen. Dateien liegen
  unter `/data/media` und damit im Add-on-Backup.
- **Moderation**: gemeldete Beiträge sehen Administrator*innen und können
  sie mit Begründung entfernen; der Vorgang steht im Änderungsprotokoll.

### Neuer Aufbau und Gestaltung

- **Leiste** auf dem Telefon: Feed · Entdecken · Neu · Logbuch · Profil.
  Mitteilungen und Nachrichten oben rechts im Feed. Am Rechner eine
  helle Seitenleiste mit allen Punkten einschließlich Auswertung und
  Verwaltung.
- **Logbuch** fasst Einsätze, Auswertung und Nachweise unter einem Reiter
  zusammen. Die Auswertung bleibt vollständig erhalten.
- **Neu** fragt, was entstehen soll: Beitrag, Fallbericht, Algorithmus,
  Studie, Kompetenz oder Einsatz dokumentieren.
- Beiträge randlos und ohne Kartenrahmen, Aktionen als Symbole, Feed am
  Rechner als schmale Spalte mit Vorschlägen rechts. Weniger Rahmen und
  Schatten insgesamt, Einstellungen mit Schaltern im iOS-Stil.
- Die frühere Profilseite heißt jetzt **Einstellungen**; das Profil ist
  die Seite im Netz.

### Datenschutzgrenze

Einsatznummer, Fahrzeug, Schicht, Datum und Uhrzeit eines Einsatzes,
Dosierungen, Notizen und Patientenschaden verlassen das eigene Logbuch
nie. Durchgesetzt im Server, nicht in der Oberfläche:

- Kompetenz- und Fallbeiträge übernehmen Logbuchdaten nur als Kopie aus
  einer Allowlist; `net_posts` hat keine Spalte, die auf einen Einsatz
  verweist.
- Beiträge, Falldetails, Kommentare, Link-Titel, Profiltexte und
  Werdegang mit eigener Einsatznummer, eigenem Fahrzeug, eigenem
  Einsatztag oder einer Uhrzeit werden abgelehnt. In Direktnachrichten
  nur die Einsatznummer, sonst wäre keine Terminabsprache möglich.
- Vor dem Teilen von Bildern oder Videos muss bestätigt werden, dass
  keine Patient*innen, Kennzeichen, Einsatzorte oder Monitorwerte mit
  Personenbezug zu erkennen sind.
- Fallberichte erscheinen voreingestellt erst nach sieben Tagen.
- Benutzername und E-Mail-Adresse anderer werden nie ausgegeben; nicht
  sichtbare Objekte antworten mit 404.
- Die Testreihe `test_netz.py` legt einen Einsatz mit eindeutigen
  Markierwerten in jedem privaten Feld an und durchsucht Feed, Entdecken,
  Profil, Chronik, Beitrag, Hashtag-Seite, Nachrichten und Mitteilungen
  danach. Sie prüft außerdem private Konten, Blockieren, Nachrichten,
  das Entfernen von EXIF- und GPS-Daten aus Bildern sowie von Orts- und
  Titelangaben aus Videos.

### Sonst

- Stammdaten, rechtliche Angaben und Sicherung sind in die Verwaltung
  gewandert. Im Profil wurden sie allen angezeigt, benutzen durfte sie nur
  die Administration.
- Auskunft (Art. 15 DSGVO) enthält alle Netzdaten einschließlich Bildern,
  Videos und Nachrichten; Kontolöschung entfernt sie vollständig, auch
  Gespräche beim Gegenüber.
- Datenschutzerklärung um das Kompetenznetz ergänzt, einschließlich
  Algorithmus und unverschlüsselter Nachrichten.
- Die Netzdaten gehören nicht in die eigene Sicherung; sie verknüpfen
  die Daten mehrerer Mitglieder. Das Add-on-Backup von Home Assistant
  enthält Datenbank und Mediendateien.
- **Nginx Proxy Manager**: für Videos muss `client_max_body_size` auf
  mindestens `210m` stehen (bisher `25m`), siehe README.
- Neue Abhängigkeit `imageio-ffmpeg` 0.7.0 (statisches ffmpeg für amd64
  und aarch64, keine apt-Pakete nötig).
- Neue Oberflächendatei `netz.js`, vor `app.js` geladen. Die
  Prüfschleife zählt beide gegen das Größenbudget und prüft Feed,
  Entdecken, Nachrichten, Mitteilungen, Logbuch und Einstellungen auf
  Barrierefreiheit.

## 4.3.1

PATCH: Fehlerbehebung ohne neue Felder, Endpunkte oder Optionen.

**Seitenende auf Mobilgeräten nicht erreichbar.** Auf Telefonbreite lag
der Inhalt unter der Navigationsleiste; selbst bei maximaler Scrolltiefe
blieben die letzten 29 bis 37 Pixel verdeckt — auf jeder Seite,
gemessen in Feed, Auswertung, Profil, Verwaltung und Rechtlichem.

Ursache war die Reihenfolge im Stylesheet, nicht die Leiste selbst. Der
mobile Block setzte die Leiste auf `position: relative`, damit sie als
Teil der Flex-Spalte unter dem Inhalt liegt. Die Grundregel mit
`position: fixed` stand aber **danach**, bei gleicher Spezifität — und
die spätere Regel gewinnt. Die Leiste schwebte damit über dem
Inhaltsbereich statt unter ihm. Der Fehler bestand seit 4.1.0; die
Flex-Spalte, die damals die überlagerte Leiste beheben sollte, hat nie
gegriffen. Mit der höheren Leiste aus 4.3.0 wurde er erst richtig
sichtbar.

- Der mobile Block steht jetzt hinter den Grundregeln, mit einem Hinweis
  im Stylesheet, warum er dort stehen muss.
- Die Prüfschleife misst bei jedem Lauf auf Telefonbreite, ob das Ende
  jeder Seite oberhalb der Leiste liegt. Mit der alten Reihenfolge schlägt
  sie auf allen fünf Seiten an.
- Der Knopf zum Seitenanfang ist jetzt rund und ohne Text. Als
  Textpille hatte er Tabellenwerte in der Auswertung verdeckt; die
  Beschriftung trägt weiterhin `aria-label`.

## 4.3.0

MINOR: deutliche Erweiterung der Oberfläche ohne Änderung an Endpunkten,
Sicherungsformat oder Migrationspfad. Keine Migration, keine neuen
Optionen. Die Oberfläche gehört laut `VERSIONIERUNG.md` nicht zur
öffentlichen Schnittstelle; ein Umbau dieser Größe ist dennoch mehr als
ein PATCH, weil sich die Bedienung spürbar ändert.

**Neuer Aufbau.** Struktur nach dem Feed-Muster, Ruhe und Kacheln nach
dem Vorbild von Notfallguru, Hierarchie, Tiefe und konzentrische Radien
nach den Apple-Prinzipien — bei unveränderter SCOPE-X-Farbwelt. Die
Herkunft der Prinzipien und alle Werte stehen in der neuen `DESIGN.md`.

- **Tab-Leiste**: Einsätze · Auswertung · **Neu** (mittig als angehobene
  Scheibe, beginnt die Dokumentation von jeder Seite aus) · Profil ·
  Verwaltung. Der Verwaltungspunkt existiert nur für Administrator*innen.
- **Einsätze-Feed** als Startseite: jeder Einsatz eine Beitragskarte mit
  Ringmarke, Zeitpunkt, Schicht und Fahrzeug, Frist-Chip und
  Inhalts-Chips. Null-Werte erscheinen nicht. Die frühere getrennte
  Erfassen-Seite entfällt, alte Lesezeichen auf `#/neu` laufen im Feed
  auf.
- **Eigene Profilseite**: Kopf mit Initialen im Scope-Ring,
  Qualifikation, Kennzahlenzeile; darunter Segmentschalter Konto ·
  Sicherheit · Erfassung · Daten. Die Karten tragen ihre Gruppe über die
  Überschrift, nicht über ihre Position — eine eingeschobene Karte
  sortiert sich selbst richtig ein.
- **Eigene Verwaltungsseite** unter `#/verwaltung` statt als Anhängsel
  des Profils: Konten, Einladungen, Betrieb, Zugang zum
  Änderungsprotokoll. Die Rollenprüfung der Seite ist Bedienkomfort;
  jede Verwaltungsroute prüft serverseitig selbst.
- **Kachel-Katalog beim Erfassen**: Maßnahmen als Kacheln mit
  Kategorie-Seitenlinie und Suchfeld, Medikamente mit dem
  DIVI-Etikettenband als Kachelkopf — die Auswahl in der App sieht aus
  wie die Spritze in der Hand. Favoriten und Zuletzt bleiben erhalten.
- Dashboard heißt in der Oberfläche **Auswertung**; die PDF-Nachweise
  sind von dort verlinkt statt eines eigenen Leistenpunkts.
- Barrierefreiheits-Audit läuft jetzt zusätzlich über die
  Verwaltungsseite.

## 4.2.0

MINOR: neue Add-on-Optionen mit Vorgabewerten und ein neuer Endpunkt.
Bestehende Endpunkte, Sicherungsformat und Migrationspfad bleiben
unverändert, es läuft **keine Migration**.

Diese Fassung ist die Antwort auf eine veränderte Lage: SCOPE X bleibt
bewusst aus dem offenen Netz erreichbar, ohne Access List im Reverse
Proxy. Damit trägt der Anmeldeweg die gesamte Last, und das hielt er in
der bisherigen Form nicht aus.

### Die Anmeldung konnte ausgespäht werden

- **Laufzeit verriet, welche Konten es gibt.** Bei unbekanntem
  Anmeldenamen kam die Abweisung sofort, bei bekanntem erst nach einem
  vollständigen Argon2id-Durchlauf mit 64 MiB und drei Durchgängen. Der
  Unterschied liegt bei mehreren Zehntelsekunden und ist aus dem offenen
  Netz mühelos messbar. Die Fehlermeldung war immer dieselbe, die
  Antwortzeit nicht. Jetzt läuft bei unbekanntem Konto ein Leerlauf-Hash
  mit demselben Aufwand.
- **Statuscodes verrieten denselben Umstand.** Ein gesperrtes Konto
  antwortete mit 429, ein stillgelegtes mit 403, ein unbekanntes mit 401.
  Nach außen gibt es jetzt genau eine Antwort; der Grund steht
  ausschließlich im Änderungsprotokoll.

### Die Kontosperre war selbst eine Waffe

Acht falsche Passwörter sperrten ein Konto fünfzehn Minuten — von jeder
Adresse aus. Aus dem offenen Netz genügte damit ein Skript in zwei
Zeilen, um alle Nutzer dauerhaft auszusperren, mitten im Dienst. Eine
Maßnahme, die der Angreifer gegen den Besitzer richten kann, schützt
niemanden.

- Die automatische kontoweite Sperre **entfällt**. An ihre Stelle tritt
  eine exponentiell wachsende Abkühlung **je Adresse und Konto**, bis
  fünfzehn Minuten: der Angreifer bremst nur sich selbst aus, der
  rechtmäßige Nutzer bleibt von seinem eigenen Anschluss unbehelligt.
- Die Benachrichtigung ab acht Fehlversuchen bleibt und sagt jetzt, was
  tatsächlich geschieht. Gezählt werden auch Versuche, die schon an der
  Abkühlung scheitern — sonst käme ein langsamer Angreifer nie bis zur
  Warnschwelle und der Besitzer erführe von einem Angriff gar nichts.
- Eine Sperre von Hand bleibt möglich, über die Verwaltung und über das
  neue Wiederherstellungswerkzeug.
- Wird ein Konto freigegeben oder sein Passwort zurückgesetzt, fallen
  Fehlversuchszähler, Sperrfrist und Abkühlung mit weg. Ohne das bliebe
  ausgerechnet die Person draußen, die ein Fremder ausgebremst hat.

### Neue Schichten vor der Anmeldung

- **Herkunftsprüfung.** Neue Option `laenderfilter`, Vorgabe `europa`:
  die 27 EU-Staaten, die EFTA, das Vereinigte Königreich mit den
  Kronbesitzungen, die europäischen Kleinstaaten sowie Gibraltar, Färöer,
  Grönland und Åland. Nicht enthalten sind Russland und Belarus, der
  Balkan außerhalb der EU, die Ukraine, Moldau und die Türkei. Grundlage
  ist eine Netzliste im Image mit 36.781 IPv4- und 18.420 IPv6-Netzen,
  erzeugt aus den Delegationsdateien von RIPE NCC und ARIN durch
  `tools/netzliste_erzeugen.py`. Zur Laufzeit wird nichts nachgeladen.
  Fehlt die Liste, wird durchgelassen und gewarnt: eine Prüfung, die bei
  einem Datenfehler den rechtmäßigen Nutzer aussperrt, richtet mehr
  Schaden an als der Scanverkehr, den sie abhält. Über `zusatznetze`
  lassen sich einzelne Netze freigeben, etwa für einen Aufenthalt
  außerhalb Europas.
- **Drosselung.** Höchstens 30 Anmeldeanfragen je Adresse in zehn
  Minuten, einstellbar über `anfragen_je_fenster` für den Fall, dass
  mehrere Personen hinter demselben Anschluss sitzen.
- **Rechenaufgabe.** Anmeldung, Registrierung und Reset-Anforderung
  tragen einen Arbeitsnachweis: finde eine Zahl, deren SHA-256 mit genug
  Nullbits beginnt. Die Schwierigkeit wächst mit den Fehlversuchen des
  Kontos, von 12 auf höchstens 16 Bit. Für eine einzelne Anmeldung sind
  das Millisekunden bis etwa eine Sekunde, für Zehntausende Versuche der
  Unterschied zwischen billig und teuer. Die Aufgabe trägt ihr eigenes
  HMAC-Siegel, ist einmal verwendbar und übersteht einen Neustart. Im
  Browser steht SHA-256 ausgeschrieben, weil `crypto.subtle` nur
  asynchron arbeitet und in einer Suchschleife ein Vielfaches kostet;
  die Umsetzung ist gegen die Standardbibliothek von Python geprüft,
  einschließlich der Blockgrenzen bei 55, 56 und 64 Byte.

### Passkeys zuerst

Die Passkey-Anmeldung steht jetzt über dem Passwortformular. Sie ist der
einzige Weg, der sich weder abfischen noch durchprobieren lässt: der
Schlüssel verlässt das Gerät nie und ist an genau diese Domain gebunden.
Das Passwort bleibt als zweiter Weg erhalten.

### Basis-Adresse ohne Schema

`scopex.example.de` ergibt in `urlparse` weder Schema noch Host. Passkeys
lehnten deshalb mit 503 ab und die Links in den Mails waren nicht
anklickbar — ohne dass irgendwo ein Fehler erschien. Lautlos war der
Ausfall wegen eines zweiten, schwächeren Tests: die Oberfläche fragte
`available` ab, das lediglich prüfte, ob die Variable gesetzt war. Sie
meldete „verfügbar", während der Endpunkt ablehnte.

- `core.base_url()` normalisiert zentral und ergänzt ein fehlendes Schema.
- `passkeys_available()` stellt dieselbe Prüfung an wie der Endpunkt.
- `run.sh` schreibt die wirksame Adresse beim Start ins Protokoll, mit
  Warnung bei fehlendem Schema oder `http`.

### Weiterleitungs-Header

`uvicorn` lief mit `--forwarded-allow-ips='*'`, jeder Client durfte also
`X-Forwarded-Proto` und `X-Forwarded-For` selbst setzen. Weil Port 8099
auf dem Host veröffentlicht ist, erreicht ein Gerät im LAN den Container
direkt, am Reverse Proxy vorbei. Schwerer wog, dass `_is_secure()` und
der HSTS-Header den **Rohheader** zusätzlich selbst auslasen und die
Vertrauensliste damit vollständig umgingen: das Secure-Flag der
Sitzungscookies war von außen steuerbar, und ohne dieses Flag kann ein
Sitzungscookie über eine unverschlüsselte Verbindung zum selben Host
abfließen.

Beide Stellen benutzen jetzt `request.url.scheme`, das uvicorn nur für
Gegenstellen aus der neuen Option `trusted_proxies` ableitet (Vorgabe
`172.30.32.0/23`, das Supervisor-Netz). Erst dadurch ist überhaupt eine
verlässliche Herkunftsprüfung möglich — vorher hätte jeder Scanner sein
Land frei behaupten können.

### Passwörter

- Prüfung gegen 10.038 häufige Passwörter und Wortstämme, mitgeliefert im
  Image, ohne externen Aufruf. Geprüft wird auch der Stamm: `passwort2026`
  fällt über `passwort`. Bei zwölf Zeichen Mindestlänge ist genau das der
  Normalfall, ein kurzes Wort mit angehängter Jahreszahl.
- Abgelehnt werden außerdem Passwörter mit weniger als fünf
  verschiedenen Zeichen und solche, die den eigenen Benutzernamen oder
  den lokalen Teil der E-Mail-Adresse enthalten.
- Beim Zurücksetzen wird die Prüfung erst nach dem Nachschlagen des
  Kontos ausgeführt, weil sie den Benutzernamen braucht.

### Wiederherstellung vom Server aus

Neu: `python -m app.wiederherstellung`. Konten auflisten, entsperren,
freigeben, zweiten Faktor entfernen, Passwort setzen, Rolle vergeben.
Jeder Eingriff landet als `wiederherstellung:*` im Änderungsprotokoll,
ohne Urheber-Kennung — hier hat sich niemand angemeldet, sondern jemand
mit Zugriff auf den Server gehandelt. Nach einem Eingriff in die
Anmeldedaten werden alle Sitzungen beendet und alle Geräte vergessen.

Das schließt eine Sackgasse, die mit jeder Härtung wahrscheinlicher wird:
wer Authenticator und Wiederherstellungscodes zugleich verliert, kam
bisher nicht mehr in sein Konto, auch nicht über „Passwort vergessen",
denn auch die Zurücksetzung verlangt den zweiten Faktor.

Bewusst ein Kommandozeilenwerkzeug und kein Notzugang über das Netz: ein
Endpunkt, der den zweiten Faktor aushebeln kann, wäre auf einem öffentlich
erreichbaren Dienst genau die Hintertür, gegen die der ganze Rest gebaut
ist.

### Unbekannte Pfade, robots.txt, security.txt

- Der Catch-all beantwortete jeden Pfad außer `api/` mit 200 und der
  vollständigen Oberfläche. Im Protokoll war zu sehen, wie ein Scanner
  `/.env`, `/.env.local`, `/.env.production`, `/.env.bak`,
  `/credentials.json`, `/service-account.json` und `/.git/HEAD` abfragte
  und auf jede dieser Anfragen 200 oder 206 bekam. Die Oberfläche
  navigiert ausschließlich über den Fragmentteil, der den Server nie
  erreicht — er braucht genau einen Pfad: `/`. Alles andere antwortet
  jetzt mit 404.
- `robots.txt` hält Suchmaschinen fern. `/.well-known/security.txt` nennt
  nach RFC 9116 eine Anlaufstelle, aus der neuen Option `kontakt` oder
  ersatzweise dem Impressum; im Protokoll war zu sehen, dass die Datei
  tatsächlich abgefragt wird.

### Weiteres

- Vertrauenswürdige Geräte verfallen nach 30 statt 90 Tagen.
- Mail bei erfolgreicher Anmeldung von einem unbekannten Gerät. Bisher
  wurde nur der **gescheiterte** Angriff gemeldet, der gelungene blieb
  still. Die Nachricht nennt bewusst weder Adresse noch Ort.
- `/api/health` gibt zusätzlich die Version aus, weiterhin ohne jede
  Angabe über den Datenbestand.
- `fpdf2` von 2.8.2 auf 2.8.9 wegen CVE-2026-114609. Der wöchentliche
  Lauf hatte die Lücke am 2. November selbst gemeldet.
- GitHub Actions auf `checkout@v5`, `setup-python@v6`,
  `upload-artifact@v5`; Runner auf `ubuntu-24.04` festgenagelt, damit die
  Umgebung nicht unangekündigt auf Ubuntu 26 wandert.
- Die Prüfschleife vergleicht die Version in `config.yaml` mit
  `app/main.py`. Die stand von der Erstfassung bis hierher unbemerkt auf
  `1.0.0`, weil nichts den Abgleich erzwang.
- `axe.min.js` und die Ergebnisdateien des Laufs stehen jetzt in
  `.gitignore`.

### Nicht betroffen

- CVE-2026-109618 und CVE-2026-109619 (PHP2Shell): SCOPE X enthält kein
  PHP.
- Die Node-Lücken vom Oktober 2026 einschließlich CVE-2026-111497 im
  Brotli-Decoder: `python:3.12-slim`, kein Node, kein npm, kein
  Build-Schritt. Die Oberfläche ist reines JavaScript im Browser.

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
