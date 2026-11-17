/* SCOPE X - Kompetenznetz
   Ein Lernfeed unter bestätigten Kontakten: Beiträge, geteiltes Wissen,
   Kompetenzen aus dem eigenen Logbuch, Anerkennung und Kommentare.

   Die Datenschutzgrenze liegt im Server, nicht hier. Diese Datei zeigt nur
   an, was der Server herausgibt, und erklärt vorher, was geteilt wird.
   Einsatznummer, Fahrzeug, Schicht, Datum und Uhrzeit eines Einsatzes,
   Dosis und Notizen verlassen das eigene Logbuch nie — auch dann nicht,
   wenn diese Datei manipuliert wird.

   Wird vor app.js geladen: die Routentabelle dort verweist auf die
   Ansichten hier. Alle Helfer aus app.js werden erst beim Aufruf
   gebraucht. Eigene Konstanten tragen das Präfix NETZ_, damit sie sich
   nicht mit Namen aus app.js überschneiden. */

"use strict";

const NETZ_REAKTIONEN = [
  ["stark", "Stark"], ["lehrreich", "Lehrreich"], ["danke", "Danke"],
];
const NETZ_ROLLEN = {
  kollegial: "Kollegial gesehen",
  praxisanleitung: "Als Praxisanleitung",
};
const NETZ = { ungelesen: 0, stand: 0, profil: null };

// ---------------------------------------------------------------- Helfer

/* Zeit wie in sozialen Netzen: relativ, ab fünf Wochen nur Monat und
   Jahr. Ein genaues Datum unter einem Kompetenzbeitrag würde den
   Einsatztag nahelegen; der Monat tut das nicht. */
function relZeit(iso) {
  const t = Date.parse(iso);
  if (!t) return "";
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 60) return "gerade eben";
  const min = Math.floor(s / 60);
  if (min < 60) return `vor ${min} Min.`;
  const std = Math.floor(min / 60);
  if (std < 24) return `vor ${std} Std.`;
  const tage = Math.floor(std / 24);
  if (tage < 2) return "gestern";
  if (tage < 7) return `vor ${tage} Tagen`;
  const wochen = Math.floor(tage / 7);
  if (tage < 35) return wochen === 1 ? "vor 1 Woche" : `vor ${wochen} Wochen`;
  return new Date(t).toLocaleDateString("de-DE", { month: "long", year: "numeric" });
}

function initialenVon(name) {
  const teile = String(name || "?").trim().split(/\s+/);
  return ((teile[0] || "?")[0] + (teile.length > 1 ? teile[teile.length - 1][0] : ""))
    .toUpperCase();
}

/* Farbe des Initialenkreises aus der Kennung, damit dieselbe Person
   überall gleich aussieht. Vier Töne aus der SCOPE-X-Palette, über
   data-farbe gesetzt — ein style-Attribut blockiert die CSP. */
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

async function netzProfil(neu = false) {
  if (!NETZ.profil || neu) NETZ.profil = await api("/api/netz/profil");
  return NETZ.profil;
}

/* Zähler ungelesener Mitteilungen. Höchstens alle 30 Sekunden abgefragt,
   beim Seitenwechsel angestoßen — kein Dauerabruf im Hintergrund. */
async function mitteilungsZaehler(sofort = false) {
  if (!state.auth || !state.auth.authenticated) return;
  if (!sofort && Date.now() - NETZ.stand < 30000) { zeigeZaehler(); return; }
  NETZ.stand = Date.now();
  try {
    const m = await api("/api/netz/mitteilungen");
    NETZ.ungelesen = m.ungelesen || 0;
  } catch (_) { /* Zähler ist Komfort, kein Fehlerfall */ }
  zeigeZaehler();
}

function zeigeZaehler() {
  document.querySelectorAll("[data-zaehler]").forEach((n) => {
    n.textContent = NETZ.ungelesen > 9 ? "9+" : String(NETZ.ungelesen || "");
    n.hidden = !NETZ.ungelesen;
  });
  document.querySelectorAll("[data-zaehler-label]").forEach((n) => {
    n.setAttribute("aria-label", NETZ.ungelesen
      ? `Mitteilungen, ${NETZ.ungelesen} ungelesen` : "Mitteilungen");
  });
}

const NETZ_DATENSCHUTZ = `
  <div class="privacy-box">
    <strong>Bleibt immer privat</strong>
    <p class="tiny">Datum und Uhrzeit des Einsatzes, Einsatznummer, Fahrzeug,
    Schicht, Dosierungen und Notizen. Ein Beitrag, der eine eigene
    Einsatznummer, ein eigenes Fahrzeug, einen eigenen Einsatztag oder eine
    Uhrzeit enthält, wird abgelehnt.</p>
    <p class="tiny">Teile Lernerfahrung, nicht den Einsatz. Nichts, was auf
    Patient*innen, Ort oder Zeitpunkt schließen lässt. Tipp: mit etwas
    Abstand zum Einsatz posten.</p>
  </div>`;

// ------------------------------------------------------------ Beitragskarte

function kompetenzBlock(k) {
  if (!k) return "";
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
  // nofollow und noreferrer: der Zielserver erfährt nicht, aus welchem
  // Netz der Klick kam, und der geteilte Link wertet nichts auf.
  return `
    <a class="link-card" href="${esc(l.url)}" target="_blank"
       rel="noopener noreferrer nofollow">
      <span class="lc-kind tiny">${esc(l.quelle || "Quelle")}</span>
      <strong>${esc(l.titel)}</strong>
      <span class="tiny muted">${esc(host)} ↗</span>
    </a>`;
}

function postCard(b) {
  const r = b.reaktionen || {};
  const reaktionen = NETZ_REAKTIONEN.map(([k, label]) => `
    <button type="button" class="react" data-akt="reaktion" data-art="${k}"
      aria-pressed="${b.meine_reaktion === k}">${esc(label)}${
        r[k] ? ` <span class="n">${r[k]}</span>` : ""}</button>`).join("");
  return `
    <article class="npost" data-post="${esc(b.id)}" data-eigen="${b.eigen}"
      data-moderierbar="${!b.eigen && b.darf_entfernen}">
      <header class="np-head">
        <a href="#/person/${esc(b.autor.id)}" class="np-who link-plain">
          ${avatarHtml(b.autor, "m")}
          <span class="grow">
            <strong>${esc(b.autor.name)}</strong>
            <span class="tiny muted np-sub">${esc(b.autor.headline)}${
              b.autor.headline ? " · " : ""}${esc(relZeit(b.erstellt))}</span>
          </span>
        </a>
        <button type="button" class="icon-btn flat" data-akt="menue"
          aria-label="Weitere Aktionen zum Beitrag">
          <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <circle cx="5" cy="12" r="2.1"/><circle cx="12" cy="12" r="2.1"/>
            <circle cx="19" cy="12" r="2.1"/></svg></button>
      </header>
      ${b.entfernt ? `<div class="notice warn" data-s="mt-sm">Von der Administration
        entfernt${b.entfernt_grund ? `: ${esc(b.entfernt_grund)}` : "."} Nur du
        siehst diesen Beitrag noch.</div>` : ""}
      ${b.text ? `<div class="np-text">${esc(b.text)}</div>` : ""}
      ${linkBlock(b.link)}
      ${kompetenzBlock(b.kompetenz)}
      <footer class="np-foot">${reaktionen}${kommentarKnopf(b.kommentare, false)}</footer>
      <div class="np-comments" hidden></div>
    </article>`;
}

/* Sprechblase statt Wort: vier Wörter passen auf einem Telefon nicht in
   eine Zeile. Der Name steht im aria-label. */
function kommentarKnopf(n, offen) {
  return `<button type="button" class="react react-k" data-akt="kommentare"
    aria-expanded="${offen}" aria-label="Kommentare${n ? `, ${n}` : ""}">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
      stroke-linejoin="round" aria-hidden="true">
      <path d="M4.5 6.5a2 2 0 0 1 2-2h11a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H10l-4 3.2v-3.2h0.5a2 2 0 0 1-2-2z"/>
    </svg>${n ? `<span class="n">${n}</span>` : ""}</button>`;
}

function kommentarListe(postId, liste) {
  const formular = canWrite() ? `
    <form class="kommentar-form row" data-s="gap-sm mt-sm">
      <label class="sr-only" for="k-${esc(postId)}">Kommentar</label>
      <input id="k-${esc(postId)}" maxlength="1000" placeholder="Kommentieren …"
        autocomplete="off" required>
      <button class="btn-primary" type="submit">Senden</button>
    </form>` : "";
  return `
    ${liste.length ? `<ul class="k-list">${liste.map((k) => `
      <li class="k-item">
        <a href="#/person/${esc(k.autor.id)}" class="link-plain"
          aria-label="Profil von ${esc(k.autor.name)}">${avatarHtml(k.autor, "s")}</a>
        <div class="grow k-bubble">
          <div class="spread"><strong class="small">${esc(k.autor.name)}</strong>
            <span class="tiny muted">${esc(relZeit(k.erstellt))}</span></div>
          <div class="small np-text">${esc(k.text)}</div>
          ${k.darf_entfernen ? `<button type="button" class="btn-quiet tiny"
            data-k-del="${esc(k.id)}">Entfernen</button>` : ""}
        </div>
      </li>`).join("")}</ul>` : `<p class="tiny muted">Noch keine Kommentare.</p>`}
    ${formular}
    <p class="tiny err muted"></p>`;
}

/* Ein Zuhörer für alle Beitragskarten eines Bereichs. Aktionen ersetzen
   nur die betroffene Karte, die Seite bleibt an ihrer Position. */
function bindePosts(bereich) {
  if (bereich.dataset.gebunden) return;
  bereich.dataset.gebunden = "1";

  bereich.addEventListener("click", async (e) => {
    const knopf = e.target.closest("[data-akt], [data-k-del]");
    if (!knopf || !bereich.contains(knopf)) return;
    const karte = knopf.closest("[data-post]");
    if (!karte) return;
    const id = karte.dataset.post;
    try {
      if (knopf.dataset.kDel) {
        await api("/api/netz/kommentare/" + encodeURIComponent(knopf.dataset.kDel),
          { method: "DELETE" });
        await ladeKommentare(karte, true);
        return;
      }
      const akt = knopf.dataset.akt;
      if (akt === "reaktion") {
        const an = knopf.getAttribute("aria-pressed") === "true";
        const b = await api(`/api/netz/beitraege/${encodeURIComponent(id)}/reaktion`,
          an ? { method: "DELETE" } : { method: "PUT", body: { art: knopf.dataset.art } });
        ersetzeKarte(karte, b);
      } else if (akt === "kommentare") {
        const box = $(".np-comments", karte);
        const offen = !box.hidden;
        box.hidden = offen;
        knopf.setAttribute("aria-expanded", String(!offen));
        if (!offen) await ladeKommentare(karte, false);
      } else if (akt === "menue") {
        beitragMenue(karte, knopf.dataset);
      }
    } catch (err) { toast(err.message); }
  });

  bereich.addEventListener("submit", async (e) => {
    const form = e.target.closest(".kommentar-form");
    if (!form) return;
    e.preventDefault();
    const karte = form.closest("[data-post]");
    const feld = $("input", form);
    try {
      const k = await api(`/api/netz/beitraege/${encodeURIComponent(karte.dataset.post)}/kommentare`,
        { method: "POST", body: { text: feld.value } });
      zeigeKommentare(karte, k.kommentare);
      const f2 = $(".kommentar-form input", karte);
      if (f2) f2.focus();
    } catch (err) {
      const fehler = $(".np-comments .err", karte);
      if (fehler) fehler.textContent = err.message;
    }
  });
}

async function ladeKommentare(karte, zaehlerNeu) {
  const k = await api(`/api/netz/beitraege/${encodeURIComponent(karte.dataset.post)}/kommentare`);
  zeigeKommentare(karte, k.kommentare);
  if (zaehlerNeu) { /* Zähler wird in zeigeKommentare gesetzt */ }
}

function zeigeKommentare(karte, liste) {
  const box = $(".np-comments", karte);
  box.innerHTML = kommentarListe(karte.dataset.post, liste);
  box.hidden = false;
  const knopf = $('[data-akt="kommentare"]', karte);
  if (knopf) knopf.outerHTML = kommentarKnopf(liste.length, true);
}

function ersetzeKarte(karte, b) {
  const offen = !$(".np-comments", karte).hidden;
  const tmp = document.createElement("div");
  tmp.innerHTML = postCard(b).trim();
  const neu = tmp.firstElementChild;
  karte.replaceWith(neu);
  if (offen) ladeKommentare(neu, false).catch(() => {});
}

function beitragMenue(karte) {
  const id = karte.dataset.post;
  const eigen = karte.dataset.eigen === "true";
  const moderierbar = karte.dataset.moderierbar === "true";
  sheet("Beitrag", `
    <div class="stack">
      ${eigen ? `<button type="button" class="choice" id="bm-loeschen">
        <strong>Beitrag löschen</strong>
        <span class="tiny muted">Mit allen Kommentaren und Reaktionen, endgültig</span></button>` : `
      <button type="button" class="choice" id="bm-melden">
        <strong>Melden</strong>
        <span class="tiny muted">Lässt auf Patient*innen, Ort oder Zeitpunkt schließen oder verletzt andere</span></button>`}
      ${moderierbar ? `<button type="button" class="choice" id="bm-mod">
        <strong>Als Administration entfernen</strong>
        <span class="tiny muted">Mit Begründung, steht im Änderungsprotokoll</span></button>` : ""}
    </div>`, (body) => {
    const l = $("#bm-loeschen", body);
    if (l) l.addEventListener("click", async () => {
      if (!confirm("Diesen Beitrag löschen? Kommentare und Reaktionen gehen mit.")) return;
      try {
        await api("/api/netz/beitraege/" + encodeURIComponent(id), { method: "DELETE" });
        closeSheet(); karte.remove(); toast("Beitrag gelöscht.");
      } catch (err) { toast(err.message); }
    });
    const m = $("#bm-melden", body);
    if (m) m.addEventListener("click", () => meldenSheet(id));
    const mod = $("#bm-mod", body);
    if (mod) mod.addEventListener("click", () => moderierenSheet(id, karte));
  });
}

function meldenSheet(id) {
  sheet("Beitrag melden", `
    <p class="small">Melde einen Beitrag, wenn er auf eine Patientin oder
    einen Patienten, einen Einsatzort oder einen Zeitpunkt schließen lässt
    oder andere verletzt. Die Administration erhält Zugriff auf genau diesen
    Beitrag und entscheidet.</p>
    <div class="sheet-actions two">
      <button type="button" data-close>Abbrechen</button>
      <button type="button" class="btn-primary" id="melden-ok">Melden</button>
    </div>`, (body) => {
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
    <p class="small muted">Der Beitrag verschwindet für alle außer der
    Verfasserin oder dem Verfasser. Der Grund wird mitgeteilt und im
    Änderungsprotokoll festgehalten.</p>
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

// --------------------------------------------------------------- Startseite

function netzKopf(titel, unter) {
  return `
    <div class="page-head netz-head">
      <div class="spread">
        <div>
          <h1>${esc(titel)}</h1>
          ${unter ? `<p class="muted small">${unter}</p>` : ""}
        </div>
        <div class="row" data-s="gap-sm">
          <a class="icon-btn link-plain" href="#/kontakte" aria-label="Kontakte">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"
              stroke-linecap="round" aria-hidden="true"><circle cx="9" cy="8.2" r="3.2"/>
              <path d="M3.2 19.2a5.9 5.9 0 0 1 11.6 0"/><path d="M18 8v6M15 11h6"/></svg></a>
          <a class="icon-btn link-plain" href="#/mitteilungen" data-zaehler-label
             aria-label="Mitteilungen">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"
              stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 1.8h-15z"/>
              <path d="M10 20.3a2.2 2.2 0 0 0 4 0"/></svg>
            <span class="badge" data-zaehler hidden></span></a>
        </div>
      </div>
    </div>`;
}

async function viewNetz() {
  const p = await netzProfil(true);
  if (!p.aktiv) return netzEinstieg(p);

  const feed = await api("/api/netz/feed");
  app().innerHTML = `
    ${netzKopf("Kompetenznetz", "Lernen aus dem Einsatzalltag, unter Kolleg*innen")}
    ${canWrite() ? `
    <div class="composer-prompt">
      ${avatarHtml({ id: state.auth.user.id, name: p.name, avatar_id: p.avatar_id }, "m")}
      <button type="button" class="prompt-btn" id="cp-text">Was hast du gelernt?</button>
    </div>
    <div class="row wrap composer-quick" data-s="gap-sm">
      <button type="button" class="chip" id="cp-wissen">Studie · Leitlinie</button>
      <button type="button" class="chip" id="cp-kompetenz">Aus dem Logbuch</button>
    </div>` : ""}
    <div id="netz-feed" class="stack" data-s="mt-md"></div>
    <div id="netz-mehr"></div>
    ${pageFoot()}`;
  zeigeZaehler();

  const cpText = $("#cp-text");
  if (cpText) {
    cpText.addEventListener("click", () => composerSheet("text"));
    $("#cp-wissen").addEventListener("click", () => composerSheet("wissen"));
    $("#cp-kompetenz").addEventListener("click", () => composerSheet("kompetenz"));
  }

  const liste = $("#netz-feed");
  bindePosts(liste);
  if (!feed.beitraege.length) {
    liste.innerHTML = `<div class="empty">${markSvg("mark")}
      <strong>Noch ist es ruhig hier.</strong>
      Der Feed zeigt deine Beiträge und die deiner Kontakte.
      <a href="#/kontakte">Kolleg*innen finden</a></div>`;
    return;
  }
  liste.innerHTML = feed.beitraege.map(postCard).join("");
  mehrLaden(feed.weiter);
}

function mehrLaden(weiter) {
  const box = $("#netz-mehr");
  if (!box) return;
  if (!weiter) { box.innerHTML = ""; return; }
  box.innerHTML = `<button type="button" class="btn-quiet btn-lg" data-s="mt-md"
    id="mehr">Ältere Beiträge laden</button>`;
  $("#mehr").addEventListener("click", async () => {
    const f = await api("/api/netz/feed?vor=" + encodeURIComponent(weiter));
    $("#netz-feed").insertAdjacentHTML("beforeend", f.beitraege.map(postCard).join(""));
    mehrLaden(f.weiter);
  });
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
      <p class="small" data-s="mt-sm">Teile, was du gelernt hast: eine
      gelungene Maßnahme aus deinem Logbuch, eine neue Leitlinie, eine Studie,
      die deine Praxis verändert. Bestätigte Kontakte geben Anerkennung,
      kommentieren und bestätigen deine Kompetenzen.</p>
      <ul class="check-list small" data-s="mt-md">
        <li>Sichtbar nur für Kontakte, die du selbst bestätigt hast.</li>
        <li>Name, Profilbild und Kurzbeschreibung sehen andere Mitglieder,
          damit eine Kontaktanfrage ein Gesicht hat.</li>
        <li>Welche Kompetenzen am Profil stehen, entscheidest du je Maßnahme.</li>
        <li>Abschalten jederzeit unter Profil · Netzwerk. Dein Logbuch
          bleibt davon unberührt.</li>
      </ul>
      ${NETZ_DATENSCHUTZ}
      <div class="sheet-actions two">
        <a class="btn link-plain" href="#/einsaetze">Zu meinen Einsätzen</a>
        <button class="btn-primary" id="netz-an">Kompetenznetz aktivieren</button>
      </div>
    </div>
    ${pageFoot()}`;
  $("#netz-an").addEventListener("click", async () => {
    try {
      NETZ.profil = await api("/api/netz/profil", { method: "PUT", body: { aktiv: true } });
      toast("Kompetenznetz aktiviert.");
      profilGruppe = "netz";
      location.hash = p.headline ? "#/" : "#/profil";
      if (p.headline) render();
    } catch (err) { toast(err.message); }
  });
}

// ------------------------------------------------------------- Erstellen

/* Der mittlere Punkt der Leiste fragt zuerst, was entstehen soll. Die
   Dokumentation bleibt der erste Eintrag: sie ist der Zweck der
   Anwendung, das Netz ist die Zugabe. */
function neuAuswahlSheet() {
  sheet("Neu", `
    <div class="stack">
      <button type="button" class="choice" id="neu-einsatz">
        <strong>Einsatz dokumentieren</strong>
        <span class="tiny muted">Maßnahmen und Medikamentengaben im eigenen Logbuch</span>
      </button>
      <button type="button" class="choice" id="neu-beitrag">
        <strong>Beitrag teilen</strong>
        <span class="tiny muted">Lernerfahrung, Studie, Leitlinie oder Kompetenz</span>
      </button>
    </div>`, (body) => {
    $("#neu-einsatz", body).addEventListener("click", () => { closeSheet(); newEncounterSheet(); });
    $("#neu-beitrag", body).addEventListener("click", async () => {
      closeSheet();
      const p = await netzProfil();
      if (!p.aktiv) { location.hash = "#/"; return; }
      composerSheet("text");
    });
  });
}

function composerSheet(art) {
  sheet("Beitrag teilen", `
    <div class="seg" role="tablist" aria-label="Beitragsart" id="cp-seg">
      <button class="seg-item" role="tab" data-art="text">Gedanke</button>
      <button class="seg-item" role="tab" data-art="wissen">Wissen</button>
      <button class="seg-item" role="tab" data-art="kompetenz">Kompetenz</button>
    </div>
    <div id="cp-body"></div>`, (body) => {
    const seg = $("#cp-seg", body);
    const ziel = $("#cp-body", body);
    function zeige(a) {
      seg.querySelectorAll(".seg-item").forEach((b) =>
        b.setAttribute("aria-selected", String(b.dataset.art === a)));
      if (a === "kompetenz") return kompetenzWahl(ziel);
      ziel.innerHTML = `
        <form id="cp-form" class="stack">
          ${a === "wissen" ? `
          <div class="field"><label for="cp-titel">Titel</label>
            <input id="cp-titel" maxlength="200" required
              placeholder="z. B. S3-Leitlinie Polytrauma, Kapitel Atemweg"></div>
          <div class="field"><label for="cp-url">Link</label>
            <input id="cp-url" type="url" inputmode="url" required
              placeholder="https://"></div>
          <div class="field"><label for="cp-quelle">Art der Quelle (optional)</label>
            <input id="cp-quelle" maxlength="120" list="cp-quellen"
              placeholder="Leitlinie, Studie, Fachartikel …">
            <datalist id="cp-quellen"><option>Leitlinie</option><option>Studie</option>
              <option>Übersichtsarbeit</option><option>Fachartikel</option>
              <option>Fortbildung</option><option>Podcast</option></datalist></div>` : ""}
          <div class="field"><label for="cp-text">${a === "wissen"
            ? "Was nimmst du daraus mit? (optional)" : "Dein Beitrag"}</label>
            <textarea id="cp-text" maxlength="3000" rows="5" ${a === "text" ? "required" : ""}
              placeholder="${a === "wissen" ? "Kernaussage für die Praxis …"
                : "Was hat dich weitergebracht? Was würdest du nächstes Mal anders machen?"}"></textarea></div>
          ${NETZ_DATENSCHUTZ}
          <button class="btn-primary btn-lg" type="submit">Teilen</button>
          <p class="tiny muted" id="cp-err"></p>
        </form>`;
      $("#cp-form", ziel).addEventListener("submit", async (e) => {
        e.preventDefault();
        const daten = { art: a, text: $("#cp-text", ziel).value };
        if (a === "wissen") {
          daten.link_url = $("#cp-url", ziel).value.trim();
          daten.link_titel = $("#cp-titel", ziel).value;
          daten.link_quelle = $("#cp-quelle", ziel).value;
        }
        try {
          await api("/api/netz/beitraege", { method: "POST", body: daten });
          closeSheet();
          toast("Geteilt.");
          if (location.hash === "#/" || location.hash === "") render();
          else location.hash = "#/";
        } catch (err) { $("#cp-err", ziel).textContent = err.message; }
      });
      const erstes = $("input, textarea", ziel);
      if (erstes) erstes.focus();
    }
    seg.querySelectorAll(".seg-item").forEach((b) =>
      b.addEventListener("click", () => zeige(b.dataset.art)));
    zeige(art || "text");
  });
}

/* Kompetenzbeiträge entstehen aus genau einem Einsatz. Die Liste zeigt
   die eigenen Einsätze mit Datum — das sieht nur die Person selbst, im
   Beitrag landet davon nichts. */
async function kompetenzWahl(ziel) {
  ziel.innerHTML = `<p class="small muted">Wird geladen …</p>`;
  const d = await api("/api/encounters?limit=30");
  const mitEintraegen = d.encounters.filter((e) => e.attempt_count || e.medication_count);
  if (!mitEintraegen.length) {
    ziel.innerHTML = `<p class="small muted">Noch kein Einsatz mit Einträgen.
      Dokumentiere zuerst eine Maßnahme, dann kannst du sie hier teilen.</p>`;
    return;
  }
  ziel.innerHTML = `
    <p class="small muted">Aus welchem Einsatz? Datum und Einsatzdaten siehst
    nur du, sie werden nicht geteilt.</p>
    <div class="stack" data-s="mt-sm">${mitEintraegen.map((e) => `
      <button type="button" class="choice" data-enc="${esc(e.id)}">
        <strong>${esc(fmtDate(e.enc_date))}</strong>
        <span class="tiny muted">${e.attempt_count} Maßnahmen · ${e.medication_count}
          Medikamente${e.naca ? " · NACA " + esc(e.naca) : ""}</span>
      </button>`).join("")}</div>`;
  ziel.querySelectorAll("[data-enc]").forEach((b) =>
    b.addEventListener("click", async () => {
      const enc = await api("/api/encounters/" + encodeURIComponent(b.dataset.enc));
      kompetenzTeilenSheet(enc, null);
    }));
}

/* Teilen aus der Einsatzansicht. Vorschau und Auswahl zeigen genau die
   Felder der Allowlist des Servers: Name, Kategorie, Ergebnis, Rolle;
   bei Medikamenten Wirkstoff, Etikettengruppe, Weg und Ergebnis. */
function kompetenzTeilenSheet(enc, vorauswahl) {
  const medGruppe = (id) => {
    const m = (state.medications || []).find((x) => x.id === id);
    return m ? m.divi_group || "" : "";
  };
  const zeilen = [
    ...enc.attempts.map((a) => ({ typ: "a", id: a.id, html: `
      <span class="cat-badge" data-cat="${esc(a.measure_category)}">${esc(a.measure_category)}</span>
      <span class="grow">${esc(a.measure_name)}</span>${statusBadge(a.outcome)}` })),
    ...enc.medications.map((m) => ({ typ: "m", id: m.id, html: `
      ${diviLabel({ name: m.medication_name, divi_group: medGruppe(m.medication_id) })}
      <span class="grow tiny muted">${esc(m.route || "")}</span>${statusBadge(m.outcome || "erfolgreich")}` })),
  ];
  const hatZek = enc.complications && enc.complications.length
    || enc.attempts.some((a) => (a.complications || []).length)
    || enc.medications.some((m) => (m.complications || []).length);

  sheet("Kompetenz teilen", `
    <form id="kt-form" class="stack">
      <fieldset class="kt-list">
        <legend class="small">Welche Einträge?</legend>
        ${zeilen.map((z) => `
          <label class="kt-row">
            <input type="checkbox" data-typ="${z.typ}" value="${esc(z.id)}"
              ${!vorauswahl || vorauswahl === z.id ? "checked" : ""}>
            ${z.html}
          </label>`).join("")}
      </fieldset>
      <div class="field">
        ${hatZek ? `<label class="check"><input type="checkbox" id="kt-zek">
          ZEK-Bezeichnungen mitteilen (ohne Bezug und Patientenschaden)</label>` : ""}
        ${enc.naca ? `<label class="check"><input type="checkbox" id="kt-naca">
          NACA-Wert mitteilen</label>` : ""}
      </div>
      <div class="field"><label for="kt-text">Was hast du dabei gelernt? (optional)</label>
        <textarea id="kt-text" maxlength="3000" rows="4"
          placeholder="Ohne Ort, Zeit und Patientenbezug"></textarea></div>
      ${NETZ_DATENSCHUTZ}
      <button class="btn-primary btn-lg" type="submit">Teilen</button>
      <p class="tiny muted" id="kt-err"></p>
    </form>`, (body) => {
    $("#kt-form", body).addEventListener("submit", async (e) => {
      e.preventDefault();
      const gewaehlt = (typ) => [...body.querySelectorAll(`input[data-typ="${typ}"]:checked`)]
        .map((i) => i.value);
      try {
        await api("/api/netz/beitraege", { method: "POST", body: {
          art: "kompetenz", text: $("#kt-text", body).value,
          attempt_ids: gewaehlt("a"), medication_ids: gewaehlt("m"),
          mit_zek: !!($("#kt-zek", body) || {}).checked,
          mit_naca: !!($("#kt-naca", body) || {}).checked,
        } });
        closeSheet();
        toast("Kompetenz geteilt.");
      } catch (err) { $("#kt-err", body).textContent = err.message; }
    });
  });
}

async function teilenAusEinsatz(enc, vorauswahl) {
  const p = await netzProfil();
  if (!p.aktiv) {
    sheet("Kompetenznetz", `
      <p class="small">Zum Teilen das Kompetenznetz einschalten. Dein
      Logbuch bleibt davon unberührt, geteilt wird nur, was du auswählst.</p>
      <a class="btn btn-primary link-plain" href="#/" data-s="mt-md">Kompetenznetz ansehen</a>`);
    return;
  }
  kompetenzTeilenSheet(enc, vorauswahl);
}

// ---------------------------------------------------------------- Personen

function beziehungsKnopf(p) {
  switch (p.beziehung) {
    case "fremd":
      return `<button type="button" class="btn-primary small" data-vernetzen="${esc(p.id)}">Vernetzen</button>`;
    case "ausgehend":
      return `<button type="button" class="small" data-loesen="${esc(p.id)}"
        aria-label="Anfrage an ${esc(p.name)} zurückziehen">Angefragt</button>`;
    case "eingehend":
      return `<div class="row" data-s="gap-sm">
        <button type="button" class="btn-primary small" data-annehmen="${esc(p.id)}">Annehmen</button>
        <button type="button" class="small" data-loesen="${esc(p.id)}"
          aria-label="Anfrage von ${esc(p.name)} ablehnen">Ablehnen</button></div>`;
    case "kontakt":
      return `<span class="status info">Kontakt</span>`;
    default:
      return "";
  }
}

function personZeile(p) {
  return `
    <li class="person-row">
      <a class="row grow link-plain" href="#/person/${esc(p.id)}" data-s="gap-sm">
        ${avatarHtml(p, "m")}
        <span class="grow"><strong>${esc(p.name)}</strong>
          <span class="tiny muted np-sub">${esc(p.headline || "")}</span></span>
      </a>
      ${beziehungsKnopf(p)}
    </li>`;
}

function bindeBeziehungen(bereich, nachher) {
  bereich.addEventListener("click", async (e) => {
    const k = e.target.closest("[data-vernetzen], [data-annehmen], [data-loesen]");
    if (!k) return;
    try {
      if (k.dataset.vernetzen) {
        await api("/api/netz/kontakte/" + encodeURIComponent(k.dataset.vernetzen), { method: "POST" });
        toast("Anfrage gesendet.");
      } else if (k.dataset.annehmen) {
        await api(`/api/netz/kontakte/${encodeURIComponent(k.dataset.annehmen)}/annehmen`, { method: "POST" });
        toast("Ihr seid jetzt vernetzt.");
      } else {
        await api("/api/netz/kontakte/" + encodeURIComponent(k.dataset.loesen), { method: "DELETE" });
      }
      nachher();
    } catch (err) { toast(err.message); }
  });
}

async function viewKontakte() {
  const p = await netzProfil();
  if (!p.aktiv) return netzEinstieg(p);
  const k = await api("/api/netz/kontakte");
  app().innerHTML = `<div id="kontakte-seite">
    ${netzKopf("Kontakte", `${k.kontakte.length} ${k.kontakte.length === 1 ? "Kontakt" : "Kontakte"}`)}
    <div class="field">
      <label for="such">Kolleg*innen finden</label>
      <input id="such" type="search" maxlength="80" autocomplete="off"
        placeholder="Name oder Kurzbeschreibung">
    </div>
    <ul class="person-list" id="treffer" data-s="mt-sm"></ul>
    ${k.eingehend.length ? `<h2 class="sec">Anfragen</h2>
      <ul class="person-list card">${k.eingehend.map(personZeile).join("")}</ul>` : ""}
    <h2 class="sec">Deine Kontakte</h2>
    ${k.kontakte.length
      ? `<ul class="person-list card">${k.kontakte.map(personZeile).join("")}</ul>`
      : `<p class="small muted">Noch keine Kontakte. Suche oben nach
        Kolleg*innen, die das Kompetenznetz eingeschaltet haben.</p>`}
    ${k.ausgehend.length ? `<h2 class="sec">Gesendete Anfragen</h2>
      <ul class="person-list card">${k.ausgehend.map(personZeile).join("")}</ul>` : ""}
    </div>
    ${pageFoot()}`;
  zeigeZaehler();
  // An die frisch gerenderte Seite gebunden, nicht an #app: der Container
  // überdauert jeden Seitenwechsel und sammelte sonst Zuhörer an.
  bindeBeziehungen($("#kontakte-seite"), () => {
    const wert = $("#such").value;
    viewKontakte().then(() => {
      if (wert) { $("#such").value = wert; $("#such").dispatchEvent(new Event("input")); }
    });
  });

  let warte = null;
  $("#such").addEventListener("input", (e) => {
    clearTimeout(warte);
    const wert = e.target.value.trim();
    if (wert.length < 2) { $("#treffer").innerHTML = ""; return; }
    warte = setTimeout(async () => {
      const r = await api("/api/netz/personen?q=" + encodeURIComponent(wert));
      const ziel = $("#treffer");
      if (!ziel) return;
      ziel.classList.toggle("card", r.personen.length > 0);
      ziel.innerHTML = r.personen.length ? r.personen.map(personZeile).join("")
        : `<li class="tiny muted">Niemand gefunden. Gefunden wird nur, wer das
          Kompetenznetz eingeschaltet hat.</li>`;
    }, 250);
  });
}

async function viewPerson(id) {
  const ich = await netzProfil();
  const selbst = id === state.auth.user.id;
  if (!ich.aktiv && !selbst) return netzEinstieg(ich);
  const p = await api("/api/netz/personen/" + encodeURIComponent(id));
  const voll = p.beziehung === "selbst" || p.beziehung === "kontakt";

  const kompetenzen = (p.kompetenzen || []).map((k) => `
    <li class="kz-item" data-cat="${esc(k.kategorie)}">
      <div class="row" data-s="gap-sm">
        <span class="cat-badge">${esc(k.kategorie)}</span>
        <strong class="grow">${esc(k.name)}</strong>
      </div>
      <div class="tiny muted" data-s="mt-xs">${k.anzahl}× dokumentiert ·
        ${k.erfolgreich} erfolgreich${k.bestaetigungen
          ? ` · ${k.bestaetigungen} ${k.bestaetigungen === 1 ? "Bestätigung" : "Bestätigungen"}${
            k.praxisanleitung ? `, davon ${k.praxisanleitung} durch Praxisanleitung` : ""}` : ""}</div>
      ${p.beziehung === "kontakt" && canWrite() ? (k.meine_bestaetigung
        ? `<button type="button" class="btn-quiet small" data-s="mt-xs"
            data-zurueck="${esc(k.meine_bestaetigung)}">Bestätigt · zurückziehen</button>`
        : `<button type="button" class="small" data-s="mt-xs"
            data-bestaetigen="${esc(k.measure_id)}" data-name="${esc(k.name)}">Bestätigen</button>`)
        : ""}
    </li>`).join("");

  app().innerHTML = `
    <div class="person-head">
      <div class="banner">${p.banner_id
        ? `<img src="/api/netz/medien/${esc(p.banner_id)}" alt="" decoding="async">`
        : ringBg()}</div>
      <div class="person-id">
        ${avatarHtml(p, "xl")}
        <div class="who">
          <h1>${esc(p.name)}</h1>
          ${p.headline ? `<p class="small">${esc(p.headline)}</p>` : ""}
          <p class="tiny muted">${p.qualifikation ? esc(p.qualifikation) + " · " : ""}${
            p.kontakte} ${p.kontakte === 1 ? "Kontakt" : "Kontakte"}</p>
        </div>
      </div>
      <div class="row wrap" data-s="gap-sm mt-sm" id="bez">
        ${selbst ? `<a class="btn small link-plain" href="#/profil" id="zum-profil">Profil bearbeiten</a>`
          : beziehungsKnopf(p)}
        ${p.beziehung === "kontakt" ? `<button type="button" class="btn-quiet small"
          data-loesen="${esc(p.id)}">Kontakt lösen</button>` : ""}
      </div>
    </div>

    ${!voll ? `<div class="notice plain" data-s="mt-md">Vorstellung, Kompetenzen und
      Beiträge sehen nur Kontakte.</div>` : `
    ${p.about ? `<div class="card pad-lg" data-s="mt-md"><h2>Über mich</h2>
      <p class="small np-text" data-s="mt-sm">${esc(p.about)}</p></div>` : ""}
    <div class="card pad-lg" data-s="mt-md">
      <h2>Kompetenzen</h2>
      <p class="tiny muted" data-s="mt-xs">Belegt durch das Logbuch: nur
      Anzahlen, kein Datum, kein Einsatzbezug.${selbst
        ? " Welche hier stehen, legst du unter Profil · Netzwerk fest." : ""}</p>
      ${kompetenzen ? `<ul class="kz-items" data-s="mt-md">${kompetenzen}</ul>`
        : `<p class="small muted" data-s="mt-sm">Noch keine Kompetenzen freigegeben.</p>`}
    </div>
    <h2 class="sec">Beiträge</h2>
    <div id="person-posts" class="stack">${(p.beitraege || []).length
      ? p.beitraege.map(postCard).join("")
      : `<p class="small muted">Noch keine Beiträge.</p>`}</div>`}
    ${pageFoot()}`;

  if (selbst) $("#zum-profil").addEventListener("click", () => { profilGruppe = "netz"; });
  const posts = $("#person-posts");
  if (posts) bindePosts(posts);
  bindeBeziehungen($(".person-head"), () => viewPerson(id));

  app().querySelectorAll("[data-bestaetigen]").forEach((b) =>
    b.addEventListener("click", () => bestaetigenSheet(p, b.dataset.bestaetigen, b.dataset.name)));
  app().querySelectorAll("[data-zurueck]").forEach((b) =>
    b.addEventListener("click", async () => {
      await api("/api/netz/bestaetigungen/" + encodeURIComponent(b.dataset.zurueck),
        { method: "DELETE" });
      toast("Bestätigung zurückgezogen."); viewPerson(id);
    }));
}

function bestaetigenSheet(p, measureId, name) {
  const rollen = Object.entries(NETZ_ROLLEN).map(([k, label], i) => `
    <label class="check"><input type="radio" name="rolle" value="${k}" ${i === 0 ? "checked" : ""}>
      ${esc(label)}</label>`).join("");
  sheet("Kompetenz bestätigen", `
    <p class="small"><strong>${esc(name)}</strong> bei ${esc(p.name)}</p>
    <p class="small muted" data-s="mt-sm">Bestätige nur, was du selbst gesehen
    hast. Deine Bestätigung steht mit deinem Namen am Profil.</p>
    <form id="bs-form" class="stack" data-s="mt-md">
      <fieldset class="field"><legend class="small">Woher kennst du es?</legend>${rollen}</fieldset>
      <button class="btn-primary btn-lg" type="submit">Bestätigen</button>
      <p class="tiny muted" id="bs-err"></p>
    </form>`, (body) => {
    $("#bs-form", body).addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await api("/api/netz/bestaetigungen", { method: "POST", body: {
          user_id: p.id, measure_id: measureId,
          rolle: $('input[name="rolle"]:checked', body).value } });
        closeSheet(); toast("Bestätigt."); viewPerson(p.id);
      } catch (err) { $("#bs-err", body).textContent = err.message; }
    });
  });
}

// ----------------------------------------------------------- Mitteilungen

const NETZ_MITTEILUNG = {
  kontaktanfrage: (n) => [`${n} möchte sich mit dir vernetzen.`, "#/kontakte"],
  kontakt_angenommen: (n, m) => [`${n} hat deine Kontaktanfrage angenommen.`,
    m.von ? "#/person/" + m.von.id : "#/kontakte"],
  reaktion: (n, m) => [`${n} hat deinem Beitrag Anerkennung gegeben.`, "#/beitrag/" + m.post_id],
  kommentar: (n, m) => [`${n} hat deinen Beitrag kommentiert.`, "#/beitrag/" + m.post_id],
  bestaetigung: (n) => [`${n} hat eine deiner Kompetenzen bestätigt.`,
    "#/person/" + state.auth.user.id],
  entfernt: (n, m) => ["Ein Beitrag von dir wurde von der Administration entfernt.",
    "#/beitrag/" + m.post_id],
  meldung: (n, m) => [`${n} hat einen Beitrag gemeldet.`, "#/beitrag/" + m.post_id],
};

async function viewMitteilungen() {
  const m = await api("/api/netz/mitteilungen");
  app().innerHTML = `
    ${netzKopf("Mitteilungen", "")}
    ${m.mitteilungen.length ? `<ul class="person-list card">${m.mitteilungen.map((x) => {
      const bau = NETZ_MITTEILUNG[x.art];
      if (!bau) return "";
      const name = x.von ? x.von.name : "Jemand";
      const [text, ziel] = bau(esc(name), x);
      return `<li class="note-row${x.gelesen ? "" : " neu"}">
        <a class="row grow link-plain" href="${esc(ziel)}" data-s="gap-sm">
          ${x.von ? avatarHtml(x.von, "m") : `<span class="av av-m ini" data-farbe="0" aria-hidden="true">!</span>`}
          <span class="grow"><span class="small">${text}</span>
            <span class="tiny muted np-sub">${esc(relZeit(x.erstellt))}${
              x.gelesen ? "" : " · neu"}</span></span>
        </a></li>`;
    }).join("")}</ul>`
      : `<div class="empty">${markSvg("mark")}<strong>Keine Mitteilungen.</strong>
        Anfragen, Anerkennung und Kommentare erscheinen hier.</div>`}
    ${pageFoot()}`;
  if (m.ungelesen) {
    await api("/api/netz/mitteilungen/gelesen", { method: "POST" });
  }
  NETZ.ungelesen = 0;
  NETZ.stand = Date.now();
  zeigeZaehler();
}

async function viewBeitrag(id) {
  const b = await api("/api/netz/beitraege/" + encodeURIComponent(id));
  app().innerHTML = `
    <div class="page-head">
      <a class="small muted link-plain" href="#/">Zurück zum Feed</a>
      <h1 class="sr-only">Beitrag von ${esc(b.autor.name)}</h1>
    </div>
    <div id="ein-beitrag">${postCard(b)}</div>
    ${pageFoot()}`;
  const box = $("#ein-beitrag");
  bindePosts(box);
  await ladeKommentare($("[data-post]", box), false);
}

// ---------------------------------------------------- Profil: Netzwerk

/* Die Karten tragen ihre Überschriften als Gruppenschlüssel, siehe
   viewProfile. Sie werden dort an den Profilkopf angehängt. */
function netzProfilKarten(p) {
  const kompetenzen = p.kompetenzen.map((k) => `
    <label class="kt-row">
      <input type="checkbox" data-kompetenz="${esc(k.measure_id)}" ${k.sichtbar ? "checked" : ""}>
      <span class="cat-badge" data-cat="${esc(k.kategorie)}">${esc(k.kategorie)}</span>
      <span class="grow">${esc(k.name)}</span>
      <span class="tiny muted">${k.anzahl}×</span>
    </label>`).join("");
  return `
    <div class="card pad-lg" data-s="mt-md">
      <h2>Kompetenznetz</h2>
      <p class="small muted" data-s="mt-xs">${p.aktiv
        ? `Eingeschaltet. ${p.kontakte} ${p.kontakte === 1 ? "Kontakt" : "Kontakte"}.`
        : "Ausgeschaltet. Niemand findet dich, dein Logbuch bleibt privat."}</p>
      <p class="tiny muted" data-s="mt-sm">Ausschalten blendet Profil und
      Beiträge sofort für alle aus. Kontakte, Beiträge und Bestätigungen
      bleiben erhalten, bis du sie löschst oder das Konto löschst.</p>
      <div class="sheet-actions two">
        ${p.aktiv ? `<a class="btn link-plain" href="#/person/${esc(state.auth.user.id)}">Profil ansehen</a>` : ""}
        <button id="netz-schalter" class="${p.aktiv ? "" : "btn-primary"}">${p.aktiv
          ? "Kompetenznetz ausschalten" : "Kompetenznetz einschalten"}</button>
      </div>
    </div>

    <div class="card pad-lg" data-s="mt-md">
      <h2>Profilbilder</h2>
      <p class="tiny muted" data-s="mt-xs">JPEG, PNG oder WebP bis 8 MB.
      Jedes Bild wird neu berechnet; Aufnahmeort, Kameradaten und andere
      Metadaten werden dabei entfernt. Das Profilbild sehen alle Mitglieder
      im Netz, das Kopfbild nur Kontakte.</p>
      <div class="media-edit" data-s="mt-md">
        <div class="banner small-banner">${p.banner_id
          ? `<img src="/api/netz/medien/${esc(p.banner_id)}" alt="Kopfbild" decoding="async">`
          : ringBg()}</div>
        ${avatarHtml({ id: state.auth.user.id, name: p.name, avatar_id: p.avatar_id }, "xl")}
      </div>
      <div class="sheet-actions two">
        <label class="btn file-btn">Profilbild wählen
          <input type="file" accept="image/jpeg,image/png,image/webp" data-bild="avatar"></label>
        <label class="btn file-btn">Kopfbild wählen
          <input type="file" accept="image/jpeg,image/png,image/webp" data-bild="banner"></label>
      </div>
      <div class="row wrap" data-s="gap-sm mt-sm">
        ${p.avatar_id ? `<button class="btn-quiet small" data-bild-weg="avatar">Profilbild entfernen</button>` : ""}
        ${p.banner_id ? `<button class="btn-quiet small" data-bild-weg="banner">Kopfbild entfernen</button>` : ""}
      </div>
    </div>

    <div class="card pad-lg" data-s="mt-md">
      <h2>Vorstellung</h2>
      <form id="vorst-form" class="stack" data-s="mt-md">
        <div class="field"><label for="nh">Kurzbeschreibung</label>
          <input id="nh" maxlength="120" value="${esc(p.headline)}"
            placeholder="z. B. Notfallsanitäter · Praxisanleiter"></div>
        <div class="field"><label for="na">Über mich (nur Kontakte)</label>
          <textarea id="na" maxlength="1500" rows="4"
            placeholder="Schwerpunkte, Fortbildungen, was dich interessiert">${esc(p.about)}</textarea></div>
        <button class="btn-primary" type="submit">Vorstellung speichern</button>
        <p class="tiny muted" id="vorst-err"></p>
      </form>
    </div>

    <div class="card pad-lg" data-s="mt-md">
      <h2>Kompetenzen freigeben</h2>
      <p class="tiny muted" data-s="mt-xs">Angehakte Maßnahmen stehen mit
      Anzahl und Erfolgsquote am Profil, sichtbar nur für Kontakte. Neue
      Maßnahmen sind zunächst nicht freigegeben.</p>
      ${kompetenzen ? `<div class="kt-list" data-s="mt-md">${kompetenzen}</div>`
        : `<p class="small muted" data-s="mt-sm">Noch keine Maßnahmen dokumentiert.</p>`}
    </div>`;
}

function bindeNetzProfil(p) {
  $("#netz-schalter").addEventListener("click", async () => {
    if (p.aktiv && !confirm("Kompetenznetz ausschalten? Profil und Beiträge "
                            + "sind dann für niemanden mehr sichtbar.")) return;
    try {
      NETZ.profil = await api("/api/netz/profil", { method: "PUT", body: { aktiv: !p.aktiv } });
      toast(p.aktiv ? "Kompetenznetz ausgeschaltet." : "Kompetenznetz eingeschaltet.");
      render();
    } catch (err) { toast(err.message); }
  });

  app().querySelectorAll("[data-bild]").forEach((input) =>
    input.addEventListener("change", async () => {
      const datei = input.files[0];
      if (!datei) return;
      if (datei.size > 8 * 1024 * 1024) { toast("Das Bild ist größer als 8 MB."); return; }
      const fd = new FormData();
      fd.append("datei", datei);
      try {
        toast("Bild wird verarbeitet …");
        await api("/api/netz/medien/" + input.dataset.bild, { method: "POST", body: fd });
        toast("Bild gespeichert.");
        render();
      } catch (err) { toast(err.message); }
    }));
  app().querySelectorAll("[data-bild-weg]").forEach((b) =>
    b.addEventListener("click", async () => {
      await api("/api/netz/medien/" + b.dataset.bildWeg, { method: "DELETE" });
      toast("Bild entfernt."); render();
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

  app().querySelectorAll("[data-kompetenz]").forEach((box) =>
    box.addEventListener("change", async () => {
      try {
        await api("/api/netz/kompetenzen/" + encodeURIComponent(box.dataset.kompetenz),
          { method: "PUT", body: { sichtbar: box.checked } });
      } catch (err) { box.checked = !box.checked; toast(err.message); }
    }));
}
