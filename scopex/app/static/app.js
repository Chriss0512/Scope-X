/* SCOPE X - Oberflaeche
   Bewusst ohne Framework und ohne Build-Schritt. Die Anwendung soll in
   fuenf Jahren noch startfaehig sein, ohne dass jemand eine
   Abhaengigkeitskette aktualisieren muss. */

"use strict";

const state = {
  auth: null,
  constants: null,
  measures: null,
  recentMeasures: [],
  medications: null,
  recentMedications: [],
  complications: null,
  settings: null,
  filters: { period: "year" },
};

// ---------------------------------------------------------------- Helfer

const $ = (sel, root = document) => root.querySelector(sel);
const app = () => document.getElementById("app");

function esc(v) {
  if (v === null || v === undefined) return "";
  return String(v).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

async function api(path, options = {}) {
  const init = { credentials: "same-origin", ...options };
  if (init.body && !(init.body instanceof FormData)) {
    init.headers = { "Content-Type": "application/json", ...(init.headers || {}) };
    if (typeof init.body !== "string") init.body = JSON.stringify(init.body);
  }
  const res = await fetch(path, init);
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (_) { /* nicht JSON */ }
  if (res.status === 401 && !path.includes("/auth/")) {
    state.auth = null;
    boot();
    throw new Error("Nicht angemeldet.");
  }
  if (!res.ok) throw new Error((data && data.detail) || "Es ist ein Fehler aufgetreten.");
  return data;
}

let toastTimer = null;
function toast(message) {
  const root = document.getElementById("toast-root");
  root.innerHTML = `<div class="toast">${esc(message)}</div>`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { root.innerHTML = ""; }, 3200);
}

function sheet(title, bodyHtml, onMount) {
  const root = document.getElementById("sheet-root");
  root.innerHTML = `
    <div class="sheet-backdrop" data-close>
      <div class="sheet" role="dialog" aria-modal="true" aria-label="${esc(title)}">
        <div class="sheet-head">
          <h2>${esc(title)}</h2>
          <button class="btn-quiet" data-close aria-label="Schließen">Schließen</button>
        </div>
        <div class="sheet-body">${bodyHtml}</div>
      </div>
    </div>`;
  root.querySelectorAll("[data-close]").forEach((n) => {
    n.addEventListener("click", (e) => { if (e.target === n) closeSheet(); });
  });
  document.addEventListener("keydown", escClose);
  if (onMount) onMount($(".sheet-body", root));
  const firstField = root.querySelector("input, select, textarea");
  if (firstField) firstField.focus();
}

function escClose(e) { if (e.key === "Escape") closeSheet(); }

function closeSheet() {
  document.getElementById("sheet-root").innerHTML = "";
  document.removeEventListener("keydown", escClose);
}

function setBars(root) {
  root.querySelectorAll("[data-fill]").forEach((n) => {
    n.style.width = Math.max(2, Number(n.dataset.fill) || 0) + "%";
  });
}

const pad = (n) => String(n).padStart(2, "0");
const todayISO = () => {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};
const nowHM = () => {
  const d = new Date();
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

function fmtDate(iso) {
  if (!iso) return "";
  const [y, m, d] = String(iso).slice(0, 10).split("-");
  return d ? `${d}.${m}.${y}` : iso;
}

function lockChip(lock) {
  if (!lock) return "";
  if (lock.locked) {
    return `<span class="lock-chip closed" title="Gesperrt, weiterhin lesbar">gesperrt</span>`;
  }
  const mins = Math.ceil(lock.remaining_seconds / 60);
  const label = mins >= 60
    ? `${Math.floor(mins / 60)} h ${mins % 60} min`
    : `${mins} min`;
  return `<span class="lock-chip open" title="Bearbeitbar bis zum Ablauf der Frist">${esc(label)} änderbar</span>`;
}

/* Unvollständiger Scope-Ring. Als Wortmarke links neben der Schrift, als
   Hintergrundmotiv mit niedriger Deckkraft, als ruhiges Zeichen in leeren
   Zuständen. Immer dieselbe Geometrie, nie dekorativ überlagert. */
function markSvg(cls = "mark") {
  return `<svg class="${cls}" viewBox="0 0 100 100" aria-hidden="true">
    <g fill="none" stroke-width="10" stroke-linecap="round" transform="rotate(-90 50 50)">
      <circle cx="50" cy="50" r="38" stroke="var(--petrol)" stroke-dasharray="68 170.76"/>
      <circle cx="50" cy="50" r="38" stroke="var(--cyan)" stroke-dasharray="52 186.76"
              stroke-dashoffset="-96"/>
      <circle cx="50" cy="50" r="38" stroke="var(--cyan)" opacity=".45"
              stroke-dasharray="26 212.76" stroke-dashoffset="-172"/>
    </g></svg>`;
}

function ringBg() {
  return `<svg class="ring-bg" viewBox="0 0 100 100" aria-hidden="true">
    <g fill="none" stroke-width="3.4" stroke-linecap="round" transform="rotate(-90 50 50)">
      <circle cx="50" cy="50" r="44" stroke="currentColor" stroke-dasharray="80 196.4"/>
      <circle cx="50" cy="50" r="44" stroke="currentColor" stroke-dasharray="60 216.4"
              stroke-dashoffset="-110"/>
      <circle cx="50" cy="50" r="33" stroke="currentColor" stroke-dasharray="44 163.4"
              stroke-dashoffset="-58"/>
    </g></svg>`;
}

function wordmark(size = "") {
  return `<div class="wordmark ${size}">${markSvg()}
    <span class="type">SCOPE<span class="x">X</span></span></div>`;
}

/* Ergebnis wird als Statuspunkt-Pille dargestellt. Die Farbe codiert den
   Ausgang, der Text bleibt trotzdem stehen: Farbe allein trägt nie eine
   Information. */
const STATUS_CLASS = {
  erfolgreich: "ok", fehlgeschlagen: "fail", abgebrochen: "abort",
};

function statusBadge(outcome) {
  return `<span class="status ${STATUS_CLASS[outcome] || ""}">${esc(outcome)}</span>`;
}

// ------------------------------------------------------------- Stammdaten

async function loadCatalogs(force = false) {
  if (state.measures && !force) return;
  const [constants, measures, medications, complications, settings] =
    await Promise.all([
      api("/api/catalog/constants"),
      api("/api/catalog/measures"),
      api("/api/catalog/medications"),
      api("/api/catalog/complications"),
      api("/api/settings"),
    ]);
  state.constants = constants;
  state.measures = measures.measures;
  state.recentMeasures = measures.recent;
  state.medications = medications.medications;
  state.recentMedications = medications.recent;
  state.complications = complications.complications;
  state.settings = settings;
  applyTheme(settings.theme);
}

function applyTheme(pref) {
  const dark = pref === "dark" ||
    (pref === "auto" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

function isAdmin() {
  return state.auth && state.auth.user && state.auth.user.role === "admin";
}

function canWrite() {
  const role = state.auth && state.auth.user && state.auth.user.role;
  return role === "user" || role === "admin";
}

function showDelegation() {
  const mode = state.settings && state.settings.show_delegation;
  if (mode === "always") return true;
  if (mode === "never") return false;
  const q = (state.auth && state.auth.profile && state.auth.profile.qualification) || "";
  return !/arzt|ärztin/i.test(q);
}

// ------------------------------------------------------------ Anmeldung

function authShell(title, inner) {
  document.body.classList.add("auth");
  document.getElementById("nav").hidden = true;
  app().innerHTML = `
    <div class="auth-wrap">
      <div class="auth-head">
        ${wordmark("lg")}
        <p class="claim">Das Maßnahmen- und Kompetenzlogbuch<br>für den Rettungsdienst</p>
      </div>
      <div class="card pad-lg">
        <h2>${esc(title)}</h2>
        <div data-s="mt-lg">${inner}</div>
      </div>
      <p class="tiny muted" data-s="mt-xl center">
        Kompetenz. Erfahrung. Sicherheit.<br>
        <a href="#/rechtliches">Impressum und Datenschutz</a></p>
    </div>`;
}

function viewLogin() {
  authShell("Anmelden", `
    <form id="login-form" class="stack">
      <div class="field"><label for="lu">Benutzername oder E-Mail-Adresse</label>
        <input id="lu" name="username" autocomplete="username"
          autocapitalize="none" autocorrect="off" spellcheck="false" required></div>
      <div class="field"><label for="lp">Passwort</label>
        <input id="lp" type="password" name="password" autocomplete="current-password" required></div>
      <div class="field"><label for="lt">Code aus der Authenticator-App</label>
        <input id="lt" name="totp_code" inputmode="numeric" autocomplete="one-time-code"
               pattern="[0-9]*" maxlength="6" placeholder="000000"></div>
      <div class="row gap-md align-start" data-s="gap-md align-start">
        <input id="remember" type="checkbox" data-s="checkbox">
        <label for="remember" data-s="m-0">Auf diesem Gerät merken
          <span class="muted">– dann entfällt der Code für 90 Tage. Nicht auf
          fremden oder geteilten Geräten verwenden.</span></label>
      </div>
      <button class="btn-primary btn-lg" type="submit">Anmelden</button>
      <button class="btn-quiet small" type="button" id="use-recovery">Stattdessen Wiederherstellungscode verwenden</button>
      <a class="btn-quiet small link-plain" href="#/passwort-vergessen"
         data-s="center link-plain">Passwort vergessen</a>
      <p class="tiny muted" id="login-error"></p>
    </form>`);

  let recoveryMode = false;
  $("#use-recovery").addEventListener("click", () => {
    recoveryMode = !recoveryMode;
    const f = $("#lt");
    f.placeholder = recoveryMode ? "XXXX-XXXX-XXXX-XXXX" : "000000";
    f.value = "";
    f.previousElementSibling.textContent = recoveryMode
      ? "Wiederherstellungscode" : "Code aus der Authenticator-App";
  });

  $("#login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const code = String(fd.get("totp_code") || "").trim();
    try {
      await api("/api/auth/login", {
        method: "POST",
        body: {
          username: fd.get("username"),
          password: fd.get("password"),
          totp_code: recoveryMode ? null : code,
          recovery_code: recoveryMode ? code : null,
          remember_device: $("#remember").checked,
        },
      });
      await boot();
    } catch (err) {
      $("#login-error").textContent = err.message;
    }
  });
}

async function viewInvitedRegister(code) {
  let info;
  try {
    info = await api("/api/auth/invitation/" + encodeURIComponent(code));
  } catch (err) {
    return authShell("Einladung ungültig", `
      <p class="small">${esc(err.message)}</p>
      <p class="small muted">Bitte wende dich an die Person, die dich
      eingeladen hat. Codes gelten befristet und nur einmal.</p>
      <a class="btn btn-lg link-plain" href="#/" data-s="mt-md">Zur Anmeldung</a>`);
  }
  viewRegister(code, info);
}

function viewRegister(inviteCode, invite) {
  authShell(inviteCode ? "Einladung annehmen" : "Konto einrichten", `
    ${inviteCode
      ? `<div class="notice">Du wurdest als <strong>${esc(invite.role_label)}</strong>
         eingeladen. Der nächste Schritt nach dem Anlegen ist die Einrichtung
         der Zwei-Faktor-Authentifizierung.</div>`
      : `<p class="small muted">Dieses Konto wird einmalig auf diesem Server
         angelegt und ist automatisch Administrator. Weitere Personen können
         danach nur noch per Einladung dazukommen.</p>`}
    <form id="reg-form" class="stack" data-s="mt-lg">
      <div class="field-row">
        <div class="field"><label for="rf">Vorname</label><input id="rf" name="first_name"></div>
        <div class="field"><label for="rl">Nachname</label><input id="rl" name="last_name"></div>
      </div>
      <div class="field"><label for="rq">Qualifikation</label>
        <select id="rq" name="qualification">
          <option>Notfallsanitäter</option>
          <option>Rettungssanitäter</option>
          <option>Arzt / Ärztin</option>
        </select></div>
      <div class="field"><label for="ru">Benutzername</label>
        <input id="ru" name="username" autocomplete="username" required minlength="3"
          autocapitalize="none" autocorrect="off" spellcheck="false">
        <p class="tiny muted" data-s="mt-xs">Damit meldest du dich an. Der Name
        steht später jederzeit unter Profil und Einstellungen.</p></div>
      <div class="field"><label for="re">E-Mail-Adresse${
        inviteCode ? "" : " (optional)"}</label>
        <input id="re" type="email" name="email" autocomplete="email"
          autocapitalize="none" autocorrect="off" spellcheck="false"
          value="${esc((invite && invite.email) || "")}">
        <p class="tiny muted" data-s="mt-xs">Wenn du eine hinterlegst, kannst du
        dich wahlweise damit anmelden.</p></div>
      <div class="field"><label for="rp">Passwort, mindestens 12 Zeichen</label>
        <input id="rp" type="password" name="password" autocomplete="new-password" required minlength="12"></div>
      <button class="btn-primary btn-lg" type="submit">Konto anlegen</button>
      <p class="tiny muted" id="reg-error"></p>
    </form>`);

  $("#reg-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    if (inviteCode) fd.invite_code = inviteCode;
    try {
      const res = await api("/api/auth/register", { method: "POST", body: fd });
      viewTotpSetup(res.totp);
    } catch (err) { $("#reg-error").textContent = err.message; }
  });
}

function viewTotpSetup(totp) {
  authShell("Zwei-Faktor-Authentifizierung", `
    <p class="small muted">Scanne den Code mit Google Authenticator, Aegis, 2FAS,
    Microsoft Authenticator oder einer anderen TOTP-App. Die Einrichtung
    funktioniert vollständig offline.</p>
    <div class="qr">${totp.qr_svg}</div>
    <div class="field">
      <label>Falls das Scannen nicht klappt, Schlüssel manuell eintragen</label>
      <input readonly value="${esc(totp.secret)}">
    </div>
    <form id="totp-form" class="stack" data-s="mt-lg">
      <div class="field"><label for="tc">Sechsstelliger Code zur Bestätigung</label>
        <input id="tc" name="code" inputmode="numeric" pattern="[0-9]*" maxlength="6"
               autocomplete="one-time-code" placeholder="000000" required></div>
      <button class="btn-primary btn-lg" type="submit">Einrichtung abschließen</button>
      <p class="tiny muted" id="totp-error"></p>
    </form>`);

  $("#totp-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const code = new FormData(e.target).get("code");
    try {
      const res = await api("/api/auth/totp/confirm", { method: "POST", body: { code } });
      viewRecoveryCodes(res.recovery_codes);
    } catch (err) { $("#totp-error").textContent = err.message; }
  });
}

function viewRecoveryCodes(codes) {
  authShell("Wiederherstellungscodes", `
    <div class="notice">Diese Codes sind der einzige Weg zurück, wenn das Gerät
    mit der Authenticator-App verloren geht. Jeder Code funktioniert einmal.
    Drucke sie aus oder lege sie in einen Passwortmanager.</div>
    <div class="codes" data-s="my-lg">
      ${codes.map((c) => `<span>${esc(c)}</span>`).join("")}
    </div>
    <div class="sheet-actions two">
      <button id="copy-codes">Codes kopieren</button>
      <button class="btn-primary" id="codes-done">Ich habe sie gesichert</button>
    </div>`);
  $("#copy-codes").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(codes.join("\n")); toast("Codes kopiert."); }
    catch (_) { toast("Kopieren nicht möglich. Bitte manuell notieren."); }
  });
  $("#codes-done").addEventListener("click", boot);
}

function viewForgotPassword() {
  authShell("Passwort vergessen", `
    <p class="small muted">Trage deinen Benutzernamen oder deine
    E-Mail-Adresse ein. Wenn dazu ein Konto mit hinterlegter Adresse
    existiert, bekommst du einen Link. Er gilt 30 Minuten und funktioniert
    einmal.</p>
    <form id="fp-form" class="stack" data-s="mt-md">
      <div class="field"><label for="fpi">Benutzername oder E-Mail-Adresse</label>
        <input id="fpi" autocapitalize="none" autocorrect="off" required></div>
      <button class="btn-primary btn-lg" type="submit">Link anfordern</button>
      <a class="btn-quiet small link-plain" href="#/" data-s="center link-plain">Zurück zur Anmeldung</a>
      <p class="tiny muted" id="fp-msg"></p>
    </form>`);
  $("#fp-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    await api("/api/auth/password-reset/request", {
      method: "POST", body: { identifier: $("#fpi").value } });
    /* Die Antwort ist immer gleich. Sonst ließe sich über dieses Formular
       herausfinden, welche Adressen registriert sind. */
    $("#fp-form").innerHTML = `<div class="notice">Wenn zu dieser Angabe ein
      Konto mit hinterlegter E-Mail-Adresse existiert, ist eine Nachricht
      unterwegs. Prüfe auch den Spam-Ordner.</div>
      <p class="small muted" data-s="mt-md">Zum Setzen des neuen Passworts
      brauchst du zusätzlich einen Code aus deiner Authenticator-App oder
      einen Wiederherstellungscode. Der Link allein genügt nicht.</p>
      <a class="btn btn-lg link-plain" href="#/" data-s="mt-md">Zur Anmeldung</a>`;
  });
}

function viewResetPassword(token) {
  authShell("Neues Passwort setzen", `
    <form id="rp-form" class="stack">
      <div class="field"><label for="rp1">Neues Passwort, mindestens 12 Zeichen</label>
        <input id="rp1" type="password" autocomplete="new-password" minlength="12" required></div>
      <div class="field"><label for="rp2">Code aus der Authenticator-App</label>
        <input id="rp2" inputmode="numeric" maxlength="6" pattern="[0-9]*"
          autocomplete="one-time-code" placeholder="000000"></div>
      <div class="field"><label for="rp3">oder Wiederherstellungscode</label>
        <input id="rp3" autocapitalize="characters" placeholder="XXXX-XXXX-XXXX-XXXX"></div>
      <button class="btn-primary btn-lg" type="submit">Passwort setzen</button>
      <p class="tiny muted" id="rp-err"></p>
    </form>`);
  $("#rp-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api("/api/auth/password-reset/confirm", { method: "POST", body: {
        token, new_password: $("#rp1").value,
        totp_code: $("#rp2").value || null,
        recovery_code: $("#rp3").value || null } });
      authShell("Passwort gesetzt", `
        <p class="small">Das neue Passwort ist aktiv. Alle offenen Sitzungen
        wurden beendet und kein Gerät gilt mehr als vertrauenswürdig.</p>
        <a class="btn btn-primary btn-lg link-plain" href="#/" data-s="mt-md">Jetzt anmelden</a>`);
      history.replaceState(null, "", "#/");
    } catch (err) { $("#rp-err").textContent = err.message; }
  });
}

// ---------------------------------------------------------------- Router

const routes = {
  "/": viewHome,
  "/rechtliches": viewLegal,
  "/neu": viewEncounters,
  "/dashboard": viewDashboard,
  "/nachweise": viewProofs,
  "/profil": viewProfile,
};

function currentRoute() {
  const raw = (location.hash || "#/").slice(1);
  const [pathPart, queryPart] = raw.split("?");
  const [path, ...rest] = pathPart.split("/").filter(Boolean);
  return {
    path: "/" + (path || ""), params: rest,
    query: new URLSearchParams(queryPart || ""),
  };
}

async function render() {
  // Ein offener Dialog gehört zur Seite, die ihn geöffnet hat. Ohne das
  // bleibt er beim Wechsel über die Navigationsleiste über der neuen Seite
  // stehen. Abläufe, die nach dem Speichern erneut einen Dialog öffnen,
  // tun das erst nach render und sind davon nicht betroffen.
  closeSheet();
  const { path, params } = currentRoute();
  document.querySelectorAll("nav.tabbar a").forEach((a) => {
    if (a.dataset.route === path) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  try {
    if (path === "/einsatz" && params[0]) return await viewEncounter(params[0]);
    const view = routes[path] || viewHome;
    await view();
  } catch (err) {
    app().innerHTML = `<div class="empty"><strong>Das hat nicht geklappt.</strong>
      ${esc(err.message)}</div>`;
  }
}

window.addEventListener("hashchange", () => {
  if (!state.auth || !state.auth.authenticated) { boot(); return; }
  render();
});

// ---------------------------------------------------------- Rechtliches

async function viewLegal() {
  const l = await api("/api/legal");
  const missing = (v, hint) => v
    ? esc(v) : `<span class="missing">${esc(hint)}</span>`;

  app().innerHTML = `
    <div class="page-head">
      <h1>Rechtliches</h1>
      <p class="muted small">Anbieterkennzeichnung und Datenschutz</p>
    </div>

    <div class="card pad-lg legal">
      <h2>Impressum</h2>
      <p class="small muted">Angaben gemäß § 5 DDG</p>
      <address data-s="mt-sm">
        ${missing(l.name, "Name nicht hinterlegt")}<br>
        ${missing(l.address, "Anschrift nicht hinterlegt")}<br>
        ${l.email ? `E-Mail: ${esc(l.email)}`
          : `<span class="missing">E-Mail-Adresse nicht hinterlegt</span>`}
      </address>
      <p class="small" data-s="mt-md"><strong>Privates Projekt.</strong>
      SCOPE X ist eine nicht kommerzielle, privat betriebene Anwendung. Es
      werden keine Leistungen angeboten, keine Werbung ausgespielt und keine
      Einnahmen erzielt. Die Nutzung ist nur mit persönlicher Einladung
      möglich.</p>

      <h2>Verantwortlich für den Betrieb</h2>
      <p class="small">Die Anwendung läuft auf einem privaten Server. Ein
      Betrieb durch Dritte, eine Auftragsverarbeitung oder eine Weitergabe
      von Daten an andere Stellen findet nicht statt.</p>

      <h2>Datenschutz</h2>
      <p class="small">Verantwortlich im Sinne von Art. 4 Nr. 7 DSGVO ist die
      oben genannte Person.</p>
      <p class="small"><strong>Welche Daten verarbeitet werden.</strong>
      Benutzername, optional eine E-Mail-Adresse, ein Passwort-Hash, die
      Einrichtung der Zwei-Faktor-Authentifizierung sowie die von dir selbst
      eingetragenen Profilangaben. Dazu die von dir dokumentierten Maßnahmen,
      Medikamentengaben, Zwischenfälle und Einsatzdaten.</p>
      <p class="small"><strong>Keine Patientendaten.</strong> Namen,
      Geburtsdaten und Anschriften werden nicht erhoben. Die Einsatznummer
      ist optional. Sie ist ein Pseudonym, das durch die Leitstelle
      auflösbar sein kann; trage sie nur ein, wenn du das brauchst, und
      halte Freitextfelder knapp.</p>
      <p class="small"><strong>Zweck und Grundlage.</strong> Die
      Verarbeitung dient ausschließlich deiner persönlichen Dokumentation
      und Nachweisführung. Grundlage ist deine Einwilligung nach
      Art. 6 Abs. 1 lit. a DSGVO, die du jederzeit widerrufen kannst.</p>
      <p class="small"><strong>Speicherort.</strong> Alle Daten liegen
      ausschließlich auf dem privaten Server des Betreibers. Es werden keine
      Cloud-Dienste, kein Tracking, keine Analyse- und keine
      Telemetriedienste eingesetzt. Die Anwendung lädt zur Laufzeit nichts
      aus dem Internet nach.</p>
      <p class="small"><strong>Speicherdauer.</strong> Daten bleiben
      gespeichert, bis du sie löschst oder dein Konto aufgelöst wird. Ein
      dokumentierter Eintrag wird nach Ablauf der eingestellten
      Bearbeitungsfrist gesperrt und kann danach nur noch mit Begründung
      stillgelegt werden.</p>
      <p class="small"><strong>Deine Rechte.</strong> Auskunft, Berichtigung,
      Löschung, Einschränkung der Verarbeitung, Datenübertragbarkeit und
      Widerspruch nach Art. 15 bis 21 DSGVO, dazu ein Beschwerderecht bei
      einer Aufsichtsbehörde. Einen vollständigen Export deiner Daten
      erzeugst du selbst unter Profil und Einstellungen.</p>

      <h2>Kein medizinisches Produkt</h2>
      <p class="small">SCOPE X ist ein persönliches Logbuch. Es ist kein
      Einsatzprotokoll, keine Patientenakte und kein
      Entscheidungsunterstützungssystem. Es schlägt keine Indikationen vor,
      empfiehlt keine Dosierungen, zeigt keine Algorithmen und ersetzt keine
      SOP.</p>
    </div>

    <button class="btn-quiet btn-lg" data-s="mt-md" id="back">Zurück</button>`;

  $("#back").addEventListener("click", () => history.back());
}

// ------------------------------------------------------------- Startseite

async function viewHome() {
  const o = await api("/api/overview");
  const name = (state.auth.profile && state.auth.profile.first_name) || "";
  app().innerHTML = `
    <div class="page-head">
      ${wordmark()}
      <p class="claim">Skills · Competencies · Outcomes · Procedures ·
        Emergency eXperience</p>
    </div>

    ${canWrite() ? `<button class="btn-start has-ring" id="new-doc">
      ${ringBg()}<span class="txt">Neue Dokumentation</span>
    </button>` : `<div class="notice plain">Dieses Konto hat Lesezugriff.
      Neue Dokumentationen kann ein Administrator freischalten.</div>`}

    <div class="tiles" data-s="mt-lg">
      <div class="tile"><div class="value">${o.attempts}</div>
        <div class="label">Maßnahmen insgesamt</div></div>
      <div class="tile"><div class="value">${o.attempts_year}</div>
        <div class="label">Maßnahmen ${o.year}</div></div>
      <div class="tile"><div class="value">${o.encounters}</div>
        <div class="label">Einsätze</div></div>
      <div class="tile"><div class="value">${o.medications}</div>
        <div class="label">Medikamentengaben</div></div>
      <div class="tile"><div class="value">${o.complications}</div>
        <div class="label">ZEK</div></div>
    </div>

    <h2 data-s="my-xl">Zuletzt dokumentiert</h2>
    <div class="stack" id="recent"></div>`;

  const newDoc = $("#new-doc");
  if (newDoc) newDoc.addEventListener("click", newEncounterSheet);

  const recent = $("#recent");
  if (!o.recent.length) {
    recent.innerHTML = `<div class="empty">${markSvg("mark")}
      <strong>Noch nichts dokumentiert.</strong>
      Der erste Eintrag ist zwei Fingertipps entfernt.</div>`;
    return;
  }
  recent.innerHTML = o.recent.map((r) => `
    <a class="entry" data-cat="${esc(r.measure_category)}" data-s="link-block"
       href="#/einsatz/${esc(r.encounter_id)}">
      <div class="spread">
        <div class="grow">
          <div class="row" data-s="gap-sm">
            <span class="cat-badge">${esc(r.measure_category)}</span>
            <strong>${esc(r.measure_name)}</strong>
          </div>
          <div class="row wrap" data-s="mt-sm gap-sm">
            ${statusBadge(r.outcome)}
            ${r.naca ? `<span class="tiny muted">NACA ${esc(r.naca)}</span>` : ""}
          </div>
        </div>
        <span class="small muted">${esc(fmtDate(r.performed_at))}</span>
      </div>
    </a>`).join("");
}

// -------------------------------------------------------- Einsatzuebersicht

async function viewEncounters() {
  const data = await api("/api/encounters?limit=50");
  app().innerHTML = `
    <div class="page-head spread">
      <div><h1>Erfassen</h1>
        <p class="muted small">Einsätze und ihre dokumentierten Einträge</p></div>
    </div>
    ${canWrite() ? `<button class="btn-start has-ring" id="new-doc">
      ${ringBg()}<span class="txt">Neue Dokumentation</span>
    </button>` : ""}
    <div class="stack" data-s="mt-lg" id="list"></div>`;
  const nd = $("#new-doc");
  if (nd) nd.addEventListener("click", newEncounterSheet);

  const list = $("#list");
  if (!data.encounters.length) {
    list.innerHTML = `<div class="empty">${markSvg("mark")}
      <strong>Keine Einsätze erfasst.</strong>
      Lege den ersten an, um Maßnahmen zu dokumentieren.</div>`;
    return;
  }
  list.innerHTML = data.encounters.map((e) => `
    <a class="card" href="#/einsatz/${esc(e.id)}" data-s="link-block">
      <div class="spread">
        <div class="grow">
          <strong>${esc(fmtDate(e.enc_date))}, ${esc(e.enc_time)}</strong>
          <div class="small muted" data-s="mt-xs">
            ${e.naca ? "NACA " + esc(e.naca) : "ohne NACA"}
            ${e.mission_number ? " · " + esc(e.mission_number) : ""}
            · ${e.attempt_count} Maßnahmen · ${e.medication_count} Medikamente
          </div>
        </div>
        ${lockChip(e.lock)}
      </div>
    </a>`).join("");
}

function newEncounterSheet() {
  const naca = state.constants.naca
    .map((n) => `<button type="button" class="chip accent" data-naca="${esc(n)}"
      aria-pressed="false">NACA ${esc(n)}</button>`).join("");
  sheet("Neue Dokumentation", `
    <form id="enc-form" class="stack">
      <div class="field-row">
        <div class="field"><label for="ed">Datum</label>
          <input id="ed" type="date" name="enc_date" value="${todayISO()}" required></div>
        <div class="field"><label for="et">Uhrzeit</label>
          <input id="et" type="time" name="enc_time" value="${nowHM()}" required></div>
      </div>
      <div class="field"><label for="em">Einsatznummer (optional)</label>
        <input id="em" name="mission_number" autocomplete="off"></div>
      <div class="field"><label>NACA (optional)</label>
        <div class="chipset" id="naca-set">${naca}</div></div>
      <p class="tiny muted">Einsatznummern und Freitext können je nach Verwendung
      einen Personenbezug herstellen. Es werden keine Patientendaten erfasst.</p>
      <div class="sheet-actions">
        <button class="btn-primary btn-lg" type="submit">Einsatz anlegen</button>
      </div>
    </form>`, (body) => {
    let selected = null;
    body.querySelectorAll("[data-naca]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const isOn = btn.getAttribute("aria-pressed") === "true";
        body.querySelectorAll("[data-naca]").forEach((b) =>
          b.setAttribute("aria-pressed", "false"));
        btn.setAttribute("aria-pressed", isOn ? "false" : "true");
        selected = isOn ? null : btn.dataset.naca;
      });
    });
    $("#enc-form", body).addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = Object.fromEntries(new FormData(e.target));
      try {
        const enc = await api("/api/encounters", {
          method: "POST",
          body: { ...fd, naca: selected },
        });
        closeSheet();
        location.hash = "#/einsatz/" + enc.id;
      } catch (err) { toast(err.message); }
    });
  });
}

// ---------------------------------------------------------- Einsatzansicht

async function viewEncounter(id) {
  const enc = await api("/api/encounters/" + encodeURIComponent(id));
  const editable = !enc.lock.locked;

  const items = [
    ...enc.attempts.map((a) => ({ kind: "attempt", at: a.performed_at, data: a })),
    ...enc.medications.map((m) => ({ kind: "med", at: m.administered_at, data: m })),
  ].sort((a, b) => String(a.at).localeCompare(String(b.at)));

  app().innerHTML = `
    <div class="page-head">
      <a class="small muted" href="#/neu" data-s="link-plain">Zurück zur Übersicht</a>
      <div class="spread" data-s="mt-sm">
        <h1>${esc(fmtDate(enc.enc_date))}, ${esc(enc.enc_time)}</h1>
        ${lockChip(enc.lock)}
      </div>
      <p class="muted small">
        ${enc.naca ? "NACA " + esc(enc.naca) : "ohne NACA"}
        ${enc.mission_number ? " · Einsatznummer " + esc(enc.mission_number) : ""}
        · ${enc.attempts.length} Maßnahmen · ${enc.medications.length} Medikamentengaben
      </p>
      ${editable ? `<button class="btn-quiet small" id="edit-enc">Einsatzdaten ändern</button>` : ""}
    </div>

    <div class="stack" id="entries"></div>

    ${editable ? `
    <div class="sheet-actions two" data-s="mt-lg">
      <button class="btn-primary btn-lg" id="add-measure">Maßnahme hinzufügen</button>
      <button class="btn-lg" id="add-med">Medikament hinzufügen</button>
    </div>
    <button class="btn-quiet btn-lg" id="finish" data-s="mt-sm">Einsatz abschließen</button>
    ` : `<div class="notice plain" data-s="mt-lg">Die Bearbeitungsfrist ist
      abgelaufen. Der Einsatz bleibt vollständig lesbar und kann nicht mehr
      geändert werden. Einzelne Einträge lassen sich mit Begründung
      stilllegen; sie verschwinden dann aus Statistik und Nachweis, bleiben
      aber im Änderungsprotokoll nachvollziehbar.</div>
      <button class="btn-quiet btn-lg btn-danger" id="withdraw-enc" data-s="mt-sm">Gesamten Einsatz entfernen</button>`}`;

  const entries = $("#entries");
  if (!items.length) {
    entries.innerHTML = `<div class="empty">${markSvg("mark")}
      <strong>Noch keine Einträge.</strong>
      Datum, Einsatznummer und NACA sind gesetzt und werden nicht erneut abgefragt.</div>`;
  } else {
    entries.innerHTML = items.map((it) => it.kind === "attempt"
      ? attemptCard(it.data, editable) : medCard(it.data, editable)).join("");
  }

  if (editable) {
    $("#add-measure").addEventListener("click", () => measurePicker(enc));
    $("#add-med").addEventListener("click", () => medicationPicker(enc));
    $("#finish").addEventListener("click", () => { location.hash = "#/"; });
    const editEnc = $("#edit-enc");
    if (editEnc) editEnc.addEventListener("click", () => editEncounterSheet(enc));
  }

  const wdEnc = $("#withdraw-enc");
  if (wdEnc) wdEnc.addEventListener("click", () =>
    withdrawSheet("Einsatz entfernen",
      `/api/encounters/${enc.id}/withdraw`,
      "Der Einsatz und alle zugehörigen Einträge werden stillgelegt.",
      () => { location.hash = "#/neu"; }));

  entries.querySelectorAll("[data-wd-attempt]").forEach((b) =>
    b.addEventListener("click", () =>
      withdrawSheet("Maßnahme entfernen",
        `/api/attempts/${b.dataset.wdAttempt}/withdraw`,
        "Der Eintrag verschwindet aus Statistik und Nachweis.")));
  entries.querySelectorAll("[data-wd-med]").forEach((b) =>
    b.addEventListener("click", () =>
      withdrawSheet("Medikamentengabe entfernen",
        `/api/administrations/${b.dataset.wdMed}/withdraw`,
        "Der Eintrag verschwindet aus Statistik und Nachweis.")));

  entries.querySelectorAll("[data-del-attempt]").forEach((b) =>
    b.addEventListener("click", async () => {
      if (!confirm("Diesen Eintrag löschen? Das lässt sich nicht rückgängig machen.")) return;
      await api("/api/attempts/" + b.dataset.delAttempt, { method: "DELETE" });
      toast("Eintrag gelöscht."); render();
    }));
  entries.querySelectorAll("[data-del-med]").forEach((b) =>
    b.addEventListener("click", async () => {
      if (!confirm("Diese Medikamentengabe löschen?")) return;
      await api("/api/administrations/" + b.dataset.delMed, { method: "DELETE" });
      toast("Eintrag gelöscht."); render();
    }));
}

function attemptCard(a, editable) {
  const params = (a.parameters || []).map((p) =>
    `${esc(p.label)}: ${esc(p.value)}${p.unit ? " " + esc(p.unit) : ""}`).join(" · ");
  const zek = zekSummary(a.complications);
  return `
    <div class="entry" data-cat="${esc(a.measure_category)}">
      <div class="spread">
        <div class="grow">
          <div class="row" data-s="gap-sm">
            <span class="cat-badge">${esc(a.measure_category)}</span>
            <strong>${esc(a.measure_name)}</strong>
          </div>
          <div class="row wrap" data-s="mt-sm gap-sm">
            ${statusBadge(a.outcome)}
            ${a.performer_role && a.performer_role !== "selbst durchgeführt"
              ? `<span class="status info">${esc(a.performer_role)}</span>` : ""}
            ${a.delegation ? `<span class="tiny muted">${esc(a.delegation)}</span>` : ""}
          </div>
          ${params ? `<div class="small muted" data-s="mt-xs">${params}</div>` : ""}
          ${zek ? `<div class="zek-line"><span>${zek}</span></div>` : ""}
          ${a.note ? `<div class="small muted" data-s="mt-xs">${esc(a.note)}</div>` : ""}
        </div>
        <div class="stack right" data-s="shrink-0">
          ${lockChip(a.lock)}
          ${a.lock.locked
            ? `<button class="btn-quiet small btn-danger" data-wd-attempt="${esc(a.id)}">Entfernen</button>`
            : `<button class="btn-quiet small btn-danger" data-del-attempt="${esc(a.id)}">Löschen</button>`}
        </div>
      </div>
    </div>`;
}

function medCard(m, editable) {
  const dose = m.dose !== null && m.dose !== undefined
    ? `${String(m.dose).replace(".", ",")}${m.unit ? " " + esc(m.unit) : ""}` : "";
  const zek = zekSummary(m.complications);
  return `
    <div class="entry medication">
      <div class="spread">
        <div class="grow">
          <div class="row" data-s="gap-sm">
            <span class="cat-badge">Rx</span>
            <strong>${esc(m.medication_name)}</strong>
          </div>
          <div class="small" data-s="mt-xs">
            ${esc(dose)}${m.route ? " · " + esc(m.route) : ""}${m.delegation ? " · " + esc(m.delegation) : ""}
          </div>
          ${m.preparation_name ? `<div class="small muted">${esc(m.preparation_name)}</div>` : ""}
          ${zek ? `<div class="zek-line"><span>${zek}</span></div>` : ""}
          ${m.note ? `<div class="small muted" data-s="mt-xs">${esc(m.note)}</div>` : ""}
        </div>
        <div class="stack right" data-s="shrink-0">
          ${lockChip(m.lock)}
          ${m.lock.locked
            ? `<button class="btn-quiet small btn-danger" data-wd-med="${esc(m.id)}">Entfernen</button>`
            : `<button class="btn-quiet small btn-danger" data-del-med="${esc(m.id)}">Löschen</button>`}
        </div>
      </div>
    </div>`;
}

function editEncounterSheet(enc) {
  const naca = state.constants.naca.map((n) =>
    `<button type="button" class="chip accent" data-naca="${esc(n)}"
      aria-pressed="${enc.naca === n}">NACA ${esc(n)}</button>`).join("");
  sheet("Einsatzdaten ändern", `
    <form id="ee-form" class="stack">
      <div class="field-row">
        <div class="field"><label for="ed2">Datum</label>
          <input id="ed2" type="date" name="enc_date" value="${esc(enc.enc_date)}"></div>
        <div class="field"><label for="et2">Uhrzeit</label>
          <input id="et2" type="time" name="enc_time" value="${esc(enc.enc_time)}"></div>
      </div>
      <div class="field"><label for="em2">Einsatznummer</label>
        <input id="em2" name="mission_number" value="${esc(enc.mission_number || "")}"></div>
      <div class="field"><label>NACA</label><div class="chipset">${naca}</div></div>
      <div class="sheet-actions two">
        <button type="button" class="btn-danger" id="del-enc">Einsatz löschen</button>
        <button class="btn-primary" type="submit">Änderungen speichern</button>
      </div>
    </form>`, (body) => {
    let selected = enc.naca || null;
    body.querySelectorAll("[data-naca]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const isOn = btn.getAttribute("aria-pressed") === "true";
        body.querySelectorAll("[data-naca]").forEach((b) =>
          b.setAttribute("aria-pressed", "false"));
        btn.setAttribute("aria-pressed", isOn ? "false" : "true");
        selected = isOn ? null : btn.dataset.naca;
      });
    });
    $("#del-enc", body).addEventListener("click", async () => {
      if (!confirm("Den gesamten Einsatz mit allen Einträgen löschen?")) return;
      await api("/api/encounters/" + enc.id, { method: "DELETE" });
      closeSheet(); toast("Einsatz gelöscht."); location.hash = "#/neu";
    });
    $("#ee-form", body).addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = Object.fromEntries(new FormData(e.target));
      try {
        await api("/api/encounters/" + enc.id, {
          method: "PATCH", body: { ...fd, naca: selected },
        });
        closeSheet(); toast("Gespeichert."); render();
      } catch (err) { toast(err.message); }
    });
  });
}

/* Gesperrte Einträge werden nicht gelöscht, sondern mit Begründung
   stillgelegt. Die Begründung ist Pflicht, weil eine Lücke im Nachweis
   sonst nicht erklärbar wäre. */
function withdrawSheet(title, url, hint, after) {
  sheet(title, `
    <div class="notice warn">${esc(hint)} Der Datensatz bleibt erhalten und
    ist im Änderungsprotokoll mit Zeitpunkt und Begründung nachvollziehbar.
    Rückgängig machen lässt sich das nicht.</div>
    <form id="wd-form" class="stack" data-s="mt-md">
      <div class="field"><label for="wd-reason">Begründung, mindestens fünf Zeichen</label>
        <textarea id="wd-reason" maxlength="500" required
          placeholder="z. B. versehentlich doppelt erfasst"></textarea></div>
      <button class="btn-primary btn-lg" type="submit">Eintrag entfernen</button>
      <p class="tiny muted" id="wd-err"></p>
    </form>`, (body) => {
    $("#wd-form", body).addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await api(url, { method: "POST",
          body: { reason: $("#wd-reason", body).value } });
        closeSheet();
        toast("Eintrag entfernt.");
        if (after) after(); else render();
      } catch (err) { $("#wd-err", body).textContent = err.message; }
    });
  });
}

// --------------------------------------------------------- Massnahmenwahl

function measurePicker(enc) {
  const cats = state.constants.categories;
  sheet("Maßnahme wählen", `
    <div class="field"><input id="m-search" type="text" placeholder="Suchen"
      autocomplete="off" aria-label="Maßnahme suchen"></div>
    <div class="chipset" data-s="my-md" id="m-cats">
      <button class="chip" data-cat="fav" aria-pressed="false">Favoriten</button>
      <button class="chip" data-cat="recent" aria-pressed="true">Zuletzt</button>
      ${cats.map((c) => `<button class="chip" data-cat="${esc(c.key)}"
        aria-pressed="false" title="${esc(c.label)}">${esc(c.key)}</button>`).join("")}
      <button class="chip" data-cat="all" aria-pressed="false">Alle</button>
    </div>
    <div class="pick-list" id="m-list"></div>`, (body) => {
    let filter = "recent";
    const search = $("#m-search", body);
    const list = $("#m-list", body);

    function draw() {
      const term = search.value.trim().toLowerCase();
      let items = state.measures;
      if (term) {
        items = items.filter((m) => m.name.toLowerCase().includes(term));
      } else if (filter === "fav") {
        items = items.filter((m) => m.favorite);
      } else if (filter === "recent") {
        items = state.recentMeasures
          .map((id) => state.measures.find((m) => m.id === id)).filter(Boolean);
        if (!items.length) items = state.measures;
      } else if (filter !== "all") {
        items = items.filter((m) => m.category === filter);
      }
      if (!items.length) {
        list.innerHTML = `<div class="empty small">Keine Treffer. Suchbegriff ändern
          oder eine andere Kategorie wählen.</div>`;
        return;
      }
      list.innerHTML = items.map((m) => `
        <button class="pick" data-measure="${esc(m.id)}" data-cat="${esc(m.category)}">
          <span class="cat-badge">${esc(m.category)}</span>
          <span class="grow" data-s="text-left">${esc(m.name)}</span>
          <span class="star ${m.favorite ? "on" : ""}" data-fav="${esc(m.id)}"
            role="button" title="Favorit">${m.favorite ? "★" : "☆"}</span>
        </button>`).join("");

      list.querySelectorAll("[data-measure]").forEach((b) =>
        b.addEventListener("click", (e) => {
          if (e.target.dataset.fav) return;
          const m = state.measures.find((x) => x.id === b.dataset.measure);
          attemptForm(enc, m);
        }));
      list.querySelectorAll("[data-fav]").forEach((s) =>
        s.addEventListener("click", async (e) => {
          e.stopPropagation();
          const res = await api(`/api/catalog/measures/${s.dataset.fav}/favorite`,
            { method: "POST" });
          const m = state.measures.find((x) => x.id === s.dataset.fav);
          m.favorite = res.favorite;
          draw();
        }));
    }

    body.querySelectorAll("[data-cat]").forEach((btn) =>
      btn.addEventListener("click", () => {
        filter = btn.dataset.cat;
        body.querySelectorAll("[data-cat]").forEach((b) =>
          b.setAttribute("aria-pressed", String(b === btn)));
        search.value = "";
        draw();
      }));
    search.addEventListener("input", draw);
    draw();
  });
}

function zekBlock() {
  const byCat = {};
  state.complications.forEach((c) => {
    (byCat[c.category] = byCat[c.category] || []).push(c);
  });
  return `
    <details class="card flat" data-s="pad-sm">
      <summary class="small muted" data-s="pointer">ZEK zuordnen (optional)</summary>
      <div data-s="mt-md">
        ${Object.entries(byCat).map(([cat, items]) => `
          <div data-s="mb-md">
            <div class="tiny muted" data-s="mb-xs">${esc(cat)}</div>
            <div class="chipset">
              ${items.map((c) => `<button type="button" class="chip accent"
                data-zek="${esc(c.id)}" aria-pressed="false"
                title="${esc(c.label)}">${esc(c.code)} ${esc(c.label)}</button>`).join("")}
            </div>
          </div>`).join("")}
      </div>
      <div id="zek-detail" class="stack"></div>
    </details>`;
}

/* Bezug und Schadenseinschätzung erscheinen erst, wenn eine ZEK gewählt ist.
   Solange keine gesetzt ist, kostet die Erweiterung beim Erfassen nichts.
   Gibt einen Sammler zurück, statt den Zustand global zu halten. */
function bindZek(body, withRelation) {
  const chosen = new Map();
  const detail = $("#zek-detail", body);

  function drawDetail() {
    if (!chosen.size) { detail.innerHTML = ""; return; }
    detail.innerHTML = `<div class="tiny muted" data-s="my-sm">
      Bezug zum Ausgang und Einschätzung eines Patientenschadens</div>` +
      Array.from(chosen.entries()).map(([id, v]) => {
        const c = state.complications.find((x) => x.id === id);
        if (!c) return "";
        return `<div class="card flat" data-s="pad-xs">
          <div class="small"><strong>${esc(c.code)}</strong> ${esc(c.label)}</div>
          ${withRelation ? `<div class="chipset" data-s="mt-sm">
            ${state.constants.zek_relations.map((r) => `
              <button type="button" class="chip" data-rel="${esc(id)}"
                data-val="${esc(r.key)}" aria-pressed="${v.relation === r.key}"
                title="${esc(r.hint)}">${esc(r.key)}</button>`).join("")}
          </div>` : ""}
          <div class="chipset" data-s="mt-xs">
            ${state.constants.patient_harm.map((h) => `
              <button type="button" class="chip" data-harm="${esc(id)}"
                data-val="${esc(h)}" aria-pressed="${v.patient_harm === h}">${
                  esc(h === "kein Schaden erkennbar" ? "kein Schaden" : h)}</button>`).join("")}
          </div>
        </div>`;
      }).join("");

    detail.querySelectorAll("[data-rel]").forEach((b) =>
      b.addEventListener("click", () => {
        chosen.get(b.dataset.rel).relation = b.dataset.val;
        drawDetail();
      }));
    detail.querySelectorAll("[data-harm]").forEach((b) =>
      b.addEventListener("click", () => {
        chosen.get(b.dataset.harm).patient_harm = b.dataset.val;
        drawDetail();
      }));
  }

  body.querySelectorAll("[data-zek]").forEach((b) =>
    b.addEventListener("click", () => {
      const on = b.getAttribute("aria-pressed") === "true";
      b.setAttribute("aria-pressed", on ? "false" : "true");
      if (on) chosen.delete(b.dataset.zek);
      else chosen.set(b.dataset.zek,
        { relation: "begleitend", patient_harm: "kein Schaden erkennbar" });
      drawDetail();
    }));

  return {
    collect: () => Array.from(chosen.entries()).map(([id, v]) => ({ id, ...v })),
  };
}

function zekSummary(list) {
  return (list || []).map((c) => {
    const bits = [];
    if (c.relation === "ursächlich") bits.push("ursächlich");
    if (c.patient_harm === "vermutet") bits.push("Schaden vermutet");
    if (c.patient_harm === "gesichert") bits.push("Schaden gesichert");
    return `${esc(c.code)} ${esc(c.label)}${
      bits.length ? " (" + esc(bits.join(", ")) + ")" : ""}`;
  }).join(", ");
}

function attemptForm(enc, measure) {
  const params = (measure.parameters || []).map((p) => {
    const id = "p_" + p.key;
    if (p.type === "select") {
      return `<div class="field"><label for="${id}">${esc(p.label)}</label>
        <select id="${id}" data-param="${esc(p.key)}">
          <option value="">ohne Angabe</option>
          ${(p.options || []).map((o) => `<option>${esc(o)}</option>`).join("")}
        </select></div>`;
    }
    const type = (p.type === "number" || p.type === "int") ? "number" : "text";
    const step = p.type === "int" ? "1" : "any";
    return `<div class="field"><label for="${id}">${esc(p.label)}${
      p.unit ? ` <span class="muted">(${esc(p.unit)})</span>` : ""}</label>
      <input id="${id}" type="${type}" step="${step}" data-param="${esc(p.key)}"
        inputmode="${type === "number" ? "decimal" : "text"}"></div>`;
  }).join("");

  const outcomes = state.constants.outcomes.map((o, i) =>
    `<button type="button" class="chip out-${STATUS_CLASS[o] || "neutral"}"
      data-outcome="${esc(o)}" aria-pressed="${i === 0}">${esc(o)}</button>`).join("");
  const delegations = state.constants.delegations.map((d) =>
    `<button type="button" class="chip" data-deleg="${esc(d)}"
      aria-pressed="false">${esc(d)}</button>`).join("");
  const roles = state.constants.performer_roles.map((r, i) =>
    `<button type="button" class="chip" data-role="${esc(r.key)}"
      aria-pressed="${i === 0}" title="${esc(r.hint)}">${esc(r.key)}</button>`).join("");

  sheet(measure.name, `
    <form id="att-form" class="stack">
      <div class="field"><label>Ergebnis</label>
        <div class="chipset" id="outcome-set">${outcomes}</div></div>
      <div class="field"><label>Rolle bei der Durchführung</label>
        <div class="chipset" id="role-set">${roles}</div>
        <div id="role-extra" data-s="mt-sm"></div></div>
      ${showDelegation() ? `<div class="field"><label>Durchführungsart</label>
        <div class="chipset" id="deleg-set">${delegations}</div></div>` : ""}
      ${params ? `<div data-s="mt-sm">${params}</div>` : ""}
      ${zekBlock()}
      <div class="field"><label for="att-note">Notiz (optional, keine Patientendaten)</label>
        <textarea id="att-note" maxlength="500"></textarea></div>
      <div class="sheet-actions two">
        <button class="btn-primary btn-lg" type="submit" data-next="more">Speichern und weitere Maßnahme</button>
        <button class="btn-lg" type="submit" data-next="close">Speichern</button>
      </div>
      <button class="btn-quiet" type="submit" data-next="med">Speichern und Medikament hinzufügen</button>
    </form>`, (body) => {
    let outcome = state.constants.outcomes[0];
    let delegation = null;
    let performerRole = state.constants.performer_roles[0].key;

    /* Bei angeleiteten oder assistierten Maßnahmen ist für den Nachweis
       relevant, wen man angeleitet hat. Das Feld erscheint deshalb nur
       dann und bleibt sonst aus dem Weg. */
    const roleExtra = $("#role-extra", body);
    function drawRoleExtra() {
      if (performerRole === "selbst durchgeführt") { roleExtra.innerHTML = ""; return; }
      const label = performerRole === "angeleitet"
        ? "Qualifikation der angeleiteten Person (optional)"
        : "Qualifikation der durchführenden Person (optional)";
      roleExtra.innerHTML = `<label for="pq">${esc(label)}</label>
        <input id="pq" maxlength="80" autocomplete="off">`;
    }
    body.querySelectorAll("[data-role]").forEach((b) =>
      b.addEventListener("click", () => {
        body.querySelectorAll("[data-role]").forEach((x) =>
          x.setAttribute("aria-pressed", "false"));
        b.setAttribute("aria-pressed", "true");
        performerRole = b.dataset.role;
        drawRoleExtra();
      }));
    body.querySelectorAll("[data-outcome]").forEach((b) =>
      b.addEventListener("click", () => {
        body.querySelectorAll("[data-outcome]").forEach((x) =>
          x.setAttribute("aria-pressed", "false"));
        b.setAttribute("aria-pressed", "true");
        outcome = b.dataset.outcome;
      }));
    body.querySelectorAll("[data-deleg]").forEach((b) =>
      b.addEventListener("click", () => {
        const on = b.getAttribute("aria-pressed") === "true";
        body.querySelectorAll("[data-deleg]").forEach((x) =>
          x.setAttribute("aria-pressed", "false"));
        b.setAttribute("aria-pressed", on ? "false" : "true");
        delegation = on ? null : b.dataset.deleg;
      }));
    const zek = bindZek(body, true);

    let nextAction = "close";
    body.querySelectorAll("[data-next]").forEach((b) =>
      b.addEventListener("click", () => { nextAction = b.dataset.next; }));

    $("#att-form", body).addEventListener("submit", async (e) => {
      e.preventDefault();
      const parameters = {};
      body.querySelectorAll("[data-param]").forEach((f) => {
        if (f.value !== "") parameters[f.dataset.param] = f.value;
      });
      try {
        await api(`/api/encounters/${enc.id}/attempts`, {
          method: "POST",
          body: {
            measure_id: measure.id, outcome, delegation, parameters,
            performer_role: performerRole,
            performer_qualification: (($("#pq", body) || {}).value || null),
            note: $("#att-note", body).value || null,
            complications: zek.collect(),
          },
        });
        closeSheet();
        toast("Maßnahme gespeichert.");
        await render();
        if (nextAction === "more") measurePicker(enc);
        if (nextAction === "med") medicationPicker(enc);
      } catch (err) { toast(err.message); }
    });
  });
}

// --------------------------------------------------------- Medikamentenwahl

function medicationPicker(enc) {
  sheet("Medikament wählen", `
    <div class="field"><input id="med-search" type="text" placeholder="Wirkstoff suchen"
      autocomplete="off" aria-label="Wirkstoff suchen"></div>
    <div class="pick-list" data-s="mt-md" id="med-list"></div>`, (body) => {
    const search = $("#med-search", body);
    const list = $("#med-list", body);
    function draw() {
      const term = search.value.trim().toLowerCase();
      let items = term
        ? state.medications.filter((m) => m.name.toLowerCase().includes(term))
        : (state.recentMedications
            .map((id) => state.medications.find((m) => m.id === id))
            .filter(Boolean).concat(state.medications).slice(0, 400));
      const seen = new Set();
      items = items.filter((m) => !seen.has(m.id) && seen.add(m.id));
      list.innerHTML = items.map((m) => `
        <button class="pick" data-med="${esc(m.id)}">
          <span class="grow" data-s="text-left">${esc(m.name)}</span>
        </button>`).join("") ||
        `<div class="empty small">Kein Treffer. Neue Wirkstoffe legst du unter
          Profil und Einstellungen an.</div>`;
      list.querySelectorAll("[data-med]").forEach((b) =>
        b.addEventListener("click", () => {
          medicationForm(enc, state.medications.find((m) => m.id === b.dataset.med));
        }));
    }
    search.addEventListener("input", draw);
    draw();
  });
}

function medicationForm(enc, med) {
  const units = state.constants.units.map((u) => `<option>${esc(u)}</option>`).join("");
  const routes = state.constants.routes.map((r) => `<option>${esc(r)}</option>`).join("");
  const preps = (med.preparations || []).map((p) =>
    `<option value="${esc(p.id)}">${esc(p.name)}${p.strength ? " " + esc(p.strength) : ""}</option>`).join("");
  const delegations = state.constants.delegations.map((d) =>
    `<button type="button" class="chip" data-deleg="${esc(d)}" aria-pressed="false">${esc(d)}</button>`).join("");

  sheet(med.name, `
    <form id="med-form" class="stack">
      ${preps ? `<div class="field"><label for="mp">Präparat (optional)</label>
        <select id="mp"><option value="">ohne Angabe</option>${preps}</select></div>` : ""}
      <div class="field-row">
        <div class="field"><label for="md">Dosis</label>
          <input id="md" type="number" step="any" inputmode="decimal"></div>
        <div class="field"><label for="mu">Einheit</label>
          <select id="mu"><option value="">ohne Angabe</option>${units}</select></div>
      </div>
      <div class="field"><label for="mr">Applikationsweg</label>
        <select id="mr"><option value="">ohne Angabe</option>${routes}</select></div>
      ${showDelegation() ? `<div class="field"><label>Durchführungsart</label>
        <div class="chipset">${delegations}</div></div>` : ""}
      ${zekBlock()}
      <div class="field"><label for="mn">Notiz (optional, keine Patientendaten)</label>
        <textarea id="mn" maxlength="500"></textarea></div>
      <div class="sheet-actions two">
        <button class="btn-primary btn-lg" type="submit" data-next="more">Speichern und weiteres Medikament</button>
        <button class="btn-lg" type="submit" data-next="close">Speichern</button>
      </div>
    </form>`, (body) => {
    let delegation = null;
    body.querySelectorAll("[data-deleg]").forEach((b) =>
      b.addEventListener("click", () => {
        const on = b.getAttribute("aria-pressed") === "true";
        body.querySelectorAll("[data-deleg]").forEach((x) =>
          x.setAttribute("aria-pressed", "false"));
        b.setAttribute("aria-pressed", on ? "false" : "true");
        delegation = on ? null : b.dataset.deleg;
      }));
    const zek = bindZek(body, false);
    let nextAction = "close";
    body.querySelectorAll("[data-next]").forEach((b) =>
      b.addEventListener("click", () => { nextAction = b.dataset.next; }));

    $("#med-form", body).addEventListener("submit", async (e) => {
      e.preventDefault();
      const prep = $("#mp", body);
      const dose = $("#md", body).value;
      try {
        await api(`/api/encounters/${enc.id}/medications`, {
          method: "POST",
          body: {
            medication_id: med.id,
            preparation_id: prep && prep.value ? prep.value : null,
            dose: dose === "" ? null : Number(dose),
            unit: $("#mu", body).value || null,
            route: $("#mr", body).value || null,
            delegation,
            note: $("#mn", body).value || null,
            complications: zek.collect(),
          },
        });
        closeSheet();
        toast("Medikamentengabe gespeichert.");
        await render();
        if (nextAction === "more") medicationPicker(enc);
      } catch (err) { toast(err.message); }
    });
  });
}

// --------------------------------------------------------------- Dashboard

const PERIODS = [
  ["7d", "7 Tage"], ["month", "Monat"], ["quarter", "Quartal"],
  ["year", "Jahr"], ["all", "Gesamt"], ["custom", "Zeitraum"],
];

function filterQuery(extra = {}) {
  const f = { ...state.filters, ...extra };
  const p = new URLSearchParams();
  if (f.period && f.period !== "custom") p.set("period", f.period);
  if (f.period === "custom") {
    if (f.date_from) p.set("date_from", f.date_from);
    if (f.date_to) p.set("date_to", f.date_to);
  }
  ["naca", "category", "outcome", "delegation", "route", "harm"].forEach((key) => {
    (f[key] || []).forEach((v) => p.append(key, v));
  });
  return p.toString();
}

function toggleFilter(key, value) {
  const cur = state.filters[key] || [];
  state.filters[key] = cur.includes(value)
    ? cur.filter((v) => v !== value) : cur.concat(value);
}

function barList(items, nameKey, max, variant = "") {
  if (!items.length) return `<p class="small muted">Keine Daten im Zeitraum.</p>`;
  return `<div class="bars">${items.map((r) => `
    <div class="bar-row">
      <span class="name">${esc(r[nameKey])}</span>
      <span class="n">${r.n}</span>
      <span class="bar-track"><span class="bar-fill ${variant}" data-fill="${
        max ? Math.round(100 * r.n / max) : 0}"></span></span>
    </div>`).join("")}</div>`;
}

async function viewDashboard() {
  const s = await api("/api/stats?" + filterQuery());
  const f = state.filters;
  const maxMeasure = Math.max(1, ...s.by_measure.map((r) => r.n));
  const maxCat = Math.max(1, ...s.by_category.map((r) => r.n));
  const maxMed = Math.max(1, ...s.by_medication.map((r) => r.n));
  const maxRoute = Math.max(1, ...s.by_route.map((r) => r.n));
  const maxTl = Math.max(1, ...s.timeline.map((r) => r.n));
  const harm = s.patient_harm || {};
  const harmRows = Object.entries(harm)
    .filter(([, v]) => v.attempts || v.medications)
    .map(([level, v]) => `<tr><td>${esc(level)}</td>
      <td class="num">${v.attempts}</td><td class="num">${v.medications}</td></tr>`)
    .join("");

  app().innerHTML = `
    <div class="page-head"><h1>Dashboard</h1>
      <p class="muted small">Alle Kennzahlen aus den lokal gespeicherten Daten</p></div>

    <div class="chipset">${PERIODS.map(([k, label]) =>
      `<button class="chip accent" data-period="${k}"
        aria-pressed="${f.period === k}">${esc(label)}</button>`).join("")}</div>

    <div class="field-row ${f.period === "custom" ? "" : "hidden"}" data-s="mt-md" id="custom-range">
      <div class="field"><label for="df">Von</label>
        <input id="df" type="date" value="${esc(f.date_from || "")}"></div>
      <div class="field"><label for="dt">Bis</label>
        <input id="dt" type="date" value="${esc(f.date_to || "")}"></div>
    </div>

    <details class="card flat" data-s="mt-md pad-sm">
      <summary class="small muted" data-s="pointer">Filter</summary>
      <div data-s="mt-md" class="stack">
        <div><div class="tiny muted">NACA</div>
          <div class="chipset">${state.constants.naca.map((n) =>
            `<button class="chip" data-f="naca" data-v="${esc(n)}"
              aria-pressed="${(f.naca || []).includes(n)}">${esc(n)}</button>`).join("")}</div></div>
        <div><div class="tiny muted">Kategorie</div>
          <div class="chipset">${state.constants.categories.map((c) =>
            `<button class="chip" data-f="category" data-v="${esc(c.key)}"
              aria-pressed="${(f.category || []).includes(c.key)}"
              title="${esc(c.label)}">${esc(c.key)}</button>`).join("")}</div></div>
        <div><div class="tiny muted">Ergebnis</div>
          <div class="chipset">${state.constants.outcomes.map((o) =>
            `<button class="chip" data-f="outcome" data-v="${esc(o)}"
              aria-pressed="${(f.outcome || []).includes(o)}">${esc(o)}</button>`).join("")}</div></div>
        <div><div class="tiny muted">Durchführungsart</div>
          <div class="chipset">${state.constants.delegations.map((d) =>
            `<button class="chip" data-f="delegation" data-v="${esc(d)}"
              aria-pressed="${(f.delegation || []).includes(d)}">${esc(d)}</button>`).join("")}</div></div>
        <div><div class="tiny muted">Patientenschaden</div>
          <div class="chipset">${["vermutet", "gesichert"].map((h) =>
            `<button class="chip" data-f="harm" data-v="${esc(h)}"
              aria-pressed="${(f.harm || []).includes(h)}">${esc(h)}</button>`).join("")}</div></div>
        <button class="btn-quiet small" id="clear-filters">Filter zurücksetzen</button>
      </div>
    </details>

    <div class="tiles" data-s="mt-lg">
      <div class="tile"><div class="value">${s.encounters}</div><div class="label">Einsätze</div></div>
      <div class="tile"><div class="value">${s.attempts}</div><div class="label">Maßnahmen</div></div>
      <div class="tile"><div class="value">${s.administrations}</div><div class="label">Medikamentengaben</div></div>
      <div class="tile"><div class="value">${s.success_rate === null ? "–" : s.success_rate + " %"}</div>
        <div class="label">Erfolgsquote</div></div>
      <div class="tile"><div class="value">${s.complications.total}</div><div class="label">ZEK</div></div>
      <div class="tile"><div class="value">${s.complications.rate === null ? "–" : s.complications.rate + " %"}</div>
        <div class="label">ZEK-Rate</div></div>
    </div>

    <div class="card" data-s="mt-lg">
      <h2>Ergebnisse</h2>
      <table class="data" data-s="mt-sm">
        <tr><td>${statusBadge("erfolgreich")}</td><td class="num">${s.outcomes.erfolgreich}</td>
          <td class="num">${s.success_rate === null ? "–" : s.success_rate + " %"}</td></tr>
        <tr><td>${statusBadge("fehlgeschlagen")}</td><td class="num">${s.outcomes.fehlgeschlagen}</td>
          <td class="num">${s.failure_rate === null ? "–" : s.failure_rate + " %"}</td></tr>
        <tr><td>${statusBadge("abgebrochen")}</td><td class="num">${s.outcomes.abgebrochen || 0}</td>
          <td class="num">${s.abort_rate === null ? "–" : s.abort_rate + " %"}</td></tr>
      </table>
      <p class="tiny muted" data-s="mt-sm">Bezugsgröße ist jeweils die
      Gesamtzahl dokumentierter Maßnahmen im Zeitraum.</p>
    </div>

    <div class="card" data-s="mt-md">
      <h2>Ergebnis im Zusammenhang mit Komplikationen</h2>
      <table class="data" data-s="mt-sm">
        ${s.derived.map((r) => `<tr><td>${esc(r.label)}</td>
          <td class="num">${r.n}</td><td class="num">${r.share} %</td></tr>`).join("")}
      </table>
      <p class="tiny muted" data-s="mt-sm">Berechnet aus Ergebnis und
      dokumentiertem Bezug der zugeordneten ZEK. Die Kategorien werden nicht
      gespeichert und können sich deshalb nicht widersprechen.</p>
    </div>

    ${harmRows ? `<div class="card" data-s="mt-md">
      <h2>Einschätzung eines Patientenschadens</h2>
      <table class="data" data-s="mt-sm">
        <tr><th>Einschätzung</th><th class="num">Maßnahmen</th>
          <th class="num">Medikamentengaben</th></tr>
        ${harmRows}
      </table>
    </div>` : ""}

    <div class="card" data-s="mt-md">
      <h2>Maßnahmen nach xABCDE</h2>
      <div data-s="mt-md">${barList(
        s.by_category.map((r) => ({ ...r, label: `${r.key} · ${r.label}` })), "label", maxCat)}</div>
    </div>

    <div class="card" data-s="mt-md">
      <h2>Häufigkeit einzelner Maßnahmen</h2>
      <div data-s="mt-md">${barList(s.by_measure, "name", maxMeasure)}</div>
    </div>

    <div class="card" data-s="mt-md">
      <h2>Entwicklung über die Zeit</h2>
      <div data-s="mt-md">${barList(
        s.timeline.map((r) => ({ ...r, bucket: r.bucket })), "bucket", maxTl)}</div>
    </div>

    <div class="card" data-s="mt-md">
      <h2>Medikamentengaben nach Wirkstoff</h2>
      <div data-s="mt-md">${barList(s.by_medication, "name", maxMed, "alt")}</div>
    </div>

    <div class="card" data-s="mt-md">
      <h2>Applikationswege</h2>
      <div data-s="mt-md">${barList(s.by_route, "name", maxRoute, "alt")}</div>
    </div>

    <div class="card" data-s="mt-md">
      <h2>Häufigste ZEK</h2>
      <div data-s="mt-md">${s.complications.top.length
        ? `<table class="data">
            ${s.complications.top.map((r) => `<tr><td data-s="col-code">${esc(r.code)}</td>
              <td>${esc(r.label)}</td><td class="num">${r.n}</td></tr>`).join("")}
          </table>`
        : `<p class="small muted">Keine ZEK im Zeitraum dokumentiert.</p>`}</div>
    </div>

    <div class="card" data-s="mt-md">
      <h2>NACA-Verteilung</h2>
      ${s.naca.length ? `<table class="data" data-s="mt-sm">
        <tr><th>NACA</th><th class="num">Eins.</th><th class="num">Anteil</th>
          <th class="num">Maßn.</th><th class="num">Med.</th><th class="num">ZEK</th></tr>
        ${s.naca.map((r) => `<tr><td>${esc(r.naca)}</td>
          <td class="num">${r.encounters}</td><td class="num">${r.share} %</td>
          <td class="num">${r.attempts}</td><td class="num">${r.medications}</td>
          <td class="num">${r.complications}</td></tr>`).join("")}
      </table>` : `<p class="small muted">Keine Einsätze im Zeitraum.</p>`}
      <p class="tiny muted" data-s="mt-md">Die Verteilung beschreibt die
      Dokumentation. Aus ihr wird keine medizinische Bewertung abgeleitet.</p>
    </div>`;

  setBars(app());

  app().querySelectorAll("[data-period]").forEach((b) =>
    b.addEventListener("click", () => {
      state.filters.period = b.dataset.period;
      render();
    }));
  app().querySelectorAll("[data-f]").forEach((b) =>
    b.addEventListener("click", () => {
      toggleFilter(b.dataset.f, b.dataset.v);
      render();
    }));
  const clear = $("#clear-filters");
  if (clear) clear.addEventListener("click", () => {
    state.filters = { period: state.filters.period };
    render();
  });
  ["#df", "#dt"].forEach((sel) => {
    const el = $(sel);
    if (!el) return;
    el.addEventListener("change", () => {
      state.filters.date_from = $("#df").value;
      state.filters.date_to = $("#dt").value;
      render();
    });
  });
}

// -------------------------------------------------------------- Nachweise

async function viewProofs() {
  app().innerHTML = `
    <div class="page-head"><h1>Nachweise</h1>
      <p class="muted small">Persönlicher Tätigkeits- und Kompetenznachweis als PDF</p></div>

    <div class="card pad-lg stack">
      <div class="field"><label>Zeitraum</label>
        <div class="chipset" id="proof-periods">${PERIODS.map(([k, label]) =>
          `<button class="chip accent" data-p="${k}"
            aria-pressed="${k === "year"}">${esc(label)}</button>`).join("")}</div></div>

      <div class="field-row hidden" id="proof-range">
        <div class="field"><label for="pf">Von</label><input id="pf" type="date"></div>
        <div class="field"><label for="pt">Bis</label><input id="pt" type="date"></div>
      </div>

      <div class="row" data-s="gap-md align-start">
        <input id="detailed" type="checkbox" data-s="checkbox">
        <label for="detailed" data-s="m-0">Detaillierten Nachweis anhängen
          <span class="muted">– listet jeden Eintrag mit Datum, NACA, Ergebnis,
          Parametern und ZEK</span></label>
      </div>

      <button class="btn-primary btn-lg" id="make-pdf">PDF erstellen</button>
    </div>

    <div class="card" data-s="mt-md">
      <h2>Rohdaten exportieren</h2>
      <p class="small muted">Für eigene Auswertungen. Der gewählte Zeitraum gilt auch hier.</p>
      <div class="sheet-actions two">
        <button id="csv-att">Maßnahmen als CSV</button>
        <button id="csv-med">Medikamente als CSV</button>
      </div>
    </div>

    <p class="tiny muted" data-s="mt-lg">Der Nachweis enthält ausschließlich
    Angaben, die dokumentiert wurden. Fehlende Werte bleiben leer und werden nicht ergänzt.</p>`;

  let period = "year";
  const range = $("#proof-range");
  app().querySelectorAll("[data-p]").forEach((b) =>
    b.addEventListener("click", () => {
      period = b.dataset.p;
      app().querySelectorAll("[data-p]").forEach((x) =>
        x.setAttribute("aria-pressed", String(x === b)));
      range.classList.toggle("hidden", period !== "custom");
    }));

  function query(extra = "") {
    const p = new URLSearchParams();
    if (period !== "custom") p.set("period", period);
    else {
      if ($("#pf").value) p.set("date_from", $("#pf").value);
      if ($("#pt").value) p.set("date_to", $("#pt").value);
    }
    return p.toString() + extra;
  }

  $("#make-pdf").addEventListener("click", () => {
    const detailed = $("#detailed").checked ? "&detailed=true" : "";
    location.href = "/api/exports/pdf?" + query(detailed);
  });
  $("#csv-att").addEventListener("click", () => {
    location.href = "/api/exports/csv?kind=attempts&" + query();
  });
  $("#csv-med").addEventListener("click", () => {
    location.href = "/api/exports/csv?kind=medications&" + query();
  });
}

// ------------------------------------------------------------------ Profil

async function viewProfile() {
  const [p, settings, recovery] = await Promise.all([
    api("/api/profile"), api("/api/settings"), api("/api/auth/recovery/status"),
  ]);
  const prof = p.profile || {};

  app().innerHTML = `
    <div class="page-head"><h1>Profil &amp; Einstellungen</h1></div>

    <div class="card pad-lg">
      <h2>Anmeldedaten</h2>
      <p class="small muted" data-s="mt-xs">Mit einer dieser beiden Angaben
      meldest du dich an.</p>
      <table class="data" data-s="mt-md">
        <tr><td class="muted">Benutzername</td>
          <td><strong>${esc(p.username)}</strong></td></tr>
        <tr><td class="muted">E-Mail-Adresse</td>
          <td>${p.email ? `<strong>${esc(p.email)}</strong>`
            : `<span class="muted">nicht hinterlegt</span>`}</td></tr>
      </table>
      <div class="sheet-actions two">
        <button id="change-email">E-Mail-Adresse ändern</button>
        <button id="copy-login">Benutzername kopieren</button>
      </div>
      <p class="tiny muted" data-s="mt-md">Der Benutzername lässt sich derzeit
      nicht ändern, weil daran Sitzungen und das Änderungsprotokoll hängen.</p>
    </div>

    <div class="card pad-lg" data-s="mt-md">
      <h2>Profil</h2>
      <form id="prof-form" class="stack" data-s="mt-md">
        <div class="field-row">
          <div class="field"><label for="pfn">Vorname</label>
            <input id="pfn" name="first_name" value="${esc(prof.first_name || "")}"></div>
          <div class="field"><label for="pln">Nachname</label>
            <input id="pln" name="last_name" value="${esc(prof.last_name || "")}"></div>
        </div>
        <div class="field"><label for="pq">Qualifikation</label>
          <select id="pq" name="qualification">
            ${p.qualifications.map((q) => `<option ${
              q === prof.qualification ? "selected" : ""}>${esc(q)}</option>`).join("")}
          </select></div>
        <div class="field" id="specialty-field">
          <label for="psp">Facharztbezeichnung (optional)</label>
          <input id="psp" name="specialty" maxlength="120"
            value="${esc(prof.specialty || "")}"
            placeholder="z. B. Anästhesiologie"></div>
        <div class="field"><label for="pr">Funktion (optional)</label>
          <input id="pr" name="role" value="${esc(prof.role || "")}"></div>
        <div class="field"><label for="pi">Personal- oder Registrierungskennung (optional)</label>
          <input id="pi" name="registration_id" value="${esc(prof.registration_id || "")}"></div>
        <button class="btn-primary" type="submit">Profil speichern</button>
      </form>
    </div>

    <div class="card pad-lg" data-s="mt-md">
      <h2>Erfassung</h2>
      <form id="set-form" class="stack" data-s="mt-md">
        <div class="field"><label for="sw">Bearbeitungsfrist in Minuten</label>
          <input id="sw" type="number" min="1" max="10080"
            value="${settings.edit_window_minutes}">
          <p class="tiny muted" data-s="mt-xs">Nach Ablauf wird ein Eintrag
          automatisch gesperrt. Er bleibt lesbar, lässt sich aber nicht mehr
          ändern. Zulässig sind 1 Minute bis 10080 Minuten, also sieben Tage.
          Übliche Werte: 120 für zwei Stunden, 1440 für einen Tag,
          10080 für eine Woche.</p>
          <div id="window-warning" class="window-warning"></div></div>
        <div class="field"><label for="st">Darstellung</label>
          <select id="st">
            <option value="auto" ${settings.theme === "auto" ? "selected" : ""}>Systemeinstellung folgen</option>
            <option value="light" ${settings.theme === "light" ? "selected" : ""}>Hell</option>
            <option value="dark" ${settings.theme === "dark" ? "selected" : ""}>Dunkel</option>
          </select></div>
        <div class="field"><label for="sd">Feld „Durchführungsart"</label>
          <select id="sd">
            <option value="auto" ${settings.show_delegation === "auto" ? "selected" : ""}>Automatisch nach Qualifikation</option>
            <option value="always" ${settings.show_delegation === "always" ? "selected" : ""}>Immer anzeigen</option>
            <option value="never" ${settings.show_delegation === "never" ? "selected" : ""}>Nie anzeigen</option>
          </select></div>
        <button class="btn-primary" type="submit">Einstellungen speichern</button>
      </form>
    </div>

    <div class="card pad-lg" data-s="mt-md">
      <h2>Sicherheit</h2>
      <p class="small muted" data-s="mt-sm">Zwei-Faktor-Authentifizierung ist
      aktiv. Von ${recovery.total} Wiederherstellungscodes sind ${recovery.unused} unbenutzt.</p>
      <div class="sheet-actions two">
        <button id="new-codes">Neue Wiederherstellungscodes</button>
        <button id="change-pw">Passwort ändern</button>
      </div>
    </div>

    <div class="card pad-lg" data-s="mt-md">
      <h2>Stammdaten</h2>
      <p class="small muted" data-s="mt-sm">Änderungen wirken nur auf neue
      Einträge. Bereits dokumentierte Maßnahmen und Medikamente behalten ihre
      ursprüngliche Bezeichnung.</p>
      <div class="sheet-actions two">
        <button id="edit-measures">Maßnahmenkatalog</button>
        <button id="edit-meds">Medikamente</button>
      </div>
    </div>

    <div class="card pad-lg" data-s="mt-md">
      <h2>Backup</h2>
      <p class="small muted" data-s="mt-sm">Die Sicherung enthält Stammdaten,
      Profil, Einsätze, Maßnahmen, Medikamentengaben, ZEK-Verknüpfungen, Einstellungen
      und das Änderungsprotokoll. Zugangsdaten und das TOTP-Geheimnis sind
      bewusst nicht enthalten.</p>
      <div class="sheet-actions two">
        <button id="backup">Sicherung herunterladen</button>
        <button class="btn-danger" id="restore">Sicherung einspielen</button>
      </div>
    </div>

    <div class="card pad-lg" data-s="mt-md">
      <h2>Änderungsprotokoll</h2>
      <div id="audit" class="small muted" data-s="mt-sm">Wird geladen …</div>
    </div>

    <div class="card pad-lg" data-s="mt-md">
      <h2>Rechtliche Angaben</h2>
      <p class="small muted" data-s="mt-xs">Diese Angaben erscheinen auf der
      Seite Impressum und Datenschutz, die auch ohne Anmeldung erreichbar ist.
      Die E-Mail-Adresse ist nach § 5 Abs. 1 DDG Pflichtangabe.</p>
      <form id="legal-form" class="stack" data-s="mt-md">
        <div class="field"><label for="ln">Name</label><input id="ln"></div>
        <div class="field"><label for="la">Anschrift</label><input id="la"></div>
        <div class="field"><label for="le">E-Mail-Adresse</label>
          <input id="le" type="email" autocomplete="email"></div>
        <button class="btn-primary" type="submit">Angaben speichern</button>
      </form>
      <a href="#/rechtliches" class="small" data-s="mt-md link-plain">Seite ansehen</a>
    </div>

    <div class="card pad-lg" data-s="mt-md">
      <h2>Vertraute Geräte</h2>
      <p class="small muted" data-s="mt-xs">Auf diesen Geräten entfällt der
      Code bei der Anmeldung. Sicherheitsrelevante Aktionen verlangen ihn
      trotzdem.</p>
      <div id="devices" class="small muted" data-s="mt-md">Wird geladen …</div>
      <button class="btn-danger" id="revoke-devices" data-s="mt-md">Allen Geräten das Vertrauen entziehen</button>
    </div>

    <div id="admin-area"></div>

    <button class="btn-quiet btn-lg" id="logout" data-s="mt-lg">Abmelden</button>

    <p class="tiny muted" data-s="mt-lg">SCOPE X dokumentiert, was tatsächlich
    durchgeführt wurde. Die Anwendung schlägt keine Indikationen vor, empfiehlt keine
    Dosierungen und ersetzt keine SOP.</p>`;

  $("#copy-login").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(p.username);
      toast("Benutzername kopiert.");
    } catch (_) { toast(`Dein Benutzername lautet: ${p.username}`); }
  });

  $("#change-email").addEventListener("click", () => sheet("E-Mail-Adresse ändern", `
    <p class="small muted">Die Adresse ist ein Anmeldemerkmal. Deshalb sind
    Passwort und ein aktueller Code nötig. Leer lassen entfernt die Adresse,
    dann bleibt nur der Benutzername als Anmeldung.</p>
    <form id="em-form" class="stack" data-s="mt-md">
      <div class="field"><label for="em">Neue E-Mail-Adresse</label>
        <input id="em" type="email" autocomplete="email" autocapitalize="none"
          value="${esc(p.email || "")}"></div>
      <div class="field"><label for="emp">Passwort</label>
        <input id="emp" type="password" autocomplete="current-password" required></div>
      <div class="field"><label for="emc">Code aus der Authenticator-App</label>
        <input id="emc" inputmode="numeric" maxlength="6" pattern="[0-9]*" required></div>
      <button class="btn-primary btn-lg" type="submit">Adresse speichern</button>
      <p class="tiny muted" id="em-err"></p>
    </form>`, (body) => {
    $("#em-form", body).addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await api("/api/auth/email", { method: "PUT", body: {
          email: $("#em", body).value,
          password: $("#emp", body).value,
          totp_code: $("#emc", body).value } });
        closeSheet();
        toast("E-Mail-Adresse gespeichert.");
        render();
      } catch (err) { $("#em-err", body).textContent = err.message; }
    });
  }));

  $("#prof-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    await api("/api/profile", { method: "PUT", body: fd });
    state.auth = await api("/api/auth/state");
    toast("Profil gespeichert.");
  });

  /* Eine lange Frist ist am Anfang praktisch, kostet den Nachweis aber
     Aussagekraft. Die Warnung erscheint deshalb sofort beim Tippen und
     nicht erst nach dem Speichern. */
  const windowInput = $("#sw");
  const windowWarn = $("#window-warning");
  function checkWindow() {
    const v = Number(windowInput.value);
    if (!v || v <= 240) { windowWarn.innerHTML = ""; return; }
    const label = v >= 1440
      ? `${(v / 1440).toFixed(1).replace(".0", "").replace(".", ",")} Tage`
      : `${Math.round(v / 60)} Stunden`;
    windowWarn.innerHTML = `<div class="notice warn tiny">
      <strong>Frist von ${esc(label)}.</strong> So lange bleibt jeder Eintrag
      rückwirkend änderbar. Für einen Tätigkeitsnachweis schwächt das die
      Aussagekraft, weil nachträgliche Korrekturen dann die Regel und nicht
      die Ausnahme sind. Die eingestellte Frist wird im PDF ausgewiesen,
      damit der Leser sie einordnen kann.</div>`;
  }
  windowInput.addEventListener("input", checkWindow);
  checkWindow();

  $("#set-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const updated = await api("/api/settings", {
      method: "PUT",
      body: {
        edit_window_minutes: Number(windowInput.value),
        theme: $("#st").value,
        show_delegation: $("#sd").value,
      },
    });
    state.settings = updated;
    applyTheme(updated.theme);
    checkWindow();
    toast("Einstellungen gespeichert.");
  });

  $("#new-codes").addEventListener("click", () => sheet("Neue Wiederherstellungscodes", `
    <p class="small muted">Bestätige mit einem aktuellen Code aus deiner
    Authenticator-App. Alle bisherigen Wiederherstellungscodes werden ungültig.</p>
    <form id="rc-form" class="stack" data-s="mt-md">
      <div class="field"><label for="rc">Code</label>
        <input id="rc" inputmode="numeric" maxlength="6" pattern="[0-9]*" required></div>
      <button class="btn-primary btn-lg" type="submit">Codes neu erzeugen</button>
      <p class="tiny muted" id="rc-err"></p>
    </form>`, (body) => {
    $("#rc-form", body).addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const res = await api("/api/auth/recovery/regenerate", {
          method: "POST", body: { code: $("#rc", body).value },
        });
        body.innerHTML = `<div class="notice">Notiere diese Codes jetzt. Sie werden
          kein zweites Mal angezeigt.</div>
          <div class="codes" data-s="mt-lg">${res.recovery_codes
            .map((c) => `<span>${esc(c)}</span>`).join("")}</div>`;
      } catch (err) { $("#rc-err", body).textContent = err.message; }
    });
  }));

  $("#change-pw").addEventListener("click", () => sheet("Passwort ändern", `
    <form id="pw-form" class="stack">
      <div class="field"><label for="cp">Aktuelles Passwort</label>
        <input id="cp" type="password" autocomplete="current-password" required></div>
      <div class="field"><label for="np">Neues Passwort, mindestens 12 Zeichen</label>
        <input id="np" type="password" autocomplete="new-password" minlength="12" required></div>
      <div class="field"><label for="pc">Code aus der Authenticator-App</label>
        <input id="pc" inputmode="numeric" maxlength="6" pattern="[0-9]*" required></div>
      <p class="tiny muted">Nach der Änderung wirst du auf allen Geräten abgemeldet.</p>
      <button class="btn-primary btn-lg" type="submit">Passwort ändern</button>
      <p class="tiny muted" id="pw-err"></p>
    </form>`, (body) => {
    $("#pw-form", body).addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await api("/api/auth/password", {
          method: "POST",
          body: {
            current_password: $("#cp", body).value,
            new_password: $("#np", body).value,
            totp_code: $("#pc", body).value,
          },
        });
        closeSheet(); toast("Passwort geändert. Bitte neu anmelden."); boot();
      } catch (err) { $("#pw-err", body).textContent = err.message; }
    });
  }));

  $("#edit-measures").addEventListener("click", measureAdmin);
  $("#edit-meds").addEventListener("click", medicationAdmin);

  $("#backup").addEventListener("click", () => {
    location.href = "/api/exports/backup";
  });

  $("#restore").addEventListener("click", () => sheet("Sicherung einspielen", `
    <div class="notice">Die Wiederherstellung ersetzt sämtliche vorhandenen Daten
    dieser Installation. Bereits gesperrte Einträge des aktuellen Bestands gehen
    dabei verloren. Lade vorher eine aktuelle Sicherung herunter.</div>
    <form id="rs-form" class="stack" data-s="mt-lg">
      <div class="field"><label for="rf">Sicherungsdatei</label>
        <input id="rf" type="file" accept="application/json,.json" required></div>
      <div class="field"><label for="rp2">Passwort</label>
        <input id="rp2" type="password" autocomplete="current-password" required></div>
      <div class="field"><label for="rt">Code aus der Authenticator-App</label>
        <input id="rt" inputmode="numeric" maxlength="6" pattern="[0-9]*" required></div>
      <button class="btn-primary btn-lg" type="submit">Daten ersetzen</button>
      <p class="tiny muted" id="rs-err"></p>
    </form>`, (body) => {
    $("#rs-form", body).addEventListener("submit", async (e) => {
      e.preventDefault();
      const file = $("#rf", body).files[0];
      if (!file) return;
      if (!confirm("Alle vorhandenen Daten werden ersetzt. Fortfahren?")) return;
      const fd = new FormData();
      fd.append("file", file);
      const qs = new URLSearchParams({
        password: $("#rp2", body).value, totp_code: $("#rt", body).value,
      });
      try {
        await api("/api/exports/restore?" + qs.toString(), { method: "POST", body: fd });
        closeSheet();
        await loadCatalogs(true);
        toast("Sicherung eingespielt.");
        location.hash = "#/";
        render();
      } catch (err) { $("#rs-err", body).textContent = err.message; }
    });
  }));

  api("/api/legal").then((l) => {
    if (!$("#ln")) return;
    $("#ln").value = l.name || "";
    $("#la").value = l.address || "";
    $("#le").value = l.email || "";
  });
  $("#legal-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    await api("/api/legal", { method: "PUT", body: {
      imprint_name: $("#ln").value, imprint_address: $("#la").value,
      imprint_email: $("#le").value } });
    toast("Rechtliche Angaben gespeichert.");
  });

  api("/api/auth/devices").then((d) => {
    const box = $("#devices");
    if (!box) return;
    if (!d.devices.length) {
      box.textContent = "Kein Gerät ist als vertrauenswürdig hinterlegt.";
      return;
    }
    box.innerHTML = `<table class="data">${d.devices.map((x) => `
      <tr><td>${esc(x.label || "Unbekanntes Gerät")}${
        x.current ? ` <span class="status info">dieses Gerät</span>` : ""}</td>
        <td class="num">bis ${esc(fmtDate(x.expires_at))}</td></tr>`).join("")}</table>`;
  });
  $("#revoke-devices").addEventListener("click", async () => {
    if (!confirm("Allen Geräten das Vertrauen entziehen? Danach ist überall "
                 + "wieder ein Code nötig.")) return;
    await api("/api/auth/devices", { method: "DELETE" });
    toast("Vertrauen entzogen."); render();
  });

  if ((state.auth.user.role || "user") === "admin") renderAdmin();

  $("#logout").addEventListener("click", async () => {
    await api("/api/auth/logout", { method: "POST" });
    state.auth = null;
    boot();
  });

  api("/api/audit?limit=25").then((a) => {
    const box = $("#audit");
    if (!box) return;
    if (!a.entries.length) { box.textContent = "Noch keine Änderungen protokolliert."; return; }
    box.innerHTML = `<table class="data">${a.entries.map((r) => `
      <tr><td data-s="nowrap">${esc(fmtDate(r.at))}</td>
        <td>${esc(r.entity_type)}</td><td>${esc(r.action)}${
          r.field ? " · " + esc(r.field) : ""}</td>
        <td class="tiny">${r.old_value !== null && r.old_value !== undefined
          ? esc(r.old_value) + " → " + esc(r.new_value) : ""}</td></tr>`).join("")}</table>`;
  });
}

/* Administrationsbereich. Die Oberfläche blendet ihn für andere Rollen aus,
   aber das ist Bequemlichkeit: jede Route dahinter prüft die Rolle selbst
   und verlangt bei Eingriffen in fremde Konten einen frischen Code. */
async function renderAdmin() {
  const box = $("#admin-area");
  if (!box) return;
  const [u, inv, st] = await Promise.all([
    api("/api/admin/users"), api("/api/admin/invitations"),
    api("/api/admin/status"),
  ]);

  box.innerHTML = `
    <div class="card pad-lg" data-s="mt-md">
      <h2>Konten</h2>
      <p class="small muted" data-s="mt-xs">${u.users.length} Konten,
      ${st.open_invitations} offene Einladungen.
      ${st.mail_configured
        ? `Mailversand über ${esc(st.mail_host)} eingerichtet.`
        : `<span class="missing">Kein Mailversand eingerichtet.</span>
           Einladungen und Zurücksetzungs-Links musst du von Hand weitergeben.`}</p>
      <div class="stack" data-s="mt-md">
        ${u.users.map((x) => `
          <div class="card flat pad-xs">
            <div class="spread">
              <div class="grow">
                <strong>${esc(x.name || x.username)}</strong>
                <div class="tiny muted">${esc(x.username)}${
                  x.email ? " · " + esc(x.email) : ""}</div>
                <div class="row wrap" data-s="mt-xs gap-sm">
                  <span class="status ${x.role === "admin" ? "zek"
                    : x.role === "guest" ? "" : "info"}">${esc(x.role_label)}</span>
                  ${x.disabled ? `<span class="status fail">gesperrt</span>` : ""}
                  ${x.totp_active ? "" : `<span class="status abort">ohne 2FA</span>`}
                  <span class="tiny muted">${x.encounters} Einsätze</span>
                </div>
              </div>
              <button class="btn-quiet small" data-edit-user="${esc(x.id)}">Verwalten</button>
            </div>
          </div>`).join("")}
      </div>
      <button class="btn-primary" id="new-invite" data-s="mt-md">Person einladen</button>
    </div>

    <div class="card pad-lg" data-s="mt-md">
      <h2>Einladungen</h2>
      ${inv.invitations.length ? `<table class="data" data-s="mt-md">
        <tr><th>Empfänger</th><th>Rolle</th><th>Status</th></tr>
        ${inv.invitations.map((i) => `<tr>
          <td>${esc(i.email || i.note || "ohne Angabe")}</td>
          <td>${esc(i.role_label)}</td>
          <td>${esc(i.status)}${i.status === "offen"
            ? ` <button class="btn-quiet tiny" data-revoke="${esc(i.id)}">zurückziehen</button>`
            : ""}</td></tr>`).join("")}
      </table>` : `<p class="small muted" data-s="mt-sm">Noch keine Einladungen.</p>`}
    </div>

    <div class="card pad-lg" data-s="mt-md">
      <h2>Betrieb</h2>
      <form id="ops-form" class="stack" data-s="mt-md">
        <div class="field"><label for="idle">Automatische Abmeldung nach Leerlauf, in Minuten</label>
          <input id="idle" type="number" min="1" max="1440"
            value="${st.idle_timeout_minutes}">
          <p class="tiny muted" data-s="mt-xs">Wird serverseitig durchgesetzt.
          Eine Sitzung ohne Zugriff wird nach dieser Zeit ungültig, unabhängig
          davon, was der Browser tut.</p></div>
        <button class="btn-primary" type="submit">Speichern</button>
      </form>
    </div>`;

  box.querySelectorAll("[data-edit-user]").forEach((b) =>
    b.addEventListener("click", () =>
      userSheet(u.users.find((x) => x.id === b.dataset.editUser), u.roles)));
  box.querySelectorAll("[data-revoke]").forEach((b) =>
    b.addEventListener("click", async () => {
      await api(`/api/admin/invitations/${b.dataset.revoke}/revoke`, { method: "POST" });
      toast("Einladung zurückgezogen."); renderAdmin();
    }));
  $("#new-invite", box).addEventListener("click", inviteSheet);
  $("#ops-form", box).addEventListener("submit", async (e) => {
    e.preventDefault();
    await api("/api/admin/status", { method: "PUT",
      body: { idle_timeout_minutes: Number($("#idle", box).value) } });
    toast("Gespeichert.");
  });
}

function inviteSheet() {
  sheet("Person einladen", `
    <form id="inv-form" class="stack">
      <div class="field"><label for="iv-mail">E-Mail-Adresse (optional)</label>
        <input id="iv-mail" type="email" autocapitalize="none">
        <p class="tiny muted" data-s="mt-xs">Mit Adresse geht die Einladung
        direkt raus. Ohne bekommst du den Code hier angezeigt.</p></div>
      <div class="field"><label for="iv-role">Rolle</label>
        <select id="iv-role">
          <option value="user" selected>Mitarbeiter</option>
          <option value="guest">Gast, nur lesen</option>
          <option value="admin">Administrator</option>
        </select></div>
      <div class="field"><label for="iv-note">Notiz (optional)</label>
        <input id="iv-note" maxlength="200"></div>
      <div class="field"><label for="iv-days">Gültig für Tage</label>
        <input id="iv-days" type="number" min="1" max="90" value="7"></div>
      <div class="field"><label for="iv-code">Dein Code aus der Authenticator-App</label>
        <input id="iv-code" inputmode="numeric" maxlength="6" pattern="[0-9]*" required></div>
      <button class="btn-primary btn-lg" type="submit">Einladung erstellen</button>
      <p class="tiny muted" id="iv-err"></p>
    </form>`, (body) => {
    $("#inv-form", body).addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const r = await api("/api/admin/invitations", { method: "POST", body: {
          email: $("#iv-mail", body).value || null,
          role: $("#iv-role", body).value,
          note: $("#iv-note", body).value || null,
          valid_days: Number($("#iv-days", body).value),
          totp_code: $("#iv-code", body).value } });
        body.innerHTML = `
          <div class="notice">${r.sent
            ? "Die Einladung ist verschickt."
            : "Kein Mailversand. Gib Code oder Link persönlich weiter."}
            Der Code wird nur jetzt angezeigt, gespeichert ist nur sein Hash.</div>
          <div class="field" data-s="mt-md"><label>Einladungscode</label>
            <input readonly value="${esc(r.code)}"></div>
          <div class="field"><label>Link</label>
            <input readonly value="${esc(r.link)}"></div>
          <button class="btn-primary btn-lg" id="inv-done" data-s="mt-md">Fertig</button>`;
        $("#inv-done", body).addEventListener("click", () => {
          closeSheet(); renderAdmin();
        });
      } catch (err) { $("#iv-err", body).textContent = err.message; }
    });
  });
}

function userSheet(u, roles) {
  sheet(u.name || u.username, `
    <p class="small muted">${esc(u.username)}${u.email ? " · " + esc(u.email) : ""}
    · ${u.encounters} Einsätze</p>
    <form id="us-form" class="stack" data-s="mt-md">
      <div class="field"><label for="us-role">Rolle</label>
        <select id="us-role">${roles.map((r) =>
          `<option value="${esc(r.key)}" ${r.key === u.role ? "selected" : ""}>${
            esc(r.label)}</option>`).join("")}</select></div>
      <div class="row gap-md align-start" data-s="gap-md align-start">
        <input id="us-disabled" type="checkbox" data-s="checkbox" ${
          u.disabled ? "checked" : ""}>
        <label for="us-disabled" data-s="m-0">Konto sperren
          <span class="muted">– beendet sofort alle Sitzungen. Die
          dokumentierten Daten bleiben unverändert erhalten.</span></label>
      </div>
      <div class="field"><label for="us-code">Dein Code aus der Authenticator-App</label>
        <input id="us-code" inputmode="numeric" maxlength="6" pattern="[0-9]*" required></div>
      <div class="sheet-actions two">
        <button type="button" id="us-reset">Zurücksetzungs-Link erzeugen</button>
        <button class="btn-primary" type="submit">Änderungen speichern</button>
      </div>
      <p class="tiny muted" id="us-err"></p>
    </form>`, (body) => {
    const code = () => $("#us-code", body).value;
    $("#us-form", body).addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await api(`/api/admin/users/${u.id}`, { method: "PATCH", body: {
          role: $("#us-role", body).value,
          disabled: $("#us-disabled", body).checked,
          totp_code: code() } });
        closeSheet(); toast("Konto aktualisiert."); renderAdmin();
      } catch (err) { $("#us-err", body).textContent = err.message; }
    });
    $("#us-reset", body).addEventListener("click", async () => {
      try {
        const r = await api(`/api/admin/users/${u.id}/password-reset`,
          { method: "POST", body: { totp_code: code() } });
        body.innerHTML = r.sent
          ? `<div class="notice">Ein Zurücksetzungs-Link ist an
             ${esc(u.email)} unterwegs. Er gilt ${r.expires_in_minutes} Minuten.</div>`
          : `<div class="notice">Kein Mailversand. Gib diesen Link persönlich
             weiter, er gilt ${r.expires_in_minutes} Minuten und wird nur jetzt
             angezeigt.</div>
             <div class="field" data-s="mt-md"><input readonly value="${esc(r.link)}"></div>`;
        body.innerHTML += `<p class="tiny muted" data-s="mt-md">Zum Setzen des
          neuen Passworts ist zusätzlich der zweite Faktor des Kontos nötig.
          Als Administrator kommst du damit nicht in ein fremdes Konto.</p>`;
      } catch (err) { $("#us-err", body).textContent = err.message; }
    });
  });
}

function measureAdmin() {
  sheet("Maßnahmenkatalog", `
    <p class="small muted">Deaktivierte Maßnahmen verschwinden aus der Auswahl,
    bleiben in bestehenden Dokumentationen aber sichtbar.</p>
    <form id="add-measure-form" class="stack" data-s="my-md">
      <div class="field-row">
        <div class="field"><label for="nm">Neue Maßnahme</label><input id="nm" required></div>
        <div class="field"><label for="nc">Kategorie</label>
          <select id="nc">${state.constants.categories.map((c) =>
            `<option value="${esc(c.key)}">${esc(c.key)} · ${esc(c.label)}</option>`).join("")}</select></div>
      </div>
      <button type="submit">Hinzufügen</button>
    </form>
    <div class="pick-list" id="ma-list"></div>`, (body) => {
    async function draw() {
      const data = await api("/api/catalog/measures?include_inactive=true");
      $("#ma-list", body).innerHTML = data.measures.map((m) => `
        <div class="row" data-s="admin-row">
          <span class="grow small"><span class="cat-badge" data-cat="${esc(m.category)}">${
            esc(m.category)}</span> ${esc(m.name)}</span>
          <button class="chip" data-toggle="${esc(m.id)}" data-active="${m.active}"
            aria-pressed="${m.active}">${m.active ? "aktiv" : "inaktiv"}</button>
        </div>`).join("");
      $("#ma-list", body).querySelectorAll("[data-toggle]").forEach((b) =>
        b.addEventListener("click", async () => {
          await api("/api/catalog/measures/" + b.dataset.toggle, {
            method: "PATCH", body: { active: b.dataset.active !== "true" },
          });
          await loadCatalogs(true);
          draw();
        }));
    }
    $("#add-measure-form", body).addEventListener("submit", async (e) => {
      e.preventDefault();
      await api("/api/catalog/measures", {
        method: "POST",
        body: { name: $("#nm", body).value, category: $("#nc", body).value },
      });
      $("#nm", body).value = "";
      await loadCatalogs(true);
      draw();
      toast("Maßnahme hinzugefügt.");
    });
    draw();
  });
}

function medicationAdmin() {
  sheet("Medikamente", `
    <form id="add-med-form" class="stack" data-s="mb-md">
      <div class="field"><label for="nmed">Neuer Wirkstoff</label><input id="nmed" required></div>
      <button type="submit">Hinzufügen</button>
    </form>
    <div class="field"><input id="ma-search" placeholder="Filtern" aria-label="Filtern"></div>
    <div class="pick-list" data-s="mt-sm" id="med-admin-list"></div>`, (body) => {
    let all = [];
    function paint() {
      const term = $("#ma-search", body).value.trim().toLowerCase();
      const items = term ? all.filter((m) => m.name.toLowerCase().includes(term)) : all;
      $("#med-admin-list", body).innerHTML = items.map((m) => `
        <div class="row" data-s="admin-row">
          <span class="grow small">${esc(m.name)}</span>
          <button class="chip" data-toggle="${esc(m.id)}" data-active="${m.active}"
            aria-pressed="${m.active}">${m.active ? "aktiv" : "inaktiv"}</button>
        </div>`).join("");
      $("#med-admin-list", body).querySelectorAll("[data-toggle]").forEach((b) =>
        b.addEventListener("click", async () => {
          await api("/api/catalog/medications/" + b.dataset.toggle, {
            method: "PATCH", body: { active: b.dataset.active !== "true" },
          });
          await refresh();
        }));
    }
    async function refresh() {
      const data = await api("/api/catalog/medications?include_inactive=true");
      all = data.medications;
      await loadCatalogs(true);
      paint();
    }
    $("#ma-search", body).addEventListener("input", paint);
    $("#add-med-form", body).addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await api("/api/catalog/medications", {
          method: "POST", body: { name: $("#nmed", body).value },
        });
        $("#nmed", body).value = "";
        await refresh();
        toast("Wirkstoff hinzugefügt.");
      } catch (err) { toast(err.message); }
    });
    refresh();
  });
}

// ------------------------------------------------------------------- Start

/* Routen, die ohne Anmeldung erreichbar sein müssen. Sie werden vor der
   Zustandsprüfung behandelt, damit ein Einladungs- oder Reset-Link auch
   dann funktioniert, wenn niemand angemeldet ist. */
function publicRoute() {
  const { path, query } = currentRoute();
  if (path === "/registrieren" && query.get("code")) {
    viewInvitedRegister(query.get("code"));
    return true;
  }
  if (path === "/passwort-neu" && query.get("token")) {
    viewResetPassword(query.get("token"));
    return true;
  }
  if (path === "/passwort-vergessen") { viewForgotPassword(); return true; }
  if (path === "/rechtliches") {
    document.body.classList.add("auth");
    document.getElementById("nav").hidden = true;
    viewLegal();
    return true;
  }
  return false;
}

async function boot() {
  const auth = await api("/api/auth/state");
  state.auth = auth;
  if (!auth.authenticated && publicRoute()) return;
  if (auth.setup_required) return viewRegister(null, null);
  if (!auth.authenticated) return viewLogin();
  if (!auth.totp_confirmed) {
    const totp = await api("/api/auth/totp/setup");
    return viewTotpSetup(totp);
  }
  document.body.classList.remove("auth");
  document.getElementById("nav").hidden = false;
  await loadCatalogs();
  resetIdleTimer();
  if (!location.hash) location.hash = "#/";
  await render();
}

/* Der Browser warnt kurz vor Ablauf und meldet dann ab. Maßgeblich ist
   trotzdem der Server: er verwirft die Sitzung nach derselben Frist, auch
   wenn dieser Zähler manipuliert oder das Fenster geschlossen wird. */
let idleTimer = null;
let idleWarnTimer = null;
const IDLE_MINUTES_FALLBACK = 30;

function resetIdleTimer() {
  clearTimeout(idleTimer);
  clearTimeout(idleWarnTimer);
  if (!state.auth || !state.auth.authenticated) return;
  const minutes = (state.admin && state.admin.idle) || IDLE_MINUTES_FALLBACK;
  const ms = minutes * 60000;
  idleWarnTimer = setTimeout(() => {
    toast("Wegen Leerlaufs wirst du gleich abgemeldet.");
  }, Math.max(ms - 60000, 5000));
  idleTimer = setTimeout(async () => {
    try { await api("/api/auth/logout", { method: "POST" }); } catch (_) {}
    state.auth = null;
    boot();
    toast("Wegen Leerlaufs abgemeldet.");
  }, ms);
}

["click", "keydown", "touchstart", "visibilitychange"].forEach((ev) =>
  document.addEventListener(ev, () => {
    if (document.visibilityState === "hidden") return;
    resetIdleTimer();
  }, { passive: true }));

window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if (state.settings) applyTheme(state.settings.theme);
});

boot().catch((err) => {
  app().innerHTML = `<div class="empty"><strong>SCOPE X konnte nicht starten.</strong>
    ${esc(err.message)}</div>`;
});
