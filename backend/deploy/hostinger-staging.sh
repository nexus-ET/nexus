#!/usr/bin/env bash
# Complete NEXUS staging deploy for Hostinger VPS.
#
# Prerequisites:
#   - /var/www/nexus/backend/.env points DATABASE_URL at Neon Nexus-Dev-1
#     (pooled postgresql+psycopg://...?sslmode=require). See
#     STAGING_CONFIG_REQUIREMENTS.md — do not overwrite .env from git.
#   - Branch "staging" on GitHub includes all alembic/versions for this release.
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

  echo ""
  echo "==> Playwright Chromium (IntelX scraper headless shell)..."
  if bash scripts/install_playwright_browsers.sh; then
    echo "    Playwright browsers: OK"
  else
    echo "    WARNING: playwright install failed — Scraper Admin browser fallback will ERROR until fixed." >&2
  fi

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
    echo ""
    echo "==> Navigation RBAC seed (Book Appointment / IntelX / FlowX / Students)..."
    if python scripts/ensure_navigation_rbac.py; then
      echo "    Navigation RBAC: OK"
    else
      echo "    WARNING: ensure_navigation_rbac.py failed — mega-nav may be incomplete." >&2
    fi
    echo ""
    echo "==> Staging login users..."
    if python scripts/seed_staging_users.py; then
      echo "    Staging users: OK"
    else
      echo "    WARNING: seed_staging_users.py failed — create an admin manually." >&2
    fi
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

MISSING_UI=0
for needle in "View Journey" "Future Insights" "ROI Calculator" "Book Appointment"; do
  if grep -rq "${needle}" "${FRONTEND}/dist" 2>/dev/null; then
    echo "    Frontend marker OK: ${needle}"
  else
    echo "    WARNING: '${needle}' not found in dist — UI may be outdated or build failed." >&2
    MISSING_UI=1
  fi
done
if [[ "${MISSING_UI}" -eq 1 ]]; then
  echo "    WARNING: one or more expected UI strings missing from frontend/dist." >&2
fi

echo ""
echo "==> Env presence checks (names only — never print secrets)..."
ENV_FILE="${BACKEND}/.env"
if [[ -f "${ENV_FILE}" ]]; then
  for key in \
    DATABASE_URL FRONTEND_URL PUBLIC_TUNNEL_BASE \
    SMTP_HOST SMTP_USER SMTP_PASSWORD SMTP_FROM_EMAIL \
    WHATSAPP_ACCESS_TOKEN WHATSAPP_BOOKING_TEMPLATE WHATSAPP_ADMIN_BOOKING_TEMPLATE \
    WHATSAPP_BOOKING_TEMPLATE_LANGUAGE WHATSAPP_ADMIN_BOOKING_TEMPLATE_LANGUAGE \
    R2_BUCKET_NAME; do
    if grep -Eq "^${key}=" "${ENV_FILE}"; then
      val="$(grep -E "^${key}=" "${ENV_FILE}" | head -1 | cut -d= -f2-)"
      # redact
      if [[ -z "${val}" ]]; then
        echo "    ${key}: EMPTY"
      elif [[ "${val}" == *"copy from"* || "${val}" == *"placeholder"* || "${val}" == *"<*"* ]]; then
        echo "    ${key}: PLACEHOLDER — replace with real value"
      else
        echo "    ${key}: set (len=${#val})"
      fi
    else
      echo "    ${key}: MISSING"
    fi
  done
  # Soft reminders from prior staging incidents
  if grep -Eq '^R2_BUCKET_NAME=nexus-edutrust$' "${ENV_FILE}"; then
    echo "    WARNING: R2_BUCKET_NAME is shared develop bucket — prefer nexus-edutrust-staging." >&2
  fi
  if grep -Eq '^NEXUS_TUNNEL_ENABLED=true' "${ENV_FILE}"; then
    echo "    WARNING: NEXUS_TUNNEL_ENABLED=true on staging — should be false." >&2
  fi
  if grep -Eq '^FRONTEND_URL=http://127\.0\.0\.1' "${ENV_FILE}"; then
    echo "    WARNING: FRONTEND_URL looks local — expect https://nexus-dev.edutrust.in" >&2
  fi
else
  echo "    WARNING: ${ENV_FILE} missing — do not copy develop .env blindly." >&2
fi

echo ""
echo "==> Restart services..."
if command -v systemctl >/dev/null 2>&1; then
  # Keep service account able to read code/.env and write uploads after root deploys.
  mkdir -p "${BACKEND}/uploads"
  chown -R www-data:www-data "${BACKEND}/uploads" 2>/dev/null || true
  if [[ -f "${BACKEND}/.env" ]]; then
    chown www-data:www-data "${BACKEND}/.env" 2>/dev/null || true
    chmod 640 "${BACKEND}/.env" 2>/dev/null || true
  fi
  # Ensure www-data can import app modules pulled as root.
  chown -R www-data:www-data "${BACKEND}/app" "${BACKEND}/alembic" "${BACKEND}/scripts" 2>/dev/null || true

  systemctl restart nexus-backend
  nginx -t
  systemctl reload nginx

  echo "    Waiting for backend on ${BACKEND_HEALTH_URL} ..."
  backend_ok=0
  for _ in $(seq 1 30); do
    if curl -sf "${BACKEND_HEALTH_URL}" >/dev/null 2>&1; then
      backend_ok=1
      break
    fi
    sleep 2
  done
  if [[ "${backend_ok}" -ne 1 ]]; then
    echo "    ERROR: nexus-backend did not become healthy." >&2
    systemctl --no-pager --full status nexus-backend || true
    journalctl -u nexus-backend -n 80 --no-pager || true
  else
    echo "    Backend is up."
  fi
else
  echo "    systemctl not available; restart nexus-backend manually." >&2
  backend_ok=0
fi

echo ""
echo "==> WhatsApp webhook sync..."
cd "${BACKEND}"
# shellcheck disable=SC1091
source .venv/bin/activate
if [[ "${backend_ok:-0}" -eq 1 ]] && python scripts/sync_whatsapp_webhook.py; then
  echo "    Webhook registered."
else
  echo "    Webhook sync skipped/failed (backend down or WHATSAPP_*/PUBLIC_TUNNEL_BASE)." >&2
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

if curl -sf "https://${PUBLIC_DOMAIN}/api/webhook/info" >/dev/null 2>&1; then
  echo "    Public API proxy: OK (/api/webhook/info)"
else
  echo "    Public API proxy: FAIL — nginx → :8002 may be down" >&2
fi

if [[ -x "${SCRIPT_DIR}/verify-staging-deploy.sh" ]]; then
  echo ""
  bash "${SCRIPT_DIR}/verify-staging-deploy.sh" || true
fi

echo ""
echo "==> Deploy complete at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "    Hard-refresh browser: Ctrl+Shift+R on https://${PUBLIC_DOMAIN}"
