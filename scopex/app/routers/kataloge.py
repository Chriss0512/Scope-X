"""Kataloge, Qualifikationen und Fortbildungsnachweis.

Mitglieder wählen aus Listen und reichen Fehlendes ein. Die Administration
sichtet Einreichungen, benennt um, führt zusammen und pflegt die
Gültigkeitsdauern der Qualifikationen. Siehe app/kataloge.py.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .. import kataloge as kat
from .. import netzkern as nk
from ..core import audit, current_user, require_admin
from ..db import conn, new_id, now_iso, q, row, rows, scalar

router = APIRouter(tags=["netz"])


# --------------------------------------------------------------------------
# Kreise (öffentlich lesbar: auch die Bewerberseite braucht sie)
# --------------------------------------------------------------------------

@router.get("/api/oeffentlich/kreise")
def kreisliste():
    return {"kreise": [{"ags": k["ags"], "name": kat.kreis_label(k["ags"]),
                        "land": k["land"]} for k in kat.kreise().values()]}


# --------------------------------------------------------------------------
# Organisationen und Wachen
# --------------------------------------------------------------------------

def org_aus(o: dict | None) -> dict | None:
    if not o:
        return None
    return {"id": o["id"], "name": o["name"], "art": o["art"], "status": o["status"]}


def wache_aus(c, w: dict | None) -> dict | None:
    if not w:
        return None
    org = row(c, "SELECT * FROM net_organisations WHERE id = :i", i=w["organisation_id"])
    return {"id": w["id"], "name": w["name"], "status": w["status"],
            "organisation": org["name"] if org else "",
            "kreis": kat.kreis_label(w["kreis_ags"]), "kreis_ags": w["kreis_ags"]}


@router.get("/api/netz/katalog/organisationen")
def organisationen(q_: str = Query("", alias="q", max_length=80),
                   user=Depends(current_user)):
    with conn() as c:
        muster = f"%{kat.normalisiert(q_)}%"
        liste = rows(c, "SELECT * FROM net_organisations WHERE lower(name) LIKE :m "
                        "ORDER BY CASE WHEN status = 'frei' THEN 0 ELSE 1 END, name "
                        "LIMIT 60", m=muster)
        return {"organisationen": [org_aus(o) for o in liste]}


class OrgIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    art: str = "sonstige"


@router.post("/api/netz/katalog/organisationen")
def organisation_einreichen(data: OrgIn, user=Depends(current_user)):
    """Reicht eine fehlende Organisation ein. Gibt es sie schon (gleicher
    Name, Groß- und Kleinschreibung egal), kommt die vorhandene zurück."""
    if nk.ist_gast(user):
        raise HTTPException(403, "Mit Lesezugriff lässt sich nichts einreichen.")
    name = " ".join(data.name.split())
    with conn() as c:
        nk.pruefe_text(c, user["id"], name, uhrzeit=False)
        da = row(c, "SELECT * FROM net_organisations WHERE lower(name) = :n",
                 n=kat.normalisiert(name))
        if da:
            return org_aus(da)
        oid = new_id()
        q(c, "INSERT INTO net_organisations (id, name, art, status, created_by, "
             "created_at) VALUES (:i, :n, :a, 'neu', :u, :t)",
          i=oid, n=name, a=data.art if data.art in kat.ORG_ARTEN else "sonstige",
          u=user["id"], t=now_iso())
        return org_aus(row(c, "SELECT * FROM net_organisations WHERE id = :i", i=oid))


@router.get("/api/netz/katalog/wachen")
def wachen(q_: str = Query("", alias="q", max_length=80), kreis: str = "",
           organisation: str = "", user=Depends(current_user)):
    with conn() as c:
        sql = "SELECT * FROM net_wachen WHERE lower(name) LIKE :m"
        werte = {"m": f"%{kat.normalisiert(q_)}%"}
        if kreis:
            sql += " AND kreis_ags = :k"
            werte["k"] = kreis
        if organisation:
            sql += " AND organisation_id = :o"
            werte["o"] = organisation
        liste = rows(c, sql + " ORDER BY name LIMIT 60", **werte)
        return {"wachen": [wache_aus(c, w) for w in liste]}


class WacheIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    organisation_id: str | None = None
    kreis_ags: str


@router.post("/api/netz/katalog/wachen")
def wache_einreichen(data: WacheIn, user=Depends(current_user)):
    if nk.ist_gast(user):
        raise HTTPException(403, "Mit Lesezugriff lässt sich nichts einreichen.")
    if not kat.kreis_gueltig(data.kreis_ags):
        raise HTTPException(400, "Wähle den Kreis der Wache.")
    name = " ".join(data.name.split())
    with conn() as c:
        nk.pruefe_text(c, user["id"], name, uhrzeit=False)
        if data.organisation_id and not row(
                c, "SELECT id FROM net_organisations WHERE id = :i", i=data.organisation_id):
            raise HTTPException(404, "Organisation nicht gefunden.")
        da = row(c, "SELECT * FROM net_wachen WHERE lower(name) = :n AND kreis_ags = :k",
                 n=kat.normalisiert(name), k=data.kreis_ags)
        if da:
            return wache_aus(c, da)
        wid = new_id()
        q(c, "INSERT INTO net_wachen (id, name, organisation_id, kreis_ags, status, "
             "created_by, created_at) VALUES (:i, :n, :o, :k, 'neu', :u, :t)",
          i=wid, n=name, o=data.organisation_id, k=data.kreis_ags, u=user["id"],
          t=now_iso())
        return wache_aus(c, row(c, "SELECT * FROM net_wachen WHERE id = :i", i=wid))


class OrtIn(BaseModel):
    kreis_ags: str | None = None
    organisation_id: str | None = None
    wache_id: str | None = None


@router.put("/api/netz/profil/ort")
def ort_speichern(data: OrtIn, user=Depends(current_user)):
    """Region, Organisation und Wache des eigenen Profils. Leere Werte
    entfernen die Angabe."""
    with conn() as c:
        nk.profil_sicherstellen(c, user["id"])
        if data.kreis_ags and not kat.kreis_gueltig(data.kreis_ags):
            raise HTTPException(400, "Unbekannter Kreis.")
        if data.organisation_id and not row(
                c, "SELECT id FROM net_organisations WHERE id = :i", i=data.organisation_id):
            raise HTTPException(404, "Organisation nicht gefunden.")
        if data.wache_id and not row(c, "SELECT id FROM net_wachen WHERE id = :i",
                                     i=data.wache_id):
            raise HTTPException(404, "Wache nicht gefunden.")
        q(c, "UPDATE user_profile SET kreis_ags = :k, organisation_id = :o, "
             "wache_id = :w WHERE user_id = :u", k=data.kreis_ags or None,
          o=data.organisation_id or None, w=data.wache_id or None, u=user["id"])
    return {"ok": True}


def ort_aus(c, p: dict) -> dict:
    org = row(c, "SELECT * FROM net_organisations WHERE id = :i",
              i=p.get("organisation_id")) if p.get("organisation_id") else None
    wache = row(c, "SELECT * FROM net_wachen WHERE id = :i",
                i=p.get("wache_id")) if p.get("wache_id") else None
    return {"kreis_ags": p.get("kreis_ags"), "kreis": kat.kreis_label(p.get("kreis_ags")),
            "organisation": org_aus(org), "wache": wache_aus(c, wache)}


# --------------------------------------------------------------------------
# Qualifikationen
# --------------------------------------------------------------------------

def qual_aus(qq: dict) -> dict:
    return {"id": qq["id"], "name": qq["name"], "kurz": qq["kurz"] or qq["name"],
            "kategorie": qq["kategorie"], "herausgeber": qq["herausgeber"] or "",
            "gueltig_monate": qq["gueltig_monate"],
            "fortbildung_stunden": qq["fortbildung_stunden"],
            "quelle": qq["quelle"] or "", "status": qq["status"]}


def status_von(gueltig_bis: str | None) -> str:
    """gueltig | bald (unter 90 Tagen) | abgelaufen | unbefristet."""
    if not gueltig_bis:
        return "unbefristet"
    heute = date.today()
    jahr, monat = int(gueltig_bis[:4]), int(gueltig_bis[5:7])
    # Gültig bis zum Monatsende.
    ende = date(jahr + (monat == 12), monat % 12 + 1, 1)
    if ende <= heute:
        return "abgelaufen"
    if (ende - heute).days <= 90:
        return "bald"
    return "gueltig"


def qualifikationen_von(c, uid: str, fuer_andere: bool) -> list[dict]:
    """Qualifikationen eines Mitglieds. Andere sehen nur gültige und
    unbefristete — eine abgelaufene Rezertifizierung geht niemanden an."""
    aus = []
    for uq in rows(c, "SELECT u.*, k.name, k.kurz, k.kategorie, k.sort_order, "
                      "k.fortbildung_stunden FROM net_user_qualifications u "
                      "JOIN net_qualifications k ON k.id = u.qual_id "
                      "WHERE u.user_id = :u ORDER BY k.sort_order, k.name", u=uid):
        st = status_von(uq["gueltig_bis"])
        if fuer_andere and st == "abgelaufen":
            continue
        aus.append({"id": uq["id"], "qual_id": uq["qual_id"], "name": uq["name"],
                    "kurz": uq["kurz"] or uq["name"], "kategorie": uq["kategorie"],
                    "erworben": uq["erworben"] or "",
                    "gueltig_bis": "" if fuer_andere else (uq["gueltig_bis"] or ""),
                    "status": "gueltig" if fuer_andere and st == "bald" else st})
    return aus


@router.get("/api/netz/katalog/qualifikationen")
def qualifikationskatalog(user=Depends(current_user)):
    with conn() as c:
        liste = rows(c, "SELECT * FROM net_qualifications WHERE status = 'frei' OR "
                        "(status = 'vorgeschlagen' AND created_by = :u) "
                        "ORDER BY sort_order, name", u=user["id"])
        return {"kategorien": list(kat.QUAL_KATEGORIEN),
                "qualifikationen": [qual_aus(x) for x in liste]}


class QualVorschlagIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    kategorie: str = "Weitere Kurse"
    herausgeber: str | None = Field(default=None, max_length=80)


@router.post("/api/netz/katalog/qualifikationen")
def qualifikation_vorschlagen(data: QualVorschlagIn, user=Depends(current_user)):
    if nk.ist_gast(user):
        raise HTTPException(403, "Mit Lesezugriff lässt sich nichts vorschlagen.")
    name = " ".join(data.name.split())
    with conn() as c:
        nk.pruefe_text(c, user["id"], name, uhrzeit=False)
        da = row(c, "SELECT * FROM net_qualifications WHERE lower(name) = :n "
                    "OR lower(kurz) = :n", n=kat.normalisiert(name))
        if da:
            return qual_aus(da)
        qid = new_id()
        q(c, "INSERT INTO net_qualifications (id, name, kurz, kategorie, herausgeber, "
             "status, sort_order, created_by, created_at) VALUES (:i, :n, :n, :k, :h, "
             "'vorgeschlagen', 999, :u, :t)", i=qid, n=name,
          k=data.kategorie if data.kategorie in kat.QUAL_KATEGORIEN else "Weitere Kurse",
          h=(data.herausgeber or "").strip() or None, u=user["id"], t=now_iso())
        for a in rows(c, "SELECT id FROM users WHERE role = 'admin' AND disabled_at IS NULL"):
            nk.melde(c, a["id"], "katalog", user["id"])
        return qual_aus(row(c, "SELECT * FROM net_qualifications WHERE id = :i", i=qid))


class MeineQualIn(BaseModel):
    qual_id: str
    erworben: str | None = Field(default=None, max_length=7)
    gueltig_bis: str | None = Field(default=None, max_length=7)


def _monat(wert: str | None) -> str | None:
    if not wert:
        return None
    if len(wert) != 7 or wert[4] != "-" or not (wert[:4] + wert[5:]).isdigit():
        raise HTTPException(400, "Datum als JJJJ-MM.")
    return wert


@router.get("/api/netz/qualifikationen")
def meine_qualifikationen(user=Depends(current_user)):
    with conn() as c:
        return {"qualifikationen": qualifikationen_von(c, user["id"], fuer_andere=False)}


@router.post("/api/netz/qualifikationen")
def qualifikation_eintragen(data: MeineQualIn, user=Depends(current_user)):
    """Trägt eine Qualifikation aus dem Katalog ein. Ohne eigenes
    Ablaufdatum wird es aus der hinterlegten Gültigkeit berechnet."""
    erworben, bis = _monat(data.erworben), _monat(data.gueltig_bis)
    with conn() as c:
        k = row(c, "SELECT * FROM net_qualifications WHERE id = :i AND (status = 'frei' "
                   "OR (status = 'vorgeschlagen' AND created_by = :u))",
                i=data.qual_id, u=user["id"])
        if not k:
            raise HTTPException(404, "Qualifikation nicht gefunden.")
        bis = bis or kat.gueltig_bis(erworben, k["gueltig_monate"])
        vorhanden = row(c, "SELECT id FROM net_user_qualifications WHERE user_id = :u "
                           "AND qual_id = :q", u=user["id"], q=data.qual_id)
        if vorhanden:
            q(c, "UPDATE net_user_qualifications SET erworben = :e, gueltig_bis = :b "
                 "WHERE id = :i", e=erworben, b=bis, i=vorhanden["id"])
        else:
            q(c, "INSERT INTO net_user_qualifications (id, user_id, qual_id, erworben, "
                 "gueltig_bis, created_at) VALUES (:i, :u, :q, :e, :b, :t)",
              i=new_id(), u=user["id"], q=data.qual_id, e=erworben, b=bis, t=now_iso())
        return {"qualifikationen": qualifikationen_von(c, user["id"], fuer_andere=False)}


@router.delete("/api/netz/qualifikationen/{uqid}")
def qualifikation_entfernen(uqid: str, user=Depends(current_user)):
    with conn() as c:
        q(c, "DELETE FROM net_user_qualifications WHERE id = :i AND user_id = :u",
          i=uqid, u=user["id"])
        return {"qualifikationen": qualifikationen_von(c, user["id"], fuer_andere=False)}


def ablauf_erinnern(c, uid: str) -> None:
    """Legt einmalig eine Mitteilung an, wenn eine Qualifikation in den
    nächsten 90 Tagen abläuft. ref_id hält Eintrag und Datum zusammen:
    nach einer Rezertifizierung mit neuem Datum gibt es eine neue."""
    for uq in qualifikationen_von(c, uid, fuer_andere=False):
        if uq["status"] not in ("bald", "abgelaufen"):
            continue
        ref = f"{uq['id']}:{uq['gueltig_bis']}"
        if not row(c, "SELECT id FROM net_notifications WHERE user_id = :u AND "
                      "kind = 'qualifikation' AND ref_id = :r", u=uid, r=ref):
            q(c, "INSERT INTO net_notifications (id, user_id, kind, ref_id, created_at) "
                 "VALUES (:i, :u, 'qualifikation', :r, :t)",
              i=new_id(), u=uid, r=ref, t=now_iso())


# --------------------------------------------------------------------------
# Fortbildungsnachweis (privat)
# --------------------------------------------------------------------------

class FortbildungIn(BaseModel):
    titel: str = Field(min_length=2, max_length=160)
    datum: str = Field(min_length=10, max_length=10)
    stunden: float = Field(gt=0, le=200)
    qual_id: str | None = None


def _fortbildungen(c, uid: str, jahr: int) -> dict:
    liste = rows(c, "SELECT f.*, k.kurz, k.name AS qual_name FROM net_fortbildungen f "
                    "LEFT JOIN net_qualifications k ON k.id = f.qual_id WHERE "
                    "f.user_id = :u AND f.datum >= :a AND f.datum <= :b ORDER BY f.datum DESC",
                 u=uid, a=f"{jahr}-01-01", b=f"{jahr}-12-31")
    summe = round(sum(f["stunden"] for f in liste), 1)
    pflichten = []
    for uq in rows(c, "SELECT k.id, k.kurz, k.name, k.fortbildung_stunden FROM "
                      "net_user_qualifications u JOIN net_qualifications k ON "
                      "k.id = u.qual_id WHERE u.user_id = :u AND "
                      "k.fortbildung_stunden IS NOT NULL", u=uid):
        erbracht = round(sum(f["stunden"] for f in liste if f["qual_id"] == uq["id"]), 1)
        pflichten.append({"qual_id": uq["id"], "name": uq["kurz"] or uq["name"],
                          "soll": uq["fortbildung_stunden"], "ist": erbracht})
    return {"jahr": jahr, "summe": summe, "pflichten": pflichten,
            "fortbildungen": [{"id": f["id"], "titel": f["titel"], "datum": f["datum"],
                               "stunden": f["stunden"], "qual_id": f["qual_id"],
                               "qualifikation": f["kurz"] or f["qual_name"] or ""}
                              for f in liste]}


@router.get("/api/netz/fortbildungen")
def fortbildungen(jahr: int = Query(0, ge=0, le=2100), user=Depends(current_user)):
    with conn() as c:
        return _fortbildungen(c, user["id"], jahr or date.today().year)


@router.post("/api/netz/fortbildungen")
def fortbildung_eintragen(data: FortbildungIn, user=Depends(current_user)):
    try:
        tag = date.fromisoformat(data.datum)
    except ValueError as exc:
        raise HTTPException(400, "Datum als JJJJ-MM-TT.") from exc
    with conn() as c:
        if data.qual_id and not row(c, "SELECT id FROM net_qualifications WHERE id = :i",
                                    i=data.qual_id):
            raise HTTPException(404, "Qualifikation nicht gefunden.")
        q(c, "INSERT INTO net_fortbildungen (id, user_id, titel, datum, stunden, qual_id, "
             "created_at) VALUES (:i, :u, :ti, :d, :s, :q, :t)",
          i=new_id(), u=user["id"], ti=" ".join(data.titel.split()), d=tag.isoformat(),
          s=round(data.stunden, 2), q=data.qual_id, t=now_iso())
        return _fortbildungen(c, user["id"], tag.year)


@router.delete("/api/netz/fortbildungen/{fid}")
def fortbildung_entfernen(fid: str, user=Depends(current_user)):
    with conn() as c:
        f = row(c, "SELECT datum FROM net_fortbildungen WHERE id = :i AND user_id = :u",
                i=fid, u=user["id"])
        q(c, "DELETE FROM net_fortbildungen WHERE id = :i AND user_id = :u",
          i=fid, u=user["id"])
        jahr = int(f["datum"][:4]) if f else date.today().year
        return _fortbildungen(c, user["id"], jahr)


# --------------------------------------------------------------------------
# Administration
# --------------------------------------------------------------------------

@router.get("/api/admin/katalog")
def katalog_admin(admin=Depends(require_admin)):
    with conn() as c:
        def nutzung(spalte: str, i: str) -> int:
            return scalar(c, f"SELECT COUNT(*) FROM user_profile WHERE {spalte} = :i",
                          i=i) or 0
        return {
            "organisationen": [{**org_aus(o), "mitglieder": nutzung("organisation_id", o["id"])}
                               for o in rows(c, "SELECT * FROM net_organisations "
                                                "ORDER BY status DESC, name")],
            "wachen": [{**wache_aus(c, w), "mitglieder": nutzung("wache_id", w["id"])}
                       for w in rows(c, "SELECT * FROM net_wachen ORDER BY status DESC, name")],
            "qualifikationen": [{**qual_aus(k), "mitglieder": scalar(
                c, "SELECT COUNT(*) FROM net_user_qualifications WHERE qual_id = :i",
                i=k["id"]) or 0} for k in rows(c, "SELECT * FROM net_qualifications "
                                                 "ORDER BY sort_order, name")],
        }


class KatalogAenderungIn(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    status: str | None = None
    zusammenfuehren_mit: str | None = None
    gueltig_monate: int | None = Field(default=None, ge=0, le=240)
    fortbildung_stunden: int | None = Field(default=None, ge=0, le=500)
    kategorie: str | None = None


TABELLEN = {
    "organisationen": ("net_organisations", "organisation_id", ("frei", "neu")),
    "wachen": ("net_wachen", "wache_id", ("frei", "neu")),
    "qualifikationen": ("net_qualifications", None, ("frei", "vorgeschlagen", "aus")),
}


@router.put("/api/admin/katalog/{art}/{eid}")
def katalog_aendern(art: str, eid: str, data: KatalogAenderungIn,
                    admin=Depends(require_admin)):
    if art not in TABELLEN:
        raise HTTPException(404, "Unbekannter Katalog.")
    tabelle, profilspalte, stati = TABELLEN[art]
    with conn() as c:
        alt = row(c, f"SELECT * FROM {tabelle} WHERE id = :i", i=eid)
        if not alt:
            raise HTTPException(404, "Eintrag nicht gefunden.")
        if data.zusammenfuehren_mit:
            ziel = row(c, f"SELECT id FROM {tabelle} WHERE id = :i",
                       i=data.zusammenfuehren_mit)
            if not ziel or ziel["id"] == eid:
                raise HTTPException(400, "Ungültiges Ziel.")
            if profilspalte:
                q(c, f"UPDATE user_profile SET {profilspalte} = :z WHERE {profilspalte} = :i",
                  z=ziel["id"], i=eid)
            if art == "organisationen":
                q(c, "UPDATE net_wachen SET organisation_id = :z WHERE organisation_id = :i",
                  z=ziel["id"], i=eid)
            if art == "qualifikationen":
                # Doppelte Einträge derselben Person beim Ziel vermeiden.
                for uq in rows(c, "SELECT id, user_id FROM net_user_qualifications "
                                  "WHERE qual_id = :i", i=eid):
                    if row(c, "SELECT id FROM net_user_qualifications WHERE user_id = :u "
                              "AND qual_id = :z", u=uq["user_id"], z=ziel["id"]):
                        q(c, "DELETE FROM net_user_qualifications WHERE id = :i", i=uq["id"])
                    else:
                        q(c, "UPDATE net_user_qualifications SET qual_id = :z WHERE id = :i",
                          z=ziel["id"], i=uq["id"])
                q(c, "UPDATE net_fortbildungen SET qual_id = :z WHERE qual_id = :i",
                  z=ziel["id"], i=eid)
            q(c, f"DELETE FROM {tabelle} WHERE id = :i", i=eid)
            audit(c, admin["id"], tabelle, eid, "zusammengeführt", "id", eid, ziel["id"])
            return {"ok": True}
        if data.name:
            q(c, f"UPDATE {tabelle} SET name = :n WHERE id = :i",
              n=" ".join(data.name.split()), i=eid)
        if data.status:
            if data.status not in stati:
                raise HTTPException(400, "Unbekannter Status.")
            q(c, f"UPDATE {tabelle} SET status = :s WHERE id = :i", s=data.status, i=eid)
        if art == "qualifikationen":
            if data.gueltig_monate is not None:
                q(c, "UPDATE net_qualifications SET gueltig_monate = :m WHERE id = :i",
                  m=data.gueltig_monate or None, i=eid)
            if data.fortbildung_stunden is not None:
                q(c, "UPDATE net_qualifications SET fortbildung_stunden = :s WHERE id = :i",
                  s=data.fortbildung_stunden or None, i=eid)
            if data.kategorie and data.kategorie in kat.QUAL_KATEGORIEN:
                q(c, "UPDATE net_qualifications SET kategorie = :k WHERE id = :i",
                  k=data.kategorie, i=eid)
        audit(c, admin["id"], tabelle, eid, "geändert")
    return {"ok": True}


@router.delete("/api/admin/katalog/{art}/{eid}")
def katalog_loeschen(art: str, eid: str, admin=Depends(require_admin)):
    if art not in TABELLEN:
        raise HTTPException(404, "Unbekannter Katalog.")
    tabelle, profilspalte, _ = TABELLEN[art]
    with conn() as c:
        if profilspalte:
            q(c, f"UPDATE user_profile SET {profilspalte} = NULL WHERE {profilspalte} = :i",
              i=eid)
        if art == "organisationen":
            q(c, "UPDATE net_wachen SET organisation_id = NULL WHERE organisation_id = :i",
              i=eid)
        if art == "qualifikationen":
            q(c, "DELETE FROM net_user_qualifications WHERE qual_id = :i", i=eid)
            q(c, "UPDATE net_fortbildungen SET qual_id = NULL WHERE qual_id = :i", i=eid)
        q(c, f"DELETE FROM {tabelle} WHERE id = :i", i=eid)
        audit(c, admin["id"], tabelle, eid, "gelöscht")
    return {"ok": True}
