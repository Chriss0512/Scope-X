"""Passwoerter, TOTP, Sessions.

Keine externen Krypto-Abhaengigkeiten. scrypt und hmac kommen aus der
Standardbibliothek, TOTP ist nach RFC 6238 implementiert. Das haelt die
Angriffsflaeche klein und funktioniert garantiert offline.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from .db import conn, new_id, now_iso, q, row

# Argon2id ist seit Update 2 das Verfahren der Wahl. Bestehende
# scrypt-Hashes bleiben pruefbar und werden bei der naechsten erfolgreichen
# Anmeldung still auf Argon2id gehoben, ohne dass jemand sein Passwort
# aendern muss.
_SCRYPT_N = 2 ** 15
_SCRYPT_R = 8
_SCRYPT_P = 1
_DKLEN = 64
# OpenSSL begrenzt scrypt standardmaessig auf 32 MB. n=2**15 braucht mit
# r=8 genau 32 MB und wuerde daran scheitern, deshalb der explizite Wert.
_MAXMEM = 96 * 1024 * 1024

SESSION_COOKIE = "scopex_session"
SESSION_DAYS = 14


# --------------------------------------------------------------------------
# Passwoerter
# --------------------------------------------------------------------------

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import InvalidHashError, VerifyMismatchError
    from argon2.low_level import Type as _ArgonType

    _argon = PasswordHasher(
        time_cost=3, memory_cost=64 * 1024, parallelism=4,
        hash_len=32, salt_len=16, type=_ArgonType.ID,
    )
except ImportError:  # pragma: no cover - nur ohne installierte Abhaengigkeit
    _argon = None


def hash_password(password: str) -> str:
    if _argon is not None:
        return _argon.hash(password)
    return _hash_password_scrypt(password)


def needs_rehash(stored: str) -> bool:
    """Meldet Hashes, die auf das aktuelle Verfahren gehoben werden sollten."""
    if _argon is None:
        return False
    if not stored.startswith("$argon2"):
        return True
    try:
        return _argon.check_needs_rehash(stored)
    except Exception:
        return True


def _hash_password_scrypt(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(
        password.encode("utf-8"), salt=salt,
        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_DKLEN, maxmem=_MAXMEM,
    )
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N, _SCRYPT_R, _SCRYPT_P,
        base64.b64encode(salt).decode(), base64.b64encode(dk).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    if stored.startswith("$argon2"):
        if _argon is None:
            return False
        try:
            return _argon.verify(stored, password)
        except (VerifyMismatchError, InvalidHashError, Exception):
            return False
    try:
        scheme, n, r, p, salt_b64, dk_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(
            password.encode("utf-8"), salt=base64.b64decode(salt_b64),
            n=int(n), r=int(r), p=int(p),
            dklen=len(base64.b64decode(dk_b64)), maxmem=_MAXMEM,
        )
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except Exception:
        return False


def password_problems(password: str) -> list[str]:
    """Bewusst schlank: Laenge schlaegt Zeichenklassen-Regeln."""
    out = []
    if len(password) < 12:
        out.append("Mindestens 12 Zeichen.")
    if password.lower() in {"password", "passwort", "scopex", "123456789012"}:
        out.append("Zu leicht zu erraten.")
    return out


# --------------------------------------------------------------------------
# TOTP (RFC 6238, SHA1, 6 Stellen, 30 s)
# --------------------------------------------------------------------------

def new_totp_secret() -> str:
    return base64.b32encode(os.urandom(20)).decode("ascii").rstrip("=")


def _totp_at(secret_b32: str, counter: int, digits: int = 6) -> str:
    pad = "=" * (-len(secret_b32) % 8)
    key = base64.b32decode(secret_b32 + pad, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10 ** digits)).zfill(digits)


def verify_totp(secret_b32: str, code: str, window: int = 1) -> bool:
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return False
    counter = int(time.time()) // 30
    for drift in range(-window, window + 1):
        if hmac.compare_digest(_totp_at(secret_b32, counter + drift), code):
            return True
    return False


def totp_uri(secret_b32: str, account: str, issuer: str = "SCOPE X") -> str:
    return (
        f"otpauth://totp/{quote(issuer)}:{quote(account)}"
        f"?secret={secret_b32}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
    )


def qr_svg(data: str) -> str:
    """QR-Code als inline-SVG.

    segno akzeptiert nur echte Farbwerte, deshalb wird nach der Erzeugung
    auf currentColor umgestellt. Der Code passt sich dadurch der hellen wie
    der dunklen Darstellung an, ohne dass zwei Varianten noetig waeren.
    """
    import io
    import segno
    buf = io.BytesIO()
    segno.make(data, error="m").save(
        buf, kind="svg", scale=1, border=2, dark="#000000", light=None,
        svgclass=None, lineclass=None, omitsize=True, xmldecl=False, svgns=True,
    )
    svg = buf.getvalue().decode("utf-8")
    return svg.replace('stroke="#000"', 'stroke="currentColor"')


# --------------------------------------------------------------------------
# Wiederherstellungscodes
# --------------------------------------------------------------------------

_RC_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # ohne I, O, 0, 1


def generate_recovery_codes(count: int = 10) -> list[str]:
    codes = []
    for _ in range(count):
        raw = "".join(secrets.choice(_RC_ALPHABET) for _ in range(16))
        codes.append(f"{raw[0:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:16]}")
    return codes


def _rc_hash(code: str) -> str:
    normalized = code.upper().replace("-", "").replace(" ", "")
    return hashlib.sha256(normalized.encode()).hexdigest()


def store_recovery_codes(c, user_id: str, codes: list[str]) -> None:
    q(c, "DELETE FROM recovery_codes WHERE user_id = :u", u=user_id)
    for code in codes:
        q(c, "INSERT INTO recovery_codes (id, user_id, code_hash, created_at) "
             "VALUES (:i, :u, :h, :t)",
          i=new_id(), u=user_id, h=_rc_hash(code), t=now_iso())


def consume_recovery_code(c, user_id: str, code: str) -> bool:
    rec = row(c, "SELECT id FROM recovery_codes WHERE user_id = :u "
                 "AND code_hash = :h AND used_at IS NULL",
              u=user_id, h=_rc_hash(code))
    if not rec:
        return False
    q(c, "UPDATE recovery_codes SET used_at = :t WHERE id = :i",
      t=now_iso(), i=rec["id"])
    return True


# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------

def token_hash(token: str) -> str:
    """Token werden nie im Klartext gespeichert. Ein Datenbankauszug
    enthaelt damit keine verwendbaren Sitzungen, Einladungen oder
    Reset-Links."""
    return hashlib.sha256(token.encode()).hexdigest()


def _token_hash(token: str) -> str:
    return token_hash(token)


def hash_ip(ip: str | None) -> str | None:
    """IP-Adressen landen nur als gekuerzter Hash im Protokoll. Damit lassen
    sich wiederholte Versuche derselben Quelle erkennen, ohne die Adresse
    selbst zu speichern."""
    if not ip:
        return None
    return hashlib.sha256(("scopex-ip:" + ip).encode()).hexdigest()[:16]


def create_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    with conn() as c:
        q(c, "INSERT INTO sessions (id, user_id, token_hash, created_at, "
             "expires_at, last_seen_at) VALUES (:i, :u, :h, :c, :e, :l)",
          i=new_id(), u=user_id, h=_token_hash(token),
          c=now_iso(), e=expires.replace(microsecond=0).isoformat(),
          l=now_iso())
    return token


def idle_limit_minutes(c) -> int:
    r = row(c, "SELECT svalue FROM settings WHERE user_id IS NULL "
               "AND skey = 'idle_timeout_minutes'")
    try:
        return max(1, int(r["svalue"])) if r else 30
    except (TypeError, ValueError):
        return 30


def resolve_session(token: str | None) -> dict | None:
    """Loest eine Sitzung auf und erneuert dabei den Zeitstempel.

    Neben dem harten Ablaufdatum gilt eine Leerlaufgrenze: wer die
    Anwendung liegen laesst, wird serverseitig abgemeldet. Das ist der
    wirksame Teil einer automatischen Abmeldung, denn ein Zaehler im
    Browser laesst sich umgehen.
    """
    if not token:
        return None
    with conn() as c:
        s = row(c, "SELECT * FROM sessions WHERE token_hash = :h",
                h=_token_hash(token))
        if not s:
            return None
        if s["expires_at"] < now_iso():
            q(c, "DELETE FROM sessions WHERE id = :i", i=s["id"])
            return None
        idle_deadline = (datetime.fromisoformat(s["last_seen_at"])
                         + timedelta(minutes=idle_limit_minutes(c)))
        if datetime.now(timezone.utc) > idle_deadline:
            q(c, "DELETE FROM sessions WHERE id = :i", i=s["id"])
            return None
        q(c, "UPDATE sessions SET last_seen_at = :t WHERE id = :i",
          t=now_iso(), i=s["id"])
        return row(c, "SELECT * FROM users WHERE id = :u", u=s["user_id"])


def destroy_session(token: str | None) -> None:
    if not token:
        return
    with conn() as c:
        q(c, "DELETE FROM sessions WHERE token_hash = :h", h=_token_hash(token))


def destroy_all_sessions(user_id: str) -> None:
    with conn() as c:
        q(c, "DELETE FROM sessions WHERE user_id = :u", u=user_id)


# --------------------------------------------------------------------------
# Vertrauensgeraete
# --------------------------------------------------------------------------
# Ein Vertrauensgeraet erspart bei der taeglichen Anmeldung den TOTP-Code.
# Es hebt die Zwei-Faktor-Pflicht nicht auf: sicherheitsrelevante Aktionen
# verlangen weiterhin einen frischen Code, unabhaengig vom Geraet.

DEVICE_COOKIE = "scopex_device"
DEVICE_DAYS = 90


def create_trusted_device(user_id: str, label: str | None = None) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=DEVICE_DAYS)
    with conn() as c:
        q(c, "INSERT INTO trusted_devices (id, user_id, token_hash, label, "
             "created_at, expires_at, last_used_at) "
             "VALUES (:i, :u, :h, :l, :c, :e, :c)",
          i=new_id(), u=user_id, h=token_hash(token), l=(label or "")[:80],
          c=now_iso(), e=expires.replace(microsecond=0).isoformat())
    return token


def trusted_device_valid(user_id: str, token: str | None) -> bool:
    if not token:
        return False
    with conn() as c:
        d = row(c, "SELECT * FROM trusted_devices WHERE token_hash = :h "
                   "AND user_id = :u", h=token_hash(token), u=user_id)
        if not d:
            return False
        if d["expires_at"] < now_iso():
            q(c, "DELETE FROM trusted_devices WHERE id = :i", i=d["id"])
            return False
        q(c, "UPDATE trusted_devices SET last_used_at = :t WHERE id = :i",
          t=now_iso(), i=d["id"])
        return True


def forget_device(token: str | None) -> None:
    if not token:
        return
    with conn() as c:
        q(c, "DELETE FROM trusted_devices WHERE token_hash = :h",
          h=token_hash(token))


def forget_all_devices(user_id: str) -> None:
    with conn() as c:
        q(c, "DELETE FROM trusted_devices WHERE user_id = :u", u=user_id)
