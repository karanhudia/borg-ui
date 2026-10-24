"""Sub-path deployment (issues #1271, #1444): mounted StaticFiles, routes and
generated URLs must resolve whether or not the reverse proxy strips the
BASE_PATH prefix, with the root path coming from BasePathMiddleware rather
than the deprecated ``FastAPI(root_path=...)``. /health and /api answer with
their own JSON, not the SPA catch-all."""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from app.config import settings
from app.core.oidc import build_default_post_login_url
from app.main import BASE_PATH, BasePathMiddleware
from app.main import app as main_app

REPO_ROOT = Path(__file__).resolve().parents[2]


def _client(tmp_path, base_path="/borg-ui"):
    (tmp_path / "index-abc.css").write_text("body{}")
    app = FastAPI(docs_url="/api/docs")
    app.add_middleware(BasePathMiddleware, base_path=base_path)
    app.mount("/assets", StaticFiles(directory=tmp_path), name="assets")

    @app.get("/")
    async def root():
        return {"ok": True}

    @app.get("/api/where")
    async def where(request: Request):
        return {
            "root_path": request.scope.get("root_path"),
            "asset_url": str(request.url_for("assets", path="index-abc.css")),
        }

    @app.get("/api/after-login")
    async def after_login(request: Request):
        return RedirectResponse(build_default_post_login_url(request))

    @app.get("/{full_path:path}")
    async def catch_all(full_path: str):
        return {"path": full_path}

    return TestClient(app)


def test_assets_resolve_when_proxy_strips_prefix(tmp_path):
    response = _client(tmp_path).get("/assets/index-abc.css")
    assert response.status_code == 200
    assert response.text == "body{}"


def test_assets_resolve_on_direct_prefixed_access(tmp_path):
    response = _client(tmp_path).get("/borg-ui/assets/index-abc.css")
    assert response.status_code == 200
    assert response.text == "body{}"


def test_root_and_spa_routes_still_match(tmp_path):
    client = _client(tmp_path)
    assert client.get("/").json() == {"ok": True}
    assert client.get("/borg-ui/").json() == {"ok": True}
    assert client.get("/dashboard").json() == {"path": "dashboard"}
    assert client.get("/borg-ui/dashboard").json() == {"path": "dashboard"}


@pytest.mark.parametrize("prefix", ["", "/borg-ui"])
def test_generated_urls_carry_base_path(tmp_path, prefix, monkeypatch):
    # The redirect host comes from the request only without PUBLIC_BASE_URL.
    monkeypatch.setattr(settings, "public_base_url", None)
    client = _client(tmp_path)

    where = client.get(f"{prefix}/api/where").json()
    assert where == {
        "root_path": "/borg-ui",
        "asset_url": "http://testserver/borg-ui/assets/index-abc.css",
    }

    redirect = client.get(f"{prefix}/api/after-login", follow_redirects=False)
    assert redirect.status_code == 307
    assert redirect.headers["location"] == "http://testserver/borg-ui/login"

    docs = client.get(f"{prefix}/api/docs")
    assert docs.status_code == 200
    assert "'/borg-ui/openapi.json'" in docs.text
    assert client.get(f"{prefix}/openapi.json").status_code == 200


def test_health_and_api_info_answer_json_not_the_spa():
    """The SPA catch-all must not shadow /health and /api."""
    client = TestClient(main_app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "healthy", "service": "borg-web-ui"}

    api_info = client.get("/api")
    assert api_info.status_code == 200
    assert api_info.json()["name"] == "Borg UI API"
    assert api_info.json()["docs"] == f"{BASE_PATH}/api/docs"


def test_app_serves_base_path_without_fastapi_root_path():
    """The real app under BASE_PATH: no FastAPI deprecation warning, and docs,
    the OpenAPI schema, /health, /api and API routes answer with and without
    the prefix."""
    script = textwrap.dedent(
        """
        import warnings
        from fastapi.exceptions import FastAPIDeprecationWarning

        warnings.simplefilter("error", FastAPIDeprecationWarning)

        from fastapi.testclient import TestClient
        import app.main

        assert not app.main.app.root_path, app.main.app.root_path
        client = TestClient(app.main.app)
        for prefix in ("", "/borg-ui"):
            config = client.get(prefix + "/api/auth/config")
            assert config.status_code == 200, prefix
            assert "proxy_auth_enabled" in config.json(), prefix
            docs = client.get(prefix + "/api/docs")
            assert docs.status_code == 200, prefix
            assert "'/borg-ui/openapi.json'" in docs.text, prefix
            assert client.get(prefix + "/openapi.json").status_code == 200, prefix
            assert client.get(prefix + "/health").json()["status"] == "healthy", prefix
            api_info = client.get(prefix + "/api").json()
            assert api_info["name"] == "Borg UI API", prefix
            assert api_info["docs"] == "/borg-ui/api/docs", prefix
        print("ok")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        env={**os.environ, "BASE_PATH": "/borg-ui/"},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr[-4000:]
    assert result.stdout.strip().endswith("ok")
