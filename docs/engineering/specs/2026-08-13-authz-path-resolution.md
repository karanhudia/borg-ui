# Version-robust endpoint authorization

Status: implemented. Concerns how `authorize_request` resolves which endpoint a
request hit, and why that resolution must not depend on FastAPI's internal route
naming. Unblocks the `fastapi` 0.136 -> 0.141 upgrade held back in the
`backend-minor-patch` dependency group.

## Problem

Role and authentication guards are enforced in one place: `authorize_request`, a
router-level dependency in `app/core/authorization.py`. It looks up an
`EndpointPolicy` in `ENDPOINT_POLICIES`, a table keyed on
`(method, full_path_template)` — e.g. `("PUT", "/api/schedule/{job_id}")` requires
`admin` or `operator`. If no policy matches, the request is allowed through (the
endpoint is public or guards itself).

The endpoint was identified by reading `request.scope["route"].path` — the full
path template. That is an implicit dependency on a FastAPI internal, and the
internal changed:

| | FastAPI 0.136.3 | FastAPI 0.141.1 |
| --- | --- | --- |
| `scope["route"].path` seen by a router-level dependency | `/api/schedule/{job_id}` (full) | `/{job_id}` (router-relative) |
| `root_path` | `""` | `""` (does not carry the prefix) |

Under 0.141 every lookup misses, `policy` is `None`, and the guard returns without
checking — **silently turning every role and auth guard into a no-op**. A viewer
could create, modify, and delete schedules; unauthenticated requests reached admin
endpoints (200 where 401/403 was due). `main` was not affected while pinned to
0.136.3; the upgrade is what would have exposed it. This was reproduced and
bisected: `fastapi` alone flips the behaviour, with `starlette` (1.6.0) and
`pydantic` (2.13.4) unchanged.

## The fix: resolve from the concrete path

The guard must not depend on *how* FastAPI names the matched route. The only
stable, version-independent input is the concrete request path
(`request.url.path`, e.g. `/api/schedule/1`). We already own the path templates —
the `ENDPOINT_POLICIES` keys — so we compile those into anchored regexes once and
match the concrete path against them:

```python
def _template_to_regex(path: str) -> Pattern[str]:
    # "/api/repositories/{repo_id}/wipe-jobs/{job_id}"
    #   -> ^/api/repositories/[^/]+/wipe-jobs/[^/]+$
    parts = re.split(r"\{[^/]+\}", path)
    return re.compile("^" + "[^/]+".join(re.escape(part) for part in parts) + "$")
```

`_match_policy(method, path)` normalises the trailing slash (unchanged
`_normalize_path`) and returns the first compiled policy whose method and pattern
match. `authorize_request` calls it with `request.url.path`; `scope["route"]` is no
longer read. The `EndpointPolicy` / `ENDPOINT_POLICIES` data is untouched — only
the lookup changed.

For this to have a single, well-defined answer, no two same-method templates may
match the same concrete path. FastAPI does *not* enforce that — it allows
overlapping routes and resolves them by declaration order — so the guard cannot
rely on it. `_assert_unambiguous_policies` enforces it here instead, at import: an
overlapping pair fails loudly at startup rather than silently resolving to the
wrong policy. With uniqueness guaranteed, the first regex match is the only match
and match order is irrelevant.

### Mounted under a base path

The policy templates are app-relative (`/api/...`), so matching must be too. When
the app is served under a non-empty `BASE_PATH` (`FastAPI(root_path=...)`), the
ASGI server can leave `request.url.path` carrying the mount prefix while
`scope["root_path"]` holds it separately — a prefixed path (`/borgui/api/...`)
would then miss every template and skip the guard, the same failure in a different
guise. `_strip_root_path` removes the prefix on a path-segment boundary (so
`/borgui` is not stripped from `/borguix/...`) before matching; it is a no-op when
no prefix is present.

## Alternatives considered

- **Repair `route.path` / use `root_path`.** Rejected: `root_path` is empty
  (measured), and `route.path` is exactly the value that shifted between versions.
- **Per-route dependencies** (`Depends(require_roles(...))` on each of ~50
  endpoints instead of the central table). This is the most idiomatic FastAPI
  shape and is immune to path semantics, but it means touching every router and
  giving up the single auditable policy table. Noted as a possible future
  direction; out of scope for restoring correctness under the version bump.

## Verification

Two guarantees, both enforced in CI:

- **Cross-version.** The nine guard tests (`test_api_schedule::TestScheduleRoleGuard`,
  the `test_api_settings` unauthenticated / non-admin cases, and
  `test_api_repository_wipe::test_preview_requires_global_admin`) pass on both
  fastapi 0.136.3 and 0.141.1.
- **Resolution invariant.** `tests/unit/test_authorization_policy.py` drives
  `_match_policy` directly. Its central test fills every `ENDPOINT_POLICIES`
  template with a concrete value and asserts it resolves back to exactly that
  policy — a single check that no template, static/parameterised sibling, or
  future addition can be misresolved, independent of the FastAPI version.
- **Base path.** The same file covers `_strip_root_path` (prefix removal,
  segment-boundary safety) and drives `authorize_request` end-to-end under
  `root_path=/borgui`: a viewer is rejected with 403 and an admin is allowed.
