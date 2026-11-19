"""Gemeinsame Regeln des Kompetenznetzes.

Hier steht, wer wen und was sehen darf, und wo die Grenze zum privaten
Logbuch verläuft. Die Router unter routers/netz.py, routers/beitraege.py
und routers/nachrichten.py fragen ausschließlich diese Funktionen. Eine
Sichtbarkeitsregel, die in einem Router selbst nachgebaut wird, ist ein
Fehler.

SICHTBARKEIT (Modell „Folgen“)

* Wer das Netz nicht eingeschaltet hat, ist für andere nicht vorhanden.
* Blockieren wirkt in beide Richtungen: keine Sicht, kein Folgen, keine
  Nachricht. Für die blockierte Person sieht es aus wie ein Konto, das
  es nicht gibt (404).
* Öffentliches Konto: Beiträge, Chronik, Kompetenzen und Info sehen alle
  aktiven Mitglieder dieser Installation. Nichts davon ist ohne
  Anmeldung erreichbar.
* Privates Konto: das sehen nur bestätigte Follower. Kopf des Profils
  (Name, Bild, Kurzbeschreibung, Zahlen) sehen alle, damit eine
  Folgeanfrage ein Gesicht hat.

DIE GRENZE ZUM PRIVATEN LOGBUCH

Einsatznummer, Einsatzdatum, Einsatzuhrzeit, Schicht, Fahrzeug, die
Zeitstempel einzelner Maßnahmen und Gaben, Freitext-Notizen, Dosierung und
Patientenschaden verlassen das Logbuch nie. Durchgesetzt durch Bauart:

1. net_posts hat keine Spalte für eines dieser Felder und keine
   encounter_id.
2. schnappschuss() liest ausschließlich die Felder der Allowlist.
3. pruefe_text() weist Texte ab, die eigene Einsatznummern,
   Fahrzeugkennungen, Einsatzdaten oder Uhrzeiten enthalten.

Benutzername und E-Mail-Adresse anderer werden nie ausgegeben.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import HTTPException

from .db import new_id, now_iso, q, row, rows, scalar

# Allowlist der Felder, die ein Kompetenz- oder Fallbeitrag aus dem
# Logbuch übernimmt. Wer hier etwas ergänzt, ändert die Datenschutzgrenze.
MASSNAHME_FELDER = ("measure_name", "measure_category", "outcome", "performer_role")
MEDIKAMENT_FELDER = ("medication_name", "route", "outcome")


# --------------------------------------------------------------------------
# Profile
# --------------------------------------------------------------------------

def profil_sicherstellen(c, uid: str) -> None:
    if not row(c, "SELECT user_id FROM user_profile WHERE user_id = :u", u=uid):
        q(c, "INSERT INTO user_profile (user_id, created_at) VALUES (:u, :t)",
          u=uid, t=now_iso())


def profil(c, uid: str) -> dict | None:
    return row(c, "SELECT p.*, u.id AS uid, u.role AS account_role, u.disabled_at "
                  "FROM users u LEFT JOIN user_profile p ON p.user_id = u.id "
                  "WHERE u.id = :u", u=uid)


def anzeigename(p: dict | None) -> str:
    if not p:
        return "Mitglied"
    name = " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x)
    return name.strip() or "Mitglied"


def aktiv(p: dict | None) -> bool:
    return bool(p and p.get("net_active") and not p.get("disabled_at"))


def privat(p: dict | None) -> bool:
    return bool(p and p.get("net_private"))


def ist_admin(user: dict) -> bool:
    return (user.get("role") or "user") == "admin"


def ist_gast(user: dict) -> bool:
    return (user.get("role") or "user") == "guest"


# --------------------------------------------------------------------------
# Beziehungen
# --------------------------------------------------------------------------

def follow(c, von: str, an: str) -> dict | None:
    return row(c, "SELECT * FROM net_follows WHERE follower_id = :a "
                  "AND followee_id = :b", a=von, b=an)


def folgt(c, von: str, an: str) -> bool:
    f = follow(c, von, an)
    return bool(f and f["status"] == "aktiv")


def blockiert(c, a: str, b: str) -> bool:
    """True, wenn eine der beiden Seiten die andere blockiert hat."""
    return bool(row(c, "SELECT id FROM net_blocks WHERE (blocker_id = :a AND "
                       "blocked_id = :b) OR (blocker_id = :b AND blocked_id = :a)",
                    a=a, b=b))


def blockierte_ids(c, ich: str) -> set[str]:
    ids = set()
    for b in rows(c, "SELECT blocker_id, blocked_id FROM net_blocks WHERE "
                     "blocker_id = :i OR blocked_id = :i", i=ich):
        ids.add(b["blocked_id"] if b["blocker_id"] == ich else b["blocker_id"])
    return ids


def gefolgt_ids(c, ich: str) -> set[str]:
    return {r_["followee_id"] for r_ in rows(
        c, "SELECT followee_id FROM net_follows WHERE follower_id = :i "
           "AND status = 'aktiv'", i=ich)}


def follower_ids(c, ich: str) -> set[str]:
    return {r_["follower_id"] for r_ in rows(
        c, "SELECT follower_id FROM net_follows WHERE followee_id = :i "
           "AND status = 'aktiv'", i=ich)}


def beziehung(c, ich: str, andere: str) -> dict:
    """Beziehung aus Sicht von ich. Zwei Richtungen, wie in Bildnetzwerken."""
    if ich == andere:
        return {"selbst": True, "ich_folge": "selbst", "folgt_mir": False}
    meins = follow(c, ich, andere)
    seins = follow(c, andere, ich)
    return {
        "selbst": False,
        # nein | angefragt | aktiv. Eine ignorierte Anfrage sieht für die
        # anfragende Person aus wie eine offene: Ignorieren sendet kein
        # Signal.
        "ich_folge": ("angefragt" if meins and meins["status"] == "ignoriert"
                      else meins["status"] if meins else "nein"),
        "folgt_mir": bool(seins and seins["status"] == "aktiv"),
        "fragt_an": bool(seins and seins["status"] == "angefragt"),
    }


def kontakt(c, a: str, b: str) -> bool:
    """Gegenseitiges Folgen. Voraussetzung für Kompetenzbestätigungen."""
    return folgt(c, a, b) and folgt(c, b, a)


def sichtbar(c, ich: str, andere: str) -> bool:
    """Darf ich die Person überhaupt finden und ihren Profilkopf sehen?"""
    if ich == andere:
        return True
    p = profil(c, andere)
    return aktiv(p) and aktiv(profil(c, ich)) and not blockiert(c, ich, andere)


def voll_sichtbar(c, ich: str, andere: str) -> bool:
    """Beiträge, Chronik, Kompetenzen, Info."""
    if ich == andere:
        return True
    if not sichtbar(c, ich, andere):
        return False
    return not privat(profil(c, andere)) or folgt(c, ich, andere)


ABZEICHEN_KATEGORIEN = ("Reanimation", "Trauma", "Weitere Kurse",
                        "Funktion und Zusatzqualifikation")


def abzeichen(c, uid: str) -> list[str]:
    """Kurzbezeichnungen gültiger Kurse und Funktionen (ERC ALS, PHTLS,
    Praxisanleitung). Abgelaufene erscheinen nicht."""
    monat = datetime.now(timezone.utc).strftime("%Y-%m")
    return [r_["kurz"] or r_["name"] for r_ in rows(
        c, "SELECT k.kurz, k.name FROM net_user_qualifications u JOIN "
           "net_qualifications k ON k.id = u.qual_id WHERE u.user_id = :u AND "
           "k.status = 'frei' AND k.kategorie IN (:k1, :k2, :k3, :k4) AND "
           "(u.gueltig_bis IS NULL OR u.gueltig_bis >= :m) "
           "ORDER BY k.sort_order, k.name LIMIT 5",
        u=uid, m=monat, k1=ABZEICHEN_KATEGORIEN[0], k2=ABZEICHEN_KATEGORIEN[1],
        k3=ABZEICHEN_KATEGORIEN[2], k4=ABZEICHEN_KATEGORIEN[3])]


def person_kurz(c, ich: str, p: dict) -> dict:
    """Was jedes aktive Mitglied von jedem anderen sehen darf.

    Abzeichen gehören zur Qualifikation und damit zum vollen Profil: bei
    privaten Konten sehen sie nur bestätigte Follower.
    """
    b = beziehung(c, ich, p["uid"])
    offen = ich == p["uid"] or not privat(p) or b["ich_folge"] == "aktiv"
    return {
        "id": p["uid"],
        "name": anzeigename(p),
        "headline": p.get("headline") or "",
        "avatar_id": p.get("avatar_id"),
        "privat": privat(p),
        "ich_folge": b["ich_folge"],
        "folgt_mir": b["folgt_mir"],
        "abzeichen": abzeichen(c, p["uid"]) if offen else [],
    }


def aktiv_erforderlich(c, user: dict) -> dict:
    p = profil(c, user["id"])
    if not aktiv(p):
        raise HTTPException(
            409, "Schalte zuerst dein Netzwerkprofil unter Profil → Netzwerk ein.")
    return p


# --------------------------------------------------------------------------
# Beiträge: Sichtbarkeit
# --------------------------------------------------------------------------

def gemeldet_an(c, admin_id: str, post_id: str) -> bool:
    return bool(row(c, "SELECT id FROM net_notifications WHERE user_id = :u "
                       "AND post_id = :p AND kind = 'meldung'",
                    u=admin_id, p=post_id))


def darf_beitrag_sehen(c, user: dict, post: dict) -> bool:
    """Die eine Sichtbarkeitsregel für Beiträge.

    Selbst: immer, auch geplante und entfernte. Sonst: veröffentlicht,
    nicht entfernt, Profil voll sichtbar. Administrator*innen sehen
    zusätzlich Beiträge, die ihnen gemeldet wurden.
    """
    if post["author_id"] == user["id"]:
        return True
    if post["removed_at"]:
        return False
    if ist_admin(user) and gemeldet_an(c, user["id"], post["id"]):
        return True
    if post["published_at"] > now_iso():
        return False
    return voll_sichtbar(c, user["id"], post["author_id"])


def beitrag_oder_404(c, user: dict, post_id: str) -> dict:
    post = row(c, "SELECT * FROM net_posts WHERE id = :i", i=post_id)
    if not post or not darf_beitrag_sehen(c, user, post):
        raise HTTPException(404, "Beitrag nicht gefunden.")
    return post


# --------------------------------------------------------------------------
# Datenschutzgrenze
# --------------------------------------------------------------------------

# Doppelpunktform nur mit zweistelliger Stunde: "03:12" ist eine Uhrzeit,
# "1:10" oder "1:1000" ist eine Verdünnung. Einstellige Stunden fängt die
# Form mit "Uhr" ab ("3 Uhr", "15.30 Uhr"). Reanimationsverhältnisse wie
# 30:2 oder 15:2 fallen durch beide Muster nicht.
UHRZEIT = re.compile(
    r"\b(?:[01]\d|2[0-3]):[0-5]\d\b"
    r"|\b(?:[01]?\d|2[0-3])(?:[.:][0-5]\d)?\s*Uhr\b",
    re.IGNORECASE)


def _datumsformen(iso: str) -> set[str]:
    try:
        d = datetime.fromisoformat(iso)
    except ValueError:
        return set()
    return {
        d.strftime("%d.%m.%Y"), d.strftime("%d.%m.%y"), d.strftime("%d.%m."),
        f"{d.day}.{d.month}.{d.year}", f"{d.day}.{d.month}.",
        d.strftime("%Y-%m-%d"),
    }


def pruefe_text(c, uid: str, text: str, uhrzeit: bool = True,
                nur_einsatznummer: bool = False) -> None:
    """Weist Texte ab, die private Einsatzangaben enthalten.

    Geprüft wird gegen das **eigene** Logbuch: die eigenen Einsatznummern,
    Fahrzeugkennungen und Einsatzdaten. Uhrzeiten werden generell
    abgewiesen: sie machen einen Einsatz am leichtesten wiederfindbar.

    In Direktnachrichten (nur_einsatznummer) wird allein die Einsatznummer
    geprüft. Datum und Uhrzeit dort zu sperren, verhinderte jede
    Terminabsprache unter Kolleg*innen.
    """
    if not text:
        return
    klein = text.lower()
    if uhrzeit and not nur_einsatznummer and UHRZEIT.search(text):
        raise HTTPException(
            400, "Der Text enthält eine Uhrzeit. Einsatzzeiten bleiben privat — "
                 "bitte entfernen.")
    for e in rows(c, "SELECT mission_number, vehicle_id, enc_date "
                     "FROM encounters WHERE user_id = :u", u=uid):
        pruefen = [(e["mission_number"], "eine Einsatznummer")]
        if not nur_einsatznummer:
            pruefen.append((e["vehicle_id"], "eine Fahrzeugkennung"))
        for wert, was in pruefen:
            if wert and len(wert.strip()) >= 3 and wert.strip().lower() in klein:
                raise HTTPException(
                    400, f"Der Text enthält {was} aus deinem Logbuch "
                         f"(„{wert.strip()}“). Diese Angaben bleiben privat.")
        if nur_einsatznummer:
            continue
        for form in _datumsformen(e["enc_date"] or ""):
            if form in text:
                raise HTTPException(
                    400, f"Der Text enthält das Datum eines deiner Einsätze "
                         f"(„{form}“). Einsatzdaten bleiben privat.")


def pruefe_link(url: str | None) -> str | None:
    """Nur http und https. Kein javascript:, data:, file:."""
    if not url:
        return None
    url = url.strip()
    if len(url) > 500:
        raise HTTPException(400, "Der Link ist zu lang.")
    teile = urlparse(url)
    if teile.scheme not in ("http", "https") or not teile.netloc:
        raise HTTPException(400, "Der Link muss mit https:// oder http:// beginnen.")
    return url


def schnappschuss(c, uid: str, attempt_ids: list[str], medication_ids: list[str],
                  mit_zek: bool, mit_naca: bool) -> dict:
    """Baut den teilbaren Teil eines Einsatzes. Nur Allowlist-Felder.

    Alle Einträge müssen dem Aufrufer gehören, nicht gelöscht sein und aus
    demselben Einsatz stammen. Fremde oder unbekannte Kennungen antworten
    mit 404, ohne zu verraten, ob es sie gibt.
    """
    if not attempt_ids and not medication_ids:
        raise HTTPException(400, "Wähle mindestens eine Maßnahme oder Gabe.")
    if len(attempt_ids) + len(medication_ids) > 20:
        raise HTTPException(400, "Höchstens 20 Einträge je Beitrag.")

    einsaetze: set[str] = set()
    massnahmen, medikamente, zek = [], [], []

    for aid in attempt_ids:
        a = row(c, "SELECT a.id, a.encounter_id, a.measure_id, "
                   + ", ".join(f"a.{f}" for f in MASSNAHME_FELDER) +
                   " FROM measure_attempts a JOIN encounters e "
                   "ON e.id = a.encounter_id WHERE a.id = :i AND e.user_id = :u "
                   "AND a.deleted_at IS NULL AND e.deleted_at IS NULL",
                i=aid, u=uid)
        if not a:
            raise HTTPException(404, "Eintrag nicht gefunden.")
        einsaetze.add(a["encounter_id"])
        massnahmen.append({
            "measure_id": a["measure_id"],
            "name": a["measure_name"], "kategorie": a["measure_category"],
            "ergebnis": a["outcome"], "rolle": a["performer_role"] or "",
        })
        if mit_zek:
            zek += [z["label"] for z in rows(
                c, "SELECT label FROM attempt_complications WHERE attempt_id = :a",
                a=aid)]

    for mid in medication_ids:
        m = row(c, "SELECT m.id, m.encounter_id, m.medication_id, "
                   + ", ".join(f"m.{f}" for f in MEDIKAMENT_FELDER) +
                   " FROM medication_administrations m JOIN encounters e "
                   "ON e.id = m.encounter_id WHERE m.id = :i AND e.user_id = :u "
                   "AND m.deleted_at IS NULL AND e.deleted_at IS NULL",
                i=mid, u=uid)
        if not m:
            raise HTTPException(404, "Eintrag nicht gefunden.")
        einsaetze.add(m["encounter_id"])
        gruppe = None
        if m["medication_id"]:
            stamm = row(c, "SELECT divi_group FROM medications WHERE id = :i",
                        i=m["medication_id"])
            gruppe = stamm["divi_group"] if stamm else None
        medikamente.append({
            "name": m["medication_name"], "divi_gruppe": gruppe or "",
            "weg": m["route"] or "", "ergebnis": m["outcome"] or "",
        })
        if mit_zek:
            zek += [z["label"] for z in rows(
                c, "SELECT label FROM medication_complications "
                   "WHERE administration_id = :a", a=mid)]

    if len(einsaetze) != 1:
        raise HTTPException(400, "Ein Beitrag teilt Einträge aus genau einem Einsatz.")
    einsatz = einsaetze.pop()
    if mit_zek:
        # Nur die Bezeichnung. Bezug und Patientenschaden bleiben privat.
        zek += [z["label"] for z in rows(
            c, "SELECT label FROM encounter_complications WHERE encounter_id = :e",
            e=einsatz)]

    schnapp = {"massnahmen": massnahmen, "medikamente": medikamente}
    if zek:
        schnapp["zek"] = sorted(set(zek))
    if mit_naca:
        naca = scalar(c, "SELECT naca FROM encounters WHERE id = :e", e=einsatz)
        if naca:
            schnapp["naca"] = naca
    return schnapp


# --------------------------------------------------------------------------
# Mitteilungen
# --------------------------------------------------------------------------

def melde(c, an: str, art: str, von: str | None, post_id: str | None = None) -> None:
    if an == von:
        return
    if von and blockiert(c, an, von):
        return
    # Ein zweites "Gefällt mir" nach Zurücknehmen erzeugt keine zweite
    # Mitteilung.
    if art in ("like", "folgt") and row(
            c, "SELECT id FROM net_notifications WHERE user_id = :u AND kind = :k "
               "AND actor_id = :a AND " + ("post_id = :p" if post_id else "post_id IS NULL"),
            u=an, k=art, a=von, **({"p": post_id} if post_id else {})):
        return
    q(c, "INSERT INTO net_notifications (id, user_id, kind, actor_id, post_id, "
         "created_at) VALUES (:i, :u, :k, :a, :p, :t)",
      i=new_id(), u=an, k=art, a=von, p=post_id, t=now_iso())


def jetzt() -> datetime:
    return datetime.now(timezone.utc)


def json_oder_none(text: str | None):
    return json.loads(text) if text else None
