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
                # Seit 4.4.0 ist "#/" der Kompetenzfeed; die Einsatzliste
                # hat eine eigene Adresse, dazu Kontakte und Mitteilungen.
                for route in ["#/", "#/entdecken", "#/nachrichten",
                              "#/mitteilungen", "#/einsaetze", "#/dashboard",
                              "#/nachweise", "#/profil", "#/einstellungen",
                              "#/administration", "#/rechtliches",
                              "#/netzwerk", "#/suche", "#/suche?q=reanimation",
                              "#/themen", "#/gespeichert", "#/fortbildung",
                              "#/nutzungsbedingungen", "#/ueber"]:
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

                    # Erreichbarkeit des Seitenendes. Von 4.1.0 bis 4.3.0
                    # lag der Inhalt auf Mobilgeräten unter der Leiste und
                    # das Ende ließ sich nicht erreichen — kein axe-Befund,
                    # aber für die Bedienung ein Totalausfall. Gemessen bei
                    # maximaler Scrolltiefe: das letzte sichtbare Element
                    # muss oberhalb der Leiste enden.
                    verdeckt = page.evaluate("""() => {
                      const app = document.getElementById('app');
                      const nav = document.getElementById('nav');
                      if (!nav || nav.hidden) return 0;
                      app.scrollTop = app.scrollHeight;
                      let unten = 0;
                      for (const e of app.querySelectorAll('*')) {
                        if (!e.offsetParent) continue;
                        // Inhalt geschlossener Aufklappbereiche hat in
                        // Chromium ein Layout, ist aber nicht zu sehen.
                        const zu = e.closest('details:not([open])');
                        if (zu && !e.closest('summary')) continue;
                        unten = Math.max(unten, e.getBoundingClientRect().bottom);
                      }
                      return Math.round(unten - nav.getBoundingClientRect().top);
                    }""")
                    if verdeckt > 0:
                        problems.append(f"{route} Seitenende {verdeckt}px "
                                        "unter der Navigationsleiste")

                # Dunkelmodus: seit 4.7.0 haben die Signalfarben eigene
                # Werte für dunklen Grund (Markenhandbuch, Kapitel 02).
                # Geprüft wird der Kontrast auf den Seiten mit den meisten
                # Status- und Kategoriefarben.
                for route in ["#/", "#/einsaetze", "#/dashboard", "#/profil",
                              "#/administration", "#/ueber"]:
                    page.goto(f"http://127.0.0.1:8199/{route}",
                              wait_until="networkidle")
                    page.evaluate("document.documentElement.dataset.theme = 'dark'")
                    page.wait_for_timeout(500)
                    page.evaluate(axe_source)
                    result = page.evaluate(
                        "async () => await axe.run(document, {resultTypes:"
                        "['violations'], runOnly: ['color-contrast']})")
                    for v in result["violations"]:
                        if v["impact"] in SEVERITIES:
                            problems.append(f"dunkel {route} {v['id']} "
                                            f"({len(v['nodes'])}x)")
                browser.close()
        finally:
            server.should_exit = True
            thread.join(timeout=5)
    return problems
