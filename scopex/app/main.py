"""SCOPE X - Anwendungseinstieg."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    PlainTextResponse,
)
from fastapi.staticfiles import StaticFiles

from .core import base_url, sweep_locks
from .db import conn, migrate, normalize_legacy_outcomes, q
from .routers import (
    admin,
    auth,
    beitraege,
    catalog,
    exports,
    kataloge,
    nachrichten,
    netz,
    netzwerk,
    passkeys,
    profile,
    records,
    stats,
    zugang,
)
from . import kataloge as katalogdaten
from .seed import seed_if_empty

log = logging.getLogger("scopex")
STATIC_DIR = Path(__file__).parent / "static"

# Muss mit "version" in config.yaml übereinstimmen. Die Prüfschleife
# vergleicht beide; sie stand hier seit der Erstfassung auf 1.0.0, weil
# nichts den Abgleich erzwang.
APP_VERSION = "4.4.0"


@asynccontextmanager
async def lifespan(_: FastAPI):
    applied = migrate()
    if applied:
        log.info("Migrationen angewendet: %s", ", ".join(applied))
    converted = normalize_legacy_outcomes()
    if converted:
        log.info("%s Einträge von 'frustran' auf 'fehlgeschlagen' abgebildet, "
                 "jeweils im Änderungsprotokoll vermerkt.", converted)
    with conn() as c:
        if seed_if_empty(c):
            log.info("Stammdaten eingespielt.")
        neu = katalogdaten.einspielen(c)
        if neu:
            log.info("%s Katalogeinträge ergänzt.", neu)
        zugang.aufraeumen(c)
        # Videos, deren Verarbeitung ein Neustart unterbrochen hat, kommen
        # nie mehr fertig; ohne diesen Schritt bliebe der Upload ewig
        # „in Verarbeitung“.
        q(c, "UPDATE net_media SET status = 'fehler:Verarbeitung durch Neustart "
             "unterbrochen.' WHERE status = 'verarbeitung'")
        locked = sweep_locks(c)
        if locked:
            log.info("%s Einträge nach Ablauf der Frist gesperrt.", locked)
    yield


app = FastAPI(
    title="SCOPE X",
    description="Das Maßnahmen- und Kompetenzlogbuch für den Rettungsdienst",
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = (
        "geolocation=(), microphone=(), camera=(), interest-cohort=()")
    # Keine externen Quellen. Wenn die Seite etwas nachladen will, das hier
    # nicht steht, ist das ein Fehler und kein Feature.
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
        "form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
    # request.url.scheme, nicht der Rohheader: uvicorn setzt das Schema aus
    # X-Forwarded-Proto nur dann, wenn die Gegenstelle in
    # --forwarded-allow-ips steht. Den Header hier selbst zu lesen hiesse,
    # jedem Client zu glauben, der den Container direkt erreicht.
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains")
    return response


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(passkeys.router)
app.include_router(catalog.router)
app.include_router(records.router)
app.include_router(stats.router)
app.include_router(profile.router)
app.include_router(exports.router)
app.include_router(netz.router)
app.include_router(beitraege.router)
app.include_router(nachrichten.router)
app.include_router(kataloge.router)
app.include_router(zugang.router)
app.include_router(netzwerk.router)


@app.get("/api/health")
def health():
    """Lebenszeichen für die Betriebsüberwachung.

    Bewusst ohne Anmeldung und ohne jede Angabe über Bestand oder
    Zustand der Daten: ein Überwachungsendpunkt, der verrät, wie viele
    Konten es gibt, ist ein Auskunftsdienst für Fremde.
    """
    return {"status": "ok", "app": "SCOPE X", "version": APP_VERSION}


@app.get("/robots.txt", include_in_schema=False)
def robots():
    """Ein persönliches Logbuch gehört in keinen Suchindex.

    Das hält keinen Angreifer auf — wohl aber die Suchmaschinen, die
    sonst Anmeldeseite und Impressum indexieren und damit erst sichtbar
    machen, dass es diesen Dienst gibt.
    """
    return PlainTextResponse("User-agent: *\nDisallow: /\n")


@app.get("/.well-known/security.txt", include_in_schema=False)
def security_txt():
    """Anlaufstelle für Sicherheitsmeldungen nach RFC 9116.

    Im Protokoll war zu sehen, dass diese Datei tatsächlich abgefragt
    wird. Wer eine Schwachstelle findet, soll eine Adresse vorfinden
    statt eines 404.
    """
    kontakt = os.environ.get("SCOPEX_KONTAKT", "").strip()
    basis = base_url()
    zeilen = [f"Contact: mailto:{kontakt}" if kontakt else "Contact: /#/rechtliches",
              "Preferred-Languages: de, en"]
    if basis:
        zeilen.append(f"Canonical: {basis}/.well-known/security.txt")
    zeilen.append("# SCOPE X ist ein privates Projekt ohne Prämienprogramm.")
    return PlainTextResponse("\n".join(zeilen) + "\n")


app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


@app.get("/{full_path:path}")
def spa(full_path: str):
    """Liefert die Anwendung aus, aber nur unter der Wurzel.

    Die Oberflaeche navigiert ausschliesslich ueber den Fragmentteil
    (#/dashboard, #/neu). Ein Fragment erreicht den Server nie, Assets
    liegen unter /assets. Der Server braucht also genau einen Pfad: '/'.

    Vorher beantwortete dieser Catch-all jeden Pfad mit 200 und der SPA.
    Scans nach /.git/config, /wp-login.php oder /.env bekamen damit eine
    Erfolgsmeldung und sahen aus wie Treffer, echte Fehler verschwanden
    zwischen falschen 200ern, und jeder Scantreffer lud die vollstaendige
    Oberflaeche aus. Ein 404 ist hier die wahre Antwort.
    """
    if full_path in ("", "/"):
        return FileResponse(STATIC_DIR / "index.html")
    return JSONResponse({"detail": "Nicht gefunden."}, status_code=404)
