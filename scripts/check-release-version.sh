#!/usr/bin/env bash

# Validate that the repository's release metadata agrees with a version tag.
# Usage: ./scripts/check-release-version.sh v2.2.7

set -euo pipefail

source "$(dirname "$0")/semver.sh"

TAG="${1:-}"

if [[ $# -ne 1 || ! "$TAG" =~ $SEMVER_TAG_PATTERN ]]; then
  echo "Usage: ./scripts/check-release-version.sh vX.Y.Z[-alpha.N|-beta.N|-rc.N]" >&2
  exit 1
fi

VERSION="${TAG#v}"
VERSION_FILE="$(tr -d '[:space:]' < VERSION)"
PACKAGE_VERSION="$(node -p "require('./frontend/package.json').version")"
LOCKFILE_VERSION="$(node -p "require('./frontend/package-lock.json').version")"
LOCKFILE_PACKAGE_VERSION="$(node -p "require('./frontend/package-lock.json').packages[''].version")"

# app/config.py and app/main.py are not checked here any more: they read VERSION
# instead of declaring their own, so they cannot disagree with it. That they do
# is covered by tests/unit/test_version.py.
for entry in \
  "VERSION:$VERSION_FILE" \
  "frontend/package.json:$PACKAGE_VERSION" \
  "frontend/package-lock.json:$LOCKFILE_VERSION" \
  "frontend/package-lock.json packages root:$LOCKFILE_PACKAGE_VERSION"; do
  source="${entry%%:*}"
  actual="${entry#*:}"
  if [[ "$actual" != "$VERSION" ]]; then
    echo "Error: $source declares $actual; expected $VERSION for $TAG." >&2
    exit 1
  fi
done

echo "Release metadata matches $TAG."
