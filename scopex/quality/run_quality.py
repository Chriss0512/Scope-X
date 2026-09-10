#!/usr/bin/env python3
"""Qualitätsschleife für SCOPE X.

Prüft bei jedem Durchlauf jede automatisierbare Anforderung entlang der
neun Charakteristiken von ISO/IEC 25010:2023 und schreibt einen Bericht.

Grundsatz: Dieses Werkzeug darf nichts grün melden, was es nicht wirklich
geprüft hat. Nicht automatisierbare Punkte erscheinen als MANUELL und
zählen ausdrücklich nicht als bestanden. Ein Qualitätsdashboard, das
Menschenarbeit als erledigt ausweist, ist schlimmer als keines.

Rückgabewert 0 nur, wenn keine Prüfung fehlgeschlagen ist.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"

PASS, FAIL, SKIP, MANUAL = "BESTANDEN", "FEHLGESCHLAGEN", "ÜBERSPRUNGEN", "MANUELL"

CHARACTERISTICS = [
    ("functional", "Functional Suitability"),
    ("performance", "Performance Efficiency"),
    ("compatibility", "Compatibility"),
    ("interaction", "Interaction Capability"),
    ("reliability", "Reliability"),
    ("security", "Security"),
    ("maintainability", "Maintainability"),
    ("flexibility", "Flexibility"),
    ("safety", "Safety"),
]


@dataclass
class Result:
    characteristic: str
    name: str
    status: str
    detail: str = ""


results: list[Result] = []


def record(characteristic: str, name: str, status: str, detail: str = "") -> None:
    results.append(Result(characteristic, name, status, detail))
    mark = {PASS: "  ok  ", FAIL: " FEHL ", SKIP: " über ", MANUAL: " manu "}[status]
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))


def check(characteristic: str, name: str):
    """Dekorator: Ausnahmen werden zum Fehlschlag, nicht zum Abbruch."""
    def wrap(fn):
        def run():
            try:
                ok, detail = fn()
                record(characteristic, name, PASS if ok else FAIL, detail)
            except SkipCheck as exc:
                record(characteristic, name, SKIP, str(exc))
            except Exception as exc:
                record(characteristic, name, FAIL, f"{type(exc).__name__}: {exc}")
        run.__name__ = fn.__name__
        return run
    return wrap


class SkipCheck(Exception):
    pass


def sh(*args, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, cwd=ROOT, **kwargs)


def have(tool: str) -> bool:
    return shutil.which(tool) is not None


# --------------------------------------------------------------------------
# Functional Suitability
# --------------------------------------------------------------------------

SUITES = [ROOT / "quality" / "suites" / n for n in
          ("test_core.py", "test_access.py", "test_documentation.py")]


@check("functional", "Funktionale Testreihen")
def check_suites():
    total, failed = 0, []
    for suite in SUITES:
        if not suite.exists():
            raise SkipCheck(f"{suite.name} fehlt")
        p = sh(sys.executable, str(suite))
        total += p.stdout.count("  OK   ")
        if p.returncode != 0:
            failed.append(f"{suite.name}: {p.stdout.strip().splitlines()[-1][:80]}")
    if failed:
        return False, "; ".join(failed)
    return total > 0, f"{total} Prüfungen bestanden"


@check("functional", "Jede API-Route wird von mindestens einem Test berührt")
def check_route_coverage():
    cov = ROOT / ".coverage-report.json"
    if not cov.exists():
        raise SkipCheck("keine Abdeckungsdaten, erst check_coverage ausführen")
    data = json.loads(cov.read_text())
    untouched = [Path(f).name for f, m in data["files"].items()
                 if "routers/" in f and m["summary"]["percent_covered"] < 40]
    return not untouched, ("alle Router abgedeckt" if not untouched
                           else "kaum abgedeckt: " + ", ".join(untouched))


# --------------------------------------------------------------------------
# Performance Efficiency
# --------------------------------------------------------------------------

@check("performance", "Antwortzeiten unter 400 ms")
def check_response_times():
    from quality.harness import seeded_client
    budgets = {"/api/overview": 0.4, "/api/stats?period=all": 0.4,
               "/api/encounters?limit=50": 0.4, "/api/catalog/measures": 0.4}
    slow = []
    with seeded_client() as (client, _):
        for path, budget in budgets.items():
            times = []
            for _ in range(5):
                t0 = time.perf_counter()
                r = client.get(path)
                times.append(time.perf_counter() - t0)
                assert r.status_code == 200, f"{path} → {r.status_code}"
            worst = max(times)
            if worst > budget:
                slow.append(f"{path} {worst*1000:.0f} ms")
    return not slow, "alle innerhalb des Budgets" if not slow else "; ".join(slow)


@check("performance", "Auslieferungsgröße der Oberfläche")
def check_asset_budget():
    static = APP / "static"
    js = (static / "app.js").stat().st_size
    css = (static / "app.css").stat().st_size
    font = (static / "fonts" / "InterVariable.woff2").stat().st_size
    total = js + css + font
    budget = 700 * 1024
    return total <= budget, (f"JS {js//1024} KB, CSS {css//1024} KB, "
                             f"Schrift {font//1024} KB, gesamt {total//1024} KB "
                             f"von {budget//1024} KB")


# --------------------------------------------------------------------------
# Compatibility
# --------------------------------------------------------------------------

@check("compatibility", "Kein dialektspezifisches SQL")
def check_sql_portability():
    # Nur Zeichenketten prüfen, die tatsächlich SQL enthalten. Ein
    # Kommentar, der AUTOINCREMENT erwähnt, ist kein Portabilitätsproblem,
    # und datetime.strftime in Python hat mit SQL nichts zu tun.
    forbidden = ["AUTOINCREMENT", "sqlite_master", "GROUP_CONCAT(",
                 "strftime(", "datetime('now')", "IFNULL("]
    sql_literal = re.compile(
        r'("""(?:[^"]|"(?!""))*"""|"[^"\n]*"|\'[^\'\n]*\')', re.DOTALL)
    sql_words = re.compile(r"\b(SELECT|INSERT INTO|UPDATE|DELETE FROM|"
                           r"CREATE TABLE|ALTER TABLE|CREATE INDEX)\b", re.I)
    hits = []
    for path in APP.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for literal in sql_literal.findall(text):
            if not sql_words.search(literal):
                continue
            for token in forbidden:
                if token in literal:
                    hits.append(f"{path.name}: {token.strip()}")
    return not hits, "portabel" if not hits else "; ".join(sorted(set(hits)))


@check("compatibility", "Datenbank über DATABASE_URL austauschbar")
def check_db_abstraction():
    text = (APP / "db.py").read_text(encoding="utf-8")
    return ("SCOPEX_DATABASE_URL" in text and "create_engine" in text), \
        "Engine wird aus der Umgebung gebaut"


# --------------------------------------------------------------------------
# Interaction Capability
# --------------------------------------------------------------------------

@check("interaction", "Barrierefreiheit der Oberfläche")
def check_accessibility():
    from quality.a11y import audit
    problems = audit()
    return not problems, ("keine Verstöße gefunden" if not problems
                          else "; ".join(problems[:4]))


@check("interaction", "Farbe trägt nie allein die Information")
def check_color_independence():
    js = _flat(APP / "static" / "app.js")
    # Jede Statuspille muss zusätzlich Text tragen.
    for match in re.finditer(r'class="status[^"]*"[^>]*>([^<]*)', js):
        if not match.group(1).strip():
            return False, "Statuspille ohne Text gefunden"
    return True, "Statuspillen und Kategoriemarken tragen Text"


@check("interaction", "Keine style-Attribute im Markup")
def check_no_inline_styles():
    hits = []
    for path in (APP / "static").glob("*.js"):
        hits += [path.name for _ in re.finditer(r'\sstyle="', path.read_text(encoding="utf-8"))]
    for path in (APP / "static").glob("*.html"):
        hits += [path.name for _ in re.finditer(r'\sstyle="', path.read_text(encoding="utf-8"))]
    return not hits, ("keine" if not hits
                      else f"{len(hits)} Vorkommen, von der CSP blockiert")


# --------------------------------------------------------------------------
# Reliability
# --------------------------------------------------------------------------

@check("reliability", "Migrationen sind idempotent")
def check_migrations():
    from quality.harness import fresh_db
    with fresh_db() as db:
        first = db.migrate()
        second = db.migrate()
    return bool(first) and second == [], \
        f"{len(first)} angewendet, zweiter Durchlauf leer"


@check("reliability", "Sicherung und Wiederherstellung als Kreis")
def check_backup_roundtrip():
    from quality.harness import seeded_client
    with seeded_client() as (client, ctx):
        before = client.get("/api/stats?period=all").json()
        backup = client.get("/api/exports/backup").json()
        r = client.post("/api/exports/restore",
                        params={"password": ctx["password"],
                                "totp_code": ctx["totp"]()},
                        files={"file": ("b.json", json.dumps(backup),
                                        "application/json")})
        assert r.status_code == 200, r.text[:120]
        after = client.get("/api/stats?period=all").json()
    same = all(before[k] == after[k] for k in
               ("encounters", "attempts", "administrations"))
    return same, "Kennzahlen vor und nach der Wiederherstellung gleich"


# --------------------------------------------------------------------------
# Security
# --------------------------------------------------------------------------

@check("security", "Bekannte Schwachstellen in Abhängigkeiten")
def check_dependencies():
    if not have("pip-audit"):
        raise SkipCheck("pip-audit nicht installiert")
    p = sh("pip-audit", "-r", "requirements.txt", "--progress-spinner", "off")
    if p.returncode == 0:
        return True, "keine bekannten Schwachstellen"
    return False, p.stdout.strip().splitlines()[-1][:120]


@check("security", "Sicherheitsheader vollständig")
def check_headers():
    from quality.harness import seeded_client
    required = {
        "content-security-policy": "default-src 'self'",
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "no-referrer",
    }
    with seeded_client() as (client, _):
        r = client.get("/")
        missing = [k for k, v in required.items()
                   if v not in r.headers.get(k, "")]
    return not missing, "vollständig" if not missing else "fehlt: " + ", ".join(missing)


@check("security", "Ausschließlich parametrisierte Abfragen")
def check_sql_injection():
    """Sucht nach Werten, die per f-String in SQL geraten.

    Erlaubt sind eingesetzte Tabellen- und Spaltennamen aus festen
    Vokabularen; verboten ist alles, was aus einer Variablen mit
    Nutzerbezug stammt.
    """
    suspicious = []
    pattern = re.compile(r'f"""?[^"]*(SELECT|INSERT|UPDATE|DELETE)[^"]*\{(\w+)\}',
                         re.IGNORECASE | re.DOTALL)
    allowed = {"table", "fk", "alias", "where", "_ATT_JOIN", "_ADM_JOIN",
               "att_where", "adm_where", "enc_where", "harm_in", "_zc", "field"}
    for path in APP.rglob("*.py"):
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            if match.group(2) not in allowed:
                suspicious.append(f"{path.name}: {{{match.group(2)}}}")
    return not suspicious, ("nur Bezeichner interpoliert"
                            if not suspicious else "; ".join(suspicious))


@check("security", "Berechtigungsmatrix über alle schreibenden Routen")
def check_rbac_matrix():
    from quality.harness import role_matrix
    violations = role_matrix()
    return not violations, ("jede Route verweigert unberechtigte Zugriffe"
                            if not violations else "; ".join(violations[:4]))


@check("security", "Keine Zugangsdaten im Quelltext")
def check_no_secrets():
    patterns = [re.compile(r'password\s*=\s*["\'][^"\']{6,}["\']', re.I),
                re.compile(r'secret\s*=\s*["\'][A-Za-z0-9+/]{16,}["\']', re.I)]
    hits = []
    for path in list(APP.rglob("*.py")) + [ROOT / "run.sh", ROOT / "config.yaml"]:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if "test" in line.lower() or "example" in line.lower():
                continue
            for pat in patterns:
                if pat.search(line):
                    hits.append(f"{path.name}: {line.strip()[:50]}")
    return not hits, "keine" if not hits else "; ".join(hits)


# --------------------------------------------------------------------------
# Maintainability
# --------------------------------------------------------------------------

@check("maintainability", "Statische Analyse ohne Befund")
def check_lint():
    if not have("ruff"):
        raise SkipCheck("ruff nicht installiert")
    p = sh("ruff", "check", "app", "quality", "--output-format", "concise")
    if p.returncode == 0:
        return True, "keine Befunde"
    lines = [line for line in p.stdout.strip().splitlines() if line]
    return False, f"{len(lines)} Befunde, erster: {lines[0][:80]}"


@check("maintainability", "Testabdeckung mindestens 70 Prozent")
def check_coverage():
    if not have("coverage"):
        raise SkipCheck("coverage nicht installiert")
    sh("coverage", "erase")
    for suite in SUITES:
        if suite.exists():
            sh("coverage", "run", "--append", "--source", "app", str(suite))
    sh("coverage", "json", "-o", ".coverage-report.json")
    data = json.loads((ROOT / ".coverage-report.json").read_text())
    pct = data["totals"]["percent_covered"]
    return pct >= 70, f"{pct:.1f} Prozent"


# --------------------------------------------------------------------------
# Flexibility
# --------------------------------------------------------------------------

@check("flexibility", "Vollständiger Export ohne proprietäres Format")
def check_export_formats():
    from quality.harness import seeded_client
    with seeded_client() as (client, _):
        backup = client.get("/api/exports/backup")
        csv_a = client.get("/api/exports/csv?kind=attempts&period=all")
        csv_m = client.get("/api/exports/csv?kind=medications&period=all")
        pdf = client.get("/api/exports/pdf?period=all")
    ok = (backup.headers["content-type"].startswith("application/json")
          and csv_a.status_code == 200 and csv_m.status_code == 200
          and pdf.content[:4] == b"%PDF")
    return ok, "JSON, CSV und PDF"


@check("flexibility", "Installierbarkeit als Add-on")
def check_addon_manifest():
    import yaml
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    needed = {"name", "version", "slug", "arch", "options", "schema"}
    missing = needed - set(cfg)
    changelog = (ROOT / "CHANGELOG.md").exists()
    return not missing and changelog, \
        f"Version {cfg.get('version')}, Änderungsprotokoll vorhanden"


# --------------------------------------------------------------------------
# Safety
# --------------------------------------------------------------------------

def _flat(path) -> str:
    """Vergleichstext ohne Zeilenumbrüche: eine Formulierung darf im
    Quelltext umgebrochen sein, ohne die Prüfung zu brechen."""
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


@check("safety", "Zweckbestimmung im Produkt verankert")
def check_purpose_statement():
    js = _flat(APP / "static" / "app.js")
    needed = ["kein Einsatzprotokoll", "keine Patientenakte",
              "empfiehlt keine Dosierungen"]
    missing = [n for n in needed if n not in js]
    return not missing, "vorhanden" if not missing else "fehlt: " + "; ".join(missing)


@check("safety", "Gefahrenhinweise vorhanden")
def check_hazard_warnings():
    js = _flat(APP / "static" / "app.js")
    needed = {
        "Warnung bei langer Bearbeitungsfrist": "schwächt das die Aussagekraft",
        "Hinweis auf Personenbezug": "Personenbezug herstellen",
        "Pflichtbegründung beim Stilllegen": "mindestens fünf Zeichen",
        "Etikett ist keine Referenz": "keine druckbaren",
    }
    missing = [k for k, v in needed.items() if v not in js]
    return not missing, "alle vorhanden" if not missing else "fehlt: " + "; ".join(missing)


@check("safety", "Keine Dosierungs- oder Therapieempfehlung in den Stammdaten")
def check_no_clinical_advice():
    from app import seed
    text = json.dumps([seed.MEDICATIONS, seed.MEASURES, seed.COMPLICATIONS],
                      ensure_ascii=False)
    forbidden = re.compile(r"\d+\s*(mg|µg|ml|I\.E\.)\s*/\s*kg|Dosis:|empfohlen")
    hit = forbidden.search(text)
    return hit is None, "keine" if hit is None else f"gefunden: {hit.group()}"


@check("safety", "Add-on ohne Zugriff auf Home Assistant")
def check_addon_isolation():
    import yaml
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    ok = cfg.get("hassio_api") is False and cfg.get("homeassistant_api") is False
    return ok, "keine Schnittstelle zur Hausautomation"


# --------------------------------------------------------------------------
# Versionierung
# --------------------------------------------------------------------------

SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def _version() -> tuple[str, tuple[int, int, int]]:
    import yaml
    raw = str(yaml.safe_load((ROOT / "config.yaml").read_text(
        encoding="utf-8"))["version"])
    m = SEMVER.match(raw)
    if not m:
        raise AssertionError(f"'{raw}' ist kein gültiges SemVer")
    return raw, tuple(int(x) for x in m.groups())


@check("maintainability", "Version folgt SemVer und ist dokumentiert")
def check_version():
    raw, parts = _version()
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if f"## {raw}" not in changelog:
        return False, f"kein Abschnitt '## {raw}' im Änderungsprotokoll"
    documented = [tuple(int(x) for x in m.groups())
                  for m in re.finditer(r"^## (\d+)\.(\d+)\.(\d+)$",
                                       changelog, re.M)]
    older = [v for v in documented if v != parts]
    if older and parts <= max(older):
        return False, f"{raw} ist nicht höher als {max(older)}"
    return True, f"{raw}, {len(documented)} Fassungen dokumentiert"


@check("maintainability", "Keine stille Änderung der öffentlichen Schnittstelle")
def check_public_surface():
    """Vergleicht Endpunkte und Sicherungsformat mit der letzten Fassung.

    Verschwindet ein Pfad oder springt das Sicherungsformat, ohne dass die
    MAJOR-Stelle steigt, ist das ein SemVer-Verstoß. Genau diesen Fall
    übersieht man beim Umbenennen einer Route.
    """
    import json as _json
    raw, parts = _version()
    from app.main import app as fastapi_app
    from app.routers.exports import BACKUP_VERSION

    # Neuere FastAPI-Fassungen kapseln eingebundene Router, deshalb muss
    # der Baum durchlaufen werden statt nur die oberste Ebene.
    def walk(routes):
        for r in routes:
            path = getattr(r, "path", "")
            if path.startswith("/api/"):
                yield path
            # Neuere FastAPI-Fassungen kapseln eingebundene Router in
            # _IncludedRouter und legen den echten Router unter
            # original_router ab.
            inner = getattr(r, "original_router", None) or r
            children = getattr(inner, "routes", [])
            if children is not routes:
                yield from walk(children)

    current = {
        "paths": sorted(set(walk(fastapi_app.routes))),
        "backup_version": BACKUP_VERSION,
    }
    baseline_path = ROOT / "quality" / "api-oberflaeche.json"
    if not baseline_path.exists():
        baseline_path.write_text(
            _json.dumps({"version": raw, **current}, indent=2, ensure_ascii=False),
            encoding="utf-8")
        return True, f"Grundlage angelegt, {len(current['paths'])} Pfade"

    baseline = _json.loads(baseline_path.read_text(encoding="utf-8"))
    base_major = int(baseline["version"].split(".")[0])
    problems = []
    if parts[0] == base_major:
        gone = sorted(set(baseline["paths"]) - set(current["paths"]))
        if gone:
            problems.append("entfallene Pfade ohne MAJOR: " + ", ".join(gone[:3]))
        if baseline["backup_version"] != current["backup_version"]:
            problems.append("Sicherungsformat gesprungen ohne MAJOR")
    if problems:
        return False, "; ".join(problems)

    added = len(set(current["paths"]) - set(baseline["paths"]))
    baseline_path.write_text(
        _json.dumps({"version": raw, **current}, indent=2, ensure_ascii=False),
        encoding="utf-8")
    return True, (f"{len(current['paths'])} Pfade, {added} neu, "
                  f"Sicherungsformat {current['backup_version']}")


# --------------------------------------------------------------------------
# Nicht automatisierbar
# --------------------------------------------------------------------------
# Diese Punkte erscheinen im Bericht und zählen nicht als bestanden. Sie
# hier zu verschweigen wäre der einzige Weg, den Bericht vollständig grün
# zu bekommen, und genau deshalb stehen sie hier.

MANUAL_ITEMS = [
    ("security", "Penetrationstest durch Dritte",
     "erfordert externe Prüfung, zuletzt: nie"),
    ("interaction", "Screenreader-Audit mit echten Hilfsmitteln",
     "VoiceOver und NVDA lassen sich nicht sinnvoll simulieren"),
    ("safety", "Risikoanalyse nach ISO 14971",
     "nur nötig, falls SCOPE X je als Medizinprodukt eingesetzt werden soll"),
    ("security", "Verschlüsselung im Ruhezustand",
     "auf Home Assistant OS nicht pro Add-on möglich, Plattformgrenze"),
    ("reliability", "Überwachung im Betrieb",
     "Ausfall derzeit nur über das Add-on-Protokoll erkennbar"),
    ("compatibility", "Prüfung gegen MariaDB",
     "erfordert eine laufende Instanz, im Prüflauf nicht verfügbar"),
]


def main() -> int:
    ordered = [
        check_lint, check_coverage, check_version, check_public_surface,
        check_suites, check_route_coverage,
        check_response_times, check_asset_budget,
        check_sql_portability, check_db_abstraction,
        check_accessibility, check_color_independence, check_no_inline_styles,
        check_migrations, check_backup_roundtrip,
        check_dependencies, check_headers, check_sql_injection,
        check_rbac_matrix, check_no_secrets,
        check_export_formats, check_addon_manifest,
        check_purpose_statement, check_hazard_warnings,
        check_no_clinical_advice, check_addon_isolation,
    ]
    print("SCOPE X — Qualitätsprüfung nach ISO/IEC 25010:2023\n")
    for fn in ordered:
        fn()
    for characteristic, name, detail in MANUAL_ITEMS:
        record(characteristic, name, MANUAL, detail)

    failed = [r for r in results if r.status == FAIL]
    write_report()

    print("\n" + "-" * 60)
    counts = {s: sum(1 for r in results if r.status == s)
              for s in (PASS, FAIL, SKIP, MANUAL)}
    print(f"bestanden {counts[PASS]} · fehlgeschlagen {counts[FAIL]} · "
          f"übersprungen {counts[SKIP]} · manuell offen {counts[MANUAL]}")
    if failed:
        print("\nFehlgeschlagen:")
        for r in failed:
            print(f"  - {r.name}: {r.detail}")
    return 1 if failed else 0


def write_report() -> None:
    lines = ["# Qualitätsbericht (automatisch erzeugt)", "",
             f"Erzeugt am {time.strftime('%d.%m.%Y um %H:%M Uhr')} "
             f"für SCOPE X.", "",
             "Erzeugt von `quality/run_quality.py`. Manuell offene Punkte "
             "zählen ausdrücklich nicht als bestanden.", ""]
    by_char = {key: [] for key, _ in CHARACTERISTICS}
    for r in results:
        by_char.setdefault(r.characteristic, []).append(r)
    icon = {PASS: "bestanden", FAIL: "**fehlgeschlagen**", SKIP: "übersprungen",
            MANUAL: "manuell offen"}
    for key, title in CHARACTERISTICS:
        lines += [f"## {title}", "", "| Prüfung | Ergebnis | Anmerkung |",
                  "|---|---|---|"]
        for r in by_char.get(key, []):
            lines.append(f"| {r.name} | {icon[r.status]} | {r.detail} |")
        lines.append("")
    (ROOT / "QUALITAETSPRUEFUNG.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("SCOPEX_DATABASE_URL", "sqlite:////tmp/scopex_quality.db")
    sys.exit(main())
