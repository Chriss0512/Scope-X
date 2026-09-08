# SCOPE X

Das Maßnahmen- und Kompetenzlogbuch für den Rettungsdienst.

Lokale Web-App zur persönlichen Dokumentation und Nachweisführung praktisch
durchgeführter Maßnahmen. Kein Einsatzprotokoll, keine Patientenakte, kein
Entscheidungsunterstützungssystem. Die Anwendung schlägt keine Indikationen
vor, empfiehlt keine Dosierungen und zeigt keine Algorithmen.

Ausgeliefert als lokales Home-Assistant-Add-on ohne Ingress und ohne
Sidebar-Eintrag. Home Assistant liefert nur den Container-Lebenszyklus und
das Backup, in der HA-Oberfläche taucht SCOPE X nicht auf.

---

## 1. Dateien auf den Server bringen

Der Ordner `scopex` gehört nach `/addons/scopex` auf dem HA-Server. Du hast
drei Add-ons installiert, mit denen das geht:

**Samba share** — im Netzwerk die Freigabe `addons` öffnen und den Ordner
`scopex` hineinkopieren. Der bequemste Weg.

**Studio Code Server** — falls `/addons` dort nicht sichtbar ist, in der
Add-on-Konfiguration unter `folders` den Eintrag `addons` ergänzen.

**Terminal & SSH** — Archiv nach `/share` legen und entpacken:

```sh
mkdir -p /addons
tar -xzf /share/scopex-addon.tar.gz -C /addons
ls /addons/scopex
```

Danach muss die Struktur so aussehen:

```
/addons/scopex/
├── config.yaml
├── Dockerfile
├── run.sh
├── requirements.txt
└── app/
    ├── main.py  db.py  core.py  security.py  seed.py  analytics.py  pdf.py
    ├── routers/
    └── static/   index.html  app.css  app.js
```

## 2. Add-on installieren

1. Einstellungen → Add-ons → Add-on Store
2. Rechts oben im Menü **Nach Updates suchen** (lädt lokale Add-ons neu)
3. Ganz oben erscheint der Abschnitt **Local add-ons** mit **SCOPE X**
4. Öffnen, **Installieren**. Der erste Build dauert einige Minuten, weil das
   Python-Image gezogen und die Abhängigkeiten installiert werden.
5. **Starten**, danach im Protokoll prüfen: `SCOPE X startet` und
   `Uvicorn running on http://0.0.0.0:8099`

Beim ersten Start werden Datenbankschema und Stammdaten angelegt: 38
Maßnahmen mit ihren Parameterdefinitionen, 60 Wirkstoffe und 55 ZEK-Einträge.

## 3. Nginx Proxy Manager

Neuer **Proxy Host**, Reiter *Details*:

| Feld | Wert |
|---|---|
| Domain Names | `scopex.deine-domain.de` (vollqualifiziert, kein bloßes `scopex`) |
| Scheme | `http` |
| Forward Hostname / IP | `local-scopex` |
| Forward Port | `8099` |
| Access List | eigene Liste, nicht „Publicly Accessible" |
| Websockets Support | an |
| Block Common Exploits | an |

`local-scopex` ist der Container des Add-ons. Nicht `homeassistant` eintragen,
das ist der Home-Assistant-Core-Container, dort lauscht auf 8099 nichts. Den
tatsächlichen Hostnamen bestätigt das Terminal-Add-on:

```sh
ha addons info local_scopex | grep -i hostname
```

Reiter *SSL*: Zertifikat anfordern, dazu **Force SSL**, **HTTP/2 Support** und
**HSTS Enabled**.

**Trust Upstream Forwarded Proto Headers** bleibt **aus**, solange NPM direkt
vom Client angesprochen wird. Sonst vertraut nginx einem Header, den der
Client selbst setzen kann. Nur einschalten, wenn ein weiterer Proxy davor
steht, etwa ein Cloudflare-Tunnel.

Reiter *Advanced*, **Custom Nginx Configuration** — genau eine Zeile, ohne
Code-Zaun, ohne Backticks:

```
client_max_body_size 25m;
```

Ohne diese Zeile scheitert das Einspielen einer Sicherung an der
Standard-Uploadgrenze.

Was dort **nicht** hineingehört, sind `proxy_set_header`-Direktiven. NPM
schreibt den Inhalt dieses Feldes außerhalb des `location`-Blocks, wo sie
nicht greifen, und für Header hängt NPM den Wert an den bestehenden an,
statt ihn zu ersetzen. Nötig sind sie ohnehin nicht: NPM setzt
`X-Forwarded-Proto` in seiner eigenen `proxy.conf` bereits korrekt, und
genau daran erkennt SCOPE X die HTTPS-Terminierung.

**Fehlersuche.** Meldet der Dialog „Internal Error", hat der nginx-Test
fehlgeschlagen. Häufigste Ursachen: Backticks oder Markdown-Zäune im
Advanced-Feld, ein Domainname ohne Punkt, oder eine Zertifikatsanforderung
für einen Namen, den Let's Encrypt nicht auflösen kann. Speichert der Host,
liefert aber 502, dann läuft das Add-on nicht oder der Forward Hostname
stimmt nicht.

**Kein öffentlicher Zugriff gewünscht?** Ein gültiges Zertifikat braucht
trotzdem einen echten Namen. Mit einer Domain bei Cloudflare geht das über
*Use DNS Challenge*: Zertifikat per DNS-01, ohne dass der Dienst von außen
erreichbar sein muss. Dazu in NPM eine *Access List* mit deinem LAN und dem
Tailscale-Bereich anlegen und dem Proxy Host zuweisen.

## 4. Erste Anmeldung

Beim ersten Aufruf legst du das Konto an. Anmelden kannst du dich danach
wahlweise mit dem Benutzernamen oder, falls hinterlegt, mit der
E-Mail-Adresse. Groß- und Kleinschreibung spielt dabei keine Rolle. Beide
Angaben stehen jederzeit unter Profil und Einstellungen im Abschnitt
Anmeldedaten. Es gibt genau eines, keine
Selbstregistrierung für weitere Personen und keine Passwort-Zurücksetzung
per E-Mail.

Direkt danach kommt die Zwei-Faktor-Einrichtung: QR-Code scannen mit Google
Authenticator, Aegis, 2FAS, Microsoft Authenticator oder einer anderen
TOTP-App, dann einen Code zur Bestätigung eingeben. Anschließend erscheinen
zehn Wiederherstellungscodes. **Sichere sie sofort.** Ohne Authenticator und
ohne diese Codes gibt es keinen Weg zurück ins Konto.

Wichtig für TOTP: Die Uhr des HA-Servers muss stimmen. `ntp_synchronized`
ist bei dir aktiv, damit passt das.

## 5. Was wo liegt

| Was | Wo |
|---|---|
| Datenbank | `/data/scopex.db` im Add-on-Container |
| In HA-Backups | ja, `/data` ist Teil jedes Add-on-Backups |
| Eigenes Backup | Profil & Einstellungen → Sicherung herunterladen |
| Zugangsdaten im Backup | nein, bewusst nicht |

Die eigene Sicherung enthält Stammdaten, Profil, Einsätze, Maßnahmen,
Medikamentengaben, ZEK-Verknüpfungen, Einstellungen und das
Änderungsprotokoll. Passwort-Hash, TOTP-Secret und Wiederherstellungscodes
fehlen absichtlich: eine abhandengekommene Sicherungsdatei gibt damit
niemandem Zugriff auf das Konto. Für den vollständigen Wiederherstellungsfall
inklusive Anmeldung ist das HA-Add-on-Backup zuständig.

## 6. Bearbeitungssperre

Neue Einträge sind 120 Minuten lang änderbar, konfigurierbar unter
Einstellungen von einer Minute bis zu 10080 Minuten, also sieben Tagen. Ab
vier Stunden erscheint eine Warnung, und die eingestellte Frist wird im
PDF-Nachweis ausgewiesen: ohne diese Angabe kann der Leser nicht
einschätzen, wie lange ein Eintrag rückwirkend änderbar war, und genau das
bestimmt die Belastbarkeit des Dokuments. Danach wird der Eintrag automatisch gesperrt: nicht mehr
änderbar, nicht mehr löschbar, weiterhin vollständig lesbar. Jede Änderung
innerhalb der Frist landet feldweise im Änderungsprotokoll mit Zeitpunkt,
altem und neuem Wert. Das Protokoll kann über die Anwendung nur gelesen
werden, es gibt keinen Endpunkt zum Löschen.

## 7. Ergebnis und Komplikationen

Das Ergebnisfeld beantwortet nur eine Frage: hat die Maßnahme ihr Ziel
erreicht?

- **erfolgreich**
- **fehlgeschlagen**
- **abgebrochen** — bewusst beendet, etwa beim Umstieg auf ein anderes
  Verfahren. Kein Misserfolg der Technik.

Alles, was mit Komplikationen zusammenhängt, hängt an der einzelnen
ZEK-Zuordnung, nicht am Ergebnis:

- **Bezug**: `begleitend` oder `ursächlich`
- **Patientenschaden**: `kein Schaden erkennbar`, `vermutet` oder `gesichert`

Beim Erfassen kostet das nichts, solange keine ZEK gesetzt ist. Erst wenn du
eine zuordnest, erscheinen die beiden Felder, vorbelegt mit `begleitend` und
`kein Schaden erkennbar`.

Dashboard und PDF berechnen daraus sieben Auswertungskategorien, von
„Erfolgreich, ohne Komplikationen" bis „Fehlgeschlagen, Komplikation
ursächlich". Diese Kategorien werden **nicht gespeichert**. Dadurch kann es
keinen Datensatz geben, der als komplikationsfrei markiert ist und trotzdem
eine ZEK trägt.

`frustran` gibt es nicht mehr. Der Wert war von `fehlgeschlagen` praktisch
nicht zu unterscheiden. Vorhandene Einträge werden beim ersten Start der
neuen Version auf `fehlgeschlagen` abgebildet, jeder einzelne mit einem
Eintrag im Änderungsprotokoll, sodass nachvollziehbar bleibt, dass der Wert
so nicht erfasst wurde.

## 8. Aktualisieren

Dateien in `/addons/scopex` ersetzen, dann im Add-on **Neu erstellen**
(Rebuild). Migrationen laufen beim Start automatisch und überspringen bereits
angewendete Versionen. Die Datenbank bleibt erhalten.

## 9. Datenschutz

Es werden keine Namen, Geburtsdaten oder Anschriften erfasst. Die
Einsatznummer ist optional und dient nur dazu, mehrere Maßnahmen desselben
Einsatzes zu verknüpfen.

Trotzdem: Einsatznummern und Freitextfelder können je nach Verwendung einen
Personenbezug herstellen, weil die Leitstelle die Nummer auflösen kann. Halte
Freitext knapp und trage dort keine Patientendaten ein. Ob und in welchem
Umfang du solche Aufzeichnungen führen darfst, richtet sich nach den Vorgaben
deines Arbeitgebers.

## 10. Technische Eckpunkte

Python 3.12, FastAPI, SQLite über SQLAlchemy Core, Frontend ohne Framework
und ohne Build-Schritt. Passwort-Hashing mit `hashlib.scrypt` aus der
Standardbibliothek, TOTP nach RFC 6238 selbst implementiert, QR-Codes über
`segno`, PDF über `fpdf2`. Zur Laufzeit gibt es keine externen Aufrufe: die
Content-Security-Policy erlaubt ausschließlich `'self'`, es gibt kein CDN,
kein Tracking, keine Telemetrie.

Der Wechsel auf MariaDB ist eine Zeile: `SCOPEX_DATABASE_URL` im Dockerfile
auf `mysql+pymysql://scopex:PASSWORT@core-mariadb:3306/scopex` setzen und
`pymysql` in `requirements.txt` ergänzen. Alle Primärschlüssel sind
UUID-Textfelder, dialektspezifisches SQL kommt nicht vor.

## 11. Designsystem

**Farbrollen.** Deep Navy `#102533` trägt Navigation, Hauptaktion und
Wortmarke. Medical Petrol `#126878` führt jede Interaktion: Buttons, Links,
aktive Chips, Balken. Clinical Cyan `#19A6B5` sitzt im Scope-Ring und in
Zweitdiagrammen. Signal Lime `#B9D936` erscheint an genau drei Stellen — im X
der Wortmarke, im X des App-Icons und als 2 px-Marker am aktiven
Navigationspunkt. Nirgendwo sonst.

**Status.** Erfolgreich `#2E8B68`, Fehlgeschlagen `#C94C4C`, Abgebrochen
`#D9862C`, ZEK `#A63D4A`, Information `#3973B9`, Neutral `#7B8890`. Die
Farbe für Abgebrochen entspricht dem Wert, der im Designsystem als Frustran
geführt wurde; der Ergebniswert selbst existiert seit Abschnitt 7 nicht mehr.
Jede Statuspille trägt zusätzlich Text — Farbe allein codiert nie eine
Information.

**xABCDE.** Kategoriefarben erscheinen als 3 px-Seitenlinie und als
Buchstaben-Badge. Die Kartenfläche bleibt weiß.

**Schrift.** Inter als Variable Font, lokal unter
`app/static/fonts/InterVariable.woff2` (344 KB, SIL Open Font License). Kein
CDN, weil die Content-Security-Policy ausschließlich `'self'` erlaubt.
Überschriften 600, Fließtext 400, Labels 500, Kennzahlen 700 mit
Tabellenziffern.

**Formensprache.** Der unvollständige Scope-Ring ist eine einzige Geometrie
in vier Auflösungen: Wortmarke, Hintergrundbogen auf „Neue Dokumentation",
Zeichen in leeren Zuständen, Vektorzeichnung im PDF-Kopf. Er schließt sich
nirgends.

**Dunkler Modus.** Navy- und Anthrazitflächen ab `#0C1820`, kein reines
Schwarz. Auf dunklem Grund übernimmt Petrol die Hauptaktion, weil Navy dort
in der Fläche verschwinden würde.

**Keine style-Attribute.** Die CSP blockiert sie. Layoutabstände laufen über
`data-s`-Tokens, Kategoriefarben über `data-cat`. Beides ist ein festes
Vokabular und lässt sich nicht aus Nutzereingaben erzeugen. Wer die
Oberfläche erweitert, muss dieselbe Ebene verwenden: ein `style="..."` im
Markup wird vom Browser stillschweigend verworfen.

## 12. Update 1

Neu gegenüber der Erstinstallation, eingespielt über Migration
`0003_rolle_und_soft_delete`:

**Rolle bei der Durchführung.** Eigene Achse neben der Durchführungsart:
selbst durchgeführt, angeleitet, assistiert. Bei angeleitet und assistiert
erscheint ein optionales Feld für die Qualifikation der durchführenden
Person. Für einen Kompetenznachweis ist der Unterschied zwischen selbst
intubiert und eine Intubation angeleitet grundlegend, deshalb zählt das
Dashboard beides getrennt und der PDF-Nachweis weist es getrennt aus.
Bestehende Einträge erhalten bei der Migration den Wert
`selbst durchgeführt`.

**Qualifikationen.** Rettungsassistent ergänzt. Zusätzlich ein optionales
Freitextfeld für die Facharztbezeichnung, das im PDF-Kopf erscheint.

**Intravenöser Zugang.** Der Parameter Größe ist von Freitext auf eine
Auswahl mit Farbcode nach ISO 10555-5 umgestellt: 14 G orange bis 26 G
violett, dazu `andere`. Bereits dokumentierte Freitextwerte bleiben
unverändert, sie stehen als Textkopie im Datensatz.

**Einträge entfernen.** Innerhalb der Frist wie bisher löschen. Danach
stilllegen mit Begründung, siehe Abschnitt 6.

**Rechtliches.** Eigene Seite unter `#/rechtliches`, ohne Anmeldung
erreichbar, mit Anbieterkennzeichnung nach § 5 DDG und einer
Datenschutzerklärung nach Art. 13 DSGVO. Name und Anschrift sind
vorbelegt, die E-Mail-Adresse trägst du unter Profil und Einstellungen
nach. Sie ist nach § 5 Abs. 1 DDG Pflichtangabe.

**Navigationsleiste auf iOS.** Auf Mobilgeräten liegt das Layout jetzt in
einer Flex-Spalte mit fester Höhe, gescrollt wird der Inhaltsbereich. Eine
per `position: fixed` verankerte Leiste wandert auf iOS mit der ein- und
ausfahrenden Adressleiste; als normales Flex-Element kann sie das nicht.

**Anmeldedaten.** Der Benutzername steht jetzt sichtbar unter Profil und
Einstellungen, zusammen mit der E-Mail-Adresse. Vorher war er nach der
Registrierung nirgends mehr abrufbar. Angemeldet wird wahlweise über
Benutzername oder E-Mail-Adresse, Groß- und Kleinschreibung ist egal. Die
Adresse ist damit ein Anmeldemerkmal, muss eindeutig sein und wird in
Kleinschreibung gespeichert; Migration `0004_email_als_anmeldename`
normalisiert vorhandene Einträge und legt den eindeutigen Index an. Sie
ändern verlangt Passwort und einen aktuellen Code, wie der Passwortwechsel.

**Tabellen auf schmalen Displays.** Datentabellen laufen nicht mehr über den
Kartenrand hinaus. Ursache war eine Kombination aus dem auto-Randmaß des
Inhaltsbereichs, das in der neuen Flex-Spalte das Strecken aufhob, und
Tabellen ohne feste Layoutbreite.

## 14. Qualität und Normen

Der Qualitätsbericht `QUALITAET-ISO-25010.md` bildet SCOPE X auf das
Produktqualitätsmodell **ISO/IEC 25010:2023** ab, mit Belegen und offenen
Punkten je Charakteristik.

Wichtig zur Einordnung: ISO 25010 ist ein Qualitätsmodell, kein
Anforderungskatalog. Es gibt keine Konformitätserklärung und keine
Zertifizierung dagegen. Wer behauptet, eine Software „erfülle ISO 25010",
sagt nichts Prüfbares. Der Bericht macht stattdessen die Kompromisse
sichtbar.

**Zu den DIVI-Farbgruppen.** EN ISO 26825 und die ergänzende
DIVI-Empfehlung ordnen Wirkstoffe Wirkungsgruppen mit einer Kennfarbe zu.
SCOPE X führt diese Gruppe als bearbeitbares Feld am Wirkstoff und belegt
sie nur dort vor, wo die Zuordnung eindeutig ist. Es handelt sich um eine
Dokumentationsangabe. SCOPE X ist keine Etikettierungsreferenz, leitet
daraus keine Vorgabe ab, und die Zuordnung sollte gegen die jeweils aktuelle
DIVI-Veröffentlichung geprüft werden.

**SCOPE X ist kein Medizinprodukt** und beansprucht das nicht. Eine
Risikoanalyse nach ISO 14971 liegt nicht vor.

## 15. Qualitätsschleife

```sh
python quality/run_quality.py
```

Prüft 24 automatisierbare Anforderungen und schreibt
`QUALITAETSPRUEFUNG.md`. Rückgabewert ungleich null, sobald etwas
fehlschlägt. Derselbe Lauf startet über `.github/workflows/qualitaet.yml`
bei jedem Push, jedem Pull Request und einmal wöchentlich.

Voraussetzungen über die Laufzeitabhängigkeiten hinaus:

```sh
pip install ruff coverage pip-audit pyyaml httpx playwright
playwright install --with-deps chromium
```

**Was die Schleife nicht kann.** Sechs Punkte erscheinen im Bericht als
manuell offen und zählen nicht als bestanden: Penetrationstest,
Screenreader-Audit mit echten Hilfsmitteln, Risikoanalyse nach ISO 14971,
Verschlüsselung im Ruhezustand, Betriebsüberwachung und die Prüfung gegen
MariaDB. Die ersten drei sind Menschenarbeit, der vierte scheitert an der
Plattform, die letzten beiden brauchen laufende Infrastruktur. Sie stehen
absichtlich im Bericht: sie dort wegzulassen wäre der einzige Weg zu einem
vollständig grünen Ergebnis.

## 16. DIVI-Spritzenetiketten in der App

Die Wirkstoffauswahl bildet das Etikett ab, wie es auf der Spritze klebt,
damit die Auswahl in der App der Spritze in der Hand entspricht. Die Gruppe
ist je Wirkstoff im Katalog änderbar und nur dort vorbelegt, wo die
Zuordnung eindeutig ist.

SCOPE X erzeugt **keine druckbaren Etiketten** und ist keine
Etikettierungsreferenz. Die normative Gestaltung steht in EN ISO 26825; die
hier verwendeten Farbwerte sind Annäherungen an die Pantone-Vorgaben und
nicht normativ. Für die tatsächliche Etikettierung gilt ausschließlich die
jeweils aktuelle DIVI-Veröffentlichung.
