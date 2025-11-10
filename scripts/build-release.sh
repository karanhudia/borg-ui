#!/bin/bash

# Script to build a complete release bundle for Borg Web UI
# This creates a production-ready build with both frontend and backend

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;36m'
NC='\033[0m' # No Color

VERSION_FILE="VERSION"
BUILD_DIR="build"
RELEASE_DIR="release"

echo -e "${BLUE}╔═══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Borg Web UI - Release Builder      ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════╝${NC}"
echo ""

# Check if VERSION file exists
if [ ! -f "$VERSION_FILE" ]; then
    echo -e "${RED}Error: VERSION file not found${NC}"
    exit 1
fi

VERSION=$(cat "$VERSION_FILE")
echo -e "${YELLOW}Building release version: ${GREEN}$VERSION${NC}"
echo ""

# Clean up previous builds
echo -e "${YELLOW}→ Cleaning previous builds...${NC}"
rm -rf "$BUILD_DIR" "$RELEASE_DIR"
mkdir -p "$BUILD_DIR" "$RELEASE_DIR"
echo -e "${GREEN}✓ Cleaned${NC}"
echo ""

# Build frontend
echo -e "${YELLOW}→ Building frontend...${NC}"
cd frontend

# Install dependencies if node_modules doesn't exist
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}  Installing frontend dependencies...${NC}"
    npm install
fi

# Build frontend
npm run build

# Check if build succeeded
if [ ! -d "build" ]; then
    echo -e "${RED}Error: Frontend build failed - build directory not found${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Frontend built successfully${NC}"
cd ..
echo ""

# Copy frontend build to app/static
echo -e "${YELLOW}→ Copying frontend build to app/static...${NC}"
rm -rf app/static
cp -r frontend/build app/static
echo -e "${GREEN}✓ Frontend copied to app/static${NC}"
echo ""

# Copy backend files to build directory
echo -e "${YELLOW}→ Preparing backend files...${NC}"
cp -r app "$BUILD_DIR/"
cp -r scripts "$BUILD_DIR/"
cp requirements.txt "$BUILD_DIR/"
cp entrypoint.sh "$BUILD_DIR/"
cp VERSION "$BUILD_DIR/"
cp README.md "$BUILD_DIR/"
cp LICENSE "$BUILD_DIR/" 2>/dev/null || echo "  (LICENSE file not found, skipping)"
echo -e "${GREEN}✓ Backend files prepared${NC}"
echo ""

# Create release archive
echo -e "${YELLOW}→ Creating release archive...${NC}"
RELEASE_NAME="borg-ui-v${VERSION}"
RELEASE_ARCHIVE="${RELEASE_DIR}/${RELEASE_NAME}.tar.gz"

cd "$BUILD_DIR"
tar -czf "../${RELEASE_ARCHIVE}" \
    --exclude='*.pyc' \
    --exclude='__pycache__' \
    --exclude='.pytest_cache' \
    --exclude='*.db' \
    .
cd ..

# Get archive size
ARCHIVE_SIZE=$(du -h "$RELEASE_ARCHIVE" | cut -f1)
echo -e "${GREEN}✓ Release archive created: ${RELEASE_ARCHIVE} (${ARCHIVE_SIZE})${NC}"
echo ""

# Create checksums
echo -e "${YELLOW}→ Generating checksums...${NC}"
cd "$RELEASE_DIR"
sha256sum "${RELEASE_NAME}.tar.gz" > "${RELEASE_NAME}.sha256"
echo -e "${GREEN}✓ SHA256 checksum created${NC}"
cd ..
echo ""

# Summary
echo -e "${BLUE}╔═══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║         Build Complete! 🎉            ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Release artifacts:${NC}"
echo -e "  📦 Archive:   ${RELEASE_ARCHIVE}"
echo -e "  🔒 Checksum:  ${RELEASE_DIR}/${RELEASE_NAME}.sha256"
echo ""
echo -e "${YELLOW}Contents:${NC}"
echo -e "  • Backend Python application (app/)"
echo -e "  • Compiled frontend (app/static/)"
echo -e "  • Requirements file"
echo -e "  • Entrypoint script"
echo -e "  • Documentation"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo -e "  1. Test the release: ${BLUE}tar -xzf ${RELEASE_ARCHIVE} -C test-dir${NC}"
echo -e "  2. Verify checksum:  ${BLUE}sha256sum -c ${RELEASE_DIR}/${RELEASE_NAME}.sha256${NC}"
echo -e "  3. Upload to GitHub releases (manual or via gh CLI)"
echo ""
