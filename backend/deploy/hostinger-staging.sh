#!/usr/bin/env bash
# Complete NEXUS staging deploy for Hostinger VPS.
#
# Unlike deploy.sh alone, this script always builds the frontend and restarts
# services even when migration bootstrap logs warnings. Use after every staging push.
#
# On the VPS (SSH):
#   sudo bash /var/www/nexus/backend/deploy/hostinger-staging.sh
#   sudo bash /var/www/nexus/backend/deploy/hostinger-staging.sh --frontend-only
#   sudo bash /var/www/nexus/backend/deploy/hostinger-staging.sh --skip-migrations
#
# From Windows (see hostinger-staging.ps1):
#   .\backend\deploy\hostinger-staging.ps1 -VpsHost root@YOUR_VPS_IP

set -euo pipefail

APP_ROOT="/var/www/nexus"
GIT_BRANCH="staging"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

FRONTEND_ONLY=0
SKIP_MIGRATIONS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --frontend-only)
      FRONTEND_ONLY=1
      shift
      ;;
    --skip-migrations)
      SKIP_MIGRATIONS=1
      shift
      ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -f "${SCRIPT_DIR}/deploy.config" ]]; then
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/deploy.config"
fi

BACKEND="${APP_ROOT}/backend"
FRONTEND="${APP_ROOT}/frontend"
BACKEND_HEALTH_URL="http://127.0.0.1:8002/"
PUBLIC_DOMAIN="${NEXUS_DOMAIN:-nexus-dev.edutrust.in}"
GIT_BRANCH="${GIT_BRANCH:-staging}"

if [[ ! -d "${APP_ROOT}/.git" ]]; then
  echo "ERROR: ${APP_ROOT} is not a git repository." >&2
  exit 1
fi

if [[ ! -d "${BACKEND}/.venv" ]]; then
  echo "ERROR: ${BACKEND}/.venv not found. Run install.sh first." >&2
  exit 1
fi

echo "==> Hostinger staging deploy"
echo "    App root:  ${APP_ROOT}"
echo "    Branch:    ${GIT_BRANCH}"
echo "    Domain:    ${PUBLIC_DOMAIN}"
echo "    Mode:      frontend_only=${FRONTEND_ONLY} skip_migrations=${SKIP_MIGRATIONS}"
echo ""

if [[ "${FRONTEND_ONLY}" -eq 0 ]]; then
  echo "==> Pull ${GIT_BRANCH}..."
  cd "${APP_ROOT}"
  git fetch origin "${GIT_BRANCH}"
  git checkout "${GIT_BRANCH}"
  git pull --ff-only origin "${GIT_BRANCH}"
  echo "    Commit: $(git log -1 --oneline)"

  echo ""
  echo "==> Backend dependencies..."
  cd "${BACKEND}"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -r requirements.txt -q
  pip install 'psycopg[binary]' -q

  if [[ "${SKIP_MIGRATIONS}" -eq 0 ]]; then
    echo ""
    echo "==> Database migrations..."
    if python scripts/bootstrap_alembic.py; then
      echo "    Migrations: bootstrap complete."
    else
      echo "    WARNING: bootstrap_alembic failed; running alembic upgrade head directly." >&2
      python -m alembic upgrade head
    fi
    echo "    Alembic: $(python -m alembic current 2>/dev/null | head -1 || echo unknown)"
  else
    echo ""
    echo "==> Skipping migrations (--skip-migrations)."
  fi
fi

echo ""
echo "==> Frontend build..."
cd "${FRONTEND}"
npm ci
npm run build

if grep -rq "View Journey" "${FRONTEND}/dist" 2>/dev/null; then
  echo "    Frontend build OK (View Journey found in dist)."
else
  echo "    WARNING: 'View Journey' not found in dist — UI may be outdated or build failed." >&2
fi

echo ""
echo "==> Restart services..."
if command -v systemctl >/dev/null 2>&1; then
  systemctl restart nexus-backend
  nginx -t
  systemctl reload nginx
else
  echo "    systemctl not available; restart nexus-backend manually." >&2
fi

echo ""
echo "==> WhatsApp webhook sync..."
cd "${BACKEND}"
# shellcheck disable=SC1091
source .venv/bin/activate
if python scripts/sync_whatsapp_webhook.py; then
  echo "    Webhook registered."
else
  echo "    Webhook sync failed (check WHATSAPP_* and PUBLIC_TUNNEL_BASE)." >&2
fi

chown -R www-data:www-data "${FRONTEND}/dist" 2>/dev/null || true

echo ""
echo "==> Health checks..."
if curl -sf "${BACKEND_HEALTH_URL}" >/dev/null 2>&1; then
  echo "    Backend: OK (${BACKEND_HEALTH_URL})"
else
  echo "    Backend: NOT responding — check journalctl -u nexus-backend -n 50" >&2
fi

if curl -sf "https://${PUBLIC_DOMAIN}/" >/dev/null 2>&1; then
  echo "    Public site: OK (https://${PUBLIC_DOMAIN}/)"
else
  echo "    Public site: check nginx / DNS" >&2
fi

if [[ -x "${SCRIPT_DIR}/verify-staging-deploy.sh" ]]; then
  echo ""
  bash "${SCRIPT_DIR}/verify-staging-deploy.sh" || true
fi

echo ""
echo "==> Deploy complete at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "    Hard-refresh browser: Ctrl+Shift+R on https://${PUBLIC_DOMAIN}"
