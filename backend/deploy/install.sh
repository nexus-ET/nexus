#!/usr/bin/env bash
# One-time Hostinger VPS bootstrap: clone NEXUS from Git, install deps, nginx, systemd.
#
# Run on the VPS as a user with sudo:
#   curl -fsSL https://raw.githubusercontent.com/YOUR_USER/nexus/main/backend/deploy/install.sh | bash -s -- \
#     --repo https://github.com/YOUR_USER/nexus.git \
#     --domain nexus.yourdomain.com \
#     --branch main
#
# Or after cloning manually:
#   cd /var/www/nexus && sudo bash backend/deploy/install.sh --domain nexus.yourdomain.com

set -euo pipefail

APP_ROOT="/var/www/nexus"
GIT_BRANCH="main"
NEXUS_DOMAIN=""
GIT_REPO=""
RUN_CERTBOT="0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'EOF'
Usage: install.sh [options]

Options:
  --repo URL          Git remote to clone (required if APP_ROOT is empty)
  --domain HOST       Public hostname, e.g. nexus.example.com (required)
  --branch NAME       Git branch (default: main)
  --app-root PATH     Install path (default: /var/www/nexus)
  --certbot           Run certbot after nginx is configured
  -h, --help          Show this help

Example:
  sudo bash backend/deploy/install.sh \
    --repo https://github.com/you/nexus.git \
    --domain nexus.example.com \
    --certbot
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) GIT_REPO="$2"; shift 2 ;;
    --domain) NEXUS_DOMAIN="$2"; shift 2 ;;
    --branch) GIT_BRANCH="$2"; shift 2 ;;
    --app-root) APP_ROOT="$2"; shift 2 ;;
    --certbot) RUN_CERTBOT="1"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ -f "${SCRIPT_DIR}/deploy.config" ]]; then
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/deploy.config"
fi

if [[ -z "$NEXUS_DOMAIN" ]]; then
  echo "ERROR: --domain is required (e.g. nexus.yourdomain.com)" >&2
  exit 1
fi

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: run with sudo" >&2
  exit 1
fi

echo "==> Installing system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  python3 python3-venv python3-pip \
  nginx certbot python3-certbot-nginx \
  git curl ca-certificates

if ! command -v node >/dev/null 2>&1 || [[ "$(node -v | cut -d. -f1 | tr -d v)" -lt 18 ]]; then
  echo "==> Installing Node.js 20..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y -qq nodejs
fi

echo "==> Preparing ${APP_ROOT}..."
mkdir -p "$(dirname "$APP_ROOT")"
if [[ ! -d "${APP_ROOT}/.git" ]]; then
  if [[ -z "$GIT_REPO" ]]; then
    echo "ERROR: ${APP_ROOT} is not a git repo. Pass --repo URL." >&2
    exit 1
  fi
  git clone --branch "$GIT_BRANCH" --depth 1 "$GIT_REPO" "$APP_ROOT"
else
  echo "    Git repo already exists — skipping clone"
fi

cd "$APP_ROOT"
git fetch origin "$GIT_BRANCH" || true
git checkout "$GIT_BRANCH" || true
git pull origin "$GIT_BRANCH" || true

BACKEND="${APP_ROOT}/backend"
FRONTEND="${APP_ROOT}/frontend"
ENV_FILE="${BACKEND}/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "==> Creating ${ENV_FILE} from template..."
  cp "${BACKEND}/deploy/env.production.example" "$ENV_FILE"
  sed -i "s|nexus.YOUR_DOMAIN.com|${NEXUS_DOMAIN}|g" "$ENV_FILE"
  sed -i "s|YOUR_DOMAIN.com|${NEXUS_DOMAIN#*.}|g" "$ENV_FILE" 2>/dev/null || true
  echo ""
  echo "IMPORTANT: Edit secrets before going live:"
  echo "  nano ${ENV_FILE}"
  echo ""
fi

echo "==> Python backend venv..."
cd "$BACKEND"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
pip install 'psycopg[binary]' -q

echo "==> Building frontend..."
cd "$FRONTEND"
npm ci
npm run build

echo "==> systemd service..."
cp "${BACKEND}/deploy/nexus-backend.service" /etc/systemd/system/nexus-backend.service
systemctl daemon-reload
systemctl enable nexus-backend
systemctl restart nexus-backend

echo "==> nginx site..."
sed "s|__NEXUS_DOMAIN__|${NEXUS_DOMAIN}|g" \
  "${BACKEND}/deploy/nginx-site.conf.template" \
  > "/etc/nginx/sites-available/nexus"
ln -sf /etc/nginx/sites-available/nexus /etc/nginx/sites-enabled/nexus
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

chown -R www-data:www-data "$APP_ROOT/frontend/dist"
chown -R www-data:www-data "$BACKEND"
chmod 600 "$ENV_FILE" 2>/dev/null || true

if [[ "$RUN_CERTBOT" == "1" ]]; then
  echo "==> HTTPS via certbot..."
  certbot --nginx -d "$NEXUS_DOMAIN" --non-interactive --agree-tos -m "admin@${NEXUS_DOMAIN}" || \
    certbot --nginx -d "$NEXUS_DOMAIN"
fi

echo ""
echo "=============================================="
echo " NEXUS install complete"
echo " Site:     http://${NEXUS_DOMAIN}"
echo " Webhook:  https://${NEXUS_DOMAIN}/api/webhook"
echo " Deploy:   sudo bash ${BACKEND}/deploy/deploy.sh"
echo "=============================================="
echo ""
echo "Next steps:"
echo "  1. nano ${ENV_FILE}   # DATABASE_URL, WhatsApp tokens, SECRET_KEY"
echo "  2. Point DNS A record: ${NEXUS_DOMAIN} -> this server's IP"
if [[ "$RUN_CERTBOT" != "1" ]]; then
  echo "  3. sudo certbot --nginx -d ${NEXUS_DOMAIN}"
fi
echo "  4. Set Meta webhook to https://${NEXUS_DOMAIN}/api/webhook"
echo "  5. sudo systemctl restart nexus-backend"
