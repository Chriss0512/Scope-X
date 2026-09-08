"""Stammdaten: Massnahmen, Parameterdefinitionen, Medikamente, ZEK.

Aenderungen hier wirken ausschliesslich nach vorne. Historische Eintraege
tragen ihre eigene Namenskopie und bleiben unberuehrt.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core import audit, current_user, require_admin
from ..db import conn, new_id, q, row, rows
from ..seed import (
    CATEGORIES,
    DELEGATIONS,
    DIVI_GROUPS,
    DIVI_LABELS,
    NACA_LEVELS,
    OUTCOMES,
    PATIENT_HARM,
    PERFORMER_ROLE_HINTS,
    PERFORMER_ROLES,
    QUALIFICATIONS,
    ROUTES,
    UNITS,
    ZEK_RELATION_HINTS,
    ZEK_RELATIONS,
)

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("/constants")
def constants():
    """Feste Auswahlwerte fuer das Frontend, an einer Stelle definiert."""
    return {
        "categories": [{"key": k, "label": v} for k, v in CATEGORIES],
        "outcomes": OUTCOMES,
        "zek_relations": [{"key": r, "hint": ZEK_RELATION_HINTS[r]}
                          for r in ZEK_RELATIONS],
        "patient_harm": PATIENT_HARM,
        "delegations": DELEGATIONS,
        "performer_roles": [{"key": r, "hint": PERFORMER_ROLE_HINTS[r]}
                            for r in PERFORMER_ROLES],
        "naca": NACA_LEVELS,
        "routes": ROUTES,
        "units": UNITS,
        "qualifications": QUALIFICATIONS,
        "divi_groups": DIVI_GROUPS,
        "divi_labels": DIVI_LABELS,
    }


@router.get("/measures")
def list_measures(include_inactive: bool = False, user=Depends(current_user)):
    with conn() as c:
        where = "" if include_inactive else "WHERE m.active = 1"
        items = rows(c, f"SELECT * FROM measures m {where} "
                        "ORDER BY m.category, m.sort_order, m.name")
        params = rows(c, "SELECT * FROM measure_parameter_definitions "
                         "ORDER BY sort_order")
        favs = {r["measure_id"] for r in rows(
            c, "SELECT measure_id FROM favorites WHERE user_id = :u", u=user["id"])}
        recent = rows(c, """
            SELECT a.measure_id, MAX(a.performed_at) AS last_used, COUNT(*) AS n
            FROM measure_attempts a
            JOIN encounters e ON e.id = a.encounter_id
            WHERE e.user_id = :u AND a.measure_id IS NOT NULL
            GROUP BY a.measure_id ORDER BY last_used DESC LIMIT 12
        """, u=user["id"])

    by_measure: dict[str, list] = {}
    for p in params:
        entry = {
            "key": p["pkey"], "label": p["label"], "type": p["ptype"],
            "unit": p["unit"], "required": bool(p["required"]),
            "options": p["options"].split("|") if p["options"] else None,
        }
        by_measure.setdefault(p["measure_id"], []).append(entry)

    for m in items:
        m["parameters"] = by_measure.get(m["id"], [])
        m["favorite"] = m["id"] in favs
        m["active"] = bool(m["active"])
        m["builtin"] = bool(m["builtin"])

    return {"measures": items, "recent": [r["measure_id"] for r in recent]}


class MeasureIn(BaseModel):
    name: str
    category: str
    sort_order: int = 999
    active: bool = True


@router.post("/measures")
def create_measure(data: MeasureIn, user=Depends(require_admin)):
    with conn() as c:
        if data.category not in dict(CATEGORIES):
            raise HTTPException(400, "Unbekannte Kategorie.")
        mid = new_id()
        code = "user_" + mid[:8]
        q(c, "INSERT INTO measures (id, code, category, name, sort_order, "
             "active, builtin) VALUES (:i, :c, :k, :n, :s, :a, 0)",
          i=mid, c=code, k=data.category, n=data.name.strip(),
          s=data.sort_order, a=1 if data.active else 0)
        audit(c, user["id"], "measures", mid, "create", "name", None, data.name)
        return row(c, "SELECT * FROM measures WHERE id = :i", i=mid)


class MeasurePatch(BaseModel):
    name: str | None = None
    category: str | None = None
    sort_order: int | None = None
    active: bool | None = None


@router.patch("/measures/{measure_id}")
def update_measure(measure_id: str, data: MeasurePatch, user=Depends(require_admin)):
    with conn() as c:
        m = row(c, "SELECT * FROM measures WHERE id = :i", i=measure_id)
        if not m:
            raise HTTPException(404, "Maßnahme nicht gefunden.")
        for field, value in data.model_dump(exclude_unset=True).items():
            if value is None:
                continue
            new = 1 if value is True else 0 if value is False else value
            if str(m[field]) == str(new):
                continue
            q(c, f"UPDATE measures SET {field} = :v WHERE id = :i", v=new, i=measure_id)
            audit(c, user["id"], "measures", measure_id, "update", field,
                  m[field], new)
        return row(c, "SELECT * FROM measures WHERE id = :i", i=measure_id)


class ParameterIn(BaseModel):
    key: str
    label: str
    type: str = "text"
    unit: str | None = None
    options: list[str] | None = None
    sort_order: int = 999


@router.post("/measures/{measure_id}/parameters")
def add_parameter(measure_id: str, data: ParameterIn, user=Depends(require_admin)):
    if data.type not in {"text", "number", "int", "select"}:
        raise HTTPException(400, "Unbekannter Parametertyp.")
    with conn() as c:
        if not row(c, "SELECT id FROM measures WHERE id = :i", i=measure_id):
            raise HTTPException(404, "Maßnahme nicht gefunden.")
        pid = new_id()
        q(c, "INSERT INTO measure_parameter_definitions (id, measure_id, pkey, "
             "label, ptype, unit, options, sort_order, required) "
             "VALUES (:i, :m, :k, :l, :t, :u, :o, :s, 0)",
          i=pid, m=measure_id, k=data.key.strip(), l=data.label.strip(),
          t=data.type, u=data.unit,
          o="|".join(data.options) if data.options else None,
          s=data.sort_order)
        audit(c, user["id"], "measure_parameter_definitions", pid, "create")
    return {"ok": True, "id": pid}


@router.delete("/measures/{measure_id}/parameters/{param_id}")
def delete_parameter(measure_id: str, param_id: str, user=Depends(require_admin)):
    with conn() as c:
        q(c, "DELETE FROM measure_parameter_definitions WHERE id = :i "
             "AND measure_id = :m", i=param_id, m=measure_id)
        audit(c, user["id"], "measure_parameter_definitions", param_id, "delete")
    return {"ok": True}


@router.post("/measures/{measure_id}/favorite")
def toggle_favorite(measure_id: str, user=Depends(current_user)):
    with conn() as c:
        existing = row(c, "SELECT id FROM favorites WHERE user_id = :u "
                          "AND measure_id = :m", u=user["id"], m=measure_id)
        if existing:
            q(c, "DELETE FROM favorites WHERE id = :i", i=existing["id"])
            return {"favorite": False}
        q(c, "INSERT INTO favorites (id, user_id, measure_id) VALUES (:i, :u, :m)",
          i=new_id(), u=user["id"], m=measure_id)
        return {"favorite": True}


# --------------------------------------------------------------------------
# Medikamente
# --------------------------------------------------------------------------

@router.get("/medications")
def list_medications(include_inactive: bool = False, user=Depends(current_user)):
    with conn() as c:
        where = "" if include_inactive else "WHERE active = 1"
        meds = rows(c, f"SELECT * FROM medications {where} ORDER BY name")
        preps = rows(c, "SELECT * FROM medication_preparations WHERE active = 1")
        recent = rows(c, """
            SELECT a.medication_id, MAX(a.administered_at) AS last_used
            FROM medication_administrations a
            JOIN encounters e ON e.id = a.encounter_id
            WHERE e.user_id = :u AND a.medication_id IS NOT NULL
            GROUP BY a.medication_id ORDER BY last_used DESC LIMIT 12
        """, u=user["id"])
    by_med: dict[str, list] = {}
    for p in preps:
        by_med.setdefault(p["medication_id"], []).append(
            {"id": p["id"], "name": p["name"], "strength": p["strength"]})
    for m in meds:
        m["preparations"] = by_med.get(m["id"], [])
        m["trade_names"] = [t.strip() for t in (m.get("trade_names") or "").split("|")
                            if t.strip()]
        m["active"] = bool(m["active"])
        m["builtin"] = bool(m["builtin"])
    return {"medications": meds, "recent": [r["medication_id"] for r in recent]}


class MedicationIn(BaseModel):
    name: str
    active: bool = True


@router.post("/medications")
def create_medication(data: MedicationIn, user=Depends(require_admin)):
    with conn() as c:
        if row(c, "SELECT id FROM medications WHERE name = :n", n=data.name.strip()):
            raise HTTPException(409, "Dieser Wirkstoff ist bereits angelegt.")
        mid = new_id()
        q(c, "INSERT INTO medications (id, name, active, builtin, sort_order) "
             "VALUES (:i, :n, :a, 0, 999)",
          i=mid, n=data.name.strip(), a=1 if data.active else 0)
        audit(c, user["id"], "medications", mid, "create", "name", None, data.name)
    return {"ok": True, "id": mid}


class MedicationPatch(BaseModel):
    name: str | None = None
    active: bool | None = None
    divi_group: str | None = None
    # Handelsnamen als einfache Liste, gespeichert mit | getrennt. Für ein
    # optionales Freitextfeld braucht es keine eigene Tabelle.
    trade_names: list[str] | None = None


@router.patch("/medications/{medication_id}")
def update_medication(medication_id: str, data: MedicationPatch,
                      user=Depends(require_admin)):
    with conn() as c:
        m = row(c, "SELECT * FROM medications WHERE id = :i", i=medication_id)
        if not m:
            raise HTTPException(404, "Wirkstoff nicht gefunden.")
        for field, value in data.model_dump(exclude_unset=True).items():
            if value is None:
                continue
            if field == "trade_names":
                value = "|".join(t.strip() for t in value if t.strip()) or None
            new = 1 if value is True else 0 if value is False else value
            if str(m[field]) == str(new):
                continue
            q(c, f"UPDATE medications SET {field} = :v WHERE id = :i",
              v=new, i=medication_id)
            audit(c, user["id"], "medications", medication_id, "update",
                  field, m[field], new)
    return {"ok": True}


class PreparationIn(BaseModel):
    name: str
    strength: str | None = None


@router.post("/medications/{medication_id}/preparations")
def add_preparation(medication_id: str, data: PreparationIn,
                    user=Depends(require_admin)):
    with conn() as c:
        if not row(c, "SELECT id FROM medications WHERE id = :i", i=medication_id):
            raise HTTPException(404, "Wirkstoff nicht gefunden.")
        pid = new_id()
        q(c, "INSERT INTO medication_preparations (id, medication_id, name, "
             "strength, active) VALUES (:i, :m, :n, :s, 1)",
          i=pid, m=medication_id, n=data.name.strip(), s=data.strength)
        audit(c, user["id"], "medication_preparations", pid, "create")
    return {"ok": True, "id": pid}


@router.delete("/medications/{medication_id}/preparations/{prep_id}")
def deactivate_preparation(medication_id: str, prep_id: str,
                           user=Depends(require_admin)):
    with conn() as c:
        q(c, "UPDATE medication_preparations SET active = 0 WHERE id = :i",
          i=prep_id)
        audit(c, user["id"], "medication_preparations", prep_id, "deactivate")
    return {"ok": True}


# --------------------------------------------------------------------------
# ZEK
# --------------------------------------------------------------------------

@router.get("/complications")
def list_complications(include_inactive: bool = False, user=Depends(current_user)):
    with conn() as c:
        where = "" if include_inactive else "WHERE active = 1"
        items = rows(c, f"SELECT * FROM complications {where} ORDER BY code")
    for i in items:
        i["active"] = bool(i["active"])
    return {"complications": items}


class ComplicationIn(BaseModel):
    code: str
    category: str
    label: str


@router.post("/complications")
def create_complication(data: ComplicationIn, user=Depends(require_admin)):
    with conn() as c:
        if row(c, "SELECT id FROM complications WHERE code = :c", c=data.code.strip()):
            raise HTTPException(409, "Dieser Code ist bereits vergeben.")
        cid = new_id()
        q(c, "INSERT INTO complications (id, code, category, label, active) "
             "VALUES (:i, :c, :k, :l, 1)",
          i=cid, c=data.code.strip(), k=data.category.strip(), l=data.label.strip())
        audit(c, user["id"], "complications", cid, "create")
    return {"ok": True, "id": cid}


@router.patch("/complications/{complication_id}")
def update_complication(complication_id: str, data: dict,
                        user=Depends(require_admin)):
    allowed = {"label", "category", "active"}
    with conn() as c:
        cur = row(c, "SELECT * FROM complications WHERE id = :i", i=complication_id)
        if not cur:
            raise HTTPException(404, "ZEK-Eintrag nicht gefunden.")
        for field, value in data.items():
            if field not in allowed:
                continue
            new = 1 if value is True else 0 if value is False else value
            if str(cur[field]) == str(new):
                continue
            q(c, f"UPDATE complications SET {field} = :v WHERE id = :i",
              v=new, i=complication_id)
            audit(c, user["id"], "complications", complication_id, "update",
                  field, cur[field], new)
    return {"ok": True}
