/* Übernahme aus NIDAshare (ab 4.8.0)

   Ablauf: Code eingeben oder fotografieren → bestätigen → der SCOPE-X-Server
   ruft das Protokoll ab und liefert nur einen Entwurf aus Maßnahmen,
   Medikamenten und Einsatzzeit → Nachbearbeitung → Übernehmen.

   Das Foto bleibt im Browser: Kamerabild, QR-Erkennung und Texterkennung
   laufen auf dem Gerät, hochgeladen wird nichts außer dem erkannten Code.
   Die Texterkennung (Tesseract, rund 6 MB) lädt erst beim ersten Foto. */

const NI_CODE = /[A-Za-z0-9-]{4,40}/g;

function niCodeAusText(text) {
  // Der längste Kandidat gewinnt: Beschriftungen wie "Code:" sind kürzer
  // als der eigentliche Code.
  const kandidaten = (String(text || "").match(NI_CODE) || [])
    .map((k) => k.replace(/^(nidashare|abrufcode|code)-?/i, ""))
    .filter((k) => k.length >= 4);
  return kandidaten.filter((k) => /\d/.test(k)).sort((a, b) => b.length - a.length)[0]
    || kandidaten.sort((a, b) => b.length - a.length)[0] || "";
}

function niLadeSkript(src) {
  return new Promise((ok, fehler) => {
    if (document.querySelector(`script[src="${src}"]`)) { ok(); return; }
    const s = document.createElement("script");
    s.src = src;
    s.onload = () => ok();
    s.onerror = () => fehler(new Error("Ein Bestandteil der Kamerafunktion fehlt."));
    document.head.appendChild(s);
  });
}

let niOcr = null;
async function niTexterkennung() {
  if (niOcr) return niOcr;
  await niLadeSkript("/assets/vendor/ocr/tesseract.min.js");
  niOcr = await window.Tesseract.createWorker("eng", 1, {
    workerPath: "/assets/vendor/ocr/worker.min.js",
    corePath: "/assets/vendor/ocr/tesseract-core-simd-lstm.js",
    langPath: "/assets/vendor/ocr/lang",
    workerBlobURL: false,
  });
  await niOcr.setParameters({
    // Doppelpunkt und Leerzeichen bleiben erlaubt, damit eine Beschriftung
    // wie "Code:" vom eigentlichen Code getrennt erkannt wird.
    tessedit_char_whitelist: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-: ",
    preserve_interword_spaces: "1",
  });
  return niOcr;
}

/* Kamera mit Rahmen. Ein QR-Code wird laufend gesucht; für Codes nur aus
   Text löst man aus, dann liest die Texterkennung den Ausschnitt im
   Rahmen. Ergebnis ist immer nur der Code, nie das Bild. */
function niKamera(fertig) {
  sheet("Code fotografieren", `
    <div class="ni-kamera">
      <video id="ni-video" playsinline muted autoplay aria-label="Kamerabild"></video>
      <div class="ni-rahmen" aria-hidden="true"></div>
    </div>
    <p class="small muted" id="ni-k-status" aria-live="polite">Richte den Rahmen auf den Code
      auf dem Tablet. Ein QR-Code wird sofort erkannt.</p>
    <p class="tiny muted">Das Bild verlässt dein Gerät nicht und wird nicht gespeichert.
      Achte darauf, dass möglichst nur der Code im Rahmen ist.</p>
    <div class="sheet-actions">
      <button class="btn-primary btn-lg" type="button" id="ni-ausloesen">Code aus Text lesen</button>
    </div>`, async (body) => {
    const video = $("#ni-video", body);
    const status = $("#ni-k-status", body);
    let strom = null, laeuft = true, takt = null;
    const stopp = () => {
      laeuft = false;
      if (takt) clearInterval(takt);
      if (strom) strom.getTracks().forEach((t) => t.stop());
    };
    const ergebnis = (code) => { stopp(); closeSheet(); fertig(code); };
    try {
      strom = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment", width: { ideal: 1920 } }, audio: false });
      video.srcObject = strom;
    } catch (_) {
      status.textContent = "Kein Zugriff auf die Kamera. Erlaube ihn in den Einstellungen "
        + "des Browsers oder gib den Code von Hand ein.";
      $("#ni-ausloesen", body).disabled = true;
      return;
    }
    // Ausschnitt im Rahmen: mittig, 80 % breit, 30 % hoch.
    const ausschnitt = () => {
      const w = video.videoWidth, h = video.videoHeight;
      if (!w || !h) return null;
      const c = document.createElement("canvas");
      c.width = Math.round(w * 0.8); c.height = Math.round(h * 0.3);
      c.getContext("2d", { willReadFrequently: true }).drawImage(
        video, Math.round(w * 0.1), Math.round(h * 0.35), c.width, c.height, 0, 0, c.width, c.height);
      return c;
    };
    const detektor = "BarcodeDetector" in window
      ? new window.BarcodeDetector({ formats: ["qr_code"] }) : null;
    if (!detektor) niLadeSkript("/assets/vendor/qr/jsqr.js").catch(() => {});
    takt = setInterval(async () => {
      if (!laeuft || !document.body.contains(video)) { stopp(); return; }
      try {
        if (detektor) {
          const f = await detektor.detect(video);
          if (f.length && f[0].rawValue) ergebnis(f[0].rawValue);
        } else if (window.jsQR) {
          const c = ausschnitt();
          if (!c) return;
          const d = c.getContext("2d").getImageData(0, 0, c.width, c.height);
          const f = window.jsQR(d.data, d.width, d.height, { inversionAttempts: "dontInvert" });
          if (f && f.data) ergebnis(f.data);
        }
      } catch (_) { /* nächster Versuch */ }
    }, 350);
    $("#ni-ausloesen", body).addEventListener("click", async (e) => {
      const knopf = e.currentTarget;
      const c = ausschnitt();
      if (!c) return;
      knopf.disabled = true;
      status.textContent = niOcr ? "Lese den Code …"
        : "Lade die Texterkennung (einmalig, etwa 6 MB) …";
      try {
        const w = await niTexterkennung();
        status.textContent = "Lese den Code …";
        const r = await w.recognize(c);
        const code = niCodeAusText(r.data.text);
        if (code) ergebnis(code);
        else {
          status.textContent = "Kein Code erkannt. Halte das Gerät ruhiger oder näher heran.";
          knopf.disabled = false;
        }
      } catch (err) {
        status.textContent = err.message || "Die Texterkennung ist fehlgeschlagen.";
        knopf.disabled = false;
      }
    });
  });
}

// ------------------------------------------------------------- Ansicht

async function viewNidaImport() {
  if (!state.constants.nidashare || !canWrite()) { location.replace("#/einsaetze"); return; }
  app().innerHTML = `
    <div class="page-head">
      <h1>Aus NIDAshare übernehmen</h1>
      <p class="muted small">SCOPE X ruft das Protokoll mit dem Code ab, liest nur
      Maßnahmen, Medikamente und die Einsatzzeit heraus und verwirft das Protokoll
      sofort. Es landet weder auf deinem Gerät noch in SCOPE X.</p>
    </div>
    <div class="card pad-lg">
      <form id="ni-form" class="stack" novalidate>
        <div class="field"><label for="ni-code">NIDAshare-Code</label>
          <input id="ni-code" autocomplete="off" autocapitalize="characters" spellcheck="false"
            inputmode="text" maxlength="200" required aria-describedby="ni-code-h"></div>
        <p class="tiny muted" id="ni-code-h">Den Code zeigt das Tablet nach der Übergabe.
          Jeder Abruf zählt bei NIDAshare als Download des Protokolls.</p>
        <div class="sheet-actions two">
          <button type="button" id="ni-foto">Code fotografieren</button>
          <button class="btn-primary" type="submit">Weiter</button>
        </div>
        <p class="small" id="ni-err" role="alert"></p>
      </form>
    </div>
    <div id="ni-entwurf"></div>
    ${pageFoot()}`;

  const feld = $("#ni-code");
  const fehler = $("#ni-err");
  $("#ni-foto").addEventListener("click", () => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      fehler.textContent = "Dieser Browser erlaubt keinen Kamerazugriff. Gib den Code von Hand ein.";
      return;
    }
    niKamera((code) => {
      feld.value = code;
      feld.focus();
      fehler.textContent = "";
      toast("Code erkannt. Bitte prüfe ihn, bevor du weitergehst.");
    });
  });

  const abrufen = async (code, erneut) => {
    $("#ni-entwurf").innerHTML = `<div class="empty">${markSvg("mark")}
      <strong>Protokoll wird abgerufen …</strong>Das kann einige Sekunden dauern.</div>`;
    try {
      const e = await api("/api/import/nidashare", { method: "POST", body: { code, erneut } });
      feld.value = "";
      await niEntwurf(e);
    } catch (err) {
      $("#ni-entwurf").innerHTML = "";
      if (!erneut && /schon einmal abgerufen/.test(err.message)) {
        sheet("Erneut abrufen?", `
          <p>${esc(err.message)}</p>
          <div class="sheet-actions two">
            <button type="button" data-close>Abbrechen</button>
            <button class="btn-primary" type="button" id="ni-erneut">Erneut abrufen</button>
          </div>`, (b) => {
          $("[data-close]", b).addEventListener("click", closeSheet);
          $("#ni-erneut", b).addEventListener("click", () => { closeSheet(); abrufen(code, true); });
        });
        return;
      }
      fehler.textContent = err.message;
    }
  };

  $("#ni-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const code = feld.value.trim();
    fehler.textContent = "";
    if (!code) { fehler.textContent = "Gib den Code ein oder fotografiere ihn."; return; }
    // Ein falsch gelesenes Zeichen kann das Protokoll eines fremden
    // Einsatzes öffnen. Deshalb vor jedem Abruf bestätigen.
    sheet("Code prüfen", `
      <p class="small muted">Stimmt der Code Zeichen für Zeichen mit dem Tablet überein?</p>
      <p class="ni-code-gross">${esc(code)}</p>
      <div class="sheet-actions two">
        <button type="button" id="ni-korr">Korrigieren</button>
        <button class="btn-primary" type="button" id="ni-ok">Abrufen</button>
      </div>`, (b) => {
      $("#ni-korr", b).addEventListener("click", () => { closeSheet(); feld.focus(); });
      $("#ni-ok", b).addEventListener("click", () => { closeSheet(); abrufen(code, false); });
    });
  });
}

// ------------------------------------------------------ Nachbearbeitung

async function niEntwurf(e) {
  const [kat, meds] = await Promise.all([
    api("/api/catalog/measures"), api("/api/catalog/medications")]);
  const massnahmen = kat.measures.filter((m) => m.active !== false);
  const medikamente = meds.medications.filter((m) => m.active !== false);
  const C = state.constants;
  const sel = (liste, wert, leer) => `${leer ? `<option value="">${esc(leer)}</option>` : ""}${
    liste.map(([v, t]) => `<option value="${esc(v)}" ${v === wert ? "selected" : ""}>${esc(t)}</option>`).join("")}`;
  const massnahmeOptionen = (id) => sel(massnahmen.map((m) => [m.id, `${m.category} · ${m.name}`]), id);
  const medOptionen = (id) => sel(medikamente.map((m) => [m.id, m.name]), id);
  const rollen = C.performer_roles.map((r) => [r.key, r.key]);
  const ergebnisse = C.outcomes.map((o) => [o, o]);
  let nr = 0;

  const massnahmeZeile = (f) => {
    const i = nr++;
    const m = massnahmen.find((x) => x.id === f.measure_id);
    const bz = m && (m.parameters || []).find((p) => p.type === "glucose");
    const p = f.parameter || {};
    return `
    <li class="ni-zeile" data-art="m" data-i="${i}" data-orig="${esc(f.measure_id || "")}"
        data-begriff="${esc(f.begriff || "")}">
      <label class="check"><input type="checkbox" data-wahl ${f.neu || f.sicher ? "checked" : ""}>
        <span class="sr-only">Übernehmen</span></label>
      <div class="ni-felder">
        <div class="field"><label for="nim-${i}">Maßnahme${f.sicher === false
          ? ' <span class="ni-pruefen">bitte prüfen</span>' : ""}${f.anzahl > 1
          ? ` <span class="tiny muted">${f.anzahl}× im Protokoll</span>` : ""}</label>
          <select id="nim-${i}" data-feld="measure_id">${massnahmeOptionen(f.measure_id)}</select></div>
        <div class="field-row three">
          <div class="field"><label for="nio-${i}">Ergebnis</label>
            <select id="nio-${i}" data-feld="outcome">${sel(ergebnisse,
              f.fehlversuch ? "fehlgeschlagen" : "erfolgreich")}</select></div>
          <div class="field"><label for="nir-${i}">Deine Rolle</label>
            <select id="nir-${i}" data-feld="performer_role">${sel(rollen, "selbst durchgeführt")}</select></div>
          <div class="field"><label for="niz-${i}">Uhrzeit</label>
            <input id="niz-${i}" type="time" data-feld="zeit" value="${esc(f.zeit || "")}"></div>
        </div>
        ${bz ? `<div class="field"><label for="nib-${i}">${esc(bz.label)}</label>
          <div class="bz-zeile">
            <input id="nib-${i}" type="number" step="any" min="0" inputmode="decimal"
              data-param="${esc(bz.key)}" value="${esc(p.wert || "")}">
            <label class="sr-only" for="nibe-${i}">Einheit</label>
            <select id="nibe-${i}" data-param="${esc(bz.key)}__einheit" data-bz-einheit>
              ${sel([["mg/dl", "mg/dl"], ["mmol/l", "mmol/l"]], p.wert__einheit || bzEinheit())}</select>
          </div><p class="tiny muted" data-bz-um aria-live="polite"></p></div>` : ""}
      </div>
    </li>`;
  };

  const gabeZeile = (g) => {
    const i = nr++;
    return `
    <li class="ni-zeile" data-art="g" data-i="${i}">
      <label class="check"><input type="checkbox" data-wahl ${g.neu || g.sicher ? "checked" : ""}>
        <span class="sr-only">Übernehmen</span></label>
      <div class="ni-felder">
        <div class="field"><label for="nig-${i}">Wirkstoff${g.sicher === false
          ? ' <span class="ni-pruefen">bitte prüfen</span>' : ""}</label>
          <select id="nig-${i}" data-feld="medication_id">${medOptionen(g.medication_id)}</select></div>
        <div class="field-row four">
          <div class="field"><label for="nid-${i}">Dosis</label>
            <input id="nid-${i}" type="number" step="any" min="0" inputmode="decimal"
              data-feld="dose" value="${g.dosis == null ? "" : esc(g.dosis)}"></div>
          <div class="field"><label for="nie-${i}">Einheit</label>
            <select id="nie-${i}" data-feld="unit">${sel(C.units.map((u) => [u, u]), g.einheit, "–")}</select></div>
          <div class="field"><label for="niw-${i}">Weg</label>
            <select id="niw-${i}" data-feld="route">${sel(C.routes.map((r) => [r, r]), g.weg, "–")}</select></div>
          <div class="field"><label for="nit-${i}">Uhrzeit</label>
            <input id="nit-${i}" type="time" data-feld="zeit" value="${esc(g.zeit || "")}"></div>
        </div>
      </div>
    </li>`;
  };

  const ein = e.einsatz || {};
  $("#ni-entwurf").innerHTML = `
    <form id="ni-uebernahme" class="stack" data-s="mt-md">
      <div class="card pad-lg">
        <h2>Einsatz</h2>
        <p class="small muted" data-s="mt-xs">Aus dem Protokoll gelesen. Prüfe, ob es dein
          Einsatz ist; wenn nicht, verwirf den Entwurf.</p>
        <div class="field-row" data-s="mt-sm">
          <div class="field"><label for="ni-datum">Datum</label>
            <input id="ni-datum" type="date" max="${todayISO()}" value="${esc(ein.datum || "")}" required></div>
          <div class="field"><label for="ni-zeit">Alarmzeit</label>
            <input id="ni-zeit" type="time" value="${esc(ein.uhrzeit || "")}" required></div>
        </div>
        <div class="field-row">
          <div class="field"><label for="ni-naca">NACA</label>
            <select id="ni-naca">${sel(C.naca.map((n) => [n, "NACA " + n]), ein.naca, "ohne Angabe")}</select></div>
          <div class="field"><label for="ni-nr">Einsatznummer (nur für dich sichtbar)</label>
            <input id="ni-nr" autocomplete="off" maxlength="40" value="${esc(ein.einsatznummer || "")}"></div>
        </div>
        ${showDelegation() ? `<div class="field"><label for="ni-deleg">Durchführungsart für alle Einträge</label>
          <select id="ni-deleg">${sel(C.delegations.map((d) => [d, d]), "", "ohne Angabe")}</select></div>` : ""}
      </div>

      <div class="notice">Übernimm nur, was du selbst durchgeführt, angeleitet oder bei dem du
        assistiert hast. Das Protokoll enthält alles, was im Einsatz geschah, auch durch andere.</div>

      <section class="card pad-lg">
        <h2>Maßnahmen <span class="tiny muted">${e.massnahmen.length} gefunden</span></h2>
        <ul class="ni-liste" id="ni-m">${e.massnahmen.map(massnahmeZeile).join("")}</ul>
        <button type="button" class="btn-soft" id="ni-m-plus" data-s="mt-sm">Maßnahme ergänzen</button>
      </section>

      <section class="card pad-lg">
        <h2>Medikamente <span class="tiny muted">${e.medikamente.length} gefunden</span></h2>
        <ul class="ni-liste" id="ni-g">${e.medikamente.map(gabeZeile).join("")}</ul>
        <button type="button" class="btn-soft" id="ni-g-plus" data-s="mt-sm">Medikament ergänzen</button>
      </section>

      <div class="sheet-actions two">
        <button type="button" id="ni-verwerfen">Verwerfen</button>
        <button class="btn-primary btn-lg" type="submit">Übernehmen</button>
      </div>
      <p class="small" id="ni-u-err" role="alert"></p>
    </form>`;
  const form = $("#ni-uebernahme");
  bindBlutzucker(form);
  form.scrollIntoView({ behavior: "smooth", block: "start" });

  $("#ni-m-plus").addEventListener("click", () => {
    $("#ni-m").insertAdjacentHTML("beforeend", massnahmeZeile({ measure_id: massnahmen[0].id, neu: true }));
    bindBlutzucker($("#ni-m").lastElementChild);
  });
  $("#ni-g-plus").addEventListener("click", () => {
    $("#ni-g").insertAdjacentHTML("beforeend", gabeZeile({ medication_id: medikamente[0].id, neu: true }));
  });
  // Eine andere Maßnahme gewählt: Blutzuckerfeld passt nicht mehr. Die
  // Zeile wird neu aufgebaut, Auswahl und Uhrzeit bleiben.
  $("#ni-m").addEventListener("change", (ev) => {
    if (ev.target.dataset.feld !== "measure_id") return;
    const li = ev.target.closest(".ni-zeile");
    const neu = document.createElement("div");
    neu.innerHTML = massnahmeZeile({ measure_id: ev.target.value, neu: true,
      zeit: $("[data-feld=zeit]", li).value });
    const ersatz = neu.firstElementChild;
    ersatz.dataset.orig = li.dataset.orig;
    ersatz.dataset.begriff = li.dataset.begriff;
    li.replaceWith(ersatz);
    bindBlutzucker(ersatz);
    $("[data-feld=measure_id]", ersatz).focus();
  });

  $("#ni-verwerfen").addEventListener("click", async () => {
    await api(`/api/import/nidashare/${encodeURIComponent(e.id)}/verwerfen`, { method: "POST" })
      .catch(() => {});
    $("#ni-entwurf").innerHTML = "";
    toast("Entwurf verworfen. Nichts wurde gespeichert.");
  });

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const fehler = $("#ni-u-err");
    const deleg = ($("#ni-deleg") || {}).value || null;
    const gewaehlt = (art) => Array.from(form.querySelectorAll(`.ni-zeile[data-art=${art}]`))
      .filter((li) => $("[data-wahl]", li).checked);
    const wert = (li, f) => { const n = $(`[data-feld=${f}]`, li); return n ? n.value : ""; };
    const daten = {
      einsatz: { datum: $("#ni-datum").value, uhrzeit: $("#ni-zeit").value,
        naca: $("#ni-naca").value || null, einsatznummer: $("#ni-nr").value || null },
      massnahmen: gewaehlt("m").map((li) => {
        const parameters = {};
        li.querySelectorAll("[data-param]").forEach((f) => { if (f.value !== "") parameters[f.dataset.param] = f.value; });
        const mid = wert(li, "measure_id");
        return { measure_id: mid, outcome: wert(li, "outcome"),
          performer_role: wert(li, "performer_role"), zeit: wert(li, "zeit") || null,
          delegation: deleg, parameters,
          begriff: li.dataset.begriff && mid !== li.dataset.orig ? li.dataset.begriff : null };
      }),
      medikamente: gewaehlt("g").map((li) => ({
        medication_id: wert(li, "medication_id"),
        dose: wert(li, "dose") === "" ? null : Number(wert(li, "dose").replace(",", ".")),
        unit: wert(li, "unit") || null, route: wert(li, "route") || null,
        zeit: wert(li, "zeit") || null, delegation: deleg })),
    };
    if (!daten.massnahmen.length && !daten.medikamente.length) {
      fehler.textContent = "Wähle mindestens eine Maßnahme oder ein Medikament."; return;
    }
    const knopf = form.querySelector("button[type=submit]");
    knopf.disabled = true;
    try {
      const r = await api(`/api/import/nidashare/${encodeURIComponent(e.id)}/uebernehmen`,
        { method: "POST", body: daten });
      toast("Übernommen. Die Bearbeitungsfrist läuft ab jetzt.");
      location.hash = "#/einsatz/" + r.encounter_id;
    } catch (err) { fehler.textContent = err.message; knopf.disabled = false; }
  });
}
