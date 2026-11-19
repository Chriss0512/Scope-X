"""Wiederherstellung vom Server aus.

Wofür das da ist: SCOPE X verlangt einen zweiten Faktor, und es gibt
bewusst keinen Weg, ihn über die Oberfläche zu umgehen. Wer Authenticator
und Wiederherstellungscodes zugleich verliert, kommt deshalb nicht mehr
in sein Konto — auch nicht über „Passwort vergessen", denn auch die
Zurücksetzung verlangt den zweiten Faktor. Das ist richtig so, lässt aber
ohne dieses Werkzeug eine Sackgasse zurück, aus der niemand mehr
herausführt. Mit jeder weiteren Härtung des Anmeldewegs wird diese
Sackgasse wahrscheinlicher, nicht unwahrscheinlicher.

Warum ein Kommandozeilenwerkzeug und kein Notzugang über das Netz: ein
Endpunkt, der den zweiten Faktor aushebeln kann, wäre auf einem öffentlich
erreichbaren Dienst genau die Hintertür, gegen die der ganze Rest gebaut
ist. Wer hier etwas tun will, muss Zugriff auf den Server selbst haben.

Aufruf über das Terminal-Add-on von Home Assistant:

    docker exec -it addon_<slug>_scopex \\
        python -m app.wiederherstellung --liste

    docker exec -it addon_<slug>_scopex \\
        python -m app.wiederherstellung --konto chris --totp-zuruecksetzen

Jeder Eingriff landet im Änderungsprotokoll der Anwendung, als
`wiederherstellung`, und ist dort später nachvollziehbar.
"""
from __future__ import annotations

import argparse
import getpass
import sys

from . import gate, schutz
from .core import audit
from .db import conn, migrate, now_iso, q, row, rows
from .security import (
    destroy_all_sessions,
    forget_all_devices,
    hash_password,
    password_problems,
)


def _protokoll(c, user_id: str, was: str, detail: str = "") -> None:
    """Schreibt den Eingriff ins Änderungsprotokoll.

    Ohne Benutzerkennung als Urheber: hier hat sich niemand angemeldet,
    sondern jemand mit Zugriff auf den Server gehandelt. Genau das soll
    im Protokoll stehen und nicht der Name des betroffenen Kontos, als
    hätte dieser die Änderung selbst vorgenommen.
    """
    audit(c, None, "users", user_id, f"wiederherstellung:{was}",
          new_value=detail or None)


def _konto(c, kennung: str) -> dict:
    treffer = row(c, "SELECT * FROM users WHERE lower(username) = :k "
                     "OR email_idx = :x", k=kennung.strip().lower(),
                  x=schutz.index(kennung))
    if not treffer:
        print(f"Kein Konto mit '{kennung}'. Mit --liste siehst du alle.",
              file=sys.stderr)
        raise SystemExit(2)
    return treffer


def _liste() -> int:
    with conn() as c:
        eintraege = rows(
            c, "SELECT u.username, u.email, u.role, u.failed_logins, "
               "u.lock_until, u.disabled_at, "
               "(SELECT COUNT(*) FROM auth_totp t WHERE t.user_id = u.id "
               " AND t.confirmed_at IS NOT NULL) AS totp "
               "FROM users u ORDER BY u.username")
    if not eintraege:
        print("Noch kein Konto angelegt.")
        return 0
    breite = max(len(e["username"]) for e in eintraege)
    print(f"{'Konto'.ljust(breite)}  Rolle  2FA  Fehlversuche  Zustand")
    for e in eintraege:
        zustand = []
        if e["disabled_at"]:
            zustand.append("stillgelegt")
        if e["lock_until"] and e["lock_until"] > now_iso():
            zustand.append(f"gesperrt bis {e['lock_until'][11:16]} UTC")
        print(f"{e['username'].ljust(breite)}  "
              f"{(e['role'] or 'user')[:5].ljust(5)}  "
              f"{'ja ' if e['totp'] else 'nein'}  "
              f"{str(e['failed_logins'] or 0).rjust(12)}  "
              f"{', '.join(zustand) or 'in Ordnung'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m app.wiederherstellung",
        description="Konten von SCOPE X vom Server aus wiederherstellen.")
    p.add_argument("--liste", action="store_true",
                   help="alle Konten mit ihrem Zustand anzeigen")
    p.add_argument("--konto", metavar="NAME",
                   help="Benutzername oder E-Mail-Adresse")
    p.add_argument("--entsperren", action="store_true",
                   help="Fehlversuche, Sperrfrist und Abkühlung zurücksetzen")
    p.add_argument("--freigeben", action="store_true",
                   help="ein stillgelegtes Konto wieder freigeben")
    p.add_argument("--totp-zuruecksetzen", action="store_true",
                   help="zweiten Faktor entfernen; bei der nächsten Anmeldung "
                        "wird er neu eingerichtet")
    p.add_argument("--passwort", action="store_true",
                   help="neues Passwort setzen, wird verdeckt abgefragt")
    p.add_argument("--rolle", choices=("admin", "user", "guest"),
                   help="Rolle setzen, etwa um wieder einen Administrator zu "
                        "haben")
    args = p.parse_args(argv)

    migrate()
    # Schlüssel gegen die Datenbank prüfen, bevor etwas gelesen wird. Ohne
    # passenden Schlüssel bricht das Werkzeug ab, statt einen neuen
    # anzulegen.
    with conn() as c:
        schutz.pruefen_und_einpflegen(c)

    if args.liste:
        return _liste()

    if not args.konto:
        p.print_help()
        return 1

    eingriffe = [args.entsperren, args.freigeben, args.totp_zuruecksetzen,
                 args.passwort, bool(args.rolle)]
    if not any(eingriffe):
        print("Nichts zu tun. Wähle mindestens einen Eingriff, siehe --help.",
              file=sys.stderr)
        return 1

    neues_passwort = None
    if args.passwort:
        # Vor dem Schreiben abfragen und prüfen, damit nicht die Hälfte der
        # Eingriffe erledigt ist und die andere an einer Eingabe scheitert.
        erste = getpass.getpass("Neues Passwort: ")
        zweite = getpass.getpass("Wiederholen: ")
        if erste != zweite:
            print("Die Eingaben stimmen nicht überein.", file=sys.stderr)
            return 2
        neues_passwort = erste

    with conn() as c:
        user = _konto(c, args.konto)
        uid = user["id"]
        getan = []

        if neues_passwort is not None:
            probleme = password_problems(
                neues_passwort,
                kennungen=(user["username"], user.get("email") or ""))
            if probleme:
                print(" ".join(probleme), file=sys.stderr)
                return 2
            q(c, "UPDATE users SET password_hash = :p WHERE id = :i",
              p=hash_password(neues_passwort), i=uid)
            _protokoll(c, uid, "passwort")
            getan.append("Passwort gesetzt")

        if args.entsperren:
            q(c, "UPDATE users SET failed_logins = 0, lock_until = NULL "
                 "WHERE id = :i", i=uid)
            _protokoll(c, uid, "entsperrt")
            getan.append("Fehlversuche und Sperrfrist zurückgesetzt")

        if args.freigeben:
            q(c, "UPDATE users SET disabled_at = NULL WHERE id = :i", i=uid)
            _protokoll(c, uid, "freigegeben")
            getan.append("Konto freigegeben")

        if args.totp_zuruecksetzen:
            q(c, "DELETE FROM auth_totp WHERE user_id = :u", u=uid)
            q(c, "DELETE FROM recovery_codes WHERE user_id = :u", u=uid)
            _protokoll(c, uid, "totp")
            getan.append("Zweiter Faktor entfernt, wird bei der nächsten "
                         "Anmeldung neu eingerichtet")

        if args.rolle:
            q(c, "UPDATE users SET role = :r WHERE id = :i", r=args.rolle, i=uid)
            _protokoll(c, uid, "rolle", args.rolle)
            getan.append(f"Rolle auf {args.rolle} gesetzt")

    # Außerhalb der Transaktion: beides öffnet eigene Verbindungen.
    gate.abkuehlung_konto_freigeben(uid)
    if neues_passwort is not None or args.totp_zuruecksetzen:
        # Nach einem Eingriff in die Anmeldedaten gilt keine bestehende
        # Sitzung und kein gemerktes Gerät mehr. Sonst bliebe genau der
        # Zugang offen, dessentwegen womöglich eingegriffen wurde.
        destroy_all_sessions(uid)
        forget_all_devices(uid)
        getan.append("Alle Sitzungen beendet und Gerätevertrauen entzogen")

    print(f"Konto {user['username']}:")
    for zeile in getan:
        print(f"  - {zeile}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
