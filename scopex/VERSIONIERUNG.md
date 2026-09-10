# Versionierung

SCOPE X folgt **Semantic Versioning 2.0.0**.

## Die öffentliche Schnittstelle

SemVer verlangt, dass die öffentliche Schnittstelle klar definiert ist.
Ohne diese Festlegung ist die Unterscheidung zwischen MAJOR und MINOR
Willkür. Für SCOPE X umfasst sie genau vier Dinge:

1. **Das Sicherungsformat.** Der Schlüssel `version` in der JSON-Sicherung
   und die Menge der enthaltenen Tabellen.
2. **Die Add-on-Optionen.** Namen, Typen und Bedeutung der Felder in
   `config.yaml` unter `options` und `schema`.
3. **Die HTTP-Endpunkte** unter `/api/`, ihre Pfade und die Bedeutung ihrer
   Felder.
4. **Der Migrationspfad.** Jede unterstützte Vorversion muss sich ohne
   Handarbeit auf die neue Fassung heben lassen.

Die Oberfläche, das Aussehen und interne Modulstruktur gehören
ausdrücklich **nicht** dazu. Ein Redesign ist kein Grund für MAJOR.

## Wann welche Stelle steigt

**MAJOR** bei jeder Änderung, die eine der vier Zusagen bricht:

- Das Sicherungsformat wird inkompatibel, `BACKUP_VERSION` steigt.
- Eine Add-on-Option entfällt oder ändert ihre Bedeutung.
- Ein API-Endpunkt entfällt, ändert seinen Pfad oder die Bedeutung eines
  bestehenden Feldes.
- Eine Migration kann nicht mehr von jeder unterstützten Vorversion aus
  laufen.

**MINOR** bei neuer Funktion unter Wahrung der Abwärtskompatibilität:

- Neue Endpunkte, neue optionale Felder, neue Add-on-Optionen mit Vorgabewert.
- Neue Datenbankspalten und Tabellen, solange bestehende Daten unverändert
  gültig bleiben.
- Eine bestehende Funktion wird deutlich erweitert.

**PATCH** ausschließlich für Fehlerbehebungen ohne neue Felder:

- Korrigiertes Verhalten, behobene Anzeigefehler, aktualisierte
  Abhängigkeiten ohne Funktionsänderung.

## Rückblick: was falsch war

Die Versionen 2.0.0, 3.0.0 und 4.0.0 hätten nach diesen Regeln 1.2.0, 1.3.0
und 1.4.0 heißen müssen. Keine davon hat Sicherungsformat, Optionen,
Endpunkte oder Migrationspfad gebrochen; es waren durchweg
Funktionserweiterungen.

Zurückversioniert wird nicht: Home Assistant bietet ein Update nur bei
höherer Versionsnummer an, eine Korrektur nach unten würde den
Aktualisierungsweg für bereits installierte Instanzen zerstören. Der Fehler
bleibt sichtbar dokumentiert, statt still bereinigt zu werden.

Ab 4.1.0 gelten die Regeln oben, und `quality/run_quality.py` prüft sie bei
jedem Durchlauf.

## Was automatisch geprüft wird

- Die Version in `config.yaml` ist gültiges SemVer.
- Zu jeder Version existiert ein Abschnitt in `CHANGELOG.md`.
- Die Version ist höher als die zuletzt im Änderungsprotokoll verzeichnete.
- `BACKUP_VERSION` ist unverändert, solange die MAJOR-Stelle gleich bleibt.
- Kein Endpunkt aus der zuletzt veröffentlichten Fassung ist entfallen,
  solange die MAJOR-Stelle gleich bleibt. Grundlage ist
  `quality/api-oberflaeche.json`, eine bei jeder Veröffentlichung
  fortgeschriebene Liste der Pfade.

Die letzte Prüfung ist die wichtigste: sie fängt genau den Fall ab, in dem
jemand einen Endpunkt umbenennt und die Version trotzdem nur auf MINOR
hebt.
