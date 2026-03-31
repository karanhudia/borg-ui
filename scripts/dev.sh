#!/bin/bash

# Development script - frontend locally, backend in Docker with hot reload
# Backend runs in Docker so both borg (v1) and borg2 binaries are available
# Uses DEV_PORT (default 8083) so prod (PORT=8082) can run simultaneously
# Usage: ./scripts/dev.sh

set -e

cd "$(dirname "$0")/.."

echo "Starting Borg UI development environment..."

# Read DEV_PORT from .env if present, fallback to 8083
DEV_PORT=8083
if [ -f .env ]; then
    _DEV_PORT=$(grep '^DEV_PORT=' .env | cut -d= -f2)
    [ -n "$_DEV_PORT" ] && DEV_PORT="$_DEV_PORT"
fi

# Stop Docker services and background jobs on exit
trap 'echo "Stopping dev environment..."; docker-compose -p borg-ui-dev -f docker-compose.dev.yml down 2>/dev/null; kill $(jobs -p) 2>/dev/null' EXIT

# Create local data directory (mounted into Docker as /data)
mkdir -p .local-data/ssh_keys .local-data/logs .local-data/borg_keys

# Start dev Redis + backend in Docker with hot-reload
echo "Starting dev Redis and backend (Docker, port $DEV_PORT)..."
DEV_PORT=$DEV_PORT docker-compose -p borg-ui-dev -f docker-compose.dev.yml up -d

# Wait for backend to be ready
sleep 3

# Stream backend logs in background
docker logs -f borg-web-ui-dev &

# Start frontend — point its proxy at the dev backend port
echo "Starting frontend..."
cd frontend && VITE_PROXY_TARGET="http://localhost:$DEV_PORT" npm run dev &

echo ""
echo "=========================================="
echo "  Frontend: http://localhost:7879"
echo "  Backend:  http://localhost:$DEV_PORT  (dev)"
echo "  Prod:     http://localhost:8082        (if running)"
echo "  Redis:    localhost:6380               (dev)"
echo "=========================================="
echo ""
echo "Backend runs in Docker (borg1 + borg2 available)"
echo "Press Ctrl+C to stop"

# Wait for all background processes
wait
