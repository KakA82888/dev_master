#!/usr/bin/env bash
# One-click start for Linux / macOS / Git Bash.
# Builds the frontend when needed, then serves API + web UI on a single port.
#
# Usage:
#   bash scripts/start.sh            # skip build if app/frontend/dist exists
#   bash scripts/start.sh --build    # force rebuild frontend
#   PYTHON=python3.13 bash scripts/start.sh
#   APP_HOST=0.0.0.0 APP_PORT=8080 bash scripts/start.sh
set -euo pipefail

cd "$(dirname "$0")/.."          # move to project root (parent of scripts/)

PY="${PYTHON:-python}"
HOST="${APP_HOST:-127.0.0.1}"
PORT="${APP_PORT:-8000}"

# --- Step 1: frontend build -------------------------------------------------
# The backend mounts app/frontend/dist statically, so a stale/missing dist
# means the UI will not load. Build it automatically on first run.
if [ ! -f app/frontend/dist/index.html ] || [ "${1:-}" = "--build" ]; then
  echo "[1/2] Building frontend (npm install && npm run build) ..."
  ( cd app/frontend && npm install && npm run build )
else
  echo "[1/2] Frontend dist found - skipping build (use --build to force rebuild)"
fi

# --- Step 2: start backend (serves API + dist) ------------------------------
echo "[2/2] Starting backend on http://${HOST}:${PORT}  (Ctrl+C to stop)"
exec "$PY" -m uvicorn app.backend.main:app --host "$HOST" --port "$PORT"
