#!/usr/bin/env bash

# Borg UI supports stable releases and alpha, beta, and rc prereleases.
# Numeric identifiers follow SemVer's no-leading-zero rule.
SEMVER_NUMBER='(0|[1-9][0-9]*)'
SEMVER_VERSION="${SEMVER_NUMBER}\\.${SEMVER_NUMBER}\\.${SEMVER_NUMBER}"
SEMVER_PRERELEASE="((alpha|beta|rc)\\.${SEMVER_NUMBER})"
SEMVER_TAG_PATTERN="^v${SEMVER_VERSION}(-${SEMVER_PRERELEASE})?$"
SEMVER_STABLE_VERSION_PATTERN="^${SEMVER_VERSION}$"
