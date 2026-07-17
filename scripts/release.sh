#!/usr/bin/env bash

# Create and publish a Borg UI release from main.
# Usage: ./scripts/release.sh v2.2.7

set -euo pipefail

source "$(dirname "$0")/semver.sh"

usage() {
  echo "Usage: ./scripts/release.sh vX.Y.Z[-alpha.N|-beta.N|-rc.N]" >&2
}

TAG="${1:-}"

if [[ $# -ne 1 || ! "$TAG" =~ $SEMVER_TAG_PATTERN ]]; then
  usage
  exit 1
fi

if [[ "$(git rev-parse --abbrev-ref HEAD)" != "main" ]]; then
  echo "Error: releases must be created from the main branch." >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Error: working tree must be clean before creating a release." >&2
  exit 1
fi

git fetch origin main

if [[ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]]; then
  echo "Error: local main must exactly match origin/main before a release." >&2
  exit 1
fi

if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null || \
  git ls-remote --exit-code --tags origin "refs/tags/$TAG" >/dev/null 2>&1; then
  echo "Error: tag $TAG already exists." >&2
  exit 1
fi

VERSION="${TAG#v}"

echo "Preparing release $TAG from $(git rev-parse --short HEAD)..."
npm --prefix frontend version "$VERSION" --no-git-tag-version
printf '%s\n' "$VERSION" > VERSION

# app/config.py and app/main.py used to be rewritten here as well. They read
# VERSION now, so there is nothing left to keep in step -- which is the point:
# this rewrite is exactly what a bump done any other way skips, and app_version
# then keeps whatever it last said.

./scripts/check-release-version.sh "$TAG"
git diff --check
npm --prefix frontend run check:locales
npm --prefix frontend run typecheck
npm --prefix frontend run format:check

git add VERSION frontend/package.json frontend/package-lock.json app/config.py app/main.py
git commit -m "chore(release): bump version to $VERSION"
git tag -a "$TAG" -m "Release $TAG"

git push --atomic origin main "$TAG"

echo "Release $TAG published. GitHub Actions will create the release and images."
