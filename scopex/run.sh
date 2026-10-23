#!/bin/sh
set -e

CONFIG=/data/options.json
LOG_LEVEL=info
if [ -f "$CONFIG" ]; then
  LOG_LEVEL=$(python3 -c "import json,sys;print(json.load(open('$CONFIG')).get('log_level','info'))" 2>/dev/null || echo info)
fi

mkdir -p /data

# Konfiguration aus der Add-on-Oberfläche in Umgebungsvariablen überführen.
# Die Zugangsdaten stehen ausschließlich hier und nie im Quelltext oder in
# der Datenbank.
if [ -f "$CONFIG" ]; then
  eval "$(python3 - "$CONFIG" <<'PYEOF'
import json, shlex, sys
opts = json.load(open(sys.argv[1]))
mapping = {
    "base_url": "SCOPEX_BASE_URL",
    "trusted_proxies": "SCOPEX_TRUSTED_PROXIES",
    "smtp_host": "SCOPEX_SMTP_HOST",
    "smtp_port": "SCOPEX_SMTP_PORT",
    "smtp_security": "SCOPEX_SMTP_SECURITY",
    "smtp_user": "SCOPEX_SMTP_USER",
    "smtp_password": "SCOPEX_SMTP_PASSWORD",
    "smtp_from": "SCOPEX_SMTP_FROM",
}
for key, env in mapping.items():
    value = opts.get(key)
    if value not in (None, ""):
        print(f"export {env}={shlex.quote(str(value))}")
PYEOF
)"
fi

if [ -n "${SCOPEX_SMTP_HOST:-}" ]; then
  echo "Mailversand über ${SCOPEX_SMTP_HOST}:${SCOPEX_SMTP_PORT:-465} eingerichtet"
else
  echo "Kein SMTP-Server hinterlegt. Einladungen und Zurücksetzungs-Links"
  echo "lassen sich im Administrationsbereich anzeigen und von Hand weitergeben."
fi

echo "SCOPE X startet, Log-Level ${LOG_LEVEL}"

# Welchen Gegenstellen die Weiterleitungs-Header geglaubt werden.
#
# Vorher stand hier '*'. Das heißt: jeder Client darf X-Forwarded-Proto und
# X-Forwarded-For selbst setzen. Weil Port 8099 auf dem Host veröffentlicht
# ist, erreicht ein Client im LAN den Container auch direkt, an Nginx Proxy
# Manager vorbei — und konnte damit das Secure-Flag der Sitzungscookies
# steuern und eine frei erfundene Client-IP ins Änderungsprotokoll
# schreiben, die dort als gehashte Herkunft landete.
#
# Die Vorgabe ist das Supervisor-Netz von Home Assistant, in dem die
# Add-on-Container liegen. Nginx Proxy Manager fällt darunter, ein Gerät im
# LAN nicht: dessen Header werden ignoriert und die echte Adresse
# protokolliert. Steht ein weiterer Proxy davor, etwa ein
# Cloudflare-Tunnel, gehört dessen Netz zusätzlich in diese Option.
TRUSTED_PROXIES="${SCOPEX_TRUSTED_PROXIES:-172.30.32.0/23}"
echo "Weiterleitungs-Header werden akzeptiert von: ${TRUSTED_PROXIES}"

if [ -n "${SCOPEX_BASE_URL:-}" ]; then
  case "${SCOPEX_BASE_URL}" in
    https://*) echo "Basis-Adresse: ${SCOPEX_BASE_URL}" ;;
    http://*)
      echo "WARNUNG: Die Basis-Adresse verwendet http. Passkeys setzen"
      echo "HTTPS voraus und bleiben damit abgeschaltet."
      ;;
    *)
      echo "WARNUNG: Die Basis-Adresse hat kein Schema und wird als"
      echo "https://${SCOPEX_BASE_URL} gelesen. Trage sie vollständig ein."
      ;;
  esac
else
  echo "Keine Basis-Adresse hinterlegt. Passkeys sind abgeschaltet, und"
  echo "Mails enthalten keine vollständigen Links."
fi

# --proxy-headers zusammen mit --forwarded-allow-ips ist nötig, damit die
# Anwendung erkennt, dass Nginx Proxy Manager die Verbindung per HTTPS
# terminiert hat. Ohne das würden Session-Cookies ohne Secure-Flag gesetzt.
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8099 \
  --proxy-headers \
  --forwarded-allow-ips="${TRUSTED_PROXIES}" \
  --log-level "${LOG_LEVEL}"
