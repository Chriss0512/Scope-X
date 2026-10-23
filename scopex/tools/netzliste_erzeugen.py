#!/usr/bin/env python3
"""Erzeugt die Länder-Netzliste für die Herkunftsprüfung.

Grundlage sind die Delegationsdateien der Regional Internet Registries.
Sie sind öffentlich, frei weiterverwendbar und die Quelle, aus der sich
jede andere Geo-Datenbank ebenfalls speist — nur ohne Lizenzschlüssel,
ohne Konto und ohne Anbieter, der den Dienst einstellen kann.

Für europäische Adressräume genügen RIPE NCC und ARIN. RIPE verwaltet
Europa, ARIN hält den älteren Bestand, der vor der Gründung von RIPE
vergeben wurde und bis heute dort geführt wird.

Aufruf:

    python tools/netzliste_erzeugen.py

Schreibt `app/data/laendernetze.txt`. Das Ergebnis gehört ins
Repository: zur Laufzeit wird nichts nachgeladen.
"""
from __future__ import annotations

import ipaddress
import sys
import urllib.request
from pathlib import Path

QUELLEN = {
    "ripencc": "https://ftp.ripe.net/pub/stats/ripencc/"
               "delegated-ripencc-extended-latest",
    "arin": "https://ftp.arin.net/pub/stats/arin/"
            "delegated-arin-extended-latest",
}

# Europa ohne Russland und ohne den Balkan außerhalb der EU.
#
# Enthalten: die 27 EU-Staaten, die EFTA (Schweiz, Norwegen, Island,
# Liechtenstein), das Vereinigte Königreich mit den Kronbesitzungen, die
# europäischen Kleinstaaten sowie Gibraltar, Färöer und Grönland.
#
# Bewusst nicht enthalten: Russland und Belarus, die Nicht-EU-Staaten des
# Balkans (Albanien, Bosnien und Herzegowina, Kosovo, Montenegro,
# Nordmazedonien, Serbien), außerdem Ukraine, Moldau und die Türkei.
# Bulgarien, Griechenland, Kroatien, Rumänien und Slowenien liegen auf
# oder am Balkan, sind aber EU-Mitglieder und deshalb enthalten.
LAENDER = sorted({
    # EU 27
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE",
    "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT",
    "RO", "SK", "SI", "ES", "SE",
    # EFTA
    "CH", "NO", "IS", "LI",
    # Vereinigtes Königreich und Kronbesitzungen
    "GB", "GG", "JE", "IM",
    # Kleinstaaten
    "AD", "MC", "SM", "VA",
    # Weitere europäische Gebiete
    "GI", "FO", "GL", "AX",
})

ZIEL = Path(__file__).resolve().parent.parent / "app" / "data" / "laendernetze.txt"


def hole(url: str) -> list[str]:
    print(f"lade {url}", file=sys.stderr)
    with urllib.request.urlopen(url, timeout=300) as antwort:
        return antwort.read().decode("utf-8", "replace").splitlines()


def netze(zeilen: list[str]) -> tuple[list, list]:
    """Liest Zuteilungen und gibt sie als Netzobjekte zurück.

    In diesen Dateien ist das vierte Feld bei IPv4 die **Anzahl** der
    Adressen, nicht die Präfixlänge, und sie ist nicht zwingend eine
    Zweierpotenz. Ein Bereich zerfällt deshalb in mehrere CIDR-Blöcke.
    Bei IPv6 ist dasselbe Feld die Präfixlänge. Wer das verwechselt,
    erzeugt eine Liste, die zu viel oder zu wenig abdeckt.
    """
    v4: list[ipaddress.IPv4Network] = []
    v6: list[ipaddress.IPv6Network] = []
    for zeile in zeilen:
        if not zeile or zeile.startswith("#"):
            continue
        teile = zeile.split("|")
        if len(teile) < 7:
            continue
        _, cc, art, start, wert, _, status = teile[:7]
        if cc not in LAENDER:
            continue
        if status not in ("allocated", "assigned"):
            continue
        try:
            if art == "ipv4":
                erste = ipaddress.IPv4Address(start)
                letzte = erste + int(wert) - 1
                v4.extend(ipaddress.summarize_address_range(erste, letzte))
            elif art == "ipv6":
                v6.append(ipaddress.IPv6Network(f"{start}/{wert}"))
        except (ipaddress.AddressValueError, ValueError):
            continue
    return v4, v6


def main() -> int:
    v4: list = []
    v6: list = []
    for name, url in QUELLEN.items():
        try:
            a, b = netze(hole(url))
        except Exception as fehler:  # noqa: BLE001 - Lauf soll weitergehen
            print(f"WARNUNG: {name} nicht erreichbar: {fehler}", file=sys.stderr)
            continue
        v4 += a
        v6 += b

    if not v4:
        print("FEHLER: keine IPv4-Netze eingelesen, Datei bleibt unverändert.",
              file=sys.stderr)
        return 1

    # Zusammenfassen: benachbarte Blöcke verschmelzen, das halbiert die
    # Liste und beschleunigt die spätere Suche.
    v4 = list(ipaddress.collapse_addresses(v4))
    v6 = list(ipaddress.collapse_addresses(v6))

    ZIEL.parent.mkdir(parents=True, exist_ok=True)
    with ZIEL.open("w", encoding="utf-8") as datei:
        datei.write("# Erzeugt von tools/netzliste_erzeugen.py\n")
        datei.write("# Quellen: RIPE NCC und ARIN, Delegationsdateien\n")
        datei.write(f"# Länder: {' '.join(LAENDER)}\n")
        datei.write(f"# Netze: {len(v4)} IPv4, {len(v6)} IPv6\n")
        for netz in v4:
            datei.write(f"{netz}\n")
        for netz in v6:
            datei.write(f"{netz}\n")

    print(f"{len(v4)} IPv4- und {len(v6)} IPv6-Netze nach {ZIEL} geschrieben",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
