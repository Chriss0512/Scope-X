"""Administration: Konten, Rollen, Einladungen.

Jede Route hier prüft die Rolle serverseitig und verlangt zusätzlich einen
frischen Code aus der Authenticator-App, sobald sie fremde Konten berührt.
Ein Vertrauensgerät hilft dabei ausdrücklich nicht.

Es gibt keinen versteckten Zugang, keinen Testendpunkt und keine Route, die
ohne Anmeldung Kontodaten liefert.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import mailer
from ..core import (
    ROLE_LABELS,
    ROLES,
    audit,
    fresh_totp_required,
    get_setting,
    require_admin,
    set_setting,
)
from ..db import conn, new_id, now_iso, q, row, rows, scalar
from ..security import (
    destroy_all_sessions,
    forget_all_devices,
    token_hash,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Ohne I, O, 0 und 1, damit ein am Telefon vorgelesener Code ankommt.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _new_code() -> str:
    raw = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(16))
    return f"{raw[0:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:16]}"


def _public_user(u: dict) -> dict:
    """Nur die Felder, die die Oberfläche braucht. Passwort-Hash, TOTP-Secret
    und interne Spalten verlassen den Server nicht."""
    return {
        "id": u["id"],
        "username": u["username"],
        "email": u["email"],
        "role": u.get("role") or "user",
        "role_label": ROLE_LABELS.get(u.get("role") or "user", "Mitarbeiter"),
        "created_at": u["created_at"],
        "last_login_at": u["last_login_at"],
        "disabled": bool(u.get("disabled_at")),
        "locked_out": bool(u["lock_until"] and u["lock_until"] > now_iso()),
    }


# --------------------------------------------------------------------------
# Konten
# --------------------------------------------------------------------------

@router.get("/users")
def list_users(user=Depends(require_admin)):
    with conn() as c:
        items = rows(c, "SELECT u.*, p.first_name, p.last_name, p.qualification "
                        "FROM users u LEFT JOIN user_profile p "
                        "ON p.user_id = u.id ORDER BY u.created_at")
        result = []
        for u in items:
            entry = _public_user(u)
            entry["name"] = " ".join(
                x for x in [u.get("first_name"), u.get("last_name")] if x).strip()
            entry["qualification"] = u.get("qualification") or ""
            entry["encounters"] = scalar(
                c, "SELECT COUNT(*) FROM encounters WHERE user_id = :u "
                   "AND deleted_at IS NULL", u=u["id"]) or 0
            entry["totp_active"] = bool(row(
                c, "SELECT confirmed_at FROM auth_totp WHERE user_id = :u "
                   "AND confirmed_at IS NOT NULL", u=u["id"]))
            result.append(entry)
    return {"users": result, "roles": [
        {"key": r, "label": ROLE_LABELS[r]} for r in ROLES]}


class UserPatch(BaseModel):
    role: str | None = None
    disabled: bool | None = None
    totp_code: str


@router.patch("/users/{user_id}")
def update_user(user_id: str, data: UserPatch, admin=Depends(require_admin)):
    fresh_totp_required(admin, data.totp_code)
    if data.role is not None and data.role not in ROLES:
        raise HTTPException(400, "Unbekannte Rolle.")
    with conn() as c:
        target = row(c, "SELECT * FROM users WHERE id = :i", i=user_id)
        if not target:
            raise HTTPException(404, "Konto nicht gefunden.")

        # Es muss immer mindestens ein aktiver Administrator übrig bleiben,
        # sonst sperrt sich die Installation selbst aus.
        admins = scalar(c, "SELECT COUNT(*) FROM users WHERE role = 'admin' "
                           "AND disabled_at IS NULL") or 0
        losing_admin = (target.get("role") == "admin"
                        and not target.get("disabled_at")
                        and (data.role not in (None, "admin")
                             or data.disabled is True))
        if losing_admin and admins <= 1:
            raise HTTPException(
                409, "Das ist der letzte aktive Administrator. Ernenne zuerst "
                     "einen weiteren, bevor du diesen änderst.")

        if data.role is not None and data.role != target.get("role"):
            q(c, "UPDATE users SET role = :r WHERE id = :i", r=data.role, i=user_id)
            audit(c, admin["id"], "users", user_id, "role_change", "role",
                  target.get("role"), data.role)
        if data.disabled is not None:
            stamp = now_iso() if data.disabled else None
            if bool(target.get("disabled_at")) != data.disabled:
                q(c, "UPDATE users SET disabled_at = :d WHERE id = :i",
                  d=stamp, i=user_id)
                audit(c, admin["id"], "users", user_id,
                      "disable" if data.disabled else "enable")
        updated = row(c, "SELECT * FROM users WHERE id = :i", i=user_id)

    if data.disabled:
        # Ein gesperrtes Konto verliert sofort alle offenen Sitzungen.
        destroy_all_sessions(user_id)
        forget_all_devices(user_id)
    return _public_user(updated)


class ResetForUserIn(BaseModel):
    totp_code: str


@router.post("/users/{user_id}/password-reset")
def admin_reset(user_id: str, data: ResetForUserIn, admin=Depends(require_admin)):
    """Erzeugt einen einmaligen Reset-Link für ein anderes Konto.

    Der Administrator setzt kein Passwort selbst, sondern stößt denselben
    Ablauf an, den auch die Person selbst auslösen könnte. Der zweite Faktor
    des Kontos bleibt damit zwingend, ein Administrator kann sich also nicht
    einfach in ein fremdes Konto einloggen.
    """
    fresh_totp_required(admin, data.totp_code)
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(minutes=30)
    with conn() as c:
        target = row(c, "SELECT * FROM users WHERE id = :i", i=user_id)
        if not target:
            raise HTTPException(404, "Konto nicht gefunden.")
        q(c, "INSERT INTO password_resets (id, user_id, token_hash, "
             "created_at, expires_at) VALUES (:i, :u, :h, :c, :e)",
          i=new_id(), u=user_id, h=token_hash(token), c=now_iso(),
          e=expires.replace(microsecond=0).isoformat())
        audit(c, admin["id"], "password_resets", user_id, "admin_request")
    sent = mailer.send_reset(target["email"], token) if target["email"] else False
    return {
        "ok": True, "sent": sent,
        # Ohne Mailversand muss der Link von Hand weitergegeben werden.
        # Er wird genau einmal angezeigt.
        "link": None if sent else mailer.link(f"#/passwort-neu?token={token}"),
        "expires_in_minutes": 30,
    }


# --------------------------------------------------------------------------
# Einladungen
# --------------------------------------------------------------------------

class InvitationIn(BaseModel):
    email: str | None = None
    role: str = "user"
    note: str | None = None
    valid_days: int = Field(default=7, ge=1, le=90)
    totp_code: str


@router.post("/invitations")
def create_invitation(data: InvitationIn, admin=Depends(require_admin)):
    fresh_totp_required(admin, data.totp_code)
    if data.role not in ROLES:
        raise HTTPException(400, "Unbekannte Rolle.")
    email = (data.email or "").strip().lower() or None
    if email and "@" not in email:
        raise HTTPException(400, "Die E-Mail-Adresse sieht nicht gültig aus.")

    code = _new_code()
    expires = datetime.now(timezone.utc) + timedelta(days=data.valid_days)
    with conn() as c:
        if email and row(c, "SELECT id FROM users WHERE email = :e", e=email):
            raise HTTPException(409, "Zu dieser Adresse gibt es bereits ein Konto.")
        iid = new_id()
        q(c, "INSERT INTO invitations (id, code_hash, email, role, note, "
             "created_by, created_at, expires_at) "
             "VALUES (:i, :h, :e, :r, :n, :cb, :c, :x)",
          i=iid, h=token_hash(code), e=email, r=data.role,
          n=(data.note or "").strip()[:200] or None, cb=admin["id"],
          c=now_iso(), x=expires.replace(microsecond=0).isoformat())
        audit(c, admin["id"], "invitations", iid, "create", "role", None, data.role)

    sent = mailer.send_invitation(email, code, ROLE_LABELS[data.role],
                                  data.valid_days) if email else False
    # Der Code wird nur hier einmal im Klartext ausgegeben. In der Datenbank
    # steht ausschließlich sein Hash.
    return {"id": iid, "code": code, "sent": sent,
            "link": mailer.link(f"#/registrieren?code={code}"),
            "expires_at": expires.replace(microsecond=0).isoformat()}


@router.get("/invitations")
def list_invitations(admin=Depends(require_admin)):
    with conn() as c:
        items = rows(c, "SELECT id, email, role, note, created_at, expires_at, "
                        "used_at, used_by, revoked_at FROM invitations "
                        "ORDER BY created_at DESC LIMIT 100")
    for i in items:
        i["role_label"] = ROLE_LABELS.get(i["role"], i["role"])
        i["status"] = ("verwendet" if i["used_at"] else
                       "zurückgezogen" if i["revoked_at"] else
                       "abgelaufen" if i["expires_at"] < now_iso() else "offen")
    return {"invitations": items}


@router.post("/invitations/{invitation_id}/revoke")
def revoke_invitation(invitation_id: str, admin=Depends(require_admin)):
    with conn() as c:
        inv = row(c, "SELECT * FROM invitations WHERE id = :i", i=invitation_id)
        if not inv:
            raise HTTPException(404, "Einladung nicht gefunden.")
        if inv["used_at"]:
            raise HTTPException(409, "Diese Einladung wurde bereits eingelöst.")
        q(c, "UPDATE invitations SET revoked_at = :t WHERE id = :i",
          t=now_iso(), i=invitation_id)
        audit(c, admin["id"], "invitations", invitation_id, "revoke")
    return {"ok": True}


# --------------------------------------------------------------------------
# Betrieb
# --------------------------------------------------------------------------

@router.get("/status")
def status(admin=Depends(require_admin)):
    with conn() as c:
        return {
            "mail_configured": mailer.is_configured(),
            "mail_host": mailer.config()["host"] or None,
            "base_url": mailer.config()["base_url"] or None,
            "idle_timeout_minutes": int(
                get_setting(c, "idle_timeout_minutes", "30")),
            "users": scalar(c, "SELECT COUNT(*) FROM users") or 0,
            "open_invitations": scalar(
                c, "SELECT COUNT(*) FROM invitations WHERE used_at IS NULL "
                   "AND revoked_at IS NULL AND expires_at > :t",
                t=now_iso()) or 0,
        }


class OperationsIn(BaseModel):
    idle_timeout_minutes: int | None = Field(default=None, ge=1, le=1440)


@router.put("/status")
def update_status(data: OperationsIn, admin=Depends(require_admin)):
    with conn() as c:
        if data.idle_timeout_minutes is not None:
            old = get_setting(c, "idle_timeout_minutes", "30")
            set_setting(c, "idle_timeout_minutes", str(data.idle_timeout_minutes))
            audit(c, admin["id"], "settings", "idle_timeout_minutes", "update",
                  "idle_timeout_minutes", old, data.idle_timeout_minutes)
    return status(admin)
