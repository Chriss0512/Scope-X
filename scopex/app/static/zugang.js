/* SCOPE X - Zugang: Bewerbung, Nutzungsvereinbarung, Administration der
   Bewerbungen und Kataloge.

   Wird vor app.js geladen. Ob jemand etwas darf, entscheidet der Server;
   diese Datei zeigt nur Formulare und Listen. */

"use strict";

// --------------------------------------------------- Nutzungsvereinbarung

function nutzungHtml(n) {
  return `
    <p class="tiny muted">Fassung ${esc(n.version)} · Stand ${esc(n.stand)}</p>
    <div class="nutzung-text">${n.abschnitte.map((a, i) => `
      <section><h3>${i + 1}. ${esc(a.titel)}</h3>${a.absaetze.map((p) =>
        `<p class="small">${esc(p)}</p>`).join("")}</section>`).join("")}</div>`;
}

async function viewNutzungsbedingungen() {
  const n = await api("/api/oeffentlich/nutzungsbedingungen");
  const angemeldet = state.auth && state.auth.authenticated;
  if (!angemeldet) {
    authShell("Nutzungsvereinbarung", `${nutzungHtml(n)}
      <button type="button" class="btn btn-lg" id="nb-zurueck" data-s="mt-md">Zurück</button>`);
  } else {
    app().innerHTML = `
      <div class="page-head"><h1>Nutzungsvereinbarung</h1></div>
      <div class="card pad-lg">${nutzungHtml(n)}</div>
      <button type="button" class="btn-quiet btn-lg" id="nb-zurueck" data-s="mt-md">Zurück</button>
      ${pageFoot()}`;
  }
  $("#nb-zurueck").addEventListener("click", zurueck);
}

/* Rechtstexte aus einem Formular heraus: im Blatt statt in einem neuen
   Tab. Im neuen Tab gab es kein Zurück, und das halb ausgefüllte
   Formular war aus dem Blick. */
document.addEventListener("click", async (e) => {
  const a = e.target.closest("[data-rechtstext]");
  if (!a) return;
  e.preventDefault();
  try {
    if (a.dataset.rechtstext === "nutzung") {
      const n = await api("/api/oeffentlich/nutzungsbedingungen");
      sheet("Nutzungsvereinbarung", nutzungHtml(n), (body) => body.closest(".sheet").classList.add("tall"));
    } else {
      const l = await api("/api/legal");
      sheet("Impressum und Datenschutz", legalHtml(l), (body) => body.closest(".sheet").classList.add("tall"));
    }
  } catch (err) { toast(err.message); }
});

// ---------------------------------------------------------- Über SCOPE X

const UEBER = `
  <p class="small">SCOPE X ist ein Maßnahmen- und Kompetenzlogbuch für den Rettungsdienst und
  ein geschlossenes Fachnetzwerk für Lernen, Praxisanleitung und kollegiale Unterstützung.
  Diese Installation wird privat betrieben, ohne Werbung, ohne Tracking und ohne Weitergabe
  an Dritte.</p>
  <p class="small"><span class="beta-badge">Erweiterte Beta</span> SCOPE X ist eine private
  Initiative und befindet sich in der erweiterten Beta. Funktionen können sich noch ändern;
  Rückmeldungen fließen direkt in die Entwicklung.</p>

  <h2>Warum</h2>
  <p class="small">Die entscheidenden Maßnahmen im Rettungsdienst sind selten. Wer weiß, wann er
  etwas zuletzt gemacht hat und wie oft es gelang, kann gezielt üben. Wer seltene Situationen
  und Komplikationen teilt, macht sie für andere weniger selten.</p>

  <h2>Das Logbuch</h2>
  <ul class="small">
    <li>Einsätze, Maßnahmen nach xABCDE, Medikamente mit DIVI-Etiketten, Ergebnis und
      Komplikationen, schnell erfasst.</li>
    <li>Auswertung und Nachweise für dich selbst, etwa für die Praxisanleitung.</li>
    <li>Fortbildungsnachweis und Qualifikationen mit Ablaufdatum.</li>
    <li>Einsatznummer, Ort, Fahrzeug und Zeitpunkt sieht niemand außer dir, auch nicht,
      wenn du etwas daraus teilst.</li>
  </ul>

  <h2>Das Netzwerk</h2>
  <ul class="small">
    <li>Feed mit nachvollziehbarer Reihenfolge, die auf Lernen zielt statt auf Verweildauer.</li>
    <li>Fallberichte, Fallvorstellungen mit Frage an die Community, Wissen mit Quelle.</li>
    <li>Kompetenzen aus dem Logbuch, die Kolleg*innen bestätigen können.</li>
    <li>Themen wie #Atemwegsmanagement, #Praxisanleitung oder #Peer-to-Peer-Hilfe.</li>
    <li>Profil, Chronik, Direktnachrichten, Bilder und Videos.</li>
  </ul>

  <h2>Für wen</h2>
  <p class="small">Notfallsanitäter*innen, Rettungssanitäter*innen, Praxisanleitungen,
  Auszubildende, Notärztinnen und Notärzte, Pflegende in Notaufnahme und Intensivmedizin,
  Luftrettung, Intensivtransport und Leitstelle.</p>

  <h2>Wie man dazukommt</h2>
  <p class="small">Mit einer Einladung der Administration oder über eine Bewerbung. Ein Mitglied
  kann dich empfehlen; über die Aufnahme entscheidet die Administration.</p>

  <h2>Datenschutz und Sicherheit</h2>
  <ul class="small">
    <li>Nachrichten und persönliche Angaben liegen verschlüsselt in der Datenbank.</li>
    <li>Anmeldung nur mit Zwei-Faktor-Authentifizierung oder Passkey.</li>
    <li>Keine Patientendaten: Texte werden auf Einsatznummern, Fahrzeuge, Daten und
      Uhrzeiten geprüft. Es gilt die Schweigepflicht.</li>
    <li>SCOPE X gibt keine Indikationen, Dosierungen oder Algorithmen vor. Maßgeblich bleiben
      Leitlinien, die Vorgaben des ÄLRD und die SOPs vor Ort.</li>
    <li>Datenauskunft und Kontolöschung jederzeit selbst im Profil.</li>
  </ul>`;

function viewUeber() {
  const angemeldet = state.auth && state.auth.authenticated;
  if (!angemeldet) {
    authShell("Über SCOPE X", `<div class="ueber">${UEBER}</div>
      <div class="sheet-actions two">
        <a class="btn link-plain" href="#/">Anmelden</a>
        <a class="btn btn-primary link-plain" href="#/bewerben">Um Zugang bewerben</a>
      </div>`);
    return;
  }
  app().innerHTML = `
    <div class="page-head"><h1>Über SCOPE X</h1></div>
    <div class="card pad-lg ueber">${UEBER}</div>
    <button type="button" class="btn-quiet btn-lg" id="ue-zurueck" data-s="mt-md">Zurück</button>
    ${pageFoot()}`;
  $("#ue-zurueck").addEventListener("click", zurueck);
}

/* Nach einer neuen Fassung: vor allem anderen. Der Server lässt bis zur
   Zustimmung ohnehin nur Anmeldung, Auskunft und Löschung durch. */
async function viewNutzungZustimmen() {
  const n = await api("/api/nutzung");
  authShell(n.zuletzt ? "Neue Nutzungsvereinbarung" : "Nutzungsvereinbarung", `
    <p class="small">${n.zuletzt ? "Die Nutzungsvereinbarung hat sich geändert. Bitte lies die neue "
      + "Fassung und stimme ihr zu, um SCOPE X weiter zu nutzen."
      : "Bevor es losgeht: Bitte lies die Nutzungsvereinbarung und stimme ihr zu."}</p>
    <div class="nutzung-box" tabindex="0" role="region" aria-label="Text der Vereinbarung"
      data-s="mt-md">${nutzungHtml(n)}</div>
    <label class="check confirm" data-s="mt-md"><input type="checkbox" id="nz-ok">
      <span>Ich habe die Nutzungsvereinbarung gelesen und stimme ihr zu.</span></label>
    <button class="btn-primary btn-lg" id="nz-senden" data-s="mt-md">Zustimmen und weiter</button>
    <p class="tiny muted" id="nz-err" role="alert"></p>
    <div class="row wrap" data-s="gap-sm mt-lg">
      <a class="btn-quiet small link-plain" href="/api/exports/my-data">Meine Daten herunterladen</a>
      <button type="button" class="btn-quiet small" id="nz-ab">Abmelden</button>
    </div>
    <p class="tiny muted">Wer nicht zustimmen möchte, kann seine Daten herunterladen und das
    Konto in den Einstellungen löschen lassen oder sich an die Administration wenden.</p>`);
  $("#nz-senden").addEventListener("click", async () => {
    if (!$("#nz-ok").checked) { $("#nz-err").textContent = "Bitte bestätige zuerst."; return; }
    try {
      await api("/api/nutzung/zustimmen", { method: "POST", body: { version: n.version } });
      boot();
    } catch (err) { $("#nz-err").textContent = err.message; }
  });
  $("#nz-ab").addEventListener("click", async () => {
    await api("/api/auth/logout", { method: "POST" }).catch(() => {});
    state.auth = null; location.hash = "#/"; boot();
  });
}

// --------------------------------------------------------------- Bewerbung

async function viewBewerben(token, empfehlungCode = currentRoute().query.get("empfehlung")) {
  if (token) {
    try {
      const r = await api("/api/oeffentlich/bewerbung/bestaetigen", { method: "POST", body: { token } });
      authShell("Bewerbung bestätigt", `<p class="small">${esc(r.detail)}</p>
        <a class="btn btn-lg link-plain" href="#/" data-s="mt-md">Zur Anmeldung</a>`);
    } catch (err) {
      authShell("Link ungültig", `<p class="small">${esc(err.message)}</p>
        <p class="small muted">Bestätigungslinks gelten 48 Stunden. Du kannst dich einfach erneut
        bewerben.</p><a class="btn btn-lg link-plain" href="#/bewerben" data-s="mt-md">Erneut bewerben</a>`);
    }
    return;
  }
  const z = await api("/api/oeffentlich/bewerbung");
  if (!z.offen) {
    authShell("Bewerbung", `<p class="small">Bewerbungen sind auf dieser Installation derzeit nicht
      möglich. Zugang gibt es nur auf Einladung eines Mitglieds.</p>
      <a class="btn btn-lg link-plain" href="#/" data-s="mt-md">Zur Anmeldung</a>`);
    return;
  }
  const kreise = await api("/api/oeffentlich/kreise");
  let empf = null;
  if (empfehlungCode) {
    try { empf = await api("/api/oeffentlich/empfehlung/" + encodeURIComponent(empfehlungCode)); }
    catch (err) {
      authShell("Einladung abgelaufen", `<p class="small">${esc(err.message)}</p>
        <p class="small muted">Du kannst dich trotzdem bewerben, dann ohne Empfehlung.</p>
        <a class="btn btn-lg btn-primary link-plain" href="#/bewerben" data-s="mt-md">Ohne Empfehlung bewerben</a>`);
      return;
    }
  }
  authShell("Um Zugang bewerben", `
    ${empf ? `<div class="notice"><strong>${esc(empf.von)}</strong> hat dich eingeladen und ist
      als Kontakt schon eingetragen. Über die Aufnahme entscheidet die Administration.</div>`
    : `<p class="small">SCOPE X ist ein geschlossenes Netz für Menschen in der Notfallversorgung.
    Erzähl kurz, wer du bist. Wenn du ein Mitglied kennst, nenn es: es wird gefragt, ob es
    dich kennt. Die Administration entscheidet und schickt dir bei Zusage eine Einladung.</p>`}
    <p class="small"><a href="#/ueber">Was ist SCOPE X?</a></p>
    <form id="bw-form" class="stack" data-s="mt-lg">
      <div class="field-row">
        <div class="field"><label for="bf">Vorname</label><input id="bf" name="first_name" required
          maxlength="80" autocomplete="given-name"
          value="${esc(empf && empf.name ? empf.name.split(" ")[0] : "")}"></div>
        <div class="field"><label for="bl">Nachname</label><input id="bl" name="last_name" required
          maxlength="80" autocomplete="family-name"
          value="${esc(empf && empf.name ? empf.name.split(" ").slice(1).join(" ") : "")}"></div>
      </div>
      <div class="field"><label for="be">E-Mail-Adresse</label>
        <input id="be" type="email" name="email" required maxlength="200" autocomplete="email"
          autocapitalize="none" spellcheck="false" value="${esc(empf ? empf.email : "")}"></div>
      <div class="field"><label for="bq">Beruf oder Ausbildung</label>
        <input id="bq" name="qualification" required maxlength="80" list="bq-liste"
          placeholder="z. B. Notfallsanitäter*in"><datalist id="bq-liste">${z.berufe.map((b) =>
          `<option value="${esc(b)}"></option>`).join("")}</datalist></div>
      <div class="field"><label for="bk">Kreis oder kreisfreie Stadt deiner Tätigkeit</label>
        <input id="bk" list="bk-liste" autocomplete="off" placeholder="z. B. Heidekreis">
        <datalist id="bk-liste">${kreise.kreise.map((k) => `<option value="${esc(k.name)}"></option>`).join("")}</datalist></div>
      <div class="field-row">
        <div class="field"><label for="bo">Organisation (optional)</label>
          <input id="bo" name="organisation" maxlength="120"></div>
        <div class="field"><label for="bwa">Wache (optional)</label>
          <input id="bwa" name="wache" maxlength="120"></div>
      </div>
      <div class="field"><label for="bm">Warum möchtest du dabei sein? (optional)</label>
        <textarea id="bm" name="motivation" maxlength="1000" rows="3"></textarea></div>
      ${empf ? "" : `<div class="field"><label for="bb">Mitglied, das dich kennt (optional)</label>
        <input id="bb" name="buerge" maxlength="200" autocapitalize="none" spellcheck="false"
          placeholder="Benutzername oder E-Mail-Adresse">
        <p class="tiny muted" data-s="mt-xs">Das Mitglied sieht Name, Beruf, Region und deine
        Begründung, nicht deine E-Mail-Adresse.</p></div>`}
      <label class="check confirm"><input type="checkbox" name="datenschutz" required>
        <span>Ich bin einverstanden, dass meine Angaben für die Entscheidung über den Zugang
        gespeichert werden. Unbestätigte Bewerbungen werden nach 48 Stunden gelöscht,
        entschiedene 30 Tage nach der Entscheidung. Mehr unter
        <a href="#/rechtliches" data-rechtstext="datenschutz">Datenschutz</a>.</span></label>
      <button class="btn-primary btn-lg" type="submit">Bewerbung absenden</button>
      <p class="tiny muted" id="bw-err" role="alert"></p>
      <a class="btn-quiet small link-plain" href="#/" data-s="center">Zurück zur Anmeldung</a>
    </form>`);
  $("#bw-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    fd.datenschutz = fd.datenschutz === "on";
    const k = kreise.kreise.find((x) => x.name === $("#bk").value.trim());
    if ($("#bk").value.trim() && !k) { $("#bw-err").textContent = "Bitte einen Kreis aus der Liste wählen."; return; }
    fd.kreis_ags = k ? k.ags : null;
    if (empf) fd.empfehlung = empfehlungCode;
    const knopf = e.target.querySelector("[type=submit]");
    knopf.disabled = true;
    try {
      fd.pow = await arbeitsnachweis(fd.email);
      const r = await api("/api/oeffentlich/bewerbung", { method: "POST", body: fd });
      authShell("Fast geschafft", `<p class="small">${esc(r.detail)}</p>
        <a class="btn btn-lg link-plain" href="#/" data-s="mt-md">Zur Anmeldung</a>`);
    } catch (err) { $("#bw-err").textContent = err.message; knopf.disabled = false; }
  });
}

// ---------------------------------------------- Administration: Bewerbungen

const BW_STATUS = { offen: "offen", angenommen: "angenommen", abgelehnt: "abgelehnt" };
const BW_BUERGE = { empfohlen: "hat die Person eingeladen", wartet: "wartet auf Bestätigung der Adresse", angefragt: "angefragt",
  bestaetigt: "kennt die Person", abgelehnt: "kennt die Person nicht",
  nicht_gefunden: "nicht gefunden", entfallen: "Konto gelöscht" };

async function renderBewerbungen() {
  const box = $("#admin-bewerbungen");
  if (!box) return;
  const r = await api("/api/admin/bewerbungen");
  const offen = r.bewerbungen.filter((b) => b.status === "offen");
  box.innerHTML = `
    <div class="card pad-lg" data-s="mt-md">
      <div class="spread"><h2>Bewerbungen</h2>
        <label class="switch-row compact"><span class="small">Bewerbung möglich</span>
          <input type="checkbox" role="switch" id="bw-schalter" ${r.offen ? "checked" : ""}></label></div>
      ${r.mail ? "" : `<p class="small missing" data-s="mt-xs">Ohne Mailversand ist keine Bewerbung möglich.</p>`}
      <p class="tiny muted" data-s="mt-xs">${offen.length} offen. Entschiedene Bewerbungen werden
      nach 30 Tagen gelöscht, angenommene spätestens mit der Registrierung.</p>
      ${r.bewerbungen.length ? `<div class="stack" data-s="mt-md">${r.bewerbungen.map((b) => `
        <div class="card flat pad-xs">
          <div class="spread"><strong>${esc(b.vorname)} ${esc(b.nachname)}</strong>
            <span class="status ${b.status === "offen" ? "info" : b.status === "angenommen" ? "ok" : "fail"}">${
              esc(BW_STATUS[b.status] || b.status)}</span></div>
          <div class="tiny muted">${esc(b.email)} · ${[b.qualifikation, b.organisation, b.wache, b.kreis]
            .filter(Boolean).map(esc).join(" · ")}</div>
          ${b.begruendung ? `<p class="small" data-s="mt-xs">${esc(b.begruendung)}</p>` : ""}
          <p class="tiny" data-s="mt-xs"><strong>Bürgschaft:</strong> ${b.buerge
            ? `${esc(b.buerge.name || b.buerge.benutzername)}: ${esc(BW_BUERGE[b.antwort] || "")}${
              b.text ? ` – „${esc(b.text)}“` : ""}`
            : b.buerge_eingabe ? `„${esc(b.buerge_eingabe)}“ ${esc(BW_BUERGE.nicht_gefunden)}`
            : "keine angegeben"}</p>
          ${b.status === "offen" ? `<div class="row wrap" data-s="gap-sm mt-sm">
            <button class="btn-primary small" data-bw-an="${esc(b.id)}">Annehmen</button>
            <button class="btn-soft small" data-bw-ab="${esc(b.id)}">Ablehnen</button></div>` : ""}
        </div>`).join("")}</div>` : `<p class="small muted" data-s="mt-sm">Keine Bewerbungen.</p>`}
    </div>`;
  $("#bw-schalter", box).addEventListener("change", async (e) => {
    await api("/api/admin/bewerbungen/einstellung", { method: "PUT", body: { offen: e.target.checked } });
    toast(e.target.checked ? "Bewerbung möglich." : "Bewerbung abgeschaltet.");
  });
  box.querySelectorAll("[data-bw-an]").forEach((k) => k.addEventListener("click", () => sheet("Bewerbung annehmen", `
    <form id="ba-form" class="stack">
      <div class="field"><label for="ba-rolle">Rolle</label>
        <select id="ba-rolle"><option value="user">Mitarbeiter</option><option value="guest">Gast (Lesezugriff)</option></select></div>
      <div class="field"><label for="ba-totp">Code aus der Authenticator-App</label>
        <input id="ba-totp" inputmode="numeric" autocomplete="one-time-code" maxlength="8" required></div>
      <p class="tiny muted">Die Einladung geht an die bestätigte Adresse und gilt 14 Tage.</p>
      <button class="btn-primary" type="submit">Annehmen und einladen</button>
      <p class="tiny muted" id="ba-err" role="alert"></p>
    </form>`, (body) => $("#ba-form", body).addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const r2 = await api(`/api/admin/bewerbungen/${encodeURIComponent(k.dataset.bwAn)}/annehmen`,
        { method: "POST", body: { role: $("#ba-rolle", body).value, totp_code: $("#ba-totp", body).value } });
      closeSheet();
      toast(r2.sent ? "Einladung verschickt." : "Angenommen, die Mail ging nicht raus.");
      renderBewerbungen();
    } catch (err) { $("#ba-err", body).textContent = err.message; }
  }))));
  box.querySelectorAll("[data-bw-ab]").forEach((k) => k.addEventListener("click", () => sheet("Bewerbung ablehnen", `
    <form id="bl-form" class="stack">
      <div class="field"><label for="bl-notiz">Interne Notiz (optional)</label><input id="bl-notiz" maxlength="300"></div>
      <label class="check"><input type="checkbox" id="bl-mail" checked> Absage per E-Mail mitteilen</label>
      <button class="btn-danger" type="submit">Ablehnen</button>
    </form>`, (body) => $("#bl-form", body).addEventListener("submit", async (e) => {
    e.preventDefault();
    await api(`/api/admin/bewerbungen/${encodeURIComponent(k.dataset.bwAb)}/ablehnen`, { method: "POST",
      body: { notiz: $("#bl-notiz", body).value, benachrichtigen: $("#bl-mail", body).checked } });
    closeSheet(); renderBewerbungen();
  }))));
}

// ------------------------------------------------ Administration: Kataloge

const KAT_TITEL = { organisationen: "Organisationen", wachen: "Wachen",
  qualifikationen: "Qualifikationen und Kurse" };

async function renderKatalogAdmin() {
  const box = $("#admin-katalog");
  if (!box) return;
  const [k, th] = await Promise.all([api("/api/admin/katalog"), api("/api/admin/themen")]);
  const offen = (l) => l.filter((x) => x.status === "neu" || x.status === "vorgeschlagen").length;
  box.innerHTML = `
    <div class="card pad-lg" data-s="mt-md">
      <h2>Kataloge</h2>
      <p class="tiny muted" data-s="mt-xs">Organisationen und Wachen entstehen aus Einreichungen der
      Mitglieder. Sichten, umbenennen, Doppelte zusammenführen. Kreise stammen aus dem
      Gemeindeverzeichnis des Statistischen Bundesamtes.</p>
      ${Object.keys(KAT_TITEL).map((art) => `
        <details class="kat-gruppe" data-s="mt-md"${offen(k[art]) ? " open" : ""}>
          <summary><strong>${KAT_TITEL[art]}</strong> <span class="tiny muted">${k[art].length}${
            offen(k[art]) ? ` · ${offen(k[art])} neu` : ""}</span></summary>
          <ul class="entry-list">${k[art].map((x) => `
            <li class="entry-row"><span class="grow"><strong>${esc(x.name)}</strong>
              <span class="tiny muted np-sub">${[x.status, x.organisation, x.kreis,
                x.gueltig_monate ? `${x.gueltig_monate} Monate gültig` : "",
                x.fortbildung_stunden ? `${x.fortbildung_stunden} h/Jahr` : "",
                `${x.mitglieder} Mitglieder`].filter(Boolean).map(esc).join(" · ")}</span></span>
              <button type="button" class="btn-quiet small" data-kat-art="${art}" data-kat-id="${esc(x.id)}">Bearbeiten</button>
            </li>`).join("")}</ul>
        </details>`).join("")}
      <details class="kat-gruppe" data-s="mt-md">
        <summary><strong>Themen</strong> <span class="tiny muted">${th.themen.length}</span></summary>
        <ul class="entry-list">${th.themen.map((t) => `
          <li class="entry-row"><span class="grow"><strong>${esc(t.name)}</strong>
            <span class="tiny muted np-sub">#${esc(t.code)} · ${esc(t.kategorie)}${t.status === "aus" ? " · aus" : ""}</span></span>
            <button type="button" class="btn-quiet small" data-th-edit="${esc(t.code)}">Bearbeiten</button></li>`).join("")}</ul>
      </details>
      <button type="button" class="btn-soft small" id="th-neu" data-s="mt-md">Thema anlegen</button>
    </div>`;

  box.querySelectorAll("[data-kat-id]").forEach((b) => b.addEventListener("click", () => {
    const art = b.dataset.katArt;
    const x = k[art].find((y) => y.id === b.dataset.katId);
    const andere = k[art].filter((y) => y.id !== x.id);
    const stati = art === "qualifikationen" ? ["frei", "vorgeschlagen", "aus"] : ["frei", "neu"];
    sheet(KAT_TITEL[art], `
      <form id="ke-form" class="stack">
        <div class="field"><label for="ke-name">Name</label><input id="ke-name" maxlength="160" value="${esc(x.name)}"></div>
        <div class="field"><label for="ke-status">Status</label><select id="ke-status">${stati.map((s) =>
          `<option ${s === x.status ? "selected" : ""}>${s}</option>`).join("")}</select></div>
        ${art === "qualifikationen" ? `<div class="field-row">
          <div class="field"><label for="ke-mon">Gültigkeit in Monaten (0 = unbefristet)</label>
            <input id="ke-mon" type="number" min="0" max="240" value="${x.gueltig_monate || 0}"></div>
          <div class="field"><label for="ke-h">Fortbildung Stunden/Jahr (0 = keine)</label>
            <input id="ke-h" type="number" min="0" max="500" value="${x.fortbildung_stunden || 0}"></div></div>
          ${x.quelle ? `<p class="tiny muted">Quelle: ${esc(x.quelle)}</p>` : ""}` : ""}
        <button class="btn-primary" type="submit">Speichern</button>
        <div class="field" data-s="mt-md"><label for="ke-ziel">Zusammenführen mit</label>
          <select id="ke-ziel"><option value="">–</option>${andere.map((y) =>
            `<option value="${esc(y.id)}">${esc(y.name)}</option>`).join("")}</select></div>
        <button type="button" class="btn-soft" id="ke-merge">Zusammenführen</button>
        <button type="button" class="btn-danger" id="ke-del">Löschen</button>
        <p class="tiny muted" id="ke-err" role="alert"></p>
      </form>`, (body) => {
      const url = `/api/admin/katalog/${art}/${encodeURIComponent(x.id)}`;
      const fertig = () => { closeSheet(); renderKatalogAdmin(); };
      $("#ke-form", body).addEventListener("submit", async (e) => {
        e.preventDefault();
        const daten = { name: $("#ke-name", body).value, status: $("#ke-status", body).value };
        if (art === "qualifikationen") {
          daten.gueltig_monate = Number($("#ke-mon", body).value);
          daten.fortbildung_stunden = Number($("#ke-h", body).value);
        }
        try { await api(url, { method: "PUT", body: daten }); fertig(); }
        catch (err) { $("#ke-err", body).textContent = err.message; }
      });
      $("#ke-merge", body).addEventListener("click", async () => {
        const ziel = $("#ke-ziel", body).value;
        if (!ziel || !confirm("Zusammenführen? Alle Mitglieder wandern zum Ziel, dieser Eintrag verschwindet.")) return;
        await api(url, { method: "PUT", body: { zusammenfuehren_mit: ziel } }); fertig();
      });
      $("#ke-del", body).addEventListener("click", async () => {
        if (!confirm("Eintrag löschen? Er verschwindet aus allen Profilen.")) return;
        await api(url, { method: "DELETE" }); fertig();
      });
    });
  }));

  const themaSheet = (t) => sheet(t ? "Thema bearbeiten" : "Thema anlegen", `
    <form id="te-form" class="stack">
      <div class="field"><label for="te-name">Name</label><input id="te-name" maxlength="60" required value="${esc(t ? t.name : "")}"></div>
      ${t ? "" : `<div class="field"><label for="te-code">Schlagwort ohne # (optional)</label>
        <input id="te-code" maxlength="40" placeholder="wird sonst aus dem Namen gebildet"></div>`}
      <div class="field"><label for="te-kat">Kategorie</label><select id="te-kat">${th.kategorien.map((x) =>
        `<option ${t && t.kategorie === x ? "selected" : ""}>${esc(x)}</option>`).join("")}</select></div>
      ${t ? `<div class="field"><label for="te-st">Status</label><select id="te-st">
        <option value="frei" ${t.status === "frei" ? "selected" : ""}>frei</option>
        <option value="aus" ${t.status === "aus" ? "selected" : ""}>aus</option></select></div>` : ""}
      <button class="btn-primary" type="submit">Speichern</button>
      <p class="tiny muted" id="te-err" role="alert"></p>
    </form>`, (body) => $("#te-form", body).addEventListener("submit", async (e) => {
    e.preventDefault();
    const daten = { name: $("#te-name", body).value, kategorie: $("#te-kat", body).value };
    try {
      if (t) {
        daten.status = $("#te-st", body).value;
        await api("/api/admin/themen/" + encodeURIComponent(t.code), { method: "PUT", body: daten });
      } else {
        if ($("#te-code", body).value) daten.code = $("#te-code", body).value.trim().toLowerCase();
        await api("/api/admin/themen", { method: "POST", body: daten });
      }
      closeSheet(); renderKatalogAdmin();
    } catch (err) { $("#te-err", body).textContent = err.message; }
  }));
  box.querySelectorAll("[data-th-edit]").forEach((b) => b.addEventListener("click", () =>
    themaSheet(th.themen.find((t) => t.code === b.dataset.thEdit))));
  $("#th-neu", box).addEventListener("click", () => themaSheet(null));
}
