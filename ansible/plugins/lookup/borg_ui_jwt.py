# -*- coding: utf-8 -*-
# Copyright (c) borg-ui contributors
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Lookup plugin — mint a borg-ui JWT from a SECRET_KEY."""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r"""
name: borg_ui_jwt
author: borg-ui contributors
version_added: "1.0.0"
short_description: Mint a short-lived JWT from a borg-ui SECRET_KEY
description:
  - Generates an HS256 JWT Bearer token from the borg-ui C(SECRET_KEY).
  - The token is valid for 24 hours — long enough for any playbook run.
  - Use the token in the C(Authorization) header of C(ansible.builtin.uri)
    tasks that call the borg-ui API directly (e.g. C(POST /api/ssh-keys/quick-setup)).
  - The C(borgui.borg_ui) resource modules (C(borg_ui_repository),
    C(borg_ui_schedule), etc.) accept C(secret_key) directly and mint the
    JWT internally — you do not need this plugin for those modules.
options:
  _terms:
    description:
      - The borg-ui C(SECRET_KEY) string.
    required: true
  username:
    description:
      - Username to embed in the JWT C(sub) claim. Must match an active
        user in borg-ui (default account is C(admin)).
    type: str
    default: admin
notes:
  - The SECRET_KEY is treated as C(no_log) — mark the variable or task
    accordingly to avoid leaking it in Ansible output.
  - Uses only the Python standard library (C(hmac), C(hashlib),
    C(base64), C(json), C(time)) — no PyJWT or python-jose required.
seealso:
  - module: borgui.borg_ui.borg_ui_repository
  - module: borgui.borg_ui.borg_ui_schedule
"""

EXAMPLES = r"""
# Mint a token using a secret_key variable.
# Mark the var or the task no_log: true to avoid leaking the key.

- name: Step 1 — Deploy SSH key via borg-ui quick-setup
  ansible.builtin.uri:
    url: "{{ borgui_url }}/api/ssh-keys/quick-setup"
    method: POST
    body_format: json
    body:
      name: "web-01 key"
      host: web-01.example.com
      username: ansible
      password: "{{ target_ssh_password }}"
      port: 22
    headers:
      Authorization: "Bearer {{ lookup('borgui.borg_ui.borg_ui_jwt', borgui_key) }}"
    validate_certs: false
    status_code: [200, 201]
  no_log: true

# With a non-default username embedded in the token:
- name: Mint token for a specific borg-ui user
  ansible.builtin.set_fact:
    _api_token: >-
      {{ lookup('borgui.borg_ui.borg_ui_jwt', borgui_key,
                username='backup-operator') }}
"""

RETURN = r"""
_raw:
  description: The minted JWT Bearer token string.
  type: list
  elements: str
"""

import json
import time
import hmac
import hashlib
import base64

from ansible.errors import AnsibleError
from ansible.plugins.lookup import LookupBase
from ansible.utils.display import Display

display = Display()


def _mint_jwt(secret_key, username="admin"):
    """Mint an HS256 JWT. Mirrors app/core/security.py::create_access_token."""

    def _b64url(data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")

    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")))
    exp = int(time.time()) + 86400  # 24-hour expiry
    payload = _b64url(json.dumps({"sub": username, "exp": exp}, separators=(",", ":")))

    signing_input = "{0}.{1}".format(header, payload).encode("utf-8")
    secret = secret_key.encode("utf-8") if isinstance(secret_key, str) else secret_key
    sig = hmac.new(secret, signing_input, hashlib.sha256).digest()

    return "{0}.{1}.{2}".format(header, payload, _b64url(sig))


class LookupModule(LookupBase):

    def run(self, terms, variables=None, **kwargs):
        self.set_options(var_options=variables, direct=kwargs)

        if not terms:
            raise AnsibleError("borg_ui_jwt lookup requires exactly one argument: the SECRET_KEY")

        secret_key = terms[0]
        if not secret_key:
            raise AnsibleError("borg_ui_jwt: SECRET_KEY must not be empty")

        username = kwargs.get("username", "admin")

        try:
            token = _mint_jwt(secret_key, username=username)
        except Exception as exc:
            raise AnsibleError("borg_ui_jwt: failed to mint JWT: {0}".format(exc))

        return [token]
