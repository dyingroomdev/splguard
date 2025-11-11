#!/usr/bin/env bash
set -euo pipefail

export PORT=${PORT:-8105}
export UVICORN_PORT=${UVICORN_PORT:-$PORT}

if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD="docker-compose"
else
  echo "docker compose is not available. Install Docker Compose v2 or docker-compose." >&2
  exit 1
fi

echo "Building and starting services via docker-compose.yml..."
$COMPOSE_CMD up -d --build

echo "Deployment complete. Tail logs with:"
echo "  $COMPOSE_CMD logs -f"
