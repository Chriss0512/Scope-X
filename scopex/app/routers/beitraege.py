"""Kompetenznetz: Beiträge, Feed, Entdecken, Gefällt mir, Kommentare, Repost.

Beitragsarten:

* beitrag     Text, bis zu zehn Bilder oder Videos
* wissen      Studie, Leitlinie, Fachartikel: Link mit Titel und Quellenart
* fall        Seltene Situation, Komplikation oder Lernfall mit Lernpunkten,
              optional mit Einträgen aus dem Logbuch. Erscheint auf Wunsch
              verzögert, Voreinstellung im Client: sieben Tage.
* algorithmus SOP oder Ablaufschema mit Pflichtquelle. SCOPE X selbst
              empfiehlt nichts; der Beitrag ist Inhalt eines Mitglieds.
* kompetenz   Einträge aus genau einem eigenen Einsatz (Allowlist-Kopie)
* repost      Teilt einen fremden Beitrag weiter, optional mit Kommentar

Sichtbarkeit, Datenschutzgrenze und Mitteilungen kommen aus netzkern.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .. import algorithmus
from .. import netzkern as nk
from ..core import audit, current_user
from ..db import conn, new_id, now_iso, q, row, rows, scalar

router = APIRouter(prefix="/api/netz", tags=["netz"])

BEITRAGSARTEN = ("beitrag", "wissen", "fall", "algorithmus", "kompetenz", "repost")
FALLKATEGORIEN = ("selten", "komplikation", "lernfall")
SEITE = 20
HASHTAG = re.compile(r"#([0-9A-Za-zÄÖÜäöüß_-]{2,40})")


def _tags(*texte: str | None) -> set[str]:
    aus = set()
    for t in texte:
        for m in HASHTAG.finditer(t or ""):
            aus.add(m.group(1).lower().strip("-_"))
    return {t for t in aus if len(t) >= 2}


def _medien(c, post_id: str) -> list[dict]:
    return [{"id": m["id"], "art": m["kind"], "breite": m["width"],
             "hoehe": m["height"], "dauer": m["duration"]}
            for m in rows(c, "SELECT id, kind, width, height, duration FROM net_media "
                             "WHERE post_id = :p AND status = 'bereit' "
                             "ORDER BY position", p=post_id)]


def beitrag_aus(c, user: dict, post: dict, gruende: list[str] | None = None,
                tiefe: int = 0) -> dict:
    ich = user["id"]
    autor = nk.profil(c, post["author_id"])
    eigen = post["author_id"] == ich
    aus = {
        "id": post["id"],
        "autor": nk.person_kurz(c, ich, autor),
        "art": post["kind"],
        "titel": post["title"] or "",
        "text": post["body"],
        "details": nk.json_oder_none(post["details"]),
        "link": ({"url": post["link_url"], "titel": post["link_title"] or "",
                  "quelle": post["link_source"] or ""}
                 if post["link_url"] else None),
        "kompetenz": nk.json_oder_none(post["snapshot"]),
        "medien": _medien(c, post["id"]),
        "erstellt": post["published_at"],
        "geplant": eigen and post["published_at"] > now_iso(),
        "likes": scalar(c, "SELECT COUNT(*) FROM net_likes WHERE post_id = :p",
                        p=post["id"]) or 0,
        "ich_like": bool(row(c, "SELECT id FROM net_likes WHERE post_id = :p AND "
                                "user_id = :u", p=post["id"], u=ich)),
        "kommentare": scalar(c, "SELECT COUNT(*) FROM net_comments WHERE "
                                "post_id = :p AND removed_at IS NULL",
                             p=post["id"]) or 0,
        "reposts": scalar(c, "SELECT COUNT(*) FROM net_posts WHERE repost_of = :p "
                             "AND removed_at IS NULL", p=post["id"]) or 0,
        "ich_repost": bool(row(c, "SELECT id FROM net_posts WHERE repost_of = :p AND "
                                  "author_id = :u AND removed_at IS NULL",
                               p=post["id"], u=ich)),
        "teilbar": not nk.privat(autor) and post["kind"] != "repost",
        "eigen": eigen,
        "darf_moderieren": not eigen and nk.ist_admin(user),
        "entfernt": bool(post["removed_at"]),
        "entfernt_grund": post["removed_reason"] if eigen else None,
        "warum": gruende or [],
        "original": None,
    }
    if post["kind"] == "repost" and tiefe == 0:
        orig = row(c, "SELECT * FROM net_posts WHERE id = :i", i=post["repost_of"])
        if orig and nk.darf_beitrag_sehen(c, user, orig) and not orig["removed_at"]:
            aus["original"] = beitrag_aus(c, user, orig, tiefe=1)
        else:
            aus["original"] = {"nicht_verfuegbar": True}
    return aus


# --------------------------------------------------------------------------
# Feed
# --------------------------------------------------------------------------

@router.get("/feed")
def feed(modus: str = "fuerdich", seite: int = Query(0, ge=0, le=50),
         user=Depends(current_user)):
    with conn() as c:
        if not nk.aktiv(nk.profil(c, user["id"])):
            return {"aktiv": False, "beitraege": [], "weiter": None}
        ich = user["id"]
        if modus == "folgeich":
            autoren = nk.gefolgt_ids(c, ich) | {ich}
            kandidaten = algorithmus.sichtbare_kandidaten(c, ich, fenster_tage=3650,
                                                          nur_autoren=autoren)
            auswahl = [(p, 0.0, []) for p in kandidaten]
        else:
            auswahl = algorithmus.rangliste(
                c, ich, algorithmus.sichtbare_kandidaten(c, ich))
        stueck = auswahl[seite * SEITE:(seite + 1) * SEITE]
        return {
            "aktiv": True,
            "beitraege": [beitrag_aus(c, user, p, g) for p, _, g in stueck],
            "weiter": seite + 1 if len(auswahl) > (seite + 1) * SEITE else None,
        }


@router.get("/entdecken")
def entdecken(seite: int = Query(0, ge=0, le=50), user=Depends(current_user)):
    """Raster wie bei Bildnetzwerken: Beiträge aus dem ganzen Netz, mit
    Schwerpunkt auf Fällen, Algorithmen und Medien. Eigene nicht."""
    with conn() as c:
        nk.aktiv_erforderlich(c, user)
        kandidaten = [p for p in algorithmus.sichtbare_kandidaten(c, user["id"], 60)
                      if p["author_id"] != user["id"] and p["kind"] != "repost"]
        auswahl = algorithmus.rangliste(c, user["id"], kandidaten, entdecken=True)
        stueck = auswahl[seite * 30:(seite + 1) * 30]
        return {"beitraege": [beitrag_aus(c, user, p, g) for p, _, g in stueck],
                "weiter": seite + 1 if len(auswahl) > (seite + 1) * 30 else None}


@router.get("/suche")
def suche(q_: str = Query("", alias="q", max_length=80), user=Depends(current_user)):
    with conn() as c:
        nk.aktiv_erforderlich(c, user)
        begriff = q_.strip().lstrip("#").lower()
        if len(begriff) < 2:
            return {"tags": []}
        tags = rows(c, "SELECT tag, COUNT(*) AS n FROM net_tags WHERE tag LIKE :m "
                       "GROUP BY tag ORDER BY n DESC LIMIT 12", m=f"%{begriff}%")
        return {"tags": [{"tag": t["tag"], "anzahl": t["n"]} for t in tags]}


@router.get("/tags/{tag}")
def tag_beitraege(tag: str, seite: int = Query(0, ge=0, le=50),
                  user=Depends(current_user)):
    with conn() as c:
        nk.aktiv_erforderlich(c, user)
        ids = {r_["post_id"] for r_ in rows(
            c, "SELECT post_id FROM net_tags WHERE tag = :t", t=tag.lower()[:40])}
        kandidaten = [p for p in algorithmus.sichtbare_kandidaten(c, user["id"], 3650)
                      if p["id"] in ids]
        stueck = kandidaten[seite * SEITE:(seite + 1) * SEITE]
        return {"tag": tag.lower(), "anzahl": len(kandidaten),
                "beitraege": [beitrag_aus(c, user, p) for p in stueck],
                "weiter": seite + 1 if len(kandidaten) > (seite + 1) * SEITE else None}


@router.get("/personen/{uid}/beitraege")
def person_beitraege(uid: str, seite: int = Query(0, ge=0, le=100),
                     user=Depends(current_user)):
    """Chronik einer Person: eigene Beiträge und Reposts, neueste zuerst.
    Für die Person selbst einschließlich geplanter Beiträge."""
    with conn() as c:
        if not nk.voll_sichtbar(c, user["id"], uid):
            raise HTTPException(404, "Mitglied nicht gefunden.")
        if uid == user["id"]:
            liste = rows(c, "SELECT * FROM net_posts WHERE author_id = :a AND "
                            "removed_at IS NULL ORDER BY published_at DESC "
                            "LIMIT 31 OFFSET :o", a=uid, o=seite * 30)
        else:
            liste = rows(c, "SELECT * FROM net_posts WHERE author_id = :a AND "
                            "removed_at IS NULL AND published_at <= :t ORDER BY "
                            "published_at DESC LIMIT 31 OFFSET :o",
                         a=uid, t=now_iso(), o=seite * 30)
        return {"beitraege": [beitrag_aus(c, user, p) for p in liste[:30]],
                "weiter": seite + 1 if len(liste) > 30 else None}


# --------------------------------------------------------------------------
# Erstellen, Ansehen, Löschen
# --------------------------------------------------------------------------

class BeitragIn(BaseModel):
    art: str
    text: str = Field(default="", max_length=3000)
    titel: str | None = Field(default=None, max_length=160)
    details: dict[str, str] | None = None
    link_url: str | None = None
    link_titel: str | None = Field(default=None, max_length=200)
    link_quelle: str | None = Field(default=None, max_length=120)
    attempt_ids: list[str] = []
    medication_ids: list[str] = []
    mit_zek: bool = False
    mit_naca: bool = False
    medien_ids: list[str] = Field(default_factory=list, max_length=10)
    medien_bestaetigt: bool = False
    repost_of: str | None = None
    verzoegerung_tage: int = Field(default=0, ge=0, le=30)


DETAILFELDER = {
    "fall": {"kategorie": 20, "besonderheit": 1500, "gut": 1500, "anders": 1500},
    "algorithmus": {"quelle": 200, "stand": 60, "geltung": 160},
}


def _details(c, uid: str, art: str, roh: dict[str, str] | None) -> dict | None:
    erlaubt = DETAILFELDER.get(art)
    if not erlaubt:
        return None
    aus = {}
    for feld, laenge in erlaubt.items():
        wert = ((roh or {}).get(feld) or "").strip()
        if len(wert) > laenge:
            raise HTTPException(400, f"Das Feld „{feld}“ ist zu lang.")
        nk.pruefe_text(c, uid, wert)
        if wert:
            aus[feld] = wert
    if art == "fall":
        if aus.get("kategorie") not in FALLKATEGORIEN:
            raise HTTPException(400, "Wähle, ob es eine seltene Situation, eine "
                                     "Komplikation oder ein Lernfall war.")
        if not aus.get("besonderheit"):
            raise HTTPException(400, "Beschreibe, was an dem Fall besonders war.")
    if art == "algorithmus" and not aus.get("quelle"):
        raise HTTPException(400, "Ein Algorithmus braucht eine Quelle, etwa die "
                                 "herausgebende Stelle und Fassung.")
    return aus


@router.post("/beitraege")
def beitrag_erstellen(data: BeitragIn, user=Depends(current_user)):
    if nk.ist_gast(user):
        raise HTTPException(403, "Mit Lesezugriff lassen sich keine Beiträge teilen.")
    if data.art not in BEITRAGSARTEN:
        raise HTTPException(400, "Unbekannte Beitragsart.")
    ich = user["id"]
    text = (data.text or "").strip()
    titel = (data.titel or "").strip() or None
    with conn() as c:
        nk.aktiv_erforderlich(c, user)
        nk.pruefe_text(c, ich, text)
        nk.pruefe_text(c, ich, titel or "")
        details = _details(c, ich, data.art, data.details)
        link_url = link_titel = link_quelle = schnapp = repost_of = None

        if data.art == "repost":
            if data.medien_ids:
                raise HTTPException(400, "Ein Repost trägt keine eigenen Medien.")
            orig = row(c, "SELECT * FROM net_posts WHERE id = :i", i=data.repost_of or "")
            if orig and orig["kind"] == "repost":
                orig = row(c, "SELECT * FROM net_posts WHERE id = :i",
                           i=orig["repost_of"])
            if not orig or orig["removed_at"] or not nk.darf_beitrag_sehen(c, user, orig) \
                    or orig["published_at"] > now_iso():
                raise HTTPException(404, "Beitrag nicht gefunden.")
            if nk.privat(nk.profil(c, orig["author_id"])):
                raise HTTPException(403, "Beiträge privater Konten lassen sich "
                                         "nicht weiterteilen.")
            if row(c, "SELECT id FROM net_posts WHERE repost_of = :o AND author_id = :a "
                      "AND removed_at IS NULL", o=orig["id"], a=ich):
                raise HTTPException(409, "Diesen Beitrag hast du bereits geteilt.")
            repost_of = orig["id"]
        elif data.art == "beitrag":
            if not text and not data.medien_ids:
                raise HTTPException(400, "Der Beitrag ist leer.")
        elif data.art == "wissen":
            link_url = nk.pruefe_link(data.link_url)
            link_titel = (data.link_titel or "").strip()
            link_quelle = (data.link_quelle or "").strip() or None
            if not link_url or not link_titel:
                raise HTTPException(400, "Ein Wissensbeitrag braucht Titel und Link.")
            nk.pruefe_text(c, ich, link_titel)
            nk.pruefe_text(c, ich, link_quelle or "")
        elif data.art in ("fall", "algorithmus"):
            if not titel:
                raise HTTPException(400, "Gib dem Beitrag einen Titel.")
            if data.art == "algorithmus" and data.link_url:
                link_url = nk.pruefe_link(data.link_url)
                link_titel = titel
            if data.art == "fall" and (data.attempt_ids or data.medication_ids):
                schnapp = nk.schnappschuss(c, ich, data.attempt_ids, data.medication_ids,
                                           data.mit_zek, data.mit_naca)
        elif data.art == "kompetenz":
            schnapp = nk.schnappschuss(c, ich, data.attempt_ids, data.medication_ids,
                                       data.mit_zek, data.mit_naca)

        medien_zeilen = []
        for mid in data.medien_ids:
            m = row(c, "SELECT * FROM net_media WHERE id = :i AND user_id = :u AND "
                       "post_id IS NULL AND message_id IS NULL AND kind IN "
                       "('bild', 'video')", i=mid, u=ich)
            if not m:
                raise HTTPException(404, "Medium nicht gefunden.")
            if m["status"] != "bereit":
                raise HTTPException(409, "Ein Video wird noch verarbeitet.")
            medien_zeilen.append(m)
        if medien_zeilen and not data.medien_bestaetigt:
            raise HTTPException(
                400, "Bestätige vor dem Teilen, dass auf Bildern und Videos keine "
                     "Patient*innen, Kennzeichen, Einsatzorte oder Monitorwerte mit "
                     "Personenbezug zu erkennen sind.")

        jetzt = datetime.now(timezone.utc).replace(microsecond=0)
        veroeffentlicht = (jetzt + timedelta(days=data.verzoegerung_tage)).isoformat()
        pid = new_id()
        q(c, "INSERT INTO net_posts (id, author_id, kind, title, body, details, "
             "link_url, link_title, link_source, snapshot, repost_of, created_at, "
             "published_at) VALUES (:i, :a, :k, :ti, :b, :d, :lu, :lt, :ls, :s, :r, "
             ":c, :p)",
          i=pid, a=ich, k=data.art, ti=titel, b=text,
          d=json.dumps(details, ensure_ascii=False) if details else None,
          lu=link_url, lt=link_titel, ls=link_quelle,
          s=json.dumps(schnapp, ensure_ascii=False) if schnapp else None,
          r=repost_of, c=jetzt.isoformat(), p=veroeffentlicht)
        for pos, m in enumerate(medien_zeilen):
            q(c, "UPDATE net_media SET post_id = :p, position = :n WHERE id = :i",
              p=pid, n=pos, i=m["id"])
        for tag in _tags(text, titel, *(details or {}).values()):
            q(c, "INSERT INTO net_tags (post_id, tag) VALUES (:p, :t)", p=pid, t=tag)
        if repost_of:
            nk.melde(c, scalar(c, "SELECT author_id FROM net_posts WHERE id = :i",
                               i=repost_of), "repost", ich, repost_of)
        return beitrag_aus(c, user, row(c, "SELECT * FROM net_posts WHERE id = :i", i=pid))


@router.get("/beitraege/{post_id}")
def ein_beitrag(post_id: str, user=Depends(current_user)):
    with conn() as c:
        return beitrag_aus(c, user, nk.beitrag_oder_404(c, user, post_id))


@router.delete("/beitraege/{post_id}")
def beitrag_loeschen(post_id: str, user=Depends(current_user)):
    with conn() as c:
        post = row(c, "SELECT * FROM net_posts WHERE id = :i AND author_id = :a",
                   i=post_id, a=user["id"])
        if not post:
            raise HTTPException(404, "Beitrag nicht gefunden.")
        from .netz import medium_loeschen
        for m in rows(c, "SELECT id FROM net_media WHERE post_id = :p", p=post_id):
            medium_loeschen(c, m["id"], user["id"])
        for tabelle in ("net_likes", "net_comments", "net_tags", "net_hidden",
                        "net_notifications"):
            q(c, f"DELETE FROM {tabelle} WHERE post_id = :p", p=post_id)
        q(c, "DELETE FROM net_posts WHERE id = :i", i=post_id)
    return {"ok": True}


class ModerationIn(BaseModel):
    grund: str = Field(max_length=300)


@router.post("/beitraege/{post_id}/moderieren")
def beitrag_moderieren(post_id: str, data: ModerationIn, user=Depends(current_user)):
    """Entfernt einen fremden Beitrag. Nur Administrator*innen, mit Grund.

    Eigener Endpunkt statt DELETE mit Body: Reverse Proxys dürfen einen
    Body an DELETE verwerfen — dann käme die Begründung nie an.
    """
    with conn() as c:
        post = nk.beitrag_oder_404(c, user, post_id)
        if not nk.ist_admin(user):
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
        nk.melde(c, post["author_id"], "entfernt", user["id"], post_id)
    return {"ok": True}


@router.post("/beitraege/{post_id}/melden")
def beitrag_melden(post_id: str, user=Depends(current_user)):
    """Meldet einen Beitrag an alle Administrator*innen. Die Meldung gibt
    ihnen Lesezugriff auf genau diesen Beitrag."""
    with conn() as c:
        post = nk.beitrag_oder_404(c, user, post_id)
        for a in rows(c, "SELECT id FROM users WHERE role = 'admin' "
                         "AND disabled_at IS NULL"):
            if not nk.gemeldet_an(c, a["id"], post_id):
                q(c, "INSERT INTO net_notifications (id, user_id, kind, actor_id, "
                     "post_id, created_at) VALUES (:i, :u, 'meldung', :a, :p, :t)",
                  i=new_id(), u=a["id"], a=user["id"], p=post["id"], t=now_iso())
        audit(c, user["id"], "net_posts", post_id, "gemeldet")
    return {"ok": True}


@router.post("/beitraege/{post_id}/ausblenden")
def beitrag_ausblenden(post_id: str, user=Depends(current_user)):
    """„Nicht interessiert“: nur für mich ausblenden."""
    with conn() as c:
        nk.beitrag_oder_404(c, user, post_id)
        if not row(c, "SELECT post_id FROM net_hidden WHERE user_id = :u AND "
                      "post_id = :p", u=user["id"], p=post_id):
            q(c, "INSERT INTO net_hidden (user_id, post_id, created_at) VALUES "
                 "(:u, :p, :t)", u=user["id"], p=post_id, t=now_iso())
    return {"ok": True}


# --------------------------------------------------------------------------
# Gefällt mir, Kommentare
# --------------------------------------------------------------------------

@router.put("/beitraege/{post_id}/like")
def gefaellt_mir(post_id: str, user=Depends(current_user)):
    with conn() as c:
        post = nk.beitrag_oder_404(c, user, post_id)
        if not row(c, "SELECT id FROM net_likes WHERE post_id = :p AND user_id = :u",
                   p=post_id, u=user["id"]):
            q(c, "INSERT INTO net_likes (id, post_id, user_id, created_at) VALUES "
                 "(:i, :p, :u, :t)", i=new_id(), p=post_id, u=user["id"], t=now_iso())
            nk.melde(c, post["author_id"], "like", user["id"], post_id)
        return {"likes": scalar(c, "SELECT COUNT(*) FROM net_likes WHERE post_id = :p",
                                p=post_id), "ich_like": True}


@router.delete("/beitraege/{post_id}/like")
def gefaellt_nicht_mehr(post_id: str, user=Depends(current_user)):
    with conn() as c:
        nk.beitrag_oder_404(c, user, post_id)
        q(c, "DELETE FROM net_likes WHERE post_id = :p AND user_id = :u",
          p=post_id, u=user["id"])
        return {"likes": scalar(c, "SELECT COUNT(*) FROM net_likes WHERE post_id = :p",
                                p=post_id), "ich_like": False}


@router.get("/beitraege/{post_id}/likes")
def wer_mag(post_id: str, user=Depends(current_user)):
    with conn() as c:
        nk.beitrag_oder_404(c, user, post_id)
        aus = []
        for r_ in rows(c, "SELECT user_id FROM net_likes WHERE post_id = :p "
                          "ORDER BY created_at DESC LIMIT 200", p=post_id):
            p = nk.profil(c, r_["user_id"])
            if nk.aktiv(p) and nk.sichtbar(c, user["id"], r_["user_id"]):
                aus.append(nk.person_kurz(c, user["id"], p))
        return {"personen": aus}


class KommentarIn(BaseModel):
    text: str = Field(max_length=1000)


@router.get("/beitraege/{post_id}/kommentare")
def kommentare(post_id: str, user=Depends(current_user)):
    with conn() as c:
        post = nk.beitrag_oder_404(c, user, post_id)
        gesperrt = nk.blockierte_ids(c, user["id"])
        aus = []
        for k in rows(c, "SELECT * FROM net_comments WHERE post_id = :p AND "
                         "removed_at IS NULL ORDER BY created_at", p=post_id):
            if k["author_id"] in gesperrt:
                continue
            autor = nk.profil(c, k["author_id"])
            aus.append({
                "id": k["id"], "text": k["body"], "erstellt": k["created_at"],
                "autor": nk.person_kurz(c, user["id"], autor),
                "darf_entfernen": k["author_id"] == user["id"]
                or post["author_id"] == user["id"] or nk.ist_admin(user),
            })
        return {"kommentare": aus}


@router.post("/beitraege/{post_id}/kommentare")
def kommentieren(post_id: str, data: KommentarIn, user=Depends(current_user)):
    if nk.ist_gast(user):
        raise HTTPException(403, "Mit Lesezugriff lassen sich keine Kommentare schreiben.")
    text = data.text.strip()
    if not text:
        raise HTTPException(400, "Der Kommentar ist leer.")
    with conn() as c:
        nk.aktiv_erforderlich(c, user)
        post = nk.beitrag_oder_404(c, user, post_id)
        nk.pruefe_text(c, user["id"], text)
        q(c, "INSERT INTO net_comments (id, post_id, author_id, body, created_at) "
             "VALUES (:i, :p, :a, :b, :t)",
          i=new_id(), p=post_id, a=user["id"], b=text, t=now_iso())
        nk.melde(c, post["author_id"], "kommentar", user["id"], post_id)
    return kommentare(post_id, user)


@router.delete("/kommentare/{comment_id}")
def kommentar_entfernen(comment_id: str, user=Depends(current_user)):
    with conn() as c:
        k = row(c, "SELECT * FROM net_comments WHERE id = :i AND removed_at IS NULL",
                i=comment_id)
        if not k:
            raise HTTPException(404, "Kommentar nicht gefunden.")
        post = nk.beitrag_oder_404(c, user, k["post_id"])
        darf = (k["author_id"] == user["id"] or post["author_id"] == user["id"]
                or nk.ist_admin(user))
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
