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

# --proxy-headers zusammen mit --forwarded-allow-ips ist nötig, damit die
# Anwendung erkennt, dass Nginx Proxy Manager die Verbindung per HTTPS
# terminiert hat. Ohne das würden Session-Cookies ohne Secure-Flag gesetzt.
# Der Port ist nicht auf dem Host veröffentlicht, erreichbar ist er nur im
# internen Docker-Netz.
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8099 \
  --proxy-headers \
  --forwarded-allow-ips='*' \
  --log-level "${LOG_LEVEL}"
