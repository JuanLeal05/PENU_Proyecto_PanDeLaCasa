#!/usr/bin/env bash
# Verificaciones posteriores al despliegue. Uso: scripts/smoke_test.sh outputs.json
set -euo pipefail

OUT="${1:?uso: smoke_test.sh outputs.json}"
out() { jq -r ".$1.value" "$OUT"; }

ENV_NAME=$(out env)
API=$(out api_base_url)
CF="https://$(out cloudfront_domain)"
ATTEMPTS="${SMOKE_ATTEMPTS:-10}"
DELAY="${SMOKE_DELAY:-15}"

retry() { # retry <descripción> <comando...>
  local desc="$1"; shift
  for i in $(seq 1 "$ATTEMPTS"); do
    if "$@" >/dev/null 2>&1; then echo "OK   $desc"; return 0; fi
    echo "...  $desc (intento $i/$ATTEMPTS)"; sleep "$DELAY"
  done
  echo "FAIL $desc"; return 1
}

status() { curl -s -o /dev/null -w '%{http_code}' "$1"; }

check_home()   { curl -fsS "$CF/" | grep -q "Pan de la Casa"; }
check_config() { curl -fsS "$CF/config.js" | grep -qF "$API"; }
check_health() { curl -fsS "$API/api/health" | jq -e --arg e "$ENV_NAME" '.status=="ok" and .env==$e'; }
check_avail()  { curl -fsS "$API/api/availability" | jq -e '(.slots | length) == 30'; }
check_admin()  { [ "$(status "$API/api/admin/orders")" = "401" ]; }
check_hsts()   { curl -sSD - -o /dev/null "$CF/" | grep -qi '^strict-transport-security'; }

FAILED=0
retry "GET / contiene 'Pan de la Casa'" check_home || FAILED=1
retry "GET /config.js contiene apiBase" check_config || FAILED=1
retry "GET /api/health (status ok, env=$ENV_NAME)" check_health || FAILED=1
retry "GET /api/availability (30 franjas)" check_avail || FAILED=1
retry "GET /api/admin/orders sin token -> 401" check_admin || FAILED=1
retry "Header strict-transport-security" check_hsts || FAILED=1

# No obligatorio: puede faltar hasta cargar los datos semilla.
if [ "$(status "$CF/assets/catalog/catalog.json")" = "200" ]; then
  echo "OK   catalog.json presente"
else
  echo "WARN catalog.json aún no existe (¿faltan los datos semilla?)"
fi

exit "$FAILED"
