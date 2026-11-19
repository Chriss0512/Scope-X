"""Löst die Rechenaufgabe für die Testreihen.

Seit der Härtung tragen Anmeldung, Registrierung und Reset-Anforderung
einen Arbeitsnachweis. Die Testreihen sollen deshalb nicht an 25 Stellen
umgeschrieben werden: dieser Helfer hängt den Nachweis dort an, wo er
fehlt, und lässt die Tests lesbar wie zuvor.

Wichtig: der Nachweis wird hier **echt gerechnet**, nicht umgangen. Eine
Testreihe, die den Schutz abschaltet, den sie prüfen soll, belegt nichts.
"""
from __future__ import annotations

import hashlib
import os

from starlette.testclient import TestClient

# Die Testreihen stellen hunderte Anfragen aus derselben Adresse. Ohne
# diesen Wert liefe die Drosselung sofort voll und alle Tests scheiterten
# an etwas, das sie gar nicht prüfen wollen. Das Fenster selbst wird in
# einem eigenen Test mit eigenem Zustand geprüft.
os.environ.setdefault("SCOPEX_ANFRAGEN_JE_FENSTER", "100000")

GESCHUETZT = (
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/password-reset/request",
    "/api/oeffentlich/bewerbung",
)

_original_post = TestClient.post


def loese(aufgabe: dict) -> dict:
    """Sucht die Zahl, die den Hash mit genug Nullbits beginnen lässt."""
    stufe = int(aufgabe["stufe"])
    n = 0
    while True:
        digest = hashlib.sha256(f"{aufgabe['aufgabe']}:{n}".encode()).digest()
        bits = 0
        for byte in digest:
            if byte == 0:
                bits += 8
                continue
            bits += 8 - byte.bit_length()
            break
        if bits >= stufe:
            return {**aufgabe, "loesung": str(n)}
        n += 1


def _kennung(nutzdaten: dict) -> str:
    for feld in ("username", "identifier", "email"):
        if nutzdaten.get(feld):
            return str(nutzdaten[feld])
    return ""


def _post(self, url, *args, **kwargs):
    nutzdaten = kwargs.get("json")
    if (isinstance(nutzdaten, dict) and not nutzdaten.get("pow")
            and any(url.endswith(pfad) for pfad in GESCHUETZT)):
        antwort = self.get("/api/auth/challenge",
                           params={"kennung": _kennung(nutzdaten)})
        if antwort.status_code == 200:
            kwargs["json"] = {**nutzdaten, "pow": loese(antwort.json())}
    # Neue Konten stimmen der Nutzungsvereinbarung zu, wenn der Test nichts
    # anderes sagt. Die Ablehnung prüft ein eigener Test mit False.
    if (url.endswith("/api/auth/register") and isinstance(kwargs.get("json"), dict)
            and "nutzung_akzeptiert" not in kwargs["json"]):
        kwargs["json"] = {**kwargs["json"], "nutzung_akzeptiert": True}
    return _original_post(self, url, *args, **kwargs)


def einhaengen() -> None:
    TestClient.post = _post


einhaengen()
