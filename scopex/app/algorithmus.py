"""Der Feed-Algorithmus „Für dich“.

Bewusst nachvollziehbar statt trainiert: eine gewichtete Summe aus fünf
Signalen, deren Anteile hier stehen und deren Gründe jeder Beitrag mit
sich trägt („Warum sehe ich das?“). Optimiert wird auf Lernen, nicht auf
Verweildauer: seltene Situationen, Komplikationen und Maßnahmen, die man
selbst selten dokumentiert, steigen; bloße Aufmerksamkeit zählt weniger.

Signale, je 0 bis 1:

* Aktualität   exp(-Alter / 48 h)
* Resonanz     Gefällt mir, Kommentare und Reposts, logarithmisch gedämpft,
               damit ein einzelner viraler Beitrag nicht alles verdrängt
* Nähe         folge ich der Person, folgt sie mir, habe ich mit ihren
               Beiträgen zu tun gehabt
* Art          Fallbericht (Komplikation, seltene Situation) vor
               Algorithmus vor Wissen und Kompetenz vor freiem Text
* Relevanz     Maßnahmen im Beitrag, die ich selbst selten oder nie
               dokumentiert habe (Lernlücke), und Themen (#Hashtags), mit
               denen ich mich beschäftigt habe

Danach Vielfalt: jeder weitere Beitrag derselben Person zählt nur noch
65 Prozent des vorigen, damit niemand den Feed allein füllt.

Das eigene Logbuch fließt nur als Zählwert je Maßnahme ein und nur in die
eigene Rangfolge. Kein anderes Mitglied erfährt daraus etwas.
"""
from __future__ import annotations

import heapq
import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone

from . import netzkern as nk
from .db import now_iso, rows

GEWICHTE = {"aktualitaet": 0.28, "resonanz": 0.18, "naehe": 0.22,
            "art": 0.16, "relevanz": 0.16}

ARTWERT = {"fall": 0.85, "algorithmus": 0.8, "wissen": 0.6, "kompetenz": 0.6,
           "beitrag": 0.4, "repost": 0.4}
FALLWERT = {"komplikation": 1.0, "selten": 1.0, "lernfall": 0.8}
FALLGRUND = {"komplikation": "Komplikation", "selten": "Seltene Situation",
             "lernfall": "Lernfall"}
FENSTER_TAGE = 21
KANDIDATEN = 600


def _alter_stunden(iso: str, jetzt: datetime) -> float:
    try:
        t = datetime.fromisoformat(iso)
    except ValueError:
        return 9999.0
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return max(0.0, (jetzt - t).total_seconds() / 3600)


def _zaehle(c, tabelle: str, spalte: str, ids: list[str]) -> Counter:
    if not ids:
        return Counter()
    platz = ", ".join(f":p{i}" for i in range(len(ids)))
    werte = {f"p{i}": x for i, x in enumerate(ids)}
    extra = " AND removed_at IS NULL" if tabelle == "net_comments" else ""
    # tabelle und spalte sind feste Bezeichner aus diesem Modul, keine Eingaben.
    return Counter({r_["k"]: r_["n"] for r_ in rows(
        c, f"SELECT {spalte} AS k, COUNT(*) AS n FROM {tabelle} "
           f"WHERE {spalte} IN ({platz}){extra} GROUP BY {spalte}", **werte)})


def _reposts(c, ids: list[str]) -> Counter:
    if not ids:
        return Counter()
    platz = ", ".join(f":p{i}" for i in range(len(ids)))
    werte = {f"p{i}": x for i, x in enumerate(ids)}
    return Counter({r_["k"]: r_["n"] for r_ in rows(
        c, f"SELECT repost_of AS k, COUNT(*) AS n FROM net_posts WHERE repost_of "
           f"IN ({platz}) AND removed_at IS NULL GROUP BY repost_of", **werte)})


def sichtbare_kandidaten(c, ich: str, fenster_tage: int = FENSTER_TAGE,
                         nur_autoren: set[str] | None = None) -> list[dict]:
    """Veröffentlichte, nicht entfernte Beiträge, die ich sehen darf."""
    seit = (datetime.now(timezone.utc) - timedelta(days=fenster_tage)) \
        .replace(microsecond=0).isoformat()
    autoren_sql, werte = "", {}
    if nur_autoren is not None:
        if not nur_autoren:
            return []
        werte = {f"a{i}": a for i, a in enumerate(sorted(nur_autoren))}
        autoren_sql = "AND p.author_id IN (" + ", ".join(f":{k}" for k in werte) + ") "
    kandidaten = rows(
        c, "SELECT p.*, a.net_private AS autor_privat FROM net_posts p "
           "JOIN user_profile a ON a.user_id = p.author_id "
           "JOIN users u ON u.id = p.author_id "
           "WHERE a.net_active = 1 AND u.disabled_at IS NULL "
           "AND p.removed_at IS NULL AND p.published_at <= :jetzt "
           f"AND p.published_at >= :seit {autoren_sql}"
           f"ORDER BY p.published_at DESC LIMIT {KANDIDATEN}",
        jetzt=now_iso(), seit=seit, **werte)
    gesperrt = nk.blockierte_ids(c, ich)
    gefolgt = nk.gefolgt_ids(c, ich)
    versteckt = {r_["post_id"] for r_ in rows(
        c, "SELECT post_id FROM net_hidden WHERE user_id = :u", u=ich)}
    aus = []
    for p in kandidaten:
        a = p["author_id"]
        if a in gesperrt or p["id"] in versteckt:
            continue
        if nur_autoren is not None and a not in nur_autoren:
            continue
        if a != ich and p["autor_privat"] and a not in gefolgt:
            continue
        aus.append(p)
    return aus


def _logbuch_profil(c, ich: str) -> Counter:
    """Wie oft habe ich welche Maßnahme dokumentiert (Name, klein)."""
    return Counter({(r_["name"] or "").lower(): r_["n"] for r_ in rows(
        c, "SELECT a.measure_name AS name, COUNT(*) AS n FROM measure_attempts a "
           "JOIN encounters e ON e.id = a.encounter_id WHERE e.user_id = :u "
           "AND a.deleted_at IS NULL AND e.deleted_at IS NULL "
           "GROUP BY a.measure_name", u=ich)})


def _interessen(c, ich: str) -> Counter:
    """Hashtags der Beiträge, die ich mochte oder kommentiert habe."""
    themen: Counter = Counter()
    for r_ in rows(c, "SELECT t.tag FROM net_tags t JOIN net_likes l ON "
                      "l.post_id = t.post_id WHERE l.user_id = :u", u=ich):
        themen[r_["tag"]] += 1
    for r_ in rows(c, "SELECT t.tag FROM net_tags t JOIN net_comments k ON "
                      "k.post_id = t.post_id WHERE k.author_id = :u", u=ich):
        themen[r_["tag"]] += 2
    return themen


def _naehe(c, ich: str) -> Counter:
    """Wie viel hatte ich mit den Beiträgen einer Person zu tun."""
    n: Counter = Counter()
    for r_ in rows(c, "SELECT p.author_id FROM net_likes l JOIN net_posts p ON "
                      "p.id = l.post_id WHERE l.user_id = :u", u=ich):
        n[r_["author_id"]] += 1
    for r_ in rows(c, "SELECT p.author_id FROM net_comments k JOIN net_posts p ON "
                      "p.id = k.post_id WHERE k.author_id = :u", u=ich):
        n[r_["author_id"]] += 2
    for r_ in rows(c, "SELECT CASE WHEN k.user_a = :u THEN k.user_b ELSE k.user_a "
                      "END AS gegen FROM net_messages m JOIN net_conversations k "
                      "ON k.id = m.conversation_id WHERE m.sender_id = :u", u=ich):
        n[r_["gegen"]] += 1
    return n


def rangliste(c, ich: str, kandidaten: list[dict], entdecken: bool = False
              ) -> list[tuple[dict, float, list[str]]]:
    """Ordnet Kandidaten. Gibt (Beitrag, Wert, Gründe) zurück."""
    if not kandidaten:
        return []
    jetzt = datetime.now(timezone.utc)
    ids = [p["id"] for p in kandidaten]
    likes = _zaehle(c, "net_likes", "post_id", ids)
    kommentare = _zaehle(c, "net_comments", "post_id", ids)
    reposts = _reposts(c, ids)
    meine_likes = {r_["post_id"] for r_ in rows(
        c, "SELECT post_id FROM net_likes WHERE user_id = :u", u=ich)}
    gefolgt = nk.gefolgt_ids(c, ich)
    folgen_mir = nk.follower_ids(c, ich)
    naehe = _naehe(c, ich)
    logbuch = _logbuch_profil(c, ich)
    interessen = _interessen(c, ich)
    namen: dict[str, str] = {}

    def name(uid: str) -> str:
        if uid not in namen:
            namen[uid] = nk.anzeigename(nk.profil(c, uid))
        return namen[uid]

    tags_je_beitrag: dict[str, list[str]] = {}
    if ids:
        platz = ", ".join(f":p{i}" for i in range(len(ids)))
        for r_ in rows(c, f"SELECT post_id, tag FROM net_tags WHERE post_id IN ({platz})",
                       **{f"p{i}": x for i, x in enumerate(ids)}):
            tags_je_beitrag.setdefault(r_["post_id"], []).append(r_["tag"])

    bewertet = []
    for p in kandidaten:
        gruende: list[tuple[float, str]] = []
        alter = _alter_stunden(p["published_at"], jetzt)
        aktualitaet = math.exp(-alter / 48)

        roh = likes[p["id"]] + 2 * kommentare[p["id"]] + 3 * reposts[p["id"]]
        resonanz = min(1.0, math.log1p(roh) / math.log1p(30))
        if roh >= 6:
            gruende.append((0.3, "Viel Resonanz"))

        autor = p["author_id"]
        if autor == ich:
            naehe_wert = 1.0
        else:
            naehe_wert = 0.0
            if autor in gefolgt:
                naehe_wert += 0.55
                gruende.append((0.5, f"Du folgst {name(autor)}"))
            if autor in folgen_mir:
                naehe_wert += 0.15
            naehe_wert += 0.3 * min(1.0, math.log1p(naehe[autor]) / math.log1p(10))
            if autor not in gefolgt:
                gruende.append((0.2, "Empfehlung aus dem Netz"))
        if entdecken:
            naehe_wert = 0.0

        art = p["kind"]
        details = nk.json_oder_none(p["details"]) or {}
        art_wert = ARTWERT.get(art, 0.4)
        if art == "fall":
            kat = details.get("kategorie", "lernfall")
            art_wert = FALLWERT.get(kat, 0.8)
            gruende.append((0.9, FALLGRUND.get(kat, "Fallbericht")))
        elif art == "algorithmus":
            gruende.append((0.7, "Algorithmus mit Quelle"))

        relevanz = 0.0
        schnapp = nk.json_oder_none(p["snapshot"]) or {}
        for m in schnapp.get("massnahmen", []):
            eigene = logbuch[(m.get("name") or "").lower()]
            luecke = 1.0 if eigene == 0 else 0.7 if eigene <= 2 else \
                0.3 if eigene <= 5 else 0.0
            if luecke > relevanz:
                relevanz = luecke
                if luecke >= 0.7:
                    gruende.append((0.8, "Maßnahme, die du selten dokumentierst: "
                                         + (m.get("name") or "")))
        themen = tags_je_beitrag.get(p["id"], [])
        bestes = max(themen, key=lambda t: interessen[t], default=None)
        if bestes and interessen[bestes]:
            relevanz = max(relevanz, min(1.0, 0.4 + 0.15 * interessen[bestes]))
            gruende.append((0.6, f"Thema, das dich interessiert: #{bestes}"))

        wert = (GEWICHTE["aktualitaet"] * aktualitaet
                + GEWICHTE["resonanz"] * resonanz
                + GEWICHTE["naehe"] * naehe_wert
                + GEWICHTE["art"] * art_wert
                + GEWICHTE["relevanz"] * relevanz)
        if p["id"] in meine_likes:
            wert -= 0.12
        if autor == ich:
            # Eigene Beiträge oben, solange sie frisch sind — danach nicht
            # mehr im eigenen Feed, dafür gibt es die Chronik.
            wert += 0.3 if alter < 6 else -0.4
            gruende = [(1.0, "Dein Beitrag")]
        if alter < 3 and autor != ich:
            gruende.append((0.1, "Neu"))
        gruende.sort(key=lambda g: -g[0])
        bewertet.append((p, wert, [g[1] for g in gruende[:3]]))

    # Vielfalt: gierig den besten nehmen, Wiederholungen derselben Person
    # abwerten. Halde mit verzögerter Neubewertung: ein Eintrag, dessen
    # Person inzwischen öfter vorkam, wird neu bewertet und zurückgelegt.
    halde = [(-wert, i, 0) for i, (_, wert, _) in enumerate(bewertet)]
    heapq.heapify(halde)
    je_autor: Counter = Counter()
    aus = []
    while halde:
        neg, i, stand = heapq.heappop(halde)
        p, wert, gruende = bewertet[i]
        jetzt_stand = je_autor[p["author_id"]]
        if stand != jetzt_stand:
            heapq.heappush(halde, (-wert * (0.65 ** jetzt_stand), i, jetzt_stand))
            continue
        aus.append((p, -neg, gruende))
        je_autor[p["author_id"]] += 1
    return aus


def snapshot_massnahmen(post: dict) -> list[str]:
    try:
        return [m.get("name", "") for m in json.loads(post["snapshot"] or "{}")
                .get("massnahmen", [])]
    except (ValueError, AttributeError):
        return []
