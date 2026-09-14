#!/usr/bin/env bash
# Docker entrypoint for the backend container.
# Runs Alembic migrations then launches uvicorn.
set -euo pipefail

echo "[entrypoint] Running Alembic migrations..."
cd /app
python -m alembic -c backend/alembic.ini upgrade head

echo "[entrypoint] Starting uvicorn..."
exec uvicorn backend.app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --log-level info \
    --no-access-log
