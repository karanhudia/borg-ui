#!/bin/bash
# Fix Docker permissions for integration tests
# Run this if you get "Permission denied" errors when testing against Docker

set -e

TEST_DIR="${1:-/tmp/borg-ui-tests}"

echo "=================================================="
echo "Fixing Docker Permissions for Borg UI Tests"
echo "=================================================="
echo ""
echo "Test directory: $TEST_DIR"
echo ""

# Check if directory exists
if [ ! -d "$TEST_DIR" ]; then
    echo "❌ Test directory not found: $TEST_DIR"
    echo "Run: ./tests/setup_test_env.sh first"
    exit 1
fi

# Get current ownership
CURRENT_OWNER=$(stat -f "%u:%g" "$TEST_DIR" 2>/dev/null || stat -c "%u:%g" "$TEST_DIR" 2>/dev/null)
echo "Current ownership: $CURRENT_OWNER"

# Get container UID/GID
echo ""
echo "Checking Docker container user ID..."
CONTAINER_UID=$(docker exec borg-web-ui id -u 2>/dev/null || echo "N/A")
CONTAINER_GID=$(docker exec borg-web-ui id -g 2>/dev/null || echo "N/A")

if [ "$CONTAINER_UID" == "N/A" ]; then
    echo "⚠️  Container not running or not found"
    echo ""
    echo "Options:"
    echo "  1. Start container: docker-compose up -d"
    echo "  2. Set ownership to your user: sudo chown -R $(id -u):$(id -g) $TEST_DIR"
else
    echo "Container runs as: UID=$CONTAINER_UID GID=$CONTAINER_GID"
    echo "Your user: UID=$(id -u) GID=$(id -g)"
    echo ""

    # Recommend fix based on situation
    if [ "$CONTAINER_UID" == "$(id -u)" ]; then
        echo "✅ UIDs match! Just need to fix permissions..."
        echo ""
        echo "Run: sudo chmod -R u+rwX $TEST_DIR"
        echo ""
    else
        echo "📋 Choose a fix:"
        echo ""
        echo "Option 1 (Recommended): Match container UID to your user"
        echo "  1. Stop container: docker-compose down"
        echo "  2. Set PUID/PGID: export PUID=\$(id -u) PGID=\$(id -g)"
        echo "  3. Start container: docker-compose up -d"
        echo ""
        echo "Option 2: Change test directory ownership to container UID"
        echo "  sudo chown -R $CONTAINER_UID:$CONTAINER_GID $TEST_DIR"
        echo ""
        echo "Option 3: Make files readable/writable by all"
        echo "  sudo chmod -R a+rwX $TEST_DIR"
        echo ""
    fi
fi

echo "=================================================="
