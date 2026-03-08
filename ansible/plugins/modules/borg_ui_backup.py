# -*- coding: utf-8 -*-
# Copyright (c) borg-ui contributors
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Ansible module for triggering and monitoring borg-ui backup runs."""

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r"""
---
module: borg_ui_backup
short_description: Trigger, monitor, or check borg-ui backup runs
version_added: "1.0.0"
description:
  - Start a backup job, poll its status, or request cancellation via the
    borg-ui REST API.
  - B(This module is NOT idempotent.) Every C(action=start) invocation
    creates a new backup run regardless of whether one recently completed.
    Use M(borgui.borg_ui.borg_ui_schedule) to manage scheduled recurring
    backups instead.
  - The I(repository) parameter takes the repository B(label) (the I(name)
    field set in M(borgui.borg_ui.borg_ui_repository)), B(not) a filesystem
    path or hostname. The module resolves the label to a path internally.
  - Supports C(--check) mode: C(action=start) reports C(changed=True) without
    actually triggering a backup.
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
      - borg-ui C(SECRET_KEY) value. The module mints a short-lived JWT —
        no separate login step required.
      - Mutually exclusive with I(token) and I(secret_key_file).
    type: str
    no_log: true
  secret_key_file:
    description:
      - Path to a file containing the borg-ui C(SECRET_KEY).
      - Mutually exclusive with I(token) and I(secret_key).
    type: path
  username:
    description:
      - borg-ui username to embed in the minted JWT. Must match an active
        user in borg-ui (default account is C(admin)).
    type: str
    default: admin
  insecure:
    description:
      - Skip TLS certificate verification. Set C(true) for self-signed certs.
    type: bool
    default: false
  repository:
    description:
      - The B(label) (I(name) field) of the repository to back up — B(not) a
        filesystem path or hostname.
      - "Example: C(web-01) (as created by M(borgui.borg_ui.borg_ui_repository))."
      - The module resolves this label to the repository path via
        C(GET /api/repositories/) and passes the path to the backup API.
      - Required when I(action=start).
    type: str
  action:
    description:
      - C(start) — trigger a new on-demand backup job for I(repository).
        Returns a I(job_id) immediately; use I(wait=true) to block until
        completion.
      - C(status) — query the current status of an existing job by I(job_id).
        Does not change anything (C(changed=False)).
      - C(cancel) — informational only. The borg-ui API does not expose a
        cancel endpoint; the module returns a message explaining this without
        making any changes.
    type: str
    required: true
    choices: [start, status, cancel]
  job_id:
    description:
      - Integer ID of the backup job to inspect or cancel.
      - Required when I(action=status) or I(action=cancel).
      - Returned as I(job_id) in the result of a previous C(action=start)
        call.
    type: int
  wait:
    description:
      - C(false) — start the backup job and return immediately with the
        I(job_id). The backup continues in the background.
      - C(true) — poll the job status every I(poll_interval) seconds until it
        reaches a terminal state (C(completed), C(failed), C(error)) or
        I(wait_timeout) is exceeded.
      - Only valid when I(action=start).
    type: bool
    default: false
  wait_timeout:
    description:
      - Maximum number of seconds to wait for backup completion when
        I(wait=true). The module fails if this limit is exceeded.
    type: int
    default: 3600
  poll_interval:
    description:
      - Seconds between status-poll API calls when I(wait=true).
      - Lower values give faster feedback but increase API load.
    type: int
    default: 5
notes:
  - Use M(borgui.borg_ui.borg_ui_schedule) for recurring, scheduled backups.
    This module is intended for on-demand runs, post-deploy triggers, and
    maintenance workflows.
  - The borg-ui API does not expose a job cancel endpoint.
    C(action=cancel) returns an informational message only.
author:
  - borg-ui contributors
seealso:
  - module: borgui.borg_ui.borg_ui_repository
  - module: borgui.borg_ui.borg_ui_schedule
"""

EXAMPLES = r"""
# repository: is the label (name) of the repository, not a path or hostname

- name: Trigger an on-demand backup and return immediately
  borgui.borg_ui.borg_ui_backup:
    base_url: https://borgui.example.com
    secret_key: "{{ lookup('community.hashi_vault.hashi_vault', 'secret/borgui:secret_key') }}"
    repository: web-01    # label as set in borg_ui_repository
    action: start
  register: backup_job

- name: Show the job ID for monitoring
  ansible.builtin.debug:
    msg: "Backup started — job_id={{ backup_job.job_id }}"

- name: Trigger backup and wait for it to finish (up to 2 hours)
  borgui.borg_ui.borg_ui_backup:
    base_url: https://borgui.example.com
    secret_key: "{{ borg_ui_secret_key }}"
    repository: db-primary
    action: start
    wait: true
    wait_timeout: 7200
    poll_interval: 15
  register: backup_result

- name: Fail if backup did not succeed
  ansible.builtin.assert:
    that:
      - backup_result.status == "completed"
    fail_msg: "Backup ended with status={{ backup_result.status }}"

- name: Check the status of a running or recent backup job
  borgui.borg_ui.borg_ui_backup:
    base_url: https://borgui.example.com
    secret_key: "{{ borg_ui_secret_key }}"
    action: status
    job_id: "{{ backup_job.job_id }}"
  register: status_result

- name: Attempt to cancel a backup (informational — API does not support it)
  borgui.borg_ui.borg_ui_backup:
    base_url: https://borgui.example.com
    secret_key: "{{ borg_ui_secret_key }}"
    action: cancel
    job_id: "{{ backup_job.job_id }}"
"""

RETURN = r"""
changed:
  description: Whether a change was made (always True for action=start).
  type: bool
  returned: always
job_id:
  description: The backup job ID.
  type: int
  returned: action=start or action=status or action=cancel
status:
  description: Current status of the backup job.
  type: str
  returned: action=start or action=status
  sample: completed
message:
  description: Human-readable message from the API or module.
  type: str
  returned: action=start or action=cancel
logs:
  description: Backup log output.
  type: str
  returned: when wait=true and backup completed
progress:
  description: Progress percentage.
  type: int
  returned: action=status
progress_details:
  description: Detailed progress information.
  type: dict
  returned: when available
  contains:
    original_size:
      description: Original data size in bytes.
      type: int
    compressed_size:
      description: Compressed data size in bytes.
      type: int
    deduplicated_size:
      description: Deduplicated data size in bytes.
      type: int
    nfiles:
      description: Number of files processed.
      type: int
    current_file:
      description: File currently being processed.
      type: str
    progress_percent:
      description: Overall progress percentage.
      type: int
    backup_speed:
      description: Backup speed in bytes per second.
      type: float
    total_expected_size:
      description: Total expected data size in bytes.
      type: int
    estimated_time_remaining:
      description: Estimated seconds remaining.
      type: int
"""

import time

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.borgui.borg_ui.plugins.module_utils.borg_ui_common import (
    make_client,
    AUTH_ARG_SPEC,
)
from ansible_collections.borgui.borg_ui.plugins.module_utils.borg_ui_client import (
    BorgUIClientError,
)


def _build_arg_spec():
    """Return the full argument spec for this module."""
    spec = {}
    spec.update(AUTH_ARG_SPEC)
    spec.update(
        repository=dict(type="str"),
        action=dict(type="str", required=True, choices=["start", "status", "cancel"]),
        job_id=dict(type="int"),
        wait=dict(type="bool", default=False),
        wait_timeout=dict(type="int", default=3600),
        poll_interval=dict(type="int", default=5),
    )
    return spec


def _resolve_repo_path(client, name):
    """Resolve a repository name to its path via GET /api/repositories/.

    :returns: Repository path string.
    :raises BorgUIClientError: if the repository is not found.
    """
    resp = client.get("/api/repositories/")
    repositories = resp.get("repositories", [])
    for repo in repositories:
        if repo.get("name") == name:
            return repo["path"]
    raise BorgUIClientError(
        "Repository '{0}' not found. Available repositories: {1}".format(
            name,
            ", ".join(r.get("name", "?") for r in repositories) or "(none)",
        )
    )


def _poll_until_complete(module, client, job_id, timeout, interval):
    """Poll backup status until terminal state or timeout.

    :returns: Final status response dict.
    """
    start_time = time.time()
    last_resp = None

    while True:
        elapsed = time.time() - start_time
        if elapsed >= timeout:
            module.fail_json(
                msg="Timed out waiting for backup job {0} after {1}s. "
                    "Last known status: {2}".format(
                        job_id, timeout,
                        last_resp.get("status", "unknown") if last_resp else "unknown",
                    ),
                job_id=job_id,
                status=last_resp.get("status") if last_resp else "unknown",
            )

        last_resp = client.get("/api/backup/status/{0}".format(job_id))
        status = last_resp.get("status", "unknown")

        if status == "completed":
            return last_resp
        elif status == "failed":
            module.fail_json(
                msg="Backup job {0} failed: {1}".format(
                    job_id,
                    last_resp.get("error_message", "no error details"),
                ),
                job_id=job_id,
                status="failed",
                logs=last_resp.get("logs"),
                progress_details=last_resp.get("progress_details"),
            )
        elif status == "cancelled":
            return last_resp

        time.sleep(interval)


def _handle_start(module, client):
    """Handle action=start."""
    params = module.params
    name = params.get("repository")

    if not name:
        module.fail_json(msg="'repository' is required when action=start")

    repo_path = _resolve_repo_path(client, name)

    if module.check_mode:
        module.exit_json(
            changed=True,
            message="Backup job would be started for repository '{0}'".format(name),
        )

    resp = client.post("/api/backup/start", data={"repository": repo_path})
    job_id = resp.get("job_id")
    status = resp.get("status", "pending")
    message = resp.get("message", "Backup job started")

    if not params.get("wait"):
        module.exit_json(
            changed=True,
            job_id=job_id,
            status=status,
            message=message,
        )

    # Wait for completion
    final = _poll_until_complete(
        module, client, job_id,
        timeout=params["wait_timeout"],
        interval=params["poll_interval"],
    )
    module.exit_json(
        changed=True,
        job_id=job_id,
        status=final.get("status"),
        message=message,
        logs=final.get("logs"),
        progress_details=final.get("progress_details"),
    )


def _handle_status(module, client):
    """Handle action=status."""
    job_id = module.params.get("job_id")
    if job_id is None:
        module.fail_json(msg="'job_id' is required when action=status")

    resp = client.get("/api/backup/status/{0}".format(job_id))
    module.exit_json(
        changed=False,
        job_id=job_id,
        status=resp.get("status"),
        progress=resp.get("progress"),
        progress_details=resp.get("progress_details"),
    )


def _handle_cancel(module):
    """Handle action=cancel."""
    job_id = module.params.get("job_id")
    if job_id is None:
        module.fail_json(msg="'job_id' is required when action=cancel")

    module.exit_json(
        changed=False,
        job_id=job_id,
        message="Cancel not supported via API; stop the borg-ui backup "
                "service to interrupt running jobs.",
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

    action = module.params["action"]

    # action=cancel needs no client
    if action == "cancel":
        _handle_cancel(module)
        return

    try:
        client = make_client(module.params)
    except (ValueError, BorgUIClientError) as exc:
        module.fail_json(msg=str(exc))

    try:
        if action == "start":
            _handle_start(module, client)
        elif action == "status":
            _handle_status(module, client)
    except BorgUIClientError as exc:
        module.fail_json(
            msg="borg-ui API error: {0}".format(str(exc)),
            status_code=getattr(exc, "status_code", None),
            body=getattr(exc, "body", None),
        )


if __name__ == "__main__":
    main()
