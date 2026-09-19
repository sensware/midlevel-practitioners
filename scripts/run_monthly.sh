#!/bin/bash
# Wrapper invoked by cron. Reads MLP_REPO_DIR from .env so no machine-specific
# path needs to be hardcoded in the crontab entry or in README.md.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR_FALLBACK="$(dirname "$SCRIPT_DIR")"

if [ -f "$REPO_DIR_FALLBACK/.env" ]; then
  set -a
  source "$REPO_DIR_FALLBACK/.env"
  set +a
fi

REPO_DIR="${MLP_REPO_DIR:-$REPO_DIR_FALLBACK}"
cd "$REPO_DIR"
mkdir -p logs
exec /usr/bin/python3 scripts/run_monthly.py >> "logs/cron_$(date +%Y-%m).log" 2>&1
