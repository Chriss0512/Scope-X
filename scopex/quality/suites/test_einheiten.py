"""Blutzucker in mg/dl und mmol/l (4.7.0).

Gespeichert wird immer mg/dl, eingegeben werden darf beides. Geprüft wird
die Umrechnung in beide Richtungen, die Plausibilitätsgrenzen, die
Einstellung der bevorzugten Einheit und die Ausgabe in CSV und PDF.
"""
import os
import sys
import time as _t

os.environ["SCOPEX_DATABASE_URL"] = "sqlite:////tmp/scopex_q_einheiten.db"
if os.path.exists("/tmp/scopex_q_einheiten.db"):
    os.remove("/tmp/scopex_q_einheiten.db")
sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parents[2].as_posix())

from fastapi.testclient import TestClient

from app import einheiten
from app.main import app
from app.security import _totp_at
from quality import nachweis  # noqa: F401,E402


def check(name, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + name + (" :: " + str(extra) if not cond else ""))
    if not cond:
        sys.exit(1)


# --- Umrechnung ohne Server ----------------------------------------------
check("100 mg/dl bleiben 100", einheiten.glukose_in_mgdl("100", "mg/dl") == 100)
check("5,5 mmol/l sind 99 mg/dl", einheiten.glukose_in_mgdl("5,5", "mmol/l") == 99)
check("2,2 mmol/l sind 40 mg/dl", einheiten.glukose_in_mgdl(2.2, "mmol/l") == 40)
check("Ohne Einheit gilt mg/dl", einheiten.glukose_in_mgdl("80", None) == 80)
check("99 mg/dl als mmol/l", einheiten.mmol_text(99) == "5,5 mmol/l", einheiten.mmol_text(99))
check("Parametertext nennt beide Einheiten",
      einheiten.parameter_text({"label": "Wert", "value": "99", "unit": "mg/dl"})
      == "Wert: 99 mg/dl (5,5 mmol/l)")
check("Andere Einheiten bleiben unverändert",
      einheiten.parameter_text({"label": "Energie", "value": "200", "unit": "J"})
      == "Energie: 200 J")

# --- Mit Server ------------------------------------------------------------
c = TestClient(app)
c.__enter__()
r = c.post("/api/auth/register", json={
    "username": "lea", "email": "bz@example.invalid", "password": "einsatzprotokoll2026",
    "first_name": "Lea", "last_name": "Sander", "qualification": "Notfallsanitäter*in"})
secret = r.json()["totp"]["secret"]
c.post("/api/auth/totp/confirm", json={"code": _totp_at(secret, int(_t.time()) // 30)})

cat = c.get("/api/catalog/measures").json()["measures"]
bz = next(m for m in cat if m["name"] == "Blutzuckermessung")
feld = bz["parameters"][0]
check("Blutzucker hat den Typ glucose", feld["type"] == "glucose" and feld["unit"] == "mg/dl",
      feld)

check("Voreinstellung mg/dl", c.get("/api/settings").json()["blutzucker_einheit"] == "mg/dl")
r = c.put("/api/settings", json={"blutzucker_einheit": "mmol/l"})
check("Bevorzugte Einheit mmol/l", r.status_code == 200 and
      r.json()["blutzucker_einheit"] == "mmol/l", r.text[:150])
check("Unbekannte Einheit in den Einstellungen abgelehnt",
      c.put("/api/settings", json={"blutzucker_einheit": "g/l"}).status_code == 400)
check("Unbekannte Darstellung abgelehnt",
      c.put("/api/settings", json={"theme": "lila"}).status_code == 400)

enc = c.post("/api/encounters", json={"enc_date": "2026-11-01", "enc_time": "10:00",
                                      "naca": "III"}).json()


def messen(wert, einheit=None):
    params = {feld["key"]: wert}
    if einheit:
        params[feld["key"] + "__einheit"] = einheit
    return c.post(f"/api/encounters/{enc['id']}/attempts", json={
        "measure_id": bz["id"], "outcome": "erfolgreich", "parameters": params})


r = messen("5,5", "mmol/l")
check("Eingabe in mmol/l gespeichert", r.status_code == 200, r.text[:200])
p = r.json()["attempts"][-1]["parameters"]
check("… als 99 mg/dl", p == [{"key": "wert", "label": "Wert", "value": "99",
                              "unit": "mg/dl"}], p)
check("Die Einheit ist kein eigener Parameter", len(p) == 1)

r = messen("142", "mg/dl")
check("Eingabe in mg/dl", r.json()["attempts"][-1]["parameters"][0]["value"] == "142")
r = messen("60")
check("Ohne Einheit mg/dl", r.json()["attempts"][-1]["parameters"][0]["value"] == "60")

check("Text statt Zahl abgelehnt", messen("hoch", "mg/dl").status_code == 400)
check("NaN und Unendlich abgelehnt", messen("nan", "mg/dl").status_code == 400
      and messen("inf", "mmol/l").status_code == 400)
check("Unbekannte Einheit abgelehnt", messen("5", "mg/l").status_code == 400)
r = messen("99", "mmol/l")
check("mg/dl-Wert mit mmol/l verwechselt: abgelehnt mit Hinweis",
      r.status_code == 400 and "Einheit" in r.json()["detail"], r.text[:200])
check("Unplausibel kleiner Wert abgelehnt", messen("0", "mg/dl").status_code == 400)
check("mmol/l-Wert mit mg/dl verwechselt: abgelehnt", messen("5,5", "mg/dl").status_code == 400)

csv = c.get("/api/exports/csv").text
check("CSV nennt beide Einheiten", "99 mg/dl (5,5 mmol/l)" in csv, csv[:400])
r = c.get("/api/exports/pdf", params={"detailed": "true"})
check("PDF mit Blutzucker erzeugt", r.status_code == 200 and r.content[:4] == b"%PDF",
      r.status_code)

print("\nEinheiten: alle Prüfungen bestanden.")
