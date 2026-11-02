#!/bin/bash
set -e

echo "[ENTRYPOINT] Starting AVENTRA Backend..."

# Run database schema migration & genesis seeding
echo "[ENTRYPOINT] Executing database migrations..."
python -m backend.database.migrate

# Launch FastAPI ASGI server
echo "[ENTRYPOINT] Launching Uvicorn server..."
exec python -m uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers "${WORKERS:-2}"
