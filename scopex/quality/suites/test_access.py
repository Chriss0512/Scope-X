import json
import os
import sys
import time as _t

os.environ["SCOPEX_DATABASE_URL"] = "sqlite:////tmp/scopex_q_access.db"
if os.path.exists("/tmp/scopex_q_access.db"): os.remove("/tmp/scopex_q_access.db")
sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parents[2].as_posix())
from fastapi.testclient import TestClient

from app.main import app
from app.security import _hash_password_scrypt, _totp_at, verify_password


def check(n, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + n + (" :: " + str(extra) if not cond else ""))
    if not cond: sys.exit(1)

def code(sec): return _totp_at(sec, int(_t.time()) // 30)

admin = TestClient(app); admin.__enter__()

# --- Erstes Konto wird Administrator ------------------------------------
r = admin.post("/api/auth/register", json={
    "username": "chris", "email": "info@cd-faust.de",
    "password": "einsatzprotokoll2026", "first_name": "Christian",
    "last_name": "Faust", "qualification": "Notfallsanitäter"})
sec = r.json()["totp"]["secret"]
admin.post("/api/auth/totp/confirm", json={"code": code(sec)})
st = admin.get("/api/auth/state").json()
check("Erstes Konto ist Administrator", st["user"]["role"] == "admin", st["user"])

# --- Argon2id ------------------------------------------------------------
from app.db import conn, q, row

with conn() as c:
    h = row(c, "SELECT password_hash FROM users")["password_hash"]
check("Passwort mit Argon2id gehasht", h.startswith("$argon2id$"), h[:20])

# Alten scrypt-Hash einsetzen und stille Anhebung prüfen
with conn() as c:
    q(c, "UPDATE users SET password_hash = :p",
      p=_hash_password_scrypt("einsatzprotokoll2026"))
r = admin.post("/api/auth/login", json={"username": "chris",
    "password": "einsatzprotokoll2026", "totp_code": code(sec)})
check("Anmeldung mit altem scrypt-Hash", r.status_code == 200, r.text[:120])
with conn() as c:
    h2 = row(c, "SELECT password_hash FROM users")["password_hash"]
check("Hash still auf Argon2id gehoben", h2.startswith("$argon2id$"), h2[:20])

# --- Registrierung ohne Einladung ist gesperrt --------------------------
anon = TestClient(app)
r = anon.post("/api/auth/register", json={"username": "fremder",
    "password": "einsatzprotokoll2026"})
check("Registrierung ohne Einladung abgelehnt", r.status_code == 403, r.status_code)
r = anon.post("/api/auth/register", json={"username": "fremder",
    "password": "einsatzprotokoll2026", "invite_code": "AAAA-BBBB-CCCC-DDDD"})
check("Erfundener Code abgelehnt", r.status_code == 403, r.status_code)

# --- Einladung erzeugen --------------------------------------------------
r = admin.post("/api/admin/invitations", json={"role": "user",
    "note": "Kollege", "valid_days": 7, "totp_code": "000000"})
check("Einladung ohne gültigen Code abgelehnt", r.status_code == 400, r.status_code)
r = admin.post("/api/admin/invitations", json={"role": "user",
    "note": "Kollege", "valid_days": 7, "totp_code": code(sec)})
check("Einladung erstellt", r.status_code == 200, r.text[:150])
invite = r.json()["code"]
check("Code hat lesbare Form", len(invite) == 19 and invite.count("-") == 3, invite)
with conn() as c:
    stored = row(c, "SELECT code_hash FROM invitations")["code_hash"]
check("Code steht nur als Hash in der Datenbank", invite not in stored)

r = anon.get(f"/api/auth/invitation/{invite}")
check("Code vorab prüfbar", r.status_code == 200 and r.json()["role"] == "user")

# --- Zweites Konto per Einladung ----------------------------------------
user = TestClient(app)
r = user.post("/api/auth/register", json={"username": "kollege",
    "email": "kollege@example.invalid", "password": "einsatzprotokoll2026",
    "invite_code": invite, "qualification": "Rettungssanitäter"})
check("Registrierung mit Einladung", r.status_code == 200, r.text[:150])
usec = r.json()["totp"]["secret"]
user.post("/api/auth/totp/confirm", json={"code": code(usec)})
st = user.get("/api/auth/state").json()
check("Rolle aus der Einladung übernommen", st["user"]["role"] == "user", st["user"])

r = anon.post("/api/auth/register", json={"username": "dritter",
    "password": "einsatzprotokoll2026", "invite_code": invite})
check("Einladung nur einmal gültig", r.status_code == 403, r.status_code)

# --- Rollentrennung ------------------------------------------------------
r = user.get("/api/admin/users")
check("Mitarbeiter sieht keine Kontenliste", r.status_code == 403, r.status_code)
r = user.post("/api/catalog/medications", json={"name": "Testwirkstoff"})
check("Mitarbeiter darf Stammdaten nicht ändern", r.status_code == 403, r.status_code)
r = user.put("/api/legal", json={"imprint_name": "Fremd"})
check("Mitarbeiter darf Impressum nicht ändern", r.status_code == 403, r.status_code)
r = user.put("/api/settings", json={"edit_window_minutes": 10080})
check("Mitarbeiter darf Frist nicht ändern", r.status_code == 403, r.status_code)
r = user.put("/api/settings", json={"theme": "dark"})
check("Eigene Darstellung darf er ändern", r.status_code == 200, r.text[:120])
r = admin.get("/api/admin/users")
check("Administrator sieht Konten", r.status_code == 200 and
      len(r.json()["users"]) == 2, r.text[:150])
check("Kontenliste ohne Passwort-Hash",
      "password_hash" not in r.text and "secret" not in r.text)

# --- Datentrennung zwischen Konten --------------------------------------
enc = user.post("/api/encounters", json={"enc_date": "2026-09-01",
                                         "enc_time": "10:00"}).json()
r = admin.get(f"/api/encounters/{enc['id']}")
check("Administrator sieht fremde Einsätze nicht", r.status_code == 404, r.status_code)
r = admin.patch(f"/api/encounters/{enc['id']}", json={"naca": "IV"})
check("Und kann sie nicht ändern", r.status_code == 404, r.status_code)

# --- Gastrolle -----------------------------------------------------------
r = admin.patch(f"/api/admin/users/{st['user']['id']}",
                json={"role": "guest", "totp_code": code(sec)})
check("Rolle geändert", r.status_code == 200 and r.json()["role"] == "guest", r.text[:150])
r = user.post("/api/encounters", json={"enc_date": "2026-09-02", "enc_time": "10:00"})
check("Gast darf nicht erfassen", r.status_code == 403, r.status_code)
r = user.get("/api/encounters")
check("Gast darf lesen", r.status_code == 200, r.status_code)
admin.patch(f"/api/admin/users/{st['user']['id']}",
            json={"role": "user", "totp_code": code(sec)})

# --- Letzter Administrator ----------------------------------------------
me = admin.get("/api/auth/state").json()["user"]["id"]
r = admin.patch(f"/api/admin/users/{me}", json={"role": "user", "totp_code": code(sec)})
check("Letzter Administrator kann sich nicht entmachten", r.status_code == 409, r.status_code)
r = admin.patch(f"/api/admin/users/{me}", json={"disabled": True, "totp_code": code(sec)})
check("Und sich nicht selbst sperren", r.status_code == 409, r.status_code)

# --- Konto sperren -------------------------------------------------------
r = admin.patch(f"/api/admin/users/{st['user']['id']}",
                json={"disabled": True, "totp_code": code(sec)})
check("Konto gesperrt", r.status_code == 200 and r.json()["disabled"])
r = user.get("/api/overview")
check("Sitzung des gesperrten Kontos sofort beendet", r.status_code == 401, r.status_code)
r = user.post("/api/auth/login", json={"username": "kollege",
    "password": "einsatzprotokoll2026", "totp_code": code(usec)})
check("Gesperrtes Konto kann sich nicht anmelden", r.status_code == 403, r.status_code)
admin.patch(f"/api/admin/users/{st['user']['id']}",
            json={"disabled": False, "totp_code": code(sec)})

# --- Vertrauensgerät -----------------------------------------------------
dev = TestClient(app)
r = dev.post("/api/auth/login", json={"username": "chris",
    "password": "einsatzprotokoll2026", "totp_code": code(sec),
    "remember_device": True})
check("Anmeldung mit Merken", r.status_code == 200, r.text[:120])
check("Gerätecookie gesetzt", "scopex_device" in dev.cookies)
r = dev.post("/api/auth/login", json={"username": "chris",
                                      "password": "einsatzprotokoll2026"})
check("Zweite Anmeldung ohne Code", r.status_code == 200 and
      r.json()["device_known"], r.text[:150])
r = dev.post("/api/admin/invitations", json={"role": "user", "totp_code": ""})
check("Vertrauensgerät hebt 2FA-Pflicht nicht auf", r.status_code == 400, r.status_code)
plain = TestClient(app)
r = plain.post("/api/auth/login", json={"username": "chris",
                                        "password": "einsatzprotokoll2026"})
check("Ohne Gerätecookie weiterhin Code nötig", r.status_code == 401, r.status_code)
r = dev.get("/api/auth/devices")
check("Gerät im Profil sichtbar", r.status_code == 200 and
      len(r.json()["devices"]) == 1, r.text[:150])
dev.delete("/api/auth/devices")
r = dev.post("/api/auth/login", json={"username": "chris",
                                      "password": "einsatzprotokoll2026"})
check("Nach Entzug wieder Code nötig", r.status_code == 401, r.status_code)

# --- Passwort vergessen --------------------------------------------------
sent = {}
import app.mailer as M

M.send = lambda to, subject, body: sent.update(to=to, body=body) or True
r = anon.post("/api/auth/password-reset/request", json={"identifier": "gibtesnicht"})
check("Antwort verrät nichts über den Bestand", r.status_code == 200)
check("Für ein unbekanntes Konto geht nichts raus", "to" not in sent)
r = anon.post("/api/auth/password-reset/request", json={"identifier": "info@cd-faust.de"})
check("Reset angefordert", r.status_code == 200 and sent.get("to") == "info@cd-faust.de")
token = sent["body"].split("token=")[1].split()[0]
r = anon.post("/api/auth/password-reset/confirm", json={
    "token": token, "new_password": "neuespasswort2026"})
check("Ohne zweiten Faktor kein neues Passwort", r.status_code == 400, r.status_code)
r = anon.post("/api/auth/password-reset/confirm", json={
    "token": token, "new_password": "kurz"})
check("Zu kurzes Passwort abgelehnt", r.status_code == 400)
r = anon.post("/api/auth/password-reset/confirm", json={
    "token": token, "new_password": "neuespasswort2026", "totp_code": code(sec)})
check("Passwort gesetzt", r.status_code == 200, r.text[:150])
r = anon.post("/api/auth/password-reset/confirm", json={
    "token": token, "new_password": "nochmalanders2026", "totp_code": code(sec)})
check("Token nur einmal verwendbar", r.status_code == 400, r.status_code)
fresh = TestClient(app)
r = fresh.post("/api/auth/login", json={"username": "chris",
    "password": "neuespasswort2026", "totp_code": code(sec)})
check("Anmeldung mit neuem Passwort", r.status_code == 200, r.text[:120])
r = fresh.post("/api/auth/login", json={"username": "chris",
    "password": "einsatzprotokoll2026", "totp_code": code(sec)})
check("Altes Passwort ungültig", r.status_code == 401)

# --- Leerlaufabmeldung ---------------------------------------------------
from datetime import datetime, timedelta, timezone

r = fresh.post("/api/auth/login", json={"username": "chris",
    "password": "neuespasswort2026", "totp_code": code(sec)})
check("Angemeldet", fresh.get("/api/overview").status_code == 200)
old = (datetime.now(timezone.utc) - timedelta(minutes=45)).replace(microsecond=0).isoformat()
with conn() as c:
    q(c, "UPDATE sessions SET last_seen_at = :t", t=old)
check("Sitzung nach Leerlauf verworfen",
      fresh.get("/api/overview").status_code == 401)

# --- Protokoll ohne personenbezogene Daten -------------------------------
with conn() as c:
    from app.db import rows
    log = rows(c, "SELECT * FROM audit_log")
    pr = rows(c, "SELECT * FROM password_resets")
blob = json.dumps(log, ensure_ascii=False)
check("Kein Passwort im Protokoll",
      "einsatzprotokoll2026" not in blob and "neuespasswort2026" not in blob)
check("Kein Token im Protokoll", token not in blob)
check("Reset-Token nur als Hash gespeichert",
      all(token != x["token_hash"] for x in pr))
check("IP nur gekürzt gehasht",
      all(x["requested_ip_hash"] is None or len(x["requested_ip_hash"]) == 16
          for x in pr), pr[:1])

print("\nUpdate 2: alle Prüfungen bestanden.")
