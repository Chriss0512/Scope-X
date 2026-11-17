"""Verarbeitung und Ablage von Bildern und Videos im Kompetenznetz.

Ein Foto vom Telefon trägt in seinen Metadaten fast immer, wo und wann es
aufgenommen wurde, oft auf wenige Meter genau. Ein Video ebenso — dort
steht der Ort im Container (``©xyz`` bei iPhones, ``location`` bei
Android). Ein Profilbild aus dem Garten verriete die Wohnadresse, ein
Video von der Wache den Standort. Deshalb wird nichts so gespeichert, wie
es hochgeladen wurde:

* **Bilder** werden dekodiert, gedreht, verkleinert und neu als JPEG
  geschrieben. Was nicht Pixel ist, geht verloren: EXIF, GPS, XMP, IPTC,
  Farbprofile, eingebettete Vorschaubilder, Daten hinter dem Bildende.
* **Videos** werden mit ffmpeg neu kodiert (H.264/AAC, höchstens 720p,
  höchstens 90 Sekunden). ``-map_metadata -1`` und ``-map_chapters -1``
  verwerfen sämtliche Container- und Stream-Metadaten; nur die erste
  Bild- und die erste Tonspur werden übernommen, Untertitel- und
  Datenspuren (dort liegen bei manchen Kameras GPS-Spuren) fallen weg.

Ausgeliefert wird nie die hochgeladene Byte-Folge, sondern eine Datei,
die Pillow oder ffmpeg selbst geschrieben hat.

ffmpeg kommt aus dem Wheel ``imageio-ffmpeg`` (statisch gebaut, für amd64
und aarch64), damit das Image ohne apt-Pakete auskommt.
"""
from __future__ import annotations

import io
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from PIL import Image, ImageOps

log = logging.getLogger("scopex.medien")

# Obergrenze für die dekodierte Fläche. Eine kleine PNG-Datei kann zu
# Gigabytes an Pixeln entpacken; Pillow bricht über diesem Wert ab.
Image.MAX_IMAGE_PIXELS = 40_000_000

BILD_MAX_BYTES = 12 * 1024 * 1024
VIDEO_MAX_BYTES = 200 * 1024 * 1024
VIDEO_MAX_SEKUNDEN = 90
BILD_ERLAUBT = {"JPEG", "PNG", "WEBP", "MPO"}

# Profilbild quadratisch, Kopfbild 3:1. Beitragsbilder behalten ihr
# Seitenverhältnis innerhalb von 4:5 (hoch) bis 1,91:1 (quer), wie in
# Bildfeeds üblich — extremere Formate werden mittig beschnitten.
FESTE_FORMATE = {"avatar": (512, 512), "banner": (1500, 500)}
BEITRAG_KANTE = 1440
MIN_VERHAELTNIS = 4 / 5
MAX_VERHAELTNIS = 1.91


class MedienFehler(ValueError):
    """Ein Upload, der kein verwendbares Bild oder Video ist."""


def ablage() -> Path:
    pfad = Path(os.environ.get("SCOPEX_MEDIA_DIR", "/data/media"))
    pfad.mkdir(parents=True, exist_ok=True)
    return pfad


def pfad_fuer(datei: str) -> Path:
    """Löst einen gespeicherten Dateinamen auf. Nur Namen, die wir selbst
    vergeben haben: hex-UUID plus Endung, kein Pfadanteil."""
    if not re.fullmatch(r"[0-9a-f-]{36}(?:-poster)?\.(?:jpg|mp4)", datei or ""):
        raise MedienFehler("Ungültiger Dateiname.")
    return ablage() / datei


def entferne(*dateien: str | None) -> None:
    for d in dateien:
        if not d:
            continue
        try:
            pfad_fuer(d).unlink(missing_ok=True)
        except (MedienFehler, OSError):
            pass


# --------------------------------------------------------------------------
# Bilder
# --------------------------------------------------------------------------

def _oeffne(roh: bytes) -> Image.Image:
    if not roh:
        raise MedienFehler("Die Datei ist leer.")
    if len(roh) > BILD_MAX_BYTES:
        raise MedienFehler("Das Bild ist größer als 12 MB.")
    try:
        # Zweimal öffnen: verify() prüft die Struktur, hinterlässt das Bild
        # aber unbrauchbar. Erst das zweite Öffnen dekodiert wirklich.
        with Image.open(io.BytesIO(roh)) as probe:
            if probe.format not in BILD_ERLAUBT:
                raise MedienFehler("Erlaubt sind JPEG, PNG und WebP.")
            probe.verify()
        bild = Image.open(io.BytesIO(roh))
        bild.load()
        # Drehung aus den Metadaten anwenden, bevor sie verworfen werden.
        bild = ImageOps.exif_transpose(bild)
        if bild.mode in ("RGBA", "LA", "P"):
            bild = bild.convert("RGBA")
            grund = Image.new("RGB", bild.size, (255, 255, 255))
            grund.paste(bild, mask=bild.split()[-1])
            return grund
        return bild.convert("RGB")
    except MedienFehler:
        raise
    except Image.DecompressionBombError as exc:
        raise MedienFehler("Das Bild ist zu groß zum Verarbeiten.") from exc
    except Exception as exc:  # noqa: BLE001 - jede Pillow-Ausnahme heißt: kein Bild
        raise MedienFehler("Die Datei ist kein lesbares Bild.") from exc


def _als_jpeg(bild: Image.Image) -> bytes:
    aus = io.BytesIO()
    # Kein exif=, kein icc_profile=: Pillow schreibt dann keine Metadaten.
    bild.save(aus, format="JPEG", quality=85, optimize=True, progressive=True)
    return aus.getvalue()


def bild_verarbeiten(roh: bytes, art: str) -> tuple[bytes, int, int]:
    """Gibt ein bereinigtes JPEG samt Breite und Höhe zurück."""
    bild = _oeffne(roh)
    if art in FESTE_FORMATE:
        bild = ImageOps.fit(bild, FESTE_FORMATE[art], method=Image.Resampling.LANCZOS)
    else:
        b, h = bild.size
        v = b / h
        if v < MIN_VERHAELTNIS:
            bild = ImageOps.fit(bild, (b, int(b / MIN_VERHAELTNIS)),
                                method=Image.Resampling.LANCZOS)
        elif v > MAX_VERHAELTNIS:
            bild = ImageOps.fit(bild, (int(h * MAX_VERHAELTNIS), h),
                                method=Image.Resampling.LANCZOS)
        bild.thumbnail((BEITRAG_KANTE, BEITRAG_KANTE), Image.Resampling.LANCZOS)
    return _als_jpeg(bild), bild.width, bild.height


def speichere_bild(mid: str, roh: bytes, art: str) -> dict:
    daten, breite, hoehe = bild_verarbeiten(roh, art)
    datei = f"{mid}.jpg"
    (ablage() / datei).write_bytes(daten)
    return {"file": datei, "mime": "image/jpeg", "width": breite,
            "height": hoehe, "bytes": len(daten)}


# --------------------------------------------------------------------------
# Videos
# --------------------------------------------------------------------------

def ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # noqa: BLE001
        gefunden = shutil.which("ffmpeg")
        if gefunden:
            return gefunden
        raise MedienFehler("Videoverarbeitung ist auf diesem System nicht verfügbar.") from exc


# Nur Containerformate, die Telefone und Kameras tatsächlich schreiben.
# Ohne diese Liste erkennt ffmpeg auch HLS-Wiedergabelisten und
# concat-Skripte — eine als .mp4 getarnte Wiedergabeliste kann ffmpeg dann
# andere Dateien des Servers einlesen und ins „Video“ kodieren lassen.
EINGABEFORMATE = "mov,mp4,m4a,3gp,3g2,mj2,matroska,webm"
EINGABE_SCHRANKEN = ["-format_whitelist", EINGABEFORMATE,
                     "-protocol_whitelist", "file"]

_DAUER = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_GROESSE = re.compile(r"Video:.*?(\d{2,5})x(\d{2,5})")
# Ein Video wird nacheinander verarbeitet. Ein Kleinrechner unter Home
# Assistant soll nicht von drei gleichzeitigen Uploads lahmgelegt werden.
_EIN_VIDEO = threading.Semaphore(1)


def _untersuche(pfad: Path) -> tuple[float, int, int]:
    erg = subprocess.run([ffmpeg(), "-hide_banner", *EINGABE_SCHRANKEN, "-i", str(pfad)],
                         capture_output=True, text=True, timeout=60)
    text = erg.stderr
    d = _DAUER.search(text)
    g = _GROESSE.search(text)
    if not d or not g or "Video:" not in text:
        raise MedienFehler("Die Datei ist kein lesbares Video.")
    dauer = int(d.group(1)) * 3600 + int(d.group(2)) * 60 + float(d.group(3))
    return dauer, int(g.group(1)), int(g.group(2))


def video_annehmen(mid: str, quelle) -> Path:
    """Schreibt den Upload in Blöcken in eine Rohdatei, ohne ihn ganz in den
    Speicher zu laden. Gibt den Pfad der Rohdatei zurück."""
    roh = ablage() / f".{mid}.upload"
    groesse = 0
    with open(roh, "wb") as ziel:
        while True:
            block = quelle.read(1024 * 1024)
            if not block:
                break
            groesse += len(block)
            if groesse > VIDEO_MAX_BYTES:
                ziel.close()
                roh.unlink(missing_ok=True)
                raise MedienFehler("Das Video ist größer als 200 MB.")
            ziel.write(block)
    if groesse == 0:
        roh.unlink(missing_ok=True)
        raise MedienFehler("Die Datei ist leer.")
    return roh


def video_verarbeiten(mid: str, roh: Path) -> dict:
    """Kodiert neu und erzeugt ein Vorschaubild. Wirft MedienFehler."""
    with _EIN_VIDEO:
        try:
            dauer, _, _ = _untersuche(roh)
            ziel = ablage() / f"{mid}.mp4"
            poster = ablage() / f"{mid}-poster.jpg"
            with tempfile.TemporaryDirectory(dir=ablage()) as tmp:
                zwischen = Path(tmp) / "out.mp4"
                befehl = [
                    ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                    *EINGABE_SCHRANKEN, "-i", str(roh),
                    "-t", str(VIDEO_MAX_SEKUNDEN),
                    "-map", "0:v:0", "-map", "0:a:0?",
                    "-map_metadata", "-1", "-map_chapters", "-1",
                    "-sn", "-dn",
                    "-vf", "scale='min(1280,iw)':'min(1280,ih)':"
                           "force_original_aspect_ratio=decrease,"
                           "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                    "-pix_fmt", "yuv420p", "-profile:v", "high",
                    "-c:a", "aac", "-b:a", "128k", "-ac", "2",
                    "-movflags", "+faststart",
                    "-metadata", "creation_time=",
                    str(zwischen),
                ]
                erg = subprocess.run(befehl, capture_output=True, text=True,
                                     timeout=900)
                if erg.returncode != 0 or not zwischen.exists():
                    log.warning("Video %s ließ sich nicht kodieren", mid)
                    raise MedienFehler("Das Video ließ sich nicht verarbeiten.")
                shutil.move(str(zwischen), ziel)
            dauer_neu, breite, hoehe = _untersuche(ziel)
            # Vorschaubild aus der ersten Sekunde, ebenfalls ohne Metadaten
            # und noch einmal durch Pillow geschickt.
            erg = subprocess.run(
                [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                 "-ss", str(min(1.0, dauer_neu / 2)), *EINGABE_SCHRANKEN,
                 "-i", str(ziel),
                 "-frames:v", "1", "-map_metadata", "-1", "-f", "image2pipe",
                 "-vcodec", "png", "-"],
                capture_output=True, timeout=60)
            if erg.returncode != 0 or not erg.stdout:
                raise MedienFehler("Kein Vorschaubild erzeugbar.")
            bild = Image.open(io.BytesIO(erg.stdout)).convert("RGB")
            bild.thumbnail((BEITRAG_KANTE, BEITRAG_KANTE))
            poster.write_bytes(_als_jpeg(bild))
            return {"file": ziel.name, "poster": poster.name, "mime": "video/mp4",
                    "width": breite, "height": hoehe,
                    "duration": round(min(dauer, VIDEO_MAX_SEKUNDEN), 1),
                    "bytes": ziel.stat().st_size}
        except subprocess.TimeoutExpired as exc:
            raise MedienFehler("Die Verarbeitung hat zu lange gedauert.") from exc
        finally:
            roh.unlink(missing_ok=True)
