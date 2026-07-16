#!/usr/bin/env bash

# Compatibility wrapper for the supported release workflow.
# Usage: ./scripts/bump-version.sh [major|minor|patch]

set -euo pipefail

BUMP_TYPE="${1:-patch}"

if [[ ! "$BUMP_TYPE" =~ ^(major|minor|patch)$ ]]; then
  echo "Usage: ./scripts/bump-version.sh [major|minor|patch]" >&2
  exit 1
fi

CURRENT_VERSION="$(tr -d '[:space:]' < VERSION)"
if [[ ! "$CURRENT_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Error: VERSION must be a stable semantic version to use this wrapper." >&2
  echo "Use ./scripts/release.sh vX.Y.Z-prerelease.N for prereleases." >&2
  exit 1
fi

IFS='.' read -r major minor patch <<< "$CURRENT_VERSION"
case "$BUMP_TYPE" in
  major) ((major += 1)); minor=0; patch=0 ;;
  minor) ((minor += 1)); patch=0 ;;
  patch) ((patch += 1)) ;;
esac

exec "$(dirname "$0")/release.sh" "v${major}.${minor}.${patch}"
