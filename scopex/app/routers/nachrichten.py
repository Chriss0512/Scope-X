"""Kompetenznetz: Direktnachrichten.

Ein Gespräch je Paar. Wer einer Person schreibt, die ihr oder ihm nicht
folgt, landet dort zuerst unter „Anfragen“: das Gegenüber sieht die
Nachricht, kann aber annehmen oder ablehnen, und die schreibende Seite
erfährt nicht, ob sie gelesen wurde. Blockieren beendet jeden Austausch.

Inhalt: Text, ein geteilter Beitrag oder ein Bild. Der Text wird nur gegen
die eigenen Einsatznummern geprüft; Datum und Uhrzeit zu sperren, hieße
jede Terminabsprache unter Kolleg*innen zu verhindern.

Gespeichert wird im Klartext in der Datenbank des Add-ons. Eine
Ende-zu-Ende-Verschlüsselung gibt es nicht; die Administration kann die
Datenbank lesen. Das steht so auch in der Datenschutzerklärung.

Die Oberfläche fragt neue Nachrichten im Abstand weniger Sekunden ab,
solange ein Gespräch offen ist. Ein Websocket wäre schneller, braucht
aber eine dauerhafte Verbindung durch den Reverse Proxy.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import netzkern as nk
from ..core import current_user
from ..db import conn, new_id, now_iso, q, row, rows, scalar
from .beitraege import beitrag_aus

router = APIRouter(prefix="/api/netz/nachrichten", tags=["netz"])


def _fein() -> str:
    """Zeitstempel mit Mikrosekunden: zwei Nachrichten derselben Sekunde
    behalten ihre Reihenfolge, und das Nachladen verliert keine."""
    return datetime.now(timezone.utc).isoformat()


def _paar(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def _gegenueber(g: dict, ich: str) -> str:
    return g["user_b"] if g["user_a"] == ich else g["user_a"]


def _ausgeblendet_seit(g: dict, ich: str) -> str | None:
    return g["hidden_a"] if g["user_a"] == ich else g["hidden_b"]


def _gespraech_oder_404(c, ich: str, gid: str) -> dict:
    g = row(c, "SELECT * FROM net_conversations WHERE id = :i AND "
               "(user_a = :u OR user_b = :u)", i=gid, u=ich)
    if not g or nk.blockiert(c, ich, _gegenueber(g, ich)):
        raise HTTPException(404, "Gespräch nicht gefunden.")
    return g


def _nachricht_aus(c, user: dict, n: dict) -> dict:
    aus = {"id": n["id"], "von_mir": n["sender_id"] == user["id"],
           "text": n["body"], "erstellt": n["created_at"],
           "gelesen": bool(n["read_at"]), "beitrag": None, "bild": None}
    if n["post_id"]:
        post = row(c, "SELECT * FROM net_posts WHERE id = :i", i=n["post_id"])
        if post and not post["removed_at"] and nk.darf_beitrag_sehen(c, user, post):
            aus["beitrag"] = beitrag_aus(c, user, post, tiefe=1)
        else:
            aus["beitrag"] = {"nicht_verfuegbar": True}
    bild = row(c, "SELECT id, width, height FROM net_media WHERE message_id = :n "
                  "AND status = 'bereit'", n=n["id"])
    if bild:
        aus["bild"] = {"id": bild["id"], "breite": bild["width"], "hoehe": bild["height"]}
    return aus


def _vorschau(c, user: dict, g: dict) -> dict:
    ich = user["id"]
    seit = _ausgeblendet_seit(g, ich) or ""
    letzte = row(c, "SELECT * FROM net_messages WHERE conversation_id = :k AND "
                    "created_at > :s ORDER BY created_at DESC LIMIT 1",
                 k=g["id"], s=seit)
    andere = nk.profil(c, _gegenueber(g, ich))
    text = ""
    if letzte:
        text = letzte["body"] or ("Hat einen Beitrag gesendet" if letzte["post_id"]
                                  else "Hat ein Bild gesendet")
        if letzte["sender_id"] == ich:
            text = "Du: " + text
    return {
        "id": g["id"],
        "mit": nk.person_kurz(c, ich, andere),
        "letzte": text[:120],
        "aktualisiert": letzte["created_at"] if letzte else g["created_at"],
        "ungelesen": scalar(c, "SELECT COUNT(*) FROM net_messages WHERE "
                               "conversation_id = :k AND sender_id <> :u AND "
                               "read_at IS NULL AND created_at > :s",
                            k=g["id"], u=ich, s=seit) or 0,
        "anfrage": g["request_for"] == ich,
        "wartet": bool(g["request_for"]) and g["request_for"] != ich,
    }


@router.get("")
def gespraeche(user=Depends(current_user)):
    ich = user["id"]
    with conn() as c:
        nk.aktiv_erforderlich(c, user)
        posteingang, anfragen = [], []
        for g in rows(c, "SELECT * FROM net_conversations WHERE user_a = :u OR "
                         "user_b = :u ORDER BY last_at DESC LIMIT 200", u=ich):
            gegen = _gegenueber(g, ich)
            if nk.blockiert(c, ich, gegen) or not nk.aktiv(nk.profil(c, gegen)):
                continue
            seit = _ausgeblendet_seit(g, ich)
            if seit and g["last_at"] <= seit:
                continue
            v = _vorschau(c, user, g)
            (anfragen if v["anfrage"] else posteingang).append(v)
        return {"gespraeche": posteingang, "anfragen": anfragen}


class NachrichtIn(BaseModel):
    text: str = Field(default="", max_length=2000)
    post_id: str | None = None
    bild_id: str | None = None


class NeueNachrichtIn(NachrichtIn):
    an: str


def _senden(c, user: dict, g: dict, data: NachrichtIn) -> dict:
    ich = user["id"]
    text = (data.text or "").strip()
    if not text and not data.post_id and not data.bild_id:
        raise HTTPException(400, "Die Nachricht ist leer.")
    nk.pruefe_text(c, ich, text, nur_einsatznummer=True)
    if data.post_id:
        nk.beitrag_oder_404(c, user, data.post_id)
    bild = None
    if data.bild_id:
        bild = row(c, "SELECT * FROM net_media WHERE id = :i AND user_id = :u AND "
                      "kind = 'bild' AND post_id IS NULL AND message_id IS NULL",
                   i=data.bild_id, u=ich)
        if not bild:
            raise HTTPException(404, "Bild nicht gefunden.")
    nid = new_id()
    jetzt = _fein()
    q(c, "INSERT INTO net_messages (id, conversation_id, sender_id, body, post_id, "
         "created_at) VALUES (:i, :k, :s, :b, :p, :t)",
      i=nid, k=g["id"], s=ich, b=text, p=data.post_id, t=jetzt)
    if bild:
        q(c, "UPDATE net_media SET message_id = :n WHERE id = :i", n=nid, i=bild["id"])
    # Wer schreibt, holt ein ausgeblendetes Gespräch beim Gegenüber zurück.
    q(c, "UPDATE net_conversations SET last_at = :t WHERE id = :k", t=jetzt, k=g["id"])
    return _nachricht_aus(c, user, row(c, "SELECT * FROM net_messages WHERE id = :i",
                                       i=nid))


@router.post("")
def nachricht_an(data: NeueNachrichtIn, user=Depends(current_user)):
    """Schreibt an eine Person; legt das Gespräch an, wenn es keines gibt."""
    if nk.ist_gast(user):
        raise HTTPException(403, "Mit Lesezugriff lassen sich keine Nachrichten senden.")
    ich = user["id"]
    with conn() as c:
        nk.aktiv_erforderlich(c, user)
        if data.an == ich:
            raise HTTPException(400, "Nachrichten an dich selbst gibt es nicht.")
        andere = nk.profil(c, data.an)
        if not andere or not nk.aktiv(andere) or not nk.sichtbar(c, ich, data.an):
            raise HTTPException(404, "Mitglied nicht gefunden.")
        a, b = _paar(ich, data.an)
        g = row(c, "SELECT * FROM net_conversations WHERE user_a = :a AND user_b = :b",
                a=a, b=b)
        if not g:
            # Anfrage, solange das Gegenüber mir nicht folgt.
            anfrage = None if nk.folgt(c, data.an, ich) else data.an
            gid = new_id()
            q(c, "INSERT INTO net_conversations (id, user_a, user_b, request_for, "
                 "created_at, last_at) VALUES (:i, :a, :b, :r, :t, :t)",
              i=gid, a=a, b=b, r=anfrage, t=_fein())
            g = row(c, "SELECT * FROM net_conversations WHERE id = :i", i=gid)
        nachricht = _senden(c, user, g, data)
        return {"gespraech": g["id"], "nachricht": nachricht}


@router.get("/{gid}")
def verlauf(gid: str, nach: str | None = None, user=Depends(current_user)):
    ich = user["id"]
    with conn() as c:
        g = _gespraech_oder_404(c, ich, gid)
        # nach: Zeitstempel der letzten bekannten Nachricht. Mit >= statt >,
        # die Oberfläche entfernt Doppelte über die Kennung.
        liste = rows(c, "SELECT * FROM net_messages WHERE conversation_id = :k AND "
                        "created_at > :s AND created_at >= :n "
                        "ORDER BY created_at DESC LIMIT 200",
                     k=gid, s=_ausgeblendet_seit(g, ich) or "", n=nach or "")
        liste.reverse()
        # Gelesen wird nur, was nicht in einer offenen Anfrage steckt —
        # sonst erführe die schreibende Seite, dass die Anfrage gesehen wurde.
        if g["request_for"] != ich:
            q(c, "UPDATE net_messages SET read_at = :t WHERE conversation_id = :k "
                 "AND sender_id <> :u AND read_at IS NULL", t=now_iso(), k=gid, u=ich)
        andere = nk.profil(c, _gegenueber(g, ich))
        return {
            "id": gid,
            "mit": nk.person_kurz(c, ich, andere),
            "anfrage": g["request_for"] == ich,
            "wartet": bool(g["request_for"]) and g["request_for"] != ich,
            "nachrichten": [_nachricht_aus(c, user, n) for n in liste],
        }


@router.post("/{gid}")
def antworten(gid: str, data: NachrichtIn, user=Depends(current_user)):
    if nk.ist_gast(user):
        raise HTTPException(403, "Mit Lesezugriff lassen sich keine Nachrichten senden.")
    with conn() as c:
        nk.aktiv_erforderlich(c, user)
        g = _gespraech_oder_404(c, user["id"], gid)
        if g["request_for"] == user["id"]:
            # Antworten heißt annehmen.
            q(c, "UPDATE net_conversations SET request_for = NULL WHERE id = :i", i=gid)
        return _senden(c, user, g, data)


@router.post("/{gid}/annehmen")
def anfrage_annehmen(gid: str, user=Depends(current_user)):
    with conn() as c:
        g = _gespraech_oder_404(c, user["id"], gid)
        if g["request_for"] == user["id"]:
            q(c, "UPDATE net_conversations SET request_for = NULL WHERE id = :i", i=gid)
    return {"ok": True}


@router.delete("/{gid}")
def gespraech_ausblenden(gid: str, user=Depends(current_user)):
    """Blendet ein Gespräch für mich aus. Eine offene Anfrage wird damit
    abgelehnt und für beide Seiten gelöscht."""
    ich = user["id"]
    with conn() as c:
        g = _gespraech_oder_404(c, ich, gid)
        if g["request_for"] == ich:
            for n in rows(c, "SELECT id FROM net_messages WHERE conversation_id = :k",
                          k=gid):
                from .netz import medium_loeschen
                for m in rows(c, "SELECT id, user_id FROM net_media WHERE "
                                 "message_id = :n", n=n["id"]):
                    medium_loeschen(c, m["id"], m["user_id"])
            q(c, "DELETE FROM net_messages WHERE conversation_id = :k", k=gid)
            q(c, "DELETE FROM net_conversations WHERE id = :k", k=gid)
        else:
            spalte = "hidden_a" if g["user_a"] == ich else "hidden_b"
            q(c, f"UPDATE net_conversations SET {spalte} = :t WHERE id = :k",
              t=_fein(), k=gid)
    return {"ok": True}


@router.delete("/nachricht/{nid}")
def zuruecknehmen(nid: str, user=Depends(current_user)):
    """Eigene Nachricht für beide Seiten zurücknehmen."""
    with conn() as c:
        n = row(c, "SELECT * FROM net_messages WHERE id = :i AND sender_id = :u",
                i=nid, u=user["id"])
        if not n:
            raise HTTPException(404, "Nachricht nicht gefunden.")
        from .netz import medium_loeschen
        for m in rows(c, "SELECT id FROM net_media WHERE message_id = :n", n=nid):
            medium_loeschen(c, m["id"], user["id"])
        q(c, "DELETE FROM net_messages WHERE id = :i", i=nid)
    return {"ok": True}
