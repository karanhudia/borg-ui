#!/bin/bash
###############################################################################
# Borg UI Master Test Runner
#
# Runs the complete test suite:
# 1. Sets up test environment (if needed)
# 2. Runs archive contents tests
# 3. Runs API tests
# 4. Generates test report
#
# Usage: ./run_tests.sh [options]
#
# Options:
#   --skip-setup    Skip test environment setup
#   --url URL       Borg UI URL (default: http://localhost:8081)
#   --clean         Clean up test environment after tests
#   --test-dir DIR  Test directory (default: /tmp/borg-ui-tests)
###############################################################################

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Default values
SKIP_SETUP=false
CLEAN=false
TEST_DIR="/tmp/borg-ui-tests"
BORG_UI_URL="http://localhost:8081"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-setup)
            SKIP_SETUP=true
            shift
            ;;
        --clean)
            CLEAN=true
            shift
            ;;
        --test-dir)
            TEST_DIR="$2"
            shift 2
            ;;
        --url)
            BORG_UI_URL="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --skip-setup      Skip test environment setup"
            echo "  --url URL         Borg UI URL (default: http://localhost:8081)"
            echo "  --clean           Clean up test environment after tests"
            echo "  --test-dir DIR    Test directory (default: /tmp/borg-ui-tests)"
            echo "  -h, --help        Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo -e "${BOLD}${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${BLUE}║         Borg UI Comprehensive Test Suite                      ║${NC}"
echo -e "${BOLD}${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Configuration:${NC}"
echo -e "  Test Directory: ${BOLD}$TEST_DIR${NC}"
echo -e "  Borg UI URL:    ${BOLD}$BORG_UI_URL${NC}"
echo -e "  Skip Setup:     ${BOLD}$SKIP_SETUP${NC}"
echo -e "  Clean After:    ${BOLD}$CLEAN${NC}"
echo ""

# Track test results
TESTS_PASSED=0
TESTS_FAILED=0
START_TIME=$(date +%s)

###############################################################################
# Step 1: Setup Test Environment
###############################################################################

if [ "$SKIP_SETUP" = false ]; then
    echo -e "${BOLD}${BLUE}[1/3] Setting up test environment...${NC}"
    echo "────────────────────────────────────────────────────────────────"

    if [ -f "./tests/setup_test_env.sh" ]; then
        if ./tests/setup_test_env.sh "$TEST_DIR"; then
            echo -e "${GREEN}✅ Test environment setup completed${NC}"
            TESTS_PASSED=$((TESTS_PASSED + 1))
        else
            echo -e "${RED}❌ Test environment setup failed${NC}"
            TESTS_FAILED=$((TESTS_FAILED + 1))
            echo ""
            echo -e "${YELLOW}Tip: Make sure you have borg installed:${NC}"
            echo "  macOS:   brew install borgbackup"
            echo "  Ubuntu:  apt install borgbackup"
            exit 1
        fi
    else
        echo -e "${RED}❌ Setup script not found: ./tests/setup_test_env.sh${NC}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        exit 1
    fi
else
    echo -e "${YELLOW}[1/3] Skipping test environment setup (--skip-setup)${NC}"
    echo "────────────────────────────────────────────────────────────────"

    # Verify test directory exists
    if [ ! -d "$TEST_DIR" ]; then
        echo -e "${RED}❌ Test directory not found: $TEST_DIR${NC}"
        echo -e "${YELLOW}Run without --skip-setup to create it${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ Using existing test environment${NC}"
fi

echo ""

###############################################################################
# Step 2: Archive Contents Tests
###############################################################################

echo -e "${BOLD}${BLUE}[2/3] Running archive contents tests...${NC}"
echo "────────────────────────────────────────────────────────────────"

# Check if Borg UI is accessible
if ! curl -s -f "$BORG_UI_URL/" > /dev/null 2>&1; then
    echo -e "${RED}❌ Borg UI not accessible at $BORG_UI_URL${NC}"
    echo -e "${YELLOW}Please make sure Borg UI is running:${NC}"
    echo "  docker-compose up -d"
    echo "  or"
    echo "  cd app && uvicorn main:app --port 8081"
    TESTS_FAILED=$((TESTS_FAILED + 1))
else
    echo -e "${GREEN}✅ Borg UI is accessible${NC}"
    echo ""

    if [ -f "./tests/test_archive_contents.py" ]; then
        if python3 ./tests/test_archive_contents.py "$TEST_DIR" --url "$BORG_UI_URL"; then
            echo -e "${GREEN}✅ Archive contents tests passed${NC}"
            TESTS_PASSED=$((TESTS_PASSED + 1))
        else
            echo -e "${RED}❌ Archive contents tests failed${NC}"
            TESTS_FAILED=$((TESTS_FAILED + 1))
        fi
    else
        echo -e "${RED}❌ Test script not found: ./tests/test_archive_contents.py${NC}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
fi

echo ""

###############################################################################
# Step 3: API Tests
###############################################################################

echo -e "${BOLD}${BLUE}[3/3] Running API tests...${NC}"
echo "────────────────────────────────────────────────────────────────"

if [ -f "./test_app.py" ]; then
    if python3 ./test_app.py --url "$BORG_UI_URL"; then
        echo -e "${GREEN}✅ API tests passed${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        echo -e "${RED}❌ API tests failed${NC}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
else
    echo -e "${YELLOW}⚠️  API test script not found: ./test_app.py (skipping)${NC}"
fi

echo ""

###############################################################################
# Cleanup
###############################################################################

if [ "$CLEAN" = true ]; then
    echo -e "${BOLD}${BLUE}Cleaning up test environment...${NC}"
    echo "────────────────────────────────────────────────────────────────"

    if [ -d "$TEST_DIR" ]; then
        rm -rf "$TEST_DIR"
        echo -e "${GREEN}✅ Test environment cleaned up${NC}"
    fi
    echo ""
fi

###############################################################################
# Final Report
###############################################################################

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo -e "${BOLD}${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${BLUE}║                    TEST SUMMARY                                ║${NC}"
echo -e "${BOLD}${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

TOTAL_TESTS=$((TESTS_PASSED + TESTS_FAILED))
if [ $TOTAL_TESTS -eq 0 ]; then
    PASS_RATE="N/A"
else
    PASS_RATE=$(( (TESTS_PASSED * 100) / TOTAL_TESTS ))
fi

echo -e "  Tests Passed:  ${GREEN}${BOLD}$TESTS_PASSED${NC}"
echo -e "  Tests Failed:  ${RED}${BOLD}$TESTS_FAILED${NC}"
echo -e "  Pass Rate:     ${BOLD}$PASS_RATE%${NC}"
echo -e "  Duration:      ${BOLD}${DURATION}s${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}${BOLD}🎉 All tests passed! Borg UI is working correctly.${NC}"
    echo ""
    exit 0
else
    echo -e "${RED}${BOLD}⚠️  Some tests failed. Please check the output above for details.${NC}"
    echo ""
    echo -e "${YELLOW}Troubleshooting tips:${NC}"
    echo "  1. Check Borg UI logs: docker logs borg-web-ui"
    echo "  2. Verify test data: cat $TEST_DIR/TEST_INFO.txt"
    echo "  3. Test manually: borg list $TEST_DIR/repositories/repo1-unencrypted"
    echo "  4. Check docs: cat ./tests/README.md"
    echo ""
    exit 1
fi
