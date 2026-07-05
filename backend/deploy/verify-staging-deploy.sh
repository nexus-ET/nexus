#!/usr/bin/env bash
# Post-deploy verification for Nexus-Staging (run on VPS after deploy.sh).
#
#   sudo bash /var/www/nexus/backend/deploy/verify-staging-deploy.sh
#
# Exit code 0 = all checks passed; non-zero = at least one failure.

set -euo pipefail

APP_ROOT="/var/www/nexus"
BACKEND="${APP_ROOT}/backend"
EXPECTED_HEAD="s5p8q1r54s0m"
BACKEND_HEALTH="http://127.0.0.1:8002/"
PUBLIC_DOMAIN="${NEXUS_DOMAIN:-nexus-dev.edutrust.in}"
PUBLIC_BASE="https://${PUBLIC_DOMAIN}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/deploy.config" ]]; then
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/deploy.config"
  PUBLIC_DOMAIN="${NEXUS_DOMAIN:-$PUBLIC_DOMAIN}"
  PUBLIC_BASE="https://${PUBLIC_DOMAIN}"
fi

failures=0

check() {
  local label="$1"
  shift
  if "$@"; then
    echo "  OK   ${label}"
  else
    echo "  FAIL ${label}" >&2
    failures=$((failures + 1))
  fi
}

echo "==> Nexus-Staging verification ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
echo "    Domain: ${PUBLIC_DOMAIN}"
echo ""

echo "==> Git"
check "On staging branch" bash -c "cd '${APP_ROOT}' && git rev-parse --abbrev-ref HEAD | grep -qx staging"

echo ""
echo "==> Backend service"
if command -v systemctl >/dev/null 2>&1; then
  check "nexus-backend active" systemctl is-active --quiet nexus-backend
else
  echo "  SKIP systemctl (not available)"
fi

echo ""
echo "==> HTTP health"
check "Backend ${BACKEND_HEALTH}" curl -sf "${BACKEND_HEALTH}" >/dev/null
check "Public ${PUBLIC_BASE}/" curl -sf "${PUBLIC_BASE}/" >/dev/null
check "Webhook info ${PUBLIC_BASE}/api/webhook/info" curl -sf "${PUBLIC_BASE}/api/webhook/info" >/dev/null

echo ""
echo "==> Database (Alembic)"
if [[ -d "${BACKEND}/.venv" ]]; then
  current_head="$(
    bash -c "cd '${BACKEND}' && source .venv/bin/activate && alembic current 2>/dev/null" \
      | awk '{print $1}' | head -1
  )"
  if [[ "${current_head}" == "${EXPECTED_HEAD}" ]]; then
    echo "  OK   Alembic head is ${EXPECTED_HEAD}"
  else
    echo "  FAIL Alembic head is '${current_head}' (expected ${EXPECTED_HEAD})" >&2
    failures=$((failures + 1))
  fi
else
  echo "  FAIL Backend venv not found at ${BACKEND}/.venv" >&2
  failures=$((failures + 1))
fi

echo ""
echo "==> Status API"
check "GET /api/v1/leads/status-definitions" curl -sf "${PUBLIC_BASE}/api/v1/leads/status-definitions" >/dev/null

echo ""
echo "==> WhatsApp webhook ownership"
if [[ -d "${BACKEND}/.venv" ]]; then
  if bash -c "cd '${BACKEND}' && source .venv/bin/activate && python scripts/sync_whatsapp_webhook.py --status" 2>/dev/null | grep -q 'owned_by_this_environment: true'; then
    echo "  OK   Webhook owned by this environment"
  else
    echo "  WARN Webhook not owned by this environment (check PUBLIC_TUNNEL_BASE and WHATSAPP_* in .env)" >&2
    failures=$((failures + 1))
  fi
else
  echo "  SKIP WhatsApp check (no venv)"
fi

echo ""
if (( failures == 0 )); then
  echo "==> All checks passed."
  exit 0
fi

echo "==> ${failures} check(s) failed. See STAGING_RELEASE_2026-07-03.md for troubleshooting." >&2
exit 1
