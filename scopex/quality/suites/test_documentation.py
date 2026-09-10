import json
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
check("DIVI-Gruppen vorhanden", len(const["divi_groups"]) == 22, const["divi_groups"])

cat = c.get("/api/catalog/measures").json()["measures"]
iv = next(m for m in cat if m["name"] == "Intravenöser Zugang")
ort = next(p for p in iv["parameters"] if p["key"] == "ort")
check("Punktionsort als Auswahl", ort["type"] == "select" and
      "V. jugularis externa links" in ort["options"], ort)

meds = c.get("/api/catalog/medications").json()["medications"]
adr = next(m for m in meds if m["name"] == "Adrenalin")
check("DIVI-Gruppe vorbelegt",
      adr["divi_group"] == "Vasopressoren", adr["divi_group"])
roc = next(m for m in meds if m["name"] == "Rocuronium")
suc = next(m for m in meds if m["name"] == "Succinylcholin")
nal = next(m for m in meds if m["name"] == "Naloxon")
check("Relaxanzien zugeordnet",
      roc["divi_group"] == "Muskelrelaxantien" and
      suc["divi_group"] == "Muskelrelaxantien", (roc["divi_group"], suc["divi_group"]))
check("Antagonist in eigener Gruppe",
      nal["divi_group"] == "Opioid-Antagonisten", nal["divi_group"])
amio = next(m for m in meds if m["name"] == "Amiodaron")
check("Antiarrhythmikum zugeordnet", amio["divi_group"] == "Antiarrhythmika", amio["divi_group"])

r = c.patch(f"/api/catalog/medications/{amio['id']}", json={
    "divi_group": "Verschiedene Medikamente", "trade_names": ["Cordarex", "Amiohexal"]})
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

# --- Update 4: Etiketten und Passkeys -----------------------------------
const = c.get("/api/catalog/constants").json()
check("Alle 22 Etikettengruppen definiert", len(const["divi_groups"]) == 22,
      len(const["divi_groups"]))
meds_all = c.get("/api/catalog/medications").json()["medications"]
ohne = [m["name"] for m in meds_all if not m["divi_group"]]
check("Jeder ausgelieferte Wirkstoff hat eine Gruppe", not ohne, ohne[:5])
by_name = {m["name"]: m["divi_group"] for m in meds_all}
erwartet = {
    "Propofol": "Hypnotika", "Midazolam": "Benzodiazepine",
    "Flumazenil": "Benzodiazepin-Antagonisten", "Morphin": "Opiate / Opioide",
    "Naloxon": "Opioid-Antagonisten", "Atropin": "Anticholinergika",
    "Adenosin": "Antiarrhythmika", "Phenytoin": "Antikonvulsiva",
    "Salbutamol": "Bronchodilatatoren", "Dobutamin": "Inodilatatoren",
    "Heparin": "Heparin", "Natriumchlorid 0,9 %": "Elektrolyte",
    "Nitroglycerin": "Antihypertonika / Vasodilatantien",
    "Metamizol": "Verschiedene Medikamente",
}
falsch = {k: (by_name.get(k), v) for k, v in erwartet.items() if by_name.get(k) != v}
check("Zuordnung entspricht der DIVI-Tabelle", not falsch, falsch)
check("Antagonisten tragen Schrägstreifen",
      const["divi_labels"]["Opioid-Antagonisten"]["pattern"] == "stripes" and
      const["divi_labels"]["Muskelrelaxans-Antagonisten"]["pattern"] == "stripes")

# Passkeys
r = c.get("/api/auth/passkeys")
check("Passkey-Liste abrufbar", r.status_code == 200 and
      r.json()["passkeys"] == [], r.text[:120])
r = c.post("/api/auth/passkeys/register/options")
check("Ohne Basis-Adresse keine Passkeys", r.status_code == 503, r.status_code)
os.environ["SCOPEX_BASE_URL"] = "https://scopex.example.de"
r = c.post("/api/auth/passkeys/register/options")
check("Mit Basis-Adresse Registrierung möglich", r.status_code == 200, r.text[:150])
opts = r.json()
check("Nutzerverifikation verpflichtend",
      opts["options"]["authenticatorSelection"]["userVerification"] == "required",
      opts["options"].get("authenticatorSelection"))
check("Domain gebunden", opts["options"]["rp"]["id"] == "scopex.example.de",
      opts["options"]["rp"])
r = c.post("/api/auth/passkeys/register/verify", json={
    "handle": opts["handle"], "credential": {"id": "x", "rawId": "x",
    "type": "public-key", "response": {"clientDataJSON": "x",
    "attestationObject": "x"}}})
check("Gefälschter Nachweis abgelehnt", r.status_code == 400, r.status_code)
r = c.post("/api/auth/passkeys/register/verify", json={
    "handle": opts["handle"], "credential": {"id": "x", "rawId": "x",
    "type": "public-key", "response": {"clientDataJSON": "x",
    "attestationObject": "x"}}})
check("Vorgang nur einmal verwendbar", r.status_code == 400, r.status_code)
os.environ["SCOPEX_BASE_URL"] = "http://unsicher.example.de"
r = c.post("/api/auth/passkeys/login/options")
check("Ohne HTTPS keine Passkeys", r.status_code == 503, r.status_code)
os.environ.pop("SCOPEX_BASE_URL", None)


# --- Update 4.1: Auskunft, Löschung, Protokoll, Impressum ---------------
r = c.put("/api/legal", json={"imprint_phone": "+49 5071 000000",
    "imprint_profession": "Notfallsanitäter", "imprint_law": "NotSanG"})
check("Pflichtangaben speicherbar", r.status_code == 200, r.text[:120])
l = c.get("/api/legal").json()
check("Telefonnummer im Impressum", l["phone"] == "+49 5071 000000", l)
check("Berufsangaben im Impressum",
      l["profession"] == "Notfallsanitäter" and l["law"] == "NotSanG", l)

# Ein Einsatz mit Maßnahme und Parametern, damit die Auskunft etwas zu
# zeigen hat.
enc2 = c.post("/api/encounters", json={"enc_date": "2026-09-02",
                                       "enc_time": "09:00"}).json()
c.post(f"/api/encounters/{enc2['id']}/attempts", json={
    "measure_id": iv["id"], "outcome": "erfolgreich",
    "parameters": {"gauge": "18 G (grün)", "ort": "Unterarm links"}})

r = c.get("/api/exports/my-data")
check("Auskunft abrufbar", r.status_code == 200, r.status_code)
aus = r.json()
check("Auskunft enthält Einsätze", len(aus["einsaetze"]) >= 1, len(aus["einsaetze"]))
check("Auskunft enthält Maßnahmen mit Parametern",
      any(a.get("parameters") for e in aus["einsaetze"] for a in e["attempts"]))
blob = json.dumps(aus, ensure_ascii=False)
check("Auskunft ohne Zugangsmittel",
      "password_hash" not in blob and "$argon2" not in blob and
      "secret" not in blob and "token_hash" not in blob)

r = c.get("/api/audit?limit=5&offset=0")
check("Protokoll blätterbar", r.status_code == 200 and
      len(r.json()["entries"]) <= 5 and r.json()["total"] > 5, r.json()["total"])
first = r.json()["entries"][0]
check("Protokoll mit Zeitstempel", "T" in first["at"] and len(first["at"]) >= 19, first["at"])
r2 = c.get("/api/audit?limit=5&offset=5")
check("Zweite Seite unterscheidet sich",
      r2.json()["entries"][0]["id"] != first["id"])

# Kontolöschung: letzter Administrator wird geschützt
r = c.post("/api/account/delete", json={"password": "einsatzprotokoll2026",
    "totp_code": code(sec), "confirm": "falsch"})
check("Bestätigungswort wird erzwungen", r.status_code == 400, r.status_code)
r = c.post("/api/account/delete", json={"password": "falsch",
    "totp_code": code(sec), "confirm": "LÖSCHEN"})
check("Löschung ohne Passwort abgelehnt", r.status_code == 400, r.status_code)
r = c.post("/api/account/delete", json={"password": "einsatzprotokoll2026",
    "totp_code": code(sec), "confirm": "LÖSCHEN"})
check("Letzter Administrator kann sich nicht löschen", r.status_code == 409, r.status_code)

print("\nUpdate 4.1: alle Prüfungen bestanden.")
