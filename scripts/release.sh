#!/bin/bash

# Release script for Borg UI
# Usage: npm run release -- v1.51.0
# Or directly: ./scripts/release.sh v1.51.0

set -e

VERSION=$1

# Validate version argument
if [ -z "$VERSION" ]; then
  echo "Error: Version argument required"
  echo "Usage: npm run release -- vX.Y.Z"
  exit 1
fi

# Validate version format (vX.Y.Z)
if ! [[ "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Error: Invalid version format. Must be vX.Y.Z (e.g., v1.51.0)"
  exit 1
fi

# Strip 'v' prefix for VERSION file
VERSION_NUMBER="${VERSION#v}"

echo "Releasing version $VERSION..."

# Update VERSION file
echo "$VERSION_NUMBER" > VERSION
echo "Updated VERSION file to $VERSION_NUMBER"

# Run tests and checks
echo "Running checks..."
cd frontend
npm run typecheck
npm run format:check
cd ..

# Commit and tag
git add VERSION
git commit -m "chore: bump version to $VERSION_NUMBER

Co-Authored-By: Claude <noreply@anthropic.com>"

git tag "$VERSION"
echo "Created tag $VERSION"

# Push
git push origin main
git push origin "$VERSION"
echo "Pushed to origin"

echo ""
echo "Release $VERSION complete!"
echo "GitHub will automatically create a release from the tag."
