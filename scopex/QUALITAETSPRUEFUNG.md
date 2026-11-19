# Qualitätsbericht (automatisch erzeugt)

Erzeugt am 19.11.2026 um 12:19 Uhr für SCOPE X.

Erzeugt von `quality/run_quality.py`. Manuell offene Punkte zählen ausdrücklich nicht als bestanden.

## Functional Suitability

| Prüfung | Ergebnis | Anmerkung |
|---|---|---|
| Funktionale Testreihen | bestanden | 642 Prüfungen bestanden |
| Jede API-Route wird von mindestens einem Test berührt | bestanden | alle Router abgedeckt |

## Performance Efficiency

| Prüfung | Ergebnis | Anmerkung |
|---|---|---|
| Antwortzeiten unter 400 ms | bestanden | alle innerhalb des Budgets |
| Auslieferungsgröße der Oberfläche | bestanden | Übertragung 449 KB von 500 KB (Skript und Stil 105 KB komprimiert, Schrift 343 KB); einzulesen 405 KB von 480 KB |

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
| Migrationen sind idempotent | bestanden | 12 angewendet, zweiter Durchlauf leer |
| Sicherung und Wiederherstellung als Kreis | bestanden | Kennzahlen vor und nach der Wiederherstellung gleich |
| Überwachung im Betrieb | manuell offen | Ausfall derzeit nur über das Add-on-Protokoll erkennbar |

## Security

| Prüfung | Ergebnis | Anmerkung |
|---|---|---|
| Bekannte Schwachstellen in Abhängigkeiten | bestanden | keine bekannten Schwachstellen |
| Statische Sicherheitsanalyse (Semgrep, OWASP Top Ten) | bestanden | keine Befunde der Stufe ERROR, 1 Hinweis ohne Abbruch |
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
| Testabdeckung mindestens 70 Prozent | bestanden | 80.7 Prozent |
| Version folgt SemVer und ist dokumentiert | bestanden | 4.6.0, 13 Fassungen dokumentiert |
| Keine stille Änderung der öffentlichen Schnittstelle | bestanden | 145 Pfade, 0 neu, Sicherungsformat 1 |

## Flexibility

| Prüfung | Ergebnis | Anmerkung |
|---|---|---|
| Vollständiger Export ohne proprietäres Format | bestanden | JSON, CSV und PDF |
| Installierbarkeit als Add-on | bestanden | Version 4.6.0, Änderungsprotokoll vorhanden |

## Safety

| Prüfung | Ergebnis | Anmerkung |
|---|---|---|
| Zweckbestimmung im Produkt verankert | bestanden | vorhanden |
| Gefahrenhinweise vorhanden | bestanden | alle vorhanden |
| Keine Dosierungs- oder Therapieempfehlung in den Stammdaten | bestanden | keine |
| Add-on ohne Zugriff auf Home Assistant | bestanden | keine Schnittstelle zur Hausautomation |
| Risikoanalyse nach ISO 14971 | manuell offen | nur nötig, falls SCOPE X je als Medizinprodukt eingesetzt werden soll |
