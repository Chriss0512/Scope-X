"""Mailversand.

Die Zugangsdaten kommen ausschliesslich aus der Add-on-Konfiguration und
stehen nie im Quelltext oder in der Datenbank. Ist kein Server hinterlegt,
bleibt die Anwendung voll funktionsfaehig: Einladungen und Reset-Links
lassen sich dann im Administrationsbereich anzeigen und von Hand
weitergeben.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

log = logging.getLogger("scopex.mail")


def config() -> dict:
    return {
        "host": os.environ.get("SCOPEX_SMTP_HOST", "").strip(),
        "port": int(os.environ.get("SCOPEX_SMTP_PORT", "465") or 465),
        "security": os.environ.get("SCOPEX_SMTP_SECURITY", "ssl").strip().lower(),
        "user": os.environ.get("SCOPEX_SMTP_USER", "").strip(),
        "password": os.environ.get("SCOPEX_SMTP_PASSWORD", ""),
        "sender": os.environ.get("SCOPEX_SMTP_FROM", "").strip(),
        "base_url": os.environ.get("SCOPEX_BASE_URL", "").strip().rstrip("/"),
    }


def is_configured() -> bool:
    c = config()
    return bool(c["host"] and c["sender"])


def send(to: str, subject: str, body: str) -> bool:
    """Verschickt eine Nachricht. Gibt False zurueck, wenn kein Server
    hinterlegt ist oder der Versand scheitert.

    Fehler werden protokolliert, aber ohne Empfaengeradresse und ohne
    Inhalt: im Log sollen keine personenbezogenen Daten landen.
    """
    c = config()
    if not is_configured():
        log.warning("Kein SMTP-Server hinterlegt, Nachricht nicht verschickt.")
        return False

    msg = EmailMessage()
    msg["From"] = formataddr(("SCOPE X", c["sender"]))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(body)

    context = ssl.create_default_context()
    try:
        if c["security"] == "ssl":
            server = smtplib.SMTP_SSL(c["host"], c["port"], timeout=20,
                                      context=context)
        else:
            server = smtplib.SMTP(c["host"], c["port"], timeout=20)
            if c["security"] == "starttls":
                server.starttls(context=context)
        with server:
            if c["user"]:
                server.login(c["user"], c["password"])
            server.send_message(msg)
        return True
    except Exception as exc:
        log.error("Mailversand fehlgeschlagen: %s", type(exc).__name__)
        return False


def link(path: str) -> str:
    base = config()["base_url"]
    return f"{base}/{path.lstrip('/')}" if base else path


def send_reset(to: str, token: str) -> bool:
    url = link(f"#/passwort-neu?token={token}")
    return send(to, "SCOPE X: Passwort zurücksetzen", f"""\
Für dein SCOPE-X-Konto wurde eine Zurücksetzung des Passworts angefordert.

{url}

Der Link gilt 30 Minuten und funktioniert einmal. Du brauchst zusätzlich
einen Code aus deiner Authenticator-App oder einen Wiederherstellungscode.

Wenn du das nicht warst, ignoriere diese Nachricht. Ohne den zweiten Faktor
lässt sich mit diesem Link nichts ausrichten.
""")


def send_invitation(to: str, code: str, role: str, days: int) -> bool:
    url = link(f"#/registrieren?code={code}")
    return send(to, "SCOPE X: Einladung", f"""\
Du wurdest zu SCOPE X eingeladen, dem Maßnahmen- und Kompetenzlogbuch für
den Rettungsdienst.

{url}

Einladungscode: {code}
Rolle: {role}
Gültig: {days} Tage

Beim ersten Anmelden richtest du eine Zwei-Faktor-Authentifizierung ein.
Halte dafür eine Authenticator-App bereit.
""")
