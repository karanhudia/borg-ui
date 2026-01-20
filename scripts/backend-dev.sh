#!/bin/bash

# Run backend locally with hot reload
# Usage: ./scripts/backend-dev.sh

set -e

cd "$(dirname "$0")/.."

# Create local data directory
mkdir -p .local-data/ssh_keys .local-data/logs .local-data/borg_keys

# Set environment variables for local development
export DATA_DIR=".local-data"
export DATABASE_URL="sqlite:///.local-data/borg.db"
export SECRET_KEY="dev-secret-key-not-for-production"
export ENVIRONMENT="development"
export PORT=8081
export REDIS_HOST="localhost"
export REDIS_PORT="6379"
export LOCAL_MOUNT_POINTS="/local"

echo "Starting backend with hot reload..."
echo "API: http://localhost:8081"
echo ""

python3 -m uvicorn app.main:app --reload --port 8081
