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

# ── Virtual environment ──────────────────────────────────────────────────────
# macOS Homebrew Python enforces PEP 668 and does not expose a bare `pip` or
# `python` command.  We use a local .venv so installs always work.
if [ ! -d ".venv" ]; then
  echo "[pit-wall] creating virtual environment in .venv…"
  python3 -m venv .venv
fi
# shellcheck source=/dev/null
source .venv/bin/activate

# ── Backend deps ─────────────────────────────────────────────────────────────
if ! python3 -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  echo "[pit-wall] installing backend deps (fastapi, uvicorn)…"
  python3 -m pip install -q -r dashboard/backend/requirements.txt
fi

# ── Ensure frontend deps ─────────────────────────────────────────────────────
if [ ! -d "dashboard/frontend/node_modules" ]; then
  echo "[pit-wall] installing frontend deps (npm install)…"
  ( cd dashboard/frontend && npm install --silent )
fi

# ── Kill stale processes on reserved ports ───────────────────────────────────
for PORT in 8765 5173; do
  OLD_PID=$(lsof -ti tcp:"$PORT" 2>/dev/null || true)
  if [ -n "$OLD_PID" ]; then
    echo "[pit-wall] killing stale process on port $PORT (pid $OLD_PID)…"
    kill "$OLD_PID" 2>/dev/null || true
    sleep 0.5
  fi
done

echo "[pit-wall] starting backend  -> http://localhost:8765"
( PYTHONPATH="$REPO_ROOT" python3 -m uvicorn dashboard.backend.server:app \
    --host 0.0.0.0 --port 8765 --reload ) &
BACK_PID=$!

echo "[pit-wall] starting frontend -> http://localhost:5173"
( cd dashboard/frontend && npm run dev -- --host 0.0.0.0 ) &
FRONT_PID=$!

trap 'echo "[pit-wall] shutting down"; kill $BACK_PID $FRONT_PID 2>/dev/null || true; wait 2>/dev/null || true' INT TERM

wait
