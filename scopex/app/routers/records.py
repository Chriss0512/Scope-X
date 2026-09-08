"""Dokumentierte Daten: Einsaetze, Massnahmen, Medikamentengaben.

Beim Speichern werden Bezeichnungen aus dem Stammdatenkatalog in den
Datensatz kopiert. Ein spaeter umbenanntes oder deaktiviertes Katalogobjekt
veraendert dadurch keine bestehende Dokumentation.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..core import (
    annotate_lock,
    audit,
    audit_diff,
    current_user,
    enforce_editable,
    enforce_encounter_editable,
    require_writer,
)
from ..db import conn, new_id, now_iso, q, row, rows, scalar
from ..seed import (
    DELEGATIONS,
    NACA_LEVELS,
    OUTCOMES,
    PATIENT_HARM,
    PERFORMER_ROLES,
    ROUTES,
    UNITS,
    ZEK_RELATIONS,
)

router = APIRouter(prefix="/api", tags=["records"])


def _own_encounter(c, encounter_id: str, user_id: str) -> dict:
    enc = row(c, "SELECT * FROM encounters WHERE id = :i AND user_id = :u "
                 "AND deleted_at IS NULL", i=encounter_id, u=user_id)
    if not enc:
        raise HTTPException(404, "Einsatz nicht gefunden.")
    return enc


def _enforce_via_encounter(c, encounter_id: str, user_id: str) -> None:
    enc = row(c, "SELECT * FROM encounters WHERE id = :i", i=encounter_id)
    if enc:
        enforce_encounter_editable(c, enc, user_id)


def _touch(c, encounter_id: str) -> None:
    q(c, "UPDATE encounters SET updated_at = :t WHERE id = :i",
      t=now_iso(), i=encounter_id)


class ComplicationLink(BaseModel):
    """Eine ZEK-Zuordnung mit ihrem Bezug zum Ausgang.

    Bezug und Schadenseinschaetzung gehoeren an die Zuordnung, nicht an das
    Ergebnisfeld. Nur so laesst sich eine erfolgreiche Massnahme mit
    Komplikation von einem Misserfolg unterscheiden, den eine Komplikation
    verursacht hat, ohne dass sich beide Angaben widersprechen koennen.
    """
    id: str
    relation: str = "begleitend"
    patient_harm: str = "kein Schaden erkennbar"


def _validate_links(links) -> None:
    for link in links or []:
        if link.relation not in ZEK_RELATIONS:
            raise HTTPException(400, "Unbekannter ZEK-Bezug.")
        if link.patient_harm not in PATIENT_HARM:
            raise HTTPException(400, "Unbekannte Schadenseinschätzung.")


def _link_complications(c, table: str, fk: str, owner_id: str, links) -> None:
    q(c, f"DELETE FROM {table} WHERE {fk} = :o", o=owner_id)
    for link in links or []:
        comp = row(c, "SELECT * FROM complications WHERE id = :i", i=link.id)
        if not comp:
            continue
        q(c, f"INSERT INTO {table} (id, {fk}, complication_id, code, label, "
             f"relation, patient_harm) VALUES (:i, :o, :c, :co, :l, :r, :h)",
          i=new_id(), o=owner_id, c=comp["id"], co=comp["code"],
          l=comp["label"], r=link.relation, h=link.patient_harm)


def _complications_for(c, table: str, fk: str, owner_id: str) -> list[dict]:
    return rows(c, f"SELECT complication_id AS id, code, label, relation, "
                   f"patient_harm FROM {table} WHERE {fk} = :o ORDER BY code",
                o=owner_id)


# --------------------------------------------------------------------------
# Einsaetze
# --------------------------------------------------------------------------

class EncounterIn(BaseModel):
    enc_date: str
    enc_time: str
    mission_number: str | None = None
    naca: str | None = None
    shift_code: str | None = None
    vehicle_id: str | None = None


@router.post("/encounters")
def create_encounter(data: EncounterIn, user=Depends(require_writer)):
    if data.naca and data.naca not in NACA_LEVELS:
        raise HTTPException(400, "Unbekannter NACA-Wert.")
    with conn() as c:
        eid = new_id()
        q(c, "INSERT INTO encounters (id, user_id, enc_date, enc_time, "
             "mission_number, naca, shift_code, vehicle_id, created_at, "
             "updated_at) VALUES (:i, :u, :d, :t, :m, :n, :s, :v, :c, :c)",
          i=eid, u=user["id"], d=data.enc_date, t=data.enc_time,
          m=(data.mission_number or "").strip() or None,
          n=data.naca or None,
          s=(data.shift_code or "").strip() or None,
          v=(data.vehicle_id or "").strip() or None, c=now_iso())
        audit(c, user["id"], "encounters", eid, "create")
        return annotate_lock(c, row(c, "SELECT * FROM encounters WHERE id = :i", i=eid),
                             user["id"])


@router.get("/encounters")
def list_encounters(date_from: str | None = None, date_to: str | None = None,
                    limit: int = 50, offset: int = 0,
                    user=Depends(current_user)):
    clauses = ["e.user_id = :u", "e.deleted_at IS NULL"]
    params: dict = {"u": user["id"], "lim": min(limit, 200), "off": offset}
    if date_from:
        clauses.append("e.enc_date >= :df")
        params["df"] = date_from
    if date_to:
        clauses.append("e.enc_date <= :dt")
        params["dt"] = date_to
    where = " AND ".join(clauses)
    with conn() as c:
        items = rows(c, f"""
            SELECT e.*,
              (SELECT COUNT(*) FROM measure_attempts a
                WHERE a.encounter_id = e.id AND a.deleted_at IS NULL)
                AS attempt_count,
              (SELECT COUNT(*) FROM medication_administrations m
                WHERE m.encounter_id = e.id AND m.deleted_at IS NULL)
                AS medication_count
            FROM encounters e WHERE {where}
            ORDER BY e.enc_date DESC, e.enc_time DESC
            LIMIT :lim OFFSET :off
        """, **params)
        total = scalar(c, f"SELECT COUNT(*) FROM encounters e WHERE {where}",
                       **{k: v for k, v in params.items() if k not in ("lim", "off")})
        items = [annotate_lock(c, i, user["id"]) for i in items]
    return {"encounters": items, "total": total}


@router.get("/encounters/{encounter_id}")
def get_encounter(encounter_id: str, user=Depends(current_user)):
    with conn() as c:
        enc = annotate_lock(c, _own_encounter(c, encounter_id, user["id"]), user["id"])
        attempts = rows(c, "SELECT * FROM measure_attempts WHERE encounter_id = :e "
                           "AND deleted_at IS NULL "
                           "ORDER BY performed_at, created_at", e=encounter_id)
        for a in attempts:
            a["parameters"] = rows(
                c, "SELECT pkey AS key, label, value_text AS value, unit "
                   "FROM measure_attempt_parameters WHERE attempt_id = :a", a=a["id"])
            a["complications"] = _complications_for(
                c, "attempt_complications", "attempt_id", a["id"])
            # Kein eigener Countdown je Eintrag: maßgeblich ist der Einsatz.
            a["lock"] = enc["lock"]
        meds = rows(c, "SELECT * FROM medication_administrations "
                       "WHERE encounter_id = :e AND deleted_at IS NULL "
                       "ORDER BY administered_at, created_at", e=encounter_id)
        for m in meds:
            m["complications"] = _complications_for(
                c, "medication_complications", "administration_id", m["id"])
            m["lock"] = enc["lock"]
    with conn() as c:
        enc["complications"] = _complications_for(
            c, "encounter_complications", "encounter_id", encounter_id)
    enc["attempts"] = attempts
    enc["medications"] = meds
    return enc


class EncounterPatch(BaseModel):
    enc_date: str | None = None
    enc_time: str | None = None
    mission_number: str | None = None
    naca: str | None = None
    shift_code: str | None = None
    vehicle_id: str | None = None


@router.patch("/encounters/{encounter_id}")
def update_encounter(encounter_id: str, data: EncounterPatch,
                     user=Depends(require_writer)):
    with conn() as c:
        enc = _own_encounter(c, encounter_id, user["id"])
        enforce_editable(c, "encounters", enc, user["id"])
        payload = data.model_dump(exclude_unset=True)
        if payload.get("naca") and payload["naca"] not in NACA_LEVELS:
            raise HTTPException(400, "Unbekannter NACA-Wert.")
        after = {**enc, **payload}
        audit_diff(c, user["id"], "encounters", encounter_id, enc, after,
                   ["enc_date", "enc_time", "mission_number", "naca",
                    "shift_code", "vehicle_id"])
        q(c, "UPDATE encounters SET enc_date = :d, enc_time = :t, "
             "mission_number = :m, naca = :n, shift_code = :s, "
             "vehicle_id = :v, updated_at = :ua WHERE id = :i",
          d=after["enc_date"], t=after["enc_time"],
          m=(after.get("mission_number") or None), n=after.get("naca") or None,
          s=(after.get("shift_code") or None), v=(after.get("vehicle_id") or None),
          ua=now_iso(), i=encounter_id)
        return annotate_lock(c, row(c, "SELECT * FROM encounters WHERE id = :i",
                                    i=encounter_id), user["id"])


@router.delete("/encounters/{encounter_id}")
def delete_encounter(encounter_id: str, user=Depends(require_writer)):
    with conn() as c:
        enc = _own_encounter(c, encounter_id, user["id"])
        enforce_editable(c, "encounters", enc, user["id"])
        for a in rows(c, "SELECT id FROM measure_attempts WHERE encounter_id = :e",
                      e=encounter_id):
            q(c, "DELETE FROM measure_attempt_parameters WHERE attempt_id = :a", a=a["id"])
            q(c, "DELETE FROM attempt_complications WHERE attempt_id = :a", a=a["id"])
        for m in rows(c, "SELECT id FROM medication_administrations "
                         "WHERE encounter_id = :e", e=encounter_id):
            q(c, "DELETE FROM medication_complications WHERE administration_id = :m",
              m=m["id"])
        q(c, "DELETE FROM measure_attempts WHERE encounter_id = :e", e=encounter_id)
        q(c, "DELETE FROM medication_administrations WHERE encounter_id = :e",
          e=encounter_id)
        q(c, "DELETE FROM encounter_complications WHERE encounter_id = :e",
          e=encounter_id)
        q(c, "DELETE FROM encounters WHERE id = :i", i=encounter_id)
        audit(c, user["id"], "encounters", encounter_id, "delete")
    return {"ok": True}


class EncounterComplicationsIn(BaseModel):
    complications: list[ComplicationLink] = Field(default_factory=list)


@router.put("/encounters/{encounter_id}/complications")
def set_encounter_complications(encounter_id: str,
                                data: EncounterComplicationsIn,
                                user=Depends(require_writer)):
    """ZEK, die zum Einsatz gehören und keiner Maßnahme zuzuordnen sind.

    Organisationsprobleme bei der Übergabe oder ein nicht verfügbares
    Rettungsmittel betreffen den Einsatz als Ganzes. Sie einer beliebigen
    Maßnahme unterzuschieben würde die Auswertung verfälschen.
    """
    _validate_links(data.complications)
    with conn() as c:
        enc = _own_encounter(c, encounter_id, user["id"])
        enforce_encounter_editable(c, enc, user["id"])
        _link_complications(c, "encounter_complications", "encounter_id",
                            encounter_id, data.complications)
        audit(c, user["id"], "encounters", encounter_id, "update", "zek")
        _touch(c, encounter_id)
    return get_encounter(encounter_id, user)


# --------------------------------------------------------------------------
# Massnahmen
# --------------------------------------------------------------------------

class AttemptIn(BaseModel):
    measure_id: str
    performed_at: str | None = None
    outcome: str
    delegation: str | None = None
    performer_role: str = "selbst durchgeführt"
    performer_qualification: str | None = None
    note: str | None = None
    parameters: dict[str, str | float | int | None] = Field(default_factory=dict)
    complications: list[ComplicationLink] = Field(default_factory=list)


@router.post("/encounters/{encounter_id}/attempts")
def create_attempt(encounter_id: str, data: AttemptIn, user=Depends(require_writer)):
    if data.outcome not in OUTCOMES:
        raise HTTPException(400, "Unbekanntes Ergebnis.")
    if data.delegation and data.delegation not in DELEGATIONS:
        raise HTTPException(400, "Unbekannte Durchführungsart.")
    if data.performer_role not in PERFORMER_ROLES:
        raise HTTPException(400, "Unbekannte Rolle.")
    _validate_links(data.complications)
    with conn() as c:
        enc = _own_encounter(c, encounter_id, user["id"])
        enforce_editable(c, "encounters", enc, user["id"])
        measure = row(c, "SELECT * FROM measures WHERE id = :i", i=data.measure_id)
        if not measure:
            raise HTTPException(404, "Maßnahme nicht gefunden.")

        aid = new_id()
        q(c, "INSERT INTO measure_attempts (id, encounter_id, measure_id, "
             "measure_name, measure_category, performed_at, outcome, "
             "delegation, performer_role, performer_qualification, note, "
             "created_at, updated_at) "
             "VALUES (:i, :e, :m, :mn, :mc, :p, :o, :d, :pr, :pq, :nt, :c, :c)",
          i=aid, e=encounter_id, m=measure["id"], mn=measure["name"],
          mc=measure["category"],
          p=data.performed_at or f"{enc['enc_date']}T{enc['enc_time']}",
          o=data.outcome, d=data.delegation, pr=data.performer_role,
          pq=(data.performer_qualification or "").strip() or None,
          nt=(data.note or "").strip() or None, c=now_iso())

        defs = {d["pkey"]: d for d in rows(
            c, "SELECT * FROM measure_parameter_definitions WHERE measure_id = :m",
            m=measure["id"])}
        for key, value in (data.parameters or {}).items():
            if value in (None, ""):
                continue
            d = defs.get(key)
            q(c, "INSERT INTO measure_attempt_parameters (id, attempt_id, pkey, "
                 "label, value_text, unit) VALUES (:i, :a, :k, :l, :v, :u)",
              i=new_id(), a=aid, k=key,
              l=d["label"] if d else key, v=str(value),
              u=d["unit"] if d else None)

        _link_complications(c, "attempt_complications", "attempt_id", aid,
                            data.complications)
        audit(c, user["id"], "measure_attempts", aid, "create", "measure_name",
              None, measure["name"])
        _touch(c, encounter_id)
    return get_encounter(encounter_id, user)


class AttemptPatch(BaseModel):
    performed_at: str | None = None
    outcome: str | None = None
    delegation: str | None = None
    performer_role: str | None = None
    performer_qualification: str | None = None
    note: str | None = None
    parameters: dict[str, str | float | int | None] | None = None
    complications: list[ComplicationLink] | None = None


@router.patch("/attempts/{attempt_id}")
def update_attempt(attempt_id: str, data: AttemptPatch, user=Depends(require_writer)):
    with conn() as c:
        att = row(c, """SELECT a.* FROM measure_attempts a
                        JOIN encounters e ON e.id = a.encounter_id
                        WHERE a.id = :i AND e.user_id = :u
                        AND a.deleted_at IS NULL""",
                  i=attempt_id, u=user["id"])
        if not att:
            raise HTTPException(404, "Maßnahme nicht gefunden.")
        _enforce_via_encounter(c, att["encounter_id"], user["id"])

        payload = data.model_dump(exclude_unset=True)
        if payload.get("outcome") and payload["outcome"] not in OUTCOMES:
            raise HTTPException(400, "Unbekanntes Ergebnis.")
        _validate_links(data.complications)
        after = {**att, **{k: v for k, v in payload.items()
                           if k not in ("parameters", "complications")}}
        if payload.get("performer_role") and \
                payload["performer_role"] not in PERFORMER_ROLES:
            raise HTTPException(400, "Unbekannte Rolle.")
        audit_diff(c, user["id"], "measure_attempts", attempt_id, att, after,
                   ["performed_at", "outcome", "delegation", "performer_role",
                    "performer_qualification", "note"])
        q(c, "UPDATE measure_attempts SET performed_at = :p, outcome = :o, "
             "delegation = :d, performer_role = :pr, "
             "performer_qualification = :pq, note = :n, updated_at = :u "
             "WHERE id = :i",
          p=after["performed_at"], o=after["outcome"], d=after["delegation"],
          pr=after["performer_role"], pq=after["performer_qualification"],
          n=after["note"], u=now_iso(), i=attempt_id)

        if payload.get("parameters") is not None:
            defs = {d["pkey"]: d for d in rows(
                c, "SELECT * FROM measure_parameter_definitions WHERE measure_id = :m",
                m=att["measure_id"])}
            q(c, "DELETE FROM measure_attempt_parameters WHERE attempt_id = :a",
              a=attempt_id)
            for key, value in payload["parameters"].items():
                if value in (None, ""):
                    continue
                d = defs.get(key)
                q(c, "INSERT INTO measure_attempt_parameters (id, attempt_id, "
                     "pkey, label, value_text, unit) VALUES (:i, :a, :k, :l, :v, :u)",
                  i=new_id(), a=attempt_id, k=key, l=d["label"] if d else key,
                  v=str(value), u=d["unit"] if d else None)
            audit(c, user["id"], "measure_attempts", attempt_id, "update", "parameters")

        if data.complications is not None:
            _link_complications(c, "attempt_complications", "attempt_id",
                                attempt_id, data.complications)
            audit(c, user["id"], "measure_attempts", attempt_id, "update", "zek")

        _touch(c, att["encounter_id"])
        encounter_id = att["encounter_id"]
    return get_encounter(encounter_id, user)


@router.delete("/attempts/{attempt_id}")
def delete_attempt(attempt_id: str, user=Depends(require_writer)):
    with conn() as c:
        att = row(c, """SELECT a.* FROM measure_attempts a
                        JOIN encounters e ON e.id = a.encounter_id
                        WHERE a.id = :i AND e.user_id = :u
                        AND a.deleted_at IS NULL""",
                  i=attempt_id, u=user["id"])
        if not att:
            raise HTTPException(404, "Maßnahme nicht gefunden.")
        _enforce_via_encounter(c, att["encounter_id"], user["id"])
        q(c, "DELETE FROM measure_attempt_parameters WHERE attempt_id = :a", a=attempt_id)
        q(c, "DELETE FROM attempt_complications WHERE attempt_id = :a", a=attempt_id)
        q(c, "DELETE FROM measure_attempts WHERE id = :i", i=attempt_id)
        audit(c, user["id"], "measure_attempts", attempt_id, "delete")
        _touch(c, att["encounter_id"])
    return {"ok": True}


# --------------------------------------------------------------------------
# Medikamentengaben
# --------------------------------------------------------------------------

class AdministrationIn(BaseModel):
    medication_id: str
    preparation_id: str | None = None
    dose: float | None = None
    unit: str | None = None
    route: str | None = None
    administered_at: str | None = None
    delegation: str | None = None
    outcome: str = "erfolgreich"
    adverse_effect: str | None = None
    follow_up: str | None = None
    note: str | None = None
    complications: list[ComplicationLink] = Field(default_factory=list)


@router.post("/encounters/{encounter_id}/medications")
def create_administration(encounter_id: str, data: AdministrationIn,
                          user=Depends(require_writer)):
    if data.unit and data.unit not in UNITS:
        raise HTTPException(400, "Unbekannte Einheit.")
    if data.route and data.route not in ROUTES:
        raise HTTPException(400, "Unbekannter Applikationsweg.")
    if data.outcome not in OUTCOMES:
        raise HTTPException(400, "Unbekanntes Ergebnis.")
    _validate_links(data.complications)
    with conn() as c:
        enc = _own_encounter(c, encounter_id, user["id"])
        enforce_editable(c, "encounters", enc, user["id"])
        med = row(c, "SELECT * FROM medications WHERE id = :i", i=data.medication_id)
        if not med:
            raise HTTPException(404, "Wirkstoff nicht gefunden.")
        prep = None
        if data.preparation_id:
            prep = row(c, "SELECT * FROM medication_preparations WHERE id = :i",
                       i=data.preparation_id)

        mid = new_id()
        q(c, "INSERT INTO medication_administrations (id, encounter_id, "
             "medication_id, medication_name, preparation_id, preparation_name, "
             "dose, unit, route, administered_at, delegation, outcome, "
             "adverse_effect, follow_up, note, created_at, updated_at) "
             "VALUES (:i, :e, :m, :mn, :p, :pn, :d, :u, :r, :a, :dl, :o, "
             ":ae, :fu, :nt, :c, :c)",
          i=mid, e=encounter_id, m=med["id"], mn=med["name"],
          p=prep["id"] if prep else None, pn=prep["name"] if prep else None,
          d=data.dose, u=data.unit, r=data.route,
          a=data.administered_at or f"{enc['enc_date']}T{enc['enc_time']}",
          dl=data.delegation, o=data.outcome,
          ae=(data.adverse_effect or "").strip() or None,
          fu=(data.follow_up or "").strip() or None,
          nt=(data.note or "").strip() or None, c=now_iso())
        _link_complications(c, "medication_complications", "administration_id",
                            mid, data.complications)
        audit(c, user["id"], "medication_administrations", mid, "create",
              "medication_name", None, med["name"])
        _touch(c, encounter_id)
    return get_encounter(encounter_id, user)


class AdministrationPatch(BaseModel):
    dose: float | None = None
    unit: str | None = None
    route: str | None = None
    administered_at: str | None = None
    delegation: str | None = None
    outcome: str | None = None
    adverse_effect: str | None = None
    follow_up: str | None = None
    note: str | None = None
    complications: list[ComplicationLink] | None = None


@router.patch("/administrations/{administration_id}")
def update_administration(administration_id: str, data: AdministrationPatch,
                          user=Depends(require_writer)):
    with conn() as c:
        adm = row(c, """SELECT m.* FROM medication_administrations m
                        JOIN encounters e ON e.id = m.encounter_id
                        WHERE m.id = :i AND e.user_id = :u
                        AND m.deleted_at IS NULL""",
                  i=administration_id, u=user["id"])
        if not adm:
            raise HTTPException(404, "Medikamentengabe nicht gefunden.")
        _enforce_via_encounter(c, adm["encounter_id"], user["id"])
        payload = data.model_dump(exclude_unset=True)
        after = {**adm, **{k: v for k, v in payload.items()
                           if k != "complications"}}
        if payload.get("outcome") and payload["outcome"] not in OUTCOMES:
            raise HTTPException(400, "Unbekanntes Ergebnis.")
        audit_diff(c, user["id"], "medication_administrations", administration_id,
                   adm, after, ["dose", "unit", "route", "administered_at",
                                "delegation", "outcome", "adverse_effect",
                                "follow_up", "note"])
        q(c, "UPDATE medication_administrations SET dose = :d, unit = :u, "
             "route = :r, administered_at = :a, delegation = :dl, "
             "outcome = :o, adverse_effect = :ae, follow_up = :fu, note = :n, "
             "updated_at = :ua WHERE id = :i",
          d=after["dose"], u=after["unit"], r=after["route"],
          a=after["administered_at"], dl=after["delegation"],
          o=after["outcome"], ae=after["adverse_effect"],
          fu=after["follow_up"], n=after["note"],
          ua=now_iso(), i=administration_id)
        if data.complications is not None:
            _link_complications(c, "medication_complications", "administration_id",
                                administration_id, data.complications)
        _touch(c, adm["encounter_id"])
        encounter_id = adm["encounter_id"]
    return get_encounter(encounter_id, user)


@router.delete("/administrations/{administration_id}")
def delete_administration(administration_id: str, user=Depends(require_writer)):
    with conn() as c:
        adm = row(c, """SELECT m.* FROM medication_administrations m
                        JOIN encounters e ON e.id = m.encounter_id
                        WHERE m.id = :i AND e.user_id = :u
                        AND m.deleted_at IS NULL""",
                  i=administration_id, u=user["id"])
        if not adm:
            raise HTTPException(404, "Medikamentengabe nicht gefunden.")
        _enforce_via_encounter(c, adm["encounter_id"], user["id"])
        q(c, "DELETE FROM medication_complications WHERE administration_id = :m",
          m=administration_id)
        q(c, "DELETE FROM medication_administrations WHERE id = :i",
          i=administration_id)
        audit(c, user["id"], "medication_administrations", administration_id, "delete")
        _touch(c, adm["encounter_id"])
    return {"ok": True}


class WithdrawIn(BaseModel):
    reason: str


def _check_reason(reason: str) -> str:
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise HTTPException(400, "Bitte gib eine Begründung an, mindestens "
                                 "fünf Zeichen.")
    return reason[:500]


@router.post("/attempts/{attempt_id}/withdraw")
def withdraw_attempt(attempt_id: str, data: WithdrawIn,
                     user=Depends(require_writer)):
    """Legt eine gesperrte Maßnahme still.

    Der Datensatz bleibt physisch erhalten und verschwindet nur aus
    Statistik, Nachweis und Ansicht. Begründung und Zeitpunkt landen im
    Änderungsprotokoll, damit die Lücke im Nachweis erklärbar bleibt.
    """
    reason = _check_reason(data.reason)
    with conn() as c:
        att = row(c, """SELECT a.* FROM measure_attempts a
                        JOIN encounters e ON e.id = a.encounter_id
                        WHERE a.id = :i AND e.user_id = :u
                        AND a.deleted_at IS NULL""",
                  i=attempt_id, u=user["id"])
        if not att:
            raise HTTPException(404, "Maßnahme nicht gefunden.")
        q(c, "UPDATE measure_attempts SET deleted_at = :t, deleted_reason = :r "
             "WHERE id = :i", t=now_iso(), r=reason, i=attempt_id)
        audit(c, user["id"], "measure_attempts", attempt_id, "withdraw",
              "measure_name", att["measure_name"], reason)
        _touch(c, att["encounter_id"])
    return {"ok": True}


@router.post("/administrations/{administration_id}/withdraw")
def withdraw_administration(administration_id: str, data: WithdrawIn,
                            user=Depends(require_writer)):
    reason = _check_reason(data.reason)
    with conn() as c:
        adm = row(c, """SELECT m.* FROM medication_administrations m
                        JOIN encounters e ON e.id = m.encounter_id
                        WHERE m.id = :i AND e.user_id = :u
                        AND m.deleted_at IS NULL""",
                  i=administration_id, u=user["id"])
        if not adm:
            raise HTTPException(404, "Medikamentengabe nicht gefunden.")
        q(c, "UPDATE medication_administrations SET deleted_at = :t, "
             "deleted_reason = :r WHERE id = :i",
          t=now_iso(), r=reason, i=administration_id)
        audit(c, user["id"], "medication_administrations", administration_id,
              "withdraw", "medication_name", adm["medication_name"], reason)
        _touch(c, adm["encounter_id"])
    return {"ok": True}


@router.post("/encounters/{encounter_id}/withdraw")
def withdraw_encounter(encounter_id: str, data: WithdrawIn,
                       user=Depends(require_writer)):
    """Legt einen gesperrten Einsatz samt aller Einträge still."""
    reason = _check_reason(data.reason)
    with conn() as c:
        enc = _own_encounter(c, encounter_id, user["id"])
        stamp = now_iso()
        for table in ("measure_attempts", "medication_administrations"):
            q(c, f"UPDATE {table} SET deleted_at = :t, deleted_reason = :r "
                 f"WHERE encounter_id = :e AND deleted_at IS NULL",
              t=stamp, r=reason, e=encounter_id)
        q(c, "UPDATE encounters SET deleted_at = :t, deleted_reason = :r "
             "WHERE id = :i", t=stamp, r=reason, i=encounter_id)
        audit(c, user["id"], "encounters", encounter_id, "withdraw",
              "enc_date", enc["enc_date"], reason)
    return {"ok": True}


# --------------------------------------------------------------------------
# Startseite
# --------------------------------------------------------------------------

@router.get("/overview")
def overview(user=Depends(current_user)):
    year = datetime.now(timezone.utc).strftime("%Y")
    with conn() as c:
        live_a = "a.deleted_at IS NULL AND e.deleted_at IS NULL"
        live_m = "m.deleted_at IS NULL AND e.deleted_at IS NULL"
        encounters = scalar(c, "SELECT COUNT(*) FROM encounters e "
                               "WHERE e.user_id = :u AND e.deleted_at IS NULL",
                            u=user["id"]) or 0
        attempts = scalar(c, "SELECT COUNT(*) FROM measure_attempts a "
                             "JOIN encounters e ON e.id = a.encounter_id "
                             f"WHERE e.user_id = :u AND {live_a}", u=user["id"]) or 0
        attempts_year = scalar(c, "SELECT COUNT(*) FROM measure_attempts a "
                                  "JOIN encounters e ON e.id = a.encounter_id "
                                  f"WHERE e.user_id = :u AND {live_a} "
                                  "AND e.enc_date LIKE :y",
                               u=user["id"], y=f"{year}%") or 0
        meds = scalar(c, "SELECT COUNT(*) FROM medication_administrations m "
                         "JOIN encounters e ON e.id = m.encounter_id "
                         f"WHERE e.user_id = :u AND {live_m}", u=user["id"]) or 0
        zek = scalar(c, """
            SELECT (SELECT COUNT(*) FROM attempt_complications ac
                     JOIN measure_attempts a ON a.id = ac.attempt_id
                     JOIN encounters e ON e.id = a.encounter_id
                     WHERE e.user_id = :u AND a.deleted_at IS NULL
                     AND e.deleted_at IS NULL)
                 + (SELECT COUNT(*) FROM medication_complications mc
                     JOIN medication_administrations m ON m.id = mc.administration_id
                     JOIN encounters e2 ON e2.id = m.encounter_id
                     WHERE e2.user_id = :u AND m.deleted_at IS NULL
                     AND e2.deleted_at IS NULL)
        """, u=user["id"]) or 0
        recent = rows(c, """
            SELECT a.measure_name, a.measure_category, a.outcome, a.performed_at,
                   e.id AS encounter_id, e.naca
            FROM measure_attempts a JOIN encounters e ON e.id = a.encounter_id
            WHERE e.user_id = :u AND a.deleted_at IS NULL
              AND e.deleted_at IS NULL
            ORDER BY a.performed_at DESC LIMIT 8
        """, u=user["id"])
    return {
        "encounters": encounters, "attempts": attempts,
        "attempts_year": attempts_year, "medications": meds,
        "complications": zek, "recent": recent, "year": year,
    }
