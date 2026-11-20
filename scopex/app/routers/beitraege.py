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
* fallvorstellung
              Strukturierte, anonymisierte Fallvorstellung mit Frage an die
              Community: Meldebild → Befund nach xABCDE → Maßnahmen → Frage.
              Kommentare sind Antworten; die fragende Person kann eine als
              hilfreich markieren. Nur Altersgruppe, kein Alter, kein Datum.

Kommentare lassen sich je Beitrag ausschalten: von der Autorin oder dem
Autor, oder von der Administration. Hat die Administration sie
geschlossen, kann nur sie sie wieder öffnen.

Kuratierte Themen (#Atemwegsmanagement, #EKG-Quiz …) sind gewöhnliche
Schlagwörter in net_tags; der Katalog net_topics gibt ihnen Namen und
Kategorie und macht sie im Feed filterbar.

Sichtbarkeit, Datenschutzgrenze und Mitteilungen kommen aus netzkern.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .. import algorithmus, schutz
from .. import netzkern as nk
from ..core import audit, current_user
from ..db import conn, new_id, now_iso, q, row, rows, scalar

router = APIRouter(prefix="/api/netz", tags=["netz"])

BEITRAGSARTEN = ("beitrag", "wissen", "fall", "algorithmus", "kompetenz", "repost",
                 "fallvorstellung")
ALTERSGRUPPEN = ("neugeboren", "saeugling", "kleinkind", "schulkind", "jugendlich",
                 "erwachsen", "hochbetagt")
XABCDE = ("x", "a", "b", "c", "d", "e")
MAX_THEMEN = 5
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


def themen_von(c, post_id: str) -> list[dict]:
    return [{"code": t["code"], "name": t["name"]} for t in rows(
        c, "SELECT k.code, k.name FROM net_tags t JOIN net_topics k ON k.code = t.tag "
           "WHERE t.post_id = :p AND k.status = 'frei' ORDER BY k.sort_order", p=post_id)]


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
        "themen": themen_von(c, post["id"]),
        "kommentare_aus": bool(post["comments_off"]),
        # Von der Administration geschlossen: die Autorin kann es nicht
        # wieder öffnen.
        "kommentare_gesperrt": post["comments_off_by"] == "admin",
        "darf_kommentare_schalten": eigen or nk.ist_admin(user),
        "gemerkt": bool(row(c, "SELECT post_id FROM net_saved WHERE user_id = :u "
                               "AND post_id = :p", u=ich, p=post["id"])),
        "hilfreich": post["answer_comment_id"],
        "erwaehnt": nk.erwaehnte(c, ich, post["id"]),
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

def _mit_tag(c, kandidaten: list[dict], tags: set[str]) -> list[dict]:
    if not tags or not kandidaten:
        return []
    werte = {f"t{i}": t for i, t in enumerate(sorted(tags))}
    ids = {r_["post_id"] for r_ in rows(
        c, "SELECT post_id FROM net_tags WHERE tag IN ("
           + ", ".join(f":{k}" for k in werte) + ")", **werte)}
    return [p for p in kandidaten if p["id"] in ids]


@router.get("/feed")
def feed(modus: str = "fuerdich", seite: int = Query(0, ge=0, le=50),
         thema: str = Query("", max_length=40), user=Depends(current_user)):
    """Modi: fuerdich (Algorithmus), folgeich (chronologisch, Personen),
    themen (Algorithmus, nur gefolgte Themen). thema filtert jeden Modus
    auf ein Schlagwort – das Kompetenz-Routing des Feeds."""
    with conn() as c:
        if not nk.aktiv(nk.profil(c, user["id"])):
            return {"aktiv": False, "beitraege": [], "weiter": None}
        ich = user["id"]
        tag = thema.strip().lstrip("#").lower()
        if modus == "folgeich":
            autoren = nk.gefolgt_ids(c, ich) | {ich}
            kandidaten = algorithmus.sichtbare_kandidaten(c, ich, fenster_tage=3650,
                                                          nur_autoren=autoren)
            if tag:
                kandidaten = _mit_tag(c, kandidaten, {tag})
            auswahl = [(p, 0.0, []) for p in kandidaten]
        else:
            kandidaten = algorithmus.sichtbare_kandidaten(
                c, ich, fenster_tage=365 if (tag or modus == "themen")
                else algorithmus.FENSTER_TAGE)
            if tag:
                kandidaten = _mit_tag(c, kandidaten, {tag})
            elif modus == "themen":
                kandidaten = _mit_tag(c, kandidaten, algorithmus.gefolgte_themen(c, ich))
            auswahl = algorithmus.rangliste(c, ich, kandidaten)
        stueck = auswahl[seite * SEITE:(seite + 1) * SEITE]
        if modus != "folgeich":
            algorithmus.gesehen(c, ich, [p["id"] for p, _, _ in stueck
                                         if p["author_id"] != ich])
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
        thema = row(c, "SELECT code, name, kategorie FROM net_topics WHERE code = :t "
                       "AND status = 'frei'", t=tag.lower()[:40])
        return {"tag": tag.lower(), "anzahl": len(kandidaten),
                "thema": ({**thema, "folge_ich": bool(row(
                    c, "SELECT tag FROM net_topic_follows WHERE user_id = :u AND "
                       "tag = :t", u=user["id"], t=thema["code"]))} if thema else None),
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
    themen: list[str] = Field(default_factory=list, max_length=MAX_THEMEN)
    kommentare_aus: bool = False
    erwaehnungen: list[str] = Field(default_factory=list, max_length=20)


DETAILFELDER = {
    "fall": {"kategorie": 20, "besonderheit": 1500, "gut": 1500, "anders": 1500},
    "algorithmus": {"quelle": 200, "stand": 60, "geltung": 160},
    "fallvorstellung": {"meldebild": 800, "x": 500, "a": 500, "b": 500, "c": 500,
                        "d": 500, "e": 500, "massnahmen": 1500, "frage": 800,
                        "altersgruppe": 20},
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
    if art == "fallvorstellung":
        if aus.get("altersgruppe") and aus["altersgruppe"] not in ALTERSGRUPPEN:
            raise HTTPException(400, "Unbekannte Altersgruppe.")
        if not aus.get("meldebild"):
            raise HTTPException(400, "Beschreibe das Meldebild.")
        if not any(aus.get(k) for k in XABCDE):
            raise HTTPException(400, "Halte mindestens einen Befund nach xABCDE fest.")
        if not aus.get("frage"):
            raise HTTPException(400, "Eine Fallvorstellung endet mit einer Frage an "
                                     "die Community.")
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
        erwaehnt = nk.erwaehnungen_pruefen(c, ich, text, data.erwaehnungen, ich)

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
        elif data.art in ("fall", "algorithmus", "fallvorstellung"):
            if not titel:
                raise HTTPException(400, "Gib dem Beitrag einen Titel.")
            if data.art == "algorithmus" and data.link_url:
                link_url = nk.pruefe_link(data.link_url)
                link_titel = titel
            if data.art in ("fall", "fallvorstellung") and (
                    data.attempt_ids or data.medication_ids):
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

        themen = set()
        for code in data.themen:
            t = row(c, "SELECT code FROM net_topics WHERE code = :c AND status = 'frei'",
                    c=(code or "").strip().lower()[:40])
            if not t:
                raise HTTPException(400, "Unbekanntes Thema.")
            themen.add(t["code"])
        if data.art == "fallvorstellung":
            themen.add("fallvorstellung")

        jetzt = datetime.now(timezone.utc).replace(microsecond=0)
        veroeffentlicht = (jetzt + timedelta(days=data.verzoegerung_tage)).isoformat()
        pid = new_id()
        q(c, "INSERT INTO net_posts (id, author_id, kind, title, body, details, "
             "link_url, link_title, link_source, snapshot, repost_of, created_at, "
             "published_at, comments_off, comments_off_by) VALUES (:i, :a, :k, :ti, "
             ":b, :d, :lu, :lt, :ls, :s, :r, :c, :p, :co, :cb)",
          i=pid, a=ich, k=data.art, ti=schutz.v(titel), b=schutz.v(text),
          d=schutz.v(json.dumps(details, ensure_ascii=False)) if details else None,
          lu=link_url, lt=schutz.v(link_titel), ls=link_quelle,
          s=schutz.v(json.dumps(schnapp, ensure_ascii=False)) if schnapp else None,
          r=repost_of, c=jetzt.isoformat(), p=veroeffentlicht,
          co=1 if data.kommentare_aus else 0,
          cb="autor" if data.kommentare_aus else None)
        for pos, m in enumerate(medien_zeilen):
            q(c, "UPDATE net_media SET post_id = :p, position = :n WHERE id = :i",
              p=pid, n=pos, i=m["id"])
        for tag in _tags(text, titel, *(details or {}).values()) | themen:
            q(c, "INSERT INTO net_tags (post_id, tag) VALUES (:p, :t)", p=pid, t=tag)
        if repost_of:
            nk.melde(c, scalar(c, "SELECT author_id FROM net_posts WHERE id = :i",
                               i=repost_of), "repost", ich, repost_of)
        # Bei geplanten Beiträgen erscheint die Mitteilung erst mit der
        # Veröffentlichung.
        nk.erwaehnungen_speichern(c, ich, pid, None, erwaehnt, ab=veroeffentlicht)
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
                        "net_notifications", "net_saved", "net_seen", "net_mentions"):
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
             "WHERE id = :p", t=now_iso(), g=schutz.v(grund), p=post_id)
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
    erwaehnungen: list[str] = Field(default_factory=list, max_length=20)


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
                "hilfreich": k["id"] == post["answer_comment_id"],
                "erwaehnt": nk.erwaehnte(c, user["id"], post_id, k["id"]),
            })
        # Die hilfreiche Antwort steht oben, wie bei Frage-Antwort-Foren.
        aus.sort(key=lambda k: not k["hilfreich"])
        return {"kommentare": aus, "aus": bool(post["comments_off"]),
                "darf_markieren": post["kind"] == "fallvorstellung"
                and post["author_id"] == user["id"]}


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
        if post["comments_off"]:
            raise HTTPException(403, "Die Kommentare zu diesem Beitrag sind "
                                     "ausgeschaltet.")
        nk.pruefe_text(c, user["id"], text)
        erwaehnt = nk.erwaehnungen_pruefen(c, user["id"], text, data.erwaehnungen,
                                           post["author_id"])
        kid = new_id()
        q(c, "INSERT INTO net_comments (id, post_id, author_id, body, created_at) "
             "VALUES (:i, :p, :a, :b, :t)",
          i=kid, p=post_id, a=user["id"], b=schutz.v(text), t=now_iso())
        nk.melde(c, post["author_id"], "kommentar", user["id"], post_id)
        # Die Autorin des Beitrags erfährt vom Kommentar schon über
        # "kommentar"; eine zweite Mitteilung wäre doppelt.
        nk.erwaehnungen_speichern(c, user["id"], post_id, kid, erwaehnt,
                                  still={post["author_id"]})
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
        if post["answer_comment_id"] == comment_id:
            q(c, "UPDATE net_posts SET answer_comment_id = NULL WHERE id = :p",
              p=post["id"])
        q(c, "DELETE FROM net_mentions WHERE comment_id = :i", i=comment_id)
        if k["author_id"] == user["id"]:
            q(c, "DELETE FROM net_comments WHERE id = :i", i=comment_id)
        else:
            q(c, "UPDATE net_comments SET removed_at = :t, removed_reason = :g "
                 "WHERE id = :i", t=now_iso(),
              g=schutz.v("vom Beitragsautor entfernt" if post["author_id"] == user["id"]
                         else "moderiert"), i=comment_id)
            audit(c, user["id"], "net_comments", comment_id, "entfernt")
    return {"ok": True}


class SchalterIn(BaseModel):
    aus: bool


@router.put("/beitraege/{post_id}/kommentare-aus")
def kommentare_schalten(post_id: str, data: SchalterIn, user=Depends(current_user)):
    """Kommentare aus- oder einschalten. Autor*in oder Administration.

    Schließt die Administration, steht in comments_off_by „admin“; dann
    kann nur sie wieder öffnen. Bestehende Kommentare bleiben sichtbar.
    """
    with conn() as c:
        post = nk.beitrag_oder_404(c, user, post_id)
        eigen = post["author_id"] == user["id"]
        admin = nk.ist_admin(user)
        if not (eigen or admin):
            raise HTTPException(403, "Nur die Autorin, der Autor oder die "
                                     "Administration schalten Kommentare.")
        if not data.aus and post["comments_off_by"] == "admin" and not admin:
            raise HTTPException(403, "Die Administration hat die Kommentare "
                                     "geschlossen.")
        von = None
        if data.aus:
            von = "autor" if eigen and post["comments_off_by"] != "admin" else "admin"
        q(c, "UPDATE net_posts SET comments_off = :a, comments_off_by = :v "
             "WHERE id = :p", a=1 if data.aus else 0, v=von, p=post_id)
        if not eigen:
            audit(c, user["id"], "net_posts", post_id,
                  "kommentare_geschlossen" if data.aus else "kommentare_geoeffnet")
        return beitrag_aus(c, user, row(c, "SELECT * FROM net_posts WHERE id = :i",
                                        i=post_id))


# --------------------------------------------------------------------------
# Merken (Favoriten)
# --------------------------------------------------------------------------

@router.put("/beitraege/{post_id}/merken")
def merken(post_id: str, user=Depends(current_user)):
    with conn() as c:
        nk.beitrag_oder_404(c, user, post_id)
        if not row(c, "SELECT post_id FROM net_saved WHERE user_id = :u AND "
                      "post_id = :p", u=user["id"], p=post_id):
            q(c, "INSERT INTO net_saved (user_id, post_id, created_at) VALUES "
                 "(:u, :p, :t)", u=user["id"], p=post_id, t=now_iso())
    return {"gemerkt": True}


@router.delete("/beitraege/{post_id}/merken")
def nicht_mehr_merken(post_id: str, user=Depends(current_user)):
    with conn() as c:
        q(c, "DELETE FROM net_saved WHERE user_id = :u AND post_id = :p",
          u=user["id"], p=post_id)
    return {"gemerkt": False}


@router.get("/gemerkt")
def gemerkte(seite: int = Query(0, ge=0, le=100), user=Depends(current_user)):
    """Gemerkte Beiträge, zuletzt gemerkte zuerst. Was inzwischen nicht mehr
    sichtbar ist (gelöscht, entfernt, privat geworden), fällt still heraus –
    Merken verschafft keinen Zugriff."""
    with conn() as c:
        aus = []
        for s_ in rows(c, "SELECT post_id FROM net_saved WHERE user_id = :u "
                          "ORDER BY created_at DESC", u=user["id"]):
            post = row(c, "SELECT * FROM net_posts WHERE id = :i", i=s_["post_id"])
            if post and not post["removed_at"] and nk.darf_beitrag_sehen(c, user, post):
                aus.append(post)
        stueck = aus[seite * SEITE:(seite + 1) * SEITE]
        return {"beitraege": [beitrag_aus(c, user, p) for p in stueck],
                "anzahl": len(aus),
                "weiter": seite + 1 if len(aus) > (seite + 1) * SEITE else None}


# --------------------------------------------------------------------------
# Fallvorstellung: hilfreiche Antwort
# --------------------------------------------------------------------------

@router.put("/beitraege/{post_id}/hilfreich/{comment_id}")
def hilfreich_markieren(post_id: str, comment_id: str, user=Depends(current_user)):
    with conn() as c:
        post = row(c, "SELECT * FROM net_posts WHERE id = :i AND author_id = :a "
                      "AND kind = 'fallvorstellung'", i=post_id, a=user["id"])
        if not post:
            raise HTTPException(404, "Fallvorstellung nicht gefunden.")
        k = row(c, "SELECT * FROM net_comments WHERE id = :i AND post_id = :p AND "
                   "removed_at IS NULL", i=comment_id, p=post_id)
        if not k:
            raise HTTPException(404, "Antwort nicht gefunden.")
        q(c, "UPDATE net_posts SET answer_comment_id = :k WHERE id = :p",
          k=comment_id, p=post_id)
        nk.melde(c, k["author_id"], "hilfreich", user["id"], post_id)
    return kommentare(post_id, user)


@router.delete("/beitraege/{post_id}/hilfreich")
def hilfreich_aufheben(post_id: str, user=Depends(current_user)):
    with conn() as c:
        if not row(c, "SELECT id FROM net_posts WHERE id = :i AND author_id = :a",
                   i=post_id, a=user["id"]):
            raise HTTPException(404, "Fallvorstellung nicht gefunden.")
        q(c, "UPDATE net_posts SET answer_comment_id = NULL WHERE id = :p", p=post_id)
    return kommentare(post_id, user)
