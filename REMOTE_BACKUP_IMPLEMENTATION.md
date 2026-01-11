# Remote Backup Orchestration - Implementation Plan

## Overview
Enable Borg Web UI to orchestrate backups from remote hosts by executing `borg create` commands over SSH on source machines, while maintaining centralized control, scheduling, and monitoring.

## Feature Request Context
- GitHub Issue: Request for centralized backup orchestration
- Key requirement: NOT pulling data over SSH, but executing Borg remotely on source hosts
- Reuse existing SSH connection infrastructure
- Example command: `ssh root@machine borg create repo::{hostname}-{now} /etc`

---

## Architecture

### Execution Models

#### Model 1: Local Backup (Current)
```
[Borg UI Container] --borg create--> [Local Repository]
                   \--borg create--> [SSH Repository]
```

#### Model 2: Remote Backup (New)
```
[Borg UI] --ssh--> [Remote Host] --borg create--> [Repository]
                                                    ↓
                                    [Local to UI] or [SSH Accessible]
```

### Repository Access Patterns

When executing remote backups, the source host needs to push to the repository:

**Pattern A: SSH Repository (Simplest)**
```bash
# On remote host, borg pushes to SSH repository
ssh user@source-host \
  borg create ssh://backup@repo-host:/path::{hostname}-{now} /data
```

**Pattern B: Local Repository via SSH (Requires SSH Server)**
```bash
# Borg UI exposes local repos via SSH
# Remote host connects back to Borg UI
ssh user@source-host \
  borg create ssh://borg-ui@borg-ui-host:/data/repos/myrepo::{hostname}-{now} /data
```

**Pattern C: Local Repository via Reverse Tunnel**
```bash
# Create reverse tunnel, then run borg on remote
ssh -R 2222:localhost:22 user@source-host \
  borg create ssh://localhost:2222/data/repos/myrepo::{hostname}-{now} /data
```

### Recommended Initial Implementation
**Start with Pattern A** (SSH repositories only) to minimize complexity. This requires:
- Source host has SSH access to repository host
- Repository is already configured as SSH type in Borg UI

Later phases can add Pattern B/C for local repositories.

---

## Database Schema Changes

### Phase 1: Add Remote Execution Support

#### 1.1 Extend `SSHConnection` Model
```python
class SSHConnection(Base):
    # ... existing fields ...

    # NEW: Mark as backup source
    is_backup_source = Column(Boolean, default=False)

    # NEW: Borg installation info
    borg_binary_path = Column(String, default="/usr/bin/borg")  # Path to borg on remote host
    borg_version = Column(String, nullable=True)  # Detected borg version
    last_borg_check = Column(DateTime, nullable=True)  # Last time borg was verified
```

#### 1.2 Extend `BackupJob` Model
```python
class BackupJob(Base):
    # ... existing fields ...

    # NEW: Execution mode
    execution_mode = Column(String, default="local")  # "local" or "remote_ssh"
    source_ssh_connection_id = Column(Integer, ForeignKey("ssh_connections.id"), nullable=True)

    # NEW: Remote execution tracking
    remote_process_pid = Column(Integer, nullable=True)  # PID on remote host
    remote_hostname = Column(String, nullable=True)  # Remote hostname for reference
```

#### 1.3 Extend `ScheduledJob` Model
```python
class ScheduledJob(Base):
    # ... existing fields ...

    # NEW: Remote execution
    execution_mode = Column(String, default="local")
    source_ssh_connection_id = Column(Integer, ForeignKey("ssh_connections.id"), nullable=True)
```

### Migration Script
```sql
-- Migration 029: Add remote backup support

-- Extend SSH connections
ALTER TABLE ssh_connections ADD COLUMN is_backup_source BOOLEAN DEFAULT FALSE;
ALTER TABLE ssh_connections ADD COLUMN borg_binary_path VARCHAR DEFAULT '/usr/bin/borg';
ALTER TABLE ssh_connections ADD COLUMN borg_version VARCHAR;
ALTER TABLE ssh_connections ADD COLUMN last_borg_check TIMESTAMP;

-- Extend backup jobs
ALTER TABLE backup_jobs ADD COLUMN execution_mode VARCHAR DEFAULT 'local';
ALTER TABLE backup_jobs ADD COLUMN source_ssh_connection_id INTEGER REFERENCES ssh_connections(id);
ALTER TABLE backup_jobs ADD COLUMN remote_process_pid INTEGER;
ALTER TABLE backup_jobs ADD COLUMN remote_hostname VARCHAR;

-- Extend scheduled jobs
ALTER TABLE scheduled_jobs ADD COLUMN execution_mode VARCHAR DEFAULT 'local';
ALTER TABLE scheduled_jobs ADD COLUMN source_ssh_connection_id INTEGER REFERENCES ssh_connections(id);

-- Create index for faster lookups
CREATE INDEX idx_backup_jobs_source_ssh ON backup_jobs(source_ssh_connection_id);
CREATE INDEX idx_scheduled_jobs_source_ssh ON scheduled_jobs(source_ssh_connection_id);
```

---

## Backend Implementation

### 1. Remote Backup Service
**File:** `app/services/remote_backup_service.py`

```python
class RemoteBackupService:
    """Execute Borg backups on remote hosts via SSH"""

    async def execute_remote_backup(
        self,
        job_id: int,
        source_ssh_connection_id: int,
        repository_id: int,
        source_paths: List[str],
        exclude_patterns: List[str] = None
    ):
        """
        Main method to execute backup on remote host

        Process:
        1. Validate SSH connection and repository
        2. Build borg create command
        3. Execute via SSH on remote host
        4. Stream output and parse progress
        5. Update job status
        """
        pass

    async def _build_remote_command(
        self,
        repository: Repository,
        archive_name: str,
        source_paths: List[str],
        exclude_patterns: List[str]
    ) -> str:
        """
        Build the borg create command for remote execution

        Returns command like:
        BORG_PASSPHRASE='secret' borg create \
          --progress --stats --json \
          --compression lz4 \
          ssh://user@repo-host:/path::{hostname}-{now} \
          /data /etc
        """
        pass

    async def _execute_ssh_command(
        self,
        ssh_connection: SSHConnection,
        command: str,
        job_id: int
    ):
        """
        Execute command on remote host via SSH
        Stream stdout/stderr for progress parsing
        """
        pass

    async def verify_remote_borg(
        self,
        ssh_connection_id: int
    ) -> Dict:
        """
        Check if Borg is installed on remote host
        Returns: {installed: bool, version: str, path: str}
        """
        pass

    async def cancel_remote_backup(
        self,
        job_id: int
    ) -> bool:
        """
        Cancel running remote backup by sending SIGTERM over SSH
        """
        pass
```

### 2. Integration with BackupService
**File:** `app/services/backup_service.py` (modify)

```python
class BackupService:
    async def execute_backup(self, job_id: int, repository_id: int, ...):
        # Check execution mode
        job = db.query(BackupJob).filter(BackupJob.id == job_id).first()

        if job.execution_mode == "remote_ssh":
            # Delegate to remote backup service
            return await remote_backup_service.execute_remote_backup(
                job_id=job_id,
                source_ssh_connection_id=job.source_ssh_connection_id,
                repository_id=repository_id,
                source_paths=source_paths,
                exclude_patterns=exclude_patterns
            )
        else:
            # Existing local backup logic
            return await self._execute_local_backup(...)
```

### 3. Repository Access Helper
**File:** `app/services/repository_access.py` (new)

```python
class RepositoryAccessHelper:
    """Helper to determine how remote hosts should access repositories"""

    @staticmethod
    def get_repository_url_for_remote(
        repository: Repository,
        from_ssh_connection: SSHConnection = None
    ) -> str:
        """
        Get the repository URL that a remote host should use

        Examples:
        - SSH repo: ssh://backup@repo-host:22/path
        - Local repo: raises NotImplementedError (Phase 2)
        """
        if repository.repository_type == "ssh":
            return f"ssh://{repository.username}@{repository.host}:{repository.port}{repository.path}"
        elif repository.repository_type == "local":
            raise NotImplementedError(
                "Local repositories are not yet supported for remote backups. "
                "Please use an SSH repository or implement SSH server in Borg UI."
            )
        else:
            raise ValueError(f"Unsupported repository type: {repository.repository_type}")
```

---

## API Endpoints

### 1. SSH Connection Management
**File:** `app/api/ssh_keys.py` (extend)

```python
# PATCH /api/ssh-keys/connections/{connection_id}/backup-source
@router.patch("/connections/{connection_id}/backup-source")
async def toggle_backup_source(
    connection_id: int,
    enable: bool,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Enable/disable SSH connection as backup source"""
    # Verify borg is installed on remote host
    if enable:
        result = await remote_backup_service.verify_remote_borg(connection_id)
        if not result["installed"]:
            raise HTTPException(
                status_code=400,
                detail=f"Borg is not installed on remote host. Please install it first."
            )

    # Update connection
    conn = db.query(SSHConnection).filter(SSHConnection.id == connection_id).first()
    conn.is_backup_source = enable
    if enable:
        conn.borg_version = result["version"]
        conn.last_borg_check = datetime.utcnow()
    db.commit()

    return {"success": True, "borg_version": result.get("version")}

# GET /api/ssh-keys/connections/backup-sources
@router.get("/connections/backup-sources")
async def list_backup_sources(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all SSH connections enabled as backup sources"""
    sources = db.query(SSHConnection).filter(
        SSHConnection.is_backup_source == True,
        SSHConnection.status == "connected"
    ).all()

    return {"sources": [
        {
            "id": s.id,
            "name": f"{s.username}@{s.host}:{s.port}",
            "host": s.host,
            "borg_version": s.borg_version
        }
        for s in sources
    ]}
```

### 2. Backup Job Creation
**File:** `app/api/backup.py` (extend)

```python
class BackupJobCreate(BaseModel):
    repository_id: int
    execution_mode: str = "local"  # "local" or "remote_ssh"
    source_ssh_connection_id: Optional[int] = None  # Required if execution_mode="remote_ssh"
    # ... existing fields ...

@router.post("/manual")
async def create_manual_backup(
    backup_request: BackupJobCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Validate execution mode
    if backup_request.execution_mode == "remote_ssh":
        if not backup_request.source_ssh_connection_id:
            raise HTTPException(400, "source_ssh_connection_id required for remote backups")

        # Verify SSH connection is enabled as backup source
        ssh_conn = db.query(SSHConnection).filter(
            SSHConnection.id == backup_request.source_ssh_connection_id,
            SSHConnection.is_backup_source == True
        ).first()
        if not ssh_conn:
            raise HTTPException(400, "Invalid backup source connection")

        # Verify repository is SSH type (for Phase 1)
        repo = db.query(Repository).filter(Repository.id == backup_request.repository_id).first()
        if repo.repository_type != "ssh":
            raise HTTPException(
                400,
                "Remote backups currently only support SSH repositories. "
                "Local repositories will be supported in a future update."
            )

    # Create job with execution mode
    job = BackupJob(
        repository=repo.path,
        execution_mode=backup_request.execution_mode,
        source_ssh_connection_id=backup_request.source_ssh_connection_id,
        status="pending"
    )
    db.add(job)
    db.commit()

    # Execute backup (delegates to appropriate service)
    asyncio.create_task(backup_service.execute_backup(job.id, ...))

    return {"job_id": job.id}
```

---

## Frontend Implementation

### 1. SSH Connection Toggle
**File:** `frontend/src/components/SSHConnectionCard.tsx` (extend)

Add toggle switch to each SSH connection:
```tsx
<FormControlLabel
  control={
    <Switch
      checked={connection.is_backup_source}
      onChange={handleToggleBackupSource}
    />
  }
  label="Use as Backup Source"
/>
{connection.is_backup_source && (
  <Chip
    label={`Borg ${connection.borg_version}`}
    size="small"
    color="success"
  />
)}
```

### 2. Backup Creation Dialog
**File:** `frontend/src/components/CreateBackupDialog.tsx` (extend)

Add execution mode selector:
```tsx
<FormControl fullWidth>
  <InputLabel>Execution Mode</InputLabel>
  <Select
    value={executionMode}
    onChange={(e) => setExecutionMode(e.target.value)}
  >
    <MenuItem value="local">Local (Run on Borg UI)</MenuItem>
    <MenuItem value="remote_ssh">Remote SSH (Run on Source Host)</MenuItem>
  </Select>
</FormControl>

{executionMode === "remote_ssh" && (
  <>
    <FormControl fullWidth>
      <InputLabel>Source Host</InputLabel>
      <Select
        value={sourceConnectionId}
        onChange={(e) => setSourceConnectionId(e.target.value)}
      >
        {backupSources.map(source => (
          <MenuItem key={source.id} value={source.id}>
            {source.name} (Borg {source.borg_version})
          </MenuItem>
        ))}
      </Select>
    </FormControl>

    <Alert severity="info">
      Backup will run on the selected remote host and push data to the repository.
      Ensure the source host has network access to the repository.
    </Alert>
  </>
)}
```

### 3. Scheduled Job Form
**File:** `frontend/src/components/ScheduledJobForm.tsx` (extend)

Same execution mode selector as above.

### 4. Job Status Display
**File:** `frontend/src/components/BackupJobCard.tsx` (extend)

Show execution mode and source host:
```tsx
{job.execution_mode === "remote_ssh" && (
  <Chip
    icon={<CloudIcon />}
    label={`Remote: ${job.remote_hostname}`}
    size="small"
    color="primary"
  />
)}
```

---

## Security Considerations

### 1. Passphrase Exposure
**Risk:** Repository passphrase exposed in SSH command process list

**Mitigation:**
- Use `BORG_PASSPHRASE` environment variable instead of stdin
- Environment variables are less visible than command arguments
- SSH command: `BORG_PASSPHRASE='secret' borg create ...`
- Still appears briefly in `/proc/[pid]/environ` but better than argv

**Future Enhancement:**
- Store passphrase in temporary file on remote host
- Use `BORG_PASSPHRASE_FILE` instead
- Remove file after backup completes

### 2. SSH Key Access
**Current:** SSH keys stored encrypted in database

**Action:** Ensure remote execution uses same key protection as current repository access

### 3. Command Injection
**Risk:** User-provided paths could inject shell commands

**Mitigation:**
- Use `shlex.quote()` for all path arguments
- Validate exclude patterns for shell metacharacters
- Use subprocess with list arguments, not shell=True

### 4. Network Access Control
**Risk:** Remote host could access unintended repositories

**Mitigation:**
- Document that source hosts need network access to repositories
- Consider firewall rules in deployment docs
- Phase 2: Add repository access whitelisting per SSH connection

---

## Testing Strategy

### Unit Tests
```python
# tests/unit/test_remote_backup_service.py
def test_build_remote_command():
    """Test SSH command building with proper quoting"""

def test_verify_remote_borg():
    """Test borg version detection on remote host"""

def test_cancel_remote_backup():
    """Test cancellation via SSH"""
```

### Integration Tests
```python
# tests/integration/test_remote_backup_flow.py
@pytest.mark.integration
def test_remote_backup_ssh_repository():
    """Test full flow: create job, execute remotely, verify completion"""

@pytest.mark.integration
def test_remote_backup_progress_tracking():
    """Test progress parsing from remote borg output"""
```

### Manual Testing Checklist
- [ ] Create SSH connection and enable as backup source
- [ ] Verify borg version detection
- [ ] Create manual remote backup job
- [ ] Monitor progress in real-time
- [ ] Cancel running remote backup
- [ ] Create scheduled remote backup
- [ ] Verify scheduler executes remote backups
- [ ] Test with large dataset (1GB+)
- [ ] Test failure scenarios (borg not installed, network issues)

---

## Phase Implementation Plan

### Phase 1: Core Remote Execution (MVP)
**Goal:** Enable remote backups to SSH repositories

**Scope:**
- Database migrations
- `RemoteBackupService` implementation
- SSH command execution with progress tracking
- API endpoints for backup source management
- Frontend: execution mode selector
- **Limitation:** SSH repositories only

**Deliverables:**
1. Users can mark SSH connections as backup sources
2. Users can create manual remote backup jobs
3. Progress tracking works for remote jobs
4. Cancellation works for remote jobs

**Timeline:** ~2-3 weeks

### Phase 2: Scheduled Remote Backups
**Goal:** Support scheduled jobs with remote execution

**Scope:**
- Extend scheduler to handle remote jobs
- Frontend: scheduled job form updates
- Prune/compact support for remote backups

**Timeline:** ~1 week

### Phase 3: Local Repository Support
**Goal:** Enable remote backups to local repositories

**Options:**
1. Add SSH server to Borg UI container
2. Implement SSH reverse tunnels
3. Use ProxyJump pattern

**Decision needed:** Which option to implement?

**Timeline:** ~2-3 weeks

### Phase 4: Advanced Features
**Scope:**
- Per-connection repository access whitelisting
- Remote host monitoring (disk space, borg version)
- Bulk remote backup scheduling
- Health checks for backup sources

**Timeline:** ~2 weeks

---

## Configuration Examples

### Example 1: Remote Host to SSH Repository
```yaml
# Borg UI Configuration
SSH Connections:
  - name: "webserver-prod"
    host: "web.example.com"
    username: "root"
    is_backup_source: true
    borg_binary_path: "/usr/bin/borg"

Repositories:
  - name: "backup-storage"
    type: "ssh"
    host: "backup.example.com"
    path: "/srv/borg-repos/webserver"

Backup Jobs:
  - name: "webserver-daily"
    execution_mode: "remote_ssh"
    source_ssh_connection: "webserver-prod"
    repository: "backup-storage"
    source_paths:
      - "/etc"
      - "/var/www"
      - "/home"
    schedule: "0 2 * * *"
```

**Execution Flow:**
1. Borg UI scheduler triggers at 2 AM
2. Connects to web.example.com via SSH
3. Executes: `borg create ssh://backup.example.com:/srv/borg-repos/webserver::{hostname}-{now} /etc /var/www /home`
4. Borg on webserver pushes data to backup.example.com
5. Progress streamed back to Borg UI
6. Job status updated in database

### Example 2: Multiple Hosts to Same Repository
```yaml
Backup Sources:
  - webserver-1 (Ubuntu 22.04, Borg 1.2.4)
  - webserver-2 (Ubuntu 22.04, Borg 1.2.4)
  - database-1 (Debian 12, Borg 1.2.6)

Repository:
  - backup-storage (SSH, backup.example.com)

Scheduled Job:
  - name: "infrastructure-backup"
    schedule: "0 3 * * *"
    repositories: [backup-storage]
    execution_mode: "remote_ssh"

    # Sequential execution
    - webserver-1: /etc /var/www
    - webserver-2: /etc /var/www
    - database-1: /etc /var/lib/postgresql
```

---

## Documentation Updates

### User Documentation
**File:** `docs/remote-backups.md` (new)

Topics:
- What are remote backups?
- When to use remote vs local execution
- Prerequisites (Borg installation on source hosts)
- Step-by-step setup guide
- Troubleshooting common issues
- Security best practices

### API Documentation
**File:** `docs/api.md` (extend)

New endpoints:
- `PATCH /api/ssh-keys/connections/{id}/backup-source`
- `GET /api/ssh-keys/connections/backup-sources`
- `POST /api/backup/manual` (extended)

### Migration Guide
**File:** `docs/migrations/v1.46.0.md` (new)

Topics:
- What's new in remote backups
- Database migration details
- Breaking changes (if any)
- Migration steps for existing deployments

---

## Open Questions

1. **Repository Access for Local Repos**
   - Should we add SSH server to container?
   - Or focus on SSH repositories only initially?
   - **Recommendation:** Start with SSH repos only (simpler, more secure)

2. **Multiple Source Hosts, Single Job**
   - Should one scheduled job support multiple source hosts?
   - Or require separate jobs per host?
   - **Recommendation:** Separate jobs initially, multi-host in Phase 4

3. **Source Path Validation**
   - Should we validate paths exist on remote host before backup?
   - Or let Borg handle missing paths?
   - **Recommendation:** Let Borg handle it (pre-validation adds complexity)

4. **Borg Version Compatibility**
   - Minimum supported Borg version on remote hosts?
   - **Recommendation:** 1.2.0+ (same as Borg UI)

5. **Pre/Post Scripts on Remote Hosts**
   - Should repository pre/post scripts run on remote host or Borg UI?
   - **Recommendation:** Skip for Phase 1, add in Phase 4 with new "remote scripts" feature

---

## Success Metrics

### Performance
- Remote backup execution overhead: <5 seconds vs local
- Progress update latency: <2 seconds
- Cancellation response time: <3 seconds

### Reliability
- Remote backup success rate: >95%
- SSH connection retry success: >90%
- Zero data corruption incidents

### Usability
- Time to setup first remote backup: <10 minutes
- User comprehension of execution modes: >80% in testing

---

## Risks and Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Passphrase exposure in SSH | High | Medium | Use env vars, document security implications |
| Network failures during backup | Medium | High | Implement retry logic, clear error messages |
| Borg version incompatibility | High | Low | Verify version on source host, show warnings |
| SSH connection instability | Medium | Medium | Use SSH keepalives, connection health checks |
| Local repo access complexity | Low | High | Postpone to Phase 3, document limitations |
| User confusion about execution modes | Medium | Medium | Clear UI labels, tooltips, documentation |

---

## Conclusion

This implementation plan provides a structured approach to adding remote backup orchestration to Borg Web UI. By starting with SSH repositories (Phase 1) and incrementally adding features, we can deliver value quickly while maintaining code quality and security.

The feature aligns well with the existing architecture and reuses SSH infrastructure, making it a natural extension rather than a bolt-on addition.

**Next Steps:**
1. Review and approve this plan
2. Create GitHub project board with phases as milestones
3. Begin Phase 1 implementation
4. Set up integration testing environment with remote hosts
5. Update user documentation

**Estimated Total Effort:** 8-10 weeks across all phases
**Estimated Phase 1 Delivery:** 2-3 weeks
