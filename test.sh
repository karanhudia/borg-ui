#!/bin/bash

# Borg Web UI Test Runner
# This script runs the comprehensive test suite for the application

set -e  # Exit on any error

echo "🧪 Borg Web UI Test Runner"
echo "================================"

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed or not in PATH"
    exit 1
fi

# Check if requests module is available
if ! python3 -c "import requests" &> /dev/null; then
    echo "⚠️  Warning: requests module not found. Installing..."
    pip3 install requests
fi

# Default URL
URL=${1:-"http://localhost:7879"}

echo "📍 Testing application at: $URL"
echo ""

# Run the test suite
python3 test_app.py --url "$URL"

# Check exit code
if [ $? -eq 0 ]; then
    echo ""
    echo "🎉 All tests passed! The application is working correctly."
    exit 0
else
    echo ""
    echo "⚠️  Some tests failed. Please check the output above for details."
    exit 1
fi
