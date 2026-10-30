#!/usr/bin/env bash
# Start the EduShield AI API (port 8000) and web client (port 5173) together.
# Uses backend/.env if present; otherwise falls back to a local SQLite database.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

(cd "$ROOT/backend" && .venv/bin/alembic upgrade head && exec .venv/bin/uvicorn app.main:app --reload --port 8000) &
(cd "$ROOT/frontend" && exec npm run dev -- --host 127.0.0.1) &
wait
