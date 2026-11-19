"""4.5.0: Zugang, Kataloge, Netzwerk, Themen, Fallvorstellung.

Schwerpunkte:

* Nutzungsvereinbarung: ohne Zustimmung kein Konto; eine neue Fassung
  sperrt alles außer Anmeldung, Vereinbarung, Auskunft und Löschung.
* Bewerbung: immer dieselbe Antwort nach außen; bürgende Mitglieder sehen
  keine E-Mail-Adresse; nur das genannte Mitglied kann antworten; Annahme
  nur mit frischem Code; Bewerbung verschwindet mit der Registrierung.
* Ort und Qualifikation privater Konten fließen weder in Vorschläge noch
  in Suchfilter ein.
* Ignorierte Folgeanfragen senden kein Signal.
* Gemerkte Beiträge verschaffen keinen Zugriff.
"""
import os
import shutil
import sys
import time as _t

os.environ["SCOPEX_DATABASE_URL"] = "sqlite:////tmp/scopex_q_zugang.db"
os.environ["SCOPEX_MEDIA_DIR"] = "/tmp/scopex_q_zugang_media"
if os.path.exists("/tmp/scopex_q_zugang.db"):
    os.remove("/tmp/scopex_q_zugang.db")
shutil.rmtree("/tmp/scopex_q_zugang_media", ignore_errors=True)
sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parents[2].as_posix())
from fastapi.testclient import TestClient

from app import mailer, nutzung
from app.main import app
from app.security import _totp_at
from quality import nachweis  # noqa: F401,E402


def check(n, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + n + (" :: " + str(extra) if not cond else ""))
    if not cond:
        sys.exit(1)


def code(sec):
    return _totp_at(sec, int(_t.time()) // 30)


# Mailversand abfangen: die Bewerbung braucht ihn, die Tests lesen die
# Links aus den Nachrichten.
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


chris = TestClient(app); chris.__enter__()

# --- Nutzungsvereinbarung bei der Registrierung ---------------------------
r = chris.post("/api/auth/register", json={
    "username": "chris", "email": "chris@example.invalid",
    "password": "einsatzprotokoll2026", "first_name": "Christian",
    "last_name": "Faust", "nutzung_akzeptiert": False})
check("Ohne Zustimmung kein Konto", r.status_code == 400, r.status_code)
r = chris.post("/api/auth/register", json={
    "username": "chris", "email": "chris@example.invalid",
    "password": "einsatzprotokoll2026", "first_name": "Christian",
    "last_name": "Faust"})
csec = r.json()["totp"]["secret"]
chris.post("/api/auth/totp/confirm", json={"code": code(csec)})
st = chris.get("/api/auth/state").json()
CHRIS = st["user"]["id"]
check("Zustimmung bei Registrierung gespeichert", st["nutzung_offen"] is False, st)
oe = TestClient(app).get("/api/oeffentlich/nutzungsbedingungen").json()
check("Vereinbarung öffentlich lesbar",
      oe["version"] == nutzung.VERSION and len(oe["abschnitte"]) >= 8)
check("Schweigepflicht ist Teil der Vereinbarung",
      any("203" in " ".join(a["absaetze"]) for a in oe["abschnitte"]))

SECRETS = {}


def mitglied(name, vorname, nachname):
    r = chris.post("/api/admin/invitations", json={"role": "user", "note": name,
        "valid_days": 7, "totp_code": code(csec)})
    k = TestClient(app)
    r = k.post("/api/auth/register", json={"username": name,
        "email": f"{name}@example.invalid", "password": "einsatzprotokoll2026",
        "first_name": vorname, "last_name": nachname,
        "invite_code": r.json()["code"]})
    s = r.json()["totp"]["secret"]
    k.post("/api/auth/totp/confirm", json={"code": code(s)})
    uid = k.get("/api/auth/state").json()["user"]["id"]
    SECRETS[uid] = s
    return k, uid


anna, ANNA = mitglied("anna", "Anna", "Berger")
ben, BEN = mitglied("ben", "Ben", "Kraus")
dora, DORA = mitglied("dora", "Dora", "Lenz")
for k in (chris, anna, ben, dora):
    k.put("/api/netz/profil", json={"aktiv": True})

# --- Neue Fassung: alles außer dem Nötigsten wartet -----------------------
alt = nutzung.VERSION
nutzung.VERSION = "2099-01"
r = anna.get("/api/netz/feed")
check("Neue Fassung sperrt den Feed mit 428", r.status_code == 428, r.status_code)
check("Anmeldestatus bleibt erreichbar und meldet offen",
      anna.get("/api/auth/state").json()["nutzung_offen"] is True)
check("Datenauskunft bleibt erreichbar",
      anna.get("/api/exports/my-data").status_code == 200)
r = anna.post("/api/nutzung/zustimmen", json={"version": alt})
check("Zustimmung zu veralteter Fassung abgewiesen", r.status_code == 409)
r = anna.post("/api/nutzung/zustimmen", json={"version": "2099-01"})
check("Zustimmung zur aktuellen Fassung", r.status_code == 200)
check("Danach wieder frei", anna.get("/api/netz/feed").status_code == 200)
nutzung.VERSION = alt

# --- Kataloge --------------------------------------------------------------
kreise = TestClient(app).get("/api/oeffentlich/kreise").json()["kreise"]
check("400 Kreise öffentlich", len(kreise) == 400, len(kreise))
HK = next(k["ags"] for k in kreise if k["name"] == "Heidekreis")
HAN = next(k["ags"] for k in kreise if k["name"] == "Region Hannover")
check("Doppelte Namen unterscheidbar",
      any(k["name"] == "München (Stadt)" for k in kreise))
orgs = anna.get("/api/netz/katalog/organisationen").json()["organisationen"]
DRK = next(o["id"] for o in orgs if "Rotes Kreuz" in o["name"])
r = anna.post("/api/netz/katalog/wachen", json={"name": "Rettungswache Soltau",
                                                "organisation_id": DRK})
check("Wache ohne Kreis abgewiesen", r.status_code in (400, 422), r.status_code)
r = anna.post("/api/netz/katalog/wachen", json={"name": "Rettungswache Soltau",
    "organisation_id": DRK, "kreis_ags": HK})
WACHE = r.json()["id"]
r2 = ben.post("/api/netz/katalog/wachen", json={"name": "rettungswache  soltau",
    "organisation_id": DRK, "kreis_ags": HK})
check("Gleiche Wache wird nicht doppelt angelegt", r2.json()["id"] == WACHE, r2.json())
for k in (anna, ben):
    k.put("/api/netz/profil/ort", json={"kreis_ags": HK, "organisation_id": DRK,
                                        "wache_id": WACHE})
dora.put("/api/netz/profil/ort", json={"kreis_ags": HK})
check("Unbekannter Kreis abgewiesen",
      dora.put("/api/netz/profil/ort", json={"kreis_ags": "99999"}).status_code == 400)

quals = anna.get("/api/netz/katalog/qualifikationen").json()["qualifikationen"]
ALS = next(x["id"] for x in quals if x["kurz"] == "ERC ALS")
PHTLS = next(x["id"] for x in quals if x["kurz"] == "PHTLS")
PAL = next(x["id"] for x in quals if x["name"].startswith("Praxisanleit"))
r = anna.post("/api/netz/qualifikationen", json={"qual_id": PHTLS, "erworben": "2025-03"})
eintrag = next(x for x in r.json()["qualifikationen"] if x["qual_id"] == PHTLS)
check("PHTLS: Ablauf nach vier Jahren berechnet", eintrag["gueltig_bis"] == "2029-03",
      eintrag)
r = anna.post("/api/netz/qualifikationen", json={"qual_id": ALS, "erworben": "2020-01"})
als = next(x for x in r.json()["qualifikationen"] if x["qual_id"] == ALS)
check("Abgelaufenes ALS als abgelaufen markiert", als["status"] == "abgelaufen", als)
ben.post("/api/netz/qualifikationen", json={"qual_id": PHTLS, "erworben": "2025-06"})
ben.post("/api/netz/qualifikationen", json={"qual_id": PAL})
p = chris.get(f"/api/netz/personen/{ANNA}").json()
check("Andere sehen keine abgelaufene Qualifikation",
      all(x["qual_id"] != ALS for x in p["qualifikationen"]), p["qualifikationen"])
check("Andere sehen keine Ablaufdaten",
      all(x["gueltig_bis"] == "" for x in p["qualifikationen"]))
check("Abzeichen im Profilkopf", "PHTLS" in p["abzeichen"] and "ERC ALS" not in
      p["abzeichen"], p["abzeichen"])

anna.get("/api/netz/zaehler")
check("Erinnerung an abgelaufene Qualifikation", any(
    m["art"] == "qualifikation" and "ERC ALS" in m["text"]
    for m in anna.get("/api/netz/mitteilungen").json()["mitteilungen"]))
anna.get("/api/netz/zaehler")
check("Erinnerung nur einmal", sum(
    m["art"] == "qualifikation"
    for m in anna.get("/api/netz/mitteilungen").json()["mitteilungen"]) == 1)
r = anna.post("/api/netz/fortbildungen", json={"titel": "Pädagogischer Fachtag",
    "datum": f"{_t.gmtime().tm_year}-02-10", "stunden": 8, "qual_id": PAL})
check("Fortbildung eingetragen", r.json()["summe"] == 8, r.json())
check("Fortbildung bleibt privat", "Fachtag" not in chris.get(
    f"/api/netz/personen/{ANNA}").text)

# --- Ben wird privat: Ort und Kurse fließen nirgends ein ------------------
ben.put("/api/netz/profil", json={"privat": True})
v = dora.get("/api/netz/vorschlaege", params={"anzahl": 30}).json()["personen"]
anna_v = next(x for x in v if x["id"] == ANNA)
ben_v = next((x for x in v if x["id"] == BEN), None)
check("Vorschlag mit Ortsbezug für öffentliches Konto",
      any("Heidekreis" in g for g in anna_v["gruende"]), anna_v)
check("Privates Konto: kein Ortsbezug im Vorschlag",
      ben_v is None or not any("Heidekreis" in g or "Wache" in g or "Organisation" in g
                               for g in ben_v["gruende"]), ben_v)
v = anna.get("/api/netz/vorschlaege", params={"anzahl": 30}).json()["personen"]
check("Privates Konto: Wache auch für Kolleg*innen nicht ausgewertet",
      all(x["id"] != BEN or "Gleiche Wache" not in x["gruende"] for x in v))
r = dora.get("/api/netz/suche", params={"wache": WACHE}).json()
ids = {x["id"] for x in r["personen"]}
check("Wachen-Filter findet öffentliches Konto", ANNA in ids, ids)
check("Wachen-Filter verrät privates Konto nicht", BEN not in ids, ids)
r = dora.get("/api/netz/suche", params={"qualifikation": PHTLS}).json()
check("Qualifikationsfilter verrät privates Konto nicht",
      BEN not in {x["id"] for x in r["personen"]})
check("Abzeichen privater Konten nur für Follower",
      dora.get(f"/api/netz/personen/{BEN}").json()["abzeichen"] == [])
dora.post(f"/api/netz/vorschlaege/{ANNA}/ausblenden")
check("Ausgeblendeter Vorschlag kommt nicht wieder", all(
    x["id"] != ANNA for x in dora.get("/api/netz/vorschlaege",
                                      params={"anzahl": 30}).json()["personen"]))

# --- Folgeanfrage ignorieren ----------------------------------------------
dora.post(f"/api/netz/folgen/{BEN}")
check("Anfrage im Zähler", ben.get("/api/netz/zaehler").json()["anfragen"] == 1)
n = ben.get("/api/netz/netzwerk").json()
check("Netzwerk zeigt die Anfrage", [x["id"] for x in n["anfragen"]] == [DORA], n["anfragen"])
check("Fremde können nicht ignorieren",
      anna.post(f"/api/netz/follower/{DORA}/ignorieren").status_code == 404)
ben.post(f"/api/netz/follower/{DORA}/ignorieren")
n = ben.get("/api/netz/netzwerk").json()
check("Ignoriert: nicht mehr unter Anfragen, aber unter Ignoriert",
      not n["anfragen"] and [x["id"] for x in n["ignoriert"]] == [DORA])
check("Ignoriert: kein Zähler", ben.get("/api/netz/zaehler").json()["anfragen"] == 0)
check("Ignoriert: für Dora weiter „angefragt“",
      dora.get(f"/api/netz/personen/{BEN}").json()["ich_folge"] == "angefragt")
check("Ignoriert: kein Signal in Doras Netzwerk",
      "ignoriert" not in dora.get("/api/netz/netzwerk").text.replace('"ignoriert":[]', ""))
check("Ignoriert: Auskunft der Anfragenden zeigt „angefragt“", all(
    f["status"] != "ignoriert"
    for f in dora.get("/api/exports/my-data").json()["netzwerk"]["folge_ich"]))
r = ben.post(f"/api/netz/follower/{DORA}/annehmen")
check("Ignorierte Anfrage später annehmbar", r.status_code == 200)

# --- Themen und Feed-Routing ----------------------------------------------
th = anna.get("/api/netz/themen").json()
check("Kuratierte Themen", {"atemwegsmanagement", "ekg-quiz", "recht-2anotsang",
                            "praxisanleitung", "luftrettung", "peer-hilfe"}
      <= {t["code"] for t in th["themen"]})
r = chris.post("/api/netz/beitraege", json={"art": "beitrag",
    "text": "Videolaryngoskopie im Training", "themen": ["atemwegsmanagement"]})
ATEM = r.json()["id"]
check("Thema am Beitrag", r.json()["themen"][0]["code"] == "atemwegsmanagement")
check("Unbekanntes Thema abgewiesen", chris.post("/api/netz/beitraege", json={
    "art": "beitrag", "text": "x", "themen": ["gibtsnicht"]}).status_code == 400)
chris.post("/api/netz/beitraege", json={"art": "beitrag", "text": "Dienstplan-Frage"})
f = anna.get("/api/netz/feed", params={"thema": "atemwegsmanagement"}).json()
check("Feed nach Thema gefiltert", [b["id"] for b in f["beitraege"]] == [ATEM], f)
anna.put("/api/netz/themen/atemwegsmanagement/folgen")
f = anna.get("/api/netz/feed", params={"modus": "themen"}).json()
check("Modus Themen zeigt gefolgte Themen", [b["id"] for b in f["beitraege"]] == [ATEM])
f = anna.get("/api/netz/feed").json()
b = next(x for x in f["beitraege"] if x["id"] == ATEM)
check("Grund: gefolgtes Thema", any("folgst: #atemwegsmanagement" in g for g in b["warum"]),
      b["warum"])
t = anna.get("/api/netz/tags/atemwegsmanagement").json()
check("Themenseite kennt Folgestatus", t["thema"]["folge_ich"] is True, t["thema"])

# --- Fallvorstellung -------------------------------------------------------
basis = {"art": "fallvorstellung", "titel": "Unklare Bewusstlosigkeit",
         "details": {"meldebild": "Person bewusstlos aufgefunden",
                     "frage": "Was hättet ihr als Nächstes gemacht?"}}
r = anna.post("/api/netz/beitraege", json=basis)
check("Fallvorstellung ohne xABCDE abgewiesen", r.status_code == 400)
r = anna.post("/api/netz/beitraege", json={**basis, "details": {
    **basis["details"], "a": "frei", "d": "GCS 7", "altersgruppe": "neunzig"}})
check("Unbekannte Altersgruppe abgewiesen", r.status_code == 400)
r = anna.post("/api/netz/beitraege", json={**basis, "details": {
    **basis["details"], "a": "frei", "d": "GCS 7, Alarmierung 03:12"}})
check("Uhrzeit im Befund abgewiesen", r.status_code == 400, r.status_code)
r = anna.post("/api/netz/beitraege", json={**basis, "themen": ["peer-hilfe"],
    "details": {**basis["details"], "a": "frei", "d": "GCS 7",
                "altersgruppe": "erwachsen"}})
FALL = r.json()
check("Fallvorstellung angelegt", FALL["art"] == "fallvorstellung" and
      {"fallvorstellung", "peer-hilfe"} <= {t["code"] for t in FALL["themen"]}, FALL)
chris.post(f"/api/netz/beitraege/{FALL['id']}/kommentare", json={"text": "BZ messen."})
k = dora.post(f"/api/netz/beitraege/{FALL['id']}/kommentare",
              json={"text": "Pupillen und Temperatur."}).json()["kommentare"]
DORA_K = next(x["id"] for x in k if "Pupillen" in x["text"])
check("Fremde können keine Antwort markieren", chris.put(
    f"/api/netz/beitraege/{FALL['id']}/hilfreich/{DORA_K}").status_code == 404)
k = anna.put(f"/api/netz/beitraege/{FALL['id']}/hilfreich/{DORA_K}").json()
check("Hilfreiche Antwort steht oben", k["kommentare"][0]["id"] == DORA_K and
      k["kommentare"][0]["hilfreich"])
check("Mitteilung an die antwortende Person", any(
    m["art"] == "hilfreich" for m in dora.get("/api/netz/mitteilungen").json()["mitteilungen"]))

# --- Kommentare ausschalten ----------------------------------------------
r = anna.put(f"/api/netz/beitraege/{FALL['id']}/kommentare-aus", json={"aus": True})
check("Autorin schaltet Kommentare aus", r.json()["kommentare_aus"] is True)
r = dora.post(f"/api/netz/beitraege/{FALL['id']}/kommentare", json={"text": "Noch was"})
check("Ausgeschaltet: kein neuer Kommentar", r.status_code == 403)
check("Fremde schalten nicht", dora.put(f"/api/netz/beitraege/{FALL['id']}/kommentare-aus",
                                        json={"aus": False}).status_code == 403)
anna.put(f"/api/netz/beitraege/{FALL['id']}/kommentare-aus", json={"aus": False})
r = chris.put(f"/api/netz/beitraege/{FALL['id']}/kommentare-aus", json={"aus": True})
check("Administration schließt", r.json()["kommentare_gesperrt"] is True)
r = anna.put(f"/api/netz/beitraege/{FALL['id']}/kommentare-aus", json={"aus": False})
check("Autorin kann Sperre der Administration nicht aufheben", r.status_code == 403)
r = anna.post("/api/netz/beitraege", json={"art": "beitrag", "text": "Ohne Diskussion",
                                           "kommentare_aus": True})
check("Kommentare schon beim Erstellen aus", r.json()["kommentare_aus"] is True)

# --- Merken ---------------------------------------------------------------
r = dora.put(f"/api/netz/beitraege/{ATEM}/merken")
check("Beitrag gemerkt", r.json()["gemerkt"] is True)
check("Gemerkt-Liste", [b["id"] for b in dora.get("/api/netz/gemerkt").json()["beitraege"]]
      == [ATEM])
bens = ben.post("/api/netz/beitraege", json={"art": "beitrag", "text": "Privat"}).json()
check("Unsichtbares lässt sich nicht merken",
      anna.put(f"/api/netz/beitraege/{bens['id']}/merken").status_code == 404)
ben.post(f"/api/netz/folgen/{ANNA}")
dora.put(f"/api/netz/beitraege/{bens['id']}/merken")
ben.delete(f"/api/netz/follower/{DORA}")
check("Gemerkter Beitrag verschwindet, wenn er nicht mehr sichtbar ist",
      all(b["id"] != bens["id"] for b in dora.get("/api/netz/gemerkt").json()["beitraege"]))

# --- Suche ----------------------------------------------------------------
r = dora.get("/api/netz/suche", params={"q": "laryngo"}).json()
check("Volltextsuche findet Beitrag", [b["id"] for b in r["beitraege"]] == [ATEM], r)
r = dora.get("/api/netz/suche", params={"q": "atemweg"}).json()
check("Suche findet Thema", any(t["code"] == "atemwegsmanagement" for t in r["themen"]))
r = dora.get("/api/netz/suche", params={"q": "Privat"}).json()
check("Suche findet keine fremden privaten Beiträge",
      all(b["id"] != bens["id"] for b in r["beitraege"]))

# --- Bewerbung -------------------------------------------------------------
gast = TestClient(app)
z = gast.get("/api/oeffentlich/bewerbung").json()
check("Bewerbung angeboten, mit Berufsliste", z["offen"] is True and len(z["berufe"]) >= 3, z)
antrag = {"first_name": "Eva", "last_name": "Sommer", "email": "eva@example.invalid",
          "qualification": "Notfallsanitäter*in", "kreis_ags": HK,
          "organisation": "DRK", "wache": "Soltau", "motivation": "Austausch",
          "buerge": "anna", "datenschutz": True}
r = gast.post("/api/oeffentlich/bewerbung", json={**antrag, "datenschutz": False})
check("Ohne Datenschutzhinweis abgewiesen", r.status_code == 400)
r = gast.post("/api/oeffentlich/bewerbung", json=antrag)
ANTWORT = r.json()["detail"]
check("Bewerbung angenommen", r.status_code == 200)
r2 = gast.post("/api/oeffentlich/bewerbung", json={**antrag, "email": "anna@example.invalid"})
check("Gleiche Antwort für bestehendes Konto", r2.json()["detail"] == ANTWORT)
check("… mit Hinweismail statt Bewerbung",
      "bereits ein Konto" in letzte_mail("anna@example.invalid")[1])
r3 = gast.post("/api/oeffentlich/bewerbung", json={**antrag, "email": "x@example.invalid",
                                                   "buerge": "niemand"})
check("Gleiche Antwort bei unbekanntem Bürgen", r3.json()["detail"] == ANTWORT)
check("Unbestätigt: nicht in der Administration",
      all(b["email"] != "eva@example.invalid"
          for b in chris.get("/api/admin/bewerbungen").json()["bewerbungen"]))
check("Unbestätigt: Bürgin noch nicht gefragt",
      anna.get("/api/netz/buergschaften").json()["buergschaften"] == [])
token = link_wert(letzte_mail("eva@example.invalid")[2], "token")
check("Ungültiger Token abgewiesen", gast.post("/api/oeffentlich/bewerbung/bestaetigen",
      json={"token": "x" * 40}).status_code == 400)
r = gast.post("/api/oeffentlich/bewerbung/bestaetigen", json={"token": token})
check("Adresse bestätigt", r.status_code == 200, r.text)
check("Token nur einmal", gast.post("/api/oeffentlich/bewerbung/bestaetigen",
      json={"token": token}).status_code == 400)
check("Bürgin per Mail gefragt", "Kennst du" in letzte_mail("anna@example.invalid")[1])
bg = anna.get("/api/netz/buergschaften")
check("Bürgin sieht die Bewerbung", len(bg.json()["buergschaften"]) == 1)
check("Bürgin sieht keine E-Mail-Adresse", "eva@example" not in bg.text)
AID = bg.json()["buergschaften"][0]["id"]
check("Andere können nicht bürgen", dora.post(f"/api/netz/buergschaften/{AID}",
      json={"antwort": "ja"}).status_code == 404)
anna.post(f"/api/netz/buergschaften/{AID}", json={"antwort": "ja",
                                                  "text": "Kenne sie aus Soltau."})
bw = chris.get("/api/admin/bewerbungen").json()["bewerbungen"]
eva = next(b for b in bw if b["id"] == AID)
check("Administration sieht Bürgschaft", eva["antwort"] == "bestaetigt" and
      eva["buerge"]["name"] == "Anna Berger", eva)
check("Mitglieder sehen keine Bewerbungen",
      anna.get("/api/admin/bewerbungen").status_code == 403)
check("Annahme nur mit frischem Code", chris.post(
    f"/api/admin/bewerbungen/{AID}/annehmen", json={}).status_code == 400)
check("Keine Annahme als Administrator", chris.post(
    f"/api/admin/bewerbungen/{AID}/annehmen",
    json={"totp_code": code(csec), "role": "admin"}).status_code == 422)
r = chris.post(f"/api/admin/bewerbungen/{AID}/annehmen", json={"totp_code": code(csec)})
check("Bewerbung angenommen, Einladung verschickt", r.json()["sent"] is True)
einl = link_wert(letzte_mail("eva@example.invalid")[2], "code")
inv = gast.get(f"/api/auth/invitation/{einl}").json()
check("Einladung füllt den Namen vor", inv["first_name"] == "Eva" and
      inv["email"] == "eva@example.invalid", inv)
eva_k = TestClient(app)
r = eva_k.post("/api/auth/register", json={"username": "eva", "email": "eva@example.invalid",
    "password": "einsatzprotokoll2026", "first_name": "Eva", "last_name": "Sommer",
    "invite_code": einl})
check("Registrierung über die Bewerbung", r.status_code == 200, r.text[:120])
check("Kreis aus der Bewerbung übernommen",
      eva_k.get("/api/netz/profil").json()["ort"]["kreis_ags"] == HK)
check("Bewerbung nach Registrierung gelöscht", all(
    b["id"] != AID for b in chris.get("/api/admin/bewerbungen").json()["bewerbungen"]))
r = chris.put("/api/admin/bewerbungen/einstellung", json={"offen": False})
check("Bewerbung abschaltbar",
      gast.get("/api/oeffentlich/bewerbung").json()["offen"] is False)
check("Abgeschaltet: 503", gast.post("/api/oeffentlich/bewerbung",
      json={**antrag, "email": "neu@example.invalid"}).status_code == 503)

# --- Administration: Themen und Katalog -----------------------------------
check("Themenpflege nur Administration",
      anna.post("/api/admin/themen", json={"name": "Tox", "kategorie": "Fachthema"})
      .status_code == 403)
r = chris.post("/api/admin/themen", json={"name": "Telenotarzt", "kategorie": "Einsatzbereich"})
check("Thema angelegt", any(t["code"] == "telenotarzt" for t in r.json()["themen"]))
kat_admin = chris.get("/api/admin/katalog").json()
check("Katalogpflege sieht eingereichte Wache",
      any(w["id"] == WACHE and w["mitglieder"] == 2 for w in kat_admin["wachen"]))

# --- DSGVO -----------------------------------------------------------------
daten = dora.get("/api/exports/my-data").json()["netzwerk"]
check("Auskunft enthält Gemerktes, Themen und Vereinbarung",
      daten["gemerkt"] and daten["nutzungsvereinbarung"] and "themen_gefolgt" in daten)
r = anna.post("/api/account/delete", json={"password": "einsatzprotokoll2026",
                                           "totp_code": code(SECRETS[ANNA]),
                                           "confirm": "LÖSCHEN"})
check("Konto gelöscht", r.status_code == 200, r.text[:120])
from app.db import conn, scalar  # noqa: E402

with conn() as c:
    rest = sum(scalar(c, f"SELECT COUNT(*) FROM {t} WHERE user_id = :u", u=ANNA) or 0
               for t in ("net_user_qualifications", "net_fortbildungen",
                         "net_topic_follows", "terms_acceptance", "net_saved",
                         "net_seen", "net_dismissed"))
    eingereicht = scalar(c, "SELECT COUNT(*) FROM net_wachen WHERE created_by = :u",
                         u=ANNA)
    wache_da = scalar(c, "SELECT COUNT(*) FROM net_wachen WHERE id = :w", w=WACHE)
check("Löschung entfernt die neuen Tabellen", rest == 0, rest)
check("Eingereichte Wache bleibt, ohne Personenbezug",
      eingereicht == 0 and wache_da == 1)

print("\n4.5.0 Zugang und Netzwerk: alle Prüfungen bestanden.")
