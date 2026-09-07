# SCOPE X Add-on Repository

Add-on-Repository für Home Assistant mit **SCOPE X**, dem Maßnahmen- und
Kompetenzlogbuch für den Rettungsdienst.

## Einbinden

Einstellungen → Add-ons → Add-on Store → Menü oben rechts →
**Repositories** → URL dieses Repositories eintragen → **Hinzufügen**.

Danach erscheint SCOPE X im Store. Bei jeder neuen Version zeigt Home
Assistant automatisch einen **Update**-Knopf, genau wie bei jedem anderen
Add-on. HACS wird dafür nicht gebraucht und kann Add-ons auch nicht
verwalten: dafür ist der Supervisor zuständig.

## Aktualisieren

1. Neue Dateien in dieses Repository committen und die `version` in
   `scopex/config.yaml` erhöhen.
2. In Home Assistant im Add-on Store **Nach Updates suchen**.
3. Bei SCOPE X erscheint **Update**. Der Änderungstext kommt aus
   `scopex/CHANGELOG.md`.

Datenbankmigrationen laufen beim Start automatisch und überspringen bereits
angewendete Versionen. `/data` bleibt beim Update erhalten.

## Versionierung

Semantische Versionierung: MAJOR bei größeren oder inkompatiblen
Änderungen, MINOR für neue Funktionen, PATCH für Korrekturen.
