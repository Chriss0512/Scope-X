"""Automatisierte Barrierefreiheitsprüfung.

Fährt die Anwendung in einem echten Browser hoch und prüft mit axe-core.
Ist kein Browser verfügbar, wird die Prüfung übersprungen statt still zu
bestehen.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AXE = Path(__file__).parent / "vendor" / "axe.min.js"

# Regeln, die für eine angemeldete Einzelplatzanwendung relevant sind.
SEVERITIES = {"critical", "serious"}


def audit() -> list[str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        from .run_quality import SkipCheck
        raise SkipCheck("playwright nicht installiert") from exc
    if not AXE.exists():
        from .run_quality import SkipCheck
        raise SkipCheck("axe-core fehlt unter quality/vendor/axe.min.js")

    import uvicorn

    from .harness import seeded_client

    problems: list[str] = []
    with seeded_client() as (client, ctx):
        import app.main as main
        from app.db import conn, row
        from app.security import create_session
        with conn() as c:
            uid = row(c, "SELECT id FROM users")["id"]
        token = create_session(uid)

        config = uvicorn.Config(main.app, host="127.0.0.1", port=8199,
                                log_level="error")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        for _ in range(50):
            if server.started:
                break
            time.sleep(0.1)

        axe_source = AXE.read_text(encoding="utf-8")
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page_ctx = browser.new_context(viewport={"width": 414, "height": 896})
                page_ctx.add_cookies([{"name": "scopex_session", "value": token,
                                       "domain": "127.0.0.1", "path": "/"}])
                page = page_ctx.new_page()
                for route in ["#/", "#/neu", "#/dashboard", "#/nachweise",
                              "#/profil", "#/rechtliches"]:
                    page.goto(f"http://127.0.0.1:8199/{route}",
                              wait_until="networkidle")
                    page.wait_for_timeout(900)
                    page.evaluate(axe_source)
                    result = page.evaluate(
                        "async () => await axe.run(document, "
                        "{resultTypes:['violations']})")
                    for v in result["violations"]:
                        if v["impact"] in SEVERITIES:
                            problems.append(f"{route} {v['id']} "
                                            f"({len(v['nodes'])}x)")
                browser.close()
        finally:
            server.should_exit = True
            thread.join(timeout=5)
    return problems
