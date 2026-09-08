import os
import sys
import time as _t

os.environ["SCOPEX_DATABASE_URL"] = "sqlite:////tmp/scopex_q_doc.db"
if os.path.exists("/tmp/scopex_q_doc.db"): os.remove("/tmp/scopex_q_doc.db")
sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parents[2].as_posix())
from fastapi.testclient import TestClient

from app.main import app
from app.security import _totp_at


def check(n, c, e=""):
    print(("  OK   " if c else "  FAIL ") + n + (" :: "+str(e) if not c else ""))
    if not c: sys.exit(1)
def code(sec): return _totp_at(sec, int(_t.time()) // 30)

c = TestClient(app); c.__enter__()
r = c.post("/api/auth/register", json={"username":"chris","email":"info@cd-faust.de",
    "password":"einsatzprotokoll2026","qualification":"Notfallsanitäter*in"})
sec = r.json()["totp"]["secret"]
c.post("/api/auth/totp/confirm", json={"code": code(sec)})

const = c.get("/api/catalog/constants").json()
check("Geschlechtsneutrale Qualifikationen",
      "Notfallsanitäter*in" in const["qualifications"] and
      "Ärztin / Arzt" in const["qualifications"], const["qualifications"])
check("DIVI-Etiketten vollständig definiert",
      all(g in const["divi_labels"] for g in const["divi_groups"]) and
      all({"bg","fg","pattern","slug"} <= set(v) for v in const["divi_labels"].values()),
      list(const["divi_labels"].values())[:1])
check("DIVI-Gruppen vorhanden", len(const["divi_groups"]) == 14, const["divi_groups"])

cat = c.get("/api/catalog/measures").json()["measures"]
iv = next(m for m in cat if m["name"] == "Intravenöser Zugang")
ort = next(p for p in iv["parameters"] if p["key"] == "ort")
check("Punktionsort als Auswahl", ort["type"] == "select" and
      "V. jugularis externa links" in ort["options"], ort)

meds = c.get("/api/catalog/medications").json()["medications"]
adr = next(m for m in meds if m["name"] == "Adrenalin")
check("DIVI-Gruppe vorbelegt",
      adr["divi_group"] == "Vasopressoren / Kreislauf (violett)", adr["divi_group"])
roc = next(m for m in meds if m["name"] == "Rocuronium")
suc = next(m for m in meds if m["name"] == "Succinylcholin")
nal = next(m for m in meds if m["name"] == "Naloxon")
check("Relaxanzien nach Wirkmechanismus getrennt",
      "nichtdepolarisierend" in roc["divi_group"] and
      "depolarisierend (rot)" in suc["divi_group"], (roc["divi_group"], suc["divi_group"]))
check("Antagonist trägt die Streifen seiner Bezugsgruppe",
      nal["divi_group"] == "Opioid-Antagonisten (blau/weiß gestreift)", nal["divi_group"])
amio = next(m for m in meds if m["name"] == "Amiodaron")
check("Unklare Zuordnung bleibt offen", amio["divi_group"] is None, amio["divi_group"])

r = c.patch(f"/api/catalog/medications/{amio['id']}", json={
    "divi_group": "Diverse (weiß)", "trade_names": ["Cordarex", "Amiohexal"]})
check("Gruppe und Handelsnamen pflegbar", r.status_code == 200, r.text[:120])
meds = c.get("/api/catalog/medications").json()["medications"]
amio = next(m for m in meds if m["name"] == "Amiodaron")
check("Handelsnamen als Liste", amio["trade_names"] == ["Cordarex", "Amiohexal"], amio)

# --- Einsatz mit Schicht und Fahrzeug -----------------------------------
r = c.post("/api/encounters", json={"enc_date":"2026-09-01","enc_time":"14:32",
    "mission_number":"2026-114233","naca":"IV","shift_code":"T1",
    "vehicle_id":"RTW 1-83-1"})
check("Schicht und Fahrzeug gespeichert",
      r.json()["shift_code"] == "T1" and r.json()["vehicle_id"] == "RTW 1-83-1", r.text[:150])
enc = r.json()

# --- Medikament mit Ergebnis, Nebenwirkung, Folge ------------------------
zek = c.get("/api/catalog/complications").json()["complications"]
hypo = next(z for z in zek if z["code"] == "18")
r = c.post(f"/api/encounters/{enc['id']}/medications", json={
    "medication_id": adr["id"], "dose": 1, "unit": "mg", "route": "intravenös",
    "outcome": "erfolgreich", "adverse_effect": "Tachykardie nach Gabe",
    "follow_up": "Frequenzkontrolle, Volumengabe",
    "complications": [{"id": hypo["id"], "relation": "begleitend",
                       "patient_harm": "kein Schaden erkennbar"}]})
check("Medikament mit Verlauf", r.status_code == 200, r.text[:200])
m = r.json()["medications"][0]
check("Ergebnis gespeichert", m["outcome"] == "erfolgreich", m.get("outcome"))
check("Nebenwirkung gespeichert", m["adverse_effect"] == "Tachykardie nach Gabe")
check("Folgeintervention gespeichert", m["follow_up"].startswith("Frequenz"))
r = c.post(f"/api/encounters/{enc['id']}/medications", json={
    "medication_id": adr["id"], "outcome": "erfunden"})
check("Unbekanntes Ergebnis abgelehnt", r.status_code == 400)

# --- ZEK am Einsatz ------------------------------------------------------
org = next(z for z in zek if z["code"] == "95")
r = c.put(f"/api/encounters/{enc['id']}/complications", json={
    "complications": [{"id": org["id"], "relation": "begleitend",
                       "patient_harm": "kein Schaden erkennbar"}]})
check("ZEK am Einsatz", r.status_code == 200 and
      r.json()["complications"][0]["code"] == "95", r.text[:200])
st = c.get("/api/stats?period=all").json()
check("Einsatz-ZEK zählt mit", st["complications"]["on_encounters"] == 1 and
      st["complications"]["total"] == 2, st["complications"])
check("Medikamentenergebnisse ausgewertet",
      st["medication_outcomes"][0]["key"] == "erfolgreich", st["medication_outcomes"])
check("Nebenwirkungen gezählt", st["adverse_effects"] == 1, st["adverse_effects"])
check("Folgeinterventionen gezählt", st["follow_ups"] == 1, st["follow_ups"])

# --- Nachträgliches Bearbeiten ------------------------------------------
r = c.patch(f"/api/administrations/{m['id']}", json={
    "outcome": "abgebrochen", "adverse_effect": "korrigiert"})
check("Medikamentengabe bearbeitbar", r.status_code == 200, r.text[:150])
mm = r.json()["medications"][0]
check("Änderung übernommen", mm["outcome"] == "abgebrochen" and
      mm["adverse_effect"] == "korrigiert", mm)

# --- Eine Frist für den ganzen Einsatz ----------------------------------
full = c.get(f"/api/encounters/{enc['id']}").json()
check("Eintrag erbt die Frist des Einsatzes",
      full["medications"][0]["lock"] == full["lock"], full["medications"][0]["lock"])
from datetime import datetime, timedelta, timezone

from app.db import conn, q

old = (datetime.now(timezone.utc) - timedelta(hours=5)).replace(microsecond=0).isoformat()
with conn() as cx:
    q(cx, "UPDATE encounters SET created_at = :t", t=old)
r = c.patch(f"/api/administrations/{m['id']}", json={"outcome": "erfolgreich"})
check("Gesperrter Einsatz sperrt auch seine Einträge", r.status_code == 409, r.status_code)
r = c.put(f"/api/encounters/{enc['id']}/complications", json={"complications": []})
check("Und die Einsatz-ZEK", r.status_code == 409, r.status_code)

# --- Gerätezustand -------------------------------------------------------
r = c.get("/api/auth/device")
check("Gerätezustand ohne Cookie", r.status_code == 200 and r.json()["known"] is False)
dev = TestClient(app)
dev.post("/api/auth/login", json={"username":"chris","password":"einsatzprotokoll2026",
    "totp_code": code(sec), "remember_device": True})
r = dev.get("/api/auth/device")
check("Gerätezustand mit Cookie", r.json()["known"] and
      r.json()["username"] == "chris", r.text[:120])

# --- Sperrmail bei Fehlversuchen -----------------------------------------
sent = {}
import app.mailer as M

M.send = lambda to, s_, b: sent.update(to=to, body=b) or True
bad = TestClient(app)
for i in range(8):
    bad.post("/api/auth/login", json={"username":"chris","password":"falsch"})
check("Sperrmail verschickt", sent.get("to") == "info@cd-faust.de", sent.get("to"))
check("Mail nennt keine Herkunft",
      "IP" not in sent["body"] and "127.0.0.1" not in sent["body"])
sent.clear()
for i in range(8):
    bad.post("/api/auth/login", json={"username":"gibtesnicht","password":"falsch"})
check("Für unbekannte Kennung keine Mail", "to" not in sent)

r = c.get("/api/exports/pdf?period=all&detailed=true")
check("PDF weiterhin erzeugbar", r.status_code == 200 and r.content[:4] == b"%PDF")
print("\nUpdate 3: alle Prüfungen bestanden.")
