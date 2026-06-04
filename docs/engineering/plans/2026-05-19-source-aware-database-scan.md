# Source-Aware Database Scan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Subagent execution is not used here because BOR-40 is running as an unattended single-workspace orchestration session.

**Goal:** Implement `POST /api/source-discovery/databases/scan` so Borg UI can scan user-selected local or SSH targets for supported database engines.

**Architecture:** Keep the existing template catalogue in `app/api/source_discovery.py`, factor database signature matching into reusable helpers, and add a scan response model that shares the existing `DatabaseCandidate` shape. Local scans use `pathlib` and `shutil.which`; remote scans reuse encrypted `SSHKey` material, run one SSH command per request, parse structured probe output, and return fallback templates plus warnings on connection failures.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy models, Python standard library (`asyncio`, `pathlib`, `posixpath`, `shlex`, `subprocess`), pytest, ruff.

---

### Task 1: Move the Engineering Spec

**Files:**
- Move: `docs/source-aware-database-scan-spec.md` to `docs/engineering/specs/2026-05-19-source-aware-database-scan.md`

- [ ] **Step 1: Move the spec into engineering specs**

  Run:

  ```bash
  git mv docs/source-aware-database-scan-spec.md docs/engineering/specs/2026-05-19-source-aware-database-scan.md
  ```

- [ ] **Step 2: Verify the moved path**

  Run:

  ```bash
  test -f docs/engineering/specs/2026-05-19-source-aware-database-scan.md
  test ! -e docs/source-aware-database-scan-spec.md
  ```

### Task 2: Add Failing Scan Endpoint Tests

**Files:**
- Modify: `tests/unit/test_source_discovery.py`
- Modify later: `app/api/source_discovery.py`
- Modify later: `app/config.py`

- [ ] **Step 1: Add scan request validation tests**

  Add tests that call `POST /api/source-discovery/databases/scan` with authenticated admin headers and assert:

  ```python
  assert response.status_code == 400
  assert "paths" in str(response.json()["detail"])
  ```

  for an empty local `paths` list, and:

  ```python
  assert response.status_code == 400
  assert "source_ssh_connection_id" in str(response.json()["detail"])
  ```

  for a remote scan without `source_ssh_connection_id`.

- [ ] **Step 2: Add local scan behavior tests**

  Add tests for:

  ```python
  response = test_client.post(
      "/api/source-discovery/databases/scan",
      json={
          "source_type": "local",
          "source_ssh_connection_id": None,
          "paths": [str(postgresql_data_dir)],
      },
      headers=admin_headers,
  )
  assert response.status_code == 200
  assert response.json()["scan_target"]["label"] == "This Borg UI server"
  assert response.json()["scanned_paths"] == [str(postgresql_data_dir)]
  assert response.json()["detections"][0]["id"] == "postgresql"
  assert response.json()["detections"][0]["detection_source"] == str(postgresql_data_dir)
  ```

  Also cover CLI fallback detection, all-negative scans returning empty detections plus all templates, non-absolute paths returning `PATH_NOT_ABSOLUTE`, and shell metacharacter paths returning 400.

- [ ] **Step 3: Add remote scan behavior tests**

  Insert `SSHKey` and `SSHConnection` rows, monkeypatch the remote command runner, and assert:

  ```python
  assert response.status_code == 200
  assert response.json()["scan_target"]["source_type"] == "remote"
  assert response.json()["scan_target"]["label"] == "backup@example.test"
  assert {item["id"] for item in response.json()["detections"]} == {"postgresql", "redis"}
  ```

  Add a connection-failure test where the runner returns non-zero and the endpoint returns `502` with a populated `warnings` array and fallback `templates`.

- [ ] **Step 4: Run tests and confirm RED**

  Run:

  ```bash
  .venv/bin/python -m pytest tests/unit/test_source_discovery.py -q
  ```

  Expected result before implementation: failures because `POST /api/source-discovery/databases/scan` does not exist.

### Task 3: Implement Scan Models and Local Probes

**Files:**
- Modify: `app/api/source_discovery.py`
- Modify: `app/config.py`

- [ ] **Step 1: Add configuration and response models**

  Add `scan_timeout_seconds: int = 15` to `Settings`. In `source_discovery.py`, add `DatabaseScanRequest`, `DatabaseScanTarget`, `ScanWarning`, and `DatabaseScanResponse` models that match the spec.

- [ ] **Step 2: Factor reusable signature matching**

  Replace the hardcoded `_detect_template()` path table with helpers that evaluate basename and top-level signature files for PostgreSQL, MySQL/MariaDB, MongoDB, and Redis. Keep legacy `GET /databases` behavior by probing the default paths through the same helpers.

- [ ] **Step 3: Add local scan execution**

  Implement local scan helpers that validate paths, probe `Path.exists()`, check signature rules, use `which()` for command fallback, deduplicate engine detections, and return the full templates list with `detected=false`.

- [ ] **Step 4: Run local tests and confirm GREEN**

  Run:

  ```bash
  .venv/bin/python -m pytest tests/unit/test_source_discovery.py -q
  ```

  Expected result after local implementation: local scan tests pass; remote tests may still fail until Task 4.

### Task 4: Implement Remote SSH Scan

**Files:**
- Modify: `app/api/source_discovery.py`

- [ ] **Step 1: Resolve remote connection and key material**

  Query `SSHConnection` by `source_ssh_connection_id`, reject missing records with 400, load the related `SSHKey`, and write the decrypted private key with `write_ssh_key_to_tempfile()`. Always clean up the temporary key file.

- [ ] **Step 2: Run one structured SSH probe command**

  Build one shell script per request that emits tab-separated `PATH`, `FILE`, `DIR`, and `COMMAND` rows. Execute it with `ssh -i <temp_key> -p <port> -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=<timeout> user@host sh -c '<script>'`.

- [ ] **Step 3: Convert remote results into detections or warnings**

  Parse probe output into the same generic detector used by local scans. Return `502` with `SSH_HOST_UNREACHABLE` or `SSH_AUTH_FAILED` warning when the SSH command fails, and `504` with `SCAN_TIMEOUT` warning when the command times out.

- [ ] **Step 4: Run remote tests and confirm GREEN**

  Run:

  ```bash
  .venv/bin/python -m pytest tests/unit/test_source_discovery.py -q
  ```

  Expected result: all source discovery tests pass.

### Task 5: Validate and Publish

**Files:**
- Verify: `app/api/source_discovery.py`
- Verify: `app/config.py`
- Verify: `tests/unit/test_source_discovery.py`
- Verify: `docs/engineering/specs/2026-05-19-source-aware-database-scan.md`
- Verify: `docs/engineering/plans/2026-05-19-source-aware-database-scan.md`

- [ ] **Step 1: Run required backend checks**

  Run:

  ```bash
  .venv/bin/python -m ruff check app tests
  .venv/bin/python -m ruff format --check app tests
  .venv/bin/python -m pytest tests/unit/test_source_discovery.py -q
  ```

- [ ] **Step 2: Run runtime route proof**

  Run a TestClient-backed request against `POST /api/source-discovery/databases/scan` or the targeted pytest suite and record the response evidence in the Linear workpad.

- [ ] **Step 3: Commit, push, and open PR**

  Commit the backend, test, and docs changes. Push the branch, create or update the PR using `.github/PULL_REQUEST_TEMPLATE.md`, attach it to BOR-40, add the `symphony` label, sweep PR feedback, confirm checks are green, and move BOR-40 to `Human Review`.

## Self-Review

- Spec coverage: The plan covers request validation, local path probes, local command probes, remote SSH probing, warnings, fallback templates, timeout setting, legacy GET reuse, tests, and docs relocation.
- Placeholder scan: No `TBD`, `TODO`, or unspecified validation command remains.
- Type consistency: The request and response model names match the source-aware database scan spec and the existing `DatabaseCandidate` catalogue.
