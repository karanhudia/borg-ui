# -*- coding: utf-8 -*-
# Copyright (c) borg-ui contributors
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Ansible module for managing borg-ui SSH connections."""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r"""
---
module: borg_ui_connection
short_description: Manage borg-ui SSH connections
version_added: "1.0.0"
description:
  - Update or delete existing SSH connections in a borg-ui instance.
  - Uses the borg-ui REST API.
  - Supports check mode for dry-run operations.
  - "SSH connections are created via the borg-ui UI (SSH Keys -> Quick Setup) or
    the quick-setup API endpoint. This module manages connections that already
    exist."
options:
  base_url:
    description: Base URL of the borg-ui instance.
    type: str
    required: true
  token:
    description: Pre-existing JWT Bearer token for authentication.
    type: str
    no_log: true
  secret_key:
    description: borg-ui SECRET_KEY used to mint a JWT on the fly.
    type: str
    no_log: true
  secret_key_file:
    description: Path to a file containing the borg-ui SECRET_KEY.
    type: path
  api_username:
    description: Username to embed in the minted JWT (borg-ui API user).
    type: str
    default: admin
  insecure:
    description: Skip TLS certificate verification.
    type: bool
    default: false
  state:
    description: Desired state of the connection.
    type: str
    default: present
    choices: [present, absent]
  host:
    description:
      - Hostname or IP of the SSH server.
      - Used together with I(ssh_username) and I(port) as the identity key.
    type: str
    required: true
  ssh_username:
    description:
      - SSH login username on the remote host.
      - Maps to the C(username) field in the borg-ui API.
    type: str
    required: true
  port:
    description: SSH port on the remote host.
    type: int
    default: 22
  use_sftp_mode:
    description: Whether to use SFTP mode for file transfers.
    type: bool
    default: false
  default_path:
    description: Default filesystem path on the remote host.
    type: str
    default: ""
  ssh_path_prefix:
    description: Path prefix prepended to SSH paths.
    type: str
    default: ""
  mount_point:
    description: Mount point for the remote filesystem.
    type: str
    default: ""
  cascade:
    description:
      - When I(state=absent), allow deletion even if repositories reference this connection.
      - "The API DELETE nulls out the foreign key references server-side."
      - If C(false) and repositories reference this connection, the module will fail.
    type: bool
    default: false
author:
  - borg-ui contributors
seealso:
  - module: borgui.borg_ui.borg_ui_repository
"""

EXAMPLES = r"""
- name: Update an SSH connection's default path
  borgui.borg_ui.borg_ui_connection:
    base_url: https://nas:8081
    token: "{{ borg_ui_token }}"
    host: backup-server.example.com
    ssh_username: ansible
    port: 22
    default_path: /opt/backups
    state: present

- name: Enable SFTP mode on a connection
  borgui.borg_ui.borg_ui_connection:
    base_url: https://nas:8081
    secret_key: "{{ borg_ui_secret_key }}"
    host: backup-server.example.com
    ssh_username: ansible
    use_sftp_mode: true
    state: present

- name: Remove a connection (fail if repositories reference it)
  borgui.borg_ui.borg_ui_connection:
    base_url: https://nas:8081
    token: "{{ borg_ui_token }}"
    host: backup-server.example.com
    ssh_username: ansible
    state: absent

- name: Remove a connection and cascade-null repository references
  borgui.borg_ui.borg_ui_connection:
    base_url: https://nas:8081
    token: "{{ borg_ui_token }}"
    host: backup-server.example.com
    ssh_username: ansible
    state: absent
    cascade: true
"""

RETURN = r"""
changed:
  description: Whether any change was made.
  type: bool
  returned: always
diff:
  description: Dictionary with before/after state for changed fields.
  type: dict
  returned: changed
  contains:
    before:
      description: Previous values of changed fields.
      type: dict
    after:
      description: New values of changed fields.
      type: dict
connection:
  description: Current state of the connection after the operation, or None if absent.
  type: dict
  returned: always
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.borgui.borg_ui.plugins.module_utils.borg_ui_common import (
    diff_dicts,
    AUTH_ARG_SPEC,
    COMMON_ARG_SPEC,
)
from ansible_collections.borgui.borg_ui.plugins.module_utils.borg_ui_client import (
    BorgUIClient,
    BorgUIClientError,
)

# Mutable fields that can be updated via PUT.
_MUTABLE_FIELDS = (
    "host",
    "username",
    "port",
    "use_sftp_mode",
    "default_path",
    "ssh_path_prefix",
    "mount_point",
)


def _build_arg_spec():
    """Return the full argument spec for this module.

    Builds from the shared AUTH_ARG_SPEC but replaces ``username`` with
    ``api_username`` (JWT minting user) and adds ``ssh_username`` (SSH login).
    """
    spec = {}
    # Pull in auth args, renaming 'username' -> 'api_username'
    for key, value in AUTH_ARG_SPEC.items():
        if key == "username":
            spec["api_username"] = dict(type="str", default="admin")
        else:
            spec[key] = value
    spec.update(COMMON_ARG_SPEC)

    # Module-specific args
    spec.update(dict(
        host=dict(type="str", required=True),
        ssh_username=dict(type="str", required=True),
        port=dict(type="int", default=22),
        use_sftp_mode=dict(type="bool", default=False),
        default_path=dict(type="str", default=""),
        ssh_path_prefix=dict(type="str", default=""),
        mount_point=dict(type="str", default=""),
        cascade=dict(type="bool", default=False),
    ))
    return spec


def _make_client(params):
    """Build a BorgUIClient, mapping api_username -> username."""
    return BorgUIClient(
        base_url=params["base_url"],
        token=params.get("token"),
        secret_key=params.get("secret_key"),
        secret_key_file=params.get("secret_key_file"),
        username=params.get("api_username", "admin"),
        insecure=params.get("insecure", False),
    )


def _find_connection(client, host, ssh_username, port):
    """Fetch all connections and return the one matching identity keys, or None."""
    resp = client.get("/api/ssh-keys/connections")
    connections = resp.get("connections", [])
    for conn in connections:
        if (conn.get("host") == host
                and conn.get("username") == ssh_username
                and conn.get("port") == port):
            return conn
    return None


def _build_payload(params):
    """Build the API request payload from module params."""
    return {
        "host": params["host"],
        "username": params["ssh_username"],
        "port": params["port"],
        "use_sftp_mode": params["use_sftp_mode"],
        "default_path": params["default_path"],
        "ssh_path_prefix": params["ssh_path_prefix"],
        "mount_point": params["mount_point"],
    }


def _needs_update(existing, desired):
    """Compare existing connection with desired state on mutable fields.

    Returns a tuple (bool, dict_before, dict_after) where the dicts contain
    only the fields that differ.
    """
    before = {}
    after = {}
    for key in _MUTABLE_FIELDS:
        existing_val = existing.get(key)
        desired_val = desired.get(key)
        if existing_val != desired_val:
            before[key] = existing_val
            after[key] = desired_val
    return bool(after), before, after


def _get_referencing_repos(client, connection_id):
    """Return list of repositories whose source_ssh_connection_id matches."""
    resp = client.get("/api/repositories/")
    repos = resp.get("repositories", [])
    return [r for r in repos if r.get("source_ssh_connection_id") == connection_id]


def _handle_present(module, client):
    """Ensure the connection exists with the desired configuration."""
    params = module.params
    host = params["host"]
    ssh_username = params["ssh_username"]
    port = params["port"]

    existing = _find_connection(client, host, ssh_username, port)

    if existing is None:
        module.fail_json(
            msg=(
                "No SSH connection exists for {0}@{1}:{2}. "
                "Create it in the borg-ui UI (SSH Keys -> Quick Setup) first, "
                "then use this module to manage its attributes."
            ).format(ssh_username, host, port)
        )

    desired = _build_payload(params)
    changed, diff_before, diff_after = _needs_update(existing, desired)

    if not changed:
        module.exit_json(changed=False, connection=existing)

    if module.check_mode:
        module.exit_json(
            changed=True,
            diff={"before": diff_before, "after": diff_after},
            connection=existing,
        )

    resp = client.put(
        "/api/ssh-keys/connections/{0}".format(existing["id"]),
        data=desired,
    )
    conn = resp.get("connection", existing)
    module.exit_json(
        changed=True,
        diff={"before": diff_before, "after": diff_after},
        connection=conn,
    )


def _handle_absent(module, client):
    """Ensure the connection does not exist."""
    params = module.params
    host = params["host"]
    ssh_username = params["ssh_username"]
    port = params["port"]

    existing = _find_connection(client, host, ssh_username, port)

    if existing is None:
        module.exit_json(changed=False, connection=None)

    connection_id = existing["id"]
    referencing = _get_referencing_repos(client, connection_id)

    if referencing and not params["cascade"]:
        repo_names = [
            r.get("name", "id={0}".format(r["id"])) for r in referencing
        ]
        module.fail_json(
            msg=(
                "Connection {0}@{1}:{2} is referenced by repository(ies): {3}. "
                "Set cascade=true to allow deletion (the API will null out "
                "foreign key references), or remove the connection from the "
                "repositories manually."
            ).format(ssh_username, host, port, ", ".join(repo_names))
        )

    if module.check_mode:
        module.exit_json(
            changed=True,
            diff={"before": existing, "after": {}},
            connection=None,
        )

    client.delete("/api/ssh-keys/connections/{0}".format(connection_id))
    module.exit_json(
        changed=True,
        diff={"before": existing, "after": {}},
        connection=None,
    )


def main():
    module = AnsibleModule(
        argument_spec=_build_arg_spec(),
        supports_check_mode=True,
        mutually_exclusive=[
            ("token", "secret_key", "secret_key_file"),
        ],
        required_one_of=[
            ("token", "secret_key", "secret_key_file"),
        ],
    )

    try:
        client = _make_client(module.params)
    except (ValueError, BorgUIClientError) as exc:
        module.fail_json(msg=str(exc))

    try:
        if module.params["state"] == "present":
            _handle_present(module, client)
        else:
            _handle_absent(module, client)
    except BorgUIClientError as exc:
        module.fail_json(
            msg="borg-ui API error: {0}".format(str(exc)),
            status_code=getattr(exc, "status_code", None),
            body=getattr(exc, "body", None),
        )


if __name__ == "__main__":
    main()
