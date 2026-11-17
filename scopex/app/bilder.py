"""Verarbeitung hochgeladener Profil- und Kopfbilder.

Ein Foto vom Telefon trägt in seinen Metadaten fast immer, wo und wann es
aufgenommen wurde, oft auf wenige Meter genau. Ein Profilbild, im Garten
aufgenommen, verriete damit die Wohnadresse an jedes Mitglied. Deshalb
wird nichts so gespeichert, wie es hochgeladen wurde: jedes Bild wird
dekodiert, gedreht, beschnitten und **neu codiert**. Was nicht Pixel ist,
geht dabei verloren — EXIF, GPS, XMP, IPTC, Farbprofile, eingebettete
Vorschaubilder, angehängte Daten hinter dem Bildende.

Das Neucodieren schützt zugleich gegen präparierte Dateien: ausgeliefert
wird nie die hochgeladene Byte-Folge, sondern ein JPEG, das Pillow selbst
geschrieben hat.
"""
from __future__ import annotations

import io

from PIL import Image, ImageOps

# Obergrenze für die dekodierte Fläche. Eine kleine PNG-Datei kann zu
# Gigabytes an Pixeln entpacken; Pillow bricht über diesem Wert ab, statt
# den Speicher des Add-ons zu füllen.
Image.MAX_IMAGE_PIXELS = 40_000_000

MAX_BYTES = 8 * 1024 * 1024
ERLAUBT = {"JPEG", "PNG", "WEBP"}

FORMATE = {
    # Profilbild quadratisch, Kopfbild im Verhältnis 3:1.
    "avatar": (512, 512),
    "banner": (1500, 500),
}


class BildFehler(ValueError):
    """Ein Upload, der kein verwendbares Bild ist."""


def verarbeite(roh: bytes, art: str) -> tuple[bytes, int, int]:
    """Gibt ein bereinigtes JPEG samt Breite und Höhe zurück."""
    if art not in FORMATE:
        raise BildFehler("Unbekannte Bildart.")
    if not roh:
        raise BildFehler("Die Datei ist leer.")
    if len(roh) > MAX_BYTES:
        raise BildFehler("Das Bild ist größer als 8 MB.")

    try:
        # Zweimal öffnen: verify() prüft die Struktur, hinterlässt das Bild
        # aber unbrauchbar. Erst das zweite Öffnen dekodiert wirklich.
        with Image.open(io.BytesIO(roh)) as probe:
            if probe.format not in ERLAUBT:
                raise BildFehler("Erlaubt sind JPEG, PNG und WebP.")
            probe.verify()
        with Image.open(io.BytesIO(roh)) as bild:
            bild.load()
            # Drehung aus den Metadaten anwenden, bevor sie verworfen
            # werden — sonst stünde ein hochkant aufgenommenes Bild quer.
            bild = ImageOps.exif_transpose(bild)
            if bild.mode in ("RGBA", "LA", "P"):
                # Transparenz auf Weiß legen; JPEG kennt keinen Alphakanal.
                bild = bild.convert("RGBA")
                grund = Image.new("RGB", bild.size, (255, 255, 255))
                grund.paste(bild, mask=bild.split()[-1])
                bild = grund
            else:
                bild = bild.convert("RGB")
            ziel = FORMATE[art]
            bild = ImageOps.fit(bild, ziel, method=Image.Resampling.LANCZOS)
    except BildFehler:
        raise
    except Image.DecompressionBombError as exc:
        raise BildFehler("Das Bild ist zu groß zum Verarbeiten.") from exc
    except Exception as exc:  # noqa: BLE001 - jede Pillow-Ausnahme heißt: kein Bild
        raise BildFehler("Die Datei ist kein lesbares Bild.") from exc

    ausgabe = io.BytesIO()
    # Kein exif=, kein icc_profile=: Pillow schreibt dann keinerlei
    # Metadaten. progressive für schnelleren Aufbau im Feed.
    bild.save(ausgabe, format="JPEG", quality=85, optimize=True,
              progressive=True)
    return ausgabe.getvalue(), bild.width, bild.height
