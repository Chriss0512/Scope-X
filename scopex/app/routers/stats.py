"""Dashboard."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..analytics import Filters, compute, resolve_period
from ..core import current_user
from ..db import conn, rows

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats")
def stats(
    period: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    naca: list[str] = Query(default=[]),
    category: list[str] = Query(default=[]),
    measure_id: list[str] = Query(default=[]),
    outcome: list[str] = Query(default=[]),
    delegation: list[str] = Query(default=[]),
    complication_id: list[str] = Query(default=[]),
    medication_id: list[str] = Query(default=[]),
    route: list[str] = Query(default=[]),
    harm: list[str] = Query(default=[]),
    performer_role: list[str] = Query(default=[]),
    user=Depends(current_user),
):
    df, dt = resolve_period(period, date_from, date_to)
    f = Filters(user["id"], df, dt, naca, category, measure_id, outcome,
                delegation, complication_id, medication_id, route, harm,
                performer_role)
    with conn() as c:
        return compute(c, f)


@router.get("/audit")
def audit_log(entity_id: str | None = None, limit: int = 100,
              user=Depends(current_user)):
    """Einsehbares Aenderungsprotokoll. Nur lesend, es gibt keinen
    Endpunkt zum Loeschen oder Aendern von Audit-Eintraegen."""
    with conn() as c:
        if entity_id:
            items = rows(c, "SELECT * FROM audit_log WHERE user_id = :u "
                            "AND entity_id = :e ORDER BY at DESC LIMIT :l",
                         u=user["id"], e=entity_id, l=min(limit, 500))
        else:
            items = rows(c, "SELECT * FROM audit_log WHERE user_id = :u "
                            "ORDER BY at DESC LIMIT :l",
                         u=user["id"], l=min(limit, 500))
    return {"entries": items}
