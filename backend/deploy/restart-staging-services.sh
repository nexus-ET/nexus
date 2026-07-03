#!/usr/bin/env bash
# Restart all NEXUS staging services on Hostinger VPS.
#
# Staging has no separate frontend daemon — nginx serves frontend/dist statically.
# This restarts: nexus-backend (FastAPI) + nginx (static UI + reverse proxy).
#
#   sudo bash /var/www/nexus/backend/deploy/restart-staging-services.sh
#   sudo bash /var/www/nexus/backend/deploy/restart-staging-services.sh --logs

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="/var/www/nexus"
BACKEND="${APP_ROOT}/backend"
PUBLIC_DOMAIN="nexus-dev.edutrust.in"

if [[ -f "${SCRIPT_DIR}/deploy.config" ]]; then
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/deploy.config"
  PUBLIC_DOMAIN="${NEXUS_DOMAIN:-$PUBLIC_DOMAIN}"
fi

SHOW_LOGS=0
if [[ "${1:-}" == "--logs" ]]; then
  SHOW_LOGS=1
fi

echo "==> Restarting NEXUS staging services ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
echo "    Domain: https://${PUBLIC_DOMAIN}"
echo ""

if ! command -v systemctl >/dev/null 2>&1; then
  echo "ERROR: systemctl not found." >&2
  exit 1
fi

echo "==> Backend (nexus-backend)..."
systemctl restart nexus-backend
sleep 2

if systemctl is-active --quiet nexus-backend; then
  echo "    nexus-backend: active"
else
  echo "    ERROR: nexus-backend failed to start" >&2
  systemctl status nexus-backend --no-pager -l || true
  exit 1
fi

echo ""
echo "==> nginx (frontend static + API proxy)..."
nginx -t
systemctl reload nginx
echo "    nginx: reloaded"

echo ""
echo "==> Health checks..."
if curl -sf "http://127.0.0.1:8002/" >/dev/null; then
  echo "    Backend API: OK (http://127.0.0.1:8002/)"
else
  echo "    Backend API: NOT responding" >&2
  SHOW_LOGS=1
fi

if curl -sf "https://${PUBLIC_DOMAIN}/" >/dev/null; then
  echo "    Public site: OK (https://${PUBLIC_DOMAIN}/)"
else
  echo "    Public site: check nginx / SSL" >&2
fi

if curl -sf "https://${PUBLIC_DOMAIN}/api/v1/leads/status-definitions" >/dev/null 2>&1; then
  echo "    API via nginx: OK"
else
  echo "    API via nginx: failed (login/issues may be backend or auth)" >&2
fi

if [[ -d "${APP_ROOT}/frontend/dist" ]]; then
  if grep -rq "View Journey" "${APP_ROOT}/frontend/dist" 2>/dev/null; then
    echo "    Frontend dist: built (View Journey present)"
  else
    echo "    Frontend dist: OLD build — run hostinger-staging.sh --frontend-only" >&2
  fi
else
  echo "    Frontend dist: missing — run npm run build in frontend/" >&2
fi

if [[ "$SHOW_LOGS" -eq 1 ]]; then
  echo ""
  echo "==> Recent backend logs..."
  journalctl -u nexus-backend -n 40 --no-pager || true
fi

echo ""
echo "==> Done. Hard-refresh browser: Ctrl+Shift+R"
echo ""
echo "Login tip: staging uses a SEPARATE Neon database from dev."
echo "If password fails, reset on VPS:"
echo "  cd ${BACKEND} && source .venv/bin/activate"
echo "  python scripts/reset_dev_password.py YOUR_EMAIL 'NewPassword123'"
