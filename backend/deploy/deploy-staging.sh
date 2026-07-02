#!/usr/bin/env bash
# Staging deploy wrapper — ensures staging branch config before deploy.sh runs.
#
#   sudo bash /var/www/nexus/backend/deploy/deploy-staging.sh
#
# Requires deploy.config with GIT_BRANCH=staging (see deploy.config.example).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${SCRIPT_DIR}/deploy.config"

if [[ ! -f "$CONFIG" ]]; then
  echo "ERROR: Missing ${CONFIG}" >&2
  echo "Copy deploy.config.example to deploy.config and set GIT_BRANCH=staging" >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$CONFIG"

if [[ "${GIT_BRANCH:-main}" != "staging" ]]; then
  echo "ERROR: deploy.config GIT_BRANCH=${GIT_BRANCH:-main} — expected 'staging' for this script." >&2
  echo "Edit ${CONFIG} or run deploy.sh directly with the correct branch." >&2
  exit 1
fi

echo "==> Staging deploy (branch=${GIT_BRANCH}, domain=${NEXUS_DOMAIN:-nexus-dev.edutrust.in})"
exec bash "${SCRIPT_DIR}/deploy.sh"
