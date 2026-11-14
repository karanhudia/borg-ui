# MCP phase 1: foundation and read tools. Implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> with superpowers:test-driven-development for every task (spec 8.2). Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Pro install answers MCP clients at `/mcp` with 36 read-only
tools, under per-connection access levels, with token isolation, an
activity log and friendly copy.

**Architecture:** A new package `app/mcp/` holds a lowlevel MCP `Server`
(official SDK, stateless Streamable HTTP) registered as one route on the
existing FastAPI app. Tools are hand-written and call the app's own REST
routes in-process through `httpx.ASGITransport`, authenticated as the
connection's user by a short-lived internal credential. The MCP layer adds
only level checks, name resolution, copy, output limits and redaction.

**Tech stack:** Python 3.12, FastAPI 0.162, `mcp==2.3.0` (adds
`mcp-types`, `sse-starlette`, `pyjwt`, `jsonschema`; resolves cleanly
against `requirements.txt`, checked 2026-11-14), httpx 0.28.1, SQLAlchemy,
Alembic, pytest.

**Spec:** `docs/engineering/specs/2026-11-14-mcp-server.md`. Sections 5.1
to 5.4, 5.5 (read tools), 5.7, 5.8, 5.11, 5.14. Read it in full first.

## Global Constraints

- No em dashes anywhere: code comments, copy, tests, docs.
- No Borg 2 branching in existing v1 files. Borg 1/2 routing lives only in
  `app/mcp/borg_routes.py`.
- Existing files this phase may edit: `requirements.txt`,
  `app/core/features.py`, `app/core/security.py`, `app/database/models.py`,
  `app/api/tokens.py`, `app/main.py`, `frontend/src/core/features.ts` and
  its test, the four `frontend/src/locales/*.json`, `docs/api.md`. Nothing
  else outside `app/mcp/`, `app/api/mcp_connections.py`, the migration,
  `scripts/` and `tests/`.
- No version bump. No commits or pushes before gate G2 (one commit at G2).
- Recompute alembic heads against a freshly fetched `origin/main` right
  before writing the migration, and again before G2.
- Numbers from the spec: list default 25, max 200; log default 200 lines,
  max 1000; result cap 60,000 characters; rate limit 120 tool calls per
  60 s per connection; activity retention 30 days or 20,000 rows; internal
  credential lifetime 60 s; `wait_for_job` blocks at most 45 s.
- Levels: `read` < `operate` < `manage` < `full`. Only `read` tools exist
  after this phase.
- MCP state shared between calls lives in the database (two gunicorn
  workers). The one exception is the auth cache in Task 4, which re-checks
  the row on every hit.
- Tests run in the dev container or the worktree venv per
  `tests/README.md`. The 14 `test_api_auth` OIDC failures in a checkout
  with a local `.env` are known and unrelated.
- A local backend for manual checks uses a fresh `DATA_DIR`, never a copy
  of live data with notifications or schedules in it.

## Facts verified while planning (do not rediscover)

- SDK 2.3.0 lowlevel API: `Server(name, version=, title=, instructions=,
  icons=, on_list_tools=, on_call_tool=)`. Handlers are
  `async (ctx: ServerRequestContext, params) -> types.ListToolsResult |
  types.CallToolResult`. `ctx.request` is the Starlette request, so
  `ctx.request.scope[...]` carries anything the ASGI wrapper put there.
- `StreamableHTTPSessionManager(app=server, stateless=True,
  json_response=True)`; `await manager.handle_request(scope, receive,
  send)`; `async with manager.run():` must be open for the app's lifetime.
- Model field names are snake_case in Python (`input_schema`,
  `structured_content`, `is_error`, `read_only_hint`) and serialize to the
  camelCase wire names.
- A plain `starlette.routing.Route("/mcp", endpoint=<ASGI object>)` added
  to `app.router.routes` works; initialize, tools/list and tools/call
  round-trip through `httpx.ASGITransport`.
- `GET /mcp` in stateless mode opens a stream that never ends. The
  endpoint must answer GET and DELETE itself with 405.
- The app uses `@app.on_event("startup")` / `("shutdown")`, not a lifespan.
- Auth modes in `_authenticate_user` (`app/core/security.py`): insecure
  no-auth, proxy auth (`settings.disable_authentication`, ignores Bearer
  tokens), then Bearer JWT or `borgui_` token. `verify_token` accepts only
  JWTs whose `purpose` is absent or `access`.
- Tests set the plan with
  `monkeypatch.setattr("app.core.features.get_effective_plan_value", lambda _db: "pro")`.
- Every new alembic revision needs a claiming test module under
  `tests/migrations/` using the `upgraded_from` fixture
  (`tests/migrations/test_revisions_have_tests.py`).
- `test_client` shares one DB session across requests; use the
  `session_per_request` fixture for tests that nest an in-process call
  inside an MCP call.

## Review Focus

1. A connection is revoked, or its user deactivated, while a client is
   connected: the very next call is refused. Test in Task 4.
2. The plan lapses or an admin turns MCP off mid-conversation: tool calls
   answer with a friendly `is_error` sentence, never a crash or a bare 403.
   Test in Task 4.
3. Two repositories with similar names ("Photos", "Photos old"): the tool
   asks which one, it never guesses. Test in Task 6.
4. A directory with 100,000 entries or a 50 MB log: the answer is paged,
   stays under the cap and says what was left out and how to get more.
   Tests in Tasks 5 and 9.
5. A REST route returns a 500 or a shape the tool did not expect: friendly
   generic error, activity row `error`, no stack trace, no secret. Test in
   Task 5.

---

## File structure

| File | Responsibility |
|---|---|
| `app/mcp/__init__.py` | Empty. |
| `app/mcp/levels.py` | `Level` enum, parsing, effective level. |
| `app/mcp/registry.py` | `ToolSpec`, `tool` decorator, `REGISTRY`. |
| `app/mcp/context.py` | `ConnectionContext`, `ToolContext`. |
| `app/mcp/db.py` | `session_scope(app)`. |
| `app/mcp/auth.py` | MCP token authentication, cache. |
| `app/mcp/client.py` | `InternalClient`, `ApiError`. |
| `app/mcp/borg_routes.py` | Borg 1/2 read route selection. |
| `app/mcp/resolve.py` | Names to objects, `Ambiguous`, `NotFound`. |
| `app/mcp/render.py` | `ToolResult`, formatting, paging, cap, `finish`. |
| `app/mcp/redact.py` | `scrub(data)`. |
| `app/mcp/errors.py` | `render_error`, backend strings lookup. |
| `app/mcp/backend_strings.json` | Generated from `en.json` `backend`. |
| `app/mcp/activity.py` | `record`, `recent_calls`, pruning. |
| `app/mcp/server.py` | `Server`, handlers, `McpEndpoint`, `mount(app)`. |
| `app/mcp/STYLE.md` | Voice guide (text in Task 5). |
| `app/mcp/tools/{overview,repositories,archives,jobs,plans,connections}.py` | Tools. |
| `app/api/mcp_connections.py` | REST for connections, config, activity. |
| `scripts/extract_backend_strings.py` | Writes `backend_strings.json`. |
| `tests/unit/mcp/` | `conftest.py` plus one test module per task. |

---

### Task 1: Feature key, columns, activity table

**Files:**
- Modify: `app/core/features.py`, `frontend/src/core/features.ts`,
  `frontend/src/core/__tests__/features.test.ts`, `app/database/models.py`
- Create: `app/database/alembic/versions/<rev>_add_mcp.py`,
  `tests/migrations/test_mcp_after_upgrade.py`,
  `tests/unit/mcp/test_schema.py`

**Interfaces, produces:**
- `FEATURES["mcp"] == Plan.PRO`; frontend `FEATURES.mcp === 'pro'`.
- `ApiToken.kind: str` (`"api"` default, not null, server default `api`),
  `.access_level: str | None`, `.skip_routine_confirmations: bool`
  (default false), `.last_client_name: str | None`,
  `.last_client_version: str | None`.
- `SystemSettings.mcp_enabled: bool` (default true),
  `.mcp_max_access_level: str` (default `"full"`).
- `McpActivity` (`mcp_activity`): `id`, `connection_id` (FK
  `api_tokens.id`, `ON DELETE SET NULL`, nullable), `connection_name`,
  `user_id` (FK `users.id`, `ON DELETE CASCADE`), `tool`,
  `effective_level`, `outcome`, `error_key` (nullable), `target`
  (nullable, max 200), `duration_ms`, `created_at` (indexed with
  `connection_id`).

Activity keeps the connection's name and survives revocation (`SET NULL`),
so a revoked connection's history is still there to inspect. This refines
spec 5.11.

- [ ] **Step 1:** Write failing tests: `test_core_features` gains
  `assert FEATURES["mcp"] == Plan.PRO`; `features.test.ts` gains the
  mirror assertion; `test_schema.py` asserts an existing `ApiToken` row
  reads `kind == "api"`, `SystemSettings` defaults are `True` and
  `"full"`, and deleting a token leaves its `McpActivity` rows with
  `connection_id is None` and `connection_name` intact.
- [ ] **Step 2:** Run them, expect failures on the missing key and columns.
- [ ] **Step 3:** Add the feature key in both files, the model columns and
  `McpActivity`.
- [ ] **Step 4:** `git fetch origin main`, compute heads, write one
  revision (batch mode for SQLite as the neighbouring revisions do) with a
  working downgrade.
- [ ] **Step 5:** Write `tests/migrations/test_mcp_after_upgrade.py`
  declaring `REVISION = "<rev>"`: with `upgraded_from`, a pre-existing
  token row comes out `kind == "api"`, `access_level is None`, and a
  pre-existing `system_settings` row comes out enabled with `full`.
- [ ] **Step 6:** Run `pytest tests/unit/test_core_features.py
  tests/unit/mcp/test_schema.py tests/migrations -q` and
  `cd frontend && npx vitest run src/core`. Expect all green.

### Task 2: Token isolation and the connections REST API

**Files:**
- Modify: `app/core/security.py` (`_resolve_api_token_user`),
  `app/api/tokens.py`, `app/main.py` (include router), the four locale
  files, `docs/api.md`
- Create: `app/api/mcp_connections.py`, `app/mcp/levels.py`,
  `tests/unit/mcp/test_token_isolation.py`,
  `tests/unit/mcp/test_connections_api.py`

**Interfaces, produces:**
- `app/mcp/levels.py`: `class Level(IntEnum)` with `READ=0, OPERATE=1,
  MANAGE=2, FULL=3`; `Level.parse(value: str) -> Level` (raises
  `ValueError`); `Level.label -> str` (`"read"` ...);
  `effective_level(connection_level: str, cap: str) -> Level` (the lower).
- `refuse_mcp_internal(request: Request) -> None` in `app/core/security.py`:
  raises 403 `backend.errors.auth.notAvailableOverMcp` when
  `request.state.mcp_connection_id` is set (set in Task 3).
- Routes, router prefix `/api/settings/mcp`, all with
  `require_feature("mcp")` and `Depends(refuse_mcp_internal)`:

| Route | Who | Body / result |
|---|---|---|
| `GET /config` | any user | `{enabled, max_access_level, endpoint_path}` (`endpoint_path` is `{BASE_PATH}/mcp`) |
| `PUT /config` | admin | `{enabled?, max_access_level?}` |
| `GET /connections` | any user; `?all=true` admin only | list: `id, name, prefix, access_level, effective_level, skip_routine_confirmations, last_client_name, last_client_version, last_used_at, created_at, username` |
| `POST /connections` | any user | `{name, access_level, skip_routine_confirmations=false}` → 201 with the row plus `token` (once) |
| `PATCH /connections/{id}` | owner or admin | `{name?, access_level?, skip_routine_confirmations?}` |
| `DELETE /connections/{id}` | owner or admin | 204 |
| `GET /connections/{id}/activity` | owner or admin | `?limit=50&before=<iso>`; rows of `McpActivity` |

Rules: tokens are minted exactly like personal tokens (`"borgui_" +
secrets.token_urlsafe(32)`, bcrypt, 12-char prefix) with `kind="mcp"`. A
level above the admin cap is 422 `backend.errors.mcp.levelAboveCap`.
`skip_routine_confirmations=true` with a level below `full` is 422
`backend.errors.mcp.skipNeedsFull`. Blank name is 422
`backend.errors.tokens.nameRequired` (existing key).

- [ ] **Step 1:** Write failing isolation tests:
  - an MCP connection's token on `GET /api/repositories/` (both
    `Authorization` and `X-Borg-Authorization`) is 401 with
    `detail.key == "backend.errors.auth.mcpTokenNotForApi"`;
  - `GET /api/settings/tokens` does not list MCP connections, and
    `DELETE /api/settings/tokens/{id}` on one is 404;
  - an existing personal token still works on REST.
- [ ] **Step 2:** Write failing API tests: create returns the token once
  and it starts with `borgui_`; list never returns `token` or
  `token_hash`; Community plan gets 403 `featureNotAvailable` with
  `feature == "mcp"`; a viewer cannot `PUT /config`; a user cannot read,
  patch or delete another user's connection (404) but an admin can; cap
  and skip rules above; lowering the cap changes `effective_level` in the
  list without changing `access_level`.
- [ ] **Step 3:** Run, expect failures.
- [ ] **Step 4:** In `_resolve_api_token_user`, when the bcrypt match is a
  `kind == "mcp"` row, raise the 401 above before stamping or loading the
  user. Filter `tokens.py` list and delete to `kind == "api"`.
- [ ] **Step 5:** Implement `levels.py`, `refuse_mcp_internal`, the router;
  include it in `main.py` next to `tokens.router`. Add
  `Depends(refuse_mcp_internal)` to the `tokens` router too.
- [ ] **Step 6:** Add the four new error keys in all four locales
  (`backend.errors.auth.mcpTokenNotForApi`,
  `backend.errors.auth.notAvailableOverMcp`,
  `backend.errors.mcp.levelAboveCap`, `backend.errors.mcp.skipNeedsFull`).
  English: "This token is for MCP clients and cannot be used
  with the API.", "This action is not available to MCP connections.",
  "Your administrator allows MCP connections up to {{max}} access.",
  "Skipping confirmations needs Full access."
- [ ] **Step 7:** Document the routes in `docs/api.md`.
- [ ] **Step 8:** Run the two test modules, `tests/unit/test_api_tokens.py`
  and `cd frontend && npm run check:locales`. Expect green.

### Task 3: Internal credential and in-process client

**Files:**
- Modify: `app/core/security.py`
- Create: `app/mcp/client.py`, `app/mcp/db.py`,
  `tests/unit/mcp/test_internal_credential.py`,
  `tests/unit/mcp/test_client.py`

**Interfaces, produces:**
- `MCP_INTERNAL_HEADER = "X-Borg-MCP-Internal"`.
- `create_mcp_internal_token(user_id: int, connection_id: int) -> str`:
  JWT signed with `settings.secret_key`, claims `sub` (user id as string),
  `conn`, `purpose: "mcp_internal"`, `exp` now + 60 s.
- `_authenticate_user` checks the header first, before the insecure and
  proxy branches. A valid credential loads that user by id, requires
  `is_active` and that an `ApiToken` row `id == conn, kind == "mcp",
  user_id == sub` still exists, sets
  `request.state.mcp_connection_id = conn`, and returns the user. An
  invalid or expired one is 401; it never falls through to another mode.
- `app/mcp/db.py`: `session_scope(app) -> ContextManager[Session]`, which
  resolves `app.dependency_overrides.get(get_db, get_db)` so tests'
  overrides apply, commits on exit, rolls back on error, always closes.
- `app/mcp/client.py`:

```python
class ApiError(Exception):
    status: int
    key: str | None      # detail.key when the backend gave one
    params: dict         # the rest of detail when it is a dict
    message: str | None  # detail when it is a plain string

class InternalClient:
    def __init__(self, app, *, user_id: int, connection_id: int): ...
    async def get(self, path: str, **params) -> Any: ...
    async def request(self, method: str, path: str, *, params=None, json=None) -> Any: ...
```

  One `httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
  base_url="http://borg-ui.internal")` per tool call, a fresh credential
  per request, paths without `BASE_PATH`, 2xx returns parsed JSON (or
  `None` for 204), anything else raises `ApiError`. `None` params are
  dropped.

- [ ] **Step 1:** Write failing credential tests, each calling
  `GET /api/settings/profile` with only the internal header:
  - normal mode: answers as the connection's user;
  - `settings.disable_authentication = True` with no proxy header: same;
  - `settings.allow_insecure_no_auth = True` and a viewer's connection:
    answers as the viewer, not admin;
  - expired, wrong signature, `purpose: "access"`, deleted connection,
    deactivated user: each 401;
  - the same JWT sent as `Authorization: Bearer` is 401;
  - with a valid credential, `GET /api/settings/tokens` and
    `GET /api/settings/mcp/connections` are 403 `notAvailableOverMcp`.
- [ ] **Step 2:** Write failing client tests (with `session_per_request`):
  `get("/api/repositories/")` returns the list; a 404 raises `ApiError`
  with `status == 404`; a route that answers
  `{"detail": {"key": "backend.errors.plan.featureNotAvailable", ...}}`
  yields `key` and `params["required"]`; with `BASE_PATH=/borg` an
  unprefixed path still resolves.
- [ ] **Step 3:** Run, expect failures.
- [ ] **Step 4:** Implement the three pieces.
- [ ] **Step 5:** Run both modules plus `tests/unit -k "auth or security"
  -q`. Expect green (bar the known OIDC `.env` failures locally).

### Task 4: Server core: registry, endpoint, auth, gating, level filter

**Files:**
- Modify: `requirements.txt` (`mcp==2.3.0`), `app/main.py`
- Create: `app/mcp/registry.py`, `app/mcp/context.py`, `app/mcp/auth.py`,
  `app/mcp/server.py`, `tests/unit/mcp/conftest.py`,
  `tests/unit/mcp/test_endpoint.py`, `tests/unit/mcp/test_registry.py`

**Interfaces, produces:**

```python
# registry.py
@dataclass(frozen=True)
class ToolSpec:
    name: str; title: str; description: str
    level: Level
    routes: tuple[str, ...]        # "GET /api/dashboard/overview"
    input_model: type[BaseModel]
    handler: Callable[[ToolContext, BaseModel], Awaitable[ToolResult]]
    read_only: bool = True; destructive: bool = False; idempotent: bool = True
REGISTRY: dict[str, ToolSpec]
def tool(*, name, title, description, level, routes, read_only=True,
         destructive=False, idempotent=True): ...   # input model = handler's 2nd annotation
def tools_for(level: Level) -> list[ToolSpec]       # level <= given, sorted by name

# context.py
@dataclass(frozen=True)
class ConnectionContext:
    connection_id: int; connection_name: str
    user_id: int; username: str
    level: Level                    # effective
@dataclass
class ToolContext:
    conn: ConnectionContext
    api: InternalClient
    target: str | None = None       # a tool sets this for the activity log

# auth.py
async def authenticate(app, token: str) -> ConnectionContext | None

# server.py
SCOPE_KEY = "borgui_mcp"            # scope[SCOPE_KEY] = ConnectionContext
def mount(app: FastAPI) -> None      # adds the route and the startup/shutdown hooks
```

Decisions:

- `authenticate` finds `kind == "mcp"` rows by prefix, bcrypt-verifies in
  a worker thread, requires an active user, stamps `last_used_at`, and
  computes the effective level from the current cap. It caches
  `sha256(token) -> connection_id` for 60 s per process to skip bcrypt,
  and on every cache hit still loads the row and user by primary key, so
  revocation and deactivation take effect on the next call.
- `McpEndpoint.__call__` (raw ASGI), in order: GET and DELETE answer 405
  with `Allow: POST`; a missing or wrong Bearer (`Authorization`, else
  `X-Borg-Authorization`) answers 401 with `WWW-Authenticate: Bearer`; an
  `Origin` header whose host differs from the `Host` header answers 403;
  the body is read once (the SDK's 4 MB limit applies; larger is 413) and,
  when it is an `initialize` request, `clientInfo.name` and `.version`
  (each cut to 100 characters) are saved on the connection; then
  `scope[SCOPE_KEY]` is set and the manager handles the request with a
  `receive` that replays the body.
- Personal API tokens and JWTs are refused at `/mcp` (401) because
  `authenticate` only matches `kind == "mcp"`.
- `on_list_tools` returns `tools_for(conn.level)` as `types.Tool` with
  `title`, `description`, `input_schema` from
  `input_model.model_json_schema()`, and annotations (`read_only_hint`,
  `destructive_hint`, `idempotent_hint`, `open_world_hint=False`).
- `on_call_tool`, in order, each failure an `is_error` result with one
  friendly sentence:
  1. feature off: "MCP access is part of Borg UI Pro. This install is on
     {plan}. An admin can upgrade under Settings > Plan."
  2. `mcp_enabled` false: "MCP access is turned off on this Borg UI. An
     administrator can turn it on under Settings > System."
  3. unknown tool, or a tool above the level: "This connection has
     {level} access, and {title} needs {needed}. You can change that under
     Settings > MCP." Activity outcome `denied_level`.
  4. rate limit (Task 7).
  5. arguments fail validation: list each field and its message, never
     the rejected value.
  6. run the handler with a fresh `InternalClient`; pass the result
     through `render.finish` (Task 5); record activity (Task 7).
  Until Tasks 5 and 7 land, step 6 returns the handler's text unchanged
  and steps 4 and the recording are no-ops behind functions those tasks
  fill in (`activity.allow`, `activity.record`, `render.finish`).
- `Server("borg-ui", version=get_runtime_app_version(), title="Borg UI",
  instructions=INSTRUCTIONS, icons=[...])`. `INSTRUCTIONS` is the text in
  Appendix 1 of this plan. The icon is the existing
  `app/static/logo.png` (or the nearest existing logo file) served by URL
  relative to the request's base; skip `icons` if no such static file
  exists.
- `mount(app)` inserts `Route("/mcp", endpoint=McpEndpoint(app),
  methods=["GET", "POST", "DELETE"])` and is called in `main.py` right
  after the last `include_router`, before the SPA catch-all is defined.
  It registers a startup hook that enters `manager.run()` on an
  `AsyncExitStack` and a shutdown hook that closes it.
- `tests/unit/mcp/conftest.py` fixtures: `pro_plan` (the monkeypatch
  above), `mcp_connection(user=..., level="read") -> (row, token)` created
  through the REST route, and `mcp(token)` returning a small helper with
  `initialize(client_name="claude-code")`, `list_tools() -> list[dict]`,
  `call(name, **args) -> dict` (`{"text", "data", "is_error"}`), each a
  JSON-RPC POST to `/mcp` with `Accept: application/json,
  text/event-stream`.

- [ ] **Step 1:** Write failing registry tests with two throwaway tools
  registered in the test (`read` and `full`): `tools_for(READ)` returns
  only the first; a duplicate name raises; the input schema is the
  model's JSON schema.
- [ ] **Step 2:** Write failing endpoint tests:
  - no token, a personal API token, and a login JWT are each 401;
  - `initialize` answers `serverInfo.name == "borg-ui"`,
    `title == "Borg UI"`, non-empty `instructions`, and afterwards the
    connection row has `last_client_name == "claude-code"`;
  - `tools/list` for a `read` connection hides the `full` throwaway tool;
    calling it by name is `is_error` with "needs full";
  - with the cap lowered to `read`, a `full` connection also loses it;
  - GET and DELETE are 405 and return at once;
  - `Origin: https://evil.example` is 403; no `Origin` passes; an `Origin`
    equal to the host passes;
  - Community plan: `tools/call` is `is_error` and mentions Pro;
    `mcp_enabled = False`: `is_error` and mentions the administrator
    (Review Focus 2);
  - after `DELETE /connections/{id}`, and separately after deactivating
    the user, the next call with the same token is 401 (Review Focus 1);
  - bad arguments: `is_error`, names the field, does not contain the
    rejected value;
  - `POST {BASE_PATH}/mcp` works when `BASE_PATH` is set;
  - `GET /mcp-settings` (any SPA path) still serves the index page.
- [ ] **Step 3:** Run, expect failures.
- [ ] **Step 4:** Add the dependency; implement registry, context, auth,
  server, `mount`; wire `main.py`.
- [ ] **Step 5:** Run `pytest tests/unit/mcp -q` and the app's startup
  test modules (`pytest tests/unit -k "main or startup" -q`). Expect green.

### Task 5: Voice, rendering, limits, redaction, errors

**Files:**
- Create: `app/mcp/render.py`, `app/mcp/redact.py`, `app/mcp/errors.py`,
  `app/mcp/STYLE.md`, `app/mcp/backend_strings.json`,
  `scripts/extract_backend_strings.py`, `tests/unit/mcp/test_render.py`,
  `tests/unit/mcp/test_redact.py`, `tests/unit/mcp/test_errors.py`

**Interfaces, produces:**

```python
# render.py
LIST_DEFAULT, LIST_MAX, LOG_DEFAULT, LOG_MAX, RESULT_CAP = 25, 200, 200, 1000, 60_000
@dataclass
class ToolResult:
    text: str                 # markdown, outcome first
    data: dict                # becomes structured_content
    is_error: bool = False
def human_size(n: int | None) -> str          # "38.2 GB", "unknown" for None
def when(dt: datetime | str | None) -> str    # "3 hours ago (2026-11-14 06:10 UTC)", "never"
def duration(seconds: float | None) -> str    # "6 min", "1 h 12 min"
def clamp_limit(limit: int | None, default=LIST_DEFAULT, max_=LIST_MAX) -> int
def page(items: list, limit: int, cursor: str | None) -> tuple[list, str | None]
def more_line(shown: int, total: int | None, noun: str, next_cursor: str | None) -> str
def finish(result: ToolResult) -> types.CallToolResult
# redact.py
def scrub(value: Any) -> Any
# errors.py
def backend_message(key: str, params: dict) -> str | None
def render_error(exc: Exception) -> ToolResult
```

Decisions:

- Cursors are opaque: URL-safe base64 of a JSON offset. A bad cursor is a
  friendly error, not a crash.
- `finish` runs `scrub` on `data` and `redact_secrets` on `text`, then
  enforces `RESULT_CAP` on the text: it cuts at the last full line and
  appends "Output was shortened to fit. Ask for a smaller page or a
  narrower path." If the JSON form of `data` exceeds the cap, list values
  are trimmed from the end until it fits and `data["truncated"] = True`.
- `scrub` walks dicts and lists. A key whose lower-cased name contains
  `passphrase`, `password`, `private_key`, `secret`, `token_hash`, or
  equals `token`, `service_url`, `webhook_url`, `key_data`, gets the value
  `"[hidden]"`. Every string value goes through
  `app.utils.redaction.redact_secrets`. Keys such as `has_passphrase`
  (booleans) are kept.
- `backend_strings.json` is the `backend` subtree of
  `frontend/src/locales/en.json`, written by the script (sorted keys). A
  test regenerates it in memory and fails with "run
  scripts/extract_backend_strings.py" when the committed file differs, so
  it cannot go stale silently. The script has a `--check` flag used by
  that test.
- `backend_message` resolves `backend.errors.x.y` in that tree and fills
  `{{name}}` placeholders from `params`; unknown key returns `None`.
- `render_error`:
  - `ApiError` with a `backend.errors.plan.*` key: "{Feature} is part of
    Borg UI {required}. This install is on {current}."
  - other keyed `ApiError`: the backend message; if unknown, "Borg UI
    refused that ({key}).";
  - 403 without a plan key: "Your account does not have permission for
    that. An admin can change your role under Settings > Users.";
  - 404: "I could not find that. It may have been removed.";
  - 5xx, unkeyed, or any other exception: "Something went wrong inside
    Borg UI while doing that. Nothing was changed. The server log has the
    details." and `report_exception(exc, kind="request",
    component="mcp:<tool>")`;
  - `resolve.Ambiguous` and `resolve.NotFound` (Task 6): their own text.
  Never a traceback, never `str(exc)` of an unexpected exception.
- `STYLE.md` holds the text in Appendix 2 of this plan.

- [ ] **Step 1:** Write failing tests:
  - `human_size(41020000000) == "38.2 GB"`, `human_size(None) ==
    "unknown"`, `duration(372) == "6 min"`, `when(None) == "never"`;
  - `page` over 60 items with limit 25 gives 25 and a cursor, the third
    page gives 10 and `None`; a garbage cursor raises the friendly error;
  - `clamp_limit(5000) == 200`, `clamp_limit(None) == 25`;
  - `finish` on 200,000 characters of text returns at most 60,000 plus
    the shortened line; on a `data` with 100,000 list items sets
    `truncated` (Review Focus 4);
  - `scrub` hides `passphrase`, `ssh_private_key`, `token`, nested inside
    lists; keeps `has_passphrase: True`; a string
    `"ssh://u:pw@host/repo"` loses the password;
  - `render_error` for each branch above; the 5xx branch output contains
    no exception text and calls `report_exception` once (Review Focus 5);
  - `backend_strings.json` is in sync; `--check` exits non-zero on a
    doctored copy.
- [ ] **Step 2:** Run, expect failures.
- [ ] **Step 3:** Implement; generate the JSON; write `STYLE.md`; replace
  the Task 4 placeholders so `on_call_tool` uses `finish` and
  `render_error`.
- [ ] **Step 4:** Run `pytest tests/unit/mcp -q`. Expect green.

### Task 6: Name resolution and Borg 1/2 read routes

**Files:**
- Create: `app/mcp/resolve.py`, `app/mcp/borg_routes.py`,
  `tests/unit/mcp/test_resolve.py`, `tests/unit/mcp/test_borg_routes.py`

**Interfaces, produces:**

```python
# resolve.py
class NotFound(Exception): ...      # .text ready for the user
class Ambiguous(Exception): ...     # .text lists the candidates
def pick(kind: str, ref: str | int, items: list[dict], *, name_key="name") -> dict
async def repository(ctx, ref) -> dict
async def archive(ctx, repo: dict, ref: str) -> dict    # ref may be "latest"
async def backup_plan(ctx, ref) -> dict
async def schedule(ctx, ref) -> dict
async def ssh_connection(ctx, ref) -> dict
async def agent(ctx, ref) -> dict
# borg_routes.py: each returns (path, params) for the repository's Borg version
def archives_list(repo: dict, **params) -> tuple[str, dict]
def archive_info(repo: dict, archive: dict) -> tuple[str, dict]
def archive_contents(repo: dict, archive: dict, path: str) -> tuple[str, dict]
def repository_info(repo: dict) -> tuple[str, dict]
def repository_stats(repo: dict) -> tuple[str, dict]
```

Decisions:

- `pick` order: integer or all-digit ref matches `id`; then exact name;
  then case-insensitive exact; then case-insensitive unique prefix; then
  case-insensitive unique substring. More than one hit at a step raises
  `Ambiguous`: "I found {n} {kind}s matching \"{ref}\": *A*, *B*. Which
  one?" (at most 8 named, then "and {k} more"). No hit raises `NotFound`:
  "I could not find a {kind} called \"{ref}\"." plus up to 5 closest names
  by `difflib.get_close_matches`, or the full list when there are 5 or
  fewer.
- Every resolver sets `ctx.target` to "{kind} {name}" (cut to 200).
- `archive(ctx, repo, "latest")` returns the newest by start time.
- `borg_routes` mirrors `frontend/src/services/borgApi/client.ts` for the
  five read operations only and keys on the same repository field that
  file keys on. Later phases add the write operations here.

- [ ] **Step 1:** Write failing `pick` tests with items `Photos`,
  `Photos old`, `Documents`: `"Documents"`, `"documents"`, `"doc"` and
  the id each resolve; `"Photos"` resolves to *Photos* (exact wins);
  `"photo"` raises `Ambiguous` naming both (Review Focus 3); `"Fotos"`
  raises `NotFound` suggesting *Photos*; `"9999"` raises `NotFound`.
- [ ] **Step 2:** Write failing route tests: a Borg 1 repository dict maps
  each function to the v1 path and a Borg 2 one to `/api/v2/...`, with
  the exact paths read from `client.ts`.
- [ ] **Step 3:** Run, expect failures. Implement. Run, expect green.

### Task 7: Activity log and rate limit

**Files:**
- Create: `app/mcp/activity.py`, `tests/unit/mcp/test_activity.py`
- Modify: `app/mcp/server.py` (use it)

**Interfaces, produces:**

```python
OUTCOMES = ("ok", "error", "denied_level", "denied_rbac")
RATE_LIMIT, RATE_WINDOW_S = 120, 60
RETENTION_DAYS, RETENTION_ROWS = 30, 20_000
def allow(app, conn: ConnectionContext) -> bool
def record(app, conn, *, tool: str, outcome: str, error_key: str | None,
           target: str | None, duration_ms: int) -> None
def prune(app, *, now: datetime | None = None) -> int
```

Decisions:

- `allow` counts the connection's `mcp_activity` rows in the last 60 s.
  At 120 or more the call is refused with "That is a lot of calls in one
  minute. Give it a moment and try again." and is not recorded, so the
  window drains by itself.
  `# ponytail: counts rows per call; move to a counter table if the query
  shows up in profiles.`
- Outcome mapping: handler returned normally → `ok`; `ApiError` 403
  without a plan key → `denied_rbac`; level refusal → `denied_level`;
  everything else → `error` with the backend key when there is one.
  `needs_confirmation` and `confirmed` arrive in phase 5.
- `record` never raises into the tool call (log and continue) and runs in
  a worker thread.
- `prune` deletes rows older than 30 days, then everything beyond the
  newest 20,000. `record` calls it at most once per hour per process.
  This replaces "the existing daily cleanup" in spec 5.11: there is no
  single daily job to hook, and pruning on write needs no scheduler.
- No arguments are ever stored. `target` is what the resolver set.

- [ ] **Step 1:** Write failing tests: a successful call writes one row
  with `tool`, `effective_level == "read"`, `outcome == "ok"`,
  `duration_ms >= 0`, `connection_name`; a viewer calling an admin-only
  tool writes `denied_rbac`; a level refusal writes `denied_level`; the
  121st call inside a minute is refused and writes nothing, and a call
  after the window passes (freeze time) succeeds; `prune` with rows at 31
  days and 20,050 rows leaves 20,000 newest and none older than 30 days;
  `GET /connections/{id}/activity` returns the rows newest first and
  never an `arguments` field; `record` raising inside does not fail the
  tool call.
- [ ] **Step 2:** Run, expect failures. Implement and wire into
  `on_call_tool`. Run `pytest tests/unit/mcp -q`, expect green.

### Tasks 8 to 11: the read tools

Shared rules for every tool in these tasks:

- Registered with `@tool(...)`, `level=Level.READ`, `read_only=True`, the
  exact `title` from the table, and `routes` listing every route it calls.
- Input model: a pydantic model with a `Field(description=...,
  examples=[...])` on every field. Objects are referenced by name or id in
  one field (`repository: str`, `archive: str`, ...). List tools take
  `limit: int | None` and `cursor: str | None`.
- Output: `ToolResult.text` follows `STYLE.md`; `data` carries the full
  structured values (ids, raw bytes, ISO times).
- The description says what the tool is for and when to prefer a
  neighbour ("For one repository in detail use get_repository.").
- The implementer reads each route's handler for its real response shape
  before writing the tool, and writes the contract test against the real
  app with fixture rows, not mocks of the REST layer. Where a route shells
  out to Borg, use the existing Borg fixtures or the route's own test
  doubles from its current test module.
- A route path below that turns out to be wrong is corrected to the real
  one; the tool's name, title, level and behaviour stay.

Each task: write the contract tests for its tools (one happy path
asserting key lines of text and key `data` fields, one empty state, and
the listed edge cases), run to see them fail, implement, run green.

### Task 8: Overview and health

**Files:** `app/mcp/tools/overview.py`, `tests/unit/mcp/test_tools_overview.py`

| Tool | Title | Routes | Notes |
|---|---|---|---|
| `get_overview` | See how my backups are doing | `GET /api/dashboard/overview` | One line verdict, then per repository: name, health, last backup age, size. |
| `list_problems` | Find what needs attention | `GET /api/dashboard/overview`, `GET /api/activity/recent` (`status=failed`, limit 10) | Repositories with warning or critical health with the reason, failed jobs in the last 7 days, failing checks or restore checks. Empty state: "Nothing needs attention." |
| `get_upcoming_runs` | See what runs next | `GET /api/schedule/upcoming-jobs` | Next runs with relative and absolute time. |
| `get_system_info` | About this Borg UI | `GET /api/system/info` | App version, plan as sold (`license_plan`), Borg versions. No instance, licence or customer ids in text or data. |

Edge cases: no repositories at all ("No repositories yet. Want to set one
up? That needs Manage access."); `get_system_info` output contains none of
`instance_id`, `license_id`, `customer_id`, `key_id`, `entitlement_id`.

### Task 9: Repositories and archives

**Files:** `app/mcp/tools/repositories.py`, `app/mcp/tools/archives.py`,
`tests/unit/mcp/test_tools_repositories.py`,
`tests/unit/mcp/test_tools_archives.py`

| Tool | Title | Routes |
|---|---|---|
| `list_repositories` | List repositories | `GET /api/repositories/` |
| `get_repository` | Look at a repository | `GET /api/repositories/{id}`, `borg_routes.repository_stats`, `GET /api/repositories/{id}/check-schedule`, `GET /api/repositories/{id}/running-jobs` |
| `get_repository_space` | See where the space goes | `GET /api/repositories/{id}/storage`, `GET /api/repositories/{id}/archives/growth` |
| `compare_retention` | Compare retention policies | `GET /api/repositories/{id}/prune/comparison`, `GET /api/repositories/{id}/prune/retention-defaults` |
| `list_archives` | List archives | `GET /api/repositories/{id}/archives` (index); falls back to `borg_routes.archives_list` when the index is off |
| `get_archive` | Look at an archive | `GET /api/repositories/{id}/archives/{archive_id}`, `borg_routes.archive_info` |
| `browse_archive` | Browse files in an archive | `borg_routes.archive_contents` |
| `search_files` | Search backed-up files | `GET /api/repositories/{id}/search` |
| `get_file_history` | Trace a file's history | `GET /api/repositories/{id}/history` |
| `compare_archives` | See what changed between archives | `GET /api/repositories/{id}/archives/{archive_id}/changes` |

Notes: `browse_archive` takes `path` (default the archive root), lists
directories first, pages with the cursor and shows size and modified time
per entry. `search_files`, `get_file_history` and `compare_archives` are
gated by `archive_history` at the route; on Community trials the plan
sentence from `render_error` is the answer. Freed-space and footprint
numbers keep the app's "at least" wording. `list_archives` accepts
`newest_first: bool = True`.

Edge cases: a directory of 100,000 entries pages at 25 and the text ends
with the `more_line` (Review Focus 4); a Borg 2 repository goes through
`/api/v2`; an ambiguous repository name asks; `archive="latest"` works;
an unknown path in `browse_archive` says so and suggests the parent.

### Task 10: Jobs and activity

**Files:** `app/mcp/tools/jobs.py`, `tests/unit/mcp/test_tools_jobs.py`

Jobs are identified by `job_type` and `job_id` exactly as
`/api/activity/recent` returns them; text shows them as "backup 412".

| Tool | Title | Routes |
|---|---|---|
| `list_activity` | Show recent activity | `GET /api/activity/recent` |
| `list_running_jobs` | See what's running | `GET /api/activity/recent` (`status=running`), `GET /api/operations/queue` |
| `get_job` | Check on a job | `GET /api/activity/recent` filtered to the job, `GET /api/operations/{id}` for operation-backed jobs |
| `get_job_log` | Read a job's log | `GET /api/activity/{job_type}/{job_id}/logs` |
| `wait_for_job` | Wait for a job to finish | same as `get_job`, polled every 3 s for at most 45 s |
| `explain_failure` | Explain why a job failed | `get_job` routes, the log route, `GET /api/activity/recent` (same repository, `status=failed`, limit 5) |

Notes: `list_activity` filters: `repository`, `status`, `job_type`,
`since` (ISO date or "24h", "7d"). `get_job_log` returns the last
`lines` (default 200, max 1000) and a `before` cursor for earlier lines.
`wait_for_job` returns the final result, or "Still running after 45
seconds ({progress}). Ask me again." Progress notifications are phase 3.
`explain_failure` with no job given picks the most recent failure; its
text is sections "What failed", "Error", "Last log lines" (40), "Similar
recent failures"; it states facts and does not guess a cause.

Edge cases: a log larger than the cap is cut by `finish` and says so; a
job that does not exist; `wait_for_job` on a finished job returns at
once; `explain_failure` when nothing has failed ("Nothing has failed
recently.").

### Task 11: Plans, schedules, connections, settings

**Files:** `app/mcp/tools/plans.py`, `app/mcp/tools/connections.py`,
`tests/unit/mcp/test_tools_plans.py`,
`tests/unit/mcp/test_tools_connections.py`

| Tool | Title | Routes |
|---|---|---|
| `list_backup_plans` | List backup plans | `GET /api/backup-plans/` |
| `get_backup_plan` | Look at a backup plan | `GET /api/backup-plans/{id}` |
| `list_plan_runs` | Show a plan's runs | `GET /api/backup-plans/{id}/runs` |
| `list_schedules` | List schedules | `GET /api/schedule/` |
| `get_schedule` | Look at a schedule | `GET /api/schedule/{id}` |
| `check_cron` | Check a schedule expression | `POST /api/schedule/validate-cron` |
| `browse_server_folders` | Browse folders on the server | the directory listing route in `app/api/filesystem.py` |
| `browse_agent_folders` | Browse folders on an agent machine | `GET /api/managed-machines/agents/{id}/filesystem/browse` |
| `list_ssh_connections` | List SSH connections | `GET /api/ssh-keys/connections` |
| `list_ssh_keys` | List SSH keys | `GET /api/ssh-keys/` |
| `list_agents` | List agent machines | `GET /api/managed-machines/agents` |
| `list_rclone_remotes` | List cloud remotes | `GET /api/rclone/remotes` |
| `list_scripts` | List scripts | `GET /api/scripts` |
| `list_notification_channels` | List notification channels | the list route in `app/api/notifications.py` |
| `get_settings` | Look at settings | `GET /api/settings/system` |
| `list_users` | List users | `GET /api/settings/users` |

Notes: `check_cron` is a POST that changes nothing, so it stays `read`
and is listed in the contract test's allowlist of non-GET read routes.
`get_backup_plan` reads like the plan summary in the app: sources,
repositories, schedule in words plus the cron, retention, scripts, next
run. `list_ssh_keys` shows name, type and fingerprint only.
`list_notification_channels` shows name, service type and events, never
the URL. `list_scripts` shows names and descriptions, not bodies (a
script body can hold credentials; reading one arrives with Manage).
`get_settings` shows a curated set (timeouts, retention of logs,
monitoring thresholds, MCP state) and no secrets.

Edge cases: a viewer calling `list_users` gets the permission sentence
and a `denied_rbac` row; `list_ssh_keys`, `list_notification_channels`,
`list_rclone_remotes` output passes the redaction scan in Task 12; an
invalid cron in `check_cron` returns the app's own validation message.

### Task 12: Cross-cutting contract tests, smoke, docs

**Files:** `tests/unit/mcp/test_contract.py`,
`tests/unit/mcp/test_redaction_scan.py`,
`tests/integration/test_mcp_smoke.py`, `docs/api.md`

- [ ] **Step 1: Registry contract.** For every tool in `REGISTRY`: the
  name is snake_case and at most 40 characters; the title is non-empty,
  has no trailing period and no em dash; the description is 40 to 600
  characters; every `routes` entry matches a route in `app.routes` (path
  template and method); a `read` tool declares only `GET` routes, except
  the explicit allowlist `{"POST /api/schedule/validate-cron"}`; no tool
  below `full` declares a `DELETE` route. Also assert the registry holds
  exactly the 36 names listed in Tasks 8 to 11 (so a missing or extra
  tool fails loudly).
- [ ] **Step 2: Level matrix.** For each of `read`, `operate`, `manage`,
  `full`, and for the cap at each level: `tools/list` returns exactly
  `tools_for(effective)`. For viewer, operator and admin users with a
  `read` connection: every tool call returns either a normal result or
  the permission sentence, never a 5xx sentence.
- [ ] **Step 3: Redaction scan.** Seed fixtures that contain a repository
  with a passphrase, an SSH key, a notification channel with a tokened
  URL, an rclone remote with a secret, and an API token. Call every tool
  with valid arguments; assert none of the seeded secret values appears
  in any `text` or serialized `data`.
- [ ] **Step 4: Smoke with the official client.** Start the app on a free
  port in a background thread (uvicorn), create a connection over REST,
  then with the SDK's Streamable HTTP client: `initialize`, `list_tools`
  (36), `call_tool("get_overview")`, `call_tool("list_repositories")`.
  Mark it `integration`.
- [ ] **Step 5:** Document the endpoint in `docs/api.md` (URL, auth
  header, that it is stateless, the level model in two lines, pointer to
  the user guide that phase 2 adds).
- [ ] **Step 6: Full verification.** `pytest tests/unit tests/migrations
  -q`, `pytest tests/integration/test_mcp_smoke.py -q`, `ruff check app
  tests scripts && ruff format --check app tests scripts`,
  `cd frontend && npm run typecheck && npx vitest run src/core && npm run
  check:locales`. Then a manual pass: fresh `DATA_DIR`, start the backend,
  create a `read` connection with curl, add it to Claude Code with
  `claude mcp add --transport http borg-ui http://localhost:<port>/mcp
  --header "Authorization: Bearer <token>"`, and ask "how are my backups
  doing?" and "what failed recently?". Record what the answers looked
  like in the progress table notes.

---

## Appendix 1. Server instructions (`INSTRUCTIONS`)

```text
You are connected to Borg UI, a web app that manages BorgBackup.

How it fits together
- A repository stores archives. Each archive is one backup at a point in time.
- A backup plan says what to back up (sources), where to (one or more
  repositories), when (a schedule) and how long to keep it (retention).
  Prefer plans for anything that should happen more than once.
- A schedule runs a plan or a repository backup on a cron expression.
- Check verifies a repository. A restore check proves files can be restored.
- Prune applies retention and removes old archives. Compact then frees the space.

How to work
- Start with get_overview or list_problems when the user asks how things are.
- Refer to things by name. If a name is ambiguous the tool will say so: ask the
  user which one they mean, do not pick.
- Lists are paged. If a result says there is more, ask for the next page only
  when the user needs it.
- Sizes and times in the text are already formatted for people. Exact values
  are in the structured result.
- This connection has an access level (read, operate, manage or full). You only
  see the tools that level allows. If the user asks for something you have no
  tool for, tell them it needs a higher access level, which they can change in
  Borg UI under Settings > MCP.
- Never ask the user for a passphrase, password, private key or token. When one
  is needed, Borg UI gives you a link to the page where the user enters it.
```

## Appendix 2. Voice guide (`app/mcp/STYLE.md`), for Karan to review

```markdown
# How Borg UI talks over MCP

Borg UI's voice: a calm colleague who knows backups. Short, specific,
a little warm. Never cute at the expense of clarity.

Rules
1. First line is the outcome. Details after. One offer of a next step
   at the end, only when there is an obvious one.
2. Say names in italics. Keep ids out of the text unless two things
   share a name.
3. Sizes like "38.2 GB". Times like "3 hours ago (2026-11-14 06:10 UTC)".
   Durations like "6 min". Estimates say "usually".
4. Status marks: ✓ fine, ⚠ needs a look, ✗ failed, ⏳ running. At most one
   per line, at the start.
5. Lists are compact: one line per item, the most useful two or three
   facts, newest or worst first.
6. When something is cut short, say what is missing and how to get it.
7. Errors say what happened and what the person can do. No codes unless
   there is nothing better. Never a stack trace.
8. No em dashes. No exclamation marks. No "successfully". No "please note".
9. English only. The assistant translates for the user.

Examples

get_overview
  ✓ All 4 repositories are healthy. Last backup finished 3 hours ago.

  ✓ *Photos*: backed up 3 hours ago, 412.6 GB, 58 archives
  ✓ *Documents*: backed up 3 hours ago, 18.1 GB, 120 archives
  ⚠ *Laptop*: last backup 9 days ago (plan expects daily)
  ✓ *Databases*: backed up 1 hour ago, 6.4 GB, 336 archives

  Want me to look into *Laptop*?

list_problems (nothing wrong)
  ✓ Nothing needs attention. 4 repositories, all backed up in the last day.

explain_failure
  ✗ Backup of *Laptop* failed 9 days ago after 2 min.

  **Error**: the repository is locked by another process.
  **Last log lines**
  ...
  **Similar recent failures**: none in the last 30 days.

Ambiguous name
  I found 2 repositories matching "photo": *Photos* and *Photos old*.
  Which one?

Not allowed
  This connection has read access, and Back up now needs operate. You can
  change that under Settings > MCP.
```

## Open questions

1. Appendix 2 is the voice every later phase copies. Is the tone right
   (status marks, the closing offer, the wording of refusals)?
2. Activity rows outlive a revoked connection (kept with the connection's
   name) so there is something to inspect afterwards. The spec said only
   "retention 30 days". Agreed?
3. When the plan lapses or an admin turns MCP off, clients still connect
   and see the tool list, and every tool call answers with the friendly
   sentence. The alternative (refuse the connection) shows up in most
   clients as a generic "failed to connect". Agreed?
4. `list_scripts` shows names and descriptions but not script bodies at
   Read, because bodies can hold credentials. Reading a body would arrive
   with Manage in phase 4. Agreed?
