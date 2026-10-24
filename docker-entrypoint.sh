#!/bin/sh
set -e
mkdir -p "$(dirname "$TUTOR_DB")"
chown tutor "$(dirname "$TUTOR_DB")"
exec su tutor -s /bin/sh -c "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"
