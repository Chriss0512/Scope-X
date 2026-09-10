"""Profil und Einstellungen.

Die Qualifikation ist eine reine Dokumentationsangabe. Sie steuert nicht,
welche Massnahmen im Katalog sichtbar sind. Der einzige Effekt ist, dass
bei aerztlicher Qualifikation das Feld Durchfuehrungsart ausgeblendet
werden kann, weil es dort keine Aussage traegt.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core import (
    audit,
    current_user,
    edit_window_minutes,
    get_setting,
    require_admin,
    set_setting,
)
from ..db import conn, now_iso, q, row
from ..seed import QUALIFICATIONS

router = APIRouter(prefix="/api", tags=["profile"])

EDITABLE_SETTINGS = {"edit_window_minutes", "theme", "show_delegation"}
IMPRINT_SETTINGS = {
    "imprint_name", "imprint_address", "imprint_email", "imprint_phone",
    "imprint_profession", "imprint_authority", "imprint_law",
}

# Sieben Tage. Darüber hinaus verliert ein Nachweis seinen Sinn, weil
# rückwirkende Änderungen dann die Regel statt die Ausnahme wären.
MAX_EDIT_WINDOW = 10080


class ProfileIn(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    qualification: str | None = None
    specialty: str | None = None
    role: str | None = None
    registration_id: str | None = None


@router.get("/profile")
def get_profile(user=Depends(current_user)):
    with conn() as c:
        p = row(c, "SELECT * FROM user_profile WHERE user_id = :u", u=user["id"]) or {}
        extra = get_setting(c, "extra_qualifications", "")
    quals = QUALIFICATIONS + [q_.strip() for q_ in (extra or "").split("|") if q_.strip()]
    return {"profile": p, "qualifications": quals,
            "username": user["username"], "email": user["email"]}


@router.put("/profile")
def update_profile(data: ProfileIn, user=Depends(current_user)):
    payload = data.model_dump(exclude_unset=True)
    with conn() as c:
        current = row(c, "SELECT * FROM user_profile WHERE user_id = :u", u=user["id"])
        if not current:
            q(c, "INSERT INTO user_profile (user_id, created_at) VALUES (:u, :t)",
              u=user["id"], t=now_iso())
            current = row(c, "SELECT * FROM user_profile WHERE user_id = :u",
                          u=user["id"])
        for field, value in payload.items():
            if field not in ProfileIn.model_fields:
                continue
            if str(current.get(field) or "") == str(value or ""):
                continue
            q(c, f"UPDATE user_profile SET {field} = :v WHERE user_id = :u",
              v=value, u=user["id"])
            audit(c, user["id"], "user_profile", user["id"], "update", field,
                  current.get(field), value)
        return {"profile": row(c, "SELECT * FROM user_profile WHERE user_id = :u",
                               u=user["id"])}


class QualificationIn(BaseModel):
    name: str


@router.post("/profile/qualifications")
def add_qualification(data: QualificationIn, user=Depends(require_admin)):
    with conn() as c:
        extra = get_setting(c, "extra_qualifications", "") or ""
        entries = [e.strip() for e in extra.split("|") if e.strip()]
        name = data.name.strip()
        if name and name not in entries and name not in QUALIFICATIONS:
            entries.append(name)
            set_setting(c, "extra_qualifications", "|".join(entries))
            audit(c, user["id"], "settings", "extra_qualifications", "update",
                  "extra_qualifications", extra, "|".join(entries))
        return {"qualifications": QUALIFICATIONS + entries}


@router.get("/settings")
def get_settings(user=Depends(current_user)):
    with conn() as c:
        return {
            "edit_window_minutes": edit_window_minutes(c, user["id"]),
            "theme": get_setting(c, "theme", "auto", user["id"]),
            "show_delegation": get_setting(c, "show_delegation", "auto", user["id"]),
        }


class SettingsIn(BaseModel):
    edit_window_minutes: int | None = None
    theme: str | None = None
    show_delegation: str | None = None


@router.put("/settings")
def update_settings(data: SettingsIn, user=Depends(current_user)):
    payload = data.model_dump(exclude_unset=True)
    window = payload.get("edit_window_minutes")
    # Die Bearbeitungsfrist bestimmt die Beweiskraft aller Nachweise dieser
    # Installation und gilt deshalb global und nur für Administratoren.
    if window is not None and (user.get("role") or "user") != "admin":
        raise HTTPException(403, "Die Bearbeitungsfrist legt der Administrator fest.")
    if window is not None and not (1 <= window <= MAX_EDIT_WINDOW):
        raise HTTPException(
            400, f"Die Bearbeitungsfrist muss zwischen 1 und "
                 f"{MAX_EDIT_WINDOW} Minuten liegen, also höchstens sieben Tage.")
    with conn() as c:
        for key, value in payload.items():
            if key not in EDITABLE_SETTINGS or value is None:
                continue
            old = get_setting(c, key, None, user["id"])
            scope = None if key == "edit_window_minutes" else user["id"]
            set_setting(c, key, str(value), scope)
            audit(c, user["id"], "settings", key, "update", key, old, value)
    return get_settings(user)


# --------------------------------------------------------------------------
# Rechtliche Angaben
# --------------------------------------------------------------------------
# Bewusst ohne Anmeldung erreichbar. Eine Anbieterkennzeichnung, die erst
# nach dem Login sichtbar wird, erfüllt ihren Zweck nicht.


class ImprintIn(BaseModel):
    imprint_name: str | None = None
    imprint_address: str | None = None
    imprint_email: str | None = None
    # § 5 Abs. 1 Nr. 2 DDG verlangt Angaben zur schnellen Kontaktaufnahme.
    # Eine E-Mail-Adresse allein genügt dafür nach der Rechtsprechung nicht.
    imprint_phone: str | None = None
    # Nr. 5 gilt für reglementierte Berufe. Notfallsanitäterin und
    # Notfallsanitäter sind nach dem NotSanG reglementiert.
    imprint_profession: str | None = None
    imprint_authority: str | None = None
    imprint_law: str | None = None


@router.get("/legal")
def legal():
    with conn() as c:
        return {
            "name": get_setting(c, "imprint_name", "") or "",
            "address": get_setting(c, "imprint_address", "") or "",
            "email": get_setting(c, "imprint_email", "") or "",
            "phone": get_setting(c, "imprint_phone", "") or "",
            "profession": get_setting(c, "imprint_profession", "") or "",
            "authority": get_setting(c, "imprint_authority", "") or "",
            "law": get_setting(c, "imprint_law", "") or "",
        }


@router.put("/legal")
def update_legal(data: ImprintIn, user=Depends(require_admin)):
    payload = data.model_dump(exclude_unset=True)
    with conn() as c:
        for key, value in payload.items():
            if key not in IMPRINT_SETTINGS or value is None:
                continue
            old = get_setting(c, key, None)
            set_setting(c, key, value.strip())
            audit(c, user["id"], "settings", key, "update", key, old, value)
    return legal()
