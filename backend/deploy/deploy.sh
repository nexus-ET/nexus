#!/usr/bin/env bash
# Pull latest NEXUS from Git and redeploy (run on VPS after each push).
#
#   sudo bash /var/www/nexus/backend/deploy/deploy.sh
#
# Optional: passwordless sudo for deploy user, or run as root.

set -euo pipefail

APP_ROOT="/var/www/nexus"
GIT_BRANCH="main"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "${SCRIPT_DIR}/deploy.config" ]]; then
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/deploy.config"
fi

BACKEND="${APP_ROOT}/backend"
FRONTEND="${APP_ROOT}/frontend"

if [[ ! -d "${APP_ROOT}/.git" ]]; then
  echo "ERROR: ${APP_ROOT} is not a git repository. Run install.sh first." >&2
  exit 1
fi

echo "==> Pulling ${GIT_BRANCH}..."
cd "$APP_ROOT"
git fetch origin "$GIT_BRANCH"
git checkout "$GIT_BRANCH"
git pull --ff-only origin "$GIT_BRANCH"

echo "==> Backend dependencies..."
cd "$BACKEND"
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -r requirements.txt -q
pip install 'psycopg[binary]' -q

echo "==> Frontend build..."
cd "$FRONTEND"
npm ci
npm run build

echo "==> Restart services..."
if command -v systemctl >/dev/null 2>&1; then
  systemctl restart nexus-backend
  nginx -t
  systemctl reload nginx
fi

chown -R www-data:www-data "$FRONTEND/dist" 2>/dev/null || true

echo "==> Deploy complete at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
curl -sf "http://127.0.0.1:8002/" >/dev/null && echo "    Backend health: OK" || echo "    Backend health: check logs"
