# Cache Lock Testing Guide

## What We Fixed

The `break-lock` function now:
1. Breaks the repository lock using `borg break-lock`
2. Gets the **actual repository ID** from `borg info --json`
3. Uses that ID to find the cache directory: `~/.cache/borg/<repo-id>/`
4. Removes all `lock.*` files/directories in the cache

## Manual Testing Steps

### Step 1: Wait for a Real Borg Operation

First, we need a borg operation to run so that a cache gets created.

**Option A: Use the UI**
1. Go to Backup or Archives page
2. Select any repository
3. Let it load (this will create/update cache)

**Option B: Run manually**
```bash
# Check if you have any repositories without passphrases
docker exec borg-web-ui borg list /local/Users/karanhudia/test-backups/<repo-name>/
```

### Step 2: Find the Cache Directory

```bash
# Look for any borg caches
docker exec borg-web-ui find /home/borg/.cache/borg -type d -maxdepth 1 2>/dev/null

# Example output:
# /home/borg/.cache/borg/09098cc66955d2dcf87b6af919b3241216bee7ba5df297b68e302020fd994205
```

### Step 3: Get Repository ID from a Real Repo

For a repository that you can access (knows passphrase):
```bash
REPO_PATH="/local/Users/karanhudia/test-backups/<your-repo>"

# Get repository ID
docker exec borg-web-ui sh -c "BORG_PASSPHRASE='<passphrase>' borg info --json '$REPO_PATH'" | jq -r '.repository.id'
```

### Step 4: Create Test Cache Locks

Once you have the repo ID:
```bash
REPO_ID="<id-from-step-3>"
CACHE_DIR="/home/borg/.cache/borg/$REPO_ID"

# Create fake locks
docker exec borg-web-ui mkdir -p "$CACHE_DIR/lock.exclusive"
docker exec borg-web-ui sh -c "echo 'test-lock' > $CACHE_DIR/lock.exclusive/fake.lock"
docker exec borg-web-ui sh -c "echo 'test-roster' > $CACHE_DIR/lock.roster"

# Verify locks exist
docker exec borg-web-ui ls -la "$CACHE_DIR" | grep lock
```

### Step 5: Test Break Lock via UI

1. Go to Archives/Repositories page
2. Select the repository you created locks for
3. Wait for lock error (should appear quickly)
4. Click "Break Lock"
5. Confirm

### Step 6: Verify in Logs

Watch the Docker logs:
```bash
docker logs -f borg-web-ui
```

You should see:
```
WARNING: Breaking stale lock, repository=<repo-path>
INFO: Found repository ID for cache cleanup, repo_id=<actual-id>
INFO: Breaking cache locks, cache_dir=/home/borg/.cache/borg/<id>, count=2
INFO: Removed cache lock file, file=/home/borg/.cache/borg/<id>/lock.roster
INFO: Removed cache lock directory, dir=/home/borg/.cache/borg/<id>/lock.exclusive
```

### Step 7: Verify Locks Are Gone

```bash
REPO_ID="<your-repo-id>"
CACHE_DIR="/home/borg/.cache/borg/$REPO_ID"

# Check if locks are removed
docker exec borg-web-ui ls -la "$CACHE_DIR" | grep lock || echo "✓ No locks found - Success!"
```

## Expected Behavior

### Before Fix
- Breaking lock only removed repository lock
- Cache locks remained
- User still got 423 errors
- Had to browse archives to clear cache lock

### After Fix
- Breaking lock removes both repository AND cache locks
- User gets immediate success
- No 423 errors after breaking
- Logs show repo ID detection and cache cleanup

## Troubleshooting

### If Repository ID Not Found
The code will log: `WARNING: Could not extract repository ID from borg info`

This happens if:
- Repository is encrypted and passphrase is wrong
- Repository doesn't exist
- Network issues for SSH repos

**Fallback**: The code still breaks the repository lock, just can't clean cache

### If Cache Directory Doesn't Exist
The code will log: `INFO: Cache directory does not exist`

This is fine - means no cache was ever created, so no cache locks either.

### If No Locks Found
The code will log: `INFO: No cache locks found`

This is fine - means cache exists but isn't locked.

## Additional Test: SSH Repository

For SSH repositories (like the GitHub issue showed):
```bash
# The repository URL matters for the ID calculation
# Example: ssh://user@host:22/path/to/repo

# After breaking lock on SSH repo, logs should show:
# - Repository ID from borg info (not calculated hash)
# - Cache cleanup attempt
# - Lock removal confirmation
```

## Success Criteria

✓ Repository lock is broken
✓ Cache locks are identified and removed
✓ Logs show actual repository ID (not calculated hash)
✓ No 423 errors after breaking lock
✓ Archives/info load successfully after break-lock
