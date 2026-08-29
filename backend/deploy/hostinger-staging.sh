#!/usr/bin/env bash
# Complete NEXUS staging deploy for Hostinger VPS.
#
# Prerequisites:
#   - /var/www/nexus/backend/.env points DATABASE_URL at Hostinger KVM 1 Postgres
#     (nexus_edutrust / nexus_et_admin). See setup_staging_db.md — do not overwrite .env from git.
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

DEPLOY_FAILURES=0

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
      echo "    ERROR: ensure_navigation_rbac.py failed — mega-nav may be incomplete." >&2
      DEPLOY_FAILURES=$((DEPLOY_FAILURES + 1))
    fi
    echo ""
    echo "==> Heal Postgres id sequences (import desync guard)..."
    if python scripts/ensure_id_sequences.py; then
      echo "    id sequences: OK"
    else
      echo "    ERROR: ensure_id_sequences.py failed — TOEFL/booking inserts may 500." >&2
      DEPLOY_FAILURES=$((DEPLOY_FAILURES + 1))
    fi
    # Keep legacy alias script for one-release compatibility.
    python scripts/ensure_candidate_test_scores_sequence.py >/dev/null 2>&1 || true
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

DEPLOY_FAILURES="${DEPLOY_FAILURES:-0}"

echo ""
echo "==> Frontend build..."
cd "${FRONTEND}"
npm ci
npm run build

MISSING_UI=0
for needle in \
  "View Journey" \
  "Future Insights" \
  "ROI Calculator" \
  "Book Appointment" \
  "Exception Report" \
  "Aspirations"; do
  if grep -rq "${needle}" "${FRONTEND}/dist" 2>/dev/null; then
    echo "    Frontend marker OK: ${needle}"
  else
    echo "    ERROR: '${needle}' not found in dist — UI may be outdated or build failed." >&2
    MISSING_UI=1
    DEPLOY_FAILURES=$((DEPLOY_FAILURES + 1))
  fi
done

echo ""
echo "==> Env presence checks (names only — never print secrets)..."
ENV_FILE="${BACKEND}/.env"
CRITICAL_ENV_MISSING=0
if [[ -f "${ENV_FILE}" ]]; then
  for key in \
    DATABASE_URL FRONTEND_URL PUBLIC_TUNNEL_BASE \
    SMTP_HOST SMTP_USER SMTP_PASSWORD SMTP_FROM_EMAIL \
    WHATSAPP_ACCESS_TOKEN WHATSAPP_BOOKING_TEMPLATE WHATSAPP_ADMIN_BOOKING_TEMPLATE \
    WHATSAPP_BOOKING_TEMPLATE_LANGUAGE WHATSAPP_ADMIN_BOOKING_TEMPLATE_LANGUAGE \
    WHATSAPP_BUSINESS_WABA_ID WHATSAPP_BUSINESS_PHONE_NUMBER_ID \
    R2_BUCKET_NAME; do
    if grep -Eq "^${key}=" "${ENV_FILE}"; then
      val="$(grep -E "^${key}=" "${ENV_FILE}" | head -1 | cut -d= -f2-)"
      if [[ -z "${val}" ]]; then
        echo "    ERROR: ${key}: EMPTY" >&2
        CRITICAL_ENV_MISSING=1
        DEPLOY_FAILURES=$((DEPLOY_FAILURES + 1))
      elif [[ "${val}" == *"copy from"* || "${val}" == *"placeholder"* || "${val}" == *"<*"* ]]; then
        echo "    ERROR: ${key}: PLACEHOLDER — replace with real value" >&2
        CRITICAL_ENV_MISSING=1
        DEPLOY_FAILURES=$((DEPLOY_FAILURES + 1))
      else
        echo "    ${key}: set (len=${#val})"
      fi
    else
      echo "    ERROR: ${key}: MISSING" >&2
      CRITICAL_ENV_MISSING=1
      DEPLOY_FAILURES=$((DEPLOY_FAILURES + 1))
    fi
  done
  if grep -Eq '^R2_BUCKET_NAME=nexus-edutrust$' "${ENV_FILE}"; then
    echo "    WARNING: R2_BUCKET_NAME is shared develop bucket — prefer nexus-edutrust-staging." >&2
  fi
  if grep -Eq '^NEXUS_TUNNEL_ENABLED=true' "${ENV_FILE}"; then
    echo "    ERROR: NEXUS_TUNNEL_ENABLED=true on staging — must be false." >&2
    DEPLOY_FAILURES=$((DEPLOY_FAILURES + 1))
  fi
  if grep -Eq '^FRONTEND_URL=http://127\.0\.0\.1' "${ENV_FILE}"; then
    echo "    ERROR: FRONTEND_URL looks local — expect https://nexus-dev.edutrust.in" >&2
    DEPLOY_FAILURES=$((DEPLOY_FAILURES + 1))
  fi
  # Soft tip: API smoke needs credentials on the VPS.
  if ! grep -Eq '^STAGING_SMOKE_EMAIL=' "${ENV_FILE}" && ! grep -Eq '^UAT_EMAIL=' "${ENV_FILE}"; then
    echo "    WARNING: set STAGING_SMOKE_EMAIL/PASSWORD (or UAT_*) in .env for booking/TOEFL API smoke." >&2
  fi
else
  echo "    ERROR: ${ENV_FILE} missing — do not copy develop .env blindly." >&2
  DEPLOY_FAILURES=$((DEPLOY_FAILURES + 1))
fi

echo ""
echo "==> Restart services..."
backend_ok=0
if command -v systemctl >/dev/null 2>&1; then
  mkdir -p "${BACKEND}/uploads"
  chown -R www-data:www-data "${BACKEND}/uploads" 2>/dev/null || true
  if [[ -f "${BACKEND}/.env" ]]; then
    chown www-data:www-data "${BACKEND}/.env" 2>/dev/null || true
    chmod 640 "${BACKEND}/.env" 2>/dev/null || true
  fi
  chown -R www-data:www-data "${BACKEND}/app" "${BACKEND}/alembic" "${BACKEND}/scripts" 2>/dev/null || true
  chmod +x "${BACKEND}/deploy/run-nexus-backend.sh" 2>/dev/null || true
  if [[ -f "${BACKEND}/deploy/nexus-backend.service" ]]; then
    cp "${BACKEND}/deploy/nexus-backend.service" /etc/systemd/system/nexus-backend.service
    systemctl daemon-reload
  fi

  systemctl restart nexus-backend
  nginx -t
  systemctl reload nginx

  echo "    Waiting for backend on ${BACKEND_HEALTH_URL} ..."
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
    DEPLOY_FAILURES=$((DEPLOY_FAILURES + 1))
  else
    echo "    Backend is up."
  fi
else
  echo "    systemctl not available; restart nexus-backend manually." >&2
fi

echo ""
echo "==> WhatsApp webhook sync..."
cd "${BACKEND}"
# shellcheck disable=SC1091
source .venv/bin/activate
if [[ "${backend_ok}" -eq 1 ]] && python scripts/sync_whatsapp_webhook.py; then
  echo "    Webhook registered."
else
  echo "    ERROR: Webhook sync skipped/failed (backend down or WHATSAPP_*/PUBLIC_TUNNEL_BASE)." >&2
  DEPLOY_FAILURES=$((DEPLOY_FAILURES + 1))
fi

chown -R www-data:www-data "${FRONTEND}/dist" 2>/dev/null || true

echo ""
echo "==> Health checks..."
if curl -sf "${BACKEND_HEALTH_URL}" >/dev/null 2>&1; then
  echo "    Backend: OK (${BACKEND_HEALTH_URL})"
else
  echo "    Backend: NOT responding — check journalctl -u nexus-backend -n 50" >&2
  DEPLOY_FAILURES=$((DEPLOY_FAILURES + 1))
fi

if curl -sf "https://${PUBLIC_DOMAIN}/" >/dev/null 2>&1; then
  echo "    Public site: OK (https://${PUBLIC_DOMAIN}/)"
else
  echo "    Public site: check nginx / DNS" >&2
  DEPLOY_FAILURES=$((DEPLOY_FAILURES + 1))
fi

if curl -sf "https://${PUBLIC_DOMAIN}/api/webhook/info" >/dev/null 2>&1; then
  echo "    Public API proxy: OK (/api/webhook/info)"
else
  echo "    Public API proxy: FAIL — nginx → :8002 may be down" >&2
  DEPLOY_FAILURES=$((DEPLOY_FAILURES + 1))
fi

echo ""
echo "==> Hard verify (must pass — 2026-08-08 post-deploy gate)..."
if [[ -x "${SCRIPT_DIR}/verify-staging-deploy.sh" ]]; then
  if bash "${SCRIPT_DIR}/verify-staging-deploy.sh"; then
    echo "    verify-staging-deploy: OK"
  else
    echo "    ERROR: verify-staging-deploy.sh failed." >&2
    DEPLOY_FAILURES=$((DEPLOY_FAILURES + 1))
  fi
else
  echo "    ERROR: verify-staging-deploy.sh missing or not executable" >&2
  DEPLOY_FAILURES=$((DEPLOY_FAILURES + 1))
fi

echo ""
if [[ "${DEPLOY_FAILURES}" -gt 0 ]]; then
  echo "==> Deploy finished WITH ${DEPLOY_FAILURES} failure(s) at $(date -u +%Y-%m-%dT%H:%M:%SZ)" >&2
  echo "    Do not hand off to BAU until verify-staging-deploy.sh and staging_post_deploy_smoke.py are green." >&2
  exit 1
fi

echo "==> Deploy complete at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "    Hard-refresh browser: Ctrl+Shift+R on https://${PUBLIC_DOMAIN}"
exit 0