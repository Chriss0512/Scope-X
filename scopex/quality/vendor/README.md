# Fremdbibliotheken der Prüfung

`axe.min.js` von Deque Systems (MPL 2.0) wird für die
Barrierefreiheitsprüfung gebraucht und ist hier nicht eingecheckt, weil es
eine Prüf- und keine Laufzeitabhängigkeit ist:

```sh
curl -sL -o quality/vendor/axe.min.js \
  https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js
```

Fehlt die Datei, meldet die Prüfung „übersprungen" statt zu bestehen.
