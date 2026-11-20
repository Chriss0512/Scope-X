# Fremdbibliotheken

Nur für die Übernahme aus NIDAshare (ab 4.8.0). Geladen werden sie erst,
wenn jemand den Code fotografiert; die Startseite bleibt davon unberührt.
Alles läuft im Browser, nichts davon spricht mit fremden Servern.

| Datei | Herkunft | Version | Lizenz |
| --- | --- | --- | --- |
| `ocr/tesseract.min.js`, `ocr/worker.min.js` | npm `tesseract.js` | 7.0.0 | Apache-2.0 |
| `ocr/tesseract-core-simd-lstm.js`, `.wasm` | npm `tesseract.js-core` | 7.0.0 | Apache-2.0 |
| `ocr/lang/eng.traineddata.gz` | npm `@tesseract.js-data/eng`, Ordner `4.0.0_best_int` | 1.0.0 | Apache-2.0 (tessdata) |
| `qr/jsqr.js` | npm `jsqr`, `dist/jsQR.js` | 1.4.0 | Apache-2.0 |

Nur die SIMD-Fassung des Tesseract-Kerns ist dabei. WebAssembly-SIMD
können alle aktuellen Browser, Safari ab 16.4. Ohne SIMD meldet die
Kamerafunktion einen Fehler, und der Code lässt sich weiter von Hand
eingeben.

Aktualisieren: Pakete mit `npm pack` laden, Dateien wie oben ersetzen,
Version hier und im CHANGELOG nachtragen.
