"""Datenbankzugriff fuer SCOPE X.

Bewusst SQLAlchemy Core statt ORM: das Schema ist flach, die Abfragen sind
statistisch gepraegt, und die Portabilitaet zwischen SQLite und MariaDB
bleibt erhalten, ohne eine Mapping-Schicht pflegen zu muessen.

Alle Primaerschluessel sind TEXT (UUID4). Das vermeidet AUTOINCREMENT-
Dialektunterschiede und macht Backups zwischen Instanzen zusammenfuehrbar.
"""
from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine

DATABASE_URL = os.environ.get("SCOPEX_DATABASE_URL", "sqlite:////data/scopex.db")

_connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine: Engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    pool_pre_ping=True,
    future=True,
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _rec):
    if not DATABASE_URL.startswith("sqlite"):
        return
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


def new_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@contextmanager
def conn():
    with engine.begin() as c:
        yield c


def q(c, sql: str, /, **params):
    return c.execute(text(sql), params)


def rows(c, sql: str, /, **params) -> list[dict]:
    return [dict(r._mapping) for r in c.execute(text(sql), params)]


def row(c, sql: str, /, **params) -> dict | None:
    r = c.execute(text(sql), params).first()
    return dict(r._mapping) if r else None


def scalar(c, sql: str, /, **params):
    return c.execute(text(sql), params).scalar()


# --------------------------------------------------------------------------
# Migrationen
# --------------------------------------------------------------------------
# Jede Migration ist eine Liste von DDL-Statements mit einer stabilen Version.
# Angewendete Versionen stehen in schema_migrations und werden nie erneut
# ausgefuehrt. Neue Versionen werden angehaengt, bestehende nie geaendert.

MIGRATIONS: list[tuple[str, list[str]]] = [
    ("0001_initial", [
        """CREATE TABLE users (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            email TEXT,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_login_at TEXT,
            failed_logins INTEGER NOT NULL DEFAULT 0,
            lock_until TEXT
        )""",
        """CREATE TABLE user_profile (
            user_id TEXT PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            qualification TEXT,
            role TEXT,
            registration_id TEXT,
            created_at TEXT NOT NULL
        )""",
        """CREATE TABLE auth_totp (
            user_id TEXT PRIMARY KEY,
            secret TEXT NOT NULL,
            confirmed_at TEXT,
            created_at TEXT NOT NULL
        )""",
        """CREATE TABLE recovery_codes (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            code_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            used_at TEXT
        )""",
        """CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        )""",
        "CREATE INDEX ix_sessions_token ON sessions(token_hash)",

        """CREATE TABLE encounters (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            enc_date TEXT NOT NULL,
            enc_time TEXT NOT NULL,
            mission_number TEXT,
            naca TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            locked_at TEXT
        )""",
        "CREATE INDEX ix_enc_user_date ON encounters(user_id, enc_date)",

        """CREATE TABLE measures (
            id TEXT PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,
            name TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            builtin INTEGER NOT NULL DEFAULT 0
        )""",
        """CREATE TABLE measure_parameter_definitions (
            id TEXT PRIMARY KEY,
            measure_id TEXT NOT NULL,
            pkey TEXT NOT NULL,
            label TEXT NOT NULL,
            ptype TEXT NOT NULL,
            unit TEXT,
            options TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            required INTEGER NOT NULL DEFAULT 0
        )""",
        "CREATE INDEX ix_mpd_measure ON measure_parameter_definitions(measure_id)",

        """CREATE TABLE measure_attempts (
            id TEXT PRIMARY KEY,
            encounter_id TEXT NOT NULL,
            measure_id TEXT,
            measure_name TEXT NOT NULL,
            measure_category TEXT NOT NULL,
            performed_at TEXT NOT NULL,
            outcome TEXT NOT NULL,
            delegation TEXT,
            note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            locked_at TEXT
        )""",
        "CREATE INDEX ix_att_enc ON measure_attempts(encounter_id)",

        """CREATE TABLE measure_attempt_parameters (
            id TEXT PRIMARY KEY,
            attempt_id TEXT NOT NULL,
            pkey TEXT NOT NULL,
            label TEXT NOT NULL,
            value_text TEXT,
            unit TEXT
        )""",
        "CREATE INDEX ix_map_att ON measure_attempt_parameters(attempt_id)",

        """CREATE TABLE medications (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            active INTEGER NOT NULL DEFAULT 1,
            builtin INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0
        )""",
        """CREATE TABLE medication_preparations (
            id TEXT PRIMARY KEY,
            medication_id TEXT NOT NULL,
            name TEXT NOT NULL,
            strength TEXT,
            active INTEGER NOT NULL DEFAULT 1
        )""",
        """CREATE TABLE medication_administrations (
            id TEXT PRIMARY KEY,
            encounter_id TEXT NOT NULL,
            medication_id TEXT,
            medication_name TEXT NOT NULL,
            preparation_id TEXT,
            preparation_name TEXT,
            dose REAL,
            unit TEXT,
            route TEXT,
            administered_at TEXT NOT NULL,
            delegation TEXT,
            note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            locked_at TEXT
        )""",
        "CREATE INDEX ix_adm_enc ON medication_administrations(encounter_id)",

        """CREATE TABLE complications (
            id TEXT PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,
            label TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )""",
        """CREATE TABLE attempt_complications (
            id TEXT PRIMARY KEY,
            attempt_id TEXT NOT NULL,
            complication_id TEXT,
            code TEXT NOT NULL,
            label TEXT NOT NULL
        )""",
        "CREATE INDEX ix_ac_att ON attempt_complications(attempt_id)",
        """CREATE TABLE medication_complications (
            id TEXT PRIMARY KEY,
            administration_id TEXT NOT NULL,
            complication_id TEXT,
            code TEXT NOT NULL,
            label TEXT NOT NULL
        )""",
        "CREATE INDEX ix_mc_adm ON medication_complications(administration_id)",

        """CREATE TABLE favorites (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            measure_id TEXT NOT NULL
        )""",
        "CREATE UNIQUE INDEX ix_fav ON favorites(user_id, measure_id)",

        """CREATE TABLE settings (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            skey TEXT NOT NULL,
            svalue TEXT
        )""",
        "CREATE UNIQUE INDEX ix_settings ON settings(user_id, skey)",

        """CREATE TABLE audit_log (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            at TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            action TEXT NOT NULL,
            field TEXT,
            old_value TEXT,
            new_value TEXT
        )""",
        "CREATE INDEX ix_audit_entity ON audit_log(entity_type, entity_id)",
    ]),

    # Ergebnis und Komplikation werden getrennt. Das Ergebnisfeld beantwortet
    # nur noch, ob die Massnahme ihr Ziel erreicht hat. Ob eine Komplikation
    # den Misserfolg verursacht hat und ob ein Patientenschaden zu vermuten
    # ist, haengt jetzt an der einzelnen ZEK-Zuordnung. Die frueheren
    # Auswertungskategorien werden daraus berechnet und koennen sich dadurch
    # nicht mehr widersprechen.
    ("0002_zek_bezug_und_schaden", [
        "ALTER TABLE attempt_complications ADD COLUMN relation TEXT",
        "ALTER TABLE attempt_complications ADD COLUMN patient_harm TEXT",
        "ALTER TABLE medication_complications ADD COLUMN relation TEXT",
        "ALTER TABLE medication_complications ADD COLUMN patient_harm TEXT",
        "UPDATE attempt_complications SET relation = 'begleitend' "
        "WHERE relation IS NULL",
        "UPDATE medication_complications SET relation = 'begleitend' "
        "WHERE relation IS NULL",
        "UPDATE attempt_complications SET patient_harm = 'kein Schaden erkennbar' "
        "WHERE patient_harm IS NULL",
        "UPDATE medication_complications SET patient_harm = 'kein Schaden erkennbar' "
        "WHERE patient_harm IS NULL",
        "CREATE INDEX ix_ac_relation ON attempt_complications(relation)",
        "CREATE INDEX ix_ac_harm ON attempt_complications(patient_harm)",
    ]),

    # Update 1: Rolle bei der Durchführung, Facharztbezeichnung,
    # Soft Delete für gesperrte Einträge.
    #
    # Die Rolle ist bewusst eine eigene Achse neben der Durchführungsart.
    # Für einen Kompetenznachweis ist der Unterschied zwischen selbst
    # durchgeführt und angeleitet grundlegend, und beides muss getrennt
    # zählbar bleiben.
    #
    # Gesperrte Einträge werden nie physisch entfernt, sondern mit
    # Begründung stillgelegt. Sie verschwinden aus Statistik und Nachweis,
    # bleiben aber im Änderungsprotokoll nachvollziehbar. Physisch gelöscht
    # wird nur bei vollständiger Kontolöschung.
    ("0003_rolle_und_soft_delete", [
        "ALTER TABLE measure_attempts ADD COLUMN performer_role TEXT",
        "ALTER TABLE measure_attempts ADD COLUMN performer_qualification TEXT",
        "UPDATE measure_attempts SET performer_role = 'selbst durchgeführt' "
        "WHERE performer_role IS NULL",
        "CREATE INDEX ix_att_role ON measure_attempts(performer_role)",

        "ALTER TABLE user_profile ADD COLUMN specialty TEXT",

        "ALTER TABLE encounters ADD COLUMN deleted_at TEXT",
        "ALTER TABLE encounters ADD COLUMN deleted_reason TEXT",
        "ALTER TABLE measure_attempts ADD COLUMN deleted_at TEXT",
        "ALTER TABLE measure_attempts ADD COLUMN deleted_reason TEXT",
        "ALTER TABLE medication_administrations ADD COLUMN deleted_at TEXT",
        "ALTER TABLE medication_administrations ADD COLUMN deleted_reason TEXT",
        "CREATE INDEX ix_enc_deleted ON encounters(deleted_at)",
        "CREATE INDEX ix_att_deleted ON measure_attempts(deleted_at)",
        "CREATE INDEX ix_adm_deleted ON medication_administrations(deleted_at)",

        # Der Punktionsort-Parameter des intravenösen Zugangs wird von
        # Freitext auf eine Auswahl mit Farbcode umgestellt. Bereits
        # dokumentierte Werte bleiben unangetastet, sie stehen als
        # Textkopie im Datensatz.
        "UPDATE measure_parameter_definitions SET ptype = 'select', "
        "options = '14 G (orange)|16 G (grau)|17 G (weiß)|18 G (grün)|"
        "20 G (rosa)|22 G (blau)|24 G (gelb)|26 G (violett)|andere', "
        "label = 'Größe / Farbe' "
        "WHERE pkey = 'gauge' AND measure_id IN "
        "(SELECT id FROM measures WHERE code = 'c_iv')",
    ]),

    # Die E-Mail-Adresse wird zum zweiten Anmeldemerkmal neben dem
    # Benutzernamen und muss deshalb eindeutig sein. Sie wird in
    # Kleinschreibung normalisiert, damit die Anmeldung nicht an der
    # Groß- und Kleinschreibung scheitert.
    #
    # Ein eindeutiger Index behandelt NULL sowohl in SQLite als auch in
    # MariaDB als verschieden. Konten ohne E-Mail-Adresse bleiben also
    # möglich.
    ("0004_email_als_anmeldename", [
        "UPDATE users SET email = LOWER(TRIM(email)) "
        "WHERE email IS NOT NULL AND TRIM(email) <> ''",
        "UPDATE users SET email = NULL WHERE TRIM(COALESCE(email, '')) = ''",
        "CREATE UNIQUE INDEX ix_users_email ON users(email)",
    ]),

    # Update 2: Rollenmodell, Einladungen, Passwort-Zurücksetzung,
    # Vertrauensgeräte.
    #
    # Das bestehende Konto wird Administrator. Registrieren kann sich danach
    # nur noch, wer einen gültigen Einladungscode hat; der Code selbst wird
    # nur als Hash gespeichert, damit ein Datenbankauszug keine
    # verwendbaren Einladungen enthält. Dasselbe gilt für Reset-Token und
    # Gerätekennungen.
    ("0005_rollen_und_zugaenge", [
        "ALTER TABLE users ADD COLUMN role TEXT",
        "ALTER TABLE users ADD COLUMN disabled_at TEXT",
        "ALTER TABLE users ADD COLUMN invited_by TEXT",
        "UPDATE users SET role = 'admin' WHERE role IS NULL",
        "CREATE INDEX ix_users_role ON users(role)",

        """CREATE TABLE invitations (
            id TEXT PRIMARY KEY,
            code_hash TEXT NOT NULL,
            email TEXT,
            role TEXT NOT NULL,
            note TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            used_by TEXT,
            revoked_at TEXT
        )""",
        "CREATE UNIQUE INDEX ix_inv_code ON invitations(code_hash)",

        """CREATE TABLE password_resets (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            requested_ip_hash TEXT
        )""",
        "CREATE INDEX ix_pr_token ON password_resets(token_hash)",

        """CREATE TABLE trusted_devices (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token_hash TEXT NOT NULL,
            label TEXT,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            last_used_at TEXT
        )""",
        "CREATE INDEX ix_td_token ON trusted_devices(token_hash)",

        "INSERT INTO settings (id, user_id, skey, svalue) VALUES "
        "('set-idle', NULL, 'idle_timeout_minutes', '30')",
        "INSERT INTO settings (id, user_id, skey, svalue) VALUES "
        "('set-invite', NULL, 'invite_valid_days', '7')",
    ]),

    # Update 3.
    ("0006_einsatzkontext_und_medikamentenverlauf", [
        # Schicht und Fahrzeug gehören zum Einsatz, nicht zur Maßnahme.
        "ALTER TABLE encounters ADD COLUMN shift_code TEXT",
        "ALTER TABLE encounters ADD COLUMN vehicle_id TEXT",

        # Medikamentengaben bekommen dieselbe Ergebnisachse wie Maßnahmen,
        # dazu Nebenwirkung und Folgeintervention. Bestandsdaten gelten als
        # erfolgreich, weil sie ohne Ergebnisfeld erfasst wurden und eine
        # dokumentierte Gabe ohne Vermerk stattgefunden hat.
        "ALTER TABLE medication_administrations ADD COLUMN outcome TEXT",
        "ALTER TABLE medication_administrations ADD COLUMN adverse_effect TEXT",
        "ALTER TABLE medication_administrations ADD COLUMN follow_up TEXT",
        "UPDATE medication_administrations SET outcome = 'erfolgreich' "
        "WHERE outcome IS NULL",
        "CREATE INDEX ix_adm_outcome ON medication_administrations(outcome)",

        # Farbgruppe der Spritzenetiketten. Reine Dokumentationsangabe,
        # frei bearbeitbar, keine Vorgabe für die Etikettierung.
        "ALTER TABLE medications ADD COLUMN divi_group TEXT",
        "ALTER TABLE medications ADD COLUMN trade_names TEXT",

        # ZEK, die zum Einsatz gehören und keiner einzelnen Maßnahme
        # zuzuordnen sind, etwa Organisationsprobleme bei der Übergabe.
        """CREATE TABLE encounter_complications (
            id TEXT PRIMARY KEY,
            encounter_id TEXT NOT NULL,
            complication_id TEXT,
            code TEXT NOT NULL,
            label TEXT NOT NULL,
            relation TEXT,
            patient_harm TEXT,
            note TEXT
        )""",
        "CREATE INDEX ix_ec_enc ON encounter_complications(encounter_id)",

        # Punktionsort des intravenösen Zugangs als Auswahl.
        "UPDATE measure_parameter_definitions SET ptype = 'select', "
        "options = 'Handrücken links|Handrücken rechts|Unterarm links|"
        "Unterarm rechts|Ellenbeuge links|Ellenbeuge rechts|Oberarm links|"
        "Oberarm rechts|V. jugularis externa links|V. jugularis externa rechts|"
        "Fußrücken links|Fußrücken rechts|andere' "
        "WHERE pkey = 'ort' AND measure_id IN "
        "(SELECT id FROM measures WHERE code = 'c_iv')",

        # Geschlechtsneutrale Bezeichnungen in bestehenden Profilen.
        "UPDATE user_profile SET qualification = 'Rettungssanitäter*in' "
        "WHERE qualification = 'Rettungssanitäter'",
        "UPDATE user_profile SET qualification = 'Rettungsassistent*in' "
        "WHERE qualification = 'Rettungsassistent'",
        "UPDATE user_profile SET qualification = 'Notfallsanitäter*in' "
        "WHERE qualification = 'Notfallsanitäter'",
        "UPDATE user_profile SET qualification = 'Ärztin / Arzt' "
        "WHERE qualification = 'Arzt / Ärztin'",

        # Vorbelegung der Farbgruppen. Bewusst nur dort, wo die Zuordnung
        # eindeutig ist. Alles Übrige bleibt leer und wird bei Bedarf im
        # Medikamentenkatalog gesetzt. Die Angabe ist Dokumentation, keine
        # Vorgabe für die Etikettierung.
        "UPDATE medications SET divi_group = 'Hypnotika / Induktion (gelb)' WHERE name IN ('Etomidat', 'Propofol', 'Thiopental', 'Esketamin')",
        "UPDATE medications SET divi_group = 'Benzodiazepine (orange)' WHERE name IN ('Midazolam', 'Diazepam', 'Lorazepam', 'Clonazepam')",
        "UPDATE medications SET divi_group = 'Opioide (blau)' WHERE name IN ('Fentanyl', 'Sufentanil', 'Morphin', 'Piritramid')",
        "UPDATE medications SET divi_group = 'Muskelrelaxanzien (rot)' WHERE name IN ('Rocuronium', 'Vecuronium', 'Succinylcholin')",
        "UPDATE medications SET divi_group = 'Antagonisten (gestreift)' WHERE name IN ('Naloxon', 'Flumazenil')",
        "UPDATE medications SET divi_group = 'Vasopressoren / Kreislauf (violett)' WHERE name IN ('Adrenalin', 'Noradrenalin', 'Dobutamin', 'Cafedrin/Theodrenalin', 'Orciprenalin')",
        "UPDATE medications SET divi_group = 'Lokalanästhetika (grau)' WHERE name IN ('Lidocain')",
        "UPDATE medications SET divi_group = 'Anticholinergika (grün)' WHERE name IN ('Atropin')",
        "UPDATE medications SET divi_group = 'Antiemetika (lachs)' WHERE name IN ('Ondansetron', 'Granisetron', 'Dimenhydrinat')",
        "UPDATE medications SET divi_group = 'Elektrolyte (dunkelgrün)' WHERE name IN ('Natriumchlorid 0,9 %', 'Ringer-Acetat', 'Vollelektrolytlösung', 'Magnesiumsulfat')",
    ]),

    # Die Etikettengruppen werden feiner aufgelöst, weil die DIVI-Empfehlung
    # zwischen depolarisierenden und nichtdepolarisierenden Relaxanzien
    # unterscheidet und Antagonisten die Schrägstreifen ihrer Bezugsgruppe
    # tragen.
    ("0007_divi_etikettengruppen", [
        "UPDATE medications SET divi_group = "
        "'Muskelrelaxanzien, nichtdepolarisierend (rot/weiß)' "
        "WHERE divi_group = 'Muskelrelaxanzien (rot)' "
        "AND name IN ('Rocuronium', 'Vecuronium')",
        "UPDATE medications SET divi_group = "
        "'Muskelrelaxanzien, depolarisierend (rot)' "
        "WHERE divi_group = 'Muskelrelaxanzien (rot)'",
        "UPDATE medications SET divi_group = "
        "'Opioid-Antagonisten (blau/weiß gestreift)' "
        "WHERE divi_group = 'Antagonisten (gestreift)' AND name = 'Naloxon'",
        "UPDATE medications SET divi_group = "
        "'Benzodiazepin-Antagonisten (orange/weiß gestreift)' "
        "WHERE divi_group = 'Antagonisten (gestreift)'",
    ]),

    # Etikettengruppen nach der DIVI-Standardtabelle. Ersetzt die grobe
    # Vorbelegung aus 0006 und 0007: alle ausgelieferten Wirkstoffe sind
    # jetzt zugeordnet, auch Antiarrhythmika, Bronchodilatatoren, Hormone
    # und Antikoagulantien, die vorher offen bleiben mussten. Selbst
    # angelegte Wirkstoffe bleiben unberührt.
    ("0008_divi_standardtabelle", [
        "UPDATE medications SET divi_group = 'Hypnotika' WHERE name IN ('Etomidat', 'Propofol', 'Thiopental', 'Esketamin')",
        "UPDATE medications SET divi_group = 'Benzodiazepine' WHERE name IN ('Midazolam', 'Diazepam', 'Lorazepam', 'Clonazepam')",
        "UPDATE medications SET divi_group = 'Benzodiazepin-Antagonisten' WHERE name IN ('Flumazenil')",
        "UPDATE medications SET divi_group = 'Muskelrelaxantien' WHERE name IN ('Rocuronium', 'Vecuronium', 'Succinylcholin')",
        "UPDATE medications SET divi_group = 'Opiate / Opioide' WHERE name IN ('Fentanyl', 'Sufentanil', 'Morphin', 'Piritramid')",
        "UPDATE medications SET divi_group = 'Opioid-Antagonisten' WHERE name IN ('Naloxon')",
        "UPDATE medications SET divi_group = 'Lokalanästhetika' WHERE name IN ('Lidocain')",
        "UPDATE medications SET divi_group = 'Vasopressoren' WHERE name IN ('Adrenalin', 'Noradrenalin', 'Cafedrin/Theodrenalin', 'Orciprenalin')",
        "UPDATE medications SET divi_group = 'Antihypertonika / Vasodilatantien' WHERE name IN ('Metoprolol', 'Urapidil', 'Nitroglycerin')",
        "UPDATE medications SET divi_group = 'Anticholinergika' WHERE name IN ('Atropin', 'Biperidin', 'Butylscopolamin')",
        "UPDATE medications SET divi_group = 'Antiemetika' WHERE name IN ('Ondansetron', 'Granisetron', 'Dimenhydrinat')",
        "UPDATE medications SET divi_group = 'Antiarrhythmika' WHERE name IN ('Amiodaron', 'Adenosin', 'Ajmalin')",
        "UPDATE medications SET divi_group = 'Antikonvulsiva' WHERE name IN ('Phenytoin')",
        "UPDATE medications SET divi_group = 'Bronchodilatatoren' WHERE name IN ('Salbutamol', 'Fenoterol', 'Reproterol', 'Ipratropiumbromid')",
        "UPDATE medications SET divi_group = 'Inodilatatoren' WHERE name IN ('Dobutamin')",
        "UPDATE medications SET divi_group = 'Hormone' WHERE name IN ('Dexamethason', 'Prednisolon', 'Prednison', 'Oxytocin')",
        "UPDATE medications SET divi_group = 'Elektrolyte' WHERE name IN ('Natriumchlorid 0,9 %', 'Ringer-Acetat', 'Vollelektrolytlösung', 'Magnesiumsulfat')",
        "UPDATE medications SET divi_group = 'Antikoagulantien' WHERE name IN ('Acetylsalicylsäure')",
        "UPDATE medications SET divi_group = 'Heparin' WHERE name IN ('Heparin')",
        "UPDATE medications SET divi_group = 'Verschiedene Medikamente' WHERE name IN ('Paracetamol', 'Metamizol', 'Furosemid', 'Glukose', 'Tranexamsäure', 'Dimetinden', 'Clemastin', 'Promethazin', 'Haloperidol', 'Gelatinelösung')",
    ]),

    # Passkeys nach WebAuthn. Der oeffentliche Schluessel liegt hier, der
    # private verlaesst das Geraet des Nutzers nie. sign_count erkennt
    # geklonte Authentifikatoren.
    ("0009_passkeys", [
        """CREATE TABLE passkeys (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            credential_id TEXT NOT NULL,
            public_key TEXT NOT NULL,
            sign_count INTEGER NOT NULL DEFAULT 0,
            label TEXT,
            created_at TEXT NOT NULL,
            last_used_at TEXT
        )""",
        "CREATE UNIQUE INDEX ix_passkeys_cred ON passkeys(credential_id)",
        "CREATE INDEX ix_passkeys_user ON passkeys(user_id)",

        """CREATE TABLE webauthn_challenges (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            kind TEXT NOT NULL,
            challenge TEXT NOT NULL,
            handle TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )""",
        "CREATE UNIQUE INDEX ix_challenge_handle ON webauthn_challenges(handle)",
    ]),
]


LEGACY_OUTCOMES = {"frustran": "fehlgeschlagen"}


def normalize_legacy_outcomes() -> int:
    """Bildet abgeschaffte Ergebniswerte auf die neue Skala ab.

    'frustran' und 'fehlgeschlagen' bezeichneten in der Praxis dasselbe.
    Jede Umsetzung wird einzeln ins Audit-Log geschrieben, damit spaeter
    erkennbar bleibt, dass der Wert nicht so erfasst wurde.
    """
    changed = 0
    with engine.begin() as c:
        for old, new in LEGACY_OUTCOMES.items():
            affected = [dict(r._mapping) for r in c.execute(text(
                "SELECT a.id, e.user_id FROM measure_attempts a "
                "JOIN encounters e ON e.id = a.encounter_id "
                "WHERE a.outcome = :o"), {"o": old})]
            for rec in affected:
                c.execute(text(
                    "INSERT INTO audit_log (id, user_id, at, entity_type, "
                    "entity_id, action, field, old_value, new_value) VALUES "
                    "(:i, :u, :t, 'measure_attempts', :e, 'migrate', "
                    "'outcome', :o, :n)"),
                    {"i": new_id(), "u": rec["user_id"], "t": now_iso(),
                     "e": rec["id"], "o": old, "n": new})
                c.execute(text("UPDATE measure_attempts SET outcome = :n "
                               "WHERE id = :i"), {"n": new, "i": rec["id"]})
                changed += 1
    return changed


def migrate() -> list[str]:
    applied: list[str] = []
    with engine.begin() as c:
        c.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        ))
        done = {r[0] for r in c.execute(text("SELECT version FROM schema_migrations"))}
        for version, statements in MIGRATIONS:
            if version in done:
                continue
            for stmt in statements:
                c.execute(text(stmt))
            c.execute(
                text("INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :a)"),
                {"v": version, "a": now_iso()},
            )
            applied.append(version)
    return applied
