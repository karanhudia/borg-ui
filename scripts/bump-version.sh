#!/bin/bash

# Script to bump version and create a git tag
# Usage:
#   ./scripts/bump-version.sh patch   # 1.0.0 -> 1.0.1
#   ./scripts/bump-version.sh minor   # 1.0.0 -> 1.1.0
#   ./scripts/bump-version.sh major   # 1.0.0 -> 2.0.0

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

VERSION_FILE="VERSION"
BUMP_TYPE="${1:-patch}"

# Validate bump type
if [[ ! "$BUMP_TYPE" =~ ^(major|minor|patch)$ ]]; then
    echo -e "${RED}Error: Invalid bump type '$BUMP_TYPE'${NC}"
    echo "Usage: $0 [major|minor|patch]"
    echo "  major: 1.0.0 -> 2.0.0"
    echo "  minor: 1.0.0 -> 1.1.0"
    echo "  patch: 1.0.0 -> 1.0.1 (default)"
    exit 1
fi

# Check if VERSION file exists
if [ ! -f "$VERSION_FILE" ]; then
    echo -e "${RED}Error: VERSION file not found${NC}"
    exit 1
fi

# Read current version
CURRENT_VERSION=$(cat "$VERSION_FILE")
echo -e "${YELLOW}Current version: $CURRENT_VERSION${NC}"

# Parse version components
IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"

# Bump version based on type
case "$BUMP_TYPE" in
    major)
        MAJOR=$((MAJOR + 1))
        MINOR=0
        PATCH=0
        ;;
    minor)
        MINOR=$((MINOR + 1))
        PATCH=0
        ;;
    patch)
        PATCH=$((PATCH + 1))
        ;;
esac

NEW_VERSION="${MAJOR}.${MINOR}.${PATCH}"
echo -e "${GREEN}New version: $NEW_VERSION${NC}"

# Update VERSION file
echo "$NEW_VERSION" > "$VERSION_FILE"
echo -e "${GREEN}✓ Updated VERSION file${NC}"

# Stage VERSION file
git add "$VERSION_FILE"
echo -e "${GREEN}✓ Staged VERSION file${NC}"

# Commit the version bump
git commit -m "chore: bump version to v$NEW_VERSION"
echo -e "${GREEN}✓ Committed version bump${NC}"

# Create and push git tag
git tag -a "v$NEW_VERSION" -m "Release v$NEW_VERSION"
echo -e "${GREEN}✓ Created tag v$NEW_VERSION${NC}"

echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Push the commit: ${GREEN}git push origin main${NC}"
echo "  2. Push the tag:    ${GREEN}git push origin v$NEW_VERSION${NC}"
echo ""
echo "This will trigger a Docker build with version $NEW_VERSION"
echo "Docker images will be tagged as:"
echo "  - $NEW_VERSION"
echo "  - ${MAJOR}.${MINOR}"
echo "  - ${MAJOR}"
echo "  - latest"
