# -*- coding: utf-8 -*-
# Copyright (c) borg-ui contributors
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Ansible module for managing borg-ui backup repositories."""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r"""
---
module: borg_ui_repository
short_description: Manage borg-ui backup repositories
version_added: "1.0.0"
description:
  - Create, update, or delete backup repositories in a borg-ui instance.
  - Uses the borg-ui REST API.
  - Supports check mode for dry-run operations.
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
  username:
    description: Username to embed in the minted JWT.
    type: str
    default: admin
  insecure:
    description: Skip TLS certificate verification.
    type: bool
    default: false
  state:
    description: Desired state of the repository.
    type: str
    default: present
    choices: [present, absent]
  name:
    description:
      - Name of the repository.
      - Used as the identity key for lookup.
    type: str
    required: true
  path:
    description:
      - Filesystem path where the repository is stored.
      - Required when I(state=present).
    type: str
  encryption:
    description: Encryption mode for the repository.
    type: str
    default: repokey
  compression:
    description: Compression algorithm specification.
    type: str
    default: "auto,lz4"
  source_directories:
    description: List of directories to back up.
    type: list
    elements: str
    default: []
  exclude_patterns:
    description: List of glob patterns to exclude from backups.
    type: list
    elements: str
    default: []
  pre_backup_script:
    description: Script to run before backup starts.
    type: str
    default: ""
  post_backup_script:
    description: Script to run after backup completes.
    type: str
    default: ""
  hook_timeout:
    description: Timeout in seconds for hook scripts.
    type: int
    default: 300
  pre_hook_timeout:
    description: Timeout in seconds for the pre-backup hook script.
    type: int
    default: 300
  post_hook_timeout:
    description: Timeout in seconds for the post-backup hook script.
    type: int
    default: 300
  continue_on_hook_failure:
    description: Whether to continue the backup if a hook script fails.
    type: bool
    default: false
  mode:
    description: Backup mode.
    type: str
    default: full
    choices: [full, partial]
  bypass_lock:
    description: Whether to bypass the repository lock.
    type: bool
    default: false
  custom_flags:
    description: Additional borg flags to pass during backup.
    type: str
    default: ""
  source_connection_id:
    description: SSH connection ID for remote source directories.
    type: int
  passphrase:
    description:
      - Repository encryption passphrase.
      - Only used during repository creation; ignored on updates.
    type: str
    no_log: true
  cascade:
    description:
      - When I(state=absent), cascade-delete schedules that reference this repository.
      - If C(false) and schedules reference this repository, the module will fail.
    type: bool
    default: false
author:
  - borg-ui contributors
seealso:
  - module: borgui.borg_ui.borg_ui_schedule
"""

EXAMPLES = r"""
- name: Create a local backup repository
  borgui.borg_ui.borg_ui_repository:
    base_url: https://nas:8081
    token: "{{ borg_ui_token }}"
    name: vault-01
    path: /backups/vault-01
    encryption: repokey
    compression: "auto,lz4"
    source_directories:
      - /opt
    exclude_patterns:
      - "*.log"
    passphrase: "{{ borg_passphrase }}"
    state: present

- name: Update repository compression
  borgui.borg_ui.borg_ui_repository:
    base_url: https://nas:8081
    secret_key: "{{ borg_ui_secret_key }}"
    name: vault-01
    path: /backups/vault-01
    compression: "auto,zstd,3"
    state: present

- name: Remove a repository (fail if schedules reference it)
  borgui.borg_ui.borg_ui_repository:
    base_url: https://nas:8081
    token: "{{ borg_ui_token }}"
    name: vault-01
    state: absent

- name: Remove a repository and cascade-delete referencing schedules
  borgui.borg_ui.borg_ui_repository:
    base_url: https://nas:8081
    token: "{{ borg_ui_token }}"
    name: vault-01
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
repository:
  description: Current state of the repository after the operation.
  type: dict
  returned: state=present
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.borgui.borg_ui.plugins.module_utils.borg_ui_common import (
    make_client,
    diff_dicts,
    arg_spec_with_auth_and_state,
)
from ansible_collections.borgui.borg_ui.plugins.module_utils.borg_ui_client import (
    BorgUIClientError,
)

# Fields to compare when determining if an update is needed.
# Excludes read-only / server-managed fields.
_IGNORE_FIELDS = frozenset({
    "id",
    "last_backup",
    "last_backup_duration",
    "last_backup_size",
    "last_backup_status",
    "last_check",
    "last_prune",
    "last_compact",
    "backup_count",
    "total_size",
    "created_at",
    "updated_at",
    "repository_type",
    "host",
    "port",
    "username",
    "ssh_key_id",
    "remote_path",
    "has_keyfile",
    "has_running_maintenance",
})

# Fields sent in the API body for create/update.
_MUTABLE_FIELDS = (
    "name",
    "path",
    "encryption",
    "compression",
    "source_directories",
    "exclude_patterns",
    "pre_backup_script",
    "post_backup_script",
    "hook_timeout",
    "pre_hook_timeout",
    "post_hook_timeout",
    "continue_on_hook_failure",
    "mode",
    "bypass_lock",
    "custom_flags",
    "source_connection_id",
)


def _build_arg_spec():
    """Return the full argument spec for this module."""
    return arg_spec_with_auth_and_state(
        name=dict(type="str", required=True),
        path=dict(type="str"),
        encryption=dict(type="str", default="repokey"),
        compression=dict(type="str", default="auto,lz4"),
        source_directories=dict(type="list", elements="str", default=[]),
        exclude_patterns=dict(type="list", elements="str", default=[]),
        pre_backup_script=dict(type="str", default=""),
        post_backup_script=dict(type="str", default=""),
        hook_timeout=dict(type="int", default=300),
        pre_hook_timeout=dict(type="int", default=300),
        post_hook_timeout=dict(type="int", default=300),
        continue_on_hook_failure=dict(type="bool", default=False),
        mode=dict(type="str", default="full", choices=["full", "partial"]),
        bypass_lock=dict(type="bool", default=False),
        custom_flags=dict(type="str", default=""),
        source_connection_id=dict(type="int"),
        passphrase=dict(type="str", no_log=True),
        cascade=dict(type="bool", default=False),
    )


def _find_repo_by_name(client, name):
    """Fetch all repositories and return the one matching *name*, or None."""
    resp = client.get("/api/repositories/")
    repositories = resp.get("repositories", [])
    for repo in repositories:
        if repo.get("name") == name:
            return repo
    return None


def _build_payload(params):
    """Build the API request payload from module params."""
    payload = {}
    for field in _MUTABLE_FIELDS:
        value = params.get(field)
        if value is not None:
            payload[field] = value
        elif field in ("source_directories", "exclude_patterns"):
            payload[field] = []
        elif field in ("pre_backup_script", "post_backup_script", "custom_flags"):
            payload[field] = ""
        elif field == "source_connection_id":
            payload[field] = None
    return payload


def _needs_update(existing, desired):
    """Compare existing repo state with desired state, ignoring server-managed fields.

    Returns a tuple (bool, dict_before, dict_after) where the dicts contain
    only the fields that differ.
    """
    before = {}
    after = {}
    for key, desired_val in desired.items():
        if key in _IGNORE_FIELDS:
            continue
        existing_val = existing.get(key)
        if existing_val != desired_val:
            before[key] = existing_val
            after[key] = desired_val
    return bool(after), before, after


def _get_referencing_schedules(client, repo_id):
    """Return list of schedules whose repository_ids include *repo_id*."""
    resp = client.get("/api/schedule/")
    jobs = resp.get("jobs", [])
    referencing = []
    for job in jobs:
        if repo_id in (job.get("repository_ids") or []):
            referencing.append(job)
    return referencing


def _cascade_delete_schedules(client, repo_id, check_mode):
    """Remove *repo_id* from all referencing schedules.

    If a schedule ends up with no repositories, delete it entirely.
    """
    schedules = _get_referencing_schedules(client, repo_id)
    for schedule in schedules:
        remaining = [rid for rid in schedule["repository_ids"] if rid != repo_id]
        if check_mode:
            continue
        if not remaining:
            client.delete("/api/schedule/{0}".format(schedule["id"]))
        else:
            client.put(
                "/api/schedule/{0}".format(schedule["id"]),
                {"repository_ids": remaining},
            )


def _handle_present(module, client):
    """Ensure the repository exists with the desired configuration."""
    params = module.params
    name = params["name"]

    if not params.get("path"):
        module.fail_json(msg="'path' is required when state=present")

    existing = _find_repo_by_name(client, name)
    desired = _build_payload(params)

    if existing is None:
        # Create
        create_payload = dict(desired)
        if params.get("passphrase"):
            create_payload["passphrase"] = params["passphrase"]

        if module.check_mode:
            module.exit_json(
                changed=True,
                diff={"before": {}, "after": desired},
                repository=desired,
            )

        resp = client.post("/api/repositories/", data=create_payload)
        repo = resp.get("repository", desired)
        module.exit_json(
            changed=True,
            diff={"before": {}, "after": desired},
            repository=repo,
        )
    else:
        # Update if needed
        changed, diff_before, diff_after = _needs_update(existing, desired)

        if not changed:
            module.exit_json(changed=False, repository=existing)

        if module.check_mode:
            module.exit_json(
                changed=True,
                diff={"before": diff_before, "after": diff_after},
                repository=existing,
            )

        resp = client.put(
            "/api/repositories/{0}".format(existing["id"]),
            data=desired,
        )
        repo = resp.get("repository", existing)
        module.exit_json(
            changed=True,
            diff={"before": diff_before, "after": diff_after},
            repository=repo,
        )


def _handle_absent(module, client):
    """Ensure the repository does not exist."""
    params = module.params
    name = params["name"]

    existing = _find_repo_by_name(client, name)

    if existing is None:
        module.exit_json(changed=False)

    repo_id = existing["id"]
    referencing = _get_referencing_schedules(client, repo_id)

    if referencing and not params["cascade"]:
        schedule_names = [s.get("name", "id={0}".format(s["id"])) for s in referencing]
        module.fail_json(
            msg=(
                "Repository '{0}' is referenced by schedule(s): {1}. "
                "Set cascade=true to remove these references, or remove "
                "the repository from the schedules manually."
            ).format(name, ", ".join(schedule_names))
        )

    if module.check_mode:
        module.exit_json(
            changed=True,
            diff={"before": existing, "after": {}},
        )

    if referencing and params["cascade"]:
        _cascade_delete_schedules(client, repo_id, check_mode=False)

    client.delete("/api/repositories/{0}".format(repo_id))
    module.exit_json(
        changed=True,
        diff={"before": existing, "after": {}},
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
        client = make_client(module.params)
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
