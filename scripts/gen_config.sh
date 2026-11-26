#!/usr/bin/env bash
# Genera window.APP_CONFIG (contrato 04 §5) a partir de `terraform output -json`.
# Uso: scripts/gen_config.sh outputs.json > config.js
set -euo pipefail

OUT="${1:?uso: gen_config.sh outputs.json}"
out() { jq -r ".$1.value" "$OUT"; }

ENV_NAME=$(out env)
API=$(out api_base_url)
CF=$(out cloudfront_domain)
COG_DOMAIN=$(out cognito_domain)
CLIENT_ID=$(out cognito_client_id)

cat <<JS
window.APP_CONFIG = {
  env: "${ENV_NAME}",
  apiBase: "${API}",
  assetsBase: "https://${CF}/assets",
  cognito: {
    domain: "${COG_DOMAIN}",
    clientId: "${CLIENT_ID}",
    redirectUri: "https://${CF}/admin/index.html",
    logoutUri: "https://${CF}/admin/index.html"
  },
  pollIntervalMs: 20000,
  useMock: false
};
JS
