"""Passkeys (WebAuthn).

Ein Passkey ersetzt Passwort und TOTP-Code in einem Schritt: der private
Schlüssel verlässt das Gerät nie, entsperrt wird er über Face ID, Touch ID,
Windows Hello oder die Geräte-PIN. Damit ist die Anmeldung
phishing-resistent, weil der Schlüssel an die Domain gebunden ist und auf
einer nachgebauten Seite gar nicht erst antwortet.

Die kryptografische Prüfung übernimmt py_webauthn. Signaturprüfung,
CBOR-Auswertung und Attestation selbst zu schreiben wäre genau die Art von
Sicherheitscode, die man nicht selbst schreibt.

Ohne HTTPS funktioniert WebAuthn nicht, ausgenommen localhost. Über Nginx
Proxy Manager mit Zertifikat ist das erfüllt.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from ..core import audit, current_user
from ..db import conn, new_id, now_iso, q, row, rows
from ..security import SESSION_COOKIE, create_session

router = APIRouter(prefix="/api/auth/passkeys", tags=["passkeys"])

CHALLENGE_MINUTES = 5


def relying_party() -> tuple[str, str, str]:
    """Ermittelt Domain und Ursprung aus der Add-on-Konfiguration.

    WebAuthn bindet jeden Schlüssel an genau diese Domain. Ist keine
    Basis-Adresse hinterlegt, sind Passkeys nicht nutzbar; ein geratener
    Wert würde Schlüssel erzeugen, die sich später nicht mehr verwenden
    lassen.
    """
    base = os.environ.get("SCOPEX_BASE_URL", "").strip().rstrip("/")
    if not base:
        raise HTTPException(
            503, "Für Passkeys muss in der Add-on-Konfiguration eine "
                 "Basis-Adresse hinterlegt sein.")
    parsed = urlparse(base)
    if parsed.scheme != "https" and parsed.hostname not in ("localhost", "127.0.0.1"):
        raise HTTPException(
            503, "Passkeys setzen HTTPS voraus. Richte im Reverse Proxy ein "
                 "Zertifikat ein.")
    return parsed.hostname, base, "SCOPE X"


def _store_challenge(user_id: str | None, kind: str, challenge: bytes,
                     handle: str) -> None:
    expires = datetime.now(timezone.utc) + timedelta(minutes=CHALLENGE_MINUTES)
    with conn() as c:
        q(c, "DELETE FROM webauthn_challenges WHERE expires_at < :t", t=now_iso())
        q(c, "INSERT INTO webauthn_challenges (id, user_id, kind, challenge, "
             "handle, created_at, expires_at) "
             "VALUES (:i, :u, :k, :ch, :h, :c, :e)",
          i=new_id(), u=user_id, k=kind, ch=challenge.hex(), h=handle,
          c=now_iso(), e=expires.replace(microsecond=0).isoformat())


def _take_challenge(kind: str, handle: str) -> dict:
    with conn() as c:
        rec = row(c, "SELECT * FROM webauthn_challenges WHERE handle = :h "
                     "AND kind = :k", h=handle, k=kind)
        if not rec or rec["expires_at"] < now_iso():
            raise HTTPException(400, "Der Vorgang ist abgelaufen. Bitte erneut "
                                     "versuchen.")
        # Eine Challenge gilt genau einmal.
        q(c, "DELETE FROM webauthn_challenges WHERE id = :i", i=rec["id"])
    return rec


# --------------------------------------------------------------------------
# Registrierung eines Passkeys
# --------------------------------------------------------------------------

@router.post("/register/options")
def register_options(request: Request):
    user = current_user(request)
    rp_id, _, rp_name = relying_party()
    with conn() as c:
        existing = rows(c, "SELECT credential_id FROM passkeys WHERE user_id = :u",
                        u=user["id"])
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=rp_name,
        user_id=user["id"].encode(),
        user_name=user["username"],
        user_display_name=user["username"],
        # Ein auffindbarer Schlüssel erlaubt die Anmeldung ohne vorherige
        # Eingabe des Benutzernamens.
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        # Bereits hinterlegte Schlüssel ausschließen, damit dasselbe Gerät
        # nicht doppelt registriert wird.
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(e["credential_id"]))
            for e in existing
        ],
    )
    handle = new_id()
    _store_challenge(user["id"], "register", options.challenge, handle)
    return {"handle": handle, "options": json.loads(options_to_json(options))}


class RegisterVerifyIn(BaseModel):
    handle: str
    credential: dict
    label: str | None = None


@router.post("/register/verify")
def register_verify(data: RegisterVerifyIn, request: Request):
    user = current_user(request)
    rp_id, origin, _ = relying_party()
    rec = _take_challenge("register", data.handle)
    if rec["user_id"] != user["id"]:
        raise HTTPException(400, "Der Vorgang gehört zu einem anderen Konto.")

    try:
        verified = verify_registration_response(
            credential=data.credential,
            expected_challenge=bytes.fromhex(rec["challenge"]),
            expected_origin=origin,
            expected_rp_id=rp_id,
            require_user_verification=True,
        )
    except Exception as exc:
        raise HTTPException(400, "Der Passkey konnte nicht geprüft werden.") from exc

    import base64
    cred_id = base64.urlsafe_b64encode(verified.credential_id).decode().rstrip("=")
    with conn() as c:
        if row(c, "SELECT id FROM passkeys WHERE credential_id = :c", c=cred_id):
            raise HTTPException(409, "Dieser Passkey ist bereits hinterlegt.")
        q(c, "INSERT INTO passkeys (id, user_id, credential_id, public_key, "
             "sign_count, label, created_at, last_used_at) "
             "VALUES (:i, :u, :c, :p, :s, :l, :t, NULL)",
          i=new_id(), u=user["id"], c=cred_id,
          p=verified.credential_public_key.hex(),
          s=verified.sign_count, l=(data.label or "Passkey")[:80], t=now_iso())
        audit(c, user["id"], "passkeys", cred_id[:16], "create")
    return {"ok": True}


# --------------------------------------------------------------------------
# Anmeldung mit Passkey
# --------------------------------------------------------------------------

@router.post("/login/options")
def login_options():
    """Erzeugt eine Aufforderung ohne Angabe des Kontos.

    Der Browser wählt den passenden Schlüssel selbst. Dadurch verrät dieser
    Endpunkt nicht, welche Konten existieren.
    """
    rp_id, _, _ = relying_party()
    options = generate_authentication_options(
        rp_id=rp_id,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    handle = new_id()
    _store_challenge(None, "login", options.challenge, handle)
    return {"handle": handle, "options": json.loads(options_to_json(options))}


class LoginVerifyIn(BaseModel):
    handle: str
    credential: dict


@router.post("/login/verify")
def login_verify(data: LoginVerifyIn, request: Request, response: Response):
    rp_id, origin, _ = relying_party()
    rec = _take_challenge("login", data.handle)
    cred_id = data.credential.get("id", "")

    with conn() as c:
        key = row(c, "SELECT * FROM passkeys WHERE credential_id = :c", c=cred_id)
        if not key:
            raise HTTPException(401, "Dieser Passkey ist hier nicht hinterlegt.")
        user = row(c, "SELECT * FROM users WHERE id = :u", u=key["user_id"])
    if not user or user.get("disabled_at"):
        raise HTTPException(403, "Dieses Konto ist gesperrt.")

    try:
        verified = verify_authentication_response(
            credential=data.credential,
            expected_challenge=bytes.fromhex(rec["challenge"]),
            expected_origin=origin,
            expected_rp_id=rp_id,
            credential_public_key=bytes.fromhex(key["public_key"]),
            credential_current_sign_count=key["sign_count"] or 0,
            require_user_verification=True,
        )
    except Exception as exc:
        raise HTTPException(401, "Die Anmeldung mit diesem Passkey ist "
                                 "fehlgeschlagen.") from exc

    with conn() as c:
        # Der Zähler erkennt geklonte Authentifikatoren: springt er nicht
        # nach oben, stimmt etwas nicht.
        q(c, "UPDATE passkeys SET sign_count = :s, last_used_at = :t "
             "WHERE id = :i", s=verified.new_sign_count, t=now_iso(), i=key["id"])
        q(c, "UPDATE users SET failed_logins = 0, lock_until = NULL, "
             "last_login_at = :t WHERE id = :i", t=now_iso(), i=user["id"])
        audit(c, user["id"], "users", user["id"], "login_passkey")

    token = create_session(user["id"])
    response.set_cookie(
        SESSION_COOKIE, token, max_age=14 * 86400, httponly=True,
        samesite="lax", path="/",
        secure=request.headers.get("x-forwarded-proto",
                                   request.url.scheme) == "https")
    return {"ok": True, "totp_confirmed": True}


# --------------------------------------------------------------------------
# Verwaltung
# --------------------------------------------------------------------------

@router.get("")
def list_passkeys(request: Request):
    user = current_user(request)
    with conn() as c:
        items = rows(c, "SELECT id, label, created_at, last_used_at "
                        "FROM passkeys WHERE user_id = :u ORDER BY created_at",
                     u=user["id"])
    return {"passkeys": items, "available": bool(os.environ.get("SCOPEX_BASE_URL"))}


@router.delete("/{passkey_id}")
def delete_passkey(passkey_id: str, request: Request):
    """Entfernt einen Passkey.

    Der letzte Passkey darf entfernt werden: Passwort und TOTP bleiben
    immer als Weg bestehen, ein Konto kann sich damit nicht aussperren.
    """
    user = current_user(request)
    with conn() as c:
        key = row(c, "SELECT * FROM passkeys WHERE id = :i AND user_id = :u",
                  i=passkey_id, u=user["id"])
        if not key:
            raise HTTPException(404, "Passkey nicht gefunden.")
        q(c, "DELETE FROM passkeys WHERE id = :i", i=passkey_id)
        audit(c, user["id"], "passkeys", key["credential_id"][:16], "delete")
    return {"ok": True}
