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
# TLS: 若存在 certs/server.{key,crt} 则自动以 HTTPS 启动（任务书 §6.2 要求加密传输）。
#      生成自签证书：
#        mkdir -p certs && openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
#          -keyout certs/server.key -out certs/server.crt \
#          -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
if [ -f certs/server.key ] && [ -f certs/server.crt ]; then
  echo "[2/2] Starting backend on https://${HOST}:${PORT}  (TLS enabled, Ctrl+C to stop)"
  exec "$PY" -m uvicorn app.backend.main:app --host "$HOST" --port "$PORT" \
      --ssl-keyfile certs/server.key --ssl-certfile certs/server.crt
else
  echo "[2/2] Starting backend on http://${HOST}:${PORT}  (no certs/ found - plain HTTP)"
  exec "$PY" -m uvicorn app.backend.main:app --host "$HOST" --port "$PORT"
fi
