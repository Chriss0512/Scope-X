/* SCOPE X - Netzwerk, Suche, Themen, Qualifikationen
   Seit 4.5.0: Übersicht „Netzwerk“ mit Anfragen, Vorschlägen und
   Kontakten; eine eigene Suche; Themen als Filter für den Feed;
   strukturierte Fallvorstellungen; Region, Organisation und Wache aus
   Listen; Qualifikationen mit Ablaufdatum; Fortbildungsnachweis.

   Wird nach netz.js und vor app.js geladen. Alle Sichtbarkeitsregeln
   stehen im Server; hier wird nur angezeigt, was er herausgibt. */

"use strict";

const NETZ_ALTER = {
  neugeboren: "Neugeborenes", saeugling: "Säugling", kleinkind: "Kleinkind",
  schulkind: "Schulkind", jugendlich: "Jugendliche*r", erwachsen: "Erwachsene*r",
  hochbetagt: "Hochbetagt",
};
const NETZ_XABCDE = [
  ["x", "x", "Kritische Blutung"], ["a", "A", "Atemweg"], ["b", "B", "Belüftung"],
  ["c", "C", "Kreislauf"], ["d", "D", "Neurologie"], ["e", "E", "Erweiterte Untersuchung"],
];
const NETZ_QSTATUS = {
  gueltig: "gültig", bald: "läuft bald ab", abgelaufen: "abgelaufen", unbefristet: "",
};
const NETZ_ICON_MERKEN = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round" aria-hidden="true"><path d="M6 3.8h12v16.6l-6-4.4-6 4.4z"/></svg>`;
const NETZ_ICON_GEMERKT = `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round" aria-hidden="true"><path d="M6 3.8h12v16.6l-6-4.4-6 4.4z"/></svg>`;

let netzThemen = null;
async function themenKatalog(neu = false) {
  if (!netzThemen || neu) netzThemen = await api("/api/netz/themen");
  return netzThemen;
}

// ------------------------------------------------------- Fallvorstellung

function fallvorstellungHtml(b) {
  const d = b.details || {};
  const befund = NETZ_XABCDE.filter(([k]) => d[k]);
  return `
    <div class="np-case np-fv">
      <div class="case-kat">Fallvorstellung${d.altersgruppe
        ? " · " + esc(NETZ_ALTER[d.altersgruppe] || "") : ""}</div>
      <h2 class="case-title">${esc(b.titel)}</h2>
      <div class="case-sec"><span>Meldebild</span><p>${esc(d.meldebild || "")}</p></div>
      ${befund.length ? `<div class="case-sec"><span>Befund nach <i class="nt">xABCDE</i></span>
        <dl class="xabcde">${befund.map(([k, buchst, name]) => `
          <dt title="${esc(name)}"><abbr title="${esc(name)}">${buchst}</abbr></dt>
          <dd>${esc(d[k])}</dd>`).join("")}</dl></div>` : ""}
      ${d.massnahmen ? `<div class="case-sec"><span>Maßnahmen</span><p>${esc(d.massnahmen)}</p></div>` : ""}
      <div class="case-sec fv-frage"><span>Frage an die Community</span>
        <p><strong>${esc(d.frage || "")}</strong></p></div>
      ${b.hilfreich ? `<p class="tiny fv-geloest">Hilfreiche Antwort markiert</p>` : ""}
    </div>
    ${kompetenzBlock(b.kompetenz)}`;
}

function themenChipsHtml(b) {
  const t = (b.themen || []).filter((x) => x.code !== "fallvorstellung");
  if (!t.length) return "";
  return `<div class="np-themen">${t.map((x) => `<a class="chip thema link-plain"
    href="#/tag/${encodeURIComponent(x.code)}">#${esc(x.name)}</a>`).join("")}</div>`;
}

function abzeichenHtml(p, max = 3) {
  const a = (p && p.abzeichen) || [];
  if (!a.length) return "";
  return `<span class="abz-reihe">${a.slice(0, max).map((x) =>
    `<span class="abz">${esc(x)}</span>`).join("")}</span>`;
}

// ---------------------------------------------------------------- Suche

async function viewSuche() {
  const p = await netzProfil();
  if (!p.aktiv) return netzEinstieg(p);
  const { query } = currentRoute();
  const start = query.get("q") || "";
  const [kreise, orgs, quals] = await Promise.all([
    api("/api/oeffentlich/kreise"), api("/api/netz/katalog/organisationen"),
    api("/api/netz/katalog/qualifikationen"),
  ]);
  app().innerHTML = `
    <div class="page-head"><h1>Suche</h1></div>
    <form class="search-bar" id="s-form" role="search">
      <label class="sr-only" for="s-q">Personen, Themen oder Beiträge</label>
      <input id="s-q" type="search" maxlength="80" autocomplete="off" value="${esc(start)}"
        placeholder="Personen, #Themen, Beiträge">
    </form>
    <details class="s-filter" id="s-filter">
      <summary class="small">Personen filtern</summary>
      <div class="field-row three" data-s="mt-sm">
        <div class="field"><label for="s-kreis">Kreis</label>
          <input id="s-kreis" list="s-kreise" autocomplete="off" placeholder="z. B. Heidekreis">
          <datalist id="s-kreise">${kreise.kreise.map((k) =>
            `<option value="${esc(k.name)}"></option>`).join("")}</datalist></div>
        <div class="field"><label for="s-org">Organisation</label>
          <select id="s-org"><option value="">alle</option>${orgs.organisationen.map((o) =>
            `<option value="${esc(o.id)}">${esc(o.name)}</option>`).join("")}</select></div>
        <div class="field"><label for="s-qual">Qualifikation oder Kurs</label>
          <select id="s-qual"><option value="">alle</option>${quals.qualifikationen.map((x) =>
            `<option value="${esc(x.id)}">${esc(x.kurz)}</option>`).join("")}</select></div>
      </div>
      <p class="tiny muted">Gefiltert wird nur über Profile, die du vollständig sehen darfst.</p>
    </details>
    <div id="s-ergebnis"></div>
    ${pageFoot()}`;

  const kreisAgs = (name) => (kreise.kreise.find((k) => k.name === name) || {}).ags || "";
  let warte = null;
  const suche = async () => {
    const w = $("#s-q").value.trim();
    const filter = { kreis: kreisAgs($("#s-kreis").value), organisation: $("#s-org").value,
      qualifikation: $("#s-qual").value };
    const ziel = $("#s-ergebnis");
    const aktiv = Object.values(filter).some(Boolean);
    if (w.length < 2 && !aktiv) return zeigeEntdeckenRaster(ziel);
    const params = new URLSearchParams({ q: w, ...filter });
    const r = await api("/api/netz/suche?" + params);
    if (!$("#s-ergebnis")) return;
    ziel.innerHTML = `
      ${r.personen.length ? `<section><h2 class="sec">Personen</h2>
        <ul class="person-list">${r.personen.map((x) => personZeile(x)).join("")}</ul></section>` : ""}
      ${r.themen.length || r.tags.length ? `<section><h2 class="sec">Themen</h2>
        <ul class="person-list">${r.themen.map((t) => `
          <li class="person-row"><a class="link-plain row grow" href="#/tag/${encodeURIComponent(t.code)}" data-s="gap-sm">
            <span class="tag-disc" aria-hidden="true">#</span><span class="grow"><strong>${esc(t.name)}</strong>
            <span class="tiny muted np-sub">${esc(t.kategorie)}</span></span></a></li>`).join("")}
          ${r.tags.map((t) => `
          <li class="person-row"><a class="link-plain row grow" href="#/tag/${encodeURIComponent(t.tag)}" data-s="gap-sm">
            <span class="tag-disc" aria-hidden="true">#</span><span class="grow"><strong>#${esc(t.tag)}</strong>
            <span class="tiny muted np-sub">${t.anzahl} ${t.anzahl === 1 ? "Beitrag" : "Beiträge"}</span></span></a></li>`).join("")}
        </ul></section>` : ""}
      ${r.beitraege.length ? `<section><h2 class="sec">Beiträge</h2>${rasterHtml(r.beitraege)}</section>` : ""}
      ${!r.personen.length && !r.themen.length && !r.tags.length && !r.beitraege.length
        ? `<p class="small muted" data-s="mt-md">Nichts gefunden. Gefunden wird nur, wer das
          Kompetenznetz eingeschaltet hat.</p>` : ""}`;
    if (!ziel.dataset.gebunden) { ziel.dataset.gebunden = "1"; bindeFolgen(ziel, () => {}); }
  };
  const spaeter = () => { clearTimeout(warte); warte = setTimeout(suche, 250); };
  $("#s-q").addEventListener("input", spaeter);
  $("#s-form").addEventListener("submit", (e) => { e.preventDefault(); suche(); });
  ["#s-kreis", "#s-org", "#s-qual"].forEach((s) => $(s).addEventListener("change", suche));
  suche();
  if (!start) $("#s-q").focus();
}

/* Leere Suche zeigt, was es zu entdecken gibt: wie bei Bildnetzwerken. */
async function zeigeEntdeckenRaster(ziel) {
  const [r, th] = await Promise.all([api("/api/netz/entdecken"), themenKatalog()]);
  if (!document.body.contains(ziel)) return;
  ziel.innerHTML = `
    <div class="chip-scroll" data-s="mt-sm">${th.themen.slice(0, 14).map((t) =>
      `<a class="chip thema link-plain" href="#/tag/${encodeURIComponent(t.code)}">#${esc(t.name)}</a>`).join("")}
      <a class="chip link-plain" href="#/themen">Alle Themen</a></div>
    ${r.beitraege.length ? rasterHtml(r.beitraege) : `<div class="empty">${markSvg("mark")}
      <strong>Noch nichts zu entdecken.</strong></div>`}`;
}

// ------------------------------------------------------------- Netzwerk

async function viewNetzwerk() {
  const p = await netzProfil();
  if (!p.aktiv) return netzEinstieg(p);
  const [n, bg] = await Promise.all([api("/api/netz/netzwerk"),
    api("/api/netz/buergschaften").catch(() => ({ buergschaften: [] }))]);
  const liste = (personen, leer) => personen.length
    ? `<ul class="person-list">${personen.map((x) => personZeile(x)).join("")}</ul>`
    : `<p class="small muted">${leer}</p>`;
  app().innerHTML = `
    <div class="page-head"><h1>Netzwerk</h1>
      <p class="small muted">Wem du folgst, wer dir folgen möchte und wen du kennen könntest.</p></div>
    <div class="feed-col" id="nw">
      ${bg.buergschaften.length ? `<section class="mt-sec"><h2 class="sec">Bürgschaften</h2>
        <p class="tiny muted">Diese Personen haben sich beworben und dich als Kontakt genannt.
        Sag der Administration, ob du sie kennst.</p>
        <ul class="bw-list">${bg.buergschaften.map((b) => `
          <li class="card flat pad-xs">
            <strong>${esc(b.vorname)} ${esc(b.nachname)}</strong>
            <div class="tiny muted">${[b.qualifikation, b.organisation, b.wache, b.kreis]
              .filter(Boolean).map(esc).join(" · ")}</div>
            ${b.begruendung ? `<p class="small" data-s="mt-xs">${esc(b.begruendung)}</p>` : ""}
            ${b.antwort === "angefragt" ? `
            <div class="field" data-s="mt-sm"><label for="bg-${esc(b.id)}" class="tiny">Anmerkung (optional)</label>
              <input id="bg-${esc(b.id)}" maxlength="500"></div>
            <div class="row" data-s="gap-sm mt-sm">
              <button type="button" class="btn-primary small" data-buerge="${esc(b.id)}" data-antwort="ja">Ich kenne die Person</button>
              <button type="button" class="btn-soft small" data-buerge="${esc(b.id)}" data-antwort="nein">Kenne ich nicht</button>
            </div>` : `<p class="tiny muted" data-s="mt-xs">Beantwortet: ${
              b.antwort === "bestaetigt" ? "kenne ich" : "kenne ich nicht"}</p>`}
          </li>`).join("")}</ul></section>` : ""}

      <section class="mt-sec"><h2 class="sec">Folgeanfragen</h2>
        ${n.anfragen.length ? `<ul class="person-list">${n.anfragen.map((x) => `
          <li class="person-row">
            <a class="row grow link-plain" href="#/person/${esc(x.id)}" data-s="gap-sm">${avatarHtml(x, "m")}
              <span class="grow"><strong>${esc(x.name)}</strong><span class="tiny muted np-sub">${esc(x.headline)}</span></span></a>
            <button type="button" class="btn-primary small" data-annehmen="${esc(x.id)}">Annehmen</button>
            <button type="button" class="btn-soft small" data-ignorieren="${esc(x.id)}">Ignorieren</button>
          </li>`).join("")}</ul>` : `<p class="small muted">Keine offenen Anfragen.</p>`}
        ${n.ignoriert.length ? `<details class="small" data-s="mt-sm"><summary>Ignoriert (${n.ignoriert.length})</summary>
          <p class="tiny muted">Wer ignoriert wurde, erfährt das nicht. Du kannst später noch annehmen.</p>
          <ul class="person-list">${n.ignoriert.map((x) => `
          <li class="person-row">
            <a class="row grow link-plain" href="#/person/${esc(x.id)}" data-s="gap-sm">${avatarHtml(x, "m")}
              <span class="grow"><strong>${esc(x.name)}</strong></span></a>
            <button type="button" class="btn-soft small" data-annehmen="${esc(x.id)}">Annehmen</button>
            <button type="button" class="btn-quiet small" data-ablehnen="${esc(x.id)}">Löschen</button>
          </li>`).join("")}</ul></details>` : ""}
      </section>

      <section class="mt-sec"><h2 class="sec">Vorschläge für dich</h2>
        ${n.vorschlaege.length ? `<ul class="person-list">${n.vorschlaege.map((x) => `
          <li class="person-row">
            <a class="row grow link-plain" href="#/person/${esc(x.id)}" data-s="gap-sm">${avatarHtml(x, "m")}
              <span class="grow"><strong>${esc(x.name)}</strong> ${abzeichenHtml(x, 2)}
                <span class="tiny muted np-sub">${esc((x.gruende || []).join(" · ") || x.headline || "")}</span></span></a>
            ${folgeKnopf(x)}
            <button type="button" class="icon-btn flat small" data-weg-vorschlag="${esc(x.id)}"
              aria-label="Vorschlag ${esc(x.name)} ausblenden">${NETZ_ICON.x}</button>
          </li>`).join("")}</ul>` : `<p class="small muted">Trag unter Einstellungen → Netzwerk
          Region, Organisation und Wache ein, dann finden sich Kolleg*innen leichter.</p>`}
      </section>

      <section class="mt-sec">
        <div class="seg" role="tablist" aria-label="Kontakte" id="nw-seg">
          <button class="seg-item" role="tab" data-nw="folge_ich" aria-selected="true">Ich folge (${n.folge_ich.length})</button>
          <button class="seg-item" role="tab" data-nw="follower">Follower (${n.follower.length})</button>
          ${n.ausstehend.length ? `<button class="seg-item" role="tab" data-nw="ausstehend">Angefragt (${n.ausstehend.length})</button>` : ""}
        </div>
        <div id="nw-liste"></div>
      </section>
      <section class="mt-sec" id="nw-einladen"></section>
      <a class="settings-link link-plain" href="#/themen"><strong>Themen</strong>
        <span class="tiny muted">Folge Kompetenz-Themen wie #Atemwegsmanagement oder #EKG-Quiz</span></a>
      <a class="settings-link link-plain" href="#/gespeichert"><strong>Gespeichert</strong>
        <span class="tiny muted">Beiträge, die du dir gemerkt hast</span></a>
    </div>
    ${pageFoot()}`;
  const zeige = (art) => {
    app().querySelectorAll("[data-nw]").forEach((b) =>
      b.setAttribute("aria-selected", String(b.dataset.nw === art)));
    $("#nw-liste").innerHTML = liste(n[art], art === "folge_ich" ? "Du folgst noch niemandem."
      : art === "follower" ? "Noch keine Follower." : "Keine offenen Anfragen.");
  };
  app().querySelectorAll("[data-nw]").forEach((b) => b.addEventListener("click", () => zeige(b.dataset.nw)));
  zeige("folge_ich");
  const box = $("#nw");
  bindeFolgen(box, () => viewNetzwerk());
  zeigeEinladungen($("#nw-einladen"));
  box.addEventListener("click", async (e) => {
    const ig = e.target.closest("[data-ignorieren]");
    const weg = e.target.closest("[data-weg-vorschlag]");
    const bu = e.target.closest("[data-buerge]");
    try {
      if (ig) {
        await api(`/api/netz/follower/${encodeURIComponent(ig.dataset.ignorieren)}/ignorieren`, { method: "POST" });
        mitteilungsZaehler(true); viewNetzwerk();
      } else if (weg) {
        await api(`/api/netz/vorschlaege/${encodeURIComponent(weg.dataset.wegVorschlag)}/ausblenden`, { method: "POST" });
        weg.closest("li").remove();
      } else if (bu) {
        const feld = $("#bg-" + CSS.escape(bu.dataset.buerge));
        await api("/api/netz/buergschaften/" + encodeURIComponent(bu.dataset.buerge),
          { method: "POST", body: { antwort: bu.dataset.antwort, text: feld ? feld.value : "" } });
        toast("Danke, die Administration ist informiert."); viewNetzwerk();
      }
    } catch (err) { toast(err.message); }
  });
}

/* „Wem folgen?“ als Karte im Feed, wie bei großen Netzwerken an fester
   Stelle. Nur, wenn es Vorschläge mit erkennbarem Zusammenhang gibt. */
async function vorschlagKarte(liste) {
  const v = await api("/api/netz/vorschlaege?anzahl=8").catch(() => ({ personen: [] }));
  const mit = v.personen.filter((x) => (x.gruende || []).length);
  if (mit.length < 2 || !document.body.contains(liste)) return;
  const karten = liste.querySelectorAll(":scope > .npost");
  const nach = karten[Math.min(3, karten.length - 1)];
  if (!nach) return;
  nach.insertAdjacentHTML("afterend", `
    <section class="wtf card flat" aria-label="Vorschläge">
      <div class="spread"><strong class="small">Vorschläge für dich</strong>
        <a class="small link-plain" href="#/netzwerk">Alle ansehen</a></div>
      <div class="wtf-reihe">${mit.slice(0, 6).map((x) => `
        <div class="wtf-karte">
          <a class="link-plain" href="#/person/${esc(x.id)}">${avatarHtml(x, "l")}
            <strong class="small">${esc(x.name)}</strong>
            <span class="tiny muted">${esc(x.gruende[0])}</span></a>
          ${folgeKnopf(x)}
        </div>`).join("")}</div>
    </section>`);
  bindeFolgen(liste.querySelector(".wtf"), () => {});
}

// ------------------------------------------------------------ Gespeichert

async function viewGespeichert() {
  const r = await api("/api/netz/gemerkt");
  app().innerHTML = `
    <div class="page-head"><a class="small muted link-plain back-btn" href="#/profil">Profil</a>
      <h1>Gespeichert</h1>
      <p class="small muted">Nur du siehst, was du gespeichert hast. Beiträge, die gelöscht oder
      nicht mehr sichtbar sind, fallen heraus.</p></div>
    ${r.beitraege.length ? rasterHtml(r.beitraege) : `<div class="empty">${markSvg("mark")}
      <strong>Noch nichts gespeichert.</strong> Tippe unter einem Beitrag auf das Lesezeichen.</div>`}
    ${pageFoot()}`;
}

// ---------------------------------------------------------------- Themen

async function viewThemen() {
  const th = await themenKatalog(true);
  app().innerHTML = `
    <div class="page-head"><h1>Themen</h1>
      <p class="small muted">Folge Themen, und „Für dich“ zeigt dir mehr davon. Im Feed lässt
      sich nach jedem Thema filtern.</p></div>
    <div id="th-liste">${th.kategorien.map((k) => {
      const liste = th.themen.filter((t) => t.kategorie === k);
      if (!liste.length) return "";
      return `<section class="mt-sec"><h2 class="sec">${esc(k)}</h2><ul class="person-list">${liste.map((t) => `
        <li class="person-row">
          <a class="link-plain row grow" href="#/tag/${encodeURIComponent(t.code)}" data-s="gap-sm">
            <span class="tag-disc" aria-hidden="true">#</span><span class="grow"><strong>${esc(t.name)}</strong>
            <span class="tiny muted np-sub">#${esc(t.code)} · ${t.beitraege} ${t.beitraege === 1 ? "Beitrag" : "Beiträge"}</span></span></a>
          ${themaKnopf(t)}
        </li>`).join("")}</ul></section>`;
    }).join("")}</div>
    ${pageFoot()}`;
  bindeThemen(app());
}

function themaKnopf(t) {
  return t.folge_ich
    ? `<button type="button" class="btn-soft small" data-thema-weg="${esc(t.code)}">Gefolgt</button>`
    : `<button type="button" class="btn-primary small" data-thema="${esc(t.code)}">Folgen</button>`;
}

function bindeThemen(bereich) {
  bereich.addEventListener("click", async (e) => {
    const k = e.target.closest("[data-thema], [data-thema-weg]");
    if (!k) return;
    const code = k.dataset.thema || k.dataset.themaWeg;
    try {
      const r = await api(`/api/netz/themen/${encodeURIComponent(code)}/folgen`,
        { method: k.dataset.thema ? "PUT" : "DELETE" });
      k.outerHTML = themaKnopf({ code, folge_ich: r.folge_ich });
      netzThemen = null;
    } catch (err) { toast(err.message); }
  });
}

/* Themen-Auswahl im Formular: bis zu fünf, als Chips. */
async function themenWahlHtml(ziel, gewaehlt) {
  const th = await themenKatalog();
  ziel.innerHTML = `<span class="field-label small" id="cp-th-l">Themen (bis zu fünf)</span>
    <div class="chip-scroll wrap" role="group" aria-labelledby="cp-th-l">${th.themen
      .filter((t) => t.code !== "fallvorstellung").map((t) => `
      <button type="button" class="chip" data-th="${esc(t.code)}"
        aria-pressed="${gewaehlt.has(t.code)}">#${esc(t.name)}</button>`).join("")}</div>`;
  ziel.addEventListener("click", (e) => {
    const c = e.target.closest("[data-th]");
    if (!c) return;
    if (gewaehlt.has(c.dataset.th)) gewaehlt.delete(c.dataset.th);
    else if (gewaehlt.size < 5) gewaehlt.add(c.dataset.th);
    else { toast("Höchstens fünf Themen."); return; }
    c.setAttribute("aria-pressed", String(gewaehlt.has(c.dataset.th)));
  });
}

// ------------------------------------------- Profil: Ort und Qualifikation

function ortText(ort, legacy = {}) {
  if (!ort) return [legacy.organisation, legacy.location].filter(Boolean).join(" · ");
  return [ort.wache && ort.wache.name, ort.organisation && ort.organisation.name,
    ort.kreis].filter(Boolean).join(" · ")
    || [legacy.organisation, legacy.location].filter(Boolean).join(" · ");
}

function qualListeHtml(liste, eigen) {
  if (!liste.length) return "";
  return `<ul class="q-list">${liste.map((x) => `
    <li class="q-row" data-status="${esc(x.status)}">
      <span class="grow"><strong>${esc(x.name)}</strong>
        <span class="tiny muted np-sub">${esc(x.kategorie)}${eigen && x.erworben
          ? " · erworben " + esc(monatJahr(x.erworben)) : ""}${eigen && x.gueltig_bis
          ? " · gültig bis " + esc(monatJahr(x.gueltig_bis)) : ""}</span></span>
      ${NETZ_QSTATUS[x.status] ? `<span class="q-status">${esc(NETZ_QSTATUS[x.status])}</span>` : ""}
      ${eigen ? `<button type="button" class="btn-quiet small" data-q-weg="${esc(x.id)}"
        aria-label="${esc(x.name)} entfernen">Entfernen</button>` : ""}
    </li>`).join("")}</ul>`;
}

function ortKarten(p) {
  const o = p.ort || {};
  return `
    <div class="card pad-lg" data-s="mt-md">
      <h2>Region und Wache</h2>
      <p class="tiny muted" data-s="mt-xs">Aus Listen statt Freitext, damit Kolleg*innen aus
      derselben Wache, Organisation oder Region zueinanderfinden. Bei einem privaten Konto
      fließen diese Angaben nicht in Vorschläge und Suchfilter für andere ein.</p>
      <form id="ort-form" class="stack" data-s="mt-md">
        <div class="field"><label for="ok">Kreis oder kreisfreie Stadt</label>
          <input id="ok" list="ok-liste" autocomplete="off" value="${esc(o.kreis || "")}"
            placeholder="z. B. Heidekreis"><datalist id="ok-liste"></datalist></div>
        <div class="field"><label for="oo">Organisation</label>
          <select id="oo"><option value="">keine Angabe</option></select>
          <button type="button" class="link-btn small strong" id="oo-neu">Organisation fehlt?</button></div>
        <div class="field"><label for="ow">Wache</label>
          <select id="ow"><option value="">keine Angabe</option></select>
          <button type="button" class="link-btn small strong" id="ow-neu">Wache fehlt? Einreichen</button></div>
        <button class="btn-primary" type="submit">Speichern</button>
        <p class="tiny muted" id="ort-err" role="alert"></p>
        <p class="tiny muted">Kreisliste: Statistisches Bundesamt (Destatis), Gemeindeverzeichnis,
        Stand 31.12.2024, Datenlizenz Deutschland – Namensnennung – Version 2.0.</p>
      </form>
    </div>
    <div class="card pad-lg" data-s="mt-md">
      <h2>Qualifikationen und Kurse</h2>
      <p class="tiny muted" data-s="mt-xs">Aus einer kuratierten Liste. Ablaufdaten werden aus
      den Angaben der Herausgeber berechnet; du wirst 90 Tage vorher erinnert. Andere sehen nur
      gültige Einträge und keine Daten; gültige Kurse erscheinen als Abzeichen am Profil.</p>
      <div id="q-meine" data-s="mt-sm">${qualListeHtml(p.qualifikationen || [], true)}</div>
      <form id="q-form" class="stack" data-s="mt-md">
        <div class="field-row">
          <div class="field"><label for="qq">Qualifikation oder Kurs</label>
            <select id="qq" required><option value="">Bitte wählen</option></select></div>
          <div class="field"><label for="qe">Erworben (Monat)</label>
            <input id="qe" type="month"></div>
        </div>
        <div class="field"><label for="qb">Gültig bis (nur wenn abweichend)</label>
          <input id="qb" type="month"></div>
        <button class="btn-soft" type="submit">Hinzufügen</button>
        <button type="button" class="link-btn small strong" id="q-fehlt">Kurs fehlt? Vorschlagen</button>
        <p class="tiny muted" id="q-err" role="alert"></p>
      </form>
      <a class="small" href="#/fortbildung" data-s="mt-md">Zum Fortbildungsnachweis</a>
    </div>`;
}

async function bindeOrt(p) {
  const form = $("#ort-form");
  if (!form) return;
  const o = p.ort || {};
  const [kreise, orgs, quals] = await Promise.all([api("/api/oeffentlich/kreise"),
    api("/api/netz/katalog/organisationen"), api("/api/netz/katalog/qualifikationen")]);
  if (!document.body.contains(form)) return;
  $("#ok-liste").innerHTML = kreise.kreise.map((k) => `<option value="${esc(k.name)}"></option>`).join("");
  const ags = () => (kreise.kreise.find((k) => k.name === $("#ok").value.trim()) || {}).ags || "";
  const orgOptionen = (liste, wahl) => `<option value="">keine Angabe</option>${liste.map((x) =>
    `<option value="${esc(x.id)}" ${x.id === wahl ? "selected" : ""}>${esc(x.name)}${
      x.status === "neu" ? " (eingereicht)" : ""}</option>`).join("")}`;
  $("#oo").innerHTML = orgOptionen(orgs.organisationen, o.organisation && o.organisation.id);
  const ladeWachen = async (wahl) => {
    const k = ags();
    if (!k) { $("#ow").innerHTML = `<option value="">Erst den Kreis wählen</option>`; return; }
    const w = await api("/api/netz/katalog/wachen?" + new URLSearchParams({ kreis: k }));
    $("#ow").innerHTML = orgOptionen(w.wachen.map((x) => ({ ...x,
      name: x.name + (x.organisation ? " · " + x.organisation : "") })), wahl);
  };
  ladeWachen(o.wache && o.wache.id);
  $("#ok").addEventListener("change", () => ladeWachen(null));

  $("#oo-neu").addEventListener("click", () => sheet("Organisation einreichen", `
    <form id="on-form" class="stack">
      <div class="field"><label for="on-name">Name</label><input id="on-name" maxlength="120" required
        placeholder="z. B. Rettungsdienst Musterkreis gGmbH"></div>
      <button class="btn-primary" type="submit">Einreichen</button>
      <p class="tiny muted">Die Administration sichtet Einreichungen und führt Doppelte zusammen.</p>
    </form>`, (body) => $("#on-form", body).addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const r = await api("/api/netz/katalog/organisationen", { method: "POST",
        body: { name: $("#on-name", body).value } });
      orgs.organisationen.push(r);
      $("#oo").innerHTML = orgOptionen(orgs.organisationen, r.id);
      closeSheet();
    } catch (err) { toast(err.message); }
  })));
  $("#ow-neu").addEventListener("click", () => {
    if (!ags()) { toast("Wähle zuerst den Kreis der Wache."); return; }
    sheet("Wache einreichen", `
      <form id="wn-form" class="stack">
        <div class="field"><label for="wn-name">Name der Wache</label><input id="wn-name" maxlength="120"
          required placeholder="z. B. Rettungswache Soltau"></div>
        <p class="tiny muted">Wird mit dem Kreis ${esc($("#ok").value)} und der gewählten Organisation
        angelegt. Gibt es die Wache schon, wird die vorhandene genommen.</p>
        <button class="btn-primary" type="submit">Einreichen</button>
      </form>`, (body) => $("#wn-form", body).addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const r = await api("/api/netz/katalog/wachen", { method: "POST", body: {
          name: $("#wn-name", body).value, kreis_ags: ags(),
          organisation_id: $("#oo").value || null } });
        closeSheet(); await ladeWachen(r.id);
      } catch (err) { toast(err.message); }
    }));
  });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if ($("#ok").value.trim() && !ags()) { $("#ort-err").textContent = "Bitte einen Kreis aus der Liste wählen."; return; }
    try {
      await api("/api/netz/profil/ort", { method: "PUT", body: { kreis_ags: ags() || null,
        organisation_id: $("#oo").value || null, wache_id: $("#ow").value || null } });
      $("#ort-err").textContent = ""; toast("Gespeichert.");
    } catch (err) { $("#ort-err").textContent = err.message; }
  });

  // Qualifikationen
  const gruppen = {};
  quals.qualifikationen.forEach((x) => (gruppen[x.kategorie] = gruppen[x.kategorie] || []).push(x));
  $("#qq").innerHTML = `<option value="">Bitte wählen</option>${Object.entries(gruppen).map(([k, l]) =>
    `<optgroup label="${esc(k)}">${l.map((x) => `<option value="${esc(x.id)}">${esc(x.name)}${
      x.gueltig_monate ? ` · ${x.gueltig_monate / 12 >= 1 && x.gueltig_monate % 12 === 0
        ? x.gueltig_monate / 12 + " J." : x.gueltig_monate + " Mon."}` : ""}${
      x.status === "vorgeschlagen" ? " (vorgeschlagen)" : ""}</option>`).join("")}</optgroup>`).join("")}`;
  const zeigeMeine = (liste) => { $("#q-meine").innerHTML = qualListeHtml(liste, true); };
  $("#q-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const r = await api("/api/netz/qualifikationen", { method: "POST", body: {
        qual_id: $("#qq").value, erworben: $("#qe").value || null, gueltig_bis: $("#qb").value || null } });
      zeigeMeine(r.qualifikationen); $("#q-err").textContent = ""; e.target.reset();
    } catch (err) { $("#q-err").textContent = err.message; }
  });
  $("#q-meine").addEventListener("click", async (e) => {
    const w = e.target.closest("[data-q-weg]");
    if (!w) return;
    zeigeMeine((await api("/api/netz/qualifikationen/" + encodeURIComponent(w.dataset.qWeg),
      { method: "DELETE" })).qualifikationen);
  });
  $("#q-fehlt").addEventListener("click", () => sheet("Kurs vorschlagen", `
    <form id="qv-form" class="stack">
      <div class="field"><label for="qv-name">Bezeichnung</label><input id="qv-name" maxlength="120" required></div>
      <div class="field"><label for="qv-her">Herausgeber (optional)</label><input id="qv-her" maxlength="80"
        placeholder="z. B. ERC, NAEMT, AHA"></div>
      <p class="tiny muted">Nach Freigabe durch die Administration ist der Kurs für alle wählbar.
      Bis dahin kannst nur du ihn eintragen.</p>
      <button class="btn-primary" type="submit">Vorschlagen</button>
    </form>`, (body) => $("#qv-form", body).addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api("/api/netz/katalog/qualifikationen", { method: "POST", body: {
        name: $("#qv-name", body).value, herausgeber: $("#qv-her", body).value } });
      closeSheet(); toast("Vorgeschlagen."); render();
    } catch (err) { toast(err.message); }
  })));
}

// ---------------------------------------------------------- Fortbildung

async function viewFortbildung() {
  const { query } = currentRoute();
  const jahr = Number(query.get("jahr")) || new Date().getFullYear();
  const [f, meine] = await Promise.all([api("/api/netz/fortbildungen?jahr=" + jahr),
    api("/api/netz/qualifikationen")]);
  app().innerHTML = `
    <div class="page-head"><h1>Logbuch</h1>
      <p class="muted small">Fortbildungsnachweis. Nur für dich, wie das Logbuch.</p></div>
    ${logbuchKopf("/fortbildung")}
    <div class="row spread" data-s="mt-md">
      <a class="btn-quiet small link-plain" href="#/fortbildung?jahr=${jahr - 1}">${jahr - 1}</a>
      <h2>${jahr}: ${String(f.summe).replace(".", ",")} Stunden</h2>
      <a class="btn-quiet small link-plain" href="#/fortbildung?jahr=${jahr + 1}">${jahr + 1}</a>
    </div>
    ${f.pflichten.length ? `<div class="stack" data-s="mt-md">${f.pflichten.map((p) => {
      const anteil = Math.min(1, p.ist / Math.max(1, p.soll));
      return `<div class="card flat pad-xs"><div class="spread"><strong class="small">${esc(p.name)}</strong>
        <span class="small">${String(p.ist).replace(".", ",")} von ${p.soll} h</span></div>
        <div class="fb-bar" role="progressbar" aria-label="${esc(p.name)}" aria-valuemin="0"
          aria-valuemax="${p.soll}" aria-valuenow="${p.ist}"><span data-anteil="${anteil}"></span></div></div>`;
    }).join("")}</div>` : `<p class="tiny muted" data-s="mt-sm">Für hinterlegte Funktionen mit jährlicher
      Fortbildungspflicht (etwa Praxisanleitung: 24 Stunden berufspädagogische Fortbildung im Jahr)
      erscheint hier der Stand.</p>`}
    <form id="fb-form" class="card pad-lg stack" data-s="mt-md">
      <h2>Fortbildung eintragen</h2>
      <div class="field"><label for="fb-t">Titel</label><input id="fb-t" maxlength="160" required></div>
      <div class="field-row">
        <div class="field"><label for="fb-d">Datum</label><input id="fb-d" type="date" required></div>
        <div class="field"><label for="fb-h">Stunden</label><input id="fb-h" type="number" min="0.25"
          max="200" step="0.25" required></div>
      </div>
      <div class="field"><label for="fb-q">Angerechnet auf (optional)</label>
        <select id="fb-q"><option value="">allgemein</option>${meine.qualifikationen.map((x) =>
          `<option value="${esc(x.qual_id)}">${esc(x.name)}</option>`).join("")}</select></div>
      <button class="btn-primary" type="submit">Eintragen</button>
      <p class="tiny muted" id="fb-err" role="alert"></p>
    </form>
    ${f.fortbildungen.length ? `<ul class="entry-list" data-s="mt-md">${f.fortbildungen.map((x) => `
      <li class="entry-row"><span class="grow"><strong>${esc(x.titel)}</strong>
        <span class="tiny muted np-sub">${esc(fmtDate(x.datum))} · ${String(x.stunden).replace(".", ",")} h${
          x.qualifikation ? " · " + esc(x.qualifikation) : ""}</span></span>
        <button type="button" class="btn-quiet small" data-fb-weg="${esc(x.id)}">Entfernen</button></li>`).join("")}</ul>` : ""}
    ${pageFoot()}`;
  app().querySelectorAll("[data-anteil]").forEach((n) => {
    n.style.width = (Number(n.dataset.anteil) * 100).toFixed(1) + "%";
  });
  $("#fb-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api("/api/netz/fortbildungen", { method: "POST", body: { titel: $("#fb-t").value,
        datum: $("#fb-d").value, stunden: Number($("#fb-h").value), qual_id: $("#fb-q").value || null } });
      toast("Eingetragen."); render();
    } catch (err) { $("#fb-err").textContent = err.message; }
  });
  app().querySelectorAll("[data-fb-weg]").forEach((b) => b.addEventListener("click", async () => {
    await api("/api/netz/fortbildungen/" + encodeURIComponent(b.dataset.fbWeg), { method: "DELETE" });
    render();
  }));
}

// ---------------------------------------------------- Kolleg*innen einladen

/* Mitglieder laden ein, die Administration entscheidet: aus der Einladung
   wird eine Bewerbung, in der das Mitglied schon als Kontakt steht. */
async function zeigeEinladungen(ziel) {
  if (!ziel) return;
  const r = await api("/api/netz/empfehlungen").catch(() => null);
  if (!r || !document.body.contains(ziel)) return;
  if (!r.moeglich && !r.empfehlungen.length) { ziel.remove(); return; }
  ziel.innerHTML = `
    <h2 class="sec">Kolleg*innen einladen</h2>
    <p class="tiny muted">Die eingeladene Person bewirbt sich über den Link in der Mail; du stehst
    dabei schon als Kontakt fest. Über die Aufnahme entscheidet die Administration.</p>
    ${r.moeglich ? `<button type="button" class="btn-primary small" id="ein-neu" data-s="mt-sm">Person einladen</button>` : ""}
    ${r.empfehlungen.length ? `<ul class="entry-list" data-s="mt-sm">${r.empfehlungen.map((x) => `
      <li class="entry-row"><span class="grow"><strong>${esc(x.name || x.email)}</strong>
        <span class="tiny muted np-sub">${x.name ? esc(x.email) + " · " : ""}${esc(x.status)}</span></span>
        ${x.status === "verschickt" ? `<button type="button" class="btn-quiet small"
          data-ein-weg="${esc(x.id)}">Zurückziehen</button>` : ""}</li>`).join("")}</ul>` : ""}`;
  const neu = $("#ein-neu", ziel);
  if (neu) neu.addEventListener("click", () => sheet("Person einladen", `
    <form id="ein-form" class="stack">
      <div class="field"><label for="ein-mail">E-Mail-Adresse</label>
        <input id="ein-mail" type="email" required maxlength="200" autocapitalize="none" spellcheck="false"></div>
      <div class="field"><label for="ein-name">Name (optional)</label>
        <input id="ein-name" maxlength="120"></div>
      <p class="tiny muted">Die Person bekommt eine Mail mit deinem Namen und einem Link zur
      Bewerbung, gültig 14 Tage. Lade nur Menschen ein, die du kennst und die in der
      Notfallversorgung arbeiten oder dafür ausgebildet werden.</p>
      <button class="btn-primary" type="submit">Einladung senden</button>
      <p class="tiny muted" id="ein-err" role="alert"></p>
    </form>`, (body) => $("#ein-form", body).addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api("/api/netz/empfehlungen", { method: "POST", body: {
        email: $("#ein-mail", body).value, name: $("#ein-name", body).value } });
      closeSheet(); toast("Einladung verschickt."); zeigeEinladungen(ziel);
    } catch (err) { $("#ein-err", body).textContent = err.message; }
  })));
  ziel.querySelectorAll("[data-ein-weg]").forEach((b) => b.addEventListener("click", async () => {
    await api("/api/netz/empfehlungen/" + encodeURIComponent(b.dataset.einWeg), { method: "DELETE" });
    zeigeEinladungen(ziel);
  }));
}
