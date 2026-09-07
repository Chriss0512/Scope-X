"""Anmeldung und Zwei-Faktor-Authentifizierung."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .. import mailer
from ..core import ROLE_LABELS, audit, current_user, optional_user
from ..db import conn, new_id, now_iso, q, row, rows, scalar
from ..security import (
    DEVICE_COOKIE, DEVICE_DAYS, SESSION_COOKIE, SESSION_DAYS,
    consume_recovery_code, create_session, create_trusted_device,
    forget_all_devices, forget_device, hash_ip, needs_rehash, token_hash,
    trusted_device_valid,
    destroy_all_sessions, destroy_session, generate_recovery_codes,
    hash_password, new_totp_secret, password_problems, qr_svg,
    store_recovery_codes, totp_uri, verify_password, verify_totp,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

MAX_FAILED = 8
LOCKOUT_MINUTES = 15


def _norm(value: str | None) -> str:
    """Anmeldemerkmale werden in Kleinschreibung verglichen. Sonst scheitert
    die Anmeldung an der Autokorrektur des Telefons, die den ersten
    Buchstaben groß schreibt."""
    return (value or "").strip().lower()


def find_login(c, identifier: str) -> dict | None:
    """Sucht ein Konto über Benutzername oder E-Mail-Adresse."""
    return row(c, "SELECT * FROM users WHERE LOWER(username) = :n "
                  "OR LOWER(email) = :n", n=_norm(identifier))


def _is_secure(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    return (proto or request.url.scheme) == "https"


def _set_device_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        DEVICE_COOKIE, token, max_age=DEVICE_DAYS * 86400, httponly=True,
        samesite="lax", secure=_is_secure(request), path="/")


def _set_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token,
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=_is_secure(request),
        path="/",
    )


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: str | None = None
    password: str
    first_name: str = ""
    last_name: str = ""
    qualification: str = ""
    invite_code: str | None = None


def _find_invitation(c, code: str | None) -> dict | None:
    if not code:
        return None
    inv = row(c, "SELECT * FROM invitations WHERE code_hash = :h",
              h=token_hash(code.strip().upper()))
    if not inv or inv["used_at"] or inv["revoked_at"]:
        return None
    if inv["expires_at"] < now_iso():
        return None
    return inv


class LoginIn(BaseModel):
    username: str  # Benutzername oder E-Mail-Adresse
    password: str
    totp_code: str | None = None
    recovery_code: str | None = None
    remember_device: bool = False


class CodeIn(BaseModel):
    code: str


@router.get("/invitation/{code}")
def check_invitation(code: str):
    """Prueft einen Einladungscode, bevor das Formular ausgefuellt wird.

    Gibt bewusst nur gueltig oder nicht gueltig zurueck, keine Angaben zur
    einladenden Person oder zum Bestand.
    """
    with conn() as c:
        inv = _find_invitation(c, code)
    if not inv:
        raise HTTPException(404, "Diese Einladung ist ungültig oder abgelaufen.")
    return {"valid": True, "role": inv["role"],
            "role_label": ROLE_LABELS.get(inv["role"], inv["role"]),
            "email": inv["email"] or ""}


@router.get("/state")
def auth_state(request: Request):
    with conn() as c:
        user_count = scalar(c, "SELECT COUNT(*) FROM users") or 0
    user = optional_user(request)
    if not user:
        return {"setup_required": user_count == 0, "authenticated": False}
    with conn() as c:
        totp = row(c, "SELECT confirmed_at FROM auth_totp WHERE user_id = :u", u=user["id"])
        profile = row(c, "SELECT * FROM user_profile WHERE user_id = :u", u=user["id"])
    # Bewusst nur die Felder, die die Oberflaeche wirklich braucht. Der
    # Passwort-Hash und andere interne Spalten verlassen den Server nicht.
    return {
        "setup_required": False,
        "authenticated": True,
        "totp_confirmed": bool(totp and totp["confirmed_at"]),
        "user": {"id": user["id"], "username": user["username"],
                 "email": user["email"], "role": user.get("role") or "user"},
        "profile": profile or {},
        "mail_configured": mailer.is_configured(),
    }


@router.post("/register")
def register(data: RegisterIn, request: Request, response: Response):
    problems = password_problems(data.password)
    if problems:
        raise HTTPException(400, " ".join(problems))
    with conn() as c:
        existing_accounts = scalar(c, "SELECT COUNT(*) FROM users") or 0
        invitation = None
        role = "admin"
        if existing_accounts:
            # Ab dem zweiten Konto ist eine gueltige Einladung Pflicht. Das
            # ersetzt ein Captcha wirksamer, als ein Captcha es koennte:
            # ohne Code kommt niemand ueberhaupt bis zum Formular.
            invitation = _find_invitation(c, data.invite_code)
            if not invitation:
                raise HTTPException(
                    403, "Für die Registrierung ist eine gültige Einladung nötig.")
            role = invitation["role"]
        email = _norm(data.email) or None
        if email and "@" not in email:
            raise HTTPException(400, "Die E-Mail-Adresse sieht nicht gültig aus.")
        if find_login(c, data.username):
            raise HTTPException(409, "Dieser Benutzername ist bereits vergeben.")
        if email and find_login(c, email):
            raise HTTPException(409, "Diese E-Mail-Adresse ist bereits vergeben.")
        uid = new_id()
        q(c, "INSERT INTO users (id, username, email, password_hash, created_at, "
             "failed_logins, role, invited_by) "
             "VALUES (:i, :n, :e, :p, :t, 0, :r, :ib)",
          i=uid, n=data.username.strip(), e=email,
          p=hash_password(data.password), t=now_iso(), r=role,
          ib=invitation["created_by"] if invitation else None)
        if invitation:
            q(c, "UPDATE invitations SET used_at = :t, used_by = :u WHERE id = :i",
              t=now_iso(), u=uid, i=invitation["id"])
        q(c, "INSERT INTO user_profile (user_id, first_name, last_name, "
             "qualification, created_at) VALUES (:u, :f, :l, :q, :t)",
          u=uid, f=data.first_name.strip(), l=data.last_name.strip(),
          q=data.qualification.strip(), t=now_iso())
        secret = new_totp_secret()
        q(c, "INSERT INTO auth_totp (user_id, secret, created_at) "
             "VALUES (:u, :s, :t)", u=uid, s=secret, t=now_iso())
        audit(c, uid, "users", uid, "create")
    token = create_session(uid)
    _set_cookie(response, request, token)
    account = data.email or data.username
    return {"ok": True, "totp": {
        "secret": secret,
        "uri": totp_uri(secret, account),
        "qr_svg": qr_svg(totp_uri(secret, account)),
    }}


@router.get("/totp/setup")
def totp_setup(request: Request):
    """Liefert QR-Code und Secret erneut, solange die Einrichtung nicht
    bestaetigt ist. Nach der Bestaetigung wird das Secret nie wieder
    ausgegeben."""
    user = current_user(request)
    with conn() as c:
        t = row(c, "SELECT * FROM auth_totp WHERE user_id = :u", u=user["id"])
        if not t:
            secret = new_totp_secret()
            q(c, "INSERT INTO auth_totp (user_id, secret, created_at) "
                 "VALUES (:u, :s, :t)", u=user["id"], s=secret, t=now_iso())
            t = {"secret": secret, "confirmed_at": None}
    if t["confirmed_at"]:
        raise HTTPException(409, "Die Zwei-Faktor-Authentifizierung ist bereits aktiv.")
    account = user["email"] or user["username"]
    return {"secret": t["secret"], "uri": totp_uri(t["secret"], account),
            "qr_svg": qr_svg(totp_uri(t["secret"], account))}


@router.post("/totp/confirm")
def totp_confirm(data: CodeIn, request: Request):
    user = current_user(request)
    with conn() as c:
        t = row(c, "SELECT * FROM auth_totp WHERE user_id = :u", u=user["id"])
        if not t:
            raise HTTPException(400, "Keine Einrichtung begonnen.")
        if t["confirmed_at"]:
            raise HTTPException(409, "Bereits bestätigt.")
        if not verify_totp(t["secret"], data.code):
            raise HTTPException(400, "Der Code stimmt nicht. Prüfe die Uhrzeit des Geräts.")
        q(c, "UPDATE auth_totp SET confirmed_at = :t WHERE user_id = :u",
          t=now_iso(), u=user["id"])
        codes = generate_recovery_codes()
        store_recovery_codes(c, user["id"], codes)
        audit(c, user["id"], "auth_totp", user["id"], "confirm")
    return {"ok": True, "recovery_codes": codes}


@router.post("/recovery/regenerate")
def regenerate_recovery(data: CodeIn, request: Request):
    """Neue Codes erfordern einen frischen TOTP-Code. Alte Codes werden
    dabei ungueltig."""
    user = current_user(request)
    with conn() as c:
        t = row(c, "SELECT * FROM auth_totp WHERE user_id = :u", u=user["id"])
        if not (t and t["confirmed_at"] and verify_totp(t["secret"], data.code)):
            raise HTTPException(400, "Ungültiger Code.")
        codes = generate_recovery_codes()
        store_recovery_codes(c, user["id"], codes)
        audit(c, user["id"], "recovery_codes", user["id"], "regenerate")
    return {"recovery_codes": codes}


@router.get("/recovery/status")
def recovery_status(request: Request):
    user = current_user(request)
    with conn() as c:
        total = scalar(c, "SELECT COUNT(*) FROM recovery_codes WHERE user_id = :u",
                       u=user["id"]) or 0
        unused = scalar(c, "SELECT COUNT(*) FROM recovery_codes "
                           "WHERE user_id = :u AND used_at IS NULL", u=user["id"]) or 0
    return {"total": total, "unused": unused}


@router.post("/login")
def login(data: LoginIn, request: Request, response: Response):
    with conn() as c:
        user = find_login(c, data.username)
        if not user:
            raise HTTPException(401, "Benutzername, Passwort oder Code stimmt nicht.")
        if user["lock_until"] and user["lock_until"] > now_iso():
            raise HTTPException(429, "Zu viele Fehlversuche. Später erneut versuchen.")

        if user.get("disabled_at"):
            raise HTTPException(403, "Dieses Konto ist gesperrt.")

        ok = verify_password(data.password, user["password_hash"])
        totp = row(c, "SELECT * FROM auth_totp WHERE user_id = :u", u=user["id"])

        # Ein bekanntes Geraet erspart den Code bei der Anmeldung. Es hebt
        # die Zwei-Faktor-Pflicht nicht auf: Eingriffe in Konten und Daten
        # verlangen weiterhin einen frischen Code.
        device_token = request.cookies.get(DEVICE_COOKIE)
        device_known = ok and trusted_device_valid(user["id"], device_token)

        if ok and totp and totp["confirmed_at"] and not device_known:
            if data.recovery_code:
                ok = consume_recovery_code(c, user["id"], data.recovery_code)
            else:
                ok = verify_totp(totp["secret"], data.totp_code or "")

        if not ok:
            failed = (user["failed_logins"] or 0) + 1
            lock_until = None
            if failed >= MAX_FAILED:
                lock_until = (datetime.now(timezone.utc)
                              + timedelta(minutes=LOCKOUT_MINUTES)
                              ).replace(microsecond=0).isoformat()
                failed = 0
            q(c, "UPDATE users SET failed_logins = :f, lock_until = :l WHERE id = :i",
              f=failed, l=lock_until, i=user["id"])
            audit(c, user["id"], "users", user["id"], "login_failed")
            raise HTTPException(401, "Benutzername, Passwort oder Code stimmt nicht.")

        # Bestehende scrypt-Hashes werden hier still auf Argon2id gehoben.
        if needs_rehash(user["password_hash"]):
            q(c, "UPDATE users SET password_hash = :p WHERE id = :i",
              p=hash_password(data.password), i=user["id"])
            audit(c, user["id"], "users", user["id"], "password_rehash")

        q(c, "UPDATE users SET failed_logins = 0, lock_until = NULL, "
             "last_login_at = :t WHERE id = :i", t=now_iso(), i=user["id"])
        audit(c, user["id"], "users", user["id"], "login")
        totp_confirmed = bool(totp and totp["confirmed_at"])

    token = create_session(user["id"])
    _set_cookie(response, request, token)
    if data.remember_device and totp_confirmed and not device_known:
        label = (request.headers.get("user-agent") or "")[:80]
        _set_device_cookie(response, request,
                           create_trusted_device(user["id"], label))
    return {"ok": True, "totp_confirmed": totp_confirmed,
            "device_known": device_known}


@router.post("/logout")
def logout(request: Request, response: Response, forget: bool = False):
    destroy_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/")
    if forget:
        forget_device(request.cookies.get(DEVICE_COOKIE))
        response.delete_cookie(DEVICE_COOKIE, path="/")
    return {"ok": True}


@router.get("/devices")
def list_devices(request: Request):
    user = current_user(request)
    current = token_hash(request.cookies.get(DEVICE_COOKIE) or "")
    with conn() as c:
        items = rows(c, "SELECT id, label, created_at, expires_at, "
                        "last_used_at, token_hash FROM trusted_devices "
                        "WHERE user_id = :u ORDER BY last_used_at DESC",
                     u=user["id"])
    for d in items:
        d["current"] = d.pop("token_hash") == current
    return {"devices": items}


@router.delete("/devices")
def revoke_devices(request: Request, response: Response):
    """Entzieht allen Geräten das Vertrauen. Danach ist überall wieder ein
    Code aus der Authenticator-App nötig."""
    user = current_user(request)
    forget_all_devices(user["id"])
    response.delete_cookie(DEVICE_COOKIE, path="/")
    with conn() as c:
        audit(c, user["id"], "trusted_devices", user["id"], "revoke_all")
    return {"ok": True}


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str
    totp_code: str


@router.post("/password")
def change_password(data: PasswordChangeIn, request: Request):
    user = current_user(request)
    problems = password_problems(data.new_password)
    if problems:
        raise HTTPException(400, " ".join(problems))
    with conn() as c:
        if not verify_password(data.current_password, user["password_hash"]):
            raise HTTPException(400, "Aktuelles Passwort stimmt nicht.")
        t = row(c, "SELECT * FROM auth_totp WHERE user_id = :u", u=user["id"])
        if t and t["confirmed_at"] and not verify_totp(t["secret"], data.totp_code):
            raise HTTPException(400, "Ungültiger Code.")
        q(c, "UPDATE users SET password_hash = :p WHERE id = :i",
          p=hash_password(data.new_password), i=user["id"])
        audit(c, user["id"], "users", user["id"], "password_change")
    destroy_all_sessions(user["id"])
    forget_all_devices(user["id"])
    return {"ok": True}


class EmailChangeIn(BaseModel):
    email: str
    password: str
    totp_code: str


@router.put("/email")
def change_email(data: EmailChangeIn, request: Request):
    """Ändert die E-Mail-Adresse.

    Sie ist ein Anmeldemerkmal, deshalb gilt hier dieselbe Hürde wie beim
    Passwortwechsel: aktuelles Passwort plus ein frischer Code.
    """
    user = current_user(request)
    email = _norm(data.email)
    if email and "@" not in email:
        raise HTTPException(400, "Die E-Mail-Adresse sieht nicht gültig aus.")
    with conn() as c:
        if not verify_password(data.password, user["password_hash"]):
            raise HTTPException(400, "Passwort stimmt nicht.")
        t = row(c, "SELECT * FROM auth_totp WHERE user_id = :u", u=user["id"])
        if t and t["confirmed_at"] and not verify_totp(t["secret"], data.totp_code):
            raise HTTPException(400, "Ungültiger Code.")
        existing = find_login(c, email) if email else None
        if existing and existing["id"] != user["id"]:
            raise HTTPException(409, "Diese Adresse gehört bereits zu einem Konto.")
        q(c, "UPDATE users SET email = :e WHERE id = :i",
          e=email or None, i=user["id"])
        audit(c, user["id"], "users", user["id"], "email_change")
    return {"ok": True, "email": email or None}


# --------------------------------------------------------------------------
# Passwort zurücksetzen
# --------------------------------------------------------------------------
# Der Link allein reicht nicht. Zum Setzen eines neuen Passworts ist
# zusätzlich der zweite Faktor nötig, sonst wäre ein Zugriff auf das
# Postfach gleichbedeutend mit einer Kontoübernahme.

RESET_MINUTES = 30


class ResetRequestIn(BaseModel):
    identifier: str


class ResetConfirmIn(BaseModel):
    token: str
    new_password: str
    totp_code: str | None = None
    recovery_code: str | None = None


@router.post("/password-reset/request")
def request_reset(data: ResetRequestIn, request: Request):
    """Fordert einen Reset-Link an.

    Antwortet immer gleich, unabhängig davon, ob es das Konto gibt. Sonst
    ließe sich über dieses Formular herausfinden, welche Adressen registriert
    sind.
    """
    ip_hash = hash_ip(request.client.host if request.client else None)
    with conn() as c:
        user = find_login(c, data.identifier)
        if user and user["email"] and not user.get("disabled_at"):
            recent = scalar(c, "SELECT COUNT(*) FROM password_resets "
                               "WHERE user_id = :u AND created_at > :t",
                            u=user["id"],
                            t=(datetime.now(timezone.utc)
                               - timedelta(minutes=10))
                              .replace(microsecond=0).isoformat()) or 0
            if recent < 3:
                token = secrets.token_urlsafe(32)
                expires = (datetime.now(timezone.utc)
                           + timedelta(minutes=RESET_MINUTES))
                q(c, "INSERT INTO password_resets (id, user_id, token_hash, "
                     "created_at, expires_at, requested_ip_hash) "
                     "VALUES (:i, :u, :h, :c, :e, :ip)",
                  i=new_id(), u=user["id"], h=token_hash(token),
                  c=now_iso(), e=expires.replace(microsecond=0).isoformat(),
                  ip=ip_hash)
                audit(c, user["id"], "password_resets", user["id"], "request")
                mailer.send_reset(user["email"], token)
    return {"ok": True, "detail": "Wenn ein Konto existiert, ist eine "
                                  "Nachricht unterwegs."}


@router.post("/password-reset/confirm")
def confirm_reset(data: ResetConfirmIn, request: Request):
    problems = password_problems(data.new_password)
    if problems:
        raise HTTPException(400, " ".join(problems))
    with conn() as c:
        rec = row(c, "SELECT * FROM password_resets WHERE token_hash = :h",
                  h=token_hash(data.token))
        if not rec or rec["used_at"] or rec["expires_at"] < now_iso():
            raise HTTPException(400, "Dieser Link ist ungültig oder abgelaufen.")
        user = row(c, "SELECT * FROM users WHERE id = :u", u=rec["user_id"])
        if not user or user.get("disabled_at"):
            raise HTTPException(400, "Dieser Link ist ungültig oder abgelaufen.")

        t = row(c, "SELECT * FROM auth_totp WHERE user_id = :u", u=user["id"])
        if t and t["confirmed_at"]:
            if data.recovery_code:
                second = consume_recovery_code(c, user["id"], data.recovery_code)
            else:
                second = verify_totp(t["secret"], data.totp_code or "")
            if not second:
                raise HTTPException(
                    400, "Zusätzlich ist ein Code aus deiner Authenticator-App "
                         "oder ein Wiederherstellungscode nötig.")

        q(c, "UPDATE users SET password_hash = :p, failed_logins = 0, "
             "lock_until = NULL WHERE id = :i",
          p=hash_password(data.new_password), i=user["id"])
        q(c, "UPDATE password_resets SET used_at = :t WHERE id = :i",
          t=now_iso(), i=rec["id"])
        q(c, "UPDATE password_resets SET used_at = :t "
             "WHERE user_id = :u AND used_at IS NULL",
          t=now_iso(), u=user["id"])
        audit(c, user["id"], "users", user["id"], "password_reset")

    # Nach einer Zurücksetzung gilt kein Gerät mehr als vertrauenswürdig.
    destroy_all_sessions(user["id"])
    forget_all_devices(user["id"])
    return {"ok": True}
