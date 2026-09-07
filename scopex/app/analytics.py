"""Kennzahlen.

Eine einzige Auswertungsfunktion versorgt Dashboard und PDF-Nachweis.
Damit koennen die beiden Darstellungen nicht auseinanderlaufen.

Alle Zahlen stammen ausschliesslich aus den lokal gespeicherten Daten.
Es findet keine medizinische Bewertung statt: gezaehlt wird, was
dokumentiert wurde.
"""
from __future__ import annotations

from datetime import date, timedelta

from .db import rows, scalar
from .seed import CATEGORY_LABELS, HARM_RELEVANT, NACA_LEVELS, OUTCOMES


def _in_clause(column: str, values, prefix: str, params: dict) -> str | None:
    """Baut eine parametrisierte IN-Bedingung. Werte werden nie in SQL
    interpoliert, nur Platzhalternamen."""
    values = [v for v in (values or []) if v not in (None, "")]
    if not values:
        return None
    names = []
    for i, v in enumerate(values):
        key = f"{prefix}{i}"
        params[key] = v
        names.append(f":{key}")
    return f"{column} IN ({', '.join(names)})"


def resolve_period(period: str | None, date_from: str | None,
                   date_to: str | None) -> tuple[str | None, str | None]:
    today = date.today()
    if period == "7d":
        return (today - timedelta(days=6)).isoformat(), today.isoformat()
    if period == "month":
        return today.replace(day=1).isoformat(), today.isoformat()
    if period == "quarter":
        first_month = 3 * ((today.month - 1) // 3) + 1
        return today.replace(month=first_month, day=1).isoformat(), today.isoformat()
    if period == "year":
        return today.replace(month=1, day=1).isoformat(), today.isoformat()
    if period == "all":
        return None, None
    return date_from or None, date_to or None


class Filters:
    def __init__(self, user_id: str, date_from=None, date_to=None, naca=None,
                 category=None, measure_id=None, outcome=None, delegation=None,
                 complication_id=None, medication_id=None, route=None,
                 harm=None, performer_role=None):
        self.user_id = user_id
        self.date_from = date_from
        self.date_to = date_to
        self.naca = naca or []
        self.category = category or []
        self.measure_id = measure_id or []
        self.outcome = outcome or []
        self.delegation = delegation or []
        self.complication_id = complication_id or []
        self.medication_id = medication_id or []
        self.route = route or []
        self.harm = harm or []
        self.performer_role = performer_role or []

    # -- Teilbedingungen -------------------------------------------------
    def encounter_sql(self, params: dict, alias: str = "e") -> str:
        parts = [f"{alias}.user_id = :u", f"{alias}.deleted_at IS NULL"]
        params["u"] = self.user_id
        if self.date_from:
            parts.append(f"{alias}.enc_date >= :df")
            params["df"] = self.date_from
        if self.date_to:
            parts.append(f"{alias}.enc_date <= :dt")
            params["dt"] = self.date_to
        naca = _in_clause(f"{alias}.naca", self.naca, "naca", params)
        if naca:
            parts.append(naca)
        return " AND ".join(parts)

    def attempt_sql(self, params: dict, alias: str = "a") -> str:
        parts = [self.encounter_sql(params), f"{alias}.deleted_at IS NULL"]
        for column, values, prefix in (
            (f"{alias}.measure_category", self.category, "cat"),
            (f"{alias}.measure_id", self.measure_id, "mid"),
            (f"{alias}.outcome", self.outcome, "out"),
            (f"{alias}.delegation", self.delegation, "del"),
            (f"{alias}.performer_role", self.performer_role, "prole"),
        ):
            clause = _in_clause(column, values, prefix, params)
            if clause:
                parts.append(clause)
        comp = _in_clause("ac.complication_id", self.complication_id, "comp", params)
        if comp:
            parts.append(
                f"EXISTS (SELECT 1 FROM attempt_complications ac "
                f"WHERE ac.attempt_id = {alias}.id AND {comp})")
        harm = _in_clause("ah.patient_harm", self.harm, "harm", params)
        if harm:
            parts.append(
                f"EXISTS (SELECT 1 FROM attempt_complications ah "
                f"WHERE ah.attempt_id = {alias}.id AND {harm})")
        return " AND ".join(parts)

    def admin_sql(self, params: dict, alias: str = "m") -> str:
        parts = [self.encounter_sql(params), f"{alias}.deleted_at IS NULL"]
        for column, values, prefix in (
            (f"{alias}.medication_id", self.medication_id, "medid"),
            (f"{alias}.route", self.route, "route"),
            (f"{alias}.delegation", self.delegation, "del"),
        ):
            clause = _in_clause(column, values, prefix, params)
            if clause:
                parts.append(clause)
        comp = _in_clause("mc.complication_id", self.complication_id, "comp", params)
        if comp:
            parts.append(
                f"EXISTS (SELECT 1 FROM medication_complications mc "
                f"WHERE mc.administration_id = {alias}.id AND {comp})")
        harm = _in_clause("mh.patient_harm", self.harm, "harm", params)
        if harm:
            parts.append(
                f"EXISTS (SELECT 1 FROM medication_complications mh "
                f"WHERE mh.administration_id = {alias}.id AND {harm})")
        return " AND ".join(parts)


_ATT_JOIN = "FROM measure_attempts a JOIN encounters e ON e.id = a.encounter_id"
_ADM_JOIN = "FROM medication_administrations m JOIN encounters e ON e.id = m.encounter_id"


def compute(c, f: Filters) -> dict:
    p_enc: dict = {}
    enc_where = f.encounter_sql(p_enc)
    p_att: dict = {}
    att_where = f.attempt_sql(p_att)
    p_adm: dict = {}
    adm_where = f.admin_sql(p_adm)

    encounters = scalar(c, f"SELECT COUNT(*) FROM encounters e WHERE {enc_where}",
                        **p_enc) or 0
    attempts = scalar(c, f"SELECT COUNT(*) {_ATT_JOIN} WHERE {att_where}",
                      **p_att) or 0
    administrations = scalar(c, f"SELECT COUNT(*) {_ADM_JOIN} WHERE {adm_where}",
                             **p_adm) or 0

    by_category = rows(c, f"""
        SELECT a.measure_category AS key, COUNT(*) AS n
        {_ATT_JOIN} WHERE {att_where}
        GROUP BY a.measure_category ORDER BY n DESC""", **p_att)
    for r in by_category:
        r["label"] = CATEGORY_LABELS.get(r["key"], r["key"])

    by_measure = rows(c, f"""
        SELECT a.measure_name AS name, a.measure_category AS category,
               COUNT(*) AS n,
               SUM(CASE WHEN a.outcome = 'erfolgreich' THEN 1 ELSE 0 END) AS ok
        {_ATT_JOIN} WHERE {att_where}
        GROUP BY a.measure_name, a.measure_category ORDER BY n DESC""", **p_att)

    outcome_rows = rows(c, f"""
        SELECT a.outcome AS key, COUNT(*) AS n
        {_ATT_JOIN} WHERE {att_where} GROUP BY a.outcome""", **p_att)
    outcomes = {o: 0 for o in OUTCOMES}
    for r in outcome_rows:
        outcomes[r["key"]] = r["n"]

    by_role = rows(c, f"""
        SELECT COALESCE(a.performer_role, 'ohne Angabe') AS key, COUNT(*) AS n,
               SUM(CASE WHEN a.outcome = 'erfolgreich' THEN 1 ELSE 0 END) AS ok
        {_ATT_JOIN} WHERE {att_where}
        GROUP BY a.performer_role ORDER BY n DESC""", **p_att)

    delegation_rows = rows(c, f"""
        SELECT COALESCE(a.delegation, 'ohne Angabe') AS key, COUNT(*) AS n
        {_ATT_JOIN} WHERE {att_where} GROUP BY a.delegation ORDER BY n DESC""",
        **p_att)

    zek_attempts = scalar(c, f"""
        SELECT COUNT(*) FROM attempt_complications ac
        JOIN measure_attempts a ON a.id = ac.attempt_id
        JOIN encounters e ON e.id = a.encounter_id
        WHERE {att_where}""", **p_att) or 0
    zek_meds = scalar(c, f"""
        SELECT COUNT(*) FROM medication_complications mc
        JOIN medication_administrations m ON m.id = mc.administration_id
        JOIN encounters e ON e.id = m.encounter_id
        WHERE {adm_where}""", **p_adm) or 0

    top_zek = rows(c, f"""
        SELECT code, label, COUNT(*) AS n FROM (
            SELECT ac.code AS code, ac.label AS label
            FROM attempt_complications ac
            JOIN measure_attempts a ON a.id = ac.attempt_id
            JOIN encounters e ON e.id = a.encounter_id
            WHERE {att_where}
        ) GROUP BY code, label ORDER BY n DESC, code LIMIT 15""", **p_att)

    by_medication = rows(c, f"""
        SELECT m.medication_name AS name, COUNT(*) AS n
        {_ADM_JOIN} WHERE {adm_where}
        GROUP BY m.medication_name ORDER BY n DESC""", **p_adm)

    by_route = rows(c, f"""
        SELECT COALESCE(m.route, 'ohne Angabe') AS name, COUNT(*) AS n
        {_ADM_JOIN} WHERE {adm_where}
        GROUP BY m.route ORDER BY n DESC""", **p_adm)

    timeline = rows(c, f"""
        SELECT substr(e.enc_date, 1, 7) AS bucket, COUNT(*) AS n
        {_ATT_JOIN} WHERE {att_where}
        GROUP BY bucket ORDER BY bucket""", **p_att)

    naca_encounters = rows(c, f"""
        SELECT COALESCE(e.naca, 'ohne Angabe') AS key, COUNT(*) AS n
        FROM encounters e WHERE {enc_where}
        GROUP BY e.naca""", **p_enc)
    naca_attempts = rows(c, f"""
        SELECT COALESCE(e.naca, 'ohne Angabe') AS key, COUNT(*) AS n
        {_ATT_JOIN} WHERE {att_where} GROUP BY e.naca""", **p_att)
    naca_meds = rows(c, f"""
        SELECT COALESCE(e.naca, 'ohne Angabe') AS key, COUNT(*) AS n
        {_ADM_JOIN} WHERE {adm_where} GROUP BY e.naca""", **p_adm)
    naca_zek = rows(c, f"""
        SELECT COALESCE(e.naca, 'ohne Angabe') AS key, COUNT(*) AS n
        FROM attempt_complications ac
        JOIN measure_attempts a ON a.id = ac.attempt_id
        JOIN encounters e ON e.id = a.encounter_id
        WHERE {att_where} GROUP BY e.naca""", **p_att)

    def _naca_table() -> list[dict]:
        keys = NACA_LEVELS + ["ohne Angabe"]
        enc_map = {r["key"]: r["n"] for r in naca_encounters}
        att_map = {r["key"]: r["n"] for r in naca_attempts}
        med_map = {r["key"]: r["n"] for r in naca_meds}
        zek_map = {r["key"]: r["n"] for r in naca_zek}
        out = []
        for k in keys:
            n = enc_map.get(k, 0)
            if not (n or att_map.get(k) or med_map.get(k)):
                continue
            out.append({
                "naca": k, "encounters": n,
                "share": round(100 * n / encounters, 1) if encounters else 0.0,
                "attempts": att_map.get(k, 0),
                "medications": med_map.get(k, 0),
                "complications": zek_map.get(k, 0),
            })
        return out

    # Die Auswertungskategorien werden hier berechnet und nicht gespeichert.
    # Ergebnis und ZEK-Zuordnung koennen sich dadurch nicht widersprechen.
    # Die Unterabfragen nutzen bewusst den Alias zc, weil att_where je nach
    # Filter bereits ac und ah belegt.
    _zc = "FROM attempt_complications zc WHERE zc.attempt_id = a.id"
    derived_raw = rows(c, f"""
        SELECT a.outcome AS outcome,
          CASE WHEN (SELECT COUNT(*) {_zc}) > 0 THEN 1 ELSE 0 END AS has_zek,
          CASE WHEN (SELECT COUNT(*) {_zc} AND zc.relation = 'ursächlich') > 0
               THEN 1 ELSE 0 END AS causal,
          COUNT(*) AS n
        {_ATT_JOIN} WHERE {att_where}
        GROUP BY outcome, has_zek, causal""", **p_att)

    buckets = {
        "erfolgreich_ohne_zek": 0, "erfolgreich_mit_zek": 0,
        "abgebrochen_ursaechlich": 0, "abgebrochen_sonst": 0,
        "fehlgeschlagen_ursaechlich": 0, "fehlgeschlagen_begleitend": 0,
        "fehlgeschlagen_ohne_zek": 0,
    }
    for r in derived_raw:
        outcome, has_zek, causal, n = r["outcome"], r["has_zek"], r["causal"], r["n"]
        if outcome == "erfolgreich":
            key = "erfolgreich_mit_zek" if has_zek else "erfolgreich_ohne_zek"
        elif outcome == "abgebrochen":
            key = "abgebrochen_ursaechlich" if causal else "abgebrochen_sonst"
        else:  # fehlgeschlagen, einschliesslich abgeloester Altwerte
            key = ("fehlgeschlagen_ursaechlich" if causal
                   else "fehlgeschlagen_begleitend" if has_zek
                   else "fehlgeschlagen_ohne_zek")
        buckets[key] += n

    DERIVED_LABELS = [
        ("erfolgreich_ohne_zek", "Erfolgreich, ohne Komplikationen"),
        ("erfolgreich_mit_zek", "Erfolgreich, mit Komplikationen"),
        ("abgebrochen_sonst", "Abgebrochen, ohne ursächliche Komplikation"),
        ("abgebrochen_ursaechlich", "Abgebrochen, Komplikation ursächlich"),
        ("fehlgeschlagen_ohne_zek", "Fehlgeschlagen, ohne Komplikationen"),
        ("fehlgeschlagen_begleitend", "Fehlgeschlagen, Komplikation begleitend"),
        ("fehlgeschlagen_ursaechlich", "Fehlgeschlagen, Komplikation ursächlich"),
    ]
    derived = [{
        "key": key, "label": label, "n": buckets[key],
        "share": round(100 * buckets[key] / attempts, 1) if attempts else 0.0,
    } for key, label in DERIVED_LABELS]

    harm_in = ", ".join(f"'{h}'" for h in HARM_RELEVANT)
    harm_attempts = rows(c, f"""
        SELECT zc.patient_harm AS level, COUNT(DISTINCT a.id) AS n
        FROM attempt_complications zc
        JOIN measure_attempts a ON a.id = zc.attempt_id
        JOIN encounters e ON e.id = a.encounter_id
        WHERE {att_where} AND zc.patient_harm IN ({harm_in})
        GROUP BY zc.patient_harm""", **p_att)
    harm_meds = rows(c, f"""
        SELECT mz.patient_harm AS level, COUNT(DISTINCT m.id) AS n
        FROM medication_complications mz
        JOIN medication_administrations m ON m.id = mz.administration_id
        JOIN encounters e ON e.id = m.encounter_id
        WHERE {adm_where} AND mz.patient_harm IN ({harm_in})
        GROUP BY mz.patient_harm""", **p_adm)

    harm = {level: {"attempts": 0, "medications": 0} for level in HARM_RELEVANT}
    for r in harm_attempts:
        harm.setdefault(r["level"], {"attempts": 0, "medications": 0})
        harm[r["level"]]["attempts"] = r["n"]
    for r in harm_meds:
        harm.setdefault(r["level"], {"attempts": 0, "medications": 0})
        harm[r["level"]]["medications"] = r["n"]

    graded = sum(outcomes.values())
    zek_total = zek_attempts + zek_meds
    documented = attempts + administrations

    return {
        "period": {"from": f.date_from, "to": f.date_to},
        "encounters": encounters,
        "attempts": attempts,
        "administrations": administrations,
        "by_category": by_category,
        "by_measure": by_measure,
        "outcomes": outcomes,
        # Nenner ist immer die Gesamtzahl dokumentierter Massnahmen, damit die
        # Quoten sich zu 100 Prozent addieren und kein verstecktes Kriterium
        # im Nenner steckt.
        "success_rate": round(100 * outcomes["erfolgreich"] / graded, 1) if graded else None,
        "failure_rate": round(100 * outcomes["fehlgeschlagen"] / graded, 1) if graded else None,
        "abort_rate": round(100 * outcomes["abgebrochen"] / graded, 1) if graded else None,
        "derived": derived,
        "patient_harm": harm,
        "by_delegation": delegation_rows,
        "by_role": by_role,
        "complications": {
            "total": zek_total,
            "on_attempts": zek_attempts,
            "on_medications": zek_meds,
            "rate": round(100 * zek_total / documented, 1) if documented else None,
            "top": top_zek,
        },
        "by_medication": by_medication,
        "by_route": by_route,
        "timeline": timeline,
        "naca": _naca_table(),
    }


def detail_rows(c, f: Filters, limit: int = 2000) -> list[dict]:
    """Einzeleintraege fuer den detaillierten Nachweis."""
    params: dict = {}
    where = f.attempt_sql(params)
    params["lim"] = limit
    attempts = rows(c, f"""
        SELECT e.enc_date, e.enc_time, e.mission_number, e.naca,
               a.id, a.measure_name, a.measure_category, a.outcome,
               a.delegation, a.performer_role, a.performer_qualification,
               a.performed_at
        {_ATT_JOIN} WHERE {where}
        ORDER BY e.enc_date, e.enc_time, a.performed_at LIMIT :lim""", **params)
    for a in attempts:
        a["parameters"] = rows(
            c, "SELECT label, value_text AS value, unit "
               "FROM measure_attempt_parameters WHERE attempt_id = :a", a=a["id"])
        a["complications"] = rows(
            c, "SELECT code, label, relation, patient_harm "
               "FROM attempt_complications WHERE attempt_id = :a ORDER BY code",
            a=a["id"])
    return attempts


def detail_medications(c, f: Filters, limit: int = 2000) -> list[dict]:
    params: dict = {}
    where = f.admin_sql(params)
    params["lim"] = limit
    meds = rows(c, f"""
        SELECT e.enc_date, e.enc_time, e.mission_number, e.naca,
               m.id, m.medication_name, m.preparation_name, m.dose, m.unit,
               m.route, m.delegation, m.administered_at
        {_ADM_JOIN} WHERE {where}
        ORDER BY e.enc_date, e.enc_time, m.administered_at LIMIT :lim""", **params)
    for m in meds:
        m["complications"] = rows(
            c, "SELECT code, label, relation, patient_harm "
               "FROM medication_complications WHERE administration_id = :a "
               "ORDER BY code", a=m["id"])
    return meds
