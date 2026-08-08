#!/usr/bin/env bash
# Post-deploy verification for Nexus-Staging (run on VPS after hostinger-staging.sh).
#
#   sudo bash /var/www/nexus/backend/deploy/verify-staging-deploy.sh
#
# Exit code 0 = all checks passed; non-zero = at least one failure.
# This script MUST fail the deploy when critical gates fail (do not wrap with || true).

set -euo pipefail

APP_ROOT="/var/www/nexus"
BACKEND="${APP_ROOT}/backend"
FRONTEND="${APP_ROOT}/frontend"
EXPECTED_HEAD=""
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
check "Clean enough working tree (no conflict markers in app)" \
  bash -c "! grep -R \"<<<<<<<\" '${BACKEND}/app' '${FRONTEND}/src' 2>/dev/null | head -1 | grep -q ."

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
# OpenAPI is optional on some nginx configs; prefer loopback.
if curl -sf "http://127.0.0.1:8002/openapi.json" >/dev/null 2>&1; then
  echo "  OK   OpenAPI (loopback)"
else
  echo "  WARN OpenAPI not exposed on loopback (non-blocking)"
fi

echo ""
echo "==> Frontend dist markers (2026-08-08 regressions)"
DIST="${FRONTEND}/dist"
if [[ -d "${DIST}" ]]; then
  for needle in \
    "Book Appointment" \
    "Future Insights" \
    "ROI Calculator" \
    "View Journey" \
    "Exception Report" \
    "Aspirations"; do
    if grep -rq "${needle}" "${DIST}" 2>/dev/null; then
      echo "  OK   dist contains: ${needle}"
    else
      echo "  FAIL dist missing: ${needle}" >&2
      failures=$((failures + 1))
    fi
  done
else
  echo "  FAIL frontend/dist missing" >&2
  failures=$((failures + 1))
fi

echo ""
echo "==> Database (Alembic)"
if [[ -d "${BACKEND}/.venv" ]]; then
  EXPECTED_HEAD="$(
    bash -c "cd '${BACKEND}' && source .venv/bin/activate && alembic heads 2>/dev/null" \
      | awk '{print $1}' | head -1
  )"
  head_count="$(
    bash -c "cd '${BACKEND}' && source .venv/bin/activate && alembic heads 2>/dev/null" \
      | awk 'NF{print $1}' | wc -l | tr -d ' '
  )"
  current_head="$(
    bash -c "cd '${BACKEND}' && source .venv/bin/activate && alembic current 2>/dev/null" \
      | awk '{print $1}' | head -1
  )"
  if [[ -z "${EXPECTED_HEAD}" ]]; then
    echo "  FAIL Could not resolve alembic heads" >&2
    failures=$((failures + 1))
  elif [[ "${head_count}" != "1" ]]; then
    echo "  FAIL Alembic has ${head_count} heads (need exactly 1)" >&2
    failures=$((failures + 1))
  elif [[ "${current_head}" == "${EXPECTED_HEAD}" ]]; then
    echo "  OK   Alembic at head ${EXPECTED_HEAD}"
  else
    echo "  FAIL Alembic current '${current_head}' (expected head ${EXPECTED_HEAD})" >&2
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
    echo "  FAIL Webhook not owned by this environment (check PUBLIC_TUNNEL_BASE and WHATSAPP_* in .env)" >&2
    failures=$((failures + 1))
  fi
else
  echo "  SKIP WhatsApp webhook check (no venv)"
fi

echo ""
echo "==> Post-deploy smoke (sequences, Meta booking templates, API)"
if [[ -d "${BACKEND}/.venv" ]]; then
  set +e
  bash -c "cd '${BACKEND}' && source .venv/bin/activate && \
    export FRONTEND_URL='${PUBLIC_BASE}' STAGING_SMOKE_BASE_URL='${PUBLIC_BASE}' && \
    python scripts/staging_post_deploy_smoke.py --base-url '${PUBLIC_BASE}'"
  smoke_rc=$?
  set -e
  if [[ "${smoke_rc}" -eq 0 ]]; then
    echo "  OK   staging_post_deploy_smoke.py"
  else
    echo "  FAIL staging_post_deploy_smoke.py (exit ${smoke_rc})" >&2
    failures=$((failures + 1))
  fi
else
  echo "  FAIL cannot run smoke — no venv" >&2
  failures=$((failures + 1))
fi

echo ""
if (( failures == 0 )); then
  echo "==> All checks passed."
  exit 0
fi

echo "==> ${failures} check(s) failed." >&2
echo "    See STAGING_DEPLOYMENT_AGENT_PROMPT.md §H (2026-08-08) and run:" >&2
echo "      python scripts/ensure_id_sequences.py" >&2
echo "      python scripts/ensure_navigation_rbac.py" >&2
echo "      python scripts/register_whatsapp_booking_templates.py   # BUSINESS WABA" >&2
echo "      python scripts/staging_post_deploy_smoke.py" >&2
exit 1
