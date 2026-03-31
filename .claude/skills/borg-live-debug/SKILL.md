---
name: borg-live-debug
description: Live Borg debugging by exec-ing into the borg-web-ui Docker container. Use when debugging borg commands, writing tests against real borg output, developing borg 2.0 features, or verifying borg behavior before writing code.
allowed-tools: Bash, Read, Edit, Write, Grep, Glob
---

# Borg Live Debug Skill

You have direct access to a running borg-web-ui Docker container. Use this to run real borg/borg2 commands, inspect actual output, and use that ground truth to write code, tests, and fixes.

## Container Details

- **Container name**: `borg-web-ui`
- **Borg 1 binary**: `borg` (e.g. `/usr/bin/borg` or via PATH)
- **Borg 2 binary**: `borg2` (e.g. `/usr/local/bin/borg2`)
- **Working dir**: `/app`
- **Data dir**: `/data` (database, SSH keys, repos)
- **Working user for borg ops**: `borg` (use `gosu borg` or `su borg -c`)

## How to exec into the container

Run commands inside the container using:

```bash
docker exec -it borg-web-ui <command>
# or as the borg user:
docker exec -u borg borg-web-ui <command>
# or for multi-step shell sessions:
docker exec borg-web-ui bash -c "<cmd1> && <cmd2>"
```

## Workflow

When the user asks to debug, test, or develop borg functionality:

### Step 1 — Verify the container is running
```bash
docker ps --filter name=borg-web-ui --format "{{.Names}} {{.Status}}"
```
If it's not running, tell the user to start it: `docker compose up -d`

### Step 2 — Probe the environment
```bash
# Check borg versions available
docker exec borg-web-ui bash -c "borg --version 2>/dev/null; borg2 --version 2>/dev/null"

# Check what repos are configured (from DB or env)
docker exec borg-web-ui bash -c "ls /data/ 2>/dev/null"
```

### Step 3 — Run the borg command and capture output
Run the exact borg command you need to test. Always capture both stdout and stderr:

```bash
docker exec -u borg borg-web-ui bash -c "BORG_PASSPHRASE='' borg list /path/to/repo 2>&1"
# For borg2:
docker exec -u borg borg-web-ui bash -c "BORG_PASSPHRASE='' borg2 rinfo /path/to/repo 2>&1"
```

**Key environment variables to set when running borg commands:**
- `BORG_PASSPHRASE` — passphrase (empty string if unencrypted)
- `BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK=yes` — skip prompts for unencrypted repos
- `BORG_RSH` — custom SSH command if needed
- `BORG_REMOTE_PATH` — path to borg on remote (for SSH repos)

### Step 4 — Use output to write code

After seeing the real output:
- Parse the exact JSON structure (use `borg ... --json` wherever possible)
- Match error messages exactly for error handling
- Match field names precisely in Python code
- Write tests using real fixture data from the output

## Common borg2 command cheat sheet (key differences from borg1)

| Task | Borg 1 | Borg 2 |
|------|--------|--------|
| Init repo | `borg init REPO` | `borg2 rcreate REPO` |
| Repo info | `borg info REPO` | `borg2 rinfo REPO` |
| Delete repo | `borg delete REPO` | `borg2 rdelete REPO` |
| List archives | `borg list REPO` | `borg2 list REPO` |
| Archive info | `borg info REPO::ARC` | `borg2 info REPO::ARC` |
| Create | `borg create REPO::ARC src/` | `borg2 create REPO::ARC src/` |
| Extract | `borg extract REPO::ARC` | `borg2 extract REPO::ARC` |
| Prune | `borg prune REPO` | `borg2 prune REPO` |
| Compact | N/A (auto) | `borg2 compact REPO` (REQUIRED after delete/prune) |
| Check | `borg check REPO` | `borg2 check REPO` |
| Mount | `borg mount REPO::ARC MNTPT` | `borg2 mount REPO::ARC MNTPT` |

## Create a temporary test repo inside the container

When you need a throwaway repo to test against:

```bash
# Create a temp repo (unencrypted for easy testing)
docker exec -u borg borg-web-ui bash -c "
  BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK=yes \
  borg init --encryption=none /tmp/test-repo-1 2>&1 &&
  echo 'test content' > /tmp/testfile.txt &&
  borg create /tmp/test-repo-1::archive-1 /tmp/testfile.txt 2>&1 &&
  borg list /tmp/test-repo-1 2>&1
"

# Same for borg2
docker exec -u borg borg-web-ui bash -c "
  BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK=yes \
  borg2 rcreate --encryption=none /tmp/test-repo-2 2>&1 &&
  echo 'test content' > /tmp/testfile.txt &&
  borg2 create /tmp/test-repo-2::archive-1 /tmp/testfile.txt 2>&1 &&
  borg2 list /tmp/test-repo-2 2>&1
"
```

## JSON output for parsing

Always prefer `--json` flag to get structured output you can map directly to Python:

```bash
docker exec -u borg borg-web-ui bash -c "borg list --json /tmp/test-repo-1 2>&1"
docker exec -u borg borg-web-ui bash -c "borg info --json /tmp/test-repo-1::archive-1 2>&1"
docker exec -u borg borg-web-ui bash -c "borg2 rinfo --json /tmp/test-repo-2 2>&1"
```

## Inspect the Python app code live

```bash
# Check what Python modules are available
docker exec borg-web-ui bash -c "cd /app && python3 -c 'from app.core.borg2 import *; print(\"ok\")'"

# Run a quick Python snippet against the live app
docker exec borg-web-ui bash -c "cd /app && python3 -c \"
import asyncio
from app.core.borg2 import borg2_rinfo
result = asyncio.run(borg2_rinfo('/tmp/test-repo-2'))
print(result)
\""
```

## Cleanup

After debugging, clean up temp repos:
```bash
docker exec borg-web-ui bash -c "rm -rf /tmp/test-repo-1 /tmp/test-repo-2 /tmp/testfile.txt"
```

## Rules

1. **Always run the command first, then write code** — never guess borg output format.
2. **Use `--json` wherever possible** — map the exact field names into Python dicts.
3. **Capture stderr** — borg sends warnings and errors to stderr; use `2>&1`.
4. **Test both binaries** — when working on borg2 features, also verify borg1 is unaffected.
5. **Clean up temp repos** after debugging sessions.
6. **If container is not running**, tell the user before attempting anything.
