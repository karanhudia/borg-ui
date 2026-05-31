# Managed Agent Archive Download Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route archive file downloads for managed-agent repositories through the owning agent instead of extracting from the controller filesystem.

**Architecture:** Keep server-owned repositories on the existing `borg.extract_archive` path. Add one repository operation capability for agent-owned archive file extraction that returns a base64 payload for the requested single file, then have the server write that payload into the existing temporary extraction directory so `extract_file_download` keeps the path containment and cleanup checks.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, the Borg UI Python agent runtime, Borg 1/Borg 2 command wrappers.

---

## Task 1: Server Download Routing

**Files:**
- Modify: `app/api/archives.py`
- Modify: `app/services/repository_executor.py`
- Test: `tests/unit/test_api_archives.py`

- [ ] **Step 1: Write failing server test**

Add a test next to the existing archive download endpoint tests that creates a repository with `executor_type="agent"` and an agent capability for `repository.extract_archive_file`. Patch `queue_agent_repository_operation_job`, `dispatch_agent_job_best_effort`, and `wait_for_agent_repository_operation_job` so the result contains a base64 file body. Assert the response body matches the decoded bytes, no local `borg.extract_archive` call is made, and the queued operation includes:

```python
{
    "archive": "test-archive",
    "file_path": "/extracted.txt",
}
```

Run:

```bash
pytest tests/unit/test_api_archives.py::TestDownloadFileEndpoint::test_download_file_for_agent_repository_queues_extract_job -q
```

Expected: fails because the endpoint calls local `borg.extract_archive` for agent repositories.

- [ ] **Step 2: Implement minimal server routing**

Add `repository.extract_archive_file` to `REPOSITORY_OPERATION_CAPABILITIES`. In `app/api/archives.py`, branch inside `download_file_from_archive` when `is_agent_executor(repo)` is true:

1. Queue `repository.extract_archive_file` with `archive` and `file_path`.
2. Dispatch the job best-effort.
3. Wait for the result.
4. Decode `content_base64`.
5. Write bytes to the temp extraction path under `file_path.lstrip("/")`.
6. Return `{"success": True, "stderr": ""}` to `extract_file_download`.

Keep the existing local/SSH server executor branch unchanged.

Run:

```bash
pytest tests/unit/test_api_archives.py::TestDownloadFileEndpoint::test_download_file_for_agent_repository_queues_extract_job -q
```

Expected: passes.

## Task 2: Agent Extract Capability

**Files:**
- Modify: `agent/borg_ui_agent/runtime.py`
- Modify: `agent/borg_ui_agent/repository_ops.py`
- Modify: `agent/README.md`
- Test: `tests/unit/test_agent_runtime.py`

- [ ] **Step 1: Write failing agent command test**

Add tests that build `RepositoryOperationPayload` for `repository.extract_archive_file` and assert commands:

```python
["borg", "extract", "--stdout", "/agent/repo::archive-1", "docs/report.txt"]
["borg2", "-r", "/agent/v2-repo", "extract", "--stdout", "archive-2", "docs/report.txt"]
```

Also assert `repository.extract_archive_file` appears in `get_capabilities()`.

Run:

```bash
pytest tests/unit/test_agent_runtime.py::test_repository_extract_file_payload_builds_agent_extract_stdout_command -q
```

Expected: fails because the capability is unsupported.

- [ ] **Step 2: Implement minimal agent capability**

Add `repository.extract_archive_file` to runtime capabilities and repository job handlers. In `RepositoryOperationPayload.build_command`, require `operation.archive` and `operation.file_path`, strip leading slashes from the file path, and build a Borg `extract --stdout` command for Borg 1 and Borg 2. Execute this job kind with binary-safe capture and complete the job with:

```python
{
    "return_code": 0,
    "command": cmd,
    "stdout": "",
    "stderr": stderr_text,
    "success": True,
    "content_base64": base64.b64encode(stdout_bytes).decode("ascii"),
}
```

For non-zero exit, complete the job with `success: False` and the captured stderr so the server returns `backend.errors.archives.failedExtractFile`.

Run:

```bash
pytest tests/unit/test_agent_runtime.py::test_repository_extract_file_payload_builds_agent_extract_stdout_command -q
```

Expected: passes.

## Task 3: Validation

**Files:**
- No additional source files expected.

- [ ] **Step 1: Run targeted tests**

Run:

```bash
pytest tests/unit/test_api_archives.py::TestDownloadFileEndpoint::test_download_file_for_agent_repository_queues_extract_job tests/unit/test_agent_runtime.py::test_repository_extract_file_payload_builds_agent_extract_stdout_command -q
```

Expected: passes.

- [ ] **Step 2: Run relevant unit modules**

Run:

```bash
pytest tests/unit/test_api_archives.py tests/unit/test_agent_runtime.py -q
```

Expected: passes.

- [ ] **Step 3: Run required backend checks**

Run:

```bash
ruff check app tests agent
ruff format --check app tests agent
pytest tests/unit/test_api_archives.py tests/unit/test_agent_runtime.py -q
```

Expected: all pass.
