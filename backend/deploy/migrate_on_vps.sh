#!/usr/bin/env bash
# Run database bootstrap/migrations ON the Hostinger VPS where Postgres is reachable.
#
# Hostinger KVM Postgres listens on 127.0.0.1:5432 (or hPanel host) — port 5432 is
# NOT open to the public internet. Running verify_staging_database.py --migrate from
# a Windows PC against 187.127.186.63:5432 will hang after "Environment: dev".
#
# Usage (SSH into VPS):
#   sudo bash /var/www/nexus/backend/deploy/migrate_on_vps.sh
#   sudo bash /var/www/nexus/backend/deploy/migrate_on_vps.sh --env dev
#   sudo bash /var/www/nexus/backend/deploy/migrate_on_vps.sh --env staging
#
# Prerequisites:
#   - /var/www/nexus/backend/.env has DATABASE_URL pointing at 127.0.0.1:5432 (or local hPanel host)
#   - Python venv at /var/www/nexus/backend/.venv
#   - develop branch checked out (or path you pass via NEXUS_BACKEND)

set -euo pipefail

APP_ROOT="${NEXUS_APP_ROOT:-/var/www/nexus}"
BACKEND="${NEXUS_BACKEND:-${APP_ROOT}/backend}"
ENV_LABEL="auto"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      ENV_LABEL="${2:-auto}"
      shift 2
      ;;
    -h|--help)
      sed -n '2,14p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

if [[ ! -d "${BACKEND}" ]]; then
  echo "ERROR: backend directory not found: ${BACKEND}" >&2
  exit 1
fi

if [[ ! -f "${BACKEND}/.env" ]]; then
  echo "ERROR: ${BACKEND}/.env missing — create it with DATABASE_URL (127.0.0.1:5432)." >&2
  exit 1
fi

cd "${BACKEND}"

if [[ ! -d .venv ]]; then
  echo "==> Creating Python venv..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
pip install -r requirements.txt -q
pip install 'psycopg[binary]' -q

VERIFY_ARGS=(scripts/verify_staging_database.py --migrate)
if [[ "${ENV_LABEL}" != "auto" ]]; then
  VERIFY_ARGS+=(--env "${ENV_LABEL}")
fi

echo "==> Verify + migrate (${ENV_LABEL})..."
python "${VERIFY_ARGS[@]}"
echo ""
echo "==> Post-migration seeds (safe to re-run)..."
python scripts/ensure_navigation_rbac.py
python scripts/ensure_id_sequences.py
echo ""
echo "Done. Alembic head should be zz6a7bbizctc (or current develop head); public tables ~110."
