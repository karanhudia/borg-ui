# -*- coding: utf-8 -*-
# Copyright (c) borg-ui contributors
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Shared HTTP client for borgui.borg_ui Ansible modules.

Uses only urllib.request — no extra Python dependencies required.
"""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import json
import ssl
import datetime

try:
    from urllib.request import urlopen, Request
    from urllib.error import HTTPError, URLError
    from urllib.parse import urlencode
except ImportError:
    # Python 2 (ansible-core still supports it for module_utils)
    from urllib2 import urlopen, Request, HTTPError, URLError
    from urllib import urlencode


class BorgUIClientError(Exception):
    """Raised on HTTP or connectivity errors from the borg-ui API."""

    def __init__(self, message, status_code=None, body=None):
        super(BorgUIClientError, self).__init__(message)
        self.status_code = status_code
        self.body = body


def _mint_jwt(secret_key, username="admin"):
    """Mint a short-lived JWT using the borg-ui SECRET_KEY (HS256).

    Replicates the logic in app/core/security.py::create_access_token.
    Uses only the stdlib — no PyJWT or python-jose required.
    """
    import hmac
    import hashlib
    import base64
    import struct
    import time

    def _b64url(data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")

    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")))
    # 24-hour expiry — long enough for any playbook run
    exp = int(time.time()) + 86400
    payload = _b64url(json.dumps({"sub": username, "exp": exp}, separators=(",", ":")))

    signing_input = "{0}.{1}".format(header, payload).encode("utf-8")
    secret = secret_key.encode("utf-8") if isinstance(secret_key, str) else secret_key
    sig = hmac.new(secret, signing_input, hashlib.sha256).digest()

    return "{0}.{1}.{2}".format(header, payload, _b64url(sig))


class BorgUIClient(object):
    """HTTP client for the borg-ui REST API.

    Authentication priority (first non-None wins):
      1. ``token``       — pre-existing JWT Bearer token
      2. ``secret_key``  — borg-ui SECRET_KEY used to mint a JWT
      3. ``secret_key_file`` — path to file containing the SECRET_KEY

    :param base_url: Base URL of the borg-ui instance (e.g. ``https://nas:8081``).
    :param token: Pre-existing JWT access token.
    :param secret_key: borg-ui SECRET_KEY string.
    :param secret_key_file: Path to file containing the SECRET_KEY.
    :param username: Username to embed in the minted JWT (default: ``admin``).
    :param insecure: If True, skip TLS certificate verification.
    :param timeout: HTTP timeout in seconds (default: 30).
    """

    def __init__(self, base_url, token=None, secret_key=None,
                 secret_key_file=None, username="admin",
                 insecure=False, timeout=30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        # Build SSL context
        if insecure:
            self._ssl_ctx = ssl.create_default_context()
            self._ssl_ctx.check_hostname = False
            self._ssl_ctx.verify_mode = ssl.CERT_NONE
        else:
            self._ssl_ctx = None

        # Resolve token
        if token:
            self._token = token
        elif secret_key:
            self._token = _mint_jwt(secret_key, username)
        elif secret_key_file:
            with open(secret_key_file, "r") as fh:
                key = fh.read().strip()
            self._token = _mint_jwt(key, username)
        else:
            raise BorgUIClientError(
                "One of token, secret_key, or secret_key_file must be provided"
            )

    def _request(self, method, path, data=None):
        url = "{0}{1}".format(self.base_url, path)
        headers = {
            "Authorization": "Bearer {0}".format(self._token),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        body = None
        if data is not None:
            body = json.dumps(data).encode("utf-8")

        req = Request(url, data=body, headers=headers)
        req.get_method = lambda: method

        try:
            kwargs = {"timeout": self.timeout}
            if self._ssl_ctx is not None:
                kwargs["context"] = self._ssl_ctx
            resp = urlopen(req, **kwargs)
            raw = resp.read()
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))
        except HTTPError as exc:
            raw = exc.read()
            body_str = raw.decode("utf-8") if raw else ""
            try:
                body_obj = json.loads(body_str)
            except (ValueError, TypeError):
                body_obj = body_str
            raise BorgUIClientError(
                "HTTP {0} from {1} {2}: {3}".format(
                    exc.code, method, url, body_str
                ),
                status_code=exc.code,
                body=body_obj,
            )
        except URLError as exc:
            raise BorgUIClientError(
                "Connection error to {0}: {1}".format(url, exc.reason)
            )

    def get(self, path):
        """HTTP GET — returns parsed JSON."""
        return self._request("GET", path)

    def post(self, path, data=None):
        """HTTP POST with JSON body — returns parsed JSON."""
        return self._request("POST", path, data=data)

    def put(self, path, data):
        """HTTP PUT with JSON body — returns parsed JSON."""
        return self._request("PUT", path, data=data)

    def patch(self, path, data):
        """HTTP PATCH with JSON body — returns parsed JSON."""
        return self._request("PATCH", path, data=data)

    def delete(self, path):
        """HTTP DELETE — returns parsed JSON or None (204)."""
        return self._request("DELETE", path)
