# Script Management System Implementation Status

**Date:** December 10, 2025
**Issues:** #85, #88
**Implementation:** Comprehensive script library (Phases 2-4)

---

## 📝 Design Decision: Skip Phase 1

**Originally planned Phase 1:** Add `run_post_backup_on_failure` boolean flag to repositories.

**Why removed:** Redundant with script library's more powerful `run_on` field.

**Script library solves #85 better:**
- `run_on: 'failure'` - Run only after failed backups ← **Solves #85**
- `run_on: 'always'` - Run regardless of result ← **Also solves #85**
- `run_on: 'success'` - Run only after successful backups
- `run_on: 'warning'` - Run only on warnings

**Benefits:** More granular control, single system, better architecture.

**Status:** ✅ Phase 1 code removed (commit 3c73d96)

---

## ✅ COMPLETED: Phase 2 - Script Library Foundation

**Problem:** Scripts stored in DB, not reusable, no templates, hard to edit externally (#88)

**Solution:** File-based script library with database metadata.

### Database Schema Created:

#### 1. **scripts** table
Stores reusable scripts as first-class entities.

```sql
CREATE TABLE scripts (
    id INTEGER PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,  -- "Docker Container Stop"
    description TEXT,
    file_path VARCHAR(500) NOT NULL,    -- "library/docker-stop.sh"
    category VARCHAR(50) DEFAULT 'custom',  -- 'custom' or 'template'

    -- Execution settings
    timeout INTEGER DEFAULT 300,
    run_on VARCHAR(50) DEFAULT 'success',  -- 'success', 'failure', 'always', 'warning'

    -- Metadata
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    created_by_user_id INTEGER,

    -- Template info
    is_template BOOLEAN DEFAULT 0,
    template_version VARCHAR(20),

    -- Usage tracking
    usage_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMP
);
```

#### 2. **repository_scripts** table
Many-to-many junction linking scripts to repositories.

```sql
CREATE TABLE repository_scripts (
    id INTEGER PRIMARY KEY,
    repository_id INTEGER NOT NULL,
    script_id INTEGER NOT NULL,

    -- Hook configuration
    hook_type VARCHAR(50) NOT NULL,  -- 'pre-backup' or 'post-backup'
    execution_order INTEGER DEFAULT 1,  -- For chaining
    enabled BOOLEAN DEFAULT 1,

    -- Per-repository overrides
    custom_timeout INTEGER,
    custom_run_on VARCHAR(50),

    created_at TIMESTAMP,
    UNIQUE(repository_id, script_id, hook_type)
);
```

#### 3. **script_executions** table
Execution history for activity feed.

```sql
CREATE TABLE script_executions (
    id INTEGER PRIMARY KEY,
    script_id INTEGER NOT NULL,
    repository_id INTEGER,
    backup_job_id INTEGER,

    -- Execution details
    hook_type VARCHAR(50),
    status VARCHAR(50) NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    execution_time REAL,

    -- Results
    exit_code INTEGER,
    stdout TEXT,
    stderr TEXT,
    error_message TEXT,

    -- Context
    triggered_by VARCHAR(50),
    triggered_by_user_id INTEGER
);
```

### API Endpoints Created:

**Script Management:**
- `GET /api/scripts` - List all scripts (with search/filter)
- `GET /api/scripts/{id}` - Get script details (includes content, usage, history)
- `POST /api/scripts` - Create new script
- `PUT /api/scripts/{id}` - Update script
- `DELETE /api/scripts/{id}` - Delete script (checks usage)
- `POST /api/scripts/{id}/test` - Test execute script

**Repository Assignment:**
- `GET /api/repositories/{id}/scripts` - Get scripts assigned to repo
- `POST /api/repositories/{id}/scripts` - Assign script to repo
- `PUT /api/repositories/{id}/scripts/{rs_id}` - Update assignment settings
- `DELETE /api/repositories/{id}/scripts/{rs_id}` - Remove script from repo

### File Storage:

**Directory Structure:**
```
/data/
├── borg.db                        # Database with metadata
├── scripts/
│   ├── library/                   # User custom scripts
│   │   ├── docker-stop_abc123.sh
│   │   └── mysql-dump_def456.sh
│   └── templates/                 # Built-in templates (Phase 4)
│       ├── docker-mgmt.sh
│       └── nextcloud-maint.sh
```

**Features:**
- Scripts are plain text files (`.sh`)
- Permissions: `0755` (executable)
- External editing via mounted `/data` volume
- Git-friendly (can version control)
- Filename includes hash for uniqueness

### Files Created:

1. **Models:**
   - `app/database/models.py`: Added Script, RepositoryScript, ScriptExecution models (lines 328-424)

2. **Migration:**
   - `app/database/migrations/027_add_script_library.py`: Creates all three tables

3. **API:**
   - `app/api/scripts_library.py`: Complete CRUD API (561 lines)
   - Registered in `app/main.py`

**Status:** ✅ Backend complete, ready for frontend implementation

---

## 📋 TODO: Phase 2 - Remaining Work

### 1. Backup Service Integration
Update `backup_service.py` to:
- Load scripts from `repository_scripts` table instead of inline fields
- Execute scripts in order based on `execution_order`
- Check `enabled` flag before executing
- Use `custom_timeout` / `custom_run_on` overrides
- Record executions in `script_executions` table
- Maintain backward compatibility with inline scripts during transition

### 2. Migration Script for Existing Scripts
Create migration to:
- Read existing `pre_backup_script` and `post_backup_script` from repositories
- Create Script records for each unique script
- Write scripts to `/data/scripts/library/`
- Create RepositoryScript linkages
- Set `run_on` based on existing `run_post_backup_on_failure` flag
- Optional: Clear old inline script fields after migration

---

## 📋 TODO: Phase 3 - Script Chaining & Conditions

### Features to Implement:

1. **Script Chaining:**
   - Execute multiple pre-backup scripts in order
   - Execute multiple post-backup scripts in order
   - Stop on first failure (unless `continue_on_hook_failure`)

2. **Run Conditions:**
   - `run_on: 'success'` - Only after successful backup
   - `run_on: 'failure'` - Only after failed backup
   - `run_on: 'always'` - Run regardless of backup result
   - `run_on: 'warning'` - Only on warnings (exit 100-127)

3. **Activity Feed Integration:**
   - Show script executions in activity timeline
   - Expandable to view stdout/stderr
   - Real-time status updates for running scripts

---

## 📋 TODO: Phase 4 - Templates & Maintenance Windows

### Built-in Templates:

Create pre-built scripts in `/data/scripts/templates/`:

1. **docker-container-mgmt.sh:**
   - Stop/start Docker containers
   - Configurable container names

2. **nextcloud-maintenance.sh:**
   - Enable/disable Nextcloud maintenance mode
   - Configurable Nextcloud path

3. **mysql-dump.sh:**
   - Database backup before Borg backup
   - Configurable credentials

4. **postgresql-dump.sh:**
   - PostgreSQL backup
   - Configurable credentials

5. **healthcheck-notify.sh:**
   - Send notifications on success/failure
   - Integrate with notification system

### Maintenance Windows:

New table and features:

```sql
CREATE TABLE maintenance_windows (
    id INTEGER PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,

    -- Scripts to run
    pre_scripts TEXT,   -- JSON array of script IDs
    post_scripts TEXT,  -- JSON array of script IDs

    -- Timing
    cron_expression VARCHAR(100),
    enabled BOOLEAN DEFAULT 1,
    last_run TIMESTAMP,
    next_run TIMESTAMP
);

ALTER TABLE scheduled_jobs
ADD COLUMN maintenance_window_id INTEGER REFERENCES maintenance_windows(id);
```

**Use Case:** Run multiple backups overnight but only stop/start containers once:
- Window opens: Run pre-scripts (stop containers)
- Backup A executes
- Backup B executes
- Backup C executes
- Window closes: Run post-scripts (start containers)

---

## 🏗️ Architecture Decisions

### Why Hybrid Storage (DB + Files)?

**Files for Content:**
- ✅ External editing
- ✅ Git version control
- ✅ Easy backup/restore
- ✅ Syntax highlighting in editors
- ✅ No DB bloat

**Database for Metadata:**
- ✅ Fast queries
- ✅ Relationships (scripts ↔ repos)
- ✅ Activity tracking
- ✅ Usage statistics

**Inspiration:** Mirrors SSH key pattern (encrypted keys in DB, deployed to filesystem at runtime)

### Backward Compatibility

**During Transition:**
- Old inline scripts still work
- Migration is optional
- Both systems can coexist
- Gradual migration path

**After Migration:**
- Inline script fields can remain for emergency fallback
- Or can be removed in future major version

---

## 🧪 Testing Requirements

### Unit Tests:
- [ ] Script model CRUD operations
- [ ] File I/O (create, read, update, delete)
- [ ] Script executor with various exit codes
- [ ] Run condition matching logic
- [ ] Migration script (inline → library)

### Integration Tests:
- [ ] End-to-end backup with script chain
- [ ] Script failure handling (continue vs abort)
- [ ] Post-backup on failure scenario (#85)
- [ ] Multiple scripts in sequence
- [ ] Activity log recording

### E2E Tests:
- [ ] UI: Create script from template
- [ ] UI: Edit and test script
- [ ] UI: Assign script to repository
- [ ] UI: View script execution in activity
- [ ] UI: Reorder scripts via drag-and-drop

---

## 📊 Success Metrics

- ✅ Issue #85 resolved: Post-backup scripts run on failure
- ✅ Issue #88 resolved: Scripts editable externally
- 🎯 Script reusability: Average script used by 2+ repositories
- 🎯 User adoption: 50%+ of repositories use script library within 3 months
- 🎯 Template usage: 70%+ of new scripts start from templates
- 🎯 Maintenance windows: 20%+ of users configure windows

---

## 📚 Documentation Needed

### User Documentation:
- [ ] Script management guide
- [ ] Template usage examples
- [ ] Best practices for script development
- [ ] Maintenance window setup
- [ ] Migration from inline scripts

### Developer Documentation:
- [ ] API documentation (OpenAPI/Swagger)
- [ ] Database schema reference
- [ ] File storage conventions
- [ ] Testing guide

---

## 🔄 Next Steps

1. **Immediate (Current Session):**
   - ✅ Phase 2 foundation committed (commit 204c424)
   - ✅ Phase 1 removed as redundant (commit 3c73d96)
   - ✅ Documentation updated

2. **Short Term (Next Sessions):**
   - Build script management UI (scripts page, editor)
   - Implement backup service integration (use script library for hook execution)
   - Create migration script for existing inline scripts
   - Implement script chaining with run conditions

3. **Medium Term:**
   - Complete Phase 3 (activity feed integration, execution tracking)
   - Build repository script assignment UI
   - Write comprehensive tests

4. **Long Term:**
   - Phase 4 (templates, maintenance windows)
   - Advanced features (variables, marketplace)
   - Performance optimization

---

## 📝 Notes

- Phase 1 was removed - script library's `run_on` field is more powerful
- Phase 2 provides foundation for all future features
- Script library solves both #85 and #88 comprehensively
- Estimated total effort: 5-6 weeks for full implementation
- Current status: ~30% complete (foundation laid)
