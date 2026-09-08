# Qualitätsbericht (automatisch erzeugt)

Erzeugt am 08.09.2026 um 13:02 Uhr für SCOPE X.

Erzeugt von `quality/run_quality.py`. Manuell offene Punkte zählen ausdrücklich nicht als bestanden.

## Functional Suitability

| Prüfung | Ergebnis | Anmerkung |
|---|---|---|
| Funktionale Testreihen | bestanden | 183 Prüfungen bestanden |
| Jede API-Route wird von mindestens einem Test berührt | bestanden | alle Router abgedeckt |

## Performance Efficiency

| Prüfung | Ergebnis | Anmerkung |
|---|---|---|
| Antwortzeiten unter 400 ms | bestanden | alle innerhalb des Budgets |
| Auslieferungsgröße der Oberfläche | bestanden | JS 118 KB, CSS 31 KB, Schrift 343 KB, gesamt 494 KB von 700 KB |

## Compatibility

| Prüfung | Ergebnis | Anmerkung |
|---|---|---|
| Kein dialektspezifisches SQL | bestanden | portabel |
| Datenbank über DATABASE_URL austauschbar | bestanden | Engine wird aus der Umgebung gebaut |
| Prüfung gegen MariaDB | manuell offen | erfordert eine laufende Instanz, im Prüflauf nicht verfügbar |

## Interaction Capability

| Prüfung | Ergebnis | Anmerkung |
|---|---|---|
| Barrierefreiheit der Oberfläche | bestanden | keine Verstöße gefunden |
| Farbe trägt nie allein die Information | bestanden | Statuspillen und Kategoriemarken tragen Text |
| Keine style-Attribute im Markup | bestanden | keine |
| Screenreader-Audit mit echten Hilfsmitteln | manuell offen | VoiceOver und NVDA lassen sich nicht sinnvoll simulieren |

## Reliability

| Prüfung | Ergebnis | Anmerkung |
|---|---|---|
| Migrationen sind idempotent | bestanden | 7 angewendet, zweiter Durchlauf leer |
| Sicherung und Wiederherstellung als Kreis | bestanden | Kennzahlen vor und nach der Wiederherstellung gleich |
| Überwachung im Betrieb | manuell offen | Ausfall derzeit nur über das Add-on-Protokoll erkennbar |

## Security

| Prüfung | Ergebnis | Anmerkung |
|---|---|---|
| Bekannte Schwachstellen in Abhängigkeiten | bestanden | keine bekannten Schwachstellen |
| Sicherheitsheader vollständig | bestanden | vollständig |
| Ausschließlich parametrisierte Abfragen | bestanden | nur Bezeichner interpoliert |
| Berechtigungsmatrix über alle schreibenden Routen | bestanden | jede Route verweigert unberechtigte Zugriffe |
| Keine Zugangsdaten im Quelltext | bestanden | keine |
| Penetrationstest durch Dritte | manuell offen | erfordert externe Prüfung, zuletzt: nie |
| Verschlüsselung im Ruhezustand | manuell offen | auf Home Assistant OS nicht pro Add-on möglich, Plattformgrenze |

## Maintainability

| Prüfung | Ergebnis | Anmerkung |
|---|---|---|
| Statische Analyse ohne Befund | bestanden | keine Befunde |
| Testabdeckung mindestens 70 Prozent | bestanden | 81.7 Prozent |

## Flexibility

| Prüfung | Ergebnis | Anmerkung |
|---|---|---|
| Vollständiger Export ohne proprietäres Format | bestanden | JSON, CSV und PDF |
| Installierbarkeit als Add-on | bestanden | Version 3.0.0, Änderungsprotokoll vorhanden |

## Safety

| Prüfung | Ergebnis | Anmerkung |
|---|---|---|
| Zweckbestimmung im Produkt verankert | bestanden | vorhanden |
| Gefahrenhinweise vorhanden | bestanden | alle vorhanden |
| Keine Dosierungs- oder Therapieempfehlung in den Stammdaten | bestanden | keine |
| Add-on ohne Zugriff auf Home Assistant | bestanden | keine Schnittstelle zur Hausautomation |
| Risikoanalyse nach ISO 14971 | manuell offen | nur nötig, falls SCOPE X je als Medizinprodukt eingesetzt werden soll |
