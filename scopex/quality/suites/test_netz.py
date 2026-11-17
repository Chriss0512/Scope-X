"""Kompetenznetz: Sichtbarkeit, Datenschutzgrenze, Medien, Nachrichten, DSGVO.

Der wichtigste Teil dieser Reihe ist die Datenschutzgrenze. Ein Einsatz
bekommt in jedem privaten Feld einen eindeutigen Markierwert; danach wird
jede Antwort, die ein anderes Mitglied erhält, als Zeichenkette nach diesen
Werten durchsucht — Feed, Entdecken, Profil, Chronik, Beitrag, Nachrichten,
Mitteilungen. Taucht einer auf, ist die Grenze verletzt, gleich über welches
Feld oder welchen Umweg.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import time as _t

os.environ["SCOPEX_DATABASE_URL"] = "sqlite:////tmp/scopex_q_netz.db"
os.environ["SCOPEX_MEDIA_DIR"] = "/tmp/scopex_q_netz_media"
if os.path.exists("/tmp/scopex_q_netz.db"):
    os.remove("/tmp/scopex_q_netz.db")
shutil.rmtree("/tmp/scopex_q_netz_media", ignore_errors=True)
sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parents[2].as_posix())
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.security import _totp_at
from quality import nachweis  # noqa: F401,E402


def check(n, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + n + (" :: " + str(extra) if not cond else ""))
    if not cond:
        sys.exit(1)


def code(sec):
    return _totp_at(sec, int(_t.time()) // 30)


# --- Vier Mitglieder -----------------------------------------------------
chris = TestClient(app); chris.__enter__()
r = chris.post("/api/auth/register", json={
    "username": "chris", "email": "chris@example.invalid",
    "password": "einsatzprotokoll2026", "first_name": "Christian",
    "last_name": "Faust", "qualification": "Notfallsanitäter*in"})
csec = r.json()["totp"]["secret"]
chris.post("/api/auth/totp/confirm", json={"code": code(csec)})
CHRIS = chris.get("/api/auth/state").json()["user"]["id"]
SECRETS = {}


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
    uid = k.get("/api/auth/state").json()["user"]["id"]
    SECRETS[uid] = s
    return k, uid


anna, ANNA = mitglied("anna", "Anna", "Berger")
ben, BEN = mitglied("ben", "Ben", "Kraus")
dora, DORA = mitglied("dora", "Dora", "Lenz")

# --- Voreinstellung: unsichtbar ------------------------------------------
check("Netzwerkprofil anfangs aus", chris.get("/api/netz/profil").json()["aktiv"] is False)
r = anna.get(f"/api/netz/personen/{CHRIS}")
check("Ohne eigenes Netz sieht man niemanden", r.status_code == 409, r.status_code)
check("Feed bei ausgeschaltetem Netz leer",
      chris.get("/api/netz/feed").json() == {"aktiv": False, "beitraege": [], "weiter": None})

for k in (chris, anna, ben, dora):
    k.put("/api/netz/profil", json={"aktiv": True})
chris.put("/api/netz/profil", json={"headline": "Notfallsanitäter · Praxisanleiter",
                                    "about": "Lernen im Rettungsdienst.",
                                    "organisation": "Rettungswache Nord"})
r = ben.put("/api/netz/profil", json={"privat": True})
check("Ben stellt auf privat", r.json()["privat"] is True)

r = anna.get("/api/netz/personen", params={"q": "faust"})
check("Suche findet aktives Mitglied", any(p["id"] == CHRIS for p in r.json()["personen"]))
check("Suche verrät weder Benutzernamen noch E-Mail",
      "chris@example" not in r.text and '"chris"' not in r.text, r.text[:200])

# --- Folgen: öffentlich ---------------------------------------------------
check("Sich selbst folgen geht nicht", anna.post(f"/api/netz/folgen/{ANNA}").status_code == 400)
r = anna.post(f"/api/netz/folgen/{CHRIS}")
check("Öffentlichem Konto sofort folgen", r.json()["ich_folge"] == "aktiv", r.json())
check("Mitteilung „folgt“",
      any(m["art"] == "folgt" for m in chris.get("/api/netz/mitteilungen").json()["mitteilungen"]))
p = anna.get(f"/api/netz/personen/{CHRIS}").json()
check("Öffentliches Profil voll sichtbar", p["voll"] and "eintraege" in p, sorted(p))
check("Auch ohne Folgen voll sichtbar (öffentlich)",
      dora.get(f"/api/netz/personen/{CHRIS}").json()["voll"])

# --- Folgen: privat --------------------------------------------------------
r = anna.post(f"/api/netz/folgen/{BEN}")
check("Privatem Konto: Anfrage", r.json()["ich_folge"] == "angefragt", r.json())
p = anna.get(f"/api/netz/personen/{BEN}").json()
check("Privates Profil zeigt nur den Kopf",
      not p["voll"] and "eintraege" not in p and "kompetenzen" not in p, sorted(p))
check("Anfrage im Zähler", ben.get("/api/netz/zaehler").json()["anfragen"] == 1)
ben_post = ben.post("/api/netz/beitraege", json={"art": "beitrag",
    "text": "Nur für Follower: #Atemweg Training heute."}).json()
check("Beitrag eines privaten Kontos vor Annahme 404",
      anna.get(f"/api/netz/beitraege/{ben_post['id']}").status_code == 404)
check("… und nicht im Feed", all(b["id"] != ben_post["id"]
      for b in anna.get("/api/netz/feed").json()["beitraege"]))
r = ben.post(f"/api/netz/follower/{ANNA}/annehmen")
check("Anfrage angenommen", r.status_code == 200, r.text[:100])
check("Nach Annahme sichtbar",
      anna.get(f"/api/netz/beitraege/{ben_post['id']}").status_code == 200)
r = dora.post("/api/netz/beitraege", json={"art": "repost", "repost_of": ben_post["id"]})
check("Wer den Beitrag nicht sieht, kann ihn nicht teilen", r.status_code == 404)
r = anna.post("/api/netz/beitraege", json={"art": "repost", "repost_of": ben_post["id"]})
check("Beiträge privater Konten lassen sich nicht weiterteilen", r.status_code == 403)

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
att = chris.post(f"/api/encounters/{enc['id']}/attempts", json={
    "measure_id": massnahme["id"], "outcome": "erfolgreich",
    "performed_at": "2026-11-14T03:19:00", "note": MARKEN["Notiz Maßnahme"],
    "complications": [{"id": zek[0]["id"], "relation": "ursächlich",
                       "patient_harm": MARKEN["Patientenschaden"]}]}).json()["attempts"][-1]
med = chris.post(f"/api/encounters/{enc['id']}/medications", json={
    "medication_id": medikament["id"], "dose": float(MARKEN["Dosis"]),
    "unit": "mg", "route": "intravenös", "note": MARKEN["Notiz Medikament"],
    "administered_at": "2026-11-14T03:25:00"}).json()["medications"][-1]
check("Einsatz mit Markierwerten angelegt", "id" in att and "id" in med)

r = chris.post("/api/netz/beitraege", json={
    "art": "kompetenz", "text": "Erster i.v.-Zugang unter schwierigen Bedingungen.",
    "attempt_ids": [att["id"]], "medication_ids": [med["id"]],
    "mit_zek": True, "mit_naca": True})
check("Kompetenzbeitrag geteilt", r.status_code == 200, r.text[:200])
kompetenz = r.json()
check("Schnappschuss enthält Maßnahme, Medikament, ZEK, NACA",
      kompetenz["kompetenz"]["massnahmen"][0]["name"] == massnahme["name"]
      and kompetenz["kompetenz"]["medikamente"][0]["divi_gruppe"]
      and kompetenz["kompetenz"]["zek"] and kompetenz["kompetenz"]["naca"] == "IV")

r = chris.post("/api/netz/beitraege", json={
    "art": "fall", "titel": "Seltene Anaphylaxie nach Insektenstich #Anaphylaxie",
    "details": {"kategorie": "selten", "besonderheit": "Biphasischer Verlauf.",
                "gut": "Frühe Adrenalingabe.", "anders": "Früher nachalarmieren."},
    "attempt_ids": [att["id"]], "verzoegerung_tage": 0})
check("Fallbericht geteilt", r.status_code == 200, r.text[:200])
fall = r.json()
geplant = chris.post("/api/netz/beitraege", json={
    "art": "fall", "titel": "Komplikation bei Thoraxdrainage",
    "details": {"kategorie": "komplikation", "besonderheit": "Fehllage."},
    "verzoegerung_tage": 7}).json()
check("Verzögerter Fall ist für den Autor geplant", geplant["geplant"] is True, geplant)
check("… und für andere unsichtbar",
      anna.get(f"/api/netz/beitraege/{geplant['id']}").status_code == 404)
r = chris.post("/api/netz/beitraege", json={"art": "fall", "titel": "Ohne Angaben",
    "details": {"kategorie": "weiss nicht", "besonderheit": "x"}})
check("Fall ohne gültige Kategorie abgewiesen", r.status_code == 400)
r = chris.post("/api/netz/beitraege", json={"art": "algorithmus",
    "titel": "Ablauf Anaphylaxie", "details": {"stand": "2025"}})
check("Algorithmus ohne Quelle abgewiesen", r.status_code == 400)
r = chris.post("/api/netz/beitraege", json={"art": "algorithmus",
    "titel": "Ablauf Anaphylaxie", "text": "Schema als Lernhilfe. #Anaphylaxie",
    "details": {"quelle": "SOP Rettungsdienst Musterregion", "stand": "2025"}})
check("Algorithmus mit Quelle geteilt", r.status_code == 200, r.text[:150])

anna.post(f"/api/netz/beitraege/{kompetenz['id']}/kommentare", json={"text": "Stark gelöst!"})
chris.post("/api/netz/nachrichten", json={"an": ANNA, "text": "Schau mal",
                                           "post_id": kompetenz["id"]})
liste = anna.get("/api/netz/nachrichten").json()
gid = (liste["gespraeche"] + liste["anfragen"])[0]["id"]
antworten = {
    "Für dich": anna.get("/api/netz/feed").text,
    "Folge ich": anna.get("/api/netz/feed", params={"modus": "folgeich"}).text,
    "Entdecken": dora.get("/api/netz/entdecken").text,
    "Profil": anna.get(f"/api/netz/personen/{CHRIS}").text,
    "Chronik": anna.get(f"/api/netz/personen/{CHRIS}/beitraege").text,
    "Beitrag": anna.get(f"/api/netz/beitraege/{kompetenz['id']}").text,
    "Fall": anna.get(f"/api/netz/beitraege/{fall['id']}").text,
    "Tag": anna.get("/api/netz/tags/anaphylaxie").text,
    "Nachrichten": anna.get(f"/api/netz/nachrichten/{gid}").text,
    "Mitteilungen": chris.get("/api/netz/mitteilungen").text,
}
for wo, text in antworten.items():
    for was, wert in MARKEN.items():
        check(f"{was} nicht in {wo}", wert not in text, f"{wert} gefunden")
    check(f"Keine encounter_id in {wo}", enc["id"] not in text)

with __import__("app.db", fromlist=["conn"]).conn() as c:
    spalten = {r_["name"] for r_ in c.exec_driver_sql(
        "PRAGMA table_info(net_posts)").mappings()}
verboten = {"encounter_id", "mission_number", "vehicle_id", "shift_code",
            "enc_date", "enc_time", "performed_at", "administered_at", "note",
            "dose", "patient_harm"}
check("net_posts hat keine Spalte für private Felder", not (spalten & verboten))

# --- Freitext gegen das eigene Logbuch ----------------------------------
for text, was in [
    (f"Einsatz {MARKEN['Einsatznummer']} war lehrreich", "Einsatznummer"),
    (f"Mit dem {MARKEN['Fahrzeug'].lower()} unterwegs", "Fahrzeug"),
    (f"Am {MARKEN['Datum deutsch']} hatten wir", "Datum"),
    ("Kurz nach 03:12 alarmiert", "Uhrzeit"),
    ("Gegen 3 Uhr nachts", "Uhrzeit mit Uhr"),
]:
    r = chris.post("/api/netz/beitraege", json={"art": "beitrag", "text": text})
    check(f"Beitrag mit {was} abgewiesen", r.status_code == 400, r.status_code)
r = chris.post("/api/netz/beitraege", json={"art": "fall", "titel": "Fall",
    "details": {"kategorie": "lernfall",
                "besonderheit": f"Mit {MARKEN['Fahrzeug']} angefahren"}})
check("Private Angaben auch in Falldetails abgewiesen", r.status_code == 400)
for text in ("Adrenalin 1:10 verdünnt", "Reanimation 30:2 und 15:2",
             "S3-Leitlinie vom 01.03.2024"):
    r = chris.post("/api/netz/beitraege", json={"art": "beitrag", "text": text})
    check(f"Kein Fehlalarm: {text}", r.status_code == 200, r.text[:150])
r = anna.post(f"/api/netz/beitraege/{kompetenz['id']}/kommentare",
              json={"text": "Wann war das? 03:12?"})
check("Uhrzeit auch im Kommentar abgewiesen", r.status_code == 400)
r = chris.post("/api/netz/eintraege", json={"art": "station",
    "titel": f"Fahrer {MARKEN['Fahrzeug']}"})
check("Private Angaben auch im Werdegang abgewiesen", r.status_code == 400)

# --- Fremde Einträge (IDOR) ----------------------------------------------
fremd = anna.post("/api/encounters", json={"enc_date": "2026-11-10",
                                          "enc_time": "10:00"}).json()
fatt = anna.post(f"/api/encounters/{fremd['id']}/attempts", json={
    "measure_id": massnahme["id"], "outcome": "erfolgreich"}).json()["attempts"][-1]
r = chris.post("/api/netz/beitraege", json={"art": "kompetenz", "attempt_ids": [fatt["id"]]})
check("Fremde Maßnahme lässt sich nicht teilen", r.status_code == 404)
r = chris.post("/api/netz/beitraege", json={"art": "kompetenz",
    "attempt_ids": [att["id"], fatt["id"]]})
check("Auch nicht gemischt mit eigener", r.status_code == 404)
anna.delete(f"/api/encounters/{fremd['id']}")

# --- Algorithmus ---------------------------------------------------------
dora_fall = dora.post("/api/netz/beitraege", json={"art": "fall",
    "titel": "Seltene Situation: Hypothermie im Sommer",
    "details": {"kategorie": "selten", "besonderheit": "Badesee, 14 Grad."}}).json()
fuer_ben = ben.get("/api/netz/feed").json()["beitraege"]
check("Für dich zeigt auch Beiträge von Personen, denen man nicht folgt",
      any(b["id"] == dora_fall["id"] for b in fuer_ben))
check("… nicht aber der Reiter Folge ich",
      all(b["id"] != dora_fall["id"] for b in
          ben.get("/api/netz/feed", params={"modus": "folgeich"}).json()["beitraege"]))
b_dora = next(b for b in fuer_ben if b["id"] == dora_fall["id"])
check("Begründung nennt die Fallart", "Seltene Situation" in b_dora["warum"], b_dora["warum"])
b_komp = next((b for b in anna.get("/api/netz/feed").json()["beitraege"]
               if b["id"] == kompetenz["id"]), None)
check("Kompetenzbeitrag im Feed einer Followerin", b_komp is not None)
check("Begründung nennt Nähe", any("Du folgst" in g for g in b_komp["warum"]), b_komp["warum"])
b_komp_ben = next(b for b in fuer_ben if b["id"] == kompetenz["id"])
check("Lernlücke wird erkannt",
      any("selten dokumentierst" in g for g in b_komp_ben["warum"]), b_komp_ben["warum"])
check("Nicht interessiert",
      ben.post(f"/api/netz/beitraege/{dora_fall['id']}/ausblenden").status_code == 200)
check("Ausgeblendeter Beitrag verschwindet",
      all(b["id"] != dora_fall["id"] for b in ben.get("/api/netz/feed").json()["beitraege"]))
r = ben.get("/api/netz/suche", params={"q": "#anaph"})
check("Hashtag-Suche", any(t["tag"] == "anaphylaxie" for t in r.json()["tags"]), r.text)
check("Beiträge zum Hashtag", anna.get("/api/netz/tags/anaphylaxie").json()["anzahl"] >= 2)

# --- Gefällt mir, Kommentare, Repost -------------------------------------
r = anna.put(f"/api/netz/beitraege/{fall['id']}/like")
check("Gefällt mir", r.json() == {"likes": 1, "ich_like": True}, r.json())
check("Kein doppeltes Gefällt mir",
      anna.put(f"/api/netz/beitraege/{fall['id']}/like").json()["likes"] == 1)
anna.delete(f"/api/netz/beitraege/{fall['id']}/like")
anna.put(f"/api/netz/beitraege/{fall['id']}/like")
likes = [m for m in chris.get("/api/netz/mitteilungen").json()["mitteilungen"]
         if m["art"] == "like" and m["post_id"] == fall["id"]]
check("Erneutes Gefällt mir erzeugt keine zweite Mitteilung", len(likes) == 1, len(likes))
r = anna.post("/api/netz/beitraege", json={"art": "repost", "repost_of": fall["id"],
                                          "text": "Unbedingt lesen!"})
check("Repost", r.status_code == 200 and r.json()["original"]["id"] == fall["id"], r.text[:150])
rp = r.json()
check("Nur ein Repost je Beitrag", anna.post("/api/netz/beitraege", json={
    "art": "repost", "repost_of": fall["id"]}).status_code == 409)
check("Repost zählt am Original",
      chris.get(f"/api/netz/beitraege/{fall['id']}").json()["reposts"] == 1)
check("Fremde löschen keine Beiträge",
      ben.delete(f"/api/netz/beitraege/{fall['id']}").status_code == 404)
kid = anna.get(f"/api/netz/beitraege/{kompetenz['id']}/kommentare").json()["kommentare"][0]["id"]
check("Fremde löschen keine Kommentare",
      dora.delete(f"/api/netz/kommentare/{kid}").status_code == 403)

# --- Bilder --------------------------------------------------------------
foto = Image.new("RGB", (900, 1200), (18, 104, 120))
exif = Image.Exif()
exif[0x8825] = {2: (52.0, 31.0, 0.0), 4: (9.0, 44.0, 0.0)}  # GPS
exif[0x010F] = "GEHEIMKAMERA"
puffer = io.BytesIO()
foto.save(puffer, format="JPEG", exif=exif)
roh = puffer.getvalue()
check("Testbild trägt GPS-Metadaten", b"GEHEIMKAMERA" in roh)
r = chris.post("/api/netz/medien/bild", files={"datei": ("f.jpg", roh, "image/jpeg")})
check("Beitragsbild hochgeladen", r.status_code == 200 and r.json()["status"] == "bereit",
      r.text[:150])
bild = r.json()
check("Hochformat auf 4:5 begrenzt", abs(bild["breite"] / bild["hoehe"] - 0.8) < 0.01, bild)
check("Entwurf für andere unsichtbar",
      anna.get(f"/api/netz/medien/{bild['id']}").status_code == 404)
r = chris.post("/api/netz/beitraege", json={"art": "beitrag", "text": "Neue Trage",
                                           "medien_ids": [bild["id"]]})
check("Ohne Bestätigung zum Personenbezug abgewiesen", r.status_code == 400)
r = chris.post("/api/netz/beitraege", json={"art": "beitrag", "text": "Neue Trage #Material",
    "medien_ids": [bild["id"]], "medien_bestaetigt": True})
check("Mit Bestätigung geteilt", r.status_code == 200 and len(r.json()["medien"]) == 1)
r = anna.get(f"/api/netz/medien/{bild['id']}")
check("Bild über den Beitrag sichtbar", r.status_code == 200)
check("Keine Metadaten im ausgelieferten Bild",
      b"GEHEIMKAMERA" not in r.content and b"Exif" not in r.content)
with Image.open(io.BytesIO(r.content)) as b:
    check("Kein EXIF nach dem Öffnen", len(b.getexif()) == 0)
r = chris.post("/api/netz/beitraege", json={"art": "beitrag", "text": "Nochmal",
    "medien_ids": [bild["id"]], "medien_bestaetigt": True})
check("Ein Medium hängt an genau einem Beitrag", r.status_code == 404)
r = chris.post("/api/netz/medien/banner",
               files={"datei": ("k.png", b"<?php system($_GET[1]); ?>", "image/png")})
check("Keine Bilddatei abgewiesen", r.status_code == 400)
av = ben.post("/api/netz/medien/avatar", files={"datei": ("a.jpg", roh, "image/jpeg")}).json()
check("Profilbild quadratisch", av["breite"] == av["hoehe"] == 512, av)
check("Profilbild eines privaten Kontos für alle sichtbar",
      dora.get(f"/api/netz/medien/{av['id']}").status_code == 200)
pb = io.BytesIO(); Image.new("RGB", (2000, 800)).save(pb, format="PNG")
ban = ben.post("/api/netz/medien/banner",
               files={"datei": ("k.png", pb.getvalue(), "image/png")}).json()
check("Kopfbild 3:1", (ban["breite"], ban["hoehe"]) == (1500, 500))
check("Kopfbild eines privaten Kontos nur für Follower",
      dora.get(f"/api/netz/medien/{ban['id']}").status_code == 404
      and anna.get(f"/api/netz/medien/{ban['id']}").status_code == 200)

# --- Video ---------------------------------------------------------------
import imageio_ffmpeg

roh_video = "/tmp/scopex_q_netz_roh.mp4"
subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
                "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25",
                "-f", "lavfi", "-i", "sine=frequency=440", "-t", "2",
                "-metadata", "title=GEHEIMVIDEO",
                "-metadata", "location=+52.5200+013.4050/",
                "-movflags", "+use_metadata_tags",
                "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                roh_video], check=True)
inhalt = open(roh_video, "rb").read()
check("Testvideo trägt Orts- und Titelangaben",
      b"GEHEIMVIDEO" in inhalt and b"52.5200" in inhalt)
r = chris.post("/api/netz/medien/video", files={"datei": ("v.mp4", inhalt, "video/mp4")})
check("Video angenommen", r.status_code == 200 and r.json()["status"] == "verarbeitung",
      r.text[:150])
vid = r.json()["id"]
for _ in range(240):
    st = chris.get(f"/api/netz/medien/{vid}/status").json()
    if st["status"] != "verarbeitung":
        break
    _t.sleep(0.5)
check("Video verarbeitet", st["status"] == "bereit", st)
check("Dauer erkannt", 1.5 <= (st["dauer"] or 0) <= 2.5, st)
chris.post("/api/netz/beitraege", json={"art": "beitrag", "text": "Video vom Training",
    "medien_ids": [vid], "medien_bestaetigt": True})
r = anna.get(f"/api/netz/medien/{vid}")
check("Video ausgeliefert", r.status_code == 200 and r.headers["content-type"] == "video/mp4")
check("Keine Orts- oder Titelangaben im Video",
      b"GEHEIMVIDEO" not in r.content and b"52.5200" not in r.content)
r = anna.get(f"/api/netz/medien/{vid}", headers={"Range": "bytes=0-99"})
check("Video spulbar (Range)", r.status_code == 206 and len(r.content) == 100, r.status_code)
check("Vorschaubild vorhanden",
      anna.get(f"/api/netz/medien/{vid}/vorschau").headers["content-type"] == "image/jpeg")
# Eine als Video getarnte HLS-Wiedergabeliste, die eine Serverdatei
# einbinden will. ffmpeg darf sie gar nicht erst als Eingabe annehmen.
hls = b"#EXTM3U\n#EXT-X-MEDIA-SEQUENCE:0\n#EXTINF:10.0,\nfile:///etc/passwd\n#EXT-X-ENDLIST\n"
bad = chris.post("/api/netz/medien/video", files={"datei": ("v.mp4", hls,
                                                           "video/mp4")}).json()["id"]
for _ in range(80):
    st = chris.get(f"/api/netz/medien/{bad}/status").json()
    if st["status"] != "verarbeitung":
        break
    _t.sleep(0.25)
check("Getarnte Wiedergabeliste endet mit Fehler", st["status"] == "fehler" and st["fehler"], st)

# --- Nachrichten ---------------------------------------------------------
r = dora.post("/api/netz/nachrichten", json={"an": CHRIS, "text": "Hallo, kurze Frage!"})
check("Nachricht an jemanden, der einem nicht folgt", r.status_code == 200, r.text[:150])
dgid = r.json()["gespraech"]
g = chris.get("/api/netz/nachrichten").json()
check("Landet bei Chris unter Anfragen",
      any(x["id"] == dgid for x in g["anfragen"])
      and all(x["id"] != dgid for x in g["gespraeche"]))
check("Anfragen zählen nicht als ungelesene Nachrichten",
      chris.get("/api/netz/zaehler").json()["nachrichten"] == 0)
chris.get(f"/api/netz/nachrichten/{dgid}")
v = dora.get(f"/api/netz/nachrichten/{dgid}").json()
check("Offene Anfrage verrät kein Gelesen", v["wartet"] and not v["nachrichten"][0]["gelesen"])
r = chris.post(f"/api/netz/nachrichten/{dgid}", json={"text": "Gern, um 14:30?"})
check("Antworten nimmt an; Uhrzeit in Nachrichten erlaubt", r.status_code == 200, r.text[:120])
r = chris.post(f"/api/netz/nachrichten/{dgid}",
               json={"text": f"War Einsatz {MARKEN['Einsatznummer']}"})
check("Eigene Einsatznummer auch in Nachrichten gesperrt", r.status_code == 400)
check("Gegenüber hat ungelesene Nachricht",
      dora.get("/api/netz/zaehler").json()["nachrichten"] == 1)
v = dora.get(f"/api/netz/nachrichten/{dgid}").json()
check("Verlauf in richtiger Reihenfolge",
      [n["text"] for n in v["nachrichten"]] == ["Hallo, kurze Frage!", "Gern, um 14:30?"])
check("Gelesen setzt Zähler zurück", dora.get("/api/netz/zaehler").json()["nachrichten"] == 0)
check("Fremde lesen kein Gespräch", ben.get(f"/api/netz/nachrichten/{dgid}").status_code == 404)
check("Unsichtbaren Beitrag kann man nicht senden",
      dora.post(f"/api/netz/nachrichten/{dgid}",
                json={"post_id": ben_post["id"]}).status_code == 404)
chris.post(f"/api/netz/nachrichten/{dgid}", json={"post_id": kompetenz["id"]})
chris.put("/api/netz/profil", json={"privat": True})
v = dora.get(f"/api/netz/nachrichten/{dgid}").json()
check("Gesendeter Beitrag folgt der Sichtbarkeit",
      v["nachrichten"][-1]["beitrag"] == {"nicht_verfuegbar": True}, v["nachrichten"][-1])
chris.put("/api/netz/profil", json={"privat": False})
nid = v["nachrichten"][0]["id"]
check("Fremde Nachricht nicht zurücknehmbar",
      chris.delete(f"/api/netz/nachrichten/nachricht/{nid}").status_code == 404)
check("Eigene Nachricht zurücknehmen",
      dora.delete(f"/api/netz/nachrichten/nachricht/{nid}").status_code == 200)

# --- Blockieren ----------------------------------------------------------
check("Blockieren", chris.post(f"/api/netz/blockieren/{DORA}").status_code == 200)
check("Blockierte Person findet das Profil nicht",
      dora.get(f"/api/netz/personen/{CHRIS}").status_code == 404)
check("… kann nicht folgen", dora.post(f"/api/netz/folgen/{CHRIS}").status_code == 404)
check("… nicht schreiben", dora.post("/api/netz/nachrichten",
                                     json={"an": CHRIS, "text": "?"}).status_code == 404)
check("… das Gespräch ist weg", dora.get(f"/api/netz/nachrichten/{dgid}").status_code == 404)
check("… und sieht keine Beiträge",
      dora.get(f"/api/netz/beitraege/{fall['id']}").status_code == 404)
check("Beiträge der Blockierten verschwinden aus dem eigenen Feed",
      all(b["autor"]["id"] != DORA for b in chris.get("/api/netz/feed").json()["beitraege"]))
check("Blockierte Person taucht in der Suche nicht auf",
      all(p["id"] != DORA for p in chris.get("/api/netz/personen",
          params={"q": "lenz"}).json()["personen"]))
chris.delete(f"/api/netz/blockieren/{DORA}")
check("Entblocken", dora.get(f"/api/netz/personen/{CHRIS}").status_code == 200)

# --- Bestätigungen -------------------------------------------------------
chris.put(f"/api/netz/kompetenzen/{massnahme['id']}", json={"sichtbar": True})
r = anna.post("/api/netz/bestaetigungen", json={"user_id": CHRIS,
    "measure_id": massnahme["id"], "rolle": "praxisanleitung"})
check("Ohne gegenseitiges Folgen keine Bestätigung", r.status_code == 403, r.status_code)
chris.post(f"/api/netz/folgen/{ANNA}")
r = anna.post("/api/netz/bestaetigungen", json={"user_id": CHRIS,
    "measure_id": massnahme["id"], "rolle": "praxisanleitung"})
check("Gegenseitig gefolgt: bestätigt", r.status_code == 200, r.text[:150])
check("Nur eine Bestätigung je Person", anna.post("/api/netz/bestaetigungen", json={
    "user_id": CHRIS, "measure_id": massnahme["id"]}).status_code == 409)
komp = anna.get(f"/api/netz/personen/{CHRIS}").json()["kompetenzen"]
check("Kompetenz mit Anzahl und Bestätigung",
      komp and komp[0]["anzahl"] == 1 and komp[0]["praxisanleitung"] == 1, komp)
chris.delete(f"/api/netz/follower/{ANNA}")
komp = chris.get("/api/netz/profil").json()["kompetenzen"]
check("Follower entfernen hebt Bestätigungen auf", komp[0]["bestaetigungen"] == 0, komp)
anna.post(f"/api/netz/folgen/{CHRIS}")

# --- Werdegang -----------------------------------------------------------
r = chris.post("/api/netz/eintraege", json={"art": "zertifikat", "titel": "PHTLS Provider",
    "org": "NAEMT", "von": "2025-03", "bis": "2029-03"})
check("Zertifikat eingetragen", r.status_code == 200 and r.json()["eintraege"])
check("Werdegang im öffentlichen Profil",
      anna.get(f"/api/netz/personen/{CHRIS}").json()["eintraege"][0]["titel"] == "PHTLS Provider")

# --- Moderation ----------------------------------------------------------
anna_post = anna.post("/api/netz/beitraege", json={"art": "beitrag",
    "text": "Heute einen Patienten aus der Hauptstraße 5 versorgt."}).json()
check("Moderation verlangt Grund", chris.post(
    f"/api/netz/beitraege/{anna_post['id']}/moderieren", json={"grund": "x"}).status_code == 400)
check("Melden", dora.post(f"/api/netz/beitraege/{anna_post['id']}/melden").status_code == 200)
r = chris.post(f"/api/netz/beitraege/{anna_post['id']}/moderieren",
               json={"grund": "Möglicher Patientenbezug (Adresse)"})
check("Administrator entfernt gemeldeten Beitrag", r.status_code == 200, r.text[:150])
check("Entfernter Beitrag verschwindet",
      dora.get(f"/api/netz/beitraege/{anna_post['id']}").status_code == 404)
r = anna.get(f"/api/netz/beitraege/{anna_post['id']}")
check("Autorin sieht den Grund", r.json()["entfernt"] and
      "Patientenbezug" in (r.json()["entfernt_grund"] or ""))
check("Mitglied moderiert nicht", anna.post(f"/api/netz/beitraege/{fall['id']}/moderieren",
      json={"grund": "weil ich will"}).status_code == 403)

# --- Gastrolle -----------------------------------------------------------
chris.patch(f"/api/admin/users/{DORA}", json={"role": "guest", "totp_code": code(csec)})
check("Gast teilt keine Beiträge", dora.post("/api/netz/beitraege",
      json={"art": "beitrag", "text": "Hallo"}).status_code == 403)
check("Gast sendet keine Nachrichten", dora.post("/api/netz/nachrichten",
      json={"an": CHRIS, "text": "Hallo"}).status_code == 403)
chris.patch(f"/api/admin/users/{DORA}", json={"role": "user", "totp_code": code(csec)})

# --- Ausschalten macht unsichtbar ----------------------------------------
chris.put("/api/netz/profil", json={"aktiv": False})
check("Ausgeschaltetes Profil verschwunden",
      anna.get(f"/api/netz/personen/{CHRIS}").status_code == 404)
check("Und seine Beiträge auch",
      all(b["autor"]["id"] != CHRIS for b in anna.get("/api/netz/feed").json()["beitraege"]))
check("Repost zeigt das Original als nicht verfügbar",
      anna.get(f"/api/netz/beitraege/{rp['id']}").json()["original"] ==
      {"nicht_verfuegbar": True})
chris.put("/api/netz/profil", json={"aktiv": True})

# --- DSGVO ---------------------------------------------------------------
aus = anna.get("/api/exports/my-data").json()["netzwerk"]
check("Auskunft enthält das Netzwerk",
      aus["kommentare"] and aus["gefaellt_mir"] and aus["folge_ich"] and aus["nachrichten"],
      sorted(aus))
check("Auskunft nennt Personen nur mit Anzeigenamen",
      "chris@example" not in json.dumps(aus, ensure_ascii=False))

from app.db import conn, scalar

with conn() as c:
    vid_datei = scalar(c, "SELECT file FROM net_media WHERE id = :i", i=vid)
r = anna.post("/api/account/delete", json={"password": "einsatzprotokoll2026",
    "confirm": "LÖSCHEN", "totp_code": code(SECRETS[ANNA])})
check("Konto gelöscht", r.status_code == 200, r.text[:150])
with conn() as c:
    rest = sum(scalar(c, sql, u=ANNA) or 0 for sql in (
        "SELECT COUNT(*) FROM net_posts WHERE author_id = :u",
        "SELECT COUNT(*) FROM net_comments WHERE author_id = :u",
        "SELECT COUNT(*) FROM net_likes WHERE user_id = :u",
        "SELECT COUNT(*) FROM net_follows WHERE follower_id = :u OR followee_id = :u",
        "SELECT COUNT(*) FROM net_endorsements WHERE endorser_id = :u OR user_id = :u",
        "SELECT COUNT(*) FROM net_notifications WHERE user_id = :u OR actor_id = :u",
        "SELECT COUNT(*) FROM net_conversations WHERE user_a = :u OR user_b = :u",
        "SELECT COUNT(*) FROM net_media WHERE user_id = :u",
    ))
check("Keine Netzwerkdaten der gelöschten Person übrig", rest == 0, rest)
check("Fremde Mediendateien bleiben erhalten",
      vid_datei in os.listdir("/tmp/scopex_q_netz_media"))
check("Ihr Repost ist mit ihr verschwunden",
      chris.get(f"/api/netz/beitraege/{fall['id']}").json()["reposts"] == 0)
chris.delete(f"/api/netz/beitraege/{fall['id']}")
check("Beitrag löschen", chris.get(f"/api/netz/beitraege/{fall['id']}").status_code == 404)

print("\nKompetenznetz: alle Prüfungen bestanden.")
