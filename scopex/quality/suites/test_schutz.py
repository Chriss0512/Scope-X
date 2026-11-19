"""4.6.0: Verschlüsselung im Ruhezustand und Empfehlungen durch Mitglieder.

Der Kern dieser Reihe: Markierwerte gehen über die normale API in jede
geschützte Spalte, danach wird die Datenbankdatei samt WAL als Bytefolge
nach ihnen durchsucht. Taucht einer im Klartext auf, hat eine Schreibstelle
das Verschlüsseln vergessen – gleich welche.
"""
import base64
import os
import shutil
import sys
import time as _t

os.environ["SCOPEX_DATABASE_URL"] = "sqlite:////tmp/scopex_q_schutz/scopex.db"
os.environ["SCOPEX_MEDIA_DIR"] = "/tmp/scopex_q_schutz/media"
shutil.rmtree("/tmp/scopex_q_schutz", ignore_errors=True)
os.makedirs("/tmp/scopex_q_schutz")
sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parents[2].as_posix())
import io  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app import mailer, schutz  # noqa: E402
from app.main import app  # noqa: E402
from app.security import _totp_at  # noqa: E402
from quality import nachweis  # noqa: E402,F401


def check(n, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + n + (" :: " + str(extra) if not cond else ""))
    if not cond:
        sys.exit(1)


def code(sec):
    return _totp_at(sec, int(_t.time()) // 30)


POST = []
mailer.is_configured = lambda: True
mailer.send = lambda to, subject, body: POST.append((to, subject, body)) or True


def letzte_mail(an):
    return next((m for m in reversed(POST) if m[0] == an), None)


def link_wert(body, schluessel):
    for zeile in body.splitlines():
        if f"{schluessel}=" in zeile:
            return zeile.split(f"{schluessel}=", 1)[1].strip()
    return None


MARKEN = {
    "vorname": "VORNAMEX7Q", "nachname": "NACHNAMEK2W", "email": "mailz9p@example.invalid",
    "nachricht": "NACHRICHTGEHEIM4R", "einsatznummer": "EINSATZ88771",
    "fahrzeug": "FAHRZEUGQ19", "schicht": "SCHICHTZ55", "notiz": "NOTIZPRIVAT3J",
    "medis": "MEDNOTIZ6H", "headline": "HEADLINEB3V", "beitrag": "BEITRAGTEXT7M",
    "kommentar": "KOMMENTARU2C", "bewerber": "BEWERBERY4D", "empfohlen": "empfz@example.invalid",
    "fortbildung": "FORTBILDUNGP8E", "werdegang": "WERDEGANGT6A",
}

admin = TestClient(app)
admin.__enter__()
r = admin.post("/api/auth/register", json={
    "username": "admin", "email": "admin@example.invalid", "password": "einsatzprotokoll2026",
    "first_name": "Ada", "last_name": "Admin"})
asec = r.json()["totp"]["secret"]
admin.post("/api/auth/totp/confirm", json={"code": code(asec)})
check("Schlüsseldatei angelegt, nur für den Besitzer lesbar",
      oct(os.stat("/tmp/scopex_q_schutz/scopex.key").st_mode & 0o777) == "0o600")


def mitglied(name, vorname, nachname, email=None, rolle="user"):
    inv = admin.post("/api/admin/invitations", json={"role": rolle, "valid_days": 3,
                                                     "totp_code": code(asec)}).json()
    k = TestClient(app)
    r = k.post("/api/auth/register", json={
        "username": name, "email": email or f"{name}@example.invalid",
        "password": "einsatzprotokoll2026", "first_name": vorname, "last_name": nachname,
        "invite_code": inv["code"]})
    k.post("/api/auth/totp/confirm", json={"code": code(r.json()["totp"]["secret"])})
    return k, k.get("/api/auth/state").json()["user"]["id"]


ben, BEN = mitglied("ben", MARKEN["vorname"], MARKEN["nachname"], MARKEN["email"])
cara, CARA = mitglied("cara", "Cara", "Lenz")
gast, GAST = mitglied("gast", "Gina", "Gast", rolle="guest")
for k in (admin, ben, cara):
    k.put("/api/netz/profil", json={"aktiv": True})

# --- Anmeldung mit verschlüsselter Adresse -------------------------------
from app.db import conn as _conn  # noqa: E402
from app.routers.auth import find_login  # noqa: E402

with _conn() as c:
    gefunden_konto = find_login(c, MARKEN["email"].upper())
check("Anmeldung per E-Mail trotz Verschlüsselung (Blindindex)",
      gefunden_konto and gefunden_konto["id"] == BEN)
check("Doppelte Adresse weiterhin abgewiesen", admin.post("/api/admin/invitations", json={
    "role": "user", "valid_days": 1, "email": MARKEN["email"],
    "totp_code": code(asec)}).status_code == 409)
check("Suche nach Namen funktioniert trotz Verschlüsselung", any(
    p["id"] == BEN for p in cara.get("/api/netz/personen", params={"q": "vornamex"}).json()["personen"]))

# --- Markierwerte in jede geschützte Spalte ------------------------------
ben.put("/api/netz/profil", json={"headline": MARKEN["headline"]})
ben.post("/api/netz/eintraege", json={"art": "station", "titel": MARKEN["werdegang"],
                                      "org": "Org", "notiz": MARKEN["werdegang"]})
ben.post("/api/netz/fortbildungen", json={"titel": MARKEN["fortbildung"],
                                          "datum": "2026-03-01", "stunden": 2})
enc = ben.post("/api/encounters", json={"enc_date": "2026-11-01", "enc_time": "10:00",
    "mission_number": MARKEN["einsatznummer"], "vehicle_id": MARKEN["fahrzeug"],
    "shift_code": MARKEN["schicht"]}).json()
mess = ben.get("/api/catalog/measures").json()["measures"]
meds = ben.get("/api/catalog/medications").json()["medications"]
ben.post(f"/api/encounters/{enc['id']}/attempts", json={
    "measure_id": mess[0]["id"], "outcome": "erfolgreich",
    "performer_role": "selbst durchgeführt", "note": MARKEN["notiz"]})
ben.post(f"/api/encounters/{enc['id']}/medications", json={
    "medication_id": meds[0]["id"], "dose": 1, "unit": "mg", "route": "intravenös",
    "outcome": "erfolgreich", "note": MARKEN["medis"]})
ben.patch(f"/api/encounters/{enc['id']}", json={"vehicle_id": MARKEN["fahrzeug"] + "B"})
check("Logbuch liest entschlüsselt",
      ben.get(f"/api/encounters/{enc['id']}").json()["mission_number"] == MARKEN["einsatznummer"])
post = ben.post("/api/netz/beitraege", json={"art": "beitrag",
                                            "text": MARKEN["beitrag"]}).json()
cara.post(f"/api/netz/beitraege/{post['id']}/kommentare", json={"text": MARKEN["kommentar"]})
r = cara.post("/api/netz/nachrichten", json={"an": BEN, "text": MARKEN["nachricht"]})
check("Nachricht gesendet", r.status_code == 200, r.text[:200])
liste = ben.get("/api/netz/nachrichten").json()
gespraeche = liste["gespraeche"] + liste["anfragen"]
check("Nachricht für Empfänger lesbar", MARKEN["nachricht"] in str(
    ben.get(f"/api/netz/nachrichten/{gespraeche[0]['id']}").json()))

# Bild in einer Nachricht: liegt verschlüsselt auf der Platte.
buf = io.BytesIO()
Image.new("RGB", (64, 48), (200, 30, 30)).save(buf, "PNG")
bild = cara.post("/api/netz/medien/bild", files={"datei": ("x.png", buf.getvalue(),
                                                            "image/png")}).json()
datei = "/tmp/scopex_q_schutz/media/" + bild["id"] + ".jpg"
roh = open(datei, "rb").read()
check("Bild auf der Platte verschlüsselt", roh[:4] == b"SXE1" and b"JFIF" not in roh)
r = cara.get(f"/api/netz/medien/{bild['id']}")
check("Bild wird entschlüsselt ausgeliefert", r.content[:2] == b"\xff\xd8", r.content[:8])
r2 = cara.get(f"/api/netz/medien/{bild['id']}", headers={"Range": "bytes=2-11"})
check("Teilbereich aus verschlüsselter Datei", r2.status_code == 206 and
      r2.content == r.content[2:12], r2.status_code)
r3 = cara.get(f"/api/netz/medien/{bild['id']}", headers={"Range": "bytes=-5"})
check("Endbereich aus verschlüsselter Datei", r3.content == r.content[-5:])
check("Unmöglicher Bereich 416", cara.get(f"/api/netz/medien/{bild['id']}",
      headers={"Range": f"bytes={len(r.content) + 10}-"}).status_code == 416)
manip = bytearray(roh)
manip[40] ^= 0xFF
open(datei, "wb").write(bytes(manip))
try:
    fehler = cara.get(f"/api/netz/medien/{bild['id']}").status_code != 200
except Exception:  # noqa: BLE001 - erwartete Authentifizierungsfehler
    fehler = True
check("Manipulierte Datei wird nicht ausgeliefert", fehler)
open(datei, "wb").write(roh)

# --- Empfehlung durch ein Mitglied ---------------------------------------
check("Gäste können nicht empfehlen", gast.post("/api/netz/empfehlungen", json={
    "email": "x@example.invalid"}).status_code == 403)
r = ben.post("/api/netz/empfehlungen", json={"email": MARKEN["empfohlen"],
                                            "name": "Emma"})
check("Empfehlung verschickt", r.status_code == 200 and
      r.json()["empfehlungen"][0]["status"] == "verschickt", r.text[:200])
mail = letzte_mail(MARKEN["empfohlen"])
check("Mail nennt das Mitglied", mail and MARKEN["vorname"] in mail[1])
ecode = link_wert(mail[2], "empfehlung")
check("Doppelte Empfehlung an dieselbe Adresse abgewiesen", ben.post(
    "/api/netz/empfehlungen", json={"email": MARKEN["empfohlen"]}).status_code == 409)
vorher = len(POST)
r = ben.post("/api/netz/empfehlungen", json={"email": "cara@example.invalid"})
check("Empfehlung an bestehendes Konto: gleiche Antwort, keine Mail",
      r.status_code == 200 and len(POST) == vorher)
for i in range(3):
    ben.post("/api/netz/empfehlungen", json={"email": f"weitere{i}@example.invalid"})
check("Höchstens fünf offene Empfehlungen", ben.post("/api/netz/empfehlungen", json={
    "email": "zuviel@example.invalid"}).status_code == 429)
oeff = TestClient(app)
info = oeff.get(f"/api/oeffentlich/empfehlung/{ecode}").json()
check("Empfehlung füllt Formular vor", info["email"] == MARKEN["empfohlen"] and
      MARKEN["vorname"] in info["von"], info)
check("Fremder Code abgewiesen",
      oeff.get("/api/oeffentlich/empfehlung/" + "x" * 30).status_code == 404)
benachrichtigungen_vorher = len(ben.get("/api/netz/mitteilungen").json()["mitteilungen"])
r = oeff.post("/api/oeffentlich/bewerbung", json={
    "first_name": MARKEN["bewerber"], "last_name": "Muster", "email": MARKEN["empfohlen"],
    "qualification": "Notfallsanitäter*in", "datenschutz": True, "empfehlung": ecode,
    "buerge": "cara"})
check("Bewerbung über Empfehlung sofort eingegangen", "eingegangen" in r.json()["detail"],
      r.text[:200])
check("Code nur einmal", oeff.post("/api/oeffentlich/bewerbung", json={
    "first_name": "A", "last_name": "B", "email": "andere@example.invalid",
    "qualification": "x" * 3, "datenschutz": True, "empfehlung": ecode}).status_code == 400)
_m = ben.get("/api/netz/mitteilungen").json()["mitteilungen"]
check("Empfehlendes Mitglied wird nicht erneut gefragt",
      len(_m) == benachrichtigungen_vorher
      and ben.get("/api/netz/buergschaften").json()["buergschaften"] == [],
      (benachrichtigungen_vorher, [x["art"] for x in _m]))
check("Genannte Bürgin wird bei Empfehlung ignoriert",
      cara.get("/api/netz/buergschaften").json()["buergschaften"] == [])
bw = next(b for b in admin.get("/api/admin/bewerbungen").json()["bewerbungen"]
          if b["vorname"] == MARKEN["bewerber"])
check("Administration sieht Empfehlung und Bürge", bw["per_empfehlung"] and
      bw["antwort"] == "empfohlen" and bw["buerge"]["id"] == BEN and bw["status"] == "offen", bw)
check("Mitglied sieht Status „beworben“", ben.get("/api/netz/empfehlungen").json()[
    "empfehlungen"][-1]["status"] in ("beworben", "verschickt"))
r = admin.post(f"/api/admin/bewerbungen/{bw['id']}/annehmen", json={"totp_code": code(asec)})
check("Administration entscheidet wie gewohnt", r.json()["sent"] is True)
eid = ben.get("/api/netz/empfehlungen").json()["empfehlungen"]
check("Fremde können Empfehlung nicht zurückziehen",
      cara.delete(f"/api/netz/empfehlungen/{eid[0]['id']}").status_code == 404)

# --- Bytes auf der Platte -------------------------------------------------
from app.db import conn, rows  # noqa: E402

with conn() as c:
    c.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
inhalt = b""
for name in os.listdir("/tmp/scopex_q_schutz"):
    pfad = os.path.join("/tmp/scopex_q_schutz", name)
    if os.path.isfile(pfad) and name.startswith("scopex.db"):
        inhalt += open(pfad, "rb").read()
gefunden = [k for k, wert in MARKEN.items() if wert.encode() in inhalt
            or wert.lower().encode() in inhalt]
check("Kein Markierwert im Klartext in Datenbank und WAL", not gefunden, gefunden)
with conn() as c:
    klartext = []
    for tabelle, spalten in schutz.SPALTEN.items():
        for r_ in rows(c, f"SELECT {', '.join(spalten)} FROM {tabelle}", _roh=True):
            for s_ in spalten:
                if isinstance(r_[s_], str) and r_[s_] and not r_[s_].startswith(schutz.PRAEFIX):
                    klartext.append(f"{tabelle}.{s_}")
check("Jede geschützte Spalte verschlüsselt", not klartext, sorted(set(klartext)))

# --- Sicherung: Klartext, Einspielen verschlüsselt wieder -----------------
sich = admin.get("/api/exports/backup")
check("Sicherung enthält lesbare Werte", MARKEN["einsatznummer"] in sich.text)
check("Sicherung enthält keinen Schlüsselfingerabdruck", "schluessel_kennung" not in sich.text)
r = admin.post("/api/exports/restore", files={"file": ("b.json", sich.content,
                                                        "application/json")},
               params={"password": "einsatzprotokoll2026", "totp_code": code(asec)})
check("Sicherung eingespielt", r.status_code == 200, r.text[:200])
with conn() as c:
    nach = rows(c, "SELECT mission_number FROM encounters", _roh=True)
check("Nach dem Einspielen wieder verschlüsselt",
      all(x["mission_number"] is None or x["mission_number"].startswith(schutz.PRAEFIX)
          for x in nach))
check("Nach dem Einspielen lesbar",
      ben.get(f"/api/encounters/{enc['id']}").json()["mission_number"] == MARKEN["einsatznummer"])

# --- Falscher Schlüssel: Start verweigert ---------------------------------
alt = os.environ.get("SCOPEX_SCHLUESSEL")
os.environ["SCOPEX_SCHLUESSEL"] = base64.b64encode(b"\x01" * 32).decode()
try:
    with conn() as c:
        schutz.pruefen_und_einpflegen(c)
    verweigert = False
except schutz.SchluesselFehler:
    verweigert = True
check("Fremder Schlüssel wird erkannt und abgewiesen", verweigert)
if alt is None:
    del os.environ["SCOPEX_SCHLUESSEL"]
os.rename("/tmp/scopex_q_schutz/scopex.key", "/tmp/scopex_q_schutz/weg.key")
try:
    with conn() as c:
        schutz.pruefen_und_einpflegen(c)
    verweigert = False
except schutz.SchluesselFehler:
    verweigert = True
check("Fehlender Schlüssel: kein neuer, Abbruch", verweigert and
      not os.path.exists("/tmp/scopex_q_schutz/scopex.key"))
os.rename("/tmp/scopex_q_schutz/weg.key", "/tmp/scopex_q_schutz/scopex.key")
with conn() as c:
    schutz.pruefen_und_einpflegen(c)
check("Mit dem richtigen Schlüssel wieder lesbar",
      ben.get(f"/api/encounters/{enc['id']}").json()["mission_number"] == MARKEN["einsatznummer"])

# --- Bestand aus der Zeit vor 4.6.0 ---------------------------------------
with conn() as c:
    c.exec_driver_sql("UPDATE net_messages SET body = 'ALTBESTAND123'")
    c.exec_driver_sql("UPDATE users SET email_idx = NULL WHERE username = 'cara'")
with conn() as c:
    n = schutz.pruefen_und_einpflegen(c)
with conn() as c:
    roh = rows(c, "SELECT body FROM net_messages", _roh=True)
check("Altbestand wird beim Start verschlüsselt",
      n >= 1 and all(x["body"].startswith(schutz.PRAEFIX) for x in roh))
with conn() as c:
    check("Blindindex vorhanden", rows(c, "SELECT email_idx FROM users WHERE username = 'cara'"
                                          )[0]["email_idx"] is not None)

print("\n4.6.0 Schutz und Empfehlungen: alle Prüfungen bestanden.")
