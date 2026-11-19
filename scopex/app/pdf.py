"""Nachweis-PDF.

Wird vollstaendig lokal erzeugt. Es werden ausschliesslich Werte
ausgegeben, die auch in der Datenbank stehen. Fehlende Angaben bleiben
leer und werden nicht ergaenzt.
"""
from __future__ import annotations

import math
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from fontTools.ttLib import TTFont
from fpdf import FPDF
from fpdf.enums import XPos, YPos

# Markenhandbuch 2.0, Kapitel 08: Inter, Logo horizontal oben links,
# Fußzeile mit Hinweis auf Selbstdokumentation. Die Schriften erzeugt
# tools/marke_erzeugen.py aus derselben Inter-Datei wie die Oberfläche.
SCHRIFTEN = Path(__file__).resolve().parent / "data" / "fonts"
SCHRIFT = "Inter"
NAVY = (16, 37, 51)
PETROL = (18, 104, 120)
CYAN = (25, 166, 181)
LIME = (185, 217, 54)
INK = (23, 36, 44)
MUTED = (102, 118, 128)
RULE = (220, 227, 230)
RULE_STRONG = (195, 207, 212)
ACCENT = PETROL
ZEK = (166, 61, 74)


@lru_cache(maxsize=1)
def _zeichenvorrat() -> frozenset[int]:
    cmap = TTFont(str(SCHRIFTEN / "Inter-Regular.ttf"))["cmap"].getBestCmap()
    return frozenset(cmap)


def _safe(text) -> str:
    """Ersetzt Zeichen, die die eingebettete Schrift nicht kennt, etwa
    Emojis aus einer Notiz, damit die Erzeugung nie daran scheitert."""
    s = "" if text is None else str(text)
    vorrat = _zeichenvorrat()
    return "".join(z if ord(z) in vorrat or z in "\n\t" else "?" for z in s)


class Nachweis(FPDF):
    def __init__(self, profile: dict, period_label: str):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.profile = profile
        self.period_label = period_label
        self.add_font(SCHRIFT, "", str(SCHRIFTEN / "Inter-Regular.ttf"))
        self.add_font(SCHRIFT, "B", str(SCHRIFTEN / "Inter-Bold.ttf"))
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(15, 15, 15)

    def header(self):
        if self.page_no() == 1:
            return
        zeichen(self, self.l_margin, self.get_y(), 5.2)
        self.set_xy(self.l_margin + 7, self.get_y())
        self.set_font(SCHRIFT, "B", 9)
        self.set_text_color(*MUTED)
        self.cell(0, 5.2, _safe("SCOPE X · Tätigkeits- und Kompetenznachweis"),
                  align="L")
        self.ln(9)

    def footer(self):
        self.set_y(-15)
        self.set_draw_color(*RULE)
        self.set_line_width(0.2)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(1.5)
        self.set_font(SCHRIFT, "", 7.5)
        self.set_text_color(*MUTED)
        name = f"{self.profile.get('first_name','')} {self.profile.get('last_name','')}".strip()
        self.cell(0, 4, _safe(f"Selbstdokumentation, erstellt mit SCOPE X · {name} · "
                              f"{self.period_label}"), align="L")
        self.set_x(self.l_margin)
        self.cell(0, 4, _safe(f"Seite {self.page_no()} von {{nb}}"), align="R")

    # -- Bausteine -------------------------------------------------------
    def rule(self, gap: float = 3):
        self.set_draw_color(*RULE_STRONG)
        self.set_line_width(0.2)
        y = self.get_y() + gap
        self.line(self.l_margin, y, self.w - self.r_margin, y)
        self.set_y(y + gap)

    def section(self, title: str):
        if self.get_y() > self.h - 45:
            self.add_page()
        self.ln(3)
        self.set_font(SCHRIFT, "B", 11)
        self.set_text_color(*INK)
        self.cell(0, 6, _safe(title))
        self.ln(7)

    def kv_table(self, pairs: list[tuple[str, str]], label_w: float = 70):
        self.set_font(SCHRIFT, "", 9.5)
        for label, value in pairs:
            self.set_text_color(*MUTED)
            self.cell(label_w, 5.6, _safe(label))
            self.set_text_color(*INK)
            self.cell(0, 5.6, _safe(value))
            self.ln(5.6)

    def table(self, headers: list[str], widths: list[float],
              data: list[list[str]], align: list[str] | None = None):
        align = align or ["L"] * len(headers)
        self.set_font(SCHRIFT, "B", 8.5)
        self.set_text_color(*MUTED)
        for h, w, a in zip(headers, widths, align, strict=False):
            self.cell(w, 5.5, _safe(h), align=a)
        self.ln(5.5)
        self.set_draw_color(*RULE)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(1.2)
        self.set_font(SCHRIFT, "", 9)
        self.set_text_color(*INK)
        for r in data:
            if self.get_y() > self.h - 26:
                self.add_page()
                self.set_font(SCHRIFT, "", 9)
            for value, w, a in zip(r, widths, align, strict=False):
                self.cell(w, 5.2, _safe(value), align=a)
            self.ln(5.2)


def zeichen(pdf: FPDF, x: float, y: float, groesse: float) -> None:
    """Zeichnet das Logo-Zeichen (Variante dark) in ein Quadrat.

    Dieselbe Geometrie wie brand/logo_symbol_dark.svg im 100er-Raster:
    vier Ringsegmente, Strichmarken, das X aus zwei Winkeln. Rein
    vektoriell, damit der Nachweis auch gedruckt scharf bleibt.
    """
    s = groesse / 100

    def punkt(px: float, py: float) -> tuple[float, float]:
        return x + px * s, y + py * s

    def bogen(a0: float, a1: float, r: float = 34) -> list[tuple[float, float]]:
        schritte = 18
        return [punkt(50 + r * math.cos(math.radians(a - 90)),
                      50 + r * math.sin(math.radians(a - 90)))
                for a in (a0 + (a1 - a0) * i / schritte for i in range(schritte + 1))]

    pdf.set_line_width(7 * s)
    for i, farbe in enumerate((PETROL, CYAN, PETROL, CYAN)):
        a = i * 90 - 90
        pdf.set_draw_color(*farbe)
        pdf.polyline(bogen(a + 14, a + 76), style="D")
    pdf.set_draw_color(*NAVY)
    pdf.set_line_width(5 * s)
    for (x0, y0), (x1, y1) in (((50, 3), (50, 22)), ((50, 78), (50, 97)),
                               ((3, 50), (22, 50)), ((78, 50), (97, 50))):
        pdf.line(*punkt(x0, y0), *punkt(x1, y1))
    pdf.set_fill_color(*NAVY)
    pdf.polygon([punkt(*p) for p in ((27, 30), (39, 30), (49.4, 50), (39, 70),
                                     (27, 70), (37.4, 50))], style="F")
    pdf.set_fill_color(*LIME)
    pdf.polygon([punkt(*p) for p in ((73, 30), (61, 30), (50.6, 50), (61, 70),
                                     (73, 70), (62.6, 50))], style="F")
    pdf.set_line_width(0.2)


def _num(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.1f}".replace(".", ",")
    return str(value)


def _window_label(minutes: int | None) -> str:
    if not minutes:
        return "-"
    if minutes < 60:
        return f"{minutes} Minuten"
    if minutes < 1440:
        h = minutes / 60
        return f"{h:.0f} Stunden".replace(".0", "")
    d = minutes / 1440
    return f"{d:.1f} Tage".replace(".0", "").replace(".", ",")


def build(profile: dict, stats: dict, period_label: str,
          details: list[dict] | None = None,
          detail_medications: list[dict] | None = None,
          edit_window_minutes: int | None = None) -> bytes:
    pdf = Nachweis(profile, period_label)
    pdf.add_page()

    # Kopf: Zeichen, Wortmarke mit Signal-Lime-X, Claim (Primärlogo)
    top = pdf.get_y()
    zeichen(pdf, pdf.l_margin, top, 16)

    pdf.set_xy(pdf.l_margin + 19, top + 0.5)
    pdf.set_font(SCHRIFT, "B", 21)
    pdf.set_text_color(*NAVY)
    pdf.cell(pdf.get_string_width("SCOPE") + 2.2, 11, "SCOPE")
    pdf.set_text_color(*LIME)
    pdf.cell(10, 11, "X")

    pdf.set_xy(pdf.l_margin + 19, top + 10.5)
    pdf.set_font(SCHRIFT, "", 9.5)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 5, _safe("Das Maßnahmen- und Kompetenzlogbuch für den Rettungsdienst"))
    pdf.set_xy(pdf.l_margin, top + 16)
    pdf.ln(4)

    pdf.set_draw_color(*PETROL)
    pdf.set_line_width(1.1)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + 22, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(6)

    name = f"{profile.get('first_name','')} {profile.get('last_name','')}".strip()
    head = [("Name", name or "-"),
            ("Qualifikation", profile.get("qualification") or "-")]
    if profile.get("role"):
        head.append(("Funktion", profile["role"]))
    if profile.get("registration_id"):
        head.append(("Kennung", profile["registration_id"]))
    if profile.get("specialty"):
        head.append(("Facharztbezeichnung", profile["specialty"]))
    head.append(("Zeitraum", period_label))
    head.append(("Erstellt am", datetime.now().strftime("%d.%m.%Y, %H:%M Uhr")))
    # Ohne diese Angabe kann der Leser nicht einschätzen, wie lange ein
    # Eintrag nachträglich änderbar war. Genau das bestimmt, wie belastbar
    # der Nachweis ist.
    head.append(("Bearbeitungsfrist je Eintrag", _window_label(edit_window_minutes)))
    pdf.kv_table(head, label_w=48)
    pdf.rule(4)

    # Überblick
    pdf.section("Überblick")
    pdf.kv_table([
        ("Dokumentierte Einsätze", _num(stats["encounters"])),
        ("Dokumentierte Maßnahmen", _num(stats["attempts"])),
        ("Medikamentengaben", _num(stats["administrations"])),
        ("Zwischenfälle, Ereignisse, Komplikationen",
         _num(stats["complications"]["total"])),
    ])

    # Ergebnisse
    pdf.section("Ergebnisse")
    o = stats["outcomes"]
    pdf.table(
        ["Ergebnis", "Anzahl", "Anteil"], [90, 30, 30],
        [["Erfolgreich", _num(o.get("erfolgreich", 0)), f"{_num(stats['success_rate'])} %"],
         ["Fehlgeschlagen", _num(o.get("fehlgeschlagen", 0)), f"{_num(stats['failure_rate'])} %"],
         ["Abgebrochen", _num(o.get("abgebrochen", 0)), f"{_num(stats['abort_rate'])} %"]],
        align=["L", "R", "R"])

    # Abgeleitete Kategorien
    pdf.section("Ergebnis im Zusammenhang mit Komplikationen")
    pdf.set_font(SCHRIFT, "", 8)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(0, 4, new_x=XPos.LMARGIN, new_y=YPos.NEXT, text=_safe(
        "Berechnet aus dem Ergebnis und dem dokumentierten Bezug der "
        "zugeordneten ZEK. Es findet keine medizinische Bewertung statt."))
    pdf.ln(1.5)
    pdf.table(["Kategorie", "Anzahl", "Anteil"], [110, 22, 22],
              [[r["label"], _num(r["n"]), f"{_num(r['share'])} %"]
               for r in stats["derived"]], align=["L", "R", "R"])

    # Patientenschaden
    harm = stats.get("patient_harm") or {}
    if any(v["attempts"] or v["medications"] for v in harm.values()):
        pdf.section("Einschätzung eines Patientenschadens")
        pdf.table(["Einschätzung", "Maßnahmen", "Medikamentengaben"],
                  [90, 32, 40],
                  [[level, _num(v["attempts"]), _num(v["medications"])]
                   for level, v in harm.items()], align=["L", "R", "R"])

    # Durchführungsart
    if stats["by_delegation"]:
        pdf.section("Durchführungsart")
        pdf.table(["Art", "Anzahl"], [90, 30],
                  [[r["key"], _num(r["n"])] for r in stats["by_delegation"]],
                  align=["L", "R"])

    # Rolle bei der Durchführung
    if stats.get("by_role"):
        pdf.section("Rolle bei der Durchführung")
        pdf.table(["Rolle", "Anzahl", "davon erfolgreich"], [80, 30, 40],
                  [[r["key"], _num(r["n"]), _num(r["ok"])]
                   for r in stats["by_role"]], align=["L", "R", "R"])

    # Kategorien
    if stats["by_category"]:
        pdf.section("Maßnahmen nach Kategorie")
        pdf.table(["Kategorie", "Anzahl"], [120, 30],
                  [[f"{r['key']} - {r['label']}", _num(r["n"])]
                   for r in stats["by_category"]], align=["L", "R"])

    # Einzelmaßnahmen
    if stats["by_measure"]:
        pdf.section("Häufigkeit einzelner Maßnahmen")
        pdf.table(["Maßnahme", "Gesamt", "Erfolgreich"], [110, 25, 25],
                  [[r["name"], _num(r["n"]), _num(r["ok"])]
                   for r in stats["by_measure"]], align=["L", "R", "R"])

    # Medikamente
    if stats["by_medication"]:
        pdf.section("Medikamentengaben nach Wirkstoff")
        pdf.table(["Wirkstoff", "Anzahl"], [120, 30],
                  [[r["name"], _num(r["n"])] for r in stats["by_medication"]],
                  align=["L", "R"])
    if stats["by_route"]:
        pdf.section("Medikamentengaben nach Applikationsweg")
        pdf.table(["Applikationsweg", "Anzahl"], [120, 30],
                  [[r["name"], _num(r["n"])] for r in stats["by_route"]],
                  align=["L", "R"])

    # ZEK
    pdf.section("Zwischenfälle, Ereignisse und Komplikationen")
    pdf.kv_table([
        ("Gesamt", _num(stats["complications"]["total"])),
        ("davon an Maßnahmen", _num(stats["complications"]["on_attempts"])),
        ("davon an Medikamentengaben", _num(stats["complications"]["on_medications"])),
        ("Rate bezogen auf alle Einträge",
         f"{_num(stats['complications']['rate'])} %"),
    ])
    if stats["complications"]["top"]:
        pdf.ln(2)
        pdf.table(["Code", "Bezeichnung", "Anzahl"], [18, 112, 22],
                  [[r["code"], r["label"], _num(r["n"])]
                   for r in stats["complications"]["top"]],
                  align=["L", "L", "R"])

    # NACA
    if stats["naca"]:
        pdf.section("NACA-Verteilung")
        pdf.table(["NACA", "Einsätze", "Anteil", "Maßnahmen", "Medikamente", "ZEK"],
                  [24, 26, 24, 30, 32, 20],
                  [[r["naca"], _num(r["encounters"]), f"{_num(r['share'])} %",
                    _num(r["attempts"]), _num(r["medications"]),
                    _num(r["complications"])] for r in stats["naca"]],
                  align=["L", "R", "R", "R", "R", "R"])

    # Detaillierter Nachweis
    if details:
        pdf.add_page()
        pdf.section("Detaillierter Nachweis: Maßnahmen")
        pdf.set_font(SCHRIFT, "", 8)
        pdf.set_text_color(*MUTED)
        pdf.multi_cell(0, 4, new_x=XPos.LMARGIN, new_y=YPos.NEXT, text=_safe(
            "Einzelne dokumentierte Maßnahmen im gewählten Zeitraum. "
            "Es werden keine Patientendaten geführt."))
        pdf.ln(2)
        for d in details:
            if pdf.get_y() > pdf.h - 34:
                pdf.add_page()
            meta = [f"{_fmt_date(d['enc_date'])} {d['enc_time']}"]
            if d.get("mission_number"):
                meta.append(f"Einsatz {d['mission_number']}")
            if d.get("naca"):
                meta.append(f"NACA {d['naca']}")
            pdf.set_font(SCHRIFT, "", 8)
            pdf.set_text_color(*MUTED)
            pdf.cell(0, 4.4, _safe(" | ".join(meta)))
            pdf.ln(4.4)
            pdf.set_font(SCHRIFT, "B", 9.5)
            pdf.set_text_color(*INK)
            pdf.cell(0, 5, _safe(
                f"{d['measure_category']}  {d['measure_name']}"))
            pdf.ln(5)
            pdf.set_font(SCHRIFT, "", 9)
            line = [f"Ergebnis: {d['outcome']}"]
            if d.get("performer_role"):
                role = d["performer_role"]
                if d.get("performer_qualification"):
                    role += f" ({d['performer_qualification']})"
                line.append(role)
            if d.get("delegation"):
                line.append(d["delegation"])
            for p in d.get("parameters", []):
                unit = f" {p['unit']}" if p.get("unit") else ""
                line.append(f"{p['label']}: {p['value']}{unit}")
            pdf.multi_cell(0, 4.6, new_x=XPos.LMARGIN, new_y=YPos.NEXT, text=_safe(" | ".join(line)))
            if d.get("complications"):
                pdf.set_text_color(*ZEK)
                def _zek(cx):
                    bits = [f"{cx['code']} {cx['label']}"]
                    if cx.get("relation"):
                        bits.append(cx["relation"])
                    if cx.get("patient_harm") in ("vermutet", "gesichert"):
                        bits.append("Schaden " + cx["patient_harm"])
                    return bits[0] + (" (" + ", ".join(bits[1:]) + ")"
                                      if len(bits) > 1 else "")
                pdf.multi_cell(0, 4.6, new_x=XPos.LMARGIN, new_y=YPos.NEXT,
                               text=_safe("ZEK: " + "; ".join(
                                   _zek(cx) for cx in d["complications"])))
                pdf.set_text_color(*INK)
            pdf.ln(1.5)

    if detail_medications:
        pdf.section("Detaillierter Nachweis: Medikamentengaben")
        header = ["Datum", "NACA", "Wirkstoff", "Dosis", "Weg", "Art"]
        widths = [22, 14, 46, 26, 26, 40]
        data = []
        for m in detail_medications:
            dose = ""
            if m.get("dose") is not None:
                dose = f"{_num(m['dose'])} {m.get('unit') or ''}".strip()
            data.append([_fmt_date(m["enc_date"]), m.get("naca") or "-",
                         m["medication_name"], dose or "-",
                         m.get("route") or "-", m.get("delegation") or "-"])
        pdf.table(header, widths, data)

    return bytes(pdf.output())


def _fmt_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d.%m.%Y")
    except Exception:
        return iso
