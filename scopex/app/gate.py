"""Vorgelagerter Schutz der Anmeldung: Herkunft, Drosselung, Rechenaufgabe.

Dieses Modul sitzt vor jeder Prüfung von Zugangsdaten und beantwortet drei
Fragen, bevor überhaupt ein Passwort angefasst wird:

1. Kommt die Anfrage aus einem Land, aus dem wir Anmeldungen erwarten?
2. Hat diese Adresse in letzter Zeit auffällig oft angeklopft?
3. Hat der Client die Rechenaufgabe gelöst, die jede Anfrage verteuert?

Warum das nötig wurde: SCOPE X bleibt aus dem offenen Netz erreichbar. Die
Kontosperre allein war dafür nicht nur zu schwach, sondern selbst
gefährlich — acht falsche Passwörter je Konto genügten, um alle Nutzer
mutwillig auszusperren. Der Schutz muss deshalb an der **Herkunft** der
Anfrage ansetzen, nicht nur am Konto.

Alles hier läuft ohne externen Aufruf. Die Netzliste liegt als Datei im
Image, die Rechenaufgabe ist ein HMAC über die Standardbibliothek.
"""
from __future__ import annotations

import bisect
import hashlib
import hmac
import ipaddress
import logging
import os
import secrets
import threading
import time
from pathlib import Path

log = logging.getLogger("scopex.gate")

DATEN = Path(__file__).parent / "data" / "laendernetze.txt"

# --------------------------------------------------------------------------
# Herkunft
# --------------------------------------------------------------------------

_v4_start: list[int] = []
_v4_ende: list[int] = []
_v6_start: list[int] = []
_v6_ende: list[int] = []
_netze_geladen = False
_netze_fehler: str | None = None


def _lade_netze() -> None:
    """Liest die Netzliste einmalig in zwei sortierte Kantenlisten.

    Gesucht wird später mit bisect statt mit einer Schleife über 55.000
    Netze: ein Vergleich pro Anfrage statt 55.000.
    """
    global _netze_geladen, _netze_fehler
    if _netze_geladen:
        return
    _netze_geladen = True
    v4: list[tuple[int, int]] = []
    v6: list[tuple[int, int]] = []
    try:
        with DATEN.open(encoding="utf-8") as datei:
            for zeile in datei:
                zeile = zeile.strip()
                if not zeile or zeile.startswith("#"):
                    continue
                netz = ipaddress.ip_network(zeile)
                paar = (int(netz.network_address),
                        int(netz.broadcast_address))
                (v4 if netz.version == 4 else v6).append(paar)
    except OSError as fehler:
        _netze_fehler = str(fehler)
        log.warning("Netzliste nicht lesbar (%s). Die Herkunftsprüfung "
                    "lässt deshalb alle Adressen durch.", fehler)
        return

    v4.sort()
    v6.sort()
    _v4_start.extend(s for s, _ in v4)
    _v4_ende.extend(e for _, e in v4)
    _v6_start.extend(s for s, _ in v6)
    _v6_ende.extend(e for _, e in v6)
    log.info("Herkunftsprüfung geladen: %d IPv4- und %d IPv6-Netze",
             len(v4), len(v6))


def netzliste_vorhanden() -> bool:
    _lade_netze()
    return bool(_v4_start)


def _in_liste(adresse: str) -> bool | None:
    """True, False — oder None, wenn keine Aussage möglich ist."""
    _lade_netze()
    if not _v4_start:
        return None
    try:
        ip = ipaddress.ip_address(adresse)
    except ValueError:
        return None
    if ip.is_private or ip.is_loopback or ip.is_link_local:
        # Der Reverse Proxy und alles im eigenen Netz sind nie Gegenstand
        # einer Länderprüfung.
        return True
    wert = int(ip)
    start, ende = (_v4_start, _v4_ende) if ip.version == 4 else (_v6_start, _v6_ende)
    if not start:
        return None
    i = bisect.bisect_right(start, wert) - 1
    if i < 0:
        return False
    return wert <= ende[i]


def herkunft_filter() -> str:
    """'europa' oder 'aus', aus den Add-on-Optionen."""
    return (os.environ.get("SCOPEX_LAENDERFILTER", "europa") or "aus").strip().lower()


def _zusatznetze() -> list:
    roh = os.environ.get("SCOPEX_ZUSATZNETZE", "").strip()
    netze = []
    for teil in roh.replace(";", ",").split(","):
        teil = teil.strip()
        if not teil:
            continue
        try:
            netze.append(ipaddress.ip_network(teil, strict=False))
        except ValueError:
            log.warning("Zusatznetz '%s' ist keine gültige Angabe und wird "
                        "übergangen.", teil)
    return netze


def herkunft_erlaubt(adresse: str | None) -> bool:
    """Entscheidet, ob aus dieser Adresse eine Anmeldung zulässig ist.

    Im Zweifel **offen**: fehlt die Netzliste oder ist die Adresse nicht
    deutbar, wird durchgelassen und gewarnt. Eine Herkunftsprüfung, die
    bei einem Datenfehler den rechtmäßigen Nutzer aussperrt, richtet mehr
    Schaden an als der Scanverkehr, den sie abhält — zumal die übrigen
    Schichten dann weiterhin greifen.
    """
    if herkunft_filter() != "europa":
        return True
    if not adresse:
        return True
    for netz in _zusatznetze():
        try:
            if ipaddress.ip_address(adresse) in netz:
                return True
        except ValueError:
            return True
    urteil = _in_liste(adresse)
    if urteil is None:
        return True
    return urteil


# --------------------------------------------------------------------------
# Drosselung
# --------------------------------------------------------------------------

FENSTER_SEKUNDEN = 600
FENSTER_MAX = 30


def _fenster_max() -> int:
    """Wie viele Anfragen eine Adresse je Fenster stellen darf.

    Konfigurierbar, weil mehrere Nutzer hinter demselben Anschluss sitzen
    können — im Rettungsdienst etwa alle im WLAN derselben Wache. Ein zu
    enger Wert sperrt dann Kollegen aus, die nichts falsch gemacht haben.
    """
    try:
        wert = int(os.environ.get("SCOPEX_ANFRAGEN_JE_FENSTER", "") or FENSTER_MAX)
    except ValueError:
        return FENSTER_MAX
    return max(wert, 5)


_sperre = threading.Lock()
_versuche: dict[str, list[float]] = {}
_abkuehlung: dict[tuple[str, str], float] = {}


def _aufraeumen(jetzt: float) -> None:
    for schluessel, zeiten in list(_versuche.items()):
        frisch = [t for t in zeiten if t > jetzt - FENSTER_SEKUNDEN]
        if frisch:
            _versuche[schluessel] = frisch
        else:
            del _versuche[schluessel]
    for schluessel, bis in list(_abkuehlung.items()):
        if bis < jetzt:
            del _abkuehlung[schluessel]


def fenster_frei(adresse: str | None) -> bool:
    """Zählt Anfragen je Adresse in einem gleitenden Fenster."""
    if not adresse:
        return True
    jetzt = time.time()
    with _sperre:
        _aufraeumen(jetzt)
        zeiten = _versuche.setdefault(adresse, [])
        if len(zeiten) >= _fenster_max():
            return False
        zeiten.append(jetzt)
    return True


def abkuehlung_rest(konto: str, adresse: str | None) -> int:
    """Restzeit in Sekunden, die diese Adresse bei diesem Konto warten muss."""
    if not adresse:
        return 0
    with _sperre:
        bis = _abkuehlung.get((konto, adresse))
    if not bis:
        return 0
    rest = int(bis - time.time())
    return max(rest, 0)


def abkuehlung_setzen(konto: str, adresse: str | None, fehlversuche: int) -> None:
    """Verlängert die Wartezeit dieser Adresse für dieses Konto.

    Die Wartezeit gilt **je Adresse**, nicht je Konto. Das ist der
    entscheidende Unterschied zur früheren Kontosperre: ein Angreifer
    bremst nur sich selbst aus, während der rechtmäßige Nutzer von seinem
    eigenen Anschluss unbehelligt bleibt.
    """
    if not adresse or fehlversuche < 2:
        return
    sekunden = min(2 ** (fehlversuche - 1), 900)
    with _sperre:
        _abkuehlung[(konto, adresse)] = time.time() + sekunden


def abkuehlung_loeschen(konto: str, adresse: str | None) -> None:
    if not adresse:
        return
    with _sperre:
        _abkuehlung.pop((konto, adresse), None)


def abkuehlung_konto_freigeben(konto: str) -> None:
    """Hebt die Abkühlung dieses Kontos für **alle** Adressen auf.

    Nötig nach einer Zurücksetzung des Passworts und nach einem Eingriff
    aus der Verwaltung. Ohne das bliebe jemand, den ein Fremder
    ausgebremst hat, auch nach erfolgreicher Zurücksetzung draußen — also
    ausgerechnet in dem Fall, für den die Zurücksetzung gedacht ist.
    """
    with _sperre:
        for schluessel in [k for k in _abkuehlung if k[0] == konto]:
            del _abkuehlung[schluessel]


def zustand_zuruecksetzen() -> None:
    """Nur für die Testreihen."""
    with _sperre:
        _versuche.clear()
        _abkuehlung.clear()


# --------------------------------------------------------------------------
# Rechenaufgabe
# --------------------------------------------------------------------------

POW_GUELTIG_SEKUNDEN = 300
POW_GRUNDSTUFE = 12
# Höchstens 16 Bit. Gemessen rechnet ein Browser rund 120.000 Hashes je
# Sekunde, ein älteres Telefon deutlich weniger. Stufe 16 bedeutet dort
# etwa eine Sekunde, Stufe 18 schon mehrere — spürbar lästig, ohne einen
# Angreifer mit nativem Code nennenswert mehr zu kosten. Die eigentliche
# Bremse ist das Zeitfenster je Adresse; die Rechenaufgabe verteuert den
# einzelnen Versuch, sie ersetzt die Drosselung nicht.
POW_HOECHSTSTUFE = 16

_geheimnis = secrets.token_bytes(32)
_verbraucht: dict[str, float] = {}


def pow_stufe(fehlversuche: int) -> int:
    """Wie schwer die Aufgabe ist, abhängig von der Vorgeschichte.

    Eine Stufe mehr verdoppelt den Aufwand. Bei der Grundstufe rechnet ein
    Telefon ein paar Millisekunden, bei der Höchststufe einige Sekunden —
    für eine einzelne Anmeldung belanglos, für Zehntausende Versuche der
    Unterschied zwischen billig und unbezahlbar.
    """
    return min(POW_GRUNDSTUFE + max(fehlversuche, 0), POW_HOECHSTSTUFE)


def pow_aufgabe(stufe: int) -> dict:
    ausgabe = secrets.token_hex(16)
    ablauf = int(time.time()) + POW_GUELTIG_SEKUNDEN
    roh = f"{ausgabe}:{stufe}:{ablauf}".encode()
    siegel = hmac.new(_geheimnis, roh, hashlib.sha256).hexdigest()[:32]
    return {"aufgabe": ausgabe, "stufe": stufe, "ablauf": ablauf,
            "siegel": siegel}


def _fuehrende_nullbits(wert: bytes) -> int:
    zahl = 0
    for byte in wert:
        if byte == 0:
            zahl += 8
            continue
        zahl += 8 - byte.bit_length()
        break
    return zahl


def pow_pruefen(aufgabe: str, stufe: int, ablauf: int, siegel: str,
                loesung: str) -> bool:
    """Prüft die Lösung, ohne die Aufgabe gespeichert zu haben.

    Die Aufgabe trägt ihr eigenes Siegel, deshalb braucht der Server
    keinen Zwischenspeicher und übersteht einen Neustart mitten im
    Anmeldevorgang. Verbraucht wird sie trotzdem genau einmal.
    """
    try:
        stufe = int(stufe)
        ablauf = int(ablauf)
    except (TypeError, ValueError):
        return False
    if not aufgabe or not siegel or not loesung:
        return False
    if ablauf < time.time():
        return False
    if not (POW_GRUNDSTUFE <= stufe <= POW_HOECHSTSTUFE):
        return False
    roh = f"{aufgabe}:{stufe}:{ablauf}".encode()
    erwartet = hmac.new(_geheimnis, roh, hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(erwartet, str(siegel)):
        return False

    jetzt = time.time()
    with _sperre:
        for schluessel, zeit in list(_verbraucht.items()):
            if zeit < jetzt - POW_GUELTIG_SEKUNDEN:
                del _verbraucht[schluessel]
        if aufgabe in _verbraucht:
            return False

    digest = hashlib.sha256(f"{aufgabe}:{loesung}".encode()).digest()
    if _fuehrende_nullbits(digest) < stufe:
        return False

    with _sperre:
        _verbraucht[aufgabe] = jetzt
    return True
