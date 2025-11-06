#!/bin/bash
# Test runner script for Borg UI
# This provides convenient commands for running tests locally

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}==================================${NC}"
echo -e "${BLUE}   Borg UI Test Runner${NC}"
echo -e "${BLUE}==================================${NC}"
echo ""

# Function to display usage
usage() {
    echo "Usage: ./run_tests.sh [command]"
    echo ""
    echo "Commands:"
    echo "  unit        - Run unit tests only (fast, no UI required)"
    echo "  integration - Run integration tests (requires Borg UI running)"
    echo "  coverage    - Run all tests with coverage report"
    echo "  quick       - Quick test run (unit tests only)"
    echo "  all         - Run all tests"
    echo "  collect     - List all available tests"
    echo "  clean       - Clean test artifacts and cache"
    echo ""
    echo "Examples:"
    echo "  ./run_tests.sh unit"
    echo "  ./run_tests.sh coverage"
    echo ""
}

# Check if pytest is available
if ! python3 -m pytest --version > /dev/null 2>&1; then
    echo -e "${RED}Error: pytest not found${NC}"
    echo "Install dependencies: pip install -r requirements.txt"
    exit 1
fi

# Parse command
COMMAND=${1:-help}

case $COMMAND in
    unit)
        echo -e "${GREEN}Running unit tests...${NC}"
        python3 -m pytest tests/ -m "not requires_ui" -v
        ;;

    integration)
        echo -e "${GREEN}Running integration tests...${NC}"
        echo -e "${YELLOW}Note: This requires Borg UI to be running${NC}"
        python3 -m pytest tests/ -m "requires_ui" -v
        ;;

    coverage)
        echo -e "${GREEN}Running all tests with coverage...${NC}"
        python3 -m pytest tests/ \
            --cov=app \
            --cov-report=term-missing \
            --cov-report=html \
            --cov-report=xml \
            -v

        echo ""
        echo -e "${GREEN}Coverage report generated:${NC}"
        echo "  - HTML: htmlcov/index.html"
        echo "  - XML:  coverage.xml"
        echo ""
        echo -e "${BLUE}To view HTML report:${NC} open htmlcov/index.html"
        ;;

    quick)
        echo -e "${GREEN}Quick test run (unit tests only)...${NC}"
        python3 -m pytest tests/ -m "not requires_ui" -v --tb=short
        ;;

    all)
        echo -e "${GREEN}Running all tests...${NC}"
        python3 -m pytest tests/ -v
        ;;

    collect)
        echo -e "${GREEN}Collecting all tests...${NC}"
        python3 -m pytest tests/ --collect-only -q
        ;;

    clean)
        echo -e "${GREEN}Cleaning test artifacts...${NC}"
        rm -rf .pytest_cache
        rm -rf htmlcov
        rm -f .coverage coverage.xml coverage.json
        rm -rf __pycache__
        rm -rf tests/__pycache__
        echo -e "${GREEN}Done!${NC}"
        ;;

    help|--help|-h)
        usage
        ;;

    *)
        echo -e "${RED}Unknown command: $COMMAND${NC}"
        echo ""
        usage
        exit 1
        ;;
esac
