"""Kataloge für das Kompetenznetz: Kreise, Organisationen, Wachen,
Qualifikationen.

Warum Listen statt Freitext: „Heidekreis“, „LK Heidekreis“ und
„Landkreis Heidekreis“ sind für einen Menschen dasselbe, für einen
Vergleich drei verschiedene Dinge. Vorschläge („auch im Heidekreis“),
Suchfilter („alle mit PHTLS in der Region Hannover“) und Ablaufhinweise
funktionieren nur mit eindeutigen Einträgen.

* **Kreise** kommen aus dem Gemeindeverzeichnis des Statistischen
  Bundesamtes (app/data/kreise.json, erzeugt mit tools/kreise_erzeugen.py).
  Schlüssel ist der Amtliche Regionalschlüssel.
* **Organisationen** beginnen mit einer kleinen Grundliste. Mitglieder
  ergänzen fehlende; die Administration sichtet, benennt um, führt
  zusammen.
* **Wachen** entstehen ausschließlich aus Einreichungen der Mitglieder,
  jeweils mit Organisation und Kreis.
* **Qualifikationen** sind kuratiert. Mitglieder können eine fehlende
  vorschlagen; sie wird erst nach Freigabe für alle wählbar.

Gültigkeitsdauern stammen aus den Angaben der Herausgeber, soweit belegt
(Quelle im Feld ``quelle``). Wo keine belegte Angabe vorlag, steht keine
Dauer: lieber kein Ablaufhinweis als ein falscher. Die Administration kann
jede Angabe anpassen.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from .db import new_id, now_iso, q, row

DATEN = Path(__file__).parent / "data" / "kreise.json"


@lru_cache(maxsize=1)
def kreise() -> dict:
    daten = json.loads(DATEN.read_text(encoding="utf-8"))
    return {k["ags"]: k for k in daten["kreise"]}


def kreis_name(ags: str | None) -> str:
    k = kreise().get(ags or "")
    return k["name"] if k else ""


def kreis_label(ags: str | None) -> str:
    """Name mit Art, wo der Name allein mehrdeutig ist (Stadt und
    Landkreis München)."""
    k = kreise().get(ags or "")
    if not k:
        return ""
    gleich = sum(1 for x in kreise().values() if x["name"] == k["name"])
    if gleich > 1:
        art = "Stadt" if "Stadt" in k["art"] or k["art"] == "Stadtkreis" else "Landkreis"
        return f"{k['name']} ({art})"
    return k["name"]


def kreis_gueltig(ags: str | None) -> bool:
    return bool(ags) and ags in kreise()


def normalisiert(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


ORG_ARTEN = ("hilfsorganisation", "kommunal", "feuerwehr", "privat", "luftrettung",
             "klinik", "bundeswehr", "sonstige")

# Grundliste: bundesweit tätige Träger. Örtliche Gesellschaften
# („Rettungsdienst Heidekreis gGmbH“) ergänzen die Mitglieder.
ORGANISATIONEN = [
    ("drk", "Deutsches Rotes Kreuz (DRK)", "hilfsorganisation"),
    ("juh", "Johanniter-Unfall-Hilfe", "hilfsorganisation"),
    ("mhd", "Malteser Hilfsdienst", "hilfsorganisation"),
    ("asb", "Arbeiter-Samariter-Bund (ASB)", "hilfsorganisation"),
    ("dlrg", "DLRG", "hilfsorganisation"),
    ("feuerwehr", "Feuerwehr (kommunal)", "feuerwehr"),
    ("kommunal", "Kommunaler Rettungsdienst", "kommunal"),
    ("privat", "Privater Rettungsdienst", "privat"),
    ("adac-lr", "ADAC Luftrettung", "luftrettung"),
    ("drf", "DRF Luftrettung", "luftrettung"),
    ("bw-san", "Sanitätsdienst der Bundeswehr", "bundeswehr"),
    ("klinik", "Klinik oder Krankenhaus", "klinik"),
]

QUAL_KATEGORIEN = ("Berufsabschluss", "Funktion und Zusatzqualifikation",
                   "Reanimation", "Trauma", "Weitere Kurse")

_ERC = "ERC: Zertifikat gilt drei Jahre (für ALS belegt, Refresher verlängert um drei Jahre)"
_AHA = "AHA: Kurskarten gelten zwei Jahre bis Monatsende"
_NAEMT = "NAEMT: Providerkarte gilt vier Jahre"
_NAEMT_ANALOG = "NAEMT-Providerkurs; Dauer analog PHTLS/AMLS, bitte prüfen"

# (code, Name, Kurzform, Kategorie, Herausgeber, Monate, Stunden/Jahr, Quelle)
QUALIFIKATIONEN = [
    ("notsan", "Notfallsanitäter*in", "NotSan", "Berufsabschluss", "", None, None,
     "Jährliche Fortbildungspflicht regelt das Landesrecht; Stunden in der "
     "Administration hinterlegen"),
    ("rettsan", "Rettungssanitäter*in", "RettSan", "Berufsabschluss", "", None, None, ""),
    ("retth", "Rettungshelfer*in", "RettH", "Berufsabschluss", "", None, None, ""),
    ("na", "Notärztin/Notarzt (Zusatzbezeichnung Notfallmedizin)", "NA",
     "Berufsabschluss", "Ärztekammer", None, None, ""),
    ("pflege", "Pflegefachfrau/Pflegefachmann", "Pflege", "Berufsabschluss", "", None, None, ""),
    ("fk-ai", "Fachpflege Anästhesie und Intensivpflege", "Fachpflege A/I",
     "Berufsabschluss", "", None, None, ""),
    ("pal", "Praxisanleiter*in Rettungsdienst", "PAL", "Funktion und Zusatzqualifikation",
     "", None, 24, "NotSan-APrV § 3: 300 Std. Zusatzqualifikation, "
     "24 Std. berufspädagogische Fortbildung jährlich"),
    ("orgl", "Organisatorische*r Leiter*in Rettungsdienst", "OrgL",
     "Funktion und Zusatzqualifikation", "", None, None, ""),
    ("lna", "Leitende*r Notärztin/Notarzt", "LNA", "Funktion und Zusatzqualifikation",
     "", None, None, ""),
    ("disponent", "Leitstellendisponent*in", "Disponent*in",
     "Funktion und Zusatzqualifikation", "", None, None, ""),
    ("desinfektor", "Desinfektor*in", "Desinfektor*in", "Funktion und Zusatzqualifikation",
     "", None, None, ""),
    ("erc-bls", "ERC Basic Life Support", "ERC BLS", "Reanimation", "ERC/GRC", 36, None, _ERC),
    ("erc-ils", "ERC Immediate Life Support", "ERC ILS", "Reanimation", "ERC/GRC", 36, None, _ERC),
    ("erc-als", "ERC Advanced Life Support", "ERC ALS", "Reanimation", "ERC/GRC", 36, None, _ERC),
    ("erc-epals", "ERC European Paediatric Advanced Life Support", "ERC EPALS",
     "Reanimation", "ERC/GRC", 36, None, _ERC),
    ("erc-nls", "ERC Newborn Life Support", "ERC NLS", "Reanimation", "ERC/GRC", 36, None, _ERC),
    ("aha-bls", "AHA Basic Life Support", "AHA BLS", "Reanimation", "AHA", 24, None, _AHA),
    ("aha-acls", "AHA Advanced Cardiovascular Life Support", "ACLS", "Reanimation",
     "AHA", 24, None, _AHA),
    ("aha-pals", "AHA Pediatric Advanced Life Support", "PALS", "Reanimation",
     "AHA", 24, None, _AHA),
    ("phtls", "Prehospital Trauma Life Support", "PHTLS", "Trauma", "NAEMT", 48, None, _NAEMT),
    ("tecc", "Tactical Emergency Casualty Care", "TECC", "Trauma", "NAEMT", 48, None,
     _NAEMT_ANALOG),
    ("itls", "International Trauma Life Support", "ITLS", "Trauma", "ITLS", None, None,
     "Gültigkeit nicht hinterlegt"),
    ("atls", "Advanced Trauma Life Support", "ATLS", "Trauma", "ACS", None, None,
     "Gültigkeit nicht hinterlegt"),
    ("amls", "Advanced Medical Life Support", "AMLS", "Weitere Kurse", "NAEMT", 48, None,
     _NAEMT),
    ("epc", "Emergency Pediatric Care", "EPC", "Weitere Kurse", "NAEMT", 48, None,
     _NAEMT_ANALOG),
    ("gems", "Geriatric Emergency Medical Services", "GEMS", "Weitere Kurse", "NAEMT", 48,
     None, _NAEMT_ANALOG),
]


THEMEN_KATEGORIEN = ("Fachthema", "Format", "Recht und Beruf", "Einsatzbereich", "Hilfe")

# Kuratierte Themen. Der code ist der Hashtag: #Atemwegsmanagement im Text
# und die Auswahl im Formular landen im selben Schlagwort.
THEMEN = [
    ("atemwegsmanagement", "Atemwegsmanagement", "Fachthema"),
    ("reanimation", "Reanimation", "Fachthema"),
    ("trauma", "Traumaversorgung", "Fachthema"),
    ("kindernotfall", "Kindernotfall", "Fachthema"),
    ("geburtshilfe", "Geburtshilfe", "Fachthema"),
    ("ekg", "EKG", "Fachthema"),
    ("schlaganfall", "Schlaganfall und Neurologie", "Fachthema"),
    ("akutes-koronarsyndrom", "Akutes Koronarsyndrom", "Fachthema"),
    ("sepsis", "Sepsis", "Fachthema"),
    ("intoxikation", "Intoxikation", "Fachthema"),
    ("psychiatrie", "Psychiatrische Notfälle", "Fachthema"),
    ("geriatrie", "Geriatrie", "Fachthema"),
    ("pharmakologie", "Pharmakologie", "Fachthema"),
    ("hygiene", "Hygiene und Infektionsschutz", "Fachthema"),
    ("fallvorstellung", "Fallvorstellung", "Format"),
    ("ekg-quiz", "EKG-Quiz", "Format"),
    ("fallquiz", "Fallquiz", "Format"),
    ("lernkarte", "Lernkarte", "Format"),
    ("recht-2anotsang", "Recht: § 2a NotSanG", "Recht und Beruf"),
    ("dokumentation", "Dokumentation", "Recht und Beruf"),
    ("praxisanleitung", "Praxisanleitung", "Recht und Beruf"),
    ("ausbildung", "Ausbildung", "Recht und Beruf"),
    ("berufspolitik", "Berufspolitik", "Recht und Beruf"),
    ("luftrettung", "Luftrettung", "Einsatzbereich"),
    ("intensivverlegung", "Intensivverlegung", "Einsatzbereich"),
    ("manv", "MANV und Großschadenslage", "Einsatzbereich"),
    ("wasserrettung", "Wasserrettung", "Einsatzbereich"),
    ("bergrettung", "Berg- und Höhenrettung", "Einsatzbereich"),
    ("leitstelle", "Leitstelle", "Einsatzbereich"),
    ("peer-hilfe", "Peer-to-Peer-Hilfe", "Hilfe"),
    ("einsatznachsorge", "Einsatznachsorge (PSNV)", "Hilfe"),
]


def einspielen(c) -> int:
    """Ergänzt fehlende Grundeinträge. Vorhandene bleiben unangetastet,
    auch wenn die Administration sie geändert hat: der code ist der
    Anker, nicht der Name."""
    neu = 0
    for code, name, art in ORGANISATIONEN:
        if not row(c, "SELECT id FROM net_organisations WHERE code = :c", c=code):
            q(c, "INSERT INTO net_organisations (id, code, name, art, status, "
                 "created_at) VALUES (:i, :c, :n, :a, 'frei', :t)",
              i=new_id(), c=code, n=name, a=art, t=now_iso())
            neu += 1
    for pos, (code, name, kurz, kat, hg, monate, stunden, quelle) in enumerate(QUALIFIKATIONEN):
        if not row(c, "SELECT id FROM net_qualifications WHERE code = :c", c=code):
            q(c, "INSERT INTO net_qualifications (id, code, name, kurz, kategorie, "
                 "herausgeber, gueltig_monate, fortbildung_stunden, quelle, status, "
                 "sort_order, created_at) VALUES (:i, :c, :n, :k, :ka, :h, :m, :s, "
                 ":q, 'frei', :p, :t)",
              i=new_id(), c=code, n=name, k=kurz, ka=kat, h=hg or None, m=monate,
              s=stunden, q=quelle or None, p=pos, t=now_iso())
            neu += 1
    for pos, (code, name, kategorie) in enumerate(THEMEN):
        if not row(c, "SELECT code FROM net_topics WHERE code = :c", c=code):
            q(c, "INSERT INTO net_topics (code, name, kategorie, status, sort_order, "
                 "created_at) VALUES (:c, :n, :k, 'frei', :p, :t)",
              c=code, n=name, k=kategorie, p=pos, t=now_iso())
            neu += 1
    return neu


def gueltig_bis(erworben: str | None, monate: int | None) -> str | None:
    """Monatsgenau: erworben 2025-03 plus 48 Monate ergibt 2029-03."""
    if not erworben or not monate or not re.fullmatch(r"\d{4}-\d{2}", erworben[:7]):
        return None
    jahr, monat = int(erworben[:4]), int(erworben[5:7])
    gesamt = jahr * 12 + (monat - 1) + monate
    return f"{gesamt // 12:04d}-{gesamt % 12 + 1:02d}"
