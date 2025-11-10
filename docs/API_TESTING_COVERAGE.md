# API Testing Coverage Documentation

**Last Updated:** 2025-11-10

## Overall Coverage Summary

| Metric | Value |
|--------|-------|
| **Total API Endpoints** | 90 |
| **Overall Code Coverage** | 30.53% |
| **Test Files** | 35+ |
| **Total Tests** | 241 passing |

## Module Coverage Breakdown

| Module | Coverage | Endpoints | Test Files | Priority |
|--------|----------|-----------|------------|----------|
| archives.py | **70.33%** ✅ | 5 | test_api_archives.py, test_api_archives_specific.py, test_api_archives_comprehensive.py | HIGH |
| dashboard.py | **76.27%** ✅ | 3 | test_api_dashboard.py, test_api_dashboard_comprehensive.py | HIGH |
| database/models.py | **100.00%** ✅ | N/A | test_models.py | HIGH |
| config.py | **62.96%** ⚠️ | N/A | test_config.py | MEDIUM |
| system.py | **60.00%** ⚠️ | 1 | test_api_system.py | MEDIUM |
| main.py | **53.68%** ⚠️ | N/A | Multiple | MEDIUM |
| security.py | **52.63%** ⚠️ | N/A | test_security.py, test_auth_comprehensive.py | MEDIUM |
| auth.py | **50.41%** ⚠️ | 9 | test_api_auth.py, test_auth_specific.py, test_auth_comprehensive.py | HIGH |
| borg.py | **43.88%** ⚠️ | N/A | test_borg_wrapper.py | HIGH |
| borg_errors.py | **42.11%** ⚠️ | N/A | test_borg_errors.py | MEDIUM |
| events.py | **36.03%** ❌ | 1 | test_api_events.py | MEDIUM |
| backup_service.py | **31.25%** ❌ | N/A | test_api_backup.py, test_backup_service.py | HIGH |
| filesystem.py | **27.55%** ❌ | 2 | None | LOW |
| backup.py | **26.46%** ❌ | 6 | test_api_backup.py | HIGH |
| restore.py | **24.24%** ❌ | 7 | test_api_restore.py | HIGH |
| schedule.py | **22.30%** ❌ | 10 | test_api_schedule.py | HIGH |
| settings.py | **21.94%** ❌ | 11 | test_api_settings.py | HIGH |
| repositories.py | **20.10%** ❌ | 21 | test_api_repositories.py, test_repositories_comprehensive.py | HIGH |
| ssh_keys.py | **18.24%** ❌ | 13 | test_api_ssh_keys.py | MEDIUM |
| browse.py | **13.91%** ❌ | 1 | test_api_browse.py | LOW |
| compact_service.py | **9.71%** ❌ | N/A | None | LOW |
| check_service.py | **9.09%** ❌ | N/A | None | LOW |
| restore_service.py | **8.38%** ❌ | N/A | None | MEDIUM |

---

## Detailed Endpoint Coverage

### 1. Archives API (`/api/archives`) - 5 endpoints - **70.33% Coverage** ✅

| Method | Endpoint | Test Coverage | Test File | Status |
|--------|----------|---------------|-----------|--------|
| GET | `/list` | ✅ Full | test_api_archives_comprehensive.py | Working |
| GET | `/{archive_id}/info` | ✅ Full | test_api_archives_comprehensive.py | Working |
| GET | `/{archive_id}/contents` | ✅ Full | test_api_archives_comprehensive.py | Working |
| DELETE | `/{archive_id}` | ✅ Full | test_api_archives_comprehensive.py | Working |
| GET | `/download` | ✅ Partial | test_api_archives_comprehensive.py | Working |

**Recent Improvements:**
- Added comprehensive tests with mocked borg responses
- Tests cover success, failure, and edge cases
- Increased coverage from 36.81% to 70.33% (+33.52%)

---

### 2. Auth API (`/api/auth`) - 9 endpoints - **50.41% Coverage** ⚠️

| Method | Endpoint | Test Coverage | Test File | Status |
|--------|----------|---------------|-----------|--------|
| POST | `/login` | ✅ Full | test_api_auth.py | Working |
| POST | `/logout` | ✅ Partial | test_api_auth.py | Working |
| POST | `/refresh` | ⚠️ Basic | test_api_auth.py | Needs more tests |
| GET | `/me` | ✅ Full | test_api_auth.py | Working |
| POST | `/change-password` | ⚠️ Basic | test_api_auth.py | Needs more tests |
| POST | `/register` | ❌ None | None | Needs tests |
| POST | `/forgot-password` | ❌ None | None | Needs tests |
| POST | `/reset-password` | ❌ None | None | Needs tests |
| POST | `/verify-email` | ❌ None | None | Needs tests |

**Recommendations:**
- Add tests for password reset flow
- Add tests for email verification
- Test token refresh edge cases

---

### 3. Backup API (`/api/backup`) - 6 endpoints - **26.46% Coverage** ❌

| Method | Endpoint | Test Coverage | Test File | Status |
|--------|----------|---------------|-----------|--------|
| POST | `/start` | ⚠️ Basic | test_api_backup.py | Needs more tests |
| GET | `/status/{job_id}` | ⚠️ Basic | test_api_backup.py | Needs more tests |
| GET | `/jobs` | ✅ Partial | test_api_backup.py | Working |
| POST | `/cancel/{job_id}` | ⚠️ Basic | test_api_backup.py | Needs more tests |
| GET | `/logs/{job_id}` | ⚠️ Basic | test_api_backup.py | Needs more tests |
| GET | `/logs/{job_id}/download` | ❌ None | None | Needs tests |

**Backup Service (`backup_service.py`) - 31.25% Coverage** ❌
- Recently added 21 new tests in `test_backup_service.py`
- Improved from 6.27% to 31.25% (+24.98%)
- Still needs tests for `execute_backup` main flow

**Recommendations:**
- Add tests for successful backup execution with mocked borg
- Test backup cancellation flow
- Test log streaming functionality
- Test pre/post backup hooks

---

### 4. Browse API (`/api/browse`) - 1 endpoint - **13.91% Coverage** ❌

| Method | Endpoint | Test Coverage | Test File | Status |
|--------|----------|---------------|-----------|--------|
| GET | `/{repository_id}/{archive_name}` | ⚠️ Basic | test_api_browse.py | Needs more tests |

**Recommendations:**
- Add comprehensive tests with mocked responses
- Test different path navigation scenarios
- Test error cases

---

### 5. Dashboard API (`/api/dashboard`) - 3 endpoints - **76.27% Coverage** ✅

| Method | Endpoint | Test Coverage | Test File | Status |
|--------|----------|---------------|-----------|--------|
| GET | `/status` | ✅ Full | test_api_dashboard_comprehensive.py | Working |
| GET | `/metrics` | ✅ Full | test_api_dashboard_comprehensive.py | Working |
| GET | `/schedule` | ✅ Full | test_api_dashboard_comprehensive.py | Working |

**Status:** Well tested, good coverage

---

### 6. Events API (`/api/events`) - 1 endpoint - **36.03% Coverage** ⚠️

| Method | Endpoint | Test Coverage | Test File | Status |
|--------|----------|---------------|-----------|--------|
| GET | `/stream` (SSE) | ⚠️ Partial | test_api_events.py | Needs more tests |

**Recommendations:**
- Test SSE connection lifecycle
- Test event broadcasting
- Test client disconnection handling

---

### 7. Filesystem API (`/api/filesystem`) - 2 endpoints - **27.55% Coverage** ❌

| Method | Endpoint | Test Coverage | Test File | Status |
|--------|----------|---------------|-----------|--------|
| GET | `/browse` | ❌ None | None | Needs tests |
| POST | `/validate-path` | ❌ None | None | Needs tests |

**Recommendations:**
- Add tests for directory browsing
- Test path validation logic
- Test permission checks

---

### 8. Repositories API (`/api/repositories`) - 21 endpoints - **20.10% Coverage** ❌

| Method | Endpoint | Test Coverage | Test File | Status |
|--------|----------|---------------|-----------|--------|
| GET | `/` | ✅ Partial | test_api_repositories.py | Working |
| POST | `/` | ✅ Partial | test_api_repositories.py | Working |
| POST | `/import` | ⚠️ Basic | test_repositories_comprehensive.py | Needs more tests |
| GET | `/{id}` | ⚠️ Basic | test_api_repositories.py | Needs more tests |
| PUT | `/{id}` | ⚠️ Basic | test_api_repositories.py | Needs more tests |
| DELETE | `/{id}` | ⚠️ Basic | test_api_repositories.py | Needs more tests |
| POST | `/{id}/check` | ⚠️ Basic | test_repositories_comprehensive.py | Needs more tests |
| POST | `/{id}/compact` | ⚠️ Basic | test_repositories_comprehensive.py | Needs more tests |
| POST | `/{id}/prune` | ⚠️ Basic | test_repositories_comprehensive.py | Needs more tests |
| POST | `/{id}/break-lock` | ❌ None | None | Needs tests |
| GET | `/{id}/stats` | ❌ None | None | Needs tests |
| GET | `/{id}/archives` | ⚠️ Basic | test_api_repositories.py | Needs more tests |
| GET | `/{id}/info` | ❌ None | None | Needs tests |
| GET | `/{id}/check-jobs` | ❌ None | None | Needs tests |
| GET | `/check-jobs/{job_id}` | ❌ None | None | Needs tests |
| GET | `/{id}/compact-jobs` | ❌ None | None | Needs tests |
| GET | `/compact-jobs/{job_id}` | ❌ None | None | Needs tests |
| GET | `/{id}/running-jobs` | ❌ None | None | Needs tests |
| GET | `/{id}/archives/{name}/info` | ❌ None | None | Needs tests |
| GET | `/{id}/archives/{name}/files` | ❌ None | None | Needs tests |
| POST | `/{id}/initialize` | ❌ None | None | Needs tests |

**Recommendations:**
- Priority: Add tests for repository CRUD operations
- Add tests for repository maintenance operations (check, compact, prune)
- Test lock management
- Test statistics retrieval
- Test job status tracking

---

### 9. Restore API (`/api/restore`) - 7 endpoints - **24.24% Coverage** ❌

| Method | Endpoint | Test Coverage | Test File | Status |
|--------|----------|---------------|-----------|--------|
| GET | `/repositories` | ⚠️ Basic | test_api_restore.py | Needs more tests |
| GET | `/archives/{repository_id}` | ⚠️ Basic | test_api_restore.py | Needs more tests |
| POST | `/preview` | ❌ None | None | Needs tests |
| POST | `/start` | ❌ None | None | Needs tests |
| GET | `/jobs` | ⚠️ Basic | test_api_restore.py | Needs more tests |
| GET | `/status/{job_id}` | ⚠️ Basic | test_api_restore.py | Needs more tests |
| POST | `/cancel/{job_id}` | ❌ None | None | Needs tests |

**Restore Service (`restore_service.py`) - 8.38% Coverage** ❌
- Lowest coverage among services
- Needs comprehensive testing

**Recommendations:**
- HIGH PRIORITY: Add tests for restore execution flow
- Test preview functionality
- Test restore job management
- Test cancellation handling

---

### 10. Schedule API (`/api/schedule`) - 10 endpoints - **22.30% Coverage** ❌

| Method | Endpoint | Test Coverage | Test File | Status |
|--------|----------|---------------|-----------|--------|
| GET | `/` | ⚠️ Basic | test_api_schedule.py | Needs more tests |
| POST | `/` | ⚠️ Basic | test_api_schedule.py | Needs more tests |
| GET | `/{id}` | ⚠️ Basic | test_api_schedule.py | Needs more tests |
| PUT | `/{id}` | ❌ None | None | Needs tests |
| DELETE | `/{id}` | ❌ None | None | Needs tests |
| POST | `/{id}/toggle` | ❌ None | None | Needs tests |
| POST | `/{id}/run-now` | ❌ None | None | Needs tests |
| POST | `/validate-cron` | ❌ None | None | Needs tests |
| GET | `/cron-presets` | ❌ None | None | Needs tests |
| GET | `/upcoming-jobs` | ❌ None | None | Needs tests |

**Recommendations:**
- Add tests for schedule CRUD operations
- Test cron expression validation
- Test job scheduling and execution
- Test toggle functionality

---

### 11. Settings API (`/api/settings`) - 11 endpoints - **21.94% Coverage** ❌

| Method | Endpoint | Test Coverage | Test File | Status |
|--------|----------|---------------|-----------|--------|
| GET | `/system` | ⚠️ Basic | test_api_settings.py | Needs more tests |
| PUT | `/system` | ❌ None | None | Needs tests |
| GET | `/users` | ⚠️ Basic | test_api_settings.py | Needs more tests |
| POST | `/users` | ⚠️ Basic | test_api_settings.py | Needs more tests |
| PUT | `/users/{id}` | ❌ None | None | Needs tests |
| DELETE | `/users/{id}` | ❌ None | None | Needs tests |
| POST | `/users/{id}/reset-password` | ❌ None | None | Needs tests |
| GET | `/profile` | ⚠️ Basic | test_api_settings.py | Needs more tests |
| PUT | `/profile` | ❌ None | None | Needs tests |
| POST | `/change-password` | ❌ None | None | Needs tests |
| POST | `/system/cleanup` | ❌ None | None | Needs tests |

**Recommendations:**
- Add tests for user management
- Test system settings updates
- Test profile management
- Test cleanup operations

---

### 12. SSH Keys API (`/api/ssh-keys`) - 13 endpoints - **18.24% Coverage** ❌

| Method | Endpoint | Test Coverage | Test File | Status |
|--------|----------|---------------|-----------|--------|
| GET | `/system-key` | ⚠️ Basic | test_api_ssh_keys.py | Needs more tests |
| POST | `/generate` | ⚠️ Basic | test_api_ssh_keys.py | Needs more tests |
| GET | `/` | ⚠️ Basic | test_api_ssh_keys.py | Needs more tests |
| POST | `/` | ❌ None | None | Needs tests |
| POST | `/quick-setup` | ❌ None | None | Needs tests |
| GET | `/{id}` | ❌ None | None | Needs tests |
| PUT | `/{id}` | ❌ None | None | Needs tests |
| DELETE | `/{id}` | ❌ None | None | Needs tests |
| POST | `/{id}/deploy` | ❌ None | None | Needs tests |
| POST | `/{id}/test-connection` | ❌ None | None | Needs tests |
| GET | `/connections` | ❌ None | None | Needs tests |
| POST | `/import` | ❌ None | None | Needs tests |
| GET | `/export/{id}` | ❌ None | None | Needs tests |

**Recommendations:**
- Add tests for SSH key generation
- Test key deployment
- Test connection validation
- Test key CRUD operations

---

### 13. System API (`/api/system`) - 1 endpoint - **60.00% Coverage** ⚠️

| Method | Endpoint | Test Coverage | Test File | Status |
|--------|----------|---------------|-----------|--------|
| GET | `/health` | ✅ Full | test_api_system.py | Working |

**Status:** Adequate coverage for simple health endpoint

---

## Test File Organization

### Unit Tests (`tests/unit/`)
- `test_api_archives.py` - Basic archives tests
- `test_api_archives_specific.py` - Specific archives scenarios
- `test_api_archives_comprehensive.py` - **NEW** Comprehensive archives tests with mocks
- `test_api_auth.py` - Auth endpoint tests
- `test_auth_comprehensive.py` - Detailed auth flow tests
- `test_auth_specific.py` - Specific auth scenarios
- `test_api_backup.py` - Backup endpoint tests
- `test_backup_service.py` - **NEW** Backup service unit tests
- `test_api_browse.py` - Browse endpoint tests
- `test_api_dashboard.py` - Dashboard endpoint tests
- `test_api_dashboard_comprehensive.py` - Comprehensive dashboard tests
- `test_api_events.py` - Events endpoint tests
- `test_api_repositories.py` - Repositories endpoint tests
- `test_repositories_comprehensive.py` - Detailed repositories tests
- `test_api_restore.py` - Restore endpoint tests
- `test_api_schedule.py` - Schedule endpoint tests
- `test_api_settings.py` - Settings endpoint tests
- `test_api_ssh_keys.py` - SSH keys endpoint tests
- `test_api_system.py` - System endpoint tests
- `test_borg_wrapper.py` - Borg interface tests
- `test_borg_errors.py` - Borg error handling tests
- `test_config.py` - Configuration tests
- `test_database_operations.py` - Database operation tests
- `test_models.py` - Database model tests
- `test_security.py` - Security utility tests

### Integration Tests (`tests/integration/`)
- `test_integration_wrapper.py` - Integration test wrapper
- `test_archive_contents.py` - Archive content testing
- `test_archive_directory_browsing.py` - Directory browsing tests
- `test_multiple_source_dirs.py` - Multi-source backup tests

---

## Priority Action Items

### High Priority (Affecting Critical Features)
1. **Backup Service** (31.25% → Target: 60%)
   - Add tests for main backup execution flow
   - Test hook execution (pre/post backup)
   - Test progress tracking and log streaming

2. **Restore Service** (8.38% → Target: 50%)
   - **CRITICAL**: Add comprehensive restore tests
   - Test restore preview functionality
   - Test restore execution and progress tracking

3. **Repositories API** (20.10% → Target: 60%)
   - Test repository maintenance operations
   - Test job status tracking
   - Test archive management

4. **Schedule API** (22.30% → Target: 50%)
   - Test cron scheduling
   - Test job execution triggers
   - Test schedule management

### Medium Priority
5. **Auth API** (50.41% → Target: 70%)
   - Complete password reset flow tests
   - Add email verification tests

6. **Settings API** (21.94% → Target: 50%)
   - Test user management operations
   - Test system configuration updates

7. **Events API** (36.03% → Target: 60%)
   - Test SSE connection management
   - Test event broadcasting

### Low Priority
8. **SSH Keys API** (18.24% → Target: 40%)
   - Test key management operations
   - Test deployment and validation

9. **Browse/Filesystem APIs** (13.91%/27.55% → Target: 40%)
   - Add basic endpoint tests

10. **Service Classes** (Check/Compact services at ~9%)
    - Add unit tests for service methods

---

## Coverage Goals

| Timeline | Target Coverage | Key Achievements |
|----------|----------------|-------------------|
| **Current** | 30.53% | Baseline established, archives & dashboard good |
| **Week 1** | 40% | Complete backup, restore, repositories tests |
| **Week 2** | 50% | Complete schedule, settings, auth tests |
| **Week 3** | 60% | Complete remaining API endpoints |
| **Long-term** | 70-80% | Comprehensive coverage across all modules |

---

## Testing Best Practices

1. **Use Mocking Appropriately**
   - Mock external dependencies (borg commands, file system)
   - Keep tests fast and isolated
   - Example: `test_api_archives_comprehensive.py`

2. **Test Error Paths**
   - Not just happy paths
   - Test validation failures
   - Test resource not found scenarios

3. **Test Authentication**
   - Test with and without auth tokens
   - Test permission checks

4. **Follow Naming Conventions**
   - `test_<endpoint>_<scenario>_<expected_result>`
   - Example: `test_delete_archive_borg_failure_returns_500`

5. **Use Fixtures**
   - Reuse common setup (test_client, admin_headers, test_db)
   - Keep tests DRY

6. **Document Test Intent**
   - Use clear docstrings
   - Explain what behavior is being tested

---

## Running Tests

```bash
# Run all tests with coverage
python3 -m pytest tests/ --cov=app --cov-report=term

# Run specific module tests
python3 -m pytest tests/unit/test_api_archives_comprehensive.py -v

# Run tests with coverage report
python3 -m pytest tests/ --cov=app --cov-report=html
open htmlcov/index.html
```

---

## Recent Improvements (2025-11-10)

1. **Archives API**: 36.81% → 70.33% (+33.52%)
   - Added comprehensive test file with mocked borg responses
   - Tests cover all endpoints with success/failure scenarios

2. **Backup Service**: 6.27% → 31.25% (+24.98%)
   - Added 21 unit tests for service methods
   - Tests cover hooks, log rotation, stats updates

3. **Overall Coverage**: 27.58% → 30.53% (+2.95%)
   - 241 tests now passing
   - Established baseline documentation

---

**Document Version:** 1.0
**Maintainer:** Development Team
**Review Schedule:** Weekly during testing phase, monthly thereafter
