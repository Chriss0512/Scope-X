# Fremdbibliotheken der Prüfung

`axe.min.js` von Deque Systems (MPL 2.0) wird für die
Barrierefreiheitsprüfung gebraucht und ist hier nicht eingecheckt, weil es
eine Prüf- und keine Laufzeitabhängigkeit ist:

```sh
curl -fsSL -o quality/vendor/axe.min.js \
  https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js
```

Denselben Schritt führt `.github/workflows/qualitaet.yml` aus. Steht
cdnjs nicht zur Verfügung, liefert die npm-Registry dieselbe Fassung:

```sh
npm pack axe-core@4.10.2 && tar -xzf axe-core-4.10.2.tgz \
  && mv package/axe.min.js quality/vendor/axe.min.js \
  && rm -rf package axe-core-4.10.2.tgz
```

Fehlt die Datei, **schlägt die Prüfung fehl**. Sie gilt nicht als
bestanden, nur weil das Werkzeug nicht da ist. Frühere Fassungen dieser
Notiz sprachen von „übersprungen"; der Lauf zählt sie unter
„fehlgeschlagen" und endet mit Rückgabewert 1.
