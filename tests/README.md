# Borg UI Testing Suite

Comprehensive testing infrastructure for Borg UI, including unit tests, integration tests, and end-to-end testing with real Borg repositories.

## Overview

This testing suite provides:

1. **Automated Test Environment Setup** - Creates real Borg repositories with various structures
2. **Archive Contents Testing** - Validates archive browsing against actual borg CLI output
3. **API Testing** - Tests all API endpoints and functionality
4. **Regression Testing** - Prevents bugs from reoccurring

## Quick Start

### Prerequisites

- Python 3.8+
- Borg backup installed (`brew install borgbackup` on macOS)
- Borg UI running (default: `http://localhost:8081`)
- Required Python packages: `requests`

### Run All Tests

```bash
# 1. Set up test environment (creates repos and test data)
./tests/setup_test_env.sh

# 2. Run archive contents tests
python3 tests/test_archive_contents.py

# 3. Run API tests
python3 test_app.py
```

## Test Components

### 1. Test Environment Setup (`setup_test_env.sh`)

Creates a comprehensive test environment with:

- **3 Test Repositories:**
  - `repo1-unencrypted`: Standard repo with 3 archives (various content)
  - `repo2-encrypted`: Encrypted repo (passphrase: `test123`)
  - `repo3-large`: Performance testing repo (5000+ files)

- **Test Data Structure:**
  - 16+ root folders (simulating real backup scenarios)
  - Documents, Photos, Code, Videos folders
  - Multiple nesting levels
  - Hidden files and folders (dotfiles)
  - Various file types

**Usage:**
```bash
# Use default location (/tmp/borg-ui-tests)
./tests/setup_test_env.sh

# Or specify custom location
./tests/setup_test_env.sh /path/to/test/dir
```

**Output:**
- Test repositories in `/tmp/borg-ui-tests/repositories/`
- Source data in `/tmp/borg-ui-tests/source_data/`
- Test info file: `/tmp/borg-ui-tests/TEST_INFO.txt`

### 2. Archive Contents Testing (`test_archive_contents.py`)

Validates that Borg UI displays archive contents correctly by:

1. Querying borg CLI for actual archive contents
2. Querying Borg UI API for displayed contents
3. Comparing results and reporting discrepancies

**Usage:**
```bash
# Test with default settings
python3 tests/test_archive_contents.py

# Specify custom test directory
python3 tests/test_archive_contents.py /custom/test/dir

# Test against different Borg UI instance
python3 tests/test_archive_contents.py --url http://localhost:7879
```

**Tests:**
- Root directory listing (the "16 folders" bug scenario)
- Nested directory navigation
- Multiple archive types (full, partial, single folder)
- Encrypted repository access
- Large repository performance

**Output:**
```
✅ PASS - Contents match perfectly!
❌ FAIL - Contents don't match!
  Missing in UI (5 items):
    - Folder1
    - Folder2
    ...
```

### 3. API Testing (`test_app.py`)

Tests all Borg UI API endpoints:

- Server availability
- SPA routing
- Authentication
- Protected endpoints
- Repository operations (CRUD)
- Config validation
- Health checks
- Error handling

**Usage:**
```bash
python3 test_app.py

# Test different instance
python3 test_app.py --url http://localhost:7879

# Save results to JSON
python3 test_app.py --output results.json
```

## Test Scenarios

### Scenario 1: Archive Root Directory Bug

**Problem:** Archive browsing only shows 1-3 folders instead of all 16

**Test:**
```bash
./tests/setup_test_env.sh
python3 tests/test_archive_contents.py
```

**Expected Result:**
```
Testing Archive: test-full-backup
📂 Testing path: (root)
  Borg found: 18 items
  UI found: 18 items
  ✅ PASS - Contents match perfectly!
```

**What it tests:**
- Parsing of absolute paths returned by borg
- Proper splitting of paths by `/`
- Deduplication logic for immediate children
- Handling of leading slashes in paths

### Scenario 2: Nested Directory Navigation

**Test:**
```bash
python3 tests/test_archive_contents.py
# Tests paths: "", "Documents", "Photos/2024", "Code"
```

**What it tests:**
- Navigation into subdirectories
- Relative path calculation
- Immediate children vs nested items
- Path parameter passing

### Scenario 3: Encrypted Repository

**Test:**
```bash
# Automatically tests repo2-encrypted with passphrase "test123"
python3 tests/test_archive_contents.py
```

**What it tests:**
- Passphrase handling
- Encrypted repository listing
- Archive contents in encrypted repos

### Scenario 4: Large Repository Performance

**Test:**
```bash
./tests/setup_test_env.sh
# Then manually add repo3-large to Borg UI
# Browse archive: large-backup (100 folders, 5000 files)
```

**What it tests:**
- Performance with 5000+ files
- Memory usage
- Response times
- UI responsiveness

## Manual Testing Workflow

### 1. Setup Test Environment

```bash
cd /Users/karanhudia/Documents/Projects/borg-ui
./tests/setup_test_env.sh
```

### 2. Start Borg UI

```bash
# Using Docker
docker-compose up -d

# Or locally
cd frontend && npm run dev &
cd app && uvicorn main:app --reload
```

### 3. Add Test Repositories

1. Open Borg UI: `http://localhost:8081`
2. Login (admin/admin123)
3. Go to Repositories
4. Add repository:
   - **Name:** Test Repo 1
   - **Type:** Local
   - **Path:** `/tmp/borg-ui-tests/repositories/repo1-unencrypted`
   - **Encryption:** None

### 4. Test Archive Browsing

1. Go to Restore page
2. Select "Test Repo 1"
3. Select archive "test-full-backup"
4. Verify you see **18 items** at root level (not just 1-3)
5. Expected folders:
   - Documents
   - Photos
   - Code
   - Videos
   - Folder5 through Folder16
   - .config (hidden file)
   - .hidden_folder

### 5. Compare with Borg CLI

```bash
# List root contents
borg list --json-lines /tmp/borg-ui-tests/repositories/repo1-unencrypted::test-full-backup \
  | jq -r '.path' | sed 's|^/||' | cut -d'/' -f1 | sort -u

# Should show same items as UI
```

### 6. Test Navigation

1. Click on "Documents" folder
2. Should see: Work, Personal
3. Click on "Work"
4. Should see: Projects, notes.txt
5. Navigate back and test other folders

### 7. Run Automated Tests

```bash
python3 tests/test_archive_contents.py
```

Expected output: All tests should PASS

## Troubleshooting

### Test Environment Setup Fails

**Error:** `borg command not found`

**Solution:**
```bash
# macOS
brew install borgbackup

# Ubuntu/Debian
sudo apt install borgbackup

# Arch
sudo pacman -S borg
```

### Archive Contents Test Fails

**Error:** `Authentication failed`

**Solution:**
- Ensure Borg UI is running at `http://localhost:8081`
- Verify default credentials (admin/admin123) work
- Check if you've changed the admin password

**Error:** `Test directory not found`

**Solution:**
```bash
./tests/setup_test_env.sh
```

### API Test Fails

**Error:** `Server not accessible`

**Solution:**
```bash
# Check if Borg UI is running
curl http://localhost:8081/

# Check Docker status
docker ps | grep borg

# Check logs
docker logs borg-web-ui
```

## Writing New Tests

### Adding Archive Content Tests

Edit `tests/test_archive_contents.py`:

```python
test_configs = [
    {
        "name": "My Test Repo",
        "path": "/path/to/repo",
        "passphrase": None,  # or "password"
        "archives": [
            {
                "name": "my-archive",
                "test_paths": ["", "some/path", "another/path"]
            }
        ]
    }
]
```

### Adding API Tests

Edit `test_app.py`:

```python
def test_my_feature(self) -> bool:
    """Test my new feature"""
    try:
        response = self.session.get(
            f"{self.base_url}/api/my-endpoint",
            headers=self.headers,
            timeout=5
        )

        if response.status_code == 200:
            self.log_test("My Feature", True, "Works!")
            return True
        else:
            self.log_test("My Feature", False, f"Failed: {response.status_code}")
            return False
    except Exception as e:
        self.log_test("My Feature", False, f"Error: {e}")
        return False
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Install borg
        run: sudo apt-get install -y borgbackup

      - name: Setup test environment
        run: ./tests/setup_test_env.sh

      - name: Start Borg UI
        run: docker-compose up -d

      - name: Wait for service
        run: sleep 10

      - name: Run tests
        run: |
          python3 tests/test_archive_contents.py
          python3 test_app.py
```

## Test Coverage

Current test coverage:

- ✅ Archive root directory listing
- ✅ Nested directory navigation
- ✅ Multiple archives per repository
- ✅ Encrypted repositories
- ✅ Large repositories (5000+ files)
- ✅ API authentication
- ✅ Repository CRUD operations
- ✅ Config validation
- ✅ Health checks
- ⏳ Restore operations (TODO)
- ⏳ Backup operations (TODO)
- ⏳ SSH repositories (TODO)
- ⏳ Schedule management (TODO)

## Cleanup

Remove test environment:

```bash
rm -rf /tmp/borg-ui-tests
```

Remove test repositories from Borg UI:

1. Go to Repositories page
2. Delete test repositories manually

## Support

For issues with tests:
1. Check logs: `docker logs borg-web-ui`
2. Verify test environment: `cat /tmp/borg-ui-tests/TEST_INFO.txt`
3. Run manual borg commands to verify repos are valid
4. Open an issue on GitHub with test output
