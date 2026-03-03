# Codebase Concerns

**Analysis Date:** 2026-03-03

## Tech Debt

**Deprecated Export Method:**
- Issue: `export_to_yaml()` in `BorgmaticExportService` is marked DEPRECATED and performs incorrect multi-repo merging. The method merges multiple repository configs into a single borgmatic config, which is incorrect - borgmatic expects one config per repository/file.
- Files: `app/services/borgmatic_service.py` (lines 120-154)
- Impact: Multi-repository exports may produce invalid borgmatic configurations. Users relying on this method will get a merged config that doesn't properly separate repository settings.
- Fix approach: Remove `export_to_yaml()` entirely. Force users to use `export_all_repositories()` which returns per-repository configs that can be written to separate files. Update documentation to clarify the new pattern.

**Incomplete Dashboard Implementation:**
- Issue: Dashboard endpoints have TODOs and return empty lists for scheduled jobs and alerts. `get_scheduled_jobs()` returns `[]` with comment "TODO: Implement when ScheduledJob model is added back". `get_alerts()` returns `[]` with comment "TODO: Implement when SystemLog model is added back".
- Files: `app/api/dashboard.py` (lines 95-131)
- Impact: Dashboard status endpoint (`/dashboard/status`) will show no scheduled jobs or alerts even if they exist. This creates misleading dashboard state.
- Fix approach: Implement `get_scheduled_jobs()` by querying `ScheduledJob` table with enabled filters. Implement `get_alerts()` by querying backup/check/compact jobs for recent failures.

**Unimplemented Backup Job Monitoring:**
- Issue: `monitor_backup_jobs()` in `app/api/events.py` is a stub that only sleeps. Comment says "TODO: Implement backup job monitoring" - no actual monitoring logic exists.
- Files: `app/api/events.py` (lines 176-187)
- Impact: Real-time backup progress updates via SSE will never be sent. Users won't see live job status in the UI.
- Fix approach: Implement actual job monitoring by querying running BackupJob records and detecting status changes, then broadcasting via `event_manager.broadcast_event()`.

**Unimplemented Settings Cleanup Logic:**
- Issue: `app/api/settings.py` line 907 has TODO comment "# TODO: Implement actual cleanup logic" in settings update endpoint. The cleanup operation acceptance is implemented but the actual cleanup is missing.
- Files: `app/api/settings.py` (line 907)
- Impact: Users can trigger cleanup operations but they won't actually execute. This could create false sense of successful cleanup while data remains.
- Fix approach: Implement the cleanup logic that was scaffolded - likely should call log_manager or cache_service cleanup methods.

**Deprecated Consistency Section in Borgmatic Export:**
- Issue: `_build_consistency_section()` in `BorgmaticExportService` is marked deprecated and returns empty dict. Comment explains that cron expressions don't map to borgmatic's frequency format.
- Files: `app/services/borgmatic_service.py` (lines 220-227)
- Impact: Consistency/check schedules are not exported when converting to borgmatic format. Users lose check scheduling configuration in exports.
- Fix approach: Either document that check schedules require manual configuration in borgmatic, or implement a proper mapping from cron expressions to borgmatic check frequency.

**Loose Exception Handling:**
- Issue: 504 occurrences of bare `except:` statements across 87 files in the app. This prevents proper error classification and logging.
- Files: App-wide - major patterns in `app/services/`, `app/api/`, `app/database/migrations/`
- Impact: Silently catches all exceptions including KeyboardInterrupt, SystemExit, and programming errors. Makes debugging harder and hides real issues.
- Fix approach: Replace all `except:` with specific exception types. Start with common ones: `except (ValueError, KeyError, TypeError, AttributeError)` or more specific application exceptions.

## Known Bugs

**SSH Host Key Verification Disabled:**
- Symptoms: SSH connections work without verifying host keys. This allows man-in-the-middle attacks on SSH repository connections.
- Files: `app/core/borg.py` (lines 59-65)
- Trigger: Any SSH repository operation uses `StrictHostKeyChecking=no` and `UserKnownHostsFile=/dev/null`
- Workaround: None. This is a design choice, not a bug per se, but a security trade-off.

**Bare Except in Migrations:**
- Symptoms: Database migrations silently catch all errors, potentially leaving database in inconsistent state.
- Files: `app/database/migrations/029_add_continue_on_error.py` (line 29), `app/database/migrations/030_add_repository_path_to_check_compact_jobs.py` (line 46)
- Trigger: Any migration failure or unexpected database state
- Workaround: Check migration logs manually and verify database schema consistency.

**EventSource Authentication Mismatch:**
- Symptoms: SSE event streaming passes auth token via query parameter, which may leak in logs/history. Modern approach should use Authorization header exclusively.
- Files: `app/api/events.py` (lines 118-146)
- Trigger: EventSource requests from browser - browsers can't send Authorization headers to EventSource, so workaround was to accept query param tokens
- Workaround: Use Authorization header. Requires JavaScript streaming library instead of native EventSource.

## Security Considerations

**Proxy Authentication Default to "admin":**
- Risk: In proxy auth mode (`DISABLE_AUTHENTICATION=true`), if no proxy headers are found, the code silently defaults to "admin" user (line 125 in `app/core/security.py`). This could bypass authentication if reverse proxy is misconfigured.
- Files: `app/core/security.py` (lines 122-125)
- Current mitigation: Documentation says "ensure Borg UI is only accessible through your reverse proxy by binding to localhost". But no runtime check enforces this.
- Recommendations: Add explicit configuration to require at least one of the proxy headers. Reject requests without proper proxy authentication headers instead of defaulting to "admin". Consider logging a WARNING when default user is used.

**Repository Passphrase Handling:**
- Risk: Repository passphrases are stored in plaintext in SQLite database. While SQLAlchemy ORM is used, there's no encryption at rest for sensitive fields.
- Files: `app/database/models.py` (Repository.passphrase), `app/services/borgmatic_service.py` (imports passphrases and writes to exported configs)
- Current mitigation: None visible. Passphrases are written to YAML exports and exposed in API responses.
- Recommendations: Implement field-level encryption using `sqlalchemy-encrypted` or similar. Never expose passphrases in API responses. Consider separating passphrase management into a secure key management system.

**Subprocess Command Construction:**
- Risk: While subprocess commands appear to use list format (which is safe), environment variables passed to subprocess could contain malicious values if not sanitized.
- Files: `app/core/borg.py` (lines 39-89, environment setup)
- Current mitigation: Only safe-looking env vars are set (BORG_*, SSH_RSH). User input doesn't flow directly to subprocess calls.
- Recommendations: Audit all subprocess invocations to ensure no user input is interpolated into commands. Consider using a subprocess sandbox/whitelist.

**JWT Secret Key Generation and Storage:**
- Risk: `app/config.py` auto-generates SECRET_KEY if not provided and saves to plaintext file `.secret_key`. If this file is committed or exposed, JWT tokens become forgeable.
- Files: `app/config.py` (lines 144-162)
- Current mitigation: File is created in data_dir which is typically git-ignored, but no guarantee.
- Recommendations: Require SECRET_KEY to be provided via environment variable in production. Add warning if using auto-generated key. Validate secret_key length (already checks minimum 32 chars at line 183).

**MQTT Password Storage:**
- Risk: MQTT broker password is stored in plaintext in database (`SystemSettings.mqtt_password`).
- Files: `app/database/models.py` (MQTT settings), `app/database/migrations/071_add_mqtt_beta_enabled.py`
- Current mitigation: None. Password is stored and retrieved as-is.
- Recommendations: Implement field-level encryption for MQTT credentials. Consider integrating with system keyring or vault.

**Disabled SSH Host Key Verification:**
- Risk: SSH connections bypass host key verification (`StrictHostKeyChecking=no`). This creates vulnerability to MITM attacks on remote repository connections.
- Files: `app/core/borg.py` (lines 59-65)
- Current mitigation: None. This is intentional for containerized/ephemeral environments.
- Recommendations: Make this configurable. For production deployments, require valid host keys. Provide mechanism to pre-populate known_hosts file.

## Performance Bottlenecks

**Dashboard Overview Complexity:**
- Problem: `get_dashboard_overview()` endpoint performs O(n) queries with multiple nested loops. It queries all repositories, schedules, SSH connections, and then iterates multiple times over these collections.
- Files: `app/api/dashboard.py` (lines 237-578)
- Cause: No query optimization, N+1 problem where repo lookups are done in loops (lines 300-306, 373-379, 377, 450-520)
- Improvement path: Use SQLAlchemy joins to fetch related data in single query. Cache repository name mapping. Pre-calculate maintenance alerts at query time using database queries instead of Python loops.

**Repetitive Size Parsing:**
- Problem: `parse_size_to_bytes()` is called repeatedly in dashboard to convert human-readable sizes. No caching of parsed values.
- Files: `app/api/dashboard.py` (lines 261-263, 268, 556-557, etc.)
- Cause: Inefficient string processing repeated for every repository.
- Improvement path: Store parsed byte values in database instead of human-readable strings, or cache the parsed values in the dashboard response builder.

**Repository Name Lookup in Activity Feed:**
- Problem: Activity feed tries multiple repository name lookups using normalized paths. This requires linear searches through all repositories for each activity item.
- Files: `app/api/dashboard.py` (lines 450-520)
- Cause: Repository names stored in BackupJob but not cached. Code tries exact match, then normalized, then by ID, then fallback parsing.
- Improvement path: Store repository_id in all job models (BackupJob, CheckJob, CompactJob) instead of just path. Add foreign key constraint and eager load repo names.

**Syncronous psutil Calls on Dashboard Metrics:**
- Problem: `get_system_metrics()` and `/metrics` endpoint make blocking system calls (`psutil.cpu_percent(interval=1)`, `getloadavg()`). If many requests hit concurrently, this could block the event loop.
- Files: `app/api/dashboard.py` (lines 63-93, 166-202)
- Cause: psutil calls are synchronous and interval-based CPU measurement blocks for 1 second.
- Improvement path: Move psutil calls to background thread pool. Cache metrics for 5-10 seconds. Consider using async-friendly system monitoring library.

## Fragile Areas

**Borgmatic Service Multi-Repo Support Transition:**
- Files: `app/services/borgmatic_service.py` (entire file)
- Why fragile: Code has three different ways to look up scheduled jobs (legacy by path, single-repo by ID, multi-repo via junction table). The export/import logic has to handle both old nested borgmatic format and new flat format. Any change to ScheduledJob structure could break imports.
- Safe modification: Add comprehensive tests for each lookup pattern. Create data migration to normalize all scheduled jobs to same format. Document the three lookup patterns and deprecate old ones with timeline.
- Test coverage: Borgmatic import/export has no visible tests. Need tests for: legacy format import, new format import, multi-repo config handling, all three scheduled job lookup patterns.

**Event Manager and SSE Connection Handling:**
- Files: `app/api/events.py` (EventManager class and event_generator function)
- Why fragile: Lazy-loaded asyncio.Lock in EventManager could race if multiple threads access `lock` property before first event loop is available. Global `event_manager` instance created at module load time but `lock` created lazily.
- Safe modification: Initialize lock in `__init__` but defer to first async operation if outside event loop. Add tests for concurrent connection operations.
- Test coverage: No visible tests for concurrent SSE connections, lock behavior, or event broadcast failure cases.

**Dashboard Repository Health Calculation:**
- Files: `app/api/dashboard.py` (lines 254-331)
- Why fragile: Hard-coded thresholds for health status (3 days = warning, 7 days = critical). These magic numbers are not configurable and assumptions about "healthy" may vary by user's backup strategy.
- Safe modification: Move thresholds to SystemSettings table. Create configuration endpoint to adjust warning/critical days. Update health calculation to use configured values.
- Test coverage: Health status calculation needs tests for edge cases like: null last_backup, recent backup, overdue backup, and various day thresholds.

**Password Validation and Reset Flow:**
- Files: `app/core/security.py`, `app/api/settings.py` (password endpoints)
- Why fragile: Password validation logic appears to be spread across multiple endpoints. No visible password complexity requirements. `must_change_password` flag could get stuck if logout happens during forced change flow.
- Safe modification: Consolidate password validation into single function. Add minimum requirements (length, complexity). Test password change flow with logout edge cases.
- Test coverage: Password endpoints have no visible test coverage.

**SSH Connection Configuration:**
- Files: `app/api/ssh_keys.py` (2046 lines), `app/services/borgmatic_service.py` (SSH parsing and handling)
- Why fragile: SSH URL parsing handles both `ssh://user@host:port/path` and `user@host:path` formats. Import logic tries to auto-detect format. Any unusual SSH URL format could be mishandled.
- Safe modification: Create comprehensive SSH URL parser with test cases for all formats. Document supported formats clearly. Add validation that rejects ambiguous formats.
- Test coverage: SSH parsing and connection logic need tests for various URL formats and edge cases.

## Scaling Limits

**SQLite Database Concurrency:**
- Current capacity: SQLite supports single writer at a time. With multiple backup jobs running concurrently, database write contention will limit scaling.
- Limit: Beyond 5-10 concurrent backup operations, database write timeout errors will increase.
- Scaling path: Migrate to PostgreSQL. This is a breaking change but necessary for production deployments. Would require updating all database initialization, migrations, and connection pooling.

**In-Memory Event Queues:**
- Current capacity: `EventManager.connections` dict stores per-user asyncio.Queue objects. Each queue can hold unlimited messages in memory.
- Limit: With thousands of concurrent SSE connections, memory usage will grow unbounded. Messages aren't persisted, so connection dropout = message loss.
- Scaling path: Use Redis or message broker for event distribution instead of in-memory queues. Implement connection limit and message queue limits.

**File-Based Log Storage:**
- Current capacity: Logs written to disk with optional cleanup based on retention days and size. Path: `data/logs/`.
- Limit: With high-frequency backup operations on many repositories, log files can grow very large. No apparent log rotation or compression.
- Scaling path: Implement log rotation with compression. Consider structured log aggregation (ELK, Loki). Add log cleanup job that's more aggressive.

## Dependencies at Risk

**Deprecated Borg Consistency Checks Format:**
- Risk: Application uses cron-based scheduling but borgmatic uses frequency-based checks format. This mismatch means check schedules can't be exported/imported without manual configuration.
- Impact: Users can't easily round-trip their configurations between Borg UI and borgmatic.
- Migration plan: Either (1) migrate Borg UI to frequency-based checks matching borgmatic, or (2) document that checks must be configured separately in borgmatic config. Create migration guide for users.

**Python 2 vs 3 Implicit in Some Code:**
- Risk: Some imports and patterns suggest potential Python 2 compatibility code that's no longer maintained.
- Impact: Unknown - depends on Python version requirements specified in runtime.
- Migration plan: Audit and enforce Python 3.8+ requirement. Remove any Python 2 compatibility code.

## Missing Critical Features

**Scheduled Job Monitoring:**
- Problem: `monitor_backup_jobs()` stub exists but is unimplemented. Users can't see real-time progress of scheduled jobs.
- Blocks: Real-time backup progress UI, job status notifications, accurate ETA calculations.

**Alert System:**
- Problem: `get_alerts()` in dashboard returns empty list. No alerting system is visible for backup failures, maintenance overdue, disk space warnings.
- Blocks: Proactive issue detection, notification delivery, alert configuration.

**System Logs:**
- Problem: Comment indicates "SystemLog model is added back" but this model is missing. No structured audit trail of system events.
- Blocks: Audit requirements, troubleshooting, compliance logging.

**Backup Job Monitoring UI:**
- Problem: While backup jobs are created and tracked in database, there's no real-time progress monitoring sent to UI. The SSE infrastructure exists but `monitor_backup_jobs()` is empty.
- Blocks: Users can't see backup progress, ETA, or real-time status updates. They must manually refresh repository stats.

## Test Coverage Gaps

**Borgmatic Import/Export:**
- What's not tested: Import of various borgmatic YAML formats (old nested, new flat, missing fields). Export round-trip (export then import should produce equivalent config). Multi-repository export handling. Error cases like invalid YAML, missing required fields.
- Files: `app/services/borgmatic_service.py` (840 lines total)
- Risk: Borgmatic operations could silently corrupt or lose configuration data.
- Priority: High - this is a critical data migration feature.

**Dashboard Complex Queries:**
- What's not tested: Dashboard overview endpoint with various repository states (0 repos, 100+ repos, repos with no backups). Correct health status calculation. Maintenance alert generation. Repository name lookup fallbacks.
- Files: `app/api/dashboard.py` (630 lines)
- Risk: Dashboard could crash or return incorrect data under edge cases.
- Priority: High - dashboard is primary UI surface.

**SSH Configuration and Parsing:**
- What's not tested: SSH URL parsing (all formats). SSH connection configuration. Remote repository path handling. SSH key selection and credential passing.
- Files: `app/api/ssh_keys.py` (2046 lines), `app/services/borgmatic_service.py` (SSH methods)
- Risk: SSH repositories could fail silently or use wrong credentials.
- Priority: High - SSH is common use case.

**Event Manager Concurrency:**
- What's not tested: Concurrent SSE connection management. Event broadcasting under high load. Connection cleanup on disconnect. Lock behavior under concurrent access.
- Files: `app/api/events.py` (EventManager class)
- Risk: Race conditions under concurrent load, memory leaks from uncleaned connections.
- Priority: Medium - affects real-time features.

**Repository Health Status Calculation:**
- What's not tested: Health status for repositories with no backups. Health status with various backup ages. Dedup ratio calculation. Warning threshold edge cases.
- Files: `app/api/dashboard.py` (health calculation section)
- Risk: Incorrect health indicators could mask failing backups.
- Priority: Medium.

**Password Management Flows:**
- What's not tested: Password change flow. Password reset. Password validation. Forced password change on first login. Password complexity requirements (if any).
- Files: `app/core/security.py`, `app/api/settings.py` (password endpoints)
- Risk: Password flows could have security issues or user experience problems.
- Priority: Medium - affects security posture.

**Authentication and Authorization:**
- What's not tested: JWT token generation and validation. Proxy authentication header handling. Default "admin" user fallback behavior. User auto-creation in proxy mode.
- Files: `app/core/security.py` (150+ lines of auth code)
- Risk: Authentication bypasses or privilege escalation.
- Priority: High - affects security.

**Script Execution:**
- What's not tested: Script execution with hooks (pre/post backup). Hook timeout behavior. Hook failure handling. Script library parameter substitution. Error message formatting.
- Files: `app/services/backup_service.py` (uses script execution), `app/services/script_executor.py`, `app/services/script_library_executor.py`
- Risk: Script execution failures could go unnoticed or cause cascading failures.
- Priority: High.

---

*Concerns audit: 2026-03-03*
