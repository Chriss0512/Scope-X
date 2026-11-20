"""Übernahme aus NIDAshare (4.8.0).

Ein nachgebautes NIDAshare läuft lokal: eine Seite mit einem einzigen
Eingabefeld, nach dem Absenden das PDF. Das PDF ist mit fpdf2 erzeugt und
enthält neben Maßnahmen und Medikamenten Patientendaten mit Markierwerten.
Geprüft wird vor allem die Grenze: Weder Markierwerte noch der Code
tauchen in einer Antwort, in der Datenbank (Bytefolge samt WAL) oder im
Log auf.
"""
import logging
import os
import shutil
import socket
import sys
import threading
import time as _t

shutil.rmtree("/tmp/scopex_q_nida", ignore_errors=True)
os.makedirs("/tmp/scopex_q_nida")
os.environ["SCOPEX_DATABASE_URL"] = "sqlite:////tmp/scopex_q_nida/scopex.db"


def freier_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


PORT = freier_port()
os.environ["SCOPEX_NIDASHARE"] = "1"
os.environ["SCOPEX_NIDASHARE_URL"] = f"http://127.0.0.1:{PORT}/"
sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parents[2].as_posix())

import uvicorn  # noqa: E402
from fastapi import FastAPI, Form  # noqa: E402
from fastapi.responses import HTMLResponse, RedirectResponse, Response  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from fpdf import FPDF  # noqa: E402

from app import nidashare  # noqa: E402
from app.main import app  # noqa: E402
from app.security import _totp_at  # noqa: E402
from quality import nachweis  # noqa: E402,F401


def check(n, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + n + (" :: " + str(extra) if not cond else ""))
    if not cond:
        sys.exit(1)


MARKEN = ["ERIKAPATIENTQ7", "MUSTERSTRASSE91X", "VERSICHERTZ44", "DIAGNOSEGEHEIM8"]
CODE_GUT, CODE_LINK, CODE_UMLEITUNG = "AB12CD34", "LINK5678", "UMLEIT99"


def protokoll_pdf() -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    zeilen = [
        "Notfallprotokoll Rettungsdienst",
        f"Patient: {MARKEN[0]}  Geburtsdatum: 01.02.1950  Alter: 76",
        f"Adresse: {MARKEN[1]} 3, 29690 Schwarmstedt",
        f"Versichertennummer: {MARKEN[2]}",
        "Einsatznummer: 2026-123456   Datum: 19.11.2026",
        "Alarm 08:03   Ankunft 08:11   19.11.2026",
        f"Verdachtsdiagnose: {MARKEN[3]}",
        "Dauermedikation: Metoprolol 47,5 mg, Acetylsalicylsaeure 100 mg",
        "Massnahmen:",
        "08:12 i.v.-Zugang Handruecken links 18 G",
        "08:15 Intubation erfolglos",
        "08:20 Larynxtubus Gr. 4",
        "08:13 12-Kanal-EKG",
        "08:14 BZ 99 mg/dl",
        "Medikamente:",
        "08:14 Adrenalin 1 mg i.v.",
        "08:18 Midazolam 5 mg i.n.",
        "08:14 Adrenalin 1 mg i.v.",
        "NACA: 4    19.11.2026 08:45",
    ]
    for z in zeilen:
        pdf.cell(0, 6, z, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


PDF = protokoll_pdf()
ABRUFE = []
fake = FastAPI()


@fake.get("/", response_class=HTMLResponse)
def startseite():
    return """<html><body><h1>NIDAshare</h1>
      <form method="post" action="/abruf">
        <input type="hidden" name="csrf" value="t0k3n">
        <input type="text" name="abrufcode">
        <button type="submit">Abrufen</button>
      </form></body></html>"""


@fake.post("/abruf")
def abruf(abrufcode: str = Form(...), csrf: str = Form(...)):
    ABRUFE.append(abrufcode)
    if csrf != "t0k3n":
        return HTMLResponse("Sitzung abgelaufen", status_code=400)
    if abrufcode == CODE_GUT:
        return Response(PDF, media_type="application/pdf")
    if abrufcode == CODE_LINK:
        return HTMLResponse('<a href="/datei/protokoll.pdf">Protokoll herunterladen</a>')
    if abrufcode == CODE_UMLEITUNG:
        return RedirectResponse("http://example.invalid/fremd.pdf", status_code=302)
    return HTMLResponse("<p>Der Code ist ungültig oder abgelaufen.</p>")


@fake.get("/datei/protokoll.pdf")
def datei():
    return Response(PDF, media_type="application/pdf")


server = uvicorn.Server(uvicorn.Config(fake, host="127.0.0.1", port=PORT, log_level="error"))
threading.Thread(target=server.run, daemon=True).start()
for _ in range(50):
    if server.started:
        break
    _t.sleep(0.1)

LOG = []


class Sammler(logging.Handler):
    def emit(self, record):
        LOG.append(self.format(record))


logging.getLogger().addHandler(Sammler())
logging.getLogger().setLevel(logging.DEBUG)

# --- Auslesen ohne Server --------------------------------------------------
check("Code aus QR-Adresse", nidashare.code_normalisieren(
    "https://nidashare.de/abruf?code=AB12CD34") == "AB12CD34")
check("Leerzeichen im Code werden entfernt", nidashare.code_normalisieren(" AB12 CD34 ") == "AB12CD34")
for falsch in ("x", "AB12<script>", "../../etc", "A" * 60):
    try:
        nidashare.code_normalisieren(falsch)
        check(f"Ungültiger Code abgelehnt: {falsch[:12]}", False)
    except nidashare.AbrufFehler:
        pass
check("Ungültige Codes abgelehnt", True)

# --- Anmeldung ---------------------------------------------------------------
c = TestClient(app)
c.__enter__()
r = c.post("/api/auth/register", json={
    "username": "nida", "email": "nida@example.invalid", "password": "einsatzprotokoll2026",
    "first_name": "Nora", "last_name": "Imhof", "qualification": "Notfallsanitäter*in"})
sec = r.json()["totp"]["secret"]
c.post("/api/auth/totp/confirm", json={"code": _totp_at(sec, int(_t.time()) // 30)})
UID = c.get("/api/auth/state").json()["user"]["id"]

check("Eingeschaltet in den Konstanten", c.get("/api/catalog/constants").json()["nidashare"])
check("Kamera nur für die eigene Seite",
      "camera=(self)" in c.get("/api/health").headers["permissions-policy"])

r = c.post("/api/import/nidashare", json={"code": "x"})
check("Formatfehler 400", r.status_code == 400, r.status_code)

r = c.post("/api/import/nidashare", json={"code": CODE_GUT})
check("Abruf liefert Entwurf", r.status_code == 200, r.text[:300])
e = r.json()
text = r.text
check("Keine Patientendaten im Entwurf", not any(m in text for m in MARKEN), text[:400])
check("Kein Geburtsdatum im Entwurf", "1950" not in text and "01.02." not in text)
check("Code steht nicht im Entwurf", CODE_GUT not in text)
check("NIDAshare hat den Code bekommen", ABRUFE[-1] == CODE_GUT)
ein = e["einsatz"]
check("Einsatzdatum statt Geburtsdatum", ein["datum"] == "2026-11-19", ein)
check("Alarmzeit", ein["uhrzeit"] == "08:03", ein)
check("NACA als römische Zahl", ein["naca"] == "IV", ein)
check("Einsatznummer", ein["einsatznummer"] == "2026-123456", ein)

cat = {m["code"] if "code" in m else m["name"]: m for m in
       c.get("/api/catalog/measures").json()["measures"]}
namen = {m["name"]: m for m in e["massnahmen"]}
check("Maßnahmen erkannt", {"Intravenöser Zugang", "Endotracheale Intubation", "Larynxtubus",
                            "12-Kanal-EKG", "Blutzuckermessung"} <= set(namen), sorted(namen))
check("Fehlversuch erkannt", namen["Endotracheale Intubation"]["fehlversuch"])
check("Uhrzeit je Maßnahme", namen["Larynxtubus"]["zeit"] == "08:20", namen["Larynxtubus"])
check("Blutzuckerwert übernommen", namen["Blutzuckermessung"].get("parameter") ==
      {"wert": "99", "wert__einheit": "mg/dl"}, namen["Blutzuckermessung"])
check("Mit Messwert gilt der Blutzucker als sicher", namen["Blutzuckermessung"]["sicher"])
meds = {(g["name"], g["dosis"], g["einheit"], g["weg"]) for g in e["medikamente"]}
check("Adrenalin mit Dosis und Weg, doppelte Zeile einmal",
      ("Adrenalin", 1.0, "mg", "intravenös") in meds and
      sum(1 for g in e["medikamente"] if g["name"] == "Adrenalin") == 1, meds)
check("Midazolam nasal", ("Midazolam", 5.0, "mg", "intranasal") in meds, meds)
check("Dauermedikation wird nicht vorgeschlagen",
      not any(g["name"] in ("Metoprolol", "Acetylsalicylsäure") for g in e["medikamente"]), meds)

r = c.post("/api/import/nidashare", json={"code": CODE_GUT})
check("Zweiter Abruf verlangt Bestätigung", r.status_code == 409 and
      "schon einmal" in r.json()["detail"], r.text[:200])
r = c.post("/api/import/nidashare", json={"code": CODE_LINK})
check("PDF hinter einem Link", r.status_code == 200, r.text[:200])
c.post(f"/api/import/nidashare/{r.json()['id']}/verwerfen")
r = c.post("/api/import/nidashare", json={"code": CODE_UMLEITUNG})
check("Weiterleitung auf fremden Host abgelehnt", r.status_code == 502, r.status_code)
r = c.post("/api/import/nidashare", json={"code": "ZZ99ZZ99"})
check("Unbekannter Code: 404 mit Hinweis", r.status_code == 404 and "Code" in r.json()["detail"],
      r.text[:200])

# --- Übernahme ---------------------------------------------------------------
m_iv = namen["Intravenöser Zugang"]["measure_id"]
m_eti = namen["Endotracheale Intubation"]["measure_id"]
m_bz = namen["Blutzuckermessung"]["measure_id"]
adr = next(g for g in e["medikamente"] if g["name"] == "Adrenalin")
r = c.post(f"/api/import/nidashare/{e['id']}/uebernehmen", json={
    "einsatz": {"datum": "2026-11-19", "uhrzeit": "08:03", "naca": "IV",
                "einsatznummer": "2026-123456"},
    "massnahmen": [
        {"measure_id": m_iv, "outcome": "erfolgreich", "zeit": "08:12"},
        {"measure_id": m_eti, "outcome": "fehlgeschlagen", "performer_role": "assistiert",
         "zeit": "08:15"},
        {"measure_id": m_bz, "outcome": "erfolgreich", "zeit": "08:14",
         "parameters": {"wert": "5,5", "wert__einheit": "mmol/l"}},
    ],
    "medikamente": [{"medication_id": adr["medication_id"], "dose": 1, "unit": "mg",
                     "route": "intravenös", "zeit": "08:14"}]})
check("Übernommen", r.status_code == 200, r.text[:300])
eid = r.json()["encounter_id"]
enc = c.get(f"/api/encounters/{eid}").json()
check("Einsatz mit drei Maßnahmen und einer Gabe",
      len(enc["attempts"]) == 3 and len(enc["medications"]) == 1, enc)
bz = next(a for a in enc["attempts"] if a["measure_id"] == m_bz)
check("Blutzucker in mg/dl gespeichert", bz["parameters"][0]["value"] == "99", bz["parameters"])
eti = next(a for a in enc["attempts"] if a["measure_id"] == m_eti)
check("Rolle und Zeit übernommen", eti["performer_role"] == "assistiert" and
      eti["performed_at"].endswith("08:15"), eti)
check("Zweite Übernahme desselben Abrufs abgelehnt", c.post(
    f"/api/import/nidashare/{e['id']}/uebernehmen", json={
        "einsatz": {"datum": "2026-11-19", "uhrzeit": "08:03"},
        "massnahmen": [{"measure_id": m_iv}]}).status_code == 409)
r = c.post("/api/import/nidashare", json={"code": CODE_GUT, "erneut": True})
check("Übernommenes Protokoll nicht erneut abrufbar",
      r.status_code == 409 and "bereits übernommen" in r.json()["detail"], r.text[:200])

# Fehlerhafte Auswahl legt keinen halben Einsatz an.
r = c.post("/api/import/nidashare", json={"code": CODE_LINK, "erneut": True})
e2 = r.json()
vorher = len(c.get("/api/encounters").json()["encounters"])
r = c.post(f"/api/import/nidashare/{e2['id']}/uebernehmen", json={
    "einsatz": {"datum": "2026-11-19", "uhrzeit": "08:03"},
    "massnahmen": [{"measure_id": m_bz, "parameters": {"wert": "99", "wert__einheit": "mmol/l"}}]})
check("Unplausibler Wert: abgelehnt", r.status_code == 400, r.text[:200])
check("… und kein halber Einsatz", len(c.get("/api/encounters").json()["encounters"]) == vorher)
r = c.post(f"/api/import/nidashare/{e2['id']}/uebernehmen", json={
    "einsatz": {"datum": "2026-11-19", "uhrzeit": "08:03"},
    "massnahmen": [{"measure_id": "gibt-es-nicht"}]})
check("Unbekannte Maßnahme abgelehnt", r.status_code == 400)
r = c.post(f"/api/import/nidashare/{e2['id']}/uebernehmen", json={
    "einsatz": {"datum": "2026-11-19", "uhrzeit": "25:99"}, "massnahmen": [{"measure_id": m_iv}]})
check("Ungültige Uhrzeit abgelehnt", r.status_code == 400)

# Eigene Zuordnung wird gemerkt.
r = c.post(f"/api/import/nidashare/{e2['id']}/uebernehmen", json={
    "einsatz": {"datum": "2026-11-19", "uhrzeit": "08:03"},
    "massnahmen": [{"measure_id": m_iv, "begriff": "Infusion"}]})
check("Übernahme mit eigener Zuordnung", r.status_code == 200, r.text[:200])
from app.db import conn, scalar  # noqa: E402

with conn() as cx:
    check("Zuordnung gespeichert", scalar(
        cx, "SELECT measure_id FROM import_begriffe WHERE user_id = :u AND begriff = 'Infusion'",
        u=UID) == m_iv)

# --- Datenschutzgrenze in Datenbank und Log --------------------------------
roh = b""
for datei in os.listdir("/tmp/scopex_q_nida"):
    if datei.startswith("scopex.db"):
        with open(os.path.join("/tmp/scopex_q_nida", datei), "rb") as f:
            roh += f.read()
check("Keine Patientendaten in der Datenbank", not any(m.encode() in roh for m in MARKEN))
check("Code nicht im Klartext in der Datenbank",
      CODE_GUT.encode() not in roh and CODE_LINK.encode() not in roh)
check("Einsatznummer verschlüsselt", b"2026-123456" not in roh)
alles = "\n".join(LOG)
check("Weder Code noch Patientendaten im Log",
      CODE_GUT not in alles and not any(m in alles for m in MARKEN))

# --- Grenzen ---------------------------------------------------------------
for i in range(12):
    r = c.post("/api/import/nidashare", json={"code": f"RATE{i:04d}"})
check("Höchstens zehn Abrufe je Stunde", r.status_code == 429, r.status_code)

os.environ["SCOPEX_NIDASHARE"] = "0"
check("Ausgeschaltet: 404", c.post("/api/import/nidashare",
                                   json={"code": "AA11BB22"}).status_code == 404)
check("Ausgeschaltet: nicht in den Konstanten",
      c.get("/api/catalog/constants").json()["nidashare"] is False)
os.environ["SCOPEX_NIDASHARE"] = "1"

# Zweites Konto: Gast darf nicht abrufen; nach Löschung bleibt nichts.
inv = c.post("/api/admin/invitations", json={"role": "user", "valid_days": 3,
              "totp_code": _totp_at(sec, int(_t.time()) // 30)}).json()
k = TestClient(app)
r = k.post("/api/auth/register", json={"username": "zweit", "password": "einsatzprotokoll2026",
    "first_name": "Zora", "last_name": "Weiss", "invite_code": inv["code"],
    "email": "zweit@example.invalid", "qualification": "Rettungssanitäter*in"})
sec2 = r.json()["totp"]["secret"]
k.post("/api/auth/totp/confirm", json={"code": _totp_at(sec2, int(_t.time()) // 30)})
UID2 = k.get("/api/auth/state").json()["user"]["id"]
c.patch(f"/api/admin/users/{UID2}", json={"role": "guest",
        "totp_code": _totp_at(sec, int(_t.time()) // 30)})
check("Gast ruft nicht ab", k.post("/api/import/nidashare",
                                   json={"code": "GAST1234"}).status_code == 403)
check("Fremder Abruf nicht übernehmbar", k.post(
    f"/api/import/nidashare/{e2['id']}/verwerfen").status_code in (403, 404))
c.patch(f"/api/admin/users/{UID2}", json={"role": "user",
        "totp_code": _totp_at(sec, int(_t.time()) // 30)})
check("Mitglied ruft ab", k.post("/api/import/nidashare",
                                 json={"code": CODE_LINK}).status_code == 200)
r = k.post("/api/account/delete", json={"password": "einsatzprotokoll2026", "confirm": "LÖSCHEN",
                                        "totp_code": _totp_at(sec2, int(_t.time()) // 30)})
check("Konto gelöscht", r.status_code == 200, r.text[:200])
with conn() as cx:
    rest = (scalar(cx, "SELECT COUNT(*) FROM nida_imports WHERE user_id = :u", u=UID2) or 0) + \
           (scalar(cx, "SELECT COUNT(*) FROM import_begriffe WHERE user_id = :u", u=UID2) or 0)
check("Abrufe und Zuordnungen mit dem Konto gelöscht", rest == 0, rest)

server.should_exit = True
print("\nNIDAshare: alle Prüfungen bestanden.")
