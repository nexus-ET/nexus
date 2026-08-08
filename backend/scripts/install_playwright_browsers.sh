#!/usr/bin/env bash
# Install Playwright Chromium / chrome-headless-shell for IntelX scraper browser fallback.
# Safe to re-run; downloads only if missing or outdated.
#
# Usage (from backend venv):
#   bash scripts/install_playwright_browsers.sh
#   bash scripts/install_playwright_browsers.sh --with-deps   # Linux bootstrap (needs apt)

set -euo pipefail

WITH_DEPS=0
if [[ "${1:-}" == "--with-deps" ]]; then
  WITH_DEPS=1
fi

if ! python -c "import playwright" >/dev/null 2>&1; then
  echo "ERROR: playwright package not installed. Run: pip install -r requirements.txt" >&2
  exit 1
fi

echo "==> Installing Playwright Chromium (chrome-headless-shell)..."
if [[ "$WITH_DEPS" -eq 1 ]]; then
  python -m playwright install --with-deps chromium
else
  python -m playwright install chromium
fi
echo "    Playwright Chromium: OK"
