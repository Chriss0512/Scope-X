"""Kompetenznetz: Profile, Kontakte, Beiträge, Reaktionen, Bestätigungen.

Aufbau nach dem Vorbild beruflicher Netzwerke, zugeschnitten auf Lernen und
Kompetenz im Rettungsdienst. Geteilt wird nur innerhalb dieser Instanz und
nur mit bestätigten Kontakten. Nichts hiervon ist ohne Anmeldung erreichbar.

DIE GRENZE ZUM PRIVATEN LOGBUCH

Einsatznummer, Einsatzdatum, Einsatzuhrzeit, Schicht, Fahrzeug, die
Zeitstempel einzelner Maßnahmen und Gaben, Freitext-Notizen, Dosierung und
Patientenschaden verlassen das Logbuch nie. Durchgesetzt durch Bauart:

1. net_posts hat keine Spalte für eines dieser Felder und keine
   encounter_id.
2. _schnappschuss() liest ausschließlich die Felder der Allowlist. Was
   dort nicht steht, wird gar nicht erst abgefragt.
3. _pruefe_text() weist Beitragstexte ab, die eigene Einsatznummern,
   Fahrzeugkennungen, Einsatzdaten oder Uhrzeiten enthalten.

Benutzername und E-Mail-Adresse anderer Mitglieder werden nie ausgegeben:
beides sind Anmeldemerkmale. Angezeigt wird der Name aus dem Profil.

Nicht sichtbare Objekte antworten mit 404, nicht mit 403, damit sich ihre
Existenz nicht erfragen lässt.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import bilder
from ..core import audit, current_user
from ..db import conn, new_id, now_iso, q, row, rows, scalar

router = APIRouter(prefix="/api/netz", tags=["netz"])

REAKTIONEN = ("stark", "lehrreich", "danke")
BESTAETIGUNGSROLLEN = ("kollegial", "praxisanleitung")
BEITRAGSARTEN = ("text", "wissen", "kompetenz")
FEED_SEITE = 30

# Allowlist der Felder, die ein Kompetenzbeitrag aus dem Logbuch übernimmt.
# Bewusst als Konstante sichtbar: wer hier etwas ergänzt, ändert die
# Datenschutzgrenze und muss das im Änderungsprotokoll begründen.
MASSNAHME_FELDER = ("measure_name", "measure_category", "outcome",
                    "performer_role")
MEDIKAMENT_FELDER = ("medication_name", "route", "outcome")


# --------------------------------------------------------------------------
# Grundlagen: Profil, Beziehung, Sichtbarkeit
# --------------------------------------------------------------------------

def _profil_sicherstellen(c, uid: str) -> None:
    if not row(c, "SELECT user_id FROM user_profile WHERE user_id = :u", u=uid):
        q(c, "INSERT INTO user_profile (user_id, created_at) VALUES (:u, :t)",
          u=uid, t=now_iso())


def _profil(c, uid: str) -> dict | None:
    return row(c, "SELECT p.*, u.id AS uid, u.role AS account_role, u.disabled_at "
                  "FROM users u LEFT JOIN user_profile p ON p.user_id = u.id "
                  "WHERE u.id = :u", u=uid)


def _anzeigename(p: dict | None) -> str:
    if not p:
        return "Mitglied"
    name = " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x)
    return name.strip() or "Mitglied"


def _aktiv(p: dict | None) -> bool:
    return bool(p and p.get("net_active") and not p.get("disabled_at"))


def _person_kurz(p: dict, beziehung: str) -> dict:
    """Was jedes aktive Mitglied von jedem anderen sehen darf.

    Kein Benutzername, keine E-Mail-Adresse: beides sind Anmeldemerkmale.
    """
    return {
        "id": p["uid"],
        "name": _anzeigename(p),
        "headline": p.get("headline") or "",
        "avatar_id": p.get("avatar_id"),
        "beziehung": beziehung,
    }


def _verbindung(c, a: str, b: str) -> dict | None:
    return row(c, "SELECT * FROM net_connections WHERE "
                  "(requester_id = :a AND addressee_id = :b) OR "
                  "(requester_id = :b AND addressee_id = :a)", a=a, b=b)


def _beziehung(c, ich: str, andere: str) -> str:
    if ich == andere:
        return "selbst"
    v = _verbindung(c, ich, andere)
    if not v:
        return "fremd"
    if v["status"] == "accepted":
        return "kontakt"
    return "ausgehend" if v["requester_id"] == ich else "eingehend"


def _kontakt_ids(c, ich: str) -> set[str]:
    ids = set()
    for v in rows(c, "SELECT requester_id, addressee_id FROM net_connections "
                     "WHERE status = 'accepted' AND "
                     "(requester_id = :i OR addressee_id = :i)", i=ich):
        ids.add(v["addressee_id"] if v["requester_id"] == ich else v["requester_id"])
    return ids


def _aktiv_erforderlich(c, user: dict) -> dict:
    p = _profil(c, user["id"])
    if not _aktiv(p):
        raise HTTPException(
            409, "Aktiviere zuerst dein Netzwerkprofil unter Profil → Netzwerk.")
    return p


def _gemeldet_an(c, admin_id: str, post_id: str) -> bool:
    return bool(row(c, "SELECT id FROM net_notifications WHERE user_id = :u "
                       "AND post_id = :p AND kind = 'meldung'",
                    u=admin_id, p=post_id))


def _darf_beitrag_sehen(c, user: dict, post: dict) -> bool:
    """Die eine Sichtbarkeitsregel für Beiträge.

    Selbst: immer. Sonst: Autor und Leser aktiv, bestätigte Verbindung,
    Beitrag nicht entfernt. Administrator*innen sehen zusätzlich Beiträge,
    die ihnen gemeldet wurden — sonst könnten sie nicht moderieren, was sie
    nicht sehen. Ansonsten haben sie keine Leserechte über andere hinaus.
    """
    if post["removed_at"]:
        return post["author_id"] == user["id"]
    if post["author_id"] == user["id"]:
        return True
    if (user.get("role") or "user") == "admin" and _gemeldet_an(c, user["id"], post["id"]):
        return True
    if not _aktiv(_profil(c, post["author_id"])) or not _aktiv(_profil(c, user["id"])):
        return False
    return _beziehung(c, user["id"], post["author_id"]) == "kontakt"


def _beitrag_oder_404(c, user: dict, post_id: str) -> dict:
    post = row(c, "SELECT * FROM net_posts WHERE id = :i", i=post_id)
    if not post or not _darf_beitrag_sehen(c, user, post):
        raise HTTPException(404, "Beitrag nicht gefunden.")
    return post


def _melde(c, an: str, art: str, von: str | None, post_id: str | None = None) -> None:
    if an == von:
        return
    q(c, "INSERT INTO net_notifications (id, user_id, kind, actor_id, post_id, "
         "created_at) VALUES (:i, :u, :k, :a, :p, :t)",
      i=new_id(), u=an, k=art, a=von, p=post_id, t=now_iso())


# --------------------------------------------------------------------------
# Datenschutzgrenze
# --------------------------------------------------------------------------

# Doppelpunktform nur mit zweistelliger Stunde: "03:12" ist eine Uhrzeit,
# "1:10" oder "1:1000" ist eine Verdünnung. Einstellige Stunden fängt die
# Form mit "Uhr" ab ("3 Uhr", "15.30 Uhr"). Reanimationsverhältnisse wie
# 30:2 oder 15:2 fallen durch beide Muster nicht.
_UHRZEIT = re.compile(
    r"\b(?:[01]\d|2[0-3]):[0-5]\d\b"
    r"|\b(?:[01]?\d|2[0-3])(?:[.:][0-5]\d)?\s*Uhr\b",
    re.IGNORECASE)


def _datumsformen(iso: str) -> set[str]:
    try:
        d = datetime.fromisoformat(iso)
    except ValueError:
        return set()
    return {
        d.strftime("%d.%m.%Y"), d.strftime("%d.%m.%y"), d.strftime("%d.%m."),
        f"{d.day}.{d.month}.{d.year}", f"{d.day}.{d.month}.",
        d.strftime("%Y-%m-%d"),
    }


def _pruefe_text(c, uid: str, text: str, uhrzeit: bool = True) -> None:
    """Weist Texte ab, die private Einsatzangaben enthalten.

    Geprüft wird gegen das **eigene** Logbuch: die eigenen Einsatznummern,
    Fahrzeugkennungen und Einsatzdaten. Das ist genauer als jedes Muster —
    ein Studiendatum oder eine Fahrzeugbezeichnung im Allgemeinen fällt
    nicht darunter, nur das, was tatsächlich aus einem eigenen Einsatz
    stammt. Uhrzeiten werden dagegen generell abgewiesen: sie sind der
    Teil, der einen Einsatz am leichtesten wiederfindbar macht.
    """
    if not text:
        return
    klein = text.lower()
    if uhrzeit and _UHRZEIT.search(text):
        raise HTTPException(
            400, "Der Text enthält eine Uhrzeit. Einsatzzeiten bleiben privat — "
                 "bitte entfernen.")
    for e in rows(c, "SELECT mission_number, vehicle_id, enc_date "
                     "FROM encounters WHERE user_id = :u", u=uid):
        for wert, was in ((e["mission_number"], "eine Einsatznummer"),
                          (e["vehicle_id"], "eine Fahrzeugkennung")):
            if wert and len(wert.strip()) >= 3 and wert.strip().lower() in klein:
                raise HTTPException(
                    400, f"Der Text enthält {was} aus deinem Logbuch "
                         f"(„{wert.strip()}“). Diese Angaben bleiben privat.")
        for form in _datumsformen(e["enc_date"] or ""):
            if form in text:
                raise HTTPException(
                    400, f"Der Text enthält das Datum eines deiner Einsätze "
                         f"(„{form}“). Einsatzdaten bleiben privat.")


def _schnappschuss(c, uid: str, attempt_ids: list[str], medication_ids: list[str],
                   mit_zek: bool, mit_naca: bool) -> dict:
    """Baut den teilbaren Teil eines Einsatzes. Nur Allowlist-Felder.

    Alle Einträge müssen dem Aufrufer gehören, nicht gelöscht sein und aus
    demselben Einsatz stammen. Fremde oder unbekannte Kennungen antworten
    mit 404, ohne zu verraten, ob es sie gibt.
    """
    if not attempt_ids and not medication_ids:
        raise HTTPException(400, "Wähle mindestens eine Maßnahme oder Gabe.")
    if len(attempt_ids) + len(medication_ids) > 20:
        raise HTTPException(400, "Höchstens 20 Einträge je Beitrag.")

    einsaetze: set[str] = set()
    massnahmen, medikamente, zek = [], [], []

    for aid in attempt_ids:
        a = row(c, "SELECT a.id, a.encounter_id, "
                   + ", ".join(f"a.{f}" for f in MASSNAHME_FELDER) +
                   " FROM measure_attempts a JOIN encounters e "
                   "ON e.id = a.encounter_id WHERE a.id = :i AND e.user_id = :u "
                   "AND a.deleted_at IS NULL AND e.deleted_at IS NULL",
                i=aid, u=uid)
        if not a:
            raise HTTPException(404, "Eintrag nicht gefunden.")
        einsaetze.add(a["encounter_id"])
        massnahmen.append({
            "name": a["measure_name"], "kategorie": a["measure_category"],
            "ergebnis": a["outcome"], "rolle": a["performer_role"] or "",
        })
        if mit_zek:
            zek += [z["label"] for z in rows(
                c, "SELECT label FROM attempt_complications WHERE attempt_id = :a",
                a=aid)]

    for mid in medication_ids:
        m = row(c, "SELECT m.id, m.encounter_id, m.medication_id, "
                   + ", ".join(f"m.{f}" for f in MEDIKAMENT_FELDER) +
                   " FROM medication_administrations m JOIN encounters e "
                   "ON e.id = m.encounter_id WHERE m.id = :i AND e.user_id = :u "
                   "AND m.deleted_at IS NULL AND e.deleted_at IS NULL",
                i=mid, u=uid)
        if not m:
            raise HTTPException(404, "Eintrag nicht gefunden.")
        einsaetze.add(m["encounter_id"])
        gruppe = None
        if m["medication_id"]:
            stamm = row(c, "SELECT divi_group FROM medications WHERE id = :i",
                        i=m["medication_id"])
            gruppe = stamm["divi_group"] if stamm else None
        medikamente.append({
            "name": m["medication_name"], "divi_gruppe": gruppe or "",
            "weg": m["route"] or "", "ergebnis": m["outcome"] or "",
        })
        if mit_zek:
            zek += [z["label"] for z in rows(
                c, "SELECT label FROM medication_complications "
                   "WHERE administration_id = :a", a=mid)]

    if len(einsaetze) != 1:
        raise HTTPException(400, "Ein Beitrag teilt Einträge aus genau einem Einsatz.")
    einsatz = einsaetze.pop()
    if mit_zek:
        # Nur die Bezeichnung. Bezug und Patientenschaden bleiben privat:
        # eine geteilte Schadensangabe ist eine Aussage mit Haftungsfolgen.
        zek += [z["label"] for z in rows(
            c, "SELECT label FROM encounter_complications WHERE encounter_id = :e",
            e=einsatz)]

    schnapp = {"massnahmen": massnahmen, "medikamente": medikamente}
    if zek:
        schnapp["zek"] = sorted(set(zek))
    if mit_naca:
        naca = scalar(c, "SELECT naca FROM encounters WHERE id = :e", e=einsatz)
        if naca:
            schnapp["naca"] = naca
    return schnapp


def _pruefe_link(url: str | None) -> str | None:
    """Nur http und https. Kein javascript:, data:, file: — ein Link, den
    andere anklicken, ist sonst ein Einfallstor für Schadcode."""
    if not url:
        return None
    url = url.strip()
    if len(url) > 500:
        raise HTTPException(400, "Der Link ist zu lang.")
    teile = urlparse(url)
    if teile.scheme not in ("http", "https") or not teile.netloc:
        raise HTTPException(400, "Der Link muss mit https:// oder http:// beginnen.")
    return url


# --------------------------------------------------------------------------
# Ausgabe
# --------------------------------------------------------------------------

def _beitrag_aus(c, user: dict, post: dict) -> dict:
    autor = _profil(c, post["author_id"])
    zaehler = dict.fromkeys(REAKTIONEN, 0)
    for r_ in rows(c, "SELECT kind, COUNT(*) AS n FROM net_reactions "
                      "WHERE post_id = :p GROUP BY kind", p=post["id"]):
        if r_["kind"] in zaehler:
            zaehler[r_["kind"]] = r_["n"]
    meine = scalar(c, "SELECT kind FROM net_reactions WHERE post_id = :p "
                      "AND user_id = :u", p=post["id"], u=user["id"])
    eigen = post["author_id"] == user["id"]
    return {
        "id": post["id"],
        "autor": _person_kurz(autor, _beziehung(c, user["id"], post["author_id"])),
        "art": post["kind"],
        "text": post["body"],
        "link": ({"url": post["link_url"], "titel": post["link_title"] or "",
                  "quelle": post["link_source"] or ""}
                 if post["link_url"] else None),
        "kompetenz": json.loads(post["snapshot"]) if post["snapshot"] else None,
        "erstellt": post["created_at"],
        "reaktionen": zaehler,
        "meine_reaktion": meine,
        "kommentare": scalar(c, "SELECT COUNT(*) FROM net_comments WHERE "
                                "post_id = :p AND removed_at IS NULL",
                             p=post["id"]) or 0,
        "eigen": eigen,
        "darf_entfernen": eigen or (user.get("role") or "user") == "admin",
        "entfernt": bool(post["removed_at"]),
        "entfernt_grund": post["removed_reason"] if eigen else None,
    }


def _kompetenzen(c, uid: str, betrachter: str, alle: bool) -> list[dict]:
    """Kompetenzen eines Mitglieds, belegt durch das Logbuch.

    Nur Zählwerte: wie oft eine Maßnahme dokumentiert wurde und wie oft
    erfolgreich. Kein Datum, kein Einsatzbezug. Andere sehen nur, was das
    Mitglied je Kompetenz freigegeben hat.
    """
    daten = rows(c, "SELECT a.measure_id, MAX(a.measure_name) AS name, "
                    "MAX(a.measure_category) AS kategorie, COUNT(*) AS anzahl, "
                    "SUM(CASE WHEN a.outcome = 'erfolgreich' THEN 1 ELSE 0 END) "
                    "AS erfolgreich "
                    "FROM measure_attempts a JOIN encounters e "
                    "ON e.id = a.encounter_id WHERE e.user_id = :u "
                    "AND a.deleted_at IS NULL AND e.deleted_at IS NULL "
                    "AND a.measure_id IS NOT NULL GROUP BY a.measure_id "
                    "ORDER BY anzahl DESC", u=uid)
    frei = {r_["measure_id"] for r_ in rows(
        c, "SELECT measure_id FROM net_competencies WHERE user_id = :u "
           "AND visible = 1", u=uid)}
    aus = []
    for d in daten:
        sichtbar = d["measure_id"] in frei
        if not alle and not sichtbar:
            continue
        best = rows(c, "SELECT b.id, b.role, b.endorser_id FROM net_endorsements b "
                       "WHERE b.user_id = :u AND b.measure_id = :m",
                    u=uid, m=d["measure_id"])
        meine = next((b["id"] for b in best if b["endorser_id"] == betrachter), None)
        aus.append({
            "measure_id": d["measure_id"], "name": d["name"],
            "kategorie": d["kategorie"], "anzahl": d["anzahl"],
            "erfolgreich": d["erfolgreich"] or 0, "sichtbar": sichtbar,
            "bestaetigungen": len(best),
            "praxisanleitung": sum(1 for b in best if b["role"] == "praxisanleitung"),
            "meine_bestaetigung": meine,
        })
    return aus


# --------------------------------------------------------------------------
# Eigenes Profil
# --------------------------------------------------------------------------

class ProfilIn(BaseModel):
    aktiv: bool | None = None
    headline: str | None = Field(default=None, max_length=120)
    about: str | None = Field(default=None, max_length=1500)


@router.get("/profil")
def eigenes_profil(user=Depends(current_user)):
    with conn() as c:
        _profil_sicherstellen(c, user["id"])
        p = _profil(c, user["id"])
        return {
            "aktiv": _aktiv(p),
            "name": _anzeigename(p),
            "headline": p.get("headline") or "",
            "about": p.get("about") or "",
            "avatar_id": p.get("avatar_id"),
            "banner_id": p.get("banner_id"),
            "qualifikation": p.get("qualification") or "",
            "kompetenzen": _kompetenzen(c, user["id"], user["id"], alle=True),
            "kontakte": len(_kontakt_ids(c, user["id"])),
        }


@router.put("/profil")
def profil_speichern(data: ProfilIn, user=Depends(current_user)):
    with conn() as c:
        _profil_sicherstellen(c, user["id"])
        if data.headline is not None:
            _pruefe_text(c, user["id"], data.headline, uhrzeit=False)
            q(c, "UPDATE user_profile SET headline = :h WHERE user_id = :u",
              h=data.headline.strip(), u=user["id"])
        if data.about is not None:
            _pruefe_text(c, user["id"], data.about, uhrzeit=False)
            q(c, "UPDATE user_profile SET about = :a WHERE user_id = :u",
              a=data.about.strip(), u=user["id"])
        if data.aktiv is not None:
            q(c, "UPDATE user_profile SET net_active = :a WHERE user_id = :u",
              a=1 if data.aktiv else 0, u=user["id"])
            audit(c, user["id"], "netz", user["id"],
                  "aktiviert" if data.aktiv else "deaktiviert")
    return eigenes_profil(user)


class KompetenzIn(BaseModel):
    sichtbar: bool


@router.put("/kompetenzen/{measure_id}")
def kompetenz_freigeben(measure_id: str, data: KompetenzIn,
                        user=Depends(current_user)):
    with conn() as c:
        if not row(c, "SELECT id FROM measures WHERE id = :m", m=measure_id):
            raise HTTPException(404, "Kompetenz nicht gefunden.")
        if row(c, "SELECT user_id FROM net_competencies WHERE user_id = :u "
                  "AND measure_id = :m", u=user["id"], m=measure_id):
            q(c, "UPDATE net_competencies SET visible = :v WHERE user_id = :u "
                 "AND measure_id = :m", v=1 if data.sichtbar else 0,
              u=user["id"], m=measure_id)
        else:
            q(c, "INSERT INTO net_competencies (user_id, measure_id, visible) "
                 "VALUES (:u, :m, :v)", u=user["id"], m=measure_id,
              v=1 if data.sichtbar else 0)
    return {"ok": True}


# --------------------------------------------------------------------------
# Bilder
# --------------------------------------------------------------------------

@router.post("/medien/{art}")
async def bild_hochladen(art: str, datei: UploadFile = File(...),
                         user=Depends(current_user)):
    if art not in bilder.FORMATE:
        raise HTTPException(404, "Unbekannte Bildart.")
    roh = await datei.read(bilder.MAX_BYTES + 1)
    try:
        daten, breite, hoehe = bilder.verarbeite(roh, art)
    except bilder.BildFehler as fehler:
        raise HTTPException(400, str(fehler)) from fehler
    spalte = "avatar_id" if art == "avatar" else "banner_id"
    with conn() as c:
        _profil_sicherstellen(c, user["id"])
        alt = scalar(c, f"SELECT {spalte} FROM user_profile WHERE user_id = :u",
                     u=user["id"])
        mid = new_id()
        q(c, "INSERT INTO net_media (id, user_id, kind, mime, data, width, height, "
             "created_at) VALUES (:i, :u, :k, 'image/jpeg', :d, :w, :h, :t)",
          i=mid, u=user["id"], k=art, d=daten, w=breite, h=hoehe, t=now_iso())
        q(c, f"UPDATE user_profile SET {spalte} = :m WHERE user_id = :u",
          m=mid, u=user["id"])
        if alt:
            q(c, "DELETE FROM net_media WHERE id = :i AND user_id = :u",
              i=alt, u=user["id"])
    return {"id": mid, "breite": breite, "hoehe": hoehe}


@router.delete("/medien/{art}")
def bild_entfernen(art: str, user=Depends(current_user)):
    if art not in bilder.FORMATE:
        raise HTTPException(404, "Unbekannte Bildart.")
    spalte = "avatar_id" if art == "avatar" else "banner_id"
    with conn() as c:
        alt = scalar(c, f"SELECT {spalte} FROM user_profile WHERE user_id = :u",
                     u=user["id"])
        q(c, f"UPDATE user_profile SET {spalte} = NULL WHERE user_id = :u",
          u=user["id"])
        if alt:
            q(c, "DELETE FROM net_media WHERE id = :i AND user_id = :u",
              i=alt, u=user["id"])
    return {"ok": True}


@router.get("/medien/{media_id}")
def bild_ausliefern(media_id: str, user=Depends(current_user)):
    """Liefert ein Bild nur, wenn der Aufrufer es sehen darf.

    Profilbilder sehen alle aktiven Mitglieder, damit eine Kontaktanfrage
    ein Gesicht hat. Kopfbilder nur Kontakte.
    """
    with conn() as c:
        m = row(c, "SELECT id, user_id, kind, mime, data FROM net_media "
                   "WHERE id = :i", i=media_id)
        if not m:
            raise HTTPException(404, "Bild nicht gefunden.")
        if m["user_id"] != user["id"]:
            besitzer = _profil(c, m["user_id"])
            betrachter = _profil(c, user["id"])
            if not (_aktiv(besitzer) and _aktiv(betrachter)):
                raise HTTPException(404, "Bild nicht gefunden.")
            if m["kind"] != "avatar" and \
                    _beziehung(c, user["id"], m["user_id"]) != "kontakt":
                raise HTTPException(404, "Bild nicht gefunden.")
    return Response(content=bytes(m["data"]), media_type=m["mime"],
                    headers={"Cache-Control": "private, max-age=3600"})


# --------------------------------------------------------------------------
# Personen und Kontakte
# --------------------------------------------------------------------------

@router.get("/personen")
def personen_suchen(q_: str = Query("", alias="q", max_length=80),
                    user=Depends(current_user)):
    with conn() as c:
        _aktiv_erforderlich(c, user)
        muster = f"%{q_.strip().lower()}%"
        treffer = rows(
            c, "SELECT p.*, p.user_id AS uid, u.disabled_at FROM user_profile p "
               "JOIN users u ON u.id = p.user_id WHERE p.net_active = 1 "
               "AND u.disabled_at IS NULL AND p.user_id <> :ich AND ("
               "lower(coalesce(p.first_name, '')) LIKE :m OR "
               "lower(coalesce(p.last_name, '')) LIKE :m OR "
               "lower(coalesce(p.headline, '')) LIKE :m) "
               "ORDER BY p.first_name, p.last_name LIMIT 30",
            ich=user["id"], m=muster)
        return {"personen": [_person_kurz(p, _beziehung(c, user["id"], p["user_id"]))
                             for p in treffer]}


@router.get("/personen/{uid}")
def person(uid: str, user=Depends(current_user)):
    with conn() as c:
        if uid != user["id"]:
            _aktiv_erforderlich(c, user)
        p = _profil(c, uid)
        if not p or (uid != user["id"] and not _aktiv(p)):
            raise HTTPException(404, "Mitglied nicht gefunden.")
        beziehung = _beziehung(c, user["id"], uid)
        aus = _person_kurz(p, beziehung)
        aus["kontakte"] = len(_kontakt_ids(c, uid))
        if beziehung in ("selbst", "kontakt"):
            aus.update({
                "banner_id": p.get("banner_id"),
                "about": p.get("about") or "",
                "qualifikation": p.get("qualification") or "",
                "kompetenzen": _kompetenzen(c, uid, user["id"], alle=False),
                "beitraege": [
                    _beitrag_aus(c, user, b) for b in rows(
                        c, "SELECT * FROM net_posts WHERE author_id = :a "
                           "AND removed_at IS NULL ORDER BY created_at DESC "
                           "LIMIT 20", a=uid)],
            })
        return aus


@router.get("/kontakte")
def kontakte(user=Depends(current_user)):
    with conn() as c:
        aus = {"kontakte": [], "eingehend": [], "ausgehend": []}
        for v in rows(c, "SELECT * FROM net_connections WHERE requester_id = :i "
                         "OR addressee_id = :i ORDER BY created_at DESC",
                      i=user["id"]):
            andere = v["addressee_id"] if v["requester_id"] == user["id"] \
                else v["requester_id"]
            p = _profil(c, andere)
            if not _aktiv(p):
                continue
            beziehung = _beziehung(c, user["id"], andere)
            ziel = {"kontakt": "kontakte", "eingehend": "eingehend",
                    "ausgehend": "ausgehend"}.get(beziehung)
            if ziel:
                aus[ziel].append(_person_kurz(p, beziehung))
        return aus


@router.post("/kontakte/{uid}")
def kontakt_anfragen(uid: str, user=Depends(current_user)):
    with conn() as c:
        _aktiv_erforderlich(c, user)
        if uid == user["id"]:
            raise HTTPException(400, "Du kannst dich nicht mit dir selbst vernetzen.")
        ziel = _profil(c, uid)
        if not _aktiv(ziel):
            raise HTTPException(404, "Mitglied nicht gefunden.")
        v = _verbindung(c, user["id"], uid)
        if v:
            if v["status"] == "pending" and v["addressee_id"] == user["id"]:
                # Gegenanfrage: beide wollen es, also gilt sie als angenommen.
                q(c, "UPDATE net_connections SET status = 'accepted', "
                     "accepted_at = :t WHERE id = :i", t=now_iso(), i=v["id"])
                _melde(c, uid, "kontakt_angenommen", user["id"])
            return {"beziehung": _beziehung(c, user["id"], uid)}
        q(c, "INSERT INTO net_connections (id, requester_id, addressee_id, status, "
             "created_at) VALUES (:i, :r, :a, 'pending', :t)",
          i=new_id(), r=user["id"], a=uid, t=now_iso())
        _melde(c, uid, "kontaktanfrage", user["id"])
        return {"beziehung": "ausgehend"}


@router.post("/kontakte/{uid}/annehmen")
def kontakt_annehmen(uid: str, user=Depends(current_user)):
    with conn() as c:
        _aktiv_erforderlich(c, user)
        v = row(c, "SELECT * FROM net_connections WHERE requester_id = :r "
                   "AND addressee_id = :a AND status = 'pending'",
                r=uid, a=user["id"])
        if not v:
            raise HTTPException(404, "Keine offene Anfrage.")
        q(c, "UPDATE net_connections SET status = 'accepted', accepted_at = :t "
             "WHERE id = :i", t=now_iso(), i=v["id"])
        _melde(c, uid, "kontakt_angenommen", user["id"])
        return {"beziehung": "kontakt"}


@router.delete("/kontakte/{uid}")
def kontakt_loesen(uid: str, user=Depends(current_user)):
    """Ablehnen, Zurückziehen und Entfernen sind derselbe Vorgang.

    Bestätigungen, die der eine dem anderen gegeben hat, fallen mit weg:
    sie setzen eine bestehende Verbindung voraus.
    """
    with conn() as c:
        v = _verbindung(c, user["id"], uid)
        if not v:
            raise HTTPException(404, "Keine Verbindung.")
        q(c, "DELETE FROM net_connections WHERE id = :i", i=v["id"])
        q(c, "DELETE FROM net_endorsements WHERE (user_id = :a AND endorser_id = :b) "
             "OR (user_id = :b AND endorser_id = :a)", a=user["id"], b=uid)
        return {"beziehung": "fremd"}


# --------------------------------------------------------------------------
# Beiträge
# --------------------------------------------------------------------------

class BeitragIn(BaseModel):
    art: str
    text: str = Field(default="", max_length=3000)
    link_url: str | None = None
    link_titel: str | None = Field(default=None, max_length=200)
    link_quelle: str | None = Field(default=None, max_length=120)
    attempt_ids: list[str] = []
    medication_ids: list[str] = []
    mit_zek: bool = False
    mit_naca: bool = False


@router.get("/feed")
def feed(vor: str | None = None, user=Depends(current_user)):
    with conn() as c:
        p = _profil(c, user["id"])
        if not _aktiv(p):
            return {"aktiv": False, "beitraege": [], "weiter": None}
        autoren = {user["id"]} | {
            k for k in _kontakt_ids(c, user["id"]) if _aktiv(_profil(c, k))}
        platzhalter = ", ".join(f":a{i}" for i in range(len(autoren)))
        parameter = {f"a{i}": a for i, a in enumerate(sorted(autoren))}
        bedingung = ""
        if vor:
            bedingung = "AND created_at < :vor "
            parameter["vor"] = vor
        beitraege = rows(
            c, f"SELECT * FROM net_posts WHERE author_id IN ({platzhalter}) "
               f"AND removed_at IS NULL {bedingung}"
               f"ORDER BY created_at DESC LIMIT {FEED_SEITE}", **parameter)
        aus = [_beitrag_aus(c, user, b) for b in beitraege]
        return {"aktiv": True, "beitraege": aus,
                "weiter": aus[-1]["erstellt"] if len(aus) == FEED_SEITE else None}


@router.post("/beitraege")
def beitrag_erstellen(data: BeitragIn, user=Depends(current_user)):
    if (user.get("role") or "user") == "guest":
        raise HTTPException(403, "Mit Lesezugriff lassen sich keine Beiträge teilen.")
    if data.art not in BEITRAGSARTEN:
        raise HTTPException(400, "Unbekannte Beitragsart.")
    text = (data.text or "").strip()
    with conn() as c:
        _aktiv_erforderlich(c, user)
        _pruefe_text(c, user["id"], text)
        link_url = link_titel = link_quelle = None
        schnapp = None
        if data.art == "text":
            if not text:
                raise HTTPException(400, "Der Beitrag ist leer.")
        elif data.art == "wissen":
            link_url = _pruefe_link(data.link_url)
            link_titel = (data.link_titel or "").strip()
            link_quelle = (data.link_quelle or "").strip() or None
            if not link_url or not link_titel:
                raise HTTPException(400, "Ein Wissensbeitrag braucht Titel und Link.")
            _pruefe_text(c, user["id"], link_titel)
            if link_quelle:
                _pruefe_text(c, user["id"], link_quelle)
        else:
            schnapp = _schnappschuss(c, user["id"], data.attempt_ids,
                                     data.medication_ids, data.mit_zek,
                                     data.mit_naca)
        pid = new_id()
        q(c, "INSERT INTO net_posts (id, author_id, kind, body, link_url, link_title, "
             "link_source, snapshot, created_at) VALUES (:i, :a, :k, :b, :lu, :lt, "
             ":ls, :s, :t)",
          i=pid, a=user["id"], k=data.art, b=text, lu=link_url, lt=link_titel,
          ls=link_quelle, s=json.dumps(schnapp, ensure_ascii=False) if schnapp else None,
          t=now_iso())
        post = row(c, "SELECT * FROM net_posts WHERE id = :i", i=pid)
        return _beitrag_aus(c, user, post)


class ModerationIn(BaseModel):
    grund: str = Field(max_length=300)


@router.delete("/beitraege/{post_id}")
def beitrag_loeschen(post_id: str, user=Depends(current_user)):
    """Löscht einen eigenen Beitrag samt Reaktionen und Kommentaren."""
    with conn() as c:
        post = _beitrag_oder_404(c, user, post_id)
        if post["author_id"] != user["id"]:
            raise HTTPException(403, "Nur eigene Beiträge lassen sich löschen.")
        q(c, "DELETE FROM net_reactions WHERE post_id = :p", p=post_id)
        q(c, "DELETE FROM net_comments WHERE post_id = :p", p=post_id)
        q(c, "DELETE FROM net_notifications WHERE post_id = :p", p=post_id)
        q(c, "DELETE FROM net_posts WHERE id = :p", p=post_id)
    return {"ok": True}


@router.post("/beitraege/{post_id}/moderieren")
def beitrag_moderieren(post_id: str, data: ModerationIn, user=Depends(current_user)):
    """Entfernt einen fremden Beitrag. Nur Administrator*innen, mit Grund.

    Eigener Endpunkt statt DELETE mit Body: ein Body an DELETE ist
    unüblich, und Reverse Proxys dürfen ihn verwerfen — dann käme die
    Begründung nie an.
    """
    with conn() as c:
        post = _beitrag_oder_404(c, user, post_id)
        if (user.get("role") or "user") != "admin":
            raise HTTPException(403, "Nur Administrator*innen moderieren.")
        if post["author_id"] == user["id"]:
            raise HTTPException(400, "Eigene Beiträge werden gelöscht, nicht moderiert.")
        grund = data.grund.strip()
        if len(grund) < 5:
            raise HTTPException(400, "Bitte einen Grund angeben.")
        q(c, "UPDATE net_posts SET removed_at = :t, removed_reason = :g "
             "WHERE id = :p", t=now_iso(), g=grund, p=post_id)
        audit(c, user["id"], "net_posts", post_id, "moderiert",
              "removed_reason", None, grund)
        _melde(c, post["author_id"], "entfernt", user["id"], post_id)
    return {"ok": True}


@router.post("/beitraege/{post_id}/melden")
def beitrag_melden(post_id: str, user=Depends(current_user)):
    """Meldet einen Beitrag an alle Administrator*innen.

    Gedacht für den einen Fall, der hier wirklich zählt: jemand teilt
    versehentlich etwas, das auf eine Patientin oder einen Patienten
    schließen lässt. Die Meldung gibt den Administrator*innen Lesezugriff
    auf genau diesen Beitrag.
    """
    with conn() as c:
        post = _beitrag_oder_404(c, user, post_id)
        for a in rows(c, "SELECT id FROM users WHERE role = 'admin' "
                         "AND disabled_at IS NULL"):
            if not _gemeldet_an(c, a["id"], post_id):
                _melde(c, a["id"], "meldung", user["id"], post["id"])
        audit(c, user["id"], "net_posts", post_id, "gemeldet")
    return {"ok": True}


class ReaktionIn(BaseModel):
    art: str


@router.put("/beitraege/{post_id}/reaktion")
def reagieren(post_id: str, data: ReaktionIn, user=Depends(current_user)):
    if data.art not in REAKTIONEN:
        raise HTTPException(400, "Unbekannte Reaktion.")
    with conn() as c:
        post = _beitrag_oder_404(c, user, post_id)
        vorhanden = row(c, "SELECT id FROM net_reactions WHERE post_id = :p "
                           "AND user_id = :u", p=post_id, u=user["id"])
        if vorhanden:
            q(c, "UPDATE net_reactions SET kind = :k WHERE id = :i",
              k=data.art, i=vorhanden["id"])
        else:
            q(c, "INSERT INTO net_reactions (id, post_id, user_id, kind, created_at) "
                 "VALUES (:i, :p, :u, :k, :t)",
              i=new_id(), p=post_id, u=user["id"], k=data.art, t=now_iso())
            _melde(c, post["author_id"], "reaktion", user["id"], post_id)
        return _beitrag_aus(c, user, post)


@router.delete("/beitraege/{post_id}/reaktion")
def reaktion_entfernen(post_id: str, user=Depends(current_user)):
    with conn() as c:
        post = _beitrag_oder_404(c, user, post_id)
        q(c, "DELETE FROM net_reactions WHERE post_id = :p AND user_id = :u",
          p=post_id, u=user["id"])
        return _beitrag_aus(c, user, post)


class KommentarIn(BaseModel):
    text: str = Field(max_length=1000)


@router.get("/beitraege/{post_id}/kommentare")
def kommentare(post_id: str, user=Depends(current_user)):
    with conn() as c:
        post = _beitrag_oder_404(c, user, post_id)
        aus = []
        for k in rows(c, "SELECT * FROM net_comments WHERE post_id = :p AND "
                         "removed_at IS NULL ORDER BY created_at", p=post_id):
            autor = _profil(c, k["author_id"])
            aus.append({
                "id": k["id"], "text": k["body"], "erstellt": k["created_at"],
                "autor": _person_kurz(autor, _beziehung(c, user["id"], k["author_id"])),
                "darf_entfernen": k["author_id"] == user["id"]
                or post["author_id"] == user["id"]
                or (user.get("role") or "user") == "admin",
            })
        return {"kommentare": aus}


@router.post("/beitraege/{post_id}/kommentare")
def kommentieren(post_id: str, data: KommentarIn, user=Depends(current_user)):
    if (user.get("role") or "user") == "guest":
        raise HTTPException(403, "Mit Lesezugriff lassen sich keine Kommentare schreiben.")
    text = data.text.strip()
    if not text:
        raise HTTPException(400, "Der Kommentar ist leer.")
    with conn() as c:
        post = _beitrag_oder_404(c, user, post_id)
        _pruefe_text(c, user["id"], text)
        q(c, "INSERT INTO net_comments (id, post_id, author_id, body, created_at) "
             "VALUES (:i, :p, :a, :b, :t)",
          i=new_id(), p=post_id, a=user["id"], b=text, t=now_iso())
        _melde(c, post["author_id"], "kommentar", user["id"], post_id)
    return kommentare(post_id, user)


@router.delete("/kommentare/{comment_id}")
def kommentar_entfernen(comment_id: str, user=Depends(current_user)):
    with conn() as c:
        k = row(c, "SELECT * FROM net_comments WHERE id = :i AND removed_at IS NULL",
                i=comment_id)
        if not k:
            raise HTTPException(404, "Kommentar nicht gefunden.")
        post = _beitrag_oder_404(c, user, k["post_id"])
        darf = (k["author_id"] == user["id"] or post["author_id"] == user["id"]
                or (user.get("role") or "user") == "admin")
        if not darf:
            raise HTTPException(403, "Diesen Kommentar kannst du nicht entfernen.")
        if k["author_id"] == user["id"]:
            q(c, "DELETE FROM net_comments WHERE id = :i", i=comment_id)
        else:
            q(c, "UPDATE net_comments SET removed_at = :t, removed_reason = :g "
                 "WHERE id = :i", t=now_iso(),
              g="vom Beitragsautor entfernt" if post["author_id"] == user["id"]
              else "moderiert", i=comment_id)
            audit(c, user["id"], "net_comments", comment_id, "entfernt")
    return {"ok": True}


# --------------------------------------------------------------------------
# Bestätigungen
# --------------------------------------------------------------------------

class BestaetigungIn(BaseModel):
    user_id: str
    measure_id: str
    rolle: str = "kollegial"


@router.post("/bestaetigungen")
def bestaetigen(data: BestaetigungIn, user=Depends(current_user)):
    """Bestätigt eine Kompetenz eines Kontakts.

    Nur Kontakte, nur freigegebene Kompetenzen, nur eine Bestätigung je
    Person und Kompetenz. Die Rolle Praxisanleitung ist eine Angabe der
    bestätigenden Person und steht mit deren Namen am Profil.
    """
    if data.rolle not in BESTAETIGUNGSROLLEN:
        raise HTTPException(400, "Unbekannte Rolle.")
    if (user.get("role") or "user") == "guest":
        raise HTTPException(403, "Mit Lesezugriff lässt sich nichts bestätigen.")
    with conn() as c:
        _aktiv_erforderlich(c, user)
        if data.user_id == user["id"]:
            raise HTTPException(400, "Eigene Kompetenzen bestätigt man nicht selbst.")
        if _beziehung(c, user["id"], data.user_id) != "kontakt" or \
                not _aktiv(_profil(c, data.user_id)):
            raise HTTPException(404, "Mitglied nicht gefunden.")
        frei = row(c, "SELECT visible FROM net_competencies WHERE user_id = :u "
                      "AND measure_id = :m", u=data.user_id, m=data.measure_id)
        if not frei or not frei["visible"]:
            raise HTTPException(404, "Kompetenz nicht gefunden.")
        if row(c, "SELECT id FROM net_endorsements WHERE user_id = :u AND "
                  "measure_id = :m AND endorser_id = :e",
               u=data.user_id, m=data.measure_id, e=user["id"]):
            raise HTTPException(409, "Diese Kompetenz hast du bereits bestätigt.")
        bid = new_id()
        q(c, "INSERT INTO net_endorsements (id, user_id, measure_id, endorser_id, "
             "role, created_at) VALUES (:i, :u, :m, :e, :r, :t)",
          i=bid, u=data.user_id, m=data.measure_id, e=user["id"], r=data.rolle,
          t=now_iso())
        _melde(c, data.user_id, "bestaetigung", user["id"])
        return {"id": bid}


@router.delete("/bestaetigungen/{bid}")
def bestaetigung_zurueckziehen(bid: str, user=Depends(current_user)):
    with conn() as c:
        b = row(c, "SELECT * FROM net_endorsements WHERE id = :i", i=bid)
        # Zurückziehen darf, wer bestätigt hat. Wer bestätigt wurde, darf
        # eine Bestätigung ebenfalls ablehnen — das eigene Profil gehört ihm.
        if not b or user["id"] not in (b["endorser_id"], b["user_id"]):
            raise HTTPException(404, "Bestätigung nicht gefunden.")
        q(c, "DELETE FROM net_endorsements WHERE id = :i", i=bid)
    return {"ok": True}


# --------------------------------------------------------------------------
# Mitteilungen
# --------------------------------------------------------------------------

@router.get("/mitteilungen")
def mitteilungen(user=Depends(current_user)):
    with conn() as c:
        aus = []
        for m in rows(c, "SELECT * FROM net_notifications WHERE user_id = :u "
                         "ORDER BY created_at DESC LIMIT 60", u=user["id"]):
            akteur = _profil(c, m["actor_id"]) if m["actor_id"] else None
            aus.append({
                "id": m["id"], "art": m["kind"], "erstellt": m["created_at"],
                "gelesen": bool(m["read_at"]), "post_id": m["post_id"],
                "von": (_person_kurz(akteur, _beziehung(c, user["id"], m["actor_id"]))
                        if akteur else None),
            })
        ungelesen = scalar(c, "SELECT COUNT(*) FROM net_notifications WHERE "
                              "user_id = :u AND read_at IS NULL", u=user["id"]) or 0
        return {"mitteilungen": aus, "ungelesen": ungelesen}


@router.post("/mitteilungen/gelesen")
def mitteilungen_gelesen(user=Depends(current_user)):
    with conn() as c:
        q(c, "UPDATE net_notifications SET read_at = :t WHERE user_id = :u "
             "AND read_at IS NULL", t=now_iso(), u=user["id"])
    return {"ok": True}


@router.get("/beitraege/{post_id}")
def ein_beitrag(post_id: str, user=Depends(current_user)):
    with conn() as c:
        return _beitrag_aus(c, user, _beitrag_oder_404(c, user, post_id))


# --------------------------------------------------------------------------
# DSGVO: Auskunft und Löschung, aufgerufen aus exports.py
# --------------------------------------------------------------------------

def auskunft(c, uid: str) -> dict:
    """Alle Netzwerkdaten eines Kontos für Art. 15 und 20."""
    import base64
    p = _profil(c, uid) or {}
    medien = [{"art": m["kind"], "mime": m["mime"],
               "daten_base64": base64.b64encode(bytes(m["data"])).decode()}
              for m in rows(c, "SELECT kind, mime, data FROM net_media "
                               "WHERE user_id = :u", u=uid)]
    namen = {}

    def name(x):
        if x not in namen:
            namen[x] = _anzeigename(_profil(c, x))
        return namen[x]

    return {
        "profil": {"aktiv": _aktiv(p), "headline": p.get("headline"),
                   "about": p.get("about")},
        "bilder": medien,
        "beitraege": rows(c, "SELECT id, kind, body, link_url, link_title, "
                             "link_source, snapshot, created_at, removed_at, "
                             "removed_reason FROM net_posts WHERE author_id = :u",
                          u=uid),
        "kommentare": rows(c, "SELECT post_id, body, created_at FROM net_comments "
                              "WHERE author_id = :u", u=uid),
        "reaktionen": rows(c, "SELECT post_id, kind, created_at FROM net_reactions "
                              "WHERE user_id = :u", u=uid),
        "kontakte": [
            {"mit": name(v["addressee_id"] if v["requester_id"] == uid
                         else v["requester_id"]),
             "status": v["status"], "seit": v["accepted_at"] or v["created_at"]}
            for v in rows(c, "SELECT * FROM net_connections WHERE "
                             "requester_id = :u OR addressee_id = :u", u=uid)],
        "kompetenzfreigaben": rows(c, "SELECT measure_id, visible FROM "
                                      "net_competencies WHERE user_id = :u", u=uid),
        "bestaetigungen_erhalten": [
            {"von": name(b["endorser_id"]), "measure_id": b["measure_id"],
             "rolle": b["role"], "am": b["created_at"]}
            for b in rows(c, "SELECT * FROM net_endorsements WHERE user_id = :u",
                          u=uid)],
        "bestaetigungen_gegeben": [
            {"fuer": name(b["user_id"]), "measure_id": b["measure_id"],
             "rolle": b["role"], "am": b["created_at"]}
            for b in rows(c, "SELECT * FROM net_endorsements WHERE endorser_id = :u",
                          u=uid)],
    }


def loeschen(c, uid: str) -> None:
    """Entfernt alle Netzwerkdaten eines Kontos für Art. 17."""
    eigene = [p["id"] for p in rows(c, "SELECT id FROM net_posts WHERE "
                                       "author_id = :u", u=uid)]
    for pid in eigene:
        q(c, "DELETE FROM net_reactions WHERE post_id = :p", p=pid)
        q(c, "DELETE FROM net_comments WHERE post_id = :p", p=pid)
        q(c, "DELETE FROM net_notifications WHERE post_id = :p", p=pid)
    q(c, "DELETE FROM net_posts WHERE author_id = :u", u=uid)
    q(c, "DELETE FROM net_comments WHERE author_id = :u", u=uid)
    q(c, "DELETE FROM net_reactions WHERE user_id = :u", u=uid)
    q(c, "DELETE FROM net_connections WHERE requester_id = :u OR addressee_id = :u",
      u=uid)
    q(c, "DELETE FROM net_endorsements WHERE user_id = :u OR endorser_id = :u", u=uid)
    q(c, "DELETE FROM net_competencies WHERE user_id = :u", u=uid)
    q(c, "DELETE FROM net_notifications WHERE user_id = :u OR actor_id = :u", u=uid)
    q(c, "DELETE FROM net_media WHERE user_id = :u", u=uid)
