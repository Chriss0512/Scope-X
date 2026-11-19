"""Zugang: Nutzungsvereinbarung, Bewerbung, Bürgschaft.

Bewerbung in vier Schritten:

1. Wer noch kein Konto hat, bewirbt sich öffentlich (Rechenaufgabe und
   Drosselung wie bei der Anmeldung). Optional nennt die Person ein
   Mitglied, das für sie bürgt.
2. Ein Link per E-Mail bestätigt die Adresse. Unbestätigte Bewerbungen
   verfallen nach 48 Stunden spurlos.
3. Das genannte Mitglied wird gefragt, ob es die Person kennt. Es sieht
   Name, Qualifikation, Region und Begründung, nicht die E-Mail-Adresse.
4. Die Administration entscheidet. Bei Annahme geht eine gewöhnliche
   Einladung an die bestätigte Adresse.

Die öffentliche Antwort ist immer dieselbe – ob es die Adresse schon als
Konto gibt, ob eine Bewerbung offen ist oder ob das genannte Mitglied
existiert, lässt sich darüber nicht herausfinden. Wer schon ein Konto hat,
bekommt stattdessen eine Mail mit dem Hinweis auf „Passwort vergessen“.

Aufbewahrung: entschiedene Bewerbungen werden 30 Tage nach der
Entscheidung gelöscht, eine angenommene spätestens mit der Registrierung.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .. import kataloge as kat
from .. import mailer, nutzung, schutz
from ..core import (
    ROLE_LABELS,
    audit,
    current_user,
    fresh_totp_required,
    get_setting,
    require_admin,
    set_setting,
)
from ..db import conn, new_id, now_iso, q, row, rows, scalar
from ..security import hash_ip, token_hash
from .admin import _new_code
from .auth import _norm, _tor_oeffnen, client_ip

log = logging.getLogger("scopex.zugang")

router = APIRouter(tags=["zugang"])

BESTAETIGUNG_STUNDEN = 48
AUFBEWAHRUNG_TAGE = 30
JE_ADRESSE_UND_TAG = 3
EINLADUNG_TAGE = 14

ANTWORT = ("Fast geschafft: Wir haben dir eine E-Mail geschickt. Bitte "
           "bestätige deine Adresse über den Link darin. Erst danach geht "
           "deine Bewerbung an die Administration.")


def _vor(**kw) -> str:
    return (datetime.now(timezone.utc) - timedelta(**kw)).replace(
        microsecond=0).isoformat()


# --------------------------------------------------------------------------
# Nutzungsvereinbarung
# --------------------------------------------------------------------------

@router.get("/api/oeffentlich/nutzungsbedingungen")
def nutzungsbedingungen():
    return nutzung.fassung()


@router.get("/api/nutzung")
def nutzung_status(user=Depends(current_user)):
    with conn() as c:
        offen = nutzung.offen(c, user["id"])
        frueher = row(c, "SELECT version, accepted_at FROM terms_acceptance "
                         "WHERE user_id = :u ORDER BY accepted_at DESC LIMIT 1",
                      u=user["id"])
    return {**nutzung.fassung(), "offen": offen,
            "zuletzt": frueher or None}


class ZustimmungIn(BaseModel):
    version: str = Field(max_length=20)


@router.post("/api/nutzung/zustimmen")
def nutzung_zustimmen(data: ZustimmungIn, user=Depends(current_user)):
    # Die Fassung, die die Person gelesen hat, muss die aktuelle sein. Sonst
    # würde eine offene Seite von gestern der Fassung von heute zustimmen.
    if data.version != nutzung.VERSION:
        raise HTTPException(409, "Die Vereinbarung wurde inzwischen geändert. "
                                 "Bitte lies die aktuelle Fassung.")
    with conn() as c:
        nutzung.zustimmen(c, user["id"])
        audit(c, user["id"], "terms_acceptance", user["id"], "accept",
              "version", None, nutzung.VERSION)
    return {"ok": True}


# --------------------------------------------------------------------------
# Bewerbung (öffentlich)
# --------------------------------------------------------------------------

def _offen(c) -> bool:
    return get_setting(c, "bewerbung_offen", "1") == "1"


@router.get("/api/oeffentlich/bewerbung")
def bewerbung_zustand():
    """Ob die Bewerbung angeboten wird. Ohne Mailversand gibt es keine
    Bestätigung und damit keine Bewerbung."""
    with conn() as c:
        offen = _offen(c)
        berufe = rows(c, "SELECT name FROM net_qualifications WHERE "
                         "kategorie = 'Berufsabschluss' AND status = 'frei' "
                         "ORDER BY sort_order, name")
    return {"offen": offen and mailer.is_configured(),
            "berufe": [b["name"] for b in berufe]}


class BewerbungIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=200)
    qualification: str = Field(min_length=2, max_length=80)
    kreis_ags: str | None = Field(default=None, max_length=8)
    organisation: str = Field(default="", max_length=120)
    wache: str = Field(default="", max_length=120)
    motivation: str = Field(default="", max_length=1000)
    buerge: str = Field(default="", max_length=200)
    # Code aus der Empfehlung eines Mitglieds, falls vorhanden.
    empfehlung: str = Field(default="", max_length=80)
    datenschutz: bool = False
    pow: dict | None = None


def _bestaetigung_senden(to: str, token: str) -> None:
    url = mailer.link(f"#/bewerben?token={token}")
    mailer.send(to, "SCOPE X: Bitte bestätige deine Bewerbung", f"""\
Du hast dich um Zugang zu SCOPE X beworben, dem Kompetenzlogbuch und
Fachnetzwerk für die Notfallversorgung.

Bitte bestätige deine E-Mail-Adresse über diesen Link:

{url}

Der Link gilt {BESTAETIGUNG_STUNDEN} Stunden. Danach wird die Bewerbung
ohne Rückstände gelöscht.

Warst du das nicht, ignoriere diese Nachricht einfach.
""")


def _konto_vorhanden_senden(to: str) -> None:
    mailer.send(to, "SCOPE X: Du hast bereits ein Konto", f"""\
Für diese E-Mail-Adresse wurde eine Bewerbung um Zugang zu SCOPE X
abgeschickt. Zu der Adresse gibt es aber bereits ein Konto.

Melde dich einfach an. Falls du dein Passwort nicht mehr weißt:

{mailer.link("#/passwort-vergessen")}

Warst du das nicht, ignoriere diese Nachricht.
""")


def _empfehlung(c, code: str) -> dict | None:
    """Gültige, ungenutzte Empfehlung zu einem Code."""
    if not code:
        return None
    r_ = row(c, "SELECT * FROM referrals WHERE code_hash = :h", h=token_hash(code.strip()))
    if not r_ or r_["used_at"] or r_["revoked_at"] or r_["expires_at"] < now_iso():
        return None
    return r_


@router.post("/api/oeffentlich/bewerbung")
def bewerben(data: BewerbungIn, request: Request):
    _tor_oeffnen(request, data.pow, kennung=_norm(data.email))
    if not data.datenschutz:
        raise HTTPException(400, "Bitte bestätige, dass du die Hinweise zum "
                                 "Datenschutz gelesen hast.")
    email = _norm(data.email)
    if "@" not in email or " " in email or len(email.split("@")[-1]) < 3:
        raise HTTPException(400, "Die E-Mail-Adresse sieht nicht gültig aus.")
    if data.kreis_ags and not kat.kreis_gueltig(data.kreis_ags):
        raise HTTPException(400, "Unbekannter Kreis.")
    ip = hash_ip(client_ip(request))
    email_idx = schutz.index(email)
    sofort = False
    with conn() as c:
        if not _offen(c) or not mailer.is_configured():
            raise HTTPException(503, "Bewerbungen sind derzeit nicht möglich.")
        aufraeumen(c)
        empf = _empfehlung(c, data.empfehlung)
        if data.empfehlung and not empf:
            # Wer den Link hat, ist die empfohlene Person; ihr darf man sagen,
            # dass er nicht mehr gilt.
            raise HTTPException(400, "Diese Empfehlung ist abgelaufen oder wurde "
                                     "schon verwendet. Du kannst dich trotzdem "
                                     "ohne Empfehlung bewerben.")
        # Drosselung je Herkunft. Was darüber hinausgeht, verschwindet still,
        # damit die Antwort nichts über die Grenze verrät.
        if not empf and ip and (scalar(c, "SELECT COUNT(*) FROM applications WHERE "
                                          "ip_hash = :h AND created_at > :t",
                                       h=ip, t=_vor(days=1)) or 0) >= JE_ADRESSE_UND_TAG:
            log.info("Bewerbung über Tagesgrenze verworfen.")
            return {"ok": True, "detail": ANTWORT}

        if row(c, "SELECT id FROM users WHERE email_idx = :x", x=email_idx):
            _konto_vorhanden_senden(email)
            return {"ok": True, "detail": ANTWORT}

        vorhanden = row(c, "SELECT id, status FROM applications WHERE email_idx = :x "
                           "AND status IN ('unbestaetigt', 'offen')", x=email_idx)
        if vorhanden and vorhanden["status"] == "offen":
            # Schon bestätigt und in Prüfung. Keine zweite Bewerbung, keine Mail:
            # die Person hat ihre Bestätigung bereits erhalten.
            return {"ok": True, "detail": ANTWORT}

        token = secrets.token_urlsafe(32)
        buerge_id, buerge_status, buerge_text = None, None, None
        if empf:
            # Das empfehlende Mitglied hat schon gebürgt, als es die Empfehlung
            # verschickt hat. Es wird nicht noch einmal gefragt.
            buerge_id, buerge_status = empf["created_by"], "empfohlen"
            # Die Empfehlung ging an genau diese Adresse: der Klick auf den
            # Link hat sie bestätigt, eine zweite Mail braucht es nicht.
            sofort = empf["email_idx"] == email_idx
        else:
            eingabe = _norm(data.buerge)
            if eingabe:
                b = row(c, "SELECT id FROM users WHERE (LOWER(username) = :n OR "
                           "email_idx = :x) AND disabled_at IS NULL",
                        n=eingabe, x=schutz.index(eingabe))
                if b:
                    buerge_id, buerge_status = b["id"], "wartet"
                else:
                    # Nicht gefunden: die Eingabe bleibt für die Administration
                    # sichtbar, die Person erfährt nichts davon.
                    buerge_status = "nicht_gefunden"
                    buerge_text = data.buerge.strip()[:200]

        felder = {
            "f": schutz.v(data.first_name.strip()), "l": schutz.v(data.last_name.strip()),
            "e": schutz.v(email), "ex": email_idx,
            "q": schutz.v(data.qualification.strip()), "k": data.kreis_ags or None,
            "o": schutz.v(data.organisation.strip() or None),
            "w": schutz.v(data.wache.strip() or None),
            "m": schutz.v(data.motivation.strip() or None), "si": buerge_id,
            "ss": buerge_status, "st": schutz.v(buerge_text),
            "h": None if sofort else token_hash(token), "ip": ip, "t": now_iso(),
            "st2": "offen" if sofort else "unbestaetigt",
            "ca": now_iso() if sofort else None, "rid": empf["id"] if empf else None}
        if vorhanden:
            # Erneut abgeschickt, bevor bestätigt wurde: Angaben und Link
            # werden erneuert, der alte Link verfällt.
            aid = vorhanden["id"]
            q(c, "UPDATE applications SET first_name = :f, last_name = :l, email = :e, "
                 "email_idx = :ex, qualification = :q, kreis_ags = :k, "
                 "organisation = :o, wache = :w, motivation = :m, sponsor_id = :si, "
                 "sponsor_status = :ss, sponsor_text = :st, token_hash = :h, "
                 "ip_hash = :ip, created_at = :t, status = :st2, confirmed_at = :ca, "
                 "referral_id = :rid WHERE id = :i", i=aid, **felder)
        else:
            aid = new_id()
            q(c, "INSERT INTO applications (id, first_name, last_name, email, email_idx, "
                 "qualification, kreis_ags, organisation, wache, motivation, "
                 "sponsor_id, sponsor_status, sponsor_text, status, token_hash, "
                 "ip_hash, created_at, confirmed_at, referral_id) VALUES (:i, :f, :l, "
                 ":e, :ex, :q, :k, :o, :w, :m, :si, :ss, :st, :st2, :h, :ip, :t, :ca, "
                 ":rid)", i=aid, **felder)
        if empf:
            q(c, "UPDATE referrals SET used_at = :t, application_id = :a WHERE id = :i",
              t=now_iso(), a=aid, i=empf["id"])
        if sofort:
            for a in _admins(c):
                _melde(c, a["id"], "bewerbung", aid)
    if sofort:
        return {"ok": True, "detail": "Danke! Deine Bewerbung ist eingegangen. Die "
                                      "Administration entscheidet und meldet sich per "
                                      "E-Mail bei dir."}
    _bestaetigung_senden(email, token)
    return {"ok": True, "detail": ANTWORT}


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


def _admins(c) -> list[dict]:
    return rows(c, "SELECT id, email FROM users WHERE role = 'admin' "
                   "AND disabled_at IS NULL")


def _melde(c, an: str, art: str, ref: str) -> None:
    q(c, "INSERT INTO net_notifications (id, user_id, kind, ref_id, created_at) "
         "VALUES (:i, :u, :k, :r, :t)", i=new_id(), u=an, k=art, r=ref, t=now_iso())


@router.post("/api/oeffentlich/bewerbung/bestaetigen")
def bewerbung_bestaetigen(data: TokenIn):
    buerge_mail = None
    with conn() as c:
        b = row(c, "SELECT * FROM applications WHERE token_hash = :h",
                h=token_hash(data.token))
        if not b or b["status"] != "unbestaetigt" or \
                b["created_at"] < _vor(hours=BESTAETIGUNG_STUNDEN):
            raise HTTPException(400, "Dieser Link ist ungültig oder abgelaufen.")
        q(c, "UPDATE applications SET status = 'offen', confirmed_at = :t, "
             "token_hash = NULL WHERE id = :i", t=now_iso(), i=b["id"])
        # Nur wer genannt wurde, wird gefragt. Ein empfehlendes Mitglied hat
        # schon gebürgt und bekommt keine zweite Nachricht.
        if b["sponsor_id"] and b["sponsor_status"] == "wartet":
            q(c, "UPDATE applications SET sponsor_status = 'angefragt' WHERE id = :i",
              i=b["id"])
            _melde(c, b["sponsor_id"], "buergschaft", b["id"])
            s = row(c, "SELECT email FROM users WHERE id = :i", i=b["sponsor_id"])
            buerge_mail = s["email"] if s else None
        for a in _admins(c):
            _melde(c, a["id"], "bewerbung", b["id"])
    if buerge_mail:
        mailer.send(buerge_mail, "SCOPE X: Kennst du diese Person?", f"""\
Jemand hat sich um Zugang zu SCOPE X beworben und dich als Person genannt,
die für sie bürgen kann.

Bitte sieh dir die Bewerbung unter „Netzwerk“ an und sag der Administration,
ob du die Person kennst:

{mailer.link("#/netzwerk")}

Du bist zu nichts verpflichtet. Kennst du die Person nicht, sag das einfach.
""")
    return {"ok": True, "detail": "Danke! Deine E-Mail-Adresse ist bestätigt. "
                                  "Die Administration meldet sich bei dir."}


# --------------------------------------------------------------------------
# Bürgschaft (Mitglied)
# --------------------------------------------------------------------------

def _fuer_buerge(b: dict) -> dict:
    """Was ein bürgendes Mitglied sieht: genug, um die Person zu erkennen,
    nicht mehr. Keine E-Mail-Adresse."""
    return {"id": b["id"], "vorname": b["first_name"], "nachname": b["last_name"],
            "qualifikation": b["qualification"], "kreis": kat.kreis_label(b["kreis_ags"]),
            "organisation": b["organisation"] or "", "wache": b["wache"] or "",
            "begruendung": b["motivation"] or "", "erstellt": b["confirmed_at"],
            "antwort": b["sponsor_status"], "text": b["sponsor_text"] or ""}


@router.get("/api/netz/buergschaften")
def buergschaften(user=Depends(current_user)):
    with conn() as c:
        # Empfehlungen stehen unter „Kolleg*innen einladen“, nicht hier:
        # wer empfohlen hat, wird nicht noch einmal gefragt.
        liste = rows(c, "SELECT * FROM applications WHERE sponsor_id = :u AND "
                        "status = 'offen' AND sponsor_status <> 'empfohlen' "
                        "ORDER BY confirmed_at DESC", u=user["id"])
    return {"buergschaften": [_fuer_buerge(b) for b in liste]}


class BuergschaftIn(BaseModel):
    antwort: str = Field(pattern="^(ja|nein)$")
    text: str = Field(default="", max_length=500)


@router.post("/api/netz/buergschaften/{aid}")
def buergschaft_beantworten(aid: str, data: BuergschaftIn,
                            user=Depends(current_user)):
    with conn() as c:
        # sponsor_id = Anfragende: sonst könnte jedes Mitglied für jede
        # Bewerbung bürgen, deren Kennung es errät.
        b = row(c, "SELECT * FROM applications WHERE id = :i AND sponsor_id = :u "
                   "AND status = 'offen' AND sponsor_status <> 'empfohlen'",
                i=aid, u=user["id"])
        if not b:
            raise HTTPException(404, "Anfrage nicht gefunden.")
        status = "bestaetigt" if data.antwort == "ja" else "abgelehnt"
        q(c, "UPDATE applications SET sponsor_status = :s, sponsor_text = :x, "
             "sponsor_at = :t WHERE id = :i",
          s=status, x=schutz.v(data.text.strip() or None), t=now_iso(), i=aid)
        audit(c, user["id"], "applications", aid, "sponsor", "sponsor_status",
              b["sponsor_status"], status)
        for a in _admins(c):
            _melde(c, a["id"], "bewerbung", aid)
    return {"ok": True}


# --------------------------------------------------------------------------
# Administration
# --------------------------------------------------------------------------

def aufraeumen(c) -> int:
    """Löscht verfallene und lange entschiedene Bewerbungen."""
    a = q(c, "DELETE FROM applications WHERE status = 'unbestaetigt' AND "
             "created_at < :t", t=_vor(hours=BESTAETIGUNG_STUNDEN)).rowcount or 0
    b = q(c, "DELETE FROM applications WHERE status IN ('angenommen', 'abgelehnt') "
             "AND decided_at < :t", t=_vor(days=AUFBEWAHRUNG_TAGE)).rowcount or 0
    # Empfehlungen enthalten die Adresse eines Menschen, der (noch) kein
    # Mitglied ist. 90 Tage nach Ablauf verschwinden sie.
    r_ = q(c, "DELETE FROM referrals WHERE expires_at < :t",
           t=_vor(days=90 + EMPFEHLUNG_TAGE)).rowcount or 0
    return a + b + r_


def _fuer_admin(c, b: dict) -> dict:
    aus = _fuer_buerge(b)
    aus.update({"email": b["email"], "status": b["status"],
                "per_empfehlung": bool(b.get("referral_id")),
                "beworben": b["created_at"], "entschieden": b["decided_at"],
                "notiz": b["decision_note"] or "", "buerge": None,
                "buerge_eingabe": ""})
    if b["sponsor_id"]:
        s = row(c, "SELECT u.username, p.first_name, p.last_name FROM users u "
                   "LEFT JOIN user_profile p ON p.user_id = u.id WHERE u.id = :i",
                i=b["sponsor_id"])
        if s:
            aus["buerge"] = {"id": b["sponsor_id"], "benutzername": s["username"],
                             "name": " ".join(x for x in (s["first_name"],
                                                          s["last_name"]) if x)}
    elif b["sponsor_status"] == "nicht_gefunden":
        aus["buerge_eingabe"] = b["sponsor_text"] or ""
        aus["text"] = ""
    return aus


@router.get("/api/admin/bewerbungen")
def bewerbungen(admin=Depends(require_admin)):
    with conn() as c:
        aufraeumen(c)
        liste = rows(c, "SELECT * FROM applications WHERE status <> 'unbestaetigt' "
                        "ORDER BY CASE WHEN status = 'offen' THEN 0 ELSE 1 END, "
                        "created_at DESC LIMIT 200")
        return {"bewerbungen": [_fuer_admin(c, b) for b in liste],
                "offen": _offen(c), "mail": mailer.is_configured()}


class SchalterIn(BaseModel):
    offen: bool


@router.put("/api/admin/bewerbungen/einstellung")
def bewerbung_schalten(data: SchalterIn, admin=Depends(require_admin)):
    with conn() as c:
        set_setting(c, "bewerbung_offen", "1" if data.offen else "0")
        audit(c, admin["id"], "settings", "bewerbung_offen", "update",
              "svalue", None, "1" if data.offen else "0")
    return {"ok": True, "offen": data.offen}


class AnnahmeIn(BaseModel):
    totp_code: str = Field(default="", max_length=12)
    role: str = Field(default="user", pattern="^(user|guest)$")
    notiz: str = Field(default="", max_length=300)


@router.post("/api/admin/bewerbungen/{aid}/annehmen")
def bewerbung_annehmen(aid: str, data: AnnahmeIn, admin=Depends(require_admin)):
    # Eine Annahme erzeugt einen Zugang. Dafür gilt dasselbe wie für jede
    # Einladung: frischer Code aus der Authenticator-App.
    fresh_totp_required(admin, data.totp_code)
    code = _new_code()
    ablauf = (datetime.now(timezone.utc) + timedelta(days=EINLADUNG_TAGE)).replace(
        microsecond=0).isoformat()
    with conn() as c:
        b = row(c, "SELECT * FROM applications WHERE id = :i AND status = 'offen'",
                i=aid)
        if not b:
            raise HTTPException(404, "Bewerbung nicht gefunden oder bereits entschieden.")
        if row(c, "SELECT id FROM users WHERE email_idx = :x", x=b["email_idx"]):
            raise HTTPException(409, "Zu dieser Adresse gibt es inzwischen ein Konto.")
        iid = new_id()
        q(c, "INSERT INTO invitations (id, code_hash, email, role, note, created_by, "
             "created_at, expires_at) VALUES (:i, :h, :e, :r, :n, :cb, :c, :x)",
          i=iid, h=token_hash(code), e=schutz.v(b["email"]), r=data.role,
          n=schutz.v("Bewerbung"), cb=admin["id"], c=now_iso(), x=ablauf)
        q(c, "UPDATE applications SET status = 'angenommen', decided_at = :t, "
             "decided_by = :a, decision_note = :n, invitation_id = :iid WHERE id = :i",
          t=now_iso(), a=admin["id"], n=schutz.v(data.notiz.strip() or None), iid=iid,
          i=aid)
        audit(c, admin["id"], "applications", aid, "accept", "role", None, data.role)
        audit(c, admin["id"], "invitations", iid, "create", "role", None, data.role)
        email = b["email"]
    gesendet = mailer.send_invitation(email, code, ROLE_LABELS[data.role],
                                      EINLADUNG_TAGE)
    return {"ok": True, "sent": gesendet,
            "link": mailer.link(f"#/registrieren?code={code}")}


class AblehnungIn(BaseModel):
    notiz: str = Field(default="", max_length=300)
    benachrichtigen: bool = True


@router.post("/api/admin/bewerbungen/{aid}/ablehnen")
def bewerbung_ablehnen(aid: str, data: AblehnungIn, admin=Depends(require_admin)):
    with conn() as c:
        b = row(c, "SELECT * FROM applications WHERE id = :i AND status = 'offen'",
                i=aid)
        if not b:
            raise HTTPException(404, "Bewerbung nicht gefunden oder bereits entschieden.")
        q(c, "UPDATE applications SET status = 'abgelehnt', decided_at = :t, "
             "decided_by = :a, decision_note = :n WHERE id = :i",
          t=now_iso(), a=admin["id"], n=schutz.v(data.notiz.strip() or None), i=aid)
        audit(c, admin["id"], "applications", aid, "reject")
        email = b["email"]
    if data.benachrichtigen:
        mailer.send(email, "SCOPE X: Deine Bewerbung", """\
Danke für dein Interesse an SCOPE X.

Wir können deiner Bewerbung um Zugang derzeit leider nicht entsprechen.
Deine Angaben werden in 30 Tagen gelöscht.
""")
    return {"ok": True}


def nach_registrierung(c, invitation_id: str, user_id: str) -> None:
    """Übernimmt den Kreis aus der Bewerbung ins Profil und löscht die
    Bewerbung: sie hat ihren Zweck erfüllt."""
    b = row(c, "SELECT * FROM applications WHERE invitation_id = :i",
            i=invitation_id)
    if not b:
        return
    if b["kreis_ags"]:
        q(c, "UPDATE user_profile SET kreis_ags = :k WHERE user_id = :u",
          k=b["kreis_ags"], u=user_id)
    q(c, "DELETE FROM applications WHERE id = :i", i=b["id"])


# --------------------------------------------------------------------------
# Empfehlung durch Mitglieder
# --------------------------------------------------------------------------
#
# Ein Mitglied lädt jemanden ein. Anders als bei einer Einladung der
# Administration entsteht daraus kein Konto, sondern eine Bewerbung: die
# empfohlene Person füllt das Formular aus, das empfehlende Mitglied steht
# schon als Bürge fest (ohne erneute Nachricht), und die Administration
# entscheidet wie bei jeder Bewerbung.

EMPFEHLUNG_TAGE = 14
OFFEN_JE_MITGLIED = 5
JE_MITGLIED_30_TAGE = 10


class EmpfehlungIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    name: str = Field(default="", max_length=120)


def _empfehlung_status(c, r_: dict) -> str:
    if r_["revoked_at"]:
        return "zurückgezogen"
    if r_["used_at"]:
        if row(c, "SELECT id FROM users WHERE email_idx = :x", x=r_["email_idx"]):
            return "Mitglied geworden"
        return "beworben"
    if r_["expires_at"] < now_iso():
        return "abgelaufen"
    return "verschickt"


def _empfehlungen(c, uid: str) -> list[dict]:
    return [{"id": r_["id"], "email": r_["email"], "name": r_["name"] or "",
             "erstellt": r_["created_at"], "gueltig_bis": r_["expires_at"],
             "status": _empfehlung_status(c, r_)}
            for r_ in rows(c, "SELECT * FROM referrals WHERE created_by = :u "
                              "ORDER BY created_at DESC LIMIT 50", u=uid)]


@router.get("/api/netz/empfehlungen")
def empfehlungen(user=Depends(current_user)):
    with conn() as c:
        moeglich = _offen(c) and mailer.is_configured() and \
            (user.get("role") or "user") != "guest"
        return {"moeglich": moeglich, "empfehlungen": _empfehlungen(c, user["id"])}


@router.post("/api/netz/empfehlungen")
def empfehlen(data: EmpfehlungIn, user=Depends(current_user)):
    if (user.get("role") or "user") == "guest":
        raise HTTPException(403, "Mit Lesezugriff lässt sich niemand einladen.")
    email = _norm(data.email)
    if "@" not in email or " " in email or len(email.split("@")[-1]) < 3:
        raise HTTPException(400, "Die E-Mail-Adresse sieht nicht gültig aus.")
    name = " ".join(data.name.split())
    with conn() as c:
        if not _offen(c) or not mailer.is_configured():
            raise HTTPException(503, "Einladungen durch Mitglieder sind derzeit nicht "
                                     "möglich.")
        offen = scalar(c, "SELECT COUNT(*) FROM referrals WHERE created_by = :u AND "
                          "used_at IS NULL AND revoked_at IS NULL AND expires_at > :t",
                       u=user["id"], t=now_iso()) or 0
        if offen >= OFFEN_JE_MITGLIED:
            raise HTTPException(429, f"Du hast schon {OFFEN_JE_MITGLIED} offene "
                                     "Einladungen. Ziehe eine zurück oder warte, bis "
                                     "sie verwendet wurde.")
        zuletzt = scalar(c, "SELECT COUNT(*) FROM referrals WHERE created_by = :u AND "
                            "created_at > :t", u=user["id"], t=_vor(days=30)) or 0
        if zuletzt >= JE_MITGLIED_30_TAGE:
            raise HTTPException(429, "Für diesen Monat sind genug Einladungen "
                                     "unterwegs.")
        x = schutz.index(email)
        if row(c, "SELECT id FROM referrals WHERE created_by = :u AND email_idx = :x "
                  "AND used_at IS NULL AND revoked_at IS NULL AND expires_at > :t",
               u=user["id"], x=x, t=now_iso()):
            raise HTTPException(409, "An diese Adresse ist schon eine Einladung von dir "
                                     "unterwegs.")
        absender = row(c, "SELECT first_name, last_name FROM user_profile WHERE "
                          "user_id = :u", u=user["id"]) or {}
        von = " ".join(v_ for v_ in (absender.get("first_name"),
                                     absender.get("last_name")) if v_) or "Ein Mitglied"
        konto = row(c, "SELECT id FROM users WHERE email_idx = :x", x=x)
        code = secrets.token_urlsafe(24)
        rid = new_id()
        q(c, "INSERT INTO referrals (id, code_hash, email, email_idx, name, created_by, "
             "created_at, expires_at) VALUES (:i, :h, :e, :x, :n, :u, :t, :b)",
          i=rid, h=token_hash(code), e=schutz.v(email), x=x, n=schutz.v(name or None),
          u=user["id"], t=now_iso(),
          b=(datetime.now(timezone.utc) + timedelta(days=EMPFEHLUNG_TAGE)).replace(
              microsecond=0).isoformat())
        audit(c, user["id"], "referrals", rid, "create")
    # Gibt es zu der Adresse schon ein Konto, geht keine Einladung raus. Das
    # Mitglied erfährt davon nichts: es sieht sonst, wer hier ein Konto hat.
    if not konto:
        mailer.send(email, f"SCOPE X: {von} lädt dich ein", f"""\
{"Hallo " + name + "," if name else "Hallo,"}

{von} lädt dich zu SCOPE X ein, dem Kompetenzlogbuch und Fachnetzwerk für
die Notfallversorgung.

Über diesen Link bewirbst du dich um Zugang. {von} ist dabei schon als
Kontakt eingetragen; über die Aufnahme entscheidet die Administration:

{mailer.link("#/bewerben?empfehlung=" + code)}

Was SCOPE X ist: {mailer.link("#/ueber")}

Der Link gilt {EMPFEHLUNG_TAGE} Tage. Möchtest du nicht, ignoriere diese
Nachricht; es wird nichts gespeichert, was über diese Einladung hinausgeht.
""")
    with conn() as c:
        return {"ok": True, "empfehlungen": _empfehlungen(c, user["id"])}


@router.delete("/api/netz/empfehlungen/{rid}")
def empfehlung_zurueckziehen(rid: str, user=Depends(current_user)):
    with conn() as c:
        r_ = row(c, "SELECT * FROM referrals WHERE id = :i AND created_by = :u",
                 i=rid, u=user["id"])
        if not r_:
            raise HTTPException(404, "Einladung nicht gefunden.")
        if not r_["used_at"] and not r_["revoked_at"]:
            q(c, "UPDATE referrals SET revoked_at = :t WHERE id = :i", t=now_iso(), i=rid)
        return {"empfehlungen": _empfehlungen(c, user["id"])}


@router.get("/api/oeffentlich/empfehlung/{code}")
def empfehlung_pruefen(code: str):
    """Für das Bewerbungsformular: wer empfiehlt, an welche Adresse. Wer den
    Code hat, ist die eingeladene Person; mehr als diese Angaben gibt es
    nicht."""
    with conn() as c:
        r_ = _empfehlung(c, code[:80])
        if not r_:
            raise HTTPException(404, "Diese Einladung ist abgelaufen oder wurde schon "
                                     "verwendet.")
        p = row(c, "SELECT first_name, last_name FROM user_profile WHERE user_id = :u",
                u=r_["created_by"]) or {}
    return {"von": " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x)
            or "Ein Mitglied", "email": r_["email"], "name": r_["name"] or ""}
