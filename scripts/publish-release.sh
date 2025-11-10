#!/bin/bash

# Script to publish release artifacts to GitHub
# Requires gh CLI to be installed and authenticated

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;36m'
NC='\033[0m' # No Color

VERSION_FILE="VERSION"
RELEASE_DIR="release"

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo -e "${RED}Error: GitHub CLI (gh) is not installed${NC}"
    echo "Install it from: https://cli.github.com/"
    exit 1
fi

# Check if VERSION file exists
if [ ! -f "$VERSION_FILE" ]; then
    echo -e "${RED}Error: VERSION file not found${NC}"
    exit 1
fi

VERSION=$(cat "$VERSION_FILE")
TAG="v${VERSION}"
RELEASE_NAME="borg-ui-v${VERSION}"
RELEASE_ARCHIVE="${RELEASE_DIR}/${RELEASE_NAME}.tar.gz"
RELEASE_CHECKSUM="${RELEASE_DIR}/${RELEASE_NAME}.sha256"

echo -e "${BLUE}╔═══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Borg Web UI - Release Publisher    ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════╝${NC}"
echo ""

# Check if release archive exists
if [ ! -f "$RELEASE_ARCHIVE" ]; then
    echo -e "${RED}Error: Release archive not found: ${RELEASE_ARCHIVE}${NC}"
    echo -e "${YELLOW}Run ./scripts/build-release.sh first${NC}"
    exit 1
fi

# Check if release exists on GitHub
echo -e "${YELLOW}→ Checking if release ${TAG} exists on GitHub...${NC}"
if gh release view "$TAG" &> /dev/null; then
    echo -e "${GREEN}✓ Release ${TAG} found${NC}"

    # Upload artifacts to existing release
    echo -e "${YELLOW}→ Uploading release artifacts...${NC}"

    gh release upload "$TAG" "$RELEASE_ARCHIVE" "$RELEASE_CHECKSUM" --clobber

    echo -e "${GREEN}✓ Artifacts uploaded to release ${TAG}${NC}"
else
    echo -e "${RED}✗ Release ${TAG} not found on GitHub${NC}"
    echo -e "${YELLOW}You need to push the tag first:${NC}"
    echo -e "  ${BLUE}git push origin ${TAG}${NC}"
    exit 1
fi

echo ""
echo -e "${BLUE}╔═══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║       Upload Complete! 🎉             ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Uploaded artifacts:${NC}"
echo -e "  📦 ${RELEASE_NAME}.tar.gz"
echo -e "  🔒 ${RELEASE_NAME}.sha256"
echo ""
echo -e "${YELLOW}View release at:${NC}"
echo -e "  ${BLUE}https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner)/releases/tag/${TAG}${NC}"
echo ""
