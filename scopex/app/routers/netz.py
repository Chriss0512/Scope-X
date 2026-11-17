"""Kompetenznetz: Profile, Folgen, Blockieren, Info, Kompetenzen, Medien.

Beiträge und Feed stehen in beitraege.py, Direktnachrichten in
nachrichten.py. Alle Sichtbarkeitsregeln kommen aus app/netzkern.py.

Nicht sichtbare Objekte antworten mit 404, nicht mit 403, damit sich ihre
Existenz nicht erfragen lässt.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import medien
from .. import netzkern as nk
from ..core import audit, current_user
from ..db import conn, new_id, now_iso, q, row, rows, scalar

router = APIRouter(prefix="/api/netz", tags=["netz"])
log = logging.getLogger("scopex.netz")

BESTAETIGUNGSROLLEN = ("kollegial", "praxisanleitung")
EINTRAGSARTEN = ("station", "ausbildung", "zertifikat", "sprache")


def _zaehlen(c, uid: str) -> dict:
    return {
        "beitraege": scalar(c, "SELECT COUNT(*) FROM net_posts WHERE author_id = :u "
                               "AND removed_at IS NULL AND published_at <= :t",
                            u=uid, t=now_iso()) or 0,
        "follower": scalar(c, "SELECT COUNT(*) FROM net_follows f JOIN user_profile p "
                              "ON p.user_id = f.follower_id WHERE f.followee_id = :u "
                              "AND f.status = 'aktiv' AND p.net_active = 1", u=uid) or 0,
        "folge_ich": scalar(c, "SELECT COUNT(*) FROM net_follows f JOIN user_profile p "
                               "ON p.user_id = f.followee_id WHERE f.follower_id = :u "
                               "AND f.status = 'aktiv' AND p.net_active = 1", u=uid) or 0,
    }


def eintraege(c, uid: str) -> list[dict]:
    return [{"id": e["id"], "art": e["kind"], "titel": e["title"], "org": e["org"] or "",
             "von": e["start_date"] or "", "bis": e["end_date"] or "",
             "notiz": e["note"] or ""}
            for e in rows(c, "SELECT * FROM net_profile_entries WHERE user_id = :u "
                             "ORDER BY COALESCE(start_date, '') DESC, created_at DESC",
                          u=uid)]


def kompetenzen(c, uid: str, betrachter: str, alle: bool) -> list[dict]:
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
    privat: bool | None = None
    headline: str | None = Field(default=None, max_length=120)
    about: str | None = Field(default=None, max_length=1500)
    location: str | None = Field(default=None, max_length=80)
    organisation: str | None = Field(default=None, max_length=120)


@router.get("/profil")
def eigenes_profil(user=Depends(current_user)):
    with conn() as c:
        nk.profil_sicherstellen(c, user["id"])
        p = nk.profil(c, user["id"])
        return {
            "id": user["id"],
            "aktiv": nk.aktiv(p),
            "privat": nk.privat(p),
            "name": nk.anzeigename(p),
            "headline": p.get("headline") or "",
            "about": p.get("about") or "",
            "location": p.get("location") or "",
            "organisation": p.get("organisation") or "",
            "avatar_id": p.get("avatar_id"),
            "banner_id": p.get("banner_id"),
            "qualifikation": p.get("qualification") or "",
            "kompetenzen": kompetenzen(c, user["id"], user["id"], alle=True),
            "eintraege": eintraege(c, user["id"]),
            "zahlen": _zaehlen(c, user["id"]),
        }


@router.put("/profil")
def profil_speichern(data: ProfilIn, user=Depends(current_user)):
    with conn() as c:
        nk.profil_sicherstellen(c, user["id"])
        for feld in ("headline", "about", "location", "organisation"):
            wert = getattr(data, feld)
            if wert is None:
                continue
            nk.pruefe_text(c, user["id"], wert, uhrzeit=False)
            q(c, f"UPDATE user_profile SET {feld} = :w WHERE user_id = :u",
              w=wert.strip(), u=user["id"])
        if data.aktiv is not None:
            q(c, "UPDATE user_profile SET net_active = :a WHERE user_id = :u",
              a=1 if data.aktiv else 0, u=user["id"])
            audit(c, user["id"], "netz", user["id"],
                  "aktiviert" if data.aktiv else "deaktiviert")
        if data.privat is not None:
            q(c, "UPDATE user_profile SET net_private = :a WHERE user_id = :u",
              a=1 if data.privat else 0, u=user["id"])
            if not data.privat:
                # Wer öffentlich wird, nimmt offene Anfragen an — sonst
                # hingen sie ohne Bedeutung herum.
                for f in rows(c, "SELECT follower_id FROM net_follows WHERE "
                                 "followee_id = :u AND status = 'angefragt'",
                              u=user["id"]):
                    nk.melde(c, f["follower_id"], "folge_angenommen", user["id"])
                q(c, "UPDATE net_follows SET status = 'aktiv', accepted_at = :t "
                     "WHERE followee_id = :u AND status = 'angefragt'",
                  t=now_iso(), u=user["id"])
    return eigenes_profil(user)


class EintragIn(BaseModel):
    art: str
    titel: str = Field(min_length=1, max_length=120)
    org: str | None = Field(default=None, max_length=120)
    von: str | None = Field(default=None, max_length=10)
    bis: str | None = Field(default=None, max_length=10)
    notiz: str | None = Field(default=None, max_length=300)


def _pruefe_eintrag(c, uid: str, data: EintragIn) -> None:
    if data.art not in EINTRAGSARTEN:
        raise HTTPException(400, "Unbekannte Art.")
    for d in (data.von, data.bis):
        if d and not (len(d) in (4, 7, 10) and d[:4].isdigit()):
            raise HTTPException(400, "Datum als JJJJ, JJJJ-MM oder JJJJ-MM-TT.")
    for t in (data.titel, data.org, data.notiz):
        nk.pruefe_text(c, uid, t or "", uhrzeit=False)


@router.post("/eintraege")
def eintrag_anlegen(data: EintragIn, user=Depends(current_user)):
    with conn() as c:
        _pruefe_eintrag(c, user["id"], data)
        if (scalar(c, "SELECT COUNT(*) FROM net_profile_entries WHERE user_id = :u",
                   u=user["id"]) or 0) >= 80:
            raise HTTPException(400, "Höchstens 80 Einträge.")
        q(c, "INSERT INTO net_profile_entries (id, user_id, kind, title, org, "
             "start_date, end_date, note, created_at) VALUES (:i, :u, :k, :t, :o, "
             ":s, :e, :n, :c)", i=new_id(), u=user["id"], k=data.art,
          t=data.titel.strip(), o=(data.org or "").strip() or None,
          s=data.von or None, e=data.bis or None,
          n=(data.notiz or "").strip() or None, c=now_iso())
        return {"eintraege": eintraege(c, user["id"])}


@router.put("/eintraege/{eid}")
def eintrag_aendern(eid: str, data: EintragIn, user=Depends(current_user)):
    with conn() as c:
        if not row(c, "SELECT id FROM net_profile_entries WHERE id = :i AND user_id = :u",
                   i=eid, u=user["id"]):
            raise HTTPException(404, "Eintrag nicht gefunden.")
        _pruefe_eintrag(c, user["id"], data)
        q(c, "UPDATE net_profile_entries SET kind = :k, title = :t, org = :o, "
             "start_date = :s, end_date = :e, note = :n WHERE id = :i",
          k=data.art, t=data.titel.strip(), o=(data.org or "").strip() or None,
          s=data.von or None, e=data.bis or None,
          n=(data.notiz or "").strip() or None, i=eid)
        return {"eintraege": eintraege(c, user["id"])}


@router.delete("/eintraege/{eid}")
def eintrag_loeschen(eid: str, user=Depends(current_user)):
    with conn() as c:
        q(c, "DELETE FROM net_profile_entries WHERE id = :i AND user_id = :u",
          i=eid, u=user["id"])
        return {"eintraege": eintraege(c, user["id"])}


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
# Medien
# --------------------------------------------------------------------------

MEDIENARTEN = ("avatar", "banner", "bild", "video")


def _aufraeumen(c, uid: str) -> None:
    """Nicht angehängte Entwürfe älter als einen Tag entfernen."""
    grenze = nk.jetzt().timestamp() - 86400
    for m in rows(c, "SELECT id, file, poster, created_at FROM net_media WHERE "
                     "user_id = :u AND kind IN ('bild', 'video') AND post_id IS NULL "
                     "AND message_id IS NULL", u=uid):
        try:
            alt = datetime.fromisoformat(m["created_at"]).timestamp() < grenze
        except ValueError:
            alt = True
        if alt:
            medien.entferne(m["file"], m["poster"])
            q(c, "DELETE FROM net_media WHERE id = :i", i=m["id"])


def _video_im_hintergrund(mid: str, roh) -> None:
    try:
        info = medien.video_verarbeiten(mid, roh)
        with conn() as c:
            q(c, "UPDATE net_media SET file = :f, poster = :p, mime = :m, width = :w, "
                 "height = :h, duration = :d, bytes = :b, status = 'bereit' "
                 "WHERE id = :i", f=info["file"], p=info["poster"], m=info["mime"],
              w=info["width"], h=info["height"], d=info["duration"], b=info["bytes"],
              i=mid)
    except medien.MedienFehler as fehler:
        with conn() as c:
            q(c, "UPDATE net_media SET status = :s WHERE id = :i",
              s="fehler:" + str(fehler)[:120], i=mid)
    except Exception:  # noqa: BLE001 - der Hintergrundfaden darf nie sterben
        log.exception("Videoverarbeitung fehlgeschlagen")
        with conn() as c:
            q(c, "UPDATE net_media SET status = 'fehler:Unerwarteter Fehler.' "
                 "WHERE id = :i", i=mid)


def medium_aus(m: dict) -> dict:
    status = m["status"]
    return {"id": m["id"], "art": m["kind"], "mime": m["mime"],
            "breite": m["width"], "hoehe": m["height"], "dauer": m["duration"],
            "status": status if status in ("bereit", "verarbeitung") else "fehler",
            "fehler": status[7:] if status.startswith("fehler:") else None}


@router.post("/medien/{art}")
def medium_hochladen(art: str, datei: UploadFile = File(...),
                     user=Depends(current_user)):
    if art not in MEDIENARTEN:
        raise HTTPException(404, "Unbekannte Medienart.")
    if art in ("bild", "video") and nk.ist_gast(user):
        raise HTTPException(403, "Mit Lesezugriff lassen sich keine Medien teilen.")
    mid = new_id()
    with conn() as c:
        nk.profil_sicherstellen(c, user["id"])
        _aufraeumen(c, user["id"])
        offen = scalar(c, "SELECT COUNT(*) FROM net_media WHERE user_id = :u AND "
                          "post_id IS NULL AND message_id IS NULL AND kind IN "
                          "('bild', 'video')", u=user["id"]) or 0
        if art in ("bild", "video") and offen >= 20:
            raise HTTPException(429, "Zu viele unveröffentlichte Medien. "
                                     "Teile oder verwirf zuerst die vorhandenen.")
    if art == "video":
        try:
            roh = medien.video_annehmen(mid, datei.file)
        except medien.MedienFehler as fehler:
            raise HTTPException(400, str(fehler)) from fehler
        with conn() as c:
            q(c, "INSERT INTO net_media (id, user_id, kind, mime, file, status, "
                 "created_at) VALUES (:i, :u, 'video', 'video/mp4', :f, "
                 "'verarbeitung', :t)", i=mid, u=user["id"], f=f"{mid}.mp4",
              t=now_iso())
        threading.Thread(target=_video_im_hintergrund, args=(mid, roh),
                         daemon=True).start()
        with conn() as c:
            return medium_aus(row(c, "SELECT * FROM net_media WHERE id = :i", i=mid))

    roh = datei.file.read(medien.BILD_MAX_BYTES + 1)
    try:
        info = medien.speichere_bild(mid, roh, art)
    except medien.MedienFehler as fehler:
        raise HTTPException(400, str(fehler)) from fehler
    with conn() as c:
        q(c, "INSERT INTO net_media (id, user_id, kind, mime, file, width, height, "
             "bytes, status, created_at) VALUES (:i, :u, :k, :m, :f, :w, :h, :b, "
             "'bereit', :t)", i=mid, u=user["id"], k=art, m=info["mime"],
          f=info["file"], w=info["width"], h=info["height"], b=info["bytes"],
          t=now_iso())
        if art in ("avatar", "banner"):
            spalte = "avatar_id" if art == "avatar" else "banner_id"
            alt = scalar(c, f"SELECT {spalte} FROM user_profile WHERE user_id = :u",
                         u=user["id"])
            q(c, f"UPDATE user_profile SET {spalte} = :m WHERE user_id = :u",
              m=mid, u=user["id"])
            if alt:
                medium_loeschen(c, alt, user["id"])
        return medium_aus(row(c, "SELECT * FROM net_media WHERE id = :i", i=mid))


def medium_loeschen(c, mid: str, uid: str) -> None:
    m = row(c, "SELECT file, poster FROM net_media WHERE id = :i AND user_id = :u",
            i=mid, u=uid)
    if m:
        medien.entferne(m["file"], m["poster"])
        q(c, "DELETE FROM net_media WHERE id = :i", i=mid)


@router.delete("/medien/profil/{art}")
def profilbild_entfernen(art: str, user=Depends(current_user)):
    if art not in ("avatar", "banner"):
        raise HTTPException(404, "Unbekannte Bildart.")
    spalte = "avatar_id" if art == "avatar" else "banner_id"
    with conn() as c:
        alt = scalar(c, f"SELECT {spalte} FROM user_profile WHERE user_id = :u",
                     u=user["id"])
        q(c, f"UPDATE user_profile SET {spalte} = NULL WHERE user_id = :u",
          u=user["id"])
        if alt:
            medium_loeschen(c, alt, user["id"])
    return {"ok": True}


@router.delete("/medien/entwurf/{mid}")
def entwurf_verwerfen(mid: str, user=Depends(current_user)):
    with conn() as c:
        m = row(c, "SELECT id FROM net_media WHERE id = :i AND user_id = :u AND "
                   "post_id IS NULL AND message_id IS NULL AND kind IN ('bild', 'video')",
                i=mid, u=user["id"])
        if m:
            medium_loeschen(c, mid, user["id"])
    return {"ok": True}


def darf_medium_sehen(c, user: dict, m: dict) -> bool:
    if m["user_id"] == user["id"]:
        return True
    if m["status"] != "bereit":
        return False
    if m["kind"] == "avatar":
        return nk.sichtbar(c, user["id"], m["user_id"])
    if m["kind"] == "banner":
        return nk.voll_sichtbar(c, user["id"], m["user_id"])
    if m["post_id"]:
        post = row(c, "SELECT * FROM net_posts WHERE id = :i", i=m["post_id"])
        return bool(post and nk.darf_beitrag_sehen(c, user, post))
    if m["message_id"]:
        g = row(c, "SELECT k.user_a, k.user_b FROM net_messages n JOIN "
                   "net_conversations k ON k.id = n.conversation_id WHERE n.id = :i",
                i=m["message_id"])
        return bool(g and user["id"] in (g["user_a"], g["user_b"]))
    return False


def _medium_oder_404(c, user: dict, mid: str) -> dict:
    m = row(c, "SELECT * FROM net_media WHERE id = :i", i=mid)
    if not m or not darf_medium_sehen(c, user, m):
        raise HTTPException(404, "Medium nicht gefunden.")
    return m


@router.get("/medien/{mid}/status")
def medium_status(mid: str, user=Depends(current_user)):
    with conn() as c:
        m = row(c, "SELECT * FROM net_media WHERE id = :i AND user_id = :u",
                i=mid, u=user["id"])
        if not m:
            raise HTTPException(404, "Medium nicht gefunden.")
        return medium_aus(m)


def _datei(name: str | None, mime: str) -> FileResponse:
    try:
        pfad = medien.pfad_fuer(name or "")
    except medien.MedienFehler as exc:
        raise HTTPException(404, "Medium nicht gefunden.") from exc
    if not pfad.exists():
        raise HTTPException(404, "Medium nicht gefunden.")
    # FileResponse beantwortet Range-Anfragen; Videos lassen sich damit
    # spulen, ohne die ganze Datei zu laden.
    return FileResponse(pfad, media_type=mime,
                        headers={"Cache-Control": "private, max-age=3600"})


@router.get("/medien/{mid}")
def medium_ausliefern(mid: str, user=Depends(current_user)):
    with conn() as c:
        m = _medium_oder_404(c, user, mid)
    if m["status"] != "bereit":
        raise HTTPException(404, "Medium nicht gefunden.")
    return _datei(m["file"], m["mime"])


@router.get("/medien/{mid}/vorschau")
def medium_vorschau(mid: str, user=Depends(current_user)):
    with conn() as c:
        m = _medium_oder_404(c, user, mid)
    if m["status"] != "bereit":
        raise HTTPException(404, "Medium nicht gefunden.")
    return _datei(m["poster"] if m["kind"] == "video" else m["file"], "image/jpeg")


# --------------------------------------------------------------------------
# Personen
# --------------------------------------------------------------------------

@router.get("/personen")
def personen_suchen(q_: str = Query("", alias="q", max_length=80),
                    user=Depends(current_user)):
    with conn() as c:
        nk.aktiv_erforderlich(c, user)
        muster = f"%{q_.strip().lower()}%"
        gesperrt = nk.blockierte_ids(c, user["id"])
        treffer = rows(
            c, "SELECT p.*, p.user_id AS uid, u.disabled_at FROM user_profile p "
               "JOIN users u ON u.id = p.user_id WHERE p.net_active = 1 "
               "AND u.disabled_at IS NULL AND p.user_id <> :ich AND ("
               "lower(coalesce(p.first_name, '')) LIKE :m OR "
               "lower(coalesce(p.last_name, '')) LIKE :m OR "
               "lower(coalesce(p.headline, '')) LIKE :m OR "
               "lower(coalesce(p.organisation, '')) LIKE :m) "
               "ORDER BY p.first_name, p.last_name LIMIT 40",
            ich=user["id"], m=muster)
        return {"personen": [nk.person_kurz(c, user["id"], p) for p in treffer
                             if p["uid"] not in gesperrt][:30]}


@router.get("/vorschlaege")
def vorschlaege(user=Depends(current_user)):
    """Personen, denen man folgen könnte: wer mir folgt, dann Gefolgte von
    Gefolgten, dann übrige aktive Mitglieder. Höchstens acht."""
    with conn() as c:
        if not nk.aktiv(nk.profil(c, user["id"])):
            return {"personen": []}
        ich = user["id"]
        gefolgt = nk.gefolgt_ids(c, ich)
        meine_follower = nk.follower_ids(c, ich)
        ausgeschlossen = gefolgt | nk.blockierte_ids(c, ich) | {ich} | {
            f["followee_id"] for f in rows(
                c, "SELECT followee_id FROM net_follows WHERE follower_id = :i",
                i=ich)}
        punkte: dict[str, float] = {}
        for g in gefolgt:
            for zweit in nk.gefolgt_ids(c, g):
                if zweit not in ausgeschlossen:
                    punkte[zweit] = punkte.get(zweit, 0) + 1.0
        for f in meine_follower:
            if f not in ausgeschlossen:
                punkte[f] = punkte.get(f, 0) + 2.0
        for r_ in rows(c, "SELECT p.user_id FROM user_profile p JOIN users u "
                          "ON u.id = p.user_id WHERE p.net_active = 1 AND "
                          "u.disabled_at IS NULL"):
            if r_["user_id"] not in ausgeschlossen:
                punkte.setdefault(r_["user_id"], 0.1)
        aus = []
        for uid, wert in sorted(punkte.items(), key=lambda x: -x[1])[:8]:
            pp = nk.profil(c, uid)
            if nk.aktiv(pp):
                person = nk.person_kurz(c, ich, pp)
                person["grund"] = ("Folgt dir" if uid in meine_follower
                                   else "Gemeinsame Kontakte" if wert >= 1
                                   else "Neu im Netz")
                aus.append(person)
        return {"personen": aus}


@router.get("/personen/{uid}")
def person(uid: str, user=Depends(current_user)):
    with conn() as c:
        if uid != user["id"]:
            nk.aktiv_erforderlich(c, user)
        p = nk.profil(c, uid)
        if not p or not nk.sichtbar(c, user["id"], uid) or \
                (uid != user["id"] and not nk.aktiv(p)):
            raise HTTPException(404, "Mitglied nicht gefunden.")
        aus = nk.person_kurz(c, user["id"], p)
        b = nk.beziehung(c, user["id"], uid)
        aus.update({
            "selbst": uid == user["id"],
            "fragt_an": b.get("fragt_an", False),
            "about": p.get("about") or "",
            "zahlen": _zaehlen(c, uid),
            "kontakt": nk.kontakt(c, user["id"], uid),
            "voll": nk.voll_sichtbar(c, user["id"], uid),
        })
        if aus["voll"]:
            aus.update({
                "banner_id": p.get("banner_id"),
                "location": p.get("location") or "",
                "organisation": p.get("organisation") or "",
                "qualifikation": p.get("qualification") or "",
                # Auch das eigene Profil zeigt nur Freigegebenes: so, wie
                # andere es sehen.
                "kompetenzen": kompetenzen(c, uid, user["id"], alle=False),
                "eintraege": eintraege(c, uid),
            })
        return aus


def _liste(c, ich: str, ids: list[str]) -> list[dict]:
    aus = []
    for i in ids:
        p = nk.profil(c, i)
        if nk.aktiv(p) and not nk.blockiert(c, ich, i):
            aus.append(nk.person_kurz(c, ich, p))
    return aus


@router.get("/personen/{uid}/follower")
def follower_liste(uid: str, user=Depends(current_user)):
    with conn() as c:
        if not nk.voll_sichtbar(c, user["id"], uid):
            raise HTTPException(404, "Mitglied nicht gefunden.")
        ids = [r_["follower_id"] for r_ in rows(
            c, "SELECT follower_id FROM net_follows WHERE followee_id = :u AND "
               "status = 'aktiv' ORDER BY accepted_at DESC", u=uid)]
        return {"personen": _liste(c, user["id"], ids)}


@router.get("/personen/{uid}/gefolgt")
def gefolgt_liste(uid: str, user=Depends(current_user)):
    with conn() as c:
        if not nk.voll_sichtbar(c, user["id"], uid):
            raise HTTPException(404, "Mitglied nicht gefunden.")
        ids = [r_["followee_id"] for r_ in rows(
            c, "SELECT followee_id FROM net_follows WHERE follower_id = :u AND "
               "status = 'aktiv' ORDER BY accepted_at DESC", u=uid)]
        return {"personen": _liste(c, user["id"], ids)}


# --------------------------------------------------------------------------
# Folgen
# --------------------------------------------------------------------------

@router.post("/folgen/{uid}")
def folgen(uid: str, user=Depends(current_user)):
    with conn() as c:
        nk.aktiv_erforderlich(c, user)
        if uid == user["id"]:
            raise HTTPException(400, "Dir selbst kannst du nicht folgen.")
        p = nk.profil(c, uid)
        if not p or not nk.aktiv(p) or not nk.sichtbar(c, user["id"], uid):
            raise HTTPException(404, "Mitglied nicht gefunden.")
        if not nk.follow(c, user["id"], uid):
            status = "angefragt" if nk.privat(p) else "aktiv"
            q(c, "INSERT INTO net_follows (id, follower_id, followee_id, status, "
                 "created_at, accepted_at) VALUES (:i, :a, :b, :s, :t, :x)",
              i=new_id(), a=user["id"], b=uid, s=status, t=now_iso(),
              x=now_iso() if status == "aktiv" else None)
            nk.melde(c, uid, "folgeanfrage" if status == "angefragt" else "folgt",
                     user["id"])
        return nk.person_kurz(c, user["id"], p)


@router.delete("/folgen/{uid}")
def entfolgen(uid: str, user=Depends(current_user)):
    """Entfolgen oder Anfrage zurückziehen."""
    with conn() as c:
        q(c, "DELETE FROM net_follows WHERE follower_id = :a AND followee_id = :b",
          a=user["id"], b=uid)
        # Bestätigungen setzen gegenseitiges Folgen voraus.
        _bestaetigungen_aufheben(c, user["id"], uid)
        p = nk.profil(c, uid)
        if not p or not nk.sichtbar(c, user["id"], uid):
            return {"ok": True}
        return nk.person_kurz(c, user["id"], p)


@router.post("/follower/{uid}/annehmen")
def anfrage_annehmen(uid: str, user=Depends(current_user)):
    with conn() as c:
        f = nk.follow(c, uid, user["id"])
        if not f or f["status"] != "angefragt":
            raise HTTPException(404, "Anfrage nicht gefunden.")
        q(c, "UPDATE net_follows SET status = 'aktiv', accepted_at = :t WHERE id = :i",
          t=now_iso(), i=f["id"])
        nk.melde(c, uid, "folge_angenommen", user["id"])
        return nk.person_kurz(c, user["id"], nk.profil(c, uid))


@router.delete("/follower/{uid}")
def follower_entfernen(uid: str, user=Depends(current_user)):
    """Anfrage ablehnen oder einen Follower entfernen."""
    with conn() as c:
        q(c, "DELETE FROM net_follows WHERE follower_id = :a AND followee_id = :b",
          a=uid, b=user["id"])
        _bestaetigungen_aufheben(c, user["id"], uid)
        return {"ok": True}


@router.get("/anfragen")
def anfragen(user=Depends(current_user)):
    with conn() as c:
        ids = [r_["follower_id"] for r_ in rows(
            c, "SELECT follower_id FROM net_follows WHERE followee_id = :u AND "
               "status = 'angefragt' ORDER BY created_at DESC", u=user["id"])]
        return {"personen": _liste(c, user["id"], ids)}


def _bestaetigungen_aufheben(c, a: str, b: str) -> None:
    q(c, "DELETE FROM net_endorsements WHERE (user_id = :a AND endorser_id = :b) "
         "OR (user_id = :b AND endorser_id = :a)", a=a, b=b)


# --------------------------------------------------------------------------
# Blockieren
# --------------------------------------------------------------------------

@router.post("/blockieren/{uid}")
def blockieren(uid: str, user=Depends(current_user)):
    """Trennt zwei Konten vollständig: kein Folgen, keine Sicht, keine
    Nachrichten, keine Bestätigungen."""
    if uid == user["id"]:
        raise HTTPException(400, "Dich selbst kannst du nicht blockieren.")
    with conn() as c:
        if not nk.profil(c, uid):
            raise HTTPException(404, "Mitglied nicht gefunden.")
        if not row(c, "SELECT id FROM net_blocks WHERE blocker_id = :a AND "
                      "blocked_id = :b", a=user["id"], b=uid):
            q(c, "INSERT INTO net_blocks (id, blocker_id, blocked_id, created_at) "
                 "VALUES (:i, :a, :b, :t)", i=new_id(), a=user["id"], b=uid,
              t=now_iso())
        q(c, "DELETE FROM net_follows WHERE (follower_id = :a AND followee_id = :b) "
             "OR (follower_id = :b AND followee_id = :a)", a=user["id"], b=uid)
        _bestaetigungen_aufheben(c, user["id"], uid)
        q(c, "DELETE FROM net_notifications WHERE user_id = :a AND actor_id = :b",
          a=user["id"], b=uid)
        audit(c, user["id"], "net_blocks", uid, "blockiert")
    return {"ok": True}


@router.delete("/blockieren/{uid}")
def entblocken(uid: str, user=Depends(current_user)):
    with conn() as c:
        q(c, "DELETE FROM net_blocks WHERE blocker_id = :a AND blocked_id = :b",
          a=user["id"], b=uid)
    return {"ok": True}


@router.get("/blockiert")
def blockiert_liste(user=Depends(current_user)):
    with conn() as c:
        aus = []
        for b in rows(c, "SELECT blocked_id FROM net_blocks WHERE blocker_id = :u",
                      u=user["id"]):
            p = nk.profil(c, b["blocked_id"])
            if p:
                aus.append({"id": p["uid"], "name": nk.anzeigename(p)})
        return {"personen": aus}


# --------------------------------------------------------------------------
# Bestätigungen
# --------------------------------------------------------------------------

class BestaetigungIn(BaseModel):
    user_id: str
    measure_id: str
    rolle: str = "kollegial"


@router.post("/bestaetigungen")
def bestaetigen(data: BestaetigungIn, user=Depends(current_user)):
    """Bestätigt eine Kompetenz. Nur bei gegenseitigem Folgen, nur
    freigegebene Kompetenzen, nur eine Bestätigung je Person und Kompetenz."""
    if data.rolle not in BESTAETIGUNGSROLLEN:
        raise HTTPException(400, "Unbekannte Rolle.")
    if nk.ist_gast(user):
        raise HTTPException(403, "Mit Lesezugriff lässt sich nichts bestätigen.")
    with conn() as c:
        nk.aktiv_erforderlich(c, user)
        if data.user_id == user["id"]:
            raise HTTPException(400, "Eigene Kompetenzen bestätigt man nicht selbst.")
        if not nk.sichtbar(c, user["id"], data.user_id):
            raise HTTPException(404, "Mitglied nicht gefunden.")
        if not nk.kontakt(c, user["id"], data.user_id):
            raise HTTPException(403, "Bestätigen können nur Personen, die sich "
                                     "gegenseitig folgen.")
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
        nk.melde(c, data.user_id, "bestaetigung", user["id"])
        return {"id": bid}


@router.delete("/bestaetigungen/{bid}")
def bestaetigung_zurueckziehen(bid: str, user=Depends(current_user)):
    with conn() as c:
        b = row(c, "SELECT * FROM net_endorsements WHERE id = :i", i=bid)
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
                         "ORDER BY created_at DESC LIMIT 80", u=user["id"]):
            akteur = nk.profil(c, m["actor_id"]) if m["actor_id"] else None
            if akteur and nk.blockiert(c, user["id"], m["actor_id"]):
                continue
            aus.append({
                "id": m["id"], "art": m["kind"], "erstellt": m["created_at"],
                "gelesen": bool(m["read_at"]), "post_id": m["post_id"],
                "von": nk.person_kurz(c, user["id"], akteur) if akteur else None,
            })
        return {"mitteilungen": aus,
                "ungelesen": sum(1 for x in aus if not x["gelesen"])}


@router.post("/mitteilungen/gelesen")
def mitteilungen_gelesen(user=Depends(current_user)):
    with conn() as c:
        q(c, "UPDATE net_notifications SET read_at = :t WHERE user_id = :u "
             "AND read_at IS NULL", t=now_iso(), u=user["id"])
    return {"ok": True}


@router.get("/zaehler")
def zaehler(user=Depends(current_user)):
    """Ungelesene Mitteilungen und Nachrichten für die Leiste."""
    with conn() as c:
        m = scalar(c, "SELECT COUNT(*) FROM net_notifications WHERE user_id = :u "
                      "AND read_at IS NULL", u=user["id"]) or 0
        n = scalar(c, "SELECT COUNT(DISTINCT n.conversation_id) FROM net_messages n "
                      "JOIN net_conversations k ON k.id = n.conversation_id "
                      "WHERE (k.user_a = :u OR k.user_b = :u) AND n.sender_id <> :u "
                      "AND n.read_at IS NULL AND (k.request_for IS NULL OR "
                      "k.request_for <> :u)", u=user["id"]) or 0
        a = scalar(c, "SELECT COUNT(*) FROM net_follows WHERE followee_id = :u "
                      "AND status = 'angefragt'", u=user["id"]) or 0
        return {"mitteilungen": m, "nachrichten": n, "anfragen": a}


# --------------------------------------------------------------------------
# DSGVO: Auskunft und Löschung, aufgerufen aus exports.py
# --------------------------------------------------------------------------

def auskunft(c, uid: str) -> dict:
    """Alle Netzwerkdaten eines Kontos für Art. 15 und 20."""
    import base64
    p = nk.profil(c, uid) or {}
    namen: dict[str, str] = {}

    def name(x):
        if x not in namen:
            namen[x] = nk.anzeigename(nk.profil(c, x))
        return namen[x]

    def datei(m):
        try:
            return base64.b64encode(medien.pfad_fuer(m["file"]).read_bytes()).decode()
        except (medien.MedienFehler, OSError):
            return None

    gespraeche = rows(c, "SELECT * FROM net_conversations WHERE user_a = :u "
                         "OR user_b = :u", u=uid)
    return {
        "profil": {"aktiv": nk.aktiv(p), "privat": nk.privat(p),
                   "headline": p.get("headline"), "about": p.get("about"),
                   "location": p.get("location"),
                   "organisation": p.get("organisation")},
        "eintraege": rows(c, "SELECT kind, title, org, start_date, end_date, note "
                             "FROM net_profile_entries WHERE user_id = :u", u=uid),
        "medien": [{"art": m["kind"], "mime": m["mime"], "beitrag": m["post_id"],
                    "daten_base64": datei(m)}
                   for m in rows(c, "SELECT * FROM net_media WHERE user_id = :u "
                                    "AND status = 'bereit'", u=uid)],
        "beitraege": rows(c, "SELECT id, kind, title, body, details, link_url, "
                             "link_title, link_source, snapshot, repost_of, "
                             "created_at, published_at, removed_at, removed_reason "
                             "FROM net_posts WHERE author_id = :u", u=uid),
        "kommentare": rows(c, "SELECT post_id, body, created_at FROM net_comments "
                              "WHERE author_id = :u", u=uid),
        "gefaellt_mir": rows(c, "SELECT post_id, created_at FROM net_likes "
                                "WHERE user_id = :u", u=uid),
        "folge_ich": [{"wem": name(f["followee_id"]), "status": f["status"],
                       "seit": f["created_at"]}
                      for f in rows(c, "SELECT * FROM net_follows WHERE "
                                       "follower_id = :u", u=uid)],
        "follower": [{"wer": name(f["follower_id"]), "status": f["status"],
                      "seit": f["created_at"]}
                     for f in rows(c, "SELECT * FROM net_follows WHERE "
                                      "followee_id = :u", u=uid)],
        "blockiert": [name(b["blocked_id"]) for b in rows(
            c, "SELECT blocked_id FROM net_blocks WHERE blocker_id = :u", u=uid)],
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
        "nachrichten": [
            {"mit": name(g["user_b"] if g["user_a"] == uid else g["user_a"]),
             "verlauf": [{"von": "ich" if n["sender_id"] == uid else "gegenüber",
                          "text": n["body"], "beitrag": n["post_id"],
                          "am": n["created_at"]}
                         for n in rows(c, "SELECT * FROM net_messages WHERE "
                                          "conversation_id = :k ORDER BY created_at",
                                       k=g["id"])]}
            for g in gespraeche],
    }


def loeschen(c, uid: str) -> None:
    """Entfernt alle Netzwerkdaten eines Kontos für Art. 17.

    Gespräche verschwinden mit dem Konto auch beim Gegenüber: ein Gespräch
    mit einem gelöschten Konto ließe sich sonst weiter lesen, ohne dass
    die Person noch Auskunft oder Löschung verlangen könnte.
    """
    for pid in [p["id"] for p in rows(c, "SELECT id FROM net_posts WHERE "
                                         "author_id = :u", u=uid)]:
        for tabelle in ("net_likes", "net_comments", "net_tags", "net_hidden",
                        "net_notifications"):
            q(c, f"DELETE FROM {tabelle} WHERE post_id = :p", p=pid)
    q(c, "DELETE FROM net_posts WHERE author_id = :u", u=uid)
    q(c, "DELETE FROM net_comments WHERE author_id = :u", u=uid)
    q(c, "DELETE FROM net_likes WHERE user_id = :u", u=uid)
    q(c, "DELETE FROM net_hidden WHERE user_id = :u", u=uid)
    q(c, "DELETE FROM net_follows WHERE follower_id = :u OR followee_id = :u", u=uid)
    q(c, "DELETE FROM net_blocks WHERE blocker_id = :u OR blocked_id = :u", u=uid)
    q(c, "DELETE FROM net_endorsements WHERE user_id = :u OR endorser_id = :u", u=uid)
    q(c, "DELETE FROM net_competencies WHERE user_id = :u", u=uid)
    q(c, "DELETE FROM net_profile_entries WHERE user_id = :u", u=uid)
    q(c, "DELETE FROM net_notifications WHERE user_id = :u OR actor_id = :u", u=uid)
    for g in rows(c, "SELECT id FROM net_conversations WHERE user_a = :u "
                     "OR user_b = :u", u=uid):
        for n in rows(c, "SELECT id FROM net_messages WHERE conversation_id = :k",
                      k=g["id"]):
            for m in rows(c, "SELECT file, poster FROM net_media WHERE "
                             "message_id = :n", n=n["id"]):
                medien.entferne(m["file"], m["poster"])
            q(c, "DELETE FROM net_media WHERE message_id = :n", n=n["id"])
        q(c, "DELETE FROM net_messages WHERE conversation_id = :k", k=g["id"])
        q(c, "DELETE FROM net_conversations WHERE id = :k", k=g["id"])
    for m in rows(c, "SELECT file, poster FROM net_media WHERE user_id = :u", u=uid):
        medien.entferne(m["file"], m["poster"])
    q(c, "DELETE FROM net_media WHERE user_id = :u", u=uid)
