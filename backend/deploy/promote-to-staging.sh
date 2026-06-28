#!/usr/bin/env bash
# Promote develop -> staging (Linux / VPS / Git Bash).
#
#   bash backend/deploy/promote-to-staging.sh
#   bash backend/deploy/promote-to-staging.sh --message "fix webhook" --vps root@YOUR_VPS_IP
#
set -euo pipefail

MESSAGE="Promote develop to staging"
DEVELOP_BRANCH="develop"
STAGING_BRANCH="staging"
VPS_HOST=""
SKIP_DEVELOP_PUSH=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --message) MESSAGE="$2"; shift 2 ;;
    --vps) VPS_HOST="$2"; shift 2 ;;
    --skip-develop-push) SKIP_DEVELOP_PUSH=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

run_git() {
  echo "  git $*"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    git "$@"
  fi
}

echo "=== NEXUS: promote ${DEVELOP_BRANCH} -> ${STAGING_BRANCH} ==="

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Committing changes on ${DEVELOP_BRANCH}..."
  run_git add -A
  run_git commit -m "$MESSAGE"
else
  echo "No uncommitted changes on ${DEVELOP_BRANCH}."
fi

if [[ "$SKIP_DEVELOP_PUSH" -eq 0 ]]; then
  echo "Pushing ${DEVELOP_BRANCH}..."
  run_git push origin "$DEVELOP_BRANCH"
fi

echo "Merging into ${STAGING_BRANCH}..."
run_git fetch origin "$DEVELOP_BRANCH" "$STAGING_BRANCH"
run_git checkout "$STAGING_BRANCH"
if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: staging branch has uncommitted changes." >&2
  exit 1
fi
run_git merge "origin/${DEVELOP_BRANCH}" -m "$MESSAGE"
run_git push origin "$STAGING_BRANCH"

if [[ -n "$VPS_HOST" ]]; then
  echo "Deploying on VPS..."
  if [[ "$DRY_RUN" -eq 0 ]]; then
    ssh "$VPS_HOST" "sudo bash /var/www/nexus/backend/deploy/deploy.sh"
  fi
fi

echo "=== Done ==="
echo "GitHub origin/${STAGING_BRANCH} updated."
