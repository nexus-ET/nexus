#!/usr/bin/env bash
# Clear WhatsApp message history for a lead on the VPS (staging/production).
#
# Preview (no changes):
#   sudo bash /var/www/nexus/backend/deploy/clear-whatsapp-messages.sh +918754545407 --dry-run
#
# Apply:
#   sudo bash /var/www/nexus/backend/deploy/clear-whatsapp-messages.sh +918754545407 --yes
#
# By lead id:
#   sudo bash /var/www/nexus/backend/deploy/clear-whatsapp-messages.sh --lead-id 27 --yes

set -euo pipefail

APP_ROOT="/var/www/nexus"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "${SCRIPT_DIR}/deploy.config" ]]; then
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/deploy.config"
fi

BACKEND="${APP_ROOT}/backend"

if [[ ! -d "${BACKEND}/.venv" ]]; then
  echo "ERROR: ${BACKEND}/.venv not found. Run install.sh first." >&2
  exit 1
fi

cd "${BACKEND}"
# shellcheck disable=SC1091
source .venv/bin/activate
exec python scripts/clear_whatsapp_messages.py "$@"
