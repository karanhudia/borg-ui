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
  - Create, update, or delete backup repositories in a borg-ui instance via
    the REST API.
  - A B(repository) is the Borg storage location on the borg-ui host where
    backup archives are written. Its B(label) (I(name)) is a free-form display
    name shown in the borg-ui web UI — it is B(not) a hostname or IP address.
    Convention is to use the hostname of the source machine as the label so
    repositories are easy to identify.
  - The actual source of data to back up is defined by I(source_directories).
    For remote sources accessed over SSH, link the repository to an existing
    SSH connection via I(source_connection_id).
  - Supports C(--check) (dry-run) and C(--diff) mode.
options:
  base_url:
    description:
      - Base URL of the borg-ui instance, including scheme and port.
      - "Examples: C(https://nas.example.com:8081), C(http://192.168.0.23:8081)."
    type: str
    required: true
  token:
    description:
      - Pre-existing JWT Bearer token obtained from C(POST /api/auth/login).
      - Mutually exclusive with I(secret_key) and I(secret_key_file).
    type: str
    no_log: true
  secret_key:
    description:
      - borg-ui C(SECRET_KEY) value. The module mints a short-lived JWT using
        HMAC-SHA256 — no separate login step required.
      - Store in Ansible Vault or HashiCorp Vault; never in plain text.
      - Mutually exclusive with I(token) and I(secret_key_file).
    type: str
    no_log: true
  secret_key_file:
    description:
      - Path to a file containing the borg-ui C(SECRET_KEY), one value per
        file (no trailing newline required).
      - Mutually exclusive with I(token) and I(secret_key).
    type: path
  username:
    description:
      - borg-ui username to embed in the minted JWT when using I(secret_key)
        or I(secret_key_file).
      - Must match an active user in borg-ui (default account is C(admin)).
    type: str
    default: admin
  insecure:
    description:
      - Skip TLS certificate verification.
      - Set to C(true) when borg-ui uses a self-signed certificate.
    type: bool
    default: false
  state:
    description:
      - C(present) — create the repository if it does not exist, or update it
        if any managed field has changed.
      - C(absent) — delete the repository. Fails if any schedule references
        it unless I(cascade=true).
    type: str
    default: present
    choices: [present, absent]
  name:
    description:
      - Display label for the repository as shown in the borg-ui web UI.
      - This is the B(identity key) — the module uses this label to look up
        whether the repository already exists. It is B(not) a hostname or IP.
      - Choose a short, unique, human-readable label. Convention is to use the
        hostname of the source machine (for example C(web-01) or
        C(db-primary)), but any unique string is valid.
      - "Cannot be changed after creation (it is the lookup key)."
    type: str
    required: true
  path:
    description:
      - Filesystem path on the borg-ui host where Borg will initialise and
        store the repository.
      - "Examples: C(/local/web-01), C(/mnt/backup/db-primary)."
      - Required when I(state=present).
    type: str
  encryption:
    description:
      - Borg encryption mode for the repository.
      - C(repokey) — passphrase stored inside the repository (most common).
      - C(repokey-blake2) — same as C(repokey) with BLAKE2b MAC (faster on
        modern CPUs).
      - C(keyfile) — passphrase key stored in C(~/.config/borg/keys/) on the
        borg-ui host (portable, key must be backed up separately).
      - C(keyfile-blake2) — same as C(keyfile) with BLAKE2b MAC.
      - C(authenticated) — no encryption, HMAC authentication only.
      - C(authenticated-blake2) — no encryption, BLAKE2b authentication only.
      - C(none) — no encryption and no authentication (not recommended).
    type: str
    default: repokey
    choices:
      - repokey
      - repokey-blake2
      - keyfile
      - keyfile-blake2
      - authenticated
      - authenticated-blake2
      - none
  compression:
    description:
      - Borg compression algorithm. Format is C(<algo>) or C(<algo>,<level>)
        or C(auto,<algo>) (skip compression for already-compressed data).
      - "C(auto,lz4) — fast, moderate ratio; good default."
      - "C(lz4) — very fast, low ratio."
      - "C(zstd) or C(zstd,N) — excellent ratio, levels 1–22."
      - "C(lzma) or C(lzma,N) — maximum ratio, very slow, levels 0–9."
      - "C(none) — no compression."
    type: str
    default: "auto,lz4"
  source_directories:
    description:
      - List of absolute paths on the source host to include in the backup.
      - "Example: C([/opt, /etc, /home])."
    type: list
    elements: str
    default: []
  exclude_patterns:
    description:
      - List of glob or shell patterns to exclude from the backup.
      - Patterns are matched against paths relative to each source directory.
      - "Examples: C(*.log), C(*.tmp), C(__pycache__), C(node_modules)."
    type: list
    elements: str
    default: []
  pre_backup_script:
    description:
      - Shell script to run on the borg-ui host B(before) the backup starts.
      - Use C({{ lookup('template', 'scripts/pre-backup.sh.j2') }}) to render
        a Jinja2 template on the control node and pass the result as a string.
      - Leave empty to run no pre-backup script.
    type: str
    default: ""
  post_backup_script:
    description:
      - Shell script to run on the borg-ui host B(after) the backup completes.
      - Leave empty to run no post-backup script.
    type: str
    default: ""
  hook_timeout:
    description: Global fallback timeout in seconds for hook scripts.
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
    description:
      - C(false) — abort the backup if a hook script returns a non-zero exit
        code (safe default).
      - C(true) — log the hook failure and continue with the backup anyway.
    type: bool
    default: false
  mode:
    description:
      - C(full) — borg-ui actively runs backups and tracks observability data
        (archive count, size, last run). This is the standard mode.
      - C(observe) — borg-ui monitors an existing Borg repository (tracks
        observability data) but does B(not) trigger new backups. Use this for
        repos managed externally that you want visible in the borg-ui UI.
    type: str
    default: full
    choices: [full, observe]
  bypass_lock:
    description:
      - Pass C(--bypass-lock) to Borg during backup operations.
      - Only applicable when I(mode=observe). Allows read access to a
        repository locked by another Borg process.
    type: bool
    default: false
  custom_flags:
    description:
      - Additional raw flags appended to the C(borg create) command line.
      - "Example: C(--stats --list --filter AME)."
    type: str
    default: ""
  source_connection_id:
    description:
      - Integer ID of the SSH connection in borg-ui that provides access to
        the source host (visible in C(GET /api/ssh-keys/connections)).
      - Required when backing up data from a remote host over SSH.
      - Omit for local repositories where source directories are on the
        borg-ui host itself.
      - Use M(borgui.borg_ui.borg_ui_connection) to inspect existing
        connections.
    type: int
  passphrase:
    description:
      - Borg repository passphrase.
      - Only sent during initial C(borg init) (repository creation). Ignored
        on subsequent updates — Borg stores the passphrase inside the repo.
      - Required when I(encryption) is any mode other than C(none),
        C(authenticated), or C(authenticated-blake2).
      - Store in Ansible Vault or HashiCorp Vault; never in plain text.
    type: str
    no_log: true
  cascade:
    description:
      - Controls behaviour when I(state=absent) and the repository is
        referenced by one or more schedules.
      - C(false) — fail with an error listing which schedules must be updated
        first (safe default, prevents accidental orphan schedules).
      - C(true) — automatically remove this repository from all referencing
        schedules before deleting the repository.
    type: bool
    default: false
author:
  - borg-ui contributors
seealso:
  - module: borgui.borg_ui.borg_ui_schedule
  - module: borgui.borg_ui.borg_ui_connection
"""

EXAMPLES = r"""
# ---------------------------------------------------------------------------
# Authentication — choose ONE of: token, secret_key, or secret_key_file
# ---------------------------------------------------------------------------

# Option A: SECRET_KEY (recommended for automation — no login step needed)
- name: Ensure repository for web-01 (SECRET_KEY auth)
  borgui.borg_ui.borg_ui_repository:
    base_url: https://borgui.example.com
    secret_key: "{{ lookup('community.hashi_vault.hashi_vault', 'secret/borgui:secret_key') }}"
    insecure: false
    name: web-01           # display label shown in borg-ui UI (not a hostname)
    path: /local/web-01    # where Borg stores archives on the borg-ui host
    encryption: repokey
    compression: "auto,lz4"
    source_directories:
      - /opt
      - /etc
    exclude_patterns:
      - "*.log"
      - "*.tmp"
      - "__pycache__"
    passphrase: "{{ vault_borg_passphrase }}"
    state: present

# Option B: pre-obtained JWT token
- name: Ensure repository (JWT token auth)
  borgui.borg_ui.borg_ui_repository:
    base_url: https://borgui.example.com
    token: "{{ borg_ui_jwt_token }}"
    name: web-01
    path: /local/web-01
    state: present

# ---------------------------------------------------------------------------
# Encryption examples
# ---------------------------------------------------------------------------

- name: Repository with repokey-blake2 (faster on modern CPUs)
  borgui.borg_ui.borg_ui_repository:
    base_url: https://borgui.example.com
    secret_key: "{{ borg_ui_secret_key }}"
    name: db-primary
    path: /local/db-primary
    encryption: repokey-blake2
    compression: "zstd,3"
    source_directories:
      - /var/lib/postgresql
    passphrase: "{{ vault_borg_passphrase }}"
    state: present

- name: Repository without encryption (internal network, performance-critical)
  borgui.borg_ui.borg_ui_repository:
    base_url: https://borgui.example.com
    secret_key: "{{ borg_ui_secret_key }}"
    name: scratch-host
    path: /local/scratch-host
    encryption: none
    compression: lz4
    source_directories:
      - /tmp/scratch
    state: present

# ---------------------------------------------------------------------------
# Remote source over SSH (source_connection_id)
# ---------------------------------------------------------------------------

- name: Repository backed up via SSH (source_connection_id links to SSH connection)
  borgui.borg_ui.borg_ui_repository:
    base_url: https://borgui.example.com
    secret_key: "{{ borg_ui_secret_key }}"
    name: app-server-01
    path: /local/app-server-01
    encryption: repokey
    compression: "auto,lz4"
    source_directories:
      - /opt/myapp
      - /etc
    source_connection_id: 12    # integer ID from GET /api/ssh-keys/connections
    passphrase: "{{ vault_borg_passphrase }}"
    state: present

# ---------------------------------------------------------------------------
# Pre/post backup hooks
# ---------------------------------------------------------------------------

- name: Repository with pre-backup script (inline)
  borgui.borg_ui.borg_ui_repository:
    base_url: https://borgui.example.com
    secret_key: "{{ borg_ui_secret_key }}"
    name: gitlab-01
    path: /local/gitlab-01
    encryption: repokey
    compression: "auto,lz4"
    source_directories:
      - /opt/gitlab
    pre_backup_script: |
      #!/bin/bash
      set -euo pipefail
      gitlab-backup create STRATEGY=copy
    pre_hook_timeout: 3600
    continue_on_hook_failure: false
    passphrase: "{{ vault_borg_passphrase }}"
    state: present

- name: Repository with Jinja2-templated pre-backup script
  borgui.borg_ui.borg_ui_repository:
    base_url: https://borgui.example.com
    secret_key: "{{ borg_ui_secret_key }}"
    name: vault-leader
    path: /local/vault-leader
    encryption: repokey
    compression: "auto,lz4"
    source_directories:
      - /opt/vault
    pre_backup_script: "{{ lookup('template', 'templates/borg/vault-pre-backup.sh.j2') }}"
    pre_hook_timeout: 300
    passphrase: "{{ vault_borg_passphrase }}"
    state: present

# ---------------------------------------------------------------------------
# Observe mode (monitor an externally-managed Borg repo)
# ---------------------------------------------------------------------------

- name: Register a read-only observability-only repository
  borgui.borg_ui.borg_ui_repository:
    base_url: https://borgui.example.com
    secret_key: "{{ borg_ui_secret_key }}"
    name: legacy-nas-repo
    path: /mnt/nas/legacy-borg
    encryption: repokey
    compression: none
    mode: observe
    bypass_lock: true
    state: present

# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------

- name: Remove repository (fails if a schedule still references it)
  borgui.borg_ui.borg_ui_repository:
    base_url: https://borgui.example.com
    secret_key: "{{ borg_ui_secret_key }}"
    name: web-01
    state: absent
    cascade: false    # default — safe, explicit

- name: Remove repository and automatically drop it from all schedules
  borgui.borg_ui.borg_ui_repository:
    base_url: https://borgui.example.com
    secret_key: "{{ borg_ui_secret_key }}"
    name: web-01
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
        mode=dict(type="str", default="full", choices=["full", "observe"]),
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
