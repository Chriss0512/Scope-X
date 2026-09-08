"""Gemeinsame Hilfen für die Qualitätsprüfung.

Jede Prüfung startet mit einer eigenen Datenbank. Ein Prüflauf, der von der
Reihenfolge seiner Prüfungen abhängt, ist wertlos.
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PASSWORD = "pruefdurchlauf2026"


def _reload_app(db_path: str):
    """Lädt die Anwendung mit einer frischen Datenbank neu.

    Engine und Sitzungen hängen an Modulzustand, deshalb reicht es nicht,
    nur die Umgebungsvariable zu setzen.
    """
    os.environ["SCOPEX_DATABASE_URL"] = f"sqlite:///{db_path}"
    for name in [m for m in list(sys.modules) if m.startswith("app")]:
        del sys.modules[name]
    return importlib.import_module("app.main")


@contextmanager
def fresh_db():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "scopex.db")
        os.environ["SCOPEX_DATABASE_URL"] = f"sqlite:///{path}"
        for name in [m for m in list(sys.modules) if m.startswith("app")]:
            del sys.modules[name]
        db = importlib.import_module("app.db")
        yield db


@contextmanager
def seeded_client():
    """Angemeldete Instanz mit realistischem Datenbestand."""
    from fastapi.testclient import TestClient
    with tempfile.TemporaryDirectory() as tmp:
        main = _reload_app(os.path.join(tmp, "scopex.db"))
        from app.security import _totp_at

        client = TestClient(main.app)
        client.__enter__()
        r = client.post("/api/auth/register", json={
            "username": "pruefer", "email": "pruefer@example.invalid",
            "password": PASSWORD, "first_name": "Prüf", "last_name": "Lauf",
            "qualification": "Notfallsanitäter*in"})
        secret = r.json()["totp"]["secret"]

        def totp():
            return _totp_at(secret, int(time.time()) // 30)

        client.post("/api/auth/totp/confirm", json={"code": totp()})

        measures = client.get("/api/catalog/measures").json()["measures"]
        meds = client.get("/api/catalog/medications").json()["medications"]
        zek = client.get("/api/catalog/complications").json()["complications"]

        for i in range(12):
            enc = client.post("/api/encounters", json={
                "enc_date": f"2026-0{(i % 9) + 1}-1{i % 9}",
                "enc_time": "10:00", "naca": ["II", "III", "IV", "V"][i % 4],
                "shift_code": "T1", "vehicle_id": "RTW 1-83-1"}).json()
            for m in measures[i % 5: (i % 5) + 3]:
                client.post(f"/api/encounters/{enc['id']}/attempts", json={
                    "measure_id": m["id"], "outcome": "erfolgreich",
                    "performer_role": "selbst durchgeführt",
                    "complications": ([{"id": zek[i % 20]["id"]}] if i % 3 == 0 else []),
                })
            for m in meds[i % 7: (i % 7) + 2]:
                client.post(f"/api/encounters/{enc['id']}/medications", json={
                    "medication_id": m["id"], "dose": 1, "unit": "mg",
                    "route": "intravenös", "outcome": "erfolgreich"})

        ctx = {"password": PASSWORD, "totp": totp, "secret": secret,
               "measures": measures, "medications": meds, "complications": zek}
        try:
            yield client, ctx
        finally:
            client.__exit__(None, None, None)


def role_matrix() -> list[str]:
    """Prüft jede schreibende Route gegen alle Rollen.

    Erwartet wird: ohne Anmeldung 401, mit unzureichender Rolle 403. Eine
    Route, die einfach ein leeres Ergebnis liefert statt zu verweigern,
    fällt hier durch.
    """
    from fastapi.testclient import TestClient
    violations: list[str] = []
    with seeded_client() as (admin, ctx):
        import app.main as main
        from app.security import _totp_at

        # Zweites Konto als Mitarbeiter
        inv = admin.post("/api/admin/invitations", json={
            "role": "user", "valid_days": 1, "totp_code": ctx["totp"]()}).json()
        member = TestClient(main.app)
        r = member.post("/api/auth/register", json={
            "username": "mitarbeiter", "password": PASSWORD,
            "invite_code": inv["code"]})
        msec = r.json()["totp"]["secret"]
        member.post("/api/auth/totp/confirm",
                    json={"code": _totp_at(msec, int(time.time()) // 30)})
        anon = TestClient(main.app)

        admin_only = [
            ("POST", "/api/catalog/medications", {"name": "Prüfstoff"}),
            ("POST", "/api/catalog/measures",
             {"name": "Prüfmaßnahme", "category": "A"}),
            ("POST", "/api/catalog/complications",
             {"code": "ZZ", "category": "Test", "label": "Prüf"}),
            ("GET", "/api/admin/users", None),
            ("GET", "/api/admin/invitations", None),
            ("GET", "/api/admin/status", None),
            ("PUT", "/api/legal", {"imprint_name": "Fremd"}),
            ("PUT", "/api/settings", {"edit_window_minutes": 500}),
        ]
        for method, path, body in admin_only:
            kw = {"json": body} if body is not None else {}
            r = anon.request(method, path, **kw)
            if r.status_code != 401:
                violations.append(f"{path} ohne Anmeldung → {r.status_code}")
            r = member.request(method, path, **kw)
            if r.status_code != 403:
                violations.append(f"{path} als Mitarbeiter → {r.status_code}")

        # Fremde Daten bleiben fremd, auch für Administratoren
        enc = member.post("/api/encounters", json={
            "enc_date": "2026-09-01", "enc_time": "10:00"}).json()
        r = admin.get(f"/api/encounters/{enc['id']}")
        if r.status_code != 404:
            violations.append(f"fremder Einsatz für Administrator → {r.status_code}")
        r = anon.get(f"/api/encounters/{enc['id']}")
        if r.status_code != 401:
            violations.append(f"fremder Einsatz ohne Anmeldung → {r.status_code}")
    return violations
