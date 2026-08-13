"""Unit tests for endpoint-policy resolution in ``app.core.authorization``.

The role/auth guards are keyed on the request's endpoint. Resolution must work
from the concrete request path alone — not from ``request.scope["route"].path``,
whose meaning changed in FastAPI 0.141 (a router-level dependency now sees the
router-relative path, e.g. ``/{job_id}`` instead of ``/api/schedule/{job_id}``).
That regression silently turned every guard into a no-op; these tests pin the
version-independent behaviour, including resolution under a non-empty
``BASE_PATH`` (``root_path``).
"""

import re
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core import authorization as authz
from app.core.authorization import (
    ENDPOINT_POLICIES,
    _assert_unambiguous_policies,
    _match_policy,
    _strip_root_path,
    _templates_overlap,
    authorize_request,
)


def _request(method: str, path: str, root_path: str = "") -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "raw_path": path.encode(),
            "root_path": root_path,
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "server": ("test", 80),
        }
    )


def _fill(template: str) -> str:
    """Turn a policy template into a concrete path (``{param}`` -> ``1``)."""
    return re.sub(r"\{[^/]+\}", "1", template)


def test_every_policy_resolves_from_its_concrete_path():
    # For each declared policy, the concrete path it governs must resolve back
    # to exactly that policy — the core invariant the guard relies on.
    for (method, template), policy in ENDPOINT_POLICIES.items():
        resolved = _match_policy(method, _fill(template))
        assert resolved is policy, f"{method} {template} resolved to {resolved!r}"


def test_resolves_parameterised_path():
    policy = _match_policy("PUT", "/api/schedule/42")
    assert policy is not None
    assert policy.detail_key == "backend.errors.schedule.operatorAccessRequired"
    assert policy.roles == ("admin", "operator")


def test_resolves_deep_multi_param_path():
    policy = _match_policy("GET", "/api/repositories/7/wipe-jobs/9")
    assert policy is not None
    assert policy.detail_key == "backend.errors.repo.adminAccessRequired"


def test_trailing_slash_is_normalised():
    assert _match_policy("POST", "/api/schedule/") is _match_policy(
        "POST", "/api/schedule"
    )
    assert _match_policy("POST", "/api/schedule") is not None


def test_method_is_significant():
    # No policy governs GET on a single schedule; it must not borrow PUT's.
    assert _match_policy("GET", "/api/schedule/1") is None


def test_static_and_parameterised_siblings_do_not_collide():
    # A concrete path must resolve to its own entry, not fall through to a
    # parameterised sibling of a different shape.
    assert (
        _match_policy("GET", "/api/packages/jobs")
        is ENDPOINT_POLICIES[("GET", "/api/packages/jobs")]
    )
    assert (
        _match_policy("GET", "/api/packages/jobs/5")
        is ENDPOINT_POLICIES[("GET", "/api/packages/jobs/{job_id}")]
    )


def test_unlisted_path_has_no_policy():
    assert _match_policy("GET", "/api/health") is None
    assert _match_policy("GET", "/api/schedule") is None


# --- policy uniqueness ------------------------------------------------------


def test_declared_policies_are_unambiguous():
    # The real table must never let two same-method templates match one path.
    _assert_unambiguous_policies()


def test_templates_overlap_detects_static_vs_param():
    assert _templates_overlap("/api/x/{id}", "/api/x/static") is True


def test_templates_overlap_ignores_different_lengths():
    assert _templates_overlap("/api/x", "/api/x/{id}") is False


def test_templates_overlap_ignores_distinct_literals():
    assert _templates_overlap("/api/a", "/api/b") is False


# --- BASE_PATH / root_path handling -----------------------------------------


def test_prefixed_path_misses_without_stripping():
    # The bug the strip closes: a mount-prefixed path matches no template.
    assert _match_policy("PUT", "/borgui/api/schedule/1") is None


def test_strip_root_path_removes_prefix():
    assert _strip_root_path("/borgui/api/schedule/1", "/borgui") == "/api/schedule/1"
    assert _strip_root_path("/borgui/api/schedule/1", "/borgui/") == "/api/schedule/1"


def test_strip_root_path_is_noop_without_prefix():
    assert _strip_root_path("/api/schedule/1", "") == "/api/schedule/1"


def test_strip_root_path_only_on_segment_boundary():
    # "/borgui" must not be stripped from "/borguix/...".
    assert _strip_root_path("/borguix/api", "/borgui") == "/borguix/api"


def test_strip_root_path_exact_match_becomes_root():
    assert _strip_root_path("/borgui", "/borgui") == "/"


def test_policy_resolves_after_stripping_prefix():
    stripped = _strip_root_path("/borgui/api/schedule/1", "/borgui")
    assert (
        _match_policy("PUT", stripped)
        is ENDPOINT_POLICIES[("PUT", "/api/schedule/{job_id}")]
    )


async def test_authorize_request_enforces_under_root_path(monkeypatch):
    async def fake_current_user(request, db):
        return SimpleNamespace(role="viewer")

    monkeypatch.setattr(authz, "get_current_user", fake_current_user)

    # Viewer hitting an operator-only endpoint behind BASE_PATH=/borgui.
    request = _request("POST", "/borgui/api/schedule", root_path="/borgui")
    with pytest.raises(HTTPException) as exc:
        await authorize_request(request, db=None)
    assert exc.value.status_code == 403


async def test_authorize_request_allows_admin_under_root_path(monkeypatch):
    async def fake_current_user(request, db):
        return SimpleNamespace(role="admin")

    monkeypatch.setattr(authz, "get_current_user", fake_current_user)

    request = _request("POST", "/borgui/api/schedule", root_path="/borgui")
    assert await authorize_request(request, db=None) is None


async def test_authorize_request_prefers_path_as_received(monkeypatch):
    # A received path that already matches must win, even when root_path happens
    # to prefix a real route — the strip must not fire and drop enforcement.
    async def fake_current_user(request, db):
        return SimpleNamespace(role="viewer")

    monkeypatch.setattr(authz, "get_current_user", fake_current_user)

    request = _request("POST", "/api/schedule", root_path="/api")
    with pytest.raises(HTTPException) as exc:
        await authorize_request(request, db=None)
    assert exc.value.status_code == 403
