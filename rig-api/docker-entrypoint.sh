#!/bin/sh
# Apply schema migrations, then start whatever CMD says (uvicorn by default).
set -eu

echo "[rig-api] running alembic migrations against ${DATABASE_URL:-sqlite:///rigs.db}"
alembic upgrade head

exec "$@"
