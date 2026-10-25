"""Require an explicit, reviewable access declaration for every registered route."""

import inspect

import pytest
from fastapi import APIRouter, Depends, FastAPI
from starlette.routing import Mount, WebSocketRoute

from app.core.authorization import ENDPOINT_POLICIES, authorize_request
from app.core.security import (
    get_current_admin_user,
    get_current_download_admin_user,
    require_role_dependency,
)


LEVELS = {"public", "authenticated", "repository-scoped", "operator", "admin", "agent"}


def registered_routes(routes, prefix=""):
    """Include nested mounts and FastAPI's lazy included routers with full prefixes."""
    for route in routes:
        if hasattr(route, "effective_candidates"):
            yield from registered_routes(route.effective_candidates(), prefix)
            continue
        route = getattr(route, "starlette_route", None) or route
        path = prefix + route.path
        if isinstance(route, Mount):
            yield ("MOUNT", path), route
            yield from registered_routes(route.routes, path)
        else:
            methods = getattr(route, "methods", None)
            if methods is None:
                assert isinstance(route, WebSocketRoute), (
                    f"Unknown route type: {route!r}"
                )
                methods = {"WEBSOCKET"}
            for method in methods:
                yield (method, path), route


def role_dependency_roles(call):
    if call in (get_current_admin_user, get_current_download_admin_user):
        return {"admin"}
    if inspect.isfunction(call) and call.__module__ == "app.core.security":
        closure = inspect.getclosurevars(call).nonlocals
        if call.__name__ == "dependency" and "allowed_roles" in closure:
            return set(closure["allowed_roles"])
    return None


def assert_route_access(routes, registry):
    failures = []
    for key, route in registered_routes(routes):
        level = registry.get(key)
        if level is None:
            failures.append(
                f"{key[0]} {key[1]} ({route.name}): declare its access level in ROUTE_ACCESS_REGISTRY"
            )
            continue
        if level not in LEVELS:
            failures.append(f"{key}: invalid access level {level!r}")
        if level not in {"admin", "operator"}:
            continue
        allowed = {"admin"} if level == "admin" else {"admin", "operator"}
        dependencies = getattr(getattr(route, "dependant", None), "dependencies", ())
        policy = ENDPOINT_POLICIES.get((key[0], key[1].rstrip("/") or "/"))
        policy_guard = (
            policy is not None
            and set(policy.roles) <= allowed
            and any(dep.call is authorize_request for dep in dependencies)
        )
        # Plain authentication does not establish an admin or operator guard.
        signature_guard = any(
            (
                roles := role_dependency_roles(
                    getattr(parameter.default, "dependency", None)
                )
            )
            and roles <= allowed
            for parameter in inspect.signature(route.endpoint).parameters.values()
        )
        router_guard = any(
            (roles := role_dependency_roles(dep.call)) and roles <= allowed
            for dep in dependencies
        )
        if not policy_guard and not signature_guard and not router_guard:
            failures.append(
                f"{key[0]} {key[1]} ({route.name}): {level} declaration has no matching role guard"
            )
    assert not failures, "\n".join(failures)


def test_registered_routes_have_access_declarations():
    from app.main import app
    from app.core.route_access import ROUTE_ACCESS_REGISTRY

    assert_route_access(app.routes, ROUTE_ACCESS_REGISTRY)


def test_undeclared_prefixed_route_fails_with_actionable_message():
    app = FastAPI()
    router = APIRouter()

    @router.get("/new-route", name="forgotten_guard")
    def endpoint():
        return {}

    app.include_router(router, prefix="/api/new")
    with pytest.raises(
        AssertionError,
        match=r"GET /api/new/new-route \(forgotten_guard\): declare its access level in ROUTE_ACCESS_REGISTRY",
    ):
        assert_route_access(app.routes, {})


def test_undeclared_websocket_and_mount_routes_fail():
    app = FastAPI(openapi_url=None)
    child = FastAPI(openapi_url=None)

    @child.websocket("/socket")
    async def socket(websocket):
        pass

    app.mount("/nested", child, name="nested")
    with pytest.raises(AssertionError) as exc:
        assert_route_access(app.routes, {})
    assert "MOUNT /nested (nested)" in str(exc.value)
    assert "WEBSOCKET /nested/socket (socket)" in str(exc.value)


@pytest.mark.parametrize("level", ["admin", "operator"])
def test_removing_signature_role_guard_fails(level):
    app = FastAPI(openapi_url=None)
    guard = require_role_dependency("admin")

    @app.get("/guarded")
    def guarded(current_user=Depends(guard)):
        return {}

    assert_route_access(app.routes, {("GET", "/guarded"): level})

    def unguarded():
        return {}

    app.routes[-1].endpoint = unguarded
    app.routes[-1].dependant.dependencies.clear()
    with pytest.raises(AssertionError, match="declaration has no matching role guard"):
        assert_route_access(app.routes, {("GET", "/guarded"): level})


def test_removing_endpoint_policy_or_router_guard_fails(monkeypatch):
    from app.core.authorization import EndpointPolicy

    app = FastAPI(openapi_url=None)
    router = APIRouter(dependencies=[Depends(authorize_request)])

    @router.get("/guarded")
    def guarded():
        return {}

    app.include_router(router, prefix="/api")
    key = ("GET", "/api/guarded")
    monkeypatch.setitem(
        ENDPOINT_POLICIES, key, EndpointPolicy(("admin",), "test.admin")
    )
    assert_route_access(app.routes, {key: "admin"})
    monkeypatch.delitem(ENDPOINT_POLICIES, key)
    with pytest.raises(AssertionError, match="no matching role guard"):
        assert_route_access(app.routes, {key: "admin"})
    monkeypatch.setitem(
        ENDPOINT_POLICIES, key, EndpointPolicy(("admin", "operator"), "test.operator")
    )
    with pytest.raises(AssertionError, match="no matching role guard"):
        assert_route_access(app.routes, {key: "admin"})
    # A policy entry is ineffective without the router authorization dependency.
    app = FastAPI(openapi_url=None)
    app.get("/api/guarded")(guarded)
    with pytest.raises(AssertionError, match="no matching role guard"):
        assert_route_access(app.routes, {key: "operator"})


@pytest.mark.parametrize(
    "roles,level",
    [
        (("admin", "operator"), "admin"),
        (("admin", "operator", "viewer"), "operator"),
    ],
)
def test_dependency_must_enforce_declared_role_set(roles, level):
    app = FastAPI(openapi_url=None)
    guard = require_role_dependency(*roles)

    @app.get("/guarded")
    def guarded(current_user=Depends(guard)):
        return {}

    with pytest.raises(AssertionError, match="no matching role guard"):
        assert_route_access(app.routes, {("GET", "/guarded"): level})


def test_plain_authentication_is_not_a_role_guard():
    from app.core.security import get_current_user

    app = FastAPI(openapi_url=None)

    @app.get("/guarded")
    def guarded(current_user=Depends(get_current_user)):
        return {}

    with pytest.raises(AssertionError, match="no matching role guard"):
        assert_route_access(app.routes, {("GET", "/guarded"): "operator"})
