"""Nachweise, Exporte, Backup und Wiederherstellung."""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel

from .. import pdf as pdf_module
from ..analytics import (
    Filters,
    compute,
    detail_medications,
    detail_rows,
    resolve_period,
)
from ..core import audit, current_user, edit_window_minutes, require_admin
from ..db import conn, engine, new_id, now_iso, q, row, rows, scalar
from ..security import verify_password, verify_totp

router = APIRouter(prefix="/api", tags=["exports"])

BACKUP_TABLES = [
    "user_profile", "encounters", "measures",
    "measure_parameter_definitions", "measure_attempts",
    "measure_attempt_parameters", "medications", "medication_preparations",
    "medication_administrations", "complications", "attempt_complications",
    "medication_complications", "favorites", "settings", "audit_log",
]

BACKUP_VERSION = 1


def _period_label(df: str | None, dt: str | None) -> str:
    def fmt(v):
        try:
            return datetime.fromisoformat(v).strftime("%d.%m.%Y")
        except Exception:
            return v
    if df and dt:
        return f"{fmt(df)} bis {fmt(dt)}"
    if df:
        return f"ab {fmt(df)}"
    if dt:
        return f"bis {fmt(dt)}"
    return "Gesamter Zeitraum"


def _filters(user_id, period, date_from, date_to, naca, category, measure_id,
             outcome, delegation, complication_id, medication_id, route,
             harm=None, performer_role=None):
    df, dt = resolve_period(period, date_from, date_to)
    return Filters(user_id, df, dt, naca, category, measure_id, outcome,
                   delegation, complication_id, medication_id, route,
                   harm or [], performer_role or []), df, dt


@router.get("/exports/pdf")
def export_pdf(
    period: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    detailed: bool = False,
    include_medications: bool = True,
    naca: list[str] = Query(default=[]),
    category: list[str] = Query(default=[]),
    measure_id: list[str] = Query(default=[]),
    outcome: list[str] = Query(default=[]),
    delegation: list[str] = Query(default=[]),
    complication_id: list[str] = Query(default=[]),
    medication_id: list[str] = Query(default=[]),
    route: list[str] = Query(default=[]),
    user=Depends(current_user),
):
    f, df, dt = _filters(user["id"], period, date_from, date_to, naca, category,
                         measure_id, outcome, delegation, complication_id,
                         medication_id, route)
    with conn() as c:
        profile = row(c, "SELECT * FROM user_profile WHERE user_id = :u",
                      u=user["id"]) or {}
        stats = compute(c, f)
        details = detail_rows(c, f) if detailed else None
        det_meds = (detail_medications(c, f)
                    if (detailed and include_medications) else None)
        window = edit_window_minutes(c, user["id"])
        audit(c, user["id"], "exports", new_id(), "pdf", "period",
              None, _period_label(df, dt))

    data = pdf_module.build(profile, stats, _period_label(df, dt), details,
                            det_meds, window)
    stamp = datetime.now().strftime("%Y%m%d")
    return Response(
        content=data, media_type="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="scopex-nachweis-{stamp}.pdf"'},
    )


@router.get("/exports/csv")
def export_csv(kind: str = "attempts", period: str | None = None,
               date_from: str | None = None, date_to: str | None = None,
               user=Depends(current_user)):
    f, df, dt = _filters(user["id"], period, date_from, date_to,
                         [], [], [], [], [], [], [], [], [], [])
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    with conn() as c:
        if kind == "medications":
            writer.writerow(["Datum", "Uhrzeit", "Einsatznummer", "NACA",
                             "Wirkstoff", "Präparat", "Dosis", "Einheit",
                             "Applikationsweg", "Durchführungsart", "ZEK"])
            for m in detail_medications(c, f, limit=100000):
                writer.writerow([
                    m["enc_date"], m["enc_time"], m.get("mission_number") or "",
                    m.get("naca") or "", m["medication_name"],
                    m.get("preparation_name") or "",
                    "" if m.get("dose") is None else m["dose"],
                    m.get("unit") or "", m.get("route") or "",
                    m.get("delegation") or "",
                    "; ".join(f"{x['code']} {x['label']} "
                              f"[Schaden {x['patient_harm']}]"
                              for x in m["complications"]),
                ])
        else:
            writer.writerow(["Datum", "Uhrzeit", "Einsatznummer", "NACA",
                             "Kategorie", "Maßnahme", "Ergebnis",
                             "Durchführungsart", "Rolle", "Parameter", "ZEK"])
            for a in detail_rows(c, f, limit=100000):
                params = "; ".join(
                    f"{p['label']}: {p['value']}{(' ' + p['unit']) if p.get('unit') else ''}"
                    for p in a["parameters"])
                writer.writerow([
                    a["enc_date"], a["enc_time"], a.get("mission_number") or "",
                    a.get("naca") or "", a["measure_category"], a["measure_name"],
                    a["outcome"], a.get("delegation") or "",
                    a.get("performer_role") or "", params,
                    "; ".join(f"{x['code']} {x['label']} [{x['relation']}, "
                              f"Schaden {x['patient_harm']}]"
                              for x in a["complications"]),
                ])
    stamp = datetime.now().strftime("%Y%m%d")
    return Response(
        content="\ufeff" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":
                 f'attachment; filename="scopex-{kind}-{stamp}.csv"'},
    )


@router.get("/exports/backup")
def export_backup(user=Depends(current_user)):
    """Vollstaendiges Backup als JSON. Enthaelt Stammdaten, Profil,
    Einsaetze, Massnahmen, Medikamentengaben, ZEK-Verknuepfungen,
    Einstellungen und das Audit-Log.

    Zugangsdaten sind bewusst nicht enthalten: kein Passwort-Hash, kein
    TOTP-Secret, keine Wiederherstellungscodes. Ein Backup allein gibt
    damit niemandem Zugriff auf das Konto.
    """
    payload = {"format": "scopex-backup", "version": BACKUP_VERSION,
               "created_at": now_iso(), "tables": {}}
    with conn() as c:
        for table in BACKUP_TABLES:
            payload["tables"][table] = rows(c, f"SELECT * FROM {table}")
        audit(c, user["id"], "exports", new_id(), "backup")
    body = json.dumps(payload, ensure_ascii=False, indent=1)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    return Response(
        content=body, media_type="application/json",
        headers={"Content-Disposition":
                 f'attachment; filename="scopex-backup-{stamp}.json"'},
    )


class RestoreConfirm(BaseModel):
    password: str
    totp_code: str | None = None


@router.post("/exports/restore")
async def restore_backup(file: UploadFile = File(...),
                         password: str = "", totp_code: str = "",
                         user=Depends(require_admin)):
    """Wiederherstellung ersetzt den gesamten Datenbestand.

    Erfordert eine erneute Authentifizierung, weil der Vorgang nicht
    umkehrbar ist. Das eigene Konto und die 2FA-Einrichtung bleiben
    unberuehrt.
    """
    if not verify_password(password, user["password_hash"]):
        raise HTTPException(400, "Passwort stimmt nicht.")
    with conn() as c:
        t = row(c, "SELECT * FROM auth_totp WHERE user_id = :u", u=user["id"])
        if t and t["confirmed_at"] and not verify_totp(t["secret"], totp_code or ""):
            raise HTTPException(400, "Ungültiger Code.")

    raw = await file.read()
    if len(raw) > 64 * 1024 * 1024:
        raise HTTPException(413, "Die Datei ist zu groß.")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(
            400, "Die Datei ist keine gültige SCOPE-X-Sicherung.") from exc
    if payload.get("format") != "scopex-backup":
        raise HTTPException(400, "Die Datei ist keine gültige SCOPE-X-Sicherung.")
    if payload.get("version") != BACKUP_VERSION:
        raise HTTPException(
            400, f"Sicherungsformat Version {payload.get('version')} wird von "
                 f"dieser Installation nicht gelesen.")

    tables = payload.get("tables", {})
    counts: dict[str, int] = {}
    with engine.begin() as c:
        for table in reversed(BACKUP_TABLES):
            c.exec_driver_sql(f"DELETE FROM {table}")
        for table in BACKUP_TABLES:
            records = tables.get(table) or []
            if not records:
                counts[table] = 0
                continue
            columns = list(records[0].keys())
            placeholders = ", ".join(f":{col}" for col in columns)
            sql = (f"INSERT INTO {table} ({', '.join(columns)}) "
                   f"VALUES ({placeholders})")
            for rec in records:
                q(c, sql, **{col: rec.get(col) for col in columns})
            counts[table] = len(records)
        # Das wiederhergestellte Profil gehoert dem aktuellen Konto.
        q(c, "UPDATE user_profile SET user_id = :u", u=user["id"])
        q(c, "UPDATE encounters SET user_id = :u", u=user["id"])
        audit(c, user["id"], "exports", new_id(), "restore", "records",
              None, sum(counts.values()))
    return {"ok": True, "restored": counts}


# --------------------------------------------------------------------------
# Auskunft und Löschung nach DSGVO
# --------------------------------------------------------------------------

USER_TABLES = {
    "encounters": "user_id",
    "measure_attempts": None,      # über den Einsatz
    "medication_administrations": None,
    "favorites": "user_id",
    "settings": "user_id",
    "audit_log": "user_id",
}


@router.get("/exports/my-data")
def export_own_data(user=Depends(current_user)):
    """Vollständige Auskunft nach Art. 15 und 20 DSGVO.

    Enthält alles, was zu diesem Konto gespeichert ist, in einem
    maschinenlesbaren Format. Passwort-Hash, TOTP-Geheimnis, Reset-Token
    und Gerätekennungen sind bewusst nicht enthalten: sie sind
    Zugangsmittel, keine Auskunft, und ein Export in falschen Händen wäre
    sonst ein Kontozugriff.
    """
    with conn() as c:
        account = row(c, "SELECT id, username, email, created_at, "
                         "last_login_at, role FROM users WHERE id = :u",
                      u=user["id"])
        profile = row(c, "SELECT * FROM user_profile WHERE user_id = :u",
                      u=user["id"])
        encounters = rows(c, "SELECT * FROM encounters WHERE user_id = :u "
                             "ORDER BY enc_date", u=user["id"])
        ids = [e["id"] for e in encounters]
        for enc in encounters:
            enc["attempts"] = rows(
                c, "SELECT * FROM measure_attempts WHERE encounter_id = :e",
                e=enc["id"])
            for a in enc["attempts"]:
                a["parameters"] = rows(
                    c, "SELECT pkey, label, value_text, unit FROM "
                       "measure_attempt_parameters WHERE attempt_id = :a",
                    a=a["id"])
                a["complications"] = rows(
                    c, "SELECT code, label, relation, patient_harm FROM "
                       "attempt_complications WHERE attempt_id = :a", a=a["id"])
            enc["medications"] = rows(
                c, "SELECT * FROM medication_administrations "
                   "WHERE encounter_id = :e", e=enc["id"])
            for m in enc["medications"]:
                m["complications"] = rows(
                    c, "SELECT code, label, relation, patient_harm FROM "
                       "medication_complications WHERE administration_id = :a",
                    a=m["id"])
            enc["complications"] = rows(
                c, "SELECT code, label, relation, patient_harm FROM "
                   "encounter_complications WHERE encounter_id = :e", e=enc["id"])
        settings_rows = rows(c, "SELECT skey, svalue FROM settings "
                                "WHERE user_id = :u", u=user["id"])
        audit_rows = rows(c, "SELECT at, entity_type, entity_id, action, "
                             "field, old_value, new_value FROM audit_log "
                             "WHERE user_id = :u ORDER BY at", u=user["id"])
        devices = rows(c, "SELECT label, created_at, expires_at, last_used_at "
                          "FROM trusted_devices WHERE user_id = :u", u=user["id"])
        keys = rows(c, "SELECT label, created_at, last_used_at FROM passkeys "
                       "WHERE user_id = :u", u=user["id"])
        audit(c, user["id"], "exports", new_id(), "self_export", "encounters",
              None, len(ids))

    payload = {
        "format": "scopex-auskunft", "version": 1, "created_at": now_iso(),
        "hinweis": "Auskunft nach Art. 15 und 20 DSGVO. Zugangsmittel wie "
                   "Passwort-Hash und Zwei-Faktor-Geheimnis sind nicht "
                   "enthalten.",
        "konto": account, "profil": profile, "einsaetze": encounters,
        "einstellungen": settings_rows, "aenderungsprotokoll": audit_rows,
        "vertraute_geraete": devices, "passkeys": keys,
    }
    stamp = datetime.now().strftime("%Y%m%d")
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=1),
        media_type="application/json",
        headers={"Content-Disposition":
                 f'attachment; filename="scopex-auskunft-{stamp}.json"'})


class DeleteAccountIn(BaseModel):
    password: str
    totp_code: str | None = None
    confirm: str


@router.post("/account/delete")
def delete_own_account(data: DeleteAccountIn, user=Depends(current_user)):
    """Löschung nach Art. 17 DSGVO.

    Entfernt Konto, Profil, alle dokumentierten Daten und alle
    Zugangsmittel physisch. Die Einträge im Änderungsprotokoll bleiben
    bestehen, verlieren aber ihren Personenbezug: sie sichern die
    Nachvollziehbarkeit administrativer Vorgänge und enthalten selbst keine
    personenbezogenen Inhalte.
    """
    if data.confirm.strip().upper() != "LÖSCHEN":
        raise HTTPException(400, "Zur Bestätigung bitte LÖSCHEN eingeben.")
    if not verify_password(data.password, user["password_hash"]):
        raise HTTPException(400, "Passwort stimmt nicht.")
    with conn() as c:
        t = row(c, "SELECT * FROM auth_totp WHERE user_id = :u", u=user["id"])
        if t and t["confirmed_at"] and not verify_totp(t["secret"],
                                                       data.totp_code or ""):
            raise HTTPException(400, "Ungültiger Code.")
        # Die Installation darf nicht ohne Administrator zurückbleiben.
        if (user.get("role") or "user") == "admin":
            others = scalar(c, "SELECT COUNT(*) FROM users WHERE role = 'admin' "
                               "AND disabled_at IS NULL AND id <> :i",
                            i=user["id"]) or 0
            if others == 0:
                raise HTTPException(
                    409, "Das ist der letzte aktive Administrator. Ernenne "
                         "zuerst eine andere Person.")

        enc_ids = [e["id"] for e in rows(
            c, "SELECT id FROM encounters WHERE user_id = :u", u=user["id"])]
        for eid in enc_ids:
            for aid in [a["id"] for a in rows(
                    c, "SELECT id FROM measure_attempts WHERE encounter_id = :e",
                    e=eid)]:
                q(c, "DELETE FROM measure_attempt_parameters WHERE attempt_id = :a", a=aid)
                q(c, "DELETE FROM attempt_complications WHERE attempt_id = :a", a=aid)
            for mid in [m["id"] for m in rows(
                    c, "SELECT id FROM medication_administrations "
                       "WHERE encounter_id = :e", e=eid)]:
                q(c, "DELETE FROM medication_complications "
                     "WHERE administration_id = :m", m=mid)
            q(c, "DELETE FROM measure_attempts WHERE encounter_id = :e", e=eid)
            q(c, "DELETE FROM medication_administrations WHERE encounter_id = :e", e=eid)
            q(c, "DELETE FROM encounter_complications WHERE encounter_id = :e", e=eid)
        q(c, "DELETE FROM encounters WHERE user_id = :u", u=user["id"])
        for table in ("favorites", "settings", "recovery_codes", "sessions",
                      "trusted_devices", "passkeys", "password_resets",
                      "auth_totp", "user_profile"):
            q(c, f"DELETE FROM {table} WHERE user_id = :u", u=user["id"])
        # Protokoll bleibt, verliert aber den Personenbezug.
        q(c, "UPDATE audit_log SET user_id = NULL WHERE user_id = :u", u=user["id"])
        q(c, "UPDATE invitations SET used_by = NULL WHERE used_by = :u", u=user["id"])
        q(c, "DELETE FROM users WHERE id = :i", i=user["id"])
        audit(c, None, "users", "gelöscht", "self_delete", "encounters",
              len(enc_ids), None)
    return {"ok": True, "deleted_encounters": len(enc_ids)}
