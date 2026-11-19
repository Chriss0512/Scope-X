"""Netzwerk: Suche, Übersicht, Vorschläge, Themen.

VORSCHLÄGE

Wen ich kennen könnte, ergibt sich aus Zusammenhängen, die jede Person
selbst angegeben hat. Punkte je Zusammenhang:

    gleiche Wache                         5
    gleiche Organisation im selben Kreis  3
    gleicher Kreis                        2
    folgt mir                             2
    gleiche Organisation                  1,5
    gemeinsame Kontakte                   0,6 je Kontakt (höchstens 3)
    gemeinsame Kurse und Funktionen       0,4 je Eintrag (höchstens 2)
    neu im Netz                           0,3

Ort, Organisation und Wache einer Person fließen nur ein, wenn ich ihr
volles Profil sehen dürfte – bei privaten Konten also nie, solange ich
nicht folge. Sonst ließe sich über die Vorschläge erfragen, wo ein
privates Konto arbeitet. Ausgeblendete Vorschläge kommen nicht wieder.

SUCHE

Eine Suche über Personen, Themen und Beiträge. Personen lassen sich nach
Kreis, Organisation, Wache und Qualifikation filtern; dieselbe
Sichtbarkeitsregel wie bei den Vorschlägen gilt auch für diese Filter.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .. import algorithmus
from .. import kataloge as kat
from .. import netzkern as nk
from ..core import audit, current_user, require_admin
from ..db import conn, now_iso, q, row, rows
from .beitraege import beitrag_aus

router = APIRouter(tags=["netz"])

NEU_TAGE = 30


def _kandidaten(c, ich: str) -> list[dict]:
    return rows(c, "SELECT p.*, p.user_id AS uid, u.disabled_at, u.role AS account_role, "
                   "u.created_at AS konto_seit FROM user_profile p JOIN users u ON "
                   "u.id = p.user_id WHERE p.net_active = 1 AND u.disabled_at IS NULL "
                   "AND p.user_id <> :ich", ich=ich)


def _darf_ort_sehen(c, ich: str, p: dict) -> bool:
    return not nk.privat(p) or nk.folgt(c, ich, p["uid"])


def _quals(c, uid: str) -> set[str]:
    return {r_["qual_id"] for r_ in rows(
        c, "SELECT u.qual_id FROM net_user_qualifications u JOIN net_qualifications k "
           "ON k.id = u.qual_id WHERE u.user_id = :u AND k.kategorie <> "
           "'Berufsabschluss'", u=uid)}


def vorschlaege_fuer(c, ich: str, anzahl: int = 12) -> list[dict]:
    mein = nk.profil(c, ich) or {}
    if not nk.aktiv(mein):
        return []
    gefolgt = nk.gefolgt_ids(c, ich)
    folgen_mir = nk.follower_ids(c, ich)
    ausgeschlossen = nk.blockierte_ids(c, ich) | {ich} | {
        f["followee_id"] for f in rows(
            c, "SELECT followee_id FROM net_follows WHERE follower_id = :i", i=ich)} | {
        d["other_id"] for d in rows(
            c, "SELECT other_id FROM net_dismissed WHERE user_id = :i", i=ich)}
    gemeinsam: dict[str, int] = {}
    for g in gefolgt:
        for zweit in nk.gefolgt_ids(c, g):
            gemeinsam[zweit] = gemeinsam.get(zweit, 0) + 1
    meine_quals = _quals(c, ich)
    kreis = kat.kreis_label(mein.get("kreis_ags"))
    grenze_neu = (datetime.now(timezone.utc) - timedelta(days=NEU_TAGE)).replace(
        microsecond=0).isoformat()

    bewertet = []
    for p in _kandidaten(c, ich):
        uid = p["uid"]
        if uid in ausgeschlossen:
            continue
        punkte, gruende = 0.0, []
        if _darf_ort_sehen(c, ich, p):
            gleiche_org = bool(mein.get("organisation_id")) and \
                p.get("organisation_id") == mein.get("organisation_id")
            gleicher_kreis = bool(mein.get("kreis_ags")) and \
                p.get("kreis_ags") == mein.get("kreis_ags")
            if mein.get("wache_id") and p.get("wache_id") == mein.get("wache_id"):
                punkte += 5
                gruende.append((5, "Gleiche Wache"))
            elif gleiche_org and gleicher_kreis:
                punkte += 3
                gruende.append((3, f"Gleiche Organisation, auch {kreis}"))
            elif gleicher_kreis:
                punkte += 2
                gruende.append((2, f"Auch {kreis}"))
            elif gleiche_org:
                punkte += 1.5
                gruende.append((1.5, "Gleiche Organisation"))
        if uid in folgen_mir:
            punkte += 2
            gruende.append((2.5, "Folgt dir"))
        n = gemeinsam.get(uid, 0)
        if n:
            punkte += 0.6 * min(3, n)
            gruende.append((1, "1 gemeinsamer Kontakt" if n == 1
                            else f"{n} gemeinsame Kontakte"))
        if meine_quals and not nk.privat(p):
            geteilt = len(meine_quals & _quals(c, uid))
            if geteilt:
                punkte += 0.4 * min(2, geteilt)
                gruende.append((0.5, "Gleiche Kurse und Funktionen"))
        if (p.get("konto_seit") or "") >= grenze_neu:
            punkte += 0.3
            gruende.append((0.2, "Neu im Netz"))
        if punkte <= 0:
            punkte = 0.05
        gruende.sort(key=lambda g: -g[0])
        bewertet.append((punkte, p, [g[1] for g in gruende[:2]]))
    bewertet.sort(key=lambda x: (-x[0], nk.anzeigename(x[1])))
    aus = []
    for punkte, p, gruende in bewertet[:anzahl]:
        person = nk.person_kurz(c, ich, p)
        person["gruende"] = gruende
        person["grund"] = gruende[0] if gruende else "Im Netz"
        aus.append(person)
    return aus


@router.get("/api/netz/vorschlaege")
def vorschlaege(anzahl: int = Query(8, ge=1, le=30), user=Depends(current_user)):
    with conn() as c:
        return {"personen": vorschlaege_fuer(c, user["id"], anzahl)}


@router.post("/api/netz/vorschlaege/{uid}/ausblenden")
def vorschlag_ausblenden(uid: str, user=Depends(current_user)):
    with conn() as c:
        if not row(c, "SELECT user_id FROM net_dismissed WHERE user_id = :u AND "
                      "other_id = :o", u=user["id"], o=uid):
            q(c, "INSERT INTO net_dismissed (user_id, other_id, created_at) VALUES "
                 "(:u, :o, :t)", u=user["id"], o=uid, t=now_iso())
    return {"ok": True}


# --------------------------------------------------------------------------
# Netzwerk-Übersicht
# --------------------------------------------------------------------------

def _personen(c, ich: str, ids: list[str]) -> list[dict]:
    aus = []
    for i in ids:
        p = nk.profil(c, i)
        if nk.aktiv(p) and not nk.blockiert(c, ich, i):
            aus.append(nk.person_kurz(c, ich, p))
    return aus


@router.get("/api/netz/netzwerk")
def netzwerk(user=Depends(current_user)):
    """Alles an einem Ort: Anfragen, Bürgschaften, Vorschläge, Kontakte."""
    ich = user["id"]
    with conn() as c:
        def ids(sql: str) -> list[str]:
            return [r_["x"] for r_ in rows(c, sql, u=ich)]
        anfragen = ids("SELECT follower_id AS x FROM net_follows WHERE followee_id = :u "
                       "AND status = 'angefragt' ORDER BY created_at DESC")
        ignoriert = ids("SELECT follower_id AS x FROM net_follows WHERE followee_id = :u "
                        "AND status = 'ignoriert' ORDER BY created_at DESC")
        folge_ich = ids("SELECT followee_id AS x FROM net_follows WHERE follower_id = :u "
                        "AND status = 'aktiv' ORDER BY accepted_at DESC")
        ausstehend = ids("SELECT followee_id AS x FROM net_follows WHERE follower_id = :u "
                         "AND status IN ('angefragt', 'ignoriert') "
                         "ORDER BY created_at DESC")
        follower = ids("SELECT follower_id AS x FROM net_follows WHERE followee_id = :u "
                       "AND status = 'aktiv' ORDER BY accepted_at DESC")
        buergschaften = rows(c, "SELECT id FROM applications WHERE sponsor_id = :u AND "
                                "status = 'offen' AND sponsor_status = 'angefragt'", u=ich)
        aktiv = nk.aktiv(nk.profil(c, ich))
        return {
            "aktiv": aktiv,
            "anfragen": _personen(c, ich, anfragen),
            "ignoriert": _personen(c, ich, ignoriert),
            "folge_ich": _personen(c, ich, folge_ich),
            "ausstehend": _personen(c, ich, ausstehend),
            "follower": _personen(c, ich, follower),
            "buergschaften": len(buergschaften),
            "vorschlaege": vorschlaege_fuer(c, ich, 24) if aktiv else [],
        }


@router.post("/api/netz/follower/{uid}/ignorieren")
def anfrage_ignorieren(uid: str, user=Depends(current_user)):
    """Ignorieren statt Ablehnen: die Anfrage verschwindet aus der Liste und
    aus dem Zähler, die anfragende Person bekommt kein Signal – für sie
    bleibt die Anfrage „angefragt“. Annehmen geht später noch."""
    with conn() as c:
        f = nk.follow(c, uid, user["id"])
        if not f or f["status"] != "angefragt":
            raise HTTPException(404, "Anfrage nicht gefunden.")
        q(c, "UPDATE net_follows SET status = 'ignoriert' WHERE id = :i", i=f["id"])
        # Die Mitteilung zur Anfrage verschwindet mit.
        q(c, "DELETE FROM net_notifications WHERE user_id = :u AND actor_id = :a "
             "AND kind = 'folgeanfrage'", u=user["id"], a=uid)
    return {"ok": True}


# --------------------------------------------------------------------------
# Suche
# --------------------------------------------------------------------------

@router.get("/api/netz/suche")
def suche(q_: str = Query("", alias="q", max_length=80),
          kreis: str = Query("", max_length=8),
          organisation: str = Query("", max_length=40),
          wache: str = Query("", max_length=40),
          qualifikation: str = Query("", max_length=40),
          user=Depends(current_user)):
    ich = user["id"]
    begriff = " ".join(q_.split()).lower()
    filter_aktiv = bool(kreis or organisation or wache or qualifikation)
    with conn() as c:
        nk.aktiv_erforderlich(c, user)
        gesperrt = nk.blockierte_ids(c, ich)
        personen = []
        if len(begriff) >= 2 or filter_aktiv:
            qual_ids = None
            if qualifikation:
                qual_ids = {r_["user_id"] for r_ in rows(
                    c, "SELECT user_id FROM net_user_qualifications WHERE qual_id = :q "
                       "AND (gueltig_bis IS NULL OR gueltig_bis >= :m)",
                    q=qualifikation, m=datetime.now(timezone.utc).strftime("%Y-%m"))}
            for p in _kandidaten(c, ich):
                if p["uid"] in gesperrt:
                    continue
                if begriff:
                    heu = " ".join((p.get("first_name") or "", p.get("last_name") or "",
                                    p.get("headline") or "")).lower()
                    if begriff.lstrip("@#") not in heu:
                        continue
                if filter_aktiv:
                    # Filter nach Ort, Organisation, Wache und Qualifikation
                    # nur bei Profilen, die ich vollständig sehen darf.
                    if not _darf_ort_sehen(c, ich, p):
                        continue
                    if kreis and p.get("kreis_ags") != kreis:
                        continue
                    if organisation and p.get("organisation_id") != organisation:
                        continue
                    if wache and p.get("wache_id") != wache:
                        continue
                    if qual_ids is not None and p["uid"] not in qual_ids:
                        continue
                personen.append(p)
                if len(personen) >= 60:
                    break
            personen.sort(key=lambda p: nk.anzeigename(p).lower())

        themen, tags, beitraege = [], [], []
        if len(begriff) >= 2 and not filter_aktiv:
            ohne = begriff.lstrip("#")
            muster = f"%{ohne}%"
            themen = [{"code": t["code"], "name": t["name"], "kategorie": t["kategorie"]}
                      for t in rows(c, "SELECT * FROM net_topics WHERE status = 'frei' "
                                       "AND (lower(name) LIKE :m OR code LIKE :m) "
                                       "ORDER BY sort_order LIMIT 8", m=muster)]
            bekannt = {t["code"] for t in themen}
            tags = [{"tag": t["tag"], "anzahl": t["n"]} for t in rows(
                c, "SELECT tag, COUNT(*) AS n FROM net_tags WHERE tag LIKE :m "
                   "GROUP BY tag ORDER BY n DESC LIMIT 12", m=muster)
                if t["tag"] not in bekannt]
            treffer = []
            for p in algorithmus.sichtbare_kandidaten(c, ich, fenster_tage=3650):
                heu = " ".join((p["title"] or "", p["body"] or "",
                                p["details"] or "", p["link_title"] or "")).lower()
                if ohne in heu:
                    treffer.append(p)
                if len(treffer) >= 20:
                    break
            beitraege = [beitrag_aus(c, user, p) for p in treffer]
        return {"personen": [nk.person_kurz(c, ich, p) for p in personen],
                "themen": themen, "tags": tags, "beitraege": beitraege}


# --------------------------------------------------------------------------
# Themen
# --------------------------------------------------------------------------

def themen_liste(c, ich: str, alle: bool = False) -> list[dict]:
    gefolgt = algorithmus.gefolgte_themen(c, ich)
    anzahl = {r_["tag"]: r_["n"] for r_ in rows(
        c, "SELECT t.tag, COUNT(*) AS n FROM net_tags t JOIN net_topics k ON "
           "k.code = t.tag GROUP BY t.tag")}
    sql = "SELECT * FROM net_topics " + ("" if alle else "WHERE status = 'frei' ") + \
        "ORDER BY sort_order, name"
    return [{"code": t["code"], "name": t["name"], "kategorie": t["kategorie"],
             "status": t["status"], "folge_ich": t["code"] in gefolgt,
             "beitraege": anzahl.get(t["code"], 0)} for t in rows(c, sql)]


@router.get("/api/netz/themen")
def themen(user=Depends(current_user)):
    with conn() as c:
        return {"kategorien": list(kat.THEMEN_KATEGORIEN),
                "themen": themen_liste(c, user["id"])}


@router.put("/api/netz/themen/{code}/folgen")
def thema_folgen(code: str, user=Depends(current_user)):
    with conn() as c:
        t = row(c, "SELECT code FROM net_topics WHERE code = :c AND status = 'frei'",
                c=code.lower()[:40])
        if not t:
            raise HTTPException(404, "Thema nicht gefunden.")
        if not row(c, "SELECT tag FROM net_topic_follows WHERE user_id = :u AND "
                      "tag = :t", u=user["id"], t=t["code"]):
            q(c, "INSERT INTO net_topic_follows (user_id, tag, created_at) VALUES "
                 "(:u, :t, :z)", u=user["id"], t=t["code"], z=now_iso())
    return {"folge_ich": True}


@router.delete("/api/netz/themen/{code}/folgen")
def thema_entfolgen(code: str, user=Depends(current_user)):
    with conn() as c:
        q(c, "DELETE FROM net_topic_follows WHERE user_id = :u AND tag = :t",
          u=user["id"], t=code.lower()[:40])
    return {"folge_ich": False}


class ThemaIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    kategorie: str
    code: str | None = Field(default=None, max_length=40, pattern=r"^[0-9a-zäöüß_-]{2,40}$")
    status: str | None = Field(default=None, pattern="^(frei|aus)$")


@router.get("/api/admin/themen")
def themen_admin(admin=Depends(require_admin)):
    with conn() as c:
        return {"kategorien": list(kat.THEMEN_KATEGORIEN),
                "themen": themen_liste(c, admin["id"], alle=True)}


@router.post("/api/admin/themen")
def thema_anlegen(data: ThemaIn, admin=Depends(require_admin)):
    if data.kategorie not in kat.THEMEN_KATEGORIEN:
        raise HTTPException(400, "Unbekannte Kategorie.")
    code = data.code or "-".join(kat.normalisiert(data.name).split())
    code = "".join(ch for ch in code if ch.isalnum() or ch in "-_")[:40]
    if len(code) < 2:
        raise HTTPException(400, "Kein gültiges Schlagwort.")
    with conn() as c:
        if row(c, "SELECT code FROM net_topics WHERE code = :c", c=code):
            raise HTTPException(409, "Dieses Thema gibt es schon.")
        q(c, "INSERT INTO net_topics (code, name, kategorie, status, sort_order, "
             "created_by, created_at) VALUES (:c, :n, :k, 'frei', 500, :u, :t)",
          c=code, n=" ".join(data.name.split()), k=data.kategorie, u=admin["id"],
          t=now_iso())
        audit(c, admin["id"], "net_topics", code, "create")
        return {"themen": themen_liste(c, admin["id"], alle=True)}


@router.put("/api/admin/themen/{code}")
def thema_aendern(code: str, data: ThemaIn, admin=Depends(require_admin)):
    if data.kategorie not in kat.THEMEN_KATEGORIEN:
        raise HTTPException(400, "Unbekannte Kategorie.")
    with conn() as c:
        if not row(c, "SELECT code FROM net_topics WHERE code = :c", c=code):
            raise HTTPException(404, "Thema nicht gefunden.")
        q(c, "UPDATE net_topics SET name = :n, kategorie = :k, status = :s "
             "WHERE code = :c", n=" ".join(data.name.split()), k=data.kategorie,
          s=data.status or "frei", c=code)
        audit(c, admin["id"], "net_topics", code, "update")
        return {"themen": themen_liste(c, admin["id"], alle=True)}
