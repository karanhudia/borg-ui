#!/bin/bash

# Release script for Borg UI
# Usage: npm run release -- v1.51.0
# Or directly: ./scripts/release.sh v1.51.0

set -e

VERSION=$1
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)

if [ "$CURRENT_BRANCH" = "HEAD" ]; then
  echo "Error: Cannot release from detached HEAD"
  exit 1
fi

# Validate version argument
if [ -z "$VERSION" ]; then
  echo "Error: Version argument required"
  echo "Usage: npm run release -- vX.Y.Z[-alpha.N|-beta.N|-rc.N]"
  exit 1
fi

# Validate version format (vX.Y.Z or prerelease variants)
if ! [[ "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-((alpha|beta|rc)\.[0-9]+))?$ ]]; then
  echo "Error: Invalid version format. Must be vX.Y.Z or vX.Y.Z-alpha.N / beta.N / rc.N"
  exit 1
fi

# Strip 'v' prefix for VERSION file
VERSION_NUMBER="${VERSION#v}"

echo "Releasing version $VERSION..."
echo "Release branch: $CURRENT_BRANCH"

# Update VERSION file
echo "$VERSION_NUMBER" > VERSION
echo "Updated VERSION file to $VERSION_NUMBER"

# Update frontend package metadata
npm --prefix frontend version "$VERSION_NUMBER" --no-git-tag-version
echo "Updated frontend/package.json to $VERSION_NUMBER"

# Update backend fallback/OpenAPI metadata
python3 - "$VERSION_NUMBER" <<'PY'
import re
import sys
from pathlib import Path

version = sys.argv[1]
updates = {
    Path("app/config.py"): (
        r'app_version: str = "[^"]+"',
        f'app_version: str = "{version}"',
    ),
    Path("app/main.py"): (
        r'version="[0-9]+\.[0-9]+\.[0-9]+(?:-[^"]+)?"',
        f'version="{version}"',
    ),
}

for path, (pattern, replacement) in updates.items():
    text = path.read_text()
    updated, count = re.subn(pattern, replacement, text, count=1)
    if count != 1:
        raise SystemExit(f"Could not update version in {path}")
    path.write_text(updated)
PY
echo "Updated backend app metadata to $VERSION_NUMBER"

# Run tests and checks
echo "Running checks..."
cd frontend
npm run typecheck
npm run format:check
cd ..

# Commit and tag
git add VERSION frontend/package.json frontend/package-lock.json app/config.py app/main.py
git commit -m "chore: bump version to $VERSION_NUMBER

Co-Authored-By: Claude <noreply@anthropic.com>"

git tag "$VERSION"
echo "Created tag $VERSION"

# Push
git push origin "$CURRENT_BRANCH"
git push origin "$VERSION"
echo "Pushed to origin"

echo ""
echo "Release $VERSION complete!"
echo "GitHub will automatically create a release from the tag."
