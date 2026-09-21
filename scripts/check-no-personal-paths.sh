#!/usr/bin/env bash
# Fail if a path copied from a real developer machine leaks into tracked files.
#
# Fixtures, stories and tests must use invented paths. A path pasted out of a
# running app exposes that machine's real filenames to everyone who clones the
# repo, and git history keeps them forever. Use /home/user, /Users/alex or a
# similar placeholder instead.
#
# This checks two things only, so it stays quiet on legitimate container and CI
# paths such as /home/borg or /home/runner:
#   1. maintainer usernames, wherever they appear outside a github.com URL
#   2. macOS /Users/<name> paths whose user is not a known placeholder
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

SELF=':!scripts/check-no-personal-paths.sh'
# Placeholder users allowed in a /Users/ path.
USERS_OK='alex|yourusername|user|username|foo|bar|test|x'

fail=0

# 1. Maintainer usernames. Legitimate uses are GitHub URLs, funding/copyright
#    metadata and engineering specs that record who owned a decision.
names=$(git grep -n -I -E '(^|[^A-Za-z0-9_-])(karanhudia|karan)([^A-Za-z0-9_-]|$)' -- \
          . ':!*.lock' ':!package-lock.json' "$SELF" \
          ':!.github/**' ':!docs/**' ':!README.md' ':!WORKFLOW.md' ':!Dockerfile*' \
          ':!distribution/**' ':!docker-compose.yml' \
        | grep -v -E 'github\.com|githubusercontent|github\.io' || true)
if [ -n "$names" ]; then
  echo "ERROR: maintainer username in tracked source. Use a placeholder." >&2
  echo "$names" >&2; echo >&2; fail=1
fi

# 2. macOS home paths with a non-placeholder user.
users=$(git grep -n -I -E '/Users/[A-Za-z0-9_.-]+' -- . ':!*.lock' ':!package-lock.json' "$SELF" \
        | grep -v -E 'github\.com|githubusercontent' \
        | grep -v -E "/Users/(${USERS_OK})(/|\"|'|\`|:| |,|\)|$)" || true)
if [ -n "$users" ]; then
  echo "ERROR: real /Users/ path in tracked files. Use /Users/alex or similar." >&2
  echo "$users" >&2; echo >&2; fail=1
fi

if [ "$fail" -ne 0 ]; then
  exit 1
fi
echo "OK: no personal paths in tracked files."
