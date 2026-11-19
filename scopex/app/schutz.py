"""Verschlüsselung im Ruhezustand.

Was hier steht, schützt Daten, die auf dem Datenträger liegen: die
Datenbankdatei, ihre Kopien und die Mediendateien. Gegen jemanden, der den
laufenden Server und den Schlüssel in der Hand hat, schützt es nicht – so
arbeiten auch die großen Netzwerke bei Direktnachrichten: Transport per
TLS, Speicherung verschlüsselt, Schlüssel beim Betreiber.

VERFAHREN

* AES-256-GCM (authentifiziert) aus der Bibliothek ``cryptography``, je
  Wert eine frische Zufallsnonce von 96 Bit. Gespeichert wird
  ``enc:v1:`` + Base64url(Nonce ‖ Chiffrat ‖ Tag). Das Präfix macht
  verschlüsselte Werte erkennbar; die Zahl erlaubt einen späteren
  Schlüsselwechsel, ohne alte Werte zu verlieren.
* Für Werte, nach denen gesucht werden muss (E-Mail-Adressen), gibt es
  zusätzlich einen Blindindex: HMAC-SHA-256 über die normalisierte
  Adresse. Er erlaubt den Vergleich, ohne die Adresse zu speichern.
* Beide Teilschlüssel werden per HKDF-SHA-256 aus einem 256-Bit-
  Hauptschlüssel abgeleitet, getrennt nach Zweck.
* Mediendateien werden in Blöcken zu 64 KiB verschlüsselt. Jeder Block
  trägt seine Nummer und eine Endmarke in den Zusatzdaten; damit lassen
  sich Videos weiterhin in Teilen ausliefern (Spulen), und Blöcke können
  weder vertauscht noch abgeschnitten werden, ohne dass es auffällt.

SCHLÜSSEL

1. ``SCOPEX_SCHLUESSEL`` (Add-on-Option ``schluessel``): 32 Byte als
   Base64. Für alle, die den Schlüssel selbst verwahren wollen.
2. Sonst die Datei ``SCOPEX_SCHLUESSELDATEI``, Vorgabe ``scopex.key`` im
   Verzeichnis der Datenbank. Fehlt sie bei einer leeren Datenbank, wird
   sie mit Rechten 0600 angelegt.

Die Datenbank merkt sich einen Fingerabdruck des Schlüssels. Startet die
Anwendung mit einem anderen oder ohne Schlüssel, obwohl schon
verschlüsselte Daten existieren, bricht sie mit einer klaren Meldung ab,
statt einen neuen Schlüssel zu erzeugen und die vorhandenen Daten
unlesbar zu machen.

Der Schlüssel liegt im Normalfall im selben Verzeichnis wie die
Datenbank und landet deshalb auch in derselben Home-Assistant-Sicherung.
Er schützt eine abgezogene Datenbankdatei, nicht eine vollständige
Sicherung. Wer das trennen will, setzt die Option ``schluessel`` und
verwahrt den Wert getrennt.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
import struct
from functools import lru_cache
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

log = logging.getLogger("scopex.schutz")

PRAEFIX = "enc:v1:"

# Was verschlüsselt gespeichert wird. Eine Spalte hier aufzunehmen heißt
# auch: sie darf in keiner SQL-Bedingung, Sortierung oder Gruppierung
# vorkommen. Die Prüfschleife sucht nach Klartext in diesen Spalten.
SPALTEN: dict[str, tuple[str, ...]] = {
    "users": ("email",),
    "user_profile": ("first_name", "last_name", "registration_id", "specialty",
                     "role", "headline", "about", "location", "organisation"),
    "invitations": ("email", "note"),
    "applications": ("first_name", "last_name", "email", "qualification",
                     "organisation", "wache", "motivation", "sponsor_text",
                     "decision_note"),
    "referrals": ("email", "name"),
    "encounters": ("mission_number", "shift_code", "vehicle_id"),
    "measure_attempts": ("note",),
    "medication_administrations": ("note", "adverse_effect", "follow_up"),
    "net_messages": ("body",),
    "net_posts": ("title", "body", "details", "snapshot", "link_title",
                  "removed_reason"),
    "net_comments": ("body", "removed_reason"),
    "net_profile_entries": ("title", "org", "note"),
    "net_fortbildungen": ("titel",),
    "audit_log": ("old_value", "new_value"),
}
# Spalten mit Blindindex: Tabelle -> (Klartextspalte, Indexspalte).
INDEX = {"users": ("email", "email_idx"), "applications": ("email", "email_idx"),
         "referrals": ("email", "email_idx")}


class SchluesselFehler(RuntimeError):
    """Schlüssel fehlt oder passt nicht zu den vorhandenen Daten."""


# --------------------------------------------------------------------------
# Schlüssel
# --------------------------------------------------------------------------

def _datei() -> Path:
    ausdruecklich = os.environ.get("SCOPEX_SCHLUESSELDATEI", "").strip()
    if ausdruecklich:
        return Path(ausdruecklich)
    url = os.environ.get("SCOPEX_DATABASE_URL", "sqlite:////data/scopex.db")
    if url.startswith("sqlite:///"):
        return Path(url[len("sqlite:///"):]).parent / "scopex.key"
    return Path("/data/scopex.key")


def _hauptschluessel(neu_erlaubt: bool) -> bytes:
    wert = os.environ.get("SCOPEX_SCHLUESSEL", "").strip()
    if wert:
        try:
            roh = base64.b64decode(wert, validate=True)
        except ValueError as exc:
            raise SchluesselFehler("Die Option „schluessel“ ist kein gültiges Base64.") from exc
        if len(roh) != 32:
            raise SchluesselFehler("Die Option „schluessel“ muss 32 Byte (Base64) lang sein.")
        return roh
    pfad = _datei()
    if pfad.exists():
        roh = pfad.read_bytes()
        if len(roh) != 32:
            raise SchluesselFehler(f"Die Schlüsseldatei {pfad.name} ist beschädigt.")
        return roh
    if not neu_erlaubt:
        raise SchluesselFehler(
            "Es gibt verschlüsselte Daten, aber keinen Schlüssel. Die Schlüsseldatei "
            f"{pfad.name} fehlt. Bitte aus der Sicherung zurückholen.")
    pfad.parent.mkdir(parents=True, exist_ok=True)
    roh = secrets.token_bytes(32)
    fd = os.open(pfad, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(roh)
    log.info("Neuer Schlüssel für die Verschlüsselung im Ruhezustand angelegt.")
    return roh


def _ableiten(haupt: bytes, zweck: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=b"scopex",
                info=zweck).derive(haupt)


_HAUPT: bytes | None = None


def laden(neu_erlaubt: bool) -> None:
    """Lädt den Hauptschlüssel. Beim Start aufgerufen; neu_erlaubt nur,
    solange die Datenbank noch keinen Fingerabdruck kennt."""
    global _HAUPT
    _HAUPT = _hauptschluessel(neu_erlaubt)
    _schluessel.cache_clear()
    _datei_aes.cache_clear()


def _haupt() -> bytes:
    if _HAUPT is None:
        laden(neu_erlaubt=True)
    return _HAUPT


@lru_cache(maxsize=1)
def _schluessel() -> tuple[AESGCM, bytes, str]:
    haupt = _haupt()
    aes = AESGCM(_ableiten(haupt, b"scopex-feld-v1"))
    idx = _ableiten(haupt, b"scopex-index-v1")
    kennung = hmac.new(idx, b"scopex-kennung", hashlib.sha256).hexdigest()[:16]
    return aes, idx, kennung


@lru_cache(maxsize=1)
def _datei_aes() -> AESGCM:
    return AESGCM(_ableiten(_haupt(), b"scopex-datei-v1"))


# --------------------------------------------------------------------------
# Felder
# --------------------------------------------------------------------------

def v(text):
    """Verschlüsselt einen Wert. None und leere Werte bleiben, wie sie sind;
    bereits Verschlüsseltes wird nicht doppelt verschlüsselt."""
    if text is None or text == "":
        return text
    text = str(text)
    if text.startswith(PRAEFIX):
        return text
    aes = _schluessel()[0]
    nonce = secrets.token_bytes(12)
    roh = nonce + aes.encrypt(nonce, text.encode("utf-8"), PRAEFIX.encode())
    return PRAEFIX + base64.urlsafe_b64encode(roh).decode("ascii")


def e(wert):
    """Entschlüsselt, wenn der Wert verschlüsselt ist; sonst unverändert.
    Ein Wert, der nur zufällig mit dem Präfix beginnt und sich nicht
    entschlüsseln lässt, bleibt ebenfalls unverändert."""
    if not isinstance(wert, str) or not wert.startswith(PRAEFIX):
        return wert
    try:
        roh = base64.urlsafe_b64decode(wert[len(PRAEFIX):])
        return _schluessel()[0].decrypt(roh[:12], roh[12:], PRAEFIX.encode()).decode("utf-8")
    except Exception:  # noqa: BLE001 - kein Absturz wegen eines Einzelwerts
        log.warning("Ein verschlüsselter Wert ließ sich nicht entschlüsseln.")
        return wert


def fuer(tabelle: str, spalte: str, wert):
    """Verschlüsselt, wenn die Spalte geschützt ist. Für Stellen, an denen
    die Spalte erst zur Laufzeit feststeht."""
    return v(wert) if spalte in SPALTEN.get(tabelle, ()) else wert


def zeile(d: dict) -> dict:
    for k, wert in d.items():
        if isinstance(wert, str) and wert.startswith(PRAEFIX):
            d[k] = e(wert)
    return d


def index(wert: str | None) -> str | None:
    """Blindindex für Vergleiche. Normalisiert auf Kleinschreibung."""
    if not wert:
        return None
    norm = str(wert).strip().lower()
    return hmac.new(_schluessel()[1], norm.encode("utf-8"), hashlib.sha256).hexdigest()


def kennung() -> str:
    return _schluessel()[2]


# --------------------------------------------------------------------------
# Dateien
# --------------------------------------------------------------------------

MAGIE = b"SXE1"
BLOCK = 64 * 1024
TAG = 16
KOPF = len(MAGIE) + 8 + 4


def _aad(kopf: bytes, nummer: int, letzter: bool) -> bytes:
    return kopf + struct.pack(">I?", nummer, letzter)


def datei_verschluesseln(quelle: Path, ziel: Path) -> None:
    """Schreibt quelle verschlüsselt nach ziel (darf dieselbe Datei sein)."""
    aes = _datei_aes()
    praefix = secrets.token_bytes(8)
    kopf = MAGIE + praefix + struct.pack(">I", BLOCK)
    tmp = ziel.with_name(ziel.name + ".enc-tmp")
    groesse = quelle.stat().st_size
    anzahl = max(1, -(-groesse // BLOCK))
    with quelle.open("rb") as ein, tmp.open("wb") as aus:
        aus.write(kopf)
        for n in range(anzahl):
            stueck = ein.read(BLOCK)
            nonce = praefix + struct.pack(">I", n)
            aus.write(aes.encrypt(nonce, stueck, _aad(kopf, n, n == anzahl - 1)))
    os.chmod(tmp, 0o600)
    os.replace(tmp, ziel)


def bytes_verschluesselt_schreiben(daten: bytes, ziel: Path) -> None:
    roh = ziel.with_name(ziel.name + ".roh-tmp")
    fd = os.open(roh, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(daten)
    try:
        datei_verschluesseln(roh, ziel)
    finally:
        roh.unlink(missing_ok=True)


def ist_verschluesselt(pfad: Path) -> bool:
    with pfad.open("rb") as f:
        return f.read(len(MAGIE)) == MAGIE


def klartext_groesse(pfad: Path) -> int:
    if not ist_verschluesselt(pfad):
        return pfad.stat().st_size
    rest = pfad.stat().st_size - KOPF
    anzahl = -(-rest // (BLOCK + TAG))
    return rest - anzahl * TAG


def datei_lesen(pfad: Path, start: int = 0, ende: int | None = None):
    """Liefert den Klartext von start bis einschließlich ende in Stücken.
    Unverschlüsselte Altdateien werden unverändert gelesen."""
    groesse = klartext_groesse(pfad)
    if ende is None or ende >= groesse:
        ende = groesse - 1
    if groesse == 0 or start > ende:
        return
    if not ist_verschluesselt(pfad):
        with pfad.open("rb") as f:
            f.seek(start)
            rest = ende - start + 1
            while rest > 0:
                stueck = f.read(min(BLOCK, rest))
                if not stueck:
                    break
                rest -= len(stueck)
                yield stueck
        return
    aes = _datei_aes()
    anzahl = -(-(pfad.stat().st_size - KOPF) // (BLOCK + TAG))
    with pfad.open("rb") as f:
        kopf = f.read(KOPF)
        praefix = kopf[len(MAGIE):len(MAGIE) + 8]
        for n in range(start // BLOCK, ende // BLOCK + 1):
            f.seek(KOPF + n * (BLOCK + TAG))
            klar = aes.decrypt(praefix + struct.pack(">I", n), f.read(BLOCK + TAG),
                               _aad(kopf, n, n == anzahl - 1))
            von = start - n * BLOCK if n == start // BLOCK else 0
            bis = ende - n * BLOCK + 1 if n == ende // BLOCK else len(klar)
            yield klar[von:bis]


def datei_bytes(pfad: Path) -> bytes:
    return b"".join(datei_lesen(pfad))


# --------------------------------------------------------------------------
# Start: Schlüssel prüfen, Bestand verschlüsseln
# --------------------------------------------------------------------------

def pruefen_und_einpflegen(c) -> int:
    """Gleicht den Schlüssel mit der Datenbank ab und verschlüsselt, was
    noch im Klartext liegt. Idempotent; gibt die Zahl der Werte zurück.

    Erwartet eine offene Verbindung. Import hier, weil db.py dieses Modul
    importiert."""
    from .db import new_id, q, row, rows  # noqa: PLC0415

    gespeichert = row(c, "SELECT svalue FROM settings WHERE user_id IS NULL AND "
                         "skey = 'schluessel_kennung'")
    kandidat = _hauptschluessel(neu_erlaubt=not gespeichert)
    idx = _ableiten(kandidat, b"scopex-index-v1")
    pruef = hmac.new(idx, b"scopex-kennung", hashlib.sha256).hexdigest()[:16]
    # Erst vergleichen, dann übernehmen: ein falscher Schlüssel darf nicht
    # einmal kurz im Speicher der laufenden Anwendung landen.
    if gespeichert and pruef != gespeichert["svalue"]:
        raise SchluesselFehler(
            "Der Schlüssel passt nicht zu den verschlüsselten Daten. Bitte die "
            "ursprüngliche Schlüsseldatei oder Option „schluessel“ wiederherstellen.")
    global _HAUPT
    _HAUPT = kandidat
    _schluessel.cache_clear()
    _datei_aes.cache_clear()
    if not gespeichert:
        q(c, "INSERT INTO settings (id, user_id, skey, svalue) VALUES "
             "(:i, NULL, 'schluessel_kennung', :k)", i=new_id(), k=kennung())

    gesamt = 0
    for tabelle, spalten in SPALTEN.items():
        schluesselspalte = "user_id" if tabelle == "user_profile" else "id"
        # Bezeichner aus der festen Liste oben, keine Eingaben.
        liste = ", ".join(spalten)
        for r in rows(c, f"SELECT {schluesselspalte} AS k, {liste} FROM {tabelle}",
                      _roh=True):
            neu = {s: v(r[s]) for s in spalten
                   if isinstance(r[s], str) and r[s] and not r[s].startswith(PRAEFIX)}
            if neu:
                setzen = ", ".join(f"{s} = :{s}" for s in neu)
                q(c, f"UPDATE {tabelle} SET {setzen} WHERE {schluesselspalte} = :k",
                  k=r["k"], **neu)
                gesamt += len(neu)
    for tabelle, (spalte, idx) in INDEX.items():
        for r in rows(c, f"SELECT id, {spalte} AS w FROM {tabelle} WHERE {idx} IS NULL "
                         f"AND {spalte} IS NOT NULL"):
            q(c, f"UPDATE {tabelle} SET {idx} = :x WHERE id = :i",
              x=index(r["w"]), i=r["id"])
    return gesamt


def medien_einpflegen(ablage: Path) -> int:
    n = 0
    for pfad in ablage.glob("*"):
        if pfad.is_file() and pfad.suffix in (".jpg", ".mp4") and not ist_verschluesselt(pfad):
            datei_verschluesseln(pfad, pfad)
            n += 1
    return n
