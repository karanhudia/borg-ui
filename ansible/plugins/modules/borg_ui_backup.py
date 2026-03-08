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
  - This module is B(NOT) idempotent by design — every invocation with
    C(action=start) creates a new backup run.
  - Supports check mode (action=start will report changed=True without
    actually triggering a backup).
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
  repository:
    description:
      - Name of the repository to back up.
      - The module resolves this name to a repository path via the
        C(GET /api/repositories/) endpoint.
      - Required when I(action=start).
    type: str
  action:
    description:
      - The backup action to perform.
      - C(start) triggers a new backup job.
      - C(status) queries the status of an existing job.
      - C(cancel) reports that cancellation is not supported via the API.
    type: str
    required: true
    choices: [start, status, cancel]
  job_id:
    description:
      - Backup job ID.
      - Required when I(action=status) or I(action=cancel).
    type: int
  wait:
    description:
      - Wait for the backup job to complete before returning.
      - Only valid with I(action=start).
    type: bool
    default: false
  wait_timeout:
    description:
      - Maximum time in seconds to wait for backup completion.
      - Only used when I(wait=true).
    type: int
    default: 3600
  poll_interval:
    description:
      - Seconds between status polls when I(wait=true).
    type: int
    default: 5
notes:
  - This module is NOT idempotent. Each C(action=start) invocation creates
    a new backup run.
  - The borg-ui API does not expose a cancel endpoint.
    C(action=cancel) returns a descriptive message without making changes.
author:
  - borg-ui contributors
seealso:
  - module: borgui.borg_ui.borg_ui_repository
  - module: borgui.borg_ui.borg_ui_schedule
"""

EXAMPLES = r"""
- name: Start a backup and return immediately
  borgui.borg_ui.borg_ui_backup:
    base_url: https://nas:8081
    token: "{{ borg_ui_token }}"
    repository: vault-01
    action: start

- name: Start a backup and wait for completion
  borgui.borg_ui.borg_ui_backup:
    base_url: https://nas:8081
    token: "{{ borg_ui_token }}"
    repository: vault-01
    action: start
    wait: true
    wait_timeout: 7200
    poll_interval: 10
  register: backup_result

- name: Check status of a running backup
  borgui.borg_ui.borg_ui_backup:
    base_url: https://nas:8081
    token: "{{ borg_ui_token }}"
    action: status
    job_id: 42

- name: Attempt to cancel a backup (informational only)
  borgui.borg_ui.borg_ui_backup:
    base_url: https://nas:8081
    token: "{{ borg_ui_token }}"
    action: cancel
    job_id: 42
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
