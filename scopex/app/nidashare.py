"""Übernahme von Maßnahmen aus einem NIDA-Protokoll über NIDAshare.

Ablauf:

1. Der Server ruft nidashare.de auf, wie es ein Browser täte: Startseite
   laden, das Formular mit dem einen Eingabefeld finden, den Code
   absenden, das PDF annehmen. Es gibt dafür keine Schnittstelle, nur die
   Webseite; medDV hat dem Abruf zugestimmt.
2. Das PDF wird nur im Arbeitsspeicher gelesen und nie gespeichert, auch
   nicht verschlüsselt, auch nicht vorübergehend auf der Platte.
3. Heraus kommt ein Entwurf mit Feldern aus einer festen Liste: Datum,
   Uhrzeit, NACA, Einsatznummer, Maßnahmen, Medikamente. Name,
   Geburtsdatum, Adresse, Versicherung, Diagnosen und Freitexte des
   Protokolls werden nicht ausgelesen; Fundstellen werden nur als der
   gefundene Katalogbegriff zurückgegeben, nie als Zeile aus dem Protokoll.

Der Code ist ein Schlüssel zu Patientendaten. Er steht in keinem Log und
in keiner Fehlermeldung.

Das Auslesen richtet sich nach dem SCOPE-X-Katalog: gesucht wird, was der
Katalog kennt, dazu eine Liste üblicher Schreibweisen aus NIDA und die
Zuordnungen, die eine Person selbst getroffen hat. Alles Weitere klärt die
Nachbearbeitung.
"""
from __future__ import annotations

import io
import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from urllib import error as urlerror
from urllib import parse, request

log = logging.getLogger("scopex.nidashare")

BASIS = os.environ.get("SCOPEX_NIDASHARE_URL", "https://nidashare.de/")
KENNUNG = "SCOPE-X (Logbuch; scopex@ch-faust.de)"
ZEITLIMIT = 20
MAX_HTML = 1024 * 1024
MAX_PDF = 15 * 1024 * 1024
MAX_SEITEN = 40
CODE_MUSTER = re.compile(r"^[A-Za-z0-9-]{4,40}$")


class AbrufFehler(Exception):
    """Fehler beim Abruf. ``text`` geht an die Person, ``art`` ins Log.
    Beides enthält nie den Code."""

    def __init__(self, text: str, art: str, status: int = 502):
        super().__init__(art)
        self.text = text
        self.art = art
        self.status = status


def aktiv() -> bool:
    return os.environ.get("SCOPEX_NIDASHARE", "").lower() in ("1", "true", "on")


# --------------------------------------------------------------------------
# Code
# --------------------------------------------------------------------------

def code_normalisieren(roh: str) -> str:
    """Nimmt die Eingabe von Hand, aus der Texterkennung oder aus einem
    QR-Code. Ein QR-Code kann eine Adresse mit dem Code enthalten."""
    roh = (roh or "").strip()
    if roh.lower().startswith(("http://", "https://")):
        teile = parse.urlsplit(roh)
        werte = parse.parse_qs(teile.query)
        for name in ("code", "c", "id", "token"):
            if werte.get(name):
                roh = werte[name][0]
                break
        else:
            roh = teile.path.rstrip("/").rsplit("/", 1)[-1]
    code = re.sub(r"\s+", "", roh)
    if not CODE_MUSTER.match(code):
        raise AbrufFehler("Der Code hat nicht das erwartete Format. Er besteht aus "
                          "Buchstaben und Ziffern.", "format", 400)
    return code


# --------------------------------------------------------------------------
# Abruf
# --------------------------------------------------------------------------

@dataclass
class _Formular:
    action: str = ""
    method: str = "get"
    versteckt: dict[str, str] = field(default_factory=dict)
    sichtbar: list[str] = field(default_factory=list)


class _Formulare(HTMLParser):
    SICHTBAR = {"text", "search", "tel", "number", "password", ""}

    def __init__(self):
        super().__init__()
        self.formulare: list[_Formular] = []
        self._aktuell: _Formular | None = None
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "form":
            self._aktuell = _Formular(a.get("action", ""), (a.get("method") or "get").lower())
            self.formulare.append(self._aktuell)
        elif tag == "input" and self._aktuell is not None and a.get("name"):
            art = (a.get("type") or "").lower()
            if art == "hidden":
                self._aktuell.versteckt[a["name"]] = a.get("value", "")
            elif art in self.SICHTBAR:
                self._aktuell.sichtbar.append(a["name"])
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"])

    def handle_endtag(self, tag):
        if tag == "form":
            self._aktuell = None


class _NurEigenerHost(request.HTTPRedirectHandler):
    """Folgt Weiterleitungen nur innerhalb von NIDAshare."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if parse.urlsplit(newurl).hostname != parse.urlsplit(BASIS).hostname:
            raise AbrufFehler("NIDAshare hat auf eine fremde Adresse verwiesen.",
                              "fremde_weiterleitung")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _lesen(antwort, grenze: int) -> bytes:
    daten = antwort.read(grenze + 1)
    if len(daten) > grenze:
        raise AbrufFehler("Die Antwort von NIDAshare ist zu groß.", "zu_gross")
    return daten


def _ist_pdf(antwort, daten: bytes) -> bool:
    typ = (antwort.headers.get("Content-Type") or "").lower()
    return daten.startswith(b"%PDF") or "application/pdf" in typ


def _eigener_host(url: str) -> str:
    voll = parse.urljoin(BASIS, url)
    teile = parse.urlsplit(voll)
    if teile.scheme != parse.urlsplit(BASIS).scheme or \
            teile.hostname != parse.urlsplit(BASIS).hostname:
        raise AbrufFehler("Das Formular von NIDAshare zeigt auf eine fremde Adresse.",
                          "fremdes_formular")
    return voll


def abrufen(code: str) -> bytes:
    """Ruft das Protokoll ab und gibt die Bytes des PDF zurück."""
    oeffner = request.build_opener(request.HTTPCookieProcessor(CookieJar()),
                                   _NurEigenerHost())
    oeffner.addheaders = [("User-Agent", KENNUNG), ("Accept", "text/html,application/pdf")]
    try:
        with oeffner.open(BASIS, timeout=ZEITLIMIT) as a:
            html = _lesen(a, MAX_HTML).decode("utf-8", "replace")
        p = _Formulare()
        p.feed(html)
        kandidaten = [f for f in p.formulare if len(f.sichtbar) == 1]
        if len(kandidaten) != 1:
            raise AbrufFehler("Die Seite von NIDAshare hat sich verändert. Der Abruf "
                              "ist vorübergehend nicht möglich.", "formular_nicht_gefunden")
        form = kandidaten[0]
        ziel = _eigener_host(form.action or BASIS)
        felder = {**form.versteckt, form.sichtbar[0]: code}
        kodiert = parse.urlencode(felder)
        if form.method == "post":
            anfrage = request.Request(ziel, data=kodiert.encode(), method="POST")
        else:
            trenner = "&" if parse.urlsplit(ziel).query else "?"
            anfrage = request.Request(ziel + trenner + kodiert)
        with oeffner.open(anfrage, timeout=ZEITLIMIT) as a:
            daten = _lesen(a, MAX_PDF)
            if _ist_pdf(a, daten):
                return daten
            seite = daten.decode("utf-8", "replace")
        # Manche Seiten zeigen nach dem Code erst einen Link zum PDF.
        p = _Formulare()
        p.feed(seite)
        pdf_links = [x for x in p.links if ".pdf" in x.lower() or "download" in x.lower()]
        if len(pdf_links) == 1:
            with oeffner.open(_eigener_host(pdf_links[0]), timeout=ZEITLIMIT) as a:
                daten = _lesen(a, MAX_PDF)
                if _ist_pdf(a, daten):
                    return daten
        raise AbrufFehler("NIDAshare hat zu diesem Code kein Protokoll geliefert. "
                          "Prüfe den Code; er gilt nur begrenzt und nur für wenige "
                          "Abrufe.", "kein_pdf", 404)
    except AbrufFehler:
        raise
    except urlerror.HTTPError as exc:
        if exc.code in (400, 403, 404, 410):
            raise AbrufFehler("NIDAshare kennt diesen Code nicht oder nicht mehr.",
                              f"http_{exc.code}", 404) from None
        raise AbrufFehler("NIDAshare ist gerade nicht erreichbar.",
                          f"http_{exc.code}") from None
    except (urlerror.URLError, TimeoutError, OSError):
        raise AbrufFehler("NIDAshare ist gerade nicht erreichbar.", "netz") from None


# --------------------------------------------------------------------------
# Auslesen
# --------------------------------------------------------------------------

# Übliche Schreibweisen in NIDA-Protokollen, zugeordnet zum Code des
# SCOPE-X-Katalogs. Bewusst eng: lieber eine Maßnahme übersehen, die in der
# Nachbearbeitung ergänzt wird, als eine falsche vorschlagen.
SYNONYME = {
    "x_tourniquet": ["Tourniquet", "Abbindung"],
    "x_druckverband": ["Druckverband"],
    "x_haemostat": ["Hämostyptikum", "hämostatische Gaze", "Hämostatikum"],
    "x_beckenschlinge": ["Beckenschlinge", "Beckengurt", "SAM Pelvic"],
    "a_guedel": ["Guedel"],
    "a_wendl": ["Wendl"],
    "a_larynxtubus": ["Larynxtubus", "LTS-D", "LT-D"],
    "a_larynxmaske": ["Larynxmaske", "LMA"],
    "a_igel": ["i-gel", "iGel", "I-Gel"],
    "a_intubation": ["Intubation", "endotracheale Intubation", "ETI", "Endotrachealtubus"],
    "a_absaugen": ["Absaugen", "Absaugung"],
    "a_koniotomie": ["Koniotomie"],
    "b_beutel_maske": ["Beutel-Masken-Beatmung", "Maskenbeatmung", "Beutel-Maske"],
    "b_sauerstoff": ["Sauerstoffgabe", "O2-Gabe", "Sauerstoff"],
    "b_cpap": ["CPAP", "NIV", "nichtinvasive Beatmung"],
    "b_invasiv": ["maschinelle Beatmung", "Respirator", "invasive Beatmung"],
    "b_entlastung": ["Entlastungspunktion", "Thoraxentlastungspunktion", "Nadeldekompression"],
    "b_fingerthorakostomie": ["Fingerthorakostomie", "Thorakostomie"],
    "b_thoraxdrainage": ["Thoraxdrainage"],
    "c_iv": ["i.v.-Zugang", "venöser Zugang", "periphervenöser Zugang", "PVK",
             "Venenverweilkanüle", "intravenöser Zugang"],
    "c_io": ["i.o.-Zugang", "intraossärer Zugang", "EZ-IO", "intraossär"],
    "c_defibrillation": ["Defibrillation"],
    "c_kardioversion": ["Kardioversion"],
    "c_pacing": ["Schrittmacher", "Pacing", "externer Schrittmacher"],
    "c_kristalloid": ["Vollelektrolyt", "Ringer", "Infusion"],
    "c_kolloid": ["Gelatine", "HAES", "kolloidale"],
    "d_bz": ["Blutzucker", "BZ-Messung", "BZ"],
    "e_temperatur": ["Wärmeerhalt", "Rettungsdecke", "Kühlung"],
    "t_reposition_fraktur": ["Reposition"],
    "t_immobilisation": ["Vakuummatratze", "Schaufeltrage", "HWS-Immobilisation",
                         "Zervikalstütze", "Stifneck", "Vakuumschiene", "Spineboard"],
    "t_traktionsschiene": ["Traktionsschiene", "Extensionsschiene"],
    "g_ekg12": ["12-Kanal-EKG", "12-Kanal EKG", "12 Kanal"],
    "g_kapnographie": ["Kapnographie", "Kapnometrie", "etCO2"],
    "g_pulsoxymetrie": ["Pulsoxymetrie", "SpO2"],
    "g_pocus": ["Sonographie", "Ultraschall", "POCUS", "eFAST"],
}

# Begriffe, die in Protokollen als Messwert oder Überschrift vorkommen und
# allein keine durchgeführte Maßnahme belegen. Sie werden nur als
# unsicher vorgeschlagen.
UNSICHER = {"Sauerstoff", "SpO2", "BZ", "Infusion", "Ringer", "Reposition",
            "Ultraschall", "etCO2", "intraossär", "kolloidale", "Kühlung"}

ROUTEN = [
    (r"\bi\.?\s?v\.?\b|intraven", "intravenös"),
    (r"\bi\.?\s?o\.?\b|intraoss", "intraossär"),
    (r"\bi\.?\s?m\.?\b|intramusk", "intramuskulär"),
    (r"\bs\.?\s?c\.?\b|subkutan", "subkutan"),
    (r"\bi\.?\s?n\.?\b|nasal|MAD\b", "intranasal"),
    (r"\bp\.?\s?o\.?\b|\boral", "oral"),
    (r"\bs\.?\s?l\.?\b|sublingual", "sublingual"),
    (r"bukkal", "bukkal"),
    (r"vernebel", "vernebelt"),
    (r"inhal", "inhalativ"),
    (r"rektal", "rektal"),
    (r"endotrach", "endotracheal"),
]
EINHEITEN = [(r"µg|mcg|ug|μg", "µg"), (r"mg", "mg"), (r"ml", "ml"),
             (r"I\.?\s?E\.?|IE\b", "I.E."), (r"g", "g")]
DOSIS = re.compile(r"(\d+(?:[.,]\d+)?)\s*(µg|μg|mcg|ug|mg|ml|I\.?\s?E\.?|IE|g)\b", re.I)
FEHLSCHLAG = re.compile(r"erfolglos|nicht erfolgreich|frustran|fehlgeschlagen|"
                        r"misslungen|Fehlversuch", re.I)
DATUM = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
ZEIT = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
NACA = re.compile(r"NACA[^\n\d]{0,12}?\b(VII|VI|IV|V|III|II|I|0|[1-7])\b")
EINSATZNR = re.compile(r"(?:Einsatz-?\s?(?:nummer|nr\.?)|E-?Nr\.?)\s*[:#]?\s*"
                       r"([A-Za-z0-9][A-Za-z0-9/-]{2,29})", re.I)
GEBURT = re.compile(r"geb|geburt|alter", re.I)
# Zeilen mit Medikamenten der Person, nicht mit Gaben im Einsatz.
FREMDMEDIKATION = re.compile(r"dauermedikation|hausmedikation|vormedikation|"
                             r"eigenmedikation|allergi|unvertr[äa]glich|"
                             r"medikamentenanamnese|einnahme", re.I)
BZ_WERT = re.compile(r"(\d+(?:[.,]\d+)?)\s*(mg/dl|mmol/l)", re.I)
ARABISCH_ROEMISCH = {"1": "I", "2": "II", "3": "III", "4": "IV", "5": "V",
                     "6": "VI", "7": "VII"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).replace("­", "")
    return re.sub(r"[ \t]+", " ", s)


def text_aus_pdf(daten: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        pdf = PdfReader(io.BytesIO(daten))
        if pdf.is_encrypted:
            raise AbrufFehler("Das Protokoll ist verschlüsselt und lässt sich nicht "
                              "auslesen.", "verschluesselt", 422)
        seiten = pdf.pages[:MAX_SEITEN]
        text = "\n".join((s.extract_text() or "") for s in seiten)
    except AbrufFehler:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise AbrufFehler("Das Protokoll ließ sich nicht lesen.", "pdf_defekt",
                          422) from exc
    if len(text.strip()) < 20:
        raise AbrufFehler("Das Protokoll enthält keinen lesbaren Text.", "pdf_ohne_text",
                          422)
    return _norm(text)


def _muster(begriff: str) -> re.Pattern:
    kern = re.escape(begriff).replace(r"\ ", r"\s*").replace(r"\-", r"[-\s]?")
    return re.compile(rf"(?<![\wÄÖÜäöüß]){kern}(?![\wÄÖÜäöüß])", re.I)


def _einsatzdatum(zeilen: list[str]) -> str | None:
    """Das häufigste Datum außerhalb von Zeilen mit Geburtsdatum oder Alter.
    Ein Protokoll trägt das Einsatzdatum an vielen Zeitstempeln, das
    Geburtsdatum einmal."""
    zaehler: dict[str, int] = {}
    for z in zeilen:
        if GEBURT.search(z):
            continue
        for t, m, j in DATUM.findall(z):
            iso = f"{int(j):04d}-{int(m):02d}-{int(t):02d}"
            zaehler[iso] = zaehler.get(iso, 0) + 1
    return max(zaehler, key=zaehler.get) if zaehler else None


def _einsatzzeit(zeilen: list[str], datum: str | None) -> str | None:
    for schluessel in ("alarm", "einsatzbeginn", "beginn"):
        for z in zeilen:
            if schluessel in z.lower():
                m = ZEIT.search(z)
                if m:
                    return f"{int(m.group(1)):02d}:{m.group(2)}"
    zeiten = sorted(f"{int(h):02d}:{mi}" for z in zeilen if not GEBURT.search(z)
                    for h, mi in ZEIT.findall(z))
    return zeiten[0] if zeiten else None


def auslesen(text: str, massnahmen: list[dict], medikamente: list[dict],
             eigene: dict[str, str] | None = None) -> dict:
    """Erzeugt den Entwurf. ``massnahmen``: id, code, name; ``medikamente``:
    id, name, praeparate (Liste von Namen); ``eigene``: Begriff → measure_id
    aus früheren Zuordnungen der Person."""
    zeilen = [z.strip() for z in text.splitlines() if z.strip()]
    datum = _einsatzdatum(zeilen)
    zeit = _einsatzzeit(zeilen, datum)
    naca = None
    m = NACA.search(text)
    if m:
        naca = ARABISCH_ROEMISCH.get(m.group(1), m.group(1))
    m = EINSATZNR.search(text)
    einsatznummer = m.group(1) if m else None

    # Maßnahmen: Begriffe nach Länge, damit "Larynxmaske" vor "Maske"
    # gewinnt und eine Fundstelle nicht doppelt zählt.
    nach_code = {x["code"]: x for x in massnahmen}
    nach_id = {x["id"]: x for x in massnahmen}
    begriffe: list[tuple[str, dict, bool]] = []
    for x in massnahmen:
        begriffe.append((x["name"], x, True))
    for code, worte in SYNONYME.items():
        if code in nach_code:
            for w in worte:
                begriffe.append((w, nach_code[code], w not in UNSICHER))
    for wort, mid in (eigene or {}).items():
        if mid in nach_id:
            begriffe.append((wort, nach_id[mid], True))
    begriffe.sort(key=lambda b: -len(b[0]))

    belegt: list[tuple[int, int, int]] = []
    funde: dict[str, dict] = {}
    for nr, z in enumerate(zeilen):
        for wort, mass, sicher in begriffe:
            for treffer in _muster(wort).finditer(z):
                a, e = treffer.span()
                if any(n == nr and a < be and e > ba for n, ba, be in belegt):
                    continue
                belegt.append((nr, a, e))
                eintrag = funde.setdefault(mass["id"], {
                    "measure_id": mass["id"], "name": mass["name"], "begriff": wort,
                    "anzahl": 0, "sicher": sicher, "fehlversuch": False, "zeit": None})
                eintrag["anzahl"] += 1
                eintrag["sicher"] = eintrag["sicher"] or sicher
                if FEHLSCHLAG.search(z):
                    eintrag["fehlversuch"] = True
                zt = ZEIT.search(z)
                if zt and not eintrag["zeit"]:
                    eintrag["zeit"] = f"{int(zt.group(1)):02d}:{zt.group(2)}"
                if mass["code"] == "d_bz" and "parameter" not in eintrag:
                    bz = BZ_WERT.search(z)
                    if bz:
                        eintrag["parameter"] = {
                            "wert": bz.group(1).replace(",", "."),
                            "wert__einheit": bz.group(2).lower()}
                        # Mit Messwert ist die Messung belegt.
                        eintrag["sicher"] = True

    gaben = []
    for med in medikamente:
        namen = [med["name"]] + list(med.get("praeparate") or [])
        for z in zeilen:
            if FREMDMEDIKATION.search(z) or not any(_muster(n).search(z) for n in namen):
                continue
            dosis = einheit = route = None
            d = DOSIS.search(z)
            if d:
                dosis = float(d.group(1).replace(",", "."))
                for muster, wert in EINHEITEN:
                    if re.fullmatch(muster, d.group(2), re.I):
                        einheit = wert
                        break
            for muster, wert in ROUTEN:
                if re.search(muster, z, re.I):
                    route = wert
                    break
            zt = ZEIT.search(z)
            gaben.append({"medication_id": med["id"], "name": med["name"],
                          "dosis": dosis, "einheit": einheit, "weg": route,
                          "zeit": f"{int(zt.group(1)):02d}:{zt.group(2)}" if zt else None,
                          "sicher": dosis is not None})
    # Dieselbe Gabe steht in Protokollen oft zweimal (Verlauf und
    # Übersicht). Gleicher Wirkstoff, Dosis und Zeit zählen einmal.
    eindeutig, gesehen = [], set()
    for g in gaben:
        k = (g["medication_id"], g["dosis"], g["einheit"], g["zeit"])
        if k not in gesehen:
            gesehen.add(k)
            eindeutig.append(g)

    return {
        "einsatz": {"datum": datum, "uhrzeit": zeit, "naca": naca,
                    "einsatznummer": einsatznummer},
        "massnahmen": sorted(funde.values(), key=lambda f: (f["zeit"] or "99", f["name"])),
        "medikamente": sorted(eindeutig, key=lambda g: (g["zeit"] or "99", g["name"])),
    }
