"""Übernahme aus NIDAshare: Abruf, Entwurf, Übernahme.

Der Entwurf wird nicht gespeichert. Er geht an das Gerät, wird dort
nachbearbeitet und kommt als fertige Auswahl zurück; erst dann entstehen
Einsatz, Maßnahmen und Medikamentengaben, über dieselben Funktionen und
Prüfungen wie bei der Eingabe von Hand. Gespeichert wird zum Abruf nur ein
Blindindex des Codes und der Status.

Datenschutzgrenze: Datum, Uhrzeit und Einsatznummer landen wie jede
andere Einsatzangabe nur im eigenen Logbuch, verschlüsselt, und sind für
andere Mitglieder nie sichtbar.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import nidashare, schutz
from ..core import audit, require_writer
from ..db import conn, new_id, now_iso, q, row, rows, scalar
from ..seed import DELEGATIONS, NACA_LEVELS, OUTCOMES, PERFORMER_ROLES, ROUTES, UNITS
from . import records

router = APIRouter(prefix="/api/import", tags=["import"])
log = logging.getLogger("scopex.import")

ABRUFE_JE_STUNDE = 10
DATUM = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ZEIT = re.compile(r"^\d{2}:\d{2}$")
ROLLEN = [r if isinstance(r, str) else r[0] for r in PERFORMER_ROLES]


def _aktiv_erforderlich() -> None:
    if not nidashare.aktiv():
        raise HTTPException(404, "Die Übernahme aus NIDAshare ist in dieser "
                                 "Installation nicht eingeschaltet.")


def _katalog(c, uid: str) -> tuple[list[dict], list[dict], dict[str, str]]:
    massnahmen = rows(c, "SELECT id, code, name FROM measures WHERE active = 1")
    medikamente = []
    for m in rows(c, "SELECT id, name FROM medications WHERE active = 1"):
        m["praeparate"] = [p["name"] for p in rows(
            c, "SELECT name FROM medication_preparations WHERE medication_id = :m "
               "AND active = 1", m=m["id"])]
        medikamente.append(m)
    eigene = {b["begriff"]: b["measure_id"] for b in rows(
        c, "SELECT begriff, measure_id FROM import_begriffe WHERE user_id = :u", u=uid)}
    return massnahmen, medikamente, eigene


class AbrufIn(BaseModel):
    code: str = Field(max_length=300)
    erneut: bool = False


@router.post("/nidashare")
def abrufen(data: AbrufIn, user=Depends(require_writer)):
    """Ruft das Protokoll ab und gibt den Entwurf zurück."""
    _aktiv_erforderlich()
    try:
        code = nidashare.code_normalisieren(data.code)
    except nidashare.AbrufFehler as exc:
        raise HTTPException(exc.status, exc.text) from None
    idx = schutz.index(code)
    with conn() as c:
        seit = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(
            microsecond=0).isoformat()
        if (scalar(c, "SELECT COUNT(*) FROM nida_imports WHERE user_id = :u AND "
                      "created_at > :s", u=user["id"], s=seit) or 0) >= ABRUFE_JE_STUNDE:
            raise HTTPException(429, "Zu viele Abrufe. Bitte in einer Stunde erneut "
                                     "versuchen.")
        frueher = row(c, "SELECT * FROM nida_imports WHERE user_id = :u AND "
                         "code_idx = :k ORDER BY created_at DESC LIMIT 1",
                      u=user["id"], k=idx)
        if frueher and frueher["status"] == "uebernommen":
            raise HTTPException(409, "Dieses Protokoll hast du bereits übernommen.")
        if frueher and not data.erneut:
            raise HTTPException(409, "Dieses Protokoll hast du schon einmal abgerufen. "
                                     "Ein weiterer Abruf zählt bei NIDAshare als "
                                     "weiterer Download.")
        massnahmen, medikamente, eigene = _katalog(c, user["id"])
        iid = new_id()
        q(c, "INSERT INTO nida_imports (id, user_id, code_idx, status, created_at, "
             "updated_at) VALUES (:i, :u, :k, 'abgerufen', :t, :t)",
          i=iid, u=user["id"], k=idx, t=now_iso())
        audit(c, user["id"], "nida_imports", iid, "abruf")

    # Der Abruf läuft außerhalb der Datenbanktransaktion: er kann bis zu
    # einer Minute dauern und soll die Datenbank nicht sperren.
    try:
        pdf = nidashare.abrufen(code)
        text = nidashare.text_aus_pdf(pdf)
        del pdf
        entwurf = nidashare.auslesen(text, massnahmen, medikamente, eigene)
        del text
    except nidashare.AbrufFehler as exc:
        log.warning("NIDAshare-Abruf fehlgeschlagen: %s", exc.art)
        with conn() as c:
            q(c, "UPDATE nida_imports SET status = 'fehler', updated_at = :t "
                 "WHERE id = :i", t=now_iso(), i=iid)
        raise HTTPException(exc.status, exc.text) from None
    return {"id": iid, **entwurf}


class EinsatzIn(BaseModel):
    datum: str
    uhrzeit: str
    naca: str | None = None
    einsatznummer: str | None = Field(default=None, max_length=40)


class MassnahmeIn(BaseModel):
    measure_id: str
    outcome: str = "erfolgreich"
    performer_role: str = "selbst durchgeführt"
    delegation: str | None = None
    zeit: str | None = None
    parameters: dict[str, str | float | int | None] = Field(default_factory=dict)
    begriff: str | None = Field(default=None, max_length=80)


class GabeIn(BaseModel):
    medication_id: str
    dose: float | None = Field(default=None, ge=0, le=100000)
    unit: str | None = None
    route: str | None = None
    zeit: str | None = None
    delegation: str | None = None


class UebernahmeIn(BaseModel):
    einsatz: EinsatzIn
    massnahmen: list[MassnahmeIn] = Field(default_factory=list, max_length=60)
    medikamente: list[GabeIn] = Field(default_factory=list, max_length=60)


def _offener_import(c, iid: str, uid: str) -> dict:
    imp = row(c, "SELECT * FROM nida_imports WHERE id = :i AND user_id = :u",
              i=iid, u=uid)
    if not imp:
        raise HTTPException(404, "Abruf nicht gefunden.")
    if imp["status"] != "abgerufen":
        raise HTTPException(409, "Dieser Abruf ist bereits abgeschlossen.")
    return imp


def _pruefen(data: UebernahmeIn) -> None:
    """Alles vorab prüfen, damit kein halber Einsatz entsteht."""
    e = data.einsatz
    if not DATUM.match(e.datum) or not ZEIT.match(e.uhrzeit):
        raise HTTPException(400, "Datum oder Uhrzeit des Einsatzes fehlt.")
    try:
        datetime.strptime(f"{e.datum} {e.uhrzeit}", "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(400, "Datum oder Uhrzeit ist ungültig.") from None
    if e.naca and e.naca not in NACA_LEVELS:
        raise HTTPException(400, "Unbekannter NACA-Wert.")
    if not data.massnahmen and not data.medikamente:
        raise HTTPException(400, "Wähle mindestens eine Maßnahme oder ein Medikament.")
    for m in data.massnahmen:
        if m.outcome not in OUTCOMES:
            raise HTTPException(400, "Unbekanntes Ergebnis.")
        if m.performer_role not in ROLLEN:
            raise HTTPException(400, "Unbekannte Rolle.")
        if m.delegation and m.delegation not in DELEGATIONS:
            raise HTTPException(400, "Unbekannte Durchführungsart.")
        if m.zeit and not ZEIT.match(m.zeit):
            raise HTTPException(400, "Ungültige Uhrzeit bei einer Maßnahme.")
    for g in data.medikamente:
        if g.unit and g.unit not in UNITS:
            raise HTTPException(400, "Unbekannte Einheit.")
        if g.route and g.route not in ROUTES:
            raise HTTPException(400, "Unbekannter Applikationsweg.")
        if g.delegation and g.delegation not in DELEGATIONS:
            raise HTTPException(400, "Unbekannte Durchführungsart.")
        if g.zeit and not ZEIT.match(g.zeit):
            raise HTTPException(400, "Ungültige Uhrzeit bei einem Medikament.")


@router.post("/nidashare/{iid}/uebernehmen")
def uebernehmen(iid: str, data: UebernahmeIn, user=Depends(require_writer)):
    _pruefen(data)
    with conn() as c:
        _offener_import(c, iid, user["id"])
        aktive_m = {r["id"] for r in rows(c, "SELECT id FROM measures WHERE active = 1")}
        aktive_w = {r["id"] for r in rows(c, "SELECT id FROM medications WHERE active = 1")}
    if any(m.measure_id not in aktive_m for m in data.massnahmen) or \
            any(g.medication_id not in aktive_w for g in data.medikamente):
        raise HTTPException(400, "Ein gewählter Katalogeintrag existiert nicht.")

    e = data.einsatz
    enc = records.create_encounter(records.EncounterIn(
        enc_date=e.datum, enc_time=e.uhrzeit, naca=e.naca,
        mission_number=(e.einsatznummer or "").strip() or None), user)
    try:
        for m in data.massnahmen:
            records.create_attempt(enc["id"], records.AttemptIn(
                measure_id=m.measure_id, outcome=m.outcome,
                performer_role=m.performer_role, delegation=m.delegation,
                performed_at=f"{e.datum}T{m.zeit or e.uhrzeit}",
                parameters=m.parameters), user)
        for g in data.medikamente:
            records.create_administration(enc["id"], records.AdministrationIn(
                medication_id=g.medication_id, dose=g.dose, unit=g.unit,
                route=g.route, delegation=g.delegation,
                administered_at=f"{e.datum}T{g.zeit or e.uhrzeit}"), user)
    except HTTPException:
        # Kein halber Einsatz: was schon angelegt ist, wieder entfernen.
        records.delete_encounter(enc["id"], user)
        raise

    with conn() as c:
        q(c, "UPDATE nida_imports SET status = 'uebernommen', encounter_id = :e, "
             "updated_at = :t WHERE id = :i", e=enc["id"], t=now_iso(), i=iid)
        # Eigene Zuordnungen merken: ein NIDA-Begriff, den die Person einem
        # anderen Katalogeintrag zugeordnet hat, gilt beim nächsten Mal.
        for m in data.massnahmen:
            begriff = (m.begriff or "").strip()
            if not begriff:
                continue
            if row(c, "SELECT id FROM import_begriffe WHERE user_id = :u AND "
                      "begriff = :b", u=user["id"], b=begriff):
                q(c, "UPDATE import_begriffe SET measure_id = :m WHERE user_id = :u "
                     "AND begriff = :b", m=m.measure_id, u=user["id"], b=begriff)
            else:
                q(c, "INSERT INTO import_begriffe (id, user_id, begriff, measure_id, "
                     "created_at) VALUES (:i, :u, :b, :m, :t)",
                  i=new_id(), u=user["id"], b=begriff, m=m.measure_id, t=now_iso())
        audit(c, user["id"], "nida_imports", iid, "uebernommen")
    return {"encounter_id": enc["id"]}


@router.post("/nidashare/{iid}/verwerfen")
def verwerfen(iid: str, user=Depends(require_writer)):
    with conn() as c:
        _offener_import(c, iid, user["id"])
        q(c, "UPDATE nida_imports SET status = 'verworfen', updated_at = :t "
             "WHERE id = :i", t=now_iso(), i=iid)
    return {"ok": True}
