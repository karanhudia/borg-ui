# Testing Guide for Borg UI

Quick guide for testing Borg UI functionality with automated test suites.

## Quick Start (30 seconds)

```bash
# Run complete test suite (setup + tests)
./run_tests.sh
```

That's it! The script will:
1. Create test Borg repositories with various structures
2. Test archive browsing functionality
3. Test all API endpoints
4. Report results

## Requirements

- **Borg Backup installed**
  ```bash
  # macOS
  brew install borgbackup

  # Ubuntu/Debian
  sudo apt install borgbackup

  # Check installation
  borg --version
  ```

- **Python 3.8+** with `requests`
  ```bash
  pip3 install requests
  ```

- **Borg UI running**
  ```bash
  # Docker (recommended)
  docker-compose up -d

  # Or manually
  # Terminal 1: Backend
  cd app && uvicorn main:app --reload --port 8081

  # Terminal 2: Frontend
  cd frontend && npm run dev
  ```

## What Gets Tested

### 1. Archive Contents Bug Fix
Tests the specific issue where archives only showed 1-3 folders instead of all 16:

```
Expected: 18 items at root (Documents, Photos, Code, Videos, Folder5-16, hidden files)
Previously: Only 1-3 items showing due to path splitting bug
Fix: Strip leading slashes before splitting paths
```

### 2. Repository Types
- **Unencrypted repos** - Standard testing
- **Encrypted repos** - Passphrase handling (password: `test123`)
- **Large repos** - Performance testing (5000+ files)

### 3. Archive Scenarios
- **Full backup** - All source data
- **Partial backup** - Selected folders only
- **Single folder** - One directory
- **Nested navigation** - Subdirectory browsing

### 4. API Endpoints
- Authentication (login, user info)
- Repository operations (list, create, delete)
- Archive browsing
- Config validation
- Health checks
- Error handling

## Test Output Examples

### ✅ Success
```
╔════════════════════════════════════════════════════════════════╗
║                    TEST SUMMARY                                ║
╚════════════════════════════════════════════════════════════════╝

  Tests Passed:  3
  Tests Failed:  0
  Pass Rate:     100%
  Duration:      45s

🎉 All tests passed! Borg UI is working correctly.
```

### ❌ Failure
```
Testing Archive: test-full-backup
📂 Testing path: (root)
  Borg found: 18 items
  UI found: 3 items
  ❌ FAIL - Contents don't match!
    Missing in UI (15 items):
      - Documents
      - Photos
      - Code
      ...
```

## Test Scenarios

### Test 1: Basic Archive Browsing
```bash
# Create test environment
./tests/setup_test_env.sh

# Run specific test
python3 tests/test_archive_contents.py
```

**What it tests:**
- Root directory shows all folders (not just 1-3)
- Navigation into subdirectories works
- File counts match borg CLI output

### Test 2: Encrypted Repository
```bash
# Automatically tested by run_tests.sh
# Or manually add repo2-encrypted with passphrase "test123"
```

**What it tests:**
- Passphrase authentication
- Encrypted archive browsing
- Same content accuracy as unencrypted

### Test 3: Large Repository Performance
```bash
# Test with repo3-large (5000+ files)
python3 tests/test_archive_contents.py
```

**What it tests:**
- Performance with many files
- UI responsiveness
- No timeouts or errors

### Test 4: Manual Verification
```bash
# 1. Check test info
cat /tmp/borg-ui-tests/TEST_INFO.txt

# 2. List with borg CLI
borg list /tmp/borg-ui-tests/repositories/repo1-unencrypted::test-full-backup

# 3. Compare with UI
# Open Borg UI → Restore → Select repo1 → Select test-full-backup
# Should see same folders as borg list output
```

## Command Reference

### Run All Tests
```bash
./run_tests.sh                    # Setup + run all tests
./run_tests.sh --skip-setup       # Use existing test data
./run_tests.sh --clean            # Cleanup after tests
./run_tests.sh --url http://localhost:7879  # Custom URL
```

### Setup Test Environment Only
```bash
./tests/setup_test_env.sh                   # Default: /tmp/borg-ui-tests
./tests/setup_test_env.sh /custom/path      # Custom location
```

### Run Specific Tests
```bash
# Archive contents tests only
python3 tests/test_archive_contents.py

# API tests only
python3 test_app.py

# Custom test directory
python3 tests/test_archive_contents.py /custom/test/dir
```

### Manual Borg Commands
```bash
TEST_DIR=/tmp/borg-ui-tests

# List repositories
ls -la $TEST_DIR/repositories/

# List archives in repo1
borg list $TEST_DIR/repositories/repo1-unencrypted

# List archive contents (root)
borg list --json-lines $TEST_DIR/repositories/repo1-unencrypted::test-full-backup

# List archive contents (specific folder)
borg list $TEST_DIR/repositories/repo1-unencrypted::test-full-backup Documents

# Mount archive for comparison
mkdir /tmp/borg-mount
borg mount $TEST_DIR/repositories/repo1-unencrypted::test-full-backup /tmp/borg-mount
ls -la /tmp/borg-mount
borg umount /tmp/borg-mount
```

## Troubleshooting

### "borg command not found"
```bash
# Install borg first
brew install borgbackup        # macOS
sudo apt install borgbackup    # Ubuntu/Debian
```

### "Server not accessible"
```bash
# Check if Borg UI is running
curl http://localhost:8081/

# Check Docker
docker ps | grep borg-web-ui

# Check logs
docker logs borg-web-ui

# Restart
docker-compose restart
```

### "Authentication failed"
```bash
# Verify default credentials work
curl -X POST http://localhost:8081/api/auth/login \
  -d "username=admin&password=admin123"

# If you changed the password, update test scripts
# or create fresh database: docker-compose down -v && docker-compose up -d
```

### "Test directory not found"
```bash
# Run setup first
./tests/setup_test_env.sh

# Or specify location
./run_tests.sh --test-dir /path/to/tests
```

### Tests pass but UI shows wrong data
```bash
# Clear browser cache
# Or open in incognito/private mode

# Check if using correct API endpoint
# Verify repository path in UI matches test repo path
```

## Cleanup

Remove test environment:
```bash
rm -rf /tmp/borg-ui-tests
```

Remove test repos from UI:
1. Login to Borg UI
2. Go to Repositories
3. Delete "Test Repo 1", "Test Repo 2", etc.

## CI/CD Integration

Add to `.github/workflows/test.yml`:

```yaml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Install dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y borgbackup
          pip3 install requests

      - name: Start Borg UI
        run: docker-compose up -d

      - name: Wait for service
        run: sleep 15

      - name: Run tests
        run: ./run_tests.sh

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v2
        with:
          name: test-results
          path: /tmp/borg-ui-tests/
```

## Test Development

See `tests/README.md` for detailed information on:
- Writing new tests
- Test architecture
- Adding test scenarios
- Debugging test failures

## Support

- **GitHub Issues**: Report bugs with test output attached
- **Logs**: Include `docker logs borg-web-ui` output
- **Test Info**: Include `/tmp/borg-ui-tests/TEST_INFO.txt`
- **Borg Version**: Include `borg --version` output
