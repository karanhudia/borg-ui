#!/bin/bash

# Development script - runs frontend and backend with hot reload
# Usage: ./scripts/dev.sh

set -e

cd "$(dirname "$0")/.."

echo "Starting Borg UI development environment..."

# Kill background processes on exit
trap 'kill $(jobs -p) 2>/dev/null' EXIT

# Start Redis (Docker)
echo "Starting Redis..."
docker-compose up -d redis

# Create local data directory
mkdir -p .local-data/ssh_keys .local-data/logs .local-data/borg_keys

# Set environment variables for local backend
export DATA_DIR=".local-data"
export DATABASE_URL="sqlite:///.local-data/borg.db"
export SECRET_KEY="dev-secret-key-not-for-production"
export ENVIRONMENT="development"
export PORT=8081
export REDIS_HOST="localhost"
export REDIS_PORT="6379"
export LOCAL_MOUNT_POINTS="/local"

# Start backend with hot reload
echo "Starting backend..."
python3 -m uvicorn app.main:app --reload --port 8081 &

# Wait for backend to be ready
sleep 3

# Start frontend with hot reload
echo "Starting frontend..."
cd frontend && npm run dev &

echo ""
echo "=========================================="
echo "  Frontend: http://localhost:7879"
echo "  Backend:  http://localhost:8081"
echo "  Redis:    localhost:6379"
echo "=========================================="
echo ""
echo "Both have hot reload - edit and save!"
echo "Press Ctrl+C to stop"

# Wait for all background processes
wait
