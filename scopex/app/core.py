"""Querschnittsfunktionen: Anmeldung, Einstellungen, Audit, Sperrfrist."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request

from .db import conn, new_id, now_iso, q, row, rows
from .security import SESSION_COOKIE, resolve_session


# --------------------------------------------------------------------------
# Anmeldung
# --------------------------------------------------------------------------

# Rollenmodell. Die Reihenfolge ist die Rangfolge.
ROLES = ["guest", "user", "admin"]
ROLE_LABELS = {
    "guest": "Gast",
    "user": "Mitarbeiter",
    "admin": "Administrator",
}


def current_user(request: Request) -> dict:
    user = resolve_session(request.cookies.get(SESSION_COOKIE))
    if not user:
        raise HTTPException(status_code=401, detail="Nicht angemeldet.")
    if user.get("disabled_at"):
        raise HTTPException(status_code=403, detail="Dieses Konto ist gesperrt.")
    return user


def require_role(*allowed: str):
    """Bindet eine Route an Rollen.

    Jede Route prueft serverseitig selbst. Dass die Oberflaeche eine
    Schaltflaeche ausblendet, ist Bequemlichkeit und niemals der Schutz.
    """
    def dependency(request: Request) -> dict:
        user = current_user(request)
        if (user.get("role") or "user") not in allowed:
            raise HTTPException(
                status_code=403,
                detail="Für diese Aktion fehlt dir die Berechtigung.")
        return user
    return dependency


require_admin = require_role("admin")
require_writer = require_role("user", "admin")


def fresh_totp_required(user: dict, code: str | None) -> None:
    """Verlangt einen aktuellen Code aus der Authenticator-App.

    Gilt fuer alles, was andere Konten oder den Datenbestand betrifft. Ein
    Vertrauensgeraet hilft hier ausdruecklich nicht: es erspart den Code bei
    der Anmeldung, nicht bei einem Eingriff in fremde Zugaenge.
    """
    from .security import verify_totp
    with conn() as c:
        t = row(c, "SELECT * FROM auth_totp WHERE user_id = :u", u=user["id"])
    if not (t and t["confirmed_at"]):
        raise HTTPException(400, "Zwei-Faktor-Authentifizierung ist nicht aktiv.")
    if not verify_totp(t["secret"], code or ""):
        raise HTTPException(
            400, "Für diese Aktion ist ein aktueller Code aus deiner "
                 "Authenticator-App nötig.")


def optional_user(request: Request) -> dict | None:
    return resolve_session(request.cookies.get(SESSION_COOKIE))


User = Depends(current_user)


# --------------------------------------------------------------------------
# Einstellungen
# --------------------------------------------------------------------------

def get_setting(c, key: str, default: str | None = None,
                user_id: str | None = None) -> str | None:
    if user_id:
        r = row(c, "SELECT svalue FROM settings WHERE user_id = :u AND skey = :k",
                u=user_id, k=key)
        if r:
            return r["svalue"]
    r = row(c, "SELECT svalue FROM settings WHERE user_id IS NULL AND skey = :k", k=key)
    return r["svalue"] if r else default


def set_setting(c, key: str, value: str, user_id: str | None = None) -> None:
    if user_id:
        existing = row(c, "SELECT id FROM settings WHERE user_id = :u AND skey = :k",
                       u=user_id, k=key)
    else:
        existing = row(c, "SELECT id FROM settings WHERE user_id IS NULL AND skey = :k",
                       k=key)
    if existing:
        q(c, "UPDATE settings SET svalue = :v WHERE id = :i", v=value, i=existing["id"])
    else:
        q(c, "INSERT INTO settings (id, user_id, skey, svalue) VALUES (:i, :u, :k, :v)",
          i=new_id(), u=user_id, k=key, v=value)


def edit_window_minutes(c, user_id: str | None = None) -> int:
    try:
        return max(1, int(get_setting(c, "edit_window_minutes", "120", user_id)))
    except (TypeError, ValueError):
        return 120


# --------------------------------------------------------------------------
# Audit-Log
# --------------------------------------------------------------------------

def audit(c, user_id: str | None, entity_type: str, entity_id: str,
          action: str, field: str | None = None,
          old_value=None, new_value=None) -> None:
    q(c, "INSERT INTO audit_log (id, user_id, at, entity_type, entity_id, "
         "action, field, old_value, new_value) "
         "VALUES (:i, :u, :t, :et, :ei, :a, :f, :o, :n)",
      i=new_id(), u=user_id, t=now_iso(), et=entity_type, ei=entity_id,
      a=action, f=field,
      o=None if old_value is None else str(old_value),
      n=None if new_value is None else str(new_value))


def audit_diff(c, user_id: str, entity_type: str, entity_id: str,
               before: dict, after: dict, fields: list[str]) -> int:
    """Protokolliert nur tatsaechliche Wertaenderungen, Feld fuer Feld."""
    changed = 0
    for f in fields:
        old, new = before.get(f), after.get(f)
        if str(old or "") == str(new or ""):
            continue
        audit(c, user_id, entity_type, entity_id, "update", f, old, new)
        changed += 1
    return changed


# --------------------------------------------------------------------------
# Bearbeitungssperre
# --------------------------------------------------------------------------

def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def lock_state(c, record: dict, user_id: str | None = None) -> dict:
    """Ermittelt, ob ein Datensatz noch bearbeitbar ist.

    Gesperrt wird nicht durch einen Hintergrundjob, sondern beim Zugriff.
    Das haelt den Zustand konsistent, auch wenn die Anwendung tagelang
    nicht lief.
    """
    if record.get("locked_at"):
        return {"locked": True, "locked_at": record["locked_at"], "remaining_seconds": 0}
    deadline = _parse(record["created_at"]) + timedelta(
        minutes=edit_window_minutes(c, user_id))
    remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
    if remaining <= 0:
        return {"locked": True, "locked_at": deadline.replace(microsecond=0).isoformat(),
                "remaining_seconds": 0}
    return {"locked": False, "locked_at": None, "remaining_seconds": int(remaining)}


def enforce_editable(c, table: str, record: dict, user_id: str) -> None:
    """Wirft 409, wenn der Datensatz gesperrt ist. Stempelt locked_at
    nach, falls die Frist abgelaufen war, aber noch nichts gesetzt wurde."""
    state = lock_state(c, record, user_id)
    if not state["locked"]:
        return
    if not record.get("locked_at"):
        q(c, f"UPDATE {table} SET locked_at = :t WHERE id = :i",
          t=state["locked_at"], i=record["id"])
        audit(c, user_id, table, record["id"], "lock")
    raise HTTPException(
        status_code=409,
        detail="Der Eintrag ist gesperrt und kann nicht mehr geändert werden.",
    )


def sweep_locks(c) -> int:
    """Stempelt abgelaufene Fristen nach. Wird beim Start aufgerufen,
    damit locked_at auch ohne Zugriff korrekt in Backups landet."""
    minutes = edit_window_minutes(c)
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes))
    cutoff_iso = cutoff.replace(microsecond=0).isoformat()
    total = 0
    for table in ("encounters", "measure_attempts", "medication_administrations"):
        res = q(c, f"UPDATE {table} SET locked_at = :t "
                   f"WHERE locked_at IS NULL AND created_at <= :c",
                t=now_iso(), c=cutoff_iso)
        total += res.rowcount or 0
    return total


def annotate_lock(c, record: dict, user_id: str | None = None) -> dict:
    record = dict(record)
    record["lock"] = lock_state(c, record, user_id)
    return record
