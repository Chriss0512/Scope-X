"""Anmeldung und Zwei-Faktor-Authentifizierung."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .. import gate, mailer
from ..core import ROLE_LABELS, audit, current_user, optional_user
from ..db import conn, new_id, now_iso, q, row, rows, scalar
from ..security import (
    DEVICE_COOKIE,
    DEVICE_DAYS,
    SESSION_COOKIE,
    SESSION_DAYS,
    consume_recovery_code,
    create_session,
    create_trusted_device,
    destroy_all_sessions,
    destroy_session,
    forget_all_devices,
    forget_device,
    generate_recovery_codes,
    hash_ip,
    hash_password,
    needs_rehash,
    new_totp_secret,
    password_problems,
    qr_svg,
    store_recovery_codes,
    token_hash,
    totp_uri,
    trusted_device_valid,
    verify_leerlauf,
    verify_password,
    verify_totp,
)

log = logging.getLogger("scopex.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Nach außen gibt es genau eine Antwort auf jede misslungene Anmeldung.
# Welcher Grund dahintersteckt — falsches Passwort, unbekanntes Konto,
# laufende Abkühlung, gesperrtes oder stillgelegtes Konto — steht
# ausschließlich im Änderungsprotokoll.
ABWEISUNG = "Benutzername, Passwort oder Code stimmt nicht."

# Ab dieser Zahl von Fehlversuchen geht eine Nachricht an den Besitzer.
# Gesperrt wird das Konto dabei nicht, siehe _fehlversuch_merken.
MAX_FAILED = 8


def client_ip(request: Request) -> str | None:
    """Die echte Gegenstelle.

    Verlässlich ist das erst, seit uvicorn die Weiterleitungs-Header nur
    noch Netzen aus `trusted_proxies` glaubt. Vorher durfte jeder Client
    seine Herkunft selbst behaupten — eine Herkunftsprüfung darauf zu
    stützen wäre sinnlos gewesen.
    """
    return request.client.host if request.client else None


def _tor_oeffnen(request: Request, nachweis: dict | None,
                 kennung: str = "") -> None:
    """Herkunft, Drosselung und Rechenaufgabe, bevor etwas geprüft wird.

    Die Reihenfolge ist Absicht: erst das Billigste, dann das Teuerste.
    Eine abgewiesene Herkunft kostet einen Vergleich, kein Argon2.
    """
    adresse = client_ip(request)

    if not gate.herkunft_erlaubt(adresse):
        log.info("Anmeldeversuch aus nicht freigegebenem Netz abgewiesen: %s",
                 adresse)
        raise HTTPException(
            403, "Aus diesem Netz sind keine Anmeldungen freigegeben.")

    if not gate.fenster_frei(adresse):
        raise HTTPException(
            429, "Zu viele Anfragen. Bitte später erneut versuchen.")

    nachweis = nachweis or {}
    if not gate.pow_pruefen(nachweis.get("aufgabe", ""),
                            nachweis.get("stufe", 0),
                            nachweis.get("ablauf", 0),
                            nachweis.get("siegel", ""),
                            str(nachweis.get("loesung", ""))):
        raise HTTPException(
            400, "Die Sicherheitsprüfung ist abgelaufen. Bitte erneut "
                 "versuchen.")


def _melde_neues_geraet(user: dict, request: Request) -> None:
    """Meldet eine gelungene Anmeldung von einem unbekannten Gerät.

    Bisher wurde nur die Sperre gemeldet, also ausschließlich der
    **gescheiterte** Angriff. Der gelungene blieb still. Diese Nachricht
    nennt bewusst weder Adresse noch Ort: sie soll den Besitzer warnen,
    nicht einem Angreifer bestätigen, welche Spur er hinterlässt.
    """
    if not user.get("email"):
        return
    try:
        mailer.send(user["email"], "SCOPE X: Anmeldung von einem neuen Gerät",
                    """\
In deinem SCOPE-X-Konto hat sich gerade jemand von einem Gerät angemeldet,
das bisher nicht als vertrauenswürdig hinterlegt war.

Warst du das selbst, kannst du diese Nachricht übergehen.

Warst du es nicht, ändere dein Passwort und entziehe im Profil allen
Geräten das Vertrauen. Beides beendet sofort alle offenen Sitzungen.
""")
    except Exception as fehler:  # noqa: BLE001
        # Ein stockender Mailversand darf eine gültige Anmeldung nicht
        # scheitern lassen.
        log.warning("Benachrichtigung über neues Gerät nicht zustellbar: %s",
                    fehler)


def _norm(value: str | None) -> str:
    """Anmeldemerkmale werden in Kleinschreibung verglichen. Sonst scheitert
    die Anmeldung an der Autokorrektur des Telefons, die den ersten
    Buchstaben groß schreibt."""
    return (value or "").strip().lower()


def find_login(c, identifier: str) -> dict | None:
    """Sucht ein Konto über Benutzername oder E-Mail-Adresse."""
    return row(c, "SELECT * FROM users WHERE LOWER(username) = :n "
                  "OR LOWER(email) = :n", n=_norm(identifier))


def _is_secure(request: Request) -> bool:
    """Entscheidet ueber das Secure-Flag der Cookies.

    Grundlage ist ausschliesslich request.url.scheme. uvicorn leitet das
    aus X-Forwarded-Proto ab, aber nur fuer Gegenstellen aus
    --forwarded-allow-ips. Den Header selbst zu lesen hiesse, die
    Entscheidung dem Client zu ueberlassen: wer den Container direkt
    erreicht, koennte das Secure-Flag nach Belieben setzen oder
    unterdruecken, und ohne Flag kann ein Sitzungscookie ueber eine
    unverschluesselte Verbindung zum selben Host abfliessen.
    """
    return request.url.scheme == "https"


def _set_device_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        DEVICE_COOKIE, token, max_age=DEVICE_DAYS * 86400, httponly=True,
        samesite="lax", secure=_is_secure(request), path="/")


def _set_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token,
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=_is_secure(request),
        path="/",
    )


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: str | None = None
    password: str
    first_name: str = ""
    last_name: str = ""
    qualification: str = ""
    invite_code: str | None = None
    pow: dict | None = None


def _find_invitation(c, code: str | None) -> dict | None:
    if not code:
        return None
    inv = row(c, "SELECT * FROM invitations WHERE code_hash = :h",
              h=token_hash(code.strip().upper()))
    if not inv or inv["used_at"] or inv["revoked_at"]:
        return None
    if inv["expires_at"] < now_iso():
        return None
    return inv


class LoginIn(BaseModel):
    username: str  # Benutzername oder E-Mail-Adresse
    password: str
    totp_code: str | None = None
    recovery_code: str | None = None
    remember_device: bool = False
    # Die geloeste Rechenaufgabe aus GET /api/auth/challenge.
    pow: dict | None = None


class CodeIn(BaseModel):
    code: str


@router.get("/invitation/{code}")
def check_invitation(code: str):
    """Prueft einen Einladungscode, bevor das Formular ausgefuellt wird.

    Gibt bewusst nur gueltig oder nicht gueltig zurueck, keine Angaben zur
    einladenden Person oder zum Bestand.
    """
    with conn() as c:
        inv = _find_invitation(c, code)
    if not inv:
        raise HTTPException(404, "Diese Einladung ist ungültig oder abgelaufen.")
    return {"valid": True, "role": inv["role"],
            "role_label": ROLE_LABELS.get(inv["role"], inv["role"]),
            "email": inv["email"] or ""}


@router.get("/device")
def device_state(request: Request):
    """Meldet, ob dieses Gerät als vertrauenswürdig hinterlegt ist.

    Verrät nichts, was der Besitzer des Geräts nicht ohnehin weiß, und
    erlaubt der Anmeldemaske, das Code-Feld erst dann einzublenden, wenn es
    wirklich gebraucht wird.
    """
    token = request.cookies.get(DEVICE_COOKIE)
    if not token:
        return {"known": False}
    with conn() as c:
        d = row(c, "SELECT user_id, expires_at FROM trusted_devices "
                   "WHERE token_hash = :h", h=token_hash(token))
        if not d or d["expires_at"] < now_iso():
            return {"known": False}
        u = row(c, "SELECT username FROM users WHERE id = :i AND "
                   "disabled_at IS NULL", i=d["user_id"])
    if not u:
        return {"known": False}
    return {"known": True, "username": u["username"]}


@router.get("/challenge")
def challenge(request: Request, kennung: str = ""):
    """Gibt die Rechenaufgabe aus, die jede Anmeldung begleiten muss.

    Die Schwierigkeit richtet sich nach den bisherigen Fehlversuchen des
    angefragten Kontos. Dass hier eine Kennung übergeben wird, verrät
    nichts: ein unbekanntes Konto bekommt dieselbe Grundstufe wie ein
    bekanntes ohne Fehlversuche, und geantwortet wird immer.
    """
    adresse = client_ip(request)
    if not gate.herkunft_erlaubt(adresse):
        log.info("Aufgabe für nicht freigegebenes Netz verweigert: %s", adresse)
        raise HTTPException(
            403, "Aus diesem Netz sind keine Anmeldungen freigegeben.")
    if not gate.fenster_frei(adresse):
        raise HTTPException(
            429, "Zu viele Anfragen. Bitte später erneut versuchen.")

    fehlversuche = 0
    if kennung:
        with conn() as c:
            user = find_login(c, kennung)
        if user:
            fehlversuche = user["failed_logins"] or 0
    return gate.pow_aufgabe(gate.pow_stufe(fehlversuche))


@router.get("/state")
def auth_state(request: Request):
    with conn() as c:
        user_count = scalar(c, "SELECT COUNT(*) FROM users") or 0
    user = optional_user(request)
    if not user:
        return {"setup_required": user_count == 0, "authenticated": False}
    with conn() as c:
        totp = row(c, "SELECT confirmed_at FROM auth_totp WHERE user_id = :u", u=user["id"])
        profile = row(c, "SELECT * FROM user_profile WHERE user_id = :u", u=user["id"])
    # Bewusst nur die Felder, die die Oberflaeche wirklich braucht. Der
    # Passwort-Hash und andere interne Spalten verlassen den Server nicht.
    return {
        "setup_required": False,
        "authenticated": True,
        "totp_confirmed": bool(totp and totp["confirmed_at"]),
        "user": {"id": user["id"], "username": user["username"],
                 "email": user["email"], "role": user.get("role") or "user"},
        "profile": profile or {},
        "mail_configured": mailer.is_configured(),
    }


@router.post("/register")
def register(data: RegisterIn, request: Request, response: Response):
    _tor_oeffnen(request, data.pow, kennung=_norm(data.username))
    problems = password_problems(
        data.password, kennungen=(data.username, data.email or ""))
    if problems:
        raise HTTPException(400, " ".join(problems))
    with conn() as c:
        existing_accounts = scalar(c, "SELECT COUNT(*) FROM users") or 0
        invitation = None
        role = "admin"
        if existing_accounts:
            # Ab dem zweiten Konto ist eine gueltige Einladung Pflicht. Das
            # ersetzt ein Captcha wirksamer, als ein Captcha es koennte:
            # ohne Code kommt niemand ueberhaupt bis zum Formular.
            invitation = _find_invitation(c, data.invite_code)
            if not invitation:
                raise HTTPException(
                    403, "Für die Registrierung ist eine gültige Einladung nötig.")
            role = invitation["role"]
        email = _norm(data.email) or None
        if email and "@" not in email:
            raise HTTPException(400, "Die E-Mail-Adresse sieht nicht gültig aus.")
        if find_login(c, data.username):
            raise HTTPException(409, "Dieser Benutzername ist bereits vergeben.")
        if email and find_login(c, email):
            raise HTTPException(409, "Diese E-Mail-Adresse ist bereits vergeben.")
        uid = new_id()
        q(c, "INSERT INTO users (id, username, email, password_hash, created_at, "
             "failed_logins, role, invited_by) "
             "VALUES (:i, :n, :e, :p, :t, 0, :r, :ib)",
          i=uid, n=data.username.strip(), e=email,
          p=hash_password(data.password), t=now_iso(), r=role,
          ib=invitation["created_by"] if invitation else None)
        if invitation:
            q(c, "UPDATE invitations SET used_at = :t, used_by = :u WHERE id = :i",
              t=now_iso(), u=uid, i=invitation["id"])
        q(c, "INSERT INTO user_profile (user_id, first_name, last_name, "
             "qualification, created_at) VALUES (:u, :f, :l, :q, :t)",
          u=uid, f=data.first_name.strip(), l=data.last_name.strip(),
          q=data.qualification.strip(), t=now_iso())
        secret = new_totp_secret()
        q(c, "INSERT INTO auth_totp (user_id, secret, created_at) "
             "VALUES (:u, :s, :t)", u=uid, s=secret, t=now_iso())
        audit(c, uid, "users", uid, "create")
    token = create_session(uid)
    _set_cookie(response, request, token)
    account = data.email or data.username
    return {"ok": True, "totp": {
        "secret": secret,
        "uri": totp_uri(secret, account),
        "qr_svg": qr_svg(totp_uri(secret, account)),
    }}


@router.get("/totp/setup")
def totp_setup(request: Request):
    """Liefert QR-Code und Secret erneut, solange die Einrichtung nicht
    bestaetigt ist. Nach der Bestaetigung wird das Secret nie wieder
    ausgegeben."""
    user = current_user(request)
    with conn() as c:
        t = row(c, "SELECT * FROM auth_totp WHERE user_id = :u", u=user["id"])
        if not t:
            secret = new_totp_secret()
            q(c, "INSERT INTO auth_totp (user_id, secret, created_at) "
                 "VALUES (:u, :s, :t)", u=user["id"], s=secret, t=now_iso())
            t = {"secret": secret, "confirmed_at": None}
    if t["confirmed_at"]:
        raise HTTPException(409, "Die Zwei-Faktor-Authentifizierung ist bereits aktiv.")
    account = user["email"] or user["username"]
    return {"secret": t["secret"], "uri": totp_uri(t["secret"], account),
            "qr_svg": qr_svg(totp_uri(t["secret"], account))}


@router.post("/totp/confirm")
def totp_confirm(data: CodeIn, request: Request):
    user = current_user(request)
    with conn() as c:
        t = row(c, "SELECT * FROM auth_totp WHERE user_id = :u", u=user["id"])
        if not t:
            raise HTTPException(400, "Keine Einrichtung begonnen.")
        if t["confirmed_at"]:
            raise HTTPException(409, "Bereits bestätigt.")
        if not verify_totp(t["secret"], data.code):
            raise HTTPException(400, "Der Code stimmt nicht. Prüfe die Uhrzeit des Geräts.")
        q(c, "UPDATE auth_totp SET confirmed_at = :t WHERE user_id = :u",
          t=now_iso(), u=user["id"])
        codes = generate_recovery_codes()
        store_recovery_codes(c, user["id"], codes)
        audit(c, user["id"], "auth_totp", user["id"], "confirm")
    return {"ok": True, "recovery_codes": codes}


@router.post("/recovery/regenerate")
def regenerate_recovery(data: CodeIn, request: Request):
    """Neue Codes erfordern einen frischen TOTP-Code. Alte Codes werden
    dabei ungueltig."""
    user = current_user(request)
    with conn() as c:
        t = row(c, "SELECT * FROM auth_totp WHERE user_id = :u", u=user["id"])
        if not (t and t["confirmed_at"] and verify_totp(t["secret"], data.code)):
            raise HTTPException(400, "Ungültiger Code.")
        codes = generate_recovery_codes()
        store_recovery_codes(c, user["id"], codes)
        audit(c, user["id"], "recovery_codes", user["id"], "regenerate")
    return {"recovery_codes": codes}


@router.get("/recovery/status")
def recovery_status(request: Request):
    user = current_user(request)
    with conn() as c:
        total = scalar(c, "SELECT COUNT(*) FROM recovery_codes WHERE user_id = :u",
                       u=user["id"]) or 0
        unused = scalar(c, "SELECT COUNT(*) FROM recovery_codes "
                           "WHERE user_id = :u AND used_at IS NULL", u=user["id"]) or 0
    return {"total": total, "unused": unused}


def _fehlversuch_merken(user: dict, adresse: str | None) -> dict:
    """Bereitet den Fehlversuch auf und verlängert die Abkühlung.

    Die Abkühlung bremst **diese Adresse** bei diesem Konto, exponentiell
    bis fünfzehn Minuten. Sie ersetzt die frühere kontoweite Sperre nach
    acht Fehlversuchen.

    Warum die Sperre weichen musste: solange SCOPE X nur im eigenen Netz
    erreichbar war, war sie harmlos. Aus dem offenen Netz ist eine Sperre,
    die jeder Fremde mit acht falschen Passwörtern auslöst, keine
    Schutzmaßnahme, sondern eine Waffe — ein Skript hätte alle Nutzer
    dauerhaft aussperren können, mitten im Dienst. Eine Maßnahme, die der
    Angreifer gegen den Besitzer richten kann, schützt niemanden.

    Geblieben ist, was wirklich schützt: der Versuch wird teurer, und zwar
    nur für den, der ihn unternimmt. Geblieben ist auch die
    Benachrichtigung — der Besitzer erfährt weiterhin, dass jemand an
    seinem Konto arbeitet.
    """
    failed = (user["failed_logins"] or 0) + 1
    gate.abkuehlung_setzen(user["id"], adresse, failed)
    return {"user_id": user["id"], "email": user["email"], "failed": failed,
            # Benachrichtigt wird genau beim Überschreiten der Schwelle,
            # nicht bei jedem weiteren Versuch. Sonst ließe sich über das
            # Anmeldeformular ein fremdes Postfach fluten.
            "notify": failed == MAX_FAILED}


def _zaehle_fehlversuch(user: dict, adresse: str | None) -> None:
    _register_failed_login(_fehlversuch_merken(user, adresse))


def _register_failed_login(failure: dict) -> None:
    """Schreibt den Fehlversuch in einer eigenen Transaktion.

    Eigene Transaktion, weil der Zähler sonst zusammen mit der gleich
    folgenden HTTPException zurückgerollt würde. Genau daran ist die
    Kontosperre von Version 1.0.0 bis 3.0.0 wirkungslos geblieben.
    """
    with conn() as c:
        q(c, "UPDATE users SET failed_logins = :f WHERE id = :i",
          f=failure["failed"], i=failure["user_id"])
        audit(c, failure["user_id"], "users", failure["user_id"],
              "login_failed")
    if failure["notify"] and failure["email"]:
        mailer.send(failure["email"], "SCOPE X: Fehlgeschlagene Anmeldeversuche",
            f"""\
Für dein SCOPE-X-Konto wurden {MAX_FAILED} fehlgeschlagene Anmeldeversuche
gezählt.

Dein Konto ist **nicht** gesperrt und bleibt von deinen eigenen Geräten
aus normal benutzbar. Stattdessen wird jeder weitere Versuch von der
Gegenstelle, die es probiert, zunehmend ausgebremst. Eine Sperre des
Kontos selbst gibt es bewusst nicht: sie ließe sich von außen auslösen und
würde dich aussperren, nicht den Angreifer.

Warst du das selbst, melde dich einfach erneut an oder setze dein Passwort
zurück.

Warst du es nicht, kennt jemand deinen Benutzernamen oder deine
E-Mail-Adresse. Dein Passwort und dein zweiter Faktor sind davon nicht
betroffen. Wenn dich das beunruhigt, ändere das Passwort und entziehe im
Profil allen Geräten das Vertrauen.

Diese Nachricht enthält bewusst keine Angaben zu Zeitpunkt oder Herkunft
der Versuche.
""")


@router.post("/login")
def login(data: LoginIn, request: Request, response: Response):
    adresse = client_ip(request)
    _tor_oeffnen(request, data.pow, kennung=_norm(data.username))

    failure = None
    with conn() as c:
        user = find_login(c, data.username)
        if not user:
            # Gleicher Aufwand wie bei einem vorhandenen Konto. Ohne diesen
            # Leerlauf verriete allein die Antwortzeit, welche Namen und
            # Adressen registriert sind.
            verify_leerlauf(data.password)
            raise HTTPException(401, ABWEISUNG)

        # Abkühlung und Sperre gelten nach außen als dieselbe Abweisung wie
        # ein falsches Passwort. Ein abweichender Statuscode hätte sonst
        # verraten, dass es das Konto gibt — und obendrein, dass gerade
        # jemand anderes daran arbeitet.
        if gate.abkuehlung_rest(user["id"], adresse):
            # Der Versuch wird trotzdem gezählt. Sonst käme ein langsamer
            # Angreifer nie bis zur Warnschwelle, und der Besitzer erführe
            # von einem Angriff gar nichts — gezählt wird hier nur, das
            # teure Argon2 bleibt ausgespart.
            verify_leerlauf(data.password)
            _zaehle_fehlversuch(user, adresse)
            raise HTTPException(401, ABWEISUNG)
        if user["lock_until"] and user["lock_until"] > now_iso():
            verify_leerlauf(data.password)
            raise HTTPException(401, ABWEISUNG)
        if user.get("disabled_at"):
            verify_leerlauf(data.password)
            raise HTTPException(401, ABWEISUNG)

        ok = verify_password(data.password, user["password_hash"])
        totp = row(c, "SELECT * FROM auth_totp WHERE user_id = :u", u=user["id"])

        # Ein bekanntes Gerät erspart den Code bei der Anmeldung. Es hebt die
        # Zwei-Faktor-Pflicht nicht auf: Eingriffe in Konten und Daten
        # verlangen weiterhin einen frischen Code.
        device_token = request.cookies.get(DEVICE_COOKIE)
        device_known = ok and trusted_device_valid(user["id"], device_token)

        if ok and totp and totp["confirmed_at"] and not device_known:
            if data.recovery_code:
                ok = consume_recovery_code(c, user["id"], data.recovery_code)
            else:
                ok = verify_totp(totp["secret"], data.totp_code or "")

        if not ok:
            # Der Zähler darf nicht in derselben Transaktion hochgezählt
            # werden, in der anschließend eine HTTPException fliegt: die
            # Exception rollt die Transaktion zurück und die Sperre käme nie
            # zustande. Deshalb hier nur merken, geschrieben wird außerhalb.
            failure = _fehlversuch_merken(user, adresse)
        else:
            # Bestehende scrypt-Hashes werden hier still auf Argon2id gehoben.
            if needs_rehash(user["password_hash"]):
                q(c, "UPDATE users SET password_hash = :p WHERE id = :i",
                  p=hash_password(data.password), i=user["id"])
                audit(c, user["id"], "users", user["id"], "password_rehash")
            q(c, "UPDATE users SET failed_logins = 0, lock_until = NULL, "
                 "last_login_at = :t WHERE id = :i", t=now_iso(), i=user["id"])
            audit(c, user["id"], "users", user["id"], "login")
            totp_confirmed = bool(totp and totp["confirmed_at"])

    if failure:
        _register_failed_login(failure)
        raise HTTPException(401, ABWEISUNG)

    gate.abkuehlung_loeschen(user["id"], adresse)
    token = create_session(user["id"])
    _set_cookie(response, request, token)
    if data.remember_device and totp_confirmed and not device_known:
        label = (request.headers.get("user-agent") or "")[:80]
        _set_device_cookie(response, request,
                           create_trusted_device(user["id"], label))
    if not device_known:
        _melde_neues_geraet(user, request)
    return {"ok": True, "totp_confirmed": totp_confirmed,
            "device_known": device_known}


@router.post("/logout")
def logout(request: Request, response: Response, forget: bool = False):
    destroy_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/")
    if forget:
        forget_device(request.cookies.get(DEVICE_COOKIE))
        response.delete_cookie(DEVICE_COOKIE, path="/")
    return {"ok": True}


@router.get("/devices")
def list_devices(request: Request):
    user = current_user(request)
    current = token_hash(request.cookies.get(DEVICE_COOKIE) or "")
    with conn() as c:
        items = rows(c, "SELECT id, label, created_at, expires_at, "
                        "last_used_at, token_hash FROM trusted_devices "
                        "WHERE user_id = :u ORDER BY last_used_at DESC",
                     u=user["id"])
    for d in items:
        d["current"] = d.pop("token_hash") == current
    return {"devices": items}


@router.delete("/devices")
def revoke_devices(request: Request, response: Response):
    """Entzieht allen Geräten das Vertrauen. Danach ist überall wieder ein
    Code aus der Authenticator-App nötig."""
    user = current_user(request)
    forget_all_devices(user["id"])
    response.delete_cookie(DEVICE_COOKIE, path="/")
    with conn() as c:
        audit(c, user["id"], "trusted_devices", user["id"], "revoke_all")
    return {"ok": True}


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str
    totp_code: str


@router.post("/password")
def change_password(data: PasswordChangeIn, request: Request):
    user = current_user(request)
    problems = password_problems(
        data.new_password,
        kennungen=(user["username"], user.get("email") or ""))
    if problems:
        raise HTTPException(400, " ".join(problems))
    with conn() as c:
        if not verify_password(data.current_password, user["password_hash"]):
            raise HTTPException(400, "Aktuelles Passwort stimmt nicht.")
        t = row(c, "SELECT * FROM auth_totp WHERE user_id = :u", u=user["id"])
        if t and t["confirmed_at"] and not verify_totp(t["secret"], data.totp_code):
            raise HTTPException(400, "Ungültiger Code.")
        q(c, "UPDATE users SET password_hash = :p WHERE id = :i",
          p=hash_password(data.new_password), i=user["id"])
        audit(c, user["id"], "users", user["id"], "password_change")
    destroy_all_sessions(user["id"])
    forget_all_devices(user["id"])
    return {"ok": True}


class EmailChangeIn(BaseModel):
    email: str
    password: str
    totp_code: str


@router.put("/email")
def change_email(data: EmailChangeIn, request: Request):
    """Ändert die E-Mail-Adresse.

    Sie ist ein Anmeldemerkmal, deshalb gilt hier dieselbe Hürde wie beim
    Passwortwechsel: aktuelles Passwort plus ein frischer Code.
    """
    user = current_user(request)
    email = _norm(data.email)
    if email and "@" not in email:
        raise HTTPException(400, "Die E-Mail-Adresse sieht nicht gültig aus.")
    with conn() as c:
        if not verify_password(data.password, user["password_hash"]):
            raise HTTPException(400, "Passwort stimmt nicht.")
        t = row(c, "SELECT * FROM auth_totp WHERE user_id = :u", u=user["id"])
        if t and t["confirmed_at"] and not verify_totp(t["secret"], data.totp_code):
            raise HTTPException(400, "Ungültiger Code.")
        existing = find_login(c, email) if email else None
        if existing and existing["id"] != user["id"]:
            raise HTTPException(409, "Diese Adresse gehört bereits zu einem Konto.")
        q(c, "UPDATE users SET email = :e WHERE id = :i",
          e=email or None, i=user["id"])
        audit(c, user["id"], "users", user["id"], "email_change")
    return {"ok": True, "email": email or None}


# --------------------------------------------------------------------------
# Passwort zurücksetzen
# --------------------------------------------------------------------------
# Der Link allein reicht nicht. Zum Setzen eines neuen Passworts ist
# zusätzlich der zweite Faktor nötig, sonst wäre ein Zugriff auf das
# Postfach gleichbedeutend mit einer Kontoübernahme.

RESET_MINUTES = 30


class ResetRequestIn(BaseModel):
    identifier: str
    pow: dict | None = None


class ResetConfirmIn(BaseModel):
    token: str
    new_password: str
    totp_code: str | None = None
    recovery_code: str | None = None


@router.post("/password-reset/request")
def request_reset(data: ResetRequestIn, request: Request):
    """Fordert einen Reset-Link an.

    Antwortet immer gleich, unabhängig davon, ob es das Konto gibt. Sonst
    ließe sich über dieses Formular herausfinden, welche Adressen registriert
    sind.
    """
    _tor_oeffnen(request, data.pow, kennung=_norm(data.identifier))
    ip_hash = hash_ip(client_ip(request))
    with conn() as c:
        user = find_login(c, data.identifier)
        if user and user["email"] and not user.get("disabled_at"):
            recent = scalar(c, "SELECT COUNT(*) FROM password_resets "
                               "WHERE user_id = :u AND created_at > :t",
                            u=user["id"],
                            t=(datetime.now(timezone.utc)
                               - timedelta(minutes=10))
                              .replace(microsecond=0).isoformat()) or 0
            if recent < 3:
                token = secrets.token_urlsafe(32)
                expires = (datetime.now(timezone.utc)
                           + timedelta(minutes=RESET_MINUTES))
                q(c, "INSERT INTO password_resets (id, user_id, token_hash, "
                     "created_at, expires_at, requested_ip_hash) "
                     "VALUES (:i, :u, :h, :c, :e, :ip)",
                  i=new_id(), u=user["id"], h=token_hash(token),
                  c=now_iso(), e=expires.replace(microsecond=0).isoformat(),
                  ip=ip_hash)
                audit(c, user["id"], "password_resets", user["id"], "request")
                mailer.send_reset(user["email"], token)
    return {"ok": True, "detail": "Wenn ein Konto existiert, ist eine "
                                  "Nachricht unterwegs."}


@router.post("/password-reset/confirm")
def confirm_reset(data: ResetConfirmIn, request: Request):
    with conn() as c:
        rec = row(c, "SELECT * FROM password_resets WHERE token_hash = :h",
                  h=token_hash(data.token))
        if not rec or rec["used_at"] or rec["expires_at"] < now_iso():
            raise HTTPException(400, "Dieser Link ist ungültig oder abgelaufen.")
        user = row(c, "SELECT * FROM users WHERE id = :u", u=rec["user_id"])
        if not user or user.get("disabled_at"):
            raise HTTPException(400, "Dieser Link ist ungültig oder abgelaufen.")

        # Erst hier, weil die Pruefung den Benutzernamen braucht: ein
        # Passwort, das den eigenen Namen enthaelt, ist fuer jemanden,
        # der ihn kennt, kein Passwort.
        problems = password_problems(
            data.new_password,
            kennungen=(user["username"], user.get("email") or ""))
        if problems:
            raise HTTPException(400, " ".join(problems))

        t = row(c, "SELECT * FROM auth_totp WHERE user_id = :u", u=user["id"])
        if t and t["confirmed_at"]:
            if data.recovery_code:
                second = consume_recovery_code(c, user["id"], data.recovery_code)
            else:
                second = verify_totp(t["secret"], data.totp_code or "")
            if not second:
                raise HTTPException(
                    400, "Zusätzlich ist ein Code aus deiner Authenticator-App "
                         "oder ein Wiederherstellungscode nötig.")

        q(c, "UPDATE users SET password_hash = :p, failed_logins = 0, "
             "lock_until = NULL WHERE id = :i",
          p=hash_password(data.new_password), i=user["id"])
        q(c, "UPDATE password_resets SET used_at = :t WHERE id = :i",
          t=now_iso(), i=rec["id"])
        q(c, "UPDATE password_resets SET used_at = :t "
             "WHERE user_id = :u AND used_at IS NULL",
          t=now_iso(), u=user["id"])
        audit(c, user["id"], "users", user["id"], "password_reset")

    # Nach einer Zurücksetzung gilt kein Gerät mehr als vertrauenswürdig.
    destroy_all_sessions(user["id"])
    forget_all_devices(user["id"])
    # Und die Abkühlung fällt weg. Sonst bliebe genau die Person draußen,
    # die ein Fremder mit Fehlversuchen ausgebremst hat — also der Fall,
    # für den die Zurücksetzung gedacht ist.
    gate.abkuehlung_konto_freigeben(user["id"])
    return {"ok": True}
