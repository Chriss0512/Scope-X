"""Auslieferungs-Stammdaten.

Wird nur beim ersten Start eingespielt. Danach gehoert der Katalog dem
Nutzer: umbenennen, sortieren, deaktivieren und ergaenzen aendern nie
bereits dokumentierte Eintraege, weil Massnahmen- und Medikamentennamen
beim Speichern in den historischen Datensatz kopiert werden.
"""
from __future__ import annotations

import re

from .db import new_id, q, row, scalar

# Kategorien nach xABCDE plus Trauma und Diagnostik.
CATEGORIES = [
    ("X", "Kritische Blutung"),
    ("A", "Atemweg"),
    ("B", "Atmung"),
    ("C", "Kreislauf"),
    ("D", "Neurologie"),
    ("E", "Exposure / Environment"),
    ("TRAUMA", "Trauma, Reposition, Immobilisation"),
    ("DIAG", "Diagnostik"),
]
CATEGORY_LABELS = dict(CATEGORIES)

# Das Ergebnis beantwortet genau eine Frage: hat die Massnahme ihr Ziel
# erreicht? Alles, was mit Komplikationen zusammenhaengt, haengt an der
# ZEK-Zuordnung, nicht hier. "abgebrochen" ist kein Misserfolg, sondern der
# bewusste Wechsel auf ein anderes Verfahren.
OUTCOMES = ["erfolgreich", "fehlgeschlagen", "abgebrochen"]

# Bezug einer ZEK zur Massnahme.
ZEK_RELATIONS = ["begleitend", "ursächlich"]
ZEK_RELATION_HINTS = {
    "begleitend": "aufgetreten, ohne den Ausgang zu bestimmen",
    "ursächlich": "hat den Misserfolg oder Abbruch verursacht",
}

# Einschaetzung eines Patientenschadens. Praeklinisch ist "gesichert" selten
# belegbar, deshalb ist "vermutet" ein eigener Wert und kein Notbehelf.
PATIENT_HARM = ["kein Schaden erkennbar", "vermutet", "gesichert"]
HARM_RELEVANT = ["vermutet", "gesichert"]
DELEGATIONS = ["eigenverantwortlich", "delegiert"]
NACA_LEVELS = ["0", "I", "II", "III", "IV", "V", "VI", "VII"]

ROUTES = [
    "intravenös", "intraossär", "intramuskulär", "subkutan", "intranasal",
    "oral", "sublingual", "bukkal", "inhalativ", "vernebelt", "rektal",
    "topisch", "endotracheal",
]
UNITS = ["mg", "µg", "g", "ml", "I.E.", "mg/kg", "µg/kg", "ml/kg"]

QUALIFICATIONS = [
    "Rettungssanitäter*in", "Rettungsassistent*in", "Notfallsanitäter*in",
    "Ärztin / Arzt",
]

# Farbgruppen der Spritzenetiketten nach EN ISO 26825 und der ergaenzenden
# DIVI-Empfehlung. Reine Dokumentationsangabe: SCOPE X leitet daraus keine
# Etikettierung ab und macht keine Vorgabe. Die Zuordnung eines Wirkstoffs
# ist im Katalog frei aenderbar und sollte gegen die jeweils aktuelle
# DIVI-Veroeffentlichung geprueft werden.
# Aufbau eines Etiketts: Hintergrundfarbe, Schriftfarbe und Muster.
# "stripes" steht fuer die Schraegstreifen der Antagonisten, "split" fuer
# zweifarbige Etiketten.
#
# Die Farbwerte sind Annaeherungen an die Pantone-Vorgaben der Norm und
# nicht normativ. SCOPE X bildet das Etikett ab, damit die Auswahl in der
# App der Spritze in der Hand entspricht. Es ist keine
# Etikettierungsreferenz und erzeugt keine druckbaren Etiketten.
DIVI_LABELS = {
    "Hypnotika":
        {"bg": "#fedd00", "fg": "#17242c", "pattern": "solid"},
    "Benzodiazepine":
        {"bg": "#ff8200", "fg": "#17242c", "pattern": "solid"},
    "Benzodiazepin-Antagonisten":
        {"bg": "#ff8200", "fg": "#17242c", "pattern": "stripes"},
    "Muskelrelaxantien":
        {"bg": "#f9423a", "fg": "#ffffff", "pattern": "solid"},
    "Muskelrelaxans-Antagonisten":
        {"bg": "#f9423a", "fg": "#ffffff", "pattern": "stripes"},
    "Opiate / Opioide":
        {"bg": "#71c5e8", "fg": "#17242c", "pattern": "solid"},
    "Opioid-Antagonisten":
        {"bg": "#71c5e8", "fg": "#17242c", "pattern": "stripes"},
    "Lokalanästhetika":
        {"bg": "#c4bfb6", "fg": "#17242c", "pattern": "solid"},
    "Vasopressoren":
        {"bg": "#d6bfdd", "fg": "#17242c", "pattern": "solid"},
    "Antihypertonika / Vasodilatantien":
        {"bg": "#d6bfdd", "fg": "#17242c", "pattern": "stripes"},
    "Anticholinergika":
        {"bg": "#a4d65e", "fg": "#17242c", "pattern": "solid"},
    "Antiemetika":
        {"bg": "#efbe7d", "fg": "#17242c", "pattern": "solid"},
    "Antiarrhythmika":
        {"bg": "#ff7f32", "fg": "#17242c", "pattern": "solid"},
    "Antikonvulsiva":
        {"bg": "#6b4c9a", "fg": "#ffffff", "pattern": "solid"},
    "Bronchodilatatoren":
        {"bg": "#10069f", "fg": "#ffffff", "pattern": "solid"},
    "Inodilatatoren":
        {"bg": "#ef95b5", "fg": "#17242c", "pattern": "solid"},
    "Hormone":
        {"bg": "#a9744f", "fg": "#ffffff", "pattern": "solid"},
    "Elektrolyte":
        {"bg": "#046a38", "fg": "#ffffff", "pattern": "solid"},
    "Antikoagulantien":
        {"bg": "#c8c9c7", "fg": "#17242c", "pattern": "solid"},
    "Heparin":
        {"bg": "#ffffff", "fg": "#17242c", "pattern": "framed"},
    "Protamin":
        {"bg": "#1c1c1c", "fg": "#ffffff", "pattern": "stripes"},
    "Verschiedene Medikamente":
        {"bg": "#ffffff", "fg": "#17242c", "pattern": "solid"},
}

# Ein Slug je Gruppe, weil die Content-Security-Policy keine
# style-Attribute erlaubt. Die Farben stehen als feste Regeln im
# Stylesheet und werden ueber data-divi ausgewaehlt.
for _name, _style in DIVI_LABELS.items():
    _base = _name.split("(")[0].strip().lower()
    for _a, _b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        _base = _base.replace(_a, _b)
    _style["slug"] = re.sub(r"[^a-z0-9]+", "-", _base).strip("-")

DIVI_GROUPS = list(DIVI_LABELS)

# Rolle bei der Durchführung. Eigene Achse neben der Durchführungsart:
# eigenverantwortlich oder delegiert beantwortet, unter welcher Legitimation
# gehandelt wurde. Die Rolle beantwortet, wer die Hand am Patienten hatte.
PERFORMER_ROLES = ["selbst durchgeführt", "angeleitet", "assistiert"]
PERFORMER_ROLE_HINTS = {
    "selbst durchgeführt": "Maßnahme eigenhändig ausgeführt",
    "angeleitet": "eine andere Person hat unter deiner Anleitung ausgeführt",
    "assistiert": "bei der Durchführung einer anderen Person assistiert",
}

_SIDES = "links|rechts"
_YESNO = "ja|nein"

# (code, kategorie, name, [(pkey, label, typ, einheit, optionen)])
MEASURES: list[tuple] = [
    ("x_tourniquet", "X", "Tourniquet", [
        ("lokalisation", "Lokalisation", "text", None, None),
    ]),
    ("x_druckverband", "X", "Druckverband", []),
    ("x_haemostat", "X", "Hämostatischer Verband", []),
    ("x_beckenschlinge", "X", "Beckenschlinge", []),

    ("a_guedel", "A", "Oropharyngealer Atemweg / Guedel-Tubus", [
        ("groesse", "Größe", "text", None, None),
    ]),
    ("a_wendl", "A", "Nasopharyngealer Atemweg", [
        ("groesse", "Größe", "text", None, None),
    ]),
    ("a_larynxtubus", "A", "Larynxtubus", [
        ("groesse", "Größe", "text", None, None),
    ]),
    ("a_larynxmaske", "A", "Larynxmaske", [
        ("groesse", "Größe", "text", None, None),
    ]),
    ("a_igel", "A", "i-gel", [
        ("groesse", "Größe", "text", None, None),
    ]),
    ("a_intubation", "A", "Endotracheale Intubation", [
        ("tubusgroesse", "Tubusgröße", "number", "ID", None),
        ("versuche", "Anzahl der Versuche", "int", None, None),
        ("cormack", "Cormack-Lehane-Grad", "select", None, "I|II a|II b|III|IV"),
    ]),
    ("a_absaugen", "A", "Absaugen", []),
    ("a_koniotomie", "A", "Koniotomie", [
        ("technik", "Variante / Technik", "select", None,
         "Nadeltechnik|Skalpell-Bougie-Technik|Seldinger-Technik|"
         "kommerzielles System|andere"),
    ]),

    ("b_beutel_maske", "B", "Beutel-Masken-Beatmung", []),
    ("b_sauerstoff", "B", "Sauerstoffgabe", [
        ("flow", "Flow", "number", "l/min", None),
        ("applikation", "Applikation", "select", None,
         "Nasenbrille|Maske|Maske mit Reservoir|Demand-Ventil|andere"),
    ]),
    ("b_cpap", "B", "CPAP / nichtinvasive Beatmung", [
        ("peep", "PEEP", "number", "cmH2O", None),
        ("fio2", "FiO2", "number", "%", None),
        ("ps", "Druckunterstützung", "number", "cmH2O", None),
    ]),
    ("b_invasiv", "B", "Invasive Beatmung", [
        ("modus", "Beatmungsmodus", "text", None, None),
        ("peep", "PEEP", "number", "cmH2O", None),
        ("asb", "ASB / Druckunterstützung", "number", "cmH2O", None),
    ]),
    ("b_entlastung", "B", "Thoraxentlastungspunktion", [
        ("seite", "Seite", "select", None, _SIDES),
        ("zugang", "Zugangsposition", "select", None,
         "Monaldi|Bülau|andere"),
        ("technik", "Technik", "text", None, None),
    ]),
    ("b_fingerthorakostomie", "B", "Fingerthorakostomie", [
        ("seite", "Seite", "select", None, _SIDES),
        ("zugang", "Zugangsposition", "select", None, "Monaldi|Bülau|andere"),
    ]),
    ("b_thoraxdrainage", "B", "Thoraxdrainage", [
        ("seite", "Seite", "select", None, _SIDES),
        ("zugang", "Zugangsposition", "select", None, "Monaldi|Bülau|andere"),
        ("groesse", "Größe", "number", "French", None),
    ]),

    ("c_iv", "C", "Intravenöser Zugang", [
        ("ort", "Punktionsort", "select", None,
         "Handrücken links|Handrücken rechts|Unterarm links|Unterarm rechts|"
         "Ellenbeuge links|Ellenbeuge rechts|Oberarm links|Oberarm rechts|"
         "V. jugularis externa links|V. jugularis externa rechts|"
         "Fußrücken links|Fußrücken rechts|andere"),
        ("gauge", "Größe / Farbe", "select", None,
         "14 G (orange)|16 G (grau)|17 G (weiß)|18 G (grün)|20 G (rosa)|"
         "22 G (blau)|24 G (gelb)|26 G (violett)|andere"),
    ]),
    ("c_io", "C", "Intraossärer Zugang", [
        ("ort", "Punktionsort", "select", None,
         "Humerus proximal|Tibia proximal|Tibia distal|Femur distal|andere"),
    ]),
    ("c_defibrillation", "C", "Defibrillation", [
        ("energie", "Energie", "number", "J", None),
    ]),
    ("c_kardioversion", "C", "Synchronisierte Kardioversion", [
        ("energie", "Energie", "number", "J", None),
    ]),
    ("c_pacing", "C", "Transkutanes Pacing", [
        ("stromstaerke", "Stromstärke", "number", "mA", None),
        ("frequenz", "Frequenz", "int", "/min", None),
    ]),
    ("c_kristalloid", "C", "Kristalloide Volumentherapie", [
        ("loesung", "Lösung / Präparat", "text", None, None),
        ("menge", "Menge", "number", "ml", None),
    ]),
    ("c_kolloid", "C", "Kolloidale Volumentherapie", [
        ("loesung", "Lösung / Präparat", "text", None, None),
        ("menge", "Menge", "number", "ml", None),
    ]),

    ("d_bz", "D", "Blutzuckermessung", [
        ("wert", "Wert", "number", "mg/dl", None),
    ]),

    ("e_temperatur", "E", "Temperaturmanagement", [
        ("massnahme", "Art", "select", None,
         "aktive Wärmeerhaltung|aktive Kühlung|passiv|andere"),
    ]),

    ("t_reposition_fraktur", "TRAUMA", "Reposition einer Fraktur", [
        ("lokalisation", "Anatomische Lokalisation", "text", None, None),
    ]),
    ("t_reposition_luxation", "TRAUMA", "Reposition einer Gelenkluxation", [
        ("lokalisation", "Anatomische Lokalisation", "text", None, None),
    ]),
    ("t_immobilisation", "TRAUMA", "Immobilisation", [
        ("art", "Art", "text", None, None),
    ]),
    ("t_traktionsschiene", "TRAUMA", "Traktionsschiene", [
        ("seite", "Seite", "select", None, _SIDES),
    ]),

    ("g_ekg12", "DIAG", "12-Kanal-EKG", []),
    ("g_kapnographie", "DIAG", "Kapnographie", []),
    ("g_pulsoxymetrie", "DIAG", "Pulsoxymetrie", []),
    ("g_pocus", "DIAG", "Präklinischer Ultraschall / POCUS", [
        ("protokoll", "Fragestellung / Protokoll", "text", None, None),
    ]),
]

# Vorbelegung der Farbgruppen. Bewusst nur dort, wo die Zuordnung eindeutig
# ist; alles Uebrige bleibt leer und wird im Katalog gesetzt. Dieselbe
# Zuordnung steht in Migration 0006 fuer bestehende Installationen.
DIVI_ASSIGNMENT = {
    "Hypnotika": ["Etomidat", "Propofol", "Thiopental", "Esketamin"],
    "Benzodiazepine": ["Midazolam", "Diazepam", "Lorazepam", "Clonazepam"],
    "Benzodiazepin-Antagonisten": ["Flumazenil"],
    "Muskelrelaxantien": ["Rocuronium", "Vecuronium", "Succinylcholin"],
    "Opiate / Opioide": ["Fentanyl", "Sufentanil", "Morphin", "Piritramid"],
    "Opioid-Antagonisten": ["Naloxon"],
    "Lokalanästhetika": ["Lidocain"],
    "Vasopressoren": ["Adrenalin", "Noradrenalin", "Cafedrin/Theodrenalin",
                      "Orciprenalin"],
    "Antihypertonika / Vasodilatantien": ["Metoprolol", "Urapidil",
                                          "Nitroglycerin"],
    "Anticholinergika": ["Atropin", "Biperidin", "Butylscopolamin"],
    "Antiemetika": ["Ondansetron", "Granisetron", "Dimenhydrinat"],
    "Antiarrhythmika": ["Amiodaron", "Adenosin", "Ajmalin"],
    "Antikonvulsiva": ["Phenytoin"],
    "Bronchodilatatoren": ["Salbutamol", "Fenoterol", "Reproterol",
                           "Ipratropiumbromid"],
    "Inodilatatoren": ["Dobutamin"],
    "Hormone": ["Dexamethason", "Prednisolon", "Prednison", "Oxytocin"],
    "Elektrolyte": ["Natriumchlorid 0,9 %", "Ringer-Acetat",
                    "Vollelektrolytlösung", "Magnesiumsulfat"],
    "Antikoagulantien": ["Acetylsalicylsäure"],
    "Heparin": ["Heparin"],
    "Verschiedene Medikamente": [
        "Paracetamol", "Metamizol", "Furosemid", "Glukose", "Tranexamsäure",
        "Dimetinden", "Clemastin", "Promethazin", "Haloperidol",
        "Gelatinelösung"],
}
_DIVI_BY_NAME = {name: group
                 for group, names in DIVI_ASSIGNMENT.items()
                 for name in names}

MEDICATIONS = [
    "Adrenalin", "Noradrenalin", "Amiodaron", "Adenosin", "Atropin",
    "Metoprolol", "Urapidil", "Nitroglycerin", "Acetylsalicylsäure",
    "Heparin", "Fentanyl", "Sufentanil", "Morphin", "Piritramid",
    "Esketamin", "Midazolam", "Diazepam", "Lorazepam", "Clonazepam",
    "Etomidat", "Propofol", "Thiopental", "Rocuronium", "Succinylcholin",
    "Vecuronium", "Naloxon", "Flumazenil", "Paracetamol", "Metamizol",
    "Ondansetron", "Granisetron", "Dimenhydrinat", "Dexamethason",
    "Prednisolon", "Prednison", "Salbutamol", "Fenoterol", "Reproterol",
    "Ipratropiumbromid", "Furosemid", "Glukose", "Tranexamsäure",
    "Magnesiumsulfat", "Biperidin", "Butylscopolamin", "Dimetinden",
    "Clemastin", "Promethazin", "Haloperidol", "Lidocain", "Ajmalin",
    "Phenytoin", "Dobutamin", "Cafedrin/Theodrenalin", "Orciprenalin",
    "Oxytocin", "Natriumchlorid 0,9 %", "Ringer-Acetat",
    "Vollelektrolytlösung", "Gelatinelösung",
]

# (code, kategorie, bezeichnung)
COMPLICATIONS = [
    ("01", "Atemwege / Gasaustausch", "Diskonnektion"),
    ("02", "Atemwege / Gasaustausch", "Tubus verlegt / abgeknickt"),
    ("03", "Atemwege / Gasaustausch", "Akzidentelle Extubation"),
    ("04", "Atemwege / Gasaustausch", "Nicht vorhergesehene schwierige Intubation"),
    ("05", "Atemwege / Gasaustausch", "Intubation nicht möglich"),
    ("06", "Atemwege / Gasaustausch", "Fehlintubation"),
    ("07", "Atemwege / Gasaustausch", "Einseitige Intubation"),
    ("09", "Atemwege / Gasaustausch", "Laryngospasmus"),
    ("11", "Atemwege / Gasaustausch", "Aspiration"),
    ("12", "Atemwege / Gasaustausch", "Hypoventilation / Hypoxämie"),
    ("15", "Atemwege / Gasaustausch", "Andere respiratorische Störung"),

    ("18", "Herz-Kreislauf", "Hypotension"),
    ("19", "Herz-Kreislauf", "Hypertension"),
    ("20", "Herz-Kreislauf", "Arrhythmie"),
    ("21", "Herz-Kreislauf", "Tachykardie"),
    ("22", "Herz-Kreislauf", "Bradykardie"),
    ("23", "Herz-Kreislauf", "Hypovolämie"),
    ("26", "Herz-Kreislauf", "Kreislaufstillstand"),
    ("29", "Herz-Kreislauf", "Venenzugang nicht möglich"),
    ("30", "Herz-Kreislauf", "Andere Störung des Herz-Kreislauf-Systems"),

    ("40", "Allgemeine Reaktionen", "Anaphylaktisch-allergische Reaktion"),
    ("42", "Allgemeine Reaktionen", "Hypothermie"),
    ("48", "Allgemeine Reaktionen", "Andere allgemeine Reaktion"),

    ("60", "Zentrales Nervensystem", "Krampfanfall"),
    ("61", "Zentrales Nervensystem", "Verwirrtheitszustand"),
    ("64", "Zentrales Nervensystem", "Andere zentrale neurologische Störung"),

    ("67", "Medizintechnik", "Narkosegerät / Beatmungsgerät"),
    ("68", "Medizintechnik", "EKG-Überwachungsgerät"),
    ("69", "Medizintechnik", "Automatische Blutdruckmessung"),
    ("70", "Medizintechnik", "Externer Schrittmacher"),
    ("71", "Medizintechnik", "Defibrillator"),
    ("72", "Medizintechnik", "Pulsoxymetrie"),
    ("73", "Medizintechnik", "Intubationsbesteck"),
    ("74", "Medizintechnik", "Medikamentenzufuhr / Infusionssystem / Pumpe"),
    ("75", "Medizintechnik", "Andere Störung der Medizintechnik"),

    ("78", "Läsionen", "Fehl- oder Mehrfachpunktion von Gefäßen"),
    ("79", "Läsionen", "Zähne"),
    ("80", "Läsionen", "Gefäße"),
    ("81", "Läsionen", "Muskel- und Weichteile"),
    ("82", "Läsionen", "Haut"),
    ("83", "Läsionen", "Atemwege"),
    ("84", "Läsionen", "Augen"),
    ("85", "Läsionen", "Epistaxis"),
    ("86", "Läsionen", "Pneumothorax / Hämatothorax"),
    ("87", "Läsionen", "Nerven"),
    ("88", "Läsionen", "Verletzung durch Herzdruckmassage"),
    ("89", "Läsionen", "Andere Läsion"),

    ("91", "Organisation", "Zwangseinweisung / Zwangsbehandlung"),
    ("92", "Organisation", "Fehlerhafte Einsatzmeldung"),
    ("93", "Organisation", "Nächstgelegenes geeignetes Rettungsmittel nicht verfügbar"),
    ("94", "Organisation", "Nächstgelegenes geeignetes Krankenhaus nicht aufnahmebereit"),
    ("95", "Organisation", "Übergabeproblem in aufnehmender Klinik"),
    ("96", "Organisation", "Zusätzlich erforderliches Rettungsmittel nicht zeitgerecht verfügbar"),
    ("97", "Organisation", "Einsatz unter Leitung eines Leitenden Notarztes"),
    ("98", "Organisation", "Sonstiges"),
]

DEFAULT_SETTINGS = {
    "edit_window_minutes": "120",
    "imprint_name": "Christian Faust",
    "imprint_address": "Eichenweg 2c, 29690 Buchholz/Aller",
    "imprint_email": "",
    "imprint_phone": "",
    "imprint_profession": "",
    "imprint_authority": "",
    "imprint_law": "",
    "theme": "auto",
    "show_delegation": "auto",
}


def seed_if_empty(c) -> bool:
    """Gibt True zurueck, wenn Stammdaten neu angelegt wurden."""
    if scalar(c, "SELECT COUNT(*) FROM measures"):
        return False

    for i, (code, cat, name, params) in enumerate(MEASURES):
        mid = new_id()
        q(c, "INSERT INTO measures (id, code, category, name, sort_order, "
             "active, builtin) VALUES (:i, :c, :k, :n, :s, 1, 1)",
          i=mid, c=code, k=cat, n=name, s=i * 10)
        for j, (pkey, label, ptype, unit, options) in enumerate(params):
            q(c, "INSERT INTO measure_parameter_definitions (id, measure_id, "
                 "pkey, label, ptype, unit, options, sort_order, required) "
                 "VALUES (:i, :m, :k, :l, :t, :u, :o, :s, 0)",
              i=new_id(), m=mid, k=pkey, l=label, t=ptype, u=unit,
              o=options, s=j * 10)

    for i, name in enumerate(MEDICATIONS):
        q(c, "INSERT INTO medications (id, name, active, builtin, sort_order, "
             "divi_group) VALUES (:i, :n, 1, 1, :s, :g)",
          i=new_id(), n=name, s=i * 10, g=_DIVI_BY_NAME.get(name))

    for code, cat, label in COMPLICATIONS:
        q(c, "INSERT INTO complications (id, code, category, label, active) "
             "VALUES (:i, :c, :k, :l, 1)",
          i=new_id(), c=code, k=cat, l=label)

    for key, value in DEFAULT_SETTINGS.items():
        if not row(c, "SELECT id FROM settings WHERE user_id IS NULL AND skey = :k", k=key):
            q(c, "INSERT INTO settings (id, user_id, skey, svalue) "
                 "VALUES (:i, NULL, :k, :v)", i=new_id(), k=key, v=value)
    return True
