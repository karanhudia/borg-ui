# -*- coding: utf-8 -*-
"""Unit tests for borg_ui_client module_utils."""

import json
import sys
import os
import pytest

# ---------------------------------------------------------------------------
# Path manipulation so tests can import the collection without installation
# ---------------------------------------------------------------------------
COLLECTION_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
# Fake the ansible_collections namespace so imports resolve without installing
NAMESPACE_ROOT = os.path.join(COLLECTION_ROOT, "_test_ns")
FAKE_COLL_PATH = os.path.join(NAMESPACE_ROOT, "ansible_collections", "borgui", "borg_ui")

# We monkey-patch sys.modules for the test session
import types

def _make_pkg(name):
    mod = types.ModuleType(name)
    mod.__path__ = []
    return mod

for pkg in [
    "ansible_collections",
    "ansible_collections.borgui",
    "ansible_collections.borgui.borg_ui",
    "ansible_collections.borgui.borg_ui.plugins",
    "ansible_collections.borgui.borg_ui.plugins.module_utils",
]:
    if pkg not in sys.modules:
        sys.modules[pkg] = _make_pkg(pkg)

# Point the module_utils package at our real source directory
_mu_path = os.path.join(COLLECTION_ROOT, "plugins", "module_utils")
sys.modules["ansible_collections.borgui.borg_ui.plugins.module_utils"].__path__ = [_mu_path]

# Now we can import the real module
import importlib.util

def _load(relpath, fullname):
    spec = importlib.util.spec_from_file_location(
        fullname,
        os.path.join(_mu_path, relpath),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[fullname] = mod
    spec.loader.exec_module(mod)
    return mod

client_mod = _load("borg_ui_client.py", "ansible_collections.borgui.borg_ui.plugins.module_utils.borg_ui_client")
BorgUIClient = client_mod.BorgUIClient
BorgUIClientError = client_mod.BorgUIClientError
_mint_jwt = client_mod._mint_jwt


# ---------------------------------------------------------------------------
# _mint_jwt tests
# ---------------------------------------------------------------------------

class TestMintJwt:
    def test_returns_three_part_string(self):
        token = _mint_jwt("mysecret", "admin")
        parts = token.split(".")
        assert len(parts) == 3

    def test_header_is_hs256(self):
        import base64
        token = _mint_jwt("mysecret", "admin")
        header_b64 = token.split(".")[0]
        # Add padding
        padded = header_b64 + "=" * (4 - len(header_b64) % 4)
        header = json.loads(base64.urlsafe_b64decode(padded))
        assert header["alg"] == "HS256"
        assert header["typ"] == "JWT"

    def test_payload_contains_sub(self):
        import base64
        token = _mint_jwt("mysecret", "testuser")
        payload_b64 = token.split(".")[1]
        padded = payload_b64 + "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        assert payload["sub"] == "testuser"
        assert "exp" in payload

    def test_different_keys_produce_different_tokens(self):
        t1 = _mint_jwt("key1", "admin")
        t2 = _mint_jwt("key2", "admin")
        assert t1 != t2

    def test_different_users_produce_different_tokens(self):
        t1 = _mint_jwt("key", "admin")
        t2 = _mint_jwt("key", "otheruser")
        assert t1 != t2


# ---------------------------------------------------------------------------
# BorgUIClient construction tests
# ---------------------------------------------------------------------------

class TestBorgUIClientInit:
    def test_requires_auth(self):
        with pytest.raises(BorgUIClientError, match="One of token"):
            BorgUIClient(base_url="http://localhost:8081")

    def test_token_auth(self):
        c = BorgUIClient(base_url="http://localhost:8081", token="mytoken")
        assert c._token == "mytoken"

    def test_secret_key_mints_token(self):
        c = BorgUIClient(base_url="http://localhost:8081", secret_key="mysecret")
        assert c._token is not None
        assert len(c._token.split(".")) == 3

    def test_secret_key_file_auth(self, tmp_path):
        key_file = tmp_path / "key.txt"
        key_file.write_text("filesecret\n")
        c = BorgUIClient(
            base_url="http://localhost:8081",
            secret_key_file=str(key_file),
        )
        assert c._token is not None

    def test_base_url_trailing_slash_stripped(self):
        c = BorgUIClient(base_url="http://localhost:8081/", token="t")
        assert c.base_url == "http://localhost:8081"

    def test_insecure_creates_ssl_ctx(self):
        import ssl
        c = BorgUIClient(base_url="https://localhost:8081", token="t", insecure=True)
        assert c._ssl_ctx is not None
        assert c._ssl_ctx.verify_mode == ssl.CERT_NONE

    def test_secure_ssl_ctx_is_none(self):
        c = BorgUIClient(base_url="https://localhost:8081", token="t", insecure=False)
        assert c._ssl_ctx is None


# ---------------------------------------------------------------------------
# BorgUIClient HTTP method tests (mocked urllib)
# ---------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, data):
        self._data = json.dumps(data).encode("utf-8") if data is not None else b""

    def read(self):
        return self._data


class FakeHTTPError(Exception):
    """Simulates urllib.error.HTTPError."""
    def __init__(self, code, body=None):
        self.code = code
        self._body = json.dumps(body).encode("utf-8") if body else b""

    def read(self):
        return self._body


@pytest.fixture
def client():
    return BorgUIClient(base_url="http://localhost:8081", token="testtoken")


@pytest.fixture
def mock_urlopen(monkeypatch):
    """Returns a factory; call with desired response to install the mock."""
    calls = []

    def _install(response_data=None, raise_exc=None):
        def _urlopen(req, **kwargs):
            calls.append({
                "method": req.get_method(),
                "url": req.get_full_url(),
                "headers": dict(req.headers),
                "data": req.data,
            })
            if raise_exc:
                raise raise_exc
            return FakeResponse(response_data)

        monkeypatch.setattr(client_mod, "urlopen", _urlopen)
        return calls

    return _install


class TestBorgUIClientRequests:
    def test_get_sends_correct_headers(self, client, mock_urlopen):
        calls = mock_urlopen({"repositories": []})
        client.get("/api/repositories/")
        assert len(calls) == 1
        assert calls[0]["method"] == "GET"
        assert "Authorization" in calls[0]["headers"] or "authorization" in calls[0]["headers"]

    def test_post_sends_data(self, client, mock_urlopen):
        calls = mock_urlopen({"success": True})
        client.post("/api/repositories/", {"name": "test"})
        assert calls[0]["method"] == "POST"
        assert calls[0]["data"] == b'{"name": "test"}'

    def test_put_sends_data(self, client, mock_urlopen):
        calls = mock_urlopen({"success": True})
        client.put("/api/repositories/1", {"name": "updated"})
        assert calls[0]["method"] == "PUT"

    def test_delete_sends_delete(self, client, mock_urlopen):
        calls = mock_urlopen(None)
        result = client.delete("/api/repositories/1")
        assert calls[0]["method"] == "DELETE"
        assert result is None

    def test_http_error_raises_borguiclienterror(self, client, monkeypatch):
        def _urlopen(req, **kwargs):
            err = FakeHTTPError(404, {"detail": "not found"})
            # urllib HTTPError attributes
            err.code = 404
            raise client_mod.HTTPError("url", 404, "Not Found", {}, None)

        # Patch HTTPError to a real one
        import urllib.error
        monkeypatch.setattr(client_mod, "urlopen", lambda req, **kw: (_ for _ in ()).throw(
            urllib.error.HTTPError("http://x", 404, "Not Found", {}, __import__("io").BytesIO(b'{"detail":"nf"}'))
        ))

        with pytest.raises(BorgUIClientError) as exc_info:
            client.get("/api/repositories/999")
        assert exc_info.value.status_code == 404

    def test_url_error_raises_borguiclienterror(self, client, monkeypatch):
        import urllib.error
        monkeypatch.setattr(
            client_mod, "urlopen",
            lambda req, **kw: (_ for _ in ()).throw(
                urllib.error.URLError("Connection refused")
            )
        )
        with pytest.raises(BorgUIClientError, match="Connection error"):
            client.get("/api/repositories/")

    def test_authorization_header_format(self, client, mock_urlopen):
        calls = mock_urlopen({"ok": True})
        client.get("/test")
        # Headers are stored as title-case by urllib
        auth_val = calls[0]["headers"].get("Authorization") or calls[0]["headers"].get("authorization")
        assert auth_val == "Bearer testtoken"

    def test_empty_response_returns_none(self, client, monkeypatch):
        class _EmptyResp:
            def read(self):
                return b""
        monkeypatch.setattr(client_mod, "urlopen", lambda req, **kw: _EmptyResp())
        result = client.get("/api/empty")
        assert result is None
