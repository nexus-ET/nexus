#!/usr/bin/env bash
# systemd ExecStart wrapper — loads .env via python-dotenv (see run_nexus_backend.py).
set -euo pipefail
BACKEND_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${BACKEND_ROOT}/.venv/bin/python" "${BACKEND_ROOT}/deploy/run_nexus_backend.py"
