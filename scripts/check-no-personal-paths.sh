#!/usr/bin/env bash
# Fail if a path copied from a real developer machine leaks into tracked files.
#
# Fixtures, stories and tests must use invented paths. A path pasted out of a
# running app exposes that machine's real filenames to everyone who clones the
# repo, and git history keeps them forever. Use /home/user, /Users/alex or a
# similar placeholder instead.
#
# This checks three things only, so it stays quiet on legitimate container and
# CI paths such as /home/borg or /home/runner:
#   1. maintainer usernames, wherever they appear outside a github.com URL
#   2. macOS /Users/<name> paths whose user is not a known placeholder
#   3. relative home/<name>/ paths, the form borg archives use, whose user is
#      not a known placeholder. This is the idiom fixtures actually use, so it
#      is the most likely way a real path gets pasted in.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

SELF=':!scripts/check-no-personal-paths.sh'
# Placeholder users allowed in a /Users/ path.
USERS_OK='alex|yourusername|user|username|foo|bar|test|x'
# Placeholder users allowed in a relative home/<name>/ archive path.
HOME_OK='alex|user|username|app|example|other|test|tester|foo|bar|k|u|x'

# --self-test checks the patterns against known strings, so a typo that makes a
# filter match nothing cannot turn this into a guard that always passes.
# Detect patterns must match a real path. Allowlist patterns are used with
# grep -v, so they must match a placeholder and must not match a real path.
if [ "${1:-}" = "--self-test" ]; then
  st_fail=0
  m()  { printf '%s\n' "$2" | grep -q -E "$3" || { echo "self-test: $1: '$2' should match" >&2; st_fail=1; }; }
  nm() { printf '%s\n' "$2" | grep -q -E "$3" && { echo "self-test: $1: '$2' should not match" >&2; st_fail=1; }; return 0; }

  users_detect="/Users/[A-Za-z0-9_.-]+"
  users_allow="/Users/(${USERS_OK})(/|\"|'|\`|:| |,|\)|$)"
  home_detect="(^|[^/A-Za-z0-9_.-])home/[A-Za-z0-9_.-]+/"
  home_allow="(^|[^/A-Za-z0-9_.-])home/(${HOME_OK})/"
  name_detect="(^|[^A-Za-z0-9_-])(karanhudia|karan)([^A-Za-z0-9_-]|$)"

  m  "users detect"  "/Users/realname/Documents/x.pdf" "$users_detect"
  m  "users allow"   "/Users/alex/Documents/x.pdf"     "$users_allow"
  nm "users allow"   "/Users/realname/Documents/x.pdf" "$users_allow"
  m  "home detect"   "path home/realname/docs/x.txt"   "$home_detect"
  m  "home allow"    "path home/alex/docs/x.txt"       "$home_allow"
  nm "home allow"    "path home/realname/docs/x.txt"   "$home_allow"
  nm "home detect"   "/home/borg/data"                 "$home_detect"
  m  "name detect"   "user karanhudia here"            "$name_detect"
  m  "url exclude"   "github.com/karanhudia/borg-ui"   "github\.com|githubusercontent"

  [ "$st_fail" -eq 0 ] || { echo "self-test FAILED" >&2; exit 1; }
  echo "self-test OK"
  exit 0
fi

fail=0

# 1. Maintainer usernames. This covers engineering docs too, so a username in
#    a spec mockup is caught however it is spaced. Legitimate uses are project
#    URLs, funding/copyright metadata, the user-facing install docs that name
#    the account to look for, and the Owner line that records who holds a spec.
names=$(git grep -n -I -E '(^|[^A-Za-z0-9_-])(karanhudia|karan)([^A-Za-z0-9_-]|$)' -- \
          . ':!*.lock' ':!package-lock.json' "$SELF" \
          ':!.github/**' ':!README.md' ':!WORKFLOW.md' ':!Dockerfile*' \
          ':!distribution/**' ':!docker-compose.yml' ':!docs/installation.md' \
        | grep -v -E 'github\.com|githubusercontent|github\.io|codecov\.io|star-history' \
        | grep -v -E '^[^:]+:[0-9]+:\*\*Owner:\*\*' || true)
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

# 3. Relative home/<user>/ paths, the form borg archives and fixtures use.
#    Only relative: a leading slash means a real filesystem path, which is
#    usually a container or CI account and is handled above.
homes=$(git grep -n -I -E "(^|[^/A-Za-z0-9_.-])home/[A-Za-z0-9_.-]+/" -- . ':!*.lock' ':!package-lock.json' "$SELF" \
        | grep -v -E 'github\.com|githubusercontent' \
        | grep -v -E "(^|[^/A-Za-z0-9_.-])home/(${HOME_OK})/" || true)
if [ -n "$homes" ]; then
  echo "ERROR: real home/<user>/ path in tracked files. Use home/alex/ or similar." >&2
  echo "$homes" >&2; echo >&2; fail=1
fi

if [ "$fail" -ne 0 ]; then
  exit 1
fi
echo "OK: no personal paths in tracked files."
