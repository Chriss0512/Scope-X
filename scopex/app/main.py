"""SCOPE X - Anwendungseinstieg."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .core import sweep_locks
from .db import conn, migrate, normalize_legacy_outcomes
from .routers import (
    admin,
    auth,
    catalog,
    exports,
    passkeys,
    profile,
    records,
    stats,
)
from .seed import seed_if_empty

log = logging.getLogger("scopex")
STATIC_DIR = Path(__file__).parent / "static"

# Muss mit "version" in config.yaml übereinstimmen. Die Prüfschleife
# vergleicht beide; sie stand hier seit der Erstfassung auf 1.0.0, weil
# nichts den Abgleich erzwang.
APP_VERSION = "4.2.0"


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


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "SCOPE X"}


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
