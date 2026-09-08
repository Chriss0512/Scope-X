import io
import json
import os
import sys
import time

os.environ["SCOPEX_DATABASE_URL"] = "sqlite:////tmp/scopex_q_core.db"
if os.path.exists("/tmp/scopex_q_core.db"): os.remove("/tmp/scopex_q_core.db")
sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parents[2].as_posix())

import time as _t

from fastapi.testclient import TestClient

from app.main import app
from app.security import _totp_at

c = TestClient(app)
c.__enter__()  # löst den lifespan-Start aus: Migration und Stammdaten

def check(name, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + name + (" :: " + str(extra) if not cond else ""))
    if not cond: sys.exit(1)

r = c.get("/api/health"); check("health", r.status_code == 200)
r = c.get("/api/auth/state"); check("setup erforderlich", r.json()["setup_required"] is True)

r = c.post("/api/auth/register", json={
    "username": "nfs", "email": "nfs@example.invalid", "password": "einsatzprotokoll2026",
    "first_name": "Jonas", "last_name": "Berger", "qualification": "Notfallsanitäter*in"})
check("Registrierung", r.status_code == 200, r.text)
secret = r.json()["totp"]["secret"]
check("QR-SVG erzeugt", "<svg" in r.json()["totp"]["qr_svg"])

code = _totp_at(secret, int(_t.time()) // 30)
r = c.post("/api/auth/totp/confirm", json={"code": code})
check("TOTP bestätigt", r.status_code == 200, r.text)
codes = r.json()["recovery_codes"]
check("10 Wiederherstellungscodes", len(codes) == 10)

r = c.post("/api/auth/logout"); check("Abmeldung", r.status_code == 200)
r = c.post("/api/auth/login", json={"username": "nfs", "password": "einsatzprotokoll2026",
                                    "totp_code": _totp_at(secret, int(_t.time()) // 30)})
check("Anmeldung mit TOTP", r.status_code == 200, r.text)
r = c.post("/api/auth/login", json={"username": "nfs", "password": "einsatzprotokoll2026",
                                    "totp_code": "000000"})
check("Anmeldung ohne gültigen Code scheitert", r.status_code == 401)
r = c.post("/api/auth/login", json={"username": "nfs", "password": "einsatzprotokoll2026",
                                    "recovery_code": codes[0]})
check("Anmeldung per Wiederherstellungscode", r.status_code == 200, r.text)
r = c.post("/api/auth/login", json={"username": "nfs", "password": "einsatzprotokoll2026",
                                    "recovery_code": codes[0]})
check("Wiederherstellungscode nur einmal gültig", r.status_code == 401)

# Anmeldung wahlweise über Benutzername oder E-Mail, Groß- und
# Kleinschreibung darf keine Rolle spielen.
for ident in ["nfs", "NFS", "nfs@example.invalid", "NFS@Example.Invalid"]:
    r = c.post("/api/auth/login", json={
        "username": ident, "password": "einsatzprotokoll2026",
        "totp_code": _totp_at(secret, int(_t.time()) // 30)})
    check(f"Anmeldung mit '{ident}'", r.status_code == 200, r.text[:120])
r = c.post("/api/auth/login", json={"username": "unbekannt@example.invalid",
                                    "password": "einsatzprotokoll2026",
                                    "totp_code": _totp_at(secret, int(_t.time()) // 30)})
check("Unbekannte Kennung abgelehnt", r.status_code == 401)

prof = c.get("/api/profile").json()
check("Benutzername abrufbar", prof["username"] == "nfs", prof.get("username"))
check("E-Mail abrufbar", prof["email"] == "nfs@example.invalid", prof.get("email"))

r = c.put("/api/auth/email", json={"email": "Neu@Example.Invalid",
                                   "password": "einsatzprotokoll2026",
                                   "totp_code": _totp_at(secret, int(_t.time()) // 30)})
check("E-Mail geändert", r.status_code == 200 and
      r.json()["email"] == "neu@example.invalid", r.text[:150])
r = c.post("/api/auth/login", json={"username": "neu@example.invalid",
                                    "password": "einsatzprotokoll2026",
                                    "totp_code": _totp_at(secret, int(_t.time()) // 30)})
check("Anmeldung mit neuer Adresse", r.status_code == 200)
r = c.put("/api/auth/email", json={"email": "x@example.invalid",
                                   "password": "falsch", "totp_code": "000000"})
check("Adressänderung ohne Passwort abgelehnt", r.status_code == 400)
r = c.put("/api/auth/email", json={"email": "keinatzeichen",
                                   "password": "einsatzprotokoll2026",
                                   "totp_code": _totp_at(secret, int(_t.time()) // 30)})
check("Ungültige Adresse abgelehnt", r.status_code == 400)

cat = c.get("/api/catalog/measures").json()
check("Maßnahmenkatalog geladen", len(cat["measures"]) > 30, len(cat["measures"]))
intub = next(m for m in cat["measures"] if m["name"].startswith("Endotracheale"))
check("Intubation hat 3 Parameter", len(intub["parameters"]) == 3, intub["parameters"])
defib = next(m for m in cat["measures"] if m["name"] == "Defibrillation")
meds = c.get("/api/catalog/medications").json()["medications"]
check("Medikamentenstamm", len(meds) == 60, len(meds))
zek = c.get("/api/catalog/complications").json()["complications"]
check("ZEK-Katalog", len(zek) == 55, len(zek))
fehlint = next(z for z in zek if z["code"] == "06")

r = c.post("/api/encounters", json={"enc_date": "2026-09-01", "enc_time": "14:32",
                                    "mission_number": "2026-114233", "naca": "IV"})
check("Einsatz angelegt", r.status_code == 200, r.text)
enc = r.json()
check("Frist läuft", enc["lock"]["locked"] is False and enc["lock"]["remaining_seconds"] > 7000,
      enc["lock"])

r = c.post(f"/api/encounters/{enc['id']}/attempts", json={
    "measure_id": intub["id"], "outcome": "fehlgeschlagen",
    "delegation": "eigenverantwortlich",
    "parameters": {"tubusgroesse": "7.5", "versuche": "3", "cormack": "III"},
    "complications": [{"id": fehlint["id"], "relation": "ursächlich",
                       "patient_harm": "vermutet"}],
    "note": "Umstieg auf supraglottischen Atemweg"})
check("Maßnahme gespeichert", r.status_code == 200, r.text)
full = r.json()
check("Parameter übernommen", len(full["attempts"][0]["parameters"]) == 3)
zc = full["attempts"][0]["complications"][0]
check("ZEK mit Bezug und Schaden", zc["code"] == "06" and
      zc["relation"] == "ursächlich" and zc["patient_harm"] == "vermutet", zc)

r = c.post(f"/api/encounters/{enc['id']}/attempts", json={
    "measure_id": defib["id"], "outcome": "erfolgreich", "delegation": "delegiert",
    "parameters": {"energie": "200"}})
check("Zweite Maßnahme", r.status_code == 200, r.text)

igel = next(m for m in cat["measures"] if m["name"] == "i-gel")
r = c.post(f"/api/encounters/{enc['id']}/attempts", json={
    "measure_id": igel["id"], "outcome": "abgebrochen",
    "parameters": {"groesse": "4"}})
check("Abgebrochene Maßnahme", r.status_code == 200, r.text)

r = c.post(f"/api/encounters/{enc['id']}/attempts", json={
    "measure_id": igel["id"], "outcome": "frustran"})
check("Abgeschaffter Ergebniswert wird abgelehnt", r.status_code == 400, r.status_code)
r = c.post(f"/api/encounters/{enc['id']}/attempts", json={
    "measure_id": igel["id"], "outcome": "erfolgreich",
    "complications": [{"id": fehlint["id"], "relation": "erfunden"}]})
check("Unbekannter ZEK-Bezug wird abgelehnt", r.status_code == 400, r.status_code)

adrenalin = next(m for m in meds if m["name"] == "Adrenalin")
for i in range(3):
    r = c.post(f"/api/encounters/{enc['id']}/medications", json={
        "medication_id": adrenalin["id"], "dose": 1, "unit": "mg",
        "route": "intravenös", "delegation": "delegiert"})
check("Drei Gaben desselben Wirkstoffs", r.status_code == 200 and
      len(r.json()["medications"]) == 3, r.text[:200])

r = c.post(f"/api/encounters/{enc['id']}/medications", json={
    "medication_id": adrenalin["id"], "unit": "Liter"})
check("Unbekannte Einheit abgelehnt", r.status_code == 400)

ov = c.get("/api/overview").json()
# --- Update 1 -----------------------------------------------------------
r = c.get("/api/catalog/constants").json()
check("Rettungsassistent im Katalog", "Rettungsassistent*in" in r["qualifications"], r["qualifications"])
check("Drei Rollen", [x["key"] for x in r["performer_roles"]] ==
      ["selbst durchgeführt", "angeleitet", "assistiert"], r["performer_roles"])

iv = next(m for m in cat["measures"] if m["name"] == "Intravenöser Zugang")
g = next(p for p in iv["parameters"] if p["key"] == "gauge")
check("Zugangsgröße mit Farbcode", g["type"] == "select" and
      "18 G (grün)" in g["options"], g)

r = c.post(f"/api/encounters/{enc['id']}/attempts", json={
    "measure_id": iv["id"], "outcome": "erfolgreich",
    "performer_role": "angeleitet",
    "performer_qualification": "NFS in Ausbildung, 3. Lehrjahr",
    "parameters": {"gauge": "18 G (grün)", "ort": "Handrücken links"}})
check("Angeleitete Maßnahme", r.status_code == 200, r.text[:200])
ang = [a for a in r.json()["attempts"] if a["performer_role"] == "angeleitet"]
check("Rolle gespeichert", len(ang) == 1 and
      ang[0]["performer_qualification"].startswith("NFS"), ang[:1])
r = c.post(f"/api/encounters/{enc['id']}/attempts", json={
    "measure_id": iv["id"], "outcome": "erfolgreich", "performer_role": "erfunden"})
check("Unbekannte Rolle abgelehnt", r.status_code == 400)

st = c.get("/api/stats?period=all").json()
roles = {x["key"]: x["n"] for x in st["by_role"]}
check("Rollenauswertung", roles.get("angeleitet") == 1 and
      roles.get("selbst durchgeführt") == 3, roles)
sr = c.get("/api/stats?period=all&performer_role=angeleitet").json()
check("Rollenfilter", sr["attempts"] == 1, sr["attempts"])

# Profil mit Facharztbezeichnung
r = c.put("/api/profile", json={"qualification": "Ärztin / Arzt",
                                "specialty": "Anästhesiologie"})
check("Facharztbezeichnung", r.json()["profile"]["specialty"] == "Anästhesiologie")
c.put("/api/profile", json={"qualification": "Notfallsanitäter*in"})

# Bearbeitungsfrist bis sieben Tage
check("7 Tage zulässig",
      c.put("/api/settings", json={"edit_window_minutes": 10080}).status_code == 200)
check("Mehr als 7 Tage abgelehnt",
      c.put("/api/settings", json={"edit_window_minutes": 20000}).status_code == 400)
c.put("/api/settings", json={"edit_window_minutes": 120})

# Rechtliche Angaben
l = c.get("/api/legal").json()
check("Impressum vorbelegt", l["name"] == "Christian Faust" and
      "Eichenweg" in l["address"], l)
check("E-Mail zunächst leer", l["email"] == "")
c.put("/api/legal", json={"imprint_email": "kontakt@example.invalid"})
check("E-Mail speicherbar",
      c.get("/api/legal").json()["email"] == "kontakt@example.invalid")

ov = c.get("/api/overview").json()
check("Startseite zählt", ov["attempts"] == 4 and ov["medications"] == 3 and
      ov["complications"] == 1, ov)

s = c.get("/api/stats?period=all").json()
check("Statistik Einsätze", s["encounters"] == 1, s["encounters"])
check("Erfolgsquote 50 %", s["success_rate"] == 50.0, s["success_rate"])
check("Abbruchquote 25 %", s["abort_rate"] == 25.0, s["abort_rate"])
d = {r["key"]: r["n"] for r in s["derived"]}
check("Erfolgreich ohne Komplikationen", d["erfolgreich_ohne_zek"] == 2, d)
check("Erfolgreich mit Komplikationen", d["erfolgreich_mit_zek"] == 0, d)
check("Komplikation ursächlich für Fehlschlag", d["fehlgeschlagen_ursaechlich"] == 1, d)
check("Fehlschlag ohne Komplikation", d["fehlgeschlagen_ohne_zek"] == 0, d)
check("Abgebrochen ohne ursächliche Komplikation", d["abgebrochen_sonst"] == 1, d)
check("Kategorien summieren sich auf die Maßnahmen",
      sum(d.values()) == s["attempts"], (sum(d.values()), s["attempts"]))
check("Patientenschaden vermutet", s["patient_harm"]["vermutet"]["attempts"] == 1,
      s["patient_harm"])
check("Kein gesicherter Schaden", s["patient_harm"]["gesichert"]["attempts"] == 0)
sh = c.get("/api/stats?period=all&harm=vermutet").json()
check("Schadensfilter greift", sh["attempts"] == 1, sh["attempts"])
check("NACA-Zeile IV", any(n["naca"] == "IV" and n["encounters"] == 1 for n in s["naca"]), s["naca"])
check("Applikationsweg gezählt", s["by_route"][0]["name"] == "intravenös", s["by_route"])
s2 = c.get("/api/stats?period=all&naca=I").json()
check("NACA-Filter greift", s2["encounters"] == 0, s2["encounters"])
s3 = c.get("/api/stats?period=all&category=A").json()
check("Kategoriefilter greift", s3["attempts"] == 2, s3["attempts"])

# --- Stilllegen gesperrter Einträge ------------------------------------
enc_full = c.get(f"/api/encounters/{enc['id']}").json()
victim = next(a["id"] for a in enc_full["attempts"] if a["measure_name"] == "i-gel")
r = c.post(f"/api/attempts/{victim}/withdraw", json={"reason": "x"})
check("Begründung wird erzwungen", r.status_code == 400, r.status_code)
r = c.post(f"/api/attempts/{victim}/withdraw",
           json={"reason": "Versehentlich doppelt erfasst"})
check("Eintrag stillgelegt", r.status_code == 200, r.text[:200])
s4 = c.get("/api/stats?period=all").json()
check("Stillgelegter Eintrag zählt nicht mehr", s4["attempts"] == 3, s4["attempts"])
enc_after = c.get(f"/api/encounters/{enc['id']}").json()
check("Und ist nicht mehr sichtbar",
      all(a["id"] != victim for a in enc_after["attempts"]))
au = [x for x in c.get("/api/audit?limit=200").json()["entries"]
      if x["action"] == "withdraw"]
check("Stilllegung protokolliert",
      au and au[0]["new_value"] == "Versehentlich doppelt erfasst", au[:1])
r = c.post(f"/api/attempts/{victim}/withdraw", json={"reason": "nochmal versuchen"})
check("Zweimal stilllegen nicht möglich", r.status_code == 404, r.status_code)

r = c.get("/api/legal")
check("Rechtliche Angaben ohne Anmeldung", r.status_code == 200)

r = c.get("/api/exports/pdf?period=all&detailed=true")
check("PDF erzeugt", r.status_code == 200 and r.content[:4] == b"%PDF", r.status_code)
open("/tmp/nachweis.pdf", "wb").write(r.content)
check("PDF hat Substanz", len(r.content) > 4000, len(r.content))

r = c.get("/api/exports/csv?kind=attempts&period=all")
check("CSV Maßnahmen", r.status_code == 200 and "Cormack" in r.text, r.text[:200])
check("CSV enthält Bezug und Schaden",
      "ursächlich" in r.text and "Schaden vermutet" in r.text, r.text[:400])
r = c.get("/api/exports/csv?kind=medications&period=all")
check("CSV Medikamente", "Adrenalin" in r.text)

b = c.get("/api/exports/backup")
check("Backup erzeugt", b.status_code == 200 and b.json()["format"] == "scopex-backup")
bj = b.json()
check("Backup ohne Zugangsdaten",
      "users" not in bj["tables"] and "auth_totp" not in bj["tables"] and
      "recovery_codes" not in bj["tables"], list(bj["tables"]))
check("Backup enthält Einsätze", len(bj["tables"]["encounters"]) == 1)

# Audit
a = c.get("/api/audit").json()["entries"]
check("Audit-Log gefüllt", len(a) > 5, len(a))
r = c.patch(f"/api/encounters/{enc['id']}", json={"naca": "V"})
check("Änderung innerhalb der Frist", r.status_code == 200, r.text)
a = c.get("/api/audit").json()["entries"]
diff = [x for x in a if x["field"] == "naca"]
check("Änderung protokolliert", diff and diff[0]["old_value"] == "IV" and
      diff[0]["new_value"] == "V", diff[:1])

# Sperrfrist
c.put("/api/settings", json={"edit_window_minutes": 1})
from datetime import datetime, timedelta, timezone

from app.db import conn, q

old = (datetime.now(timezone.utc) - timedelta(minutes=10)).replace(microsecond=0).isoformat()
with conn() as cx:
    q(cx, "UPDATE encounters SET created_at = :t", t=old)
    q(cx, "UPDATE measure_attempts SET created_at = :t", t=old)
r = c.patch(f"/api/encounters/{enc['id']}", json={"naca": "VI"})
check("Gesperrter Einsatz nicht änderbar", r.status_code == 409, r.status_code)
r = c.delete(f"/api/encounters/{enc['id']}")
check("Gesperrter Einsatz nicht löschbar", r.status_code == 409, r.status_code)
r = c.get(f"/api/encounters/{enc['id']}")
check("Gesperrter Einsatz weiterhin lesbar", r.status_code == 200 and
      r.json()["lock"]["locked"] is True)

# Wiederherstellung
r = c.post("/api/exports/restore",
           params={"password": "einsatzprotokoll2026",
                   "totp_code": _totp_at(secret, int(_t.time()) // 30)},
           files={"file": ("backup.json", json.dumps(bj), "application/json")})
check("Wiederherstellung", r.status_code == 200, r.text[:300])
s = c.get("/api/stats?period=all").json()
check("Daten nach Wiederherstellung", s["encounters"] == 1 and s["attempts"] == 3, s)
check("Bezug übersteht Wiederherstellung",
      {r["key"]: r["n"] for r in s["derived"]}["fehlgeschlagen_ursaechlich"] == 1,
      s["derived"])
r = c.post("/api/exports/restore", params={"password": "falsch", "totp_code": "000000"},
           files={"file": ("b.json", json.dumps(bj), "application/json")})
check("Wiederherstellung ohne Passwort abgelehnt", r.status_code == 400)

# Sicherheitsheader und SPA
r = c.get("/")
check("SPA ausgeliefert", r.status_code == 200 and "SCOPE X" in r.text)
check("CSP gesetzt", "default-src 'self'" in r.headers.get("content-security-policy", ""))
check("Kein Framing", r.headers.get("x-frame-options") == "DENY")
r = c.get("/assets/app.js")
check("app.js ausgeliefert", r.status_code == 200 and len(r.content) > 20000, len(r.content))
r = c.get("/assets/app.css"); check("app.css ausgeliefert", r.status_code == 200)

print("\nAlle Prüfungen bestanden.")
