#!/usr/bin/env bash
# Print the runtime-base image tag, computed from the version facts in
# runtime-base.env. The tag is a function of the versions, never a stored field,
# so both the build scripts and CI call this — the string exists in one place.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$here/runtime-base.env"
printf 'runtime-borg1-%s-borg2-%s-r%s\n' \
  "$BORG1_VERSION" "$BORG2_VERSION" "$RUNTIME_BASE_REVISION"
