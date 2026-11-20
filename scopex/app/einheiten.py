"""Einheiten, die sich umrechnen lassen.

Blutzucker wird in Deutschland meist in mg/dl gemessen, international und
in vielen Geräten in mmol/l. SCOPE X nimmt beides an und speichert immer
mg/dl. So bleiben Auswertungen vergleichbar, und ältere Einträge, die vor
4.7.0 nur mg/dl kannten, brauchen keine Umstellung. Angezeigt werden beide
Werte, die bevorzugte Einheit zuerst.

Umrechnung über die molare Masse der Glukose, 180,16 g/mol:
1 mmol/l = 18,016 mg/dl.
"""
from __future__ import annotations

import math

from fastapi import HTTPException

MGDL_JE_MMOL = 18.016
GLUKOSE_EINHEITEN = ("mg/dl", "mmol/l")
# Plausibilitätsgrenzen, keine klinischen Schwellen. Messgeräte im
# Rettungsdienst zeigen etwa unter 20 und über 600 mg/dl nur LO oder HI;
# Werte außerhalb von 10 bis 1000 mg/dl sind deshalb fast immer ein
# Tippfehler oder die falsche Einheit. Die Grenzen fangen die häufigste
# Verwechslung ab: ein mg/dl-Wert ab 56, als mmol/l eingegeben, und ein
# mmol/l-Wert, als mg/dl eingegeben.
GLUKOSE_MIN_MGDL = 10
GLUKOSE_MAX_MGDL = 1000


def _zahl(wert) -> float:
    try:
        zahl = float(str(wert).strip().replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "Der Blutzuckerwert muss eine Zahl sein.") from exc
    if not math.isfinite(zahl):
        raise HTTPException(400, "Der Blutzuckerwert muss eine Zahl sein.")
    return zahl


def glukose_in_mgdl(wert, einheit: str | None) -> int:
    """Rechnet eine Eingabe in ganze mg/dl um und prüft die Plausibilität."""
    einheit = einheit or "mg/dl"
    if einheit not in GLUKOSE_EINHEITEN:
        raise HTTPException(400, "Unbekannte Einheit für den Blutzucker.")
    zahl = _zahl(wert)
    mgdl = round(zahl * MGDL_JE_MMOL) if einheit == "mmol/l" else round(zahl)
    if not GLUKOSE_MIN_MGDL <= mgdl <= GLUKOSE_MAX_MGDL:
        if einheit == "mmol/l":
            grenze = (f"{GLUKOSE_MIN_MGDL / MGDL_JE_MMOL:.1f} und "
                      f"{GLUKOSE_MAX_MGDL / MGDL_JE_MMOL:.0f} mmol/l").replace(".", ",")
        else:
            grenze = f"{GLUKOSE_MIN_MGDL} und {GLUKOSE_MAX_MGDL} mg/dl"
        raise HTTPException(400, f"Der Blutzuckerwert muss zwischen {grenze} liegen. "
                                 "Stimmt die Einheit?")
    return mgdl


def mmol_text(mgdl) -> str:
    """mg/dl als mmol/l mit einer Nachkommastelle, deutsches Komma."""
    return f"{_zahl(mgdl) / MGDL_JE_MMOL:.1f}".replace(".", ",") + " mmol/l"


def parameter_text(p: dict) -> str:
    """Ein Parameter als Text für PDF und CSV, Blutzucker in beiden
    Einheiten. Erwartet label, value (oder value_text) und unit."""
    wert = p.get("value", p.get("value_text"))
    einheit = p.get("unit") or ""
    text = f"{p['label']}: {wert}{(' ' + einheit) if einheit else ''}"
    if einheit == "mg/dl":
        try:
            text += f" ({mmol_text(wert)})"
        except HTTPException:
            pass
    return text
