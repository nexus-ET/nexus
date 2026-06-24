#!/usr/bin/env bash
# Optional: push-to-deploy bare Git repo on the VPS.
# After setup, from your PC:
#   git remote add production ssh://root@YOUR_VPS_IP/var/repo/nexus.git
#   git push production main
#
# Run once on VPS:
#   sudo bash backend/deploy/setup-bare-repo.sh

set -euo pipefail

APP_ROOT="/var/www/nexus"
BARE_REPO="/var/repo/nexus.git"
GIT_BRANCH="main"
DEPLOY_USER="${SUDO_USER:-root}"

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: run with sudo" >&2
  exit 1
fi

mkdir -p "$(dirname "$BARE_REPO")" "$APP_ROOT"

if [[ ! -d "${BARE_REPO}/HEAD" ]]; then
  git init --bare "$BARE_REPO"
fi

HOOK="${BARE_REPO}/hooks/post-receive"
cat > "$HOOK" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export GIT_WORK_TREE="${APP_ROOT}"
export GIT_DIR="${BARE_REPO}"
git checkout -f ${GIT_BRANCH}
bash "${APP_ROOT}/backend/deploy/deploy.sh"
EOF
chmod +x "$HOOK"
chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "$BARE_REPO" 2>/dev/null || true

echo ""
echo "Bare repo ready: ${BARE_REPO}"
echo ""
echo "On your PC (from E:\\NEXUS):"
echo "  git remote add production ssh://${DEPLOY_USER}@YOUR_VPS_IP${BARE_REPO}"
echo "  git push production main"
echo ""
echo "Ensure ${APP_ROOT} exists and install.sh has been run once before first push."
