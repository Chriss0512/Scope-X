"""Nutzungsvereinbarung.

Die Fassung steht im Code und nicht in der Datenbank: jede Änderung geht
damit durch dieselbe Prüfung und dasselbe Änderungsprotokoll wie der
übrige Quelltext, und niemand kann sie über die Oberfläche still
umschreiben, nachdem andere ihr zugestimmt haben.

Erhöht sich VERSION, müssen alle Mitglieder bei der nächsten Anfrage
erneut zustimmen. Bis dahin beantwortet der Server jede Anfrage außerhalb
der unten freigegebenen Pfade mit 428 (siehe core.current_user). Eine
reine Korrektur von Tippfehlern rechtfertigt keine neue Fassung.

Der Text ist eine sorgfältige Vorlage, keine Rechtsberatung. Wer SCOPE X
für andere betreibt, sollte ihn vor dem Einsatz prüfen lassen.
"""
from __future__ import annotations

from .db import new_id, now_iso, q, row

VERSION = "2026-11"
STAND = "19. November 2026"

ABSCHNITTE: list[tuple[str, list[str]]] = [
    ("Worum es geht", [
        "SCOPE X ist ein Kompetenzlogbuch und ein fachliches Netzwerk für "
        "Menschen, die in der Notfallversorgung arbeiten oder dafür "
        "ausgebildet werden. Es soll Lernen, Praxisanleitung und kollegialen "
        "Austausch unterstützen.",
        "Diese Vereinbarung regelt, wie wir miteinander umgehen. Sie gilt "
        "zwischen dir und dem Betreiber dieser Installation, der im Impressum "
        "genannt ist.",
    ]),
    ("Wer teilnehmen darf", [
        "Teilnehmen dürfen Angehörige der Gesundheitsfachberufe, Einsatzkräfte "
        "und Personen in entsprechender Ausbildung. Der Zugang erfolgt nur "
        "auf Einladung oder nach angenommener Bewerbung.",
        "Du legst ein Konto ausschließlich für dich selbst an, machst wahre "
        "Angaben zu Person und Qualifikation und gibst deine Zugangsdaten "
        "nicht weiter.",
    ]),
    ("Schweigepflicht und Patientendaten", [
        "Für alles, was du hier teilst, gilt deine berufliche Schweigepflicht "
        "(§ 203 StGB) unverändert. Patientinnen und Patienten dürfen weder "
        "direkt noch über die Summe der Angaben erkennbar sein.",
        "Nicht in Beiträge, Kommentare, Fallvorstellungen oder Nachrichten "
        "gehören insbesondere: Namen, Geburtsdaten, Anschriften, "
        "Einsatznummern, Einsatzorte, Uhrzeiten, Kennzeichen, Fotos von "
        "Personen oder Dokumenten mit Personenbezug, seltene Merkmale, die "
        "auf eine Person schließen lassen.",
        "SCOPE X prüft Texte auf einige dieser Angaben und weist auf Treffer "
        "hin. Diese Prüfung ist eine Hilfe, keine Garantie; die "
        "Verantwortung bleibt bei dir.",
    ]),
    ("Keine Behandlungsempfehlung", [
        "Inhalte in SCOPE X sind kollegialer Austausch. Sie ersetzen weder "
        "Leitlinien noch die Vorgaben deines Ärztlichen Leiters "
        "Rettungsdienst, deine SOPs oder die ärztliche Anordnung im "
        "Einzelfall.",
        "SCOPE X selbst gibt keine Indikationen, Dosierungen oder "
        "Algorithmen vor. Für deine Entscheidungen im Einsatz bist du nach "
        "den für dich geltenden Regeln verantwortlich.",
    ]),
    ("Umgang miteinander", [
        "Wir diskutieren sachlich, respektvoll und kollegial – auch bei "
        "Fehlern und Komplikationen. Wer einen eigenen Fehler offen teilt, "
        "verdient Unterstützung, keine Bloßstellung.",
        "Nicht erlaubt sind Beleidigungen, Diskriminierung, Belästigung, "
        "Drohungen, Bloßstellung von Kolleginnen, Kollegen oder "
        "Organisationen, Werbung ohne Kennzeichnung und das Sammeln von "
        "Daten anderer Mitglieder.",
        "Beurteile Fälle, nicht Menschen. Kritik an Abläufen und "
        "Entscheidungen ist willkommen, wenn sie konkret und konstruktiv ist.",
    ]),
    ("Deine Inhalte", [
        "Du teilst nur, was du teilen darfst: eigene Texte, eigene Bilder und "
        "Videos oder Material, für das du die nötigen Rechte hast.",
        "Du räumst dem Betreiber das einfache, nicht übertragbare Recht ein, "
        "deine Inhalte innerhalb von SCOPE X im Rahmen deiner "
        "Sichtbarkeitseinstellungen anzuzeigen. Du kannst sie jederzeit "
        "löschen; geteilte Fassungen anderer verweisen danach ins Leere.",
    ]),
    ("Moderation und Sperrung", [
        "Mitglieder können Inhalte melden. Die Administration prüft "
        "Meldungen und kann Inhalte ausblenden, Kommentare schließen oder "
        "Konten sperren, wenn gegen diese Vereinbarung verstoßen wird.",
        "Bei schweren Verstößen, insbesondere gegen die Schweigepflicht, "
        "kann ein Inhalt ohne vorherige Rücksprache entfernt werden. Du "
        "erfährst davon und kannst Stellung nehmen.",
    ]),
    ("Datenschutz", [
        "Welche Daten SCOPE X verarbeitet und welche Rechte du hast, steht "
        "in der Datenschutzerklärung dieser Installation. Dein Logbuch ist "
        "privat; Einsatznummer, Ort, Fahrzeug und Zeitpunkt sind nur für dich "
        "sichtbar.",
        "Eine Auskunft über deine Daten und die Löschung deines Kontos sind "
        "jederzeit im Profil möglich, auch ohne dieser Fassung zuzustimmen.",
    ]),
    ("Haftung", [
        "SCOPE X wird ohne Gewähr für Verfügbarkeit und Richtigkeit der "
        "Inhalte anderer Mitglieder bereitgestellt. Die Haftung des "
        "Betreibers für Vorsatz und grobe Fahrlässigkeit sowie bei Verletzung "
        "von Leben, Körper oder Gesundheit bleibt unberührt.",
    ]),
    ("Änderungen", [
        "Ändert sich diese Vereinbarung inhaltlich, erhält sie eine neue "
        "Fassung. Du wirst bei der nächsten Anmeldung gebeten, ihr "
        "zuzustimmen. Stimmst du nicht zu, kannst du deine Daten exportieren "
        "und dein Konto löschen.",
    ]),
]

# Pfade, die auch ohne Zustimmung zur aktuellen Fassung erreichbar bleiben:
# Anmeldung und Abmeldung, die Vereinbarung selbst, öffentliche Angaben,
# Datenauskunft und Kontolöschung. Alles andere wartet auf die Zustimmung.
FREI = (
    "/api/auth/",
    "/api/nutzung",
    "/api/oeffentlich/",
    "/api/legal",
    "/api/exports/my-data",
    "/api/account/delete",
)


def frei(pfad: str) -> bool:
    return any(pfad.startswith(p) for p in FREI)


def offen(c, user_id: str) -> bool:
    """True, solange die aktuelle Fassung nicht angenommen ist."""
    return not row(c, "SELECT id FROM terms_acceptance WHERE user_id = :u "
                      "AND version = :v", u=user_id, v=VERSION)


def zustimmen(c, user_id: str) -> None:
    if offen(c, user_id):
        q(c, "INSERT INTO terms_acceptance (id, user_id, version, accepted_at) "
             "VALUES (:i, :u, :v, :t)",
          i=new_id(), u=user_id, v=VERSION, t=now_iso())


def fassung() -> dict:
    return {"version": VERSION, "stand": STAND,
            "abschnitte": [{"titel": t, "absaetze": a} for t, a in ABSCHNITTE]}
