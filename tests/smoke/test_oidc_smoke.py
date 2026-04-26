#!/usr/bin/env python3
"""Black-box smoke coverage for built-in OIDC login against a local mock provider."""

from __future__ import annotations

import argparse
import base64
import json
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.utils import base64url_encode

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.smoke.live_helpers import SmokeClient, SmokeFailure


def _rsa_keypair() -> tuple[Any, dict[str, str]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_numbers = private_key.public_key().public_numbers()
    jwk = {
        "kty": "RSA",
        "kid": "smoke-key",
        "use": "sig",
        "alg": "RS256",
        "n": base64url_encode(
            public_numbers.n.to_bytes((public_numbers.n.bit_length() + 7) // 8, "big")
        ).decode("ascii"),
        "e": base64url_encode(
            public_numbers.e.to_bytes((public_numbers.e.bit_length() + 7) // 8, "big")
        ).decode("ascii"),
    }
    return private_key, jwk


class MockOidcProvider:
    def __init__(self) -> None:
        self.private_key, self.jwk = _rsa_keypair()
        self.codes: dict[str, dict[str, str]] = {}
        self.user = {
            "sub": "smoke-user-subject",
            "preferred_username": "oidc-smoke",
            "email": "oidc-smoke@example.com",
            "name": "OIDC Smoke User",
        }
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        provider = self

        class Handler(BaseHTTPRequestHandler):
            def _json(self, payload: dict[str, Any], status: int = 200) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path == "/.well-known/openid-configuration":
                    issuer = provider.issuer
                    self._json(
                        {
                            "issuer": issuer,
                            "authorization_endpoint": f"{issuer}/authorize",
                            "token_endpoint": f"{issuer}/token",
                            "userinfo_endpoint": f"{issuer}/userinfo",
                            "jwks_uri": f"{issuer}/jwks",
                            "end_session_endpoint": f"{issuer}/logout",
                        }
                    )
                    return
                if parsed.path == "/jwks":
                    self._json({"keys": [provider.jwk]})
                    return
                if parsed.path == "/authorize":
                    query = parse_qs(parsed.query)
                    state = query["state"][0]
                    nonce = query["nonce"][0]
                    redirect_uri = query["redirect_uri"][0]
                    code = f"code-{len(provider.codes) + 1}"
                    provider.codes[code] = {
                        "nonce": nonce,
                        "code_challenge": query["code_challenge"][0],
                        "client_id": query["client_id"][0],
                    }
                    location = (
                        f"{redirect_uri}?{urlencode({'code': code, 'state': state})}"
                    )
                    self.send_response(HTTPStatus.FOUND)
                    self.send_header("Location", location)
                    self.end_headers()
                    return
                if parsed.path == "/userinfo":
                    self._json(provider.user)
                    return
                if parsed.path == "/logout":
                    query = parse_qs(parsed.query)
                    location = query.get("post_logout_redirect_uri", ["/"])[0]
                    self.send_response(HTTPStatus.FOUND)
                    self.send_header("Location", location)
                    self.end_headers()
                    return
                self.send_error(HTTPStatus.NOT_FOUND)

            def do_POST(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path != "/token":
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                length = int(self.headers.get("Content-Length", "0"))
                payload = parse_qs(
                    self.rfile.read(length).decode("utf-8"),
                    keep_blank_values=True,
                )
                code = payload["code"][0]
                code_verifier = payload["code_verifier"][0]
                code_data = provider.codes.pop(code, None)
                if code_data is None:
                    self._json({"error": "invalid_grant"}, status=400)
                    return
                expected_challenge = (
                    base64.urlsafe_b64encode(
                        __import__("hashlib")
                        .sha256(code_verifier.encode("ascii"))
                        .digest()
                    )
                    .decode("ascii")
                    .rstrip("=")
                )
                if expected_challenge != code_data["code_challenge"]:
                    self._json({"error": "invalid_grant"}, status=400)
                    return

                now = int(time.time())
                id_token = jwt.encode(
                    {
                        **provider.user,
                        "iss": provider.issuer,
                        "aud": code_data["client_id"],
                        "iat": now,
                        "exp": now + 300,
                        "nonce": code_data["nonce"],
                    },
                    provider.private_key,
                    algorithm="RS256",
                    headers={"kid": provider.jwk["kid"]},
                )
                self._json(
                    {
                        "access_token": "mock-access-token",
                        "id_token": id_token,
                        "token_type": "Bearer",
                        "expires_in": 300,
                    }
                )

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
                return

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        host, port = self.httpd.server_address
        self.issuer = f"http://{host}:{port}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
        if self.thread is not None:
            self.thread.join(timeout=5)


def configure_oidc(client: SmokeClient, discovery_url: str) -> None:
    response = client.request_ok("GET", "/api/settings/system")
    current = response.json().get("settings", {})
    payload = {
        "oidc_enabled": True,
        "oidc_disable_local_auth": True,
        "oidc_provider_name": "Smoke OIDC",
        "oidc_discovery_url": discovery_url,
        "oidc_client_id": "borg-ui-smoke",
        "oidc_client_secret": "smoke-secret",
        "oidc_scopes": "openid profile email",
        "oidc_claim_username": "preferred_username",
        "oidc_claim_email": "email",
        "oidc_claim_full_name": "name",
        "oidc_new_user_mode": "viewer",
        "oidc_default_role": "viewer",
        "oidc_default_all_repositories_role": "viewer",
        "metrics_enabled": current.get("metrics_enabled", False),
        "metrics_require_auth": current.get("metrics_require_auth", False),
        "mqtt_password": "",
    }
    client.request_ok(
        "PUT",
        "/api/settings/system",
        headers=client._headers(json_body=True),
        json=payload,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run built-in OIDC smoke test")
    parser.add_argument("--url", default="http://localhost:8082")
    args = parser.parse_args()

    client = SmokeClient(args.url)
    provider = MockOidcProvider()
    try:
        provider.start()
        client.authenticate()
        configure_oidc(client, f"{provider.issuer}/.well-known/openid-configuration")

        auth_config = client.request_ok("GET", "/api/auth/config").json()
        if not auth_config.get("oidc_enabled"):
            raise SmokeFailure("OIDC smoke expected oidc_enabled=true in auth config")

        callback_target = f"{args.url.rstrip('/')}/login"
        login_response = client.session.get(
            f"{args.url.rstrip('/')}/api/auth/oidc/login",
            params={"return_to": callback_target},
            allow_redirects=True,
            timeout=30,
        )
        final_url = login_response.url
        parsed_final = urlparse(final_url)
        if not parsed_final.path.endswith("/login"):
            raise SmokeFailure(
                f"Expected final OIDC redirect to /login, got {final_url}"
            )
        query = parse_qs(parsed_final.query)
        if query.get("oidc", [None])[0] != "complete":
            raise SmokeFailure(
                f"OIDC smoke missing completion marker in final URL: {final_url}"
            )

        exchange_response = client.request_ok(
            "POST",
            "/api/auth/oidc/exchange",
            headers={**client._headers(json_body=True), "Origin": args.url.rstrip("/")},
        )
        app_token = exchange_response.json()["access_token"]

        profile_response = client.request_ok("GET", "/api/auth/me", token=app_token)
        profile = profile_response.json()
        if profile["username"] != "oidc-smoke":
            raise SmokeFailure(f"Expected oidc-smoke profile, got {profile}")

        events_response = client.request_ok(
            "GET", "/api/auth/events", params={"limit": 20}
        )
        events = events_response.json()
        if not any(event["event_type"] == "oidc_login_succeeded" for event in events):
            raise SmokeFailure(
                "Expected oidc_login_succeeded auth event after OIDC smoke"
            )

        client.log("OIDC smoke passed")
        return 0
    finally:
        provider.stop()
        client.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
