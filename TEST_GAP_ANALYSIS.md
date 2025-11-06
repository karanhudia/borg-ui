# Test Gap Analysis for Borg UI

## Coverage by Category

### 🔴 CRITICAL GAPS (< 10% coverage)

1. **Backup Service** (3.67% - 473 statements)
   - Missing: Backup job creation and management
   - Missing: Progress tracking and streaming
   - Missing: Backup cancellation
   - Missing: Backup logs handling
   - Missing: Error handling for backup failures

2. **Backup API** (6.32% - 146 statements)
   - Missing: POST /backup/start endpoint
   - Missing: GET /backup/jobs endpoint  
   - Missing: GET /backup/status/{job_id}
   - Missing: POST /backup/cancel/{job_id}
   - Missing: Backup log streaming

3. **Main Application** (6.61% - 105 statements)
   - Missing: FastAPI app initialization
   - Missing: Router inclusion
   - Missing: Middleware setup
   - Missing: Exception handlers
   - Missing: CORS configuration
   - Missing: Static file serving

4. **Restore Service** (8.48% - 125 statements)
   - Missing: Restore job creation
   - Missing: File extraction logic
   - Missing: Restore progress tracking
   - Missing: Restore validation

### 🟡 MODERATE GAPS (10-25% coverage)

5. **Borg Core Operations** (22.76% - 115 statements)
   - Missing: Borg command execution
   - Missing: Archive listing
   - Missing: Repository info fetching
   - Missing: Borg error parsing

6. **Repositories API** (12.13% - 649 statements!)
   - Missing: POST /repositories/ (create)
   - Missing: PUT /repositories/{id} (update)
   - Missing: DELETE /repositories/{id} (delete)
   - Missing: Repository validation
   - Missing: Borg init wrapper
   - Missing: Repository stats
   - Missing: Archive management

7. **Archives API** (15.06% - 132 statements)
   - Missing: GET /archives/list
   - Missing: GET /archives/{id}/info
   - Missing: GET /archives/{id}/contents
   - Missing: DELETE /archives/{id}
   - Missing: Archive download

8. **SSH Keys API** (16.89% - 457 statements)
   - Missing: SSH key generation
   - Missing: SSH key deployment
   - Missing: Connection testing
   - Missing: Key CRUD operations

9. **Schedule API** (18.73% - 251 statements)
   - Missing: Cron job creation
   - Missing: Schedule validation
   - Missing: Job execution triggers
   - Missing: Schedule management (update/delete)

10. **Settings API** (18.05% - 203 statements)
    - Missing: User management endpoints
    - Missing: System settings update
    - Missing: Profile management
    - Missing: Password change

11. **Restore API** (21.21% - 127 statements)
    - Missing: POST /restore/start
    - Missing: Restore preview
    - Missing: Repository/archive listing for restore

### 🟢 GOOD COVERAGE (> 25%)

12. **Security Module** (27.37% - 71 statements)
    - ✅ Password hashing tested
    - ✅ JWT token creation tested
    - ❌ Missing: Token verification
    - ❌ Missing: User authentication flow
    - ❌ Missing: Permission checks

13. **Dashboard API** (36.73% - 172 statements)
    - ✅ Basic endpoints imported
    - ❌ Missing: Dashboard metrics calculation
    - ❌ Missing: System health checks
    - ❌ Missing: Schedule status

14. **Auth API** (40.16% - 100 statements)
    - ✅ Basic structure imported
    - ❌ Missing: Login endpoint logic
    - ❌ Missing: User CRUD operations
    - ❌ Missing: Password reset

15. **Config** (60.19% - 84 statements)
    - ✅ Settings model tested
    - ✅ Environment variables tested
    - ❌ Missing: Secret key generation
    - ❌ Missing: Path validation

16. **Database** (68.00% - 21 statements)
    - ✅ Database setup tested
    - ❌ Missing: Session management
    - ❌ Missing: Connection pooling

17. **Models** (99.26% - 136 statements)
    - ✅ Repository model tested
    - ✅ User model tested
    - ✅ Nearly complete!

## Missing Test Categories

### 1. API Endpoint Tests (CRITICAL)
**Impact: High** | **Effort: Medium**

Currently missing tests for actual API route handlers:
- POST /api/backup/start
- GET /api/backup/jobs
- POST /api/repositories/
- GET /api/repositories/
- POST /api/restore/start
- GET /api/archives/list
- POST /api/schedule/
- All SSH key endpoints
- All settings endpoints

**Why it matters:** These are the primary user-facing features

**How to test:**
```python
# Example: Test backup start endpoint
def test_backup_start_endpoint(test_client, auth_headers):
    response = test_client.post(
        "/api/backup/start",
        json={"repository_id": 1},
        headers=auth_headers
    )
    assert response.status_code == 200
    assert "job_id" in response.json()
```

### 2. Service Layer Tests (CRITICAL)
**Impact: High** | **Effort: High**

Currently missing:
- Backup service workflow tests
- Restore service workflow tests
- Job queue management
- Progress tracking logic

**Why it matters:** Core business logic lives here

**How to test:**
```python
def test_backup_service_create_backup():
    service = BackupService()
    job = service.create_backup(repo_id=1, paths=["/test"])
    assert job.status == "pending"
    assert job.repository_id == 1
```

### 3. Borg Integration Tests (HIGH PRIORITY)
**Impact: High** | **Effort: High**

Currently missing:
- Actual borg command execution tests
- Borg output parsing tests
- Error handling for borg failures
- Archive creation/deletion

**Why it matters:** This is what makes the app work!

**How to test:**
```python
@pytest.mark.requires_borg
def test_borg_create_archive():
    borg = BorgWrapper()
    result = borg.create_archive(
        repo_path="/tmp/test-repo",
        archive_name="test-archive",
        paths=["/tmp/test-data"]
    )
    assert result.returncode == 0
```

### 4. Authentication Flow Tests (MEDIUM PRIORITY)
**Impact: Medium** | **Effort: Low**

Currently missing:
- Login flow end-to-end
- Token refresh
- Permission checks
- Multi-user scenarios

**How to test:**
```python
def test_login_flow(test_client):
    response = test_client.post(
        "/api/auth/login",
        data={"username": "admin", "password": "admin123"}
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    
    # Use token
    response = test_client.get(
        "/api/repositories/",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
```

### 5. Database Operations Tests (MEDIUM PRIORITY)
**Impact: Medium** | **Effort: Medium**

Currently missing:
- Repository CRUD database operations
- User CRUD database operations
- Schedule storage/retrieval
- Transaction handling
- Relationship queries

**How to test:**
```python
def test_create_repository_in_db(db_session):
    repo = Repository(
        name="Test Repo",
        path="/tmp/repo",
        encryption="repokey"
    )
    db_session.add(repo)
    db_session.commit()
    
    assert repo.id is not None
    retrieved = db_session.query(Repository).filter_by(id=repo.id).first()
    assert retrieved.name == "Test Repo"
```

### 6. Error Handling Tests (LOW PRIORITY)
**Impact: Low** | **Effort: Low**

Currently missing:
- Invalid input handling
- Borg command failures
- Database connection errors
- File system errors
- Network errors (SSH)

### 7. Frontend Tests (NOT COVERED)
**Impact: High** | **Effort: High**

Currently: 0% coverage
- No React component tests
- No UI interaction tests
- No end-to-end tests

**Tools needed:**
- Jest for unit tests
- React Testing Library
- Cypress/Playwright for E2E

### 8. Schedule/Cron Tests (LOW PRIORITY)
**Impact: Medium** | **Effort: Medium**

Currently missing:
- Cron expression validation
- Schedule execution logic
- Job triggering
- Retry logic

## Recommended Priority Order

### Phase 1: Critical (Get to 40% coverage)
1. **API Endpoint Tests** - Test all major routes
2. **Service Layer Tests** - Test backup/restore logic
3. **Database Operations** - Test CRUD operations

### Phase 2: Important (Get to 60% coverage)
4. **Borg Integration** - Test actual borg commands
5. **Authentication** - Test auth flows
6. **Error Handling** - Test failure scenarios

### Phase 3: Complete (Get to 80% coverage)
7. **Schedule/Cron** - Test scheduling logic
8. **SSH Operations** - Test key management
9. **Edge Cases** - Test boundary conditions

### Phase 4: Excellence (Get to 90%+)
10. **Frontend Tests** - Add React component tests
11. **E2E Tests** - Full workflow tests
12. **Performance Tests** - Load and stress tests

## Quick Wins for Next Session

Add these simple tests to boost coverage quickly:

```python
# test_api_routes.py
def test_repositories_list_endpoint(test_client, auth_headers):
    response = test_client.get("/api/repositories/", headers=auth_headers)
    assert response.status_code == 200

def test_dashboard_status(test_client, auth_headers):
    response = test_client.get("/api/dashboard/status", headers=auth_headers)
    assert response.status_code == 200

def test_archives_list(test_client, auth_headers):
    response = test_client.get("/api/archives/list", headers=auth_headers)
    assert response.status_code in [200, 404]  # 404 if no repos
```

This would increase coverage from 19% to ~35% with minimal effort!
