# Borg UI Vault App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inside Borg UI, show a Vault card to installs whose licence owns a Vault, connect it in one dialog (no hostname, username or key to copy), and show usage, payment state and space release.

**Architecture:** A thin backend module (`vault_service.py` plus `api/vault.py`) proxies the licence service's Vault API with the stored licence key, registers the existing system SSH key, and creates an ordinary `SSHConnection` tagged with the Vault id. The repository itself is created by the existing `POST /api/repositories/` endpoint. The frontend adds a small `components/vault/` folder: a hook, four presentational components and one dialog, mounted on the Repositories page.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, pytest; React 19, MUI 9, TanStack Query, react-i18next, Vitest, Storybook 10.

**Spec:** `docs/engineering/specs/2026-11-11-borg-ui-vault-beta.md`. Sections 9.1, 9.2 and 11 are what this plan implements. Read sections 1 to 5 and 9 to 12 before task 1.

## How to work on this plan

Rules that come from this repository's `AGENTS.md` and the owner's standing instructions. They are not optional.

- **Worktree.** Do all work in a git worktree on a new branch `feat/vault-app` cut from a freshly fetched `origin/main`. Skill: `superpowers:using-git-worktrees`. Never edit the main checkout. In the worktree run `cd frontend && npm ci` once; the pre-push hook runs oxlint and fails without `node_modules`.
- **TDD.** Skill: `superpowers:test-driven-development`. Every task starts with a failing test.
- **UI skill.** Before any UI decision or code in tasks 5 to 9, load the `ui-ux-pro-max` skill and follow it. If your agent has no skills (for example Codex), read `AGENTS.md` sections "UI Workflow", "UI Preferences" and "Shared UI Components", then copy the structure, spacing and tone handling of `frontend/src/components/LicenseSeatsCard.tsx`, which is the closest existing component. Do not invent new visual patterns.
- **Shared components.** Dialogs use `frontend/src/components/shared/ResponsiveDialog.tsx`, never raw MUI `Dialog`. Chips use `tintChipSx` from `components/shared/tones.ts`. No heavy left accent borders on cards, banners or rows: use a full outline with a light tint.
- **Stories.** Every new or changed UI component gets a Storybook story showing each state. Do not commit generated PNGs.
- **Visual proof before pushing.** Storybook needs Node 20.19 or newer: `fnm use 24`. Run `cd frontend && npm run storybook`, open each new story in light and dark mode at 375 px and 1280 px, and fix what looks wrong. For screenshots run `npm run snapshots` (output is git-ignored). Tests passing is not visual proof.
- **Locales.** Every string goes into `frontend/src/locales/en.json`, `de.json`, `es.json` and `it.json`. A language covers the whole feature or none of it. `npm run check:locales` must pass.
- **Copy.** No em dash anywhere (UI copy, comments, commit messages, docs). No exclamation marks. Sentence case.
- **Fixtures.** Never paste real hostnames, paths, emails or licence keys into tests or stories. `scripts/check-no-personal-paths.sh` runs in pre-commit and CI.
- **Migrations.** Recompute the Alembic head against fetched `origin/main` right before writing the migration (task 1), because another merge may have added a revision.
- **Versions.** Do not bump the app or agent version.
- **Backend tests** run in the worktree: `pytest tests/unit/<file> -q`. If `tests/unit/test_api_auth*.py` fails with OIDC errors in the main checkout, that is the local `.env`, not your change; it does not happen in a worktree.
- **Before claiming completion:** skill `superpowers:verification-before-completion`. Then the project skill `prep-pr` (local CodeRabbit review, fix what is real, review again until it finds nothing, then open the PR).
- **Do not commit a fix the owner is still reproducing.** This plan's commits are new feature work behind a card that only appears for Vault owners, so commit per task; but if the owner reports a problem during Gate C, fix it and wait for their confirmation before committing that fix.

## Global Constraints

- Vault repositories are Borg 1: `borg_version: 1` in the create payload. No Borg 2 code is touched. Do not add `borg_version` checks or `BorgApiClient` branching to existing v1 code.
- The Vault card renders nothing unless the licence service reports a Vault for this licence. No teaser, no promotion.
- All `/api/vault` routes are admin only and are registered in `ROUTE_ACCESS_REGISTRY` as `"admin"`.
- The licence key never leaves the backend. The frontend never receives `host_key`.
- A licence service outage must not break the Repositories page: the status endpoint answers 200 with `vault: null, reason: "service_unavailable"`.
- Sizes are bytes in the API and formatted in the UI with decimal units (1 TB = 10^12 bytes).
- Repository path: `<base_path>/<slug>`, slug rule from spec section 11.2.
- Commit after every task with a conventional message, ending with `Co-Authored-By: Claude <noreply@anthropic.com>` when the author is Claude.

## Review Focus

1. The user clicks Connect twice, or retries after a failure halfway. There must be one SSH connection for the Vault, not two. Pinned in task 3.
2. The licence service is down or slow when the Repositories page loads. The page renders normally without the card. Pinned in tasks 2 and 6.
3. The repository is created on the Vault but the passphrase fields did not match or were empty. The dialog must refuse before calling connect. Pinned in task 8.
4. The connect step succeeds and repository creation fails (name already exists). The dialog must show the server's error, keep the form, and a retry must reuse the connection. Pinned in tasks 3 and 8.
5. A read-only Vault. The card must say backups are paused, restores work, and show the deletion date, in every language. Pinned in tasks 7 and 9.

## File Structure

```
app/database/alembic/versions/<rev>_add_ssh_connection_vault_id.py   new
app/database/models.py                 modified: SSHConnection.vault_id
app/services/vault_service.py          new: licence service calls, connect, status
app/api/vault.py                       new: /api/vault routes
app/api/ssh_keys.py                    modified: extract create_system_ssh_key()
app/main.py                            modified: include the router
app/core/route_access.py               modified: five entries
tests/unit/test_ssh_connection_vault_id_migration.py   new
tests/unit/test_vault_service.py       new
tests/unit/test_api_vault.py           new
frontend/src/services/api.ts           modified: vaultAPI
frontend/src/components/vault/types.ts            new
frontend/src/components/vault/vaultFormat.ts      new: formatBytes, usagePercent, repoSlug, vaultPathPrefix
frontend/src/components/vault/useVault.ts         new
frontend/src/components/vault/VaultUsageMeter.tsx new (+ .stories.tsx)
frontend/src/components/vault/VaultStatusBanner.tsx new (+ .stories.tsx)
frontend/src/components/vault/VaultCard.tsx       new (+ .stories.tsx)
frontend/src/components/vault/ConnectVaultDialog.tsx new (+ .stories.tsx)
frontend/src/components/vault/__tests__/*.test.ts(x)   new
frontend/src/pages/Repositories.tsx    modified: mount the card and dialog
frontend/src/pages/repositories-page/RepositoryGroups.tsx   modified: Vault chip
frontend/src/locales/{en,de,es,it}.json   modified: "vault" section
docs/vault.md                          new user doc
docs/.vitepress/config.mts             modified: sidebar entry
```

---

### Task 1: Migration and model

**Files:**
- Create: `app/database/alembic/versions/<rev>_add_ssh_connection_vault_id.py`, `tests/unit/test_ssh_connection_vault_id_migration.py`
- Modify: `app/database/models.py` (class `SSHConnection`)

**Interfaces:**
- Produces: nullable string column `ssh_connections.vault_id`, and `SSHConnection.vault_id = Column(String, nullable=True, index=True)`.

- [ ] **Step 1: Find the current head**

Run:

```bash
git fetch origin && git merge-base --is-ancestor origin/main HEAD && echo "branch contains origin/main"
python - <<'EOF'
import glob, re
revs, downs = {}, set()
for path in glob.glob("app/database/alembic/versions/*.py"):
    text = open(path).read()
    rev = re.search(r'^revision[^=]*=\s*"([^"]+)"', text, re.M)
    down = re.search(r'^down_revision[^=]*=\s*(.+)$', text, re.M)
    if rev:
        revs[rev.group(1)] = path
        if down:
            downs.update(re.findall(r'"([^"]+)"', down.group(1)))
print([r for r in revs if r not in downs])
EOF
```

Expected: one revision id. On 2026-11-11 it was `f7a4417c5d4d`. Use whatever it prints as `down_revision`. If it prints two ids, stop and tell the owner: `main` has two heads and that must be fixed first.

- [ ] **Step 2: Write the failing migration test**

A revision that no release ships yet must be claimed by a test under `tests/migrations` that uses the `upgraded_from` fixture (`tests/migrations/test_revisions_have_tests.py` enforces this; a copy of an older test under `tests/unit` is rejected). Read `tests/migrations/test_backup_plan_restore_check_after_upgrade.py` and `tests/migrations/conftest.py` first, then create `tests/migrations/test_ssh_connection_vault_id_after_upgrade.py` on the same pattern:

- Module docstring: "Upgrade test for revision a7c3e9d1f5b2 (ssh_connections.vault_id). From every release before it, SSH connections keep their rows and start without a Vault id."
- `REVISION = "a7c3e9d1f5b2"`, `RELEASES = upgrade_paths.releases_before(REVISION) or ["no-release-tags"]`.
- `ROWS = {"ssh_connections": [{"id": 500, "host": "backup.example.com", "username": "borg", "port": 22}]}`.
- One test, `test_connections_survive_and_start_without_a_vault_id(release, dialect, upgraded_from)`, parametrized over `DIALECTS` and `RELEASES` exactly like the example: `require_releases()`, `db = upgraded_from(release, dialect=dialect, rows=ROWS)`, then in a `Session(db.engine)`: `connection = session.get(SSHConnection, 500)`; assert `connection.host == "backup.example.com"` and `connection.vault_id is None`.

The revision id `a7c3e9d1f5b2` was unused on 2026-11-11 (`d4e5f6a7b8c9` is taken by the auto prune preview revision). Check with `ls app/database/alembic/versions | grep a7c3e9d1f5b2`; if that prints a file, pick another 12 character hex id and use it everywhere below.

Run: `pytest tests/migrations/test_ssh_connection_vault_id_after_upgrade.py -q`
Expected: FAIL (`SSHConnection` has no attribute `vault_id`), or every case skipped when the checkout has no release tags; in that case run `git fetch --tags` first.

- [ ] **Step 3: Write the migration and the model column**

Copy `app/database/alembic/versions/c9d0e1f2a3b4_add_ssh_connection_shell_restricted.py` to `a7c3e9d1f5b2_add_ssh_connection_vault_id.py`. Set `revision = "a7c3e9d1f5b2"`, `down_revision` from step 1, a docstring that says: "add ssh_connections.vault_id. Set when the connection was created by Connect Vault; holds the Borg UI Vault id (vlt_...). Null for every other connection." `upgrade` adds `sa.Column("vault_id", sa.String(), nullable=True)`; `downgrade` drops it.

In `models.py`, add `vault_id = Column(String, nullable=True, index=True)` to `SSHConnection` next to `shell_restricted`, with a one-line comment: `# Borg UI Vault id when Connect Vault created this connection`.

- [ ] **Step 4: Run**

Run: `pytest tests/migrations -q 2>&1 | tail -3`
Expected: all pass, including `test_revisions_have_tests.py`.

- [ ] **Step 5: Commit**

```bash
git add app/database/alembic/versions app/database/models.py tests/migrations/test_ssh_connection_vault_id_after_upgrade.py
git commit -m "feat(vault): tag SSH connections created for a Vault"
```

---

### Task 2: Vault status service

**Files:**
- Create: `app/services/vault_service.py`, `tests/unit/test_vault_service.py`

**Interfaces:**
- Consumes: `app.services.licensing_service._post_activation(endpoint_path, payload)` and `get_or_create_licensing_state(db)` (both exist), `SSHConnection`, `Repository`.
- Produces:
  - `class VaultUnavailable(RuntimeError)`: the licence service could not be reached or answered with an error.
  - `async def fetch_vault(db) -> dict | None`: the raw vault object from `/v1/vault/status` (including `host_key`), or `None` when the licence owns no Vault. Raises `VaultUnavailable`, and `RuntimeError("no_license_key")` when no key is stored.
  - `def find_vault_connection(db, vault_id: str) -> SSHConnection | None`
  - `def public_vault(vault: dict) -> dict`: a copy without `host_key`.
  - `async def get_vault_status(db) -> dict`: `{"vault": dict | None, "connection_id": int | None, "repository_count": int, "reason": str | None}`. Never raises.

`get_vault_status` rules: no stored licence key gives `{"vault": None, "connection_id": None, "repository_count": 0, "reason": "no_license_key"}` without any network call. `VaultUnavailable` gives the same with `reason: "service_unavailable"` and logs a warning. `repository_count` counts `Repository` rows whose `path` starts with `f"ssh://{username}@{host}"`.

`fetch_vault` sends `{"license_key": <stored key>, "instance_id": state.instance_id}`. It wraps any exception from `_post_activation` (it raises `RuntimeError` for HTTP errors and httpx errors for network failures) into `VaultUnavailable(str(error))`.

- [ ] **Step 1: Write the failing tests**

Use the patching style of `tests/unit/test_licensing_service.py` (`patch("app.services.vault_service._post_activation", new=AsyncMock(...))`) and its database fixture. Give the licensing state a key with `state.license_key = "TEST-KEY-0000-0000"`.

```python
VAULT = {
    "vault_id": "vlt_0123456789ab", "tier": "1tb", "quota_bytes": 1_000_000_000_000,
    "used_bytes": 312_000_000_000, "used_checked_at": "2026-11-11T10:17:00.000Z", "status": "active",
    "paid_through": "2027-11-11T09:00:00.000Z", "cancel_at": None, "read_only_at": None, "delete_at": None,
    "host": "v0123456789ab.vault.example.test", "port": 22, "username": "v0123456789ab",
    "base_path": "/srv/vault/v0123456789ab",
    "host_key": "v0123456789ab.vault.example.test ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleExampleExampleExampleExampleExampleE",
    "connected": False, "release": None,
}
```

| Test name | Arrange | Assert |
|---|---|---|
| `test_status_without_a_licence_key_makes_no_call` | no key stored; `_post_activation` mocked | result reason `no_license_key`, `vault` None; mock not awaited |
| `test_status_returns_the_vault_without_its_host_key` | mock returns `{"vault": VAULT}` | `result["vault"]["vault_id"] == "vlt_0123456789ab"`; `"host_key" not in result["vault"]`; `connection_id` None; `repository_count == 0`; `reason` None; the mock was awaited with `"/v1/vault/status"` and a payload holding the key and the instance id |
| `test_status_reports_no_vault` | mock returns `{"vault": None}` | `vault` None, `reason` None |
| `test_status_survives_a_service_outage` | mock raises `RuntimeError("activation service offline")` | `vault` None, `reason == "service_unavailable"` |
| `test_status_finds_the_connection_and_counts_repositories` | an `SSHConnection(vault_id="vlt_0123456789ab", host=VAULT["host"], username=VAULT["username"], port=22)`; two `Repository` rows with paths `ssh://v0123456789ab@v0123456789ab.vault.example.test:22/srv/vault/v0123456789ab/a` and `/local/b` | `connection_id` equals the connection's id; `repository_count == 1` |

For the `Repository` rows, copy the minimal constructor arguments used by an existing unit test that creates a repository (search `tests/unit` for `Repository(`).

- [ ] **Step 2: Run and see them fail**

Run: `pytest tests/unit/test_vault_service.py -q`
Expected: import error for `app.services.vault_service`.

- [ ] **Step 3: Implement, run, commit**

Run: `pytest tests/unit/test_vault_service.py -q && ruff check app tests && ruff format --check app tests`
Expected: 5 passed, ruff clean.

```bash
git add app/services/vault_service.py tests/unit/test_vault_service.py
git commit -m "feat(vault): read the Vault status from the licence service"
```

---

### Task 3: Connect

**Files:**
- Modify: `app/services/vault_service.py`, `app/api/ssh_keys.py`, `tests/unit/test_vault_service.py`

**Interfaces:**
- Produces in `app/api/ssh_keys.py`: `async def create_system_ssh_key(db, *, name: str, description: str, key_type: str) -> SSHKey`: the body of the existing `generate_ssh_key` handler from "Generate SSH key pair" down to and including the filesystem deploy, moved into a function. It raises `RuntimeError(<message>)` when key generation fails. The handler keeps its existing checks and response and calls this function. Behaviour of the endpoint must not change; `tests/unit/test_api_ssh_keys.py` must still pass untouched.
- Changes in `app/api/ssh_keys.py`: `test_ssh_key_connection(ssh_key, host, username, port, connection=None)`. The new optional argument replaces the `None` in its `host_key_ssh_opts(None)` call, so a caller that passes a connection is checked against that connection's pinned host key. With `None` it uses the shared known-hosts file and accepts a first-seen key, which is what every existing caller keeps doing.
- Produces in `vault_service.py`:
  - `async def ensure_system_key(db) -> SSHKey`: the active system key, created as `ed25519` with name `"System SSH Key"` when none exists.
  - `async def connect_vault(db) -> dict`: `{"connection_id": int, "base_path": str, "vault": <public vault>}`.
  - `class VaultConnectError(RuntimeError)` with attribute `code: str`.

`connect_vault` steps:

1. `state` and key as in `fetch_vault`; no key raises `VaultConnectError("no_license_key")`.
2. `ssh_key = await ensure_system_key(db)`.
3. `POST /v1/vault/keys` with `license_key`, `instance_id`, `public_key = ssh_key.public_key`, `label = socket.gethostname()[:64]`. A failure raises `VaultConnectError("service_failed")` with the service's message. A response without a `vault` raises `VaultConnectError("vault_not_found")`.
4. Upsert the connection: `find_vault_connection(db, vault["vault_id"])`, else a new `SSHConnection`. Set `ssh_key_id`, `host`, `username`, `port`, `default_path = vault["base_path"]`, `vault_id`. Commit.
5. Pin the host key from the licence service: `pin_host_key(connection, db, vault["host_key"])` from `app.utils.ssh_host_keys`. A Vault whose `host_key` is empty or missing is refused with `VaultConnectError("host_key_missing")` and the message "The Vault service did not send a host key. Try again in a few minutes." Do that check right after step 3, before the connection row is written and before any SSH connection: without a pin, the test in step 6 would accept whatever key the host presents. Before relying on this, read `scan_host_key` and `host_keys_match` in that module and confirm a line of the form `<host> ssh-ed25519 <base64>` is what a scan of a port 22 host stores; if the module stores a different form (for example without the host), convert to that form here and say so in a comment.
6. Test the connection with the existing `test_ssh_key_connection(ssh_key, host, username, port, connection=connection)` from `app.api.ssh_keys` (import it inside the function to avoid an import cycle; passing the connection is what makes the test verify the key pinned in step 5, not a key accepted on first use), and record the result on the connection exactly as the `test_ssh_connection` handler in that file does (`status`, `last_test`, `last_success`, `error_message`, `shell_restricted`). A failed test raises `VaultConnectError("ssh_failed")` with the test's error text. The connection row stays, so a retry reuses it.
7. Return the dict.

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_vault_service.py`)

Patch `_post_activation`, `app.services.vault_service.pin_host_key` (a `MagicMock`), and the SSH test (`patch("app.api.ssh_keys.test_ssh_key_connection", new=AsyncMock(return_value={"success": True, "message": "ok", "restricted": True}))`). Seed a system key with `SSHKey(name="System SSH Key", public_key="ssh-ed25519 AAAAexample system", private_key="x", key_type="ed25519", is_system_key=True, is_active=True)`.

| Test name | Arrange | Assert |
|---|---|---|
| `test_connect_registers_the_system_key_and_creates_the_connection` | mock returns `{"vault": {**VAULT, "connected": True}}` | awaited with `"/v1/vault/keys"` and `public_key == "ssh-ed25519 AAAAexample system"`; one `SSHConnection` with `vault_id`, `host`, `username`, `port == 22`, `default_path == "/srv/vault/v0123456789ab"`, `status == "connected"`, `shell_restricted is True`; `pin_host_key` called once with the vault's `host_key`; the SSH test mock awaited once with `connection=` that same `SSHConnection`; result `connection_id` matches, `"host_key" not in result["vault"]` |
| `test_connect_twice_reuses_the_connection` | call twice | exactly one `SSHConnection` row with that `vault_id` |
| `test_connect_without_a_vault_fails_clearly` | mock returns `{"vault": None}` | raises `VaultConnectError` with `code == "vault_not_found"`; no connection row |
| `test_connect_refuses_a_vault_without_a_host_key` | mock returns the vault with `host_key: ""` | raises `VaultConnectError` with `code == "host_key_missing"`; no connection row; the SSH test mock was not awaited; `pin_host_key` not called |
| `test_connect_reports_a_failed_ssh_test_and_keeps_the_row` | SSH test returns `{"success": False, "error": "Connection refused"}` | raises with `code == "ssh_failed"` and the text in the message; one connection row with `status == "failed"`; a second call with a succeeding test leaves one row with `status == "connected"` |
| `test_connect_creates_a_system_key_when_none_exists` | no system key; patch `app.api.ssh_keys.create_system_ssh_key` with an `AsyncMock` returning a seeded key | the mock was awaited once with `key_type="ed25519"` |
| `test_connect_wraps_a_licence_service_error` | mock raises `RuntimeError("Too many requests")` | raises with `code == "service_failed"` and that message |

- [ ] **Step 2: Run and see them fail**

Run: `pytest tests/unit/test_vault_service.py -q`

- [ ] **Step 3: Extract `create_system_ssh_key`, implement `connect_vault`**

- [ ] **Step 4: Run**

Run: `pytest tests/unit/test_vault_service.py tests/unit/test_api_ssh_keys.py tests/unit/test_ssh_host_keys.py -q 2>&1 | tail -3 && ruff check app tests && ruff format --check app tests`
Expected: all pass, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add app/services/vault_service.py app/api/ssh_keys.py tests/unit/test_vault_service.py
git commit -m "feat(vault): connect a Vault with the system SSH key"
```

---

### Task 4: API routes

**Files:**
- Create: `app/api/vault.py`, `tests/unit/test_api_vault.py`
- Modify: `app/main.py`, `app/core/route_access.py`, `app/services/vault_service.py`

**Interfaces:**
- Produces in `vault_service.py`: `async def vault_portal_url(db) -> str`, `async def request_release(db) -> dict`, `async def cancel_release(db) -> dict` (the last two return `{"vault": <public vault>}`), each a `_post_activation` call to `/v1/vault/portal`, `/v1/vault/release`, `/v1/vault/release/cancel`.
- Produces routes (all `Depends(get_current_admin_user)`, the dependency `app/api/system.py` uses for licence seats):

| Route | Success | Failure |
|---|---|---|
| `GET /api/vault` | 200, the dict of `get_vault_status` | never fails for service errors |
| `POST /api/vault/connect` | 200 `{"connection_id", "base_path", "vault"}` | 400 `vault_connect_failed` with the message |
| `POST /api/vault/portal` | 200 `{"url": "..."}` | 400 `vault_portal_failed` |
| `POST /api/vault/release` | 200 `{"vault": ...}` | 400 `vault_release_failed` |
| `POST /api/vault/release/cancel` | 200 `{"vault": ...}` | 400 `vault_release_failed` |

Error body shape: the one `_licensing_http_error` in `app/api/system.py` produces (`detail.error.code` and `detail.error.message`). Move that helper into a shared spot only if importing it from `system.py` creates a cycle; otherwise import it.

Register the router in `app/main.py` next to the system router: `app.include_router(vault.router, prefix="/api/vault", tags=["Vault"])`. Add the five `(method, path)` pairs to `ROUTE_ACCESS_REGISTRY` in alphabetical position with the value `"admin"`. The paths are `/api/vault`, `/api/vault/connect`, `/api/vault/portal`, `/api/vault/release`, `/api/vault/release/cancel`. If FastAPI registers the root route as `/api/vault/` (with a slash), declare the route as `@router.get("")` so the path is `/api/vault`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_api_vault.py`, with the `test_client` and `admin_headers` fixtures used in `tests/unit/test_api_system.py`, and the fixture for a non-admin user's headers that the same folder's permission tests use (search for `operator_headers` or `viewer_headers` in `tests/conftest.py` and use whichever exists).

| Test name | Assert |
|---|---|
| `test_vault_status_requires_auth` | no headers: 401 or 403 (match what `GET /api/system/licensing/seats` returns without headers) |
| `test_vault_routes_are_admin_only` | each of the five routes with non-admin headers: 403 |
| `test_vault_status_passes_the_service_result_through` | `patch("app.api.vault.get_vault_status", new=AsyncMock(return_value={"vault": None, "connection_id": None, "repository_count": 0, "reason": "service_unavailable"}))`: 200 and that JSON |
| `test_vault_connect_maps_errors` | `connect_vault` mocked to raise `VaultConnectError("ssh_failed")` with message "Connection refused": 400, `detail.error.code == "vault_connect_failed"`, message contains "Connection refused" |
| `test_vault_portal_returns_the_url` | mocked to return `"https://pay.example.test/update"`: 200 `{"url": ...}` |
| `test_vault_release_and_cancel` | both mocked: 200 with the vault |

- [ ] **Step 2: Run and see them fail, implement, run**

Run: `pytest tests/unit/test_api_vault.py tests/unit/test_route_access_registry.py tests/unit/test_vault_service.py -q 2>&1 | tail -3 && ruff check app tests && ruff format --check app tests`
Expected: all pass. `test_route_access_registry.py` fails if a route is missing from the registry or spelled differently; fix the registry, not the test.

- [ ] **Step 3: Commit**

```bash
git add app/api/vault.py app/main.py app/core/route_access.py app/services/vault_service.py tests/unit/test_api_vault.py
git commit -m "feat(vault): admin API for status, connect, payment link and space release"
```

---

### Task 5: Frontend types, formatting and API client

**Files:**
- Create: `frontend/src/components/vault/types.ts`, `frontend/src/components/vault/vaultFormat.ts`, `frontend/src/components/vault/__tests__/vaultFormat.test.ts`
- Modify: `frontend/src/services/api.ts`

**Interfaces:**
- Produces in `types.ts`:

```ts
export type VaultStatus = 'active' | 'past_due' | 'read_only' | 'deleted'

export interface VaultRelease {
  state: 'scheduled' | 'running' | 'done' | 'failed'
  release_at: string
}

export interface Vault {
  vault_id: string
  tier: string
  quota_bytes: number
  used_bytes: number
  used_checked_at: string | null
  status: VaultStatus
  paid_through: string | null
  cancel_at: string | null
  read_only_at: string | null
  delete_at: string | null
  host: string
  port: number
  username: string
  base_path: string
  connected: boolean
  release: VaultRelease | null
}

export interface VaultStatusResponse {
  vault: Vault | null
  connection_id: number | null
  repository_count: number
  reason: 'no_license_key' | 'service_unavailable' | null
}

export interface VaultConnectResponse {
  connection_id: number
  base_path: string
  vault: Vault
}

/** What the card shows. Derived once so every component agrees. */
export type VaultCardState =
  'ready' | 'connected' | 'full' | 'past_due' | 'read_only' | 'ending' | 'deleted'
```

- Produces in `vaultFormat.ts`:
  - `formatVaultBytes(bytes: number): string` (`"312 GB"`, `"1 TB"`, `"1.5 TB"`, `"62.9 MB"`, `"0 MB"`)
  - `vaultUsagePercent(used: number, quota: number): number` (integer 0 to 100)
  - `repoSlug(name: string): string` (lowercase; every character outside `[a-z0-9-]` becomes `-`; runs of `-` collapse; trimmed of `-`; at most 48 characters; empty input gives `"vault"`)
  - `vaultPathPrefix(vault: Pick<Vault, 'username' | 'host'>): string` (`ssh://<username>@<host>`)
  - `vaultCardState(response: VaultStatusResponse): VaultCardState | null`: null when there is no vault; `deleted`, `read_only`, `past_due` from the status; then `ending` when `cancel_at` is set; then `ready` when `connection_id` is null; then `full` when `used_bytes >= quota_bytes`; otherwise `connected`.
- Produces in `api.ts` (next to `licensingAPI`):

```ts
export const vaultAPI = {
  status: () => api.get<VaultStatusResponse>('/vault'),
  connect: () => api.post<VaultConnectResponse>('/vault/connect'),
  portal: () => api.post<{ url: string }>('/vault/portal'),
  release: () => api.post<{ vault: Vault }>('/vault/release'),
  cancelRelease: () => api.post<{ vault: Vault }>('/vault/release/cancel'),
}
```

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/components/vault/__tests__/vaultFormat.test.ts
import { describe, expect, it } from 'vitest'
import { formatVaultBytes, repoSlug, vaultCardState, vaultPathPrefix, vaultUsagePercent } from '../vaultFormat'
import type { Vault, VaultStatusResponse } from '../types'

const vault: Vault = {
  vault_id: 'vlt_0123456789ab', tier: '1tb', quota_bytes: 1_000_000_000_000, used_bytes: 312_000_000_000,
  used_checked_at: '2026-11-11T10:17:00.000Z', status: 'active', paid_through: '2027-11-11T09:00:00.000Z',
  cancel_at: null, read_only_at: null, delete_at: null, host: 'v0123456789ab.vault.example.test', port: 22,
  username: 'v0123456789ab', base_path: '/srv/vault/v0123456789ab', connected: true, release: null,
}
const response = (over: Partial<Vault> = {}, connectionId: number | null = 7): VaultStatusResponse => ({
  vault: { ...vault, ...over }, connection_id: connectionId, repository_count: 1, reason: null,
})

describe('vaultFormat', () => {
  it('formats sizes in decimal units', () => {
    expect(formatVaultBytes(312_000_000_000)).toBe('312 GB')
    expect(formatVaultBytes(1_000_000_000_000)).toBe('1 TB')
    expect(formatVaultBytes(1_500_000_000_000)).toBe('1.5 TB')
    expect(formatVaultBytes(62_920_000)).toBe('62.9 MB')
    expect(formatVaultBytes(0)).toBe('0 MB')
  })

  it('computes a bounded usage percentage', () => {
    expect(vaultUsagePercent(312_000_000_000, 1_000_000_000_000)).toBe(31)
    expect(vaultUsagePercent(2, 1)).toBe(100)
    expect(vaultUsagePercent(1, 0)).toBe(0)
  })

  it('builds a safe repository slug', () => {
    expect(repoSlug('Vault Home Server')).toBe('vault-home-server')
    expect(repoSlug('  ../../etc/passwd ')).toBe('etc-passwd')
    expect(repoSlug('Ünïcode & spaces!!')).toBe('n-code-spaces')
    expect(repoSlug('')).toBe('vault')
    expect(repoSlug('---')).toBe('vault')
    expect(repoSlug('a'.repeat(80))).toHaveLength(48)
  })

  it('builds the path prefix of vault repositories', () => {
    expect(vaultPathPrefix(vault)).toBe('ssh://v0123456789ab@v0123456789ab.vault.example.test')
  })

  it('derives the card state in priority order', () => {
    expect(vaultCardState({ vault: null, connection_id: null, repository_count: 0, reason: null })).toBeNull()
    expect(vaultCardState(response({}, null))).toBe('ready')
    expect(vaultCardState(response())).toBe('connected')
    expect(vaultCardState(response({ used_bytes: 1_000_000_000_000 }))).toBe('full')
    expect(vaultCardState(response({ status: 'past_due' }))).toBe('past_due')
    expect(vaultCardState(response({ status: 'read_only' }))).toBe('read_only')
    expect(vaultCardState(response({ cancel_at: '2027-11-11T09:00:00.000Z' }))).toBe('ending')
    expect(vaultCardState(response({ status: 'read_only', cancel_at: '2027-11-11T09:00:00.000Z' }))).toBe('read_only')
    expect(vaultCardState(response({ status: 'deleted' }))).toBe('deleted')
  })
})
```

- [ ] **Step 2: Run, implement, run**

Run: `cd frontend && npx vitest run src/components/vault/__tests__/vaultFormat.test.ts && npm run typecheck`
Expected after implementing: 5 passed, typecheck clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/vault frontend/src/services/api.ts
git commit -m "feat(vault): frontend types, formatting and API client"
```

---

### Task 6: Locale strings and the hook

**Files:**
- Modify: `frontend/src/locales/en.json`, `de.json`, `es.json`, `it.json`
- Create: `frontend/src/components/vault/useVault.ts`, `frontend/src/components/vault/__tests__/useVault.test.tsx`

**Interfaces:**
- Produces: `useVault(enabled: boolean)` returning `{ data: VaultStatusResponse | undefined, state: VaultCardState | null, isLoading: boolean, refetch }`. Query key `['vault']`, `staleTime: 5 * 60 * 1000`, `retry: false`, `enabled`. A failed request yields `state: null` (the card hides).
- Produces a top-level `"vault"` object in all four locale files with exactly these keys.

English values:

```json
"vault": {
  "chip": "Vault",
  "card": {
    "readyTitle": "Your Vault is ready",
    "readyBody": "{{size}} of offsite storage in an EU data centre. Connect it to start backing up.",
    "connect": "Connect Vault",
    "connectedTitle": "Borg UI Vault",
    "renews": "Renews {{date}}",
    "ends": "Ends {{date}}",
    "usage": "{{used}} of {{total}} used",
    "usageChecked": "Measured {{time}}",
    "addRepository": "Add a repository",
    "updatePayment": "Update payment",
    "releaseSpace": "Release space",
    "releaseScheduled": "Space release on {{date}}",
    "releaseRunning": "Releasing space",
    "cancelRelease": "Cancel release"
  },
  "banner": {
    "pastDueTitle": "We could not renew your Vault",
    "pastDueBody": "Backups and restores keep working. If the payment is still missing on {{readOnlyDate}}, the Vault becomes read-only.",
    "readOnlyTitle": "Your Vault is read-only",
    "readOnlyBody": "Restores work, new backups are paused. The data is deleted on {{deleteDate}} unless the payment is updated.",
    "fullTitle": "Your Vault is full",
    "fullBody": "New backups will fail. Prune old archives and release space, or ask us for a larger Vault.",
    "endingTitle": "Your Vault ends on {{date}}",
    "endingBody": "After that it is read-only for 30 days, then the data is deleted on {{deleteDate}}.",
    "deletedTitle": "Your Vault was deleted",
    "deletedBody": "You can remove its repositories from Borg UI."
  },
  "connect": {
    "title": "Connect Vault",
    "name": "Repository name",
    "nameHelp": "Shown in Borg UI. You can add more repositories to the same Vault later.",
    "passphrase": "Encryption passphrase",
    "passphraseConfirm": "Repeat the passphrase",
    "passphraseHelp": "Encrypted on this machine. We cannot read your backups or recover a lost passphrase.",
    "passphraseTooShort": "Use at least 8 characters.",
    "passphraseMismatch": "The passphrases do not match.",
    "nameRequired": "Enter a repository name.",
    "submit": "Connect",
    "cancel": "Cancel",
    "stepConnecting": "Connecting to your Vault",
    "stepCreating": "Creating the encrypted repository",
    "doneTitle": "Your Vault is connected",
    "doneBody": "Add it to a backup plan so backups start going there.",
    "openPlans": "Open backup plans",
    "close": "Close",
    "failed": "Could not connect the Vault. {{message}}",
    "createFailed": "The Vault is connected, but the repository could not be created. {{message}}"
  },
  "release": {
    "title": "Release space",
    "body": "Archives you pruned or deleted still take up space on your Vault. Releasing removes them for good and frees that space.",
    "delay": "For safety this happens in 7 days. We email you the date and a link to cancel. For 7 more days after it has run, our support can bring back what it removed.",
    "confirm": "Schedule release",
    "scheduledToast": "Space release scheduled",
    "cancelledToast": "Space release cancelled",
    "failed": "Could not schedule the release. {{message}}"
  },
  "portalFailed": "Could not open the payment page. {{message}}"
}
```

Translate every value for `de`, `es` and `it`: formal address, the words "Vault" and "Borg UI" untranslated, every `{{placeholder}}` kept exactly. Insert the object in the same position in each file (alphabetical order is not used in these files; put it directly before the top-level `"licensing"` key in all four).

- [ ] **Step 1: Write the hook test**

`useVault.test.tsx`: mock `../../../services/api` so `vaultAPI.status` is a `vi.fn()`; render the hook with `renderHook` inside a `QueryClientProvider` (copy the wrapper from an existing hook test in `frontend/src/hooks/__tests__/`).

| Test name | Assert |
|---|---|
| `does not fetch when disabled` | `useVault(false)`; `vaultAPI.status` not called; `state` null |
| `returns the card state for a connected vault` | status resolves with `{ data: <response with connection_id 7> }`; `await waitFor(() => expect(result.current.state).toBe('connected'))` |
| `hides the card when the request fails` | status rejects; `state` stays null and `isLoading` becomes false |
| `hides the card when there is no vault` | resolves with `vault: null, reason: "service_unavailable"`; `state` null |

- [ ] **Step 2: Add the strings to all four files, implement the hook**

- [ ] **Step 3: Run**

Run: `cd frontend && npx vitest run src/components/vault && npm run check:locales && npm run typecheck && npm run format:check`
Expected: tests pass, locale parity OK, typecheck and format clean.

- [ ] **Step 4: Check for mixed language**

Run: `cd frontend && node -e "const en=require('./src/locales/en.json').vault;for(const l of ['de','es','it']){const o=require('./src/locales/'+l+'.json').vault;const same=[];(function w(a,b,p){for(const k in a){if(typeof a[k]==='object')w(a[k],b[k],p+k+'.');else if(a[k]===b[k]&&!['chip'].includes(k))same.push(p+k)}})(en,o,'');console.log(l,same)}"`
Expected: an empty or near-empty list per language. `card.connectedTitle` ("Borg UI Vault") may legitimately be identical. Anything else identical to English is an untranslated string: translate it.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/locales frontend/src/components/vault
git commit -m "feat(vault): locale strings in four languages and the status hook"
```

---

### Task 7: Usage meter, status banner and card

Load the `ui-ux-pro-max` skill now (see "How to work on this plan").

**Files:**
- Create: `frontend/src/components/vault/VaultUsageMeter.tsx`, `VaultStatusBanner.tsx`, `VaultCard.tsx`, a `.stories.tsx` for each, and `__tests__/VaultCard.test.tsx`

**Interfaces:**
- `VaultUsageMeter({ usedBytes, quotaBytes, checkedAt }: { usedBytes: number; quotaBytes: number; checkedAt?: string | null })`: a `LinearProgress` (determinate, height 6, rounded) with an `aria-label` equal to the usage sentence, the sentence `vault.card.usage` below it, and `vault.card.usageChecked` as a caption when `checkedAt` is given (relative time through the existing date helpers in `frontend/src/utils/dateUtils`). Colour: `primary` below 90%, `warning` from 90%, `error` at 100%.
- `VaultStatusBanner({ state, vault, onUpdatePayment, busy }: { state: VaultCardState; vault: Vault; onUpdatePayment: () => void; busy?: boolean })`: renders nothing for `ready` and `connected`. Otherwise an MUI `Alert` with `variant="outlined"` (full outline, light tint, no left accent border), `severity` `warning` for `past_due`, `full`, `ending`; `error` for `read_only`; `info` for `deleted`. Title and body from the `vault.banner.*` keys with dates formatted in the app's locale. An "Update payment" action button for `past_due` and `read_only` only.
- `VaultCard({ response, state, onConnect, onAddRepository, onUpdatePayment, onReleaseSpace, onCancelRelease, busyAction }: { response: VaultStatusResponse; state: VaultCardState; onConnect: () => void; onAddRepository: () => void; onUpdatePayment: () => void; onReleaseSpace: () => void; onCancelRelease: () => void; busyAction?: 'portal' | 'release' | null })`: presentational only, no data fetching.

Card layout (one MUI `Paper` with `variant="outlined"`, matching the Repositories page's cards):

- Header row: a lucide `CloudCog` or `Vault` icon in a `TintedTile` (`components/shared/TintedTile.tsx`), the title, and on the right the primary action.
- `ready`: title `readyTitle`, body `readyBody` with the tier size, primary button `connect`.
- Every other state except `deleted`: title `connectedTitle`, a secondary line `renews` (or `ends` when `cancel_at` is set), the `VaultUsageMeter`, then a row of text buttons: `addRepository`, and `releaseSpace` (hidden for `read_only`). When `response.vault.release` is `scheduled`: the text `releaseScheduled` and a `cancelRelease` button instead of `releaseSpace`. When it is `running`: the text `releaseRunning`.
- The `VaultStatusBanner` sits inside the card, under the header.
- `deleted`: only the banner.
- Responsive: the header stacks on `xs` (`direction={{ xs: 'column', sm: 'row' }}`), buttons become full width on `xs`, touch targets at least 44 px high.

- [ ] **Step 1: Write the failing component test**

`__tests__/VaultCard.test.tsx`, rendering with the i18n test setup other component tests use (see `frontend/src/components/__tests__/LicensingTab.test.tsx` for the render helper):

| Test name | Assert |
|---|---|
| `ready state offers Connect and no meter` | button "Connect Vault" present and calls `onConnect`; no `progressbar` role |
| `connected state shows usage and actions` | text "312 GB of 1 TB used"; `progressbar` with `aria-valuenow` 31; buttons "Add a repository" and "Release space" |
| `past due shows the banner with the read-only date and Update payment` | alert contains "We could not renew your Vault"; "Update payment" calls `onUpdatePayment` |
| `read-only hides Release space and shows the deletion date` | alert "Your Vault is read-only" containing the formatted `delete_at`; no "Release space" button |
| `full shows the full banner` | alert "Your Vault is full"; `aria-valuenow` 100 |
| `a scheduled release shows its date and a cancel button` | "Cancel release" calls `onCancelRelease`; no "Release space" button |
| `deleted shows only the banner` | alert "Your Vault was deleted"; no buttons and no `progressbar` |

- [ ] **Step 2: Run and see it fail, build the three components, run**

Run: `cd frontend && npx vitest run src/components/vault && npm run typecheck && npm run lint && npm run format:check`
Expected: all pass.

- [ ] **Step 3: Stories**

`VaultCard.stories.tsx` with one story per state: `Ready`, `Connected`, `NearlyFull` (95%), `Full`, `PastDue`, `ReadOnly`, `Ending`, `ReleaseScheduled`, `ReleaseRunning`, `Deleted`. `VaultUsageMeter.stories.tsx`: `Low`, `Warning`, `Full`. `VaultStatusBanner.stories.tsx`: one per non-empty state. Use the fixture from task 5's test with host `v0123456789ab.vault.example.test` (never a real host). Follow `frontend/src/components/LicensingTab.stories.tsx` for the meta and provider wrappers.

- [ ] **Step 4: Look at them**

Run: `cd frontend && fnm use 24 && npm run storybook`. Open every story in light and dark mode, at 375 px and 1280 px. Check: no left accent borders, text contrast is readable on the tinted alerts in dark mode, nothing overflows at 375 px, focus rings are visible when tabbing. Fix what is wrong before committing.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/vault
git commit -m "feat(vault): Vault card, usage meter and status banner"
```

---

### Task 8: Connect dialog

**Files:**
- Create: `frontend/src/components/vault/ConnectVaultDialog.tsx`, `ConnectVaultDialog.stories.tsx`, `__tests__/ConnectVaultDialog.test.tsx`

**Interfaces:**
- `ConnectVaultDialog({ open, onClose, onConnected, defaultName }: { open: boolean; onClose: () => void; onConnected: () => void; defaultName: string })`.
- Consumes `vaultAPI.connect()`, the existing `repositoriesAPI.createRepository(data)` in `services/api.ts` (line 1066 on 2026-11-11), `repoSlug`.

Behaviour:

1. Stage `form`: three fields (name, passphrase, repeat passphrase, both passphrase fields `type="password"` with `autoComplete="new-password"`), the `passphraseHelp` text with a lock icon, buttons Cancel and Connect. Validation on submit, each error under its field: empty name (`nameRequired`), passphrase shorter than 8 characters (`passphraseTooShort`), mismatch (`passphraseMismatch`). Nothing is sent while validation fails.
2. Stage `working`: the two step lines (`stepConnecting`, `stepCreating`) with a spinner on the current one and a check on the finished one. The dialog cannot be closed in this stage.
3. Call `vaultAPI.connect()`. On failure go back to `form` with an error `Alert` (`vault.connect.failed`, message from `error.response.data.detail.error.message`, falling back to `error.message`).
4. Then `repositoriesAPI.createRepository` with exactly:

```ts
{
  name: name.trim(),
  borg_version: 1,
  path: `${connect.base_path}/${repoSlug(name)}`,
  encryption: 'repokey',
  compression: 'lz4',
  passphrase,
  connection_id: connect.connection_id,
  mode: 'full',
  executor_type: 'server',
  execution_target: 'ssh',
  storage_backend: 'ssh',
}
```

   Before relying on `storage_backend: 'ssh'`, open `frontend/src/components/RepositoryWizard.tsx`, find where `storageBackend` is assigned for an SSH repository location (it feeds `storage_backend:` near line 1046), and use the same literal. On failure go back to `form` with `vault.connect.createFailed` and the server message. The connection already exists; a second submit calls `connect` again (which is idempotent) and retries the creation.
5. Stage `done`: `doneTitle`, `doneBody`, a primary button `openPlans` that navigates to the Backup Plans route (find the path of `BackupPlans` in `frontend/src/App.tsx`) and a `close` button. Entering this stage calls `onConnected()` and invalidates the React Query keys `['vault']` and the repositories list key the Repositories page uses (find it in `frontend/src/pages/Repositories.tsx`).
6. Passphrase state is cleared when the dialog closes.

Use `ResponsiveDialog` and model the layout on the release dialog inside `LicenseSeatsCard.tsx`.

- [ ] **Step 1: Write the failing tests**

Mock `../../../services/api` (`vaultAPI.connect`, `repositoriesAPI.createRepository`) and `react-router-dom`'s `useNavigate`.

| Test name | Assert |
|---|---|
| `refuses an empty name, a short passphrase and a mismatch before sending anything` | three separate submits show the three messages; `vaultAPI.connect` never called |
| `connects, then creates the repository with the vault path` | fill "Vault Home Server", passphrase "correct horse" twice, submit; `connect` called once; `createRepository` called once with `path: "/srv/vault/v0123456789ab/vault-home-server"`, `connection_id: 7`, `borg_version: 1`, `encryption: "repokey"`, `passphrase: "correct horse"`; the done title appears; `onConnected` called |
| `a connect failure returns to the form with the server message` | `connect` rejects with `{ response: { data: { detail: { error: { message: "Connection refused" } } } } }`; alert contains "Connection refused"; the name field still holds the typed value; `createRepository` not called |
| `a create failure says the vault is connected and allows a retry` | `createRepository` rejects once with `{ response: { data: { detail: { key: 'backend.errors.repo.repositoryNameExists' } } } }`, then resolves; first submit shows the `createFailed` text including the English text of that key from `en.json` (so the message goes through `translateBackendKey(getApiErrorDetail(error))`, as the other repository forms do); second submit reaches the done stage; `connect` was called twice, `createRepository` twice |
| `the done stage links to backup plans` | clicking "Open backup plans" calls `navigate` with the Backup Plans path |
| `closing clears the passphrase` | close and reopen: both passphrase fields are empty |

- [ ] **Step 2: Run and see them fail, build the dialog, run**

Run: `cd frontend && npx vitest run src/components/vault && npm run typecheck && npm run lint && npm run format:check`
Expected: all pass.

- [ ] **Step 3: Stories and visual check**

Stories: `Form`, `ValidationErrors`, `Working`, `ConnectFailed`, `Done`. To show the later stages, give the component an optional `initialStage` prop used only by stories and tests. Check in Storybook, light and dark, 375 px (the dialog must go full screen on small screens, which `ResponsiveDialog` does) and 1280 px.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/vault
git commit -m "feat(vault): one-screen Connect Vault dialog"
```

---

### Task 9: Mount on the Repositories page

**Files:**
- Modify: `frontend/src/pages/Repositories.tsx`, `frontend/src/pages/repositories-page/RepositoryGroups.tsx` (and its `.stories.tsx`), `frontend/src/pages/__tests__/` (the existing Repositories page test, or a new `RepositoriesVault.test.tsx`)
- Create: `frontend/src/components/vault/ReleaseSpaceDialog.tsx` (+ story)

**Interfaces:**
- `ReleaseSpaceDialog({ open, onClose, onConfirm, busy })`: `ResponsiveDialog` with `vault.release.title`, the `body` and `delay` paragraphs, buttons Cancel and `vault.release.confirm`.
- `RepositoryGroups` gains an optional prop `vaultPathPrefix?: string`. A repository whose `path` starts with it shows a small `Chip` labelled `t('vault.chip')` with `tintChipSx(theme, 'info')` next to its name. Find where the repository name is rendered (in `RepositoryGroups.tsx` or the row or card component it uses) and pass the prop down to that component.

In `Repositories.tsx`:

- `const vault = useVault(canManageRepositoriesGlobally)`.
- Between `<RepositoriesHeader .../>` and `<RepositoryGroups .../>`: when `vault.state` is not null, `<VaultCard .../>` with a bottom margin matching the page's section spacing.
- `onConnect` and `onAddRepository` both open `ConnectVaultDialog` (adding a repository to a connected Vault is the same flow: connect is idempotent and a new repository is created). `defaultName`: `vault-` plus the slug of the hostname from `useSystemInfo()` if it exposes one, otherwise `"vault-backup"`; for a second repository append `-2`, `-3` using `repository_count + 1`.
- `onUpdatePayment`: put the logic in `frontend/src/components/vault/openPaymentPage.ts` as `export async function openPaymentPage(getUrl: () => Promise<string>): Promise<void>` and call it with `() => vaultAPI.portal().then((r) => r.data.url)` (use the real shape of the `portal` response). Rules:
  - Open the tab inside the click, before the request, because a browser blocks `window.open` once the click's activation has expired: `const tab = window.open('', '_blank')`. Do not pass `noopener` or `noreferrer` there: the call would return `null` and the tab could not be pointed at the URL.
  - Keep what those two flags gave. Right after opening: `tab.opener = null`, and add `<meta name="referrer" content="no-referrer">` to `tab.document.head` (`createElement` plus `appendChild`), so the navigation sends no `Referer` with the address of this Borg UI.
  - `const url = await getUrl()`. With a tab: `tab.location.href = url`. Without one (popup blocked): navigate this tab without a referrer through a temporary link, `const a = document.createElement('a'); a.href = url; a.rel = 'noreferrer'; a.click()`.
  - When `getUrl` rejects: `tab?.close()` and rethrow. The caller shows `toast.error(t('vault.portalFailed', { message }))`.
- `onReleaseSpace` opens `ReleaseSpaceDialog`; confirm calls `vaultAPI.release()`, toasts `scheduledToast`, refetches. `onCancelRelease` calls `vaultAPI.cancelRelease()`, toasts `cancelledToast`, refetches.
- Pass `vaultPathPrefix(vault.data.vault)` to `RepositoryGroups` when there is a vault.

- [ ] **Step 1: Write the failing page test**

Mock `vaultAPI.status`. Follow the setup of the existing Repositories page tests for the other API mocks.

| Test name | Assert |
|---|---|
| `shows no vault card when the licence has no vault` | status resolves `vault: null`; no text "Borg UI Vault" and no "Connect Vault" button; the page's normal header is present |
| `shows no vault card when the status request fails` | status rejects; same assertions; no error toast |
| `shows the ready card and opens the connect dialog` | status resolves a vault with `connection_id: null`; "Your Vault is ready" visible; clicking "Connect Vault" shows the dialog title |
| `non-admins never request the vault status` | render with a user lacking `repositories.manage_all`; `vaultAPI.status` not called |
| `vault repositories carry the Vault chip` | a repository whose path starts with the prefix shows "Vault"; another repository does not |
| `update payment opens the tab inside the click` | Arrange: past due vault; `window.open` mocked to return `{ opener: {}, location: { href: '' }, close: vi.fn(), document: document.implementation.createHTMLDocument('') }`; click "Update payment". Assert: `window.open` was called with `('', '_blank')` before `vaultAPI.portal` resolved; afterwards the fake tab's `location.href` is the portal URL, its `opener` is `null`, and its document has `meta[name="referrer"]` with content `no-referrer` |
| `update payment falls back to this tab when the popup is blocked` | Arrange: `window.open` returns `null`; `HTMLAnchorElement.prototype.click` spied. Assert: the spy ran once on a link whose `href` is the portal URL and whose `rel` is `noreferrer` |
| `a failed portal request closes the empty tab` | Arrange: `vaultAPI.portal` rejects. Assert: the fake tab's `close` was called and an error toast is shown |

- [ ] **Step 2: Run and see it fail, wire it up, run the whole frontend suite**

Run: `cd frontend && npx vitest run && npm run typecheck && npm run lint && npm run format:check && npm run check:locales`
Expected: everything passes, including tests that existed before.

- [ ] **Step 3: Stories**

Add a `WithVaultChip` story to `RepositoryGroups.stories.tsx` and a story for `ReleaseSpaceDialog`. Check both in Storybook, light and dark.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages frontend/src/components/vault
git commit -m "feat(vault): Vault card on the Repositories page"
```

---

### Task 10: User documentation

**Files:**
- Create: `docs/vault.md`
- Modify: `docs/.vitepress/config.mts` (add `{ text: 'Borg UI Vault', link: '/vault' }` directly after the `Licensing` entry at line 63)

`docs/vault.md` sections, plain language, no em dash:

1. **What Vault is.** Two sentences. Closed beta, by invite.
2. **Connect your Vault.** Activate the licence key (link to `/licensing`), open Repositories, choose Connect Vault, pick a name and a passphrase. State plainly that the passphrase cannot be recovered and how to export the key (link to the existing repository key export doc if there is one; search `docs/` for "keyfile").
3. **Add it to a backup plan.**
4. **How much space is used.** The meter is measured hourly on the Vault, so it can lag a backup by up to an hour.
5. **Why pruning does not free space, and Release space.** Append-only in two sentences, then the 7 day delay and the cancel link.
6. **If a payment fails.** The timeline from spec section 3, D4, as a short table: day 0, day 14, day 44, with what works at each point.
7. **Restore without Borg UI.** The exact command: `borg list ssh://<username>@<username>.vault.borgui.com/srv/vault/<username>/<repository>` and that any Borg 1.2 or newer works, with the same SSH key.
8. **Limits of the beta.** One copy in one EU data centre, Borg 1 repositories only, sizes 250 GB and 1 TB, size changes by email.

- [ ] **Step 1: Write the page and the sidebar entry.**
- [ ] **Step 2: Build the docs.** Run: `cd docs && npm ci && npm run docs:build 2>&1 | tail -3` (use the script name in `docs/package.json` if it differs). Expected: build succeeds with no dead-link error.
- [ ] **Step 3: Commit.**

```bash
git add docs/vault.md docs/.vitepress/config.mts
git commit -m "docs: Borg UI Vault user guide"
```

---

### Task 11: Final verification and pull request

- [ ] **Step 1: Backend.** Run: `ruff check app tests && ruff format --check app tests && pytest tests/unit/test_vault_service.py tests/unit/test_api_vault.py tests/unit/test_ssh_connection_vault_id_migration.py tests/unit/test_route_access_registry.py tests/unit/test_api_ssh_keys.py tests/unit/test_licensing_service.py -q 2>&1 | tail -3`. Expected: all pass.
- [ ] **Step 2: Frontend.** Run: `cd frontend && npx vitest run 2>&1 | tail -5 && npm run typecheck && npm run lint && npm run format:check && npm run check:locales && npm run build 2>&1 | tail -2`. Expected: all pass.
- [ ] **Step 3: Guards.** Run: `bash scripts/check-no-personal-paths.sh && grep -rn "—" app/services/vault_service.py app/api/vault.py frontend/src/components/vault docs/vault.md; echo "em dash grep exit=$?"`. Expected: the guard passes and the grep prints nothing (`exit=1`). Also search the four locale files' `vault` sections for an em dash and for `!`.
- [ ] **Step 4: Visual proof.** `fnm use 24`, `npm run snapshots` in `frontend/`, open the generated screenshots for every `vault` story in light and dark. Do not commit them.
- [ ] **Step 5: Local review loop.** Run the project skill `prep-pr`: CodeRabbit reviews the branch locally, you fix the findings that are real, and you run it again until it reports nothing. Agents without that skill: read your own full diff once (`git diff origin/main...HEAD`) looking for unused code, missing error handling at the three network calls, and strings not in the locale files.
- [ ] **Step 6: Pull request.**

```bash
git push -u origin feat/vault-app
gh pr create --title "feat: Borg UI Vault card and Connect Vault" --body "Implements docs/engineering/plans/2026-11-11-borg-ui-vault-app.md (spec: docs/engineering/specs/2026-11-11-borg-ui-vault-beta.md). The card only appears for installs whose licence owns a Vault. Backend and frontend tests, lint, typecheck and locale parity pass. Gate C (a real install against the real node) is still open."
```

After the PR is open, use the `ccd_pr` tools to bind it and read CI if you are running in the Claude desktop app. Do not enable auto-merge. Do not cut a release.

---

### Gate C: a real install against the real node (owner plus one engineer session)

Needs plan 1 deployed (Gate A passed) and plan 2 deployed with sandbox prices (Gate B passed).

- [ ] Run this branch locally with `ACTIVATION_SERVICE_URL` pointing at the sandbox Worker. Use a fresh database, never a copy of a live one: a copied database carries notification, MQTT and schedule settings that fire for real.
- [ ] Buy a 250 GB Vault with Lite through the sandbox checkout, activate the licence key in the app, open Repositories: the card says "Your Vault is ready".
- [ ] Connect. Expected: under two minutes, no manual SSH step, the repository appears with the Vault chip, and the Remote Machines page shows the connection as connected with a verified host key.
- [ ] Run a backup of a small folder to the Vault repository, then a restore of one file. Both succeed.
- [ ] Make the Vault full without uploading 250 GB: lower its limit on the node to 1 GiB (`PUT /v1/accounts/<username>` with `quota_bytes: 1073741824`, `frozen: false` and the account's current key list, using the node token), then back up a folder larger than 1 GB. Put the real limit back afterwards with the admin "Sync" button. Expected: the backup fails, the job log shows "Disk quota exceeded", and within an hour the card shows "Your Vault is full". Note what the failed backup job looks like in the Activity page; if the message is not clear to a normal user, open a follow-up issue with a screenshot (do not fix it inside this gate).
- [ ] In the Paddle simulator send `subscription.past_due`, wait for the next cron or call the admin sync: the card shows the past due banner with a date. Open "Update payment": the Paddle page opens.
- [ ] Check that the payment page gets no `Referer` from Borg UI, which unit tests cannot prove. Use a request inspector that is served over HTTPS and shows request headers (a browser drops the referrer by itself when an HTTPS page links to plain HTTP, which would make this check pass for the wrong reason). First the control: from the running app, follow a plain `<a href="<inspector url>" target="_blank">` without `rel` (add it in devtools) and confirm the inspector does show a `Referer` with the app's origin. If it shows none, the inspector cannot detect a leak; pick another. Then temporarily make `openPaymentPage` receive the inspector URL, click "Update payment" once normally and once with popups blocked for the site, and confirm that neither request carries a `Referer` header. Undo the temporary change.
- [ ] Prune an archive, click "Release space": the card shows the scheduled date and the email arrives with a working cancel link.
- [ ] Use the skill `borg-live-debug` if a Borg command fails and you need to see its real output inside the container.
- [ ] Tell the owner exactly which steps passed, with the terminal or screen output for each. The owner decides when the first real invite goes out.
