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

Korrekturen nach dem Vorbild großer offener Feed-Systeme (Kandidaten aus
dem eigenen Netz und von außerhalb, Abwertung für bereits Gesehenes,
negative Signale, Vielfalt mit Untergrenze):

* Gesehen      Was der Feed schon ausgeliefert hat, sinkt je Auslieferung
               um 0,06 (höchstens dreimal). Neues kommt so nach oben, ohne
               dass Gesehenes verschwindet.
* Außerhalb    Beiträge von Personen, denen ich nicht folge, zählen 85 %.
               Das eigene Netz hat Vorrang, ohne es abzuschotten.
* Negativ      Habe ich Beiträge einer Person mit „Nicht interessiert“
               ausgeblendet, zählt jeder weitere Beitrag von ihr 75 % je
               Ausblendung, mindestens aber 40 %.
* Gemerkt      Merken ist das stärkste positive Signal: Themen und
               Personen gemerkter Beiträge zählen dreifach.
* Themen       Gefolgte Themen heben die Relevanz auf 0,9.
* Neu im Netz  Wer neu ist und noch wenig geteilt hat, bekommt einen
               kleinen Zuschlag, damit neue Stimmen überhaupt gesehen werden.
* Fragen       Fallvorstellungen ohne hilfreiche Antwort steigen in den
               ersten drei Tagen: dort wird Hilfe gebraucht.

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
from .db import now_iso, q, row, rows

GEWICHTE = {"aktualitaet": 0.28, "resonanz": 0.18, "naehe": 0.22,
            "art": 0.16, "relevanz": 0.16}

ARTWERT = {"fall": 0.85, "fallvorstellung": 0.9, "algorithmus": 0.8, "wissen": 0.6,
           "kompetenz": 0.6, "beitrag": 0.4, "repost": 0.4}
GESEHEN_ABZUG = 0.06
AUSSERHALB = 0.85
AUSGEBLENDET = 0.75
AUSGEBLENDET_MIN = 0.4
NEU_TAGE = 14
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


def gefolgte_themen(c, ich: str) -> set[str]:
    return {r_["tag"] for r_ in rows(
        c, "SELECT tag FROM net_topic_follows WHERE user_id = :u", u=ich)}


def gesehen(c, ich: str, ids: list[str]) -> None:
    """Merkt, welche Beiträge der Feed ausgeliefert hat."""
    jetzt = now_iso()
    for pid in ids:
        if row(c, "SELECT post_id FROM net_seen WHERE user_id = :u AND post_id = :p",
               u=ich, p=pid):
            q(c, "UPDATE net_seen SET times = times + 1, last_at = :t WHERE "
                 "user_id = :u AND post_id = :p", t=jetzt, u=ich, p=pid)
        else:
            q(c, "INSERT INTO net_seen (user_id, post_id, times, last_at) VALUES "
                 "(:u, :p, 1, :t)", u=ich, p=pid, t=jetzt)


def _interessen(c, ich: str) -> Counter:
    """Hashtags der Beiträge, die ich mochte, kommentiert oder gemerkt habe."""
    themen: Counter = Counter()
    for r_ in rows(c, "SELECT t.tag FROM net_tags t JOIN net_saved s ON "
                      "s.post_id = t.post_id WHERE s.user_id = :u", u=ich):
        themen[r_["tag"]] += 3
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
    for r_ in rows(c, "SELECT p.author_id FROM net_saved s JOIN net_posts p ON "
                      "p.id = s.post_id WHERE s.user_id = :u", u=ich):
        n[r_["author_id"]] += 3
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
    meine_themen = gefolgte_themen(c, ich)
    schon_gesehen = {r_["post_id"]: r_["times"] for r_ in rows(
        c, "SELECT post_id, times FROM net_seen WHERE user_id = :u", u=ich)}
    abgelehnt = Counter({r_["author_id"]: r_["n"] for r_ in rows(
        c, "SELECT p.author_id, COUNT(*) AS n FROM net_hidden h JOIN net_posts p "
           "ON p.id = h.post_id WHERE h.user_id = :u GROUP BY p.author_id", u=ich)})
    grenze_neu = (jetzt - timedelta(days=NEU_TAGE)).replace(microsecond=0).isoformat()
    neue_autoren = {r_["id"] for r_ in rows(
        c, "SELECT id FROM users WHERE created_at >= :g", g=grenze_neu)}
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
        elif art == "fallvorstellung":
            gruende.append((0.85, "Fallvorstellung: Frage an die Community"))

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
        gefolgt_thema = next((t for t in themen if t in meine_themen), None)
        if gefolgt_thema:
            relevanz = max(relevanz, 0.9)
            gruende.append((0.75, f"Thema, dem du folgst: #{gefolgt_thema}"))
        if art == "fallvorstellung" and not p.get("answer_comment_id") and alter < 72:
            relevanz = max(relevanz, 0.8)
            gruende.append((0.7, "Noch ohne hilfreiche Antwort"))

        wert = (GEWICHTE["aktualitaet"] * aktualitaet
                + GEWICHTE["resonanz"] * resonanz
                + GEWICHTE["naehe"] * naehe_wert
                + GEWICHTE["art"] * art_wert
                + GEWICHTE["relevanz"] * relevanz)
        if p["id"] in meine_likes:
            wert -= 0.12
        if autor != ich:
            wert -= GESEHEN_ABZUG * min(3, schon_gesehen.get(p["id"], 0))
            if autor not in gefolgt and not entdecken:
                wert *= AUSSERHALB
            if abgelehnt[autor]:
                wert *= max(AUSGEBLENDET_MIN, AUSGEBLENDET ** abgelehnt[autor])
            if autor in neue_autoren:
                wert += 0.05
                gruende.append((0.15, "Neu im Netz"))
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
