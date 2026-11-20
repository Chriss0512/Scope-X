/* SCOPE X - Kompetenznetz
   Soziales Netz für beruflichen Support in der Notfallmedizin: Feed mit
   Algorithmus, Entdecken, Profile mit Chronik, Nachrichten, Medien.

   Die Datenschutzgrenze liegt im Server, nicht hier. Diese Datei zeigt
   nur an, was der Server herausgibt, und erklärt vorher, was geteilt wird.
   Einsatznummer, Fahrzeug, Schicht, Datum und Uhrzeit eines Einsatzes,
   Dosis und Notizen verlassen das Logbuch nie — auch dann nicht, wenn
   diese Datei manipuliert wird.

   Wird vor app.js geladen: die Routentabelle dort verweist auf die
   Ansichten hier. Helfer aus app.js (api, esc, sheet, toast …) werden erst
   beim Aufruf gebraucht. Eigene Konstanten tragen das Präfix NETZ_. */

"use strict";

const NETZ = { profil: null, zaehler: { mitteilungen: 0, nachrichten: 0, anfragen: 0 },
  stand: 0, poll: null, feedModus: "fuerdich" };

const NETZ_ICON = {
  herz: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M12 20.2s-7.8-4.6-7.8-10.2A4.4 4.4 0 0 1 12 7.3 4.4 4.4 0 0 1 19.8 10c0 5.6-7.8 10.2-7.8 10.2z"/></svg>`,
  herzVoll: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M12 20.2s-7.8-4.6-7.8-10.2A4.4 4.4 0 0 1 12 7.3 4.4 4.4 0 0 1 19.8 10c0 5.6-7.8 10.2-7.8 10.2z"/></svg>`,
  kommentar: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M20.2 11.6a8.2 8.2 0 0 1-11.7 7.4L3.8 20.2l1.3-4.4A8.2 8.2 0 1 1 20.2 11.6z"/></svg>`,
  repost: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 9.5V8a3 3 0 0 1 3-3h11m0 0-3-3m3 3-3 3M20 14.5V16a3 3 0 0 1-3 3H6m0 0 3 3m-3-3 3-3"/></svg>`,
  senden: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 3.5 10.2 13.3M21 3.5l-6.6 17-4.2-7.2L3 9.6z"/></svg>`,
  mehr: `<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.9"/><circle cx="12" cy="12" r="1.9"/><circle cx="19" cy="12" r="1.9"/></svg>`,
  schloss: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><rect x="5" y="10.5" width="14" height="10" rx="2.2"/><path d="M8.2 10.5V8a3.8 3.8 0 0 1 7.6 0v2.5"/></svg>`,
  raster: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="3.5" y="3.5" width="17" height="17" rx="1.5"/><path d="M9.2 3.5v17M14.8 3.5v17M3.5 9.2h17M3.5 14.8h17"/></svg>`,
  chronik: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M7 4v16"/><circle cx="7" cy="7" r="2"/><circle cx="7" cy="16" r="2"/><path d="M11 7h9M11 16h9M11 11.5h6"/></svg>`,
  kompetenz: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m12 3.5 2.5 5.2 5.7.8-4.1 4 1 5.6-5.1-2.7-5.1 2.7 1-5.6-4.1-4 5.7-.8z"/></svg>`,
  info: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5M12 7.6v.2"/></svg>`,
  video: `<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5.5v13l10.5-6.5z"/></svg>`,
  stapel: `<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 3h11a3 3 0 0 1 3 3v11h-2V6a1 1 0 0 0-1-1H7z"/><rect x="3" y="7" width="14" height="14" rx="2.5"/></svg>`,
  zurueck: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 5 8 12l7 7"/></svg>`,
  zahnrad: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 13.5a7.6 7.6 0 0 0 0-3l2-1.6-2-3.4-2.4.9a7.5 7.5 0 0 0-2.6-1.5L14 2.4h-4l-.4 2.5A7.5 7.5 0 0 0 7 6.4l-2.4-.9-2 3.4 2 1.6a7.6 7.6 0 0 0 0 3l-2 1.6 2 3.4 2.4-.9a7.5 7.5 0 0 0 2.6 1.5l.4 2.5h4l.4-2.5a7.5 7.5 0 0 0 2.6-1.5l2.4.9 2-3.4z"/></svg>`,
  bild: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><circle cx="9" cy="10" r="1.8"/><path d="m4 17.5 4.8-4.6 3.4 3 2.8-2.4 5 4.4"/></svg>`,
  x: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>`,
};

const NETZ_FALL = {
  selten: "Seltene Situation", komplikation: "Komplikation", lernfall: "Lernfall",
};
const NETZ_ART = {
  beitrag: "", wissen: "Wissen", fall: "Fallbericht", algorithmus: "Algorithmus",
  kompetenz: "Kompetenz", repost: "", fallvorstellung: "Fallvorstellung",
};
const NETZ_EINTRAG = {
  station: "Werdegang", ausbildung: "Ausbildung", zertifikat: "Zertifikate und Kurse",
  sprache: "Sprachen",
};
const NETZ_ROLLEN = {
  kollegial: "Kollegial gesehen", praxisanleitung: "Als Praxisanleitung",
};

// ---------------------------------------------------------------- Helfer

/* Zeit wie in Bildnetzwerken: relativ, ab fünf Wochen nur Monat und Jahr.
   Ein genaues Datum unter einem Fallbericht legte den Einsatztag nahe. */
function relZeit(iso, kurz = false) {
  const t = Date.parse(iso);
  if (!t) return "";
  const s = (Date.now() - t) / 1000;
  if (s < 0) {
    const tage = Math.ceil(-s / 86400);
    return tage <= 1 ? "morgen" : `in ${tage} Tagen`;
  }
  if (s < 60) return kurz ? "jetzt" : "gerade eben";
  const min = Math.floor(s / 60);
  if (min < 60) return kurz ? `${min} Min.` : `vor ${min} Min.`;
  const std = Math.floor(min / 60);
  if (std < 24) return kurz ? `${std} Std.` : `vor ${std} Std.`;
  const tage = Math.floor(std / 24);
  if (tage < 7) return kurz ? `${tage} T.` : (tage === 1 ? "gestern" : `vor ${tage} Tagen`);
  const wochen = Math.floor(tage / 7);
  if (tage < 35) return kurz ? `${wochen} Wo.` : (wochen === 1 ? "vor 1 Woche" : `vor ${wochen} Wochen`);
  return new Date(t).toLocaleDateString("de-DE", { month: "long", year: "numeric" });
}

function initialenVon(name) {
  const teile = String(name || "?").trim().split(/\s+/);
  return ((teile[0] || "?")[0] + (teile.length > 1 ? teile[teile.length - 1][0] : ""))
    .toUpperCase();
}

/* Farbe des Initialenkreises aus der Kennung: dieselbe Person sieht
   überall gleich aus. Über data-farbe, ein style-Attribut blockiert die CSP. */
function farbeVon(id) {
  let h = 0;
  for (const ch of String(id || "")) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return h % 4;
}

function avatarHtml(p, groesse = "m") {
  if (p && p.avatar_id) {
    return `<img class="av av-${groesse}" src="/api/netz/medien/${esc(p.avatar_id)}"
      alt="" loading="lazy" decoding="async">`;
  }
  return `<span class="av av-${groesse} ini" data-farbe="${farbeVon(p && p.id)}"
    aria-hidden="true">${esc(initialenVon(p && p.name))}</span>`;
}

function ichId() { return state.auth && state.auth.user && state.auth.user.id; }

async function netzProfil(neu = false) {
  if (!NETZ.profil || neu) {
    NETZ.profil = await api("/api/netz/profil");
    zeigeNavAvatar();
  }
  return NETZ.profil;
}

function zeigeNavAvatar() {
  const box = document.getElementById("nav-av");
  if (!box || !NETZ.profil || !NETZ.profil.avatar_id) return;
  box.innerHTML = avatarHtml({ id: NETZ.profil.id, avatar_id: NETZ.profil.avatar_id }, "nav");
}

/* Zähler für Mitteilungen und Nachrichten. Höchstens alle 30 Sekunden,
   beim Seitenwechsel angestoßen — kein Dauerabruf im Hintergrund. */
async function mitteilungsZaehler(sofort = false) {
  if (!state.auth || !state.auth.authenticated) return;
  if (!NETZ.profil) netzProfil().catch(() => {});
  if (!sofort && Date.now() - NETZ.stand < 30000) { zeigeZaehler(); return; }
  NETZ.stand = Date.now();
  try { NETZ.zaehler = await api("/api/netz/zaehler"); } catch (_) { /* Komfort */ }
  zeigeZaehler();
}

function zeigeZaehler() {
  const z = NETZ.zaehler || {};
  // Folgeanfragen stehen seit 4.5.0 unter Netzwerk und zählen dort.
  const werte = { mitteilungen: z.mitteilungen || 0, anfragen: z.anfragen || 0,
    nachrichten: z.nachrichten || 0 };
  document.querySelectorAll("[data-zaehler]").forEach((n) => {
    const w = werte[n.dataset.zaehler] || 0;
    n.textContent = w > 9 ? "9+" : String(w || "");
    n.hidden = !w;
  });
}

/* Seitenwechsel beendet laufende Abfragen eines offenen Gesprächs. */
function netzAufraeumen() {
  if (NETZ.poll) { clearInterval(NETZ.poll); NETZ.poll = null; }
}

/* Seitenverhältnis kommt aus den Daten. style-Attribute blockiert die CSP;
   die CSSOM-Eigenschaft ist erlaubt. */
function setzeVerhaeltnis(root) {
  root.querySelectorAll("[data-ar]").forEach((n) => {
    const v = Number(n.dataset.ar);
    if (v > 0) n.style.aspectRatio = String(Math.min(1.91, Math.max(0.8, v)));
  });
}

function zahl(n) {
  return Number(n || 0).toLocaleString("de-DE");
}

const NETZ_DATENSCHUTZ = `
  <details class="privacy-box">
    <summary><strong>Was privat bleibt</strong></summary>
    <p class="tiny">Datum und Uhrzeit des Einsatzes, Einsatznummer, Fahrzeug,
    Schicht, Dosierungen und Notizen verlassen dein Logbuch nie. Texte mit
    einer eigenen Einsatznummer, einem eigenen Fahrzeug, einem Einsatztag
    oder einer Uhrzeit lehnt SCOPE X ab.</p>
    <p class="tiny">Teile Lernerfahrung, nicht den Einsatz: nichts, was auf
    Patient*innen, Ort oder Zeitpunkt schließen lässt. Tipp: mit Abstand zum
    Einsatz posten.</p>
  </details>`;

// ------------------------------------------------------------- Beiträge

function kompetenzBlock(k) {
  if (!k || (!(k.massnahmen || []).length && !(k.medikamente || []).length)) return "";
  const massnahmen = (k.massnahmen || []).map((m) => `
    <li class="kz-row" data-cat="${esc(m.kategorie)}">
      <span class="cat-badge">${esc(m.kategorie)}</span>
      <span class="grow"><strong>${esc(m.name)}</strong>${
        m.rolle && m.rolle !== "selbst durchgeführt"
          ? `<span class="tiny muted"> · ${esc(m.rolle)}</span>` : ""}</span>
      ${statusBadge(m.ergebnis)}
    </li>`).join("");
  const medikamente = (k.medikamente || []).map((m) => `
    <li class="kz-row med">
      ${diviLabel({ name: m.name, divi_group: m.divi_gruppe })}
      <span class="grow tiny muted">${esc(m.weg)}</span>
      ${m.ergebnis ? statusBadge(m.ergebnis) : ""}
    </li>`).join("");
  const zusatz = [
    k.naca ? `<span class="chip static">NACA ${esc(k.naca)}</span>` : "",
    ...(k.zek || []).map((z) => `<span class="chip static zek">ZEK: ${esc(z)}</span>`),
  ].join("");
  return `
    <div class="kompetenz">
      <div class="kz-head tiny">Aus dem Logbuch</div>
      <ul class="kz-list">${massnahmen}${medikamente}</ul>
      ${zusatz ? `<div class="row wrap" data-s="gap-sm mt-sm">${zusatz}</div>` : ""}
    </div>`;
}

function linkBlock(l) {
  if (!l) return "";
  let host = "";
  try { host = new URL(l.url).hostname.replace(/^www\./, ""); } catch (_) { host = ""; }
  // nofollow und noreferrer: der Zielserver erfährt nicht, woher der Klick kam.
  return `
    <a class="link-card" href="${esc(l.url)}" target="_blank" rel="noopener noreferrer nofollow">
      <span class="lc-kind tiny">${esc(l.quelle || host)}</span>
      <strong>${esc(l.titel)}</strong>
      <span class="tiny muted">${esc(host)} ↗</span>
    </a>`;
}

function medienHtml(medien) {
  if (!medien || !medien.length) return "";
  const erster = medien[0];
  const slides = medien.map((m, i) => `
    <figure class="np-slide">${m.art === "video"
      ? `<video src="/api/netz/medien/${esc(m.id)}" poster="/api/netz/medien/${esc(m.id)}/vorschau"
          controls playsinline preload="none" aria-label="Video ${i + 1} von ${medien.length}"></video>`
      : `<img src="/api/netz/medien/${esc(m.id)}" alt="Bild ${i + 1} von ${medien.length}"
          loading="lazy" decoding="async">`}</figure>`).join("");
  return `
    <div class="np-media" data-ar="${erster.breite && erster.hoehe ? erster.breite / erster.hoehe : 1}">
      <div class="np-track" tabindex="0" role="group"
        aria-label="${medien.length === 1 ? "Medium" : `${medien.length} Medien, zum Blättern wischen oder Pfeiltasten`}">${slides}</div>
      ${medien.length > 1 ? `<span class="np-count" aria-hidden="true">1/${medien.length}</span>` : ""}
    </div>
    ${medien.length > 1 ? `<div class="np-dots" aria-hidden="true">${medien.map((_, i) =>
      `<span${i === 0 ? ' class="on"' : ""}></span>`).join("")}</div>` : ""}`;
}

function inhaltHtml(b) {
  const d = b.details || {};
  if (b.art === "fall") {
    return `
      <div class="np-case" data-kat="${esc(d.kategorie || "lernfall")}">
        <div class="case-kat">${esc(NETZ_FALL[d.kategorie] || "Fallbericht")}</div>
        <h2 class="case-title">${esc(b.titel)}</h2>
        ${d.besonderheit ? `<div class="case-sec"><span>Was war besonders</span>
          <p>${esc(d.besonderheit)}</p></div>` : ""}
        ${d.gut ? `<div class="case-sec"><span>Was lief gut</span><p>${esc(d.gut)}</p></div>` : ""}
        ${d.anders ? `<div class="case-sec"><span>Was ich anders machen würde</span>
          <p>${esc(d.anders)}</p></div>` : ""}
      </div>
      ${kompetenzBlock(b.kompetenz)}`;
  }
  if (b.art === "algorithmus") {
    return `
      <div class="np-algo">
        <div class="case-kat">Algorithmus${d.stand ? " · Stand " + esc(d.stand) : ""}</div>
        <h2 class="case-title">${esc(b.titel)}</h2>
        <p class="tiny muted">Quelle: ${esc(d.quelle || "")}${
          d.geltung ? " · " + esc(d.geltung) : ""}</p>
      </div>
      ${linkBlock(b.link)}`;
  }
  if (b.art === "fallvorstellung") return fallvorstellungHtml(b);
  if (b.art === "wissen") return linkBlock(b.link);
  if (b.art === "kompetenz") return kompetenzBlock(b.kompetenz);
  return "";
}

function kopfHtml(b, klein = false) {
  const unter = [
    b.art === "wissen" || b.art === "kompetenz" ? NETZ_ART[b.art] : "",
    b.autor.headline,
  ].filter(Boolean).join(" · ");
  return `
    <header class="np-head">
      <a href="#/person/${esc(b.autor.id)}" class="np-who link-plain">
        ${avatarHtml(b.autor, klein ? "s" : "m")}
        <span class="grow">
          <span class="np-name"><strong>${esc(b.autor.name)}</strong>${klein ? "" : abzeichenHtml(b.autor, 2)}
            <span class="muted"> · ${esc(relZeit(b.erstellt, true))}</span></span>
          ${unter ? `<span class="tiny muted np-sub">${esc(unter)}</span>` : ""}
        </span>
      </a>
      ${klein ? "" : `<button type="button" class="icon-btn flat" data-akt="menue"
        aria-label="Weitere Aktionen zum Beitrag">${NETZ_ICON.mehr}</button>`}
    </header>`;
}

/* Hashtags und Erwähnungen werden zu Links. Erst escapen, dann ersetzen:
   im Ergebnis steht nur Markup, das hier erzeugt wurde. Verlinkt wird nur
   "@Name" von Personen, die der Server als erwähnt zurückgibt. */
function textMitTags(text, erwaehnt = []) {
  let html = esc(text).replace(/#([0-9A-Za-zÄÖÜäöüß_-]{2,40})/g,
    (_, t) => `<a href="#/tag/${encodeURIComponent(t.toLowerCase())}" class="tag">#${t}</a>`);
  [...(erwaehnt || [])].sort((a, b) => b.name.length - a.name.length).forEach((p) => {
    const muster = "@" + esc(p.name);
    html = html.split(muster).join(
      `<a href="#/person/${esc(p.id)}" class="erwaehnung">${muster}</a>`);
  });
  return html;
}

/* Auswahl nach "@" in einem Text- oder Eingabefeld. Angeboten werden nur
   Konten, denen man folgt; der Server prüft beim Speichern noch einmal.
   Tastatur: Pfeiltasten wählen, Enter oder Tab übernimmt, Escape schließt. */
function erwaehnungsFeld(feld, postId = null) {
  const gewaehlt = new Map();
  const liste = document.createElement("ul");
  const lid = feld.id + "-erw";
  liste.id = lid;
  liste.className = "erw-liste";
  liste.setAttribute("role", "listbox");
  liste.setAttribute("aria-label", "Person erwähnen");
  liste.hidden = true;
  feld.insertAdjacentElement("afterend", liste);
  feld.setAttribute("aria-autocomplete", "list");
  feld.setAttribute("aria-controls", lid);
  feld.setAttribute("aria-expanded", "false");
  let treffer = [], aktiv = -1, anfang = -1, laeuft = 0;

  const schliessen = () => {
    liste.hidden = true; treffer = []; aktiv = -1;
    feld.setAttribute("aria-expanded", "false");
    feld.removeAttribute("aria-activedescendant");
  };
  const zeigen = () => {
    liste.innerHTML = treffer.map((p, i) => `
      <li role="option" id="${lid}-${i}" data-i="${i}" aria-selected="${i === aktiv}">
        ${avatarHtml(p, "s")}<span><strong>${esc(p.name)}</strong>
        <span class="tiny muted">${esc(p.headline || "")}</span></span></li>`).join("");
    liste.hidden = !treffer.length;
    feld.setAttribute("aria-expanded", String(!!treffer.length));
    if (aktiv >= 0) feld.setAttribute("aria-activedescendant", `${lid}-${aktiv}`);
    else feld.removeAttribute("aria-activedescendant");
  };
  const uebernehmen = (p) => {
    const ende = feld.selectionStart;
    const einsetzen = `@${p.name} `;
    feld.value = feld.value.slice(0, anfang) + einsetzen + feld.value.slice(ende);
    const pos = anfang + einsetzen.length;
    feld.setSelectionRange(pos, pos);
    gewaehlt.set(p.id, p.name);
    schliessen();
    feld.focus();
  };
  feld.addEventListener("input", async () => {
    const vor = feld.value.slice(0, feld.selectionStart);
    const m = vor.match(/(^|\s)@([^\s@]{0,30})$/);
    if (!m) { schliessen(); return; }
    anfang = vor.length - m[2].length - 1;
    const nr = ++laeuft;
    const pfad = `/api/netz/erwaehnbar?q=${encodeURIComponent(m[2])}${
      postId ? `&post_id=${encodeURIComponent(postId)}` : ""}`;
    const r = await api(pfad).catch(() => ({ personen: [] }));
    if (nr !== laeuft) return;
    treffer = r.personen; aktiv = treffer.length ? 0 : -1;
    zeigen();
  });
  feld.addEventListener("keydown", (e) => {
    if (liste.hidden) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      aktiv = (aktiv + (e.key === "ArrowDown" ? 1 : treffer.length - 1)) % treffer.length;
      zeigen();
    } else if ((e.key === "Enter" || e.key === "Tab") && aktiv >= 0) {
      e.preventDefault(); uebernehmen(treffer[aktiv]);
    } else if (e.key === "Escape") {
      e.preventDefault(); e.stopPropagation(); schliessen();
    }
  });
  liste.addEventListener("mousedown", (e) => {
    const li = e.target.closest("[data-i]");
    if (li) { e.preventDefault(); uebernehmen(treffer[Number(li.dataset.i)]); }
  });
  feld.addEventListener("blur", () => setTimeout(schliessen, 150));
  return {
    // Nur wer noch mit "@Name" im Text steht, gilt als erwähnt.
    ids: () => [...gewaehlt].filter(([, name]) => feld.value.includes("@" + name))
      .map(([id]) => id),
    leeren: () => gewaehlt.clear(),
  };
}

function captionHtml(b, mitName = true) {
  if (!b.text) return "";
  const lang = b.text.length > 220;
  return `<div class="np-caption${lang ? " gekuerzt" : ""}">${mitName
    ? `<strong>${esc(b.autor.name)}</strong> ` : ""}<span class="np-text">${
    textMitTags(b.text, b.erwaehnt)}</span>${lang ? ` <button type="button" class="link-btn muted"
    data-akt="mehr-text">mehr</button>` : ""}</div>`;
}

function aktionenHtml(b) {
  return `
    <div class="np-actions">
      <button type="button" class="act${b.ich_like ? " an" : ""}" data-akt="like"
        aria-pressed="${b.ich_like}" aria-label="Gefällt mir">${
        b.ich_like ? NETZ_ICON.herzVoll : NETZ_ICON.herz}</button>
      <button type="button" class="act" data-akt="kommentare"
        aria-label="Kommentieren">${NETZ_ICON.kommentar}</button>
      <button type="button" class="act${b.ich_repost ? " an-r" : ""}" data-akt="repost"
        aria-label="${b.teilbar ? "Repost" : "Repost nicht möglich"}"
        ${b.teilbar && !b.eigen && !b.ich_repost ? "" : "disabled"}>${NETZ_ICON.repost}</button>
      <button type="button" class="act" data-akt="senden"
        aria-label="Senden">${NETZ_ICON.senden}</button>
      <button type="button" class="act merken${b.gemerkt ? " an" : ""}" data-akt="merken"
        aria-pressed="${!!b.gemerkt}" aria-label="Speichern">${
        b.gemerkt ? NETZ_ICON_GEMERKT : NETZ_ICON_MERKEN}</button>
    </div>
    <div class="np-stats small">
      ${b.likes ? `<button type="button" class="link-btn" data-akt="likes"><strong>${
        b.likes === 1 ? "Gefällt 1 Mal" : `Gefällt ${zahl(b.likes)} Mal`}</strong></button>` : ""}
      ${b.reposts ? `<span class="muted">${b.reposts === 1 ? "1 Repost" : `${zahl(b.reposts)} Reposts`}</span>` : ""}
    </div>`;
}

function postHtml(b) {
  const fuss = `
    ${b.kommentare_aus ? `<p class="tiny muted np-kaus">Kommentare ${
      b.kommentare_gesperrt ? "von der Administration geschlossen" : "ausgeschaltet"}.</p>` : ""}
    ${b.kommentare ? `<button type="button" class="link-btn muted np-allk" data-akt="kommentare">${
      b.kommentare === 1 ? "1 Kommentar ansehen" : `Alle ${b.kommentare} Kommentare ansehen`}</button>` : ""}
    <div class="np-zeit tiny muted">${esc(relZeit(b.erstellt))}</div>`;
  if (b.art === "repost") {
    const o = b.original || {};
    return `
      <article class="npost repost" data-post="${esc(b.id)}" data-eigen="${b.eigen}"
        data-mod="${b.darf_moderieren}" data-kaus="${b.kommentare_aus}"
        data-kschalt="${b.darf_kommentare_schalten}" data-kgesperrt="${b.kommentare_gesperrt}">
        <div class="rp-line small">${NETZ_ICON.repost}
          <a href="#/person/${esc(b.autor.id)}" class="link-plain grow"><strong>${esc(b.autor.name)}</strong>
          <span class="muted">hat geteilt · ${esc(relZeit(b.erstellt, true))}</span></a>
          <button type="button" class="icon-btn flat" data-akt="menue"
            aria-label="Weitere Aktionen zum Repost">${NETZ_ICON.mehr}</button></div>
        ${b.text ? `<div class="np-caption rp-text"><span class="np-text">${textMitTags(b.text, b.erwaehnt)}</span></div>` : ""}
        ${o.nicht_verfuegbar
          ? `<div class="rp-gone small muted">Dieser Beitrag ist nicht mehr verfügbar.</div>`
          : `<div class="rp-orig">${kopfHtml(o, true)}
              ${inhaltHtml(o)}${medienHtml(o.medien)}${captionHtml(o, false)}
              <a class="tiny link-plain rp-open" href="#/beitrag/${esc(o.id)}">Original ansehen</a></div>`}
        ${aktionenHtml(b)}${fuss}
      </article>`;
  }
  return `
    <article class="npost" data-post="${esc(b.id)}" data-eigen="${b.eigen}"
      data-mod="${b.darf_moderieren}" data-kaus="${b.kommentare_aus}"
      data-kschalt="${b.darf_kommentare_schalten}" data-kgesperrt="${b.kommentare_gesperrt}">
      ${kopfHtml(b)}
      ${b.geplant ? `<div class="np-plan tiny">Geplant · erscheint ${esc(relZeit(b.erstellt))}.
        Bis dahin siehst nur du ihn.</div>` : ""}
      ${b.entfernt ? `<div class="notice warn">Von der Administration entfernt${
        b.entfernt_grund ? `: ${esc(b.entfernt_grund)}` : "."} Nur du siehst diesen Beitrag noch.</div>` : ""}
      ${inhaltHtml(b)}
      ${medienHtml(b.medien)}
      ${aktionenHtml(b)}
      ${captionHtml(b)}
      ${themenChipsHtml(b)}
      ${b.art === "algorithmus" ? `<p class="tiny muted np-hinweis">Geteilt von einem Mitglied,
        keine Empfehlung von SCOPE X. Maßgeblich ist die SOP deines ÄLRD.</p>` : ""}
      ${fuss}
    </article>`;
}

/* Ein Zuhörer für alle Beiträge eines Bereichs. Gebunden an den frisch
   gerenderten Bereich, nie an #app: der überdauert jeden Seitenwechsel. */
function bindePosts(bereich) {
  setzeVerhaeltnis(bereich);
  bindeKarussell(bereich);
  if (bereich.dataset.gebunden) return;
  bereich.dataset.gebunden = "1";

  bereich.addEventListener("click", async (e) => {
    const knopf = e.target.closest("[data-akt]");
    if (!knopf || !bereich.contains(knopf)) return;
    const karte = knopf.closest("[data-post]");
    if (!karte) return;
    e.preventDefault();
    const id = karte.dataset.post;
    const akt = knopf.dataset.akt;
    try {
      if (akt === "like") {
        const an = knopf.getAttribute("aria-pressed") === "true";
        knopf.setAttribute("aria-pressed", String(!an));
        knopf.classList.toggle("an", !an);
        knopf.innerHTML = !an ? NETZ_ICON.herzVoll : NETZ_ICON.herz;
        if (!an) { knopf.classList.add("pop"); setTimeout(() => knopf.classList.remove("pop"), 320); }
        const r = await api(`/api/netz/beitraege/${encodeURIComponent(id)}/like`,
          { method: an ? "DELETE" : "PUT" });
        const stats = $(".np-stats", karte);
        const rest = stats.querySelector("span");
        stats.innerHTML = (r.likes ? `<button type="button" class="link-btn" data-akt="likes"><strong>${
          r.likes === 1 ? "Gefällt 1 Mal" : `Gefällt ${zahl(r.likes)} Mal`}</strong></button>` : "")
          + (rest ? rest.outerHTML : "");
      } else if (akt === "kommentare") {
        kommentarSheet(id, karte);
      } else if (akt === "repost") {
        repostSheet(id, knopf);
      } else if (akt === "senden") {
        sendenSheet(id);
      } else if (akt === "merken") {
        const an = knopf.getAttribute("aria-pressed") === "true";
        await api(`/api/netz/beitraege/${encodeURIComponent(id)}/merken`, { method: an ? "DELETE" : "PUT" });
        knopf.setAttribute("aria-pressed", String(!an));
        knopf.classList.toggle("an", !an);
        knopf.innerHTML = an ? NETZ_ICON_MERKEN : NETZ_ICON_GEMERKT;
        toast(an ? "Nicht mehr gespeichert." : "Gespeichert. Zu finden unter Profil → Gespeichert.");
      } else if (akt === "likes") {
        personenSheet("Gefällt", `/api/netz/beitraege/${encodeURIComponent(id)}/likes`);
      } else if (akt === "mehr-text") {
        knopf.closest(".np-caption").classList.remove("gekuerzt");
        knopf.remove();
      } else if (akt === "menue") {
        beitragMenue(karte);
      }
    } catch (err) { toast(err.message); }
  });
}

function bindeKarussell(bereich) {
  bereich.querySelectorAll(".np-track:not([data-kar])").forEach((track) => {
    track.dataset.kar = "1";
    const media = track.closest(".np-media");
    const dots = media.nextElementSibling && media.nextElementSibling.classList.contains("np-dots")
      ? media.nextElementSibling.children : null;
    const zaehler = $(".np-count", media);
    if (!dots && !zaehler) return;
    track.addEventListener("scroll", () => {
      const i = Math.round(track.scrollLeft / Math.max(1, track.clientWidth));
      if (dots) [...dots].forEach((p, j) => p.classList.toggle("on", i === j));
      if (zaehler) zaehler.textContent = `${i + 1}/${track.children.length}`;
    }, { passive: true });
  });
}

function beitragDaten(id) {
  return api("/api/netz/beitraege/" + encodeURIComponent(id));
}

function beitragMenue(karte) {
  const id = karte.dataset.post;
  const eigen = karte.dataset.eigen === "true";
  const mod = karte.dataset.mod === "true";
  const kaus = karte.dataset.kaus === "true";
  const schalten = karte.dataset.kschalt === "true"
    && !(kaus && karte.dataset.kgesperrt === "true" && !isAdmin());
  sheet("Beitrag", `
    <div class="menu-list">
      ${schalten ? `<button type="button" id="bm-kaus">${kaus ? "Kommentare einschalten"
        : "Kommentare ausschalten"}</button>` : ""}
      ${karte.dataset.warum !== undefined ? `<button type="button" id="bm-warum">Warum sehe ich das?</button>` : ""}
      <a href="#/beitrag/${esc(id)}" class="link-plain" id="bm-oeffnen">Zum Beitrag</a>
      ${eigen ? `<button type="button" class="danger" id="bm-loeschen">Löschen</button>` : `
        <button type="button" id="bm-weg">Nicht interessiert</button>
        <button type="button" class="danger" id="bm-melden">Melden</button>`}
      ${mod ? `<button type="button" class="danger" id="bm-mod">Als Administration entfernen</button>` : ""}
    </div>`, (body) => {
    $("#bm-oeffnen", body).addEventListener("click", closeSheet);
    const ka = $("#bm-kaus", body);
    if (ka) ka.addEventListener("click", async () => {
      try {
        await api(`/api/netz/beitraege/${encodeURIComponent(id)}/kommentare-aus`,
          { method: "PUT", body: { aus: !kaus } });
        closeSheet(); toast(kaus ? "Kommentare eingeschaltet." : "Kommentare ausgeschaltet.");
        render();
      } catch (err) { toast(err.message); }
    });
    const warum = $("#bm-warum", body);
    if (warum) warum.addEventListener("click", () => {
      const gruende = (karte.dataset.warum || "").split("|").filter(Boolean);
      sheet("Warum sehe ich das?", `
        <ul class="check-list small">${(gruende.length ? gruende : ["Neu im Netz"])
          .map((g) => `<li>${esc(g)}</li>`).join("")}</ul>
        <p class="tiny muted" data-s="mt-md">„Für dich“ ordnet nach Aktualität, Resonanz, Nähe
        zur Person, Art des Beitrags und Relevanz für dein Lernen. Fallberichte zu seltenen
        Situationen und Komplikationen, offene Fallvorstellungen, Themen, denen du folgst, und
        Maßnahmen, die du selbst selten dokumentierst, steigen nach oben. Schon Gesehenes und
        Personen, deren Beiträge du ausgeblendet hast, sinken. Dein Logbuch fließt nur als Anzahl
        je Maßnahme ein und nur in deine eigene Reihenfolge.</p>`);
    });
    const l = $("#bm-loeschen", body);
    if (l) l.addEventListener("click", async () => {
      if (!confirm("Diesen Beitrag löschen? Kommentare, Gefällt mir und Medien gehen mit.")) return;
      await api("/api/netz/beitraege/" + encodeURIComponent(id), { method: "DELETE" });
      closeSheet(); karte.remove(); toast("Beitrag gelöscht.");
    });
    const w = $("#bm-weg", body);
    if (w) w.addEventListener("click", async () => {
      await api(`/api/netz/beitraege/${encodeURIComponent(id)}/ausblenden`, { method: "POST" });
      closeSheet(); karte.remove(); toast("Ausgeblendet. Du siehst weniger davon.");
    });
    const m = $("#bm-melden", body);
    if (m) m.addEventListener("click", () => meldenSheet(id));
    const mo = $("#bm-mod", body);
    if (mo) mo.addEventListener("click", () => moderierenSheet(id, karte));
  });
}

function meldenSheet(id) {
  sheet("Melden", `
    <p class="small">Melde einen Beitrag, wenn er auf Patient*innen, einen Einsatzort oder
    einen Zeitpunkt schließen lässt oder andere verletzt. Die Administration erhält Zugriff
    auf genau diesen Beitrag und entscheidet.</p>
    <button type="button" class="btn-primary btn-lg" id="melden-ok" data-s="mt-md">Melden</button>`,
  (body) => {
    $("#melden-ok", body).addEventListener("click", async () => {
      try {
        await api(`/api/netz/beitraege/${encodeURIComponent(id)}/melden`, { method: "POST" });
        closeSheet(); toast("Gemeldet. Danke.");
      } catch (err) { toast(err.message); }
    });
  });
}

function moderierenSheet(id, karte) {
  sheet("Beitrag entfernen", `
    <p class="small muted">Der Beitrag verschwindet für alle außer der Verfasserin oder dem
    Verfasser. Der Grund wird mitgeteilt und im Änderungsprotokoll festgehalten.</p>
    <form id="mod-form" class="stack" data-s="mt-md">
      <div class="field"><label for="mg">Grund (mindestens fünf Zeichen)</label>
        <textarea id="mg" maxlength="300" required></textarea></div>
      <button class="btn-primary btn-danger" type="submit">Entfernen</button>
      <p class="tiny muted" id="mod-err"></p>
    </form>`, (body) => {
    $("#mod-form", body).addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await api(`/api/netz/beitraege/${encodeURIComponent(id)}/moderieren`,
          { method: "POST", body: { grund: $("#mg", body).value } });
        closeSheet(); karte.remove(); toast("Beitrag entfernt.");
      } catch (err) { $("#mod-err", body).textContent = err.message; }
    });
  });
}

// ------------------------------------------------------------ Kommentare

function kommentarListeHtml(liste, markieren = false) {
  if (!liste.length) return `<p class="small muted k-leer">Noch keine Kommentare.</p>`;
  return `<ul class="k-list">${liste.map((k) => `
    <li class="k-item${k.hilfreich ? " hilfreich" : ""}">
      <a href="#/person/${esc(k.autor.id)}" class="link-plain"
        aria-label="Profil von ${esc(k.autor.name)}">${avatarHtml(k.autor, "s")}</a>
      <div class="grow">
        <div class="small"><strong>${esc(k.autor.name)}</strong> <span class="np-text">${
          textMitTags(k.text, k.erwaehnt)}</span></div>
        ${k.hilfreich ? `<div class="tiny k-hilf">Hilfreiche Antwort</div>` : ""}
        <div class="tiny muted k-meta">${esc(relZeit(k.erstellt, true))}${k.darf_entfernen
          ? ` · <button type="button" class="link-btn muted" data-k-del="${esc(k.id)}">Entfernen</button>` : ""}${
          markieren ? ` · <button type="button" class="link-btn muted" data-k-hilf="${esc(k.id)}"
            data-an="${k.hilfreich}">${k.hilfreich ? "Markierung aufheben" : "Als hilfreich markieren"}</button>` : ""}</div>
      </div>
    </li>`).join("")}</ul>`;
}

async function kommentarSheet(postId, karte) {
  const k = await api(`/api/netz/beitraege/${encodeURIComponent(postId)}/kommentare`);
  sheet("Kommentare", `
    <div id="k-liste">${kommentarListeHtml(k.kommentare, k.darf_markieren)}</div>
    ${k.aus ? `<p class="small muted">Für diesen Beitrag sind die Kommentare ausgeschaltet.</p>` : ""}
    ${canWrite() && !k.aus ? `
    <form class="k-form" id="k-form">
      ${avatarHtml({ id: ichId(), name: (NETZ.profil || {}).name, avatar_id: (NETZ.profil || {}).avatar_id }, "s")}
      <label class="sr-only" for="k-text">Kommentar</label>
      <span class="erw-anker"><input id="k-text" maxlength="1000" placeholder="Kommentar schreiben, @ für Erwähnung" autocomplete="off" required></span>
      <button class="link-btn strong" type="submit">Posten</button>
    </form>
    <p class="tiny muted" id="k-err" role="alert"></p>` : ""}`, (body) => {
    body.closest(".sheet").classList.add("tall");
    const zeige = (liste) => {
      $("#k-liste", body).innerHTML = kommentarListeHtml(liste, k.darf_markieren);
      const alle = karte && $(".np-allk", karte);
      if (alle) alle.textContent = liste.length === 1 ? "1 Kommentar ansehen"
        : `Alle ${liste.length} Kommentare ansehen`;
    };
    body.addEventListener("click", async (e) => {
      const hilf = e.target.closest("[data-k-hilf]");
      if (hilf) {
        const pfad = `/api/netz/beitraege/${encodeURIComponent(postId)}/hilfreich`;
        const r = await api(hilf.dataset.an === "true" ? pfad
          : `${pfad}/${encodeURIComponent(hilf.dataset.kHilf)}`,
        { method: hilf.dataset.an === "true" ? "DELETE" : "PUT" });
        zeige(r.kommentare);
        return;
      }
      const del = e.target.closest("[data-k-del]");
      if (!del) return;
      await api("/api/netz/kommentare/" + encodeURIComponent(del.dataset.kDel), { method: "DELETE" });
      zeige((await api(`/api/netz/beitraege/${encodeURIComponent(postId)}/kommentare`)).kommentare);
    });
    const form = $("#k-form", body);
    const erw = form ? erwaehnungsFeld($("#k-text", body), postId) : null;
    if (form) form.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const r = await api(`/api/netz/beitraege/${encodeURIComponent(postId)}/kommentare`,
          { method: "POST", body: { text: $("#k-text", body).value, erwaehnungen: erw.ids() } });
        $("#k-text", body).value = "";
        erw.leeren();
        $("#k-err", body).textContent = "";
        zeige(r.kommentare);
      } catch (err) { $("#k-err", body).textContent = err.message; }
    });
  });
}

// --------------------------------------------------- Repost, Senden, Listen

function repostSheet(id, knopf) {
  sheet("Repost", `
    <p class="small muted">Der Beitrag erscheint in deiner Chronik und bei deinen Followern,
    mit Verweis auf das Original.</p>
    <form id="rp-form" class="stack" data-s="mt-md">
      <div class="field"><label for="rp-text">Eigener Gedanke dazu (optional)</label>
        <textarea id="rp-text" maxlength="3000" rows="3"></textarea></div>
      <button class="btn-primary btn-lg" type="submit">Teilen</button>
      <p class="tiny muted" id="rp-err" role="alert"></p>
    </form>`, (body) => {
    $("#rp-form", body).addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await api("/api/netz/beitraege", { method: "POST",
          body: { art: "repost", repost_of: id, text: $("#rp-text", body).value } });
        closeSheet(); toast("Geteilt.");
        if (knopf) { knopf.classList.add("an-r"); knopf.disabled = true; }
      } catch (err) { $("#rp-err", body).textContent = err.message; }
    });
  });
}

async function sendenSheet(postId) {
  const [g, f] = await Promise.all([
    api("/api/netz/nachrichten").catch(() => ({ gespraeche: [] })),
    api(`/api/netz/personen/${encodeURIComponent(ichId())}/gefolgt`).catch(() => ({ personen: [] })),
  ]);
  const gesehen = new Set();
  const ziele = [];
  g.gespraeche.forEach((x) => { gesehen.add(x.mit.id); ziele.push(x.mit); });
  f.personen.forEach((p) => { if (!gesehen.has(p.id)) ziele.push(p); });
  sheet("Senden", `
    <div class="field"><label class="sr-only" for="sd-such">Suchen</label>
      <input id="sd-such" type="search" placeholder="Suchen …" autocomplete="off"></div>
    <ul class="person-list" id="sd-liste"></ul>
    <div class="field" data-s="mt-sm"><label for="sd-text">Nachricht dazu (optional)</label>
      <input id="sd-text" maxlength="2000" autocomplete="off"></div>`, (body) => {
    const liste = $("#sd-liste", body);
    const zeige = (personen) => {
      liste.innerHTML = personen.length ? personen.map((p) => `
        <li class="person-row">
          <span class="row grow" data-s="gap-sm">${avatarHtml(p, "m")}
            <span class="grow"><strong>${esc(p.name)}</strong>
            <span class="tiny muted np-sub">${esc(p.headline || "")}</span></span></span>
          <button type="button" class="btn-primary small" data-an="${esc(p.id)}">Senden</button>
        </li>`).join("") : `<li class="small muted">Folge Personen, um ihnen Beiträge zu senden.</li>`;
    };
    zeige(ziele);
    let warte = null;
    $("#sd-such", body).addEventListener("input", (e) => {
      clearTimeout(warte);
      const w = e.target.value.trim();
      if (w.length < 2) { zeige(ziele); return; }
      warte = setTimeout(async () => {
        zeige((await api("/api/netz/personen?q=" + encodeURIComponent(w))).personen);
      }, 250);
    });
    liste.addEventListener("click", async (e) => {
      const k = e.target.closest("[data-an]");
      if (!k) return;
      try {
        await api("/api/netz/nachrichten", { method: "POST",
          body: { an: k.dataset.an, post_id: postId, text: $("#sd-text", body).value } });
        k.textContent = "Gesendet"; k.disabled = true;
      } catch (err) { toast(err.message); }
    });
  });
}

async function personenSheet(titel, url) {
  const r = await api(url);
  sheet(titel, `<ul class="person-list">${r.personen.length
    ? r.personen.map((p) => personZeile(p)).join("") : `<li class="small muted">Niemand.</li>`}</ul>`,
  (body) => {
    body.addEventListener("click", (e) => { if (e.target.closest("a")) closeSheet(); });
    bindeFolgen(body, () => {});
  });
}

// --------------------------------------------------------------- Feed

async function viewNetz() {
  const p = await netzProfil(true);
  if (!p.aktiv) return netzEinstieg(p);
  const modus = NETZ.feedModus;
  const thema = NETZ.feedThema || "";
  const th = await themenKatalog().catch(() => ({ themen: [] }));
  const gefolgt = th.themen.filter((t) => t.folge_ich);
  const chips = [...gefolgt, ...th.themen.filter((t) => !t.folge_ich)].slice(0, 16);
  app().innerHTML = `
    <h1 class="sr-only">Feed</h1>
    <div class="feed-layout">
      <div class="feed-col">
        <div class="feed-tabs" role="tablist" aria-label="Feed">
          <button role="tab" data-modus="fuerdich" aria-selected="${modus === "fuerdich"}">Für dich</button>
          <button role="tab" data-modus="folgeich" aria-selected="${modus === "folgeich"}">Folge ich</button>
          ${gefolgt.length ? `<button role="tab" data-modus="themen" aria-selected="${modus === "themen"}">Meine Themen</button>` : ""}
        </div>
        <div class="chip-scroll feed-themen" role="group" aria-label="Nach Thema filtern">
          ${chips.map((t) => `<button type="button" class="chip thema" data-feedthema="${esc(t.code)}"
            aria-pressed="${t.code === thema}">#${esc(t.name)}</button>`).join("")}
          <a class="chip link-plain" href="#/themen">Themen</a>
        </div>
        <div id="netz-feed"><p class="small muted feed-laedt">Wird geladen …</p></div>
        <div id="netz-mehr"></div>
      </div>
      <aside class="feed-side nur-gross" id="feed-side" aria-label="Vorschläge"></aside>
    </div>
    ${pageFoot()}`;
  zeigeZaehler();
  app().querySelectorAll("[data-modus]").forEach((b) => b.addEventListener("click", () => {
    NETZ.feedModus = b.dataset.modus;
    viewNetz();
  }));
  app().querySelectorAll("[data-feedthema]").forEach((b) => b.addEventListener("click", () => {
    NETZ.feedThema = NETZ.feedThema === b.dataset.feedthema ? "" : b.dataset.feedthema;
    viewNetz();
  }));
  ladeVorschlaege($("#feed-side"), p);

  const feed = await api(`/api/netz/feed?modus=${modus}&thema=${encodeURIComponent(thema)}`);
  const liste = $("#netz-feed");
  if (!liste) return;
  if (!feed.beitraege.length) {
    liste.innerHTML = `<div class="empty">${markSvg("mark")}
      <strong>${thema ? "Zu diesem Thema noch nichts." : modus === "folgeich"
        ? "Noch niemandem gefolgt." : "Noch ist es ruhig hier."}</strong>
      ${thema ? "Teile den ersten Beitrag dazu." : "Folge Kolleg*innen oder teile den ersten Fall."}
      <a href="#/netzwerk">Netzwerk</a></div>`;
    return;
  }
  zeigeBeitraege(liste, feed.beitraege, false);
  mehrLaden(feed.weiter, modus, thema);
  if (modus === "fuerdich" && !thema) vorschlagKarte(liste);
}

function zeigeBeitraege(liste, beitraege, anhaengen) {
  const html = beitraege.map(postHtml).join("");
  if (anhaengen) liste.insertAdjacentHTML("beforeend", html);
  else liste.innerHTML = html;
  // Die Begründung des Algorithmus hängt an der Karte, für „Warum sehe ich das?“.
  beitraege.forEach((b) => {
    const k = liste.querySelector(`[data-post="${CSS.escape(b.id)}"]`);
    if (k) k.dataset.warum = (b.warum || []).join("|");
  });
  bindePosts(liste);
}

function mehrLaden(weiter, modus, thema = "") {
  const box = $("#netz-mehr");
  if (!box) return;
  if (weiter === null || weiter === undefined) { box.innerHTML = ""; return; }
  box.innerHTML = `<button type="button" class="btn-quiet btn-lg" id="mehr">Weitere Beiträge</button>`;
  $("#mehr").addEventListener("click", async () => {
    const f = await api(`/api/netz/feed?modus=${modus}&seite=${weiter}&thema=${encodeURIComponent(thema)}`);
    zeigeBeitraege($("#netz-feed"), f.beitraege, true);
    mehrLaden(f.weiter, modus, thema);
  });
}

async function ladeVorschlaege(box, p) {
  if (!box) return;
  const v = await api("/api/netz/vorschlaege").catch(() => ({ personen: [] }));
  if (!document.body.contains(box)) return;
  box.innerHTML = `
    <a class="side-me link-plain" href="#/profil">${avatarHtml({ id: p.id, name: p.name, avatar_id: p.avatar_id }, "l")}
      <span class="grow"><strong>${esc(p.name)}</strong><span class="tiny muted np-sub">${esc(p.headline)}</span></span></a>
    ${v.personen.length ? `<div class="side-title small muted spread">Vorschläge für dich
      <a class="tiny link-plain" href="#/netzwerk">Alle</a></div>
    <ul class="person-list">${v.personen.map((x) => personZeile(x, x.grund)).join("")}</ul>` : ""}
    <p class="tiny muted side-foot">„Für dich“ ordnet nach Relevanz für dein Lernen.
    Dein Logbuch bleibt privat.</p>`;
  bindeFolgen(box, () => ladeVorschlaege(box, p));
}

function netzEinstieg(p) {
  app().innerHTML = `
    <div class="page-head">
      ${wordmark()}
      <p class="claim">Skills · Competencies · Outcomes · Procedures ·
        Emergency eXperience</p>
    </div>
    <div class="card pad-lg netz-intro">
      <h2>Kompetenznetz</h2>
      <p class="small" data-s="mt-sm">Lernen aus dem Einsatzalltag, unter Kolleg*innen:
      Fallberichte zu seltenen Situationen und Komplikationen, Algorithmen mit Quelle,
      Studien und Leitlinien, Kompetenzen aus deinem Logbuch. Mit Feed, Chronik,
      Nachrichten, Bildern und Videos.</p>
      <ul class="check-list small" data-s="mt-md">
        <li>Sichtbar nur für angemeldete Mitglieder dieser SCOPE-X-Installation.</li>
        <li>Mit einem privaten Konto sehen nur Follower, die du bestätigt hast, deine
          Beiträge.</li>
        <li>Welche Kompetenzen am Profil stehen, entscheidest du je Maßnahme.</li>
        <li>Abschalten jederzeit in den Einstellungen. Dein Logbuch bleibt davon
          unberührt.</li>
      </ul>
      ${NETZ_DATENSCHUTZ}
      <div class="sheet-actions two">
        <a class="btn link-plain" href="#/einsaetze">Zum Logbuch</a>
        <button class="btn-primary" id="netz-an">Kompetenznetz einschalten</button>
      </div>
    </div>
    ${pageFoot()}`;
  $("#netz-an").addEventListener("click", async () => {
    try {
      NETZ.profil = await api("/api/netz/profil", { method: "PUT", body: { aktiv: true } });
      toast("Kompetenznetz eingeschaltet.");
      if (!p.headline) { profilGruppe = "netz"; location.hash = "#/einstellungen"; }
      else render();
    } catch (err) { toast(err.message); }
  });
}

// ------------------------------------------------------------- Entdecken

function rasterHtml(beitraege) {
  return `<div class="grid3">${beitraege.map((b) => {
    const quelle = b.art === "repost" && b.original && !b.original.nicht_verfuegbar ? b.original : b;
    const m = (quelle.medien || [])[0];
    const symbol = m && m.art === "video" ? NETZ_ICON.video
      : (quelle.medien || []).length > 1 ? NETZ_ICON.stapel
      : b.art === "repost" ? NETZ_ICON.repost : "";
    const label = quelle.art === "fall" ? NETZ_FALL[(quelle.details || {}).kategorie] || "Fallbericht"
      : NETZ_ART[quelle.art] || "";
    const text = quelle.titel || quelle.text || (quelle.link && quelle.link.titel) || "";
    return `<a class="g-tile link-plain" href="#/beitrag/${esc(b.id)}" aria-label="${esc(
      (label ? label + ": " : "") + (text || "Beitrag").slice(0, 80))}">
      ${m ? `<img src="/api/netz/medien/${esc(m.id)}/vorschau" alt="" loading="lazy" decoding="async">`
        : `<span class="g-text" data-art="${esc(quelle.art)}" data-kat="${esc((quelle.details || {}).kategorie || "")}">
          ${label ? `<span class="g-label">${esc(label)}</span>` : ""}
          <span class="g-body">${esc(text.slice(0, 140))}</span></span>`}
      ${symbol ? `<span class="g-sym">${symbol}</span>` : ""}
      ${m && label ? `<span class="g-badge">${esc(label)}</span>` : ""}
    </a>`;
  }).join("")}</div>`;
}

async function viewEntdecken() {
  const p = await netzProfil();
  if (!p.aktiv) return netzEinstieg(p);
  app().innerHTML = `
    <h1 class="sr-only">Entdecken</h1>
    <a class="search-bar link-plain such-link" href="#/suche">Personen, #Themen, Beiträge suchen</a>
    <div id="entdecken-raster"><p class="small muted" data-s="mt-md">Wird geladen …</p></div>
    <div id="entdecken-mehr"></div>
    ${pageFoot()}`;

  const lade = async (seite) => {
    const r = await api("/api/netz/entdecken?seite=" + seite);
    const ziel = $("#entdecken-raster");
    if (!ziel) return;
    if (seite === 0) {
      ziel.innerHTML = r.beitraege.length ? rasterHtml(r.beitraege)
        : `<div class="empty">${markSvg("mark")}<strong>Noch nichts zu entdecken.</strong>
          Sobald Mitglieder Fälle und Wissen teilen, erscheinen sie hier.</div>`;
    } else {
      ziel.insertAdjacentHTML("beforeend", rasterHtml(r.beitraege));
    }
    const mehr = $("#entdecken-mehr");
    mehr.innerHTML = r.weiter ? `<button type="button" class="btn-quiet btn-lg" id="em">Mehr</button>` : "";
    if (r.weiter) $("#em").addEventListener("click", () => lade(r.weiter));
  };
  lade(0);
}

async function viewTag(tag) {
  const r = await api("/api/netz/tags/" + encodeURIComponent(tag));
  app().innerHTML = `
    <div class="page-head">
      <a class="small muted link-plain" href="#/entdecken">Entdecken</a>
      <div class="row tag-head" data-s="gap-md mt-sm"><span class="tag-disc big" aria-hidden="true">#</span>
        <div class="grow"><h1>${r.thema ? esc(r.thema.name) : "#" + esc(r.tag)}</h1>
          <p class="small muted">${r.thema ? `#${esc(r.tag)} · ${esc(r.thema.kategorie)} · ` : ""}${r.anzahl} ${
          r.anzahl === 1 ? "Beitrag" : "Beiträge"}</p></div>
        ${r.thema ? themaKnopf({ code: r.thema.code, folge_ich: r.thema.folge_ich }) : ""}</div>
      ${r.thema ? `<button type="button" class="btn-soft small" data-s="mt-sm" id="tag-feed">Im Feed filtern</button>` : ""}
    </div>
    ${r.beitraege.length ? rasterHtml(r.beitraege) : `<p class="small muted">Keine sichtbaren Beiträge.</p>`}
    ${pageFoot()}`;
  bindeThemen($(".page-head"));
  const tf = $("#tag-feed");
  if (tf) tf.addEventListener("click", () => { NETZ.feedThema = r.tag; location.hash = "#/"; });
}

// ---------------------------------------------------------------- Personen

function folgeKnopf(p, klein = true) {
  if (!p || p.id === ichId()) return "";
  const k = klein ? " small" : "";
  if (p.ich_folge === "aktiv") {
    return `<button type="button" class="btn-soft${k}" data-entfolgen="${esc(p.id)}">Gefolgt</button>`;
  }
  if (p.ich_folge === "angefragt") {
    return `<button type="button" class="btn-soft${k}" data-entfolgen="${esc(p.id)}">Angefragt</button>`;
  }
  return `<button type="button" class="btn-primary${k}" data-folgen="${esc(p.id)}">${
    p.folgt_mir ? "Zurückfolgen" : "Folgen"}</button>`;
}

function personZeile(p, grund) {
  return `
    <li class="person-row">
      <a class="row grow link-plain" href="#/person/${esc(p.id)}" data-s="gap-sm">
        ${avatarHtml(p, "m")}
        <span class="grow"><strong>${esc(p.name)}</strong>${p.privat
          ? ` <span class="lock" title="Privates Konto">${NETZ_ICON.schloss}</span>` : ""}${abzeichenHtml(p, 2)}
          <span class="tiny muted np-sub">${esc(grund || p.headline || "")}</span></span>
      </a>
      ${folgeKnopf(p)}
    </li>`;
}

function bindeFolgen(bereich, nachher) {
  bereich.addEventListener("click", async (e) => {
    const k = e.target.closest("[data-folgen], [data-entfolgen], [data-annehmen], [data-ablehnen]");
    if (!k || !bereich.contains(k)) return;
    try {
      if (k.dataset.folgen) {
        const r = await api("/api/netz/folgen/" + encodeURIComponent(k.dataset.folgen), { method: "POST" });
        k.outerHTML = folgeKnopf(r, k.classList.contains("small"));
        if (r.ich_folge === "angefragt") toast("Anfrage gesendet.");
      } else if (k.dataset.entfolgen) {
        if (k.textContent.trim() === "Gefolgt" &&
            !confirm("Nicht mehr folgen? Gegenseitige Kompetenzbestätigungen entfallen dabei.")) return;
        const r = await api("/api/netz/folgen/" + encodeURIComponent(k.dataset.entfolgen), { method: "DELETE" });
        if (r && r.id) k.outerHTML = folgeKnopf(r, k.classList.contains("small"));
      } else if (k.dataset.annehmen) {
        await api(`/api/netz/follower/${encodeURIComponent(k.dataset.annehmen)}/annehmen`, { method: "POST" });
        nachher();
      } else if (k.dataset.ablehnen) {
        await api("/api/netz/follower/" + encodeURIComponent(k.dataset.ablehnen), { method: "DELETE" });
        nachher();
      }
      mitteilungsZaehler(true);
    } catch (err) { toast(err.message); }
  });
}

let personReiter = "beitraege";

async function viewEigenesProfil() {
  const p = await netzProfil(true);
  if (!p.aktiv) return netzEinstieg(p);
  return viewPerson(p.id);
}

async function viewPerson(id) {
  const ich = await netzProfil();
  const selbst = id === ichId();
  if (!ich.aktiv && !selbst) return netzEinstieg(ich);
  const p = await api("/api/netz/personen/" + encodeURIComponent(id));
  const z = p.zahlen;

  app().innerHTML = `
    <div class="prof">
      ${p.voll && p.banner_id ? `<div class="banner"><img src="/api/netz/medien/${esc(p.banner_id)}"
        alt="" decoding="async"></div>` : ""}
      <div class="prof-head${p.voll && p.banner_id ? " mit-banner" : ""}">
        <div class="prof-av">${avatarHtml(p, "xl")}</div>
        <div class="prof-main">
          <div class="prof-name">
            <h1>${esc(p.name)}</h1>${p.privat ? `<span class="lock" title="Privates Konto">${NETZ_ICON.schloss}</span>` : ""}
            ${selbst ? `<a class="icon-btn flat link-plain" href="#/einstellungen" aria-label="Einstellungen">${NETZ_ICON.zahnrad}</a>` : ""}
          </div>
          <div class="prof-stats" role="group" aria-label="Kennzahlen">
            <span><strong>${zahl(z.beitraege)}</strong> Beiträge</span>
            <button type="button" class="link-btn" data-liste="follower"><strong>${zahl(z.follower)}</strong> Follower</button>
            <button type="button" class="link-btn" data-liste="gefolgt"><strong>${zahl(z.folge_ich)}</strong> Gefolgt</button>
          </div>
        </div>
      </div>
      <div class="prof-bio">
        ${p.headline ? `<div class="small"><strong>${esc(p.headline)}</strong></div>` : ""}
        ${p.abzeichen && p.abzeichen.length ? `<div>${abzeichenHtml(p, 6)}</div>` : ""}
        ${p.about ? `<div class="small np-text">${esc(p.about)}</div>` : ""}
        ${p.voll && ortText(p.ort, p) ? `<div class="tiny muted">${esc(ortText(p.ort, p))}</div>` : ""}
        ${!selbst && p.folgt_mir ? `<div class="tiny muted">Folgt dir</div>` : ""}
      </div>
      <div class="prof-actions">
        ${selbst ? `
          <a class="btn-soft link-plain" href="#/einstellungen" id="bearbeiten">Profil bearbeiten</a>
          <a class="btn-soft link-plain" href="#/gespeichert">Gespeichert</a>` : `
          ${p.fragt_an ? `<button type="button" class="btn-primary" data-annehmen="${esc(p.id)}">Anfrage bestätigen</button>` : ""}
          ${folgeKnopf(p, false)}
          <a class="btn-soft link-plain" href="#/nachrichten/an/${esc(p.id)}">Nachricht</a>
          <button type="button" class="btn-soft icon-only" id="person-mehr" aria-label="Weitere Aktionen">${NETZ_ICON.mehr}</button>`}
      </div>
    </div>

    ${p.voll ? `
    <div class="prof-tabs" role="tablist" aria-label="Profilbereiche">
      <button role="tab" data-reiter="beitraege">${NETZ_ICON.raster}<span>Beiträge</span></button>
      <button role="tab" data-reiter="chronik">${NETZ_ICON.chronik}<span>Chronik</span></button>
      <button role="tab" data-reiter="kompetenzen">${NETZ_ICON.kompetenz}<span>Kompetenzen</span></button>
      <button role="tab" data-reiter="info">${NETZ_ICON.info}<span>Info</span></button>
    </div>
    <div id="prof-inhalt"></div>` : `
    <div class="privat-hinweis">
      <span class="lock-gross">${NETZ_ICON.schloss}</span>
      <strong>Dieses Konto ist privat</strong>
      <p class="small muted">Folge ${esc(p.name)}, um Beiträge, Chronik, Kompetenzen und Info
      zu sehen.</p>
    </div>`}
    ${pageFoot()}`;

  bindeFolgen($(".prof"), () => viewPerson(id));
  app().querySelectorAll("[data-liste]").forEach((b) => b.addEventListener("click", () => {
    if (!p.voll) return;
    personenSheet(b.dataset.liste === "follower" ? "Follower" : "Gefolgt",
      `/api/netz/personen/${encodeURIComponent(id)}/${b.dataset.liste}`);
  }));
  const bearbeiten = $("#bearbeiten");
  if (bearbeiten) bearbeiten.addEventListener("click", () => { profilGruppe = "netz"; });
  const mehr = $("#person-mehr");
  if (mehr) mehr.addEventListener("click", () => personMenue(p));

  if (!p.voll) return;
  const zeige = async (reiter) => {
    personReiter = reiter;
    app().querySelectorAll("[data-reiter]").forEach((b) =>
      b.setAttribute("aria-selected", String(b.dataset.reiter === reiter)));
    const ziel = $("#prof-inhalt");
    if (reiter === "beitraege") {
      const r = await api(`/api/netz/personen/${encodeURIComponent(id)}/beitraege`);
      ziel.innerHTML = r.beitraege.length ? rasterHtml(r.beitraege)
        : `<div class="empty"><strong>${selbst ? "Teile deinen ersten Beitrag" : "Noch keine Beiträge"}</strong>
          ${selbst ? "Fälle, Algorithmen, Wissen, Fotos und Videos aus deinem Alltag." : ""}</div>`;
    } else if (reiter === "chronik") {
      const r = await api(`/api/netz/personen/${encodeURIComponent(id)}/beitraege`);
      ziel.innerHTML = chronikHtml(r.beitraege, p.eintraege || []);
      bindePosts(ziel);
    } else if (reiter === "kompetenzen") {
      ziel.innerHTML = kompetenzenHtml(p, selbst);
      bindeKompetenzen(ziel, p);
    } else {
      ziel.innerHTML = infoHtml(p);
    }
  };
  app().querySelectorAll("[data-reiter]").forEach((b) =>
    b.addEventListener("click", () => zeige(b.dataset.reiter)));
  zeige(personReiter);
}

function personMenue(p) {
  sheet(p.name, `
    <div class="menu-list">
      <button type="button" id="pm-teilen">Profil-Link kopieren</button>
      ${p.folgt_mir ? `<button type="button" id="pm-entfernen">Als Follower entfernen</button>` : ""}
      <button type="button" class="danger" id="pm-block">Blockieren</button>
    </div>`, (body) => {
    $("#pm-teilen", body).addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(location.origin + "/#/person/" + p.id); toast("Link kopiert."); }
      catch (_) { toast("Kopieren nicht möglich."); }
      closeSheet();
    });
    const ent = $("#pm-entfernen", body);
    if (ent) ent.addEventListener("click", async () => {
      await api("/api/netz/follower/" + encodeURIComponent(p.id), { method: "DELETE" });
      closeSheet(); toast("Follower entfernt."); viewPerson(p.id);
    });
    $("#pm-block", body).addEventListener("click", async () => {
      if (!confirm(`${p.name} blockieren? Ihr folgt euch dann nicht mehr, seht eure Beiträge `
        + "nicht und könnt euch keine Nachrichten senden.")) return;
      await api("/api/netz/blockieren/" + encodeURIComponent(p.id), { method: "POST" });
      closeSheet(); toast("Blockiert."); location.hash = "#/";
    });
  });
}

function monatJahr(d) {
  if (!d) return "";
  if (d.length === 4) return d;
  const [y, m] = d.split("-");
  return new Date(Number(y), Number(m) - 1, 1).toLocaleDateString("de-DE", { month: "short", year: "numeric" });
}

/* Chronik: Beiträge und Lebensstationen in einer Zeitleiste. */
function chronikHtml(beitraege, eintraege) {
  const punkte = [
    ...beitraege.map((b) => ({ t: b.erstellt, html: postHtml(b) })),
    ...eintraege.filter((e) => e.von).map((e) => ({
      t: e.von.length === 4 ? e.von + "-01-01" : e.von.length === 7 ? e.von + "-01" : e.von,
      html: `<div class="ch-event"><span class="ch-dot" aria-hidden="true"></span><div>
        <div class="tiny muted">${esc(NETZ_EINTRAG[e.art] || "")} · ${esc(monatJahr(e.von))}</div>
        <strong>${esc(e.titel)}</strong>${e.org ? `<div class="small muted">${esc(e.org)}</div>` : ""}</div></div>`,
    })),
  ].sort((a, b) => String(b.t).localeCompare(String(a.t)));
  if (!punkte.length) return `<div class="empty"><strong>Die Chronik ist noch leer.</strong></div>`;
  return `<div class="chronik feed-col">${punkte.map((x) => x.html).join("")}</div>`;
}

function kompetenzenHtml(p, selbst) {
  const k = p.kompetenzen || [];
  if (!k.length) {
    return `<div class="empty"><strong>Noch keine Kompetenzen freigegeben.</strong>${selbst
      ? " Lege in den Einstellungen fest, welche Maßnahmen aus deinem Logbuch am Profil stehen." : ""}</div>`;
  }
  return `
    <p class="tiny muted kz-hint">Belegt durch das Logbuch: nur Anzahlen, kein Datum, kein
    Einsatzbezug. Bestätigen können Personen, die sich gegenseitig folgen.</p>
    <ul class="kz-items">${k.map((x) => `
      <li class="kz-item" data-cat="${esc(x.kategorie)}">
        <div class="row" data-s="gap-sm">
          <span class="cat-badge">${esc(x.kategorie)}</span>
          <strong class="grow">${esc(x.name)}</strong>
          ${p.kontakt && canWrite() ? (x.meine_bestaetigung
            ? `<button type="button" class="btn-soft small" data-zurueck="${esc(x.meine_bestaetigung)}">Bestätigt</button>`
            : `<button type="button" class="btn-primary small" data-bestaetigen="${esc(x.measure_id)}"
                data-name="${esc(x.name)}">Bestätigen</button>`) : ""}
        </div>
        <div class="tiny muted" data-s="mt-xs">${x.anzahl}× dokumentiert · ${x.erfolgreich} erfolgreich${
          x.bestaetigungen ? ` · ${x.bestaetigungen} ${x.bestaetigungen === 1 ? "Bestätigung" : "Bestätigungen"}${
            x.praxisanleitung ? `, davon ${x.praxisanleitung} durch Praxisanleitung` : ""}` : ""}</div>
      </li>`).join("")}</ul>`;
}

function bindeKompetenzen(ziel, p) {
  ziel.querySelectorAll("[data-bestaetigen]").forEach((b) =>
    b.addEventListener("click", () => bestaetigenSheet(p, b.dataset.bestaetigen, b.dataset.name)));
  ziel.querySelectorAll("[data-zurueck]").forEach((b) =>
    b.addEventListener("click", async () => {
      await api("/api/netz/bestaetigungen/" + encodeURIComponent(b.dataset.zurueck), { method: "DELETE" });
      toast("Bestätigung zurückgezogen."); personReiter = "kompetenzen"; viewPerson(p.id);
    }));
}

function bestaetigenSheet(p, measureId, name) {
  const rollen = Object.entries(NETZ_ROLLEN).map(([k, label], i) => `
    <label class="check"><input type="radio" name="rolle" value="${k}" ${i === 0 ? "checked" : ""}>
      ${esc(label)}</label>`).join("");
  sheet("Kompetenz bestätigen", `
    <p class="small"><strong>${esc(name)}</strong> bei ${esc(p.name)}</p>
    <p class="small muted" data-s="mt-sm">Bestätige nur, was du selbst gesehen hast. Deine
    Bestätigung steht mit deinem Namen am Profil.</p>
    <form id="bs-form" class="stack" data-s="mt-md">
      <fieldset class="field"><legend class="small">Woher kennst du es?</legend>${rollen}</fieldset>
      <button class="btn-primary btn-lg" type="submit">Bestätigen</button>
      <p class="tiny muted" id="bs-err" role="alert"></p>
    </form>`, (body) => {
    $("#bs-form", body).addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await api("/api/netz/bestaetigungen", { method: "POST", body: {
          user_id: p.id, measure_id: measureId,
          rolle: $('input[name="rolle"]:checked', body).value } });
        closeSheet(); toast("Bestätigt."); personReiter = "kompetenzen"; viewPerson(p.id);
      } catch (err) { $("#bs-err", body).textContent = err.message; }
    });
  });
}

function infoHtml(p) {
  const heute = new Date().toISOString().slice(0, 7);
  const gruppen = Object.keys(NETZ_EINTRAG).map((art) => {
    const liste = (p.eintraege || []).filter((e) => e.art === art);
    if (!liste.length) return "";
    return `<section class="info-sec"><h2>${esc(NETZ_EINTRAG[art])}</h2><ul>${liste.map((e) => `
      <li><strong>${esc(e.titel)}</strong>${e.org ? `<div class="small">${esc(e.org)}</div>` : ""}
        ${e.von || e.bis ? `<div class="tiny muted">${esc(monatJahr(e.von))}${
          art === "zertifikat" ? (e.bis ? ` · gültig bis ${esc(monatJahr(e.bis))}${e.bis < heute ? " (abgelaufen)" : ""}` : "")
          : e.bis ? " – " + esc(monatJahr(e.bis)) : e.von ? " – heute" : ""}</div>` : ""}
        ${e.notiz ? `<div class="small muted">${esc(e.notiz)}</div>` : ""}</li>`).join("")}</ul></section>`;
  }).join("");
  const o = p.ort || {};
  const wache = o.wache && o.wache.name;
  const org = (o.organisation && o.organisation.name) || p.organisation;
  const region = o.kreis || p.location;
  return `
    <section class="info-sec"><h2>Persönliche Informationen</h2>
      ${p.qualifikation || org || region || wache ? `<dl class="info-dl">
        ${p.qualifikation ? `<dt>Beruf</dt><dd>${esc(p.qualifikation)}</dd>` : ""}
        ${wache ? `<dt>Wache</dt><dd>${esc(wache)}</dd>` : ""}
        ${org ? `<dt>Organisation</dt><dd>${esc(org)}</dd>` : ""}
        ${region ? `<dt>Region</dt><dd>${esc(region)}</dd>` : ""}
      </dl>` : `<p class="small muted">Keine Angaben.</p>`}
    </section>
    ${(p.qualifikationen || []).length ? `<section class="info-sec"><h2>Qualifikationen und Kurse</h2>
      ${qualListeHtml(p.qualifikationen, false)}</section>` : ""}
    ${gruppen}`;
}

// ----------------------------------------------------------- Mitteilungen

const NETZ_MITTEILUNG = {
  folgt: "folgt dir jetzt.",
  folgeanfrage: "möchte dir folgen.",
  folge_angenommen: "hat deine Anfrage angenommen.",
  like: "gefällt dein Beitrag.",
  kommentar: "hat deinen Beitrag kommentiert.",
  repost: "hat deinen Beitrag geteilt.",
  bestaetigung: "hat eine deiner Kompetenzen bestätigt.",
  entfernt: "hat einen Beitrag von dir entfernt. Der Grund steht am Beitrag.",
  meldung: "hat einen Beitrag gemeldet.",
  hilfreich: "hat deine Antwort als hilfreich markiert.",
  erwaehnung: "hat dich in einem Beitrag erwähnt.",
  erwaehnung_kommentar: "hat dich in einem Kommentar erwähnt.",
  katalog: "hat einen Katalogeintrag vorgeschlagen.",
  qualifikation: "",
  bewerbung: "",
  buergschaft: "",
};
const NETZ_MITTEILUNG_SYSTEM = {
  qualifikation: ["Ablauf", "#/einstellungen"],
  bewerbung: ["Bewerbung", "#/administration"],
  buergschaft: ["Bürgschaft angefragt", "#/netzwerk"],
};

async function viewMitteilungen() {
  const [m, a] = await Promise.all([api("/api/netz/mitteilungen"),
    api("/api/netz/anfragen").catch(() => ({ personen: [] }))]);
  const jetzt = Date.now();
  const gruppe = (iso) => {
    const t = (jetzt - Date.parse(iso)) / 86400000;
    return t < 1 ? "Heute" : t < 7 ? "Diese Woche" : t < 31 ? "Diesen Monat" : "Früher";
  };
  const gruppen = {};
  m.mitteilungen.forEach((x) => {
    if (!(x.art in NETZ_MITTEILUNG) || x.art === "folgeanfrage") return;
    (gruppen[gruppe(x.erstellt)] = gruppen[gruppe(x.erstellt)] || []).push(x);
  });
  app().innerHTML = `
    <div class="page-head"><h1>Mitteilungen</h1></div>
    <div id="mt-seite" class="feed-col">
    ${a.personen.length ? `<section class="mt-sec"><h2 class="sec">Folgeanfragen
      <a class="tiny link-plain" href="#/netzwerk">Im Netzwerk</a></h2>
      <ul class="person-list">${a.personen.map((p) => `
        <li class="person-row">
          <a class="row grow link-plain" href="#/person/${esc(p.id)}" data-s="gap-sm">${avatarHtml(p, "m")}
            <span class="grow"><strong>${esc(p.name)}</strong><span class="tiny muted np-sub">${esc(p.headline)}</span></span></a>
          <button type="button" class="btn-primary small" data-annehmen="${esc(p.id)}">Bestätigen</button>
          <button type="button" class="btn-soft small" data-ablehnen="${esc(p.id)}">Löschen</button>
        </li>`).join("")}</ul></section>` : ""}
    ${Object.keys(gruppen).length ? Object.entries(gruppen).map(([titel, liste]) => `
      <section class="mt-sec"><h2 class="sec">${esc(titel)}</h2>
      <ul class="person-list">${liste.map((x) => {
        const sys = NETZ_MITTEILUNG_SYSTEM[x.art];
        const wer = sys ? sys[0] : x.art === "entfernt" ? "Die Administration"
          : (x.von ? x.von.name : "Jemand");
        const ziel = sys ? sys[1] : x.post_id ? "#/beitrag/" + x.post_id
          : x.art === "bestaetigung" ? "#/profil"
          : x.art === "katalog" ? "#/administration"
          : x.von ? "#/person/" + x.von.id : "#/";
        return `<li class="note-row${x.gelesen ? "" : " neu"}">
          <a class="row grow link-plain" href="${esc(ziel)}" data-s="gap-sm">
            ${x.von && x.art !== "entfernt" ? avatarHtml(x.von, "m")
              : `<span class="av av-m ini" data-farbe="0" aria-hidden="true">!</span>`}
            <span class="grow small"><strong>${esc(wer)}</strong> ${esc(sys ? (x.art === "bewerbung"
              ? `${x.text || "Jemand"} wartet auf eine Entscheidung.` : x.art === "buergschaft"
              ? `${x.text || "Jemand"} hat dich als Kontakt genannt.` : x.text) : NETZ_MITTEILUNG[x.art])}
              <span class="muted">${esc(relZeit(x.erstellt, true))}</span></span>
          </a>
          ${x.art === "folgt" && x.von && x.von.ich_folge === "nein" ? folgeKnopf(x.von) : ""}
        </li>`;
      }).join("")}</ul></section>`).join("")
      : (!a.personen.length ? `<div class="empty">${markSvg("mark")}<strong>Keine Mitteilungen.</strong>
        Gefällt mir, Kommentare, Reposts und neue Follower erscheinen hier.</div>` : "")}
    </div>
    ${pageFoot()}`;
  bindeFolgen($("#mt-seite"), () => viewMitteilungen());
  if (m.ungelesen) await api("/api/netz/mitteilungen/gelesen", { method: "POST" });
  mitteilungsZaehler(true);
}

async function viewBeitrag(id) {
  const b = await beitragDaten(id);
  app().innerHTML = `
    <div class="page-head">
      <button type="button" class="link-btn muted back-btn" id="zurueck">${NETZ_ICON.zurueck} Zurück</button>
      <h1 class="sr-only">Beitrag von ${esc(b.autor.name)}</h1>
    </div>
    <div class="feed-col" id="ein-beitrag">${postHtml(b)}</div>
    <section class="feed-col k-inline" id="k-inline" aria-label="Kommentare"></section>
    ${pageFoot()}`;
  $("#zurueck").addEventListener("click", () => (history.length > 1 ? history.back() : (location.hash = "#/")));
  bindePosts($("#ein-beitrag"));
  const k = await api(`/api/netz/beitraege/${encodeURIComponent(id)}/kommentare`);
  const box = $("#k-inline");
  if (!box) return;
  box.innerHTML = `<h2 class="sec">${b.art === "fallvorstellung" ? "Antworten" : "Kommentare"}</h2>
    ${kommentarListeHtml(k.kommentare)}
    ${k.aus ? `<p class="small muted">Kommentare ausgeschaltet.</p>` : canWrite()
      ? `<button type="button" class="btn-soft" data-s="mt-sm" id="k-schreiben">${
        b.art === "fallvorstellung" ? (k.darf_markieren ? "Antworten ansehen und markieren" : "Antworten")
        : "Kommentieren"}</button>` : ""}`;
  const s = $("#k-schreiben");
  if (s) s.addEventListener("click", () => kommentarSheet(id, $("[data-post]", $("#ein-beitrag"))));
}

// ------------------------------------------------------------ Nachrichten

async function viewNachrichten(gid, an) {
  const p = await netzProfil();
  if (!p.aktiv) return netzEinstieg(p);
  const liste = await api("/api/netz/nachrichten");
  const offen = gid || an;
  app().innerHTML = `
    <div class="dm${offen ? " offen" : ""}">
      <section class="dm-list" aria-label="Gespräche">
        <div class="dm-list-head"><h1>Nachrichten</h1></div>
        <div class="feed-tabs small-tabs" role="tablist" aria-label="Postfach">
          <button role="tab" data-dm="chats" aria-selected="true">Chats</button>
          <button role="tab" data-dm="anfragen" aria-selected="false">Anfragen${
            liste.anfragen.length ? ` (${liste.anfragen.length})` : ""}</button>
        </div>
        <ul class="dm-items" id="dm-items"></ul>
      </section>
      <section class="dm-thread" id="dm-thread" aria-label="Gespräch">
        ${offen ? "" : `<div class="dm-empty">${NETZ_ICON.senden}<strong>Deine Nachrichten</strong>
          <p class="small muted">Sende Kolleg*innen Fragen, Fälle oder Beiträge.</p></div>`}
      </section>
    </div>`;
  const zeigeListe = (welche) => {
    app().querySelectorAll("[data-dm]").forEach((b) =>
      b.setAttribute("aria-selected", String(b.dataset.dm === welche)));
    const items = welche === "chats" ? liste.gespraeche : liste.anfragen;
    $("#dm-items").innerHTML = items.length ? items.map((g) => `
      <li><a class="dm-item link-plain${g.id === gid ? " aktiv" : ""}" href="#/nachrichten/${esc(g.id)}">
        ${avatarHtml(g.mit, "l")}
        <span class="grow"><strong>${esc(g.mit.name)}</strong>
          <span class="tiny${g.ungelesen ? " ungelesen" : " muted"} np-sub">${esc(g.letzte)} · ${esc(relZeit(g.aktualisiert, true))}</span></span>
        ${g.ungelesen ? `<span class="dot-neu"><span class="sr-only">ungelesen</span></span>` : ""}
      </a></li>`).join("")
      : `<li class="small muted dm-none">${welche === "chats"
        ? "Noch keine Gespräche. Öffne ein Profil und tippe auf „Nachricht“."
        : "Keine Anfragen. Nachrichten von Personen, die dir nicht folgen, landen hier."}</li>`;
  };
  app().querySelectorAll("[data-dm]").forEach((b) => b.addEventListener("click", () => zeigeListe(b.dataset.dm)));
  zeigeListe(gid && liste.anfragen.some((x) => x.id === gid) ? "anfragen" : "chats");
  if (offen) await zeigeGespraech(gid, an);
}

function nachrichtHtml(n) {
  const b = n.beitrag;
  return `
    <div class="msg${n.von_mir ? " mine" : ""}" data-msg="${esc(n.id)}">
      ${n.text ? `<div class="bubble">${esc(n.text)}</div>` : ""}
      ${n.bild ? `<img class="msg-img" src="/api/netz/medien/${esc(n.bild.id)}" alt="Gesendetes Bild" loading="lazy">` : ""}
      ${b ? (b.nicht_verfuegbar
        ? `<div class="bubble muted small">Beitrag nicht verfügbar</div>`
        : `<a class="msg-post link-plain" href="#/beitrag/${esc(b.id)}">
            <span class="row" data-s="gap-sm">${avatarHtml(b.autor, "s")}<strong class="small">${esc(b.autor.name)}</strong></span>
            ${(b.medien || [])[0] ? `<img src="/api/netz/medien/${esc(b.medien[0].id)}/vorschau" alt="" loading="lazy">` : ""}
            <span class="small">${esc((b.titel || b.text || (b.link && b.link.titel) || "").slice(0, 120))}</span></a>`) : ""}
      <span class="msg-meta tiny muted">${esc(relZeit(n.erstellt, true))}${n.von_mir && n.gelesen ? " · gesehen" : ""}${
        n.von_mir ? ` · <button type="button" class="link-btn muted" data-unsend="${esc(n.id)}">Zurücknehmen</button>` : ""}</span>
    </div>`;
}

async function zeigeGespraech(gid, an) {
  const box = $("#dm-thread");
  const daten = gid ? await api("/api/netz/nachrichten/" + encodeURIComponent(gid))
    : { id: null, mit: await api("/api/netz/personen/" + encodeURIComponent(an)),
      anfrage: false, wartet: false, nachrichten: [] };
  box.innerHTML = `
    <header class="dm-head">
      <a class="icon-btn flat link-plain nur-schmal" href="#/nachrichten" aria-label="Zurück zu den Gesprächen">${NETZ_ICON.zurueck}</a>
      <a class="row grow link-plain" href="#/person/${esc(daten.mit.id)}" data-s="gap-sm">
        ${avatarHtml(daten.mit, "m")}<span class="grow"><strong>${esc(daten.mit.name)}</strong>
        <span class="tiny muted np-sub">${esc(daten.mit.headline || "")}</span></span></a>
      ${daten.id ? `<button type="button" class="icon-btn flat" id="dm-mehr" aria-label="Optionen zum Gespräch">${NETZ_ICON.mehr}</button>` : ""}
    </header>
    <div class="dm-msgs" id="dm-msgs" aria-live="polite"></div>
    ${daten.anfrage ? `<div class="dm-req small">
      <p><strong>${esc(daten.mit.name)}</strong> möchte dir schreiben. Bis du annimmst, erfährt die
      Person nicht, ob du die Nachricht gelesen hast.</p>
      <div class="row wrap" data-s="gap-sm mt-sm"><button type="button" class="btn-primary small" id="dm-ja">Annehmen</button>
      <button type="button" class="btn-soft small" id="dm-nein">Löschen</button>
      <button type="button" class="btn-soft small" id="dm-block">Blockieren</button></div></div>` : ""}
    ${daten.wartet ? `<p class="tiny muted dm-wait">Anfrage gesendet. ${esc(daten.mit.name)} sieht deine
      Nachricht und kann sie annehmen.</p>` : ""}
    ${canWrite() ? `<form class="dm-form" id="dm-form">
      <label class="file-icon" aria-label="Bild senden">${NETZ_ICON.bild}
        <input type="file" accept="image/jpeg,image/png,image/webp" id="dm-bild"></label>
      <label class="sr-only" for="dm-text">Nachricht</label>
      <input id="dm-text" maxlength="2000" placeholder="Nachricht …" autocomplete="off">
      <button class="link-btn strong" type="submit">Senden</button>
    </form>` : ""}`;

  const msgs = $("#dm-msgs");
  const bekannt = new Set();
  let letzte = "";
  const zeichne = (liste) => {
    let neu = false;
    liste.forEach((n) => {
      if (bekannt.has(n.id)) return;
      const start = $(".dm-start", msgs);
      if (start) start.remove();
      bekannt.add(n.id); neu = true;
      if (n.erstellt > letzte) letzte = n.erstellt;
      msgs.insertAdjacentHTML("beforeend", nachrichtHtml(n));
    });
    if (neu) msgs.scrollTop = msgs.scrollHeight;
  };
  if (daten.nachrichten.length) zeichne(daten.nachrichten);
  else msgs.innerHTML = `<div class="dm-start">${avatarHtml(daten.mit, "xl")}<strong>${esc(daten.mit.name)}</strong>
      <span class="small muted">${esc(daten.mit.headline || "")}</span></div>`;

  let aktuelleId = daten.id;
  netzAufraeumen();
  // Neue Nachrichten im Abstand von vier Sekunden, nur solange das Gespräch
  // sichtbar ist. render() beendet die Abfrage beim Seitenwechsel.
  NETZ.poll = setInterval(async () => {
    if (document.hidden || !aktuelleId) return;
    if (!document.getElementById("dm-msgs")) { netzAufraeumen(); return; }
    try {
      const r = await api(`/api/netz/nachrichten/${encodeURIComponent(aktuelleId)}?nach=${encodeURIComponent(letzte)}`);
      zeichne(r.nachrichten);
    } catch (_) { /* nächster Versuch */ }
  }, 4000);

  msgs.addEventListener("click", async (e) => {
    const u = e.target.closest("[data-unsend]");
    if (!u) return;
    await api("/api/netz/nachrichten/nachricht/" + encodeURIComponent(u.dataset.unsend), { method: "DELETE" });
    const el = msgs.querySelector(`[data-msg="${CSS.escape(u.dataset.unsend)}"]`);
    if (el) el.remove();
  });

  const senden = async (inhalt) => {
    if (aktuelleId) {
      zeichne([await api("/api/netz/nachrichten/" + encodeURIComponent(aktuelleId), { method: "POST", body: inhalt })]);
    } else {
      const r = await api("/api/netz/nachrichten", { method: "POST", body: { an: daten.mit.id, ...inhalt } });
      aktuelleId = r.gespraech;
      history.replaceState(null, "", "#/nachrichten/" + r.gespraech);
      zeichne([r.nachricht]);
    }
  };
  const form = $("#dm-form");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const feld = $("#dm-text");
      if (!feld.value.trim()) return;
      try { await senden({ text: feld.value }); feld.value = ""; }
      catch (err) { toast(err.message); }
    });
    $("#dm-bild").addEventListener("change", async (e) => {
      const datei = e.target.files[0];
      if (!datei) return;
      try {
        toast("Bild wird verarbeitet …");
        const m = await hochladen(datei, "bild");
        await senden({ bild_id: m.id });
      } catch (err) { toast(err.message); }
      e.target.value = "";
    });
    if (window.matchMedia("(min-width: 900px)").matches) $("#dm-text").focus();
  }
  const ja = $("#dm-ja");
  if (ja) ja.addEventListener("click", async () => {
    await api(`/api/netz/nachrichten/${encodeURIComponent(gid)}/annehmen`, { method: "POST" });
    viewNachrichten(gid);
  });
  const nein = $("#dm-nein");
  if (nein) nein.addEventListener("click", async () => {
    await api("/api/netz/nachrichten/" + encodeURIComponent(gid), { method: "DELETE" });
    location.hash = "#/nachrichten";
  });
  const block = $("#dm-block");
  if (block) block.addEventListener("click", async () => {
    if (!confirm(`${daten.mit.name} blockieren?`)) return;
    await api("/api/netz/blockieren/" + encodeURIComponent(daten.mit.id), { method: "POST" });
    location.hash = "#/nachrichten";
  });
  const mehr = $("#dm-mehr");
  if (mehr) mehr.addEventListener("click", () => sheet(daten.mit.name, `
    <div class="menu-list">
      <a class="link-plain" href="#/person/${esc(daten.mit.id)}">Profil ansehen</a>
      <button type="button" id="dm-aus">Gespräch ausblenden</button>
    </div>`, (body) => {
    $("a", body).addEventListener("click", closeSheet);
    $("#dm-aus", body).addEventListener("click", async () => {
      await api("/api/netz/nachrichten/" + encodeURIComponent(aktuelleId), { method: "DELETE" });
      closeSheet(); location.hash = "#/nachrichten";
    });
  }));
  mitteilungsZaehler(true);
}

// ------------------------------------------------------------- Hochladen

/* XMLHttpRequest statt fetch: nur damit gibt es einen Fortschritt beim
   Hochladen. Ein Video vom Telefon braucht im Mobilnetz eine Weile. */
function hochladen(datei, art, beiFortschritt) {
  return new Promise((resolve, reject) => {
    const fd = new FormData();
    fd.append("datei", datei);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/netz/medien/" + art);
    xhr.withCredentials = true;
    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable && beiFortschritt) beiFortschritt(e.loaded / e.total);
    });
    xhr.addEventListener("load", () => {
      let d = null;
      try { d = JSON.parse(xhr.responseText); } catch (_) { d = null; }
      if (xhr.status === 401) { state.auth = null; boot(); reject(new Error("Nicht angemeldet.")); return; }
      if (xhr.status >= 200 && xhr.status < 300) resolve(d);
      else reject(new Error((d && d.detail) || (xhr.status === 413
        ? "Die Datei ist zu groß für den Server." : "Hochladen fehlgeschlagen.")));
    });
    xhr.addEventListener("error", () => reject(new Error("Verbindung unterbrochen.")));
    xhr.send(fd);
  });
}

async function warteAufVideo(id) {
  for (let i = 0; i < 600; i++) {
    const s = await api(`/api/netz/medien/${encodeURIComponent(id)}/status`);
    if (s.status !== "verarbeitung") return s;
    await new Promise((r) => setTimeout(r, 1500));
  }
  throw new Error("Die Verarbeitung dauert ungewöhnlich lange.");
}

// ------------------------------------------------------------- Erstellen

function neuAuswahlSheet() {
  const optionen = [
    ["beitrag", "Beitrag", "Foto, Video oder Gedanke"],
    ["fallvorstellung", "Fallvorstellung", "Fall vorstellen, Community fragen"],
    ["fall", "Fallbericht", "Seltene Situation, Komplikation, Lernfall"],
    ["algorithmus", "Algorithmus", "SOP oder Ablaufschema mit Quelle"],
    ["wissen", "Studie oder Leitlinie", "Link mit Kernaussage"],
    ["kompetenz", "Kompetenz", "Einträge aus einem eigenen Einsatz"],
  ];
  sheet("Neu", `
    <div class="choice-grid">
      ${optionen.map(([art, titel, text]) => `
        <button type="button" class="choice" data-neu="${art}">
          <strong>${esc(titel)}</strong><span class="tiny muted">${esc(text)}</span></button>`).join("")}
      <button type="button" class="choice log" id="neu-einsatz">
        <strong>Einsatz dokumentieren</strong>
        <span class="tiny muted">Ins eigene Logbuch, nur für dich</span></button>
      ${state.constants.nidashare && canWrite() ? `<a class="choice log" href="#/import" id="neu-nida">
        <strong>Aus NIDAshare übernehmen</strong>
        <span class="tiny muted">Maßnahmen aus dem Protokoll, nur für dich</span></a>` : ""}
    </div>`, (body) => {
    $("#neu-einsatz", body).addEventListener("click", () => { closeSheet(); newEncounterSheet(); });
    const nida = $("#neu-nida", body);
    if (nida) nida.addEventListener("click", () => closeSheet());
    body.querySelectorAll("[data-neu]").forEach((b) => b.addEventListener("click", async () => {
      closeSheet();
      const p = await netzProfil();
      if (!p.aktiv) { location.hash = "#/"; return; }
      composer(b.dataset.neu);
    }));
  });
}

const NETZ_COMPOSER_TITEL = {
  beitrag: "Neuer Beitrag", fall: "Fallbericht", algorithmus: "Algorithmus teilen",
  fallvorstellung: "Fallvorstellung",
  wissen: "Studie oder Leitlinie", kompetenz: "Kompetenz teilen",
};

/* Ein Formular für alle Beitragsarten. Medien werden sofort hochgeladen
   und neu codiert; geteilt wird erst mit „Teilen“. */
function composer(art, vorgabe = {}) {
  const medien = [];
  const mitMedien = art === "beitrag" || art === "fall" || art === "algorithmus";
  const auswahl = { a: new Set(), m: new Set(), zek: false, naca: false };
  const themen = new Set(vorgabe.themen || []);
  const fv = art === "fallvorstellung";

  sheet(NETZ_COMPOSER_TITEL[art] || "Teilen", `
    <form id="cp-form" class="stack composer-form">
      ${art === "fall" ? `
        <div class="field"><label id="cp-kat-l">Art des Falls</label>
          <div class="chipset" id="cp-kat" role="group" aria-labelledby="cp-kat-l">${Object.entries(NETZ_FALL).map(([k, v], i) => `
            <button type="button" class="chip" data-kat="${k}" aria-pressed="${i === 0}">${esc(v)}</button>`).join("")}</div></div>
        <div class="field"><label for="cp-titel">Titel</label>
          <input id="cp-titel" maxlength="160" required placeholder="z. B. Spannungspneumothorax nach Sturz"></div>
        <div class="field"><label for="cp-bes">Was war besonders?</label>
          <textarea id="cp-bes" maxlength="1500" rows="3" required
            placeholder="Verlauf und Besonderheit, ohne Ort, Zeit und Patientendaten"></textarea></div>
        <div class="field"><label for="cp-gut">Was lief gut? (optional)</label>
          <textarea id="cp-gut" maxlength="1500" rows="2"></textarea></div>
        <div class="field"><label for="cp-and">Was würdest du anders machen? (optional)</label>
          <textarea id="cp-and" maxlength="1500" rows="2"></textarea></div>` : ""}
      ${fv ? `
        <p class="small muted">Anonymisiert vorstellen und gezielt fragen. Kein Alter, nur die
        Altersgruppe; kein Ort, keine Zeit. Antworten können Kolleg*innen als Kommentar geben, du
        markierst die hilfreichste.</p>
        <div class="field"><label for="cp-titel">Titel</label>
          <input id="cp-titel" maxlength="160" required placeholder="z. B. Bewusstlose Person, unklare Ursache"></div>
        <div class="field"><label for="cp-alter">Altersgruppe (optional)</label>
          <select id="cp-alter"><option value="">keine Angabe</option>${Object.entries(NETZ_ALTER).map(([k, v]) =>
            `<option value="${k}">${esc(v)}</option>`).join("")}</select></div>
        <div class="field"><label for="cp-mb">Meldebild</label>
          <textarea id="cp-mb" maxlength="800" rows="2" required
            placeholder="Was wurde gemeldet, was fandet ihr vor?"></textarea></div>
        <fieldset class="field xabcde-form"><legend class="small">Befund nach xABCDE
          <span class="tiny muted">· mindestens ein Feld</span></legend>
          ${NETZ_XABCDE.map(([k, b, name]) => `<div class="xab-row"><label for="cp-${k}"><abbr
            title="${esc(name)}">${b}</abbr><span class="sr-only"> ${esc(name)}</span></label>
            <input id="cp-${k}" maxlength="500" placeholder="${esc(name)}"></div>`).join("")}
        </fieldset>
        <div class="field"><label for="cp-mn">Maßnahmen (optional)</label>
          <textarea id="cp-mn" maxlength="1500" rows="2"></textarea></div>
        <div class="field"><label for="cp-frage">Frage an die Community</label>
          <textarea id="cp-frage" maxlength="800" rows="2" required
            placeholder="z. B. Was hättet ihr als Nächstes gemacht?"></textarea></div>` : ""}
      ${art === "algorithmus" ? `
        <div class="field"><label for="cp-titel">Titel</label>
          <input id="cp-titel" maxlength="160" required placeholder="z. B. Ablauf Anaphylaxie"></div>
        <div class="field-row">
          <div class="field"><label for="cp-quelle">Quelle</label>
            <input id="cp-quelle" maxlength="200" required placeholder="Herausgeber, Dokument"></div>
          <div class="field"><label for="cp-stand">Stand (optional)</label>
            <input id="cp-stand" maxlength="60" placeholder="z. B. 2025"></div>
        </div>
        <div class="field"><label for="cp-geltung">Geltungsbereich (optional)</label>
          <input id="cp-geltung" maxlength="160" placeholder="z. B. Rettungsdienstbereich"></div>
        <div class="field"><label for="cp-url">Link zum Dokument (optional)</label>
          <input id="cp-url" type="url" inputmode="url" placeholder="https://"></div>
        <p class="tiny muted">Teile nur, was du weitergeben darfst. Unter jedem Algorithmus steht:
        maßgeblich ist die SOP des eigenen ÄLRD.</p>` : ""}
      ${art === "wissen" ? `
        <div class="field"><label for="cp-titel">Titel</label>
          <input id="cp-titel" maxlength="200" required placeholder="z. B. S3-Leitlinie Polytrauma"></div>
        <div class="field"><label for="cp-url">Link</label>
          <input id="cp-url" type="url" inputmode="url" required placeholder="https://"></div>
        <div class="field"><label for="cp-quelle">Art der Quelle (optional)</label>
          <input id="cp-quelle" maxlength="120" list="cp-quellen" placeholder="Leitlinie, Studie …">
          <datalist id="cp-quellen"><option>Leitlinie</option><option>Studie</option>
            <option>Übersichtsarbeit</option><option>Fachartikel</option><option>Podcast</option></datalist></div>` : ""}
      ${art === "kompetenz" || art === "fall" || fv ? `<div id="cp-logbuch"></div>` : ""}
      ${mitMedien ? `
        <div class="media-pick" id="cp-medien"></div>
        <label class="btn-soft file-btn" id="cp-medien-btn">${NETZ_ICON.bild}<span>Fotos oder Videos</span>
          <input type="file" id="cp-datei" multiple
            accept="image/jpeg,image/png,image/webp,video/mp4,video/quicktime,video/webm"></label>
        <label class="check confirm" id="cp-confirm" hidden><input type="checkbox" id="cp-ok">
          <span>Auf den Bildern und Videos sind keine Patient*innen, Kennzeichen, Einsatzorte
          oder Monitorwerte mit Personenbezug zu erkennen.</span></label>` : ""}
      <div class="field"><label for="cp-text">${art === "beitrag" ? "Bildunterschrift oder Gedanke"
        : art === "algorithmus" ? "Kernaussage oder Schritte (optional)"
        : fv ? "Weitere Angaben (optional)"
        : "Was nimmst du mit? (optional)"}</label>
        <textarea id="cp-text" maxlength="3000" rows="${art === "beitrag" ? 4 : 3}"
          placeholder="#Hashtags helfen anderen, es zu finden. Mit @ erwähnst du Personen, denen du folgst."></textarea></div>
      <div class="field" id="cp-themen"></div>
      <label class="check"><input type="checkbox" id="cp-kaus"> Kommentare ausschalten</label>
      ${art === "fall" || fv ? `
        <div class="field"><label for="cp-delay">Veröffentlichen</label>
          <select id="cp-delay"><option value="0" ${fv ? "selected" : ""}>sofort</option><option value="1">in 1 Tag</option>
            <option value="3">in 3 Tagen</option><option value="7" ${fv ? "" : "selected"}>in 7 Tagen (empfohlen)</option>
            <option value="14">in 14 Tagen</option></select>
          <p class="tiny muted" data-s="mt-xs">Ein seltener Fall ist leicht wiederzuerkennen. Mit
          Abstand zum Einsatz geteilt, lässt er sich keinem Tag mehr zuordnen.</p></div>` : ""}
      ${NETZ_DATENSCHUTZ}
      <button class="btn-primary btn-lg" type="submit" id="cp-senden">Teilen</button>
      <p class="tiny muted" id="cp-err" role="alert"></p>
    </form>`, (body) => {
    const erw = erwaehnungsFeld($("#cp-text", body));
    body.closest(".sheet").classList.add("tall");
    if (fv) themen.add("peer-hilfe");
    themenWahlHtml($("#cp-themen", body), themen).catch(() => {});
    let kategorie = "selten";
    body.querySelectorAll("[data-kat]").forEach((b) => b.addEventListener("click", () => {
      body.querySelectorAll("[data-kat]").forEach((x) => x.setAttribute("aria-pressed", "false"));
      b.setAttribute("aria-pressed", "true");
      kategorie = b.dataset.kat;
    }));

    // --- Medien
    const zeigeMedien = () => {
      const box = $("#cp-medien", body);
      if (!box) return;
      box.innerHTML = medien.map((m, i) => `
        <div class="mp-tile">
          ${m.id && m.status === "bereit" ? `<img src="/api/netz/medien/${esc(m.id)}/vorschau" alt="">`
            : `<span class="mp-wait tiny">${m.fehler ? "Fehler" : m.status === "verarbeitung"
              ? "Video wird verarbeitet …" : `Lädt ${Math.round((m.fortschritt || 0) * 100)} %`}</span>`}
          ${m.art === "video" ? `<span class="g-sym">${NETZ_ICON.video}</span>` : ""}
          <button type="button" class="mp-x" data-weg="${i}" aria-label="Medium entfernen">${NETZ_ICON.x}</button>
        </div>`).join("");
      $("#cp-confirm", body).hidden = !medien.length;
      $("#cp-medien-btn", body).hidden = medien.length >= 10;
    };
    const datei = $("#cp-datei", body);
    if (datei) datei.addEventListener("change", () => {
      [...datei.files].slice(0, 10 - medien.length).forEach(async (f) => {
        const eintrag = { art: f.type.startsWith("video/") ? "video" : "bild", status: "laedt", fortschritt: 0 };
        medien.push(eintrag);
        zeigeMedien();
        try {
          const m = await hochladen(f, eintrag.art, (x) => { eintrag.fortschritt = x; zeigeMedien(); });
          Object.assign(eintrag, m);
          zeigeMedien();
          if (m.status === "verarbeitung") {
            Object.assign(eintrag, await warteAufVideo(m.id));
            if (eintrag.status === "fehler") throw new Error(eintrag.fehler || "Video unbrauchbar.");
            zeigeMedien();
          }
        } catch (err) {
          eintrag.fehler = err.message;
          $("#cp-err", body).textContent = err.message;
          zeigeMedien();
        }
      });
      datei.value = "";
    });
    const mbox = $("#cp-medien", body);
    if (mbox) mbox.addEventListener("click", (e) => {
      const w = e.target.closest("[data-weg]");
      if (!w) return;
      const [m] = medien.splice(Number(w.dataset.weg), 1);
      if (m && m.id) api("/api/netz/medien/entwurf/" + encodeURIComponent(m.id), { method: "DELETE" }).catch(() => {});
      zeigeMedien();
    });

    // --- Logbuch
    const logbuch = $("#cp-logbuch", body);
    const zeigeEinsatz = (enc, vorauswahl) => {
      const medGruppe = (id) => {
        const m = (state.medications || []).find((x) => x.id === id);
        return m ? m.divi_group || "" : "";
      };
      if (vorauswahl) {
        (enc.attempts.some((a) => a.id === vorauswahl) ? auswahl.a : auswahl.m).add(vorauswahl);
      } else if (art === "kompetenz") {
        enc.attempts.forEach((a) => auswahl.a.add(a.id));
        enc.medications.forEach((m) => auswahl.m.add(m.id));
      }
      const hatZek = (enc.complications || []).length
        || enc.attempts.some((a) => (a.complications || []).length)
        || enc.medications.some((m) => (m.complications || []).length);
      logbuch.innerHTML = `
        <fieldset class="kt-list">
          <legend class="small">Aus dem Logbuch <span class="tiny muted">· Einsatzdaten bleiben privat</span></legend>
          ${enc.attempts.map((a) => `<label class="kt-row"><input type="checkbox" data-typ="a"
            value="${esc(a.id)}" ${auswahl.a.has(a.id) ? "checked" : ""}>
            <span class="cat-badge" data-cat="${esc(a.measure_category)}">${esc(a.measure_category)}</span>
            <span class="grow">${esc(a.measure_name)}</span>${statusBadge(a.outcome)}</label>`).join("")}
          ${enc.medications.map((m) => `<label class="kt-row"><input type="checkbox" data-typ="m"
            value="${esc(m.id)}" ${auswahl.m.has(m.id) ? "checked" : ""}>
            ${diviLabel({ name: m.medication_name, divi_group: medGruppe(m.medication_id) })}
            <span class="grow tiny muted">${esc(m.route || "")}</span>${statusBadge(m.outcome || "erfolgreich")}</label>`).join("")}
        </fieldset>
        ${hatZek ? `<label class="check"><input type="checkbox" id="cp-zek"> ZEK-Bezeichnungen mitteilen
          (ohne Bezug und Patientenschaden)</label>` : ""}
        ${enc.naca ? `<label class="check"><input type="checkbox" id="cp-naca"> NACA-Wert mitteilen</label>` : ""}
        <button type="button" class="link-btn small strong" id="cp-anderer">Anderen Einsatz wählen</button>`;
      logbuch.querySelectorAll("[data-typ]").forEach((i) => i.addEventListener("change", () => {
        const set = i.dataset.typ === "a" ? auswahl.a : auswahl.m;
        if (i.checked) set.add(i.value); else set.delete(i.value);
      }));
      const z = $("#cp-zek", logbuch);
      if (z) z.addEventListener("change", () => { auswahl.zek = z.checked; });
      const n = $("#cp-naca", logbuch);
      if (n) n.addEventListener("change", () => { auswahl.naca = n.checked; });
      $("#cp-anderer", logbuch).addEventListener("click", () => {
        auswahl.a.clear(); auswahl.m.clear(); waehleEinsatz();
      });
    };
    const waehleEinsatz = async () => {
      logbuch.innerHTML = `<p class="small muted">Wird geladen …</p>`;
      const d = await api("/api/encounters?limit=30");
      const liste = d.encounters.filter((e) => e.attempt_count || e.medication_count);
      logbuch.innerHTML = `
        <div class="field"><span class="field-label small">${art === "fall"
          ? "Einträge aus dem Logbuch anhängen (optional)" : "Aus welchem Einsatz?"}</span>
        ${liste.length ? `<div class="stack">${liste.map((e) => `
          <button type="button" class="choice compact" data-enc="${esc(e.id)}">
            <strong>${esc(fmtDate(e.enc_date))}</strong>
            <span class="tiny muted">${e.attempt_count} Maßnahmen · ${e.medication_count} Medikamente${
              e.naca ? " · NACA " + esc(e.naca) : ""} · Datum bleibt privat</span></button>`).join("")}</div>`
          : `<p class="small muted">Noch kein Einsatz mit Einträgen.</p>`}</div>`;
      logbuch.querySelectorAll("[data-enc]").forEach((b) => b.addEventListener("click", async () => {
        zeigeEinsatz(await api("/api/encounters/" + encodeURIComponent(b.dataset.enc)), null);
      }));
    };
    if (logbuch) {
      if (vorgabe.enc) zeigeEinsatz(vorgabe.enc, vorgabe.vorauswahl);
      else if (art === "kompetenz") waehleEinsatz();
      else if (fv) {
        logbuch.innerHTML = `<button type="button" class="btn-soft" id="cp-log">Maßnahmen aus dem Logbuch anhängen (optional)</button>`;
        $("#cp-log", logbuch).addEventListener("click", waehleEinsatz);
      }
      else {
        logbuch.innerHTML = `<button type="button" class="btn-soft" id="cp-log">Einträge aus dem Logbuch anhängen</button>`;
        $("#cp-log", logbuch).addEventListener("click", waehleEinsatz);
      }
    }

    // --- Absenden
    $("#cp-form", body).addEventListener("submit", async (e) => {
      e.preventDefault();
      const err = $("#cp-err", body);
      err.textContent = "";
      if (medien.some((m) => m.status !== "bereit")) {
        err.textContent = medien.some((m) => m.fehler)
          ? "Entferne zuerst das fehlerhafte Medium." : "Warte, bis alle Medien verarbeitet sind.";
        return;
      }
      const wert = (sel) => { const n = $(sel, body); return n ? n.value : ""; };
      const daten = { art, text: wert("#cp-text"), themen: [...themen],
        kommentare_aus: !!($("#cp-kaus", body) || {}).checked, erwaehnungen: erw.ids() };
      if (art === "fall") {
        daten.titel = wert("#cp-titel");
        daten.details = { kategorie, besonderheit: wert("#cp-bes"), gut: wert("#cp-gut"), anders: wert("#cp-and") };
        daten.verzoegerung_tage = Number(wert("#cp-delay") || 0);
      } else if (art === "algorithmus") {
        daten.titel = wert("#cp-titel");
        daten.details = { quelle: wert("#cp-quelle"), stand: wert("#cp-stand"), geltung: wert("#cp-geltung") };
        if (wert("#cp-url")) daten.link_url = wert("#cp-url").trim();
      } else if (fv) {
        daten.titel = wert("#cp-titel");
        daten.details = { meldebild: wert("#cp-mb"), massnahmen: wert("#cp-mn"),
          frage: wert("#cp-frage"), altersgruppe: wert("#cp-alter") };
        NETZ_XABCDE.forEach(([k]) => { daten.details[k] = wert("#cp-" + k); });
        if (!NETZ_XABCDE.some(([k]) => daten.details[k].trim())) {
          err.textContent = "Halte mindestens einen Befund nach xABCDE fest."; return;
        }
        daten.verzoegerung_tage = Number(wert("#cp-delay") || 0);
      } else if (art === "wissen") {
        daten.link_url = wert("#cp-url").trim();
        daten.link_titel = wert("#cp-titel");
        daten.link_quelle = wert("#cp-quelle");
      }
      if (art === "kompetenz" || art === "fall" || fv) {
        daten.attempt_ids = [...auswahl.a];
        daten.medication_ids = [...auswahl.m];
        daten.mit_zek = auswahl.zek;
        daten.mit_naca = auswahl.naca;
        if (art === "kompetenz" && !daten.attempt_ids.length && !daten.medication_ids.length) {
          err.textContent = "Wähle mindestens einen Eintrag."; return;
        }
      }
      if (medien.length) {
        daten.medien_ids = medien.map((m) => m.id);
        daten.medien_bestaetigt = !!($("#cp-ok", body) || {}).checked;
        if (!daten.medien_bestaetigt) {
          err.textContent = "Bitte bestätige, dass auf den Medien niemand und nichts mit Personenbezug zu erkennen ist.";
          return;
        }
      }
      const knopf = $("#cp-senden", body);
      knopf.disabled = true;
      try {
        const b = await api("/api/netz/beitraege", { method: "POST", body: daten });
        closeSheet();
        toast(b.geplant ? `Geplant. Der Beitrag erscheint ${relZeit(b.erstellt)}.` : "Geteilt.");
        if (location.hash === "#/" || location.hash === "") render(); else location.hash = "#/";
      } catch (er) { err.textContent = er.message; knopf.disabled = false; }
    });
  });
}

async function teilenAusEinsatz(enc, vorauswahl) {
  const p = await netzProfil();
  if (!p.aktiv) {
    sheet("Kompetenznetz", `
      <p class="small">Zum Teilen das Kompetenznetz einschalten. Dein Logbuch bleibt davon
      unberührt, geteilt wird nur, was du auswählst.</p>
      <a class="btn btn-primary link-plain" href="#/" data-s="mt-md">Kompetenznetz ansehen</a>`);
    return;
  }
  composer("kompetenz", { enc, vorauswahl });
}

// ---------------------------------------------------- Einstellungen: Netz

/* Die Karten tragen ihre Überschriften als Gruppenschlüssel, siehe
   viewEinstellungen in app.js. */
function netzProfilKarten(p) {
  const kompetenzen = p.kompetenzen.map((k) => `
    <label class="kt-row">
      <input type="checkbox" data-kompetenz="${esc(k.measure_id)}" ${k.sichtbar ? "checked" : ""}>
      <span class="cat-badge" data-cat="${esc(k.kategorie)}">${esc(k.kategorie)}</span>
      <span class="grow">${esc(k.name)}</span>
      <span class="tiny muted">${k.anzahl}×</span>
    </label>`).join("");
  const eintraege = (p.eintraege || []).map((e) => `
    <li class="entry-row"><span class="grow"><strong>${esc(e.titel)}</strong>
      <span class="tiny muted np-sub">${esc(NETZ_EINTRAG[e.art])}${e.org ? " · " + esc(e.org) : ""}${
        e.von ? " · " + esc(monatJahr(e.von)) : ""}${e.bis ? " – " + esc(monatJahr(e.bis)) : ""}</span></span>
      <button type="button" class="btn-quiet small" data-eintrag-weg="${esc(e.id)}">Entfernen</button></li>`).join("");
  return `
    <div class="card pad-lg" data-s="mt-md">
      <h2>Kompetenznetz</h2>
      <label class="switch-row"><span class="grow"><strong>Kompetenznetz</strong>
        <span class="tiny muted np-sub">${p.aktiv ? "Eingeschaltet" : "Aus: niemand findet dich"}</span></span>
        <input type="checkbox" role="switch" id="netz-schalter" ${p.aktiv ? "checked" : ""}></label>
      <label class="switch-row"><span class="grow"><strong>Privates Konto</strong>
        <span class="tiny muted np-sub">Nur bestätigte Follower sehen Beiträge, Chronik, Kompetenzen
        und Info</span></span>
        <input type="checkbox" role="switch" id="netz-privat" ${p.privat ? "checked" : ""}></label>
      <p class="tiny muted" data-s="mt-sm">Ausschalten blendet Profil und Beiträge sofort für alle
      aus. Alles bleibt gespeichert, bis du es löschst oder dein Konto löschst.</p>
      ${p.aktiv ? `<a class="btn link-plain" data-s="mt-sm" href="#/profil">Profil ansehen</a>` : ""}
    </div>

    <div class="card pad-lg" data-s="mt-md">
      <h2>Profilbilder</h2>
      <p class="tiny muted" data-s="mt-xs">JPEG, PNG oder WebP. Jedes Bild wird neu berechnet;
      Aufnahmeort, Kameradaten und andere Metadaten werden dabei entfernt. Das Profilbild sehen
      alle Mitglieder im Netz, das Titelbild wer auch deine Beiträge sieht.</p>
      <div class="media-edit" data-s="mt-md">
        <div class="banner small-banner">${p.banner_id
          ? `<img src="/api/netz/medien/${esc(p.banner_id)}" alt="Titelbild" decoding="async">` : ""}</div>
        ${avatarHtml({ id: p.id, name: p.name, avatar_id: p.avatar_id }, "xl")}
      </div>
      <div class="sheet-actions two">
        <label class="btn file-btn">Profilbild wählen
          <input type="file" accept="image/jpeg,image/png,image/webp" data-bild="avatar"></label>
        <label class="btn file-btn">Titelbild wählen
          <input type="file" accept="image/jpeg,image/png,image/webp" data-bild="banner"></label>
      </div>
      <div class="row wrap" data-s="gap-sm mt-sm">
        ${p.avatar_id ? `<button class="btn-quiet small" data-bild-weg="avatar">Profilbild entfernen</button>` : ""}
        ${p.banner_id ? `<button class="btn-quiet small" data-bild-weg="banner">Titelbild entfernen</button>` : ""}
      </div>
    </div>

    <div class="card pad-lg" data-s="mt-md">
      <h2>Vorstellung</h2>
      <form id="vorst-form" class="stack" data-s="mt-md">
        <div class="field"><label for="nh">Kurzbeschreibung</label>
          <input id="nh" maxlength="120" value="${esc(p.headline)}"
            placeholder="z. B. Notfallsanitäter · Praxisanleiter"></div>
        <div class="field"><label for="na">Über mich</label>
          <textarea id="na" maxlength="1500" rows="3"
            placeholder="Schwerpunkte, Fortbildungen, was dich interessiert">${esc(p.about)}</textarea></div>
        <button class="btn-primary" type="submit">Vorstellung speichern</button>
        <p class="tiny muted" id="vorst-err" role="alert"></p>
      </form>
    </div>

    ${ortKarten(p)}

    <div class="card pad-lg" data-s="mt-md">
      <h2>Werdegang und Zertifikate</h2>
      <p class="tiny muted" data-s="mt-xs">Kurse mit Ablaufdatum gehören unter „Qualifikationen
      und Kurse“. Hier steht der Werdegang und alles, was es dort nicht gibt.</p>
      ${eintraege ? `<ul class="entry-list" data-s="mt-sm">${eintraege}</ul>` : ""}
      <form id="eintrag-form" class="stack" data-s="mt-md">
        <div class="field-row">
          <div class="field"><label for="ea">Art</label>
            <select id="ea">${Object.entries(NETZ_EINTRAG).map(([k, v]) =>
              `<option value="${k}">${esc(v)}</option>`).join("")}</select></div>
          <div class="field"><label for="etitel">Titel</label>
            <input id="etitel" maxlength="120" required placeholder="z. B. PHTLS Provider"></div>
        </div>
        <div class="field"><label for="eo">Organisation (optional)</label><input id="eo" maxlength="120"></div>
        <div class="field-row">
          <div class="field"><label for="evon">Von (optional)</label><input id="evon" type="month"></div>
          <div class="field"><label for="ebis">Bis oder gültig bis (optional)</label><input id="ebis" type="month"></div>
        </div>
        <button class="btn-soft" type="submit">Hinzufügen</button>
        <p class="tiny muted" id="eintrag-err" role="alert"></p>
      </form>
    </div>

    <div class="card pad-lg" data-s="mt-md">
      <h2>Kompetenzen freigeben</h2>
      <p class="tiny muted" data-s="mt-xs">Angehakte Maßnahmen stehen mit Anzahl und
      Erfolgsquote am Profil. Neue Maßnahmen sind zunächst nicht freigegeben.</p>
      ${kompetenzen ? `<div class="kt-list" data-s="mt-md">${kompetenzen}</div>`
        : `<p class="small muted" data-s="mt-sm">Noch keine Maßnahmen dokumentiert.</p>`}
    </div>

    <div class="card pad-lg" data-s="mt-md">
      <h2>Blockiert</h2>
      <div id="blockiert" class="small muted" data-s="mt-sm">Wird geladen …</div>
    </div>`;
}

function bindeNetzProfil() {
  const schalte = async (daten, frage) => {
    if (frage && !confirm(frage)) { render(); return; }
    try {
      NETZ.profil = await api("/api/netz/profil", { method: "PUT", body: daten });
      render();
    } catch (err) { toast(err.message); render(); }
  };
  $("#netz-schalter").addEventListener("change", (e) => schalte({ aktiv: e.target.checked },
    e.target.checked ? null : "Kompetenznetz ausschalten? Profil und Beiträge sind dann für niemanden mehr sichtbar."));
  $("#netz-privat").addEventListener("change", (e) => schalte({ privat: e.target.checked },
    e.target.checked ? null : "Konto öffentlich machen? Offene Folgeanfragen werden dabei angenommen."));

  app().querySelectorAll("[data-bild]").forEach((input) =>
    input.addEventListener("change", async () => {
      const datei = input.files[0];
      if (!datei) return;
      try {
        toast("Bild wird verarbeitet …");
        await hochladen(datei, input.dataset.bild);
        NETZ.profil = null;
        toast("Bild gespeichert."); render();
      } catch (err) { toast(err.message); }
    }));
  app().querySelectorAll("[data-bild-weg]").forEach((b) =>
    b.addEventListener("click", async () => {
      await api("/api/netz/medien/profil/" + b.dataset.bildWeg, { method: "DELETE" });
      NETZ.profil = null; toast("Bild entfernt."); render();
    }));

  $("#vorst-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      NETZ.profil = await api("/api/netz/profil", { method: "PUT", body: {
        headline: $("#nh").value, about: $("#na").value } });
      $("#vorst-err").textContent = "";
      toast("Vorstellung gespeichert.");
    } catch (err) { $("#vorst-err").textContent = err.message; }
  });

  $("#eintrag-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api("/api/netz/eintraege", { method: "POST", body: {
        art: $("#ea").value, titel: $("#etitel").value, org: $("#eo").value,
        von: $("#evon").value || null, bis: $("#ebis").value || null } });
      toast("Hinzugefügt."); render();
    } catch (err) { $("#eintrag-err").textContent = err.message; }
  });
  app().querySelectorAll("[data-eintrag-weg]").forEach((b) => b.addEventListener("click", async () => {
    await api("/api/netz/eintraege/" + encodeURIComponent(b.dataset.eintragWeg), { method: "DELETE" });
    render();
  }));

  app().querySelectorAll("[data-kompetenz]").forEach((box) =>
    box.addEventListener("change", async () => {
      try {
        await api("/api/netz/kompetenzen/" + encodeURIComponent(box.dataset.kompetenz),
          { method: "PUT", body: { sichtbar: box.checked } });
      } catch (err) { box.checked = !box.checked; toast(err.message); }
    }));

  api("/api/netz/blockiert").then((r) => {
    const ziel = $("#blockiert");
    if (!ziel) return;
    ziel.innerHTML = r.personen.length ? `<ul class="entry-list">${r.personen.map((x) => `
      <li class="entry-row"><span class="grow">${esc(x.name)}</span>
        <button type="button" class="btn-quiet small" data-entblocken="${esc(x.id)}">Freigeben</button></li>`).join("")}</ul>`
      : "Niemand blockiert.";
    ziel.querySelectorAll("[data-entblocken]").forEach((b) => b.addEventListener("click", async () => {
      await api("/api/netz/blockieren/" + encodeURIComponent(b.dataset.entblocken), { method: "DELETE" });
      render();
    }));
  });
}
