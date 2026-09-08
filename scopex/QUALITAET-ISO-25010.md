# Qualitätsbericht SCOPE X

Abbildung auf das Produktqualitätsmodell **ISO/IEC 25010:2023**.

## Vorbemerkung: Was dieser Bericht ist und was nicht

ISO/IEC 25010 ist ein **Qualitätsmodell**, kein Anforderungskatalog. Es
liefert ein Vokabular, um Qualität zu spezifizieren, zu messen und zu
bewerten. Es gibt keine Konformitätserklärung und keine Zertifizierung
dagegen. Der Satz „diese Software erfüllt ISO 25010" ist deshalb nicht
prüfbar und wäre eine Falschaussage.

Was möglich und sinnvoll ist: jede Charakteristik des Modells auf konkrete,
nachprüfbare Eigenschaften der Anwendung abbilden und dabei auch die Lücken
benennen. Genau das leistet dieses Dokument.

Die Ausgabe 2023 ersetzt die Ausgabe 2011 und wurde technisch überarbeitet.
Wesentliche Änderungen: **Safety** kam als neunte Charakteristik hinzu,
**Usability** heißt jetzt **Interaction Capability**, **Portability** heißt
**Flexibility**, und es kamen Unterpunkte wie Inclusivity, Resistance und
Scalability hinzu. Das Quality-in-Use-Modell ist in ISO/IEC 25019
ausgelagert und in diesem Bericht nicht behandelt.

Stand: SCOPE X 3.0.0.

---

## 1. Functional Suitability

**Umgesetzt.** Der Funktionsumfang ist gegen die ursprüngliche Spezifikation
gebaut: Erfassung von Einsätzen, Maßnahmen mit maßnahmenspezifischen
Parametern, Medikamentengaben, ZEK, Auswertung und PDF-Nachweis.
Funktionale Korrektheit wird durch drei automatisierte Testreihen belegt
(`smoke`, `smoke2`, `smoke3`), die den Weg von der Registrierung über die
Erfassung bis zu Export und Wiederherstellung abdecken, einschließlich der
abgeleiteten Auswertungskategorien.

**Bewusst nicht enthalten:** Indikationsvorschläge, Dosierungsempfehlungen,
Algorithmen, SOP-Ersatz, automatische medizinische Bewertung. Das ist keine
Lücke, sondern eine Produktentscheidung, die die Zweckbestimmung
begrenzt.

**Lücke:** Es gibt keine formale Anforderungsverfolgung. Die Abdeckung ist
über Tests belegt, nicht über eine Traceability-Matrix.

## 2. Performance Efficiency

**Umgesetzt.** Datenvolumen eines persönlichen Logbuchs liegt bei einigen
tausend Datensätzen pro Jahr. Indizes bestehen auf allen Fremdschlüsseln
und Filterspalten. Die Auswertung aggregiert in SQL statt in Python. Das
Frontend lädt eine CSS- und eine JS-Datei ohne Build-Kette; einzige größere
Ressource ist die Schrift mit 344 KB, einmalig und danach im Cache.

**Lücke:** Es gibt keine Lasttests und keine definierten Antwortzeitziele.
Für den Einsatzzweck ist das vertretbar, für eine Mehrbenutzerinstallation
mit vielen gleichzeitigen Zugriffen wäre es nachzuholen.

## 3. Compatibility

**Umgesetzt.** Koexistenz: läuft als eigener Container ohne Zugriff auf
Home Assistant (`hassio_api: false`, `homeassistant_api: false`) und ohne
veröffentlichten Host-Port. Interoperabilität: Export als CSV und als
vollständige JSON-Sicherung, PDF nach ISO 32000. Der Datenzugriff ist über
`DATABASE_URL` abstrahiert, SQLite und MariaDB sind ohne Codeänderung
nutzbar.

**Lücke:** Keine standardisierte medizinische Schnittstelle (HL7, FHIR).
Für ein persönliches Logbuch nicht vorgesehen.

## 4. Interaction Capability

**Umgesetzt.** Mobile-first, große Touch-Flächen ab 44 px, helle und dunkle
Darstellung, Tastaturbedienbarkeit mit sichtbarem Fokusring,
`prefers-reduced-motion` respektiert. Statusinformation wird nie allein über
Farbe transportiert: jede Statuspille trägt zusätzlich Text. Fehlermeldungen
benennen die Ursache und den nächsten Schritt.

**Inclusivity und Self-descriptiveness** (neu in 2023): Qualifikations- und
Rollenbezeichnungen sind geschlechtsneutral formuliert. Formularfelder tragen
erklärende Hinweise statt bloßer Beschriftungen.

**Lücke:** Kein Screenreader-Test, keine formale WCAG-Prüfung. Die
Signalfarbe der Wortmarke unterschreitet den Kontrastwert für Fließtext;
sie wird ausschließlich als Markenelement eingesetzt, wo WCAG das zulässt.
Ein Audit mit assistiven Technologien steht aus.

## 5. Reliability

**Umgesetzt.** Fehlertoleranz: fehlender Mailversand legt die Anwendung
nicht lahm, Einladungen und Reset-Links lassen sich stattdessen anzeigen.
SQLite läuft im WAL-Modus mit aktivierten Fremdschlüsseln.
Wiederherstellbarkeit über zwei unabhängige Wege: eigene JSON-Sicherung und
das Add-on-Backup von Home Assistant. Migrationen sind idempotent und
werden bei jedem Update gegen einen simulierten Altbestand getestet.

**Faultlessness** (2023 anstelle von Maturity): 151 automatisierte
Prüfungen. Beim Bau von Update 3 deckte diese Testreihe einen Fehler auf,
der seit Version 1 bestand: der Zähler für Fehlanmeldungen wurde innerhalb
derselben Transaktion hochgezählt, in der anschließend eine Exception flog,
und dadurch stets zurückgerollt. Die Kontosperre hat nie ausgelöst.

**Lücke:** Keine Überwachung im Betrieb, keine Alarmierung bei Fehlern.
Erkennbar ist ein Ausfall nur über das Add-on-Protokoll.

## 6. Security

**Umgesetzt.**

- *Confidentiality:* Rollenmodell mit serverseitiger Prüfung auf jeder
  schreibenden Route. Datentrennung je Konto, auch gegenüber
  Administratoren: eine fremde UUID liefert 404.
- *Integrity:* Bearbeitungsfrist, danach Sperre. Änderungen innerhalb der
  Frist feldweise im Änderungsprotokoll. Gesperrte Einträge nur mit
  Pflichtbegründung stilllegbar, nie physisch gelöscht.
- *Non-repudiation:* Änderungsprotokoll mit Zeitpunkt, Objekt, altem und
  neuem Wert. Kein Endpunkt zum Löschen von Protokolleinträgen.
- *Accountability:* Anmeldungen, Fehlversuche, Sperren, Rollenänderungen
  und Einladungen sind protokolliert.
- *Authenticity:* Argon2id, verpflichtende TOTP-Zwei-Faktor-Authentifizierung,
  frischer Code bei Eingriffen in fremde Konten. Registrierung nur mit
  Einladung.
- *Resistance* (neu in 2023): Rate Limit und Kontosperre nach acht
  Fehlversuchen mit Benachrichtigung, Leerlaufabmeldung, Einmal-Token für
  Zurücksetzung, Content-Security-Policy ohne externe Quellen,
  ausschließlich parametrisierte Abfragen.

**Lücke:** Keine Verschlüsselung im Ruhezustand. Home Assistant OS bietet
keine Verschlüsselung einzelner Add-on-Volumes; ein Schlüssel müsste auf
derselben Maschine liegen und würde nur gegen einen entwendeten Datenträger
schützen. Kein externes Penetrationstest-Ergebnis. Keine Passkeys.

## 7. Maintainability

**Umgesetzt.** Modularer Aufbau mit getrennten Zuständigkeiten: Datenzugriff,
Sicherheit, Auswertung, PDF, Mail, Router je Themenbereich. Versionierte,
idempotente Migrationen. Testbarkeit über drei Suiten mit 151 Prüfungen.
Wiederverwendbarkeit: die Auswertung wird von Dashboard und PDF geteilt, ein
Auseinanderlaufen ist dadurch ausgeschlossen. Analysierbarkeit über
Änderungsprotokoll und Add-on-Protokoll.

**Modifizierbarkeit:** Stammdaten sind zur Laufzeit erweiterbar, ohne
historische Einträge zu verändern, weil Bezeichnungen beim Speichern in den
Datensatz kopiert werden.

**Lücke:** Keine Typprüfung im Frontend, keine automatisierte
Testabdeckungsmessung, keine CI-Pipeline.

## 8. Flexibility

**Umgesetzt.** *Adaptability:* Datenbank über `DATABASE_URL` austauschbar,
alle Primärschlüssel sind UUID-Textfelder, kein dialektspezifisches SQL.
*Installability:* Add-on-Repository mit Versionsprüfung, Installation und
Update über die Home-Assistant-Oberfläche. *Replaceability:* vollständiger
Datenexport als JSON und CSV, keine proprietären Formate.

**Scalability** (neu in 2023): horizontal nicht skalierbar, weil SQLite als
Dateidatenbank auf einen Prozess ausgelegt ist. Der Wechsel auf MariaDB ist
vorbereitet und wäre der erste Schritt, falls das je gebraucht wird.

## 9. Safety

Neu in der Ausgabe 2023 und für ein medizinnahes Werkzeug die interessanteste
Charakteristik.

**Operational constraint:** Die Zweckbestimmung ist im Produkt selbst
verankert und wird im PDF-Nachweis wiederholt: kein Einsatzprotokoll, keine
Patientenakte, kein Entscheidungsunterstützungssystem.

**Risk identification:** Das erkannte Hauptrisiko ist Zweckentfremdung — dass
jemand die Anwendung als klinische Referenz benutzt. Gegenmaßnahme: es gibt
schlicht keine Inhalte, die sich so lesen ließen. Keine Dosierungen, keine
Indikationen, keine Algorithmen. Die DIVI-Farbgruppen sind als
Dokumentationsangabe gekennzeichnet, frei änderbar und nur dort vorbelegt,
wo die Zuordnung eindeutig ist.

**Fail safe:** Ohne Mailversand bleibt die Anwendung nutzbar. Eine
abgelaufene Sitzung führt zur Abmeldung, nicht zu unklaren Zuständen.
Migrationen brechen laut ab, statt still weiterzulaufen.

**Hazard warning:** Warnung bei langer Bearbeitungsfrist, weil das den
Beweiswert des Nachweises senkt; die geltende Frist wird im PDF ausgewiesen.
Hinweis auf den möglichen Personenbezug von Einsatznummern.
Pflichtbegründung beim Stilllegen von Einträgen.

**Safe integration:** Das Add-on hat keinen Zugriff auf Home Assistant und
kann dort weder Zustände lesen noch Dienste aufrufen. Ein Fehler in SCOPE X
kann die Hausautomation nicht beeinträchtigen.

**Lücke:** Keine formale Risikoanalyse nach ISO 14971. SCOPE X ist kein
Medizinprodukt und beansprucht das nicht; wer es in einem regulierten Umfeld
einsetzen wollte, müsste diese Bewertung eigenständig führen.

---

## Zusammenfassung der offenen Punkte

| Charakteristik | Offen |
|---|---|
| Functional Suitability | keine Traceability-Matrix |
| Performance Efficiency | keine Lasttests, keine Antwortzeitziele |
| Compatibility | keine medizinische Fachschnittstelle |
| Interaction Capability | kein Screenreader- und WCAG-Audit |
| Reliability | keine Betriebsüberwachung |
| Security | keine Verschlüsselung im Ruhezustand, kein Pentest, keine Passkeys |
| Maintainability | keine CI, keine Abdeckungsmessung, keine Typprüfung |
| Flexibility | nicht horizontal skalierbar |
| Safety | keine Risikoanalyse nach ISO 14971 |

Diese Liste ist der eigentliche Nutzen des Modells: sie macht die
Kompromisse sichtbar, statt sie zu verschweigen.
