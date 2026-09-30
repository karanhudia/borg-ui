"""Sub-path deployment (issue #1271): mounted StaticFiles must resolve whether or
not the reverse proxy strips the BASE_PATH prefix."""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from app.main import BasePathMiddleware


def _client(tmp_path, base_path="/borg-ui"):
    (tmp_path / "index-abc.css").write_text("body{}")
    app = FastAPI(root_path=base_path)
    app.add_middleware(BasePathMiddleware, base_path=base_path)
    app.mount("/assets", StaticFiles(directory=tmp_path), name="assets")

    @app.get("/")
    async def root():
        return {"ok": True}

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


def test_root_and_spa_routes_still_match(tmp_path):
    client = _client(tmp_path)
    assert client.get("/").json() == {"ok": True}
    assert client.get("/borg-ui/").json() == {"ok": True}
    assert client.get("/dashboard").json() == {"path": "dashboard"}
    assert client.get("/borg-ui/dashboard").json() == {"path": "dashboard"}
