"""Kompetenznetz: Sichtbarkeit, Datenschutzgrenze, Bilder, DSGVO.

Der wichtigste Teil dieser Reihe ist die Datenschutzgrenze. Ein Einsatz
bekommt in jedem privaten Feld einen eindeutigen Markierwert; danach wird
jede Antwort, die ein Kontakt erhält, als Zeichenkette nach diesen Werten
durchsucht. Taucht einer auf, ist die Grenze verletzt, gleich über welches
Feld oder welchen Umweg.
"""
import io
import json
import os
import sys
import time as _t

os.environ["SCOPEX_DATABASE_URL"] = "sqlite:////tmp/scopex_q_netz.db"
if os.path.exists("/tmp/scopex_q_netz.db"):
    os.remove("/tmp/scopex_q_netz.db")
sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parents[2].as_posix())
from fastapi.testclient import TestClient

from app.main import app
from app.security import _totp_at
from quality import nachweis  # noqa: F401,E402


def check(n, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + n + (" :: " + str(extra) if not cond else ""))
    if not cond:
        sys.exit(1)


def code(sec):
    return _totp_at(sec, int(_t.time()) // 30)


# --- Drei Mitglieder -----------------------------------------------------
chris = TestClient(app); chris.__enter__()
r = chris.post("/api/auth/register", json={
    "username": "chris", "email": "chris@example.invalid",
    "password": "einsatzprotokoll2026", "first_name": "Christian",
    "last_name": "Faust", "qualification": "Notfallsanitäter*in"})
csec = r.json()["totp"]["secret"]
chris.post("/api/auth/totp/confirm", json={"code": code(csec)})
CHRIS = chris.get("/api/auth/state").json()["user"]["id"]


def mitglied(name, vorname, nachname):
    r = chris.post("/api/admin/invitations", json={"role": "user", "note": name,
        "valid_days": 7, "totp_code": code(csec)})
    k = TestClient(app)
    r = k.post("/api/auth/register", json={"username": name,
        "email": f"{name}@example.invalid", "password": "einsatzprotokoll2026",
        "first_name": vorname, "last_name": nachname,
        "invite_code": r.json()["code"], "qualification": "Rettungssanitäter*in"})
    s = r.json()["totp"]["secret"]
    k.post("/api/auth/totp/confirm", json={"code": code(s)})
    return k, k.get("/api/auth/state").json()["user"]["id"]


anna, ANNA = mitglied("anna", "Anna", "Berger")
ben, BEN = mitglied("ben", "Ben", "Kraus")

# --- Voreinstellung: unsichtbar ------------------------------------------
r = chris.get("/api/netz/profil")
check("Netzwerkprofil ist anfangs inaktiv", r.json()["aktiv"] is False, r.json())
r = anna.get(f"/api/netz/personen/{CHRIS}")
check("Inaktives Mitglied sieht niemanden", r.status_code == 409, r.status_code)
r = chris.get("/api/netz/feed")
check("Feed bei inaktivem Profil leer und markiert",
      r.json()["aktiv"] is False and r.json()["beitraege"] == [], r.json())

for k in (chris, anna, ben):
    k.put("/api/netz/profil", json={"aktiv": True})
chris.put("/api/netz/profil", json={"headline": "Notfallsanitäter*in, Praxisanleiter",
                                    "about": "Lernen im Rettungsdienst."})

r = anna.get("/api/netz/personen", params={"q": "faust"})
check("Suche findet aktives Mitglied",
      any(p["id"] == CHRIS for p in r.json()["personen"]), r.text[:150])
check("Suche verrät weder Benutzernamen noch E-Mail",
      "chris@example" not in r.text and '"chris"' not in r.text, r.text[:200])

r = anna.get(f"/api/netz/personen/{CHRIS}")
p = r.json()
check("Fremde sehen Name und Kopfzeile", p["name"] == "Christian Faust"
      and p["headline"].startswith("Notfallsanitäter"), p)
check("Fremde sehen weder Über mich noch Beiträge",
      "about" not in p and "beitraege" not in p and "kompetenzen" not in p, sorted(p))

# --- Kontakte ------------------------------------------------------------
r = anna.post(f"/api/netz/kontakte/{ANNA}")
check("Keine Anfrage an sich selbst", r.status_code == 400, r.status_code)
r = anna.post(f"/api/netz/kontakte/{CHRIS}")
check("Anfrage gesendet", r.json()["beziehung"] == "ausgehend", r.json())
r = anna.get(f"/api/netz/personen/{CHRIS}")
check("Ausstehende Anfrage ist noch kein Kontakt", "beitraege" not in r.json())
r = chris.get("/api/netz/mitteilungen")
check("Mitteilung über Anfrage",
      any(m["art"] == "kontaktanfrage" for m in r.json()["mitteilungen"]), r.text[:150])
r = chris.post(f"/api/netz/kontakte/{ANNA}/annehmen")
check("Anfrage angenommen", r.json()["beziehung"] == "kontakt", r.text[:120])
r = anna.get("/api/netz/kontakte")
check("Kontakt in der Liste", [p["id"] for p in r.json()["kontakte"]] == [CHRIS])

# Gegenanfrage gilt als Annahme
ben.post(f"/api/netz/kontakte/{ANNA}")
r = anna.post(f"/api/netz/kontakte/{BEN}")
check("Gegenanfrage gilt als Annahme", r.json()["beziehung"] == "kontakt", r.json())

# --- Ein Einsatz mit Markierwerten in jedem privaten Feld ----------------
MARKEN = {
    "Einsatznummer": "E-2026-471199",
    "Fahrzeug": "RTW 4-83-17",
    "Schicht": "SCHICHT-N7Q",
    "Datum": "2026-11-14",
    "Datum deutsch": "14.11.2026",
    "Uhrzeit": "03:12",
    "Notiz Maßnahme": "NOTIZ-GEHEIM-9F3",
    "Notiz Medikament": "MEDNOTIZ-GEHEIM-7K2",
    "Dosis": "4.75",
    "Patientenschaden": "gesichert",
}
mess = chris.get("/api/catalog/measures").json()["measures"]
meds = chris.get("/api/catalog/medications").json()["medications"]
zek = chris.get("/api/catalog/complications").json()["complications"]
massnahme = next(m for m in mess if "Intravenöser Zugang" in m["name"])
medikament = next(m for m in meds if m["name"].startswith("Amiodaron"))

enc = chris.post("/api/encounters", json={
    "enc_date": MARKEN["Datum"], "enc_time": MARKEN["Uhrzeit"],
    "mission_number": MARKEN["Einsatznummer"], "naca": "IV",
    "shift_code": MARKEN["Schicht"], "vehicle_id": MARKEN["Fahrzeug"]}).json()
# Die Anlage-Endpunkte liefern den ganzen Einsatz zurück; die neue
# Maßnahme steckt darin.
att = chris.post(f"/api/encounters/{enc['id']}/attempts", json={
    "measure_id": massnahme["id"], "outcome": "erfolgreich",
    "performed_at": "2026-11-14T03:19:00", "note": MARKEN["Notiz Maßnahme"],
    "complications": [{"id": zek[0]["id"], "relation": "ursächlich",
                       "patient_harm": MARKEN["Patientenschaden"]}]}).json()["attempts"][-1]
med = chris.post(f"/api/encounters/{enc['id']}/medications", json={
    "medication_id": medikament["id"], "dose": float(MARKEN["Dosis"]),
    "unit": "mg", "route": "intravenös", "note": MARKEN["Notiz Medikament"],
    "administered_at": "2026-11-14T03:25:00"}).json()["medications"][-1]
check("Einsatz mit Markierwerten angelegt", "id" in att and "id" in med,
      (att, med))

# --- Kompetenzbeitrag ----------------------------------------------------
r = chris.post("/api/netz/beitraege", json={
    "art": "kompetenz", "text": "Erster i.v.-Zugang unter schwierigen Bedingungen.",
    "attempt_ids": [att["id"]], "medication_ids": [med["id"]],
    "mit_zek": True, "mit_naca": True})
check("Kompetenzbeitrag geteilt", r.status_code == 200, r.text[:200])
beitrag = r.json()
check("Schnappschuss enthält Maßnahme, Medikament, ZEK, NACA",
      beitrag["kompetenz"]["massnahmen"][0]["name"] == massnahme["name"]
      and beitrag["kompetenz"]["medikamente"][0]["divi_gruppe"]
      and beitrag["kompetenz"]["zek"] and beitrag["kompetenz"]["naca"] == "IV",
      beitrag["kompetenz"])

# Jede Antwort, die ein Kontakt bekommt, als Ganzes durchsuchen.
antworten = {
    "Feed": anna.get("/api/netz/feed").text,
    "Profil": anna.get(f"/api/netz/personen/{CHRIS}").text,
    "Beitrag": anna.get(f"/api/netz/beitraege/{beitrag['id']}").text,
    "Mitteilungen": chris.get("/api/netz/mitteilungen").text,
}
for wo, text in antworten.items():
    for was, wert in MARKEN.items():
        check(f"{was} nicht im {wo} des Kontakts", wert not in text,
              f"{wert} gefunden")
check("Keine encounter_id im Beitrag", enc["id"] not in antworten["Beitrag"])

with __import__("app.db", fromlist=["conn"]).conn() as c:
    spalten = {r_["name"] for r_ in c.exec_driver_sql(
        "PRAGMA table_info(net_posts)").mappings()}
verboten = {"encounter_id", "mission_number", "vehicle_id", "shift_code",
            "enc_date", "enc_time", "performed_at", "administered_at", "note",
            "dose", "patient_harm"}
check("net_posts hat keine Spalte für private Felder",
      not (spalten & verboten), spalten & verboten)

# --- Freitext gegen das eigene Logbuch ----------------------------------
for text, was in [
    (f"Einsatz {MARKEN['Einsatznummer']} war lehrreich", "Einsatznummer"),
    (f"Mit dem {MARKEN['Fahrzeug'].lower()} unterwegs", "Fahrzeug"),
    (f"Am {MARKEN['Datum deutsch']} hatten wir", "Datum"),
    ("Kurz nach 03:12 alarmiert", "Uhrzeit"),
    ("Gegen 3 Uhr nachts", "Uhrzeit mit Uhr"),
]:
    r = chris.post("/api/netz/beitraege", json={"art": "text", "text": text})
    check(f"Text mit {was} abgewiesen", r.status_code == 400, r.status_code)
for text in ("Adrenalin 1:10 verdünnt", "Reanimation 30:2 und 15:2",
             "S3-Leitlinie vom 01.03.2024"):
    r = chris.post("/api/netz/beitraege", json={"art": "text", "text": text})
    check(f"Kein Fehlalarm: {text}", r.status_code == 200, r.text[:150])
r = anna.post(f"/api/netz/beitraege/{beitrag['id']}/kommentare",
              json={"text": "Wann war das? 03:12?"})
check("Uhrzeit auch im Kommentar abgewiesen", r.status_code == 400, r.status_code)

# --- Fremde Einträge (IDOR) ----------------------------------------------
fremd = anna.post("/api/encounters", json={"enc_date": "2026-11-10",
                                          "enc_time": "10:00"}).json()
fatt = anna.post(f"/api/encounters/{fremd['id']}/attempts", json={
    "measure_id": massnahme["id"], "outcome": "erfolgreich"}).json()["attempts"][-1]
r = chris.post("/api/netz/beitraege", json={"art": "kompetenz",
    "attempt_ids": [fatt["id"]]})
check("Fremde Maßnahme lässt sich nicht teilen", r.status_code == 404, r.status_code)
r = chris.post("/api/netz/beitraege", json={"art": "kompetenz",
    "attempt_ids": [att["id"], fatt["id"]]})
check("Auch nicht gemischt mit eigener", r.status_code == 404, r.status_code)

# --- Sichtbarkeit von Beiträgen ------------------------------------------
r = ben.get("/api/netz/feed")
check("Nicht-Kontakt sieht den Beitrag nicht im Feed",
      all(b["id"] != beitrag["id"] for b in r.json()["beitraege"]))
r = ben.get(f"/api/netz/beitraege/{beitrag['id']}")
check("Nicht-Kontakt bekommt 404 statt 403", r.status_code == 404, r.status_code)
r = ben.put(f"/api/netz/beitraege/{beitrag['id']}/reaktion", json={"art": "stark"})
check("Nicht-Kontakt kann nicht reagieren", r.status_code == 404, r.status_code)
r = ben.post(f"/api/netz/beitraege/{beitrag['id']}/kommentare", json={"text": "Hallo"})
check("Nicht-Kontakt kann nicht kommentieren", r.status_code == 404, r.status_code)

# --- Wissensbeitrag ------------------------------------------------------
r = chris.post("/api/netz/beitraege", json={"art": "wissen",
    "text": "Lesenswert", "link_url": "javascript:alert(1)", "link_titel": "X"})
check("javascript:-Link abgewiesen", r.status_code == 400, r.status_code)
r = chris.post("/api/netz/beitraege", json={"art": "wissen",
    "link_url": "www.awmf.org/leitlinien", "link_titel": "X"})
check("Link ohne Schema abgewiesen", r.status_code == 400, r.status_code)
r = chris.post("/api/netz/beitraege", json={"art": "wissen",
    "text": "Neue S3-Leitlinie zur Polytraumaversorgung.",
    "link_url": "https://register.awmf.org/de/leitlinien/detail/187-023",
    "link_titel": "S3-Leitlinie Polytrauma", "link_quelle": "AWMF"})
check("Wissensbeitrag geteilt", r.status_code == 200, r.text[:150])

# --- Reaktionen und Kommentare -------------------------------------------
r = anna.put(f"/api/netz/beitraege/{beitrag['id']}/reaktion", json={"art": "lehrreich"})
check("Reaktion gesetzt", r.json()["reaktionen"]["lehrreich"] == 1, r.text[:150])
r = anna.put(f"/api/netz/beitraege/{beitrag['id']}/reaktion", json={"art": "stark"})
check("Reaktion ändern statt doppeln",
      r.json()["reaktionen"]["stark"] == 1 and r.json()["reaktionen"]["lehrreich"] == 0)
r = anna.put(f"/api/netz/beitraege/{beitrag['id']}/reaktion", json={"art": "herz"})
check("Unbekannte Reaktion abgewiesen", r.status_code == 400)
r = anna.post(f"/api/netz/beitraege/{beitrag['id']}/kommentare",
              json={"text": "Danke fürs Teilen!"})
check("Kommentar geschrieben", len(r.json()["kommentare"]) == 1, r.text[:150])
kid = r.json()["kommentare"][0]["id"]
r = ben.delete(f"/api/netz/kommentare/{kid}")
check("Fremde können Kommentar nicht löschen", r.status_code == 404, r.status_code)

# --- Bestätigungen -------------------------------------------------------
r = anna.post("/api/netz/bestaetigungen", json={"user_id": CHRIS,
    "measure_id": massnahme["id"], "rolle": "praxisanleitung"})
check("Verborgene Kompetenz nicht bestätigbar", r.status_code == 404, r.status_code)
chris.put(f"/api/netz/kompetenzen/{massnahme['id']}", json={"sichtbar": True})
r = anna.post("/api/netz/bestaetigungen", json={"user_id": CHRIS,
    "measure_id": massnahme["id"], "rolle": "praxisanleitung"})
check("Kontakt bestätigt freigegebene Kompetenz", r.status_code == 200, r.text[:150])
r = anna.post("/api/netz/bestaetigungen", json={"user_id": CHRIS,
    "measure_id": massnahme["id"], "rolle": "kollegial"})
check("Nur eine Bestätigung je Person", r.status_code == 409, r.status_code)
r = ben.post("/api/netz/bestaetigungen", json={"user_id": CHRIS,
    "measure_id": massnahme["id"]})
check("Nicht-Kontakt kann nicht bestätigen", r.status_code == 404, r.status_code)
r = chris.post("/api/netz/bestaetigungen", json={"user_id": CHRIS,
    "measure_id": massnahme["id"]})
check("Keine Selbstbestätigung", r.status_code == 400, r.status_code)
komp = anna.get(f"/api/netz/personen/{CHRIS}").json()["kompetenzen"]
check("Kompetenz mit Anzahl und Bestätigung sichtbar",
      komp and komp[0]["anzahl"] == 1 and komp[0]["praxisanleitung"] == 1, komp)

# --- Bilder --------------------------------------------------------------
from PIL import Image

foto = Image.new("RGB", (900, 600), (18, 104, 120))
exif = Image.Exif()
exif[0x8825] = {2: (52.0, 31.0, 0.0), 4: (9.0, 44.0, 0.0)}  # GPS
exif[0x010F] = "GEHEIMKAMERA"
puffer = io.BytesIO()
foto.save(puffer, format="JPEG", exif=exif)
roh = puffer.getvalue()
check("Testbild trägt GPS-Metadaten", b"GEHEIMKAMERA" in roh)
r = chris.post("/api/netz/medien/avatar",
               files={"datei": ("profil.jpg", roh, "image/jpeg")})
check("Profilbild hochgeladen", r.status_code == 200, r.text[:150])
av = r.json()
check("Profilbild quadratisch", av["breite"] == av["hoehe"] == 512, av)
r = anna.get(f"/api/netz/medien/{av['id']}")
check("Kontakt sieht Profilbild", r.status_code == 200)
ausgeliefert = r.content
check("Keine Metadaten im ausgelieferten Bild",
      b"GEHEIMKAMERA" not in ausgeliefert and b"Exif" not in ausgeliefert)
with Image.open(io.BytesIO(ausgeliefert)) as b:
    check("Kein EXIF nach dem Öffnen", len(b.getexif()) == 0, dict(b.getexif()))

r = chris.post("/api/netz/medien/banner",
               files={"datei": ("kopf.png", b"<?php system($_GET[1]); ?>", "image/png")})
check("Keine Bilddatei abgewiesen", r.status_code == 400, r.status_code)
ban = Image.new("RGB", (2000, 800), (16, 37, 51)); pb = io.BytesIO()
ban.save(pb, format="PNG")
r = chris.post("/api/netz/medien/banner",
               files={"datei": ("kopf.png", pb.getvalue(), "image/png")})
check("Kopfbild im Verhältnis 3:1", r.json()["breite"] == 1500
      and r.json()["hoehe"] == 500, r.text[:150])
bid = r.json()["id"]
r = ben.get(f"/api/netz/medien/{bid}")
check("Kopfbild nur für Kontakte", r.status_code == 404, r.status_code)
r = ben.get(f"/api/netz/medien/{av['id']}")
check("Profilbild für alle aktiven Mitglieder", r.status_code == 200, r.status_code)

# --- Moderation ----------------------------------------------------------
anna_post = anna.post("/api/netz/beitraege", json={"art": "text",
    "text": "Heute einen Patienten aus der Hauptstraße 5 versorgt."}).json()
r = chris.post(f"/api/netz/beitraege/{anna_post['id']}/moderieren", json={"grund": "x"})
check("Moderation verlangt Grund", r.status_code == 400, r.status_code)
r = ben.post(f"/api/netz/beitraege/{anna_post['id']}/melden")
check("Ben ist Annas Kontakt und kann melden", r.status_code == 200, r.text[:120])
r = chris.post(f"/api/netz/beitraege/{anna_post['id']}/moderieren",
               json={"grund": "Möglicher Patientenbezug (Adresse)"})
check("Administrator entfernt gemeldeten Beitrag", r.status_code == 200, r.text[:150])
r = ben.get("/api/netz/feed")
check("Entfernter Beitrag verschwindet aus dem Feed",
      all(b["id"] != anna_post["id"] for b in r.json()["beitraege"]))
r = anna.get(f"/api/netz/beitraege/{anna_post['id']}")
check("Autorin sieht den Grund", r.json()["entfernt"] and
      "Patientenbezug" in (r.json()["entfernt_grund"] or ""), r.text[:200])
r = anna.post(f"/api/netz/beitraege/{beitrag['id']}/moderieren", json={"grund": "weil ich will"})
check("Mitglied moderiert nicht", r.status_code == 403, r.status_code)
r = anna.delete(f"/api/netz/beitraege/{beitrag['id']}")
check("Mitglied löscht keine fremden Beiträge", r.status_code == 403, r.status_code)

# --- Gastrolle -----------------------------------------------------------
chris.patch(f"/api/admin/users/{BEN}", json={"role": "guest", "totp_code": code(csec)})
r = ben.post("/api/netz/beitraege", json={"art": "text", "text": "Hallo"})
check("Gast teilt keine Beiträge", r.status_code == 403, r.status_code)
chris.patch(f"/api/admin/users/{BEN}", json={"role": "user", "totp_code": code(csec)})

# --- Deaktivieren macht unsichtbar ---------------------------------------
chris.put("/api/netz/profil", json={"aktiv": False})
r = anna.get(f"/api/netz/personen/{CHRIS}")
check("Deaktiviertes Profil ist verschwunden", r.status_code == 404, r.status_code)
r = anna.get("/api/netz/feed")
check("Und seine Beiträge auch",
      all(b["autor"]["id"] != CHRIS for b in r.json()["beitraege"]))
chris.put("/api/netz/profil", json={"aktiv": True})

# --- DSGVO ---------------------------------------------------------------
aus = anna.get("/api/exports/my-data").json()
check("Auskunft enthält das Netzwerk",
      aus["netzwerk"]["kommentare"] and aus["netzwerk"]["reaktionen"]
      and aus["netzwerk"]["bestaetigungen_gegeben"], sorted(aus["netzwerk"]))
check("Auskunft nennt Kontakte nur mit Anzeigenamen",
      "chris@example" not in json.dumps(aus["netzwerk"], ensure_ascii=False))

r = anna.post("/api/account/delete", json={"password": "einsatzprotokoll2026",
    "confirm": "LÖSCHEN", "totp_code": "000000"})
from app.db import conn, scalar

with conn() as c:
    s = __import__("app.db", fromlist=["row"]).row(
        c, "SELECT secret FROM auth_totp WHERE user_id = :u", u=ANNA)["secret"]
r = anna.post("/api/account/delete", json={"password": "einsatzprotokoll2026",
    "confirm": "LÖSCHEN", "totp_code": code(s)})
check("Konto gelöscht", r.status_code == 200, r.text[:150])
with conn() as c:
    rest = sum(scalar(c, sql, u=ANNA) or 0 for sql in (
        "SELECT COUNT(*) FROM net_posts WHERE author_id = :u",
        "SELECT COUNT(*) FROM net_comments WHERE author_id = :u",
        "SELECT COUNT(*) FROM net_reactions WHERE user_id = :u",
        "SELECT COUNT(*) FROM net_connections WHERE requester_id = :u OR addressee_id = :u",
        "SELECT COUNT(*) FROM net_endorsements WHERE endorser_id = :u OR user_id = :u",
        "SELECT COUNT(*) FROM net_notifications WHERE user_id = :u OR actor_id = :u",
        "SELECT COUNT(*) FROM net_media WHERE user_id = :u",
    ))
check("Keine Netzwerkdaten der gelöschten Person übrig", rest == 0, rest)
komp = chris.get("/api/netz/profil").json()["kompetenzen"]
check("Ihre Bestätigung ist mit ihr verschwunden",
      komp[0]["bestaetigungen"] == 0, komp)

print("\nKompetenznetz: alle Prüfungen bestanden.")
