#!/usr/bin/env bash
# Run the cinematic Kalshi pit-wall dashboard.
#
# This launches:
#   1. The FastAPI backend on http://localhost:8765 (reads data/trades.db)
#   2. The Vite dev server on http://localhost:5173
#
# Both run in the foreground until you Ctrl+C; the script forwards the signal.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." &> /dev/null && pwd)"

cd "$REPO_ROOT"

# Ensure backend deps.
if ! python -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  echo "[pit-wall] installing backend deps (fastapi, uvicorn)…"
  pip install -q -r dashboard/backend/requirements.txt
fi

# Ensure frontend deps.
if [ ! -d "dashboard/frontend/node_modules" ]; then
  echo "[pit-wall] installing frontend deps (npm install)…"
  ( cd dashboard/frontend && npm install --silent )
fi

echo "[pit-wall] starting backend  -> http://localhost:8765"
( PYTHONPATH="$REPO_ROOT" python -m uvicorn dashboard.backend.server:app \
    --host 0.0.0.0 --port 8765 --reload ) &
BACK_PID=$!

echo "[pit-wall] starting frontend -> http://localhost:5173"
( cd dashboard/frontend && npm run dev -- --host 0.0.0.0 ) &
FRONT_PID=$!

trap 'echo "[pit-wall] shutting down"; kill $BACK_PID $FRONT_PID 2>/dev/null || true; wait 2>/dev/null || true' INT TERM

wait
