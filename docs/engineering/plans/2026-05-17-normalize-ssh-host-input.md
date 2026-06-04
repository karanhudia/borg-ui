# Normalize SSH Host Input Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Normalize safe SSH host inputs and reject ambiguous or malformed host strings before they reach OpenSSH or persistent `ssh_connections.host` storage.

**Architecture:** Add one backend host normalization module and use it from every Pydantic model that accepts SSH connection host input. Add one frontend helper with matching pre-submit validation, then wire the deploy, edit, and manual-test dialogs to show MUI inline validation errors and submit normalized host values.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy, pytest, React, Vite, Vitest, MUI, Storybook.

---

### Task 1: Backend Tests

**Files:**
- Modify: `tests/unit/test_api_ssh_keys.py`

- [ ] **Step 1: Write failing model validation tests**

Add focused tests that instantiate `SSHConnectionCreate`, `SSHConnectionUpdate`, `SSHConnectionTest`, and `SSHQuickSetup` with valid and invalid host inputs:

```python
from pydantic import ValidationError

@pytest.mark.parametrize(
    ("raw_host", "expected_host"),
    [
        ("  u123456.your-storagebox.de  ", "u123456.your-storagebox.de"),
        ("\tbackup.example.com\n", "backup.example.com"),
        ("192.0.2.10", "192.0.2.10"),
        ("2001:db8::1", "2001:db8::1"),
    ],
)
def test_ssh_connection_models_normalize_safe_hosts(raw_host, expected_host):
    assert SSHConnectionCreate(host=raw_host, username="borg", password="secret").host == expected_host
    assert SSHConnectionUpdate(host=raw_host).host == expected_host
    assert SSHConnectionTest(host=raw_host, username="borg").host == expected_host
    assert SSHQuickSetup(name="key", host=raw_host, username="borg", password="secret").host == expected_host
```

```python
@pytest.mark.parametrize(
    "raw_host",
    [
        "http://host",
        "ssh://user@host",
        "host:23",
        "example.com/path",
        "user@example.com",
        "[example.com]",
        "[2001:db8::1]",
        "[host](https://host)",
        "host name",
        "host\u200bname",
        "",
        "   ",
    ],
)
def test_ssh_connection_models_reject_malformed_hosts(raw_host):
    with pytest.raises(ValidationError):
        SSHConnectionCreate(host=raw_host, username="borg", password="secret")
```

- [ ] **Step 2: Run the backend test to verify RED**

Run:

```bash
.venv/bin/pytest tests/unit/test_api_ssh_keys.py -k "ssh_connection_models" -q
```

Expected: FAIL because the current models accept malformed hosts and do not trim safe values.

### Task 2: Backend Implementation

**Files:**
- Create: `app/utils/ssh_host_validation.py`
- Modify: `app/api/ssh_keys.py`
- Test: `tests/unit/test_api_ssh_keys.py`

- [ ] **Step 1: Implement host normalization**

Create `app/utils/ssh_host_validation.py` with `normalize_ssh_host(host: str) -> str`. It must:

```python
def normalize_ssh_host(host: str) -> str:
    candidate = host.strip()
    if not candidate:
        raise ValueError("Host is required.")
    if _has_forbidden_host_characters(candidate):
        raise ValueError("Enter a bare DNS name or IP address without scheme, path, user, spaces, brackets, or port.")
    parsed_ip = _parse_ip_literal(candidate)
    if parsed_ip:
        return parsed_ip
    if not _is_valid_dns_name(candidate):
        raise ValueError("Enter a bare DNS name or IP address without scheme, path, user, spaces, brackets, or port.")
    return candidate
```

- [ ] **Step 2: Apply the validator to request models**

Import the helper and add Pydantic field validators:

```python
from pydantic import BaseModel, Field, field_validator
from app.utils.ssh_host_validation import normalize_ssh_host

class SSHConnectionCreate(BaseModel):
    host: str

    @field_validator("host")
    @classmethod
    def normalize_host(cls, value: str) -> str:
        return normalize_ssh_host(value)
```

Repeat the same validator on `SSHConnectionTest`, `SSHConnectionUpdate`, and `SSHQuickSetup`. `SSHConnectionUpdate.host` and `SSHQuickSetup.host` must preserve `None` values.

- [ ] **Step 3: Run backend targeted tests to verify GREEN**

Run:

```bash
.venv/bin/pytest tests/unit/test_api_ssh_keys.py -k "ssh_connection_models" -q
```

Expected: PASS.

### Task 3: Saved Connection Audit/Cleanup

**Files:**
- Modify: `app/api/ssh_keys.py`
- Test: `tests/unit/test_api_ssh_keys.py`

- [ ] **Step 1: Add failing route tests**

Add tests for a read-only audit endpoint and a dry-run/default cleanup path that identifies invalid existing `SSHConnection.host` values without attempting network work.

```python
def test_audit_ssh_connection_hosts_reports_suspicious_saved_hosts(test_client, admin_headers, test_db):
    test_db.add(SSHConnection(host="http://bad", username="borg", port=22, status="failed"))
    test_db.add(SSHConnection(host=" u123456.your-storagebox.de ", username="borg", port=22, status="failed"))
    test_db.commit()

    response = test_client.get("/api/ssh-keys/connections/host-audit", headers=admin_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["suspicious"] == 1
    assert data["summary"]["normalizable"] == 1
```

- [ ] **Step 2: Implement audit and cleanup endpoints**

Add endpoints before `/{key_id}` routes so `/connections/host-audit` is not parsed as a key id:

```python
@router.get("/connections/host-audit")
async def audit_ssh_connection_hosts(...):
    ...

@router.post("/connections/host-cleanup")
async def cleanup_ssh_connection_hosts(dry_run: bool = True, ...):
    ...
```

The cleanup endpoint should only trim safely normalizable saved values by default. Suspicious malformed values must be reported, not silently rewritten.

- [ ] **Step 3: Run audit/cleanup tests**

Run:

```bash
.venv/bin/pytest tests/unit/test_api_ssh_keys.py -k "host_audit or host_cleanup" -q
```

Expected: PASS.

### Task 4: Frontend Tests

**Files:**
- Modify: `frontend/src/pages/__tests__/SSHConnectionsSingleKey.test.tsx`
- Create: `frontend/src/pages/ssh-connections-single-key/hostValidation.ts`
- Test: `frontend/src/pages/ssh-connections-single-key/hostValidation.test.ts`

- [ ] **Step 1: Write failing helper tests**

Add tests for safe trim and malformed values:

```ts
expect(normalizeSshHostInput('  u123456.your-storagebox.de  ')).toEqual({
  ok: true,
  host: 'u123456.your-storagebox.de',
})
expect(normalizeSshHostInput('host:23')).toEqual({
  ok: false,
  errorKey: 'sshConnections.validation.hostBareOnly',
})
```

- [ ] **Step 2: Write failing form behavior tests**

Add tests that deploy/edit/manual-test submit trimmed hosts and block `http://host` with inline helper text before calling the API.

```ts
await user.type(screen.getByLabelText(/^host$/i), 'http://host')
await user.click(screen.getByRole('button', { name: /^deploy key$/i }))
expect(await screen.findByText(/bare dns name or ip address/i)).toBeInTheDocument()
expect(sshKeysAPI.deploySSHKey).not.toHaveBeenCalled()
```

- [ ] **Step 3: Run frontend targeted tests to verify RED**

Run:

```bash
cd frontend && npm test -- src/pages/ssh-connections-single-key/hostValidation.test.ts src/pages/__tests__/SSHConnectionsSingleKey.test.tsx
```

Expected: FAIL because the helper and UI validation do not exist yet.

### Task 5: Frontend Implementation And Stories

**Files:**
- Create: `frontend/src/pages/ssh-connections-single-key/hostValidation.ts`
- Modify: `frontend/src/pages/SSHConnectionsSingleKey.tsx`
- Modify: `frontend/src/pages/ssh-connections-single-key/dialogs/DeployKeyDialog.tsx`
- Modify: `frontend/src/pages/ssh-connections-single-key/dialogs/EditConnectionDialog.tsx`
- Modify: `frontend/src/pages/ssh-connections-single-key/dialogs/TestConnectionDialog.tsx`
- Modify: `frontend/src/pages/ssh-connections-single-key/SSHConnectionDialogs.tsx`
- Modify: `frontend/src/pages/ssh-connections-single-key/types.ts`
- Modify: `frontend/src/locales/en.json`
- Update parity locales if required by `npm run check:locales`
- Create: `frontend/src/pages/ssh-connections-single-key/SSHConnectionDialogs.stories.tsx`

- [ ] **Step 1: Implement shared frontend validation**

Create a helper that mirrors backend decisions for browser pre-submit feedback:

```ts
export function normalizeSshHostInput(rawHost: string): HostValidationResult {
  const host = rawHost.trim()
  if (!host || hasForbiddenHostSyntax(host) || (!isBareIp(host) && !isBareDnsName(host))) {
    return { ok: false, errorKey: 'sshConnections.validation.hostBareOnly' }
  }
  return { ok: true, host }
}
```

- [ ] **Step 2: Wire validation into dialog submit handlers**

Add host error state in `SSHConnectionsSingleKey.tsx`. Each submit handler must normalize host before mutation:

```ts
const normalized = normalizeSshHostInput(connectionForm.host)
if (!normalized.ok) {
  setConnectionHostError(t(normalized.errorKey))
  return
}
deployKeyMutation.mutate({
  keyId: systemKey.id,
  connectionData: { ...connectionForm, host: normalized.host },
})
```

- [ ] **Step 3: Show inline MUI errors**

Pass `hostError` props to the three dialogs and render:

```tsx
<TextField
  error={Boolean(hostError)}
  helperText={hostError || undefined}
/>
```

- [ ] **Step 4: Add Storybook coverage**

Add a story that renders deploy/edit/manual-test dialog states with invalid host helper text visible. Reuse existing app providers only if the dialogs require them.

- [ ] **Step 5: Run targeted frontend tests to verify GREEN**

Run:

```bash
cd frontend && npm test -- src/pages/ssh-connections-single-key/hostValidation.test.ts src/pages/__tests__/SSHConnectionsSingleKey.test.tsx
```

Expected: PASS.

### Task 6: Final Validation And Handoff

**Files:**
- Update workpad comment only for progress tracking.

- [ ] **Step 1: Run backend validation**

```bash
.venv/bin/ruff check app tests
.venv/bin/ruff format --check app tests
.venv/bin/pytest tests/unit/test_api_ssh_keys.py
```

- [ ] **Step 2: Run frontend validation**

```bash
cd frontend && npm run check:locales
cd frontend && npm run typecheck
cd frontend && npm run lint
cd frontend && npm run build
cd frontend && npm run snapshots
```

- [ ] **Step 3: Run runtime walkthrough**

Launch Borg UI with the repo-approved local path and validate that deploy, edit, and manual-test host fields show pre-submit errors for malformed hosts and allow a valid Storage Box-style host.

- [ ] **Step 4: Commit and push**

Use the repo `commit` and `push` skills. The PR body must use `.github/PULL_REQUEST_TEMPLATE.md`, include the validation evidence, attach the PR to BOR-14, and ensure the PR has the `symphony` label.
