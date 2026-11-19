"""Erzeugt app/data/kreise.json aus dem Gemeindeverzeichnis des Statistischen
Bundesamtes (GV-ISys, „Kreisfreie Städte und Landkreise“).

Aufruf mit der heruntergeladenen Datei:

    python tools/kreise_erzeugen.py 04-kreise.xlsx

Quelle: https://www.destatis.de/DE/Themen/Laender-Regionen/Regionales/
Gemeindeverzeichnis/Administrativ/04-kreise.html
Lizenz: Datenlizenz Deutschland – Namensnennung – Version 2.0,
© Statistisches Bundesamt (Destatis).

Die Datei ändert sich nur bei Gebietsreformen. Der Amtliche
Regionalschlüssel (AGS) bleibt der Schlüssel in der Datenbank; ein Kreis,
der in einem anderen aufgeht, bleibt deshalb lesbar, auch wenn er in der
Auswahl nicht mehr erscheint.
"""
import json
import sys
from pathlib import Path

import openpyxl

ZUSAETZE = (", Stadt", ", Landeshauptstadt", ", Hansestadt", ", Wissenschaftsstadt",
            ", documenta-Stadt", ", Universitätsstadt", ", kreisfreie Stadt",
            ", Klingenstadt", ", Freie und Hansestadt", ", Freie Hansestadt",
            ", Stadtkreis")


def kurzname(name: str) -> str:
    for z in ZUSAETZE:
        if z in name:
            return name.split(z)[0].strip()
    return name.strip()


def main(xlsx: str) -> None:
    wb = openpyxl.load_workbook(xlsx, read_only=True)
    ws = wb["Kreisfreie Städte u. Landkreise"]
    land = ""
    stand = ""
    kreise = []
    for i, zeile in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            stand = str(zeile[0])
            continue
        schluessel, art, name = (zeile[0], zeile[1], zeile[2])
        if not schluessel or not isinstance(schluessel, str):
            continue
        schluessel = schluessel.strip()
        if len(schluessel) == 2 and art and not name:
            land = art.strip()
            continue
        if len(schluessel) == 5 and name:
            kreise.append({"ags": schluessel, "name": kurzname(name),
                           "amtlich": name.strip(), "art": art.strip(),
                           "land": land})
    ziel = Path(__file__).resolve().parents[1] / "app" / "data" / "kreise.json"
    ziel.write_text(json.dumps({"quelle": "Statistisches Bundesamt (Destatis), "
                                          "Gemeindeverzeichnis GV-ISys, dl-de/by-2-0",
                                "stand": stand, "kreise": kreise},
                               ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(kreise)} Kreise geschrieben: {ziel}")


if __name__ == "__main__":
    main(sys.argv[1])
